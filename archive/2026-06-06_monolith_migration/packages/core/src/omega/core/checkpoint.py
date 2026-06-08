"""
Checkpoint/Restore Mechanism - OMEGA_QUANT Quant AI System
Version: 1.0.0
Status: Implementation-Ready

Implements atomic checkpoint save/load with:
- CheckpointManager class for managing checkpoints
- Atomic write pattern (write-temp-then-rename)
- SHA256 checksum validation
- PIT Safety (Point-In-Time) support
- Recovery from failure scenarios
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib
import os
import shutil


class CheckpointError(Exception):
    """Raised when a checkpoint operation fails."""
    pass


class CheckpointManager:
    """
    CheckpointManager class - manages checkpoint save/load/restore.
    
    Features:
    - Atomic writes (temp file → rename)
    - SHA256 checksum validation
    - PIT Safety (as_of_time support)
    - Recovery from failures
    """
    
    def __init__(self, state_dir: Path):
        """Initialize checkpoint manager.
        
        Args:
            state_dir: Base state directory
        """
        self.state_dir = Path(state_dir)
        self.session_dir = self.state_dir / "session"
        self.session_dir.mkdir(parents=True, exist_ok=True)
    
    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """Compute SHA256 checksum of data.
        
        Args:
            data: Data to checksum
        
        Returns:
            Hex string of SHA256 hash
        """
        # Sort keys for consistent hashing
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def _verify_checksum(self, data: Dict[str, Any], expected_checksum: str) -> bool:
        """Verify data checksum.
        
        Args:
            data: Data to verify
            expected_checksum: Expected checksum
        
        Returns:
            True if checksum matches, False otherwise
        """
        actual_checksum = self._compute_checksum(data)
        return actual_checksum == expected_checksum
    
    def validate_pit_safety(self, checkpoint_data: Dict[str, Any], current_time: Optional[datetime] = None) -> bool:
        """Validate PIT safety - ensure as_of_time is not in the future.
        
        Args:
            checkpoint_data: Checkpoint data to validate
            current_time: Current time (defaults to now)
        
        Returns:
            True if PIT safety is valid, False otherwise
        
        Raises:
            CheckpointError: If as_of_time is in the future (look-ahead violation)
        """
        as_of_time_str = checkpoint_data.get("as_of_time")
        
        # If no as_of_time specified, consider it valid
        if not as_of_time_str:
            return True
        
        # Parse as_of_time
        try:
            as_of_time = datetime.fromisoformat(as_of_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise CheckpointError(f"Invalid as_of_time format: {as_of_time_str}")
        
        # Get current time
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        # Ensure as_of_time is not in the future
        if as_of_time > current_time:
            raise CheckpointError(
                f"PIT Safety violation: as_of_time ({as_of_time_str}) is in the future. "
                f"Current time: {current_time.isoformat()}"
            )
        
        return True
    
    def save_checkpoint(
        self,
        task_id: str,
        state: Dict[str, Any],
        as_of_time: Optional[str] = None
    ) -> Path:
        """Save checkpoint atomically.
        
        Args:
            task_id: Task identifier
            state: State to checkpoint
            as_of_time: Point-In-Time timestamp (optional)
        
        Returns:
            Path to saved checkpoint file
        
        Raises:
            CheckpointError: If save fails
        """
        try:
            checkpoint_file = self.session_dir / f"checkpoint_{task_id}.json"
            temp_file = self.session_dir / f"checkpoint_{task_id}.tmp"
            
            # Build checkpoint data
            checkpoint_data = {
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "as_of_time": as_of_time,
                "state": state,
            }
            
            # Compute checksum
            checksum = self._compute_checksum(state)
            checkpoint_data["checksum"] = checksum
            
            # Atomic write: write to temp file first
            with open(temp_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Force to disk before rename
            
            # Verify temp file was written
            if not temp_file.exists():
                raise CheckpointError("Failed to write temp file")
            
            # Atomic rename (use replace for Windows compatibility)
            os.replace(temp_file, checkpoint_file)
            
            # Verify final file
            if not checkpoint_file.exists():
                raise CheckpointError("Checkpoint file not found after rename")
            
            # Clean up any leftover temp files
            for temp in self.session_dir.glob("checkpoint_*.tmp"):
                try:
                    temp.unlink()
                except Exception:
                    pass
            
            return checkpoint_file
        except Exception as e:
            # Clean up temp file on error
            temp_file = self.session_dir / f"checkpoint_{task_id}.tmp"
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            
            raise CheckpointError(f"Failed to save checkpoint: {e}")
    
    def load_checkpoint(self, task_id: str) -> Dict[str, Any]:
        """Load checkpoint and verify integrity.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Checkpoint data dictionary
        
        Raises:
            CheckpointError: If load or verification fails
        """
        try:
            checkpoint_file = self.session_dir / f"checkpoint_{task_id}.json"
            
            if not checkpoint_file.exists():
                raise CheckpointError(f"Checkpoint not found: {task_id}")
            
            with open(checkpoint_file, "r") as f:
                data = json.load(f)
            
            # Verify checksum
            state = data.get("state", {})
            expected_checksum = data.get("checksum")
            
            if not self._verify_checksum(state, expected_checksum):
                raise CheckpointError("Checksum mismatch - checkpoint may be corrupted")
            
            # Validate PIT safety on load
            self.validate_pit_safety(data)
            
            return data
        except CheckpointError:
            raise
        except json.JSONDecodeError as e:
            raise CheckpointError(f"Invalid checkpoint format: {e}")
        except Exception as e:
            raise CheckpointError(f"Failed to load checkpoint: {e}")
    
    def restore_from_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Restore state from checkpoint.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Restored state dictionary, or None if checkpoint not found
        """
        try:
            data = self.load_checkpoint(task_id)
            return data.get("state")
        except CheckpointError as e:
            # Log error but return None
            print(f"Restore failed: {e}")
            return None
    
    def list_checkpoints(self) -> Dict[str, datetime]:
        """List all active checkpoints.
        
        Returns:
            Dictionary mapping task_id to checkpoint timestamp
        """
        checkpoints = {}
        
        for checkpoint_file in self.session_dir.glob("checkpoint_*.json"):
            try:
                data = self.load_checkpoint(checkpoint_file.stem.replace("checkpoint_", ""))
                timestamp = data.get("timestamp")
                task_id = data.get("task_id")
                
                if timestamp and task_id:
                    checkpoints[task_id] = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except CheckpointError:
                # Skip corrupted checkpoints
                continue
        
        return checkpoints
    
    def delete_checkpoint(self, task_id: str) -> bool:
        """Delete a checkpoint.
        
        Args:
            task_id: Task identifier
        
        Returns:
            True if deleted, False if not found
        """
        try:
            checkpoint_file = self.session_dir / f"checkpoint_{task_id}.json"
            
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                return True
            
            return False
        except Exception as e:
            raise CheckpointError(f"Failed to delete checkpoint: {e}")
    
    def cleanup_old_checkpoints(self, max_age_hours: int = 24) -> int:
        """Delete checkpoints older than specified age.
        
        Args:
            max_age_hours: Maximum age in hours
        
        Returns:
            Number of checkpoints deleted
        """
        deleted = 0
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        
        for checkpoint_file in self.session_dir.glob("checkpoint_*.json"):
            try:
                # Get file modification time
                mtime = checkpoint_file.stat().st_mtime
                
                if mtime < cutoff:
                    checkpoint_file.unlink()
                    deleted += 1
            except Exception:
                continue
        
        return deleted
