"""
Hyperparameter Autotuner - V21 Institutional
Uses Optuna for Bayesian hyperparameter optimization.
"""

from dataclasses import dataclass
from typing import Dict, List, Callable, Optional, Any
import numpy as np

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False


@dataclass
class TuneResult:
    """Result from hyperparameter tuning."""
    model_name: str
    best_params: Dict[str, Any]
    best_score: float
    n_trials: int
    study_best_value: float
    study_best_params: Dict[str, Any]


class HyperparameterAutotuner:
    """Bayesian hyperparameter optimization using Optuna.
    
    Supports Ridge, XGBoost, LightGBM with predefined search spaces.
    Uses TPE (Tree-structured Parzen Estimator) sampler.
    """
    
    SEARCH_SPACES = {
        "ridge": {
            "learning_rate": [0.001, 0.005, 0.01, 0.02],
            "n_iterations": [50, 100, 200, 400],
            "l2_lambda": [0.0, 0.01, 0.05, 0.1, 0.2],
            "train_ratio": [0.6, 0.7, 0.8]
        },
        "xgboost": {
            "max_depth": [3, 4, 5, 6],
            "eta": [0.01, 0.03, 0.05, 0.1],
            "subsample": [0.6, 0.8, 1.0],
            "colsample_bytree": [0.6, 0.8, 1.0],
            "min_child_weight": [1, 3, 5],
            "reg_lambda": [0.1, 1.0, 5.0],
            "n_estimators": [100, 200, 400]
        },
        "lightgbm": {
            "num_leaves": [15, 31, 63],
            "max_depth": [-1, 4, 6, 8],
            "learning_rate": [0.01, 0.03, 0.05, 0.1],
            "feature_fraction": [0.6, 0.8, 1.0],
            "bagging_fraction": [0.6, 0.8, 1.0],
            "min_data_in_leaf": [20, 50, 100],
            "lambda_l2": [0.0, 0.1, 1.0, 5.0],
            "n_estimators": [100, 200, 400]
        }
    }
    
    def __init__(
        self,
        seed: int = 42,
        n_trials: int = 50,
        timeout: Optional[int] = None
    ):
        if not OPTUNA_AVAILABLE:
            raise ImportError("optuna is required. Install with: pip install optuna")
        
        self.seed = seed
        self.n_trials = n_trials
        self.timeout = timeout
        self.study: Optional[optuna.Study] = None
    
    def _create_objective(
        self,
        model_name: str,
        train_data: Any,
        train_labels: Any,
        val_data: Any,
        val_labels: Any
    ) -> Callable:
        """Create objective function for Optuna."""
        
        def objective(trial: optuna.Trial) -> float:
            # Sample parameters
            params = self._sample_params(trial, model_name)
            
            # Train model (simplified - would use actual model in production)
            # Here we simulate with a simple function
            score = self._simulate_training(params, train_data, train_labels, val_data, val_labels)
            
            return score
        
        return objective
    
    def _sample_params(self, trial: optuna.Trial, model_name: str) -> Dict[str, Any]:
        """Sample parameters from search space."""
        params = {}
        space = self.SEARCH_SPACES.get(model_name.lower(), {})
        
        for param_name, param_values in space.items():
            params[param_name] = trial.suggest_categorical(param_name, param_values)
        
        return params
    
    def _simulate_training(
        self,
        params: Dict[str, Any],
        train_data: Any,
        train_labels: Any,
        val_data: Any,
        val_labels: Any
    ) -> float:
        """Simulate model training and evaluation.
        
        In production, this would train the actual model.
        """
        # Simplified simulation - in production, use real training
        # Score based on parameter combinations
        score = 0.5  # Base score
        
        # Add some variance based on parameters
        for k, v in params.items():
            if isinstance(v, (int, float)):
                score += v * 0.01
        
        # Add randomness
        score += np.random.randn() * 0.1
        
        return max(0.0, min(1.0, score))
    
    def tune(
        self,
        model_name: str,
        train_data: Any,
        train_labels: Any,
        val_data: Any,
        val_labels: Any,
        direction: str = "maximize"
    ) -> TuneResult:
        """Run hyperparameter optimization.
        
        Args:
            model_name: Name of model (ridge, xgboost, lightgbm)
            train_data: Training data
            train_labels: Training labels
            val_data: Validation data
            val_labels: Validation labels
            direction: Optimization direction (maximize/minimize)
            
        Returns:
            TuneResult with best parameters
        """
        # Create study
        study = optuna.create_study(
            direction=direction,
            sampler=optuna.samplers.TPESampler(seed=self.seed),
            pruner=optuna.pruners.MedianPruner(
                n_startup_trials=5,
                n_warmup_steps=10
            )
        )
        
        # Create objective
        objective = self._create_objective(
            model_name, train_data, train_labels, val_data, val_labels
        )
        
        # Run optimization
        study.optimize(
            objective,
            n_trials=self.n_trials,
            timeout=self.timeout,
            show_progress_bar=False
        )
        
        best_params = study.best_params
        best_score = study.best_value
        
        return TuneResult(
            model_name=model_name,
            best_params=best_params,
            best_score=best_score,
            n_trials=self.n_trials,
            study_best_value=study.best_value,
            study_best_params=study.best_params
        )
    
    def get_search_space(self, model_name: str) -> Dict[str, List]:
        """Get search space for a model."""
        return self.SEARCH_SPACES.get(model_name.lower(), {})
