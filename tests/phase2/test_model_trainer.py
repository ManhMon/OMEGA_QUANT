"""
Test Suite for Model Trainer

Tests cover:
1. Walk-forward window creation (non-overlapping, temporal ordering)
2. PIT safety validation (as_of <= available_at)
3. Training data preparation (feature scaling, target computation)
4. Validation data preparation (temporal boundaries)
5. Performance metrics computation (IC, IR, Sharpe, Sortino, MDD)
6. Hyperparameter optimization (Bayesian via optuna)
7. Model training (XGBoost, Random Forest)
8. Walk-forward training pipeline
9. Prediction interface
10. Training summary and logging

Reference: COMPREHENSIVE_SYSTEM_BUILD_PLAN.md Phase 2.3
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from omega.core.trainer import (
    ModelTrainer,
    WalkForwardWindow,
    PerformanceMetrics
)
from omega.core.model_registry import ModelRegistry


class TestWalkForwardWindow:
    """Test WalkForwardWindow dataclass."""
    
    def test_window_creation(self):
        """Test creating a walk-forward window."""
        start = pd.Timestamp('2024-01-01')
        end = pd.Timestamp('2024-12-31')
        val_start = pd.Timestamp('2025-01-01')
        val_end = pd.Timestamp('2025-03-31')
        
        window = WalkForwardWindow(
            train_start=start,
            train_end=end,
            validation_start=val_start,
            validation_end=val_end,
            horizon=1
        )
        
        assert window.train_start == start
        assert window.train_end == end
        assert window.validation_start == val_start
        assert window.validation_end == val_end
        assert window.horizon == 1
    
    def test_window_to_dict(self):
        """Test converting window to dictionary."""
        window = WalkForwardWindow(
            train_start=pd.Timestamp('2024-01-01'),
            train_end=pd.Timestamp('2024-12-31'),
            validation_start=pd.Timestamp('2025-01-01'),
            validation_end=pd.Timestamp('2025-03-31'),
            horizon=3
        )
        
        d = window.to_dict()
        assert isinstance(d, dict)
        assert 'train_start' in d
        assert 'horizon' in d
        assert d['horizon'] == 3


class TestPerformanceMetrics:
    """Test PerformanceMetrics dataclass."""
    
    def test_metrics_creation(self):
        """Test creating performance metrics."""
        metrics = PerformanceMetrics(
            ic=0.15,
            ir=1.2,
            sharpe=1.5,
            sortino=2.0,
            max_drawdown=-0.10,
            rmse=0.05,
            mae=0.03,
            r_squared=0.25
        )
        
        assert metrics.ic == 0.15
        assert metrics.sharpe == 1.5
        assert metrics.max_drawdown == -0.10
    
    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = PerformanceMetrics(
            ic=0.15,
            ir=1.2,
            sharpe=1.5,
            sortino=2.0,
            max_drawdown=-0.10,
            rmse=0.05,
            mae=0.03,
            r_squared=0.25
        )
        
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert d['ic'] == 0.15
        assert d['sharpe'] == 1.5


class TestModelTrainerInitialization:
    """Test ModelTrainer initialization."""
    
    def test_initialization_default(self):
        """Test initialization with default parameters."""
        trainer = ModelTrainer(model_name="test_model")
        
        assert trainer.model_name == "test_model"
        assert trainer.horizons == [1, 3, 5]
        assert trainer.min_train_days == 252
        assert trainer.min_validation_days == 63
    
    def test_initialization_custom_horizons(self):
        """Test initialization with custom horizons."""
        trainer = ModelTrainer(
            model_name="test_model",
            horizons=[1, 2, 3]
        )
        
        assert trainer.horizons == [1, 2, 3]
    
    def test_initialization_custom_window_sizes(self):
        """Test initialization with custom window sizes."""
        trainer = ModelTrainer(
            model_name="test_model",
            min_train_days=100,
            min_validation_days=50
        )
        
        assert trainer.min_train_days == 100
        assert trainer.min_validation_days == 50


class TestWalkForwardWindowCreation:
    """Test walk-forward window creation."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        dates = pd.date_range('2020-01-01', periods=500, freq='D')
        data = {
            'date': dates,
            'symbol': ['AAPL'] * 500,
            'close': np.random.randn(500).cumsum() + 100,
            'high': np.random.randn(500).cumsum() + 101,
            'low': np.random.randn(500).cumsum() + 99,
            'volume': np.random.randint(1000000, 10000000, 500),
            'available_at': dates + timedelta(days=1)
        }
        return pd.DataFrame(data)
    
    def test_create_windows_basic(self, sample_data):
        """Test basic window creation."""
        trainer = ModelTrainer(
            model_name="test_model",
            min_train_days=100,
            min_validation_days=50
        )
        
        windows = trainer.create_walk_forward_windows(sample_data)
        
        assert len(windows) > 0
        assert all(isinstance(w, WalkForwardWindow) for w in windows)
    
    def test_windows_non_overlapping(self, sample_data):
        """Test that windows are non-overlapping."""
        trainer = ModelTrainer(
            model_name="test_model",
            min_train_days=100,
            min_validation_days=50
        )
        
        windows = trainer.create_walk_forward_windows(sample_data)
        
        # Group by horizon
        windows_by_horizon = {}
        for w in windows:
            if w.horizon not in windows_by_horizon:
                windows_by_horizon[w.horizon] = []
            windows_by_horizon[w.horizon].append(w)
        
        # Check non-overlapping for each horizon
        for horizon, horizon_windows in windows_by_horizon.items():
            sorted_windows = sorted(horizon_windows, key=lambda w: w.train_start)
            for i in range(len(sorted_windows) - 1):
                current = sorted_windows[i]
                next_window = sorted_windows[i + 1]
                # Validation end of current should be before train start of next
                assert current.validation_end < next_window.train_start
    
    def test_windows_pit_safety_embargo(self, sample_data):
        """Test PIT safety: validation starts after train_end + max_horizon."""
        trainer = ModelTrainer(
            model_name="test_model",
            horizons=[1, 3, 5],
            min_train_days=100,
            min_validation_days=50
        )
        
        windows = trainer.create_walk_forward_windows(sample_data)
        max_horizon = max(trainer.horizons)
        
        for window in windows:
            # Validation should start at least max_horizon days after train_end
            embargo_end = window.train_end + timedelta(days=max_horizon)
            assert window.validation_start >= embargo_end
    
    def test_insufficient_data_raises_error(self):
        """Test that insufficient data raises error."""
        dates = pd.date_range('2020-01-01', periods=50, freq='D')
        data = {
            'date': dates,
            'symbol': ['AAPL'] * 50,
            'close': np.random.randn(50).cumsum() + 100,
            'available_at': dates + timedelta(days=1)
        }
        df = pd.DataFrame(data)
        
        trainer = ModelTrainer(
            model_name="test_model",
            min_train_days=100,
            min_validation_days=50
        )
        
        with pytest.raises(ValueError, match="Insufficient data"):
            trainer.create_walk_forward_windows(df)


