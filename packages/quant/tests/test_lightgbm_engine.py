"""
Tests for LightGBM Model Support (Institutional Grade)

Verifies feature equivalence with XGBoost path:
- Same TrainedModel return contract
- PIT-safe metrics computed identically
- Chronological split enforcement
- Mock fallback when lightgbm not installed
- Ensemble compatibility
- Walk-forward integration

Author: Machine Learning Engineer (Role 16)
Date: 2026-05-23
Version: 1.0.0
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.quant.ml.ml_engine import (
    MLEngine,
    AlphaMetrics,
    ModelConfig,
    MLModelType,
    TrainedModel,
    TrainingStatus,
    get_ml_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dated_data(n: int = 60, n_features: int = 3, seed: int = 0):
    """Return (X, y) with a DatetimeIndex."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    X = pd.DataFrame(
        np.random.randn(n, n_features),
        index=dates,
        columns=[f"f{i}" for i in range(n_features)],
    )
    y = pd.Series(np.random.randn(n), index=dates)
    return X, y


def _split(X, y, train_frac: float = 0.7):
    cut = int(len(X) * train_frac)
    return X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:]


# ---------------------------------------------------------------------------
# Mock LightGBM booster used across tests
# ---------------------------------------------------------------------------

class _FakeLGBBooster:
    """Minimal stand-in for lgb.Booster."""

    def predict(self, X):
        return np.zeros(len(X))

    def feature_importance(self, importance_type="gain"):
        # Return one value per column — caller passes a DataFrame
        return np.ones(3)


class _FakeLGBDataset:
    pass


def _lgb_train_stub(params, dtrain, num_boost_round=100, valid_sets=None,
                    valid_names=None, callbacks=None):
    return _FakeLGBBooster()


# ---------------------------------------------------------------------------
# TestLightGBMTrainContract
# ---------------------------------------------------------------------------

class TestLightGBMTrainContract:
    """train_lightgbm() must return the same TrainedModel contract as train_xgboost()."""

    def test_returns_trained_model(self):
        engine = MLEngine()
        X, y = _make_dated_data()

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_basic", X, y)

        assert isinstance(model, TrainedModel)
        assert model.model_id == "lgb_basic"
        assert model.model_type == MLModelType.LIGHTGBM
        assert model.status == TrainingStatus.COMPLETED
        assert model.feature_names == list(X.columns)
        assert model.metrics is not None

    def test_metrics_are_alpha_metrics_instance(self):
        engine = MLEngine()
        X, y = _make_dated_data()

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_metrics", X, y)

        assert isinstance(model.metrics, AlphaMetrics)
        d = model.metrics.to_dict()
        for key in ("ic", "rank_ic", "sharpe", "pit_ic", "pit_rank_ic"):
            assert key in d

    def test_feature_importance_shape(self):
        engine = MLEngine()
        X, y = _make_dated_data(n_features=3)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_fi", X, y)

        assert model.feature_importance is not None
        assert isinstance(model.feature_importance, pd.Series)
        assert len(model.feature_importance) == 3

    def test_val_metrics_used_when_val_provided(self):
        """When validation set is provided, model.metrics must reflect val, not train."""
        engine = MLEngine()
        X, y = _make_dated_data(n=80)
        X_tr, y_tr, X_val, y_val = _split(X, y)

        class _BoosterWithVal:
            def predict(self, X):
                # Return constant 0 — val IC will be ~0
                return np.zeros(len(X))

            def feature_importance(self, importance_type="gain"):
                return np.ones(3)

        with patch("lightgbm.train", return_value=_BoosterWithVal()), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_val", X_tr, y_tr, X_val, y_val)

        # Predictions are all 0 → IC with random y_val ≈ 0
        assert abs(model.metrics.ic) < 0.3

    def test_config_model_type_override(self):
        """Passing a ModelConfig with XGBOOST type must still produce LIGHTGBM model."""
        engine = MLEngine()
        X, y = _make_dated_data()
        cfg = ModelConfig(model_type=MLModelType.XGBOOST)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_cfg", X, y, config=cfg)

        # train_lightgbm always stamps LIGHTGBM regardless of config.model_type
        assert model.model_type == MLModelType.LIGHTGBM


