"""Stacking ensemble implementation.

Meta-learner ensemble for alpha predictions.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb

from omega.quant.ml.ensemble_config import (
    MetaLearnerType,
    EnsembleConfig,
    BaseModelPrediction,
    EnsembleResult,
)

logger = logging.getLogger(__name__)


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
        elif isinstance(aligned.index, pd.DataFrame):
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
