"""
CVaR / VaR — functional API, PIT-safe (T-1 lag on rolling/portfolio variants).

Public API
----------
var_historical(returns, confidence) -> float
cvar_historical(returns, confidence) -> float
rolling_cvar(returns, window, confidence, min_periods) -> pd.Series
portfolio_cvar(asset_returns, weights, confidence) -> float
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_confidence(confidence: float) -> None:
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")


def var_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR (positive = loss magnitude). Uses lower interpolation (no smoothing)."""
    _validate_confidence(confidence)
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    q = np.quantile(clean.values, 1.0 - confidence, method="lower")
    return float(abs(q))


def cvar_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical CVaR / Expected Shortfall (positive = loss magnitude)."""
    _validate_confidence(confidence)
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    threshold = np.quantile(clean.values, 1.0 - confidence)
    tail = clean[clean <= threshold]
    if tail.empty:
        return float(abs(threshold))
    return float(abs(tail.mean()))


def rolling_cvar(
    returns: pd.Series,
    window: int = 20,
    confidence: float = 0.95,
    min_periods: int | None = None,
) -> pd.Series:
    """
    Rolling CVaR with T-1 lag (each position i uses returns[i-window : i]).

    Position i is computed from the window ending at i-1 (exclusive of i),
    so there is no look-ahead.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    _validate_confidence(confidence)
    mp = min_periods if min_periods is not None else window

    result = pd.Series(np.nan, index=returns.index, dtype="float64")
    for i in range(len(returns)):
        start = i - window
        if start < 0:
            start = 0
        slice_ = returns.iloc[start:i]  # excludes index i → T-1 lag
        if len(slice_) >= mp:
            result.iloc[i] = cvar_historical(slice_, confidence)
    return result


def portfolio_cvar(
    asset_returns: pd.DataFrame,
    weights: dict[str, float],
    confidence: float = 0.95,
) -> float:
    """
    Portfolio CVaR using T-1 lagged asset returns.

    Shifts asset_returns by 1 row before computing weighted portfolio returns,
    ensuring no look-ahead.
    """
    _validate_confidence(confidence)
    w = pd.Series(weights)
    lagged = asset_returns.shift(1)
    portfolio_ret = lagged.mul(w, axis=1).sum(axis=1).dropna()
    return cvar_historical(portfolio_ret, confidence)
