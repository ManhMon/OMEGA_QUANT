"""Unit tests for evolution modules (P2 coverage gap fix)."""
import sys
import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "quant" / "src"))

# === Test Continuous Learning ===
class TestContinuousLearning:
    def test_should_retrain_first_time(self):
        from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
        engine = ContinuousLearningEngine(ContinuousLearningConfig(retraining_interval_days=7))
        assert engine.should_retrain(pd.Timestamp("2026-01-01")) == True

    def test_should_not_retrain_within_interval(self):
        from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
        engine = ContinuousLearningEngine(ContinuousLearningConfig(retraining_interval_days=7))
        engine.last_retrain_date = pd.Timestamp("2026-01-01")
        assert engine.should_retrain(pd.Timestamp("2026-01-05")) == False

    def test_should_retrain_after_interval(self):
        from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
        engine = ContinuousLearningEngine(ContinuousLearningConfig(retraining_interval_days=7))
        engine.last_retrain_date = pd.Timestamp("2026-01-01")
        assert engine.should_retrain(pd.Timestamp("2026-01-09")) == True

    def test_evaluate_model(self):
        from omega.quant.evolution.continuous_learning import ContinuousLearningEngine
        engine = ContinuousLearningEngine()
        preds = pd.Series(np.random.randn(100))
        actuals = pd.Series(preds * 0.8 + np.random.randn(100) * 0.2)
        metrics = engine.evaluate_model(preds, actuals)
        assert "ic" in metrics or "sharpe" in metrics

# === Test Drift Detector ===
class TestDriftDetector:
    def test_no_drift_stable_metrics(self):
        from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig
        detector = DriftDetectorEnsemble(DriftDetectorConfig())
        for i in range(10):
            detector.record_metrics(pd.Timestamp(f"2026-01-{i+1:02d}"), 1.5, 0.15, 0.12)
        result = detector.check_drift(1.4, 0.14, 0.13)
        assert result["drift_detected"] == False

    def test_drift_on_sharpe_drop(self):
        from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig
        detector = DriftDetectorEnsemble(DriftDetectorConfig(sharpe_drop_threshold=0.30))
        for i in range(10):
            detector.record_metrics(pd.Timestamp(f"2026-01-{i+1:02d}"), 2.0, 0.20, 0.10)
        result = detector.check_drift(0.5, 0.05, 0.40)
        assert result["drift_detected"] == True

    def test_record_metrics_cleanup(self):
        from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig
        detector = DriftDetectorEnsemble(DriftDetectorConfig(lookback_window_days=5))
        for i in range(20):
            detector.record_metrics(pd.Timestamp(f"2026-01-{i+1:02d}"), 1.5, 0.15, 0.12)
        assert len(detector.history) <= 10

# === Test Alpha Bridge ===
class TestAlphaBridge:
    def test_register_alpha(self):
        from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge
        bridge = AlphaToExecutionBridge()
        ok = bridge.register_alpha("a1", "(f0+f1)", horizon=5,
            train_end_date=pd.Timestamp("2026-01-01"), ic=0.12, sharpe=1.5)
        assert ok == True
        assert "a1" in bridge.active_alphas

    def test_embargo_t3(self):
        from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge, AlphaBridgeConfig
        bridge = AlphaToExecutionBridge(AlphaBridgeConfig(t3_embargo_days=4))
        bridge.register_alpha("a2", "rank(f0)", horizon=3,
            train_end_date=pd.Timestamp("2026-01-10"), ic=0.10, sharpe=1.0)
        # Day 3 after train_end: still in embargo
        assert bridge.validate_embargo("a2", pd.Timestamp("2026-01-13")) == False
        # Day 5 after train_end: past embargo
        assert bridge.validate_embargo("a2", pd.Timestamp("2026-01-15")) == True

    def test_weight_bounds(self):
        from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge, AlphaBridgeConfig
        config = AlphaBridgeConfig(min_alpha_weight=0.05, max_alpha_weight=0.35)
        bridge = AlphaToExecutionBridge(config)
        assert config.min_alpha_weight == 0.05
        assert config.max_alpha_weight == 0.35

# === Test Rollback Handler ===
class TestRollbackHandler:
    def test_import_and_init(self):
        from omega.quant.evolution.rollback_handler import RollbackHandler
        handler = RollbackHandler()
        assert handler is not None

# === Test Atomic Snapshot Manager ===
class TestAtomicSnapshot:
    def test_import_and_init(self):
        from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager
        import tempfile
        mgr = AtomicSnapshotManager(archive_dir=Path(tempfile.mkdtemp()))
        assert mgr is not None

    def test_sha256_calculation(self):
        from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager
        import tempfile
        mgr = AtomicSnapshotManager(archive_dir=Path(tempfile.mkdtemp()))
        # Create temp file
        tmp = Path(tempfile.mktemp(suffix=".txt"))
        tmp.write_text("test content")
        checksum = mgr.calculate_sha256(tmp)
        assert len(checksum) == 64
        tmp.unlink()

# === Test SRE Alerting Engine ===
class TestSREAlerting:
    def test_import_and_init(self):
        from omega.quant.evolution.sre_alerting_engine import SREAlertingEngine
        engine = SREAlertingEngine()
        assert engine is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
