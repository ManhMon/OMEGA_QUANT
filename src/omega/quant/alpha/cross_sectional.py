"""
Cross-Sectional Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
"""

import pandas as pd
import numpy as np
from .primitives import _safe_divide


def compute_cross_sectional_zscore(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    Cross-Sectional Z-Score - Standardized return vs universe per date.

    Formula: (stock_return - universe_mean) / universe_std per date
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with cross-sectional z-score values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate cross-sectional mean and std per date
    df_work["_returns"] = returns
    cs_mean = df_work.groupby("date")["_returns"].transform("mean")
    cs_std = df_work.groupby("date")["_returns"].transform("std")

    # Calculate z-score
    zscore = _safe_divide(returns - cs_mean, cs_std, fill_value=0.0)

    return zscore.astype(np.float64).fillna(0.0)


def compute_relative_strength_universe(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Relative Strength Universe - Stock rank vs universe over period.

    Formula: percentile_rank(stock_return) vs all stocks per date
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with relative strength rank values (float64, range: 0 to 1)
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

    # Calculate cross-sectional rank per date
    df_work["_stock_return"] = stock_return
    rank = df_work.groupby("date")["_stock_return"].rank(pct=True)

    return rank.astype(np.float64).fillna(0.5)
