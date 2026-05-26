"""
Conditional Value-at-Risk (CVaR) for V21 Institutional Grade.

Implements:
- CVaR (Expected Shortfall) calculation
- Tail risk estimation (z-score, historical simulation)
- Risk concentration detection (symbols/sectors)
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple


class CVaRManager:
    """
    Manager for Conditional Value-at-Risk (CVaR).
    
    CVaR is the average of losses beyond the VaR threshold at a given confidence level.
    """
    
    def __init__(self, confidence: float = 0.95, lookback_days: int = 252):
        self.confidence = confidence
        self.lookback_days = lookback_days
        self.history: List[float] = []
        
    def calculate_cvar(self, returns: List[float]) -> float:
        """
        Calculate CVaR using historical simulation.
        
        Args:
            returns: List of portfolio returns
            
        Returns:
            CVaR (Expected Shortfall) value (absolute loss)
        """
        if not returns:
            return 0.0
            
        # Use only specified lookback period
        window = min(len(returns), self.lookback_days)
        recent_returns = sorted(returns[-window:])
        
        # VaR threshold (index for specified confidence level)
        var_idx = int((1 - self.confidence) * len(recent_returns))
        
        # Correctly get the VaR threshold value
        if var_idx >= len(recent_returns):
            return 0.0 # Should not happen with validation, but as a safeguard
        var_threshold = recent_returns[var_idx]
        
        # Tail losses (all returns strictly less than VaR threshold)
        tail_losses = [r for r in recent_returns if r < var_threshold]
        
        # CVaR = Average of tail losses
        cvar = np.mean(tail_losses) if tail_losses else var_threshold
        
        # Returns absolute loss (positive value)
        return abs(float(cvar))

    def detect_risk_concentration(
        self, 
        symbol_returns: Dict[str, List[float]], 
        symbol_weights: Dict[str, float]
    ) -> Tuple[Dict[str, float], str]:
        """
        Detect symbols contributing most to portfolio CVaR.
        
        Returns:
            Dictionary of (symbol -> risk_contribution), and risk warning string
        """
        # Calculate individual symbol CVaRs
        contributions = {}
        for symbol, returns in symbol_returns.items():
            weight = symbol_weights.get(symbol, 0.0)
            if weight > 0:
                # Approximate marginal CVaR contribution
                symbol_cvar = self.calculate_cvar(returns)
                contributions[symbol] = weight * symbol_cvar
                
        # Find highest risk concentration
        if not contributions:
            return {}, "No risk concentration detected."
            
        total_risk = sum(contributions.values())
        max_symbol = max(contributions, key=contributions.get)
        max_ratio = contributions[max_symbol] / total_risk if total_risk > 0 else 0.0
        
        warning = f"Risk concentration: {max_symbol} contributes {max_ratio:.1%} of portfolio tail risk."
        
        return contributions, warning