class TestPITSafetyValidation:
    """Test PIT safety validation."""
    
    def test_pit_safety_valid_data(self):
        """Test PIT safety validation with valid data."""
        trainer = ModelTrainer(model_name="test_model")
        
        dates = pd.date_range('2020-01-01', periods=100, freq='D')
        data = {
            'date': dates,
            'available_at': dates + timedelta(days=1)
        }
        df = pd.DataFrame(data)
        
        # Should not raise
        assert trainer._validate_pit_safety(df) is True
    
    def test_pit_safety_violation_detected(self):
        """Test that PIT safety violations are detected."""
        trainer = ModelTrainer(model_name="test_model")
        
        dates = pd.date_range('2020-01-01', periods=100, freq='D')
        data = {
            'date': dates,
            'available_at': dates - timedelta(days=1)  # Look-ahead!
        }
        df = pd.DataFrame(data)
        
        with pytest.raises(ValueError, match="PIT safety violation"):
            trainer._validate_pit_safety(df)


class TestDataPreparation:
    """Test training and validation data preparation."""
    
    @pytest.fixture
    def sample_data_with_features(self):
        """Create sample data with features."""
        dates = pd.date_range('2020-01-01', periods=500, freq='D')
        data = {
            'date': dates,
            'symbol': ['AAPL'] * 500,
            'close': np.random.randn(500).cumsum() + 100,
            'available_at': dates + timedelta(days=1),
            'feat_rsi': np.random.uniform(0, 100, 500),
            'feat_macd': np.random.randn(500),
            'feat_bb_position': np.random.uniform(0, 1, 500)
        }
        return pd.DataFrame(data)
    
    def test_prepare_training_data(self, sample_data_with_features):
        """Test training data preparation."""
        trainer = ModelTrainer(model_name="test_model")
        
        window = WalkForwardWindow(
            train_start=pd.Timestamp('2020-01-01'),
            train_end=pd.Timestamp('2020-06-30'),
            validation_start=pd.Timestamp('2020-07-01'),
            validation_end=pd.Timestamp('2020-09-30'),
            horizon=1
        )
        
        feature_cols = ['feat_rsi', 'feat_macd', 'feat_bb_position']
        
        X, y, metadata = trainer.prepare_training_data(
            sample_data_with_features,
            feature_cols=feature_cols,
            target_col='close',
            window=window
        )
        
        assert X.shape[0] > 0
        assert X.shape[1] == len(feature_cols)
        assert len(y) == X.shape[0]
    
    def test_prepare_validation_data(self, sample_data_with_features):
        """Test validation data preparation."""
        trainer = ModelTrainer(model_name="test_model")
        
        window = WalkForwardWindow(
            train_start=pd.Timestamp('2020-01-01'),
            train_end=pd.Timestamp('2020-06-30'),
            validation_start=pd.Timestamp('2020-07-10'),
            validation_end=pd.Timestamp('2020-09-30'),
            horizon=1
        )
        
        feature_cols = ['feat_rsi', 'feat_macd', 'feat_bb_position']
        
        X, y, metadata = trainer.prepare_validation_data(
            sample_data_with_features,
            feature_cols=feature_cols,
            target_col='close',
            window=window
        )
        
        assert X.shape[0] > 0
        assert X.shape[1] == len(feature_cols)
        assert len(y) == X.shape[0]


