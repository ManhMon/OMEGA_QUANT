"""
Online Model Updater - Continuous Learning Module
Layer 06: Data Governance

Implements incremental model updates using .partial_fit() with T+3 embargo
to prevent look-ahead bias. Integrates with AlphaDecayMonitor for adaptive learning.

Key Features:
- 100% Vectorized operations
- PIT-Safe: T+3 embargo enforced
- Only supports models with .partial_fit() method
- Connects to AlphaDecayMonitor for decay detection
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Protocol
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import warnings


@dataclass
class OnlineUpdaterConfig:
    """Configuration for Online Model Updater"""
    embargo_days: int = 3  # T+3 embargo period
    min_samples_update: int = 50  # Minimum samples before update
    update_frequency: int = 5  # Update every N days
    decay_threshold: float = 0.3  # Trigger retraining if decay > threshold
    max_history_days: int = 252  # Rolling window for training data
    

class PartialFitModel(Protocol):
    """Protocol for models that support incremental learning"""
    def partial_fit(self, X: np.ndarray, y: np.ndarray, **kwargs) -> Any:
        """Incrementally fit the model"""
        ...
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions"""
        ...


class AlphaDecayMonitor:
    """
    Monitors alpha decay over time using rolling IC correlation.
    Triggers retraining when decay exceeds threshold.
    """
    def __init__(self, window: int = 20):
        self.window = window
        self.ic_history: List[float] = []
        
    def update(self, predictions: np.ndarray, actuals: np.ndarray) -> float:
        """
        Compute IC and update history.
        
        Args:
            predictions: Model predictions (n_samples,)
            actuals: Actual returns (n_samples,)
            
        Returns:
            Current IC value
        """
        # Vectorized IC computation
        pred_mean = np.mean(predictions)
        actual_mean = np.mean(actuals)
        
        pred_centered = predictions - pred_mean
        actual_centered = actuals - actual_mean
        
        numerator = np.sum(pred_centered * actual_centered)
        denominator = np.sqrt(np.sum(pred_centered ** 2) * np.sum(actual_centered ** 2))
        
        ic = numerator / (denominator + 1e-10)
        self.ic_history.append(ic)
        
        # Keep only recent window
        if len(self.ic_history) > self.window:
            self.ic_history = self.ic_history[-self.window:]
            
        return ic
    
    def get_decay_rate(self) -> float:
        """
        Compute decay rate as percentage drop from peak IC.
        
        Returns:
            Decay rate (0.0 to 1.0)
        """
        if len(self.ic_history) < 2:
            return 0.0
            
        ic_array = np.array(self.ic_history)
        peak_ic = np.max(ic_array)
        current_ic = ic_array[-1]
        
        if peak_ic <= 0:
            return 0.0
            
        decay = (peak_ic - current_ic) / peak_ic
        return max(0.0, decay)


