# src/omega/data/pipeline_orchestrator.py
"""Master data pipeline orchestrator and release state machine for OMEGA_QUANT."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile

from filelock import FileLock


class ReleaseState(str, Enum):
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"


_ALLOWED = {
    ReleaseState.BUILDING: {ReleaseState.VALIDATING, ReleaseState.CANDIDATE, ReleaseState.QUARANTINED},
    ReleaseState.VALIDATING: {ReleaseState.CANDIDATE, ReleaseState.QUARANTINED},
    ReleaseState.CANDIDATE: {ReleaseState.ACTIVE, ReleaseState.QUARANTINED},
    ReleaseState.ACTIVE: set(),
    ReleaseState.QUARANTINED: set(),
}


class PipelineOrchestrator:
    def __init__(self, release_root: str | Path):
        self.root = Path(release_root)
        self.manifest = self.root / "release_manifest.json"
        self.pointer = self.root / "active_release.json"
        self.lock = FileLock(str(self.root / ".activation.lock"))

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", dir=path.parent, delete=False) as tmp:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.flush()
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _parse_timestamp(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone-aware timestamp required")
        return parsed.astimezone(timezone.utc)

    def _validate_manifest(self, payload: dict) -> None:
        required = {"release_id", "files", "created_at", "cutoff_at"}
        if not required.issubset(payload):
            raise ValueError("incomplete manifest")
        cutoff = self._parse_timestamp(payload["cutoff_at"])
        for item in payload["files"]:
            file_path = self.root / item["path"]
            if not file_path.exists():
                raise ValueError("artifact missing")
            if item.get("sha256") and self._sha256(file_path) != item["sha256"]:
                raise ValueError("artifact validation failed")
        for item in payload.get("artifacts", []):
            available = self._parse_timestamp(item["available_at"])
            if available > cutoff:
                raise ValueError("PIT availability exceeds cutoff")

    def build_manifest(self, release_id: str, files: list[str], cutoff_at: str | None = None) -> dict:
        manifest_files = []
        for f in files:
            artifact = self.root / f
            digest = self._sha256(artifact) if artifact.exists() else None
            manifest_files.append({"path": f, "sha256": digest})
        manifest = {
            "release_id": release_id,
            "state": ReleaseState.BUILDING.value,
            "files": manifest_files,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_at": cutoff_at or datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.manifest, manifest)
        return manifest

    def transition(self, state: ReleaseState) -> dict:
        payload = json.loads(self.manifest.read_text())
        current = ReleaseState(payload["state"])
        if state not in _ALLOWED[current]:
            raise ValueError(f"invalid transition {current}->{state}")
        payload["state"] = state.value
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self.manifest, payload)
        return payload

    def activate(self) -> dict:
        with self.lock:
            pointer_backup = self.pointer.read_bytes() if self.pointer.exists() else None
            manifest_backup = self.manifest.read_text()
            try:
                payload = json.loads(manifest_backup)
                self._validate_manifest(payload)
                if ReleaseState(payload["state"]) != ReleaseState.CANDIDATE:
                    self.transition(ReleaseState.CANDIDATE)
                active = {"state": ReleaseState.ACTIVE.value, "manifest": str(self.manifest)}
                self._write_json(self.pointer, active)
                self.transition(ReleaseState.ACTIVE)
                return active
            except Exception:
                if pointer_backup is None:
                    self.pointer.unlink(missing_ok=True)
                else:
                    self._write_json(self.pointer, json.loads(pointer_backup))
                self._write_json(self.manifest, json.loads(manifest_backup))
                raise

    def quarantine(self, reason: str) -> dict:
        payload = json.loads(self.manifest.read_text())
        payload["state"] = ReleaseState.QUARANTINED.value
        payload["reason"] = reason
        self._write_json(self.manifest, payload)
        return payload
