"""
Contagion Risk Validator - OMEGA_QUANT Phase 5.
Detects correlation spikes and beta jumps indicating systemic risk.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger("OmegaContagionValidator")

@dataclass
class ContagionConfig:
    """Configuration for contagion detection."""
    correlation_threshold: float = 0.8  # Alert if correlation > 80%
    beta_jump_threshold: float = 0.5  # Alert if beta jumps > 0.5
    lookback_window: int = 21  # 21-day rolling window

class ContagionRiskValidator:
    """Validates portfolio against contagion risk."""
    
    def __init__(self, config: Optional[ContagionConfig] = None):
        self.config = config or ContagionConfig()
        
    def check_correlation_spikes(
        self,
        asset_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Check for correlation spikes across assets.
        
        Args:
            asset_returns: DataFrame of asset returns (rows=dates, cols=symbols).
            
        Returns:
            Dictionary of (asset_pair, correlation) for pairs > threshold.
        """
        if len(asset_returns) < 2:
            return {}
            
        corr_matrix = asset_returns.corr()
        
        # Get upper triangle (exclude diagonal)
        correlations = {}
        for i, sym1 in enumerate(corr_matrix.columns):
            for j, sym2 in enumerate(corr_matrix.columns):
                if i < j:  # Upper triangle only
                    corr = corr_matrix.loc[sym1, sym2]
                    if abs(corr) > self.config.correlation_threshold:
                        correlations[f"{sym1}/{sym2}"] = corr
                        
        return correlations
    
    def check_beta_jumps(
        self,
        asset_returns: pd.Series,
        market_returns: pd.Series
    ) -> Tuple[bool, float, float]:
        """
        Check for beta jumps in asset relative to market.
        
        Args:
            asset_returns: Asset return series.
            market_returns: Market return series.
            
        Returns:
            Tuple of (jump_detected, current_beta, previous_beta)
        """
        if len(asset_returns) < self.config.lookback_window + 1:
            return False, 0.0, 0.0
            
        # Calculate rolling beta
        covariance = asset_returns.rolling(window=self.config.lookback_window).cov(market_returns)
        market_variance = market_returns.rolling(window=self.config.lookback_window).var()
        
        beta = covariance / market_variance
        
        current_beta = beta.iloc[-1]
        previous_beta = beta.iloc[-2] if len(beta) > 1 else current_beta
        
        beta_jump = abs(current_beta - previous_beta)
        
        return bool(beta_jump > self.config.beta_jump_threshold), float(current_beta), float(previous_beta)

