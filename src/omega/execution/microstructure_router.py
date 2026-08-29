"""
Microstructure-Aware Router - Institutional Grade.

Dynamically adjusts TWAP/VWAP execution schedules based on real-time
L2 Order Book metrics like Order Book Imbalance (OBI) and Volume-Weighted Mid Price (VWMP).
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass
import logging


@dataclass
class L2OrderBook:
    """Snapshot of Level 2 Order Book."""
    timestamp: int
    symbol: str
    bids: List[tuple]  # [(price, volume), ...]
    asks: List[tuple]  # [(price, volume), ...]

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0

    @property
    def mid_price(self) -> float:
        if not self.bids or not self.asks:
            return 0.0
        return (self.best_bid + self.best_ask) / 2.0


class MicrostructureRouter:
    """
    Adaptive router that shifts execution urgency based on order book dynamics.
    Used by high-frequency/execution funds to minimize adverse selection.
    """

    def __init__(self, depth_levels: int = 5, urgency_multiplier: float = 1.5):
        """
        Args:
            depth_levels: How many levels of L2 book to use for OBI.
            urgency_multiplier: Max multiplier for speeding up/slowing down execution.
        """
        self.depth_levels = depth_levels
        self.urgency_multiplier = urgency_multiplier

    def calculate_obi(self, book: L2OrderBook) -> float:
        """
        Calculate Order Book Imbalance (OBI).
        Ranges from -1.0 (heavy sell pressure) to 1.0 (heavy buy pressure).
        """
        if not book.bids or not book.asks:
            return 0.0

        bids = book.bids[:self.depth_levels]
        asks = book.asks[:self.depth_levels]

        bid_vol = sum(vol for price, vol in bids)
        ask_vol = sum(vol for price, vol in asks)

        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0

        return float((bid_vol - ask_vol) / total_vol)

    def calculate_vwmp(self, book: L2OrderBook) -> float:
        """
        Calculate Volume-Weighted Mid Price (Micro-price).
        Useful for detecting if the true price is skewed towards bid or ask.
        """
        if not book.bids or not book.asks:
            return 0.0

        best_bid, bid_vol = book.bids[0]
        best_ask, ask_vol = book.asks[0]

        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return book.mid_price

        vwmp = (best_bid * ask_vol + best_ask * bid_vol) / total_vol
        return float(vwmp)

    def adjust_schedule(
        self,
        base_schedule: List[Dict[str, Any]],
        book: L2OrderBook,
        side: str
    ) -> List[Dict[str, Any]]:
        """
        Adjust execution quantities and limits based on OBI.

        Adverse Selection Detection (Drift Monitoring):
        - If side='buy' and microprice is drifting lower (DeltaVWMP << 0), it's a favorable
          price movement but could indicate adverse information. Slow down urgency to
          capture better prices.
        - If side='buy' and microprice is drifting higher (DeltaVWMP >> 0), we are being
          adversely selected. Speed up to avoid further slippage or pause to wait for revert.
        """
        if not base_schedule:
            return []

        obi = self.calculate_obi(book)
        vwmp = self.calculate_vwmp(book)

        # Adverse Selection Detection logic
        # Current implementation: if DeltaVWMP is adverse above threshold, apply penalty/bonus
        drift_factor = 1.0
        # For simplicity in this version, we use microprice vs midprice as a proxy for drift
        microprice_drift = (vwmp - book.mid_price) / book.mid_price if book.mid_price != 0 else 0

        # If buying and microprice is much higher than midprice (adverse), increase urgency
        if side.upper() == 'BUY':
            if microprice_drift > 0.0005:  # 5 bps adverse drift
                drift_factor = 1.2
            elif microprice_drift < -0.0005: # 5 bps favorable drift
                drift_factor = 0.8
        elif side.upper() == 'SELL':
            if microprice_drift < -0.0005: # adverse for seller
                drift_factor = 1.2
            elif microprice_drift > 0.0005: # favorable for seller
                drift_factor = 0.8

        urgency = 1.0
        if side.upper() == 'BUY':
            urgency += obi * (self.urgency_multiplier - 1.0)
        elif side.upper() == 'SELL':
            urgency -= obi * (self.urgency_multiplier - 1.0)

        # Combine OBI urgency with drift-based urgency
        urgency = urgency * drift_factor

        urgency = float(np.clip(urgency, 1.0 / self.urgency_multiplier, self.urgency_multiplier))

        adjusted_schedule = []
        for slice_order in base_schedule:
            adj = dict(slice_order)
            original_qty = adj.get("quantity", 0)
            adj["target_quantity"] = int(original_qty * urgency)
            adj["vwmp"] = vwmp
            adj["obi"] = obi
            adj["microprice_drift_bps"] = microprice_drift * 10000
            adjusted_schedule.append(adj)

        # Re-normalize to ensure total quantity doesn't change
        total_adjusted = sum(adj.get("target_quantity", 0) for adj in adjusted_schedule)
        total_original = sum(adj.get("quantity", 0) for adj in base_schedule)

        if total_adjusted > 0 and total_original > 0:
            factor = total_original / total_adjusted
            for adj in adjusted_schedule:
                # Maintain board-lot (100 shares) in VN market
                new_qty = int(adj["target_quantity"] * factor)
                new_qty = round(new_qty / 100) * 100
                adj["quantity"] = new_qty

        return adjusted_schedule

    def route_order(
        self,
        order: Dict[str, Any],
        execution_algo: str = "VWAP",
        duration_minutes: int = 60,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Simple routing stub for compatibility with SmartRouter.
        """
        qty = order.get("quantity", 0)
        side = order.get("side", "BUY")
        symbol = order.get("symbol", "")

        # Generate slices
        n_slices = max(1, duration_minutes // 5)
        slice_qty = qty // n_slices

        schedule = []
        for i in range(n_slices):
            schedule.append({
                "symbol": symbol,
                "side": side,
                "quantity": slice_qty,
                "time_offset": i * 5
            })
        return schedule

    def generate_depth_waterfall(
        self,
        symbol: str,
        mid_price: float,
        depth_levels: int = 10,
        spread_bps: float = 10.0,
        base_volume: float = 50000.0,
    ) -> Dict[str, Any]:
        """
        Generate 10-level Depth Waterfall and cumulative volume distributions.

        Institutional Microstructure Depth Model:
        - Bid & Ask price ladders with realistic Vietnamese tick step increments
        - Cumulative depth ladder and imbalance curve
        """
        if mid_price <= 0:
            mid_price = 50000.0  # Safe fallback VND

        tick_size = 50.0 if mid_price < 50000 else 100.0
        half_spread = (mid_price * (spread_bps / 20000.0))
        best_bid = np.floor((mid_price - half_spread) / tick_size) * tick_size
        best_ask = np.ceil((mid_price + half_spread) / tick_size) * tick_size
        if best_ask <= best_bid:
            best_ask = best_bid + tick_size

        bids = []
        asks = []
        cum_bid_vol = 0.0
        cum_ask_vol = 0.0

        for i in range(depth_levels):
            # Volume decays / clusters at outer levels
            decay_factor = 1.0 + (i * 0.15)
            bid_p = best_bid - (i * tick_size)
            ask_p = best_ask + (i * tick_size)

            # Deterministic volume shape based on symbol and level
            seed_offset = (hash(symbol) % 100) / 100.0
            bid_v = float(int((base_volume * (0.8 + 0.4 * np.sin(i + seed_offset)) * decay_factor) // 100) * 100)
            ask_v = float(int((base_volume * (0.8 + 0.4 * np.cos(i + seed_offset)) * decay_factor) // 100) * 100)

            cum_bid_vol += bid_v
            cum_ask_vol += ask_v

            bids.append({
                "level": i + 1,
                "price": float(bid_p),
                "volume": bid_v,
                "cumulative_volume": cum_bid_vol,
                "orders": int(max(1, int(bid_v // 500))),
            })
            asks.append({
                "level": i + 1,
                "price": float(ask_p),
                "volume": ask_v,
                "cumulative_volume": cum_ask_vol,
                "orders": int(max(1, int(ask_v // 500))),
            })

        actual_spread = float(best_ask - best_bid)
        actual_spread_bps = float((actual_spread / mid_price) * 10000) if mid_price > 0 else 0.0
        total_vol = cum_bid_vol + cum_ask_vol
        total_obi = float((cum_bid_vol - cum_ask_vol) / total_vol) if total_vol > 0 else 0.0

        return {
            "symbol": symbol.upper(),
            "depth_levels": depth_levels,
            "mid_price": float(mid_price),
            "spread": actual_spread,
            "spread_bps": actual_spread_bps,
            "total_bid_depth": cum_bid_vol,
            "total_ask_depth": cum_ask_vol,
            "obi": total_obi,
            "bids": bids,
            "asks": asks,
        }
