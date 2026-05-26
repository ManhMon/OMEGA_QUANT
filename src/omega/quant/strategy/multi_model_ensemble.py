"""
Multi-Model Ensemble - Ensemble Builder with Diversity Enforcement
Layer 02: Strategy Logic

Creates diverse ensemble of 5-8 models with correlation-based filtering.
Supports: XGBoost, LightGBM, Random Forest, CatBoost, Neural Networks, Linear Models
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.neural_network import MLPClassifier
import warnings
warnings.filterwarnings('ignore')

import os
from omega.quant.feature_pruning import FeaturePruning, FeaturePruningConfig

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

try:
    from catboost import CatBoostClassifier, CatBoostRegressor
    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False


@dataclass
class ModelConfig:
    """Configuration for individual model"""
    name: str
    model_type: str  # 'xgboost', 'lightgbm', 'catboost', 'rf', 'nn', 'ridge', 'logistic'
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class EnsembleConfig:
    """Configuration for ensemble"""
    models: List[ModelConfig] = field(default_factory=list)
    diversity_threshold: float = 0.55  # Max correlation between models (lowered for VN market diversity)
    min_models: int = 3
    max_models: int = 8
    correlation_window: int = 252  # For correlation calculation
    
    def __post_init__(self):
        if not self.models:
            self.models = self._get_default_models()
    
    def _get_default_models(self) -> List[ModelConfig]:
        """Get default model configurations"""
        models = []
        
        if HAS_XGBOOST:
            models.append(ModelConfig(
                name='xgb_rank',
                model_type='xgboost_rank',
                params={'objective': 'rank:pairwise', 'n_estimators': 100, 'max_depth': 5, 'subsample': 0.8, 'min_child_weight': 5}
            ))
            models.append(ModelConfig(
                name='xgb_reg',
                model_type='xgboost_reg',
                params={'objective': 'reg:squarederror', 'n_estimators': 100, 'max_depth': 4, 'subsample': 0.8, 'min_child_weight': 5}
            ))
        
        if HAS_LIGHTGBM:
            models.append(ModelConfig(
                name='lgb_rank',
                model_type='lightgbm_rank',
                params={'objective': 'lambdarank', 'n_estimators': 100, 'max_depth': 5, 'subsample': 0.8, 'min_child_samples': 20}
            ))
            models.append(ModelConfig(
                name='lgb_reg',
                model_type='lightgbm_reg',
                params={'objective': 'regression', 'n_estimators': 100, 'max_depth': 4, 'subsample': 0.8, 'min_child_samples': 20}
            ))
        
        if HAS_CATBOOST:
            models.append(ModelConfig(
                name='catboost',
                model_type='catboost',
                params={'iterations': 100, 'depth': 5}
            ))
        
        # Always add sklearn models
        models.append(ModelConfig(
            name='random_forest',
            model_type='rf',
            params={'n_estimators': 100, 'max_depth': 8}
        ))
        
        models.append(ModelConfig(
            name='ridge',
            model_type='ridge',
            params={'alpha': 1.0}
        ))
        
        models.append(ModelConfig(
            name='neural_net',
            model_type='nn',
            params={'hidden_layer_sizes': (64, 32), 'max_iter': 500}
        ))
        
        return models[:self.max_models]


class MultiModelEnsemble:
    """
    Multi-model ensemble with diversity enforcement.
    Creates 5-8 diverse models and combines predictions.
    Integrates with FeaturePruning (Layer 01) to remove noise before fitting.
    """
    
    def __init__(self, config: Optional[EnsembleConfig] = None, feature_pruning_config: Optional[FeaturePruningConfig] = None):
        self.config = config or EnsembleConfig()
        self.models: Dict[str, Any] = {}
        self.model_predictions: Dict[str, np.ndarray] = {}
        self.is_fitted = False
        self.pruner = FeaturePruning(feature_pruning_config)
        self.active_features: List[str] = []
        
        # Initialize models
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize all enabled model instances"""
        for model_config in self.config.models:
            if not model_config.enabled:
                continue
            
            try:
                model = self._create_model(model_config)
                self.models[model_config.name] = {
                    'config': model_config,
                    'instance': model,
                    'fitted': False
                }
            except Exception as e:
                print(f"Warning: Failed to initialize {model_config.name}: {e}")
    
    def _create_model(self, model_config: ModelConfig) -> Any:
        """Create model instance from config"""
        model_type = model_config.model_type
        params = model_config.params
        
        if model_type == 'xgboost_rank' and HAS_XGBOOST:
            return xgb.XGBRanker(**params)
        elif model_type == 'xgboost_reg' and HAS_XGBOOST:
            return xgb.XGBRegressor(**params)
        elif model_type == 'lightgbm_rank' and HAS_LIGHTGBM:
            return lgb.LGBMRanker(**params)
        elif model_type == 'lightgbm_reg' and HAS_LIGHTGBM:
            return lgb.LGBMRegressor(**params)
        elif model_type == 'catboost' and HAS_CATBOOST:
            return CatBoostRegressor(**params)
        elif model_type == 'rf':
            return RandomForestClassifier(**params)
        elif model_type == 'ridge':
            return Ridge(**params)
        elif model_type == 'logistic':
            return LogisticRegression(**params)
        elif model_type == 'nn':
            return MLPClassifier(**params)
        else:
            # Default to gradient boosting
            return GradientBoostingRegressor(**params)
    
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        prune_features: bool = True
    ) -> 'MultiModelEnsemble':
        """
        Fit all models in ensemble.
        
        Args:
            X: Feature matrix
            y: Target values (Series)
            sample_weight: Optional sample weights
            prune_features: Whether to run Layer 01 feature pruning before fitting
        """
        if prune_features and isinstance(X, pd.DataFrame) and isinstance(y, pd.Series):
            print("Running Layer 01 Feature Pruning...")
            pruning_result = self.pruner.prune_features(X, y)
            self.active_features = pruning_result.kept_features
            print(f"Pruning complete. Kept {len(self.active_features)} features.")
            X_fit = X[self.active_features]
        else:
            self.active_features = list(X.columns) if isinstance(X, pd.DataFrame) else []
            X_fit = X
            
        print(f"Fitting ensemble with {len(self.models)} models on {X_fit.shape[1] if isinstance(X_fit, pd.DataFrame) else 'all'} features...")
        
        for name, model_info in self.models.items():
            try:
                model = model_info['instance']
                
                if sample_weight is not None:
                    model.fit(X_fit, y, sample_weight=sample_weight)
                else:
                    model.fit(X_fit, y)
                
                model_info['fitted'] = True
                print(f"  âœ“ {name} fitted successfully")
                
            except Exception as e:
                print(f"  âœ— {name} failed: {e}")
                model_info['fitted'] = False
        
        self.is_fitted = True
        return self
    
    def predict(self, X: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Generate ensemble predictions.
        
        Args:
            X: Feature matrix
            weights: Optional dictionary of model weights. If None, uses equal weighting.
            
        Returns:
            ensemble_pred: Weighted ensemble prediction
            model_preds: Individual model predictions
        """
        if not self.is_fitted:
            raise ValueError("Ensemble must be fitted before predict")
            
        # Ensure we only predict using features that survived pruning
        X_pred = X[self.active_features] if self.active_features and isinstance(X, pd.DataFrame) else X
        
        model_preds = {}
        
        for name, model_info in self.models.items():
            if not model_info['fitted']:
                continue
            
            try:
                pred = model_info['instance'].predict(X_pred)
                pred = np.nan_to_num(pred, nan=0.0, posinf=0.0, neginf=0.0) # Handle NaN/Inf
                model_preds[name] = pred
            except Exception as e:
                print(f"Warning: {name} prediction failed: {e}")
        
        if not model_preds:
            raise ValueError("No models successfully predicted")
        
        # Apply weighting
        if weights is not None:
            # Normalize weights for available models
            valid_weights = {k: v for k, v in weights.items() if k in model_preds}
            if valid_weights:
                total_w = sum(valid_weights.values())
                if total_w > 0:
                    normalized_weights = {k: v / total_w for k, v in valid_weights.items()}
                    weighted_preds = [pred * normalized_weights[name] for name, pred in model_preds.items() if name in normalized_weights]
                    ensemble_pred = np.sum(weighted_preds, axis=0)
                else:
                    ensemble_pred = np.mean(list(model_preds.values()), axis=0)
            else:
                ensemble_pred = np.mean(list(model_preds.values()), axis=0)
        else:
            # Equal weighting
            ensemble_pred = np.mean(list(model_preds.values()), axis=0)
        
        return ensemble_pred, model_preds
    
    def predict_with_confidence(
        self,
        X: pd.DataFrame,
        confidence_method: str = 'std'
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate predictions with confidence intervals.
        
        Args:
            X: Feature matrix
            confidence_method: 'std' or 'agreement'
            
        Returns:
            predictions: Ensemble predictions
            confidence: Confidence scores
        """
        _, model_preds = self.predict(X)
        
        pred_matrix = np.column_stack(list(model_preds.values()))
        
        if confidence_method == 'std':
            # Use standard deviation as uncertainty measure
            confidence = np.std(pred_matrix, axis=1)
        else:
            # Use agreement (fraction of models that agree on direction)
            mean_pred = np.mean(pred_matrix, axis=1, keepdims=True)
            agreement = np.mean(np.sign(pred_matrix) == np.sign(mean_pred), axis=1)
            confidence = 1 - agreement
        
        ensemble_pred = np.mean(pred_matrix, axis=1)
        
        return ensemble_pred, confidence
    
    def compute_correlation_matrix(
        self,
        X: pd.DataFrame,
        n_samples: int = 1000
    ) -> pd.DataFrame:
        """
        Compute correlation matrix of model predictions.
        
        Args:
            X: Feature matrix (sample for prediction)
            n_samples: Number of samples to use
            
        Returns:
            Correlation matrix as DataFrame
        """
        if not self.is_fitted:
            raise ValueError("Ensemble must be fitted first")
        
        X_sample = X.head(n_samples) if len(X) > n_samples else X
        _, model_preds = self.predict(X_sample)
        
        pred_matrix = np.column_stack(list(model_preds.values()))
        corr_matrix = np.corrcoef(pred_matrix.T)
        
        return pd.DataFrame(
            corr_matrix,
            index=list(model_preds.keys()),
            columns=list(model_preds.keys())
        )
    
    def enforce_diversity(
        self,
        X: pd.DataFrame,
        correlation_window: int = 252
    ) -> List[str]:
        """
        Enforce diversity by removing highly correlated models.
        
        Args:
            X: Feature matrix
            correlation_window: Window for correlation calculation
            
        Returns:
            List of removed model names
        """
        if not self.is_fitted:
            raise ValueError("Ensemble must be fitted first")
        
        corr_matrix = self.compute_correlation_matrix(X)
        
        # Find highly correlated pairs
        removed = []
        threshold = self.config.diversity_threshold
        
        # Get upper triangle indices
        n = len(corr_matrix)
        for i in range(n):
            for j in range(i + 1, n):
                model_i = corr_matrix.index[i]
                model_j = corr_matrix.index[j]
                
                if abs(corr_matrix.iloc[i, j]) > threshold:
                    # Remove less important model (prefer tree-based over linear)
                    to_remove = self._select_model_to_remove(model_i, model_j)
                    
                    if to_remove not in removed:
                        removed.append(to_remove)
                        print(f"Removing {to_remove} due to high correlation "
                              f"({corr_matrix.iloc[i, j]:.2f})")
        
        # Remove models
        for name in removed:
            if name in self.models:
                del self.models[name]
        
        # Ensure minimum models
        if len(self.models) < self.config.min_models:
            print(f"Warning: Ensemble has only {len(self.models)} models "
                  f"(minimum: {self.config.min_models})")
        
        return removed
    
    def _select_model_to_remove(self, model1: str, model2: str) -> str:
        """Select which model to remove based on priority"""
        # Priority: keep advanced models, remove simple ones
        priority_order = ['xgboost_rank', 'lightgbm_rank', 'xgboost_reg', 'lightgbm_reg', 'catboost', 'rf', 'nn', 'ridge']
        
        type1 = self.models.get(model1, {}).get('config', {}).model_type
        type2 = self.models.get(model2, {}).get('config', {}).model_type
        
        idx1 = priority_order.index(type1) if type1 in priority_order else 99
        idx2 = priority_order.index(type2) if type2 in priority_order else 99
        
        # Lower index = higher priority to keep. Remove the one with higher index (lower priority)
        return model2 if idx1 < idx2 else model1
    
    def get_model_importance(
        self,
        X: pd.DataFrame,
        method: str = 'permutation'
    ) -> Dict[str, float]:
        """
        Get feature importance from all models.
        
        Args:
            X: Feature matrix
            method: 'permutation' or 'builtin'
            
        Returns:
            Dictionary of model importance scores
        """
        importance = {}
        
        for name, model_info in self.models.items():
            if not model_info['fitted']:
                continue
            
            model = model_info['instance']
            
            try:
                if hasattr(model, 'feature_importances_'):
                    importance[name] = np.mean(model.feature_importances_)
                elif hasattr(model, 'coef_'):
                    importance[name] = np.mean(np.abs(model.coef_))
                else:
                    importance[name] = 0.0
            except:
                importance[name] = 0.0
        
        return importance
    
    def get_ensemble_stats(self) -> Dict[str, Any]:
        """Get ensemble statistics"""
        fitted_count = sum(1 for m in self.models.values() if m['fitted'])
        
        return {
            'total_models': len(self.models),
            'fitted_models': fitted_count,
            'enabled_models': sum(1 for c in self.config.models if c.enabled),
            'diversity_threshold': self.config.diversity_threshold,
            'model_names': list(self.models.keys())
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ensemble config to dict"""
        return {
            'config': {
                'diversity_threshold': self.config.diversity_threshold,
                'min_models': self.config.min_models,
                'max_models': self.config.max_models,
                'models': [
                    {
                        'name': m.name,
                        'model_type': m.model_type,
                        'params': m.params,
                        'enabled': m.enabled
                    }
                    for m in self.config.models
                ]
            },
            'stats': self.get_ensemble_stats()
        }


class AdaptiveEnsembleWeighting:
    """
    Adaptive weighting based on recent performance.
    """
    
    def __init__(self, lookback_windows: List[int] = None):
        self.lookback_windows = lookback_windows or [21, 63, 126]
        self.weights_history = []
    
    def compute_weights(
        self,
        predictions: Dict[str, np.ndarray],
        actuals: np.ndarray,
        method: str = 'ic'
    ) -> Dict[str, float]:
        """
        Compute adaptive weights based on recent performance.
        
        Args:
            predictions: Dictionary of model predictions
            actuals: Actual returns
            method: 'ic' (information coefficient) or 'mse'
            
        Returns:
            Dictionary of model weights
        """
        weights = {}
        
        for name, pred in predictions.items():
            scores = []
            
            for window in self.lookback_windows:
                if len(pred) < window:
                    continue
                
                recent_pred = pred[-window:]
                recent_actual = actuals[-window:]
                
                if method == 'ic':
                    # Information Coefficient (Spearman for robustness)
                    try:
                        from scipy.stats import spearmanr
                        ic, _ = spearmanr(recent_pred, recent_actual)
                    except:
                        ic = 0.0
                    scores.append(ic if not np.isnan(ic) else 0)
                else:
                    # Mean Squared Error (inverted)
                    mse = np.mean((recent_pred - recent_actual) ** 2)
                    scores.append(1 / (mse + 1e-10))
            
            # Average score across windows
            weights[name] = np.mean(scores) if scores else 0
        
        # Normalize weights
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        
        self.weights_history.append(weights)
        
        return weights
    
    def apply_weights(
        self,
        predictions: Dict[str, np.ndarray],
        weights: Dict[str, float]
    ) -> np.ndarray:
        """Apply weights to predictions"""
        weighted_preds = []
        
        for name, pred in predictions.items():
            if name in weights:
                weighted_preds.append(weights[name] * pred)
        
        return np.sum(weighted_preds, axis=0)


if __name__ == '__main__':
    print("=" * 80)
    print("MULTI-MODEL ENSEMBLE - DEMO")
    print("=" * 80)
    
    # Create sample data
    np.random.seed(42)
    n_samples = 1000
    n_features = 20
    
    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f'feature_{i}' for i in range(n_features)]
    )
    y = np.random.randn(n_samples)
    
    # Create and fit ensemble
    config = EnsembleConfig(
        diversity_threshold=0.70,
        max_models=5
    )
    
    print(f"\n1. Creating ensemble with {config.max_models} models...")
    ensemble = MultiModelEnsemble(config)
    
    print(f"\n2. Fitting ensemble...")
    ensemble.fit(X, y)
    
    print(f"\n3. Ensemble statistics:")
    stats = ensemble.get_ensemble_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")
    
    print(f"\n4. Generating predictions...")
    pred, model_preds = ensemble.predict(X.head(100))
    print(f"   âœ“ Predictions shape: {pred.shape}")
    
    print(f"\n5. Computing correlation matrix...")
    corr = ensemble.compute_correlation_matrix(X.head(500))
    print(f"   Correlation matrix:\n{corr.round(2)}")
    
    print(f"\n6. Enforcing diversity...")
    removed = ensemble.enforce_diversity(X.head(500))
    print(f"   Removed models: {removed}")
    
    print(f"\n7. Getting feature importance...")
    importance = ensemble.get_model_importance(X)
    for name, imp in importance.items():
        print(f"   {name}: {imp:.4f}")
    
    print("\n" + "=" * 80)
    print("âœ… Multi-Model Ensemble demo complete")
    print("=" * 80)
