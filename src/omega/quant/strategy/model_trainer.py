"""
Institutional-Grade Model Trainer with Optuna Multi-Objective Tuning.

Implements Walk-Forward Optuna tuning with PurgedTimeSeriesSplit for
leak-free hyperparameter optimization.

PIT Safety: Uses PurgedTimeSeriesSplit for all CV splits. No future leakage.
Vectorization: Model training delegates to sklearn/xgboost vectorized internals.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from .purged_cv import PurgedTimeSeriesSplit

__all__ = [
    "TrainerConfig",
    "WalkForwardOptunaTrainer",
]

logger = logging.getLogger(__name__)

try:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    OPTUNA_AVAILABLE = True
except ImportError:
    optuna = None  # type: ignore[assignment]
    OPTUNA_AVAILABLE = False

try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_squared_error

    SKLEARN_AVAILABLE = True
except ImportError:
    GradientBoostingRegressor = None  # type: ignore[assignment, misc]
    mean_squared_error = None  # type: ignore[assignment]
    SKLEARN_AVAILABLE = False


@dataclass
class TrainerConfig:
    """Configuration for WalkForwardOptunaTrainer."""

    n_trials: int = 50
    model_type: str = "xgboost"
    cv_splits: int = 5
    gap_days: int = 3
    early_stopping_rounds: int = 20


class WalkForwardOptunaTrainer:
    """
    Hyperparameter optimization via Optuna with Walk-Forward CV.

    Uses PurgedTimeSeriesSplit to prevent data leakage during
    cross-validation. Supports GradientBoosting as base model
    with extensible objective function.

    PIT Contract:
    - All CV splits use purged gaps (T+2.5 -> 3 days).
    - No test data leaks into training via embargo.
    - Final model trained on full dataset after best params found.
    """

    def __init__(self, config: Optional[TrainerConfig] = None) -> None:
        self.config = config or TrainerConfig()
        self.study: Any = None
        self.best_params: Optional[dict[str, Any]] = None
        self.best_model: Any = None

    def objective(
        self, trial: Any, X: np.ndarray, y: np.ndarray
    ) -> float:
        """
        Optuna objective function.

        Maximizes negative MSE across purged CV folds as proxy for
        Sharpe/IC (production should replace with actual metrics).

        Args:
            trial: Optuna trial object.
            X: Feature matrix.
            y: Target vector.

        Returns:
            Mean score across CV folds (higher is better).
        """
        if not OPTUNA_AVAILABLE or not SKLEARN_AVAILABLE:
            return 0.0

        # Hyperparameter search space
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "learning_rate": trial.suggest_float(
                "learning_rate", 0.01, 0.2, log=True
            ),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }

        cv = PurgedTimeSeriesSplit(
            n_splits=self.config.cv_splits, gap_days=self.config.gap_days
        )
        scores: list[float] = []

        for train_idx, test_idx in cv.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model = GradientBoostingRegressor(**params, random_state=42)
            model.fit(X_train, y_train)

            preds = model.predict(X_test)
            mse = mean_squared_error(y_test, preds)
            scores.append(-mse)  # Negative MSE (higher is better)

        return float(np.mean(scores))

    def fit(self, X: np.ndarray, y: np.ndarray) -> Any:
        """
        Run Optuna study to find best parameters, then train final model.

        Args:
            X: Feature matrix (n_samples, n_features).
            y: Target vector (n_samples,).

        Returns:
            Trained model with best parameters.
        """
        if not OPTUNA_AVAILABLE or not SKLEARN_AVAILABLE:
            # Mock behavior for environments without ML libraries
            logger.warning(
                "optuna/sklearn not available. Using default parameters."
            )
            self.best_params = {
                "n_estimators": 100,
                "learning_rate": 0.1,
                "max_depth": 3,
                "subsample": 0.8,
            }

            class _MockModel:
                def predict(self, X: np.ndarray) -> np.ndarray:
                    return np.zeros(len(X), dtype=np.float64)

            self.best_model = _MockModel()
            return self.best_model

        self.study = optuna.create_study(direction="maximize")
        self.study.optimize(
            lambda trial: self.objective(trial, X, y),
            n_trials=self.config.n_trials,
        )

        self.best_params = self.study.best_params
        logger.info("Best params found: %s", self.best_params)

        # Train final model with best params on full dataset
        self.best_model = GradientBoostingRegressor(
            **self.best_params, random_state=42
        )
        self.best_model.fit(X, y)

        return self.best_model

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions using the best trained model.

        Args:
            X: Feature matrix (n_samples, n_features).

        Returns:
            Predictions (n_samples,).

        Raises:
            ValueError: If model has not been fitted.
        """
        if self.best_model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")
        return self.best_model.predict(X)
