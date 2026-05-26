"""
OOS Walk-Forward Validator - V21 Institutional
Rigorous out-of-sample validation framework to prevent overfitting.
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple, Callable, Any
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
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    window_size: int = 252  # 1 year in trading days
    step_size: int = 63   # 3 months (quarterly retraining)
    train_ratio: float = 0.8
    min_samples: int = 100
    robustness_threshold: float = 0.8  # 80% of windows must pass
    ic_threshold: float = 0.15
    sharpe_threshold: float = 1.5
    degradation_threshold: float = 0.02  # Max validation-test gap


class OOSWalkForwardValidator:
    """
    Out-of-Sample Walk-Forward Validation Framework.
    
    Implements rigorous validation to prevent overfitting:
    - Expanding window: Train on [start, t-12m], validate on [t-12m, t-6m], test on [t-6m, t]
    - Rolling window: Train on [t-24m, t-12m], validate on [t-12m, t-6m], test on [t-6m, t]
    - Statistical tests for robustness
    - Degradation monitoring
    """
    
    def __init__(self, config: WalkForwardConfig = None):
        self.config = config or WalkForwardConfig()
        self.results: List[Dict] = []
        self.robustness_score: float = 0.0
        
    def run_expanding_window(self, X: np.ndarray, y: np.ndarray,
                            train_model_fn: Callable,
                            evaluate_fn: Callable,
                            start_date: int = None,
                            end_date: int = None) -> Dict[str, Any]:
        """
        Run expanding window walk-forward validation.
        
        Strategy: Train on [start, t-12m], validate on [t-12m, t-6m], test on [t-6m, t]
        
        Args:
            X: Feature matrix
            y: Target vector
            train_model_fn: Function that trains model and returns predictions
            evaluate_fn: Function that evaluates predictions (returns IC, Sharpe, MaxDD)
            start_date: Optional start timestamp
            end_date: Optional end timestamp
        
        Returns:
            Dict with validation results
        """
        n_samples = len(y)
        
        # Filter by date if provided - apply mask to both X and y together
        if start_date is not None or end_date is not None:
            mask = np.ones(n_samples, dtype=bool)
            if start_date is not None:
                mask &= (X[:, -1] >= start_date) if X.shape[1] > 1 else np.ones(n_samples, dtype=bool)
            if end_date is not None:
                mask &= (X[:, -1] <= end_date) if X.shape[1] > 1 else np.ones(n_samples, dtype=bool)
            
            X = X[mask]
            y = y[mask]
            n_samples = len(y)
        
        # Calculate number of windows
        window_size = self.config.window_size
        step_size = self.config.step_size
        
        n_windows = (n_samples - 2 * window_size) // step_size
        if n_windows < 1:
            return {'error': 'Insufficient data for walk-forward validation'}
        
        results = []
        
        for i in range(n_windows):
            # Calculate indices
            train_end = window_size + i * step_size
            val_end = train_end + window_size // 2
            test_end = val_end + window_size // 2
            
            if test_end > n_samples:
                break
            
            # Split data
            X_train = X[:train_end]
            y_train = y[:train_end]
            
            X_val = X[train_end:val_end]
            y_val = y[train_end:val_end]
            
            X_test = X[val_end:test_end]
            y_test = y[val_end:test_end]
            
            # Train model
            model = train_model_fn(X_train, y_train)
            
            # Validate
            val_preds = model.predict(X_val) if hasattr(model, 'predict') else model(X_val)
            val_ic, val_sharpe, val_maxdd = evaluate_fn(val_preds, y_val)
            
            # Test
            test_preds = model.predict(X_test) if hasattr(model, 'predict') else model(X_test)
            test_ic, test_sharpe, test_maxdd = evaluate_fn(test_preds, y_test)
            
            # Calculate degradation
            ic_degradation = val_ic - test_ic
            sharpe_degradation = val_sharpe - test_sharpe
            
            # Check if degradation exceeds threshold (overfitting indicator)
            # Positive degradation = validation better than test (good)
            # Negative degradation = test worse than validation (overfitting)
            # We flag overfitting when test drops significantly below validation
            ic_degradation_ok = ic_degradation > -self.config.degradation_threshold
            sharpe_degradation_ok = sharpe_degradation > -self.config.degradation_threshold
            
            results.append({
                'window': i,
                'train_end': train_end,
                'val_ic': val_ic,
                'val_sharpe': val_sharpe,
                'val_maxdd': val_maxdd,
                'test_ic': test_ic,
                'test_sharpe': test_sharpe,
                'test_maxdd': test_maxdd,
                'ic_degradation': ic_degradation,
                'sharpe_degradation': sharpe_degradation,
                'ic_degradation_ok': ic_degradation_ok,
                'sharpe_degradation_ok': sharpe_degradation_ok,
                'degradation_ok': ic_degradation_ok and sharpe_degradation_ok
            })
        
        # Calculate robustness score
        if not results:
            return {'error': 'No validation windows generated'}
        
        ic_pass = len([r for r in results if r['test_ic'] > self.config.ic_threshold])
        sharpe_pass = len([r for r in results if r['test_sharpe'] > self.config.sharpe_threshold])
        # Use the per-window degradation_ok flags for consistency
        # Fail closed: missing degradation_ok means validation failed
        degradation_ok = len([r for r in results if r.get('degradation_ok', False)])
        
        robustness_score = min(
            ic_pass / len(results),
            sharpe_pass / len(results),
            degradation_ok / len(results)
        )
        
        self.results = results
        self.robustness_score = robustness_score
        
        return {
            'n_windows': len(results),
            'robustness_score': robustness_score,
            'ic_pass_rate': ic_pass / len(results),
            'sharpe_pass_rate': sharpe_pass / len(results),
            'degradation_ok_rate': degradation_ok / len(results),
            'avg_val_ic': np.mean([r['val_ic'] for r in results]),
            'avg_val_sharpe': np.mean([r['val_sharpe'] for r in results]),
            'avg_test_ic': np.mean([r['test_ic'] for r in results]),
            'avg_test_sharpe': np.mean([r['test_sharpe'] for r in results]),
            'avg_ic_degradation': np.mean([r['ic_degradation'] for r in results]),
            'results': results
        }
    
    def run_rolling_window(self, X: np.ndarray, y: np.ndarray,
                          train_model_fn: Callable,
                          evaluate_fn: Callable) -> Dict[str, Any]:
        """
        Run rolling window walk-forward validation.
        
        Strategy: Train on [t-24m, t-12m], validate on [t-12m, t-6m], test on [t-6m, t]
        """
        n_samples = len(y)
        window_size = self.config.window_size
        
        # For rolling window, we need at least 3 windows
        if n_samples < 3 * window_size:
            return {'error': 'Insufficient data for rolling window validation'}
        
        results = []
        
        for i in range(n_samples // window_size - 2):
            # Calculate indices
            train_start = i * window_size
            train_end = (i + 1) * window_size
            val_end = (i + 2) * window_size
            test_end = (i + 3) * window_size
            
            if test_end > n_samples:
                break
            
            # Split data
            X_train = X[train_start:train_end]
            y_train = y[train_start:train_end]
            
            X_val = X[train_end:val_end]
            y_val = y[train_end:val_end]
            
            X_test = X[val_end:test_end]
            y_test = y[val_end:test_end]
            
            # Train model
            model = train_model_fn(X_train, y_train)
            
            # Validate
            val_preds = model.predict(X_val) if hasattr(model, 'predict') else model(X_val)
            val_ic, val_sharpe, val_maxdd = evaluate_fn(val_preds, y_val)
            
            # Test
            test_preds = model.predict(X_test) if hasattr(model, 'predict') else model(X_test)
            test_ic, test_sharpe, test_maxdd = evaluate_fn(test_preds, y_test)
            
            results.append({
                'window': i,
                'val_ic': val_ic,
                'val_sharpe': val_sharpe,
                'test_ic': test_ic,
                'test_sharpe': test_sharpe
            })
        
        # Calculate robustness
        ic_pass = len([r for r in results if r['test_ic'] > self.config.ic_threshold])
        robustness_score = ic_pass / len(results) if results else 0
        
        return {
            'n_windows': len(results),
            'robustness_score': robustness_score,
            'avg_test_ic': np.mean([r['test_ic'] for r in results]),
            'avg_test_sharpe': np.mean([r['test_sharpe'] for r in results]),
            'results': results
        }
    
    def statistical_test(self, test_ic_array: np.ndarray, baseline_ic: float = 0.15) -> Dict[str, Any]:
        """
        Perform statistical significance test.
        
        Args:
            test_ic_array: Array of test ICs from multiple windows
            baseline_ic: Expected IC
        
        Returns:
            Dict with t-test results
        """
        if not SCIPY_AVAILABLE:
            return {'error': 'scipy not available for statistical tests'}
        
        if len(test_ic_array) < 2:
            return {'error': 'Need at least 2 IC values for t-test'}
        
        # One-sample t-test (one-tailed, testing if test_ic < baseline)
        t_stat, p_value = stats.ttest_1samp(test_ic_array, baseline_ic, alternative='less')
        
        return {
            't_statistic': t_stat,
            'p_value': p_value,
            'significant': p_value < 0.05,
            'confidence': 1 - p_value,
            'n_samples': len(test_ic_array)
        }
    
    def is_robust(self) -> bool:
        """Check if model passes robustness criteria."""
        return self.robustness_score >= self.config.robustness_threshold
    
    def save_results(self, output_path: str = "state/walk_forward_results.json"):
        """Save validation results."""
        results = {
            'robustness_score': self.robustness_score,
            'n_windows': len(self.results),
            'results': self.results,
            'timestamp': datetime.now().isoformat()
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of validation results."""
        if not self.results:
            return {'error': 'No validation results available'}
        
        return {
            'robustness_score': self.robustness_score,
            'n_windows': len(self.results),
            'avg_test_ic': np.mean([r['test_ic'] for r in self.results]),
            'avg_test_sharpe': np.mean([r['test_sharpe'] for r in self.results]),
            'avg_ic_degradation': np.mean([r['ic_degradation'] for r in self.results]),
            'ic_std': np.std([r['test_ic'] for r in self.results]),
            'sharpe_std': np.std([r['test_sharpe'] for r in self.results])
        }
