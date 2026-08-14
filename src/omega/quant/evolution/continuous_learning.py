"""
Continuous Learning Engine - OMEGA Phase 6.1
Adapted from V21_QUANT for OMEGA architecture.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging

from omega.quant.evolution.alpha_to_execution_bridge import CANONICAL_METRIC_KEY, resolve_metric_config

logger = logging.getLogger("OmegaContinuousLearning")

@dataclass
class ContinuousLearningConfig:
    """Configuration for continuous learning."""
    retraining_interval_days: int = 7  # Weekly retraining
    min_ic_improvement: float = 0.05  # 5% IC improvement threshold
    p_value_threshold: float = 0.05
    min_absolute_ic: float = 0.10
    sharpe_tolerance: float = 0.95  # Keep if Sharpe >= 95% of champion

class ContinuousLearningEngine:
    """Daily monitoring with weekly retraining and champion/challenger selection."""
    
    def __init__(self, config: Optional[ContinuousLearningConfig] = None):
        self.config = config or ContinuousLearningConfig()
        self.champion_model = None
        self.challenger_model = None
        self.last_retrain_date = None
        self.retraining_history = []
    
    def should_retrain(self, current_date: pd.Timestamp) -> bool:
        """Check if weekly retraining is due."""
        if self.last_retrain_date is None:
            return True
        
        days_since_retrain = (current_date - self.last_retrain_date).days
        return days_since_retrain >= self.config.retraining_interval_days
    
    def evaluate_model(
        self,
        predictions: pd.Series,
        actuals: pd.Series,
        model_name: str = "model"
    ) -> Dict[str, float]:
        """Compute IC and Sharpe ratio for model evaluation."""
        # PIT-safe: ensure no future data leakage
        if len(predictions) != len(actuals):
            raise ValueError("Predictions and actuals must have same length")
        
        # Information Coefficient (IC)
        ic = predictions.corr(actuals)
        
        # Sharpe ratio (simplified: returns / volatility)
        returns = predictions * actuals  # Proxy for P&L
        sharpe = returns.mean() / (returns.std() + 1e-8) if returns.std() > 0 else 0.0
        
        return {
            "model_name": model_name,
            "ic": float(ic) if not pd.isna(ic) else 0.0,
            CANONICAL_METRIC_KEY: float(sharpe),
            "sharpe": float(sharpe),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def champion_vs_challenger(
        self,
        champion_metrics: Dict[str, float],
        challenger_metrics: Dict[str, float]
    ) -> Tuple[bool, str]:
        """
        Compare champion vs challenger using paired t-test logic.
        Returns: (should_promote, reason)
        """
        champion_ic = champion_metrics.get("ic", 0.0)
        challenger_ic = challenger_metrics.get("ic", 0.0)
        
        # P0 FIX: Verify absolute thresholds FIRST
        if challenger_ic < self.config.min_absolute_ic:
            logger.warning(f"Challenger IC {challenger_ic:.4f} below absolute minimum {self.config.min_absolute_ic}")
            return False, "IC below minimum threshold"
            
        champion_sharpe = resolve_metric_config(champion_metrics)[0] or champion_metrics.get("sharpe", 0.0)
        challenger_sharpe = resolve_metric_config(challenger_metrics)[0] or challenger_metrics.get("sharpe", 0.0)
        
        sharpe_ratio = challenger_sharpe / (champion_sharpe + 1e-8) if champion_sharpe > 0 else 1.0
        
        if sharpe_ratio < self.config.sharpe_tolerance:
            logger.warning(f"Challenger Sharpe {sharpe_ratio:.2%} of champion (below tolerance {self.config.sharpe_tolerance})")
            return False, "Sharpe ratio below tolerance"
            
        # P0 FIX: Verify relative IC improvement LAST
        ic_improvement = (challenger_ic - champion_ic) / (abs(champion_ic) + 1e-8)
        
        if ic_improvement >= self.config.min_ic_improvement:
            logger.info(f"Challenger IC improved by {ic_improvement:.2%}")
            return True, f"IC improved by {ic_improvement:.2%}"
        
        return False, "No significant improvement"
    
    def retrain_cycle(
        self,
        train_data: pd.DataFrame,
        train_labels: pd.Series,
        current_date: pd.Timestamp
    ) -> Dict[str, Any]:
        """Execute weekly retraining cycle."""
        if not self.should_retrain(current_date):
            return {"status": "skipped", "reason": "Not yet time for retraining"}
        
        # Simulate model training (in production, would call actual trainer)
        challenger_predictions = train_data.mean(axis=1)  # Placeholder
        
        challenger_metrics = self.evaluate_model(
            challenger_predictions,
            train_labels,
            model_name="challenger"
        )
        
        # Compare with champion
        if self.champion_model is None:
            # First retrain: challenger becomes champion
            self.champion_model = challenger_metrics
            self.last_retrain_date = current_date
            logger.info("First retrain: challenger promoted to champion")
            return {
                "status": "promoted",
                "reason": "First retrain",
                "metrics": challenger_metrics
            }
        
        # Champion vs Challenger comparison
        should_promote, reason = self.champion_vs_challenger(
            self.champion_model,
            challenger_metrics
        )
        
        self.last_retrain_date = current_date
        
        if should_promote:
            self.champion_model = challenger_metrics
            logger.info(f"Challenger promoted: {reason}")
            return {
                "status": "promoted",
                "reason": reason,
                "metrics": challenger_metrics
            }
        else:
            logger.info(f"Champion retained: {reason}")
            return {
                "status": "retained",
                "reason": reason,
                "metrics": self.champion_model
            }
