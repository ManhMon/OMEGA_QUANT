"""
OMEGA_QUANT Regime Detector
Detects market regime (bull/bear/sideways) and adjusts alpha weights accordingly.

Strategy:
- Bull: favor momentum, increase exposure
- Bear: favor mean-reversion, reduce exposure, tighten risk
- Sideways: balanced, favor low-vol premium

Signals:
- MA cross (50/200 day)
- Volatility regime (realized vol vs long-term)
- Market breadth (% stocks above MA20)
- Drawdown state

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All indicators use only past data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


@dataclass
class RegimeConfig:
    """Configuration for regime detection."""
    ma_short: int = 50
    ma_long: int = 200
    vol_short: int = 20
    vol_long: int = 60
    breadth_window: int = 20
    dd_threshold: float = -0.10  # -10% drawdown = bear
    vol_expansion_threshold: float = 1.5  # vol_short/vol_long > 1.5 = high vol


@dataclass
class RegimeState:
    """Current regime state with confidence."""
    regime: MarketRegime
    confidence: float  # 0-1
    signals: Dict[str, float]
    exposure_multiplier: float  # 0.3 (bear) to 1.2 (bull)
    timestamp: Optional[str] = None


class RegimeDetector:
    """
    Detect market regime from price data.
    Uses ensemble of 4 signals for robust detection.
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config = config or RegimeConfig()

    def detect(self, market_prices: pd.Series) -> RegimeState:
        """
        Detect current regime from market index/portfolio prices.

        Args:
            market_prices: Time series of market prices (e.g., VN-Index proxy)

        Returns:
            RegimeState with regime, confidence, and exposure multiplier.
        """
        if len(market_prices) < self.config.ma_long + 10:
            return RegimeState(
                regime=MarketRegime.SIDEWAYS, confidence=0.5,
                signals={}, exposure_multiplier=1.0,
            )

        signals = {}

        # Signal 1: MA Cross (trend)
        ma_short = market_prices.rolling(self.config.ma_short).mean()
        ma_long = market_prices.rolling(self.config.ma_long).mean()
        ma_signal = (ma_short.iloc[-1] - ma_long.iloc[-1]) / ma_long.iloc[-1]
        signals['ma_cross'] = float(ma_signal)

        # Signal 2: Volatility regime
        returns = market_prices.pct_change()
        vol_short = returns.rolling(self.config.vol_short).std().iloc[-1]
        vol_long = returns.rolling(self.config.vol_long).std().iloc[-1]
        vol_ratio = vol_short / vol_long if vol_long > 0 else 1.0
        signals['vol_ratio'] = float(vol_ratio)

        # Signal 3: Drawdown state
        running_max = market_prices.expanding().max()
        current_dd = (market_prices.iloc[-1] - running_max.iloc[-1]) / running_max.iloc[-1]
        signals['drawdown'] = float(current_dd)

        # Signal 4: Momentum (20-day return)
        ret_20d = market_prices.pct_change(20).iloc[-1]
        signals['momentum_20d'] = float(ret_20d)

        # Regime classification
        bull_score = 0.0
        bear_score = 0.0

        # MA cross
        if ma_signal > 0.02:
            bull_score += 0.3
        elif ma_signal < -0.02:
            bear_score += 0.3

        # Volatility
        if vol_ratio > self.config.vol_expansion_threshold:
            bear_score += 0.2
        elif vol_ratio < 0.8:
            bull_score += 0.2

        # Drawdown
        if current_dd < self.config.dd_threshold:
            bear_score += 0.3
        elif current_dd > -0.03:
            bull_score += 0.2

        # Momentum
        if ret_20d > 0.05:
            bull_score += 0.2
        elif ret_20d < -0.05:
            bear_score += 0.2

        # Determine regime
        if bull_score > bear_score and bull_score > 0.4:
            regime = MarketRegime.BULL
            confidence = min(bull_score, 1.0)
            exposure = 1.0 + 0.2 * confidence  # 1.0 - 1.2x
        elif bear_score > bull_score and bear_score > 0.4:
            regime = MarketRegime.BEAR
            confidence = min(bear_score, 1.0)
            exposure = max(0.3, 1.0 - 0.7 * confidence)  # 0.3 - 1.0x
        else:
            regime = MarketRegime.SIDEWAYS
            confidence = 1.0 - bull_score - bear_score
            exposure = 0.8  # Slightly reduced in uncertain regime

        return RegimeState(
            regime=regime,
            confidence=confidence,
            signals=signals,
            exposure_multiplier=exposure,
        )

    def detect_rolling(self, market_prices: pd.Series) -> pd.DataFrame:
        """
        Detect regime for each date (rolling). PIT-safe.

        Returns:
            DataFrame with columns: regime, confidence, exposure_multiplier
        """
        results = []
        min_len = self.config.ma_long + 10

        for i in range(min_len, len(market_prices)):
            window = market_prices.iloc[:i+1]
            state = self.detect(window)
            results.append({
                'date': market_prices.index[i],
                'regime': state.regime.value,
                'confidence': state.confidence,
                'exposure': state.exposure_multiplier,
                'ma_cross': state.signals.get('ma_cross', 0),
                'vol_ratio': state.signals.get('vol_ratio', 1),
                'drawdown': state.signals.get('drawdown', 0),
            })

        return pd.DataFrame(results).set_index('date')

    def adjust_weights(
        self, weights: pd.DataFrame, regime_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Adjust portfolio weights based on regime.

        Args:
            weights: Original weights (dates x symbols)
            regime_df: Regime DataFrame from detect_rolling()

        Returns:
            Adjusted weights with exposure scaling.
        """
        adjusted = weights.copy()
        common_dates = adjusted.index.intersection(regime_df.index)

        for date in common_dates:
            exposure = regime_df.loc[date, 'exposure']
            adjusted.loc[date] = adjusted.loc[date] * exposure

        # Re-normalize (exposure < 1 means partial cash allocation)
        row_sums = adjusted.sum(axis=1).replace(0, 1.0)
        # Don't re-normalize if exposure < 1 (keep cash)
        # Only re-normalize if exposure > 1 (leverage not allowed, cap at 1)
        for date in common_dates:
            rs = adjusted.loc[date].sum()
            if rs > 1.0:
                adjusted.loc[date] = adjusted.loc[date] / rs

        return adjusted
