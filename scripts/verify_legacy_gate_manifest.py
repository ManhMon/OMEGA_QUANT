#!/usr/bin/env python3
"""Verify the immutable B1 legacy-gate manifest."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".ly_state" / "session" / "legacy_gate_migration_b1_manifest_20260728.json"
PHASE_GATES = ROOT / ".ly_state" / "session" / "phase_gates.json"
EXPECTED = (
    "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
    "LLM_PROMPT_SYNTHESIS_SEARCH_IMPROVEMENT_20260612",
    "SHARPE_TCOST_PHASE2_SIMULATOR_FIX",
    "SHARPE_TCOST_PHASE2_HYSTERESIS_FIX",
    "SHARPE_TCOST_PHASE2_HYSTERESIS_FIX_CLEANUP",
)
STAGED_GATE = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
MUTABLE_PHASE_GATE_FIELDS = frozenset(
    {"l3_session_id", "l3_session_key", "l3_role_id", "l3_role_name", "audit_report_path", "final_verdict"}
)
STAGED_FIELDS = frozenset(
    {"expected_l3_report_path", "expected_l3_report_sha256", "expected_l3_session_id",
     "expected_l3_session_key", "expected_l3_role_id", "expected_l3_role_name", "expected_l3_verdict"}
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def repo_file(relative: str, required: bool = True) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe path: {relative}")
    resolved = ROOT / path
    if required and not resolved.is_file():
        raise ValueError(f"missing file: {relative}")
    return resolved


def immutable_projection(value: dict) -> dict:
    return {key: item for key, item in value.items() if key not in MUTABLE_PHASE_GATE_FIELDS}


def validate_staged_l3_metadata(entry: dict, phase_gate: dict) -> None:
    """Bind mutable B1 L3 metadata to the manifest's staged target."""
    if set(entry) - {"l2_report_path", "l2_report_sha256", "phase_gate_snapshot_sha256"} - STAGED_FIELDS:
        raise ValueError("unknown staged metadata field")
    if not STAGED_FIELDS.issubset(entry):
        raise ValueError("staged L3 metadata incomplete")
    expected_path = entry["expected_l3_report_path"]
    if not expected_path.startswith(".ly_state/session/audit_reports/"):
        raise ValueError(f"unsafe expected L3 path: {expected_path}")
    if phase_gate.get("audit_report_path") != expected_path:
        raise ValueError("staged L3 report path mismatch")
    report = repo_file(expected_path)
    report_hash = sha256(report)
    if report_hash != entry["expected_l3_report_sha256"]:
        raise ValueError("staged L3 report hash mismatch")
    if not isinstance(phase_gate.get("l3_session_id"), str) or not phase_gate["l3_session_id"]:
        raise ValueError("staged L3 session ID missing")
    if phase_gate.get("l3_session_key") != phase_gate["l3_session_id"]:
        raise ValueError("staged L3 session identity mismatch")
    for field in ("l3_session_id", "l3_session_key", "l3_role_id", "l3_role_name"):
        expected = entry[f"expected_{field}"]
        if phase_gate.get(field) != expected:
            raise ValueError(f"staged L3 {field} mismatch")
    if phase_gate.get("final_verdict") != entry["expected_l3_verdict"]:
        raise ValueError("staged L3 final_verdict mismatch")


def verify() -> None:
    raw = MANIFEST.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise ValueError("manifest must be UTF-8 without BOM and use LF")
    data = json.loads(raw.decode("utf-8"))
    if data["schema_version"] != "legacy-gate-migration-b1/v1" or data["batch"] != "B1":
        raise ValueError("manifest identity mismatch")
    if set(data["b1_gates"]) != set(EXPECTED):
        raise ValueError("B1 membership must contain exactly the five required keys")
    stored = data["manifest_sha256"]
    unsigned = dict(data)
    del unsigned["manifest_sha256"]
    if hashlib.sha256(canonical(unsigned)).hexdigest() != stored:
        raise ValueError("manifest_sha256 mismatch")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    if commit != data["commit"]:
        raise ValueError("commit mismatch")
    baseline = subprocess.run(
        [sys.executable, "scripts/sod_gate_enforcer.py"], cwd=ROOT, check=True, capture_output=True
    )
    if hashlib.sha256(baseline.stdout + baseline.stderr).hexdigest() != data["baseline_enforcer_output_sha256"]:
        raise ValueError("baseline enforcer output hash mismatch")
    phase = json.loads(PHASE_GATES.read_text(encoding="utf-8"))
    for key in EXPECTED:
        entry = data["b1_gates"][key]
        if sha256(repo_file(entry["l2_report_path"])) != entry["l2_report_sha256"]:
            raise ValueError(f"L2 report hash mismatch: {key}")
        if hashlib.sha256(canonical(immutable_projection(phase[key]))).hexdigest() != entry["phase_gate_snapshot_sha256"]:
            raise ValueError(f"phase-gate snapshot mismatch: {key}")
        if key == STAGED_GATE:
            validate_staged_l3_metadata(entry, phase[key])
    for path, expected_hash in data["advisory_fixture_sha256"].items():
        if sha256(repo_file(path)) != expected_hash:
            raise ValueError(f"fixture hash mismatch: {path}")
    print("B1 manifest verification: PASS")


if __name__ == "__main__":
    try:
        verify()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"B1 manifest verification: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
