"""
Layer 03: Execution Engine - Transaction Cost Estimator
Fixed: Pure round-trip estimation for signal validation.
"""
import numpy as np

class CostEstimator:
    def __init__(self, commission=0.0015, tax=0.0010, impact_coeff=0.1, spread_bps=10.0):
        self.commission = commission
        self.tax = tax
        self.impact_coeff = impact_coeff
        self.spread_bps = spread_bps
        
    def estimate_round_trip_cost(self, order_value, adv_value, volatility=0.02):
        """
        Calculates one single round-trip cost (Buy + Sell).
        Tax is only 0.1% once (at SELL side usually, or BUY in some contexts).
        Standard VN: Buy (0.15% fee) + Sell (0.15% fee + 0.1% tax).
        """
        if adv_value <= 0: return 0.01
        
        # 1. Fees: 0.15% x 2 = 0.30%
        fees = self.commission * 2
        # 2. Tax: 0.1% (Standard VN Sell Tax)
        tax = self.tax
        # 3. Spread: 10bps x 2 = 0.20%
        spread = (self.spread_bps / 10000) * 2
        # 4. Impact (Avg of buy/sell impact)
        participation = min(order_value / adv_value, 1.0)
        impact = self.impact_coeff * volatility * np.sqrt(participation) * 2
        
        return fees + tax + spread + impact
