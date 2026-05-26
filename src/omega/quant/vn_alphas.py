"""
VN-Specific Alphas Module - Phase 2 Task P2.3
Layer 01: Core Intelligence

Provides 2 Vietnam-specific alpha factors:
1. alpha_vn_t2_momentum_adj: T+2 settlement cycle momentum adjustment
2. alpha_vn_penny_trap_score: Penny stock trap risk scoring

Author: V21_QUANT Team
Date: 2026-04-28
Status: Codex Approved P2.3
Compliance: 100% vectorized, PIT-safe, full type hints

PIT Safety:
    All alphas use shift(1) to ensure T-1 lag, preventing look-ahead bias.
    
Vectorization:
    100% Pandas/NumPy operations. No explicit Python loops.
    All operations use groupby/transform for cross-sectional processing.

NaN/Inf Handling:
    Safe division with replace/fillna patterns.
    Explicit handling of edge cases (zero volume, zero price).
"""

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    fill_value: float = 0.0
) -> pd.Series:
    """
    Safe division with zero/NaN/Inf handling.
    
    Args:
        numerator: Numerator series
        denominator: Denominator series
        fill_value: Value to use when division fails
    
    Returns:
        Series with safe division results
    """
    result = numerator / denominator.replace(0, np.nan)
    result = result.replace([np.inf, -np.inf], fill_value)
    result = result.fillna(fill_value)
    return result


def _apply_pit_lag(
    df: pd.DataFrame,
    col: str,
    symbol_col: str = 'ticker'
) -> pd.Series:
    """
    Apply T-1 lag to a column for PIT safety.
    
    Args:
        df: DataFrame with date and symbol columns
        col: Column name to lag
        symbol_col: Symbol column name for grouping
    
    Returns:
        Series with T-1 lagged values
    """
    return df.groupby(symbol_col)[col].shift(1)


# ============================================================================
# ALPHA 1: T+2 MOMENTUM ADJUSTMENT
# ============================================================================

