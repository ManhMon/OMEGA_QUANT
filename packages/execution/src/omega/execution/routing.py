import math
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Order:
    symbol: str
    quantity: int
    side: str
    target_pov: float = 0.1  # Target participation rate (e.g., 10%)

@dataclass
class OrderChunk:
    symbol: str
    quantity: int
    side: str
    time_bucket: int  # Abstract time slice (e.g., hour of day)

class POVRoutingEngine:
    def __init__(self, min_lot_size: int = 100):
        self.min_lot_size = min_lot_size
        self.volume_profiles: Dict[str, List[float]] = {}
        
    def load_historical_profile(self, symbol: str, profile_weights: List[float]):
        """Load normalized volume distribution across time buckets."""
        total = sum(profile_weights)
        if not math.isclose(total, 1.0, rel_tol=1e-5):
            normalized = [w / total for w in profile_weights]
        else:
            normalized = profile_weights
        self.volume_profiles[symbol] = normalized

    def route_order(self, order: Order, historical_daily_volume: int) -> List[OrderChunk]:
        """Split order according to historical POV distribution."""
        if historical_daily_volume <= 0:
            raise ValueError("Historical volume must be positive")
            
        if order.symbol not in self.volume_profiles:
            # Fallback to even distribution across 6 time buckets
            self.load_historical_profile(order.symbol, [1/6] * 6)
            
        profile = self.volume_profiles[order.symbol]
        target_quantity = order.quantity
        
        chunks = []
        allocated = 0
        
        for i, weight in enumerate(profile):
            # Maximum we are allowed to participate in this bucket
            bucket_volume = historical_daily_volume * weight
            max_participate = bucket_volume * order.target_pov
            
            # We want to fill proportionally, but capped by max_participate
            chunk_qty = min(target_quantity * weight, max_participate)
            
            # Round to minimum lot size
            rounded_qty = (int(chunk_qty) // self.min_lot_size) * self.min_lot_size
            
            # Adjust if it's the last bucket
            if i == len(profile) - 1:
                remaining = target_quantity - allocated
                # Do not exceed remaining OR max_participate
                adjusted_remaining = min(remaining, max_participate)
                rounded_remaining = (int(adjusted_remaining) // self.min_lot_size) * self.min_lot_size
                rounded_qty = rounded_remaining
                
            if rounded_qty > 0:
                chunks.append(OrderChunk(
                    symbol=order.symbol,
                    quantity=rounded_qty,
                    side=order.side,
                    time_bucket=i
                ))
                allocated += rounded_qty
                
        return chunks