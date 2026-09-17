"""
OMEGA_QUANT Order Book Analyzer (Layer 03)
Phase 4.3: Market Microstructure Analysis

Analyzes order book data to compute indicators like OBI, VWMP,
and determine market pressure for optimal execution timing.

Author: Backend Engineer (Role 09)
Date: 2026-05-18
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarketDepth:
    """Market depth at a single price level."""
    price: float
    volume: int
    orders: int = 1  # Number of orders at this level


@dataclass
class OrderBookSnapshot:
    """Complete order book snapshot."""
    symbol: str
    timestamp: float
    bid_levels: List[MarketDepth]
    ask_levels: List[MarketDepth]
    mid_price: float
    spread_bps: float


class OrderBookAnalyzer:
    """
    Analyzes order book data for execution optimization.

    Features:
    - Order Book Imbalance (OBI) calculation
    - Volume-Weighted Mid Price (VWMP)
    - Market pressure detection
    - Liquidity assessment
    - Slippage estimation
    - Timing optimization
    """

    def __init__(self, lookback: int = 5):
        """
        Initialize OrderBookAnalyzer.

        Args:
            lookback: Number of past data points for trend analysis
        """
        self.lookback = lookback
        self.obi_history: List[float] = []
        self.vwmp_history: List[float] = []
        logger.info("Initialized OrderBookAnalyzer")

    def compute_obi(self, bid_levels: List[Dict], ask_levels: List[Dict]) -> float:
        """
        Compute Order Book Imbalance (OBI).

        OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)

        Args:
            bid_levels: List of bid levels with 'price' and 'volume'
            ask_levels: List of ask levels with 'price' and 'volume'

        Returns:
            OBI value from -1.0 to 1.0
        """
        bid_vol = sum(level.get('volume', 0) for level in bid_levels)
        ask_vol = sum(level.get('volume', 0) for level in ask_levels)

        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0

        obi = (bid_vol - ask_vol) / total_vol
        self.obi_history.append(obi)

        # Keep only lookback period
        if len(self.obi_history) > self.lookback:
            self.obi_history = self.obi_history[-self.lookback:]

        return obi

    def compute_vwmp(self, bid_levels: List[Dict], ask_levels: List[Dict]) -> float:
        """
        Compute Volume-Weighted Mid Price (VWMP).

        VWMP = (Sum(bid_price * bid_volume) + Sum(ask_price * ask_volume)) / (Sum(bid_volume) + Sum(ask_volume))

        Args:
            bid_levels: List of bid levels
            ask_levels: List of ask levels

        Returns:
            VWMP price
        """
        total_price_vol = 0.0
        total_vol = 0.0

        for level in bid_levels:
            vol = level.get('volume', 0)
            total_price_vol += level.get('price', 0) * vol
            total_vol += vol

        for level in ask_levels:
            vol = level.get('volume', 0)
            total_price_vol += level.get('price', 0) * vol
            total_vol += vol

        if total_vol == 0:
            return 0.0

        vwmp = total_price_vol / total_vol
        self.vwmp_history.append(vwmp)

        if len(self.vwmp_history) > self.lookback:
            self.vwmp_history = self.vwmp_history[-self.lookback:]

        return vwmp

    def get_pressure(self, bid_levels: List[Dict], ask_levels: List[Dict]) -> str:
        """
        Determine market pressure based on OBI.

        Args:
            bid_levels: Bid levels from order book
            ask_levels: Ask levels from order book

        Returns:
            'BUY' if OBI > 0.1, 'SELL' if OBI < -0.1, 'NEUTRAL' otherwise
        """
        obi = self.compute_obi(bid_levels, ask_levels)

        if obi > 0.1:
            return 'BUY'
        elif obi < -0.1:
            return 'SELL'
        else:
            return 'NEUTRAL'

    def assess_liquidity(
        self,
        bid_levels: List[Dict],
        ask_levels: List[Dict],
        target_quantity: int
    ) -> Dict[str, Any]:
        """
        Assess liquidity for target order size.

        Args:
            bid_levels: Bid levels
            ask_levels: Ask levels
            target_quantity: Target order quantity

        Returns:
            Liquidity assessment dict
        """
        # Calculate available volume at each level
        bid_depth = sum(level.get('volume', 0) for level in bid_levels)
        ask_depth = sum(level.get('volume', 0) for level in ask_levels)

        # Determine which side we're trading on
        if target_quantity > 0:  # BUY
            available = ask_depth
            side = 'ask'
        else:  # SELL
            available = bid_depth
            side = 'bid'

        # Liquidity rating
        target_qty_abs = abs(target_quantity)
        if available >= target_qty_abs * 10:
            rating = 'EXCELLENT'
            slippage_bps = 0.5
        elif available >= target_qty_abs * 5:
            rating = 'GOOD'
            slippage_bps = 1.0
        elif available >= target_qty_abs * 2:
            rating = 'MODERATE'
            slippage_bps = 2.0
        elif available >= target_qty_abs:
            rating = 'LIMITED'
            slippage_bps = 3.5
        else:
            rating = 'POOR'
            slippage_bps = 5.0

        return {
            'side': side,
            'available_volume': available,
            'target_quantity': target_qty_abs,
            'rating': rating,
            'estimated_slippage_bps': slippage_bps,
            'can_execute_immediately': available >= target_qty_abs
        }

    def estimate_slippage(
        self,
        order_size: int,
        avg_daily_volume: int,
        market_depth: Dict[str, float],
        historical_slippage_bps: float = 1.5
    ) -> float:
        """
        Estimate execution slippage.

        Args:
            order_size: Order size in shares
            avg_daily_volume: Average daily volume in shares
            market_depth: Current market depth {bid: price, ask: price}
            historical_slippage_bps: Historical average slippage

        Returns:
            Estimated slippage in bps
        """
        # Order size impact
        if avg_daily_volume > 0:
            participation_rate = order_size / avg_daily_volume
        else:
            participation_rate = 0.0

        # Volume impact (non-linear)
        if participation_rate < 0.01:
            volume_factor = 1.0
        elif participation_rate < 0.05:
            volume_factor = 1.5
        elif participation_rate < 0.10:
            volume_factor = 2.5
        else:
            volume_factor = 4.0

        # Market depth impact
        spread_bps = market_depth.get('spread_bps', 1.0)

        # Total estimated slippage
        estimated = (
            historical_slippage_bps * volume_factor +
            spread_bps * 0.5
        )

        return max(estimated, 0.5)  # Minimum 0.5 bps

    def compute_vpin_from_ohlcv(
        self,
        df: pd.DataFrame,
        bucket_volume: Optional[float] = None,
        n_buckets: int = 20,
    ) -> Dict[str, Any]:
        """
        Compute Volume-Synchronized Probability of Toxicity (VPIN) from OHLCV bars.

        Uses BVC (Bulk Volume Classification) with standard normal CDF of price changes:
        V_buy = Volume * NormalCDF(delta_price / sigma)
        V_sell = Volume * (1 - NormalCDF(delta_price / sigma))

        VPIN = sum(|V_buy - V_sell|) / (N * V_bucket)
        """
        if df.empty or len(df) < 5:
            return {
                "vpin": 0.0,
                "toxicity_level": "LOW",
                "bucket_volume": 0.0,
                "n_buckets": n_buckets,
                "history": [],
                "current_imbalance": 0.0,
            }

        closes = df["close"].to_numpy(dtype=np.float64)
        volumes = df["volume"].to_numpy(dtype=np.float64)
        dates = df["date"].astype(str).tolist() if "date" in df.columns else [str(i) for i in range(len(df))]

        # Price changes and volatility
        delta_p = np.diff(closes, prepend=closes[0])
        std_p = np.std(delta_p) if np.std(delta_p) > 1e-8 else 1.0

        # Bulk volume classification (vectorized approximation of normal CDF)
        # Using erf approximation for fast standard normal CDF
        from scipy.special import erf
        z_scores = delta_p / (std_p * np.sqrt(2.0))
        buy_probs = 0.5 * (1.0 + erf(z_scores))
        buy_probs = np.clip(buy_probs, 0.0, 1.0)

        buy_volumes = volumes * buy_probs
        sell_volumes = volumes * (1.0 - buy_probs)

        total_vol = float(np.sum(volumes))
        if total_vol <= 0:
            return {
                "vpin": 0.0,
                "toxicity_level": "LOW",
                "bucket_volume": 0.0,
                "n_buckets": n_buckets,
                "history": [],
                "current_imbalance": 0.0,
            }

        # Determine bucket size if not provided
        if bucket_volume is None or bucket_volume <= 0:
            bucket_volume = max(100.0, total_vol / max(1, n_buckets * 2))

        # Compute rolling VPIN over buckets
        abs_imbalances = np.abs(buy_volumes - sell_volumes)
        vpin_series = []

        # Vectorized rolling sum with window
        window = min(n_buckets, len(volumes))
        if window > 0:
            rolling_imb = pd.Series(abs_imbalances).rolling(window=window, min_periods=1).sum().to_numpy()
            rolling_tot = pd.Series(volumes).rolling(window=window, min_periods=1).sum().to_numpy()

            with np.errstate(divide="ignore", invalid="ignore"):
                vpin_vals = np.where(rolling_tot > 0, rolling_imb / rolling_tot, 0.0)
                vpin_vals = np.nan_to_num(vpin_vals, nan=0.0, posinf=0.0, neginf=0.0)

            for i in range(len(df)):
                vpin_series.append({
                    "time": dates[i],
                    "vpin": float(vpin_vals[i]),
                    "buy_volume": float(buy_volumes[i]),
                    "sell_volume": float(sell_volumes[i]),
                    "price": float(closes[i]),
                })

        current_vpin = float(vpin_series[-1]["vpin"]) if vpin_series else 0.0

        if current_vpin > 0.55:
            toxicity_level = "TOXIC"
        elif current_vpin > 0.40:
            toxicity_level = "HIGH"
        elif current_vpin > 0.25:
            toxicity_level = "MODERATE"
        else:
            toxicity_level = "LOW"

        return {
            "vpin": current_vpin,
            "toxicity_level": toxicity_level,
            "bucket_volume": float(bucket_volume),
            "n_buckets": int(n_buckets),
            "history": vpin_series[-50:],
            "current_imbalance": float(buy_volumes[-1] - sell_volumes[-1]) if len(buy_volumes) > 0 else 0.0,
        }

    def optimize_timing(
        self,
        current_time: str,
        market_volatility: float,
        is_market_open: bool = True
    ) -> Dict[str, Any]:
        """
        Optimize execution timing.

        Args:
            current_time: Current time (HH:MM)
            market_volatility: Current market volatility
            is_market_open: Whether market is open

        Returns:
            Timing optimization recommendations
        """
        # Market hours impact
        hour = int(current_time.split(':')[0]) if ':' in current_time else 10

        if not is_market_open:
            timing = 'AFTER_HOURS'
            slippage_factor = 2.0
        elif hour == 9 or hour == 14:  # Open/Close
            timing = 'VOLATILE'
            slippage_factor = 1.5
        elif 10 <= hour <= 13:
            timing = 'STABLE'
            slippage_factor = 1.0
        else:
            timing = 'MODERATE'
            slippage_factor = 1.2

        # Volatility impact
        if market_volatility < 0.01:
            vol_rating = 'LOW'
            vol_factor = 0.8
        elif market_volatility < 0.02:
            vol_rating = 'MODERATE'
            vol_factor = 1.0
        else:
            vol_rating = 'HIGH'
            vol_factor = 1.3

        return {
            'timing': timing,
            'volatility_rating': vol_rating,
            'recommended_participation_rate': 0.15 * vol_factor,  # 15% of ADV
            'estimated_slippage_factor': slippage_factor * vol_factor,
            'optimal_start_time': '10:00' if timing == 'VOLATILE' else '09:30'
        }

    def get_order_book_snapshot(
        self,
        bid_levels: List[Dict],
        ask_levels: List[Dict],
        symbol: str,
        timestamp: float
    ) -> OrderBookSnapshot:
        """
        Create complete order book snapshot.

        Args:
            bid_levels: Bid levels
            ask_levels: Ask levels
            symbol: Stock symbol
            timestamp: Snapshot timestamp

        Returns:
            OrderBookSnapshot
        """
        # Calculate mid price
        if ask_levels and bid_levels:
            best_bid = max(level.get('price', 0) for level in bid_levels)
            best_ask = min(level.get('price', 0) for level in ask_levels)
            mid_price = (best_bid + best_ask) / 2
            spread_bps = (best_ask - best_bid) / mid_price * 10000 if mid_price > 0 else 0
        else:
            mid_price = 0
            spread_bps = 0

        return OrderBookSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            bid_levels=[MarketDepth(**level) if isinstance(level, dict) else level for level in bid_levels],
            ask_levels=[MarketDepth(**level) if isinstance(level, dict) else level for level in ask_levels],
            mid_price=mid_price,
            spread_bps=spread_bps
        )
