"""
Drift Detection Engine - OMEGA Phase 6.1
Ensemble of 3 detectors with 2-of-3 majority voting.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger("OmegaDriftDetection")

@dataclass
class DriftDetectorConfig:
    """Configuration for drift detection."""
    sharpe_drop_threshold: float = 0.30  # 30% drop triggers alert
    ic_drop_threshold: float = 0.20      # 20% drop triggers alert
    turnover_spike_threshold: float = 0.50  # 50% spike triggers alert
    lookback_window_days: int = 30

class DriftDetectorEnsemble:
    """3-detector ensemble with 2-of-3 majority voting."""
    
    def __init__(self, config: Optional[DriftDetectorConfig] = None):
        self.config = config or DriftDetectorConfig()
        self.history: Dict[str, List[Dict[str, float]]] = {}
    
    def record_metrics(
        self,
        timestamp: pd.Timestamp,
        sharpe: float,
        ic: float,
        turnover: float
    ) -> None:
        """Record metrics for drift analysis."""
        if timestamp not in self.history:
            self.history[timestamp] = []
        
        self.history[timestamp].append({
            "timestamp": timestamp,
            "sharpe": sharpe,
            "ic": ic,
            "turnover": turnover
        })
        
        # P1 FIX: Clean up old entries beyond lookback window
        self._cleanup_old_history()
    
    def _cleanup_old_history(self) -> None:
        """Remove history entries older than lookback window."""
        if not self.history:
            return
        
        # Find the oldest timestamp we should keep
        all_timestamps = list(self.history.keys())
        if not all_timestamps:
            return
        
        latest_timestamp = max(all_timestamps)
        cutoff_date = latest_timestamp - pd.Timedelta(days=self.config.lookback_window_days)
        
        # Remove old entries
        old_keys = [ts for ts in all_timestamps if ts < cutoff_date]
        for key in old_keys:
            del self.history[key]
    
    def _get_lookback_metrics(self) -> tuple:
        """Get metrics within lookback window."""
        historical_sharpe = []
        historical_ic = []
        historical_turnover = []
        
        if not self.history:
            return historical_sharpe, historical_ic, historical_turnover
        
        # P1 FIX: Apply lookback window filter
        all_timestamps = list(self.history.keys())
        if all_timestamps:
            latest_timestamp = max(all_timestamps)
            cutoff_date = latest_timestamp - pd.Timedelta(days=self.config.lookback_window_days)
            
            for timestamp, metrics_list in self.history.items():
                if timestamp >= cutoff_date:  # Only include recent history
                    for m in metrics_list:
                        historical_sharpe.append(m["sharpe"])
                        historical_ic.append(m["ic"])
                        historical_turnover.append(m["turnover"])
        
        return historical_sharpe, historical_ic, historical_turnover
    
    def detect_sharpe_drift(
        self,
        current_sharpe: float,
        historical_sharpe: List[float]
    ) -> bool:
        """Detect Sharpe ratio drop > 30%."""
        if len(historical_sharpe) < 2:
            return False
        
        avg_historical = np.mean(historical_sharpe)
        if avg_historical == 0:
            return False
        
        drop_ratio = (avg_historical - current_sharpe) / abs(avg_historical)
        return bool(drop_ratio > self.config.sharpe_drop_threshold)
    
    def detect_ic_drift(
        self,
        current_ic: float,
        historical_ic: List[float]
    ) -> bool:
        """Detect IC drop > 20%."""
        if len(historical_ic) < 2:
            return False
        
        avg_historical = np.mean(historical_ic)
        if avg_historical == 0:
            return False
        
        drop_ratio = (avg_historical - current_ic) / abs(avg_historical)
        return bool(drop_ratio > self.config.ic_drop_threshold)
    
    def detect_turnover_spike(
        self,
        current_turnover: float,
        historical_turnover: List[float]
    ) -> bool:
        """Detect turnover spike > 50%."""
        if len(historical_turnover) < 2:
            return False
        
        avg_historical = np.mean(historical_turnover)
        if avg_historical == 0:
            return False
        
        spike_ratio = (current_turnover - avg_historical) / abs(avg_historical)
        return bool(spike_ratio > self.config.turnover_spike_threshold)
    
    def check_drift(
        self,
        current_sharpe: float,
        current_ic: float,
        current_turnover: float
    ) -> Dict[str, Any]:
        """
        Run all 3 detectors and apply 2-of-3 majority voting.
        Returns: {drift_detected: bool, detectors_triggered: List[str], reason: str}
        """
        # P1 FIX: Get metrics within lookback window only
        historical_sharpe, historical_ic, historical_turnover = self._get_lookback_metrics()
        
        # Run 3 detectors
        sharpe_drift = self.detect_sharpe_drift(current_sharpe, historical_sharpe)
        ic_drift = self.detect_ic_drift(current_ic, historical_ic)
        turnover_drift = self.detect_turnover_spike(current_turnover, historical_turnover)
        
        # 2-of-3 majority voting
        detectors_triggered = []
        if sharpe_drift:
            detectors_triggered.append("sharpe_drop")
        if ic_drift:
            detectors_triggered.append("ic_drop")
        if turnover_drift:
            detectors_triggered.append("turnover_spike")
        
        drift_detected = len(detectors_triggered) >= 2
        
        return {
            "drift_detected": drift_detected,
            "detectors_triggered": detectors_triggered,
            "reason": f"Detected: {', '.join(detectors_triggered)}" if drift_detected else "No drift detected",
            "sharpe_drift": sharpe_drift,
            "ic_drift": ic_drift,
            "turnover_drift": turnover_drift
        }
    
    def get_rollback_signal(
        self,
        current_sharpe: float,
        current_ic: float,
        current_turnover: float
    ) -> bool:
        """
        High-level interface: Should we rollback to last stable state?
        Returns True if drift detected (2-of-3 voting).
        """
        result = self.check_drift(current_sharpe, current_ic, current_turnover)
        return bool(result["drift_detected"])
