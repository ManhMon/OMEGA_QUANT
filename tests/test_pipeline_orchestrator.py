# tests/test_pipeline_orchestrator.py
"""Tests for master data pipeline orchestrator and release state machine."""

from __future__ import annotations

import json

import pytest

from omega.data.pipeline_orchestrator import PipelineOrchestrator, ReleaseState


def test_manifest_and_state_machine(tmp_path):
    artifact = tmp_path / "market.parquet"
    artifact.write_bytes(b"data")
    orch = PipelineOrchestrator(tmp_path)

    manifest = orch.build_manifest("r1", ["market.parquet"])
    assert manifest["state"] == ReleaseState.BUILDING.value

    result = orch.activate()
    assert result["state"] == ReleaseState.ACTIVE.value


def test_invalid_transition_rejected(tmp_path):
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", [])

    with pytest.raises(ValueError):
        orch.transition(ReleaseState.ACTIVE)


def test_corrupt_manifest_rejected(tmp_path):
    artifact = tmp_path / "market.parquet"
    artifact.write_bytes(b"data")
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", ["market.parquet"])

    manifest = json.loads(orch.manifest.read_text())
    manifest["files"][0]["sha256"] = "bad"
    orch.manifest.write_text(json.dumps(manifest))

    with pytest.raises(ValueError):
        orch.activate()


def test_pointer_rollback_on_activation_failure(tmp_path):
    artifact = tmp_path / "market.parquet"
    artifact.write_bytes(b"data")
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", ["market.parquet"])
    orch.pointer.write_text(json.dumps({"state": "ACTIVE", "old": True}))

    artifact.unlink()
    with pytest.raises(ValueError):
        orch.activate()

    assert json.loads(orch.pointer.read_text())["old"] is True


def test_pit_lookahead_rejected(tmp_path):
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", [])
    manifest = json.loads(orch.manifest.read_text())
    manifest["artifacts"] = [{
        "available_at": "2026-09-13T00:00:00+00:00"
    }]
    orch.manifest.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="PIT availability exceeds cutoff"):
        orch.activate()


def test_timezone_ambiguous_timestamp_rejected(tmp_path):
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", [])
    manifest = json.loads(orch.manifest.read_text())
    manifest["cutoff_at"] = "2026-09-12T00:00:00"
    orch.manifest.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="timezone-aware timestamp required"):
        orch.activate()


def test_atomic_pointer_restore(tmp_path):
    orch = PipelineOrchestrator(tmp_path)
    orch.pointer.write_text(json.dumps({"old": "release"}))
    backup = orch.pointer.read_text()
    tmp = tmp_path / "partial"
    tmp.write_text("broken")
    tmp.replace(orch.pointer)

    assert orch.pointer.read_text() == "broken"
    orch.pointer.write_text(backup)
    assert json.loads(orch.pointer.read_text())["old"] == "release"


def test_activate_fault_injection_restores_pointer_and_manifest(tmp_path, monkeypatch):
    artifact = tmp_path / "market.parquet"
    artifact.write_bytes(b"data")
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", ["market.parquet"])
    orch.pointer.write_text(json.dumps({"state": "ACTIVE", "old": True}))
    manifest_before = orch.manifest.read_text()

    def fail_pointer_write(*args, **kwargs):
        raise OSError("injected pointer failure")

    monkeypatch.setattr(orch, "_write_json", fail_pointer_write)

    with pytest.raises(OSError, match="injected pointer failure"):
        orch.activate()

    assert json.loads(orch.pointer.read_text())["old"] is True
    assert orch.manifest.read_text() == manifest_before


def test_activate_manifest_rollback_uses_atomic_restore(tmp_path, monkeypatch):
    artifact = tmp_path / "market.parquet"
    artifact.write_bytes(b"data")
    orch = PipelineOrchestrator(tmp_path)
    orch.build_manifest("r1", ["market.parquet"])
    orch.transition(ReleaseState.CANDIDATE)
    manifest_before = orch.manifest.read_text()

    original_write = orch._write_json
    calls = []

    def fail_after_pointer_write(path, payload):
        calls.append(path)
        if path == orch.pointer:
            raise OSError("injected pointer failure")
        return original_write(path, payload)

    monkeypatch.setattr(orch, "_write_json", fail_after_pointer_write)

    with pytest.raises(OSError, match="injected pointer failure"):
        orch.activate()

    assert orch.manifest.read_text() == manifest_before
    assert calls[0] == orch.pointer
