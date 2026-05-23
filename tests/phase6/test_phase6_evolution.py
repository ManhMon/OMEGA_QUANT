"""
Gap Phase 6.2 & 6.3 Unit Tests - Atomic Snapshot Manager & Alpha to Execution Bridge
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
import tempfile
import shutil

from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager
from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge, AlphaBridgeConfig
from omega.quant.evolution.rollback_handler import RollbackHandler
from omega.quant.evolution.sre_alerting_engine import SREAlertingEngine, SREAlertingConfig


@pytest.fixture
def temp_archive_dir():
    """Create temporary archive directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


class MockModelForPickle:
    def __init__(self):
        self.weights = np.random.randn(10)


@pytest.fixture
def sample_model():
    """Create a simple mock model for testing."""
    return MockModelForPickle()


class TestAtomicSnapshotManager:
    """Test Suite for Atomic Snapshot Manager."""
    
    def test_snapshot_creation_and_checksum(self, temp_archive_dir, sample_model):
        """Test atomic snapshot creation with SHA256 checksum."""
        manager = AtomicSnapshotManager(archive_dir=temp_archive_dir)
        
        snapshot_id = "test_snap_001"
        bandit_state = {"alpha_success": 10, "alpha_failure": 5}
        metrics = {"ic": 0.15, "sharpe": 2.5, "turnover": 0.25}
        
        archive_path = manager.create_atomic_snapshot(
            snapshot_id=snapshot_id,
            model=sample_model,
            model_name="test_model",
            bandit_state=bandit_state,
            metrics=metrics,
            pit_verified=True
        )
        
        assert archive_path.exists()
        assert archive_path.suffix == ".gz"
        
        # Verify checksum file exists
        checksum_path = temp_archive_dir / f"{snapshot_id}.sha256"
        assert checksum_path.exists()
        
        with open(checksum_path, 'r') as f:
            checksum = f.read().strip()
        assert len(checksum) == 64  # SHA256 hex length
    
    def test_atomic_restore_with_verification(self, temp_archive_dir, sample_model):
        """Test atomic restore with SHA256 verification."""
        manager = AtomicSnapshotManager(archive_dir=temp_archive_dir)
        
        snapshot_id = "test_snap_002"
        bandit_state = {"alpha_success": 20, "alpha_failure": 8}
        metrics = {"ic": 0.18, "sharpe": 2.8, "turnover": 0.22}
        
        # Create snapshot
        manager.create_atomic_snapshot(
            snapshot_id=snapshot_id,
            model=sample_model,
            model_name="test_model_v2",
            bandit_state=bandit_state,
            metrics=metrics,
            pit_verified=True
        )
        
        # Restore snapshot
        restored_model, restored_bandit, restored_meta = manager.verify_and_restore(snapshot_id)
        
        assert restored_bandit == bandit_state
        assert restored_meta["metrics"] == metrics
        assert restored_meta["pit_verified"] == True
    
    def test_checksum_mismatch_detection(self, temp_archive_dir, sample_model):
        """Test that checksum mismatch is detected."""
        manager = AtomicSnapshotManager(archive_dir=temp_archive_dir)
        
        snapshot_id = "test_snap_003"
        manager.create_atomic_snapshot(
            snapshot_id=snapshot_id,
            model=sample_model,
            model_name="test_model",
            bandit_state={"alpha_success": 15},
            metrics={"ic": 0.12}
        )
        
        # Corrupt checksum
        checksum_path = temp_archive_dir / f"{snapshot_id}.sha256"
        with open(checksum_path, 'w') as f:
            f.write("0" * 64)  # Invalid checksum
        
        # Attempt restore should fail
        with pytest.raises(ValueError, match="SHA256 checksum mismatch"):
            manager.verify_and_restore(snapshot_id)


