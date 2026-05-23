"""
OMEGA_QUANT Feature Factory - Statistical Features (Layer 01)
Phase 2.2: Feature Engineering - Statistical Features

100% Vectorized | PIT-Safe | Institutional Grade

Implements:
- Rolling Skewness (period=20)
- Rolling Kurtosis (period=20)
- Rolling Z-score (period=20)
- Rolling Correlation (Returns vs Volume, period=20)

Contract:
- Input: OHLCV DataFrame with DatetimeIndex
- Output: Feature DataFrame with same index
- PIT Guard: All features shifted by T-1 lag (available_at = as_of + 1 day)

Author: Backend Engineer (Role 9)
Date: 2026-05-13
Version: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Optional


def compute_rolling_skewness(
    close: pd.Series,
    period: int = 20,
    lag: int = 1
) -> pd.Series:
    """
    Compute Rolling Skewness - 100% Vectorized.
    
    Skewness measures the asymmetry of the return distribution.
    Positive skew = right tail, Negative skew = left tail.
    
    Args:
        close: Close price series
        period: Rolling window period (default 20)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Rolling skewness series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized returns calculation
    returns = close.pct_change()
    
    # Vectorized rolling skewness
    skew = returns.rolling(window=period).skew()
    
    # Handle NaNs from warmup period
    skew = skew.fillna(0.0)
    
    # PIT Guard: Shift by lag periods
    return skew.shift(lag)


def compute_rolling_kurtosis(
    close: pd.Series,
    period: int = 20,
    lag: int = 1
) -> pd.Series:
    """
    Compute Rolling Kurtosis - 100% Vectorized.
    
    Kurtosis measures the "tailedness" of the return distribution.
    High kurtosis = fat tails (extreme events), Low kurtosis = thin tails.
    
    Args:
        close: Close price series
        period: Rolling window period (default 20)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Rolling kurtosis series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized returns calculation
    returns = close.pct_change()
    
    # Vectorized rolling kurtosis
    kurt = returns.rolling(window=period).kurt()
    
    # Handle NaNs from warmup period
    kurt = kurt.fillna(0.0)
    
    # PIT Guard: Shift by lag periods
    return kurt.shift(lag)


def compute_rolling_zscore(
    close: pd.Series,
    period: int = 20,
    lag: int = 1
) -> pd.Series:
    """
    Compute Rolling Z-score - 100% Vectorized.
    
    Z-score = (current_price - rolling_mean) / rolling_std
    Measures how many standard deviations the current price is from the mean.
    
    Args:
        close: Close price series
        period: Rolling window period (default 20)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Rolling z-score series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized rolling mean and std
    rolling_mean = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    
    # Z-score calculation
    zscore = (close - rolling_mean) / rolling_std
    
    # Handle division by zero (when std = 0)
    zscore = zscore.fillna(0.0)
    
    # PIT Guard: Shift by lag periods
    return zscore.shift(lag)


def compute_rolling_correlation(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
    lag: int = 1
) -> pd.Series:
    """
    Compute Rolling Correlation between Returns and Volume - 100% Vectorized.
    
    Correlation measures the linear relationship between price returns and volume.
    High correlation = volume confirms price moves.
    
    Args:
        close: Close price series
        volume: Volume series
        period: Rolling window period (default 20)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        Rolling correlation series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized returns calculation
    returns = close.pct_change()
    
    # Vectorized rolling correlation
    corr = returns.rolling(window=period).corr(volume)
    
    # Handle NaNs from warmup period
    corr = corr.fillna(0.0)
    
    # PIT Guard: Shift by lag periods
    return corr.shift(lag)


def compute_all_statistical_features(
    df: pd.DataFrame,
    skew_period: int = 20,
    kurt_period: int = 20,
    zscore_period: int = 20,
    corr_period: int = 20,
    lag: int = 1
) -> pd.DataFrame:
    """
    Compute all statistical features in one pass - 100% Vectorized.
    
    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
        skew_period: Skewness period (default 20)
        kurt_period: Kurtosis period (default 20)
        zscore_period: Z-score period (default 20)
        corr_period: Correlation period (default 20)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with all statistical feature columns, same index as input
    
    PIT Safety: All features shifted by `lag` periods to enforce T-1 availability.
    
    Raises:
        ValueError: If required columns are missing
    """
    # Validate input
    required_cols = ['close', 'volume']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Extract series
    close = df['close']
    volume = df['volume']
    
    # Compute all statistical features
    result = pd.DataFrame(index=df.index)
    
    # Rolling Skewness
    result['rolling_skew'] = compute_rolling_skewness(
        close, period=skew_period, lag=lag
    )
    
    # Rolling Kurtosis
    result['rolling_kurt'] = compute_rolling_kurtosis(
        close, period=kurt_period, lag=lag
    )
    
    # Rolling Z-score
    result['rolling_zscore'] = compute_rolling_zscore(
        close, period=zscore_period, lag=lag
    )
    
    # Rolling Correlation (Returns vs Volume)
    result['rolling_corr_ret_vol'] = compute_rolling_correlation(
        close, volume, period=corr_period, lag=lag
    )
    
    return result
