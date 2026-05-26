"""
Market Regime Filter - V21 Institutional
Detects market regimes (uptrend, downtrend, sideway) to gate trading signals.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class MarketRegime(Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAY = "sideway"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"


@dataclass
class RegimeReport:
    """Report from market regime detection."""
    regime: MarketRegime
    confidence: float        # 0-1
    ma_short: float
    ma_long: float
    volatility: float
    is_tradeable: bool       # Whether conditions allow trading


class MarketRegimeFilter:
    """Detect market regimes using moving averages + volatility.

    Method:
    - MA crossover: short MA vs long MA
    - Volatility regime: rolling vol vs vol threshold
    - Combine both for final regime classification
    """

    def __init__(
        self,
        ma_short: int = 20,
        ma_long: int = 60,
        vol_window: int = 20,
        high_vol_threshold: float = 0.03,  # 3% daily vol = high vol
        trend_threshold: float = 0.02      # 2% MA gap = trending
    ):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.vol_window = vol_window
        self.high_vol_threshold = high_vol_threshold
        self.trend_threshold = trend_threshold

    def detect(
        self,
        prices: np.ndarray,
        timestamps: Optional[np.ndarray] = None
    ) -> RegimeReport:
        """Detect current market regime.

        Args:
            prices: Price series (e.g., VN-Index)
            timestamps: Optional timestamps

        Returns:
            RegimeReport with regime classification
        """
        n = len(prices)
        if n < self.ma_long:
            return RegimeReport(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                ma_short=0.0,
                ma_long=0.0,
                volatility=0.0,
                is_tradeable=True  # Default to tradeable if insufficient data
            )

        # Compute MAs
        ma_s = np.mean(prices[-self.ma_short:])
        ma_l = np.mean(prices[-self.ma_long:])
        current_price = prices[-1]

        # Compute rolling volatility
        returns = np.diff(prices[-self.vol_window:]) / prices[-self.vol_window:-1]
        volatility = np.std(returns) if len(returns) > 1 else 0.0

        # Trend detection
        ma_gap = (ma_s - ma_l) / (ma_l + 1e-10)
        # Guard against zero/negative threshold
        trend_th = max(self.trend_threshold, 1e-8)

        # Regime classification
        if volatility > self.high_vol_threshold:
            regime = MarketRegime.HIGH_VOL
            confidence = min(1.0, volatility / max(self.high_vol_threshold * 2, 1e-8))
            is_tradeable = False  # Avoid trading in high vol

        elif ma_gap > trend_th:
            regime = MarketRegime.UPTREND
            confidence = min(1.0, ma_gap / (trend_th * 2))
            is_tradeable = True

        elif ma_gap < -trend_th:
            regime = MarketRegime.DOWNTREND
            confidence = min(1.0, abs(ma_gap) / (trend_th * 2))
            is_tradeable = False  # Long-only: avoid downtrend

        else:
            regime = MarketRegime.SIDEWAY
            confidence = max(0.0, 1.0 - abs(ma_gap) / trend_th)
            is_tradeable = True  # Sideway: can still trade on signal strength

        return RegimeReport(
            regime=regime,
            confidence=confidence,
            ma_short=ma_s,
            ma_long=ma_l,
            volatility=volatility,
            is_tradeable=is_tradeable
        )

    def is_tradeable(self, prices: np.ndarray) -> bool:
        """Quick check if current regime allows trading.

        Args:
            prices: Price series

        Returns:
            True if regime is tradeable
        """
        report = self.detect(prices)
        return report.is_tradeable
