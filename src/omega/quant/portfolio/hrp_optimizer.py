from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.optimize import Bounds, LinearConstraint, minimize
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf


@dataclass(frozen=True)
class HRPOptimizationConfig:
    covariance_lookback: int = 252
    min_observations: int = 60
    max_position: float = 0.10
    factor_bound: float = 0.05


def _nearest_psd(matrix: np.ndarray) -> np.ndarray:
    sym = 0.5 * (matrix + matrix.T)
    eigvals, eigvecs = np.linalg.eigh(sym)
    eigvals = np.clip(eigvals, 0.0, None)
    psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    psd = 0.5 * (psd + psd.T)
    np.fill_diagonal(psd, np.maximum(np.diag(psd), 1e-12))
    return psd


def estimate_shrunk_covariance(
    returns_window: pd.DataFrame,
    *,
    min_observations: int = 60,
    min_assets_for_shrinkage: int = 5,
) -> pd.DataFrame:
    clean = returns_window.copy().replace([np.inf, -np.inf], np.nan)
    clean = clean.tail(max(min_observations, len(clean.index)))
    if clean.empty:
        return pd.DataFrame()
    variances = clean.var(ddof=0).fillna(0.0).clip(lower=1e-12)
    sufficient_obs = clean.notna().sum().ge(min_observations)
    if len(clean.columns) < min_assets_for_shrinkage or not bool(sufficient_obs.all()):
        cov = np.diag(variances.to_numpy(dtype=float))
    else:
        filled = clean.fillna(0.0).to_numpy(dtype=float)
        try:
            cov = LedoitWolf().fit(filled).covariance_
        except Exception:
            cov = np.diag(variances.to_numpy(dtype=float))
    cov = _nearest_psd(np.asarray(cov, dtype=float))
    assert np.allclose(cov, cov.T, atol=1e-8)
    assert np.linalg.eigvalsh(cov).min() >= -1e-8
    return pd.DataFrame(cov, index=clean.columns, columns=clean.columns)


def _correlation_distance(cov: pd.DataFrame) -> np.ndarray:
    vol = np.sqrt(np.clip(np.diag(cov.to_numpy(dtype=float)), 1e-12, None))
    corr = cov.to_numpy(dtype=float) / np.outer(vol, vol)
    corr = np.clip(corr, -1.0, 1.0)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, 1.0))
    np.fill_diagonal(dist, 0.0)
    return dist


def _cluster_variance(cov: pd.DataFrame, assets: list[str]) -> float:
    sub_cov = cov.loc[assets, assets].to_numpy(dtype=float)
    inv_diag = 1.0 / np.clip(np.diag(sub_cov), 1e-12, None)
    weights = inv_diag / inv_diag.sum()
    return float(weights @ sub_cov @ weights)


def compute_hrp_weights(covariance: pd.DataFrame) -> pd.Series:
    if covariance.empty:
        return pd.Series(dtype=float)
    if len(covariance.index) == 1:
        return pd.Series(1.0, index=covariance.index, dtype=float)
    dist = _correlation_distance(covariance)
    condensed = squareform(dist, checks=False)
    linkage_matrix = linkage(condensed, method="single")
    order = covariance.index[leaves_list(linkage_matrix)].tolist()
    weights = pd.Series(1.0, index=order, dtype=float)
    clusters: list[list[str]] = [order]
    while clusters:
        cluster = clusters.pop(0)
        if len(cluster) <= 1:
            continue
        split = len(cluster) // 2
        left = cluster[:split]
        right = cluster[split:]
        left_var = _cluster_variance(covariance, left)
        right_var = _cluster_variance(covariance, right)
        alpha = 1.0 - left_var / max(left_var + right_var, 1e-12)
        weights[left] *= alpha
        weights[right] *= 1.0 - alpha
        clusters.extend([left, right])
    weights = weights.reindex(covariance.index).fillna(0.0)
    total = float(weights.sum())
    if total <= 0:
        return pd.Series(1.0 / len(weights), index=weights.index, dtype=float)
    return weights / total


