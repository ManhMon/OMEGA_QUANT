"""
ML Models - Institutional Grade Estimators.

Provides a unified interface (BaseEstimator) for tree-based ML models:
- XGBoost
- LightGBM
- CatBoost

All with graceful fallback if a library is not installed.

PIT Safety: Models are stateless predictors. Caller must ensure train/test
    split respects temporal ordering (use PurgedTimeSeriesSplit).
Vectorization: All predict/fit operations use numpy arrays natively.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np

__all__ = [
    "BaseEstimator",
    "XGBEstimator",
    "LGBEstimator",
    "CatBoostEstimator",
    "ESTIMATOR_REGISTRY",
    "create_estimator",
]

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb

    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import lightgbm as lgb

    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

try:
    import catboost as cb

    CB_AVAILABLE = True
except ImportError:
    CB_AVAILABLE = False


class BaseEstimator(ABC):
    """Abstract base class for all ML estimators in strategy layer."""

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, **kwargs: Any) -> None:
        """Train the model on feature matrix X and target y."""
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Generate predictions for feature matrix X."""
        ...

    @abstractmethod
    def get_feature_importance(self) -> Dict[str, float]:
        """Return feature importance dict {feature_name: importance}."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable model name."""
        ...


class XGBEstimator(BaseEstimator):
    """XGBoost Gradient Boosted Trees estimator."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params: Dict[str, Any] = params or {
            "objective": "reg:squarederror",
            "max_depth": 6,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
        }
        self._model: Any = None
        self._feature_names: list[str] = []

    @property
    def name(self) -> str:
        return "XGBoost"

    def fit(self, X: np.ndarray, y: np.ndarray, **kwargs: Any) -> None:
        """Train XGBoost model. No-op if xgboost not installed."""
        if not XGB_AVAILABLE:
            logger.warning("xgboost not installed. XGBEstimator will not train.")
            return
        params = self.params.copy()
        n_estimators = params.pop("n_estimators", 200)
        self._model = xgb.XGBRegressor(n_estimators=n_estimators, **params)
        self._model.fit(X, y, verbose=False)
        self._feature_names = [f"f{i}" for i in range(X.shape[1])]

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict using trained model. Returns zeros if not fitted."""
        if self._model is None:
            return np.zeros(len(X), dtype=np.float64)
        return self._model.predict(X)

    def get_feature_importance(self) -> Dict[str, float]:
        """Return feature importance from trained model."""
        if self._model is None:
            return {}
        imp = self._model.feature_importances_
        return {self._feature_names[i]: float(imp[i]) for i in range(len(imp))}


class LGBEstimator(BaseEstimator):
    """LightGBM Gradient Boosted Trees estimator."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params: Dict[str, Any] = params or {
            "objective": "regression",
            "max_depth": 6,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "verbose": -1,
        }
        self._model: Any = None
        self._feature_names: list[str] = []

    @property
    def name(self) -> str:
        return "LightGBM"

    def fit(self, X: np.ndarray, y: np.ndarray, **kwargs: Any) -> None:
        """Train LightGBM model. No-op if lightgbm not installed."""
        if not LGB_AVAILABLE:
            logger.warning("lightgbm not installed. LGBEstimator will not train.")
            return
        self._model = lgb.LGBMRegressor(**self.params)
        self._model.fit(X, y)
        self._feature_names = [f"f{i}" for i in range(X.shape[1])]

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict using trained model. Returns zeros if not fitted."""
        if self._model is None:
            return np.zeros(len(X), dtype=np.float64)
        return self._model.predict(X)

    def get_feature_importance(self) -> Dict[str, float]:
        """Return feature importance from trained model."""
        if self._model is None:
            return {}
        imp = self._model.feature_importances_
        return {self._feature_names[i]: float(imp[i]) for i in range(len(imp))}


class CatBoostEstimator(BaseEstimator):
    """CatBoost Gradient Boosted Trees estimator."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params: Dict[str, Any] = params or {
            "depth": 6,
            "learning_rate": 0.05,
            "iterations": 200,
            "l2_leaf_reg": 3.0,
            "random_seed": 42,
            "verbose": 0,
        }
        self._model: Any = None
        self._feature_names: list[str] = []

    @property
    def name(self) -> str:
        return "CatBoost"

    def fit(self, X: np.ndarray, y: np.ndarray, **kwargs: Any) -> None:
        """Train CatBoost model. No-op if catboost not installed."""
        if not CB_AVAILABLE:
            logger.warning("catboost not installed. CatBoostEstimator will not train.")
            return
        self._model = cb.CatBoostRegressor(**self.params)
        self._model.fit(X, y)
        self._feature_names = [f"f{i}" for i in range(X.shape[1])]

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict using trained model. Returns zeros if not fitted."""
        if self._model is None:
            return np.zeros(len(X), dtype=np.float64)
        return self._model.predict(X)

    def get_feature_importance(self) -> Dict[str, float]:
        """Return feature importance from trained model."""
        if self._model is None:
            return {}
        imp = self._model.get_feature_importance()
        return {self._feature_names[i]: float(imp[i]) for i in range(len(imp))}


# Registry of available estimators
ESTIMATOR_REGISTRY: Dict[str, type] = {
    "xgboost": XGBEstimator,
    "lightgbm": LGBEstimator,
    "catboost": CatBoostEstimator,
}


def create_estimator(
    name: str, params: Optional[Dict[str, Any]] = None
) -> BaseEstimator:
    """
    Factory function to create an estimator by name.

    Args:
        name: Estimator name ('xgboost', 'lightgbm', 'catboost').
        params: Optional parameter dict to override defaults.

    Returns:
        Instantiated BaseEstimator subclass.

    Raises:
        ValueError: If name is not in ESTIMATOR_REGISTRY.
    """
    cls = ESTIMATOR_REGISTRY.get(name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown estimator: {name}. "
            f"Available: {list(ESTIMATOR_REGISTRY.keys())}"
        )
    return cls(params=params)