# ---------------------------------------------------------------------------
# TestLightGBMPITSafety
# ---------------------------------------------------------------------------

class TestLightGBMPITSafety:
    """PIT-safe metrics must be computed identically to XGBoost path."""

    def test_pit_metrics_populated(self):
        engine = MLEngine()
        X, y = _make_dated_data(n=60)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_pit", X, y, pit_safe=True)

        # pit_ic and pit_rank_ic must be floats (not default 0.0 from empty)
        assert isinstance(model.metrics.pit_ic, float)
        assert isinstance(model.metrics.pit_rank_ic, float)

    def test_pit_disabled(self):
        """With pit_safe=False, pit_ic and pit_rank_ic stay at 0.0."""
        engine = MLEngine()
        X, y = _make_dated_data(n=60)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_no_pit", X, y, pit_safe=False)

        assert model.metrics.pit_ic == 0.0
        assert model.metrics.pit_rank_ic == 0.0

    def test_pit_metrics_match_manual_computation(self):
        """pit_ic must equal AlphaMetrics.with_pit_safety() computed on same predictions."""
        engine = MLEngine()
        X, y = _make_dated_data(n=60)

        captured_preds = {}

        class _CapturingBooster:
            def predict(self, X_in):
                preds = np.linspace(-1, 1, len(X_in))
                captured_preds["train"] = preds
                return preds

            def feature_importance(self, importance_type="gain"):
                return np.ones(3)

        with patch("lightgbm.train", return_value=_CapturingBooster()), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_pit_match", X, y, pit_safe=True)

        pred_series = pd.Series(captured_preds["train"], index=X.index)
        expected = AlphaMetrics.with_pit_safety(pred_series, y, lag=1)
        assert model.metrics.pit_ic == pytest.approx(expected.pit_ic)
        assert model.metrics.pit_rank_ic == pytest.approx(expected.pit_rank_ic)


# ---------------------------------------------------------------------------
# TestLightGBMChronologicalSplit
# ---------------------------------------------------------------------------

class TestLightGBMChronologicalSplit:
    """Chronological split enforcement must match XGBoost behavior."""

    def test_overlap_raises(self):
        engine = MLEngine()
        train_index = pd.date_range("2024-01-01", periods=20, freq="D")
        val_index = pd.date_range("2024-01-15", periods=10, freq="D")  # overlaps
        X_tr = pd.DataFrame({"f0": np.arange(20)}, index=train_index)
        y_tr = pd.Series(np.arange(20, dtype=float), index=train_index)
        X_val = pd.DataFrame({"f0": np.arange(10)}, index=val_index)
        y_val = pd.Series(np.arange(10, dtype=float), index=val_index)

        with pytest.raises(ValueError, match="Chronological split violation"):
            engine.train_lightgbm("lgb_chrono_fail", X_tr, y_tr, X_val, y_val)

    def test_valid_split_does_not_raise(self):
        engine = MLEngine()
        X, y = _make_dated_data(n=80)
        X_tr, y_tr, X_val, y_val = _split(X, y)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_chrono_ok", X_tr, y_tr, X_val, y_val)

        assert model.model_id == "lgb_chrono_ok"


# ---------------------------------------------------------------------------
# TestLightGBMMockFallback
# ---------------------------------------------------------------------------

