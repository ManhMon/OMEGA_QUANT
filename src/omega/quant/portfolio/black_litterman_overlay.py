"""
OMEGA_QUANT Black-Litterman Overlay for Pipeline A
Uses BL optimizer to adjust weights based on alpha views + market equilibrium.

Flag: --black-litterman
Logic: Combine Ridge signal (views) with equal-weight equilibrium via BL framework.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Views from T-1 signal, covariance from past returns.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import math
from pathlib import Path
import sys
from typing import Any, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

from omega.core.llm_config import _canonical

logger = logging.getLogger(__name__)


def apply_black_litterman_overlay(
    daily_weights: pd.DataFrame,
    returns_matrix: np.ndarray,
    signal_matrix: np.ndarray,
    tau: float = 0.05,
    view_confidence: float = 0.5,
    l2_reg: float = 0.01,
    max_weight: float = 0.05,
) -> pd.DataFrame:
    """
    Apply Black-Litterman optimization to adjust weights.

    Combines market equilibrium (equal-weight) with alpha views (signal).
    BL produces posterior expected returns -> optimize weights.

    Args:
        daily_weights: T x N original weights (from signal ranking)
        returns_matrix: T x N asset returns for covariance estimation
        signal_matrix: T x N alpha signal values (views)
        tau: Uncertainty in equilibrium (lower = trust market more)
        view_confidence: Confidence in alpha views (0-1)
        l2_reg: L2 regularization for weight stability
        max_weight: Maximum single-asset weight

    Returns:
        BL-optimized weights.
    """
    T, N = returns_matrix.shape

    if T < 60 or N < 3:
        return daily_weights

    try:
        from omega.quant.strategy.black_litterman import BlackLittermanOptimizer
        bl = BlackLittermanOptimizer()

        # Use rolling covariance (last 120 days) for BL
        lookback = min(120, T - 1)
        adjusted = daily_weights.copy()

        # Apply BL at periodic intervals (every 20 bars) to reduce computation
        rebal_interval = 20

        for t in range(lookback, T, rebal_interval):
            window_end = min(t + rebal_interval, T)

            # Covariance from past returns (PIT-safe)
            cov_window = returns_matrix[max(0, t - lookback):t]
            cov_matrix = np.cov(cov_window.T) + l2_reg * np.eye(N)

            # Equilibrium returns (from equal-weight portfolio)
            eq_weights = np.ones(N) / N
            risk_aversion = 2.5
            pi = risk_aversion * cov_matrix @ eq_weights  # Implied equilibrium returns

            # Views from signal (T-1 lagged)
            if t > 0 and t - 1 < len(signal_matrix):
                views = signal_matrix[t - 1]  # T-1 signal as view
            else:
                views = np.zeros(N)

            # BL posterior: combine equilibrium + views
            omega = np.diag(np.diag(tau * cov_matrix)) / view_confidence  # View uncertainty
            P = np.eye(N)  # Each asset has its own view
            Q = views  # View values

            # BL formula: posterior_mu = pi + tau*Sigma*P'*(P*tau*Sigma*P' + Omega)^-1 * (Q - P*pi)
            tau_sigma = tau * cov_matrix
            M = P @ tau_sigma @ P.T + omega
            try:
                M_inv = np.linalg.inv(M)
            except np.linalg.LinAlgError:
                M_inv = np.linalg.pinv(M)

            posterior_mu = pi + tau_sigma @ P.T @ M_inv @ (Q - P @ pi)

            # Optimal weights from posterior (mean-variance)
            try:
                sigma_inv = np.linalg.inv(cov_matrix)
            except np.linalg.LinAlgError:
                sigma_inv = np.linalg.pinv(cov_matrix)

            raw_weights = sigma_inv @ posterior_mu
            raw_weights = np.maximum(raw_weights, 0)  # Long-only
            raw_weights = np.minimum(raw_weights, max_weight)

            w_sum = raw_weights.sum()
            if w_sum > 0:
                bl_weights = raw_weights / w_sum
            else:
                bl_weights = eq_weights

            # Apply BL weights to the rebalance window
            for bar in range(t, window_end):
                if bar < len(adjusted):
                    adjusted.iloc[bar] = bl_weights

        logger.info("Black-Litterman overlay applied: tau=%.3f, confidence=%.2f, rebal_every=%d",
                    tau, view_confidence, rebal_interval)
        return adjusted

    except ImportError:
        logger.warning("BlackLittermanOptimizer not available, returning original weights")
        return daily_weights
    except Exception as e:
        logger.warning("BL overlay failed: %s, returning original weights", e)
        return daily_weights


# =====================================================================
# W6 CALIBRATED BLACK-LITTERMAN POSTERIOR PROPOSAL (SHADOW-ONLY API)
# =====================================================================

GATE_ID_W6 = "GATE_JEV_DEEP_INTEGRATION_W6_20260930"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _valid_p_row(p: np.ndarray) -> bool:
    if abs(float(np.sum(p))) <= 1e-6:
        pos, neg = p[p > 0.0], p[p < 0.0]
        return len(pos) > 0 and len(neg) > 0 and abs(float(np.sum(pos)) - 1.0) <= 1e-6 and abs(float(np.sum(neg)) + 1.0) <= 1e-6
    return bool(np.all(p >= -1e-12) and abs(float(np.sum(p)) - 1.0) <= 1e-6)


def apply_calibrated_black_litterman_overlay(
    baseline_weights: pd.Series,
    ordered_assets: Sequence[str],
    cutoff: datetime,
    calibration_maturity: datetime,
    covariance_matrix: Optional[np.ndarray] = None,
    ordered_view_ids: Optional[Sequence[str]] = None,
    P: Optional[np.ndarray] = None,
    Q: Optional[np.ndarray] = None,
    calibration_errors: Optional[np.ndarray] = None,
    tau: float = 0.05,
    delta: float = 2.5,
    rho: float = 1e-4,
    kappa_max: float = 1e6,
    residual_tol: float = 1e-4,
    v_floor: float = 1e-8,
    omega_floor: float = 1e-6,
    c_min: float = 0.01,
    c_max: float = 100.0,
    max_saturation_rate: float = 0.5,
    return_horizon: str = "daily",
    return_units: str = "simple_return",
    gate_id: str = GATE_ID_W6,
    decision_id: Optional[str] = None,
    source_revision: str = "R1",
    policy_version: str = "P1",
) -> Tuple[pd.Series, dict[str, Any]]:
    """W6 calibrated Black-Litterman posterior proposal (bounded shadow-only)."""
    # 1. Strict Baseline Validation (unsafe raises)
    if not isinstance(baseline_weights, pd.Series):
        raise TypeError("baseline_weights must be a pd.Series")
    if not (np.issubdtype(baseline_weights.dtype, np.floating) or np.issubdtype(baseline_weights.dtype, np.integer)) or pd.api.types.is_bool_dtype(baseline_weights.dtype):
        raise TypeError("baseline_weights must have numeric float/int dtype")
    N = len(ordered_assets) if isinstance(ordered_assets, (list, tuple)) else -1
    if N < 1 or N > 256 or any(type(a) is not str or not a or len(a) > 32 for a in ordered_assets) or len(set(ordered_assets)) != N or "CASH" in ordered_assets:
        raise ValueError("ordered_assets must be sequence of 1..256 unique string IDs")
    M_base = len(baseline_weights)
    if M_base not in (N, N + 1) or M_base > 257 or list(baseline_weights.index[:N]) != list(ordered_assets) or (M_base == N + 1 and baseline_weights.index[N] != "CASH"):
        raise ValueError("baseline_weights must strictly match ordered_assets with optional trailing CASH")
    vals = baseline_weights.to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(vals)) or np.any(vals < 0.0) or float(np.sum(vals)) > 1.0 + 1e-6:
        raise ValueError("baseline_weights must be finite, non-negative, and sum <= 1 + 1e-6")

    baseline_copy = baseline_weights.copy()
    w0 = vals[:N]
    baseline_digest = _sha(_canonical({"index": list(baseline_weights.index), "dtype": str(baseline_weights.dtype), "values": [float(x) for x in vals]}))

    def _fallback(reason: str, c_s: str = "unknown", m_s: str = "unknown", status: str = "fallback", prop: Optional[dict[str, Any]] = None) -> Tuple[pd.Series, dict[str, Any]]:
        shas = [_sha(_canonical({"shape": list(a.shape), "dtype": str(a.dtype), "bytes": _sha(a.tobytes())}))
                if isinstance(a, np.ndarray) and a.dtype.kind in "iuf" and a.size <= 262144 else ""
                for a in (covariance_matrix, P, Q, calibration_errors)]
        f = lambda v: float(v) if isinstance(v, (int, float)) and -sys.float_info.max <= v <= sys.float_info.max and math.isfinite(v) else 0.0
        inp_manifest = {
            "c_max": f(c_max), "c_min": f(c_min), "covariance_sha256": shas[0], "delta": f(delta),
            "errors_sha256": shas[3], "kappa_max": f(kappa_max), "max_saturation_rate": f(max_saturation_rate),
            "omega_floor": f(omega_floor), "p_sha256": shas[1], "q_sha256": shas[2], "residual_tol": f(residual_tol),
            "return_horizon": "daily", "return_units": "simple_return", "rho": f(rho), "tau": f(tau), "v_floor": f(v_floor),
        }
        input_digest = _sha(_canonical(inp_manifest))
        def safe_id(value, default):
            if type(value) is not str or not 1 <= len(value) <= 64 or not all(c.isascii() and (c.isalnum() or c in "_-.") for c in value):
                return default
            try:
                _canonical(value)
            except ValueError:
                return default
            return value
        eff_dec = safe_id(decision_id, f"BL_{input_digest[:16]}")
        payload = {
            "advisory_only": True, "applied": False, "baseline_digest": baseline_digest,
            "calibration_maturity": m_s, "cutoff": c_s, "decision_id": eff_dec, "gate_id": GATE_ID_W6,
            "input_digest": input_digest, "live_influence": 0.0, "ordered_assets": list(ordered_assets),
            "ordered_view_ids": [safe_id(v, "rejected") for v in ordered_view_ids]
                if type(ordered_view_ids) in (list, tuple) and len(ordered_view_ids) <= 64 else [],
            "policy_version": safe_id(policy_version, "rejected"),
            "posterior_proposal": prop, "reason": reason, "return_horizon": "daily",
            "return_units": "simple_return", "source_revision": safe_id(source_revision, "rejected"), "status": status,
        }
        return baseline_copy, {**payload, "decision_digest": _sha(_canonical(payload))}

    # 2. Timezone & Horizon Bounds
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        return _fallback("INVALID_CUTOFF")
    if not isinstance(calibration_maturity, datetime) or calibration_maturity.tzinfo is None or calibration_maturity.utcoffset() is None:
        return _fallback("INVALID_CUTOFF", c_s=cutoff.isoformat())
    cutoff_iso = cutoff.astimezone(timezone.utc).isoformat()
    mat_iso = calibration_maturity.astimezone(timezone.utc).isoformat()
    if mat_iso > cutoff_iso:
        return _fallback("CALIBRATION_NOT_MATURE", cutoff_iso, mat_iso)
    if return_horizon != "daily" or return_units != "simple_return" or gate_id != GATE_ID_W6:
        return _fallback("INVALID_HORIZON_OR_UNITS", cutoff_iso, mat_iso)
    identifiers = [source_revision, policy_version, *([] if decision_id is None else [decision_id])]
    if type(ordered_view_ids) in (list, tuple) and len(ordered_view_ids) <= 64:
        identifiers.extend(ordered_view_ids)
    if any(type(v) is not str or not 1 <= len(v) <= 64 or
           not all(c.isascii() and (c.isalnum() or c in "_-.") for c in v) for v in identifiers):
        return _fallback("INVALID_IDENTIFIERS", cutoff_iso, mat_iso)
    try:
        _canonical(identifiers)
    except ValueError:
        return _fallback("INVALID_IDENTIFIERS", cutoff_iso, mat_iso)

    # 3. Hyperparameter validation
    params = [tau, delta, rho, kappa_max, residual_tol, v_floor, omega_floor, c_min, c_max]
    if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or x <= 0.0 or x > 1e6 or not math.isfinite(x) for x in params)
            or c_min > c_max or kappa_max < 1.0 or type(max_saturation_rate) not in (int, float)
            or not (0.0 <= max_saturation_rate <= 1.0) or not math.isfinite(max_saturation_rate)):
        return _fallback("INVALID_HYPERPARAMETERS", cutoff_iso, mat_iso)

    # 4. K=0 Bypass (before checking covariance or running any numpy solver)
    if ordered_view_ids is None or type(ordered_view_ids) in (list, tuple) and len(ordered_view_ids) == 0:
        return _fallback("K0_BYPASS", cutoff_iso, mat_iso, status="k0_bypass")

    # 5. Views validation
    if type(ordered_view_ids) not in (list, tuple):
        return _fallback("INVALID_VIEWS", cutoff_iso, mat_iso)
    K = len(ordered_view_ids)
    if K > 64 or any(type(v) is not str or not v or len(v) > 64 for v in ordered_view_ids) or len(set(ordered_view_ids)) != K:
        return _fallback("INVALID_VIEWS", cutoff_iso, mat_iso)
    if not isinstance(P, np.ndarray) or not np.issubdtype(P.dtype, np.floating) or P.dtype == bool or P.shape != (K, N) or not np.all(np.isfinite(P)) or len(np.unique(P, axis=0)) != K or any(not _valid_p_row(P[k]) for k in range(K)):
        return _fallback("INVALID_P_MATRIX", cutoff_iso, mat_iso)
    if not isinstance(Q, np.ndarray) or not np.issubdtype(Q.dtype, np.floating) or Q.dtype == bool or Q.shape not in ((K,), (K, 1)) or not np.all(np.isfinite(Q)):
        return _fallback("INVALID_Q_VECTOR", cutoff_iso, mat_iso)
    Q_vec = Q.reshape(-1)

    # 6. Calibration Errors Validation (2D K x M, min M=20)
    if not isinstance(calibration_errors, np.ndarray) or not np.issubdtype(calibration_errors.dtype, np.floating) or calibration_errors.dtype == bool or calibration_errors.ndim != 2 or calibration_errors.shape[0] != K or calibration_errors.shape[1] < 20 or calibration_errors.shape[1] > 4096 or not np.all(np.isfinite(calibration_errors)):
        return _fallback("INVALID_CALIBRATION_ERRORS", cutoff_iso, mat_iso)

    try:
        with np.errstate(over="raise", invalid="raise"):
            s2 = np.mean(calibration_errors ** 2, axis=1)
        if np.any(s2 <= 0.0) or not np.all(np.isfinite(s2)):
            return _fallback("INVALID_CALIBRATION_ERRORS", cutoff_iso, mat_iso)

        # 7. Covariance Validation (strict symmetry 1e-12, PSD on original Sigma)
        if not isinstance(covariance_matrix, np.ndarray) or not np.issubdtype(covariance_matrix.dtype, np.floating) or covariance_matrix.dtype == bool or covariance_matrix.shape != (N, N) or not np.all(np.isfinite(covariance_matrix)) or np.max(np.abs(covariance_matrix - covariance_matrix.T)) > 1e-12:
            return _fallback("INVALID_COVARIANCE", cutoff_iso, mat_iso)
        eig_orig = np.linalg.eigvalsh(covariance_matrix)
        if np.min(eig_orig) < -1e-12:
            return _fallback("COVARIANCE_NOT_PSD", cutoff_iso, mat_iso)
        Sigma_s = (covariance_matrix + covariance_matrix.T) / 2.0
        Sigma_r = Sigma_s + rho * np.eye(N, dtype=np.float64)
        eig_r = np.linalg.eigvalsh(Sigma_r)
        if np.min(eig_r) <= 0:
            return _fallback("COVARIANCE_NOT_PSD", cutoff_iso, mat_iso)
        cond_Sigma = float(np.max(eig_r)) / float(np.min(eig_r))
        if cond_Sigma > kappa_max or cond_Sigma > 1e12:
            return _fallback("COVARIANCE_CONDITION_EXCEEDED", cutoff_iso, mat_iso)

        # 8. Empirical Omega
        tau_Sigma_r = tau * Sigma_r
        v_vec = np.zeros(K, dtype=np.float64)
        for k in range(K):
            vk = float(P[k] @ tau_Sigma_r @ P[k])
            if vk <= v_floor or not math.isfinite(vk):
                return _fallback("VIEW_VARIANCE_BELOW_FLOOR", cutoff_iso, mat_iso)
            v_vec[k] = vk

        r = s2 / v_vec
        clipping_rate = float(np.mean((r < c_min) | (r > c_max)))
        if clipping_rate > max_saturation_rate:
            return _fallback("SATURATION_EXCEEDED", cutoff_iso, mat_iso)

        c = np.clip(r, c_min, c_max)
        omega = np.maximum(omega_floor, c * v_vec)
        Omega = np.diag(omega)

        # 9. Solve Posterior mu_BL
        pi = delta * (Sigma_r @ w0)
        A = P @ tau_Sigma_r @ P.T + Omega
        eig_A = np.linalg.eigvalsh(A)
        min_A = float(np.min(eig_A))
        if min_A <= 0.0:
            return _fallback("SYSTEM_NOT_SPD", cutoff_iso, mat_iso)
        cond_A = float(np.max(eig_A)) / min_A
        if cond_A > kappa_max or cond_A > 1e12:
            return _fallback("SYSTEM_CONDITION_EXCEEDED", cutoff_iso, mat_iso)

        rhs = Q_vec - P @ pi
        x = np.linalg.solve(A, rhs)
        res = float(np.linalg.norm(A @ x - rhs) / max(float(np.linalg.norm(rhs)), 1e-12))
        if not math.isfinite(res) or res > residual_tol:
            return _fallback("RESIDUAL_EXCEEDED", cutoff_iso, mat_iso)

        mu_BL = pi + tau_Sigma_r @ P.T @ x
        if not np.all(np.isfinite(mu_BL)):
            return _fallback("NON_FINITE_POSTERIOR", cutoff_iso, mat_iso)

        proposal = {
            "clipping_rate": float(clipping_rate), "cond_A": float(cond_A), "cond_Sigma_r": float(cond_Sigma),
            "mu_BL": [float(val) for val in mu_BL], "omega_diag": [float(val) for val in omega], "pi": [float(val) for val in pi],
            "solve_residual": float(res), "unclipped_ratios": [float(val) for val in r], "clipped_ratios": [float(val) for val in c],
        }
        return _fallback("SUCCESS", cutoff_iso, mat_iso, status="proposal_ready", prop=proposal)

    except (FloatingPointError, np.linalg.LinAlgError, MemoryError, ValueError, OverflowError):
        return _fallback("NUMERICAL_OR_MEMORY_ERROR", cutoff_iso, mat_iso)
