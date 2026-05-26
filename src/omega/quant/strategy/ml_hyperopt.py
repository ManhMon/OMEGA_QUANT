"""
ML Hyperparameter Auto-Tuner - Institutional Grade.

Model-agnostic hyperparameter optimization for Ridge/Linear, XGBoost, LightGBM.
Supports grid search and random search with deterministic seeding.

PIT Safety: Tuner is stateless w.r.t. data ordering. Caller must ensure
    train/val split respects temporal ordering (use PurgedTimeSeriesSplit).
Vectorization: Search space generation is vectorized via itertools.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

__all__ = [
    "AutoTuneResult",
    "MLHyperparameterAutotuner",
]


@dataclass
class AutoTuneResult:
    """Result from hyperparameter tuning."""

    model_name: str
    best_params: Dict[str, Any]
    best_score: float
    trials: int


class MLHyperparameterAutotuner:
    """
    Auto-tune ML hyperparameters for Ridge/Linear, XGBoost, LightGBM.

    Tuner is model-agnostic: caller provides objective_fn(params) -> score.
    Uses deterministic seed for reproducibility.

    Usage:
        tuner = MLHyperparameterAutotuner(seed=42)
        result = tuner.tune("xgboost", objective_fn, n_trials=50)
        print(result.best_params)
    """

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def get_search_space(self, model_name: str) -> Dict[str, List[Any]]:
        """
        Return predefined search space for a given model type.

        Args:
            model_name: One of 'ridge', 'linear', 'xgboost', 'xgb',
                'lightgbm', 'lgbm'.

        Returns:
            Dict mapping parameter names to lists of candidate values.

        Raises:
            ValueError: If model_name is not supported.
        """
        name = model_name.lower()

        if name in ("ridge", "linear", "ridge_linear"):
            return {
                "learning_rate": [0.001, 0.005, 0.01, 0.02],
                "n_iterations": [50, 100, 200, 400],
                "l2_lambda": [0.0, 0.01, 0.05, 0.1, 0.2],
                "train_ratio": [0.6, 0.7, 0.8],
            }

        if name in ("xgboost", "xgb"):
            return {
                "max_depth": [3, 4, 5, 6],
                "eta": [0.01, 0.03, 0.05, 0.1],
                "subsample": [0.6, 0.8, 1.0],
                "colsample_bytree": [0.6, 0.8, 1.0],
                "min_child_weight": [1, 3, 5],
                "reg_lambda": [0.1, 1.0, 5.0],
                "n_estimators": [100, 200, 400],
            }

        if name in ("lightgbm", "lgbm"):
            return {
                "num_leaves": [15, 31, 63],
                "max_depth": [-1, 4, 6, 8],
                "learning_rate": [0.01, 0.03, 0.05, 0.1],
                "feature_fraction": [0.6, 0.8, 1.0],
                "bagging_fraction": [0.6, 0.8, 1.0],
                "min_data_in_leaf": [20, 50, 100],
                "lambda_l2": [0.0, 0.1, 1.0, 5.0],
                "n_estimators": [100, 200, 400],
            }

        raise ValueError(
            f"Unsupported model for autotune: {model_name}. "
            f"Supported: ridge, linear, xgboost, xgb, lightgbm, lgbm"
        )

    def tune(
        self,
        model_name: str,
        objective_fn: Callable[[Dict[str, Any]], float],
        n_trials: int = 50,
        mode: str = "random",
    ) -> AutoTuneResult:
        """
        Run hyperparameter search.

        Args:
            model_name: Model type for search space selection.
            objective_fn: Callable that takes params dict and returns a score
                (higher is better).
            n_trials: Maximum number of parameter combinations to evaluate.
            mode: 'random' for random search, 'grid' for grid search.

        Returns:
            AutoTuneResult with best parameters and score.

        Raises:
            ValueError: If n_trials <= 0 or mode is invalid.
        """
        if n_trials <= 0:
            raise ValueError("n_trials must be > 0")

        space = self.get_search_space(model_name)

        if mode == "grid":
            candidates = self._all_grid_candidates(space)[:n_trials]
        elif mode == "random":
            candidates = self._sample_candidates(space, n_trials)
        else:
            raise ValueError("mode must be 'random' or 'grid'")

        best_score = float("-inf")
        best_params: Dict[str, Any] = {}
        evaluated = 0

        for params in candidates:
            score = float(objective_fn(params))
            evaluated += 1
            if score > best_score:
                best_score = score
                best_params = params

        return AutoTuneResult(
            model_name=model_name,
            best_params=best_params,
            best_score=best_score,
            trials=evaluated,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _all_grid_candidates(
        self, search_space: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """Generate all grid combinations (Cartesian product)."""
        keys = list(search_space.keys())
        values = [search_space[k] for k in keys]
        return [
            dict(zip(keys, combo)) for combo in itertools.product(*values)
        ]

    def _sample_candidates(
        self, search_space: Dict[str, List[Any]], n_trials: int
    ) -> List[Dict[str, Any]]:
        """Generate random parameter combinations."""
        keys = list(search_space.keys())
        return [
            {k: self.rng.choice(search_space[k]) for k in keys}
            for _ in range(n_trials)
        ]
