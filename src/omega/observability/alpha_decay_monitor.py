"""
Alpha Decay Monitor - V21 Institutional
Continuous monitoring of alpha signal decay with automated retraining triggers.
"""

from __future__ import annotations

import numpy as np
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import logging

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


@dataclass
class AlphaDecayConfig:
    """Configuration for alpha decay monitoring."""
    baseline_ic: float = 0.1871
    baseline_sharpe: float = 1.9961
    decay_threshold: float = 0.10  # 10% decay triggers alert
    p_value_threshold: float = 0.05  # Statistical significance
    min_samples: int = 30  # Minimum samples for t-test
    retrain_trigger: str = "p_value"  # "p_value" or "absolute"
    monitoring_frequency: str = "daily"  # "daily" or "weekly"


class AlphaDecayMonitor:
    """
    Monitor alpha signal decay and trigger retraining when necessary.
    
    Features:
    - Daily/weekly IC and Sharpe tracking
    - Statistical significance testing (t-test)
    - Automated retraining triggers
    - Decay attribution analysis
    - Audit trail with JSONL logging
    """
    
    def __init__(self, config: AlphaDecayConfig = None):
        self.config = config or AlphaDecayConfig()
        self.history: Dict[str, List[Dict]] = {}
        self.retraining_log: List[Dict] = []
        
    def record_performance(self, model_name: str, ic: float, sharpe: float, 
                          timestamp: Optional[datetime] = None):
        """Record performance metrics for a model.
        
        Raises:
            ValueError: If timestamp is in the future (PIT compliance)
        """
        if model_name not in self.history:
            self.history[model_name] = []
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # Block future-dated observations (PIT compliance)
        now = datetime.now()
        if timestamp > now:
            raise ValueError(
                f"Future-dated observation rejected for '{model_name}': "
                f"timestamp {timestamp.isoformat()} > now {now.isoformat()}"
            )
        
        self.history[model_name].append({
            'timestamp': timestamp.isoformat(),
            'ic': ic,
            'sharpe': sharpe
        })
        
    def check_decay(self, model_name: str) -> Dict[str, Any]:
        """
        Check if model has decayed significantly.
        
        Returns:
            Dict with:
            - status: "OK", "WARNING", or "RETRAIN_REQUIRED"
            - ic_decay_pct: IC decay percentage
            - sharpe_decay_pct: Sharpe decay percentage
            - p_value: Statistical significance
            - recommendation: Action recommendation
        """
        if model_name not in self.history:
            return {
                'status': 'OK',
                'ic_decay_pct': 0.0,
                'sharpe_decay_pct': 0.0,
                'p_value': 1.0,
                'recommendation': 'No history available'
            }
        
        history = self.history[model_name]
        
        if len(history) < self.config.min_samples:
            return {
                'status': 'OK',
                'ic_decay_pct': 0.0,
                'sharpe_decay_pct': 0.0,
                'p_value': 1.0,
                'recommendation': f'Insufficient data ({len(history)}/{self.config.min_samples} samples)'
            }
        
        # Get recent performance (last 30 samples)
        recent = history[-30:]
        recent_ic = [h['ic'] for h in recent]
        recent_sharpe = [h['sharpe'] for h in recent]
        
        # Calculate decay percentages
        ic_decay_pct = (self.config.baseline_ic - np.mean(recent_ic)) / self.config.baseline_ic
        sharpe_decay_pct = (self.config.baseline_sharpe - np.mean(recent_sharpe)) / self.config.baseline_sharpe
        
        # Statistical significance test (one-sample t-test)
        if SCIPY_AVAILABLE:
            ic_t_stat, ic_p_value = stats.ttest_1samp(recent_ic, self.config.baseline_ic, alternative='less')
            sharpe_t_stat, sharpe_p_value = stats.ttest_1samp(recent_sharpe, self.config.baseline_sharpe, alternative='less')
            # Use min() - trigger if EITHER metric decays significantly
            p_value = min(ic_p_value, sharpe_p_value)
        else:
            # Simple approximation without scipy
            ic_std = np.std(recent_ic)
            sharpe_std = np.std(recent_sharpe)
            ic_se = ic_std / np.sqrt(len(recent_ic))
            sharpe_se = sharpe_std / np.sqrt(len(recent_sharpe))
            ic_t_stat = (np.mean(recent_ic) - self.config.baseline_ic) / ic_se
            sharpe_t_stat = (np.mean(recent_sharpe) - self.config.baseline_sharpe) / sharpe_se
            # One-tailed p-value (left-tailed for decay detection)
            # If t_stat < 0, performance is below baseline (decay)
            if ic_t_stat < 0:
                ic_p_value = 0.5 * (1 - math.erf(abs(ic_t_stat) / math.sqrt(2)))
            else:
                ic_p_value = 1.0  # No decay if above baseline
            
            if sharpe_t_stat < 0:
                sharpe_p_value = 0.5 * (1 - math.erf(abs(sharpe_t_stat) / math.sqrt(2)))
            else:
                sharpe_p_value = 1.0  # No decay if above baseline
            
            # Use min() - trigger if EITHER metric decays significantly
            p_value = min(ic_p_value, sharpe_p_value)
        
        # Determine status
        if self.config.retrain_trigger == "p_value":
            if p_value < self.config.p_value_threshold:
                status = "RETRAIN_REQUIRED"
            elif abs(ic_decay_pct) > self.config.decay_threshold or abs(sharpe_decay_pct) > self.config.decay_threshold:
                status = "WARNING"
            else:
                status = "OK"
        else:  # absolute threshold
            if abs(ic_decay_pct) > self.config.decay_threshold or abs(sharpe_decay_pct) > self.config.decay_threshold:
                status = "RETRAIN_REQUIRED"
            elif abs(ic_decay_pct) > self.config.decay_threshold * 0.5 or abs(sharpe_decay_pct) > self.config.decay_threshold * 0.5:
                status = "WARNING"
            else:
                status = "OK"
        
        # Generate recommendation
        if status == "RETRAIN_REQUIRED":
            recommendation = f"Retrain {model_name} immediately - significant decay detected"
        elif status == "WARNING":
            recommendation = f"Monitor {model_name} closely - potential decay detected"
        else:
            recommendation = f"{model_name} performing normally"
        
        return {
            'status': status,
            'ic_decay_pct': ic_decay_pct,
            'sharpe_decay_pct': sharpe_decay_pct,
            'p_value': p_value,
            'recommendation': recommendation,
            'recent_ic_mean': np.mean(recent_ic),
            'recent_sharpe_mean': np.mean(recent_sharpe),
            'baseline_ic': self.config.baseline_ic,
            'baseline_sharpe': self.config.baseline_sharpe
        }
    
    def trigger_retraining(self, model_name: str, reason: str):
        """Log retraining trigger event."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'model_name': model_name,
            'reason': reason,
            'action': 'retraining_triggered'
        }
        self.retraining_log.append(event)
        logging.info(f"Retraining triggered for {model_name}: {reason}")
        
    def get_decay_attribution(self, model_name: str) -> Dict[str, float]:
        """
        Analyze what factors contributed to decay.
        
        Returns:
            Dict with attribution for:
            - market_regime_change
            - data_quality_degradation
            - feature_drift
            - model_overfitting
        """
        if model_name not in self.history:
            return {}
        
        history = self.history[model_name]
        if len(history) < 60:
            return {'insufficient_data': True}
        
        # Split into early and late periods
        early = history[:30]
        late = history[-30:]
        
        early_ic = np.mean([h['ic'] for h in early])
        late_ic = np.mean([h['ic'] for h in late])
        
        # Simple attribution (in production, use more sophisticated methods)
        attribution = {
            'market_regime_change': max(0, (early_ic - late_ic) / early_ic) * 0.5,
            'data_quality_degradation': max(0, (early_ic - late_ic) / early_ic) * 0.2,
            'feature_drift': max(0, (early_ic - late_ic) / early_ic) * 0.2,
            'model_overfitting': max(0, (early_ic - late_ic) / early_ic) * 0.1
        }
        
        return attribution
    
    def save_state(self, state_path: str = "state/alpha_decay_state.json"):
        """Save monitor state to file."""
        state = {
            'history': self.history,
            'retraining_log': self.retraining_log,
            'last_updated': datetime.now().isoformat()
        }
        
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, state_path: str = "state/alpha_decay_state.json"):
        """Load monitor state from file."""
        if os.path.exists(state_path):
            with open(state_path, 'r') as f:
                state = json.load(f)
                self.history = state.get('history', {})
                self.retraining_log = state.get('retraining_log', [])
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all model performance."""
        summary = {}
        for model_name, history in self.history.items():
            if history:
                recent = history[-30:]
                summary[model_name] = {
                    'total_records': len(history),
                    'recent_ic_mean': np.mean([h['ic'] for h in recent]),
                    'recent_sharpe_mean': np.mean([h['sharpe'] for h in recent]),
                    'ic_std': np.std([h['ic'] for h in recent]),
                    'sharpe_std': np.std([h['sharpe'] for h in recent])
                }
        return summary
