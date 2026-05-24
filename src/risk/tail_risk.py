from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(returns: pd.Series | np.ndarray | list[float], name: str = "returns") -> pd.Series:
    series = pd.Series(returns, copy=True, dtype="float64")
    if series.empty:
        raise ValueError(f"{name} must contain at least 1 value")
    return series


def downside_deviation(returns: pd.Series | np.ndarray | list[float], target: float = 0.0) -> float:
    series = _to_series(returns).dropna()
    downside = np.minimum(series - target, 0.0)
    return float(np.sqrt(np.mean(np.square(downside))))


def tail_loss_ratio(returns: pd.Series | np.ndarray | list[float], threshold: float = -0.02) -> float:
    series = _to_series(returns).dropna()
    return float((series <= threshold).mean())


def expected_tail_frequency(
    returns: pd.Series,
    window: int,
    threshold: float = -0.02,
    min_periods: int | None = None,
) -> pd.Series:
    if window < 1:
        raise ValueError("window must be >= 1")
    if min_periods is None:
        min_periods = window
    if min_periods < 1 or min_periods > window:
        raise ValueError("min_periods must be between 1 and window")
    series = _to_series(returns)
    lagged = series.shift(1)
    return lagged.le(threshold).rolling(window=window, min_periods=min_periods).mean()


def tail_risk_score(returns: pd.Series | np.ndarray | list[float]) -> float:
    series = _to_series(returns).dropna()
    if series.std(ddof=0) == 0.0:
        z_score = 0.0
    else:
        z_score = abs(float((series.min() - series.mean()) / series.std(ddof=0)))
    return float(z_score + downside_deviation(series) * 100.0 + tail_loss_ratio(series) * 10.0)


def cross_sectional_tail_flags(asset_returns: pd.DataFrame, threshold: float = -0.03) -> pd.Series:
    if asset_returns.empty:
        raise ValueError("asset_returns must contain at least 1 row")
    lagged = asset_returns.shift(1)
    if lagged.iloc[-1].isna().all():
        raise ValueError("asset_returns must contain at least 1 row of T-1 history")
    latest = lagged.iloc[-1]
    return latest.le(threshold).fillna(False)
