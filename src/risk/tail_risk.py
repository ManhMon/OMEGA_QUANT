"""
Tail risk metrics — PIT-safe rolling variant uses T-1 lag.

Public API
----------
downside_deviation(returns, target) -> float
tail_loss_ratio(returns, threshold) -> float
expected_tail_frequency(returns, window, threshold, min_periods) -> pd.Series
tail_risk_score(returns) -> float
cross_sectional_tail_flags(asset_returns, threshold) -> pd.Series
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def downside_deviation(returns: pd.Series, target: float = 0.0) -> float:
    """Downside deviation: RMS of returns below *target*."""
    below = returns[returns < target]
    if below.empty:
        return 0.0
    return float(np.sqrt((below ** 2).mean()))


def tail_loss_ratio(returns: pd.Series, threshold: float = -0.02) -> float:
    """Fraction of returns at or below *threshold*."""
    if returns.empty:
        return 0.0
    return float((returns <= threshold).mean())


def expected_tail_frequency(
    returns: pd.Series,
    window: int = 20,
    threshold: float = -0.02,
    min_periods: int | None = None,
) -> pd.Series:
    """
    Rolling tail-breach frequency with T-1 lag.

    Position i uses returns[i-window : i] (excludes bar i).
    Raises ValueError if min_periods > window.
    """
    mp = min_periods if min_periods is not None else window
    if mp > window:
        raise ValueError(
            f"min_periods ({mp}) must be <= window ({window})"
        )
    result = pd.Series(np.nan, index=returns.index, dtype="float64")
    for i in range(len(returns)):
        start = max(0, i - window)
        slice_ = returns.iloc[start:i]  # T-1 lag
        if len(slice_) >= mp:
            result.iloc[i] = float((slice_ <= threshold).mean())
    return result


def tail_risk_score(returns: pd.Series, threshold: float = -0.02) -> float:
    """
    Composite tail risk score: downside_deviation * (1 + tail_loss_ratio).

    Higher = worse tail risk.
    """
    dd = downside_deviation(returns)
    tlr = tail_loss_ratio(returns, threshold)
    return dd * (1.0 + tlr)


def cross_sectional_tail_flags(
    asset_returns: pd.DataFrame,
    threshold: float = -0.02,
) -> pd.Series:
    """
    Flag assets whose T-1 return (second-to-last row) breached *threshold*.

    Raises ValueError if frame is empty or has fewer than 2 rows (no T-1 history).
    """
    if asset_returns.empty:
        raise ValueError("asset_returns must not be empty")
    if len(asset_returns) < 2:
        raise ValueError("Need at least 2 rows for T-1 history")
    t_minus_1 = asset_returns.iloc[-2]
    return t_minus_1 <= threshold
