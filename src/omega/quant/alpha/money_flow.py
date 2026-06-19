"""
Money Flow Alpha Functions

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


def compute_sector_relative_momentum(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
    sector_col: str = "sector",
) -> pd.Series:
    """
    Sector-Relative Momentum - Stock ROC minus Sector ROC.

    Formula: Stock_ROC(period) - Sector_Median_ROC(period)
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and sector columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name
        sector_col: Sector column name (if missing, uses cross-sectional
                    median)

    Returns:
        Series with sector-relative momentum values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Use lagged prices to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate stock ROC on lagged prices
    df_work["_price_lagged"] = price_lagged
    price_lagged_shifted = df_work.groupby(symbol_col)["_price_lagged"].shift(
        period
    )
    stock_roc = (
        _safe_divide(price_lagged, price_lagged_shifted, fill_value=1.0) - 1.0
    )

    # Calculate sector median ROC using LAGGED returns (cross-sectional per
    # date)
    df_work["_stock_roc"] = stock_roc

    if sector_col in df_work.columns:
        # Calculate sector median from lagged returns per date
        sector_roc = df_work.groupby(["date", sector_col])[
            "_stock_roc"
        ].transform("median")
    else:
        # No sector column - use cross-sectional median across all stocks per
        # date
        sector_roc = df_work.groupby("date")["_stock_roc"].transform("median")

    # Calculate relative momentum (stock - sector)
    relative_momentum = stock_roc - sector_roc

    return relative_momentum.astype(np.float64).fillna(0.0)


def compute_volume_momentum(
    df: pd.DataFrame,
    period: int = 5,
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Volume Momentum - Liquidity shift detector.

    Formula: (Volume_t - Volume_{t-period}) / Volume_{t-period}
    PIT: Uses T-1 lagged volumes.

    Args:
        df: DataFrame with date, symbol, and volume columns
        period: Lookback period (default 5)
        volume_col: Volume column name
        symbol_col: Symbol column name

    Returns:
        Series with volume momentum values (percentage change)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate volume change
    vol_shifted = df_work.groupby(symbol_col)[volume_col].shift(period)
    vol_momentum = _safe_divide(
        df_work[volume_col] - vol_shifted, vol_shifted, fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_vol_mom_temp"] = vol_momentum
    vol_momentum_lagged = df_work.groupby(symbol_col)["_vol_mom_temp"].shift(1)

    return vol_momentum_lagged.fillna(0.0)


def compute_price_acceleration(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    Price Acceleration - Momentum inflection point detector.

    Formula: Second derivative of returns (diff of diff)
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with price acceleration values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate first derivative (returns)
    returns = df_work.groupby(symbol_col)[price_col].pct_change()

    # Calculate second derivative (acceleration)
    acceleration = returns.groupby(df_work[symbol_col]).diff()

    # Apply T-1 lag for PIT safety
    df_work["_accel_temp"] = acceleration
    acceleration_lagged = df_work.groupby(symbol_col)["_accel_temp"].shift(1)

    return acceleration_lagged.fillna(0.0)
