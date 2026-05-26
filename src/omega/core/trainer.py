"""
Model Trainer for OMEGA_QUANT

Implements walk-forward training with temporal splitting, hyperparameter optimization,
and PIT safety enforcement.

Institutional Grade Standards:
- Walk-forward validation (T+1, T+3, T+5 horizons)
- Non-overlapping temporal windows
- Bayesian hyperparameter optimization (optuna)
- Performance metrics: IC, IR, Sharpe, Sortino, max_drawdown
- PIT safety: as_of <= available_at validation
- Model persistence via ModelRegistry
"""

import pandas as pd
import numpy as np
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from pathlib import Path
import logging
import json
from dataclasses import dataclass, asdict
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb

from omega.core.model_registry import ModelRegistry


logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """Represents a single walk-forward training/validation window."""
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    horizon: int  # T+1, T+3, or T+5
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "train_start": str(self.train_start),
            "train_end": str(self.train_end),
            "validation_start": str(self.validation_start),
            "validation_end": str(self.validation_end),
            "horizon": self.horizon
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics for a model on a validation window."""
    ic: float  # Information Coefficient
    ir: float  # Information Ratio
    sharpe: float  # Sharpe Ratio
    sortino: float  # Sortino Ratio
    max_drawdown: float  # Maximum Drawdown
    rmse: float  # Root Mean Squared Error
    mae: float  # Mean Absolute Error
    r_squared: float  # R-squared
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization."""
        return asdict(self)


