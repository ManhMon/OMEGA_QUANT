from __future__ import annotations

import pandas as pd


def _lagged_equity_curve(equity_curve: pd.Series) -> pd.Series:
    series = pd.Series(equity_curve, copy=True, dtype="float64")
    if series.empty:
        raise ValueError("equity_curve must contain at least 1 value")
    return series.shift(1)


def drawdown_series(equity_curve: pd.Series) -> pd.Series:
    lagged = _lagged_equity_curve(equity_curve)
    running_peak = lagged.cummax()
    return lagged.div(running_peak).sub(1.0)


def max_drawdown(equity_curve: pd.Series) -> float:
    min_drawdown = drawdown_series(equity_curve).min(skipna=True)
    if pd.isna(min_drawdown):
        return 0.0
    return abs(float(min_drawdown))


def rolling_max_drawdown(equity_curve: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    if window < 1:
        raise ValueError("window must be >= 1")
    if min_periods is None:
        min_periods = window
    if min_periods < 1 or min_periods > window:
        raise ValueError("min_periods must be between 1 and window")
    lagged = _lagged_equity_curve(equity_curve)
    rolling_peak = lagged.rolling(window=window, min_periods=min_periods).max()
    rolling_drawdown = lagged.div(rolling_peak).sub(1.0)
    rolling_mdd = rolling_drawdown.abs().rolling(window=window, min_periods=1).max()
    valid_counts = lagged.rolling(window=window, min_periods=1).count()
    return rolling_mdd.where(valid_counts >= min_periods)


def underwater_duration(equity_curve: pd.Series) -> int:
    dd = drawdown_series(equity_curve)
    underwater = dd < 0.0
    groups = underwater.ne(underwater.shift()).cumsum()
    durations = underwater.groupby(groups).cumsum().where(underwater, 0)
    return int(durations.max())


def breach_drawdown_limit(equity_curve: pd.Series, limit: float) -> bool:
    if limit < 0.0:
        raise ValueError("limit must be >= 0")
    return max_drawdown(equity_curve) >= limit
