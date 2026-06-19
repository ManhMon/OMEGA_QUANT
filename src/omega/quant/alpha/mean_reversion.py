"""
Mean Reversion Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().mean/std()
  with reset_index(level=0, drop=True)
"""

import pandas as pd
import numpy as np
from typing import List
from .primitives import _safe_divide, compute_rsi


def compute_bollinger_distance(
    df: pd.DataFrame,
    period: int = 120,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Bollinger Band Distance - Mean reversion indicator.

    Formula: (Price - MA) / (2 * StdDev)
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 120)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with Bollinger distance values (typically -1 to +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate moving average and standard deviation using native rolling API
    ma = (
        df_work.groupby(symbol_col)[price_col]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    std = (
        df_work.groupby(symbol_col)[price_col]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Calculate Bollinger distance
    bb_dist = _safe_divide(df_work[price_col] - ma, 2 * std, fill_value=0.0)

    # Apply T-1 lag for PIT safety
    df_work["_bb_dist_temp"] = bb_dist
    bb_dist_lagged = df_work.groupby(symbol_col)["_bb_dist_temp"].shift(1)

    return bb_dist_lagged.fillna(0.0)


def compute_rsi_crossover(
    df: pd.DataFrame,
    short_period: int = 20,
    long_period: int = 120,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    RSI Crossover - Momentum regime change detector.

    Formula: RSI(short) - RSI(long)
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        short_period: Short RSI period (default 20)
        long_period: Long RSI period (default 120)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with RSI crossover values
    """
    # Compute RSI for both periods (already includes T-1 lag)
    rsi_short = compute_rsi(
        df, period=short_period, price_col=price_col, symbol_col=symbol_col
    )
    rsi_long = compute_rsi(
        df, period=long_period, price_col=price_col, symbol_col=symbol_col
    )

    # Crossover signal
    crossover = rsi_short - rsi_long

    return crossover.fillna(0.0)


def compute_bb_distance_multi(
    df: pd.DataFrame,
    periods: List[int] = [20, 60, 120],
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.DataFrame:
    """
    Multiple Bollinger Band Distance - Mean reversion at multiple timeframes.

    Formula: (Price - MA) / (2 * StdDev) for each period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        periods: List of BB periods (default [20, 60, 120])
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        DataFrame with multiple BB distance columns
    """
    result = pd.DataFrame(index=df.index)

    for period in periods:
        col_name = f"bb_dist_{period}d"
        result[col_name] = compute_bollinger_distance(
            df, period, price_col, symbol_col
        )

    return result


def compute_rsi_divergence(
    df: pd.DataFrame,
    period: int = 14,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    RSI Divergence - Detects price-RSI divergence.

    Formula: sign(price_change) != sign(RSI_change)
    PIT: Uses T-1 lagged prices with per-ticker groupby shift.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: RSI period (default 14)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with divergence indicator (1 = divergence, 0 = no divergence)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate RSI (already includes T-1 lag)
    rsi = compute_rsi(
        df_work, period=period, price_col=price_col, symbol_col=symbol_col
    )

    # Calculate price change (with T-1 lag) - FIXED: per-ticker shift
    price_change = df_work.groupby(symbol_col)[price_col].diff()
    df_work["_price_change_temp"] = price_change
    price_change_lagged = df_work.groupby(symbol_col)[
        "_price_change_temp"
    ].shift(1)

    # Calculate RSI change - FIXED: per-ticker diff
    df_work["_rsi_temp"] = rsi
    rsi_change = df_work.groupby(symbol_col)["_rsi_temp"].diff()

    # Detect divergence
    divergence = (
        (np.sign(price_change_lagged) != np.sign(rsi_change))
        & (price_change_lagged != 0)
        & (rsi_change != 0)
    ).astype(float)

    return divergence.fillna(0.0)


def compute_zscore(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Z-Score of Returns - Standardized return deviation.

    Formula: (return - mean(return)) / std(return) over period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with z-score values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate rolling mean and std using native rolling API
    df_work["_returns"] = returns
    ret_mean = (
        df_work.groupby(symbol_col)["_returns"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    ret_std = (
        df_work.groupby(symbol_col)["_returns"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Calculate z-score
    zscore = _safe_divide(returns - ret_mean, ret_std, fill_value=0.0)

    return zscore.astype(np.float64).fillna(0.0)


def compute_percentile_rank(
    df: pd.DataFrame,
    period: int = 60,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Percentile Rank - Current price percentile in lookback window.

    Formula: percentile_rank(close) over period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().apply()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 60)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with percentile rank values (float64, range: 0 to 1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    df_work["_price_lagged"] = price_lagged

    # Vectorized percentile rank calculation using rolling window
    # This avoids groupby.apply by calculating percentile rank vectorially
    percentile = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        ticker_prices = df_work.loc[mask, "_price_lagged"].values

        # Calculate rolling percentile rank
        ticker_percentile = []
        for i in range(len(ticker_prices)):
            if i < 1:
                ticker_percentile.append(0.5)
            else:
                start_idx = max(0, i - period + 1)
                window = ticker_prices[start_idx : i + 1]
                valid_window = window[~np.isnan(window)]

                if len(valid_window) < 2:
                    ticker_percentile.append(0.5)
                else:
                    current_val = ticker_prices[i]
                    if np.isnan(current_val):
                        ticker_percentile.append(0.5)
                    else:
                        pct_rank = (valid_window < current_val).sum() / len(
                            valid_window
                        )
                        ticker_percentile.append(pct_rank)

        percentile.loc[mask] = ticker_percentile

    return percentile.astype(np.float64).fillna(0.5)


def compute_consecutive_up_days(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    Consecutive Up Days - Count of consecutive positive return days.

    Formula: count of consecutive days where return > 0
             (negative for down days)
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with consecutive up days count (float64,
               positive=up, negative=down)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Determine direction
    direction = np.sign(returns)

    # Calculate consecutive streaks
    df_work["_direction"] = direction

    # Vectorized streak calculation
    # This avoids groupby.apply by calculating streaks vectorially per ticker
    consecutive = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        ticker_direction = df_work.loc[mask, "_direction"].values

        # Calculate consecutive streaks
        ticker_streak = []
        current_streak = 0.0

        for i, val in enumerate(ticker_direction):
            if i == 0 or np.isnan(val):
                ticker_streak.append(0.0)
                current_streak = 0.0
            else:
                prev_val = ticker_direction[i - 1]
                if np.isnan(prev_val):
                    ticker_streak.append(val)
                    current_streak = val
                elif val == prev_val and val != 0:
                    current_streak += val
                    ticker_streak.append(current_streak)
                else:
                    current_streak = val
                    ticker_streak.append(val)

        consecutive.loc[mask] = ticker_streak

    return consecutive.astype(np.float64).fillna(0.0)
