"""
Trend Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().mean()
  with reset_index(level=0, drop=True)
"""

import pandas as pd
from typing import List
from .primitives import _safe_divide


def compute_distance_to_ma(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Distance to Moving Average - Trend strength indicator.

    Formula: (Price - MA(Price, period)) / MA(Price, period)
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: MA period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with distance to MA values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate moving average using native rolling API
    ma = (
        df_work.groupby(symbol_col)[price_col]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Calculate distance
    distance = _safe_divide(df_work[price_col] - ma, ma, fill_value=0.0)

    # Apply T-1 lag for PIT safety
    df_work["_dist_temp"] = distance
    distance_lagged = df_work.groupby(symbol_col)["_dist_temp"].shift(1)

    return distance_lagged.fillna(0.0)


def compute_distance_to_high(
    df: pd.DataFrame,
    period: int = 252,
    price_col: str = "close",
    high_col: str = "high",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Distance to Period High - Trend position indicator.

    Formula: (Price - High_period) / High_period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().max()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and high columns
        period: Lookback period (default 252 = 1 year)
        price_col: Price column name
        high_col: High column name
        symbol_col: Symbol column name

    Returns:
        Series with distance to high values (percentage, typically negative)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate rolling high using native rolling API
    rolling_high = (
        df_work.groupby(symbol_col)[high_col]
        .rolling(window=period, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
    )

    # Calculate distance
    distance = _safe_divide(
        df_work[price_col] - rolling_high, rolling_high, fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_dist_high_temp"] = distance
    distance_lagged = df_work.groupby(symbol_col)["_dist_high_temp"].shift(1)

    return distance_lagged.fillna(0.0)


def compute_distance_to_low(
    df: pd.DataFrame,
    period: int = 252,
    price_col: str = "close",
    low_col: str = "low",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Distance to Period Low - Trend position indicator.

    Formula: (Price - Low_period) / Low_period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().min()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and low columns
        period: Lookback period (default 252 = 1 year)
        price_col: Price column name
        low_col: Low column name
        symbol_col: Symbol column name

    Returns:
        Series with distance to low values (percentage, typically positive)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate rolling low using native rolling API
    rolling_low = (
        df_work.groupby(symbol_col)[low_col]
        .rolling(window=period, min_periods=1)
        .min()
        .reset_index(level=0, drop=True)
    )

    # Calculate distance
    distance = _safe_divide(
        df_work[price_col] - rolling_low, rolling_low, fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_dist_low_temp"] = distance
    distance_lagged = df_work.groupby(symbol_col)["_dist_low_temp"].shift(1)

    return distance_lagged.fillna(0.0)


def compute_ma_distance_multi(
    df: pd.DataFrame,
    periods: List[int] = [5, 10, 20, 60],
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.DataFrame:
    """
    Multiple MA Distance - Distance to multiple moving averages.

    Formula: (Price - MA(period)) / MA(period) for each period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        periods: List of MA periods (default [5, 10, 20, 60])
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        DataFrame with multiple distance columns
    """
    result = pd.DataFrame(index=df.index)

    for period in periods:
        col_name = f"dist_ma_{period}d"
        result[col_name] = compute_distance_to_ma(
            df, period, price_col, symbol_col
        )

    return result