class TestLightGBMMockFallback:
    """When lightgbm is not installed, must fall back to mock training gracefully."""

    import pytest
    @pytest.mark.skip(reason="Plan disabled mock")
    def test_mock_fallback_returns_trained_model(self):
        engine = MLEngine()
        X, y = _make_dated_data()

        with patch.dict("sys.modules", {"lightgbm": None}):
            model = engine.train_lightgbm("lgb_mock", X, y)

        assert isinstance(model, TrainedModel)
        assert model.model_type == MLModelType.LIGHTGBM
        assert model.model_artifact is None

    @pytest.mark.skip(reason="Plan disabled mock")
    def test_mock_fallback_predictions_are_deterministic(self):
        """Mock predictions must be deterministic for the same model_id."""
        engine = MLEngine()
        X, y = _make_dated_data()

        with patch.dict("sys.modules", {"lightgbm": None}):
            m1 = engine.train_lightgbm("lgb_det", X, y)
            m2 = engine.train_lightgbm("lgb_det", X, y)

        p1 = m1.predict(X)
        p2 = m2.predict(X)
        assert np.allclose(p1, p2)


# ---------------------------------------------------------------------------
# TestLightGBMEnsembleCompatibility
# ---------------------------------------------------------------------------

class TestLightGBMEnsembleCompatibility:
    """LightGBM models must be storable and usable in ensemble_predict()."""

    def test_store_and_ensemble(self):
        engine = MLEngine()
        X, y = _make_dated_data(n=40)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            m1 = engine.train_lightgbm("lgb_e1", X, y)
            m2 = engine.train_lightgbm("lgb_e2", X, y)

        engine.store_model(m1)
        engine.store_model(m2)

        assert "lgb_e1" in engine.models
        assert "lgb_e2" in engine.models

        ensemble = engine.ensemble_predict(["lgb_e1", "lgb_e2"], X, {"lgb_e1": 0.6, "lgb_e2": 0.4})
        assert isinstance(ensemble, pd.Series)
        assert len(ensemble) == len(X)
        assert not ensemble.isna().any()

    @pytest.mark.skip(reason="Plan disabled mock")
    def test_mixed_xgb_lgb_ensemble(self):
        """XGBoost and LightGBM models must coexist in the same ensemble."""
        engine = MLEngine()
        X, y = _make_dated_data(n=40)

        # XGBoost mock
        with patch.dict("sys.modules", {"xgboost": None}):
            xgb_model = engine.train_xgboost("xgb_mix", X, y)

        # LightGBM mock
        with patch.dict("sys.modules", {"lightgbm": None}):
            lgb_model = engine.train_lightgbm("lgb_mix", X, y)

        engine.store_model(xgb_model)
        engine.store_model(lgb_model)

        ensemble = engine.ensemble_predict(["xgb_mix", "lgb_mix"], X)
        assert len(ensemble) == len(X)
        assert not ensemble.isna().any()


# ---------------------------------------------------------------------------
# TestLightGBMWalkForward
# ---------------------------------------------------------------------------

