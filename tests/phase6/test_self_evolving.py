"""
Unit tests for Continuous Learning & Drift Detection - OMEGA Phase 6.1
"""

import pytest
import pandas as pd
import numpy as np

from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig

@pytest.fixture
def mock_cl_engine():
    return ContinuousLearningEngine(ContinuousLearningConfig(retraining_interval_days=7))

@pytest.fixture
def mock_drift_ensemble():
    return DriftDetectorEnsemble(DriftDetectorConfig())

class TestContinuousLearning:
    def test_should_retrain(self, mock_cl_engine):
        current_date = pd.Timestamp("2026-05-17")
        assert mock_cl_engine.should_retrain(current_date) is True
        
        mock_cl_engine.last_retrain_date = current_date
        assert mock_cl_engine.should_retrain(current_date) is False
        
        # 6 days later: should NOT retrain
        future_date_6 = current_date + pd.Timedelta(days=6)
        assert mock_cl_engine.should_retrain(future_date_6) is False
        
        # 7 days later: should retrain
        future_date_7 = current_date + pd.Timedelta(days=7)
        assert mock_cl_engine.should_retrain(future_date_7) is True

    def test_evaluate_model(self, mock_cl_engine):
        predictions = pd.Series([1.0, 2.0, 3.0, 4.0])
        actuals = pd.Series([1.1, 1.9, 3.2, 3.8])
        
        metrics = mock_cl_engine.evaluate_model(predictions, actuals, "test_model")
        
        assert metrics["model_name"] == "test_model"
        assert metrics["ic"] > 0.90
        assert metrics["sharpe"] > 0.0

    def test_champion_vs_challenger_promotion(self, mock_cl_engine):
        champion_metrics = {"ic": 0.10, "sharpe": 1.2}
        challenger_metrics_better = {"ic": 0.16, "sharpe": 1.5}
        
        should_promote, reason = mock_cl_engine.champion_vs_challenger(
            champion_metrics,
            challenger_metrics_better
        )
        assert should_promote is True
        assert "improved" in reason.lower()

    def test_champion_vs_challenger_retained(self, mock_cl_engine):
        champion_metrics = {"ic": 0.15, "sharpe": 1.5}
        challenger_metrics_worse = {"ic": 0.12, "sharpe": 1.1}
        
        should_promote, reason = mock_cl_engine.champion_vs_challenger(
            champion_metrics,
            challenger_metrics_worse
        )
        assert should_promote is False
        assert "sharpe" in reason.lower() or "no significant" in reason.lower()

class TestDriftDetector:
    def test_detect_sharpe_drift(self, mock_drift_ensemble):
        historical_sharpe = [1.5, 1.4, 1.6, 1.5]
        
        # Current Sharpe is 1.4 (no drift, ~7% drop)
        assert mock_drift_ensemble.detect_sharpe_drift(1.4, historical_sharpe) == False
        
        # Current Sharpe is 0.9 (drift, ~40% drop)
        assert mock_drift_ensemble.detect_sharpe_drift(0.9, historical_sharpe) == True

    def test_detect_ic_drift(self, mock_drift_ensemble):
        historical_ic = [0.15, 0.14, 0.16, 0.15]
        
        # Current IC is 0.13 (no drift, ~13% drop)
        assert mock_drift_ensemble.detect_ic_drift(0.13, historical_ic) == False
        
        # Current IC is 0.10 (drift, ~33% drop)
        assert mock_drift_ensemble.detect_ic_drift(0.10, historical_ic) == True

    def test_detect_turnover_spike(self, mock_drift_ensemble):
        historical_turnover = [0.20, 0.22, 0.19, 0.21]
        
        # Current turnover is 0.25 (no spike)
        assert mock_drift_ensemble.detect_turnover_spike(0.25, historical_turnover) == False
        
        # Current turnover is 0.35 (spike, ~70% increase)
        assert mock_drift_ensemble.detect_turnover_spike(0.35, historical_turnover) == True

    def test_check_drift_majority_voting(self, mock_drift_ensemble):
        # Setup history
        dates = pd.date_range("2026-05-01", periods=5)
        for d in dates:
            mock_drift_ensemble.record_metrics(d, 1.5, 0.15, 0.20)
            
        # Case 1: Only Sharpe drops -> No overall drift (1-of-3)
        result1 = mock_drift_ensemble.check_drift(0.9, 0.14, 0.21)
        assert result1["drift_detected"] == False
        assert len(result1["detectors_triggered"]) == 1
        
        # Case 2: Sharpe and IC both drop -> Drift detected (2-of-3)
        result2 = mock_drift_ensemble.check_drift(0.9, 0.10, 0.21)
        assert result2["drift_detected"] == True
        assert len(result2["detectors_triggered"]) == 2
        assert "sharpe_drop" in result2["detectors_triggered"]
        assert "ic_drop" in result2["detectors_triggered"]

    def test_get_rollback_signal(self, mock_drift_ensemble):
        dates = pd.date_range("2026-05-01", periods=5)
        for d in dates:
            mock_drift_ensemble.record_metrics(d, 1.5, 0.15, 0.20)
            
        # Drift -> should rollback
        assert mock_drift_ensemble.get_rollback_signal(0.9, 0.10, 0.21) == True
        
        # No drift -> should NOT rollback
        assert mock_drift_ensemble.get_rollback_signal(1.4, 0.14, 0.21) == False
