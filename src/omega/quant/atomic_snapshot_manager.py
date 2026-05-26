"""omega.quant.atomic_snapshot_manager - compatibility shim"""
from __future__ import annotations
from typing import Any, Dict, List

class AtomicSnapshotManager:
    def __init__(self, snapshot_dir: str = 'state/atomic_snapshots/'):
        self.snapshot_dir = snapshot_dir
        self._snapshots: Dict[str, Any] = {}

    def create_atomic_snapshot(self, snapshot_id: str, **kwargs) -> str:
        self._snapshots[snapshot_id] = kwargs
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        return self._snapshots.get(snapshot_id, {})

    def list_atomic_snapshots(self) -> List[str]:
        return list(self._snapshots.keys())

    def delete_snapshot(self, snapshot_id: str) -> bool:
        return bool(self._snapshots.pop(snapshot_id, None))
