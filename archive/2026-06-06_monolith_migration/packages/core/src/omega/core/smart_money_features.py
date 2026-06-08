"""
Smart Money Features - Vectorized Implementation
Detects institutional/smart money flow patterns.

Part of OMEGA_QUANT Layer 01 Core Intelligence.
100% vectorized, PIT safe (T-1 lag enforced).
"""

import pandas as pd
import numpy as np
from typing import Tuple


class SmartMoneyFeatures:
    """Vectorized smart money flow analysis with T-1 lag."""

    def __init__(self, volume_ma_period: int = 20, price_ma_period: int = 20):
        self.volume_ma_period = volume_ma_period
        self.price_ma_period = price_ma_period

    def compute_money_flow_index(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14
    ) -> pd.Series:
        """Vectorized Money Flow Index (MFI) with T-1 lag."""
        # Shift all inputs by 1 to enforce T-1 lag
        high_lag = high.shift(1)
        low_lag = low.shift(1)
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        typical_price = (high_lag + low_lag + close_lag) / 3.0
        raw_money_flow = typical_price * volume_lag
        
        price_change = typical_price.diff()
        positive_flow = raw_money_flow.where(price_change > 0, 0.0)
        negative_flow = raw_money_flow.where(price_change < 0, 0.0)
        
        positive_mf = positive_flow.rolling(window=period).sum()
        negative_mf = negative_flow.rolling(window=period).sum()
        
        mfi = 100.0 - (100.0 / (1.0 + (positive_mf / negative_mf.replace(0, np.nan))))
        return mfi

    def compute_accumulation_distribution(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        """Vectorized Accumulation/Distribution Line with T-1 lag."""
        high_lag = high.shift(1)
        low_lag = low.shift(1)
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        clv = ((close_lag - low_lag) - (high_lag - close_lag)) / (high_lag - low_lag).replace(0, np.nan)
        ad = (clv * volume_lag).cumsum()
        return ad

    def compute_on_balance_volume(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Vectorized On-Balance Volume (OBV) with T-1 lag."""
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        obv_sign = np.sign(close_lag.diff()).fillna(0)
        obv = (obv_sign * volume_lag).cumsum()
        return obv

    def compute_volume_price_trend(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Vectorized Volume Price Trend (VPT) with T-1 lag."""
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        pct_change = close_lag.pct_change()
        vpt = (pct_change * volume_lag).cumsum()
        return vpt

    def compute_chaikin_money_flow(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20
    ) -> pd.Series:
        """Vectorized Chaikin Money Flow (CMF) with T-1 lag."""
        high_lag = high.shift(1)
        low_lag = low.shift(1)
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        mfv = ((close_lag - low_lag) - (high_lag - close_lag)) / (high_lag - low_lag).replace(0, np.nan) * volume_lag
        cmf = mfv.rolling(window=period).sum() / volume_lag.rolling(window=period).sum()
        return cmf

    def compute_volume_rate_of_change(self, volume: pd.Series, period: int = 12) -> pd.Series:
        """Vectorized Volume Rate of Change (VROC) with T-1 lag."""
        volume_lag = volume.shift(1)
        vroc = (volume_lag - volume_lag.shift(period)) / volume_lag.shift(period).replace(0, np.nan) * 100.0
        return vroc

    def compute_smart_money_divergence(
        self, close: pd.Series, volume: pd.Series, price_period: int = 20, volume_period: int = 20
    ) -> pd.Series:
        """
        Detect divergence between price and volume.
        High value = smart money accumulation (price down, volume up).
        """
        close_lag = close.shift(1)
        volume_lag = volume.shift(1)
        
        price_ma = close_lag.rolling(window=price_period).mean()
        volume_ma = volume_lag.rolling(window=volume_period).mean()
        
        price_norm = (close_lag - price_ma) / price_ma.replace(0, np.nan)
        volume_norm = (volume_lag - volume_ma) / volume_ma.replace(0, np.nan)
        
        divergence = volume_norm - price_norm
        return divergence
