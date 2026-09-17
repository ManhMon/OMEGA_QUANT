"""
Hyperopt Layer - Walk-Forward Validation with Bayesian Optimization (P0-2)

This module implements hyperparameter optimization with strict PIT compliance:
- Uses TimeSeriesSplit for walk-forward validation
- Train/Val/Test split ensures no future data leakage
- Bayesian optimization (gp_minimize) for efficient hyperparameter search
- Only train data is used for optimization, val data for evaluation (1 time only)

Usage:
    hyperopt = HyperoptLayer(n_splits=5, n_trials=50)
    best_params = hyperopt.optimize(X_train, y_train, X_val, y_val)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Callable
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from skopt import gp_minimize
from skopt.space import Real, Integer, Categorical
from skopt.utils import use_named_args
import warnings


@dataclass
class HyperoptConfig:
    """Configuration for Hyperopt Layer."""
    n_splits: int = 5  # Number of walk-forward splits
    n_trials: int = 50  # Number of Bayesian optimization trials
    random_state: int = 42
    n_jobs: int = 1  # Windows fix: set to 1 to avoid 'Access is denied' errors
    verbose: bool = True


@dataclass
class HyperoptResult:
    """Result from hyperparameter optimization."""
    best_params: Dict[str, Any]
    best_score: float
    cv_scores: List[float]
    optimization_history: List[Dict[str, Any]]
    n_trials: int
    n_splits: int


class HyperoptLayer:
    """
    Walk-Forward Hyperparameter Optimization with PIT compliance.
    
    Key features:
    - TimeSeriesSplit ensures train < val < test ordering
    - Bayesian optimization (gp_minimize) for efficient search
    - No data leakage: hyperopt only sees train data during optimization
    - Validation data used ONCE for final evaluation
    """
    
    def __init__(self, config: Optional[HyperoptConfig] = None):
        """
        Initialize Hyperopt Layer.
        
        Args:
            config: Hyperopt configuration
        """
        self.config = config or HyperoptConfig()
        self.best_params: Optional[Dict[str, Any]] = None
        self.best_score: Optional[float] = None
        self.optimization_history: List[Dict[str, Any]] = []
    
    def optimize(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        model_type: str = "lightgbm",
        objective_fn: Optional[Callable] = None,
        search_space: Optional[Dict[str, Any]] = None
    ) -> HyperoptResult:
        """
        Optimize hyperparameters using walk-forward validation.
        
        Args:
            X_train: Training features (PIT-safe, historical only)
            y_train: Training targets
            X_val: Validation features (optional, for final evaluation)
            y_val: Validation targets (optional)
            model_type: Model type ('lightgbm', 'xgboost', 'catboost')
            objective_fn: Custom objective function (optional)
            search_space: Custom search space (optional)
            
        Returns:
            HyperoptResult with best parameters and scores
        """
        if X_train is None or y_train is None:
            raise ValueError("X_train and y_train cannot be None")
        
        if len(X_train) != len(y_train):
            raise ValueError(f"X_train and y_train length mismatch: {len(X_train)} != {len(y_train)}")
        
        # Define search space based on model type
        if search_space is None:
            search_space = self._get_default_search_space(model_type)
        
        # Define objective function
        if objective_fn is None:
            objective_fn = self._get_default_objective(model_type, X_train, y_train)
        
        # Run Bayesian optimization
        if self.config.verbose:
            print(f"Starting Bayesian optimization with {self.config.n_trials} trials...")
        
        # Convert search space to skopt format with named dimensions
        dimensions = []
        param_names = []
        for param_name, param_space in search_space.items():
            param_names.append(param_name)
            # Set the name attribute for the dimension
            param_space.name = param_name
            dimensions.append(param_space)
        
        # Wrap objective function to accept list of params
        @use_named_args(dimensions)
        def objective_wrapper(**params):
            score = objective_fn(params)
            self.optimization_history.append({
                'params': params.copy(),
                'score': score
            })
            return -score  # Minimize negative score (maximize score)
        
        # Run optimization
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = gp_minimize(
                objective_wrapper,
                dimensions,
                n_calls=self.config.n_trials,
                n_initial_points=min(self.config.n_trials // 2, 10),  # Use half of trials or 10, whichever is smaller
                random_state=self.config.random_state,
                n_jobs=self.config.n_jobs,
                verbose=self.config.verbose
            )
        
        # Extract best parameters
        self.best_params = {
            param_names[i]: result.x[i] 
            for i in range(len(param_names))
        }
        self.best_score = -result.fun  # Convert back to positive score
        
        # Evaluate on validation set if provided
        val_score = None
        if X_val is not None and y_val is not None:
            val_score = self._evaluate_on_val(
                self.best_params, 
                X_train, y_train, 
                X_val, y_val, 
                model_type
            )
            if self.config.verbose:
                print(f"Validation score: {val_score:.4f}")
        
        # Compute CV scores from optimization history
        cv_scores = [h['score'] for h in self.optimization_history]
        
        return HyperoptResult(
            best_params=self.best_params,
            best_score=self.best_score,
            cv_scores=cv_scores,
            optimization_history=self.optimization_history,
            n_trials=self.config.n_trials,
            n_splits=self.config.n_splits
        )
    
    def _get_default_search_space(self, model_type: str) -> Dict[str, Any]:
        """Get default hyperparameter search space for model type."""
        if model_type == "lightgbm":
            return {
                'learning_rate': Real(0.01, 0.3, prior='log-uniform'),
                'num_leaves': Integer(20, 150),
                'max_depth': Integer(3, 12),
                'min_child_samples': Integer(10, 100),
                'subsample': Real(0.6, 1.0),
                'colsample_bytree': Real(0.6, 1.0),
                'reg_alpha': Real(1e-8, 10.0, prior='log-uniform'),
                'reg_lambda': Real(1e-8, 10.0, prior='log-uniform')
            }
        elif model_type == "xgboost":
            return {
                'learning_rate': Real(0.01, 0.3, prior='log-uniform'),
                'max_depth': Integer(3, 12),
                'min_child_weight': Integer(1, 10),
                'subsample': Real(0.6, 1.0),
                'colsample_bytree': Real(0.6, 1.0),
                'gamma': Real(0.0, 5.0),
                'reg_alpha': Real(1e-8, 10.0, prior='log-uniform'),
                'reg_lambda': Real(1e-8, 10.0, prior='log-uniform')
            }
        elif model_type == "catboost":
            return {
                'learning_rate': Real(0.01, 0.3, prior='log-uniform'),
                'depth': Integer(4, 10),
                'l2_leaf_reg': Real(1.0, 10.0),
                'border_count': Integer(32, 255),
                'bagging_temperature': Real(0.0, 1.0)
            }
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
    
    def _get_default_objective(
        self, 
        model_type: str, 
        X_train: np.ndarray, 
        y_train: np.ndarray
    ) -> Callable:
        """Get default objective function for model type."""
        
        def objective(params: Dict[str, Any]) -> float:
            """
            Objective function using walk-forward cross-validation.
            
            Returns:
                Mean CV score (higher is better)
            """
            # TimeSeriesSplit for walk-forward validation
            tscv = TimeSeriesSplit(n_splits=self.config.n_splits)
            cv_scores = []
            
            for train_idx, val_idx in tscv.split(X_train):
                X_fold_train = X_train[train_idx]
                y_fold_train = y_train[train_idx]
                X_fold_val = X_train[val_idx]
                y_fold_val = y_train[val_idx]
                
                # Train model on fold
                model = self._train_model(
                    model_type, 
                    params, 
                    X_fold_train, 
                    y_fold_train
                )
                
                # Evaluate on validation fold (1 time only)
                score = self._evaluate_model(
                    model, 
                    X_fold_val, 
                    y_fold_val
                )
                cv_scores.append(score)
            
            # Return mean CV score
            return float(np.mean(cv_scores))
        
        return objective
    
    def _train_model(
        self, 
        model_type: str, 
        params: Dict[str, Any], 
        X: np.ndarray, 
        y: np.ndarray
    ):
        """Train model with given parameters."""
        if model_type == "lightgbm":
            import lightgbm as lgb
            model = lgb.LGBMRegressor(
                **params,
                n_estimators=100,
                random_state=self.config.random_state,
                verbose=-1
            )
        elif model_type == "xgboost":
            import xgboost as xgb
            model = xgb.XGBRegressor(
                **params,
                n_estimators=100,
                random_state=self.config.random_state,
                verbosity=0
            )
        elif model_type == "catboost":
            from catboost import CatBoostRegressor
            model = CatBoostRegressor(
                **params,
                iterations=100,
                random_state=self.config.random_state,
                verbose=False
            )
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
        
        model.fit(X, y)
        return model
    
    def _evaluate_model(self, model, X: np.ndarray, y: np.ndarray) -> float:
        """Evaluate model using IC (Information Coefficient)."""
        y_pred = model.predict(X)
        
        # Compute IC (Spearman correlation between predictions and targets)
        from scipy.stats import spearmanr
        ic, _ = spearmanr(y_pred, y)
        
        return float(ic) if not np.isnan(ic) else 0.0
    
    def _evaluate_on_val(
        self,
        params: Dict[str, Any],
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        model_type: str
    ) -> float:
        """Evaluate best parameters on validation set (1 time only)."""
        # Train on full training set
        model = self._train_model(model_type, params, X_train, y_train)
        
        # Evaluate on validation set
        val_score = self._evaluate_model(model, X_val, y_val)
        
        return val_score
    
    def get_best_params(self) -> Optional[Dict[str, Any]]:
        """Get best hyperparameters from last optimization."""
        return self.best_params
    
    def get_optimization_history(self) -> List[Dict[str, Any]]:
        """Get full optimization history."""
        return self.optimization_history
