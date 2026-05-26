"""
Signal Decay Analyzer Module
Layer 07: Monitoring & Observability

Detects alpha decay using:
1. Rolling T-test (Slow Decay)
2. CUSUM (Structural Breaks)
3. Rolling Sharpe Ratio Degradation
Provides regime-conditional tracking to avoid false alarms during regime shifts.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from scipy.stats import ttest_1samp
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class DecayConfig:
    """Configuration for Signal Decay Analyzer"""
    window_size: int = 21  # 1 month trading days
    min_samples: int = 10
    ic_decay_threshold_pct: float = 0.15  # 15% drop in IC triggers slow decay
    sharpe_decay_threshold_pct: float = 0.20  # 20% drop in Sharpe triggers slow decay
    p_value_threshold: float = 0.05  # 95% confidence for T-test
    cusum_threshold: float = 3.0  # Z-score equivalent for structural break
    cusum_drift: float = 0.5  # Allowed drift before accumulating CUSUM


@dataclass
class DecayEvent:
    """Event emitted when decay is detected"""
    status: str  # "OK", "RETRAIN_REQUIRED", "EMERGENCY_PAUSE", "REGIME_SHIFT"
    action: str  # "CONTINUE", "TRIGGER_WALK_FORWARD", "PAUSE_AND_INVESTIGATE", "MONITOR_CLOSELY"
    reason: str
    regime: str
    metrics: Dict[str, float] = field(default_factory=dict)


class CUSUMDetector:
    """Cumulative Sum (CUSUM) for detecting abrupt structural breaks."""
    def __init__(self, threshold: float = 3.0, drift: float = 0.5):
        self.threshold = threshold
        self.drift = drift
        self.reset()
        
    def reset(self):
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        
    def detect(self, series: np.ndarray) -> bool:
        if len(series) < 10:
            return False
            
        # Robust standardization using MAD (using the FIRST HALF of the series as baseline)
        # If we use the whole series, a huge drop will pull the median down.
        baseline_idx = max(5, len(series) // 2)
        baseline_series = series[:baseline_idx]
        
        median = np.median(baseline_series)
        mad = np.median(np.abs(baseline_series - median))
        if mad < 1e-8:
            mad = 1e-8  # Prevent division by zero
            
        std_est = 1.4826 * mad
        z_scores = (series - median) / std_est
        
        self.reset()
        for z in z_scores:
            self.cusum_neg = max(0, self.cusum_neg - z - self.drift)
            if self.cusum_neg > self.threshold:
                return True
        return False


class SignalDecayAnalyzer:
    def __init__(self, config: Optional[DecayConfig] = None):
        self.config = config or DecayConfig()
        
        # History tracking per regime
        self.history_ic: Dict[str, List[float]] = {'Bull': [], 'Bear': [], 'Sideways': []}
        self.history_sharpe: Dict[str, List[float]] = {'Bull': [], 'Bear': [], 'Sideways': []}
        
        # Baselines established during training per regime
        self.baselines: Dict[str, Dict[str, float]] = {}
        
        self.cusum = CUSUMDetector(self.config.cusum_threshold, self.config.cusum_drift)
        self.last_regime = None

    def set_baseline(self, regime: str, baseline_ic: float, baseline_sharpe: float):
        """Set baseline performance from training phase."""
        self.baselines[regime] = {
            'ic': baseline_ic,
            'sharpe': baseline_sharpe
        }
        # Reset history for this regime
        self.history_ic[regime] = []
        self.history_sharpe[regime] = []

    def _filter_tet_gaps(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """Create mask to filter out gaps > 5 days (Tet holidays)."""
        if len(dates) < 2:
            return np.ones(len(dates), dtype=bool)
        
        diffs = (dates[1:] - dates[:-1]).days
        mask = np.ones(len(dates), dtype=bool)
        
        for i, diff in enumerate(diffs):
            if diff > 5:
                # Mark the day after gap as potentially noisy
                mask[i+1] = False
        return mask

    def update_and_analyze(
        self, 
        dates: pd.DatetimeIndex,
        daily_ic: np.ndarray, 
        daily_returns: np.ndarray, 
        current_regime: str,
        limit_lock_rates: Optional[np.ndarray] = None
    ) -> DecayEvent:
        """
        Main entry point for daily monitoring.
        """
        # Regime shift handling
        if self.last_regime is not None and self.last_regime != current_regime:
            self.last_regime = current_regime
            return DecayEvent("REGIME_SHIFT", "MONITOR_CLOSELY", f"Shifted to {current_regime}", current_regime)
        self.last_regime = current_regime

        # 1. VN Market Pre-processing
        mask = self._filter_tet_gaps(dates)
        if limit_lock_rates is not None:
            mask = mask & (limit_lock_rates < 0.30)  # Filter days where >30% portfolio is limit-locked
            
        valid_ic = daily_ic[mask]
        valid_ret = daily_returns[mask]
        
        if len(valid_ic) == 0:
            return DecayEvent("OK", "CONTINUE", "No valid data today", current_regime)

        # 2. Update History
        self.history_ic[current_regime].extend(valid_ic)
        
        # Approximate daily Sharpe
        if len(valid_ret) > 0 and np.std(valid_ret) > 1e-8:
            daily_sharpe = np.mean(valid_ret) / np.std(valid_ret)
        else:
            daily_sharpe = 0.0
        self.history_sharpe[current_regime].append(daily_sharpe)

        # 3. Trim History to Window
        self.history_ic[current_regime] = self.history_ic[current_regime][-self.config.window_size:]
        self.history_sharpe[current_regime] = self.history_sharpe[current_regime][-self.config.window_size:]

        # Need minimum samples to analyze
        if len(self.history_ic[current_regime]) < self.config.min_samples:
            return DecayEvent("OK", "CONTINUE", "Warming up", current_regime)
            
        if current_regime not in self.baselines:
            return DecayEvent("OK", "CONTINUE", "No baseline set", current_regime)

        # 4. Analyze CUSUM (Structural Break)
        ic_array = np.array(self.history_ic[current_regime])
        if self.cusum.detect(ic_array):
            return DecayEvent(
                "EMERGENCY_PAUSE", 
                "PAUSE_AND_INVESTIGATE", 
                "CUSUM detected abrupt structural break", 
                current_regime
            )

        # 5. Analyze Slow Decay (T-Test & Sharpe Drop)
        baseline = self.baselines[current_regime]
        current_ic_mean = np.mean(ic_array)
        current_sharpe_mean = np.mean(self.history_sharpe[current_regime])
        
        ic_drop_pct = (baseline['ic'] - current_ic_mean) / abs(baseline['ic']) if baseline['ic'] != 0 else 0
        sharpe_drop_pct = (baseline['sharpe'] - current_sharpe_mean) / abs(baseline['sharpe']) if baseline['sharpe'] != 0 else 0
        
        # Perform 1-sample T-test against baseline mean
        # H0: current mean >= baseline mean
        # H1: current mean < baseline mean
        t_stat, p_val = ttest_1samp(ic_array, baseline['ic'], alternative='less')
        
        metrics = {
            "ic_drop_pct": float(ic_drop_pct),
            "sharpe_drop_pct": float(sharpe_drop_pct),
            "p_value": float(p_val)
        }
        
        is_ic_decayed = (ic_drop_pct > self.config.ic_decay_threshold_pct) and (p_val < self.config.p_value_threshold)
        is_sharpe_decayed = (sharpe_drop_pct > self.config.sharpe_decay_threshold_pct)
        
        if is_ic_decayed or is_sharpe_decayed:
            reason = "Statistically significant IC decay" if is_ic_decayed else "Severe Sharpe degradation"
            if is_ic_decayed and is_sharpe_decayed:
                reason = "Both IC and Sharpe degraded"
                
            return DecayEvent("RETRAIN_REQUIRED", "TRIGGER_WALK_FORWARD", reason, current_regime, metrics)

        return DecayEvent("OK", "CONTINUE", "Performance within normal bounds", current_regime, metrics)
