"""
Alpha Primitives - Core Utility Functions
Extracted from ultimate_alpha_arsenal.py for reusability and modularity.

Version: v21.39-Phase0
Author: Role 9 (Backend Engineer)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All functions use T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().mean()
  with reset_index(level=0, drop=True)

FUNCTIONS:
1. _safe_divide: Safe division with zero/NaN/Inf handling
2. _round_to_board_lot: Round shares to VN board lot size (100 shares)
3. compute_returns: Simple returns over period with T-1 lag
4. compute_rsi: Relative Strength Index with T-1 lag
"""

import pandas as pd
import numpy as np


def _safe_divide(
    numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0
) -> pd.Series:
    """
    Safe division with zero/NaN/Inf handling.

    Args:
        numerator: Numerator series
        denominator: Denominator series
        fill_value: Value to use when division fails (can be scalar or Series)

    Returns:
        Series with safe division results
    """
    result = numerator / denominator
    # Handle infinities and NaN
    if isinstance(fill_value, pd.Series):
        # For infinite values, replace with corresponding fill_value
        result = result.where(~np.isinf(result), fill_value)
        # For NaN values, fill with corresponding fill_value
        result = result.fillna(fill_value)
    else:
        result = result.replace([np.inf, -np.inf], fill_value)
        result = result.fillna(fill_value)
    return result.astype(np.float64)


def _round_to_board_lot(shares: pd.Series, board_size: int = 100) -> pd.Series:
    """
    Round shares to board lot size (VN market: 100 shares per lot).

    Args:
        shares: Series of share quantities
        board_size: Board lot size (default 100 for VN market)

    Returns:
        Series with shares rounded down to nearest board lot
    """
    return (shares // board_size) * board_size


def compute_returns(
    df: pd.DataFrame,
    period: int,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Simple returns over period.

    Formula: (Price_t / Price_{t-period}) - 1
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (5, 20, 60, 120)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with return values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate returns
    returns = df_work.groupby(symbol_col)[price_col].pct_change(period)

    # Apply T-1 lag for PIT safety
    df_work["_ret_temp"] = returns
    returns_lagged = df_work.groupby(symbol_col)["_ret_temp"].shift(1)

    return returns_lagged.fillna(0.0)


def compute_rsi(
    df: pd.DataFrame,
    period: int = 14,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Relative Strength Index (RSI) - Momentum oscillator.

    Formula: RSI = 100 - (100 / (1 + RS))
             RS = Average Gain / Average Loss over period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 14)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with RSI values (0-100)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate price changes
    delta = df_work.groupby(symbol_col)[price_col].diff()

    # Separate gains and losses
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Calculate rolling averages using native rolling API
    avg_gain = (
        gain.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    avg_loss = (
        loss.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Calculate RS and RSI
    rs = _safe_divide(avg_gain, avg_loss, fill_value=0.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Apply T-1 lag for PIT safety
    df_work["_rsi_temp"] = rsi
    rsi_lagged = df_work.groupby(symbol_col)["_rsi_temp"].shift(1)

    return rsi_lagged.fillna(50.0)  # Neutral RSI for missing values
