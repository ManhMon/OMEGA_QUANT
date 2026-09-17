import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import sod_gate_enforcer as sod
import phase_workflow_enforcer as workflow
import verify_legacy_gate_manifest as manifest


def test_allowlists_are_exact():
    assert sod.LEGACY_DATE_KEYS == frozenset({
        "GP_PRODUCTION_VALIDATION_GATE6_20260704", "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
        "HYBRID_REGIME_DYNAMIC_BRAKE_FIX_20260621", "RECOVERY_SELECTOR_OPT_IN_20260614",
        "VNSTOCK_LATEST_STANDARDIZATION_20260612", "LABEL_HORIZON_SWEEP_ENSEMBLE_20260623",
        "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624", "LATENT_ALPHA_MINING_64D_20260617",
        "GP_CLAUDE_IDEAS_UPGRADE_20260702", "GP_V4_IMPLEMENTATION", "GP_V4_ADVANCED_IMPLEMENTATION",
        "GP_NUMBA_JIT_VM_IMPLEMENTATION", "GP_ALT_DATA_FETCHER_OPTIMIZATION",
        "ALPHA_WEAKNESS_DIAGNOSTICS_20260614",
    })
    assert sod.LEGACY_WORKFLOW_KEYS == frozenset({
        "GP_ALTERNATIVE_FEATURES_MEMORY_FIX", "GP_ALT_DATA_FETCHER_OPTIMIZATION",
        "GP_ALT_FEATURES_OVERLAP_AND_OOM_FIX", "GP_DIVERSITY_ORTHO_PENALTY_20260702",
        "GP_EVOLUTION_BACKEND_LOKY_20260702", "GP_PARALLEL_OPTIMIZATION_20260705",
        "GP_PRODUCTION_RUN_CODE_AUDIT", "GP_PRODUCTION_RUN_WORKFLOW_SETUP",
        "GP_V4_ADVANCED_IMPLEMENTATION", "GP_V4_ADVANCED_PLAN_REVIEW", "GP_V4_IMPLEMENTATION",
        "GP_V4_OPTIMIZATION_PLAN_REVIEW", "GP_VN_ALPHAS_MEMORY_FIX",
    })


def _valid_fixture(tmp_path, monkeypatch, timestamp="2026-07-27T00:00:00Z"):
    monkeypatch.setattr(sod, "WORKSPACE", tmp_path)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_FILE", tmp_path / "retry2.json")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_LOCK", tmp_path / "retry2.sha256")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_FILE", tmp_path / "retry3.json")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_LOCK", tmp_path / "retry3.sha256")
    sidecar = tmp_path / "legacy.json"
    lock = tmp_path / "legacy.sha256"
    records, gates = {}, {}
    for index, key in enumerate(sorted(sod.LEGACY_DATE_KEYS)):
        evidence = Path(".ly_state/session/evidence") / f"{index}.md"
        report = Path(".ly_state/session/audit_reports") / f"fresh_{index}.md"
        (tmp_path / evidence).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / report).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / evidence).write_text("historical", encoding="utf-8")
        (tmp_path / report).write_text("[APPROVED]", encoding="utf-8")
        gate = {"phase_name": key, "timestamp": timestamp, "immutable": index}
        gates[key] = gate
        records[key] = {
            "original_gate_record_sha256": sod._sha256(sod._immutable_gate_record(gate)),
            "original_key": key, "original_timestamp": timestamp,
            "historical_evidence_path": evidence.as_posix(),
            "historical_evidence_sha256": sod._sha256((tmp_path / evidence).read_bytes()),
            "resolved_date": "2026-07-27", "reason_code": "legacy",
            "reconciled_at": "2026-07-27T01:00:00Z", "fresh_l3_report_path": report.as_posix(),
            "fresh_l3_session_id": f"fresh-{index}", "fresh_l3_session_key": f"fresh-{index}",
            "fresh_l3_verdict": "[APPROVED]", "workflow_classification": "reconcile",
        }
    gate4 = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
    snapshot = {"record": sod._immutable_gate_record(gates[gate4]), "record_sha256": records[gate4]["original_gate_record_sha256"]}
    records[gate4].update(original_gate_snapshot=snapshot, original_gate_sha256=sod._sha256(snapshot))
    encoded = json.dumps(records, sort_keys=True).encode()
    sidecar.write_bytes(encoded)
    lock.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", sidecar)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", lock)
    return records, gates


