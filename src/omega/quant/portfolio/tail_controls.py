"""Tail risk controls for Phase 3.4 (audit-fixed v2).

Three controls applied in order:
  1. Per-name cap: clip absolute weight per ticker (default 5%)
  2. Volatility targeting: scale to constant target_vol via realized 60d
  3. Drawdown circuit breaker (TRIP-AND-HOLD): cut exposure if 20d DD > thr;
     stays cut until equity >= last high-water mark (HWM)

PIT-safe: state appends AFTER current-bar scale decision.

Fixes applied per L3 audit (.ly_state/session/audit_phase3_4.md):
  TC-3: DD breaker is now PERSISTENT (trip-and-hold semantics)
  TC-4: vol-target uses PRE-LEVERAGE portfolio returns (decouples feedback)
  TC-5: max_leverage exposed as kwarg
  TC-6: lookback / periods_per_year exposed as kwargs
  BT-2: optional warmup_history arg lets caller seed vol estimator with
        train-period returns so per-fold warmup does not run at scale=1.0
  TC-1: cap_weights doc clarified (no renorm)

Reference: Mosk & Carver "Systematic Trading" (2020) ch. 11.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

__all__ = ["vol_target_weights", "cap_weights", "drawdown_breaker",
           "soft_dynamic_brake", "dynamic_dd_threshold",
           "apply_tail_controls"]


def vol_target_weights(weights: np.ndarray, returns_history: np.ndarray,
                       target_vol_ann: float = 0.15,
                       periods_per_year: int = 252,
                       lookback: int = 60,
                       max_leverage: float = 3.0) -> np.ndarray:
    """Scale weights so realized vol matches target. Returns scaled weights."""
    if len(returns_history) < lookback:
        return weights
    recent = returns_history[-lookback:]
    realized_vol = np.std(recent, ddof=1) * np.sqrt(periods_per_year)
    if realized_vol < 1e-8:
        return weights
    scale = min(target_vol_ann / realized_vol, max_leverage)
    return weights * scale


def cap_weights(weights: np.ndarray, max_abs_weight: float = 0.05) -> np.ndarray:
    """Hard clip to +/-max_abs_weight. Gross exposure may shrink (intentional risk reduction; no renorm)."""
    return np.clip(weights, -max_abs_weight, max_abs_weight)


def drawdown_breaker(equity_curve: np.ndarray,
                     scale: float = 1.0,
                     window: int = 20,
                     dd_threshold: float = 0.08,
                     cut_factor: float = 0.5) -> float:
    """Single-bar DD breaker (kept for backward compat / unit tests).

    For trip-and-hold semantics use apply_tail_controls.
    """
    if len(equity_curve) < window:
        return scale
    recent = equity_curve[-window:]
    peak = recent.max()
    current = recent[-1]
    if peak <= 0:
        return scale
    dd = (current - peak) / peak
    if dd < -dd_threshold:
        return scale * cut_factor
    return scale


def soft_dynamic_brake(dd: float,
                        dd_threshold: float = 0.05,
                        min_scale: float = 0.1,
                        brake_depth: float = 2.0,
                        current_scale: float = 1.0) -> float:
    """Progressive brake curve for soft drawdown control (Giai phap A).

    Instead of a binary trip-and-hold, scale decreases linearly from 1.0
    to min_scale as drawdown deepens past dd_threshold toward
    brake_depth * dd_threshold.

    Args:
        dd: Current drawdown (negative = drawdown, positive = profit).
        dd_threshold: Threshold at which braking begins (positive value, e.g. 0.05 = 5%).
        min_scale: Minimum scale factor at maximum brake depth (default 0.1).
        brake_depth: Multiplier of dd_threshold at which min_scale is reached (default 2.0).
            E.g. brake_depth=2.0 with dd_threshold=0.05 → min_scale at 10% DD.
        current_scale: Incoming scale to modulate (default 1.0).

    Returns:
        Adjusted scale factor: current_scale * brake_factor.
    """
    if dd_threshold <= 0:
        return current_scale
    if dd >= 0:
        return current_scale
    abs_dd = abs(dd)
    if abs_dd <= dd_threshold:
        return current_scale

    dd_ratio = abs_dd / dd_threshold

    if brake_depth <= 1.0:
        return current_scale * min_scale

    progress = min((dd_ratio - 1.0) / (brake_depth - 1.0), 1.0)
    brake_factor = 1.0 - progress * (1.0 - min_scale)
    return current_scale * brake_factor


def dynamic_dd_threshold(realized_vol_ann: float = 0.15,
                         target_vol_ann: float = 0.15,
                         base_threshold: float = 0.05,
                         vol_sensitivity: float = 1.0,
                         min_threshold: float = 0.02,
                         max_threshold: float = 0.15) -> float:
    """Vol-adaptive DD threshold (Giai phap A).

    Higher realized vol tightens the DD threshold (earlier braking),
    lower vol loosens it (more tolerance).

    Formula: threshold = base_threshold / (vol_ratio ** vol_sensitivity)
    where vol_ratio = realized_vol_ann / target_vol_ann.

    Args:
        realized_vol_ann: Annualized realized volatility.
        target_vol_ann: Target annualized volatility (default 0.15).
        base_threshold: Base DD threshold at target vol (default 0.05).
        vol_sensitivity: Exponent controlling vol sensitivity (default 1.0).
        min_threshold: Floor for the adaptive threshold (default 0.02).
        max_threshold: Ceiling for the adaptive threshold (default 0.15).

    Returns:
        Adaptive DD threshold clipped to [min_threshold, max_threshold].
    """
    if realized_vol_ann <= 0 or target_vol_ann <= 0:
        return base_threshold

    vol_ratio = realized_vol_ann / target_vol_ann
    threshold = base_threshold / (vol_ratio ** vol_sensitivity)
    return float(np.clip(threshold, min_threshold, max_threshold))


def smooth_regime_scale(
    p_bull: float,
    p_bear: float,
    bear_scale: float,
    bull_scale: float,
    tau: float,
    bocpd_penalty_scale: float = 1.0,
) -> float:
    """Smoothly interpolate exposure between bear/bull scales from regime probabilities."""
    safe_tau = max(float(tau), 1e-6)
    score = (float(p_bull) - float(p_bear)) / safe_tau
    sigmoid = 1.0 / (1.0 + np.exp(-score))
    base_scale = float(bear_scale) + (float(bull_scale) - float(bear_scale)) * sigmoid
    return base_scale * float(bocpd_penalty_scale)


def apply_tail_controls(daily_weights: pd.DataFrame,
                        daily_realized_y: np.ndarray,
                        target_vol_ann: float = 0.15,
                        max_abs_weight: float = 0.05,
                        max_leverage: float = 3.0,
                        lookback: int = 60,
                        periods_per_year: int = 252,
                        dd_window: int = 20,
                        dd_threshold: float = 0.08,
                        dd_cut: float = 0.5,
                        warmup_history: np.ndarray | None = None,
                        warmup_equity: np.ndarray | None = None,
                        soft_brake_enabled: bool = False,
                        soft_brake_base_threshold: float = 0.05,
                        soft_brake_min_scale: float = 0.1,
                        soft_brake_depth: float = 2.0,
                        soft_brake_vol_sensitivity: float = 1.0,
                        soft_brake_min_threshold: float = 0.02,
                        soft_brake_max_threshold: float = 0.08,
                        regime_dates: pd.Index | None = None,
                        gmm_p_bull: dict[str, float] | None = None,
                        gmm_p_bear: dict[str, float] | None = None,
                        regime_ramp_enabled: bool = False,
                        regime_ramp_tau: float = 0.20,
                        regime_bear_scale: float = 0.50,
                        regime_bull_scale: float = 1.00,
                        bocpd_penalty_scale: float = 0.75,
                        ) -> tuple[pd.DataFrame, np.ndarray]:
    """Apply 3 tail controls bar-by-bar (causal).

    Args:
        daily_weights: T x N DataFrame; row t = weights AT bar t (used to realize y[t]).
        daily_realized_y: T x N matrix of realized per-ticker returns.
        target_vol_ann: 0.15 = 15% annualized portfolio vol target.
        max_abs_weight: per-name cap (intentional risk reduction; no renorm).
        max_leverage: cap on vol-target multiplier (default 3x).
        lookback: bars for realized vol estimation (default 60).
        periods_per_year: 252 daily.
        dd_window: rolling window for DD detection (default 20).
        dd_threshold: trip threshold (default 8% DD).
        dd_cut: scale multiplier when tripped (default 0.5 = 50%).
        warmup_history: pre-fold pre-leverage returns (caller-provided to fix
            per-fold warmup leakage; if None, first lookback bars run at scale=1.0).
        warmup_equity: optional cumulative equity series matching warmup_history;
            used to anchor the high-water mark for trip-and-hold DD.
        soft_brake_enabled: if True, use progressive soft brake (Giai phap A)
            instead of binary trip-and-hold DD breaker (default False).
        soft_brake_base_threshold: base DD threshold for soft brake at target vol
            (default 0.05 = 5%).
        soft_brake_min_scale: minimum scale at maximum brake depth (default 0.1).
        soft_brake_depth: multiplier of threshold at which min_scale is reached
            (default 2.0).
        soft_brake_vol_sensitivity: exponent for vol-adaptive threshold tightening
            (default 1.0).
        soft_brake_min_threshold: floor for adaptive DD threshold (default 0.02).
        soft_brake_max_threshold: ceiling for adaptive DD threshold (default 0.08).
        regime_dates: optional date index aligned to rows for regime maps.
        gmm_p_bull: optional date->bull posterior map from upstream GMM overlay.
        gmm_p_bear: optional date->bear posterior map from upstream GMM overlay.
        regime_ramp_enabled: if True, apply smooth GMM/BOCPD exposure ramp.
        regime_ramp_tau: sigmoid temperature for bull-bear probability spread.
        regime_bear_scale: minimum regime scale.
        regime_bull_scale: maximum regime scale.
        bocpd_penalty_scale: extra multiplicative penalty when bear > bull.

    Returns:
        adj_weights: same shape, after caps + vol-target + DD breaker.
        portfolio_rets: T-vector of portfolio returns (post-control).
    """
    T = len(daily_weights)
    if T == 0:
        return daily_weights, np.array([])

    # Step 1: per-name cap (idempotent, no state).
    capped = daily_weights.clip(lower=-max_abs_weight, upper=max_abs_weight)

    portfolio_rets = np.zeros(T)
    final_w = capped.copy()

    # Pre-leverage history (TC-4 fix): vol estimated on pre-scale returns.
    pre_lev_history: list[float] = (list(warmup_history)
                                     if warmup_history is not None else [])
    eq_curve: list[float] = (list(warmup_equity)
                              if warmup_equity is not None else [1.0])
    if not eq_curve:
        eq_curve = [1.0]

    # TC-3 trip-and-hold state.
    dd_tripped = False
    hwm = max(eq_curve) if eq_curve else 1.0

    for t in range(T):
        w_t = capped.iloc[t].to_numpy()

        # Vol target on PRE-LEVERAGE history.
        if len(pre_lev_history) >= lookback:
            vol = np.std(pre_lev_history[-lookback:], ddof=1) * np.sqrt(periods_per_year)
            scale = min(target_vol_ann / max(vol, 1e-8), max_leverage)
        else:
            scale = 1.0

        if regime_ramp_enabled and regime_dates is not None:
            dt_key = str(regime_dates[t])[:10]
            p_bull = 0.0 if gmm_p_bull is None else float(gmm_p_bull.get(dt_key, 0.0))
            p_bear = 0.0 if gmm_p_bear is None else float(gmm_p_bear.get(dt_key, 0.0))
            penalty = bocpd_penalty_scale if p_bear > p_bull else 1.0
            scale *= smooth_regime_scale(
                p_bull=p_bull,
                p_bear=p_bear,
                bear_scale=regime_bear_scale,
                bull_scale=regime_bull_scale,
                tau=regime_ramp_tau,
                bocpd_penalty_scale=penalty,
            )

        # DD breaker: trip-and-hold (TC-3 fix) OR soft brake (Giai phap A).
        if soft_brake_enabled:
            # Soft brake: progressive scale reduction using vol-adaptive threshold.
            # Compute realized vol from pre-leverage history for dynamic threshold.
            if len(pre_lev_history) >= lookback:
                rv = np.std(pre_lev_history[-lookback:], ddof=1) * np.sqrt(periods_per_year)
            else:
                rv = target_vol_ann
            adaptive_thr = dynamic_dd_threshold(
                realized_vol_ann=rv,
                target_vol_ann=target_vol_ann,
                base_threshold=soft_brake_base_threshold,
                vol_sensitivity=soft_brake_vol_sensitivity,
                min_threshold=soft_brake_min_threshold,
                max_threshold=soft_brake_max_threshold,
            )
            # Compute current DD from equity curve.
            if len(eq_curve) >= 2:
                peak_eq = max(eq_curve)
                current_eq = eq_curve[-1]
                current_dd = (current_eq - peak_eq) / peak_eq if peak_eq > 0 else 0.0
            else:
                current_dd = 0.0
            brake_scale = soft_dynamic_brake(
                dd=current_dd,
                dd_threshold=adaptive_thr,
                min_scale=soft_brake_min_scale,
                brake_depth=soft_brake_depth,
                current_scale=1.0,
            )
            scale *= brake_scale
        else:
            # Legacy trip-and-hold DD breaker.
            # Trip if rolling-window DD exceeds threshold OR already tripped.
            # Release ONLY when equity >= HWM.
            if len(eq_curve) >= dd_window + 1:
                recent_eq = eq_curve[-dd_window:]
                peak = max(recent_eq)
                current_eq = recent_eq[-1]
                dd = (current_eq - peak) / peak if peak > 0 else 0.0
                if (not dd_tripped) and (dd < -dd_threshold):
                    dd_tripped = True
                elif dd_tripped and current_eq >= hwm:
                    dd_tripped = False
            if dd_tripped:
                scale *= dd_cut

        # Realize bar.
        w_scaled = w_t * scale
        final_w.iloc[t] = w_scaled
        # Pre-leverage portfolio return (for vol estimation next bar).
        pre_lev_ret = float(np.sum(w_t * daily_realized_y[t]))
        # Post-leverage = realized PnL.
        ret_t = pre_lev_ret * scale if scale != 0 else 0.0
        portfolio_rets[t] = ret_t

        pre_lev_history.append(pre_lev_ret)
        new_eq = eq_curve[-1] * (1 + ret_t)
        eq_curve.append(new_eq)
        hwm = max(hwm, new_eq)

    return final_w, portfolio_rets