class OnlineModelUpdater:
    """
    Manages incremental model updates with PIT-safe embargo and decay monitoring.
    
    Only supports models with .partial_fit() method (e.g., SGDRegressor, 
    PassiveAggressiveRegressor, MiniBatchKMeans).
    """
    
    # Approved whitelist for partial_fit models
    APPROVED_MODELS = {
        'SGDRegressor',
        'PassiveAggressiveClassifier',
        'PassiveAggressiveRegressor',
        'MiniBatchKMeans'
    }
    
    def __init__(
        self, 
        model: PartialFitModel,
        config: Optional[OnlineUpdaterConfig] = None,
        skip_whitelist_check: bool = False
    ):
        """
        Initialize the updater.
        
        Args:
            model: Model instance with .partial_fit() method
            config: Configuration object
            skip_whitelist_check: If True, skip whitelist validation (for testing only)
        """
        if not hasattr(model, 'partial_fit'):
            raise ValueError(
                f"Model {type(model).__name__} does not support .partial_fit(). "
                "Only incremental learning models are supported."
            )
        
        # Whitelist enforcement: only approved models allowed
        if not skip_whitelist_check:
            model_class_name = type(model).__name__
            if model_class_name not in self.APPROVED_MODELS:
                raise ValueError(
                    f"Model {model_class_name} not in approved partial_fit whitelist. "
                    f"Allowed models: {', '.join(sorted(self.APPROVED_MODELS))}"
                )
            
        self.model = model
        self.config = config or OnlineUpdaterConfig()
        self.decay_monitor = AlphaDecayMonitor(window=20)
        
        # State tracking
        self.last_update_date: Optional[pd.Timestamp] = None
        self.update_count: int = 0
        self.pending_data: List[Dict[str, Any]] = []
        
    def add_observation(
        self, 
        features: np.ndarray, 
        target: float,
        timestamp: pd.Timestamp
    ) -> None:
        """
        Add a new observation to the pending queue (with embargo).
        
        Args:
            features: Feature vector (1D array)
            target: Target value (actual return)
            timestamp: Observation timestamp
        """
        self.pending_data.append({
            'features': features,
            'target': target,
            'timestamp': timestamp
        })
        
    def _apply_embargo(self, current_date: pd.Timestamp) -> List[Dict[str, Any]]:
        """
        Apply T+3 embargo: only return data older than embargo_days.
        Strict enforcement: data from (current_date - embargo_days) or earlier is safe.
        
        NOTE: This does NOT remove data from pending_data. Data accumulates until
        manually cleared or max_history_days is exceeded.
        
        Args:
            current_date: Current date for embargo calculation
            
        Returns:
            List of embargoed observations ready for training
        """
        # Strict embargo: only data strictly older than (current_date - embargo_days)
        embargo_cutoff = current_date - pd.Timedelta(days=self.config.embargo_days)
        
        # Vectorized filtering: use < for strict enforcement
        embargoed = [
            obs for obs in self.pending_data 
            if obs['timestamp'] < embargo_cutoff
        ]
        
        # Apply max_history_days rolling window
        history_cutoff = current_date - pd.Timedelta(days=self.config.max_history_days)
        self.pending_data = [
            obs for obs in self.pending_data 
            if obs['timestamp'] >= history_cutoff
        ]
        
        return embargoed
    
    def update(self, current_date: pd.Timestamp) -> Dict[str, Any]:
        """
        Perform incremental model update if conditions are met.
        
        Args:
            current_date: Current date for embargo and frequency checks
            
        Returns:
            Update status dictionary
        """
        # Check update frequency
        if self.last_update_date is not None:
            days_since_update = (current_date - self.last_update_date).days
            if days_since_update < self.config.update_frequency:
                return {
                    'updated': False,
                    'reason': 'update_frequency_not_met',
                    'days_since_update': days_since_update
                }
        
        # Apply embargo
        embargoed_data = self._apply_embargo(current_date)
        
        # Check minimum samples
        if len(embargoed_data) < self.config.min_samples_update:
            return {
                'updated': False,
                'reason': 'insufficient_samples',
                'available_samples': len(embargoed_data),
                'required_samples': self.config.min_samples_update
            }
        
        # Prepare data (vectorized)
        X = np.vstack([obs['features'] for obs in embargoed_data])
        y = np.array([obs['target'] for obs in embargoed_data])
        
        # Perform partial fit
        self.model.partial_fit(X, y)
        
        # Update decay monitor
        predictions = self.model.predict(X)
        current_ic = self.decay_monitor.update(predictions, y)
        decay_rate = self.decay_monitor.get_decay_rate()
        
        # Update state
        self.last_update_date = current_date
        self.update_count += 1
        
        return {
            'updated': True,
            'samples_used': len(embargoed_data),
            'current_ic': current_ic,
            'decay_rate': decay_rate,
            'update_count': self.update_count,
            'needs_retraining': decay_rate > self.config.decay_threshold
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current updater status.
        
        Returns:
            Status dictionary
        """
        return {
            'update_count': self.update_count,
            'last_update_date': self.last_update_date,
            'pending_observations': len(self.pending_data),
            'decay_rate': self.decay_monitor.get_decay_rate(),
            'ic_history': self.decay_monitor.ic_history.copy()
        }
    
    def reset(self) -> None:
        """Reset updater state (keeps model intact)"""
        self.pending_data.clear()
        self.decay_monitor.ic_history.clear()
        self.last_update_date = None
        self.update_count = 0
