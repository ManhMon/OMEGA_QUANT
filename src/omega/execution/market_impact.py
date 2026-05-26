"""
Market Impact Model for V21 Institutional Grade.

Implements:
- Almgren-Chriss square-root impact model
- Implementation shortfall calculation
- Adverse selection detection
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Optional


class MarketImpactModel:
    """
    Market impact modeling for execution quality analysis.
    
    Uses Almgren-Chriss square-root model adapted for VN market microstructure.
    """
    
    def __init__(self, impact_coefficient: float = 0.2):
        self.impact_coefficient = impact_coefficient
        
    def calculate_impact_bps(
        self,
        order_size: float,
        average_daily_volume: float,
        volatility: float = 0.02,
        participation_rate: float = 0.1
    ) -> float:
        """
        Calculate estimated market impact in basis points (bps).
        
        Formula: impact = gamma * sigma * sqrt(Q / V)
        where:
        - gamma = impact coefficient (typically 0.1-0.3 for liquid markets)
        - sigma = volatility
        - Q = order size
        - V = daily volume
        """
        if average_daily_volume <= 0:
            return 0.0
            
        normalized_size = order_size / average_daily_volume
        
        # Square-root impact model (Almgren-Chriss)
        impact = self.impact_coefficient * volatility * np.sqrt(normalized_size)
        
        # Convert to basis points (multiply by 10000)
        impact_bps = impact * 10000
        
        return float(impact_bps)
        
    def calculate_implementation_shortfall(
        self,
        order_size: float,
        average_daily_volume: float,
        volatility: float,
        arrival_price: float,
        execution_price: float,
        participation_rate: float = 0.1
    ) -> Dict[str, float]:
        """
        Calculate implementation shortfall components.
        
        Returns:
            {
                "realized_spread": execution - arrival (direction-aware),
                "market_impact": estimated impact cost,
                "timing_risk": difference between expected and realized,
                "total_cost": total implementation shortfall (bps)
            }
        """
        # Market impact estimate
        impact = self.calculate_impact_bps(
            order_size=order_size,
            average_daily_volume=average_daily_volume,
            volatility=volatility,
            participation_rate=participation_rate
        )
        
        # Realized spread (arrival vs execution)
        # Positive = buy higher, sell lower = cost
        # Negative = buy lower, sell higher = benefit
        if arrival_price <= 0:
            realized_spread = 0.0
        else:
            realized_spread = ((execution_price - arrival_price) / arrival_price) * 10000
        
        # Timing risk = realized spread - market impact
        # (unexpected move against us)
        timing_risk = realized_spread - impact
        
        # Total: includes impact + realized spread
        total_cost = realized_spread + impact
        
        return {
            "realized_spread": float(realized_spread),
            "market_impact": float(impact),
            "timing_risk": float(timing_risk),
            "total_cost": float(total_cost)
        }
        
    def detect_adverse_selection(
        self,
        order_side: str,  # "BUY" or "SELL"
        execution_price: float,
        arrival_price: float,
        volume_imbalance: float  # -1 to 1 (sell pressure to buy pressure)
    ) -> str:
        """
        Detect if execution suffered from adverse selection.
        
        Returns:
            "none": No adverse selection detected
            "possible": Possible adverse selection
            "likely": Likely adverse selection
        """
        if order_side.upper() == "BUY":
            # Adverse selection for buys = price moved up during execution
            price_move = (execution_price - arrival_price) / arrival_price if arrival_price > 0 else 0.0
            if volume_imbalance < -0.3 and price_move > 0.002:
                return "likely"
            elif volume_imbalance < 0 and price_move > 0:
                return "possible"
        else:  # SELL
            # Adverse selection for sells = price moved down
            price_move = (arrival_price - execution_price) / arrival_price if arrival_price > 0 else 0.0
            if volume_imbalance > 0.3 and price_move > 0.002:
                return "likely"
            elif volume_imbalance > 0 and price_move > 0:
                return "possible"
                
        return "none"
