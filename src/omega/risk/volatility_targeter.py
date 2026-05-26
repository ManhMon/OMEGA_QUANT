"""
Layer 04: Risk Management - Volatility Targeter
Scales portfolio exposure based on realized volatility.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional

class VolatilityTargeter:
    """
    Maintains a stable portfolio volatility by scaling exposure.
    """
    
    def __init__(self, target_vol: float = 0.15, lookback_days: int = 20):
        self.target_vol = target_vol  # Annualized (e.g. 15%)
        self.lookback_days = lookback_days
        
    def calculate_scaling_factor(self, daily_returns: pd.Series) -> float:
        """
        Calculate the multiplier to apply to all weights.
        """
        if len(daily_returns) < self.lookback_days:
            return 1.0
            
        # Annualized Realized Volatility
        realized_vol = daily_returns.tail(self.lookback_days).std() * np.sqrt(252)
        
        if realized_vol <= 0 or np.isnan(realized_vol):
            return 1.0
            
        # Scaling Factor = Target / Realized
        scaling_factor = self.target_vol / realized_vol
        
        # FIX (v21.10.1): Limit scaling to [0.2, 1.0] to prevent leverage
        # Never allow exposure > 100% (no leverage in VN market)
        return np.clip(scaling_factor, 0.2, 1.0)
    
    def calculate_scaling_factor_from_returns(
        self, returns: List[float], lookback_override: Optional[int] = None
    ) -> float:
        """
        FIX (v21.10.1): Accept a list of daily returns instead of a pd.Series.
        This is the canonical method for use in the risk pipeline.
        """
        import pandas as pd
        lookback = lookback_override or self.lookback_days
        if len(returns) < lookback:
            return 1.0
        series = pd.Series(returns)
        realized = series.tail(lookback).std() * np.sqrt(252)
        if realized <= 0 or np.isnan(realized):
            return 1.0
        # FIX (v21.10.1): Cap at 1.0 to prevent leverage > 100%
        return float(np.clip(self.target_vol / realized, 0.2, 1.0))

    def scale_weights(self, weights: Dict[str, float], factor: float) -> Dict[str, float]:
        """Apply scaling factor and move remainder to cash."""
        scaled_weights = {s: w * factor for s, w in weights.items()}
        total_exposure = sum(scaled_weights.values())
        scaled_weights["CASH"] = max(0.0, 1.0 - total_exposure)
        return scaled_weights
