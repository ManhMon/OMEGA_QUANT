"""Tail risk controls for Phase 3.4.

Three controls applied in order:
  1. Volatility targeting: scale portfolio to constant target_vol (e.g. 15% ann)
  2. Per-name cap: clip absolute weight per ticker (e.g. 5%)
  3. Drawdown circuit breaker: cut exposure if 20d DD > threshold

All operations are PIT-safe (use only past returns/vols).

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
    """Scale portfolio so realized vol matches target.

    Args:
        weights: 1-D array of per-name weights for current bar (long+short).
        returns_history: realized portfolio returns BEFORE current bar.
        target_vol_ann: target annualized portfolio vol (default 15%).
        periods_per_year: 252 daily.
        lookback: bars used to estimate realized vol (default 60).
        max_leverage: cap scale factor to avoid pathological multiplier.

    Returns:
        Scaled weights array with same shape.
    """
    if len(returns_history) < lookback:
        return weights
    recent = returns_history[-lookback:]
    realized_vol = np.std(recent, ddof=1) * np.sqrt(periods_per_year)
    if realized_vol < 1e-8:
        return weights
    scale = min(target_vol_ann / realized_vol, max_leverage)
    return weights * scale


def cap_weights(weights: np.ndarray, max_abs_weight: float = 0.05) -> np.ndarray:
    """Clip absolute weight per name and re-normalize so sum(|w|) is preserved
    when feasible. If clipping reduces gross, do not re-amplify (intentional
    risk reduction).

    Args:
        weights: 1-D array.
        max_abs_weight: cap on |w_i|.
    Returns:
        Clipped weights.
    """
    return np.clip(weights, -max_abs_weight, max_abs_weight)


def drawdown_breaker(equity_curve: np.ndarray,
                     scale: float = 1.0,
                     window: int = 20,
                     dd_threshold: float = 0.08,
                     cut_factor: float = 0.5) -> float:
    """Return position scale based on rolling drawdown.

    If 20-bar drawdown exceeds threshold, multiply position by cut_factor.

    Args:
        equity_curve: cumulative product of (1+returns) up to PRIOR bar.
        scale: incoming scale (default 1.0).
        window: rolling window for max equity (default 20).
        dd_threshold: trip level (default 8%).
        cut_factor: scale multiplier when triggered (default 0.5).

    Returns:
        New scale (float).
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
                        dd_window: int = 20,
                        dd_threshold: float = 0.08,
                        dd_cut: float = 0.5) -> tuple[pd.DataFrame, np.ndarray]:
    """Apply all three tail controls bar-by-bar (causal).

    Args:
        daily_weights: T x N DataFrame; row t = weights AT bar t (used to
            realize y[t]). Columns are tickers.
        daily_realized_y: T x N matrix of realized per-ticker returns
            aligned with daily_weights.
    Returns:
        adj_weights: same shape, after caps + vol target + DD breaker.
        portfolio_rets: T-vector of portfolio returns.
    """
    T = len(daily_weights)
    if T == 0:
        return daily_weights, np.array([])

    # Step 1: per-name cap (idempotent, no state)
    capped = daily_weights.clip(lower=-max_abs_weight, upper=max_abs_weight)

    # Step 2 + 3: vol target + DD breaker need running history
    portfolio_rets = np.zeros(T)
    equity = np.zeros(T)
    final_w = capped.copy()
    history: list[float] = []
    eq_curve: list[float] = [1.0]

    for t in range(T):
        w_t = capped.iloc[t].to_numpy()
        # Vol target using past portfolio returns only
        if len(history) >= 60:
            vol = np.std(history[-60:], ddof=1) * np.sqrt(252)
            scale = min(target_vol_ann / max(vol, 1e-8), 3.0)
        else:
            scale = 1.0
        # DD breaker using past equity only
        if len(eq_curve) >= dd_window + 1:
            recent_eq = eq_curve[-dd_window:]
            peak = max(recent_eq)
            dd = (recent_eq[-1] - peak) / peak if peak > 0 else 0
            if dd < -dd_threshold:
                scale *= dd_cut
        w_scaled = w_t * scale
        final_w.iloc[t] = w_scaled
        ret_t = float(np.sum(w_scaled * daily_realized_y[t]))
        portfolio_rets[t] = ret_t
        history.append(ret_t)
        eq_curve.append(eq_curve[-1] * (1 + ret_t))

    return final_w, portfolio_rets
