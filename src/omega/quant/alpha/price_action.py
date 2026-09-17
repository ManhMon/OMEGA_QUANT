"""
Price Action Alpha Functions

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


def compute_candle_range(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Candle Range - Full range of price movement.

    Formula: (High - Low) / Open
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, high, low columns
        symbol_col: Symbol column name

    Returns:
        Series with candle range values (percentage, float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate candle range
    candle_range = _safe_divide(
        df_work["high"] - df_work["low"], df_work["open"], fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_range_temp"] = candle_range
    range_lagged = df_work.groupby(symbol_col)["_range_temp"].shift(1)

    return range_lagged.fillna(0.0).astype(np.float64)


def compute_wick_ratio(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Wick Ratio - Ratio of wicks to body (rejection strength).

    Formula: (Upper_Shadow + Lower_Shadow) / Body_Size
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, high, low, close columns
        symbol_col: Symbol column name

    Returns:
        Series with wick ratio values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate body and shadows
    body_top = df_work[["open", "close"]].max(axis=1)
    body_bottom = df_work[["open", "close"]].min(axis=1)
    body_size = (df_work["close"] - df_work["open"]).abs()

    upper_shadow = df_work["high"] - body_top
    lower_shadow = body_bottom - df_work["low"]

    total_wick = upper_shadow + lower_shadow
    wick_ratio = _safe_divide(total_wick, body_size, fill_value=0.0)

    # Apply T-1 lag for PIT safety
    df_work["_wick_ratio_temp"] = wick_ratio
    wick_ratio_lagged = df_work.groupby(symbol_col)["_wick_ratio_temp"].shift(
        1
    )

    return wick_ratio_lagged.fillna(0.0).astype(np.float64)


def compute_body_size(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Candlestick Body Size - Price action strength.

    Formula: |Close - Open| / Open
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, and close columns
        symbol_col: Symbol column name

    Returns:
        Series with body size values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate body size
    body = _safe_divide(
        (df_work["close"] - df_work["open"]).abs(),
        df_work["open"],
        fill_value=0.0,
    )

    # Apply T-1 lag for PIT safety
    df_work["_body_temp"] = body
    body_lagged = df_work.groupby(symbol_col)["_body_temp"].shift(1)

    return body_lagged.fillna(0.0)


def compute_upper_shadow(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Upper Shadow - Rejection at higher prices.

    Formula: (High - max(Open, Close)) / Open
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, high, and close columns
        symbol_col: Symbol column name

    Returns:
        Series with upper shadow values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate upper shadow
    body_top = df_work[["open", "close"]].max(axis=1)
    shadow = _safe_divide(
        df_work["high"] - body_top, df_work["open"], fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_upper_shadow_temp"] = shadow
    shadow_lagged = df_work.groupby(symbol_col)["_upper_shadow_temp"].shift(1)

    return shadow_lagged.fillna(0.0)


def compute_lower_shadow(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Lower Shadow - Support at lower prices.

    Formula: (min(Open, Close) - Low) / Open
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, low, and close columns
        symbol_col: Symbol column name

    Returns:
        Series with lower shadow values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate lower shadow
    body_bottom = df_work[["open", "close"]].min(axis=1)
    shadow = _safe_divide(
        body_bottom - df_work["low"], df_work["open"], fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_lower_shadow_temp"] = shadow
    shadow_lagged = df_work.groupby(symbol_col)["_lower_shadow_temp"].shift(1)

    return shadow_lagged.fillna(0.0)


def compute_gap_return(
    df: pd.DataFrame, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Gap Return - Overnight price movement.

    Formula: (Open_t - Close_{t-1}) / Close_{t-1}
    PIT: Uses T-1 lagged values.

    Args:
        df: DataFrame with date, symbol, open, and close columns
        symbol_col: Symbol column name

    Returns:
        Series with gap return values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate gap
    close_prev = df_work.groupby(symbol_col)["close"].shift(1)
    gap = _safe_divide(
        df_work["open"] - close_prev, close_prev, fill_value=0.0
    )

    # Apply T-1 lag for PIT safety
    df_work["_gap_temp"] = gap
    gap_lagged = df_work.groupby(symbol_col)["_gap_temp"].shift(1)

    return gap_lagged.fillna(0.0)