def alpha_vn_t2_momentum_adj(
    df: pd.DataFrame,
    momentum_window: int = 20,
    price_col: str = 'close',
    symbol_col: str = 'ticker'
) -> pd.Series:
    """
    VN-Specific Alpha: T+2 Settlement Cycle Momentum Adjustment.
    
    Logic:
        1. Compute standard 20-day momentum
        2. Determine position in T+2 settlement cycle (day 0, 1, or 2)
        3. Apply cycle-based adjustment factor
        4. Apply T-1 lag for PIT safety
    
    Settlement Cycle Logic:
        - Day 0 (trade day): No adjustment (factor = 1.0)
        - Day 1 (T+1): Slight dampening (factor = 0.95)
        - Day 2 (T+2, settlement): Maximum dampening (factor = 0.90)
    
    The adjustment reflects reduced momentum reliability near settlement
    due to forced liquidations and settlement-driven flows.
    
    Args:
        df: DataFrame with columns [date, ticker, close]
        momentum_window: Lookback period for momentum (default 20)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        pd.Series: T+2 adjusted momentum, T-1 lagged for PIT safety
    
    Vectorization:
        - groupby/transform for per-symbol momentum
        - modulo arithmetic for cycle position
        - vectorized adjustment factor application
    
    PIT Safety:
        - shift(1) applied before return
    """
    # Validate inputs
    required_cols = [price_col, symbol_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Step 1: Compute 20-day momentum (vectorized per symbol)
    momentum = df.groupby(symbol_col)[price_col].transform(
        lambda x: x.pct_change(periods=momentum_window)
    )
    
    # Step 2: Determine position in T+2 cycle
    # Use cumulative count within each symbol group, then modulo 3
    df_temp = df.copy()
    df_temp['row_idx'] = df_temp.groupby(symbol_col).cumcount()
    cycle_position = df_temp['row_idx'] % 3
    
    # Step 3: Create adjustment factor based on cycle position
    # Day 0: 1.0, Day 1: 0.95, Day 2: 0.90
    adjustment_factor = pd.Series(1.0, index=df.index)
    adjustment_factor = adjustment_factor.where(cycle_position != 1, 0.95)
    adjustment_factor = adjustment_factor.where(cycle_position != 2, 0.90)
    
    # Step 4: Apply adjustment
    adjusted_momentum = momentum * adjustment_factor
    
    # Step 5: Handle NaN/Inf
    adjusted_momentum = adjusted_momentum.replace([np.inf, -np.inf], 0.0)
    adjusted_momentum = adjusted_momentum.fillna(0.0)
    
    # Step 6: Apply T-1 lag for PIT safety
    # Use a temporary column to ensure proper groupby behavior
    df_temp['adjusted_momentum'] = adjusted_momentum
    result = df_temp.groupby(symbol_col)['adjusted_momentum'].shift(1)
    
    return result


# ============================================================================
# ALPHA 2: PENNY TRAP SCORE
# ============================================================================

def alpha_vn_penny_trap_score(
    df: pd.DataFrame,
    price_col: str = 'close',
    volume_col: str = 'volume',
    high_col: str = 'high',
    low_col: str = 'low',
    symbol_col: str = 'ticker',
    price_threshold: float = 10000.0,  # VND 10,000
    volume_window: int = 20,
    limit_lock_window: int = 10
) -> pd.Series:
    """
    VN-Specific Alpha: Penny Stock Trap Risk Score.
    
    Logic:
        Combines three risk factors:
        1. Low price (< 10,000 VND threshold)
        2. Low liquidity (below median 20-day average volume)
        3. Frequent limit locks (high/low = close, indicating price manipulation)
    
    Score Calculation:
        - Price component: 1.0 if price < threshold, else 0.0
        - Liquidity component: 1.0 if ADV < cross-sectional median, else 0.0
        - Limit lock component: frequency of limit locks in last 10 days
        - Final score: weighted average (0.4 * price + 0.3 * liquidity + 0.3 * limit_lock)
    
    Higher score = higher penny trap risk.
    
    Args:
        df: DataFrame with columns [date, ticker, close, volume, high, low]
        price_col: Price column name
        volume_col: Volume column name
        high_col: High price column name
        low_col: Low price column name
        symbol_col: Symbol column name
        price_threshold: Price threshold for penny stock classification (VND)
        volume_window: Window for average volume calculation
        limit_lock_window: Window for limit lock frequency
    
    Returns:
        pd.Series: Penny trap risk score [0, 1], T-1 lagged for PIT safety
    
    Vectorization:
        - groupby/transform for rolling averages
        - vectorized comparisons for thresholds
        - cross-sectional median via transform
    
    PIT Safety:
        - shift(1) applied before return
    """
    # Validate inputs
    required_cols = [price_col, volume_col, high_col, low_col, symbol_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Component 1: Low price indicator (vectorized)
    price_component = (df[price_col] < price_threshold).astype(float)
    
    # Component 2: Low liquidity indicator
    # Calculate 20-day average volume per symbol
    adv_20 = df.groupby(symbol_col)[volume_col].transform(
        lambda x: x.rolling(window=volume_window, min_periods=1).mean()
    )
    
    # Calculate cross-sectional median ADV at each timestamp
    # Use groupby on date if available, otherwise use simple median
    if 'date' in df.columns:
        median_adv = df.groupby('date')[volume_col].transform('median')
    else:
        median_adv = adv_20.median()
    
    liquidity_component = (adv_20 < median_adv).astype(float)
    
    # Component 3: Limit lock frequency
    # Detect limit locks: close == high (ceiling) or close == low (floor)
    # Use small epsilon for floating point comparison
    epsilon = 1e-6
    ceiling_lock = (np.abs(df[price_col] - df[high_col]) < epsilon).astype(float)
    floor_lock = (np.abs(df[price_col] - df[low_col]) < epsilon).astype(float)
    limit_lock = (ceiling_lock + floor_lock).clip(upper=1.0)
    
    # Calculate limit lock frequency over window
    df_temp = df.copy()
    df_temp['limit_lock'] = limit_lock
    limit_lock_freq = df_temp.groupby(symbol_col)['limit_lock'].transform(
        lambda x: x.rolling(window=limit_lock_window, min_periods=1).mean()
    )
    
    # Combine components with weights
    # Weights: 40% price, 30% liquidity, 30% limit lock
    trap_score = (
        0.4 * price_component +
        0.3 * liquidity_component +
        0.3 * limit_lock_freq
    )
    
    # Handle NaN/Inf
    trap_score = trap_score.replace([np.inf, -np.inf], 0.0)
    trap_score = trap_score.fillna(0.0)
    
    # Clip to [0, 1] range
    trap_score = trap_score.clip(lower=0.0, upper=1.0)
    
    # Apply T-1 lag for PIT safety
    df_temp['trap_score'] = trap_score
    result = df_temp.groupby(symbol_col)['trap_score'].shift(1)
    
    return result


# ============================================================================
# BATCH COMPUTATION INTERFACE
# ============================================================================

def compute_vn_alphas(
    df: pd.DataFrame,
    symbol_col: str = 'ticker'
) -> pd.DataFrame:
    """
    Compute all VN-specific alphas in batch.
    
    Args:
        df: DataFrame with OHLCV data
        symbol_col: Symbol column name
    
    Returns:
        DataFrame with original data plus alpha columns:
            - alpha_vn_t2_momentum_adj
            - alpha_vn_penny_trap_score
    """
    result = df.copy()
    
    # Compute alphas
    result['alpha_vn_t2_momentum_adj'] = alpha_vn_t2_momentum_adj(
        df, symbol_col=symbol_col
    )
    result['alpha_vn_penny_trap_score'] = alpha_vn_penny_trap_score(
        df, symbol_col=symbol_col
    )
    
    logger.info(f"Computed 2 VN-specific alphas for {df[symbol_col].nunique()} symbols")
    
    return result
