"""
Layer 03: Execution Engine - Turnover Control
Prevents excessive rebalancing while maintaining regulatory compliance.
"""
import pandas as pd
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass(frozen=True) # FIX (v21.9.1): Truly immutable to prevent leakage
class TradeSnapshot:
    """Immutable snapshot of a trade decision at a point in time."""
    date: pd.Timestamp
    symbol: str
    weight_change: float
    decision: bool
    reason: str

class TurnoverControl:
    """
    Controls portfolio rebalancing frequency.
    """
    
    def __init__(self, drift_threshold=0.03, rebalance_freq_days=5):
        self.drift_threshold = drift_threshold
        self.rebalance_freq_days = rebalance_freq_days
        self._last_execution_date: Dict[str, pd.Timestamp] = {}
        self._decision_history: Dict[str, list] = {}
        
    def check_turnover(self, symbol, current_weight, target_weight, curr_date, regime='Sideways') -> TradeSnapshot:
        drift = abs(target_weight - current_weight)
        
        # Rule 1: High drift (Emergency)
        if drift > self.drift_threshold:
            decision, reason = True, f"High drift ({drift:.2%})"
        # Rule 2: Bull Market (Aggressive)
        elif regime == 'Bull' and drift > 0.01:
            decision, reason = True, f"Bull regime, drift ({drift:.2%})"
        # Rule 3: Cooldown (Only if last trade was SUCCESSFUL)
        else:
            last_date = self._last_execution_date.get(symbol)
            if last_date is None:
                decision, reason = True, "No prior trade"
            else:
                days_since = (curr_date - last_date).days
                if days_since >= self.rebalance_freq_days:
                    decision, reason = True, f"Cooldown complete ({days_since}d)"
                else:
                    decision, reason = False, f"In cooldown ({days_since}d < {self.rebalance_freq_days}d)"
        
        # RECORD ONLY ON SUCCESSFUL EXECUTION (Fixes Reset Bug)
        if decision:
            self._last_execution_date[symbol] = curr_date
            
        snapshot = TradeSnapshot(curr_date, symbol, drift, decision, reason)
        
        if symbol not in self._decision_history: self._decision_history[symbol] = []
        self._decision_history[symbol].append(snapshot)
        
        return snapshot
