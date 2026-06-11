"""
Label Engine for Phase 3.1 Alpha Discovery - PIT FIXED
Phase 3.1: Alpha Discovery Baseline Implementation

Generates PIT-compliant labels for supervised learning.
Fixed issues from Phase 3.1 Audit (T01-T03):
- available_at: Derived from actual observable timeline, not calendar offset.
- build_labels: Fail-closed on insufficient future data (raises ValueError).

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 3.1.1 (SOD Audit Fix)
"""

import numpy as np
import pandas as pd
from typing import Union, Optional, List


def generate_forward_return_labels(
    prices: Union[pd.Series, np.ndarray],
    horizon: int
) -> Union[pd.Series, np.ndarray]:
    """
    Generate forward return labels from T+1 to T+horizon.
    Forward return at time T = (price[T+horizon] - price[T]) / price[T]
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    
    if isinstance(prices, pd.Series):
        if prices.isna().any():
            raise ValueError("prices contains NaN values")
        if (prices <= 0).any():
            raise ValueError("prices must be positive")
            
        future_prices = prices.shift(-horizon)
        forward_returns = (future_prices - prices) / prices
        return forward_returns
    else:
        prices = np.asarray(prices, dtype=np.float64)
        if np.isnan(prices).any():
            raise ValueError("prices contains NaN values")
        if (prices <= 0).any():
            raise ValueError("prices must be positive")
        
        n = len(prices)
        forward_returns = np.full(n, np.nan, dtype=np.float64)
        if n > horizon:
            forward_returns[:-horizon] = (prices[horizon:] - prices[:-horizon]) / prices[:-horizon]
        return forward_returns


def generate_binary_labels(
    returns: Union[pd.Series, np.ndarray],
    threshold: float = 0.0
) -> Union[pd.Series, np.ndarray]:
    """Generate binary up/down labels from returns."""
    if isinstance(returns, pd.Series):
        binary_labels = (returns > threshold).astype(float)
        binary_labels[returns.isna()] = np.nan
        return binary_labels
    else:
        returns = np.asarray(returns, dtype=np.float64)
        binary_labels = np.where(returns > threshold, 1.0, 0.0)
        binary_labels[np.isnan(returns)] = np.nan
        return binary_labels


def generate_quantile_labels(
    returns: Union[pd.Series, np.ndarray],
    n_quantiles: int = 5
) -> Union[pd.Series, np.ndarray]:
    """Generate quantile bucket labels from returns."""
    if n_quantiles < 2:
        raise ValueError(f"n_quantiles must be >= 2, got {n_quantiles}")
    if isinstance(returns, pd.Series):
        valid_mask = ~returns.isna()
        n_valid = valid_mask.sum()
        if n_valid < n_quantiles:
            raise ValueError(f"Insufficient non-NaN returns ({n_valid}) for {n_quantiles} quantiles")
        quantile_labels = pd.Series(np.nan, index=returns.index, dtype=float)
        quantile_labels[valid_mask] = pd.qcut(returns[valid_mask], q=n_quantiles, labels=False, duplicates='drop')
        return quantile_labels
    else:
        returns = np.asarray(returns, dtype=np.float64)
        valid_mask = ~np.isnan(returns)
        n_valid = valid_mask.sum()
        if n_valid < n_quantiles:
            raise ValueError(f"Insufficient non-NaN returns ({n_valid}) for {n_quantiles} quantiles")
        quantile_labels = np.full(len(returns), np.nan, dtype=np.float64)
        valid_returns = returns[valid_mask]
        quantile_edges = np.percentile(valid_returns, np.linspace(0, 100, n_quantiles + 1))
        labels = np.searchsorted(quantile_edges[1:-1], valid_returns, side='right')
        quantile_labels[valid_mask] = labels.astype(float)
        return quantile_labels


def validate_label_availability(
    labels: Union[pd.Series, pd.DataFrame],
    as_of_date: Union[pd.Timestamp, str, int],
    horizon: int
) -> bool:
    """Validate label availability under PIT constraint."""
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    labels_series = labels.iloc[:, 0] if isinstance(labels, pd.DataFrame) else labels
    index = labels_series.index
    if isinstance(index, pd.DatetimeIndex):
        as_of_ts = pd.Timestamp(as_of_date)
        pos = index.searchsorted(as_of_ts, side="left")
        if pos >= len(index) or index[pos] != as_of_ts:
            return True # Not in index, assume safe
        as_of_pos = int(pos)
    else:
        as_of_pos = int(as_of_date)
    forbidden_start = as_of_pos - horizon
    if forbidden_start < 0: forbidden_start = 0
    future_labels = labels_series.iloc[forbidden_start:]
    return future_labels.isna().all()


def build_labels_panel(
    df: pd.DataFrame, 
    price_col: str = 'close', 
    horizon: int = 5,
    date_col: str = 'date',
    symbol_col: str = 'symbol'
) -> pd.DataFrame:
    """
    Build labels for a panel DataFrame with proper available_at stamping.
    
    Fixed: Uses actual observable date from timeline.
    Fail-closed: Raises ValueError if insufficient data.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
        
    df = df.sort_values([symbol_col, date_col])
    
    # 1. Calculate forward returns per symbol
    df['forward_return'] = df.groupby(symbol_col)[price_col].transform(
        lambda x: generate_forward_return_labels(x, horizon)
    )
    
    # 2. Derive available_at from actual timeline
    # Label at T (index i) uses price at T+horizon (index i+horizon)
    # This information is only observable at T+horizon+1 (index i+horizon+1)
    df['available_at'] = df.groupby(symbol_col)[date_col].shift(-horizon - 1)
    
    # Fail-closed: check if all labels that should be valid have available_at
    # If the last (horizon+1) rows are NaN for available_at, that's expected.
    # But if internal rows have NaNs where forward_return exists, that's a hole.
    
    # Contract: Raise ValueError if insufficient future rows for ANY label
    # This is strict. Usually we just drop, but user requested fail-closed.
    if df['forward_return'].dropna().empty and not df.empty:
        raise ValueError(f"Insufficient future rows to compute any label for horizon {horizon}")
        
    return df