class TestPerformanceMetricsComputation:
    """Test performance metrics computation."""
    
    def test_compute_metrics_basic(self):
        """Test basic metrics computation."""
        trainer = ModelTrainer(model_name="test_model")
        
        y_true = np.array([0.01, 0.02, -0.01, 0.03, -0.02])
        y_pred = np.array([0.015, 0.018, -0.008, 0.032, -0.025])
        
        metrics = trainer.compute_metrics(y_true, y_pred)
        
        assert isinstance(metrics, PerformanceMetrics)
        assert -1 <= metrics.ic <= 1  # IC should be correlation
        assert metrics.rmse >= 0
        assert metrics.mae >= 0
    
    def test_compute_metrics_perfect_prediction(self):
        """Test metrics with perfect prediction."""
        trainer = ModelTrainer(model_name="test_model")
        
        y_true = np.array([0.01, 0.02, -0.01, 0.03, -0.02])
        y_pred = y_true.copy()
        
        metrics = trainer.compute_metrics(y_true, y_pred)
        
        assert metrics.ic == 1.0  # Perfect correlation
        assert metrics.rmse == 0.0
        assert metrics.mae == 0.0
    
    def test_compute_metrics_negative_correlation(self):
        """Test metrics with negative correlation."""
        trainer = ModelTrainer(model_name="test_model")
        
        y_true = np.array([0.01, 0.02, -0.01, 0.03, -0.02])
        y_pred = -y_true  # Opposite predictions
        
        metrics = trainer.compute_metrics(y_true, y_pred)
        
        assert metrics.ic < 0  # Negative correlation


class TestModelTraining:
    """Test model training."""
    
    @pytest.fixture
    def sample_training_data(self):
        """Create sample training data."""
        X = np.random.randn(100, 10)
        y = np.random.randn(100)
        return X, y
    
    def test_train_xgboost_model(self, sample_training_data):
        """Test training XGBoost model."""
        trainer = ModelTrainer(model_name="test_model")
        X, y = sample_training_data
        
        model, scaler = trainer.train_single_model(
            X, y,
            model_type='xgboost'
        )
        
        assert model is not None
        assert scaler is not None
        
        # Test prediction
        X_scaled = scaler.transform(X[:5])
        predictions = model.predict(X_scaled)
        assert len(predictions) == 5
    
    def test_train_random_forest_model(self, sample_training_data):
        """Test training Random Forest model."""
        trainer = ModelTrainer(model_name="test_model")
        X, y = sample_training_data
        
        model, scaler = trainer.train_single_model(
            X, y,
            model_type='random_forest'
        )
        
        assert model is not None
        assert scaler is not None
    
    def test_train_with_custom_hyperparams(self, sample_training_data):
        """Test training with custom hyperparameters."""
        trainer = ModelTrainer(model_name="test_model")
        X, y = sample_training_data
        
        hyperparams = {
            'n_estimators': 50,
            'max_depth': 3
        }
        
        model, scaler = trainer.train_single_model(
            X, y,
            model_type='xgboost',
            hyperparams=hyperparams
        )
        
        assert model is not None