def project_weights_slsqp(
    initial_weights: pd.Series,
    factor_exposures: pd.DataFrame,
    *,
    max_position: float = 0.10,
    factor_bound: float = 0.05,
    max_iterations: int = 500,
) -> tuple[pd.Series, bool]:
    aligned = factor_exposures.reindex(initial_weights.index).fillna(0.0)
    w0 = initial_weights.to_numpy(dtype=float)
    x = aligned.to_numpy(dtype=float)
    long_mask = w0 > 0
    short_mask = w0 < 0
    if not bool(long_mask.any()) or not bool(short_mask.any()):
        return _fallback_rank_weights(initial_weights, max_position=max_position), False
    sign = np.where(long_mask, 1.0, -1.0)
    q0 = np.abs(w0)
    bounds = Bounds(np.zeros(len(w0)), max_position * np.ones(len(w0)))
    constraints = [
        LinearConstraint(long_mask.astype(float)[None, :], [0.5], [0.5]),
        LinearConstraint(short_mask.astype(float)[None, :], [0.5], [0.5]),
    ]
    if x.shape[1] > 0:
        constraints.append(LinearConstraint((x * sign[:, None]).T, -factor_bound, factor_bound))
    result = minimize(
        lambda q: 0.5 * float(np.sum((sign * q - w0) ** 2)),
        x0=q0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": max_iterations},
    )
    if result.success:
        weights = pd.Series(sign * result.x, index=initial_weights.index, dtype=float)
        return weights, True
    return _fallback_rank_weights(initial_weights, max_position=max_position), False


def _fallback_rank_weights(initial_weights: pd.Series, *, max_position: float) -> pd.Series:
    ranked = initial_weights.sort_values()
    n = len(ranked)
    if n == 0:
        return ranked
    half = n // 2
    if half == 0:
        return pd.Series(0.0, index=ranked.index, dtype=float)
    result = pd.Series(0.0, index=ranked.index, dtype=float)
    long_names = ranked.index[-half:]
    short_names = ranked.index[:half]
    w_val = min(max_position, 0.5 / half)
    result.loc[long_names] = w_val
    result.loc[short_names] = -w_val
    gross = float(result.abs().sum())
    return result if gross < 1.0 else result / gross


def optimize_hrp_barra_long_short(
    alpha_scores: pd.Series,
    returns_window: pd.DataFrame,
    factor_exposures: pd.DataFrame,
    config: HRPOptimizationConfig | None = None,
) -> tuple[pd.Series, dict[str, object]]:
    cfg = config or HRPOptimizationConfig()
    alpha = alpha_scores.dropna().sort_values()
    if alpha.empty:
        return pd.Series(dtype=float), {"solver_success": False, "reason": "empty_alpha"}
    assets = alpha.index.intersection(returns_window.columns).intersection(factor_exposures.index)
    alpha = alpha.reindex(assets).dropna()
    if alpha.empty:
        return pd.Series(dtype=float), {"solver_success": False, "reason": "empty_intersection"}

    half = max(1, len(alpha) // 2)
    long_assets = alpha.tail(half).index.tolist()
    short_assets = alpha.head(half).index.tolist()
    selected = pd.Index(sorted(set(long_assets + short_assets)))
    returns_subset = returns_window.loc[:, selected]
    cov = estimate_shrunk_covariance(
        returns_subset.tail(cfg.covariance_lookback),
        min_observations=cfg.min_observations,
    )
    if cov.empty:
        return pd.Series(dtype=float), {"solver_success": False, "reason": "empty_covariance"}

    initial = pd.Series(0.0, index=selected, dtype=float)
    long_cov = cov.loc[long_assets, long_assets]
    short_cov = cov.loc[short_assets, short_assets]
    if not long_cov.empty:
        initial.loc[long_assets] = compute_hrp_weights(long_cov) * 0.5
    if not short_cov.empty:
        initial.loc[short_assets] = -compute_hrp_weights(short_cov) * 0.5

    projected, success = project_weights_slsqp(
        initial_weights=initial,
        factor_exposures=factor_exposures.reindex(selected).fillna(0.0),
        max_position=cfg.max_position,
        factor_bound=cfg.factor_bound,
    )
    exposures = factor_exposures.reindex(projected.index).fillna(0.0)
    return projected, {
        "solver_success": success,
        "covariance": cov,
        "initial_weights": initial,
        "factor_exposure": exposures.T @ projected,
    }
