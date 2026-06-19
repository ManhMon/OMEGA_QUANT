"""
Momentum Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
"""

import pandas as pd
from .primitives import _safe_divide, compute_returns


def compute_roc(
    df: pd.DataFrame,
    period: int,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Rate of Change (ROC) - Momentum indicator.

    Formula: (Price_t / Price_{t-period} - 1) * 100
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (5 or 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with ROC values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Compute ROC on current prices, then lag the result
    price_shifted = df_work.groupby(symbol_col)[price_col].shift(period)
    roc = _safe_divide(df_work[price_col], price_shifted, fill_value=0.0) - 1.0
    roc = roc * 100.0

    # Apply T-1 lag for PIT safety
    df_work["_roc_temp"] = roc
    roc_lagged = df_work.groupby(symbol_col)["_roc_temp"].shift(1)

    return roc_lagged.fillna(0.0)


def compute_momentum_acceleration(
    df: pd.DataFrame,
    short_period: int = 20,
    long_period: int = 60,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Momentum Acceleration - Difference between short and long momentum.

    Formula: Return(short) - Return(long)
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        short_period: Short lookback period (default 20)
        long_period: Long lookback period (default 60)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with momentum acceleration values
    """
    ret_short = compute_returns(df, short_period, price_col, symbol_col)
    ret_long = compute_returns(df, long_period, price_col, symbol_col)

    return ret_short - ret_long
