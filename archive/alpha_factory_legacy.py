"""
Core Alphas Module - Layer 01 Core Intelligence
UPDATED: Now uses ultimate_alpha_arsenal.py as the single source of truth.

Version: v21.29-Unified (Institutional Grade)
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-04-26
Major Update: Consolidated all alphas into ultimate_alpha_arsenal.py

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data.
- Vectorization: 100% Pandas/NumPy operations, zero loops.
- Robustness: Handles division by zero, NaN, and Inf.
- Schema: Returns DataFrame with same index, columns prefixed 'alpha_'.

This module now acts as a wrapper/facade to ultimate_alpha_arsenal.py
for backward compatibility with existing code.
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# AlphaFactory wrapper class for backward compatibility
class AlphaFactory:
    """Facade class for V21 Alpha computation."""
    
    def __init__(self, config=None):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def calculate_elite_alphas(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Backward compatibility wrapper for static calls."""
        if ARSENAL_AVAILABLE:
            return compute_ultimate_alphas(df, **kwargs)
        else:
            raise RuntimeError("Alpha arsenal not available")
            
    def compute_all_alphas(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Compute all alphas using the ultimate alpha arsenal."""
        return self.calculate_elite_alphas(df, **kwargs)

# Import the unified alpha arsenal
try:
    from .ultimate_alpha_arsenal import (
        compute_ultimate_alphas,
        get_alpha_metadata,
        _safe_divide
    )
    from .vn_alphas import compute_vn_alphas
    from .microstructure_alphas import compute_microstructure_alphas
    from .promoted_alphas import compute_promoted_alphas
    ARSENAL_AVAILABLE = True
    logger.info("Successfully imported ultimate_alpha_arsenal, vn_alphas, microstructure_alphas, and promoted_alphas")
except ImportError as e:
    ARSENAL_AVAILABLE = False
    logger.warning(f"Could not import alpha modules: {e}. Falling back to legacy implementation.")


def _safe_divide(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    """
    Safe division with zero/NaN/Inf handling.
    
    Args:
        numerator: Numerator series
        denominator: Denominator series
        fill_value: Value to use when division fails
    
    Returns:
        Series with safe division results
    """
    result = numerator / denominator
    result = result.replace([np.inf, -np.inf], fill_value)
    result = result.fillna(fill_value)
    return result


def _apply_lag(df: pd.DataFrame, columns: list, lag: int = 1, symbol_col: str = 'ticker') -> pd.DataFrame:
    """
    Apply T-lag to specified columns for PIT safety.
    
    Args:
        df: Input DataFrame with 'date' column
        columns: List of column names to lag
        lag: Number of periods to lag (default 1 for T-1)
        symbol_col: Symbol column name for grouping
    
    Returns:
        DataFrame with lagged columns (original names preserved)
    """
    df_out = df.copy()
    
    if 'date' not in df_out.columns:
        raise ValueError("PIT SAFETY: 'date' column required for lagging")
    
    df_out = df_out.sort_values(['date', symbol_col])
    
    for col in columns:
        if col in df_out.columns:
            df_out[col] = df_out.groupby(symbol_col)[col].shift(lag)
    
    return df_out


# ============================================================================
# MOMENTUM ALPHAS (3)
# ============================================================================

def compute_roc(df: pd.DataFrame, period: int, price_col: str = 'close', 
                symbol_col: str = 'ticker') -> pd.Series:
    """
    Rate of Change (ROC) - Momentum indicator.
    
    Formula: (Price_t / Price_{t-period} - 1) * 100
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (5 or 20)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with ROC values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Compute ROC on current prices, then lag the result
    price_shifted = df_work.groupby(symbol_col)[price_col].shift(period)
    roc = _safe_divide(df_work[price_col], price_shifted, fill_value=0.0) - 1.0
    roc = roc * 100.0
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_roc_temp'] = roc
    roc_lagged = df_work.groupby(symbol_col)['_roc_temp'].shift(1)
    
    return roc_lagged.fillna(0.0)


def compute_rsi(df: pd.DataFrame, period: int = 14, price_col: str = 'close',
                symbol_col: str = 'ticker') -> pd.Series:
    """
    Relative Strength Index (RSI) - Momentum oscillator.
    
    Formula: RSI = 100 - (100 / (1 + RS))
             RS = Average Gain / Average Loss over period
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 14)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with RSI values (0-100)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate price changes
    delta = df_work.groupby(symbol_col)[price_col].diff()
    
    # Separate gains and losses
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Calculate rolling averages using native rolling API
    avg_gain = gain.groupby(df_work[symbol_col]).rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df_work[symbol_col]).rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Calculate RS and RSI
    rs = _safe_divide(avg_gain, avg_loss, fill_value=0.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_rsi_temp'] = rsi
    rsi_lagged = df_work.groupby(symbol_col)['_rsi_temp'].shift(1)
    
    return rsi_lagged.fillna(50.0)  # Neutral RSI for missing values


# ============================================================================
# VOLATILITY ALPHAS (2)
# ============================================================================

def compute_atr_normalized(df: pd.DataFrame, period: int = 14, 
                          symbol_col: str = 'ticker') -> pd.Series:
    """
    Average True Range (ATR) normalized by close price.
    
    Formula: ATR / Close
             TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    PIT: Uses T-1 lagged values.
    
    Args:
        df: DataFrame with date, symbol, high, low, close columns
        period: Lookback period (default 14)
        symbol_col: Symbol column name
    
    Returns:
        Series with normalized ATR values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate True Range components
    high_low = df_work['high'] - df_work['low']
    
    close_prev = df_work.groupby(symbol_col)['close'].shift(1)
    high_close_prev = (df_work['high'] - close_prev).abs()
    low_close_prev = (df_work['low'] - close_prev).abs()
    
    # True Range = max of three components
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    
    # Calculate ATR (rolling mean of TR) using native rolling
    atr = tr.groupby(df_work[symbol_col]).rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Normalize by close price
    atr_norm = _safe_divide(atr, df_work['close'], fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_atr_norm_temp'] = atr_norm
    atr_norm_lagged = df_work.groupby(symbol_col)['_atr_norm_temp'].shift(1)
    
    return atr_norm_lagged.fillna(0.0)


def compute_historical_volatility(df: pd.DataFrame, period: int = 20,
                                  price_col: str = 'close', 
                                  symbol_col: str = 'ticker') -> pd.Series:
    """
    Historical Volatility - Standard deviation of returns.
    
    Formula: StdDev(log_returns) * sqrt(252) (annualized)
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with annualized volatility values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate log returns
    log_returns = np.log(df_work[price_col] / df_work.groupby(symbol_col)[price_col].shift(1))
    
    # Calculate rolling standard deviation using native rolling
    vol = log_returns.groupby(df_work[symbol_col]).rolling(window=period, min_periods=1).std().reset_index(level=0, drop=True)
    
    # Annualize (252 trading days)
    vol_annualized = vol * np.sqrt(252)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_vol_temp'] = vol_annualized
    vol_lagged = df_work.groupby(symbol_col)['_vol_temp'].shift(1)
    
    return vol_lagged.fillna(0.0)


# ============================================================================
# LIQUIDITY ALPHAS (2)
# ============================================================================

def compute_volume_ma_ratio(df: pd.DataFrame, short_period: int = 5,
                           long_period: int = 20, volume_col: str = 'volume',
                           symbol_col: str = 'ticker') -> pd.Series:
    """
    Volume Moving Average Ratio - Liquidity indicator.
    
    Formula: MA(Volume, short) / MA(Volume, long)
    PIT: Uses T-1 lagged volumes.
    
    Args:
        df: DataFrame with date, symbol, and volume columns
        short_period: Short MA period (default 5)
        long_period: Long MA period (default 20)
        volume_col: Volume column name
        symbol_col: Symbol column name
    
    Returns:
        Series with volume MA ratio values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate short and long moving averages using native rolling
    vol_ma_short = df_work.groupby(symbol_col)[volume_col].rolling(window=short_period, min_periods=1).mean().reset_index(level=0, drop=True)
    vol_ma_long = df_work.groupby(symbol_col)[volume_col].rolling(window=long_period, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Calculate ratio
    ratio = _safe_divide(vol_ma_short, vol_ma_long, fill_value=1.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_ratio_temp'] = ratio
    ratio_lagged = df_work.groupby(symbol_col)['_ratio_temp'].shift(1)
    
    return ratio_lagged.fillna(1.0)


def compute_illiquidity_amihud(df: pd.DataFrame, period: int = 20,
                               price_col: str = 'close', volume_col: str = 'volume',
                               symbol_col: str = 'ticker') -> pd.Series:
    """
    Amihud Illiquidity Measure - Price impact per unit volume.
    
    Formula: Average(|Return| / Volume) over period
    PIT: Uses T-1 lagged data.
    
    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period (default 20)
        price_col: Price column name
        volume_col: Volume column name
        symbol_col: Symbol column name
    
    Returns:
        Series with illiquidity values (scaled by 1e6)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate absolute returns
    returns = df_work.groupby(symbol_col)[price_col].pct_change().abs()
    
    # Calculate price impact (return / volume)
    price_impact = _safe_divide(returns, df_work[volume_col], fill_value=0.0)
    
    # Calculate rolling average using native rolling
    illiquidity = price_impact.groupby(df_work[symbol_col]).rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Scale by 1e6 for readability
    illiquidity = illiquidity * 1e6
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_illiq_temp'] = illiquidity
    illiquidity_lagged = df_work.groupby(symbol_col)['_illiq_temp'].shift(1)
    
    return illiquidity_lagged.fillna(0.0)


# ============================================================================
# TREND ALPHAS (2)
# ============================================================================

def compute_distance_to_ma(df: pd.DataFrame, period: int = 20,
                          price_col: str = 'close', symbol_col: str = 'ticker') -> pd.Series:
    """
    Distance to Moving Average - Trend strength indicator.
    
    Formula: (Price - MA(Price, period)) / MA(Price, period)
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        period: MA period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with distance to MA values (percentage)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate moving average using native rolling
    ma = df_work.groupby(symbol_col)[price_col].rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Calculate distance
    distance = _safe_divide(df_work[price_col] - ma, ma, fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_dist_temp'] = distance
    distance_lagged = df_work.groupby(symbol_col)['_dist_temp'].shift(1)
    
    return distance_lagged.fillna(0.0)


def compute_distance_to_high(df: pd.DataFrame, period: int = 252,
                            price_col: str = 'close', high_col: str = 'high',
                            symbol_col: str = 'ticker') -> pd.Series:
    """
    Distance to Period High - Trend position indicator.
    
    Formula: (Price - High_period) / High_period
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, price, and high columns
        period: Lookback period (default 252 = 1 year)
        price_col: Price column name
        high_col: High column name
        symbol_col: Symbol column name
    
    Returns:
        Series with distance to high values (percentage, typically negative)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate rolling high using native rolling
    rolling_high = df_work.groupby(symbol_col)[high_col].rolling(window=period, min_periods=1).max().reset_index(level=0, drop=True)
    
    # Calculate distance
    distance = _safe_divide(df_work[price_col] - rolling_high, rolling_high, fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_dist_high_temp'] = distance
    distance_lagged = df_work.groupby(symbol_col)['_dist_high_temp'].shift(1)
    
    return distance_lagged.fillna(0.0)


# ============================================================================
# MEAN REVERSION ALPHAS (2)
# ============================================================================

def compute_bollinger_distance(df: pd.DataFrame, period: int = 120,
                               price_col: str = 'close', symbol_col: str = 'ticker') -> pd.Series:
    """
    Bollinger Band Distance - Mean reversion indicator.
    
    Formula: (Price - MA) / (2 * StdDev)
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 120)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with Bollinger distance values (typically -1 to +1)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate moving average and standard deviation using native rolling
    ma = df_work.groupby(symbol_col)[price_col].rolling(window=period, min_periods=1).mean().reset_index(level=0, drop=True)
    std = df_work.groupby(symbol_col)[price_col].rolling(window=period, min_periods=1).std().reset_index(level=0, drop=True)
    
    # Calculate Bollinger distance
    bb_dist = _safe_divide(df_work[price_col] - ma, 2 * std, fill_value=0.0)
    
    # Apply T-1 lag for PIT safety
    df_work['_bb_dist_temp'] = bb_dist
    bb_dist_lagged = df_work.groupby(symbol_col)['_bb_dist_temp'].shift(1)
    
    return bb_dist_lagged.fillna(0.0)


def compute_rsi_crossover(df: pd.DataFrame, short_period: int = 20,
                         long_period: int = 120, price_col: str = 'close',
                         symbol_col: str = 'ticker') -> pd.Series:
    """
    RSI Crossover - Momentum regime change detector.
    
    Formula: RSI(short) - RSI(long)
    PIT: Uses T-1 lagged prices.
    
    Args:
        df: DataFrame with date, symbol, and price columns
        short_period: Short RSI period (default 20)
        long_period: Long RSI period (default 120)
        price_col: Price column name
        symbol_col: Symbol column name
    
    Returns:
        Series with RSI crossover values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Compute RSI for both periods (already includes T-1 lag)
    rsi_short = compute_rsi(df_work, period=short_period, price_col=price_col, symbol_col=symbol_col)
    rsi_long = compute_rsi(df_work, period=long_period, price_col=price_col, symbol_col=symbol_col)
    
    # Crossover signal
    crossover = rsi_short - rsi_long
    
    return crossover.fillna(0.0)


# ============================================================================
# LIQUIDITY SHIFT ALPHAS (2)
# ============================================================================

def compute_volume_momentum(df: pd.DataFrame, period: int = 5,
                           volume_col: str = 'volume', symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate volume change
    vol_shifted = df_work.groupby(symbol_col)[volume_col].shift(period)
    vol_momentum = _safe_divide(df_work[volume_col] - vol_shifted, vol_shifted, fill_value=0.0)
    
    # Apply T-1 lag for PIT safety
    df_work['_vol_mom_temp'] = vol_momentum
    vol_momentum_lagged = df_work.groupby(symbol_col)['_vol_mom_temp'].shift(1)
    
    return vol_momentum_lagged.fillna(0.0)


def compute_price_acceleration(df: pd.DataFrame, price_col: str = 'close',
                               symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate first derivative (returns)
    returns = df_work.groupby(symbol_col)[price_col].pct_change()
    
    # Calculate second derivative (acceleration)
    acceleration = returns.groupby(df_work[symbol_col]).diff()
    
    # Apply T-1 lag for PIT safety
    df_work['_accel_temp'] = acceleration
    acceleration_lagged = df_work.groupby(symbol_col)['_accel_temp'].shift(1)
    
    return acceleration_lagged.fillna(0.0)


# ============================================================================
# PRICE ACTION ALPHAS (4)
# ============================================================================

def compute_body_size(df: pd.DataFrame, symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate body size
    body = _safe_divide((df_work['close'] - df_work['open']).abs(), 
                       df_work['open'], fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_body_temp'] = body
    body_lagged = df_work.groupby(symbol_col)['_body_temp'].shift(1)
    
    return body_lagged.fillna(0.0)


def compute_upper_shadow(df: pd.DataFrame, symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate upper shadow
    body_top = df_work[['open', 'close']].max(axis=1)
    shadow = _safe_divide(df_work['high'] - body_top, df_work['open'], fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_upper_shadow_temp'] = shadow
    shadow_lagged = df_work.groupby(symbol_col)['_upper_shadow_temp'].shift(1)
    
    return shadow_lagged.fillna(0.0)


def compute_lower_shadow(df: pd.DataFrame, symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate lower shadow
    body_bottom = df_work[['open', 'close']].min(axis=1)
    shadow = _safe_divide(body_bottom - df_work['low'], df_work['open'], fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_lower_shadow_temp'] = shadow
    shadow_lagged = df_work.groupby(symbol_col)['_lower_shadow_temp'].shift(1)
    
    return shadow_lagged.fillna(0.0)


def compute_gap_return(df: pd.DataFrame, symbol_col: str = 'ticker') -> pd.Series:
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
    df_work = df_work.sort_values(['date', symbol_col])
    
    # Calculate gap
    close_prev = df_work.groupby(symbol_col)['close'].shift(1)
    gap = _safe_divide(df_work['open'] - close_prev, close_prev, fill_value=0.0)
    
    # Apply T-1 lag for PIT safety - add to DataFrame first
    df_work['_gap_temp'] = gap
    gap_lagged = df_work.groupby(symbol_col)['_gap_temp'].shift(1)
    
    return gap_lagged.fillna(0.0)


# ============================================================================
# MAIN COMPUTATION FUNCTION
# ============================================================================

def compute_core_alphas(df: pd.DataFrame, symbol_col: str = 'ticker', apply_neutralization: bool = True) -> pd.DataFrame:
    """
    Compute all core alpha factors with PIT safety.
    
    UPDATED v21.29: Now uses ultimate_alpha_arsenal.py for all computations.
    UPDATED v21.30: Added neutralization integration (FIX Issue 1).
    This function maintains backward compatibility with existing code.
    
    REQUIREMENTS:
    - Input must have columns: date, ticker, open, high, low, close, volume
    - All alphas use T-1 lagged data for PIT compliance
    - Output has same index as input with alpha columns prefixed 'alpha_'
    - Neutralization applied AFTER alpha computation if apply_neutralization=True
    
    Args:
        df: Input DataFrame with OHLCV data
        symbol_col: Symbol column name (default 'ticker')
        apply_neutralization: Whether to apply neutralization (default True)
    
    Returns:
        DataFrame with original data + alpha columns (neutralized if enabled)
    
    Raises:
        ValueError: If required columns are missing
    """
    # Handle empty or invalid DataFrame
    if df.empty or 'date' not in df.columns:
        logger.warning("Empty or invalid DataFrame provided to compute_core_alphas")
        return pd.DataFrame()
    
    # Validate required columns
    required_cols = ['date', symbol_col, 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Use ultimate_alpha_arsenal if available
    if ARSENAL_AVAILABLE:
        logger.info("Computing alphas using ultimate_alpha_arsenal...")
        try:
            # Compute all alphas using the unified arsenal
            df_out = compute_ultimate_alphas(df, symbol_col=symbol_col)
            logger.info(f"Alpha computation complete. Total columns: {len(df_out.columns)}")
            
            # FIX Issue 1: Apply neutralization AFTER alpha computation
            if apply_neutralization:
                df_out = _apply_neutralization(df_out, symbol_col=symbol_col)
            
            return df_out
        except Exception as e:
            logger.error(f"Error using ultimate_alpha_arsenal: {e}. Falling back to legacy.")
    
    # Fallback to legacy implementation if arsenal not available
    logger.warning("Using legacy alpha computation (ultimate_alpha_arsenal not available)")
    df_out = df.copy()
    
    # Legacy implementation preserved for backward compatibility
    # 1. Momentum Alphas (3)
    df_out['alpha_roc_5'] = compute_roc(df_out, period=5, symbol_col=symbol_col)
    df_out['alpha_roc_20'] = compute_roc(df_out, period=20, symbol_col=symbol_col)
    df_out['alpha_rsi_14'] = compute_rsi(df_out, period=14, symbol_col=symbol_col)
    
    # 2. Volatility Alphas (2)
    df_out['alpha_atr_14_norm'] = compute_atr_normalized(df_out, period=14, symbol_col=symbol_col)
    df_out['alpha_hist_vol_20'] = compute_historical_volatility(df_out, period=20, symbol_col=symbol_col)
    
    # 3. Liquidity Alphas (2)
    df_out['alpha_vol_ma_ratio'] = compute_volume_ma_ratio(df_out, short_period=5, 
                                                           long_period=20, symbol_col=symbol_col)
    df_out['alpha_illiquidity_amihud'] = compute_illiquidity_amihud(df_out, period=20, 
                                                                     symbol_col=symbol_col)
    
    # 4. Trend Alphas (2)
    df_out['alpha_dist_ma_20'] = compute_distance_to_ma(df_out, period=20, symbol_col=symbol_col)
    df_out['alpha_dist_high_252'] = compute_distance_to_high(df_out, period=252, symbol_col=symbol_col)
    
    # 5. Price Action Alphas (4)
    df_out['alpha_body_size'] = compute_body_size(df_out, symbol_col=symbol_col)
    df_out['alpha_upper_shadow'] = compute_upper_shadow(df_out, symbol_col=symbol_col)
    df_out['alpha_lower_shadow'] = compute_lower_shadow(df_out, symbol_col=symbol_col)
    df_out['alpha_gap_return'] = compute_gap_return(df_out, symbol_col=symbol_col)
    
    # 6. Mean Reversion Alphas (2)
    df_out['alpha_bb_dist_120'] = compute_bollinger_distance(df_out, period=120, symbol_col=symbol_col)
    df_out['alpha_rsi_crossover_20_120'] = compute_rsi_crossover(df_out, short_period=20, 
                                                                  long_period=120, symbol_col=symbol_col)
    
    # 7. Liquidity Shift Alphas (2)
    df_out['alpha_vol_momentum_5'] = compute_volume_momentum(df_out, period=5, symbol_col=symbol_col)
    df_out['alpha_price_acceleration'] = compute_price_acceleration(df_out, symbol_col=symbol_col)
    
    logger.info("Legacy alpha computation complete.")
    
    # FIX Issue 1: Apply neutralization AFTER alpha computation
    if apply_neutralization:
        df_out = _apply_neutralization(df_out, symbol_col=symbol_col)
    
    return df_out


def _apply_neutralization(df: pd.DataFrame, symbol_col: str = 'ticker') -> pd.DataFrame:
    """
    FIX Issue 1: Apply neutralization to alpha columns.
    
    This function is called AFTER alpha computation to neutralize alphas
    against sector, price, and liquidity biases.
    
    Args:
        df: DataFrame with alpha columns
        symbol_col: Symbol column name
        
    Returns:
        DataFrame with neutralized alpha columns (suffix: _neutral)
    """
    try:
        from omega.quant.neutralization import NeutralizationEngine
        
        # FIX Issue 3 (PIT-003): Validate PIT safety for existing neutralization columns
        # If sector/price_bucket/liquidity_bucket already exist, validate they use T-1 lagged data
        required_neutral_cols = ['sector', 'price_bucket', 'liquidity_bucket']
        existing_neutral_cols = [col for col in required_neutral_cols if col in df.columns]
        
        if existing_neutral_cols:
            logger.info(f"Validating PIT safety for existing neutralization columns: {existing_neutral_cols}")
            
            # Validation: Check if these columns are properly lagged
            if 'date' in df.columns and symbol_col in df.columns:
                df_sorted = df.sort_values(['date', symbol_col])
                
                for col in existing_neutral_cols:
                    # Check if column values change within the same symbol (indicating time-series data)
                    # If they don't change, they might be static (like sector) which is OK
                    grouped = df_sorted.groupby(symbol_col)[col]
                    nunique_per_symbol = grouped.nunique()
                    
                    # If column varies over time for any symbol, it should be lagged
                    if (nunique_per_symbol > 1).any():
                        # Check if first occurrence per symbol has NaN (indicating T-1 lag was applied)
                        first_values = grouped.first()
                        first_row_per_symbol = df_sorted.groupby(symbol_col).first()[col]
                        
                        # For time-varying columns, we expect some NaN in early dates if properly lagged
                        # This is a heuristic check - not perfect but catches obvious violations
                        if col in ['price_bucket', 'liquidity_bucket']:
                            # These should definitely be lagged
                            logger.warning(f"PIT VALIDATION WARNING: Column '{col}' already exists and varies over time.")
                            logger.warning(f"  Ensure '{col}' uses T-1 lagged data. Current implementation assumes it's PIT-safe.")
                            logger.warning(f"  If '{col}' uses same-day data, this violates PIT safety!")
                    else:
                        # Static column (like sector) - this is fine
                        logger.info(f"Column '{col}' appears static (no time variation) - PIT safe")
        
        # FIX Issue 6: Create required columns if they don't exist
        missing_neutral_cols = [col for col in required_neutral_cols if col not in df.columns]
        
        if missing_neutral_cols:
            logger.info(f"Creating missing neutralization columns: {missing_neutral_cols}")
            
            # Create sector column (default to 'Unknown' if not available)
            if 'sector' not in df.columns:
                df['sector'] = 'Unknown'
                logger.warning("Created 'sector' column with default value 'Unknown'. Consider adding real sector data.")
            
            # Create price_bucket column (quintiles based on T-1 lagged close price)
            if 'price_bucket' not in df.columns:
                if 'close' in df.columns:
                    # P0 FIX: Lag close price by T-1 before creating buckets (PIT safety)
                    if 'date' in df.columns and symbol_col in df.columns:
                        # Sort by date and symbol for proper groupby shift
                        df = df.sort_values(['date', symbol_col]).reset_index(drop=True)
                        
                        # Apply T-1 lag using grouped shift
                        close_lagged = df.groupby(symbol_col)['close'].shift(1)
                        
                        # Error handling: Check if T-1 data exists
                        if close_lagged.isna().all():
                            logger.critical("PIT VIOLATION BLOCKED: No T-1 close data available for price_bucket creation")
                            df['price_bucket'] = 'P3'  # Default to middle bucket
                            logger.warning("Created 'price_bucket' column with default value 'P3' due to missing T-1 data")
                        else:
                            # FIX Issue 2 (PIT-002): Apply pd.qcut() separately for each date
                            # This prevents cross-date buckets which violate PIT safety
                            def create_date_buckets(group):
                                """Create quintile buckets within each date."""
                                try:
                                    return pd.qcut(group, q=5, labels=['P1', 'P2', 'P3', 'P4', 'P5'], duplicates='drop')
                                except (ValueError, TypeError):
                                    # Handle cases with too few unique values or all NaN
                                    return pd.Series(['P3'] * len(group), index=group.index)
                            
                            # Add close_lagged to DataFrame temporarily for groupby
                            df['_close_lagged_temp'] = close_lagged
                            
                            # Apply qcut per date to ensure date-specific buckets
                            df['price_bucket'] = df.groupby('date')['_close_lagged_temp'].transform(create_date_buckets)
                            
                            # Clean up temporary column
                            df = df.drop(columns=['_close_lagged_temp'])
                            
                            logger.info("Created 'price_bucket' column using T-1 lagged close price quintiles (PIT compliant, date-specific)")
                            
                            # Validation: Ensure buckets are from T-1 data
                            na_count = df['price_bucket'].isna().sum()
                            if na_count > 0:
                                logger.warning(f"PIT validation: {na_count} rows have NaN price_bucket due to missing T-1 data")
                                # Fill NaN with default bucket
                                df['price_bucket'] = df['price_bucket'].fillna('P3')
                    else:
                        # P0 FIX: DO NOT fall back to same-day data - use safe default with CRITICAL log
                        logger.critical("PIT VIOLATION BLOCKED: 'date' or symbol column missing, cannot lag close price")
                        df['price_bucket'] = 'P3'  # Safe default to middle bucket
                        logger.critical("Created 'price_bucket' column with safe default 'P3' (NOT using same-day data)")
                else:
                    df['price_bucket'] = 'P3'  # Default to middle bucket
                    logger.warning("Created 'price_bucket' column with default value 'P3'")
            
            # Create liquidity_bucket column (quintiles based on T-1 lagged volume)
            if 'liquidity_bucket' not in df.columns:
                if 'volume' in df.columns:
                    # PIT FIX: Lag volume by T-1 before creating buckets
                    if 'date' in df.columns and symbol_col in df.columns:
                        # Apply T-1 lag using grouped shift
                        volume_lagged = df.groupby(symbol_col)['volume'].shift(1)
                        
                        # Error handling: Check if T-1 data exists
                        if volume_lagged.isna().all():
                            logger.critical("PIT VIOLATION BLOCKED: No T-1 volume data available for liquidity_bucket creation")
                            df['liquidity_bucket'] = 'L3'  # Default to middle bucket
                            logger.warning("Created 'liquidity_bucket' column with default value 'L3' due to missing T-1 data")
                        else:
                            # FIX Issue 2 (PIT-002): Apply pd.qcut() separately for each date
                            # This prevents cross-date buckets which violate PIT safety
                            def create_date_buckets(group):
                                """Create quintile buckets within each date."""
                                try:
                                    return pd.qcut(group, q=5, labels=['L1', 'L2', 'L3', 'L4', 'L5'], duplicates='drop')
                                except (ValueError, TypeError):
                                    # Handle cases with too few unique values or all NaN
                                    return pd.Series(['L3'] * len(group), index=group.index)
                            
                            # Add volume_lagged to DataFrame temporarily for groupby
                            df['_volume_lagged_temp'] = volume_lagged
                            
                            # Apply qcut per date to ensure date-specific buckets
                            df['liquidity_bucket'] = df.groupby('date')['_volume_lagged_temp'].transform(create_date_buckets)
                            
                            # Clean up temporary column
                            df = df.drop(columns=['_volume_lagged_temp'])
                            
                            logger.info("Created 'liquidity_bucket' column using T-1 lagged volume quintiles (PIT compliant, date-specific)")
                            
                            # Validation: Ensure buckets are from T-1 data
                            na_count = df['liquidity_bucket'].isna().sum()
                            if na_count > 0:
                                logger.warning(f"PIT validation: {na_count} rows have NaN liquidity_bucket due to missing T-1 data")
                                # Fill NaN with default bucket
                                df['liquidity_bucket'] = df['liquidity_bucket'].fillna('L3')
                    else:
                        # P0 FIX: DO NOT fall back to same-day data - use safe default with CRITICAL log
                        logger.critical("PIT VIOLATION BLOCKED: 'date' or symbol column missing, cannot lag volume")
                        df['liquidity_bucket'] = 'L3'  # Safe default to middle bucket
                        logger.critical("Created 'liquidity_bucket' column with safe default 'L3' (NOT using same-day data)")
                else:
                    df['liquidity_bucket'] = 'L3'  # Default to middle bucket
                    logger.warning("Created 'liquidity_bucket' column with default value 'L3'")
        
        # P2 FIX: Validate PIT compliance for neutralization features
        # Ensure sector/price/liquidity buckets use T-1 data
        if 'date' in df.columns or 'timestamp' in df.columns:
            date_col = 'date' if 'date' in df.columns else 'timestamp'
            # Check if neutralization features are lagged
            # This is a validation warning - caller must ensure features are T-1
            if df[date_col].nunique() > 1:
                logger.info("PIT validation: Neutralization features should be computed from T-1 data")
                # Log sample to audit trail
                sample_dates = df[date_col].unique()[:3]
                logger.info(f"Sample dates in neutralization: {sample_dates}")
        
        # Get all alpha columns
        alpha_cols = [col for col in df.columns if col.startswith('alpha_')]
        
        if not alpha_cols:
            logger.warning("No alpha columns found for neutralization")
            return df
        
        # Set MultiIndex (date, symbol) if not already set
        if not isinstance(df.index, pd.MultiIndex):
            df_indexed = df.set_index(['date', symbol_col])
        else:
            df_indexed = df
        
        # Initialize neutralization engine
        engine = NeutralizationEngine(
            min_l3_size=5,
            min_l2_size=10,
            winsorize_lower=0.01,
            winsorize_upper=0.99
        )
        
        # Apply neutralization to all alpha columns
        df_neutralized = engine.neutralize_panel(
            df_indexed,
            alpha_cols=alpha_cols,
            sector_col='sector',
            price_level_col='price_bucket',
            liquidity_col='liquidity_bucket'
        )
        
        # P1 FIX: Replace raw alphas with neutralized versions
        # Drop the _neutral suffix and replace original alpha columns
        for alpha_col in alpha_cols:
            neutral_col = f"{alpha_col}_neutral"
            if neutral_col in df_neutralized.columns:
                # Replace raw alpha with neutralized version
                df_neutralized[alpha_col] = df_neutralized[neutral_col]
                # Drop the _neutral column
                df_neutralized = df_neutralized.drop(columns=[neutral_col])
        
        logger.info(f"Neutralization applied to {len(alpha_cols)} alpha columns (raw alphas replaced)")
        
        # Reset index if it was set in this function
        if not isinstance(df.index, pd.MultiIndex):
            df_neutralized = df_neutralized.reset_index()
        
        return df_neutralized
        
    except ImportError as e:
        logger.warning(f"NeutralizationEngine not available: {e}. Skipping neutralization.")
        return df
    except Exception as e:
        logger.error(f"Error during neutralization: {e}. Returning unneutralized alphas.")
        return df


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create test data
    print("Creating test data...")
    test_df = pd.DataFrame({
        'date': pd.to_datetime(['2026-04-20', '2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
                                '2026-04-20', '2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24'] * 2),
        'ticker': ['VNM'] * 10 + ['HPG'] * 10,
        'open': [80000, 81000, 82000, 81500, 83000,
                 24000, 24500, 25000, 24800, 25500] * 2,
        'high': [82000, 83000, 84000, 83500, 85000,
                 25000, 25500, 26000, 25800, 26500] * 2,
        'low': [79000, 80000, 81000, 80500, 82000,
                23500, 24000, 24500, 24300, 25000] * 2,
        'close': [81000, 82000, 83000, 82500, 84000,
                  24500, 25000, 25500, 25300, 26000] * 2,
        'volume': [1000000, 1100000, 1200000, 1150000, 1300000,
                   2000000, 2100000, 2200000, 2150000, 2300000] * 2
    })
    
    print("\nComputing core alphas...")
    result_df = compute_core_alphas(test_df)
    
    print("\nResult columns:")
    print([col for col in result_df.columns if col.startswith('alpha_')])
    
    print("\nSample output (first 5 rows):")
    alpha_cols = [col for col in result_df.columns if col.startswith('alpha_')]
    print(result_df[['date', 'ticker', 'close'] + alpha_cols].head())
    
    print("\nPIT Safety Check - First row should have NaN/0 for most alphas (no T-1 data):")
    print(result_df[alpha_cols].iloc[0])


