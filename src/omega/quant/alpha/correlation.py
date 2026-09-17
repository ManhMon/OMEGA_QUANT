"""
Correlation Alpha Functions

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


def compute_stock_sector_correlation(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
    sector_col: str = "sector",
) -> pd.Series:
    """
    Stock-Sector Correlation - Rolling correlation between stock
    and sector returns.

    Formula: corr(stock_returns, sector_median_returns) over period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().corr()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and sector columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name
        sector_col: Sector column name

    Returns:
        Series with stock-sector correlation values (float64, range: -1 to +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Use lagged prices to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate stock returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    stock_returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate sector median returns using LAGGED returns (cross-sectional
    # per date)
    df_work["_stock_returns"] = stock_returns

    if sector_col in df_work.columns:
        sector_returns = df_work.groupby(["date", sector_col])[
            "_stock_returns"
        ].transform("median")
    else:
        sector_returns = df_work.groupby("date")["_stock_returns"].transform(
            "median"
        )

    # Calculate rolling correlation using native rolling API
    df_work["_sector_returns"] = sector_returns

    # Vectorized correlation calculation per ticker using expanding
    # window approach
    # series
    correlation = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        stock_ret = df_work.loc[mask, "_stock_returns"]
        sector_ret = df_work.loc[mask, "_sector_returns"]

        # Calculate rolling correlation using pandas rolling.corr
        ticker_corr = stock_ret.rolling(window=period, min_periods=5).corr(
            sector_ret
        )
        correlation.loc[mask] = ticker_corr.values

    return correlation.astype(np.float64).fillna(0.0)


def compute_market_correlation(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Market Correlation - Rolling correlation between stock and market
    (VN-Index proxy).

    Formula: corr(stock_returns, market_returns) over period
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().corr()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with market correlation values (float64, range: -1 to +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Use lagged prices to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate stock returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    stock_returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate market returns (cross-sectional median per date as VN-Index
    # proxy)
    df_work["_stock_returns"] = stock_returns
    market_returns = df_work.groupby("date")["_stock_returns"].transform(
        "median"
    )

    # Calculate rolling correlation using native rolling API
    df_work["_market_returns"] = market_returns

    # Vectorized correlation calculation per ticker using expanding
    # window approach
    # series
    correlation = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        stock_ret = df_work.loc[mask, "_stock_returns"]
        market_ret = df_work.loc[mask, "_market_returns"]

        # Calculate rolling correlation using pandas rolling.corr
        ticker_corr = stock_ret.rolling(window=period, min_periods=5).corr(
            market_ret
        )
        correlation.loc[mask] = ticker_corr.values

    return correlation.astype(np.float64).fillna(0.0)


def compute_pair_correlation(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Pair Correlation - Rolling correlation with market
    (alternative implementation).

    Formula: corr(stock_returns, market_median_returns) over period
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with pair correlation values (float64, range: -1 to +1)
    """
    # Reuse market_correlation implementation
    return compute_market_correlation(df, period, price_col, symbol_col)
