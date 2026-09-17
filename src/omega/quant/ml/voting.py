"""Voting ensemble implementation.

Weighted voting ensemble for alpha predictions.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from omega.quant.ml.ensemble_config import (
    WeightingScheme,
    EnsembleConfig,
    BaseModelPrediction,
    EnsembleResult,
)

logger = logging.getLogger(__name__)


class VotingEnsemble:
    """
    Weighted voting ensemble for alpha predictions.
    
    Workflow:
    1. Collect predictions from base models
    2. Compute weights based on IC/Sharpe/Variance
    3. Generate weighted average (100% vectorized)
    4. Apply IC gating
    
    PIT Safety:
    - All base model predictions must be PIT-safe
    - Weights computed on historical data only
    - No look-ahead bias in weight calculation
    """
    
    def __init__(self, config: Optional[EnsembleConfig] = None):
        self.config = config or EnsembleConfig()
        self.weights: Dict[str, float] = {}
        self.is_fitted = False
        
    def _compute_ic(self, predictions: pd.Series, actuals: pd.Series) -> float:
        """Compute Information Coefficient (Spearman)."""
        aligned = pd.DataFrame({'pred': predictions, 'act': actuals}).dropna()
        if len(aligned) < 10:
            return 0.0
        ic = aligned['pred'].corr(aligned['act'], method='spearman')
        return ic if not pd.isna(ic) else 0.0
    
    def _compute_sharpe(self, returns: pd.Series) -> float:
        """Compute annualized Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        mean_ret = returns.mean()
        std_ret = returns.std()
        if std_ret == 0:
            return 0.0
        return (mean_ret / std_ret) * np.sqrt(252)
    
    def _compute_weights_uniform(self, base_models: List[BaseModelPrediction]) -> Dict[str, float]:
        """Uniform weighting."""
        n = len(base_models)
        return {model.model_name: 1.0 / n for model in base_models}

    def _apply_weight_constraints(self, raw_weights: np.ndarray) -> np.ndarray:
        """Project non-negative weights onto feasible simplex with hard caps."""
        n_weights = len(raw_weights)
        min_total = self.config.min_weight * n_weights
        max_total = self.config.max_weight * n_weights

        if min_total > 1.0 + 1e-12:
            raise ValueError(
                f"Infeasible weight constraints: min_weight ({self.config.min_weight}) "
                f"across {n_weights} models exceeds total weight budget."
            )

        if max_total < 1.0 - 1e-12:
            raise ValueError(
                f"Infeasible weight constraints: max_weight ({self.config.max_weight}) "
                f"across {n_weights} models cannot reach total weight 1.0."
            )

        total = raw_weights.sum()
        if total <= 0:
            normalized = np.full(n_weights, 1.0 / n_weights)
        else:
            normalized = raw_weights / total

        constrained = np.full(n_weights, self.config.min_weight)
        remaining = 1.0 - constrained.sum()

        if remaining <= 1e-12:
            return constrained

        capacities = np.full(
            n_weights,
            max(0.0, self.config.max_weight - self.config.min_weight),
        )
        residual = normalized.copy()
        active = capacities > 1e-12

        while remaining > 1e-12 and active.any():
            active_indices = np.where(active)[0]
            active_residual = residual[active_indices]
            residual_total = active_residual.sum()

            if residual_total <= 1e-12:
                share = remaining / len(active_indices)
                additions = np.minimum(np.full(len(active_indices), share), capacities[active_indices])
            else:
                proposed = remaining * (active_residual / residual_total)
                additions = np.minimum(proposed, capacities[active_indices])

            constrained[active_indices] += additions
            capacities[active_indices] -= additions
            remaining -= additions.sum()
            active = capacities > 1e-12

        if remaining > 1e-8:
            raise ValueError("Unable to satisfy weight constraints while preserving total weight 1.0.")

        return constrained
    
    def _compute_weights_ic(self, base_models: List[BaseModelPrediction]) -> Dict[str, float]:
        """IC-based weighting with normalization."""
        # Filter models by IC threshold
        valid_models = [m for m in base_models if m.ic >= self.config.min_ic_threshold]
        
        if not valid_models:
            logger.warning("No models meet IC threshold, using uniform weights")
            return self._compute_weights_uniform(base_models)
        
        # Compute raw weights (IC)
        raw_weights = np.array([m.ic for m in valid_models])
        raw_weights = np.maximum(raw_weights, 0)  # Ensure non-negative
        
        if raw_weights.sum() == 0:
            return self._compute_weights_uniform(valid_models)
        normalized = self._apply_weight_constraints(raw_weights)
        
        weights = {m.model_name: float(w) for m, w in zip(valid_models, normalized)}
        
        # Zero weight for filtered models
        for model in base_models:
            if model.model_name not in weights:
                weights[model.model_name] = 0.0
        
        return weights
    
    def _compute_weights_sharpe(self, base_models: List[BaseModelPrediction]) -> Dict[str, float]:
        """Sharpe-based weighting."""
        valid_models = [m for m in base_models if m.sharpe > 0]
        
        if not valid_models:
            logger.warning("No models with positive Sharpe, using uniform weights")
            return self._compute_weights_uniform(base_models)

        if len(valid_models) == 1:
            weights = {model.model_name: 0.0 for model in base_models}
            weights[valid_models[0].model_name] = 1.0
            return weights
        
        raw_weights = np.array([m.sharpe for m in valid_models])
        normalized = self._apply_weight_constraints(raw_weights)
        
        weights = {m.model_name: float(w) for m, w in zip(valid_models, normalized)}
        
        for model in base_models:
            if model.model_name not in weights:
                weights[model.model_name] = 0.0
        
        return weights
    
    def _compute_weights_inverse_variance(self, base_models: List[BaseModelPrediction]) -> Dict[str, float]:
        """Inverse variance weighting."""
        valid_models = [m for m in base_models if m.variance > 0]
        
        if not valid_models:
            return self._compute_weights_uniform(base_models)

        if len(valid_models) == 1:
            weights = {model.model_name: 0.0 for model in base_models}
            weights[valid_models[0].model_name] = 1.0
            return weights
        
        inv_var = np.array([1.0 / m.variance for m in valid_models])
        normalized = self._apply_weight_constraints(inv_var)
        
        weights = {m.model_name: float(w) for m, w in zip(valid_models, normalized)}
        
        for model in base_models:
            if model.model_name not in weights:
                weights[model.model_name] = 0.0
        
        return weights
    
    def fit(
        self,
        base_models: List[BaseModelPrediction],
        actuals: pd.Series
    ) -> None:
        """
        Fit ensemble by computing optimal weights.
        
        Args:
            base_models: List of base model predictions
            actuals: Actual returns for weight optimization
        """
        # Compute metrics for each model
        for model in base_models:
            model.ic = self._compute_ic(model.predictions, actuals)
            model.variance = model.predictions.var()
            
            # Compute Sharpe based on prediction-conditioned returns (np.sign(pred) * act)
            aligned = pd.DataFrame({
                'pred': model.predictions,
                'act': actuals
            }).dropna()
            if len(aligned) > 0:
                strategy_returns = np.sign(aligned['pred']) * aligned['act']
                model.sharpe = self._compute_sharpe(strategy_returns)
        
        # Compute weights based on scheme
        if self.config.weighting_scheme == WeightingScheme.UNIFORM:
            self.weights = self._compute_weights_uniform(base_models)
        elif self.config.weighting_scheme == WeightingScheme.IC_WEIGHTED:
            self.weights = self._compute_weights_ic(base_models)
        elif self.config.weighting_scheme == WeightingScheme.SHARPE_WEIGHTED:
            self.weights = self._compute_weights_sharpe(base_models)
        elif self.config.weighting_scheme == WeightingScheme.INVERSE_VARIANCE:
            self.weights = self._compute_weights_inverse_variance(base_models)
        
        self.is_fitted = True
        logger.info(f"Voting ensemble fitted with weights: {self.weights}")
    
    def predict(self, base_models: List[BaseModelPrediction]) -> EnsembleResult:
        """
        Generate ensemble predictions using fitted weights.
        
        Args:
            base_models: List of base model predictions
            
        Returns:
            EnsembleResult with weighted predictions
        """
        if not self.is_fitted:
            logger.warning("Ensemble not fitted, using uniform weights")
            self.weights = self._compute_weights_uniform(base_models)
        
        # Align all predictions to common index
        pred_df = pd.DataFrame({
            model.model_name: model.predictions
            for model in base_models
        })
        
        # Vectorized weighted average
        weight_array = np.array([self.weights.get(col, 0.0) for col in pred_df.columns])
        ensemble_pred = (pred_df.values @ weight_array).flatten()
        ensemble_series = pd.Series(ensemble_pred, index=pred_df.index)
        
        return EnsembleResult(
            predictions=ensemble_series,
            weights=self.weights.copy(),
            metrics={'n_models': len(base_models)}
        )


def create_voting_ensemble(
    base_predictions: Dict[str, pd.Series],
    actuals: pd.Series,
    config: Optional[EnsembleConfig] = None
) -> EnsembleResult:
    """
    Convenience function to create and fit voting ensemble.
    
    Args:
        base_predictions: Dict mapping model_name -> predictions
        actuals: Actual returns
        config: Optional ensemble config
        
    Returns:
        EnsembleResult with weighted predictions
    """
    base_models = [
        BaseModelPrediction(model_name=name, predictions=pred)
        for name, pred in base_predictions.items()
    ]
    
    ensemble = VotingEnsemble(config)
    ensemble.fit(base_models, actuals)
    return ensemble.predict(base_models)
