from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(returns: pd.Series | np.ndarray | list[float], name: str = "returns") -> pd.Series:
    series = pd.Series(returns, copy=True, dtype="float64")
    if series.empty:
        raise ValueError(f"{name} must contain at least 1 value")
    return series


def _validate_confidence(confidence: float) -> None:
    if confidence <= 0.0 or confidence >= 1.0:
        raise ValueError("confidence must be between 0 and 1")


def _tail_count(length: int, confidence: float) -> int:
    return max(1, int(np.ceil((1.0 - confidence) * length)))


def var_historical(returns: pd.Series | np.ndarray | list[float], confidence: float = 0.95) -> float:
    _validate_confidence(confidence)
    series = _to_series(returns).dropna()
    if series.empty:
        raise ValueError("returns must contain at least 1 non-null value")
    sorted_returns = np.sort(series.to_numpy())
    tail_count = _tail_count(len(sorted_returns), confidence)
    return abs(float(sorted_returns[tail_count - 1]))


def cvar_historical(returns: pd.Series | np.ndarray | list[float], confidence: float = 0.95) -> float:
    _validate_confidence(confidence)
    series = _to_series(returns).dropna()
    if series.empty:
        raise ValueError("returns must contain at least 1 non-null value")
    sorted_returns = np.sort(series.to_numpy())
    tail_count = _tail_count(len(sorted_returns), confidence)
    return abs(float(sorted_returns[:tail_count].mean()))


def _rolling_window_cvar(values: np.ndarray, confidence: float) -> float:
    if len(values) == 0:
        return float(np.nan)
    sorted_values = np.sort(values)
    tail_count = _tail_count(len(sorted_values), confidence)
    return abs(float(sorted_values[:tail_count].mean()))


def rolling_cvar(
    returns: pd.Series,
    window: int,
    confidence: float = 0.95,
    min_periods: int | None = None,
) -> pd.Series:
    _validate_confidence(confidence)
    if window < 1:
        raise ValueError("window must be >= 1")
    if min_periods is None:
        min_periods = window
    if min_periods < 1 or min_periods > window:
        raise ValueError("min_periods must be between 1 and window")

    series = _to_series(returns)
    lagged = series.shift(1)
    return lagged.rolling(window=window, min_periods=min_periods).apply(
        _rolling_window_cvar,
        args=(confidence,),
        raw=True,
    )


def portfolio_cvar(
    asset_returns: pd.DataFrame,
    weights: pd.Series | dict[str, float],
    confidence: float = 0.95,
) -> float:
    _validate_confidence(confidence)
    if asset_returns.empty:
        raise ValueError("asset_returns must contain at least 1 row")
    weight_series = pd.Series(weights, dtype="float64")
    missing = asset_returns.columns.difference(weight_series.index)
    if len(missing) > 0:
        raise ValueError(f"weights missing assets: {list(missing)}")
    lagged_returns = asset_returns[weight_series.index].shift(1)
    portfolio_returns = lagged_returns.mul(weight_series, axis=1).sum(axis=1, min_count=1).dropna()
    if portfolio_returns.empty:
        raise ValueError("portfolio_returns is empty after T-1 lag")
    return cvar_historical(portfolio_returns, confidence=confidence)
