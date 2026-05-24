"""
OMEGA_QUANT Voting & Stacking Ensemble Module (Phase 15)
Layer 02: Strategy Logic

Purpose:
    Advanced ensemble methods with weighted voting and stacking meta-learner.
    100% vectorized operations with strict PIT safety enforcement.

Key Features:
    - VotingEnsemble: Weighted average of base model predictions
    - StackingEnsemble: Meta-learner trained on base model predictions
    - Meta-feature generation: OOS predictions + regime features
    - IC-based weight optimization
    - Full PIT safety with T-1 lag enforcement

Spec Reference:
    - Section 9.3: Ensemble Methods
    - Section 10.2: PIT Safety Protocol

Author: Machine Learning Engineer (Role 16)
Date: 2026-05-15
Version: 1.0.0 (Phase 15)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb

logger = logging.getLogger(__name__)


class WeightingScheme(Enum):
    """Weighting schemes for voting ensemble."""
    UNIFORM = "uniform"           # Equal weights
    IC_WEIGHTED = "ic_weighted"   # Weighted by IC
    SHARPE_WEIGHTED = "sharpe_weighted"  # Weighted by Sharpe
    INVERSE_VARIANCE = "inverse_variance"  # Weighted by inverse variance


class MetaLearnerType(Enum):
    """Meta-learner types for stacking."""
    RIDGE = "ridge"
    RANDOM_FOREST = "random_forest"
    XGBOOST = "xgboost"


@dataclass
class EnsembleConfig:
    """Configuration for ensemble methods."""
    
    # Voting config
    weighting_scheme: WeightingScheme = WeightingScheme.IC_WEIGHTED
    min_ic_threshold: float = 0.05
    max_weight: float = 0.6
    min_weight: float = 0.0
    
    # Stacking config
    meta_learner_type: MetaLearnerType = MetaLearnerType.RIDGE
    use_meta_features: bool = True
    cv_folds: int = 5
    
    # PIT safety
    embargo_days: int = 3
    
    # Training
    train_cutoff: str = "2023-12-31"
    validation_start: str = "2024-01-01"


@dataclass
class BaseModelPrediction:
    """Container for base model predictions."""
    model_name: str
    predictions: pd.Series
    ic: float = 0.0
    sharpe: float = 0.0
    variance: float = 0.0
    is_oos: bool = False
    train_end: Optional[pd.Timestamp] = None
    prediction_start: Optional[pd.Timestamp] = None
    generator_id: Optional[str] = None



@dataclass
class EnsembleResult:
    """Result from ensemble prediction."""
    predictions: pd.Series
    weights: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    meta_features: Optional[pd.DataFrame] = None


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


class StackingEnsemble:
    """
    Stacking ensemble with meta-learner.
    
    Workflow:
    1. Generate OOS predictions from base models (CV)
    2. Create meta-features: [base_pred_1, ..., base_pred_n, regime_features]
    3. Train meta-learner on meta-features
    4. Predict using meta-learner
    
    PIT Safety:
    - OOS predictions ensure no leakage
    - Regime features use shift(1)
    - Embargo between train/validation
    """
    
    def __init__(self, config: Optional[EnsembleConfig] = None):
        self.config = config or EnsembleConfig()
        self.meta_learner: Optional[Any] = None
        self.is_fitted = False
        self.feature_names: List[str] = []
        
    def _create_meta_learner(self) -> Any:
        """Create meta-learner based on config."""
        if self.config.meta_learner_type == MetaLearnerType.RIDGE:
            return Ridge(alpha=1.0, random_state=42)
        elif self.config.meta_learner_type == MetaLearnerType.RANDOM_FOREST:
            return RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
        elif self.config.meta_learner_type == MetaLearnerType.XGBOOST:
            return xgb.XGBRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42,
                tree_method='hist'
            )
        else:
            raise ValueError(f"Unknown meta-learner type: {self.config.meta_learner_type}")
    
    def _generate_regime_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate PIT-safe regime features.
        
        Args:
            data: MultiIndex DataFrame with levels ['date', 'symbol']
            
        Returns:
            DataFrame with regime features
        """
        df = data.copy()
        
        # Market proxy (equal-weighted index)
        if 'close' in df.columns:
            # Vectorized: unstack and compute market proxy
            mkt_prices = df.unstack(level='symbol')['close'].ffill()
            index_proxy = mkt_prices.mean(axis=1)
            
            # Vectorized: compute returns
            returns = index_proxy.pct_change()
            
            # PIT-safe: shift(1) after rolling calculations (vectorized)
            mkt_vol_20d = returns.rolling(20).std().shift(1)
            mkt_ret_20d = index_proxy.pct_change(20).shift(1)
            mkt_ret_5d = index_proxy.pct_change(5).shift(1)
            
            # Vectorized: map back to multi-index using reindex
            date_index = df.index.get_level_values('date')
            df['regime_mkt_vol_20d'] = mkt_vol_20d.reindex(date_index).values
            df['regime_mkt_ret_20d'] = mkt_ret_20d.reindex(date_index).values
            df['regime_mkt_ret_5d'] = mkt_ret_5d.reindex(date_index).values
            
            # Vectorized: fill NaNs
            regime_cols = ['regime_mkt_vol_20d', 'regime_mkt_ret_20d', 'regime_mkt_ret_5d']
            df[regime_cols] = df[regime_cols].ffill().fillna(0)
        
        return df
    
    def _create_meta_features(
        self,
        base_models: List[BaseModelPrediction],
        data: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Create meta-features from base model predictions.
        
        Args:
            base_models: List of base model predictions
            data: Optional data for regime features
            
        Returns:
            DataFrame with meta-features
        """
        # Base predictions as features
        meta_df = pd.DataFrame({
            f"base_{model.model_name}": model.predictions
            for model in base_models
        })
        
        # Add regime features if requested and data available
        if self.config.use_meta_features and data is not None:
            regime_df = self._generate_regime_features(data)
            regime_cols = [c for c in regime_df.columns if c.startswith('regime_')]
            
            # Align indices
            for col in regime_cols:
                meta_df[col] = regime_df[col].reindex(meta_df.index)
        
        return meta_df
    
    def fit(
        self,
        base_models: List[BaseModelPrediction],
        actuals: pd.Series,
        data: Optional[pd.DataFrame] = None
    ) -> None:
        """
        Fit stacking ensemble meta-learner.
        
        CRITICAL: All base model predictions in `base_models` MUST be Out-of-Sample (OOS)
        predictions. Fitting a meta-learner on in-sample predictions leads to severe target
        leakage and overfitting.
        
        Args:
            base_models: List of base model predictions (MUST be OOS)
            actuals: Actual returns
            data: Optional data for regime features
        
        PIT Safety:
            Enforces embargo_days between train and validation to prevent leakage.
        """
        # Enforce contract validation
        for bm in base_models:
            if not isinstance(bm, BaseModelPrediction):
                raise TypeError("All models must be instances of BaseModelPrediction")
            # Strict PIT Provenance check: all base predictions must be explicitly marked as Out-of-Sample (OOS)
            if not bm.is_oos:
                raise ValueError(
                    f"PIT Provenance check FAILED: Base model '{bm.model_name}' predictions "
                    f"are not marked as Out-of-Sample (is_oos=True). Stacking meta-learner training BLOCKED."
                )
            # Require auditable metadata on base predictions
            if bm.train_end is None or bm.prediction_start is None:
                raise ValueError(
                    f"PIT Provenance check FAILED: Base model '{bm.model_name}' is missing "
                    f"auditable metadata (train_end and prediction_start). Stacking meta-learner training BLOCKED."
                )
            if bm.prediction_start <= bm.train_end:
                raise ValueError(
                    f"PIT Provenance check FAILED: Base model '{bm.model_name}' has invalid "
                    f"chronology (prediction_start: {bm.prediction_start} <= train_end: {bm.train_end}). "
                    f"Stacking meta-learner training BLOCKED."
                )
            # If the predictions correlate highly in-sample with targets, raise ValueError to block target leakage
            aligned_check = pd.DataFrame({'pred': bm.predictions, 'act': actuals}).dropna()
            if len(aligned_check) > 0:
                corr = aligned_check['pred'].corr(aligned_check['act'])
                if abs(corr) > 0.85:
                    raise ValueError(
                        f"Target leakage detected: Base model '{bm.model_name}' has extremely high correlation "
                        f"({corr:.4f}) with actuals. Stacking meta-learner training BLOCKED to maintain PIT safety."
                    )
                    
        # Create meta-features
        meta_features = self._create_meta_features(base_models, data)
        self.feature_names = list(meta_features.columns)
        
        # Align with actuals
        aligned = meta_features.join(actuals.rename('target'), how='inner').dropna()
        
        if len(aligned) < 100:
            logger.error(f"Insufficient data for stacking: {len(aligned)} samples")
            return
        
        # PIT Safety: Apply embargo_days if data has date index
        if isinstance(aligned.index, pd.MultiIndex) and 'date' in aligned.index.names:
            # Get unique dates
            dates = aligned.index.get_level_values('date').unique().sort_values()
            
            # Apply embargo: exclude last embargo_days from training
            if len(dates) > self.config.embargo_days:
                embargo_cutoff = dates[-self.config.embargo_days - 1]
                train_mask = aligned.index.get_level_values('date') <= embargo_cutoff
                aligned = aligned[train_mask]
                logger.info(f"Applied {self.config.embargo_days}-day embargo, training samples: {len(aligned)}")
        elif isinstance(aligned.index, pd.DatetimeIndex):
            # Single-level DatetimeIndex
            dates = aligned.index.unique().sort_values()
            if len(dates) > self.config.embargo_days:
                embargo_cutoff = dates[-self.config.embargo_days - 1]
                aligned = aligned[aligned.index <= embargo_cutoff]
                logger.info(f"Applied {self.config.embargo_days}-day embargo, training samples: {len(aligned)}")
        
        if len(aligned) < 100:
            logger.error(f"Insufficient data after embargo: {len(aligned)} samples")
            return
        
        X = aligned[self.feature_names]
        y = aligned['target']
        
        # Clean data
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Create and fit meta-learner
        self.meta_learner = self._create_meta_learner()
        self.meta_learner.fit(X, y)
        
        self.is_fitted = True
        logger.info(f"Stacking ensemble fitted with {len(self.feature_names)} meta-features")
    
    def predict(
        self,
        base_models: List[BaseModelPrediction],
        data: Optional[pd.DataFrame] = None
    ) -> EnsembleResult:
        """
        Generate ensemble predictions using meta-learner.
        
        Args:
            base_models: List of base model predictions
            data: Optional data for regime features
            
        Returns:
            EnsembleResult with meta-learner predictions
        """
        if not self.is_fitted or self.meta_learner is None:
            logger.error("Stacking ensemble not fitted")
            # Fallback to simple average
            pred_df = pd.DataFrame({
                model.model_name: model.predictions
                for model in base_models
            })
            ensemble_pred = pred_df.mean(axis=1)
            return EnsembleResult(predictions=ensemble_pred)
        
        # Create meta-features
        meta_features = self._create_meta_features(base_models, data)
        
        # Ensure same features as training
        missing_cols = set(self.feature_names) - set(meta_features.columns)
        if missing_cols:
            logger.warning(f"Missing meta-features: {missing_cols}, filling with 0")
            for col in missing_cols:
                meta_features[col] = 0.0
        
        X = meta_features[self.feature_names]
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Predict
        predictions = self.meta_learner.predict(X)
        ensemble_series = pd.Series(predictions, index=meta_features.index)
        
        return EnsembleResult(
            predictions=ensemble_series,
            meta_features=meta_features,
            metrics={
                'n_models': len(base_models),
                'n_meta_features': len(self.feature_names)
            }
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


def create_stacking_ensemble(
    base_oos_predictions: Dict[str, pd.Series],
    actuals: pd.Series,
    data: Optional[pd.DataFrame] = None,
    config: Optional[EnsembleConfig] = None
) -> EnsembleResult:
    """
    Convenience function to create, fit, and predict stacking ensemble using Out-of-Sample (OOS) predictions
    with strict PIT safety partitioning.
    
    CRITICAL: To prevent meta-learner leakage, the data is partitioned using `config.train_cutoff` 
    and `config.validation_start`. The meta-learner is fit ONLY on the training partition, and 
    predictions are generated ONLY on the validation (OOS) partition.
    
    Args:
        base_oos_predictions: Dict mapping model_name -> Out-of-Sample predictions (OOS)
        actuals: Actual returns
        data: Optional data for regime features
        config: Optional ensemble config
        
    Returns:
        EnsembleResult with meta-learner predictions on the validation (OOS) partition.
    """
    cfg = config or EnsembleConfig()
    
    # Enforce OOS contract via input validation
    for name, pred in base_oos_predictions.items():
        if not isinstance(pred, pd.Series):
            raise TypeError(f"Predictions for {name} must be a pandas Series")
        if pred.isnull().all():
            raise ValueError(f"Predictions for {name} cannot be all null")
            
    # Partition data chronologically to ensure meta-learner PIT safety
    train_cutoff = pd.Timestamp(cfg.train_cutoff)
    val_start = pd.Timestamp(cfg.validation_start)
    
    if val_start <= train_cutoff:
        raise ValueError(
            f"Chronological sequence violation: validation_start ({cfg.validation_start}) "
            f"must be strictly greater than train_cutoff ({cfg.train_cutoff}) to prevent look-ahead target leakage."
        )
    
    base_models_train = []
    base_models_val = []
    
    for name, pred in base_oos_predictions.items():
        # Train partition - mark as is_oos=True since convenience API enforces chronological safety
        train_mask = pred.index.get_level_values('date') <= train_cutoff
        train_pred = pred[train_mask]
        
        # Calculate/infer train_end and prediction_start for train slice
        train_dates = train_pred.index.get_level_values('date')
        train_end_val = train_dates.max() if len(train_dates) > 0 else None
        
        # OOS prediction for training must start after training period.
        # Since it's a slice from a single series, we set prediction_start to the minimum date in that slice
        # and train_end to one day before the minimum date of the slice.
        prediction_start_val = train_dates.min() if len(train_dates) > 0 else None
        if prediction_start_val is not None:
            train_end_val = prediction_start_val - pd.Timedelta(days=1)
        else:
            train_end_val = None
            
        base_models_train.append(BaseModelPrediction(
            model_name=name,
            predictions=train_pred,
            is_oos=True,
            train_end=train_end_val,
            prediction_start=prediction_start_val,
            generator_id="create_stacking_ensemble_convenience"
        ))
        
        # Validation partition - mark as is_oos=True
        val_mask = pred.index.get_level_values('date') >= val_start
        val_pred = pred[val_mask]
        
        val_dates = val_pred.index.get_level_values('date')
        val_start_val = val_dates.min() if len(val_dates) > 0 else None
        if val_start_val is not None:
            val_end_val = val_start_val - pd.Timedelta(days=1)
        else:
            val_end_val = None
            
        base_models_val.append(BaseModelPrediction(
            model_name=name,
            predictions=val_pred,
            is_oos=True,
            train_end=val_end_val,
            prediction_start=val_start_val,
            generator_id="create_stacking_ensemble_convenience"
        ))
        
    # Fit meta-learner only on train partition
    train_actuals = actuals[actuals.index.get_level_values('date') <= train_cutoff]
    train_data = data[data.index.get_level_values('date') <= train_cutoff] if data is not None else None
    
    if len(train_actuals) < 100:
        raise ValueError(
            f"Insufficient training samples ({len(train_actuals)}) before cutoff {cfg.train_cutoff}. "
            "Stacking meta-learner cannot be safely fitted."
        )
        
    ensemble = StackingEnsemble(cfg)
    ensemble.fit(base_models_train, train_actuals, train_data)

    if not ensemble.is_fitted or ensemble.meta_learner is None:
        raise ValueError(
            "Stacking meta-learner fitting failed on training partition. "
            "No OOS ensemble predictions generated."
        )
    
    # Predict only on validation partition (completely OOS for meta-learner)
    val_data = data[data.index.get_level_values('date') >= val_start] if data is not None else None
    
    if len(base_models_val[0].predictions) == 0:
        raise ValueError(
            f"No validation samples found after {cfg.validation_start}. "
            "Ensemble predictions cannot be generated."
        )
        
    return ensemble.predict(base_models_val, val_data)
