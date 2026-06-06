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
                        warmup_equity: np.ndarray | None = None
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

        # DD breaker: trip-and-hold (TC-3 fix).
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
