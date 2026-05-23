"""
Test suite for Checkpoint/Restore Mechanism

Tests cover:
- Checkpoint save/load/restore
- Atomic write pattern (write-temp-then-replace)
- Checksum validation (SHA256)
- State persistence and recovery
- Recovery from failure scenarios
- PIT Safety (Point-In-Time)

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 2 (State Persistence)
"""

import os
import pytest
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from omega.core.checkpoint import CheckpointManager, CheckpointError


class TestCheckpointManager:
    """Test CheckpointManager class."""
    
    def test_checkpoint_save_basic(self, workspace_tmp):
        """Test basic checkpoint save."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        
        task_id = "task-001"
        state = {
            "status": "RUNNING",
            "progress": 50,
            "data": {"last_index": 100}
        }
        
        checkpoint_path = manager.save_checkpoint(task_id, state)
        
        assert checkpoint_path.exists()
        assert checkpoint_path.name == f"checkpoint_{task_id}.json"
        
        # Verify content
        saved_data = json.loads(checkpoint_path.read_text())
        assert saved_data["task_id"] == task_id
        assert saved_data["state"] == state
        assert "timestamp" in saved_data
        assert "checksum" in saved_data
    
    def test_checkpoint_atomic_write(self, workspace_tmp):
        """Test that checkpoint write is atomic."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        # Save first checkpoint
        manager.save_checkpoint(task_id, {"step": 1})
        
        # Save second checkpoint - should overwrite atomically
        checkpoint_path = manager.save_checkpoint(task_id, {"step": 2})
        
        # Verify second checkpoint is correct
        saved_data = json.loads(checkpoint_path.read_text())
        assert saved_data["state"]["step"] == 2
        
        # Verify no temp files left behind
        temp_files = list(checkpoint_path.parent.glob("*.tmp"))
        assert len(temp_files) == 0
    
    def test_checkpoint_checksum_validation(self, workspace_tmp):
        """Test checksum validation during load."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        state = {"step": 1}
        
        checkpoint_path = manager.save_checkpoint(task_id, state)
        
        # Load and verify checksum
        loaded_data = manager.load_checkpoint(task_id)
        assert loaded_data["state"] == state
        
        # Corrupt file content manually
        data = json.loads(checkpoint_path.read_text())
        data["state"]["step"] = 999  # Change data without updating checksum
        checkpoint_path.write_text(json.dumps(data))
        
        # Load should now raise CheckpointError due to checksum mismatch
        with pytest.raises(CheckpointError, match="Checksum mismatch"):
            manager.load_checkpoint(task_id)
    
    def test_checkpoint_restore(self, workspace_tmp):
        """Test restoring state from checkpoint."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        state = {"step": 5, "records_processed": 500}
        
        manager.save_checkpoint(task_id, state)
        
        # Restore state
        restored_state = manager.restore_from_checkpoint(task_id)
        
        assert restored_state == state
    
    def test_checkpoint_list_checkpoints(self, workspace_tmp):
        """Test listing all active checkpoints."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        
        manager.save_checkpoint("task-001", {"step": 1})
        manager.save_checkpoint("task-002", {"step": 2})
        
        checkpoints = manager.list_checkpoints()
        
        assert len(checkpoints) == 2
        assert "task-001" in checkpoints
        assert "task-002" in checkpoints
    
    def test_checkpoint_delete(self, workspace_tmp):
        """Test deleting a checkpoint."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        checkpoint_path = manager.save_checkpoint(task_id, {"step": 1})
        assert checkpoint_path.exists()
        
        manager.delete_checkpoint(task_id)
        assert not checkpoint_path.exists()
    
    def test_checkpoint_pit_safety(self, workspace_tmp):
        """Test PIT safety (using as_of_time in checkpoints)."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        # Point-In-Time timestamp (T-1)
        as_of_time = "2026-05-12T00:00:00Z"
        state = {"data": "historical_data"}
        
        checkpoint_path = manager.save_checkpoint(task_id, state, as_of_time=as_of_time)
        
        saved_data = json.loads(checkpoint_path.read_text())
        assert saved_data["as_of_time"] == as_of_time
        assert saved_data["timestamp"] != as_of_time  # Real timestamp is different

    def test_checkpoint_rejects_future_data(self, workspace_tmp):
        """Test that checkpoint load rejects future as_of_time."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-future"
        
        # Point-In-Time timestamp in the future (Look-ahead)
        future_time = "2029-01-01T00:00:00Z"
        state = {"data": "future_data"}
        
        # Save should work (storage), but load should fail PIT validation
        checkpoint_path = manager.save_checkpoint(task_id, state, as_of_time=future_time)
        
        with pytest.raises(CheckpointError, match="PIT Safety violation"):
            manager.load_checkpoint(task_id)


