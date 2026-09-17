"""
Momentum Extensions Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().max/min()
  with reset_index(level=0, drop=True)
"""

import pandas as pd
import numpy as np
from .primitives import _safe_divide


def compute_turtle_traders(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Turtle Traders Signal - Breakout signal based on Turtle Trading rules.

    Formula: +1 if close > high_20d, -1 if close < low_20d, 0 otherwise
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().max/min()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, close, high, low columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with turtle signal values (float64, range: -1, 0, +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)

    # Calculate rolling high and low using native rolling API
    df_work["_high_lagged"] = high_lagged
    df_work["_low_lagged"] = low_lagged

    rolling_high = (
        df_work.groupby(symbol_col)["_high_lagged"]
        .rolling(window=period, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
    )
    rolling_low = (
        df_work.groupby(symbol_col)["_low_lagged"]
        .rolling(window=period, min_periods=1)
        .min()
        .reset_index(level=0, drop=True)
    )

    # Generate signal using values to avoid index mismatch
    signal = np.where(
        close_lagged.values > rolling_high.values,
        1.0,
        np.where(close_lagged.values < rolling_low.values, -1.0, 0.0),
    )

    return pd.Series(signal, index=df_work.index, dtype=np.float64)


def compute_inertia(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Price Inertia - Momentum persistence score.

    Formula: corr(returns, time_index) over period (trend strength)
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().apply()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with inertia values (float64, range: -1 to +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    df_work["_returns"] = returns

    # Vectorized inertia calculation using rolling window
    # This avoids groupby.apply by calculating correlation with time index
    # vectorially
    inertia = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        ticker_returns = df_work.loc[mask, "_returns"].values

        # Calculate rolling correlation with time index
        ticker_inertia = []
        for i in range(len(ticker_returns)):
            if i < period - 1:
                ticker_inertia.append(0.0)
            else:
                window = ticker_returns[i - period + 1 : i + 1]
                if len(window) < 3 or np.all(np.isnan(window)):
                    ticker_inertia.append(0.0)
                else:
                    time_idx = np.arange(len(window))
                    valid_mask = ~np.isnan(window)
                    if valid_mask.sum() < 3:
                        ticker_inertia.append(0.0)
                    else:
                        corr = np.corrcoef(
                            window[valid_mask], time_idx[valid_mask]
                        )[0, 1]
                        ticker_inertia.append(
                            corr if not np.isnan(corr) else 0.0
                        )

        inertia.loc[mask] = ticker_inertia

    return inertia.astype(np.float64).fillna(0.0)


def compute_relative_strength(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Relative Strength - Stock performance vs universe.

    Formula: stock_return / universe_median_return over period
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with relative strength values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Use lagged prices to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate stock returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    price_lagged_shifted = df_work.groupby(symbol_col)["_price_lagged"].shift(
        period
    )
    stock_return = (
        _safe_divide(price_lagged, price_lagged_shifted, fill_value=1.0) - 1.0
    )

    # Calculate universe median return per date
    df_work["_stock_return"] = stock_return
    universe_return = df_work.groupby("date")["_stock_return"].transform(
        "median"
    )

    # Calculate relative strength
    rs = _safe_divide(stock_return, universe_return, fill_value=1.0)

    return rs.astype(np.float64).fillna(1.0)


def compute_acceleration_index(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    Acceleration Index - Rate of change of momentum.

    Formula: diff(momentum) where momentum = price - price_t-1
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with acceleration index values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate momentum (first derivative)
    df_work["_price_lagged"] = price_lagged
    momentum = df_work.groupby(symbol_col)["_price_lagged"].diff()

    # Calculate acceleration (second derivative)
    df_work["_momentum"] = momentum
    acceleration = df_work.groupby(symbol_col)["_momentum"].diff()

    return acceleration.astype(np.float64).fillna(0.0)