class TestRollbackHandler:
    """Test suite for continuous learning rollback orchestration."""

    def test_executes_rollback_when_drift_detected(self, temp_archive_dir, sample_model):
        manager = AtomicSnapshotManager(archive_dir=temp_archive_dir)
        handler = RollbackHandler()
        sre_engine = SREAlertingEngine(
            SREAlertingConfig(sharpe_threshold=1.0, ic_threshold=0.10, lookback_days=3)
        )

        manager.create_atomic_snapshot(
            snapshot_id="stable_snap",
            model=sample_model,
            model_name="stable_model",
            bandit_state={"alpha_success": 30, "alpha_failure": 4},
            metrics={"sharpe": 1.35, "ic": 0.18, "turnover": 0.20},
            pit_verified=True,
        )

        for day in range(4):
            timestamp = pd.Timestamp("2026-05-01") + pd.Timedelta(days=day)
            sre_engine.register_metric("sharpe", 1.25 + 0.01 * day, timestamp)
            sre_engine.register_metric("ic", 0.16 + 0.002 * day, timestamp)

        drift_timestamp = pd.Timestamp("2026-05-05")
        sre_engine.register_metric("sharpe", 0.72, drift_timestamp)
        sre_engine.register_metric("ic", 0.07, drift_timestamp)

        rolled_back, reason = handler.check_and_execute_rollback(
            sre_engine=sre_engine,
            snapshot_manager=manager,
            current_snapshot_id="current_snap",
            rollback_snapshot_id="stable_snap",
        )

        assert rolled_back is True
        assert "Rollback executed from current_snap to stable_snap" in reason
        assert manager.last_restored_state["snapshot_id"] == "stable_snap"
        assert handler.last_restored_state["metadata"]["metrics"]["sharpe"] == 1.35

    def test_skips_rollback_without_drift(self, temp_archive_dir, sample_model):
        manager = AtomicSnapshotManager(archive_dir=temp_archive_dir)
        handler = RollbackHandler()
        sre_engine = SREAlertingEngine(
            SREAlertingConfig(sharpe_threshold=1.0, ic_threshold=0.10, lookback_days=3)
        )

        manager.create_atomic_snapshot(
            snapshot_id="stable_snap",
            model=sample_model,
            model_name="stable_model",
            bandit_state={"alpha_success": 30, "alpha_failure": 4},
            metrics={"sharpe": 1.35, "ic": 0.18, "turnover": 0.20},
            pit_verified=True,
        )

        for day in range(5):
            timestamp = pd.Timestamp("2026-05-01") + pd.Timedelta(days=day)
            sre_engine.register_metric("sharpe", 1.20 + 0.01 * day, timestamp)
            sre_engine.register_metric("ic", 0.15 + 0.002 * day, timestamp)

        rolled_back, reason = handler.check_and_execute_rollback(
            sre_engine=sre_engine,
            snapshot_manager=manager,
            current_snapshot_id="current_snap",
            rollback_snapshot_id="stable_snap",
        )

        assert rolled_back is False
        assert reason == "No rollback executed: no drift detected"
        assert handler.last_restored_state is None


class TestAlphaToExecutionBridge:
    """Test Suite for Alpha to Execution Bridge."""
    
    def test_alpha_registration(self):
        """Test alpha signal registration."""
        bridge = AlphaToExecutionBridge()
        
        train_end = pd.Timestamp('2026-05-01')
        result = bridge.register_alpha(
            alpha_id="alpha_001",
            formula="rank(close) - rank(volume)",
            horizon=3,
            train_end_date=train_end,
            ic=0.15,
            sharpe=2.5
        )
        
        assert result == True
        assert "alpha_001" in bridge.active_alphas
        assert bridge.active_alphas["alpha_001"]["horizon"] == 3
    
    def test_embargo_enforcement_t3(self):
        """Test T+3 embargo enforcement (4-day embargo)."""
        bridge = AlphaToExecutionBridge(AlphaBridgeConfig(t3_embargo_days=4))
        
        train_end = pd.Timestamp('2026-05-01')
        bridge.register_alpha(
            alpha_id="alpha_t3",
            formula="test_formula",
            horizon=3,
            train_end_date=train_end,
            ic=0.15,
            sharpe=2.5
        )
        
        # Day 3 (train_end + 3): Should be blocked
        current_date_blocked = train_end + timedelta(days=3)
        assert bridge.validate_embargo("alpha_t3", current_date_blocked) == False
        
        # Day 4 (train_end + 4): Should be allowed
        current_date_allowed = train_end + timedelta(days=4)
        assert bridge.validate_embargo("alpha_t3", current_date_allowed) == True
    
    def test_embargo_enforcement_t5(self):
        """Test T+5 embargo enforcement (6-day embargo)."""
        bridge = AlphaToExecutionBridge(AlphaBridgeConfig(t5_embargo_days=6))
        
        train_end = pd.Timestamp('2026-05-01')
        bridge.register_alpha(
            alpha_id="alpha_t5",
            formula="test_formula",
            horizon=5,
            train_end_date=train_end,
            ic=0.18,
            sharpe=2.8
        )
        
        # Day 5 (train_end + 5): Should be blocked
        current_date_blocked = train_end + timedelta(days=5)
        assert bridge.validate_embargo("alpha_t5", current_date_blocked) == False
        
        # Day 6 (train_end + 6): Should be allowed
        current_date_allowed = train_end + timedelta(days=6)
        assert bridge.validate_embargo("alpha_t5", current_date_allowed) == True
    
    def test_signal_to_weight_conversion(self):
        """Test conversion of alpha signals to portfolio weights."""
        bridge = AlphaToExecutionBridge()
        
        train_end = pd.Timestamp('2026-05-01')
        bridge.register_alpha(
            alpha_id="alpha_001",
            formula="test",
            horizon=3,
            train_end_date=train_end,
            ic=0.15,
            sharpe=2.5
        )
        
        # Create sample signals (embargo-safe date)
        current_date = train_end + timedelta(days=5)
        signals = {
            "alpha_001": pd.Series({
                "FPT": 0.8,
                "HPG": 0.6,
                "SSI": 0.4,
                "VNM": 0.2
            })
        }
        
        weights = bridge.convert_signals_to_weights(signals, current_date)
        
        # Top 30% stocks should get weights
        assert len(weights) > 0
        for ticker, weight in weights.items():
            assert 0.05 <= weight <= 0.35  # Within config bounds
