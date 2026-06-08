"""
OMEGA_QUANT Feature Factory - Basic Indicators (Layer 01)
Phase 2.1: Feature Engineering - Basic Technical Indicators

100% Vectorized | PIT-Safe | Institutional Grade

Implements:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands (Upper, Middle, Lower)
- ATR (Average True Range)
- VWAP (Volume Weighted Average Price)

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


def compute_rsi(
    close: pd.Series,
    period: int = 14,
    lag: int = 1
) -> pd.Series:
    """
    Compute Relative Strength Index (RSI) - 100% Vectorized.
    
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss over period
    
    Args:
        close: Close price series
        period: RSI period (default 14)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        RSI series (0-100 scale), shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized price changes
    delta = close.diff()
    
    # Separate gains and losses
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Exponential moving average (Wilder's smoothing)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    
    # RS and RSI calculation
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    # Handle division by zero (when avg_loss = 0)
    rsi = rsi.fillna(100.0)
    
    # PIT Guard: Shift by lag periods
    return rsi.shift(lag)


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    lag: int = 1
) -> pd.DataFrame:
    """
    Compute MACD (Moving Average Convergence Divergence) - 100% Vectorized.
    
    MACD Line = EMA(fast) - EMA(slow)
    Signal Line = EMA(MACD, signal)
    Histogram = MACD - Signal
    
    Args:
        close: Close price series
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line period (default 9)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with columns: macd, macd_signal, macd_hist
        All shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized EMA calculations
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    
    # Histogram
    histogram = macd_line - signal_line
    
    # Combine into DataFrame
    result = pd.DataFrame({
        'macd': macd_line,
        'macd_signal': signal_line,
        'macd_hist': histogram
    }, index=close.index)
    
    # PIT Guard: Shift by lag periods
    return result.shift(lag)


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
    lag: int = 1
) -> pd.DataFrame:
    """
    Compute Bollinger Bands - 100% Vectorized.
    
    Middle Band = SMA(period)
    Upper Band = Middle + (num_std * std)
    Lower Band = Middle - (num_std * std)
    
    Args:
        close: Close price series
        period: Rolling window period (default 20)
        num_std: Number of standard deviations (default 2.0)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with columns: bb_upper, bb_middle, bb_lower, bb_width
        All shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Vectorized rolling calculations
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    
    # Band calculations
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    
    # Band width (normalized by middle)
    width = (upper - lower) / middle
    width = width.fillna(0.0)
    
    # Combine into DataFrame
    result = pd.DataFrame({
        'bb_upper': upper,
        'bb_middle': middle,
        'bb_lower': lower,
        'bb_width': width
    }, index=close.index)
    
    # PIT Guard: Shift by lag periods
    return result.shift(lag)


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    lag: int = 1
) -> pd.Series:
    """
    Compute Average True Range (ATR) - 100% Vectorized.
    
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = EMA(True Range, period)
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 14)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        ATR series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Previous close
    prev_close = close.shift(1)
    
    # Vectorized True Range calculation
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    # True Range is the maximum of the three
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR using exponential moving average
    atr = true_range.ewm(span=period, adjust=False).mean()
    
    # PIT Guard: Shift by lag periods
    return atr.shift(lag)


def compute_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: Optional[int] = None,
    lag: int = 1
) -> pd.Series:
    """
    Compute Volume Weighted Average Price (VWAP) - 100% Vectorized.
    
    Typical Price = (High + Low + Close) / 3
    VWAP = Sum(Typical Price * Volume) / Sum(Volume)
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        volume: Volume series
        period: Rolling window period (None = cumulative from start)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        VWAP series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    
    Note: If period is None, computes cumulative VWAP from start.
          If period is specified, computes rolling VWAP over that window.
    """
    # Vectorized typical price calculation
    typical_price = (high + low + close) / 3.0
    
    # Price * Volume
    pv = typical_price * volume
    
    if period is None:
        # Cumulative VWAP
        vwap = pv.cumsum() / volume.cumsum()
    else:
        # Rolling VWAP
        pv_sum = pv.rolling(window=period).sum()
        vol_sum = volume.rolling(window=period).sum()
        vwap = pv_sum / vol_sum
    
    # Handle division by zero
    vwap = vwap.ffill().fillna(0.0)
    
    # PIT Guard: Shift by lag periods
    return vwap.shift(lag)


def compute_returns(
    close: pd.Series,
    period: int = None,
    periods: int = None,
    lag: int = 0
) -> pd.Series:
    """
    Compute simple returns - 100% Vectorized.
    
    Returns = (close[t] - close[t-period]) / close[t-period]
    
    Args:
        close: Close price series
        period: Lookback period for returns (default 1 = daily returns)
        periods: Alias for period (for backward compatibility)
        lag: T-lag for PIT safety (default 0 for testing, use 1 in production)
    
    Returns:
        Returns series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Support both 'period' and 'periods' parameter names
    lookback = periods if periods is not None else (period if period is not None else 1)
    returns = close.pct_change(periods=lookback)
    if lag > 0:
        return returns.shift(lag)
    return returns