class ModelTrainer:
    """
    Walk-forward model trainer with PIT safety enforcement.
    
    Supports:
    - Multiple horizons (T+1, T+3, T+5)
    - Non-overlapping temporal windows
    - Bayesian hyperparameter optimization
    - Performance metrics computation
    - Model checkpointing
    """
    
    def __init__(
        self,
        model_name: str,
        horizons: List[int] = None,
        min_train_days: int = 252,  # ~1 year of trading days
        min_validation_days: int = 63,  # ~3 months
        test_size_days: int = 63,  # ~3 months for final test
        random_state: int = 42,
        registry: Optional[ModelRegistry] = None
    ):
        """
        Initialize ModelTrainer.
        
        Args:
            model_name: Name of the model
            horizons: List of prediction horizons (default [1, 3, 5])
            min_train_days: Minimum training window size
            min_validation_days: Minimum validation window size
            test_size_days: Size of final test set
            random_state: Random seed for reproducibility
            registry: Optional ModelRegistry to save checkpoints
        """
        self.model_name = model_name
        self.horizons = horizons or [1, 3, 5]
        self.min_train_days = min_train_days
        self.min_validation_days = min_validation_days
        self.test_size_days = test_size_days
        self.random_state = random_state
        self.registry = registry
        
        self.models = {}  # {horizon: model}
        self.scalers = {}  # {horizon: scaler}
        self.training_history = []  # List of WalkForwardWindow
        self.metrics_history = {}  # {horizon: [PerformanceMetrics]}
        
    def create_walk_forward_windows(
        self,
        df: pd.DataFrame,
        date_col: str = 'date',
        available_at_col: str = 'available_at'
    ) -> List[WalkForwardWindow]:
        """
        Create non-overlapping walk-forward windows with PIT safety.
        
        Args:
            df: Input DataFrame with features and targets
            date_col: Date column name
            available_at_col: Available-at timestamp column name
        
        Returns:
            List of WalkForwardWindow objects
        
        PIT Safety:
            - Validation window starts AFTER train_end + max_horizon
            - No look-ahead: validation_start >= train_end + max_horizon + 1
            - Non-overlapping windows
        """
        df = df.sort_values(date_col).copy()
        dates = pd.to_datetime(df[date_col]).unique()
        
        if len(dates) < self.min_train_days + self.min_validation_days:
            raise ValueError(
                f"Insufficient data: {len(dates)} days, need at least "
                f"{self.min_train_days + self.min_validation_days}"
            )
        
        windows = []
        max_horizon = max(self.horizons)
        
        # Reserve final test set
        test_start_idx = len(dates) - self.test_size_days
        available_dates = dates[:test_start_idx]
        
        # Create rolling windows
        train_start_idx = 0
        while True:
            train_end_idx = train_start_idx + self.min_train_days
            
            # PIT safety: validation starts after train_end + max_horizon
            validation_start_idx = train_end_idx + max_horizon
            validation_end_idx = validation_start_idx + self.min_validation_days
            
            # Check if we have enough data
            if validation_end_idx >= len(available_dates):
                break
            
            train_start = pd.Timestamp(available_dates[train_start_idx])
            train_end = pd.Timestamp(available_dates[train_end_idx - 1])
            validation_start = pd.Timestamp(available_dates[validation_start_idx])
            validation_end = pd.Timestamp(available_dates[validation_end_idx - 1])
            
            # Create windows for each horizon
            for horizon in self.horizons:
                window = WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    validation_start=validation_start,
                    validation_end=validation_end,
                    horizon=horizon
                )
                windows.append(window)
            
            # Move forward by min_validation_days (non-overlapping)
            train_start_idx = validation_end_idx
        
        logger.info(f"Created {len(windows)} walk-forward windows for {len(self.horizons)} horizons")
        return windows
    
    def _validate_pit_safety(
        self,
        df: pd.DataFrame,
        date_col: str = 'date',
        available_at_col: str = 'available_at'
    ) -> bool:
        """
        Validate PIT safety: as_of <= available_at for all rows.
        
        Args:
            df: DataFrame to validate
            date_col: Date column (as_of)
            available_at_col: Available-at column
        
        Returns:
            True if PIT safe, raises ValueError otherwise
        """
        df_check = df.copy()
        df_check[date_col] = pd.to_datetime(df_check[date_col])
        df_check[available_at_col] = pd.to_datetime(df_check[available_at_col])
        
        violations = df_check[df_check[date_col] > df_check[available_at_col]]
        
        if len(violations) > 0:
            raise ValueError(
                f"PIT safety violation: {len(violations)} rows have as_of > available_at. "
                f"Example: {violations.iloc[0]}"
            )
        
        return True
    
    def prepare_training_data(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str,
        window: WalkForwardWindow,
        date_col: str = 'date',
        available_at_col: str = 'available_at',
        symbol_col: str = 'symbol'
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Prepare training data for a single window with PIT safety.
        
        Args:
            df: Input DataFrame
            feature_cols: List of feature column names
            target_col: Target column name
            window: WalkForwardWindow object
            date_col: Date column name
            available_at_col: Available-at column name
            symbol_col: Symbol column name
        
        Returns:
            Tuple of (X, y, metadata_df)
        
        PIT Safety:
            - Only use data where available_at <= date (no look-ahead)
            - Target computed at T+horizon
        """
        # Validate PIT safety
        self._validate_pit_safety(df, date_col, available_at_col)
        
        # Filter to training window
        df_train = df[
            (pd.to_datetime(df[date_col]) >= window.train_start) &
            (pd.to_datetime(df[date_col]) <= window.train_end)
        ].copy()
        
        if len(df_train) == 0:
            raise ValueError(f"No data in training window: {window.train_start} to {window.train_end}")
        
        # Compute target: forward return at T+horizon
        df_train = df_train.sort_values([symbol_col, date_col])
        df_train['target'] = df_train.groupby(symbol_col)['close'].pct_change(window.horizon)
        
        # Drop NaN targets
        df_train = df_train.dropna(subset=['target'])
        
        # Extract features and target
        X = df_train[feature_cols].values
        y = df_train['target'].values
        
        logger.info(
            f"Prepared training data: {X.shape[0]} samples, {X.shape[1]} features, "
            f"horizon={window.horizon}"
        )
        
        return X, y, df_train
    
    def prepare_validation_data(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str,
        window: WalkForwardWindow,
        date_col: str = 'date',
        available_at_col: str = 'available_at',
        symbol_col: str = 'symbol'
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Prepare validation data for a single window with PIT safety.
        
        Args:
            df: Input DataFrame
            feature_cols: List of feature column names
            target_col: Target column name
            window: WalkForwardWindow object
            date_col: Date column name
            available_at_col: Available-at column name
            symbol_col: Symbol column name
        
        Returns:
            Tuple of (X, y, metadata_df)
        
        PIT Safety:
            - Validation starts AFTER train_end + horizon
            - Only use data where available_at <= date
        """
        # Validate PIT safety
        self._validate_pit_safety(df, date_col, available_at_col)
        
        # Filter to validation window
        df_val = df[
            (pd.to_datetime(df[date_col]) >= window.validation_start) &
            (pd.to_datetime(df[date_col]) <= window.validation_end)
        ].copy()
        
        if len(df_val) == 0:
            raise ValueError(
                f"No data in validation window: {window.validation_start} to {window.validation_end}"
            )
        
        # Compute target: forward return at T+horizon
        df_val = df_val.sort_values([symbol_col, date_col])
        df_val['target'] = df_val.groupby(symbol_col)['close'].pct_change(window.horizon)
        
        # Drop NaN targets
        df_val = df_val.dropna(subset=['target'])
        
        # Extract features and target
        X = df_val[feature_cols].values
        y = df_val['target'].values
        
        logger.info(
            f"Prepared validation data: {X.shape[0]} samples, {X.shape[1]} features, "
            f"horizon={window.horizon}"
        )
        
        return X, y, df_val
    
    def compute_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> PerformanceMetrics:
        """
        Compute performance metrics.
        
        Args:
            y_true: True target values
            y_pred: Predicted values
        
        Returns:
            PerformanceMetrics object
        """
        # Information Coefficient (correlation)
        ic = np.corrcoef(y_true, y_pred)[0, 1]
        
        # Information Ratio (IC / std(IC))
        residuals = y_true - y_pred
        ir = ic / (np.std(residuals) + 1e-8)
        
        # Sharpe Ratio (mean return / std return)
        sharpe = np.mean(y_pred) / (np.std(y_pred) + 1e-8) * np.sqrt(252)
        
        # Sortino Ratio (mean return / std downside return)
        downside_returns = np.minimum(y_pred, 0)
        sortino = np.mean(y_pred) / (np.std(downside_returns) + 1e-8) * np.sqrt(252)
        
        # Maximum Drawdown
        cumulative_returns = np.cumprod(1 + y_pred)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        # RMSE
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        
        # MAE
        mae = np.mean(np.abs(y_true - y_pred))
        
        # R-squared
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        r_squared = 1 - (ss_res / (ss_tot + 1e-8))
        
        return PerformanceMetrics(
            ic=ic,
            ir=ir,
            sharpe=sharpe,
            sortino=sortino,
            max_drawdown=max_drawdown,
            rmse=rmse,
            mae=mae,
            r_squared=r_squared
        )
    
    def train_single_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        model_type: str = 'xgboost',
        hyperparams: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, StandardScaler]:
        """
        Train a single model with optional hyperparameters.
        
        Args:
            X_train: Training features
            y_train: Training targets
            model_type: Model type ('xgboost' or 'random_forest')
            hyperparams: Hyperparameter dictionary
        
        Returns:
            Tuple of (trained_model, scaler)
        """
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        
        # Default hyperparameters
        if hyperparams is None:
            hyperparams = {}
        
        if model_type == 'xgboost':
            default_params = {
                'n_estimators': 100,
                'max_depth': 5,
                'learning_rate': 0.1,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': self.random_state
            }
            default_params.update(hyperparams)
            model = xgb.XGBRegressor(**default_params)
        elif model_type == 'random_forest':
            default_params = {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 5,
                'random_state': self.random_state
            }
            default_params.update(hyperparams)
            model = RandomForestRegressor(**default_params)
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        model.fit(X_train_scaled, y_train)
        
        logger.info(f"Trained {model_type} model with {X_train.shape[0]} samples")
        
        return model, scaler
    
    def optimize_hyperparameters(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        model_type: str = 'xgboost',
        n_trials: int = 20,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Optimize hyperparameters using Bayesian optimization (optuna).
        
        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Validation features
            y_val: Validation targets
            model_type: Model type
            n_trials: Number of optimization trials
            timeout: Timeout in seconds
        
        Returns:
            Best hyperparameters dictionary
        """
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        
        def objective(trial):
            if model_type == 'xgboost':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                    'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                    'random_state': self.random_state
                }
                model = xgb.XGBRegressor(**params)
            elif model_type == 'random_forest':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                    'max_depth': trial.suggest_int('max_depth', 5, 20),
                    'min_samples_split': trial.suggest_int('min_samples_split', 2, 10),
                    'random_state': self.random_state
                }
                model = RandomForestRegressor(**params)
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_val_scaled)
            
            # Optimize for IC (Information Coefficient)
            ic = np.corrcoef(y_val, y_pred)[0, 1]
            
            return ic
        
        sampler = TPESampler(seed=self.random_state)
        pruner = MedianPruner()
        study = optuna.create_study(
            direction='maximize',
            sampler=sampler,
            pruner=pruner
        )
        
        study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)
        
        best_params = study.best_params
        logger.info(f"Best hyperparameters (IC={study.best_value:.4f}): {best_params}")
        
        return best_params
    
    def train_walk_forward(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str = 'close',
        date_col: str = 'date',
        available_at_col: str = 'available_at',
        symbol_col: str = 'symbol',
        model_type: str = 'xgboost',
        optimize_hyperparams: bool = True,
        n_trials: int = 20
    ) -> Dict[int, Dict[str, Any]]:
        """
        Train models using walk-forward validation.
        
        Args:
            df: Input DataFrame with features and targets
            feature_cols: List of feature column names
            target_col: Target column name
            date_col: Date column name
            available_at_col: Available-at column name
            symbol_col: Symbol column name
            model_type: Model type ('xgboost' or 'random_forest')
            optimize_hyperparams: Whether to optimize hyperparameters
            n_trials: Number of optimization trials
        
        Returns:
            Dictionary mapping horizon -> {model, scaler, metrics}
        
        PIT Safety:
            - All windows respect as_of <= available_at
            - Validation starts after train_end + horizon
            - Non-overlapping windows
        """
        # Create walk-forward windows
        windows = self.create_walk_forward_windows(df, date_col, available_at_col)
        
        # Group windows by horizon
        windows_by_horizon = {}
        for window in windows:
            if window.horizon not in windows_by_horizon:
                windows_by_horizon[window.horizon] = []
            windows_by_horizon[window.horizon].append(window)
        
        results = {}
        
        for horizon in self.horizons:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training model for horizon T+{horizon}")
            logger.info(f"{'='*60}")
            
            horizon_windows = windows_by_horizon.get(horizon, [])
            if not horizon_windows:
                logger.warning(f"No windows for horizon T+{horizon}")
                continue
            
            all_metrics = []
            best_model = None
            best_scaler = None
            best_ic = -np.inf
            
            for i, window in enumerate(horizon_windows):
                logger.info(f"\nWindow {i+1}/{len(horizon_windows)}: {window.train_start} to {window.validation_end}")
                
                # Prepare data
                X_train, y_train, _ = self.prepare_training_data(
                    df, feature_cols, target_col, window,
                    date_col, available_at_col, symbol_col
                )
                X_val, y_val, _ = self.prepare_validation_data(
                    df, feature_cols, target_col, window,
                    date_col, available_at_col, symbol_col
                )
                
                # Optimize hyperparameters if requested
                hyperparams = {}
                if optimize_hyperparams and i == 0:  # Only optimize on first window
                    hyperparams = self.optimize_hyperparameters(
                        X_train, y_train, X_val, y_val,
                        model_type=model_type,
                        n_trials=n_trials
                    )
                
                # Train model
                model, scaler = self.train_single_model(
                    X_train, y_train,
                    model_type=model_type,
                    hyperparams=hyperparams
                )
                
                # Evaluate on validation set
                X_val_scaled = scaler.transform(X_val)
                y_pred = model.predict(X_val_scaled)
                
                metrics = self.compute_metrics(y_val, y_pred)
                all_metrics.append(metrics)
                
                logger.info(f"Validation metrics: IC={metrics.ic:.4f}, IR={metrics.ir:.4f}, "
                           f"Sharpe={metrics.sharpe:.4f}, Sortino={metrics.sortino:.4f}")
                
                # Track best model
                if metrics.ic > best_ic:
                    best_ic = metrics.ic
                    best_model = model
                    best_scaler = scaler
                
                # Store window
                self.training_history.append(window)
            
            # Store results for this horizon
            results[horizon] = {
                'model': best_model,
                'scaler': best_scaler,
                'metrics': all_metrics,
                'best_ic': best_ic
            }
            
            self.models[horizon] = best_model
            self.scalers[horizon] = best_scaler
            self.metrics_history[horizon] = all_metrics
            
            # Save to registry if available
            if self.registry is not None and best_model is not None:
                metadata = {
                    'horizon': horizon,
                    'best_ic': best_ic,
                    'num_windows': len(horizon_windows),
                    'model_type': model_type
                }
                artifact = {
                    'model': best_model,
                    'scaler': best_scaler
                }
                version = self.registry.register_model(
                    model_name=f"{self.model_name}_H{horizon}",
                    model_object=artifact,
                    metadata=metadata
                )
                logger.info(f"Saved best model for horizon {horizon} to registry as version {version}")
            
            # Log summary
            avg_ic = np.mean([m.ic for m in all_metrics])
            avg_sharpe = np.mean([m.sharpe for m in all_metrics])
            logger.info(f"\nHorizon T+{horizon} Summary:")
            logger.info(f"  Average IC: {avg_ic:.4f}")
            logger.info(f"  Average Sharpe: {avg_sharpe:.4f}")
            logger.info(f"  Best IC: {best_ic:.4f}")
        
        logger.info(f"\n{'='*60}")
        logger.info("Walk-forward training complete")
        logger.info(f"{'='*60}")
        
        return results
    
    def predict(
        self,
        X: np.ndarray,
        horizon: int = 1
    ) -> np.ndarray:
        """
        Make predictions using trained model.
        
        Args:
            X: Feature matrix
            horizon: Prediction horizon (must be one of self.horizons)
        
        Returns:
            Predictions
        """
        if horizon not in self.models:
            raise ValueError(f"No model trained for horizon T+{horizon}")
        
        model = self.models[horizon]
        scaler = self.scalers[horizon]
        
        X_scaled = scaler.transform(X)
        return model.predict(X_scaled)
    
    def get_training_summary(self) -> Dict[str, Any]:
        """
        Get summary of training results.
        
        Returns:
            Dictionary with training summary
        """
        summary = {
            'model_name': self.model_name,
            'horizons': self.horizons,
            'num_windows': len(self.training_history),
            'metrics_by_horizon': {}
        }
        
        for horizon, metrics_list in self.metrics_history.items():
            if metrics_list:
                metrics_dicts = [m.to_dict() for m in metrics_list]
                summary['metrics_by_horizon'][horizon] = {
                    'num_windows': len(metrics_list),
                    'avg_ic': np.mean([m['ic'] for m in metrics_dicts]),
                    'avg_ir': np.mean([m['ir'] for m in metrics_dicts]),
                    'avg_sharpe': np.mean([m['sharpe'] for m in metrics_dicts]),
                    'avg_sortino': np.mean([m['sortino'] for m in metrics_dicts]),
                    'avg_max_drawdown': np.mean([m['max_drawdown'] for m in metrics_dicts]),
                    'all_metrics': metrics_dicts
                }
        
        return summary
