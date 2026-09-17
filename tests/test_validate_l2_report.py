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
