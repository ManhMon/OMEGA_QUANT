"""
OMEGA_QUANT Feature Factory - Cross-Sectional Features (Layer 01)
Phase 2.3: Feature Engineering - Cross-Sectional Features

100% Vectorized | PIT-Safe | Institutional Grade

Implements:
- Cross-sectional Rank (by date)
- Sector-Neutralized Returns (Value - Sector Mean)
- Cross-sectional Z-score (by date)

Contract:
- Input: Multi-index DataFrame (date, symbol) or flat DataFrame with date/symbol/sector columns
- Output: Feature DataFrame with same index
- PIT Guard: All features shifted by T-1 lag (available_at = as_of + 1 day)

Author: Backend Engineer (Role 9)
Date: 2026-05-13
Version: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Optional, Union


def compute_rank(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = None,
    symbol_col: str = 'symbol',
    groupby: str = None,
    lag: int = 1
) -> Union[pd.Series, pd.DataFrame]:
    """
    Compute Cross-sectional Rank by date - 100% Vectorized.
    Alias for compute_cross_sectional_rank with flexible parameter names.
    
    Args:
        df: DataFrame with date, symbol, and value columns
        value_col: Column name to rank (default 'returns')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol')
        groupby: Alias for date_col (for backward compatibility)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with added rank column or Series with ranks
    """
    # Support both 'date_col' and 'groupby' parameter names
    date_column = groupby if groupby is not None else (date_col if date_col is not None else 'date')
    
    # Check if this is a simple ranking (returns DataFrame with rank column)
    if groupby is not None:
        # Legacy mode: return DataFrame with rank column added
        result_df = df.copy()
        ranks = df.groupby(date_column)[value_col].rank(method='dense', ascending=True)
        result_df[f'{value_col}_rank'] = ranks
        return result_df
    else:
        # New mode: return Series
        return compute_cross_sectional_rank(df, value_col, date_column, symbol_col, lag)


def compute_zscore(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = None,
    symbol_col: str = 'symbol',
    groupby: str = None,
    lag: int = 1
) -> Union[pd.Series, pd.DataFrame]:
    """
    Compute Cross-sectional Z-score by date - 100% Vectorized.
    Alias for compute_cross_sectional_zscore with flexible parameter names.
    
    Args:
        df: DataFrame with date, symbol, and value columns
        value_col: Column name to normalize (default 'returns')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol')
        groupby: Alias for date_col (for backward compatibility)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with added zscore column or Series with zscores
    """
    # Support both 'date_col' and 'groupby' parameter names
    date_column = groupby if groupby is not None else (date_col if date_col is not None else 'date')
    
    # Check if this is a simple zscore (returns DataFrame with zscore column)
    if groupby is not None:
        # Legacy mode: return DataFrame with zscore column added
        result_df = df.copy()
        
        def zscore_group(group):
            mean = group.mean()
            std = group.std()
            if std == 0 or pd.isna(std):
                return pd.Series(0.0, index=group.index)
            return (group - mean) / std
        
        zscores = df.groupby(date_column)[value_col].transform(zscore_group)
        result_df[f'{value_col}_zscore'] = zscores
        return result_df
    else:
        # New mode: return Series
        return compute_cross_sectional_zscore(df, value_col, date_column, symbol_col, lag)


def compute_cross_sectional_rank(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = 'date',
    symbol_col: str = 'symbol',
    lag: int = 1
) -> pd.Series:
    """
    Compute Cross-sectional Rank by date - 100% Vectorized.
    
    Ranks values within each date cross-section using percentile ranking.
    Rank = 0.0 (lowest) to 1.0 (highest) within each date.
    
    Args:
        df: DataFrame with date, symbol, and value columns
        value_col: Column name to rank (default 'returns')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol')
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Series with cross-sectional ranks (0.0 to 1.0), shifted by lag periods per symbol
    
    PIT Safety: Output is shifted by `lag` periods within each symbol's time series
                to enforce T-1 availability and prevent cross-symbol leakage.
    
    Note: Uses pct=True for percentile ranking (0.0 = min, 1.0 = max).
          Handles ties using average ranking.
    """
    # Vectorized groupby rank operation
    # pct=True returns percentile ranks (0.0 to 1.0)
    ranks = df.groupby(date_col)[value_col].rank(pct=True, method='average')
    
    # Handle NaN values (preserve them)
    ranks = ranks.fillna(0.5)  # Neutral rank for missing values
    
    # PIT Guard: Shift by lag periods WITHIN EACH SYMBOL to prevent cross-symbol leakage
    # Sort by (date, symbol) to ensure stable order, then shift within symbol groups
    df_temp = df[[date_col, symbol_col]].copy()
    df_temp['ranks'] = ranks
    df_temp = df_temp.sort_values([date_col, symbol_col])
    df_temp['ranks_lagged'] = df_temp.groupby(symbol_col)['ranks'].shift(lag)
    
    # Restore original order
    return df_temp['ranks_lagged'].reindex(df.index)


def compute_sector_neutralized(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = 'date',
    sector_col: str = 'sector',
    symbol_col: str = 'symbol',
    lag: int = 1
) -> pd.Series:
    """
    Compute Sector-Neutralized Values - 100% Vectorized.
    
    Neutralized Value = Value - Sector Mean (within each date)
    Removes sector-specific effects from the value.
    
    Args:
        df: DataFrame with date, symbol, sector, and value columns
        value_col: Column name to neutralize (default 'returns')
        date_col: Date column name (default 'date')
        sector_col: Sector column name (default 'sector')
        symbol_col: Symbol column name (default 'symbol')
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Series with sector-neutralized values, shifted by lag periods per symbol
    
    PIT Safety: Output is shifted by `lag` periods within each symbol's time series
                to enforce T-1 availability and prevent cross-symbol leakage.
    
    Note: If sector is missing/NaN, the value is preserved as-is.
    """
    # Vectorized groupby transform to compute sector means
    sector_means = df.groupby([date_col, sector_col])[value_col].transform('mean')
    
    # Subtract sector mean from value
    neutralized = df[value_col] - sector_means
    
    # Handle missing sectors (preserve original value)
    neutralized = neutralized.fillna(df[value_col])
    
    # PIT Guard: Shift by lag periods WITHIN EACH SYMBOL to prevent cross-symbol leakage
    # Sort by (date, symbol) to ensure stable order, then shift within symbol groups
    df_temp = df[[date_col, symbol_col]].copy()
    df_temp['neutralized'] = neutralized
    df_temp = df_temp.sort_values([date_col, symbol_col])
    df_temp['neutralized_lagged'] = df_temp.groupby(symbol_col)['neutralized'].shift(lag)
    
    # Restore original order
    return df_temp['neutralized_lagged'].reindex(df.index)


def compute_cross_sectional_zscore(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = 'date',
    symbol_col: str = 'symbol',
    lag: int = 1
) -> pd.Series:
    """
    Compute Cross-sectional Z-score by date - 100% Vectorized.
    
    Z-score = (Value - Cross-sectional Mean) / Cross-sectional Std
    Standardizes values within each date cross-section.
    
    Args:
        df: DataFrame with date, symbol, and value columns
        value_col: Column name to standardize (default 'returns')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol')
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Series with cross-sectional z-scores, shifted by lag periods per symbol
    
    PIT Safety: Output is shifted by `lag` periods within each symbol's time series
                to enforce T-1 availability and prevent cross-symbol leakage.
    
    Note: If cross-sectional std = 0 (all values identical), z-score = 0.
    """
    # Vectorized groupby transform for mean and std
    cs_mean = df.groupby(date_col)[value_col].transform('mean')
    cs_std = df.groupby(date_col)[value_col].transform('std')
    
    # Z-score calculation
    zscore = (df[value_col] - cs_mean) / cs_std
    
    # Handle division by zero (when std = 0)
    zscore = zscore.fillna(0.0)
    
    # Handle infinite values (edge case)
    zscore = zscore.replace([np.inf, -np.inf], 0.0)
    
    # PIT Guard: Shift by lag periods WITHIN EACH SYMBOL to prevent cross-symbol leakage
    # Sort by (date, symbol) to ensure stable order, then shift within symbol groups
    df_temp = df[[date_col, symbol_col]].copy()
    df_temp['zscore'] = zscore
    df_temp = df_temp.sort_values([date_col, symbol_col])
    df_temp['zscore_lagged'] = df_temp.groupby(symbol_col)['zscore'].shift(lag)
    
    # Restore original order
    return df_temp['zscore_lagged'].reindex(df.index)


def compute_all_cross_sectional_features(
    df: pd.DataFrame,
    value_col: str = 'returns',
    date_col: str = 'date',
    symbol_col: str = 'symbol',
    sector_col: Optional[str] = 'sector',
    lag: int = 1
) -> pd.DataFrame:
    """
    Compute all cross-sectional features in one pass - 100% Vectorized.
    
    Args:
        df: DataFrame with date, symbol, value, and optionally sector columns
            Can be multi-index (date, symbol) or flat with date/symbol columns
        value_col: Column name to compute features on (default 'returns')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol')
        sector_col: Sector column name (default 'sector', None to skip sector features)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with all cross-sectional feature columns, same index as input
    
    PIT Safety: All features shifted by `lag` periods within each symbol's time series
                to enforce T-1 availability and prevent cross-symbol leakage.
    
    Raises:
        ValueError: If required columns are missing
    """
    # Handle multi-index input (date, symbol)
    if isinstance(df.index, pd.MultiIndex):
        # Reset index to work with flat DataFrame
        df_work = df.reset_index()
        if 'date' not in df_work.columns and 'level_0' in df_work.columns:
            df_work = df_work.rename(columns={'level_0': 'date'})
        if 'symbol' not in df_work.columns and 'level_1' in df_work.columns:
            df_work = df_work.rename(columns={'level_1': 'symbol'})
        original_index = df.index
    else:
        df_work = df.copy()
        original_index = df.index
    
    # Validate input
    required_cols = [date_col, symbol_col, value_col]
    missing = [col for col in required_cols if col not in df_work.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Initialize result DataFrame
    result = pd.DataFrame(index=original_index)
    
    # Cross-sectional Rank
    # Use .values to avoid index alignment issues between df_work (RangeIndex) and result (MultiIndex)
    rank_series = compute_cross_sectional_rank(
        df_work, value_col=value_col, date_col=date_col, 
        symbol_col=symbol_col, lag=lag
    )
    result['cs_rank'] = rank_series.values
    
    # Cross-sectional Z-score
    zscore_series = compute_cross_sectional_zscore(
        df_work, value_col=value_col, date_col=date_col, 
        symbol_col=symbol_col, lag=lag
    )
    result['cs_zscore'] = zscore_series.values
    
    # Sector-Neutralized (if sector column exists)
    if sector_col and sector_col in df_work.columns:
        neutral_series = compute_sector_neutralized(
            df_work, value_col=value_col, date_col=date_col, 
            sector_col=sector_col, symbol_col=symbol_col, lag=lag
        )
        result['sector_neutral'] = neutral_series.values
    
    return result


def prepare_cross_sectional_input(
    df: pd.DataFrame,
    price_col: str = 'close',
    date_col: str = 'date',
    symbol_col: Optional[str] = 'symbol'
) -> pd.DataFrame:
    """
    Prepare input DataFrame for cross-sectional feature computation.
    
    Converts OHLCV data to returns and ensures proper structure.
    
    Args:
        df: OHLCV DataFrame (can be multi-index or flat)
        price_col: Price column to compute returns from (default 'close')
        date_col: Date column name (default 'date')
        symbol_col: Symbol column name (default 'symbol', None if multi-index)
    
    Returns:
        DataFrame with 'returns' column ready for cross-sectional features
    
    Note: Returns are computed as pct_change() within each symbol.
    """
    # Handle multi-index input
    if isinstance(df.index, pd.MultiIndex):
        df_work = df.reset_index()
        if 'date' not in df_work.columns and 'level_0' in df_work.columns:
            df_work = df_work.rename(columns={'level_0': 'date'})
        if 'symbol' not in df_work.columns and 'level_1' in df_work.columns:
            df_work = df_work.rename(columns={'level_1': 'symbol'})
        symbol_col = 'symbol'
    else:
        df_work = df.copy()
    
    # Compute returns within each symbol
    if symbol_col and symbol_col in df_work.columns:
        df_work['returns'] = df_work.groupby(symbol_col)[price_col].pct_change()
    else:
        df_work['returns'] = df_work[price_col].pct_change()
    
    # Fill NaN returns with 0.0
    df_work['returns'] = df_work['returns'].fillna(0.0)
    
    return df_work