class TestHyperparameterOptimization:
    """Test hyperparameter optimization."""
    
    @pytest.fixture
    def sample_opt_data(self):
        """Create sample data for optimization."""
        X_train = np.random.randn(100, 10)
        y_train = np.random.randn(100)
        X_val = np.random.randn(50, 10)
        y_val = np.random.randn(50)
        return X_train, y_train, X_val, y_val
    
    def test_optimize_hyperparameters_xgboost(self, sample_opt_data):
        """Test hyperparameter optimization for XGBoost."""
        trainer = ModelTrainer(model_name="test_model")
        X_train, y_train, X_val, y_val = sample_opt_data
        
        best_params = trainer.optimize_hyperparameters(
            X_train, y_train, X_val, y_val,
            model_type='xgboost',
            n_trials=5,
            timeout=60
        )
        
        assert isinstance(best_params, dict)
        assert 'n_estimators' in best_params
        assert 'max_depth' in best_params
    
    def test_optimize_hyperparameters_random_forest(self, sample_opt_data):
        """Test hyperparameter optimization for Random Forest."""
        trainer = ModelTrainer(model_name="test_model")
        X_train, y_train, X_val, y_val = sample_opt_data
        
        best_params = trainer.optimize_hyperparameters(
            X_train, y_train, X_val, y_val,
            model_type='random_forest',
            n_trials=5,
            timeout=60
        )
        
        assert isinstance(best_params, dict)
        assert 'n_estimators' in best_params


class TestPrediction:
    """Test prediction interface."""
    
    @pytest.fixture
    def trained_trainer(self):
        """Create a trainer with trained models."""
        trainer = ModelTrainer(model_name="test_model", horizons=[1, 3])
        
        # Train models for each horizon
        X_train = np.random.randn(100, 10)
        y_train = np.random.randn(100)
        
        for horizon in trainer.horizons:
            model, scaler = trainer.train_single_model(X_train, y_train)
            trainer.models[horizon] = model
            trainer.scalers[horizon] = scaler
        
        return trainer
    
    def test_predict_horizon_1(self, trained_trainer):
        """Test prediction for horizon 1."""
        X = np.random.randn(10, 10)
        predictions = trained_trainer.predict(X, horizon=1)
        
        assert len(predictions) == 10
    
    def test_predict_horizon_3(self, trained_trainer):
        """Test prediction for horizon 3."""
        X = np.random.randn(10, 10)
        predictions = trained_trainer.predict(X, horizon=3)
        
        assert len(predictions) == 10
    
    def test_predict_untrained_horizon_raises_error(self, trained_trainer):
        """Test that predicting with untrained horizon raises error."""
        X = np.random.randn(10, 10)
        
        with pytest.raises(ValueError, match="No model trained"):
            trained_trainer.predict(X, horizon=5)


class TestTrainingSummary:
    """Test training summary generation."""
    
    def test_get_training_summary_empty(self):
        """Test summary with no training."""
        trainer = ModelTrainer(model_name="test_model")
        summary = trainer.get_training_summary()
        
        assert summary['model_name'] == "test_model"
        assert summary['num_windows'] == 0
    
    def test_get_training_summary_with_metrics(self):
        """Test summary with metrics."""
        trainer = ModelTrainer(model_name="test_model", horizons=[1])
        
        # Add mock metrics
        metrics = PerformanceMetrics(
            ic=0.15,
            ir=1.2,
            sharpe=1.5,
            sortino=2.0,
            max_drawdown=-0.10,
            rmse=0.05,
            mae=0.03,
            r_squared=0.25
        )
        trainer.metrics_history[1] = [metrics]
        
        summary = trainer.get_training_summary()
        
        assert 1 in summary['metrics_by_horizon']
        assert summary['metrics_by_horizon'][1]['num_windows'] == 1
        assert 'avg_ic' in summary['metrics_by_horizon'][1]


