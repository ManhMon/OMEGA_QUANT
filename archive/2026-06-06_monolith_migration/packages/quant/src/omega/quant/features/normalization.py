"""
OMEGA_QUANT Feature Factory - Signal Normalization (Layer 01)
Phase 3.2.5: Feature Engineering - Signal Normalization

100% Vectorized | PIT-Safe | Institutional Grade

Implements:
- zscore_normalize: StandardScaler (mean=0, std=1)
- rank_normalize: Uniform distribution [-1, 1]
- robust_normalize: Outlier-resistant scaling (Median/IQR)
- percentile_rank: Normalized ranks [0, 1]
- rolling_normalize: PIT-safe rolling window standardization
- expanding_normalize: PIT-safe expanding window standardization

PIT Safety:
- Cross-sectional normalization: Applied per-date, no temporal leakage.
- Time-series normalization: Uses rolling/expanding windows to ensure no look-ahead.

Author: Data Scientist (Role 14)
Date: 2026-05-13
Version: 2.0.0 (V21 Math Utils Port)
"""

import pandas as pd
import numpy as np
from typing import Optional, Union, Tuple, List


def zscore_normalize(series: pd.Series, epsilon: float = 1e-9) -> pd.Series:
    """
    Standard Z-score normalization (mean=0, std=1) - Vectorized.
    
    Args:
        series: Input series
        epsilon: Small constant to avoid division by zero
        
    Returns:
        Z-scored series. Returns zeros if std is too small.
    """
    if series.isna().all():
        return series.copy()
    
    mean = series.mean()
    std = series.std()
    
    if pd.isna(mean) or pd.isna(std) or std < epsilon:
        return pd.Series(0.0, index=series.index)
    
    return (series - mean) / (std + epsilon)


def rank_normalize(series: pd.Series) -> pd.Series:
    """
    Rank-based normalization to uniform distribution [-1, 1] - Vectorized.
    
    Args:
        series: Input series
        
    Returns:
        Ranked series scaled to [-1, 1].
    """
    # Get percentile ranks (0 to 1)
    ranks = series.rank(pct=True)
    
    # Scale to [-1, 1]
    return 2 * ranks - 1


def percentile_rank(series: pd.Series) -> pd.Series:
    """
    Compute percentile rank [0, 1] - Vectorized.
    
    Args:
        series: Input series
        
    Returns:
        Series with percentile ranks [0, 1].
    """
    return series.rank(pct=True)


def robust_normalize(series: pd.Series, epsilon: float = 1e-9) -> pd.Series:
    """
    Robust normalization using Median and IQR - Vectorized.
    
    Robust to outliers. Result is centered at 0 with IQR=1.
    
    Args:
        series: Input series
        epsilon: Small constant to avoid division by zero
        
    Returns:
        Robustly scaled series.
    """
    median = series.median()
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    
    if pd.isna(median) or pd.isna(iqr) or iqr < epsilon:
        return pd.Series(0.0, index=series.index)
    
    return (series - median) / (iqr + epsilon)


def rolling_normalize(
    series: pd.Series, 
    window: int, 
    min_periods: Optional[int] = None,
    epsilon: float = 1e-9
) -> pd.Series:
    """
    PIT-safe rolling window Z-score normalization - Vectorized.
    
    Uses only past data within window to normalize the current point.
    
    Args:
        series: Input time-series
        window: Rolling window size
        min_periods: Minimum observations (default: window)
        epsilon: Constant for numerical stability
        
    Returns:
        Rolling Z-scored series.
    """
    if min_periods is None:
        min_periods = window
        
    rolling_mean = series.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = series.rolling(window=window, min_periods=min_periods).std()
    
    result = (series - rolling_mean) / (rolling_std + epsilon)
    return result.fillna(0.0)


def expanding_normalize(
    series: pd.Series, 
    min_periods: int = 20,
    epsilon: float = 1e-9
) -> pd.Series:
    """
    PIT-safe expanding window Z-score normalization - Vectorized.
    
    Uses all available historical data up to the current point.
    
    Args:
        series: Input time-series
        min_periods: Minimum observations (default: 20)
        epsilon: Constant for numerical stability
        
    Returns:
        Expanding Z-scored series.
    """
    expanding_mean = series.expanding(min_periods=min_periods).mean()
    expanding_std = series.expanding(min_periods=min_periods).std()
    
    result = (series - expanding_mean) / (expanding_std + epsilon)
    return result.fillna(0.0)


class Normalizer:
    """
    Unified Normalization Engine for OMEGA_QUANT.
    
    Provides a consistent interface for different normalization methods.
    Supports single series and panel data.
    """
    
    def __init__(self, method: str = 'zscore', **kwargs):
        """
        Initialize Normalizer.
        
        Args:
            method: 'zscore', 'rank', 'robust', 'rolling', 'expanding'
            **kwargs: Extra arguments for specific methods (e.g., window)
        """
        self.method = method
        self.kwargs = kwargs
        
    def normalize(self, data: Union[pd.Series, pd.DataFrame]) -> Union[pd.Series, pd.DataFrame]:
        """
        Apply normalization based on the selected method.
        
        Args:
            data: Series or DataFrame (Panel data with MultiIndex [date, symbol])
            
        Returns:
            Normalized data.
        """
        if isinstance(data, pd.DataFrame):
            return data.apply(self._normalize_series)
        return self._normalize_series(data)
    
    def _normalize_series(self, series: pd.Series) -> pd.Series:
        """Internal worker for series normalization."""
        if self.method == 'zscore':
            return zscore_normalize(series)
        elif self.method == 'rank':
            return rank_normalize(series)
        elif self.method == 'robust':
            return robust_normalize(series)
        elif self.method == 'rolling':
            window = self.kwargs.get('window', 20)
            return rolling_normalize(series, window=window)
        elif self.method == 'expanding':
            min_periods = self.kwargs.get('min_periods', 20)
            return expanding_normalize(series, min_periods=min_periods)
        else:
            raise ValueError(f"Unknown normalization method: {self.method}")


def normalize_panel(
    df: pd.DataFrame,
    columns: Union[str, List[str]],
    method: str = 'zscore',
    by_date: bool = True,
    **kwargs
) -> pd.DataFrame:
    """
    Normalize panel data (MultiIndex [date, symbol]).
    
    Args:
        df: Input panel DataFrame
        columns: Column(s) to normalize
        method: Normalization method
        by_date: If True, normalize cross-sectionally per date
        **kwargs: Arguments for normalizer
        
    Returns:
        DataFrame with normalized columns.
    """
    if isinstance(columns, str):
        columns = [columns]
        
    result = df.copy()
    normalizer = Normalizer(method=method, **kwargs)
    
    for col in columns:
        if by_date:
            # Cross-sectional normalization
            result[f"{col}_norm"] = df.groupby(level='date')[col].transform(
                lambda x: normalizer.normalize(x)
            )
        else:
            # Time-series normalization (per symbol)
            result[f"{col}_norm"] = df.groupby(level='symbol')[col].transform(
                lambda x: normalizer.normalize(x)
            )
            
    return result