class TestRecoveryScenarios:
    """Test recovery from various failure scenarios."""
    
    def test_recovery_from_interrupted_execution(self, workspace_tmp):
        """Scenario: Task interrupted mid-execution, resume from checkpoint."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        # Simulate work in progress (50% done)
        in_progress_state = {"step": 50, "total_steps": 100, "partial_results": [1, 2, 3]}
        manager.save_checkpoint(task_id, in_progress_state)
        
        # Simulate worker restart and recovery
        new_manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        recovered_state = new_manager.restore_from_checkpoint(task_id)
        
        assert recovered_state == in_progress_state
        assert recovered_state["step"] == 50
    
    def test_recovery_from_missing_checkpoint(self, workspace_tmp):
        """Scenario: Restore attempted for non-existent checkpoint."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        
        # Should return None or raise error depending on implementation
        result = manager.restore_from_checkpoint("non-existent")
        assert result is None
    
    def test_recovery_from_corrupt_file(self, workspace_tmp):
        """Scenario: Checkpoint file is truncated or invalid JSON."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        checkpoint_path = manager.save_checkpoint(task_id, {"step": 1})
        
        # Corrupt file (not JSON)
        checkpoint_path.write_text("NOT_JSON")
        
        with pytest.raises(CheckpointError, match="Invalid checkpoint format"):
            manager.load_checkpoint(task_id)
    
    def test_recovery_with_checksum_mismatch(self, workspace_tmp):
        """Scenario: Checkpoint file data tampered with."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        manager.save_checkpoint(task_id, {"data": "secret"})
        
        # Manually change data in file
        checkpoint_file = workspace_tmp / ".ly_state" / "session" / f"checkpoint_{task_id}.json"
        data = json.loads(checkpoint_file.read_text())
        data["state"]["data"] = "tampered"
        checkpoint_file.write_text(json.dumps(data))
        
        # Should fail checksum validation (load_checkpoint raises, restore_from_checkpoint returns None)
        with pytest.raises(CheckpointError, match="Checksum mismatch"):
            manager.load_checkpoint(task_id)


class TestAtomicWriteVerification:
    """Verification of the atomic write pattern."""
    
    def test_atomic_write_sequence(self, workspace_tmp, monkeypatch):
        """Verify the temp file → replace sequence."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-001"
        
        replaced = False
        original_replace = os.replace
        
        def mock_replace(src, dst):
            nonlocal replaced
            replaced = True
            # Verify temp file exists before replace
            assert ".tmp" in str(src)
            assert Path(src).exists()
            original_replace(src, dst)
            
        monkeypatch.setattr(os, "replace", mock_replace)
        
        manager.save_checkpoint(task_id, {"step": 1})
        assert replaced is True

    def test_checkpoint_durability_barrier(self, workspace_tmp, monkeypatch):
        """Test that checkpoint write includes fsync durability barrier."""
        manager = CheckpointManager(state_dir=workspace_tmp / ".ly_state")
        task_id = "task-durability"
        
        fsync_called = False
        original_fsync = os.fsync
        
        def mock_fsync(fd):
            nonlocal fsync_called
            fsync_called = True
            original_fsync(fd)
            
        monkeypatch.setattr(os, "fsync", mock_fsync)
        
        manager.save_checkpoint(task_id, {"data": "test"})
        assert fsync_called is True