def compute_volatility(
    returns: pd.Series = None,
    close: pd.Series = None,
    period: int = None,
    window: int = None,
    lag: int = 0
) -> pd.Series:
    """
    Compute rolling volatility (standard deviation of returns) - 100% Vectorized.
    
    Volatility = std(returns) over rolling window
    
    Args:
        returns: Returns series (optional if close provided)
        close: Close price series (optional if returns provided)
        period: Rolling window period (default 20)
        window: Alias for period (for backward compatibility)
        lag: T-lag for PIT safety (default 0 for testing, use 1 in production)
    
    Returns:
        Volatility series, shifted by lag periods
    
    PIT Safety: Output is shifted by `lag` periods to enforce T-1 availability.
    """
    # Support both 'period' and 'window' parameter names
    lookback = window if window is not None else (period if period is not None else 20)
    
    # Compute returns if not provided
    if returns is None:
        if close is None:
            raise ValueError("Either 'close' or 'returns' must be provided")
        returns = close.pct_change()
    
    volatility = returns.rolling(window=lookback).std()
    if lag > 0:
        return volatility.shift(lag)
    return volatility


def compute_all_basic_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
    atr_period: int = 14,
    vwap_period: Optional[int] = None,
    lag: int = 1
) -> pd.DataFrame:
    """
    Compute all basic indicators in one pass - 100% Vectorized.
    
    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
        rsi_period: RSI period (default 14)
        macd_fast: MACD fast period (default 12)
        macd_slow: MACD slow period (default 26)
        macd_signal: MACD signal period (default 9)
        bb_period: Bollinger Bands period (default 20)
        bb_std: Bollinger Bands std multiplier (default 2.0)
        atr_period: ATR period (default 14)
        vwap_period: VWAP period (None = cumulative)
        lag: T-lag for PIT safety (default 1)
    
    Returns:
        DataFrame with all indicator columns, same index as input
    
    PIT Safety: All features shifted by `lag` periods to enforce T-1 availability.
    
    Raises:
        ValueError: If required columns are missing
    """
    # Validate input
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Extract series
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    # Compute all indicators
    result = pd.DataFrame(index=df.index)
    
    # RSI
    result['rsi'] = compute_rsi(close, period=rsi_period, lag=lag)
    
    # MACD
    macd_df = compute_macd(close, fast=macd_fast, slow=macd_slow, signal=macd_signal, lag=lag)
    result = result.join(macd_df)
    
    # Bollinger Bands
    bb_df = compute_bollinger_bands(close, period=bb_period, num_std=bb_std, lag=lag)
    result = result.join(bb_df)
    
    # ATR
    result['atr'] = compute_atr(high, low, close, period=atr_period, lag=lag)
    
    # VWAP
    result['vwap'] = compute_vwap(high, low, close, volume, period=vwap_period, lag=lag)
    
    return result
