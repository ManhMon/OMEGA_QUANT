"""omega.quant.atomic_snapshot_manager - shim wrapper for evolution"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from omega.quant.evolution.atomic_snapshot_manager import (
    AtomicSnapshotManager as RealManager
)


class AtomicSnapshotManager:
    """Wrapper delegating to the real AtomicSnapshotManager from evolution."""
    def __init__(self, snapshot_dir: str = 'state/atomic_snapshots/'):
        # Map string path to Path object
        self.snapshot_dir = snapshot_dir
        self._real = RealManager(archive_dir=Path(snapshot_dir))

    def create_atomic_snapshot(self, snapshot_id: str, **kwargs) -> str:
        model = kwargs.get('model', None)
        model_name = kwargs.get('model_name', 'champion')
        bandit_state = kwargs.get('bandit_state', {})
        metrics = kwargs.get('metrics', {})
        pit_verified = kwargs.get('pit_verified', True)

        self._real.create_atomic_snapshot(
            snapshot_id=snapshot_id,
            model=model,
            model_name=model_name,
            bandit_state=bandit_state,
            metrics=metrics,
            pit_verified=pit_verified
        )
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        return self.atomic_rollback(snapshot_id)

    def atomic_rollback(self, snapshot_id: str) -> Dict[str, Any]:
        model, bandit_state, metadata = (
            self._real.verify_and_restore(snapshot_id)
        )
        return {
            'model': model,
            'bandit_state': bandit_state,
            'metadata': metadata
        }

    def list_atomic_snapshots(self) -> List[str]:
        if not self._real.archive_dir.exists():
            return []
        snapshots = []
        for f in self._real.archive_dir.iterdir():
            if f.name.endswith(".tar.gz"):
                snapshots.append(f.name[:-7])
        return snapshots

    def delete_snapshot(self, snapshot_id: str) -> bool:
        tar_file = self._real.archive_dir / f"{snapshot_id}.tar.gz"
        sha_file = self._real.archive_dir / f"{snapshot_id}.sha256"
        deleted = False
        try:
            if tar_file.exists():
                tar_file.unlink()
                deleted = True
            if sha_file.exists():
                sha_file.unlink()
                deleted = True
            return deleted
        except Exception:
            return False
