"""
Alpha Decay Service
Wraps alpha_decay.py for signal lifecycle monitoring.
"""
import sys
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
import numpy as np
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from omega.quant.alpha_decay import AlphaDecayAnalyzer, AlphaDecayReport

logger = logging.getLogger(__name__)


class AlphaDecayService:
    """Service for alpha decay analysis"""
    
    def __init__(self, max_lag: int = 20):
        self.analyzer = AlphaDecayAnalyzer(max_lag=max_lag)
    
    def analyze_decay(
        self,
        predictions: np.ndarray,
        returns: np.ndarray
    ) -> Optional[Dict]:
        """
        Analyze alpha signal decay
        
        Args:
            predictions: Model predictions
            returns: Actual returns
            
        Returns:
            Dict with decay metrics
        """
        try:
            report = self.analyzer.analyze(predictions, returns)
            
            return {
                "ic_by_lag": report.ic_by_lag,
                "optimal_horizon": report.optimal_horizon,
                "half_life": report.half_life,
                "decay_rate": report.decay_rate,
                "ci_low": report.ci_low,
                "ci_high": report.ci_high,
                "recommended_horizon": self.analyzer.get_recommended_horizon(report)
            }
        except Exception as e:
            logger.error(f"Alpha decay analysis failed: {e}")
            return None
    
    def compute_ic_curve(
        self,
        predictions: np.ndarray,
        returns: np.ndarray,
        max_lag: int = 20
    ) -> List[Dict]:
        """
        Compute IC at multiple lags for visualization
        
        Returns:
            List of dicts with lag and IC values
        """
        ic_curve = []
        
        for lag in range(1, max_lag + 1):
            ic = self.analyzer.compute_ic_at_lag(predictions, returns, lag)
            ic_curve.append({
                "lag": lag,
                "ic": ic
            })
        
        return ic_curve
    
    def detect_decay_threshold(
        self,
        ic_by_lag: Dict[int, float],
        threshold: float = 0.02
    ) -> Optional[int]:
        """
        Detect lag where IC drops below threshold
        
        Returns:
            Lag where IC first drops below threshold, or None
        """
        for lag in sorted(ic_by_lag.keys()):
            if abs(ic_by_lag[lag]) < threshold:
                return lag
        return None
    
    def is_alpha_decayed(
        self,
        report: Dict,
        ic_threshold: float = 0.02,
        half_life_threshold: int = 5
    ) -> bool:
        """
        Check if alpha signal is decayed
        
        Args:
            report: Alpha decay report
            ic_threshold: Minimum IC threshold
            half_life_threshold: Maximum acceptable half-life
            
        Returns:
            True if alpha is decayed
        """
        # Check if IC at lag 1 is below threshold
        ic_lag1 = report.get("ic_by_lag", {}).get(1, 0.0)
        if abs(ic_lag1) < ic_threshold:
            return True
        
        # Check if half-life is too short
        half_life = report.get("half_life", 0)
        if half_life < half_life_threshold:
            return True
        
        return False
