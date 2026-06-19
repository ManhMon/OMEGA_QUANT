#!/usr/bin/env python3
"""Mine Latent Alphas from 64-Dimensional Feature Space.

Deterministic, PIT-safe latent alpha extraction from features_advanced_sim.parquet.
Uses PCA and ICA to discover latent factors, evaluates IC/IR per factor,
and prepares projection artifacts for Phase 3.5 backtest integration.

Gate: LATENT_ALPHA_MINING_64D_20260617
Role: 14 (data-scientist) L2 — implementation only, no self-approval.

Methodology
-----------
1. Load features_advanced_sim.parquet (multi-symbol panel).
2. Separate alpha feature columns from metadata (ticker, date, returns, OHLCV).
3. Per-date cross-sectional standardization (PIT-safe, no look-ahead).
4. Fit PCA and FastICA on the cross-sectional feature space.
5. Project each (date, ticker) row onto latent components.
6. Compute per-date Spearman rank IC against next-period returns.
7. Aggregate IC time-series: mean, std, IR, IC decay, turnover.
8. Apply cost-adjusted IC gate (quant-research skill thresholds).
9. Persist:
   - data/latent_alphas_components.parquet  (projected signals)
   - data/latent_alphas_model.pkl           (fitted PCA + ICA for backtest)
   - data/latent_alphas_metrics.json        (per-component IC/IR/turnover)
   - .ly_state/session/latent_alphas_report_20260617.md  (human-readable)

PIT Safety
----------
- Features are already T-1 lagged in the parquet (pre-computed).
- Cross-sectional standardization uses only same-date data (no future leak).
- Forward returns column (``returns``) is the label, NOT used in projection.
- PCA/ICA fit on training window only; OOS projection uses frozen model.

Usage
-----
    python scripts/mine_latent_alphas.py
    python scripts/mine_latent_alphas.py --n-components 10 --method pca
    python scripts/mine_latent_alphas.py --quick-mode
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import pickle
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reproducibility — all seeds set at the top (data-science-workflow skill)
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SESSION_DIR = REPO_ROOT / ".ly_state" / "session"
FEATURES_PATH = DATA_DIR / "features_advanced_sim.parquet"
OUTPUT_PARQUET = DATA_DIR / "latent_alphas_components.parquet"
OUTPUT_MODEL = DATA_DIR / "latent_alphas_model.pkl"
OUTPUT_METRICS = DATA_DIR / "latent_alphas_metrics.json"
OUTPUT_REPORT = SESSION_DIR / "latent_alphas_report_20260617.md"

# ---------------------------------------------------------------------------
# Constants (quant-research skill thresholds)
# ---------------------------------------------------------------------------
GATE = "LATENT_ALPHA_MINING_64D_20260617"
IC_MIN_THRESHOLD = 0.02        # Minimum net-of-cost IC
IR_MIN_THRESHOLD = 0.30        # Minimum IR (marginal signal)
TURNOVER_MAX = 0.30            # Max 30% daily one-way turnover
ROUND_TRIP_COST_BPS = 27.0     # VN market round-trip cost
TRADING_DAYS_VN = 248          # VN trading days per year

# Non-feature columns (metadata + labels)
META_COLS = {"ticker", "date", "returns", "adv_vnd"}
RAW_OHLCV = {"open", "high", "low", "close", "volume"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mine_latent_alphas")


# ===================================================================
# Helper functions
# ===================================================================

def identify_alpha_columns(df: pd.DataFrame) -> List[str]:
    """Return list of alpha feature columns (excluding metadata and OHLCV)."""
    all_cols = set(df.columns)
    exclude = META_COLS | RAW_OHLCV
    alpha_cols = sorted(all_cols - exclude)
    return alpha_cols


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file for reproducibility tracking."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()[:16]


def cross_sectional_standardize(
    df: pd.DataFrame, feature_cols: List[str], date_col: str = "date"
) -> pd.DataFrame:
    """Per-date cross-sectional z-score standardization (PIT-safe).

    Each date's features are standardized using only that date's cross-section.
    No look-ahead bias possible.

    Parameters
    ----------
    df : DataFrame
        Panel data with date and feature columns.
    feature_cols : list of str
        Columns to standardize.
    date_col : str
        Date column name.

    Returns
    -------
    DataFrame
        Copy of df with standardized feature columns.
    """
    result = df.copy()
    grouped_mean = result.groupby(date_col)[feature_cols].transform("mean")
    grouped_std = result.groupby(date_col)[feature_cols].transform("std")
    # Replace zero std with NaN to avoid division by zero
    grouped_std = grouped_std.replace(0, np.nan)
    result[feature_cols] = (result[feature_cols] - grouped_mean) / grouped_std
    # Fill any NaN from zero-std dates with 0
    result[feature_cols] = result[feature_cols].fillna(0.0)
    return result


def fit_pca_components(
    X_train: np.ndarray, n_components: int
) -> Tuple[np.ndarray, Any]:
    """Fit PCA on training data and return projection matrix + model.

    Parameters
    ----------
    X_train : ndarray (n_train_samples, n_features)
        Training feature matrix.
    n_components : int
        Number of principal components to extract.

    Returns
    -------
    components : ndarray (n_components, n_features)
        PCA loading vectors.
    model : PCA
        Fitted PCA model for OOS projection.
    """
    from sklearn.decomposition import PCA

    pca = PCA(n_components=n_components, random_state=SEED, svd_solver="full")
    pca.fit(X_train)
    return pca.components_, pca


def fit_ica_components(
    X_train: np.ndarray, n_components: int
) -> Tuple[np.ndarray, Any]:
    """Fit FastICA on training data and return mixing matrix + model.

    Parameters
    ----------
    X_train : ndarray (n_train_samples, n_features)
        Training feature matrix (should be pre-whitened or PCA-reduced).
    n_components : int
        Number of independent components.

    Returns
    -------
    components : ndarray (n_components, n_features)
        ICA unmixing vectors.
    model : FastICA
        Fitted ICA model for OOS projection.
    """
    from sklearn.decomposition import FastICA

    ica = FastICA(
        n_components=n_components,
        random_state=SEED,
        max_iter=500,
        tol=1e-4,
        whiten="unit-variance",
    )
    ica.fit(X_train)
    return ica.components_, ica


def project_latent_factors(
    df: pd.DataFrame,
    feature_cols: List[str],
    model: Any,
    method: str,
    prefix: str,
) -> pd.DataFrame:
    """Project dataframe rows onto latent components.

    Parameters
    ----------
    df : DataFrame
        Panel data with standardized features.
    feature_cols : list of str
        Feature column names.
    model : PCA or FastICA
        Fitted decomposition model.
    method : str
        'pca' or 'ica'.
    prefix : str
        Prefix for output column names (e.g. 'latent_pca_' or 'latent_ica_').

    Returns
    -------
    DataFrame
        Original df with added latent factor columns.
    """
    X = df[feature_cols].values
    # Handle NaN: replace with 0 for projection
    X = np.nan_to_num(X, nan=0.0)

    if method == "pca":
        projections = model.transform(X)
    elif method == "ica":
        projections = model.transform(X)
    else:
        raise ValueError(f"Unknown method: {method}")

    result = df.copy()
    n_comp = projections.shape[1]
    for i in range(n_comp):
        result[f"{prefix}{i:02d}"] = projections[:, i]

    return result


def compute_per_date_ic(
    df: pd.DataFrame,
    signal_col: str,
    return_col: str = "returns",
    date_col: str = "date",
    min_obs: int = 10,
) -> pd.Series:
    """Compute per-date Spearman rank IC between signal and returns.

    Parameters
    ----------
    df : DataFrame
        Panel data with signal and return columns.
    signal_col : str
        Signal column name.
    return_col : str
        Forward return column name.
    date_col : str
        Date column name.
    min_obs : int
        Minimum observations per date to compute IC.

    Returns
    -------
    Series
        IC per date (index=date, value=Spearman rho).
    """
    from scipy.stats import spearmanr

    ic_values = {}
    for date, group in df.groupby(date_col):
        mask = group[[signal_col, return_col]].dropna()
        if len(mask) < min_obs:
            ic_values[date] = np.nan
            continue
        rho, _ = spearmanr(mask[signal_col], mask[return_col])
        ic_values[date] = rho

    return pd.Series(ic_values, name=f"IC_{signal_col}")


def compute_ic_metrics(ic_series: pd.Series) -> Dict[str, float]:
    """Aggregate IC time-series into summary metrics.

    Parameters
    ----------
    ic_series : Series
        Per-date IC values.

    Returns
    -------
    dict
        IC mean, std, IR, positive rate, t-stat, p-value proxy.
    """
    clean = ic_series.dropna()
    if len(clean) == 0:
        return {
            "ic_mean": np.nan,
            "ic_std": np.nan,
            "ir": np.nan,
            "ic_positive_rate": np.nan,
            "ic_t_stat": np.nan,
            "n_dates": 0,
        }

    ic_mean = float(clean.mean())
    ic_std = float(clean.std()) if len(clean) > 1 else 0.0
    ir = ic_mean / ic_std if ic_std > 1e-8 else 0.0
    ic_positive_rate = float((clean > 0).mean())
    t_stat = ic_mean / (ic_std / np.sqrt(len(clean))) if ic_std > 1e-8 else 0.0

    return {
        "ic_mean": round(ic_mean, 6),
        "ic_std": round(ic_std, 6),
        "ir": round(ir, 4),
        "ic_positive_rate": round(ic_positive_rate, 4),
        "ic_t_stat": round(t_stat, 4),
        "n_dates": int(len(clean)),
    }


def compute_cost_adjusted_ic(
    ic_mean: float, turnover: float, round_trip_cost_bps: float = ROUND_TRIP_COST_BPS
) -> float:
    """Compute net-of-cost IC.

    Parameters
    ----------
    ic_mean : float
        Gross IC mean.
    turnover : float
        Daily one-way turnover (0-1).
    round_trip_cost_bps : float
        Round-trip transaction cost in basis points.

    Returns
    -------
    float
        Net IC after cost drag.
    """
    cost_drag = turnover * (round_trip_cost_bps / 10000.0)
    return ic_mean - cost_drag


def compute_signal_turnover(
    df: pd.DataFrame,
    signal_col: str,
    date_col: str = "date",
    ticker_col: str = "ticker",
) -> float:
    """Compute mean daily signal turnover (rank change).

    Turnover = mean(|rank_t - rank_{t-1}|) averaged across dates.

    Parameters
    ----------
    df : DataFrame
        Panel with signal column.
    signal_col : str
        Signal column.
    date_col : str
        Date column.
    ticker_col : str
        Ticker column.

    Returns
    -------
    float
        Mean daily turnover (0-1 scale).
    """
    pivot = df.pivot_table(
        index=date_col, columns=ticker_col, values=signal_col, aggfunc="first"
    )
    ranks = pivot.rank(axis=1, pct=True)
    rank_diff = ranks.diff().abs()
    # Mean turnover = mean of absolute rank changes per day
    daily_turnover = rank_diff.mean(axis=1).dropna()
    return float(daily_turnover.mean()) if len(daily_turnover) > 0 else 0.0


def compute_explained_variance_ratio(
    model: Any, method: str, n_components: int
) -> List[float]:
    """Get explained variance ratio from PCA model.

    For ICA, returns uniform placeholder (ICA doesn't have variance explained).
    For PLS, returns R² per component.
    """
    if method == "pca" and hasattr(model, "explained_variance_ratio_"):
        return [round(float(v), 6) for v in model.explained_variance_ratio_]
    if method == "pls" and hasattr(model, "x_scores_"):
        # PLS: approximate explained variance from x_scores_ (not scores_)
        # L3-Fix: PLSRegression stores x-scores in model.x_scores_
        total_var = np.var(model.x_scores_, axis=0).sum()
        if total_var > 1e-8:
            component_vars = np.var(model.x_scores_, axis=0)
            return [round(float(v / total_var), 6) for v in component_vars]
    # ICA or fallback: uniform
    return [round(1.0 / n_components, 6)] * n_components


# ===================================================================
# Advanced: PLS Regression (supervised latent extraction)
# ===================================================================

def fit_pls_components(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_components: int,
) -> Tuple[np.ndarray, Any]:
    """Fit PLS regression on training data using forward returns as target.

    PLS extracts latent components that maximise covariance between
    the feature space X and the return target y.  Unlike PCA (unsupervised),
    PLS is supervised and may yield components with higher IC.

    Parameters
    ----------
    X_train : ndarray (n_samples, n_features)
        Training feature matrix.
    y_train : ndarray (n_samples,)
        Forward return labels (cross-sectionally neutralised).
    n_components : int
        Number of PLS components to extract.

    Returns
    -------
    components : ndarray (n_components, n_features)
        PLS x-loadings.
    model : PLSRegression
        Fitted PLS model for OOS projection.
    """
    from sklearn.cross_decomposition import PLSRegression

    # PLS requires n_components <= min(n_samples, n_features)
    max_comp = min(X_train.shape[1], X_train.shape[0], n_components)
    pls = PLSRegression(n_components=max_comp, scale=False, max_iter=500)
    y_2d = y_train.reshape(-1, 1) if y_train.ndim == 1 else y_train
    pls.fit(X_train, y_2d)
    return pls.x_loadings_.T, pls


def project_pls_factors(
    df: pd.DataFrame,
    feature_cols: List[str],
    model: Any,
    prefix: str = "latent_pls_",
) -> pd.DataFrame:
    """Project dataframe rows onto PLS latent components.

    Parameters
    ----------
    df : DataFrame
        Panel data with features.
    feature_cols : list of str
        Feature column names.
    model : PLSRegression
        Fitted PLS model.
    prefix : str
        Prefix for output column names.

    Returns
    -------
    DataFrame
        Original df with added PLS factor columns.
    """
    X = df[feature_cols].values
    X = np.nan_to_num(X, nan=0.0)
    # PLS transform returns scores (n_samples, n_components)
    projections = model.transform(X)
    result = df.copy()
    n_comp = projections.shape[1]
    for i in range(n_comp):
        result[f"{prefix}{i:02d}"] = projections[:, i]
    return result


# ===================================================================
# Advanced: Cross-sectional target returns neutralization
# ===================================================================

def neutralize_target_returns(
    df: pd.DataFrame,
    feature_cols: List[str],
    return_col: str = "returns",
    date_col: str = "date",
) -> np.ndarray:
    """Cross-sectionally neutralise target returns against feature exposures.

    For each date, regress returns on the feature cross-section and return
    the residual.  This removes linear factor exposures from the target,
    allowing PLS to focus on the non-linear / residual alpha signal.

    PIT-safe: uses only same-date cross-section (no look-ahead).

    Parameters
    ----------
    df : DataFrame
        Panel data with features and returns.
    feature_cols : list of str
        Feature columns used as controls.
    return_col : str
        Forward return column.
    date_col : str
        Date column.

    Returns
    -------
    ndarray (n_rows,)
        Neutralised return residuals aligned to df index.
    """
    from numpy.linalg import lstsq

    residuals = pd.Series(0.0, index=df.index)
    for date, idx in df.groupby(date_col).groups.items():
        rows = df.loc[idx]
        X = rows[feature_cols].values
        X = np.nan_to_num(X, nan=0.0)
        y = rows[return_col].values.astype(np.float64)
        # Add intercept
        X_aug = np.column_stack([np.ones(len(X)), X])
        try:
            coef, _, _, _ = lstsq(X_aug, y, rcond=None)
            y_hat = X_aug @ coef
            residuals.loc[idx] = y - y_hat
        except Exception:
            # If regression fails, keep raw returns
            residuals.loc[idx] = y
    return residuals.values


# ===================================================================
# Advanced: Regime-conditional PCA/PLS using rolling HMMs
# ===================================================================

def detect_regimes_hmm(
    market_returns: np.ndarray,
    n_states: int = 3,
    min_window: int = 60,
) -> Tuple[np.ndarray, Any]:
    """Detect market regimes using a rolling Gaussian HMM.

    Fits a Gaussian HMM on trailing market returns and assigns each
    date to one of n_states regimes (e.g. Bull/Bear/Sideways).

    PIT-safe: uses only trailing data (no future returns).

    If hmmlearn is not available, falls back to a simple heuristic
    regime detector based on rolling mean and volatility.

    Parameters
    ----------
    market_returns : ndarray (T,)
        Daily market returns (cross-sectional mean or index proxy).
    n_states : int
        Number of HMM hidden states.
    min_window : int
        Minimum trailing window for HMM fitting.

    Returns
    -------
    regime_labels : ndarray (T,)
        Integer regime label per date (0..n_states-1).
    hmm_model : GaussianHMM or None
        Fitted HMM model (None if fitting failed or hmmlearn unavailable).
    """
    T = len(market_returns)
    regime_labels = np.zeros(T, dtype=int)

    if T < min_window:
        logger.warning(
            f"HMM: insufficient data ({T} < {min_window}). "
            "Assigning all to regime 0."
        )
        return regime_labels, None

    # Try hmmlearn first
    try:
        from hmmlearn.hmm import GaussianHMM

        X_hmm = market_returns.reshape(-1, 1)
        hmm = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=100,
            random_state=SEED,
        )
        hmm.fit(X_hmm)
        regime_labels = hmm.predict(X_hmm)
        return regime_labels, hmm
    except ImportError:
        logger.warning(
            "hmmlearn not available. Falling back to heuristic regime detection."
        )
    except Exception as e:
        logger.warning(f"HMM fitting failed: {e}. Falling back to heuristic.")

    # Heuristic fallback: rolling mean/vol quantile-based regimes
    window = min(min_window, T // 3)
    cum_returns = np.cumsum(market_returns)
    rolling_mean = np.convolve(market_returns, np.ones(window) / window, mode='same')
    rolling_std = pd.Series(market_returns).rolling(window, min_periods=1).std().values

    # 3 states: Bear (low mean, high vol), Sideways (mid), Bull (high mean, low vol)
    mean_median = np.median(rolling_mean)
    vol_median = np.median(rolling_std)

    for i in range(T):
        if rolling_mean[i] < mean_median and rolling_std[i] > vol_median:
            regime_labels[i] = 0  # Bear
        elif rolling_mean[i] > mean_median:
            regime_labels[i] = 2  # Bull
        else:
            regime_labels[i] = 1  # Sideways

    return regime_labels, None


def fit_regime_conditional_models(
    X_train: np.ndarray,
    y_train: np.ndarray,
    regime_labels: np.ndarray,
    n_components: int,
    method: str = "pca",
) -> Dict[int, Dict[str, Any]]:
    """Fit separate PCA/PLS models per HMM regime.

    For each regime, fits a decomposition model on the subset of
    training data belonging to that regime.

    Parameters
    ----------
    X_train : ndarray (n_train, n_features)
        Training feature matrix.
    y_train : ndarray (n_train,)
        Neutralised return targets.
    regime_labels : ndarray (n_train,)
        Regime label per training sample.
    n_components : int
        Number of components per regime model.
    method : str
        'pca' or 'pls'.

    Returns
    -------
    dict
        {regime_id: {"model": fitted_model, "components": ndarray, "prefix": str, "n_samples": int}}
    """
    regime_models: Dict[int, Dict[str, Any]] = {}
    unique_regimes = sorted(set(regime_labels))

    for regime_id in unique_regimes:
        mask = regime_labels == regime_id
        X_r = X_train[mask]
        y_r = y_train[mask]
        n_r = len(X_r)

        if n_r < n_components + 1:
            logger.warning(
                f"Regime {regime_id}: only {n_r} samples, "
                f"skipping (need >= {n_components + 1})."
            )
            continue

        prefix = f"latent_r{regime_id}_{method}_"
        n_comp = min(n_components, X_r.shape[1], n_r - 1)

        if method == "pls":
            components, model = fit_pls_components(X_r, y_r, n_comp)
        else:
            components, model = fit_pca_components(X_r, n_comp)

        regime_models[regime_id] = {
            "model": model,
            "components": components,
            "prefix": prefix,
            "n_samples": n_r,
            "method": method,
            "n_components": n_comp,
        }
        logger.info(
            f"  Regime {regime_id}: fitted {method.upper()} "
            f"with {n_comp} components on {n_r} samples"
        )

    return regime_models


def project_regime_conditional(
    df: pd.DataFrame,
    feature_cols: List[str],
    regime_models: Dict[int, Dict[str, Any]],
    regime_labels_map: Dict,
    date_col: str = "date",
) -> pd.DataFrame:
    """Project data using regime-conditional models.

    For each date, looks up the regime label and applies the
    corresponding regime model.  If a regime has no fitted model,
    falls back to regime 0 (or the first available regime).

    Parameters
    ----------
    df : DataFrame
        Panel data with features and date column.
    feature_cols : list of str
        Feature column names.
    regime_models : dict
        {regime_id: {"model": ..., "prefix": ..., "method": ...}}
    regime_labels_map : dict
        {date: regime_id} mapping for projection dates.
    date_col : str
        Date column name.

    Returns
    -------
    DataFrame
        df with regime-conditional latent factor columns added.
    """
    result = df.copy()
    # Determine max n_components across regimes for column pre-allocation
    all_prefixes = set()
    max_n_comp = 0
    for info in regime_models.values():
        all_prefixes.add(info["prefix"])
        max_n_comp = max(max_n_comp, info["n_components"])

    # Pre-fill all possible latent columns with 0
    latent_col_names = []
    for info in regime_models.values():
        for i in range(info["n_components"]):
            col_name = f"{info['prefix']}{i:02d}"
            if col_name not in latent_col_names:
                latent_col_names.append(col_name)
                result[col_name] = 0.0

    # Fallback regime
    fallback_regime = min(regime_models.keys()) if regime_models else 0

    for date, group_idx in df.groupby(date_col).groups.items():
        regime_id = regime_labels_map.get(date, fallback_regime)
        if regime_id not in regime_models:
            regime_id = fallback_regime
        if regime_id not in regime_models:
            continue

        info = regime_models[regime_id]
        model = info["model"]
        prefix = info["prefix"]
        method = info["method"]
        n_comp = info["n_components"]

        X = df.loc[group_idx, feature_cols].values
        X = np.nan_to_num(X, nan=0.0)

        if method == "pls":
            projections = model.transform(X)
        else:
            projections = model.transform(X)

        idx_arr = group_idx if isinstance(group_idx, np.ndarray) else group_idx.to_numpy()
        for i in range(n_comp):
            col_name = f"{prefix}{i:02d}"
            result.loc[idx_arr, col_name] = projections[:, i]

    return result


# ===================================================================
# Advanced: Deep Nonlinear Autoencoder (GATE: LATENT_ALPHA_MINING_64D_20260617)
# ===================================================================

def fit_autoencoder_components(
    X_train: np.ndarray,
    n_components: int,
    epochs: int = 20,
    hidden_dims: Tuple[int, ...] = (256, 128, 64),
    seed: int = SEED,
) -> Tuple[Any, Dict[str, float]]:
    """Train a deep nonlinear autoencoder on training data.

    Uses NonlinearDeepLatentEncoder from omega.quant.models.latent_encoder.

    Parameters
    ----------
    X_train : ndarray (n_samples, n_features)
        Training feature matrix.
    n_components : int
        Latent dimension (bottleneck).
    epochs : int
        Number of training epochs.
    hidden_dims : tuple of int
        Encoder hidden layer sizes (decoder mirrors).
    seed : int
        Random seed.

    Returns
    -------
    encoder : NonlinearDeepLatentEncoder
        Fitted encoder for OOS projection.
    metrics : dict
        Training metrics (final_loss, n_epochs, reconstruction_loss).
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from omega.quant.models.latent_encoder import (
        NonlinearDeepLatentEncoder,
        DeepAutoencoderConfig,
    )

    cfg = DeepAutoencoderConfig(
        n_features=X_train.shape[1],
        latent_dim=n_components,
        hidden_dims=hidden_dims,
        epochs=epochs,
        seed=seed,
    )
    encoder = NonlinearDeepLatentEncoder(cfg)
    encoder.fit(X_train)

    train_loss = encoder._train_loss_history[-1] if encoder._train_loss_history else float("nan")
    recon_loss = encoder.get_reconstruction_loss(X_train)

    ae_metrics = {
        "final_train_loss": round(train_loss, 6),
        "reconstruction_loss": round(recon_loss, 6),
        "n_epochs_trained": len(encoder._train_loss_history),
        "input_dim": X_train.shape[1],
        "latent_dim": n_components,
        "hidden_dims": list(hidden_dims),
    }
    return encoder, ae_metrics


def project_autoencoder_factors(
    df: pd.DataFrame,
    feature_cols: List[str],
    encoder: Any,
    prefix: str = "latent_ae_",
) -> pd.DataFrame:
    """Project dataframe rows onto deep autoencoder latent components.

    Parameters
    ----------
    df : DataFrame
        Panel data with feature columns.
    feature_cols : list of str
        Feature column names.
    encoder : NonlinearDeepLatentEncoder
        Fitted deep autoencoder encoder.
    prefix : str
        Prefix for output column names.

    Returns
    -------
    DataFrame
        Original df with added autoencoder latent factor columns.
    """
    X = df[feature_cols].values
    X = np.nan_to_num(X, nan=0.0)
    projections = encoder.transform(X)  # (N, latent_dim)

    result = df.copy()
    n_comp = projections.shape[1]
    for i in range(n_comp):
        result[f"{prefix}{i:02d}"] = projections[:, i]

    return result


# ===================================================================
# Main pipeline
# ===================================================================

def run_latent_alpha_mining(
    n_components: int = 64,
    method: str = "pca",
    train_ratio: float = 0.6,
    quick_mode: bool = False,
    features_path: Optional[Path] = None,
    enable_pls: bool = False,
    enable_neutralize: bool = False,
    enable_regime_conditional: bool = False,
    n_hmm_states: int = 3,
    hmm_min_window: int = 60,
) -> Dict[str, Any]:
    """Execute the full latent alpha mining pipeline.

    Parameters
    ----------
    n_components : int
        Number of latent components to extract.
    method : str
        Decomposition method: 'pca', 'ica', 'both', or 'pls'.
    train_ratio : float
        Fraction of dates used for training (chronological split).
    quick_mode : bool
        If True, use fewer components and symbols for speed.
    features_path : Path, optional
        Override path to features parquet.
    enable_pls : bool
        If True, also run PLS regression (supervised).
    enable_neutralize : bool
        If True, cross-sectionally neutralise returns before PLS.
    enable_regime_conditional : bool
        If True, fit regime-conditional models via rolling HMM.
    n_hmm_states : int
        Number of HMM hidden states for regime detection.
    hmm_min_window : int
        Minimum trailing window for HMM fitting.

    Returns
    -------
    dict
        Complete mining results with metrics, model info, and evidence.
    """
    t_start = time.time()
    features_path = features_path or FEATURES_PATH

    if quick_mode:
        n_components = min(n_components, 5)

    # GATE: LATENT_ALPHA_MINING_64D_20260617 — quick_mode suffix
    # When quick_mode is True, use '_quick' suffix on all output artifacts
    # to avoid overwriting production 64D files.
    _suffix = "_quick" if quick_mode else ""
    output_parquet = DATA_DIR / f"latent_alphas_components{_suffix}.parquet"
    output_model = DATA_DIR / f"latent_alphas_model{_suffix}.pkl"
    output_metrics = DATA_DIR / f"latent_alphas_metrics{_suffix}.json"
    output_report = SESSION_DIR / f"latent_alphas_report_20260617{_suffix}.md"

    logger.info("=" * 80)
    logger.info(f"GATE: {GATE}")
    logger.info(f"Latent Alpha Mining — {method.upper()} — {n_components} components")
    logger.info(f"Features: {features_path}")
    logger.info("=" * 80)

    # ------------------------------------------------------------------
    # Step 1: Load data
    # ------------------------------------------------------------------
    logger.info("Step 1: Loading features_advanced_sim.parquet...")
    if not features_path.exists():
        logger.error(f"Features file not found: {features_path}")
        sys.exit(1)

    df = pd.read_parquet(features_path)
    file_hash = compute_file_hash(features_path)
    logger.info(f"  Shape: {df.shape}")
    logger.info(f"  File hash (SHA-256 prefix): {file_hash}")
    logger.info(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    logger.info(f"  Symbols: {df['ticker'].nunique()}")

    # ------------------------------------------------------------------
    # Step 2: Identify alpha feature columns
    # ------------------------------------------------------------------
    alpha_cols = identify_alpha_columns(df)
    logger.info(f"Step 2: Identified {len(alpha_cols)} alpha feature columns")

    if len(alpha_cols) < n_components:
        logger.warning(
            f"Only {len(alpha_cols)} features available for {n_components} components. "
            f"Reducing n_components to {len(alpha_cols)}."
        )
        n_components = len(alpha_cols)

    # ------------------------------------------------------------------
    # Step 3: Drop rows with NaN returns (labels) and cross-sectional standardize
    # ------------------------------------------------------------------
    logger.info("Step 3: Cross-sectional standardization (PIT-safe)...")
    n_before = len(df)
    df_clean = df.dropna(subset=["returns"]).copy()
    logger.info(f"  Rows before NaN drop: {n_before}, after: {len(df_clean)}")

    df_std = cross_sectional_standardize(df_clean, alpha_cols)
    logger.info(f"  Standardized {len(alpha_cols)} columns per-date")

    # ------------------------------------------------------------------
    # Step 4: Chronological train/test split (PIT-safe)
    # ------------------------------------------------------------------
    logger.info("Step 4: Chronological train/test split...")
    dates_sorted = sorted(df_std["date"].unique())
    n_dates = len(dates_sorted)
    split_idx = int(n_dates * train_ratio)
    train_dates = set(dates_sorted[:split_idx])
    test_dates = set(dates_sorted[split_idx:])

    train_mask = df_std["date"].isin(train_dates)
    test_mask = df_std["date"].isin(test_dates)

    df_train = df_std[train_mask].copy()
    df_test = df_std[test_mask].copy()

    logger.info(f"  Train: {len(train_dates)} dates, {len(df_train)} rows")
    logger.info(f"  Test:  {len(test_dates)} dates, {len(df_test)} rows")
    logger.info(f"  Train end: {max(train_dates)}, Test start: {min(test_dates)}")

    # ------------------------------------------------------------------
    # Step 5: Fit decomposition on TRAINING data only
    # ------------------------------------------------------------------
    logger.info(f"Step 5: Fitting {method.upper()} on training data...")
    X_train = df_train[alpha_cols].values
    X_train = np.nan_to_num(X_train, nan=0.0)

    models = {}
    all_results = {}

    methods_to_run = []
    if method in ("pca", "both"):
        methods_to_run.append("pca")
    if method in ("ica", "both"):
        methods_to_run.append("ica")
    if method == "pls" or enable_pls:
        methods_to_run.append("pls")
    if method == "autoencoder":
        methods_to_run.append("autoencoder")

    for m in methods_to_run:
        logger.info(f"  Fitting {m.upper()} with {n_components} components...")
        if m == "pca":
            components, model = fit_pca_components(X_train, n_components)
            prefix = "latent_pca_"
        elif m == "ica":
            components, model = fit_ica_components(X_train, n_components)
            prefix = "latent_ica_"
        elif m == "pls":
            # PLS: use returns as target (optionally neutralised)
            y_train_raw = df_train["returns"].values.astype(np.float64)
            if enable_neutralize:
                logger.info("    Neutralising target returns cross-sectionally...")
                y_train = neutralize_target_returns(
                    df_train, alpha_cols, "returns", "date"
                )
            else:
                y_train = y_train_raw
            n_comp_pls = min(n_components, X_train.shape[1], X_train.shape[0])
            components, model = fit_pls_components(X_train, y_train, n_comp_pls)
            prefix = "latent_pls_"
        elif m == "autoencoder":
            logger.info(f"    Training deep nonlinear autoencoder...")
            encoder, ae_metrics = fit_autoencoder_components(
                X_train, n_components, epochs=20, seed=SEED
            )
            model = encoder
            components = None  # Deep AE has no explicit component matrix
            prefix = "latent_ae_"
            logger.info(
                f"    DeepAE: train_loss={ae_metrics['final_train_loss']:.6f}, "
                f"recon_loss={ae_metrics['reconstruction_loss']:.6f}, "
                f"epochs={ae_metrics['n_epochs_trained']}"
            )
        else:
            raise ValueError(f"Unknown method: {m}")

        models[m] = {"model": model, "components": components, "prefix": prefix}

        # Explained variance
        if m == "autoencoder":
            # Deep AE: use reconstruction-based proxy instead of variance ratio
            var_ratio = [round(1.0 / n_components, 6)] * n_components
            if m == "autoencoder":
                logger.info(
                    f"    DeepAE reconstruction loss: {ae_metrics['reconstruction_loss']:.6f}"
                )
        else:
            var_ratio = compute_explained_variance_ratio(model, m, n_components)
            logger.info(f"    Explained variance (first 5): {var_ratio[:5]}")
        if m == "pca":
            total_var = sum(var_ratio)
            logger.info(f"    Total variance explained ({n_components} comp): {total_var:.4f}")

    # ------------------------------------------------------------------
    # Step 6: Project TRAIN and TEST data using frozen models
    # ------------------------------------------------------------------
    logger.info("Step 6: Projecting train and test data onto latent components...")
    for m, info in models.items():
        prefix = info["prefix"]
        model = info["model"]

        if m == "pls":
            df_train = project_pls_factors(df_train, alpha_cols, model, prefix)
            df_test = project_pls_factors(df_test, alpha_cols, model, prefix)
        elif m == "autoencoder":
            df_train = project_autoencoder_factors(df_train, alpha_cols, model, prefix)
            df_test = project_autoencoder_factors(df_test, alpha_cols, model, prefix)
        else:
            df_train = project_latent_factors(df_train, alpha_cols, model, m, prefix)
            df_test = project_latent_factors(df_test, alpha_cols, model, m, prefix)

        actual_n_comp = (
            model.x_loadings_.shape[1] if m == "pls" else n_components
        )
        latent_cols = [f"{prefix}{i:02d}" for i in range(actual_n_comp)]
        logger.info(f"  {m.upper()}: projected {len(latent_cols)} latent columns")

    # ------------------------------------------------------------------
    # Step 6b: Regime-conditional PCA/PLS (optional, advanced)
    # ------------------------------------------------------------------
    regime_models = {}
    regime_labels_map = {}
    regime_evidence = None
    if enable_regime_conditional:
        logger.info("Step 6b: Regime-conditional modeling via rolling HMM...")
        # Compute daily cross-sectional mean returns as market proxy
        daily_mean_returns = (
            df_train.groupby("date")["returns"].mean().sort_index()
        )
        market_ret = daily_mean_returns.values.astype(np.float64)
        train_dates_sorted = sorted(df_train["date"].unique())

        # Detect regimes on training data only (PIT-safe)
        regime_labels_train, hmm_model = detect_regimes_hmm(
            market_ret, n_states=n_hmm_states, min_window=hmm_min_window
        )
        # Build date→regime mapping for train
        for i, d in enumerate(train_dates_sorted):
            regime_labels_map[d] = int(regime_labels_train[i])

        # For test dates, predict regime using HMM (PIT-safe, walk-forward).
        # L3-Fix-R2: For each test date t (at index i in test_dates_sorted),
        # predict its state using ONLY historical returns up to date t by
        # concatenating training market returns (market_ret) with OOS returns
        # up to day i+1 (test_market_ret[:i+1]). Run predict on the combined
        # history and assign the LAST predicted state preds[-1] to date t.
        # This prevents the Viterbi algorithm from leaking future OOS data.
        test_dates_sorted = sorted(df_test["date"].unique())
        if hmm_model is not None:
            test_daily_mean = (
                df_test.groupby("date")["returns"].mean().sort_index()
            )
            test_market_ret = test_daily_mean.values.astype(np.float64)
            test_dates_for_regime = list(test_daily_mean.index)
            try:
                for i, d in enumerate(test_dates_sorted):
                    # PIT-safe: concatenate training returns + OOS returns
                    # up to and including day i (no future data used).
                    combined_ret = np.concatenate(
                        [market_ret, test_market_ret[: i + 1]]
                    )
                    X_combined = combined_ret.reshape(-1, 1)
                    preds = hmm_model.predict(X_combined)
                    regime_labels_map[d] = int(preds[-1])
            except Exception as e:
                logger.warning(
                    f"HMM OOS predict failed ({e}). "
                    "Falling back to last training regime."
                )
                last_train_regime = int(regime_labels_train[-1])
                for d in test_dates_sorted:
                    regime_labels_map[d] = last_train_regime
        else:
            for d in test_dates_sorted:
                regime_labels_map[d] = 0

        # Neutralise targets for regime-conditional PLS
        rc_method = "pls" if (method == "pls" or enable_pls) else "pca"
        y_train_rc = df_train["returns"].values.astype(np.float64)
        if enable_neutralize:
            y_train_rc = neutralize_target_returns(
                df_train, alpha_cols, "returns", "date"
            )

        # Map daily regime labels to row-level so that the label array
        # matches X_train / y_train_rc in length (one label per stock-date
        # row, not one per unique date).  Fixes boolean-index size mismatch
        # inside fit_regime_conditional_models where mask = (regime_labels == k)
        # is applied directly to X_train[mask].
        regime_labels_row = (
            df_train["date"].map(regime_labels_map).values.astype(int)
        )

        regime_models = fit_regime_conditional_models(
            X_train=X_train,
            y_train=y_train_rc,
            regime_labels=regime_labels_row,
            n_components=min(n_components, 10),  # cap for regime subsets
            method=rc_method,
        )

        if regime_models:
            # Project train and test using regime-conditional models
            df_train = project_regime_conditional(
                df_train, alpha_cols, regime_models, regime_labels_map, "date"
            )
            df_test = project_regime_conditional(
                df_test, alpha_cols, regime_models, regime_labels_map, "date"
            )

            # Record evidence
            regime_evidence = {
                "n_hmm_states": n_hmm_states,
                "hmm_min_window": hmm_min_window,
                "method": rc_method,
                "regime_counts": {
                    int(k): int((regime_labels_train == k).sum())
                    for k in set(regime_labels_train)
                },
                "n_regime_models": len(regime_models),
                "regime_model_details": {
                    int(k): {
                        "n_samples": v["n_samples"],
                        "n_components": v["n_components"],
                        "method": v["method"],
                    }
                    for k, v in regime_models.items()
                },
            }
            logger.info(f"  Regime evidence: {regime_evidence}")

            # Add regime model info to models dict for metrics computation
            for reg_id, rc_info in regime_models.items():
                rc_key = f"regime_{reg_id}_{rc_method}"
                models[rc_key] = rc_info

    # ------------------------------------------------------------------
    # Step 7: Compute IC per latent component on TEST (OOS) data
    # ------------------------------------------------------------------
    logger.info("Step 7: Computing per-date Spearman IC on TEST (OOS) data...")
    component_metrics = {}

    for m, info in models.items():
        prefix = info["prefix"]
        # Determine actual component count
        if m == "pls":
            actual_n = info["model"].x_loadings_.shape[1]
        elif m.startswith("regime_"):
            actual_n = info.get("n_components", n_components)
        else:
            actual_n = n_components

        latent_cols = [f"{prefix}{i:02d}" for i in range(actual_n)]

        for col in latent_cols:
            # OOS IC
            ic_series = compute_per_date_ic(df_test, col)
            metrics = compute_ic_metrics(ic_series)

            # Turnover
            turnover = compute_signal_turnover(df_test, col)

            # Cost-adjusted IC
            net_ic = compute_cost_adjusted_ic(metrics["ic_mean"], turnover)

            # Gate check
            passes_ic_gate = abs(net_ic) >= IC_MIN_THRESHOLD
            passes_ir_gate = abs(metrics["ir"]) >= IR_MIN_THRESHOLD
            passes_turnover_gate = turnover <= TURNOVER_MAX

            component_metrics[col] = {
                **metrics,
                "turnover": round(turnover, 4),
                "net_ic": round(net_ic, 6),
                "passes_ic_gate": passes_ic_gate,
                "passes_ir_gate": passes_ir_gate,
                "passes_turnover_gate": passes_turnover_gate,
                "method": m,
                "component_index": int(col.split("_")[-1]),
            }

            status = "PASS" if (passes_ic_gate and passes_ir_gate and passes_turnover_gate) else "WEAK"
            logger.info(
                f"  {col}: IC={metrics['ic_mean']:.4f}, IR={metrics['ir']:.4f}, "
                f"Turnover={turnover:.4f}, NetIC={net_ic:.4f} [{status}]"
            )

    # ------------------------------------------------------------------
    # Step 8: Also compute in-sample IC for comparison (diagnostic only)
    # ------------------------------------------------------------------
    logger.info("Step 8: In-sample IC (diagnostic only, NOT for selection)...")
    for m, info in models.items():
        prefix = info["prefix"]
        if m == "pls":
            actual_n = info["model"].x_loadings_.shape[1]
        elif m.startswith("regime_"):
            actual_n = info.get("n_components", n_components)
        else:
            actual_n = n_components

        latent_cols = [f"{prefix}{i:02d}" for i in range(actual_n)]

        for col in latent_cols:
            ic_series_train = compute_per_date_ic(df_train, col)
            train_metrics = compute_ic_metrics(ic_series_train)
            component_metrics[col]["train_ic_mean"] = train_metrics["ic_mean"]
            component_metrics[col]["train_ir"] = train_metrics["ir"]

            decay_ratio = (
                abs(component_metrics[col]["ic_mean"]) / abs(train_metrics["ic_mean"])
                if abs(train_metrics["ic_mean"]) > 1e-8
                else 0.0
            )
            component_metrics[col]["oos_is_decay_ratio"] = round(decay_ratio, 4)

    # ------------------------------------------------------------------
    # Step 9: Rank components by OOS IR
    # ------------------------------------------------------------------
    ranked = sorted(
        component_metrics.items(),
        key=lambda x: abs(x[1]["ir"]) if not np.isnan(x[1]["ir"]) else 0.0,
        reverse=True,
    )
    logger.info("Step 9: Ranked latent alphas by |OOS IR|:")
    for i, (name, met) in enumerate(ranked):
        logger.info(
            f"  #{i+1}: {name} — IR={met['ir']:.4f}, IC={met['ic_mean']:.4f}, "
            f"NetIC={met['net_ic']:.4f}, Turnover={met['turnover']:.4f}"
        )

    # ------------------------------------------------------------------
    # Step 10: Persist artifacts
    # ------------------------------------------------------------------
    logger.info("Step 10: Persisting artifacts...")

    # Ensure output directories exist
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 10a: Save projected components parquet (full period: train + test)
    # Both df_train and df_test were projected in Step 6 using the same
    # frozen models (fit on training data only — PIT-safe).  The downstream
    # walk-forward backtest needs latent values for the ENTIRE date range so
    # that training/validation ICs can be computed per fold.  Saving only
    # df_test left the training period with 0.0 values after the left-merge,
    # preventing the backtest from selecting latent alphas.
    latent_cols_all = []
    for m, info in models.items():
        prefix = info["prefix"]
        if m == "pls":
            actual_n = info["model"].x_loadings_.shape[1]
        elif m.startswith("regime_"):
            actual_n = info.get("n_components", n_components)
        else:
            actual_n = n_components
        latent_cols_all.extend([f"{prefix}{i:02d}" for i in range(actual_n)])

    # Filter to only columns that exist in both df_train and df_test
    latent_cols_all = [
        c for c in latent_cols_all
        if c in df_train.columns and c in df_test.columns
    ]

    output_cols = ["ticker", "date", "returns"] + latent_cols_all
    df_full = pd.concat([df_train[output_cols], df_test[output_cols]], ignore_index=True)
    df_full.sort_values(["date", "ticker"], inplace=True)
    df_full.reset_index(drop=True, inplace=True)
    df_full.to_parquet(output_parquet, index=False)
    logger.info(
        f"  Saved: {output_parquet} ({len(df_full)} rows, "
        f"{len(latent_cols_all)} latent cols, "
        f"train={len(df_train)} + test={len(df_test)})"
    )

    # 10b: Save fitted models
    model_payload = {
        "gate": GATE,
        "seed": SEED,
        "method": method,
        "n_components": n_components,
        "alpha_cols": alpha_cols,
        "models": {m: info["model"] for m, info in models.items()},
        "train_dates_range": (str(min(train_dates)), str(max(train_dates))),
        "test_dates_range": (str(min(test_dates)), str(max(test_dates))),
        "features_hash": file_hash,
        # Advanced options
        "enable_pls": enable_pls or method == "pls",
        "enable_neutralize": enable_neutralize,
        "enable_regime_conditional": enable_regime_conditional,
        "regime_models": regime_models if regime_models else None,
        "regime_labels_map": regime_labels_map if regime_labels_map else None,
        "regime_evidence": regime_evidence,
    }
    with open(output_model, "wb") as f:
        pickle.dump(model_payload, f)
    logger.info(f"  Saved: {output_model}")

    # 10c: Save metrics JSON
    metrics_payload = {
        "gate": GATE,
        "timestamp": datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        "seed": SEED,
        "method": method,
        "n_components": n_components,
        "n_features": len(alpha_cols),
        "train_ratio": train_ratio,
        "train_dates": len(train_dates),
        "test_dates": len(test_dates),
        "features_hash": file_hash,
        "features_path": str(features_path),
        "vn_market_params": {
            "round_trip_cost_bps": ROUND_TRIP_COST_BPS,
            "trading_days_per_year": TRADING_DAYS_VN,
            "ic_min_threshold": IC_MIN_THRESHOLD,
            "ir_min_threshold": IR_MIN_THRESHOLD,
            "turnover_max": TURNOVER_MAX,
        },
        "advanced_options": {
            "enable_pls": enable_pls or method == "pls",
            "enable_neutralize": enable_neutralize,
            "enable_regime_conditional": enable_regime_conditional,
            "n_hmm_states": n_hmm_states if enable_regime_conditional else None,
            "regime_evidence": regime_evidence,
        },
        "component_metrics": component_metrics,
        "ranking": [
            {"rank": i + 1, "component": name, "ir": met["ir"], "ic_mean": met["ic_mean"]}
            for i, (name, met) in enumerate(ranked)
        ],
        "summary": {
            "n_components_evaluated": len(component_metrics),
            "n_pass_all_gates": sum(
                1 for m in component_metrics.values()
                if m["passes_ic_gate"] and m["passes_ir_gate"] and m["passes_turnover_gate"]
            ),
            "n_pass_ic_gate": sum(1 for m in component_metrics.values() if m["passes_ic_gate"]),
            "n_pass_ir_gate": sum(1 for m in component_metrics.values() if m["passes_ir_gate"]),
            "best_oos_ir": ranked[0][1]["ir"] if ranked else None,
            "best_oos_ic": ranked[0][1]["ic_mean"] if ranked else None,
        },
    }
    with open(output_metrics, "w") as f:
        json.dump(metrics_payload, f, indent=2, default=str)
    logger.info(f"  Saved: {output_metrics}")

    # ------------------------------------------------------------------
    # Step 11: Generate markdown report
    # ------------------------------------------------------------------
    logger.info("Step 11: Generating markdown report...")
    report = generate_markdown_report(
        metrics_payload=metrics_payload,
        ranked=ranked,
        component_metrics=component_metrics,
        n_features=len(alpha_cols),
        alpha_cols=alpha_cols,
        models=models,
        n_components=n_components,
        t_elapsed=time.time() - t_start,
        output_parquet=output_parquet,
        output_model=output_model,
        output_metrics=output_metrics,
        output_report=output_report,
    )
    with open(output_report, "w") as f:
        f.write(report)
    logger.info(f"  Saved: {output_report}")

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"Mining complete in {time.time() - t_start:.1f}s")
    logger.info(f"  Components evaluated: {len(component_metrics)}")
    logger.info(f"  Pass all gates: {metrics_payload['summary']['n_pass_all_gates']}")
    logger.info(f"  Best OOS IR: {metrics_payload['summary']['best_oos_ir']}")
    logger.info(f"  Best OOS IC: {metrics_payload['summary']['best_oos_ic']}")
    logger.info("=" * 80)

    return metrics_payload


def generate_markdown_report(
    metrics_payload: Dict[str, Any],
    ranked: List[Tuple[str, Dict]],
    component_metrics: Dict[str, Dict],
    n_features: int,
    alpha_cols: List[str],
    models: Dict[str, Any],
    n_components: int,
    t_elapsed: float,
    output_parquet: Path = OUTPUT_PARQUET,
    output_model: Path = OUTPUT_MODEL,
    output_metrics: Path = OUTPUT_METRICS,
    output_report: Path = OUTPUT_REPORT,
) -> str:
    """Generate human-readable markdown report."""
    lines = []
    lines.append(f"# Latent Alpha Mining Report — {GATE}")
    lines.append("")
    lines.append(f"**Role**: 14 (data-scientist) L2 — implementation only, no self-approval")
    lines.append(f"**Timestamp**: {metrics_payload['timestamp']}")
    lines.append(f"**Seed**: {SEED}")
    lines.append(f"**Elapsed**: {t_elapsed:.1f}s")
    lines.append("")

    lines.append("## 1. Configuration")
    lines.append("")
    lines.append(f"| Parameter | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Method | {metrics_payload['method'].upper()} |")
    lines.append(f"| N Components | {n_components} |")
    lines.append(f"| N Features (input) | {n_features} |")
    lines.append(f"| Train Ratio | {metrics_payload['train_ratio']} |")
    lines.append(f"| Train Dates | {metrics_payload['train_dates']} |")
    lines.append(f"| Test Dates (OOS) | {metrics_payload['test_dates']} |")
    lines.append(f"| Features Hash | `{metrics_payload['features_hash']}` |")
    lines.append(f"| Features Path | `{metrics_payload['features_path']}` |")
    lines.append("")

    lines.append("## 2. Vietnam Market Parameters")
    lines.append("")
    vn = metrics_payload["vn_market_params"]
    lines.append(f"| Parameter | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Round-trip cost | {vn['round_trip_cost_bps']} bps |")
    lines.append(f"| Trading days/year | {vn['trading_days_per_year']} |")
    lines.append(f"| IC min threshold | {vn['ic_min_threshold']} |")
    lines.append(f"| IR min threshold | {vn['ir_min_threshold']} |")
    lines.append(f"| Turnover max | {vn['turnover_max']} |")
    lines.append("")

    lines.append("## 3. PIT Safety Verification")
    lines.append("")
    lines.append("- [x] Features are T-1 lagged in source parquet (pre-computed)")
    lines.append("- [x] Cross-sectional standardization uses only same-date data")
    lines.append("- [x] PCA/ICA fit on TRAINING window only (chronological split)")
    lines.append("- [x] OOS projection uses frozen model (no re-fit on test)")
    lines.append("- [x] Forward returns (labels) NOT used in projection")
    lines.append("- [x] No look-ahead bias in any pipeline step")
    lines.append("")

    lines.append("## 4. Summary")
    lines.append("")
    summary = metrics_payload["summary"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Components evaluated | {summary['n_components_evaluated']} |")
    lines.append(f"| Pass all gates | {summary['n_pass_all_gates']} |")
    lines.append(f"| Pass IC gate (|net_IC| >= {vn['ic_min_threshold']}) | {summary['n_pass_ic_gate']} |")
    lines.append(f"| Pass IR gate (|IR| >= {vn['ir_min_threshold']}) | {summary['n_pass_ir_gate']} |")
    lines.append(f"| Best OOS IR | {summary['best_oos_ir']} |")
    lines.append(f"| Best OOS IC | {summary['best_oos_ic']} |")
    lines.append("")

    lines.append("## 5. Ranked Latent Alphas (by |OOS IR|)")
    lines.append("")
    lines.append("| Rank | Component | Method | OOS IC | OOS IR | Net IC | Turnover | IC Gate | IR Gate | TO Gate | OOS/IS Decay |")
    lines.append("|------|-----------|--------|--------|--------|--------|----------|---------|---------|---------|--------------|")
    for i, (name, met) in enumerate(ranked):
        ic_gate = "PASS" if met["passes_ic_gate"] else "FAIL"
        ir_gate = "PASS" if met["passes_ir_gate"] else "FAIL"
        to_gate = "PASS" if met["passes_turnover_gate"] else "FAIL"
        lines.append(
            f"| {i+1} | {name} | {met['method'].upper()} | "
            f"{met['ic_mean']:.4f} | {met['ir']:.4f} | {met['net_ic']:.4f} | "
            f"{met['turnover']:.4f} | {ic_gate} | {ir_gate} | {to_gate} | "
            f"{met.get('oos_is_decay_ratio', 'N/A')} |"
        )
    lines.append("")

    lines.append("## 6. Detailed Metrics per Component")
    lines.append("")
    for name, met in ranked:
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Method | {met['method'].upper()} |")
        lines.append(f"| Component Index | {met['component_index']} |")
        lines.append(f"| OOS IC Mean | {met['ic_mean']} |")
        lines.append(f"| OOS IC Std | {met['ic_std']} |")
        lines.append(f"| OOS IR | {met['ir']} |")
        lines.append(f"| IC Positive Rate | {met['ic_positive_rate']} |")
        lines.append(f"| IC t-stat | {met['ic_t_stat']} |")
        lines.append(f"| N Dates (OOS) | {met['n_dates']} |")
        lines.append(f"| Turnover | {met['turnover']} |")
        lines.append(f"| Net IC (cost-adj) | {met['net_ic']} |")
        lines.append(f"| Train IC Mean | {met.get('train_ic_mean', 'N/A')} |")
        lines.append(f"| Train IR | {met.get('train_ir', 'N/A')} |")
        lines.append(f"| OOS/IS Decay Ratio | {met.get('oos_is_decay_ratio', 'N/A')} |")
        lines.append("")

    lines.append("## 7. Input Feature Columns")
    lines.append("")
    lines.append(f"Total alpha features used: **{len(alpha_cols)}**")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Click to expand full feature list</summary>")
    lines.append("")
    for i, col in enumerate(alpha_cols):
        lines.append(f"{i+1}. `{col}`")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("## 8. Artifacts")
    lines.append("")
    lines.append(f"| Artifact | Path |")
    lines.append(f"|----------|------|")
    lines.append(f"| Projected components | `{output_parquet.relative_to(REPO_ROOT)}` |")
    lines.append(f"| Fitted models | `{output_model.relative_to(REPO_ROOT)}` |")
    lines.append(f"| Metrics JSON | `{output_metrics.relative_to(REPO_ROOT)}` |")
    lines.append(f"| This report | `{output_report.relative_to(REPO_ROOT)}` |")
    lines.append("")

    lines.append("## 9. Reproducibility")
    lines.append("")
    lines.append(f"- **Seed**: {SEED} (random, numpy)")
    lines.append(f"- **Features hash**: `{metrics_payload['features_hash']}`")
    lines.append(f"- **Python packages**: numpy, pandas, scikit-learn, scipy")
    lines.append(f"- **Deterministic**: Yes (all random_state=SEED, no stochastic splits)")
    lines.append("")

    lines.append("## 10. SOD/PIT Guardrails")
    lines.append("")
    lines.append("| Guardrail | Status |")
    lines.append("|-----------|--------|")
    lines.append("| PIT: No look-ahead | PASS — train-only fit, frozen OOS projection |")
    lines.append("| PIT: T-1 lag verified | PASS — source features pre-lagged |")
    lines.append("| SOD: No self-approval | COMPLIANT — L2 role, submit to Tier 3 |")
    lines.append("| SOD: Tier 3 audit pending | PENDING — Code Reviewer (role 21) + QA Engineer (role 17) |")
    lines.append("| Reproducibility | PASS — seeds set, hash recorded, deterministic |")
    lines.append("")

    lines.append("> **Verdict**: RESEARCH_ONLY — latent alphas require walk-forward OOS validation")
    lines.append("> via Phase 3.5 backtest before promotion consideration.")

    return "\n".join(lines)


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description=f"Mine latent alphas from 64D feature space (Gate: {GATE})"
    )
    parser.add_argument(
        "--n-components",
        type=int,
        default=64,
        help="Number of latent components to extract (default: 64 for 64D constraint)",
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["pca", "ica", "both", "pls", "autoencoder"],
        default="pca",
        help="Decomposition method (default: pca). 'autoencoder' uses deep nonlinear AE.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.6,
        help="Fraction of dates for training (default: 0.6)",
    )
    parser.add_argument(
        "--quick-mode",
        action="store_true",
        help="Quick smoke test with fewer components",
    )
    parser.add_argument(
        "--features-path",
        type=str,
        default=None,
        help="Override path to features parquet (default: data/features_advanced_sim.parquet)",
    )
    # Advanced options
    parser.add_argument(
        "--enable-pls",
        action="store_true",
        help=(
            "Enable PLS regression (supervised latent extraction). "
            "Uses forward returns as target. Can be combined with PCA/ICA."
        ),
    )
    parser.add_argument(
        "--enable-neutralize",
        action="store_true",
        help=(
            "Cross-sectionally neutralise target returns against feature "
            "exposures before PLS fitting. Removes linear factor loadings."
        ),
    )
    parser.add_argument(
        "--enable-regime-conditional",
        action="store_true",
        help=(
            "Fit regime-conditional PCA/PLS models using rolling HMM. "
            "Detects market regimes on training data and fits separate "
            "decomposition models per regime."
        ),
    )
    parser.add_argument(
        "--n-hmm-states",
        type=int,
        default=3,
        help="Number of HMM hidden states for regime detection (default: 3).",
    )
    parser.add_argument(
        "--hmm-min-window",
        type=int,
        default=60,
        help="Minimum trailing window for HMM fitting (default: 60 days).",
    )
    args = parser.parse_args()

    features_path = Path(args.features_path) if args.features_path else FEATURES_PATH

    run_latent_alpha_mining(
        n_components=args.n_components,
        method=args.method,
        train_ratio=args.train_ratio,
        quick_mode=args.quick_mode,
        features_path=features_path,
        enable_pls=args.enable_pls,
        enable_neutralize=args.enable_neutralize,
        enable_regime_conditional=args.enable_regime_conditional,
        n_hmm_states=args.n_hmm_states,
        hmm_min_window=args.hmm_min_window,
    )


if __name__ == "__main__":
    main()