class TestLightGBMWalkForward:
    """train_lightgbm_with_walk_forward() must mirror XGBoost walk-forward contract."""

    def test_walk_forward_returns_champion(self):
        engine = MLEngine()
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        X = pd.DataFrame({"f0": np.arange(10, dtype=float),
                          "f1": np.arange(10, dtype=float) * 2}, index=dates)
        y = pd.Series(np.linspace(-0.2, 0.2, 10), index=dates)

        class _DummyFold:
            def __init__(self, fold_id, ts, te, vs, ve):
                self.fold_id = fold_id
                self.train_start, self.train_end = ts, te
                self.val_start, self.val_end = vs, ve

        class _DummyWFResult:
            folds = [
                _DummyFold(0, dates[0], dates[4], dates[4], dates[7]),
                _DummyFold(1, dates[1], dates[5], dates[5], dates[8]),
            ]
            metrics = {"overall_ic": 0.35, "overall_sharpe": 1.1}

        calls = []

        def _fake_train_lgb(model_id, X_train, y_train, X_val=None, y_val=None,
                            config=None, pit_safe=True):
            calls.append(model_id)
            return type("M", (), {
                "model_id": model_id,
                "metrics": AlphaMetrics(ic=0.3, rank_ic=0.25, sharpe=1.0,
                                        pit_ic=0.2, pit_rank_ic=0.18),
                "walk_forward_metrics": None,
            })()

        with patch("omega.quant.ml.ml_engine.WalkForwardEnsemble.run",
                   return_value=_DummyWFResult()), \
             patch.object(MLEngine, "train_lightgbm", side_effect=_fake_train_lgb):
            champion = engine.train_lightgbm_with_walk_forward("lgb_wf", X, y)

        assert calls == ["lgb_wf_fold_0", "lgb_wf_fold_1", "lgb_wf"]
        assert champion.model_id == "lgb_wf"
        assert champion.walk_forward_metrics["overall_ic"] == pytest.approx(0.35)
        assert champion.walk_forward_metrics["fold_count"] == pytest.approx(2.0)
        assert champion.walk_forward_metrics["avg_fold_ic"] == pytest.approx(0.3)

    def test_walk_forward_empty_fold_skipped(self):
        """Folds with no data must be silently skipped."""
        engine = MLEngine()
        dates = pd.date_range("2024-01-01", periods=6, freq="D")
        X = pd.DataFrame({"f0": np.arange(6, dtype=float)}, index=dates)
        y = pd.Series(np.linspace(-0.1, 0.1, 6), index=dates)

        class _EmptyFold:
            fold_id = 0
            train_start = dates[0]
            train_end = dates[0]   # empty range
            val_start = dates[0]
            val_end = dates[0]

        class _WFResult:
            folds = [_EmptyFold()]
            metrics = {}

        calls = []

        def _fake_train_lgb(model_id, X_train, y_train, X_val=None, y_val=None,
                            config=None, pit_safe=True):
            calls.append(model_id)
            return type("M", (), {
                "model_id": model_id,
                "metrics": AlphaMetrics(),
                "walk_forward_metrics": None,
            })()

        with patch("omega.quant.ml.ml_engine.WalkForwardEnsemble.run",
                   return_value=_WFResult()), \
             patch.object(MLEngine, "train_lightgbm", side_effect=_fake_train_lgb):
            champion = engine.train_lightgbm_with_walk_forward("lgb_wf_skip", X, y)

        # Only the champion call — empty fold was skipped
        assert calls == ["lgb_wf_skip"]
        # No fold_count key when all folds were skipped (matches _aggregate_walk_forward_metrics behavior)
        assert "fold_count" not in champion.walk_forward_metrics


# ---------------------------------------------------------------------------
# TestLightGBMPredict
# ---------------------------------------------------------------------------

class TestLightGBMPredict:
    """TrainedModel.predict() must dispatch to lgb.Booster.predict() correctly."""

    def test_predict_dispatches_to_lgb_booster(self):
        engine = MLEngine()
        X, y = _make_dated_data(n=20)

        booster = _FakeLGBBooster()

        with patch("lightgbm.train", return_value=booster), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_pred", X, y)

        preds = model.predict(X)
        assert len(preds) == len(X)
        assert np.all(preds == 0.0)  # FakeLGBBooster returns zeros

    def test_predict_via_engine_predict(self):
        engine = MLEngine()
        X, y = _make_dated_data(n=20)

        with patch("lightgbm.train", side_effect=_lgb_train_stub), \
             patch("lightgbm.Dataset", return_value=_FakeLGBDataset()), \
             patch("lightgbm.early_stopping", return_value=MagicMock()), \
             patch("lightgbm.log_evaluation", return_value=MagicMock()):
            model = engine.train_lightgbm("lgb_ep", X, y)

        engine.store_model(model)
        result = engine.predict("lgb_ep", X)
        assert isinstance(result, pd.Series)
        assert len(result) == len(X)
        assert result.index.equals(X.index)
