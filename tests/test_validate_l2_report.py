from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.validate_l2_report as validator

SESSION = "l2_role11_anti_drip_validator_20260907"
GATE = "ANTI_DRIP_PIPELINE_HARDENING_20260907"
CONTRACT_REL = f".ly_state/session/anti_drip_contract_{SESSION}.json"
AUDIT_REL = ".ly_state/session/audit_reports/role21_anti_drip_pipeline_hardening_20260907.md"
NODE = "tests/test_probe.py::test_regression"
FAULT_NODE = "tests/test_probe.py::test_fault_injection"
SKILLS = ("deployment-procedures", "server-management", "clean-code", "testing-patterns", "systematic-debugging")


def canonical(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def contract(mode="remediation"):
    source = {"path": AUDIT_REL, "sha256": "0" * 64, "verdict": "NEEDS_FIX", "timestamp": "2026-09-06T20:00:00+00:00", "cycle": 1}
    return {
        "schema_version": "anti-drip-contract/v1", "contract_type": "ANTI_DRIP_PIPELINE_HARDENING",
        "session_id": SESSION, "gate_name": GATE, "mode": mode, "generated_at": "2026-09-07T00:00:00Z",
        "source_audit": source if mode == "remediation" else None,
        "required_findings": [{"finding_id": "F-004", "severity": "high", "title": "Backup rollback leaks plaintext", "probe_strings": ["BACKUP_LEAK=True"]}] if mode == "remediation" else [],
        "passed_dimensions": [], "failed_dimensions": [{"dimension": 16, "name": "Secret redaction"}] if mode == "remediation" else [],
        "directive": {"version": "codex-anti-drip-6/v1", "points": [
            {"id": key, "requirement": value} for key, value in validator.EXPECTED_ANTI_DRIP_DIRECTIVE_POINTS
        ]},
    }


def sweep(digest, source_sha):
    finding = {
        "finding_id": "F-004", "root_cause": "Rollback retained a plaintext backup after replacement failure.",
        "probe_strings": ["BACKUP_LEAK=True"], "searches": [{
            "search_regex": "BACKUP_LEAK=True|backup", "scanned_paths": ["scripts/validate_l2_report.py"],
            "total_matches": 1, "changed_matches": 1, "non_actionable_matches": 0,
            "non_actionable_justifications": [], "unresolved_matches": 0,
        }], "test_node_ids": [NODE, FAULT_NODE], "fault_injection_test_node_ids": [FAULT_NODE], "unresolved_matches": 0,
    }
    return {"schema_version": "anti-drip-sweep/v1", "session_id": SESSION, "gate_name": GATE,
            "mode": "remediation", "contract_path": CONTRACT_REL, "contract_sha256": digest,
            "source_audit_path": AUDIT_REL, "source_audit_sha256": source_sha,
            "finding_sweeps": [finding], "pytest_node_ids": [NODE, FAULT_NODE],
            "fault_injection_test_node_ids": [FAULT_NODE], "unresolved_matches": 0}


def report(mode, digest, payload=None):
    skill_lines = "\n".join(f"- `.agents/skills/{name}/SKILL.md`" for name in SKILLS)
    common = f"""# L2 Implementation Report

- **Role**: 11 devops-engineer - OpenCode L2 Implementation
- **Gate**: `{GATE}`
- **Session**: `{SESSION}`
- **Date**: `2026-09-07`
- **Anti-Drip Mode**: `{mode}`
- **Anti-Drip Contract**: `{CONTRACT_REL}`
- **Anti-Drip Contract SHA-256**: `{digest}`
- **Subagent Model**: `9router/bzl/qwen3.7-flash`

## Summary

Implemented anti-drip validation.

## Repo-Local Files Read

- `.agents/agent/devops-engineer.md`
{skill_lines}

## Changes Made

- `scripts/validate_l2_report.py`: hardened validation.

## Verification

- scoped tests passed.

"""
    if payload is not None:
        common += "## Root-Cause Architectural Sweep\n\n```json\n" + json.dumps(payload, indent=2) + "\n```\n\n"
    lines = "\n".join(f"- `{path}`: not read; {validator.FORBIDDEN_SUFFIX}" for path in validator.FORBIDDEN_PATHS)
    return common + f"## Forbidden Path Scan\n\n{lines}\n"


@pytest.fixture
def case(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    session = tmp_path / ".ly_state/session"
    audit = tmp_path / AUDIT_REL
    audit.parent.mkdir(parents=True)
    audit.write_text("# source audit\n[NEEDS_FIX]\n", encoding="utf-8")
    test = tmp_path / "tests/test_probe.py"
    test.parent.mkdir()
    test.write_text("def test_regression():\n    assert True\n\ndef test_fault_injection():\n    assert True\n", encoding="utf-8")
    payload = contract()
    payload["source_audit"]["sha256"] = hashlib.sha256(audit.read_bytes()).hexdigest()
    raw = canonical(payload)
    digest = hashlib.sha256(raw).hexdigest()
    contract_path = tmp_path / CONTRACT_REL
    contract_path.write_bytes(raw)
    contract_path.with_suffix(".sha256").write_bytes(f"{digest}  {contract_path.name}\n".encode("ascii"))
    (session / f"prompt_{SESSION}.txt").write_text(validator._canonical_prompt_block(SESSION, payload, digest) + "\n", encoding="utf-8", newline="\n")
    metadata = json.dumps({"session_id": SESSION, "role_id": 11, "role_name": "devops-engineer", "subagent_model": "9router/bzl/qwen3.7-flash", "model": "9router/cx/gpt-6-luna"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    (session / f"l2_metadata_{SESSION}.json").write_bytes(metadata)
    (session / f"l2_metadata_{SESSION}.json.sha256").write_bytes(f"{hashlib.sha256(metadata).hexdigest()}  l2_metadata_{SESSION}.json\n".encode("ascii"))
    sweep_payload = sweep(digest, payload["source_audit"]["sha256"])
    report_path = session / f"{SESSION}.md"
    report_path.write_text(report("remediation", digest, sweep_payload), encoding="utf-8", newline="\n")
    return {"root": tmp_path, "contract": payload, "digest": digest, "sweep": sweep_payload, "report": report_path}


def validate(case):
    return validator.validate_anti_drip_report(SESSION, case["report"].read_text(encoding="utf-8"), case["root"], collect_timeout_seconds=20)


def rewrite_report(case, payload):
    case["report"].write_text(report("remediation", case["digest"], payload), encoding="utf-8", newline="\n")


def test_valid_remediation_collects_real_pytest_nodes(case):
    result = validate(case)
    assert result == ("remediation", []), result


def test_valid_baseline_has_no_sweep(case):
    payload = contract("baseline")
    raw = canonical(payload)
    digest = hashlib.sha256(raw).hexdigest()
    path = case["root"] / CONTRACT_REL
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_bytes(f"{digest}  {path.name}\n".encode("ascii"))
    (case["root"] / f".ly_state/session/prompt_{SESSION}.txt").write_text(validator._canonical_prompt_block(SESSION, payload, digest) + "\n", encoding="utf-8", newline="\n")
    case["report"].write_text(report("baseline", digest), encoding="utf-8", newline="\n")
    assert validate(case) == ("baseline", [])


def _assert_dimension_contract_rejected(case, mutation):
    payload = copy.deepcopy(case["contract"])
    mutation(payload)
    raw = canonical(payload)
    path = case["root"] / CONTRACT_REL
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_bytes(f"{hashlib.sha256(raw).hexdigest()}  {path.name}\n".encode("ascii"))
    mode, errors = validate(case)
    assert mode is None
    assert any("E304" in error for error in errors)


def test_dimension_ids_reject_duplicates(case):
    _assert_dimension_contract_rejected(case, lambda payload: payload["passed_dimensions"].extend([
        {"dimension": 13, "name": "Schema drift"}, {"dimension": 13, "name": "Schema drift again"}
    ]))


def test_dimension_ids_reject_overlap(case):
    _assert_dimension_contract_rejected(case, lambda payload: payload["passed_dimensions"].append(
        {"dimension": 16, "name": "Secret redaction"}
    ))


@pytest.mark.parametrize("target", ["contract", "sidecar", "prompt", "report", "sweep"])
def test_digest_binding_fails_closed(case, target):
    if target == "contract":
        (case["root"] / CONTRACT_REL).write_bytes((case["root"] / CONTRACT_REL).read_bytes() + b" ")
    elif target == "sidecar":
        (case["root"] / CONTRACT_REL).with_suffix(".sha256").write_text("0" * 64 + "  wrong.json\n", encoding="ascii")
    elif target == "prompt":
        path = case["root"] / f".ly_state/session/prompt_{SESSION}.txt"
        path.write_text(path.read_text(encoding="utf-8").replace(case["digest"], "0" * 64), encoding="utf-8")
    elif target == "report":
        case["report"].write_text(case["report"].read_text(encoding="utf-8").replace(case["digest"], "0" * 64, 1), encoding="utf-8")
    else:
        payload = copy.deepcopy(case["sweep"]); payload["contract_sha256"] = "0" * 64; rewrite_report(case, payload)
    assert validate(case)[0] is None


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p["finding_sweeps"].append(copy.deepcopy(p["finding_sweeps"][0])), "E501"),
    (lambda p: p["finding_sweeps"][0].update(probe_strings=[]), "E502"),
    (lambda p: p["finding_sweeps"][0]["searches"][0].update(search_regex="(a+)+$"), "E503"),
    (lambda p: p["finding_sweeps"][0]["searches"][0].update(unresolved_matches=1, total_matches=2), "E504"),
    (lambda p: p["finding_sweeps"][0].update(fault_injection_test_node_ids=[]), "E602"),
    (lambda p: p.update(pytest_node_ids=["tests/test_probe.py::missing"]), "E601"),
])
def test_finding_coverage_adversarial_failures(case, mutation, code):
    payload = copy.deepcopy(case["sweep"])
    mutation(payload)
    rewrite_report(case, payload)
    mode, errors = validate(case)
    assert mode is None
    assert any(f"[{code}]" in error for error in errors)


@pytest.mark.parametrize("node", ["../../evil.py::test_x", "tests/test_probe.py::test_x;whoami", "C:/evil.py::test_x"])
def test_pytest_node_id_rejects_traversal_and_injection(case, node):
    assert "E603" in validator._validate_pytest_node_id(node, case["root"])


def test_pytest_collection_timeout_and_missing_node(case):
    ok, errors = validator._collect_pytest_node_ids(["tests/test_probe.py::missing"], case["root"], 20)
    assert not ok and any("E603" in error for error in errors)
    ok, errors = validator._collect_pytest_node_ids([NODE], case["root"], 0)
    assert not ok and any("E603" in error for error in errors)


def test_duplicate_json_keys_and_nonfinite_rejected():
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        with pytest.raises(ValueError):
            validator._strict_json(text)


def test_report_heading_duplicate_and_forbidden_wording(case):
    content = case["report"].read_text(encoding="utf-8").replace("## Verification", "## Verification\n\n## Verification")
    case["report"].write_text(content, encoding="utf-8")
    assert any("E203" in error for error in validate(case)[1])
    case["report"].write_text(report("remediation", case["digest"], case["sweep"]).replace(validator.FORBIDDEN_SUFFIX, "trusted source", 1), encoding="utf-8")
    assert any("E703" in error or "E704" in error for error in validate(case)[1])


def test_main_usage_is_fatal_exit_two():
    assert validator.main([]) == 2


def test_main_options_parsing_and_validation(case):
    # Valid options
    assert validator.main([SESSION, "11", "devops-engineer", "--collect-timeout", "30"], repo_root=case["root"]) == 0
    assert validator.main([SESSION, "11", "devops-engineer", "--timeout=45"], repo_root=case["root"]) == 0

    # Missing option value
    assert validator.main([SESSION, "11", "devops-engineer", "--collect-timeout"], repo_root=case["root"]) == 2

    # Invalid option value (non-integer or negative)
    assert validator.main([SESSION, "11", "devops-engineer", "--collect-timeout", "abc"], repo_root=case["root"]) == 2
    assert validator.main([SESSION, "11", "devops-engineer", "--timeout=-5"], repo_root=case["root"]) == 2

    # Unrecognized option
    assert validator.main([SESSION, "11", "devops-engineer", "--unrecognized"], repo_root=case["root"]) == 2


def test_typesafe_pre_audit_rejects_bool_nan_and_infinity_confidence():
    base = {"schema_version": "1.0", "gate": "G", "session_id": "s", "role": "devops-engineer",
            "scope": ["tests/test_probe.py"], "fingerprints": {"tests/test_probe.py": "a" * 64}, "verifier": {"exit_code": 0},
            "ast_findings": [], "judgments": [], "scores": [],
            "routing": {"routing": "JUDGE", "reason_code": "CLEAN", "evidence_refs": [], "confidence": 1.0},
            "generated_at": "2026-09-22T00:00:00+00:00"}
    for value in (True, float("nan"), float("inf"), -0.1, 1.1):
        payload = copy.deepcopy(base)
        payload["routing"]["confidence"] = value
        with pytest.raises(ValueError):
            validator.validate_pre_audit_schema(payload)


def test_pre_audit_routing_priority_and_atomic_sidecar(tmp_path):
    assert validator.resolve_routing(pytest_exit=1, cheat_certain=False, uncertain_findings=True)["routing"] == "BLOCK"
    assert validator.resolve_routing(pytest_exit=0, cheat_certain=True, uncertain_findings=False)["routing"] == "BLOCK"
    assert validator.resolve_routing(pytest_exit=0, cheat_certain=False, uncertain_findings=True)["routing"] == "PROBE"
    payload = {"schema_version": "1.0", "gate": "G", "session_id": "s", "role": "devops-engineer",
               "scope": ["tests/test_probe.py"], "fingerprints": {"tests/test_probe.py": "a" * 64}, "verifier": {"exit_code": 0},
               "ast_findings": [], "judgments": [], "scores": [],
               "routing": {"routing": "JUDGE", "reason_code": "CLEAN", "evidence_refs": [], "confidence": 1.0},
               "generated_at": "2026-09-22T00:00:00+00:00"}
    artifact, sidecar = validator.write_atomic_pre_audit(payload, tmp_path, "s")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert sidecar.read_text(encoding="ascii") == f"{digest}  {artifact.name}\n"


def test_pre_audit_publication_rolls_back_pair_on_sidecar_failure(tmp_path, monkeypatch):
    payload = {"schema_version": "1.0", "gate": "G", "session_id": "s", "role": "r",
               "scope": ["tests/test_x.py"], "fingerprints": {"tests/test_x.py": "a" * 64},
               "verifier": {"exit_code": 0}, "ast_findings": [], "judgments": [], "scores": [],
               "routing": {"routing": "JUDGE", "reason_code": "CLEAN", "evidence_refs": [], "confidence": 1.0},
               "generated_at": "2026-09-22T00:00:00+00:00"}
    real_replace = validator.os.replace
    def fail_sidecar(source, target):
        if str(target).endswith(".sha256"):
            raise OSError("disk full")
        return real_replace(source, target)
    monkeypatch.setattr(validator.os, "replace", fail_sidecar)
    with pytest.raises(OSError, match="disk full"):
        validator.write_atomic_pre_audit(payload, tmp_path, "s")
    assert not (tmp_path / "pre_audit_s.json").exists()
    assert not (tmp_path / "pre_audit_s.sha256").exists()


def test_pre_audit_without_tests_fails_closed(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    code, metadata = validator.run_pre_audit("s", "r", "G", ["module.py"], tmp_path)
    assert code == 1
    artifact = json.loads((tmp_path / metadata["PRE_AUDIT_PATH"]).read_text(encoding="utf-8"))
    assert artifact["verifier"]["exit_code"] != 0
    assert artifact["routing"]["routing"] == "BLOCK"


def test_pre_audit_flag_still_requires_l2_report(tmp_path, monkeypatch):
    monkeypatch.setattr(validator, "run_pre_audit", lambda *args: (0, {"PRE_AUDIT_PATH": "x", "PRE_AUDIT_SHA256": "a" * 64}))
    assert validator.main(["l2_role11_missing_20260922", "11", "devops-engineer", "--pre-audit", "--gate", "G", "--scope", "module.py"], repo_root=tmp_path) == 1


# === Jev Integration Tests ===


def test_jev_graceful_degradation_import_error(monkeypatch):
    """run_jev_judgments returns None when typesafe-sdk is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "typesafe_sdk":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    result = validator.run_jev_judgments("report", "test output", ["file.py"])
    assert result is None


def test_jev_api_timeout_graceful(monkeypatch):
    """run_jev_judgments returns None when API raises exception."""
    def mock_system_one(*args, **kwargs):
        raise TimeoutError("mocked timeout")

    class MockClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        system_one = mock_system_one

    monkeypatch.setattr("typesafe_sdk.TypeSafeClient", MockClient, raising=False)
    # Force re-import path through the try block
    result = validator.run_jev_judgments("report", "test output", ["file.py"])
    # Result is None because the real TypeSafeClient will raise or our mock will
    assert result is None


def test_jev_fabricated_evidence_block():
    """Jev fabricated_evidence noul > 0.7 escalates to BLOCK."""
    base = {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0}
    jev = {
        "genuine_testing": {"noul": 0.9},
        "fabricated_evidence": {"noul": 0.85},
        "test_quality": {"score": 2.0, "confidence": 0.9},
    }
    routing, judgments, scores = validator._merge_jev_into_routing(base, jev)
    assert routing["routing"] == "BLOCK"
    assert routing["reason_code"] == "JEV_FABRICATED_EVIDENCE"
    assert len(judgments) == 2
    assert len(scores) == 1


def test_jev_low_genuine_testing_probe():
    """Jev genuine_testing noul < 0.3 escalates JUDGE to PROBE."""
    base = {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0}
    jev = {
        "genuine_testing": {"noul": 0.15},
        "fabricated_evidence": {"noul": 0.1},
        "test_quality": {"score": 1.5, "confidence": 0.8},
    }
    routing, judgments, scores = validator._merge_jev_into_routing(base, jev)
    assert routing["routing"] == "PROBE"
    assert routing["reason_code"] == "JEV_SEMANTIC_CONCERN"
    assert any("genuine_testing" in r for r in routing["evidence_refs"])


def test_jev_all_clean_judge():
    """Jev all-clean keeps JUDGE routing."""
    base = {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0}
    jev = {
        "genuine_testing": {"noul": 0.92},
        "fabricated_evidence": {"noul": 0.05},
        "test_quality": {"score": 2.0, "confidence": 0.95},
    }
    routing, judgments, scores = validator._merge_jev_into_routing(base, jev)
    assert routing["routing"] == "JUDGE"
    assert routing["reason_code"] == "CLEAN_PASS"


def test_jev_results_in_pre_audit_artifact(tmp_path):
    """Pre-audit artifact contains jev_available and jev_raw_response fields."""
    jev_data = {
        "genuine_testing": {"noul": 0.8},
        "fabricated_evidence": {"noul": 0.1},
        "test_quality": {"score": 1.5, "confidence": 0.7},
    }
    routing, jev_judgments, jev_scores = validator._merge_jev_into_routing(
        {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0},
        jev_data,
    )
    payload = {
        "schema_version": "1.0", "gate": "G", "session_id": "s", "role": "r",
         "scope": ["tests/test_x.py"], "fingerprints": {"tests/test_x.py": "a" * 64}, "verifier": {"exit_code": 0},
        "ast_findings": [], "judgments": jev_judgments, "scores": jev_scores,
        "routing": routing, "generated_at": "2026-09-22T00:00:00+00:00",
        "jev_available": True, "jev_raw_response": jev_data,
    }
    # Schema validation should pass with Jev fields
    validator.validate_pre_audit_schema(payload)
    artifact, _ = validator.write_atomic_pre_audit(payload, tmp_path, "s")
    loaded = json.loads(artifact.read_bytes())
    assert loaded["jev_available"] is True
    assert loaded["jev_raw_response"]["genuine_testing"]["noul"] == 0.8
    assert not artifact.with_suffix(".tmp").exists()
