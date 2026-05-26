"""
Alpha Decay Analysis Module - V21 Institutional
Measures how quickly alpha signals decay over time.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np


@dataclass
class AlphaDecayReport:
    """Report containing alpha decay metrics."""
    ic_by_lag: Dict[int, float]  # IC at lag 1, 2, 3, ...
    optimal_horizon: int  # Optimal holding period (days)
    half_life: float  # Signal half-life in days
    decay_rate: float  # Exponential decay rate
    ci_low: float = 0.0  # Bootstrap CI low (95%)
    ci_high: float = 0.0  # Bootstrap CI high (95%)


class AlphaDecayAnalyzer:
    """Analyze alpha signal decay over time.
    
    Measures Information Coefficient (IC) at different lags
    to determine optimal holding period and signal half-life.
    """
    
    def __init__(self, max_lag: int = 20):
        """
        Args:
            max_lag: Maximum lag days to analyze (default 20)
        """
        self.max_lag = max_lag
    
    def compute_ic_at_lag(
        self, 
        predictions: np.ndarray, 
        returns: np.ndarray, 
        lag: int
    ) -> float:
        """Compute IC at a specific lag.
        
        Args:
            predictions: Model predictions (aligned with returns)
            returns: Actual returns
            lag: Lag in days
            
        Returns:
            Pearson correlation (IC)
        """
        if len(predictions) <= lag:
            return 0.0
            
        pred_lagged = predictions[:-lag]
        ret_lagged = returns[lag:]
        
        if len(pred_lagged) < 2:
            return 0.0
            
        # Pearson correlation
        pred_mean = np.mean(pred_lagged)
        ret_mean = np.mean(ret_lagged)
        
        cov = np.mean((pred_lagged - pred_mean) * (ret_lagged - ret_mean))
        pred_std = np.std(pred_lagged)
        ret_std = np.std(ret_lagged)
        
        if pred_std == 0 or ret_std == 0:
            return 0.0
            
        return cov / (pred_std * ret_std)
    
    def _compute_ic_ci(
        self,
        predictions: np.ndarray,
        returns: np.ndarray,
        n_bootstraps: int = 100,
        confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """Compute bootstrap confidence interval for IC.
        
        Args:
            predictions: Model predictions
            returns: Actual returns
            n_bootstraps: Number of bootstrap iterations
            confidence_level: Confidence level (0-1)
            
        Returns:
            (ci_low, ci_high)
        """
        boot_ics = []
        n = len(predictions)
        if n < 5:
            return (0.0, 0.0)
            
        for _ in range(n_bootstraps):
            # Resample with replacement
            indices = np.random.randint(0, n, size=n)
            p_resampled = predictions[indices]
            r_resampled = returns[indices]
            
            # Simple correlation (IC)
            if np.std(p_resampled) > 1e-10 and np.std(r_resampled) > 1e-10:
                ic = np.corrcoef(p_resampled, r_resampled)[0, 1]
                if not np.isnan(ic):
                    boot_ics.append(ic)
        
        if not boot_ics:
            return (0.0, 0.0)
            
        lower_pct = (1.0 - confidence_level) / 2.0 * 100
        upper_pct = (1.0 + confidence_level) / 2.0 * 100
        
        return float(np.percentile(boot_ics, lower_pct)), float(np.percentile(boot_ics, upper_pct))
    
    def analyze(
        self, 
        predictions: np.ndarray, 
        returns: np.ndarray
    ) -> AlphaDecayReport:
        """Perform full alpha decay analysis.
        
        Args:
            predictions: Model predictions
            returns: Actual returns
            
        Returns:
            AlphaDecayReport with decay metrics
        """
        ic_by_lag = {}
        
        for lag in range(1, self.max_lag + 1):
            ic_by_lag[lag] = self.compute_ic_at_lag(predictions, returns, lag)
        
        # Find optimal horizon (lag with maximum IC)
        optimal_horizon = max(ic_by_lag.keys(), key=lambda k: ic_by_lag[k])
        
        # Estimate half-life (lag where IC drops to half of peak)
        # FIX: Handle both positive and negative IC scenarios
        peak_ic = max(ic_by_lag.values()) if ic_by_lag else 0.0
        min_ic = min(ic_by_lag.values()) if ic_by_lag else 0.0
        
        # For positive IC: find where it drops to half
        # For negative IC: find where it becomes half as negative (closer to zero)
        half_ic = peak_ic / 2.0
        
        # Use absolute value to find decay regardless of sign
        abs_peak = abs(peak_ic)
        
        half_life = self.max_lag  # default
        for lag in sorted(ic_by_lag.keys()):
            if abs(ic_by_lag[lag]) <= abs_peak / 2.0:
                half_life = lag
                break
        
        # Handle case where IC never decays below half (stays strong)
        if half_life == self.max_lag and abs_peak > 0:
            half_life = self.max_lag  # Signal is still strong
        
        # Estimate decay rate (exponential fit)
        # Using IC at lag 1 and lag max_lag
        ic_1 = ic_by_lag.get(1, 0.0)
        ic_max = ic_by_lag.get(self.max_lag, 0.0)
        
        # FIX: Handle edge case where ic_1 is zero or negative
        if ic_1 > 0 and ic_max > 0:
            decay_rate = -np.log(ic_max / ic_1) / (self.max_lag - 1) if ic_1 != 0 else 0.0
        else:
            decay_rate = 0.0
        
        # FIX: Compute confidence interval for IC
        ci_low, ci_high = self._compute_ic_ci(predictions, returns)
        
        return AlphaDecayReport(
            ic_by_lag=ic_by_lag,
            optimal_horizon=optimal_horizon,
            half_life=half_life,
            decay_rate=decay_rate,
            ci_low=ci_low,
            ci_high=ci_high
        )
    
    def get_recommended_horizon(self, report: AlphaDecayReport) -> int:
        """Get recommended holding horizon based on decay analysis.
        
        Args:
            report: AlphaDecayReport
            
        Returns:
            Recommended holding period (days)
        """
        # Use half-life as recommendation
        return max(1, int(report.half_life))
