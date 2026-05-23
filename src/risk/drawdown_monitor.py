"""
Drawdown monitoring — PIT-safe rolling variant uses T-1 lag.

Public API
----------
drawdown_series(equity_curve) -> pd.Series
max_drawdown(equity_curve) -> float
rolling_max_drawdown(equity_curve, window) -> pd.Series
underwater_duration(equity_curve) -> int
breach_drawdown_limit(equity_curve, limit) -> bool
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _drawdown_series_raw(equity_curve: pd.Series) -> pd.Series:
    """Standard (non-lagged) drawdown: value[i] / cummax[0..i] - 1. No NaN padding."""
    running_peak = equity_curve.cummax()
    return equity_curve / running_peak - 1.0


def drawdown_series(equity_curve: pd.Series) -> pd.Series:
    """
    Per-bar drawdown series with T-1 lag.

    Position i reports the drawdown that was observable at bar i-1:
        drawdown[i] = equity_curve[i-1] / cummax(equity_curve[0:i]) - 1

    First bar is NaN (no prior bar). This ensures no look-ahead.
    """
    if equity_curve.empty:
        raise ValueError("equity_curve must not be empty")
    standard_dd = _drawdown_series_raw(equity_curve)
    return standard_dd.shift(1)


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown magnitude (positive value). Returns 0.0 for single-bar series."""
    if equity_curve.empty:
        raise ValueError("equity_curve must not be empty")
    if len(equity_curve) < 2:
        return 0.0
    dd = _drawdown_series_raw(equity_curve).dropna()
    if dd.empty:
        return 0.0
    return float(abs(dd.min()))


def rolling_max_drawdown(equity_curve: pd.Series, window: int = 20) -> pd.Series:
    """
    Rolling max drawdown with T-1 lag.

    Position i uses equity_curve[i-window : i] (excludes bar i).
    Uses non-lagged drawdown within each window slice since the T-1 lag
    is already enforced by excluding bar i from the window.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    result = pd.Series(np.nan, index=equity_curve.index, dtype="float64")
    for i in range(len(equity_curve)):
        start = max(0, i - window)
        slice_ = equity_curve.iloc[start:i]  # T-1 lag: excludes bar i
        if len(slice_) >= 2:
            result.iloc[i] = max_drawdown(slice_)
    return result


def underwater_duration(equity_curve: pd.Series) -> int:
    """Longest consecutive run of bars below the prior peak (drawdown < 0)."""
    dd = _drawdown_series_raw(equity_curve).fillna(0.0)
    below = (dd < 0.0).astype(int)
    max_run = 0
    current = 0
    for v in below:
        if v:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def breach_drawdown_limit(equity_curve: pd.Series, limit: float = 0.20) -> bool:
    """Return True if max_drawdown exceeds *limit* (positive fraction)."""
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    return max_drawdown(equity_curve) > limit
