"""
Liquidity Alpha Functions

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


def compute_volume_ma_ratio(
    df: pd.DataFrame,
    short_period: int = 5,
    long_period: int = 20,
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Volume Moving Average Ratio - Liquidity indicator.

    Formula: MA(Volume, short) / MA(Volume, long)
    PIT: Uses T-1 lagged volumes.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and volume columns
        short_period: Short MA period (default 5)
        long_period: Long MA period (default 20)
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with volume MA ratio values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate short and long moving averages using native rolling API
    vol_ma_short = (
        df_work.groupby(symbol_col)[volume_col]
        .rolling(window=short_period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_ma_long = (
        df_work.groupby(symbol_col)[volume_col]
        .rolling(window=long_period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Calculate ratio
    ratio = _safe_divide(vol_ma_short, vol_ma_long, fill_value=1.0)

    # Apply T-1 lag for PIT safety
    df_work["_ratio_temp"] = ratio
    ratio_lagged = df_work.groupby(symbol_col)["_ratio_temp"].shift(1)

    return ratio_lagged.fillna(1.0)


def compute_illiquidity_amihud(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Amihud Illiquidity Measure - Price impact per unit volume.

    Formula: Average(|Return| / Volume) over period
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with illiquidity values (scaled by 1e6)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate absolute returns
    returns = df_work.groupby(symbol_col)[price_col].pct_change().abs()

    # Calculate price impact (return / volume)
    price_impact = _safe_divide(returns, df_work[volume_col], fill_value=0.0)

    # Calculate rolling average using native rolling API
    illiquidity = (
        price_impact.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Scale by 1e6 for readability
    illiquidity = illiquidity * 1e6

    # Apply T-1 lag for PIT safety
    df_work["_illiq_temp"] = illiquidity
    illiquidity_lagged = df_work.groupby(symbol_col)["_illiq_temp"].shift(1)

    return illiquidity_lagged.fillna(0.0)


def compute_adv(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Average Daily Value (ADV) - Liquidity measure in VND terms.

    Formula: Average(Volume * Price) over period
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with ADV values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate daily value
    daily_value = df_work[volume_col] * df_work[price_col]

    # Calculate rolling average using native rolling API
    df_work["_daily_value"] = daily_value
    adv = (
        df_work.groupby(symbol_col)["_daily_value"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Apply T-1 lag for PIT safety
    df_work["_adv_temp"] = adv
    adv_lagged = df_work.groupby(symbol_col)["_adv_temp"].shift(1)

    return adv_lagged.fillna(0.0)


def compute_zero_trade_frequency(
    df: pd.DataFrame,
    period: int = 20,
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Zero Trade Frequency - Proportion of zero-volume days.

    Formula: Count(Volume == 0) / period
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and volume columns
        period: Lookback period (default 20)
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with zero trade frequency values (0 to 1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Identify zero-volume days
    zero_days = (df_work[volume_col] == 0).astype(int)

    # Calculate rolling mean using native rolling API
    df_work["_zero_days"] = zero_days
    zero_freq = (
        df_work.groupby(symbol_col)["_zero_days"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Apply T-1 lag for PIT safety
    df_work["_zero_freq_temp"] = zero_freq
    zero_freq_lagged = df_work.groupby(symbol_col)["_zero_freq_temp"].shift(1)

    return zero_freq_lagged.fillna(0.0)


def compute_obv_change(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    On-Balance Volume (OBV) Change - Money flow indicator.

    Formula: Cumsum(sign(price_change) * volume), then pct_change over period
    PIT: Uses T-1 lagged data.

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with OBV change values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate price direction
    price_change = df_work.groupby(symbol_col)[price_col].diff()
    direction = np.sign(price_change).fillna(0)

    # Calculate OBV
    obv_flow = direction * df_work[volume_col]
    obv = obv_flow.groupby(df_work[symbol_col]).cumsum()

    # Calculate OBV change over period
    obv_change = obv.groupby(df_work[symbol_col]).pct_change(periods=period)

    # Apply T-1 lag for PIT safety
    df_work["_obv_change_temp"] = obv_change
    obv_change_lagged = df_work.groupby(symbol_col)["_obv_change_temp"].shift(
        1
    )

    return obv_change_lagged.fillna(0.0)


def compute_liquidity_quality_score(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Liquidity Quality Score - Combines volume consistency and price stability.

    Formula: (volume_cv) * (price_cv)
             where cv = coefficient of variation = std / mean
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().std/mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with liquidity quality scores (lower is better)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate volume CV using native rolling API
    vol_mean = (
        df_work.groupby(symbol_col)[volume_col]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)[volume_col]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    vol_cv = _safe_divide(vol_std, vol_mean, fill_value=0.0)

    # Calculate price CV using native rolling API
    price_mean = (
        df_work.groupby(symbol_col)[price_col]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    price_std = (
        df_work.groupby(symbol_col)[price_col]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    price_cv = _safe_divide(price_std, price_mean, fill_value=0.0)

    # Combine
    quality_score = vol_cv * price_cv

    # Apply T-1 lag for PIT safety
    df_work["_quality_temp"] = quality_score
    quality_lagged = df_work.groupby(symbol_col)["_quality_temp"].shift(1)

    return quality_lagged.fillna(0.0)


def alpha_liquidity_quality_score(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    RESCUE P3 WEEK 1 - Alpha 3/3: Liquidity Quality Score

    Formula: (volume_std / volume_mean) * (close_std / close_mean)
    Logic: Combines volume consistency and price stability
           (lower = better quality)
    PIT: Uses T-1 lagged data
    Vectorization: 100% Pandas/NumPy operations
    Native Rolling API: Uses .groupby().rolling().std/mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period for rolling statistics (default 20)
        price_col: Price column name (default 'close')
        volume_col: Volume column name (default 'volume')
        symbol_col: Symbol column name (default 'ticker')

    Returns:
        Series with liquidity quality scores (float64, lower = better quality)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)[volume_col].shift(1).astype(np.float64)
    )

    # Calculate volume CV (coefficient of variation) using native rolling API
    df_work["_volume_lagged"] = volume_lagged
    vol_mean = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    vol_cv = _safe_divide(vol_std, vol_mean, fill_value=0.0)

    # Calculate price CV (coefficient of variation) using native rolling API
    df_work["_price_lagged"] = price_lagged
    price_mean = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    price_std = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    price_cv = _safe_divide(price_std, price_mean, fill_value=0.0)

    # Combine volume CV and price CV (already PIT-safe via lagged inputs)
    liquidity_quality = vol_cv * price_cv

    return liquidity_quality.astype(np.float64).fillna(0.0)