def test_valid_sidecar_preserves_gate_timestamp_and_null_semantics(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = sorted(gates)[0]
    gates[key]["timestamp"] = None
    records[key]["original_timestamp"] = None
    records[key]["original_gate_record_sha256"] = sod._sha256(sod._immutable_gate_record(gates[key]))
    encoded = json.dumps(records, sort_keys=True).encode()
    sod.LEGACY_RECONCILIATION_FILE.write_bytes(encoded)
    sod.LEGACY_RECONCILIATION_LOCK.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    assert sod.validate_legacy_reconciliation(gates) == (True, "legacy reconciliation valid")


def test_original_timestamp_drift_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = sorted(gates)[0]
    gates[key]["timestamp"] = "2026-07-28T00:00:00Z"
    assert not sod.validate_legacy_reconciliation(gates)[0]


def test_required_schema_types_and_hashes_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = sorted(records)[0]
    records[key]["reason_code"] = 1
    encoded = json.dumps(records, sort_keys=True).encode()
    sod.LEGACY_RECONCILIATION_FILE.write_bytes(encoded)
    sod.LEGACY_RECONCILIATION_LOCK.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    assert "field types" in sod.validate_legacy_reconciliation(gates)[1]


def test_original_record_hash_drift_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    gates[sorted(gates)[0]]["immutable"] = 99
    assert "original gate record hash drift" in sod.validate_legacy_reconciliation(gates)[1]


def test_non_gate4_legacy_record_uses_original_hash_compatibility(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = next(key for key in records if key != "GP_OVERFITTING_REMEDIATION_GATE4_20260704")
    assert sod.validate_legacy_reconciliation(gates) == (True, "legacy reconciliation valid")
    gates[key]["immutable"] = "tampered"
    assert "original gate record hash drift" in sod.validate_legacy_reconciliation(gates)[1]


def test_gate4_snapshot_survives_mutable_metadata_update(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
    snapshot = {"record": sod._immutable_gate_record(gates[key]), "record_sha256": records[key]["original_gate_record_sha256"]}
    records[key]["original_gate_snapshot"] = snapshot
    records[key]["original_gate_sha256"] = sod._sha256(snapshot)
    gates[key]["l3_session_id"] = "fresh-session"
    gates[key]["audit_report_path"] = ".ly_state/session/audit_reports/fresh.md"
    assert sod.resolve_original_gate_snapshot(records[key], key)[1] == "ok"


def test_gate4_snapshot_tamper_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
    snapshot = {"record": sod._immutable_gate_record(gates[key]), "record_sha256": records[key]["original_gate_record_sha256"]}
    records[key]["original_gate_snapshot"] = snapshot
    records[key]["original_gate_sha256"] = sod._sha256(snapshot)
    snapshot["record"]["scope"] = "tampered"
    assert "snapshot hash drift" in sod.resolve_original_gate_snapshot(records[key], key)[1]


def test_gate4_residual_snapshot_validates_with_staged_l3_metadata(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    key = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
    snapshot = {"record": sod._immutable_gate_record(gates[key]), "record_sha256": records[key]["original_gate_record_sha256"]}
    records[key].update(original_gate_snapshot=snapshot, original_gate_sha256=sod._sha256(snapshot))
    gates[key].update(l3_session_id="staged", l3_session_key="staged", audit_report_path=".ly_state/session/audit_reports/staged.md")
    assert sod.resolve_original_gate_snapshot(records[key], key)[0] == snapshot


def test_manifest_rejects_staged_report_path_mismatch(tmp_path, monkeypatch):
    report, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    gate["audit_report_path"] = ".ly_state/session/audit_reports/other.md"
    with pytest.raises(ValueError, match="path mismatch"):
        manifest.validate_staged_l3_metadata(entry, gate)


def _staged_manifest_fixture(tmp_path):
    report = tmp_path / ".ly_state/session/audit_reports/staged.md"
    report.parent.mkdir(parents=True)
    report.write_text("L3 Session: staged\nRole: code-reviewer\n[APPROVED]\n", encoding="utf-8")
    entry = {
        "l2_report_path": "l2.md", "l2_report_sha256": "0" * 64,
        "phase_gate_snapshot_sha256": "0" * 64,
        "expected_l3_report_path": report.relative_to(tmp_path).as_posix(),
        "expected_l3_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "expected_l3_session_id": "staged", "expected_l3_session_key": "staged",
        "expected_l3_role_id": 21, "expected_l3_role_name": "code-reviewer",
        "expected_l3_verdict": "[APPROVED]",
    }
    gate = {"audit_report_path": entry["expected_l3_report_path"], "l3_session_id": "staged",
            "l3_session_key": "staged", "l3_role_id": 21, "l3_role_name": "code-reviewer",
            "final_verdict": "[APPROVED]"}
    return report, entry, gate


def test_manifest_accepts_valid_staged_metadata(tmp_path, monkeypatch):
    report, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    manifest.validate_staged_l3_metadata(entry, gate)


def test_manifest_rejects_report_tamper(tmp_path, monkeypatch):
    report, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    report.write_bytes(report.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="report hash mismatch"):
        manifest.validate_staged_l3_metadata(entry, gate)


def test_manifest_rejects_staged_metadata_mismatch(tmp_path, monkeypatch):
    _, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    gate["l3_role_name"] = "wrong"
    with pytest.raises(ValueError, match="l3_role_name mismatch"):
        manifest.validate_staged_l3_metadata(entry, gate)


def test_manifest_rejects_missing_staged_report_hash(tmp_path, monkeypatch):
    _, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    del entry["expected_l3_report_sha256"]
    with pytest.raises(ValueError, match="staged L3 metadata incomplete"):
        manifest.validate_staged_l3_metadata(entry, gate)


def test_manifest_verify_gate4_missing_staged_report_hash_fails_closed(tmp_path, monkeypatch):
    manifest_file = tmp_path / "manifest.json"
    source = manifest.MANIFEST
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["b1_gates"][manifest.STAGED_GATE]["expected_l3_report_sha256"]
    payload["baseline_enforcer_output_sha256"] = hashlib.sha256(b"baseline").hexdigest()
    unsigned = dict(payload)
    del unsigned["manifest_sha256"]
    payload["manifest_sha256"] = hashlib.sha256(manifest.canonical(unsigned)).hexdigest()
    manifest_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(manifest, "MANIFEST", manifest_file)
    monkeypatch.setattr(
        manifest.subprocess,
        "run",
        lambda args, **kwargs: SimpleNamespace(
            stdout=payload["commit"] if args[0] == "git" else b"baseline",
            stderr=b"",
        ),
    )

    with pytest.raises(ValueError, match="staged L3 metadata incomplete"):
        manifest.verify()

def test_manifest_rejects_unknown_staged_field(tmp_path, monkeypatch):
    _, entry, gate = _staged_manifest_fixture(tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    entry["expected_scope"] = "bad"
    with pytest.raises(ValueError, match="unknown staged metadata"):
        manifest.validate_staged_l3_metadata(entry, gate)


def test_manifest_immutable_projection_rejects_field_drift():
    gate = {"phase_name": "x", "l2_role_id": 11, "l3_session_id": "a"}
    expected = hashlib.sha256(manifest.canonical(manifest.immutable_projection(gate))).hexdigest()
    gate["l2_role_id"] = 12
    assert hashlib.sha256(manifest.canonical(manifest.immutable_projection(gate))).hexdigest() != expected


def test_manifest_immutable_projection_ignores_staged_metadata():
    gate = {"phase_name": "x", "l3_session_id": "a"}
    expected = hashlib.sha256(manifest.canonical(manifest.immutable_projection(gate))).hexdigest()
    gate["l3_session_id"] = "b"
    assert hashlib.sha256(manifest.canonical(manifest.immutable_projection(gate))).hexdigest() == expected


def test_historical_evidence_hash_drift_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    (tmp_path / records[sorted(records)[0]]["historical_evidence_path"]).write_text("changed", encoding="utf-8")
    assert "historical evidence hash drift" in sod.validate_legacy_reconciliation(gates)[1]


def test_reused_report_or_session_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    keys = sorted(records)
    records[keys[1]]["fresh_l3_session_id"] = records[keys[0]]["fresh_l3_session_id"]
    records[keys[1]]["fresh_l3_session_key"] = records[keys[0]]["fresh_l3_session_key"]
    encoded = json.dumps(records, sort_keys=True).encode()
    sod.LEGACY_RECONCILIATION_FILE.write_bytes(encoded)
    sod.LEGACY_RECONCILIATION_LOCK.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    assert "reuses L3 identity" in sod.validate_legacy_reconciliation(gates)[1]


@pytest.mark.parametrize("content", ["[NEEDS_FIX]", "[MANUAL_APPROVAL]", "manual approval"])
def test_invalid_approval_evidence_rejected(tmp_path, monkeypatch, content):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    report = tmp_path / records[sorted(records)[0]]["fresh_l3_report_path"]
    report.write_text(content, encoding="utf-8")
    assert not sod.validate_legacy_reconciliation(gates)[0]


def test_blocked_workflow_rejected(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    records[sorted(records)[0]]["workflow_classification"] = "blocked"
    encoded = json.dumps(records, sort_keys=True).encode()
    sod.LEGACY_RECONCILIATION_FILE.write_bytes(encoded)
    sod.LEGACY_RECONCILIATION_LOCK.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    assert "is blocked" in sod.validate_legacy_reconciliation(gates)[1]


def test_missing_sidecar_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", tmp_path / "legacy.sha256")
    (tmp_path / "legacy.sha256").write_text("0" * 64, encoding="utf-8")
    valid, message = sod.validate_legacy_reconciliation({})
    assert not valid
    assert "required" in message


def test_lock_hash_drift_fails_closed(tmp_path, monkeypatch):
    sidecar = tmp_path / "legacy.json"
    lock = tmp_path / "legacy.sha256"
    sidecar.write_text("{}", encoding="utf-8")
    lock.write_text("0" * 64, encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", sidecar)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", lock)
    valid, message = sod.validate_legacy_reconciliation({})
    assert not valid
    assert "hash drift" in message


def test_workflow_rejects_fabricated_or_derived_identity(monkeypatch):
    monkeypatch.setattr(workflow, "load_phase_gates", lambda: {
        "GP_V4_IMPLEMENTATION": {
            "l3_session_id": "fresh", "l3_session_key": "derived",
            "audit_report_path": ".ly_state/session/audit_reports/a.md",
            "final_verdict": "[APPROVED]",
        }
    })
    monkeypatch.setattr(workflow, "resolve_active_legacy_gate", lambda gates, phase: None)
    assert not workflow.check_phase("GP_V4_IMPLEMENTATION")


def test_audit_path_traversal_rejected():
    valid, message = sod.validate_audit_report_path(".ly_state/session/audit_reports/../x.md")
    assert not valid
    assert "traversal" in message


def test_sidecar_schema_rejects_unknown_key(tmp_path, monkeypatch):
    sidecar = tmp_path / "legacy.json"
    lock = tmp_path / "legacy.sha256"
    payload = {"unexpected": {}}
    encoded = json.dumps(payload).encode()
    sidecar.write_bytes(encoded)
    lock.write_text(hashlib.sha256(encoded).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", sidecar)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", lock)
    valid, message = sod.validate_legacy_reconciliation({})
    assert not valid
    assert "exactly the 14" in message


def test_retry2_resolver_rejects_superseded_lock_drift(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    retry = tmp_path / "retry2.json"
    lock = retry.with_suffix(".sha256")
    payload = {"version": sod.LEGACY_RECONCILIATION_RETRY2_VERSION,
               "supersedes": "legacy.json",
               "supersedes_lock_sha256": "0" * 64,
               "records": records}
    raw = sod._canonical_json(payload)
    retry.write_bytes(raw)
    lock.write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", tmp_path / "legacy.sha256")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_FILE", retry)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_LOCK", lock)
    assert sod.resolve_active_legacy_sidecar(gates) == (False, "retry2 superseded V1 lock hash drift")


def test_retry2_rejects_report_identity_drift(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    v1_lock = sod.LEGACY_RECONCILIATION_LOCK.read_text().strip()
    report = tmp_path / records[sorted(records)[0]]["fresh_l3_report_path"]
    report.write_text("L3 Session: `wrong`\nL3 Session Key: `wrong`\n[APPROVED]", encoding="utf-8")
    payload = {"version": sod.LEGACY_RECONCILIATION_RETRY2_VERSION,
               "supersedes": "legacy.json",
               "supersedes_lock_sha256": v1_lock,
               "records": records}
    raw = sod._canonical_json(payload)
    retry = tmp_path / "retry2.json"
    retry.write_bytes(raw)
    retry.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_LOCK", tmp_path / "legacy.sha256")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_FILE", retry)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_LOCK", retry.with_suffix(".sha256"))
    assert "fresh report identity drift" in sod.resolve_active_legacy_sidecar(gates)[1]


def test_retry3_resolver_rejects_retry2_lock_drift(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    retry2 = tmp_path / "retry2.json"
    retry2_lock = retry2.with_suffix(".sha256")
    retry2_payload = {"version": sod.LEGACY_RECONCILIATION_RETRY2_VERSION,
                      "supersedes": "legacy.json",
                      "supersedes_lock_sha256": tmp_path.joinpath("legacy.sha256").read_text(),
                      "records": records}
    retry2_raw = sod._canonical_json(retry2_payload)
    retry2.write_bytes(retry2_raw)
    retry2_lock.write_text(hashlib.sha256(retry2_raw).hexdigest(), encoding="utf-8")
    retry3 = tmp_path / "retry3.json"
    payload = {"version": sod.LEGACY_RECONCILIATION_RETRY3_VERSION,
               "supersedes": "retry2.json", "supersedes_lock_sha256": "0" * 64,
               "records": records}
    raw = sod._canonical_json(payload)
    retry3.write_bytes(raw)
    retry3.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_FILE", retry2)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_LOCK", retry2_lock)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_FILE", retry3)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_LOCK", retry3.with_suffix(".sha256"))
    assert sod.resolve_active_legacy_sidecar(gates) == (False, "retry3 superseded retry2 lock hash drift")


def test_retry3_resolver_fails_closed_on_partial_records(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    for record in records.values():
        report = tmp_path / record["fresh_l3_report_path"]
        session = record["fresh_l3_session_id"]
        report.write_text(f"L3 Session: `{session}`\nL3 Session Key: `{session}`\n[APPROVED]", encoding="utf-8")
    retry2 = tmp_path / "retry2.json"
    retry2_records = {key: {field: value for field, value in record.items() if field not in sod.LEGACY_SNAPSHOT_FIELDS}
                     for key, record in records.items()}
    retry2_payload = {"version": sod.LEGACY_RECONCILIATION_RETRY2_VERSION,
                      "supersedes": "legacy.json",
                      "supersedes_lock_sha256": tmp_path.joinpath("legacy.sha256").read_text(),
                      "records": retry2_records}
    retry2_raw = sod._canonical_json(retry2_payload)
    retry2.write_bytes(retry2_raw)
    retry2.with_suffix(".sha256").write_text(hashlib.sha256(retry2_raw).hexdigest(), encoding="utf-8")
    retry3 = tmp_path / "retry3.json"
    payload = {"version": sod.LEGACY_RECONCILIATION_RETRY3_VERSION,
               "supersedes": "retry2.json",
               "supersedes_lock_sha256": retry2.with_suffix(".sha256").read_text(),
               "records": {next(iter(records)): records[next(iter(records))]}}
    raw = sod._canonical_json(payload)
    retry3.write_bytes(raw)
    retry3.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_FILE", retry2)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY2_LOCK", retry2.with_suffix(".sha256"))
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_FILE", retry3)
    monkeypatch.setattr(sod, "LEGACY_RECONCILIATION_RETRY3_LOCK", retry3.with_suffix(".sha256"))
    assert "exactly the 14" in sod.resolve_active_legacy_sidecar(gates)[1]


def test_residual_ledger_requires_exact_fail_closed_classes(tmp_path, monkeypatch):
    payload = {
        "version": sod.LEGACY_RESIDUAL_EVIDENCE_VERSION,
        "records": {
            key: {"residual_class": sod.LEGACY_RESIDUAL_EXPECTED_CLASSES[key], "status": "NEEDS_FIX"}
            for key in sod.LEGACY_RESIDUAL_KEYS
        },
    }
    raw = sod._canonical_json(payload)
    ledger = tmp_path / "residual.json"
    lock = tmp_path / "residual.sha256"
    ledger.write_bytes(raw)
    lock.write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_FILE", ledger)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_LOCK", lock)
    assert sod.validate_legacy_residual_evidence() == (
        True, "legacy residual evidence ledger valid"
    )


def test_residual_ledger_rejects_approval(tmp_path, monkeypatch):
    payload = {
        "version": sod.LEGACY_RESIDUAL_EVIDENCE_VERSION,
        "records": {
            key: {"residual_class": "gate_date_mismatch", "status": "APPROVED"}
            for key in sod.LEGACY_RESIDUAL_KEYS
        },
    }
    raw = sod._canonical_json(payload)
    ledger = tmp_path / "residual.json"
    lock = tmp_path / "residual.sha256"
    ledger.write_bytes(raw)
    lock.write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_FILE", ledger)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_LOCK", lock)
    valid, message = sod.validate_legacy_residual_evidence()
    assert not valid
    assert "fail-closed" in message


def test_residual_mapping_is_exact_and_complete():
    assert set(sod.LEGACY_RESIDUAL_EXPECTED_CLASSES) == sod.LEGACY_RESIDUAL_KEYS
    assert len(set(sod.LEGACY_RESIDUAL_EXPECTED_CLASSES.values())) == 5
    assert sod.LEGACY_RESIDUAL_EXPECTED_CLASSES["ALPHA_WEAKNESS_DIAGNOSTICS_20260614"] == "fresh_report_missing_approval"
    assert sod.LEGACY_RESIDUAL_EXPECTED_CLASSES["GP_V4_IMPLEMENTATION"] == "l3_report_evidence_missing"
    assert sod.LEGACY_RESIDUAL_EXPECTED_CLASSES["GP_V4_ADVANCED_IMPLEMENTATION"] == "l3_report_evidence_missing"
    assert sod.LEGACY_RESIDUAL_EXPECTED_CLASSES["GP_NUMBA_JIT_VM_IMPLEMENTATION"] == "l3_report_evidence_missing"
    assert sod.LEGACY_RESIDUAL_EXPECTED_CLASSES["GP_ALT_DATA_FETCHER_OPTIMIZATION"] == "l3_report_evidence_missing"


def test_residual_ledger_rejects_mapping_drift(tmp_path, monkeypatch):
    payload = {
        "version": sod.LEGACY_RESIDUAL_EVIDENCE_VERSION,
        "records": {
            key: {"residual_class": "gate_date_mismatch", "status": "NEEDS_FIX"}
            for key in sod.LEGACY_RESIDUAL_KEYS
        },
    }
    raw = sod._canonical_json(payload)
    ledger, lock = tmp_path / "residual.json", tmp_path / "residual.sha256"
    ledger.write_bytes(raw)
    lock.write_text(sod._sha256(raw), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_FILE", ledger)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_EVIDENCE_LOCK", lock)
    assert not sod.validate_legacy_residual_evidence()[0]


def test_residual_reconciliation_requires_both_final_artifacts(tmp_path, monkeypatch):
    target = tmp_path / "residual.json"
    lock = tmp_path / "residual.sha256"
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", lock)
    target.write_bytes(sod._canonical_gate4_provenance_json({}))
    assert "required" in sod.resolve_active_residual_reconciliation()[1]


def test_residual_reconciliation_rejects_full_original_gate_record_hash_drift(tmp_path, monkeypatch):
    records, gates = _valid_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_KEYS", frozenset(gates))
    monkeypatch.setattr(
        sod, "LEGACY_RESIDUAL_EXPECTED_CLASSES",
        {key: "gate_date_mismatch" for key in gates},
    )
    payload = {
        "version": sod.LEGACY_RESIDUAL_RECONCILIATION_VERSION,
        "records": {
            key: {
                "original_gate_record_sha256": sod._sha256(sod._immutable_gate_record(gate)),
                "original_key": key,
                "original_timestamp": gate["timestamp"],
                "residual_class": "gate_date_mismatch",
                "historical_evidence_path": ".ly_state/session/evidence/0.md",
                "historical_evidence_sha256": "0" * 64,
                "fresh_l3_report_path": ".ly_state/session/audit_reports/fresh_0.md",
                "fresh_l3_report_sha256": "0" * 64,
                "fresh_l3_session_id": f"session-{index}",
                "fresh_l3_session_key": f"session-{index}",
                "fresh_l3_verdict": "[APPROVED]",
                "reconciled_at": "2026-07-27T01:00:00Z",
            }
            for index, (key, gate) in enumerate(gates.items())
        },
    }
    first = next(iter(payload["records"]))
    gates[first]["immutable"] = "tampered"
    target = tmp_path / "residual.json"
    raw = sod._canonical_json(payload)
    target.write_bytes(raw)
    target.with_suffix(".sha256").write_text(sod._sha256(raw), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", target.with_suffix(".sha256"))
    assert "original gate record hash drift" in sod.validate_residual_reconciliation(gates)[1]


def test_residual_reconciliation_publisher_never_clobbers(tmp_path, monkeypatch):
    target = tmp_path / "residual.json"
    lock = tmp_path / "residual.sha256"
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", lock)
    target.write_text("existing", encoding="utf-8")
    payload = {"version": sod.LEGACY_RESIDUAL_RECONCILIATION_VERSION, "records": {}}
    with pytest.raises(FileExistsError):
        sod.publish_residual_reconciliation(payload)
    assert target.read_text(encoding="utf-8") == "existing"


def test_residual_reconciliation_publisher_rejects_partial_final(tmp_path, monkeypatch):
    target = tmp_path / "residual.json"
    lock = tmp_path / "residual.sha256"
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", lock)
    lock.write_text("partial", encoding="utf-8")
    payload = {"version": sod.LEGACY_RESIDUAL_RECONCILIATION_VERSION, "records": {}}
    with pytest.raises(FileExistsError):
        sod.publish_residual_reconciliation(payload)


def test_compliance_uses_fresh_residual_evidence_instead_of_historical_report(monkeypatch):
    key = next(iter(sod.LEGACY_RESIDUAL_KEYS))
    fresh_path = ".ly_state/session/audit_reports/fresh.md"
    gate = {"phase_name": key, "final_verdict": "[APPROVED]", "audit_report_path": "docs/historical.md"}
    record = {"fresh_l3_report_path": fresh_path, "fresh_l3_session_id": "fresh", "fresh_l3_session_key": "fresh", "fresh_l3_verdict": "[APPROVED]"}
    monkeypatch.setattr(sod, "validate_task_graph", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "load_gates", lambda: [gate])
    monkeypatch.setattr(sod, "validate_legacy_residual_evidence", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_legacy_sidecar", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_residual_reconciliation", lambda gates: (True, "ok"))
    monkeypatch.setattr(sod, "_read_locked_json", lambda path, lock: ({"records": {key: record}}, "ok"))
    monkeypatch.setattr(sod, "load_role_specs", lambda: {})
    monkeypatch.setattr(sod, "check_audit_report_exists", lambda path: (path == fresh_path, "ok"))
    monkeypatch.setattr(sod, "check_audit_report_content", lambda path, verdict: (path == fresh_path, "ok"))
    monkeypatch.setattr(sod, "check_report_evidence_wording", lambda *args: (True, "ok"))
    assert sod.check_sod_compliance() is True


@pytest.mark.parametrize("reason", ["missing", "tampered", "missing residual key", "NEEDS_FIX", "duplicate identity"])
def test_compliance_fails_closed_when_residual_reconciliation_is_invalid(monkeypatch, reason):
    key = next(iter(sod.LEGACY_RESIDUAL_KEYS))
    monkeypatch.setattr(sod, "validate_task_graph", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "load_gates", lambda: [{"phase_name": key, "final_verdict": "[APPROVED]"}])
    monkeypatch.setattr(sod, "validate_legacy_residual_evidence", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_legacy_sidecar", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_residual_reconciliation", lambda gates: (False, reason))
    assert sod.check_sod_compliance() is False


def test_compliance_prints_closure_only_after_both_residual_artifacts_validate(monkeypatch, capsys):
    key = next(iter(sod.LEGACY_RESIDUAL_KEYS))
    record = {
        "fresh_l3_report_path": ".ly_state/session/audit_reports/fresh.md",
        "fresh_l3_session_id": "fresh",
        "fresh_l3_session_key": "fresh",
        "fresh_l3_verdict": "[APPROVED]",
    }
    monkeypatch.setattr(sod, "validate_task_graph", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "load_gates", lambda: [{"phase_name": key, "final_verdict": "[APPROVED]"}])
    monkeypatch.setattr(sod, "validate_legacy_residual_evidence", lambda: (True, "ledger valid"))
    monkeypatch.setattr(sod, "resolve_active_legacy_sidecar", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_residual_reconciliation", lambda gates: (False, "hash drift"))
    assert sod.check_sod_compliance() is False
    assert "17 resolved; 0 open" not in capsys.readouterr().out

    monkeypatch.setattr(sod, "resolve_active_residual_reconciliation", lambda gates: (True, "legacy residual reconciliation: 17 resolved; 0 open"))
    monkeypatch.setattr(sod, "_read_locked_json", lambda path, lock: ({"records": {key: record}}, "ok"))
    monkeypatch.setattr(sod, "load_role_specs", lambda: {})
    monkeypatch.setattr(sod, "check_audit_report_exists", lambda path: (True, "ok"))
    monkeypatch.setattr(sod, "check_audit_report_content", lambda path, verdict: (True, "ok"))
    monkeypatch.setattr(sod, "check_report_evidence_wording", lambda *args: (True, "ok"))
    assert sod.check_sod_compliance() is True
    assert "legacy residual reconciliation: 17 resolved; 0 open" in capsys.readouterr().out


def test_compliance_does_not_bypass_nonresidual_gate(monkeypatch):
    key = "NONRESIDUAL_GATE"
    monkeypatch.setattr(sod, "validate_task_graph", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "load_gates", lambda: [{"phase_name": key, "final_verdict": "[APPROVED]", "audit_report_path": "docs/historical.md"}])
    monkeypatch.setattr(sod, "validate_legacy_residual_evidence", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_legacy_sidecar", lambda: (True, "ok"))
    monkeypatch.setattr(sod, "resolve_active_residual_reconciliation", lambda gates: (True, "ok"))
    monkeypatch.setattr(sod, "_read_locked_json", lambda path, lock: ({"records": {}}, "ok"))
    monkeypatch.setattr(sod, "load_role_specs", lambda: {})
    monkeypatch.setattr(sod, "check_audit_report_exists", lambda path: (False, "missing"))
    assert sod.check_sod_compliance() is False


def test_retry1_bundle_requires_valid_trusted_tag_oid_pin(monkeypatch):
    assert sod.PROVENANCE_TRUST_TAG == "refs/tags/omega-provenance-retry1-gate3-20260801"
    assert sod.PROVENANCE_TRUST_TAG_OBJECT_OID == "58cbde4924eef16166ea57b9ee8e6197fdced302"
    monkeypatch.setattr(sod, "PROVENANCE_TRUST_TAG_OBJECT_OID", None)
    assert sod.validate_legacy_residual_provenance_retry1() == (
        False, "retry1 provenance trusted tag object OID pin unset"
    )


def test_gate1_retry1_authority_requires_exact_blob_not_worktree(monkeypatch):
    record = {
        "original_audit_report_path": sod.LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_PATH,
        "original_audit_report_blob_oid": sod.LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_BLOB_OID,
        "original_audit_report_sha256": sod.LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_SHA256,
    }
    assert sod._gate1_original_audit_blob(record)
    record["original_audit_report_blob_oid"] = "0" * 40
    assert not sod._gate1_original_audit_blob(record)


def test_retry1_bundle_accepts_only_exact_gate2_authority_tuple(monkeypatch):
    payload = json.loads(sod.LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE.read_text(encoding="utf-8"))
    record = payload["records"]["GP_OVERFITTING_REMEDIATION_GATE4_20260704"]
    assert record["authority_evidence_path"] == sod.LEGACY_GATE2_AUTHORITY_PATH
    assert record["authority_evidence_sha256"] == sod.LEGACY_GATE2_AUTHORITY_SHA256
    assert record["authority_l3_session_id"] == sod.LEGACY_GATE2_AUTHORITY_SESSION
    assert record["authority_l3_session_key"] == sod.LEGACY_GATE2_AUTHORITY_SESSION


def test_retry1_validated_resolution_is_17_resolved_1_open(monkeypatch):
    monkeypatch.setattr(sod, "_trusted_provenance_bundle", lambda raw: (True, "ok"))
    assert sod.validate_legacy_residual_provenance_retry1() == (
        True, "legacy residual reconciliation: 17 resolved; 1 open"
    )


def test_retry1_gate3_absent_from_immutable_predecessor_uses_pinned_claim(tmp_path, monkeypatch):
    predecessor = Path(r"C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\legacy_residual_reconciliation_20260727.json")
    predecessor_lock = predecessor.with_suffix(".sha256")
    if not predecessor.is_file() or not predecessor_lock.is_file():
        pytest.skip("primary immutable predecessor unavailable")
    payload = json.loads(sod.LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE.read_text(encoding="utf-8"))
    assert sod._sha256(predecessor.read_bytes()) == payload["supersedes_raw_sha256"]
    assert predecessor_lock.read_text(encoding="utf-8").strip() == payload["supersedes_lock_value"]
    gate1 = payload["records"]["GP_ALT_DATA_FETCHER_OPTIMIZATION"]
    gate2 = payload["records"]["GP_OVERFITTING_REMEDIATION_GATE4_20260704"]
    gate3 = payload["records"][sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY]
    for record in (gate2, payload["records"][sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY]):
        for field in ("authority_evidence_path", "original_audit_report_path"):
            source = sod.WORKSPACE / record[field]
            raw = source.read_bytes() if source.is_file() else sod._pinned_file_bytes(sod.PROVENANCE_TRUST_TAG, record[field])
            assert raw is not None, record[field]
            destination = tmp_path / record[field]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    gate1_authority = sod._git("cat-file", "blob", "9c588c18506f0d9fe9a3aebc785fbbb18df6f929")
    assert gate1_authority.returncode == 0
    assert sod._sha256(gate1_authority.stdout) == gate1["authority_evidence_sha256"]
    destination = tmp_path / gate1["authority_evidence_path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(gate1_authority.stdout)
    current_gates = sod.load_canonical_gate_map()
    current_gate2 = sod._immutable_gate_record(current_gates[gate2["original_key"]])
    pinned_gate2 = sod._immutable_gate_record(sod._pinned_gate_record(gate2["pinned_commit"], gate2["original_key"]))
    gate2["authoritative_record"] = pinned_gate2
    gate2["authoritative_record_sha256"] = sod._sha256(pinned_gate2)
    gate2["current_record_sha256"] = sod._sha256(current_gate2)
    gate2["field_drift"] = {
        field: {"pinned": pinned_gate2.get(field), "current": current_gate2.get(field)}
        for field in sorted(set(pinned_gate2) | set(current_gate2))
        if pinned_gate2.get(field) != current_gate2.get(field)
    }
    gate3 = payload["records"][sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY]
    pinned_gate3 = sod._pinned_gate_record(gate3["pinned_commit"], gate3["original_key"])
    assert pinned_gate3 is not None
    gate3["current_record_sha256"] = sod._sha256(
        sod._immutable_gate_record(current_gates[sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY])
    )
    unsigned = dict(payload)
    del unsigned["bundle_sha256"]
    payload["bundle_sha256"] = sod._sha256(sod._canonical_bundle_json(unsigned))
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(sod._canonical_bundle_json(payload))
    git_dir = sod._git("rev-parse", "--git-dir")
    assert git_dir.returncode == 0
    (tmp_path / ".git").write_text(f"gitdir: {git_dir.stdout.decode().strip()}\n", encoding="utf-8")
    monkeypatch.setattr(sod, "WORKSPACE", tmp_path)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", predecessor)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", predecessor_lock)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE", bundle)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING", Path(f"{bundle}.pending"))
    monkeypatch.setattr(sod, "_trusted_provenance_bundle", lambda raw: (True, "ok"))
    original_pinned_gate_record = sod._pinned_gate_record

    def pinned_gate_record(commit, key):
        if key == gate3["original_key"]:
            return pinned_gate3
        if key == gate2["original_key"]:
            return pinned_gate2
        return original_pinned_gate_record(commit, key)

    monkeypatch.setattr(sod, "_pinned_gate_record", pinned_gate_record)
    gate3["recorded_claim_sha256"] = sod._sha256(
        sod._immutable_gate_record(pinned_gate3)
    )
    unsigned = dict(payload)
    del unsigned["bundle_sha256"]
    payload["bundle_sha256"] = sod._sha256(sod._canonical_bundle_json(unsigned))
    bundle.write_bytes(sod._canonical_bundle_json(payload))
    monkeypatch.setattr(sod, "_gate1_original_audit_blob", lambda record: True)
    gates = {
        gate1["original_key"]: gate1["authoritative_record"],
        gate2["original_key"]: current_gates[gate2["original_key"]],
        sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY: current_gates[sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY],
    }
    assert sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY not in json.loads(predecessor.read_text(encoding="utf-8"))["records"]
    result = sod.validate_legacy_residual_provenance_retry1(gates)
    assert result == (True, "legacy residual reconciliation: 17 resolved; 1 open"), result

    payload["records"][sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY]["recorded_claim_sha256"] = "0" * 64
    unsigned = dict(payload)
    del unsigned["bundle_sha256"]
    payload["bundle_sha256"] = sod._sha256(sod._canonical_bundle_json(unsigned))
    bundle.write_bytes(sod._canonical_bundle_json(payload))
    assert not sod.validate_legacy_residual_provenance_retry1(gates)[0]


def test_retry1_recreated_trusted_tag_oid_rejected_before_signature(monkeypatch):
    pinned_oid = "a" * 40
    moved_oid = "b" * 40
    calls = []

    def git(*args):
        calls.append(args)
        if args == ("rev-parse", "--is-shallow-repository"):
            return SimpleNamespace(returncode=0, stdout=b"false\n", stderr=b"")
        if args == ("for-each-ref", "refs/replace/", "--format=%(refname)"):
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if args == ("config", "--get-regexp", r"^(core\.useReplaceRefs|refs\.replace)"):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
        if args == ("rev-parse", "--show-object-format"):
            return SimpleNamespace(returncode=0, stdout=b"sha1\n", stderr=b"")
        if args == ("cat-file", "-e", f"{sod.PROVENANCE_TRUST_TAG}^{{tag}}"):
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if args == ("rev-parse", "--verify", f"{sod.PROVENANCE_TRUST_TAG}^{{tag}}"):
            return SimpleNamespace(returncode=0, stdout=f"{moved_oid}\n".encode(), stderr=b"")
        if args == ("verify-tag", "--raw", sod.PROVENANCE_TRUST_TAG):
            return SimpleNamespace(
                returncode=0,
                stdout=f"[GNUPG:] VALIDSIG x 0 0 0 0 0 0 0 0 {sod.PROVENANCE_TRUST_FINGERPRINT}\n".encode(),
                stderr=b"",
            )
        raise AssertionError(args)

    monkeypatch.setattr(sod, "PROVENANCE_TRUST_TAG_OBJECT_OID", pinned_oid)
    monkeypatch.setattr(sod, "_git", git)
    assert sod._trusted_provenance_bundle(b"canonical") == (
        False, "retry1 provenance trusted tag object OID mismatch"
    )
    assert ("verify-tag", "--raw", sod.PROVENANCE_TRUST_TAG) not in calls


def _validsig(*fields):
    return "[GNUPG:] VALIDSIG " + " ".join(fields)


def test_validsig_accepts_field2_signer_for_11_tokens():
    status = _validsig(sod.PROVENANCE_TRUST_FINGERPRINT, "0", "0", "0", "0", "0", "0", "0", "0")
    assert len(status.split()) == 11
    assert sod._validsig_matches_trusted_fingerprint(status)


def test_validsig_accepts_field11_primary_for_12_tokens():
    status = _validsig("A" * 40, "0", "0", "0", "0", "0", "0", "0", "0", sod.PROVENANCE_TRUST_FINGERPRINT)
    assert len(status.split()) == 12
    assert sod._validsig_matches_trusted_fingerprint(status)


@pytest.mark.parametrize("status", [
    _validsig("A" * 40, "0", "0", "0", "0", "0", "0", "0", "0"),
    _validsig("a" * 40, "0", "0", "0", "0", "0", "0", "0", "0"),
    _validsig(sod.PROVENANCE_TRUST_FINGERPRINT, "0", "0", "0", "0", "0", "0", "0"),
    _validsig(sod.PROVENANCE_TRUST_FINGERPRINT, "0", "0", "0", "0", "0", "0", "0", "0") + "\n" + _validsig(sod.PROVENANCE_TRUST_FINGERPRINT, "0", "0", "0", "0", "0", "0", "0", "0"),
], ids=["wrong", "malformed", "missing", "duplicate"])
def test_validsig_rejects_wrong_missing_malformed_or_duplicate_status(status):
    assert not sod._validsig_matches_trusted_fingerprint(status)


def test_validsig_integration_accepts_exact_trusted_signed_tag(tmp_path, monkeypatch):
    gpg = r"C:\Program Files\GnuPG\bin\gpg.exe"
    if not os.path.isfile(gpg):
        pytest.skip(f"exact GnuPG binary unavailable: {gpg}")
    secret = subprocess.run(
        [gpg, "--batch", "--with-colons", "--list-secret-keys", sod.PROVENANCE_TRUST_FINGERPRINT],
        capture_output=True, text=True, check=False,
    )
    if secret.returncode or f"fpr:::::::::{sod.PROVENANCE_TRUST_FINGERPRINT}:" not in secret.stdout:
        pytest.skip(f"trusted secret key unavailable: {sod.PROVENANCE_TRUST_FINGERPRINT}")
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)
    git("init", "-q")
    git("config", "user.name", "VALIDSIG integration")
    git("config", "user.email", "validsig@example.test")
    git("config", "gpg.program", gpg)
    git("config", "user.signingkey", sod.PROVENANCE_TRUST_FINGERPRINT)
    (tmp_path / "proof").write_text("proof\n", encoding="utf-8")
    git("add", "proof")
    git("commit", "-qm", "first proof")
    original_commit_oid = git("rev-parse", "HEAD").stdout.strip()
    git("tag", "-s", "-m", "proof", "trusted-proof")
    original_tag_oid = git("rev-parse", "trusted-proof^{tag}").stdout.strip().decode()
    (tmp_path / "proof").write_text("later proof\n", encoding="utf-8")
    git("commit", "-am", "later proof", "-q")
    recreated_commit_oid = git("rev-parse", "HEAD").stdout.strip()
    git("tag", "-s", "-f", "-m", "later proof", "trusted-proof")
    recreated_tag_oid = git("rev-parse", "trusted-proof^{tag}").stdout.strip().decode()
    assert recreated_tag_oid != original_tag_oid
    assert recreated_commit_oid != original_commit_oid
    assert git("rev-parse", "trusted-proof^{commit}").stdout.strip() == recreated_commit_oid
    verified = subprocess.run(
        ["git", "verify-tag", "--raw", "trusted-proof"],
        cwd=tmp_path, capture_output=True, check=False,
    )
    if verified.returncode:
        pytest.skip("trusted GnuPG key cannot verify signed tags")
    status = (verified.stdout + verified.stderr).decode("utf-8", "replace")
    assert sod._validsig_matches_trusted_fingerprint(status)

    calls = []

    def tracked_git(*args):
        calls.append(args)
        environment = os.environ.copy()
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
        return subprocess.run(["git", *args], cwd=tmp_path, env=environment, capture_output=True, check=False)

    monkeypatch.setattr(sod, "WORKSPACE", tmp_path)
    monkeypatch.setattr(sod, "PROVENANCE_TRUST_TAG", "refs/tags/trusted-proof")
    monkeypatch.setattr(sod, "PROVENANCE_TRUST_TAG_OBJECT_OID", original_tag_oid)
    monkeypatch.setattr(sod, "_git", tracked_git)
    assert sod._trusted_provenance_bundle(b"canonical") == (
        False, "retry1 provenance trusted tag object OID mismatch"
    )
    assert ("verify-tag", "--raw", "refs/tags/trusted-proof") not in calls

    calls.clear()
    monkeypatch.setattr(sod, "PROVENANCE_TRUST_TAG_OBJECT_OID", recreated_tag_oid)
    assert sod._trusted_provenance_bundle(b"canonical") == (
        False, "retry1 provenance bundle does not match trusted tag"
    )
    assert ("verify-tag", "--raw", "refs/tags/trusted-proof") in calls


def test_closed_authority_report_parser_rejects_swapped_tuple(tmp_path):
    report = tmp_path / "authority.md"
    key = "GP_ALT_DATA_FETCHER_OPTIMIZATION"
    session = "l3_role21_provenance_reaudit_gp_alt_data_fetcher_20260730"
    report.write_bytes(
        f"- Gate: {key}\n- Role: 21 code-reviewer\n- L3 session ID/key: {session}\n[APPROVED]\n".encode("utf-8")
    )
    assert sod._closed_report_tuple(report, key, 21, session)
    assert not sod._closed_report_tuple(report, "GP_OVERFITTING_REMEDIATION_GATE4_20260704", 21, session)


def test_gate4_sidecar_authority_requires_exact_approved_tuple(tmp_path):
    report = tmp_path / "authority.md"
    session = "l2_role9_gate4_original_provenance_sidecar_fix1_20260731"
    report.write_bytes(
        ("- Verdict: [APPROVED]\n"
         "- Gate: `gate4_original_provenance_sidecar_fix1_20260731`\n"
         f"- L2 session: `{session}`\n"
         "- Roles: PASS (`9 backend-engineer != 21 code-reviewer`)\n"
         "[APPROVED]\n").encode("utf-8")
    )
    assert sod._closed_gate4_sidecar_authority(report, session)
    assert not sod._closed_gate4_sidecar_authority(report, "wrong")


@pytest.mark.parametrize("mutation", [
    lambda payload: payload["records"].pop("GP_ALT_DATA_FETCHER_OPTIMIZATION"),
    lambda payload: payload["records"]["GP_ALT_DATA_FETCHER_OPTIMIZATION"].update(extra=True),
    lambda payload: payload.update(supersedes_path=".ly_state/session/../escape.json"),
    lambda payload: payload["records"]["GP_OVERFITTING_REMEDIATION_GATE4_20260704"].update(pinned_commit="0" * 40),
])
def test_retry1_bundle_tamper_fails_closed(tmp_path, monkeypatch, mutation):
    source = sod.LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE
    target = tmp_path / "bundle.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    mutation(payload)
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING", Path(f"{target}.pending"))
    assert not sod.validate_legacy_residual_provenance_retry1()[0]


def test_retry1_bundle_rejects_rehashed_recorded_claim_tamper(tmp_path, monkeypatch):
    source = sod.LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE
    target = tmp_path / "bundle.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["records"]["GP_ALT_DATA_FETCHER_OPTIMIZATION"]["recorded_claim_sha256"] = "0" * 64
    unsigned = dict(payload)
    del unsigned["bundle_sha256"]
    payload["bundle_sha256"] = sod._sha256(sod._canonical_bundle_json(unsigned))
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING", Path(f"{target}.pending"))
    assert not sod.validate_legacy_residual_provenance_retry1()[0]


def test_retry1_pending_residue_and_publish_collision_fail_closed(tmp_path, monkeypatch):
    target = tmp_path / "bundle.json"
    pending = Path(f"{target}.pending")
    pending.write_text("partial", encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING", pending)
    assert "pending residue" in sod.validate_legacy_residual_provenance_retry1()[1]
    with pytest.raises(FileExistsError):
        sod.publish_legacy_residual_provenance_retry1({})


def _gate4_provenance_fixture(tmp_path, monkeypatch):
    source = sod.LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE
    payload = json.loads(source.read_text(encoding="utf-8"))
    target = tmp_path / "gate4.json"
    lock = target.with_suffix(".sha256")
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_GATE4_ORIGINAL_PROVENANCE_LOCK", lock)
    return payload, target, lock


def test_gate4_original_provenance_validates_pinned_authority(tmp_path, monkeypatch):
    _, _, _ = _gate4_provenance_fixture(tmp_path, monkeypatch)
    assert sod.validate_legacy_gate4_original_provenance() == (True, "Gate4 original provenance valid")


def test_gate4_original_provenance_rejects_joint_predecessor_lock_sidecar_replacement(tmp_path, monkeypatch):
    payload, target, lock = _gate4_provenance_fixture(tmp_path, monkeypatch)
    predecessor = tmp_path / "predecessor.json"
    predecessor_lock = predecessor.with_suffix(".sha256")
    raw = b'{"records":{"GP_OVERFITTING_REMEDIATION_GATE4_20260704":{"original_gate_record_sha256":"0"}}}'
    replacement_hash = hashlib.sha256(raw).hexdigest()
    predecessor.write_bytes(raw)
    predecessor_lock.write_text(replacement_hash, encoding="utf-8")
    payload["predecessor_raw_sha256"] = replacement_hash
    payload["predecessor_lock_value"] = replacement_hash
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", predecessor)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", predecessor_lock)
    assert sod.validate_legacy_gate4_original_provenance() == (
        False, "Gate4 original provenance predecessor drift"
    )


@pytest.mark.parametrize("published_at", ["2026-07-30T23:50:13+00:00", "not-a-timestamp", "2999-01-01T00:00:00Z"])
def test_gate4_original_provenance_rejects_malformed_or_future_timestamp(tmp_path, monkeypatch, published_at):
    payload, target, lock = _gate4_provenance_fixture(tmp_path, monkeypatch)
    payload["published_at"] = published_at
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    assert not sod.validate_legacy_gate4_original_provenance()[0]


@pytest.mark.parametrize("field,value", [
    ("original_commit", "0" * 40),
    ("supersedes_claim_sha256", "0" * 64),
    ("original_audit_report_sha256", "0" * 64),
    ("current_gate_record_sha256", "0" * 64),
])
def test_gate4_original_provenance_rejects_rehashed_authority_tamper(tmp_path, monkeypatch, field, value):
    payload, target, lock = _gate4_provenance_fixture(tmp_path, monkeypatch)
    payload[field] = value
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    assert not sod.validate_legacy_gate4_original_provenance()[0]


def test_gate4_original_provenance_rejects_partial_or_invalid_without_fallback(tmp_path, monkeypatch):
    _, target, lock = _gate4_provenance_fixture(tmp_path, monkeypatch)
    lock.unlink()
    assert sod.validate_legacy_gate4_original_provenance() == (
        False, "Gate4 original provenance sidecar and lock are required"
    )
    target.write_bytes(sod._canonical_gate4_provenance_json({}))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    assert "schema invalid" in sod.validate_legacy_gate4_original_provenance()[1]


def test_gate4_original_provenance_publisher_never_clobbers(tmp_path, monkeypatch):
    _, target, _ = _gate4_provenance_fixture(tmp_path, monkeypatch)
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        sod.publish_legacy_gate4_original_provenance({})
    assert target.read_bytes() == before


def test_gate3_original_provenance_validates_pinned_authority():
    assert sod.validate_legacy_gate3_original_provenance() == (True, "Gate3 original provenance valid")


def test_gate3_original_provenance_rejects_authority_hash_drift(tmp_path, monkeypatch):
    target = tmp_path / "gate3.json"
    lock = target.with_suffix(".sha256")
    payload = json.loads(sod.LEGACY_GATE3_ORIGINAL_PROVENANCE_FILE.read_text(encoding="utf-8"))
    payload["authority_evidence_sha256"] = "0" * 64
    target.write_bytes(sod._canonical_gate4_provenance_json(payload))
    lock.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    monkeypatch.setattr(sod, "LEGACY_GATE3_ORIGINAL_PROVENANCE_FILE", target)
    monkeypatch.setattr(sod, "LEGACY_GATE3_ORIGINAL_PROVENANCE_LOCK", lock)
    assert not sod.validate_legacy_gate3_original_provenance()[0]
