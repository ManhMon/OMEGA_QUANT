"""
Volume Profile Alpha Functions

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
import numpy as np
from .primitives import _safe_divide


def compute_vwap_distance(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VWAP Distance - Distance from Volume-Weighted Average Price.

    Formula: (Close - VWAP) / VWAP
             where VWAP = cumsum(price * volume) / cumsum(volume) per day
    PIT: Uses T-1 lagged data.

    Args:
        df: DataFrame with date, symbol, close, volume columns
        symbol_col: Symbol column name

    Returns:
        Series with VWAP distance values (float64, percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate VWAP (intraday approximation using close price)
    pv = close_lagged * volume_lagged
    df_work["_pv"] = pv
    df_work["_volume_lagged"] = volume_lagged

    # Calculate cumulative sums per date (reset daily)
    cumsum_pv = df_work.groupby(["date", symbol_col])["_pv"].cumsum()
    cumsum_vol = df_work.groupby(["date", symbol_col])[
        "_volume_lagged"
    ].cumsum()

    # Calculate VWAP with fallback to close price
    vwap = cumsum_pv / cumsum_vol.replace(0, np.nan)
    vwap = vwap.fillna(close_lagged)

    # Calculate distance
    distance = _safe_divide(close_lagged - vwap, vwap, fill_value=0.0)

    return distance.astype(np.float64).fillna(0.0)


def compute_twap_deviation(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    TWAP Deviation - Deviation from Time-Weighted Average Price.

    Formula: (Close - TWAP) / TWAP
             where TWAP = mean(close) per day
    PIT: Uses T-1 lagged data.

    Args:
        df: DataFrame with date, symbol, close columns
        symbol_col: Symbol column name

    Returns:
        Series with TWAP deviation values (float64, percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag close price first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)

    # Calculate TWAP (daily mean of lagged close)
    df_work["_close_lagged"] = close_lagged
    twap = df_work.groupby(["date", symbol_col])["_close_lagged"].transform(
        "mean"
    )

    # Calculate deviation
    deviation = _safe_divide(close_lagged - twap, twap, fill_value=0.0)

    return deviation.astype(np.float64).fillna(0.0)


def compute_close_vwap_ratio(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Close/VWAP Ratio - Ratio of close price to VWAP.

    Formula: Close / VWAP
    PIT: Uses T-1 lagged data.

    Args:
        df: DataFrame with date, symbol, close, volume columns
        symbol_col: Symbol column name

    Returns:
        Series with close/VWAP ratio values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate VWAP
    pv = close_lagged * volume_lagged
    df_work["_pv"] = pv
    df_work["_volume_lagged"] = volume_lagged

    cumsum_pv = df_work.groupby(["date", symbol_col])["_pv"].cumsum()
    cumsum_vol = df_work.groupby(["date", symbol_col])[
        "_volume_lagged"
    ].cumsum()

    # Calculate VWAP with fallback to close price
    vwap = cumsum_pv / cumsum_vol.replace(0, np.nan)
    vwap = vwap.fillna(close_lagged)

    # Calculate ratio
    ratio = _safe_divide(close_lagged, vwap, fill_value=1.0)

    return ratio.astype(np.float64).fillna(1.0)


def compute_volume_weighted_return(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Volume-Weighted Return - Returns weighted by volume intensity.

    Formula: sum(returns * volume_weight) over period
             where volume_weight = volume / sum(volume)
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().apply()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with volume-weighted return values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)[volume_col].shift(1).astype(np.float64)
    )

    # Calculate returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate volume weights using rolling window
    df_work["_returns"] = returns.astype(np.float64)
    df_work["_volume_lagged"] = volume_lagged

    # Calculate rolling sum of volume
    vol_sum = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    # Calculate volume weights
    vol_weights = _safe_divide(volume_lagged, vol_sum, fill_value=0.0)

    # Calculate weighted returns
    weighted_returns = returns * vol_weights

    # Calculate rolling sum of weighted returns
    df_work["_weighted_returns"] = weighted_returns.astype(np.float64)
    vw_return = (
        df_work.groupby(symbol_col)["_weighted_returns"]
        .rolling(window=period, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    return vw_return.astype(np.float64).fillna(0.0)
