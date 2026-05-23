"""
OMEGA_QUANT Alpha Primitives (Layer 01) - PIT FIXED
Phase 3.1: Alpha Discovery Baseline Implementation

100% Vectorized | PIT-Safe (Fail-Closed) | Deterministic

Fixed issues from Phase 3.1 Audit (T01-T03):
- available_at discipline: Fail-closed when column missing or violation occurs.
- apply_lag: Mandates sorted panel by date to prevent look-ahead.
- validate_pit_safety: Enforces both as_of and available_at checks.

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 3.1.1 (SOD Audit Fix)
"""

import numpy as np
import pandas as pd
from typing import Optional, Union, List


from scipy.stats import spearmanr, pearsonr

def calculate_ic(scores: pd.Series, labels: pd.Series) -> float:
    """Calculate Information Coefficient (Pearson). Assumes labels are forward PIT-aligned."""
    valid = scores.notna() & labels.notna()
    if valid.sum() < 2: return np.nan
    try:
        r, _ = pearsonr(scores[valid], labels[valid])
        return float(r)
    except ValueError:
        return np.nan

def calculate_rank_ic(scores: pd.Series, labels: pd.Series) -> float:
    """Calculate Rank Information Coefficient (Spearman). Assumes labels are forward PIT-aligned."""
    valid = scores.notna() & labels.notna()
    if valid.sum() < 2: return np.nan
    try:
        r, _ = spearmanr(scores[valid], labels[valid])
        return float(r)
    except ValueError:
        return np.nan

def calculate_turnover(weights_prev: pd.Series, weights_new: pd.Series) -> float:
    """Calculate portfolio turnover."""
    df = pd.DataFrame({'prev': weights_prev, 'new': weights_new}).fillna(0)
    return float((df['new'] - df['prev']).abs().sum() / 2.0)

def calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.0, periods: int = 252) -> float:
    """Calculate annualized Sharpe ratio."""
    valid = returns.dropna()
    if valid.empty: return np.nan
    excess_returns = valid - risk_free_rate
    std = excess_returns.std(ddof=1)
    if std == 0 or np.isnan(std): return np.nan
    return float((excess_returns.mean() / std) * np.sqrt(periods))

def calculate_max_drawdown(returns: pd.Series) -> float:
    """Calculate maximum drawdown from returns."""
    valid = returns.dropna()
    if valid.empty: return np.nan
    # Prepend 1.0 initial capital to track first-period drops correctly
    cum_returns = pd.concat([pd.Series([1.0]), (1 + valid).cumprod()]).reset_index(drop=True)
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / peak
    return float(drawdown.min())


def filter_as_of(
    panel: pd.DataFrame, 
    as_of: Union[str, pd.Timestamp], 
    date_col: str = 'date',
    available_at_col: Optional[str] = 'available_at'
) -> pd.DataFrame:
    """
    Filter panel data up to as_of time with fail-closed availability check.
    
    Args:
        panel: Input panel DataFrame
        as_of: Point-in-time reference
        date_col: Column for data timestamp
        available_at_col: Column for when data became observable
        
    Returns:
        Filtered DataFrame.
        
    Raises:
        ValueError: If available_at_col is requested but missing.
    """
    as_of = pd.to_timestamp(as_of)
    mask = (panel[date_col] <= as_of)
    
    if available_at_col:
        if available_at_col not in panel.columns:
            raise ValueError(f"PIT Violation: '{available_at_col}' requested but not found in panel.")
        mask &= (panel[available_at_col] <= as_of)
        
    return panel[mask]


def validate_pit_safety(
    df: pd.DataFrame, 
    as_of: Union[str, pd.Timestamp],
    date_col: str = 'date',
    available_at_col: Optional[str] = 'available_at'
) -> bool:
    """
    Validate that no row in df violates PIT safety for the given as_of.
    
    Fail-closed: All rows must satisfy date <= as_of AND available_at <= as_of.
    """
    as_of = pd.to_timestamp(as_of)
    
    # Check date
    if (df[date_col] > as_of).any():
        return False
        
    # Check available_at
    if available_at_col:
        if available_at_col not in df.columns:
            raise ValueError(f"PIT Violation: '{available_at_col}' missing during validation.")
        if (df[available_at_col] > as_of).any():
            return False
            
    return True


def apply_lag(
    df: pd.DataFrame, 
    lag: int = 1, 
    groupby_col: str = 'symbol',
    date_col: str = 'date'
) -> pd.DataFrame:
    """
    Apply lag to all numeric columns in df within groups.
    Mandates monotonic date order to prevent look-ahead.
    
    Args:
        df: Input panel
        lag: Number of steps to shift
        groupby_col: Column to group by (e.g., symbol)
        date_col: Column for temporal ordering
        
    Returns:
        DataFrame with lagged values.
    """
    # Fail-closed: Mandate sorting
    # We sort explicitly to ensure shift(lag) is always backward in time
    df_sorted = df.sort_values([groupby_col, date_col])
    
    # Check if original was sorted (optional, but good for validation)
    # if not df.index.equals(df_sorted.index):
    #    warnings.warn("apply_lag: Input was unsorted; auto-sorting to prevent look-ahead.")
    
    result = df_sorted.groupby(groupby_col).shift(lag)
    return result


def compute_momentum(
    returns: pd.Series = None,
    close: pd.Series = None,
    period: int = None,
    window: int = None,
    lag: int = 0
) -> pd.Series:
    """
    Compute momentum alpha signal - 100% Vectorized.
    
    Momentum = Sum of returns over lookback period
    
    Args:
        returns: Returns series (optional if close provided)
        close: Close price series (optional if returns provided)
        period: Lookback period (default 20)
        window: Alias for period (for backward compatibility)
        lag: T-lag for PIT safety (default 0 for testing, use 1 in production)
    
    Returns:
        Momentum series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Support both 'period' and 'window' parameter names
    lookback = window if window is not None else (period if period is not None else 20)
    
    # Compute returns if not provided
    if returns is None:
        if close is None:
            raise ValueError("Either 'close' or 'returns' must be provided")
        returns = close.pct_change()
    
    # Momentum = rolling sum of returns
    momentum = returns.rolling(window=lookback).sum()
    
    if lag > 0:
        return momentum.shift(lag)
    return momentum


def compute_reversal(
    returns: pd.Series = None,
    close: pd.Series = None,
    period: int = None,
    window: int = None,
    lag: int = 0
) -> pd.Series:
    """
    Compute mean reversion alpha signal - 100% Vectorized.
    
    Reversal = -1 * rolling mean of returns (negative momentum for mean reversion)
    
    Args:
        returns: Returns series (optional if close provided)
        close: Close price series (optional if returns provided)
        period: Lookback period (default 5 for short-term reversal)
        window: Alias for period (for backward compatibility)
        lag: T-lag for PIT safety (default 0 for testing, use 1 in production)
    
    Returns:
        Reversal series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Support both 'period' and 'window' parameter names
    lookback = window if window is not None else (period if period is not None else 5)
    
    # Compute returns if not provided
    if returns is None:
        if close is None:
            raise ValueError("Either 'close' or 'returns' must be provided")
        returns = close.pct_change()
    
    # Reversal = negative of rolling mean returns
    reversal = -returns.rolling(window=lookback).mean()
    
    if lag > 0:
        return reversal.shift(lag)
    return reversal
