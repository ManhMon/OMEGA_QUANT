"""
Advanced Feature Engineering - Vectorized Implementation
Part of OMEGA_QUANT Layer 01 Core Intelligence.

Includes: RSI, MACD, Bollinger Bands, ATR, ADX, Money Flow.
Strictly vectorized (no loops) and PIT safe (T-1 lag enforced).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple


class AdvancedFeatures:
    """Vectorized implementation of advanced technical indicators with T-1 lag."""

    def __init__(
        self,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        adx_period: int = 14
    ):
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.adx_period = adx_period

    def compute_rsi(self, prices: pd.Series) -> pd.Series:
        """Vectorized RSI using EWM with T-1 lag."""
        # Shift prices by 1 to enforce T-1 lag (use yesterday's data)
        prices_lagged = prices.shift(1)
        delta = prices_lagged.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(span=self.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(span=self.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100.0 - (100.0 / (1.0 + rs))

    def compute_macd(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Vectorized MACD with T-1 lag."""
        prices_lagged = prices.shift(1)
        ema_fast = prices_lagged.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = prices_lagged.ewm(span=self.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def compute_bollinger_bands(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Vectorized Bollinger Bands with T-1 lag."""
        prices_lagged = prices.shift(1)
        sma = prices_lagged.rolling(window=self.bb_period).mean()
        std = prices_lagged.rolling(window=self.bb_period).std()
        upper = sma + (self.bb_std * std)
        lower = sma - (self.bb_std * std)
        return upper, sma, lower

    def compute_atr(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        """Vectorized ATR with T-1 lag."""
        high_lag = high.shift(1)
        low_lag = low.shift(1)
        close_lag = close.shift(1)
        prev_close = close_lag.shift(1)
        
        tr = pd.concat([
            high_lag - low_lag,
            (high_lag - prev_close).abs(),
            (low_lag - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(span=self.atr_period, adjust=False).mean()

    def compute_adx(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        """Vectorized ADX with T-1 lag."""
        high_lag = high.shift(1)
        low_lag = low.shift(1)
        close_lag = close.shift(1)
        
        plus_dm = high_lag.diff().where((high_lag.diff() > low_lag.diff().abs()) & (high_lag.diff() > 0), 0.0)
        minus_dm = low_lag.diff().abs().where((low_lag.diff().abs() > high_lag.diff()) & (low_lag.diff().abs() > 0), 0.0)
        
        tr = self.compute_atr(high, low, close)
        plus_di = 100.0 * (plus_dm.ewm(span=self.adx_period, adjust=False).mean() / tr.replace(0, np.nan))
        minus_di = 100.0 * (minus_dm.ewm(span=self.adx_period, adjust=False).mean() / tr.replace(0, np.nan))
        
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        return dx.ewm(span=self.adx_period, adjust=False).mean()
