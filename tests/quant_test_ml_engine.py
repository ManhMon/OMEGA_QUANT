"""
Tests for Machine Learning Engine and Alpha Metrics (Institutional Grade)

Author: Machine Learning Engineer (Role 16)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path
from unittest.mock import patch

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from omega.quant.ml.ml_engine import (
    MLEngine,
    AlphaMetrics,
    ModelConfig,
    MLModelType,
    get_ml_engine,
)


class TestAlphaMetrics:
    """Test Alpha metrics computation."""
    
    def test_from_predictions(self):
        """Test computing metrics from predictions."""
        # Create correlated data
        np.random.seed(42)
        n = 100
        pred = pd.Series(np.random.randn(n))
        act = pred * 0.1 + np.random.randn(n) * 0.05
        
        metrics = AlphaMetrics.from_predictions(pred, act)
        
        assert metrics.ic > 0.8
        assert metrics.rank_ic > 0.8
        # Sharpe can be negative due to random data, just check it's computed
        assert isinstance(metrics.sharpe, float)
        assert metrics.win_rate > 0.5
    
    def test_pit_safety_shift(self):
        """Test PIT safety with T-1 lag shift."""
        np.random.seed(42)
        n = 100
        pred = pd.Series(np.random.randn(n))
        act = pred * 0.1 + np.random.randn(n) * 0.05
        
        # In PIT-safe mode with lag=1
        # Prediction at T must be compared with Return at T
        # But prediction at T is only available at T-1 for current returns
        # So we shift predictions forward by 1 period
        metrics = AlphaMetrics.with_pit_safety(pred, act, lag=1)
        
        # Correlated at T=0, but uncorrelated after T-1 shift
        assert abs(metrics.pit_ic) < 0.3
    
    def test_metrics_serialization(self):
        """Test converting metrics to dictionary."""
        metrics = AlphaMetrics(ic=0.1, sharpe=1.5)
        d = metrics.to_dict()
        
        assert d["ic"] == 0.1
        assert d["sharpe"] == 1.5

    def test_profit_factor_correctness(self):
        """Profit factor must count only winning and losing trades."""
        pred = pd.Series([1, 1, -1, -1, 1, 1, -1, -1, 1, -1], dtype=float)
        act = pd.Series([0.10, -0.20, -0.05, 0.08, 0.06, -0.03, -0.04, 0.02, 0.07, -0.01], dtype=float)

        metrics = AlphaMetrics.from_predictions(pred, act)

        expected_profits = 0.10 + 0.05 + 0.06 + 0.04 + 0.07 + 0.01
        expected_losses = 0.20 + 0.08 + 0.03 + 0.02
        assert metrics.profit_factor == pytest.approx(expected_profits / expected_losses)


class TestMLEngine:
    """Test ML Engine features."""
    
    def test_mock_training(self):
        """Test mock training path."""
        engine = MLEngine()
        X = pd.DataFrame(np.random.randn(100, 5), columns=["f1", "f2", "f3", "f4", "f5"])
        y = pd.Series(np.random.randn(100))
        
        model = engine.train_xgboost(
            model_id="test_model",
            X_train=X,
            y_train=y,
        )
        
        assert model.model_id == "test_model"
        assert model.model_type == MLModelType.XGBOOST
        assert len(model.feature_names) == 5
        assert model.metrics is not None
    
    def test_ensemble_prediction(self):
        """Test ensemble weighted voting."""
        engine = MLEngine()
        X = pd.DataFrame(np.random.randn(10, 2), columns=["f1", "f2"])
        y = pd.Series(np.random.randn(10))
        
        m1 = engine.train_xgboost("m1", X, y)
        m2 = engine.train_xgboost("m2", X, y)
        
        engine.store_model(m1)
        engine.store_model(m2)
        
        # Check models are stored
        assert "m1" in engine.models
        assert "m2" in engine.models
        
        # Mock doesn't have real predict, but interface is valid
        ensemble_pred = engine.ensemble_predict(
            model_ids=["m1", "m2"],
            X=X,
            weights={"m1": 0.7, "m2": 0.3}
        )
        
        assert len(ensemble_pred) == 10
        assert not ensemble_pred.isna().any()
    
    def test_feature_importance_mock(self):
        """Test getting feature importance."""
        engine = MLEngine()
        X = pd.DataFrame(np.random.randn(10, 5), columns=[f"f{i}" for i in range(5)])
        y = pd.Series(np.random.randn(10))
        
        model = engine.train_xgboost("m1", X, y)
        # Mock training doesn't set importance by default, but let's check interface
        engine.store_model(model)
        importance = engine.get_feature_importance("m1")
        assert isinstance(importance, pd.Series)

    def test_pit_safe_validation_metrics(self):
        """Validation metrics must carry PIT-safe values when validation set exists."""
        engine = MLEngine()
        train_index = pd.date_range("2024-01-01", periods=40, freq="D")
        val_index = pd.date_range("2024-03-01", periods=20, freq="D")
        X_train = pd.DataFrame({"f1": np.linspace(0, 1, 40)}, index=train_index)
        y_train = pd.Series(np.linspace(-0.1, 0.1, 40), index=train_index)
        X_val = pd.DataFrame({"f1": np.linspace(1, 2, 20)}, index=val_index)
        y_val = pd.Series(np.linspace(-0.2, 0.2, 20), index=val_index)

        class DummyBooster:
            def predict(self, dmatrix):
                data = dmatrix.get_label()
                return np.asarray(data, dtype=float)

            def get_score(self, importance_type="gain"):
                return {"f1": 1.0}

        with patch("xgboost.train", return_value=DummyBooster()):
            model = engine.train_xgboost("pit_val_model", X_train, y_train, X_val, y_val)

        expected = AlphaMetrics.with_pit_safety(pd.Series(y_val.values, index=val_index), y_val, lag=1)
        assert model.metrics.pit_ic == pytest.approx(expected.pit_ic)
        assert model.metrics.pit_rank_ic == pytest.approx(expected.pit_rank_ic)

    def test_ensemble_signal_normalization(self):
        """Ensemble must z-score normalize each model signal before weighting."""
        engine = MLEngine()
        index = pd.RangeIndex(4)
        X = pd.DataFrame({"f1": [0, 1, 2, 3]}, index=index)

        class StubModel:
            def __init__(self, values):
                self.values = np.asarray(values, dtype=float)

            def predict(self, X):
                return self.values

        engine.models["small"] = type("Stored", (), {"predict": StubModel([1, 2, 3, 4]).predict})()
        engine.models["large"] = type("Stored", (), {"predict": StubModel([100, 200, 300, 400]).predict})()

        ensemble = engine.ensemble_predict(["small", "large"], X, {"small": 0.5, "large": 0.5})
        expected_component = pd.Series([-1.3416407865, -0.4472135955, 0.4472135955, 1.3416407865], index=index)
        assert np.allclose(ensemble.values, expected_component.values)

    def test_chronological_split_enforcement(self):
        """Validation set must start after training set ends."""
        engine = MLEngine()
        train_index = pd.date_range("2024-01-01", periods=20, freq="D")
        val_index = pd.date_range("2024-01-15", periods=10, freq="D")
        X_train = pd.DataFrame({"f1": np.arange(20)}, index=train_index)
        y_train = pd.Series(np.arange(20, dtype=float), index=train_index)
        X_val = pd.DataFrame({"f1": np.arange(10)}, index=val_index)
        y_val = pd.Series(np.arange(10, dtype=float), index=val_index)

        with pytest.raises(ValueError, match="Chronological split violation"):
            engine.train_xgboost("chrono_fail", X_train, y_train, X_val, y_val)

    def test_walk_forward_integration(self):
        """Walk-forward trainer must aggregate folds and return final champion."""
        engine = MLEngine()
        dates = pd.date_range("2024-01-01", periods=8, freq="D")
        X = pd.DataFrame({"f1": np.arange(8, dtype=float), "f2": np.arange(8, dtype=float) * 2}, index=dates)
        y = pd.Series(np.linspace(-0.2, 0.2, 8), index=dates)

        class DummyFold:
            def __init__(self, fold_id, train_start, train_end, val_start, val_end):
                self.fold_id = fold_id
                self.train_start = train_start
                self.train_end = train_end
                self.val_start = val_start
                self.val_end = val_end

        class DummyWFResult:
            def __init__(self):
                self.folds = [
                    DummyFold(0, dates[0], dates[3], dates[3], dates[5]),
                    DummyFold(1, dates[1], dates[4], dates[4], dates[6]),
                ]
                self.metrics = {"overall_ic": 0.4, "overall_sharpe": 1.2}

        calls = []

        def fake_train(model_id, X_train, y_train, X_val=None, y_val=None, config=None, pit_safe=True):
            calls.append(model_id)
            return type(
                "DummyModel",
                (),
                {
                    "model_id": model_id,
                    "metrics": AlphaMetrics(
                        ic=0.2 if "fold_0" in model_id else 0.6 if "fold_1" in model_id else 0.9,
                        rank_ic=0.3,
                        sharpe=1.0,
                        pit_ic=0.15,
                        pit_rank_ic=0.12,
                    ),
                    "walk_forward_metrics": None,
                },
            )()

        with patch("omega.quant.ml.ml_engine.WalkForwardEnsemble.run", return_value=DummyWFResult()):
            with patch.object(MLEngine, "train_xgboost", side_effect=fake_train):
                champion = engine.train_xgboost_with_walk_forward("wf_model", X, y)

        assert calls == ["wf_model_fold_0", "wf_model_fold_1", "wf_model"]
        assert champion.model_id == "wf_model"
        assert champion.walk_forward_metrics["overall_ic"] == pytest.approx(0.4)
        assert champion.walk_forward_metrics["fold_count"] == pytest.approx(2.0)
        assert champion.walk_forward_metrics["avg_fold_ic"] == pytest.approx(0.4)


class TestMLEngineSingleton:
    """Test MLEngine singleton pattern."""
    
    def test_singleton(self):
        assert get_ml_engine() is get_ml_engine()