class TestWalkForwardTrainingPipeline:
    """Test complete walk-forward training pipeline."""
    
    @pytest.fixture
    def sample_data_for_training(self):
        """Create sample data for full training pipeline."""
        dates = pd.date_range('2020-01-01', periods=500, freq='D')
        data = {
            'date': dates,
            'symbol': ['AAPL'] * 500,
            'close': np.random.randn(500).cumsum() + 100,
            'high': np.random.randn(500).cumsum() + 101,
            'low': np.random.randn(500).cumsum() + 99,
            'volume': np.random.randint(1000000, 10000000, 500),
            'available_at': dates + timedelta(days=1),
            'feat_rsi': np.random.uniform(0, 100, 500),
            'feat_macd': np.random.randn(500),
            'feat_bb_position': np.random.uniform(0, 1, 500),
            'feat_atr': np.random.uniform(0, 5, 500)
        }
        return pd.DataFrame(data)
    
    def test_train_walk_forward_basic(self, sample_data_for_training):
        """Test basic walk-forward training."""
        trainer = ModelTrainer(
            model_name="test_model",
            horizons=[1],
            min_train_days=100,
            min_validation_days=50
        )
        
        feature_cols = ['feat_rsi', 'feat_macd', 'feat_bb_position', 'feat_atr']
        
        results = trainer.train_walk_forward(
            sample_data_for_training,
            feature_cols=feature_cols,
            model_type='xgboost',
            optimize_hyperparams=False
        )
        
        assert 1 in results
        assert 'model' in results[1]
        assert 'scaler' in results[1]
        assert 'metrics' in results[1]
    
    def test_train_walk_forward_multiple_horizons(self, sample_data_for_training):
        """Test walk-forward training with multiple horizons."""
        trainer = ModelTrainer(
            model_name="test_model",
            horizons=[1, 3],
            min_train_days=100,
            min_validation_days=50
        )
        
        feature_cols = ['feat_rsi', 'feat_macd', 'feat_bb_position', 'feat_atr']
        
        results = trainer.train_walk_forward(
            sample_data_for_training,
            feature_cols=feature_cols,
            model_type='xgboost',
            optimize_hyperparams=False
        )
        
        assert 1 in results
        assert 3 in results
    
    def test_train_walk_forward_with_optimization(self, sample_data_for_training):
        """Test walk-forward training with hyperparameter optimization."""
        trainer = ModelTrainer(
            model_name="test_model",
            horizons=[1],
            min_train_days=100,
            min_validation_days=50
        )
        
        feature_cols = ['feat_rsi', 'feat_macd', 'feat_bb_position', 'feat_atr']
        
        results = trainer.train_walk_forward(
            sample_data_for_training,
            feature_cols=feature_cols,
            model_type='xgboost',
            optimize_hyperparams=True,
            n_trials=3
        )
        
        assert 1 in results
        assert results[1]['model'] is not None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_model_type_raises_error(self):
        """Test that invalid model type raises error."""
        trainer = ModelTrainer(model_name="test_model")
        X = np.random.randn(100, 10)
        y = np.random.randn(100)
        
        with pytest.raises(ValueError, match="Unknown model type"):
            trainer.train_single_model(X, y, model_type='invalid_model')
    
    def test_empty_feature_columns(self):
        """Test handling of empty feature columns."""
        trainer = ModelTrainer(model_name="test_model")
        
        dates = pd.date_range('2020-01-01', periods=100, freq='D')
        data = {
            'date': dates,
            'symbol': ['AAPL'] * 100,
            'close': np.random.randn(100).cumsum() + 100,
            'available_at': dates + timedelta(days=1)
        }
        df = pd.DataFrame(data)
        
        window = WalkForwardWindow(
            train_start=pd.Timestamp('2020-01-01'),
            train_end=pd.Timestamp('2020-03-31'),
            validation_start=pd.Timestamp('2020-04-01'),
            validation_end=pd.Timestamp('2020-06-30'),
            horizon=1
        )
        
        # Should handle gracefully (may raise or return empty)
        try:
            X, y, _ = trainer.prepare_training_data(
                df,
                feature_cols=[],
                target_col='close',
                window=window
            )
            assert X.shape[1] == 0
        except (ValueError, KeyError):
            pass  # Expected behavior


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
