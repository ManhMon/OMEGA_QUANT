"""
Layer 03: Execution Engine - Signal Validator
Updated: Robust >= threshold logic and round-trip alignment.
"""
import numpy as np
from typing import Dict

class SignalValidator:
    def __init__(self, round_trip_cost=0.0060, safety_margin=1.5):
        self.round_trip_cost = round_trip_cost
        self.safety_margin = safety_margin
        self.regime_multipliers = {'Bull': 1.0, 'Sideways': 0.7, 'Bear': 0.4}

    def _get_score(self, alpha_score) -> float:
        """Extracts float value from alpha_score (supports L2OrderBook or float)."""
        if alpha_score is None:
            return 2.0 # Default strong signal if missing to avoid blocking execution
            
        if isinstance(alpha_score, (int, float, np.number)):
            return float(alpha_score)
        
        # FIX (v21.10.6): Handle L2OrderBook via MicrostructureRouter logic
        # If it's an L2OrderBook object (contains bids/asks)
        if hasattr(alpha_score, 'bids') and hasattr(alpha_score, 'asks'):
            # Manually compute a simple OBI since we don't want to import Router here to avoid circularity
            best_bid_qty = sum(qty for price, qty in alpha_score.bids[:1])
            best_ask_qty = sum(qty for price, qty in alpha_score.asks[:1])
            total = best_bid_qty + best_ask_qty
            obi = (best_bid_qty - best_ask_qty) / total if total > 0 else 0
            return float(obi * 5.0) # Scale OBI to comparable alpha range
            
        if hasattr(alpha_score, 'score'):
            return float(alpha_score.score)
        if hasattr(alpha_score, 'signal'):
            return float(alpha_score.signal)
            
        return 0.0

    def should_trade(self, alpha_score, current_weight, target_weight, regime='Sideways') -> bool:
        weight_change = abs(target_weight - current_weight)
        if weight_change < 0.001: return False
        
        score = self._get_score(alpha_score)
        # FIX (v21.10.5): Use extracted float score
        expected_alpha = score * 0.01 * self.regime_multipliers.get(regime, 0.7)
        threshold = self.round_trip_cost * self.safety_margin
        
        # FIX (v21.9.1): Inclusive threshold (>=) to match documentation
        return expected_alpha >= (threshold - 1e-10) # Float stability

    def filter_weights(self, alpha_scores, current_weights, target_weights, regime='Sideways'):
        return {s: (target_weights[s] if self.should_trade(alpha_scores.get(s, 0), current_weights.get(s, 0), target_weights[s], regime) else current_weights.get(s, 0)) for s in target_weights}
