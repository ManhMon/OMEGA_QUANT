"""
Transaction Cost Model - V21 Institutional
Models slippage, commission, spread, and market impact.
"""

from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np


@dataclass
class CostEstimate:
    """Transaction cost breakdown."""
    commission: float = 0.0
    slippage: float = 0.0
    spread: float = 0.0
    market_impact: float = 0.0
    total_cost: float = 0.0
    cost_bps: float = 0.0  # Basis points


class TransactionCostModel:
    """Models transaction costs for VN market.
    
    Components:
    - Commission: Broker fee (VN ~0.1%)
    - Slippage: Price slippage based on order size
    - Bid-Ask Spread: Spread cost
    - Market Impact: Impact of large orders
    """
    
    def __init__(
        self,
        commission_rate: float = 0.001,  # 0.1% VN
        impact_coefficient: float = 0.1,   # Impact coefficient
        avg_spread_bps: float = 10.0       # 10 bps typical VN
    ):
        """
        Validate inputs.
        """
        if not 0 <= commission_rate <= 1:
            raise ValueError(f"commission_rate must be between 0 and 1, got {commission_rate}")
        if impact_coefficient < 0:
            raise ValueError(f"impact_coefficient must be non-negative, got {impact_coefficient}")
        if not 0 <= avg_spread_bps <= 10000:
            raise ValueError(f"avg_spread_bps must be between 0 and 10000 bps, got {avg_spread_bps}")
        self.commission_rate = commission_rate
        self.impact_coefficient = impact_coefficient
        self.avg_spread_bps = avg_spread_bps
    
    def estimate_cost(
        self,
        symbol: str,
        order_value: float,          # Notional value in VNĐ
        adv_value: float,            # Average Daily Value in VNĐ
        price: float,                # Execution price
        side: str = "BUY"            # BUY or SELL
    ) -> CostEstimate:
        """Estimate total transaction cost.
        
        Args:
            symbol: Stock symbol
            order_value: Notional value of order
            adv_value: Average daily value (20-day)
            price: Execution price
            side: BUY or SELL
            
        Returns:
            CostEstimate with breakdown
        """
        # 1. Commission
        commission = order_value * self.commission_rate
        
        # 2. Slippage (proportional to order size relative to ADV)
        participation_rate = order_value / (adv_value + 1e-10)
        slippage_bps = 5.0 * participation_rate  # Simple linear model
        slippage = order_value * (slippage_bps / 10000)
        
        # 3. Bid-Ask Spread
        spread_cost = order_value * (self.avg_spread_bps / 10000)
        
        # 4. Market Impact (square root model)
        # impact = coefficient * sqrt(order_size/ADV) * price
        if adv_value > 0:
            impact_factor = self.impact_coefficient * np.sqrt(participation_rate)
            market_impact = order_value * impact_factor / 100
        else:
            market_impact = 0.0
        
        # Total
        total_cost = commission + slippage + spread_cost + market_impact
        cost_bps = (total_cost / order_value * 10000) if order_value > 0 else 0.0
        
        return CostEstimate(
            commission=commission,
            slippage=slippage,
            spread=spread_cost,
            market_impact=market_impact,
            total_cost=total_cost,
            cost_bps=cost_bps
        )
    
    def adjust_position_for_cost(
        self,
        target_weight: float,
        total_capital: float,
        cost_estimate: CostEstimate,
        min_weight: float = 0.01
    ) -> float:
        """Adjust target position to account for transaction costs.
        
        Args:
            target_weight: Original target weight (0-1)
            total_capital: Total capital
            cost_estimate: Estimated transaction cost
            min_weight: Minimum position weight
            
        Returns:
            Adjusted position weight
        """
        # Reduce weight if cost is too high relative to expected return
        cost_bps = cost_estimate.cost_bps
        
        if cost_bps > 50:  # More than 50 bps cost
            # Reduce position significantly
            adjustment = min(0.5, cost_bps / 200)
            adjusted = target_weight * (1 - adjustment)
        else:
            adjusted = target_weight
        
        return max(min_weight, adjusted)
    
    def calculate_break_even_return(
        self,
        cost_estimate: CostEstimate
    ) -> float:
        """Calculate break-even return to cover transaction costs.
        
        Args:
            cost_estimate: Transaction cost estimate
            
        Returns:
            Break-even return (as decimal, e.g., 0.001 = 0.1%)
        """
        # Round-trip cost (buy + sell)
        round_trip_cost = cost_estimate.cost_bps * 2 / 10000
        return round_trip_cost

# Aliases for backward compatibility
VNTransactionCostModel = TransactionCostModel

@dataclass
class TransactionCostConfig:
    commission_rate: float = 0.001
    impact_coefficient: float = 0.1
    avg_spread_bps: float = 10.0
