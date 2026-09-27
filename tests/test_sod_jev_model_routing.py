import hashlib
import os
import time
import sys
import types
from datetime import datetime
# Regression coverage: decision binding, atomic publication, pre-audit, throttling, credential safety.
import json
from pathlib import Path

import pytest
from argparse import Namespace

from scripts.jev_model_router import (
    L2_LEAD_ALLOWLIST,
    L3_LEAD_ALLOWLIST,
    atomic_publish_decision,
    escape_xml_data,
    evaluate_model_decision,
    load_decision,
    validate_standalone_verdict,
)
import scripts.sod_pipeline as sod_pipeline
import scripts.validate_l2_report as validate_l2_report


def test_baseline_routes_by_role_and_publishes_digest(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(role="l2", risk="low", gate="G", session_id="S", decision_path=path)
    assert envelope["lead_model"] == L2_LEAD_ALLOWLIST[1]
    assert envelope["decision_digest"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_decision(
        path,
        envelope["decision_digest"],
        expected_role="l2",
        expected_gate="G",
        expected_session_id="S",
        expected_risk="low",
    )["schema_version"] == "2.0"


def test_w0_inventory_binds_sources_consumers_and_market_release():
    import pyarrow.parquet as pq

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / ".ly_state/session/jev_deep_integration_20260926/W0/input_manifest.json").read_text(encoding="utf-8"))
    gates = json.loads((root / ".ly_state/session/phase_gates.json").read_text(encoding="utf-8"))
    assert manifest["repo_commit"] == "74a3b507776b78cf361e8f7f0f4ac0c7efe9e3ae"
    assert manifest["gate_recorded_in_phase_gates"] is (manifest["gate"] in gates)
    if manifest["gate_recorded_in_phase_gates"]:
        receipt = gates[manifest["gate"]]
        assert receipt["final_verdict"] == "[APPROVED]"
        assert receipt["l2_session_id"] == "l2_role6_jev_deep_integration_w0_inventory_20260927"
        assert (root / receipt["audit_report_path"]).is_file()
    assert all(gates[name]["final_verdict"] == "[APPROVED]" for name in manifest["recorded_approved_gates"])
    graph = manifest["graph_evidence"]
    assert graph["sha256"] == "45679feb71de68a995e8581410f17338ba30bdc504fa710dc0a0a0dcb7da72ad"
    assert hashlib.sha256((root / graph["path"]).read_bytes()).hexdigest() == graph["sha256"]
    contract = root / ".ly_state/session/anti_drip_contract_l2_role6_jev_deep_integration_w0_inventory_20260927.json"
    assert hashlib.sha256(contract.read_bytes()).hexdigest() == "44bac89575abe3738712cd5742f710ecbb222163a4785a43b87b71537e33909b"
    assert json.loads(contract.read_text(encoding="utf-8"))["required_findings"] == []
    for entry in (*manifest["sources"], *manifest["consumers"], *manifest["datasets"]):
        path = Path(entry["path"])
        assert not path.is_absolute() and ".." not in path.parts and (root / path).is_file()
    consumers = {entry["path"]: entry["call"] for entry in manifest["consumers"]}
    assert "classify_jev(domain=copilot-router-v1)" in consumers["src/omega/data/smart_llm_router.py"]
    assert "evaluate_model_decision" in consumers["scripts/sod_pipeline.py"]
    release, canonical = manifest["datasets"][:2]
    assert hashlib.sha256((root / release["path"]).read_bytes()).hexdigest() == release["sha256"]
    assert pq.ParquetFile(root / release["path"]).metadata.num_rows == release["rows"]
    assert hashlib.sha256((root / canonical["path"]).read_bytes()).hexdigest() == canonical["current_sha256"]
    assert canonical["current_sha256"] != canonical["release_manifest_canonical_sha256"]
    for item in manifest["datasets"][2:8]:
        assert pq.ParquetFile(root / item["path"]).metadata.num_rows == item["rows"]
    checkpoint = manifest["datasets"][-1]
    assert json.loads((root / checkpoint["path"]).read_text(encoding="utf-8"))["symbols_count"] == checkpoint["symbols_count_manifest"]
    assert json.loads((root / checkpoint["routing_plan"]).read_text(encoding="utf-8"))["llm_mode"] == "off"


@pytest.mark.parametrize("shard", ["manifest.json", "quant_records.json", "routing_plan.json", "evaluation_records.json"])
def test_corrupted_hybrid_checkpoint_shards_fail_closed(tmp_path, shard):
    from scripts.run_hybrid_fundamental import compute_run_contract_hash, parse_cli_args, run_pipeline

    output = tmp_path / "out.parquet"
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    args = parse_cli_args([
        "--decision-cutoff", "2026-06-15T15:00:00+07:00",
        "--knowledge-cutoff", "2026-06-15T09:00:00+07:00",
        "--symbols", "VNM", "--output", str(output),
        "--checkpoint-dir", str(checkpoint), "--llm-mode", "off", "--resume",
    ])
    (checkpoint / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "run_contract_hash": compute_run_contract_hash(vars(args), ["VNM"]),
        "status": "in_progress",
    }), encoding="utf-8")
    (checkpoint / shard).write_text("{truncated", encoding="utf-8")
    code, result, summary = run_pipeline(args)
    assert code == 6 and result is None and summary["status"] == "resume_manifest_corrupted"
    assert not output.exists()


def test_context_bound_decision_rejects_replay(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(role="l3", risk="high", gate="G", session_id="S", decision_path=path)
    for kwargs in (
        {"expected_role": "l2"},
        {"expected_gate": "OTHER"},
        {"expected_session_id": "OTHER"},
        {"expected_risk": "low"},
    ):
        with pytest.raises(ValueError, match="context mismatch"):
            load_decision(path, envelope["decision_digest"], **kwargs)


def test_schema_drift_fails_closed_after_digest_recomputed(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(role="l2", risk="low", decision_path=path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("role")
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_extra_decision_field_fails_closed_even_with_matching_digest(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(role="l2", risk="low", response={}, decision_path=path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected_authority"] = "approve"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_digest_tamper_fails_closed(tmp_path):
    path, digest = atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
    path.write_text('{"schema_version":"2.0","tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_decision(path, digest)


def test_nonfinite_and_boolean_inputs_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        evaluate_model_decision(role="l2", risk="low", cycle=True)
    with pytest.raises(ValueError):
        json.loads('{"x":NaN}', parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def test_w0_zero_reference_price_does_not_divide():
    from omega.data.vci_direct import validate_price_bounds

    assert validate_price_bounds(27_000, 0, "HOSE") is True
    assert validate_price_bounds(27_000, -1, "HOSE") is True
    assert validate_price_bounds(float("inf"), 0, "HOSE") is False


@pytest.mark.parametrize("cycle", [float("nan"), float("inf"), "1", [], True])
def test_malformed_cycle_rejected_before_publication(tmp_path, cycle):
    path = tmp_path / "decision.json"
    with pytest.raises(ValueError, match="invalid routing inputs"):
        evaluate_model_decision(role="l2", risk="low", cycle=cycle, response={}, decision_path=path)
    assert not path.exists()


@pytest.mark.parametrize("cycle", [0, -1, 4])
def test_out_of_bounds_cycle_rejected_before_publication(tmp_path, cycle):
    path = tmp_path / "decision.json"
    with pytest.raises(RuntimeError, match="MAX_REMEDIATIONS_EXCEEDED"):
        evaluate_model_decision(role="l2", risk="low", cycle=cycle, response={}, decision_path=path)
    assert not path.exists()


def test_high_finding_escalates_l2_and_l3(tmp_path):
    report = tmp_path / "audit.md"
    report.write_text("[NEEDS_FIX] F-001 HIGH", encoding="utf-8")
    assert evaluate_model_decision(role="l2", risk="high", predecessor_report=report)["lead_model"] == L2_LEAD_ALLOWLIST[0]
    assert evaluate_model_decision(role="l3", risk="high", predecessor_report=report)["lead_model"] == L3_LEAD_ALLOWLIST[0]


@pytest.mark.parametrize("role,choices", [("l2", L2_LEAD_ALLOWLIST), ("l3", L3_LEAD_ALLOWLIST)])
def test_high_finding_prevents_provider_downgrade(tmp_path, role, choices):
    report = tmp_path / "audit.md"
    report.write_text("[NEEDS_FIX] F-001 HIGH", encoding="utf-8")
    envelope = evaluate_model_decision(
        role=role, risk="high", predecessor_report=report,
        response={"lead_model": choices[1]}, decision_path=tmp_path / "decision.json",
    )
    assert envelope["escalated"] is True
    assert envelope["lead_model"] == choices[0]
    assert load_decision(tmp_path / "decision.json", envelope["decision_digest"])["lead_model"] == choices[0]


def test_l2_and_l3_decisions_are_distinct_and_context_bound(tmp_path):
    l2_path = tmp_path / "l2.json"
    l3_path = tmp_path / "l3.json"
    l2 = evaluate_model_decision(role="l2", risk="high", gate="G", session_id="L2", decision_path=l2_path)
    l3 = evaluate_model_decision(role="l3", risk="high", gate="G", session_id="L3", decision_path=l3_path)
    assert l2_path != l3_path
    assert l2["decision_digest"] != l3["decision_digest"]
    assert load_decision(l3_path, l3["decision_digest"], expected_role="l3", expected_gate="G", expected_session_id="L3", expected_risk="high")["role"] == "l3"


def test_pipeline_jev_dispatches_distinct_bound_decision_paths(monkeypatch):
    args = Namespace(
        l2_role="devops-engineer", l3_role="code-reviewer", gate="GATE", slug="slug",
        scope="scripts/sod_pipeline.py", risk="high", model=None, subagent_model=None,
        dry_run=False, graph_evidence=None, model_decision_path="l2.json",
        model_decision_digest="a" * 64, pre_audit_path=None, pre_audit_sha256=None,
    )
    captured = []
    monkeypatch.setattr(sod_pipeline, "capture", lambda command: (captured.append(command) or (0, "---COMMAND---\ncmd")))
    monkeypatch.setattr(sod_pipeline, "parse_dispatch_output", lambda output, required: {key: "value" for key in required})
    sod_pipeline._dispatch_l2(args, "task")
    assert "l2.json" in captured[-1]
    args.model_decision_path = "l3.json"
    args.model_decision_digest = "b" * 64
    sod_pipeline._dispatch_l3(args, "l2_session")
    assert "l3.json" in captured[-1]


def test_sod_pipeline_imports_standalone_verdict_validator():
    assert sod_pipeline.validate_standalone_verdict("[APPROVED]") == "APPROVED"


def test_standalone_verdict_rejects_conflicts_and_prose():
    assert validate_standalone_verdict("[APPROVED]\n") == "APPROVED"
    assert validate_standalone_verdict(" [NEEDS_FIX] ") == "NEEDS_FIX"
    for report in (
        "[APPROVED]\n[NEEDS_FIX]",
        "audit complete\n[APPROVED]",
        "[APPROVED]\naudit complete",
        "APPROVED",
    ):
        with pytest.raises(ValueError, match="standalone verdict"):
            validate_standalone_verdict(report)


def test_cycle_four_and_oversized_response_fail_closed():
    with pytest.raises(RuntimeError, match="MAX_REMEDIATIONS_EXCEEDED"):
        evaluate_model_decision(role="l2", risk="low", cycle=4)
    with pytest.raises(ValueError, match="1MB"):
        evaluate_model_decision(role="l2", risk="low", response={"x": "a" * 1_048_577})


def test_prompt_data_escapes_delimiters_and_rejects_controls():
    assert escape_xml_data("<&\"'") == "&lt;&amp;&quot;&apos;"
    with pytest.raises(ValueError):
        escape_xml_data("bad\x00value")

def test_directory_decision_paths_fail_without_publication(tmp_path):
    directory = tmp_path / "decision.json"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        atomic_publish_decision({"schema_version": "2.0"}, directory)
    with pytest.raises(FileNotFoundError, match="decision file not found"):
        load_decision(directory, "0" * 64)
    assert not list(directory.iterdir())

def test_injected_scope_control_character_rejected_before_provider(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **_):
            calls.append("provider")
    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **_: None, Client
    for name in ("TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError", "TypeSafeInternalServerError"):
        setattr(sdk, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    with pytest.raises(ValueError, match="control characters"):
        evaluate_model_decision(role="l2", risk="high", scope=["-x", "bad\x00scope"])
    assert not calls

def test_jev_retries_429_once_then_returns_judgments(monkeypatch):
    calls = []
    response = types.SimpleNamespace(
        nouls={"genuine_testing": types.SimpleNamespace(noul=0.9), "fabricated_evidence": types.SimpleNamespace(noul=0.1)},
        scores={"test_quality": types.SimpleNamespace(score=0.8, confidence=0.9)},
    )

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("HTTP 429")
            return response

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    monkeypatch.setattr(validate_l2_report.time, "sleep", lambda seconds: calls.append(seconds))
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) == {
        "genuine_testing": {"noul": 0.9}, "fabricated_evidence": {"noul": 0.1},
        "test_quality": {"score": 0.8, "confidence": 0.9},
    }
    assert calls == [1, 1, 1]

def test_jev_auth_exception_redacts_credentials_and_fails_open(monkeypatch, capsys):
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            error = RuntimeError("Authorization: Bearer secret-jev-token")
            error.status = 401
            raise error

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) is None
    assert "secret-jev-token" not in capsys.readouterr().out

def test_jev_429_retry_exhaustion_is_bounded(monkeypatch, capsys):
    calls = []

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            calls.append("request")
            raise RuntimeError("HTTP 429")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    monkeypatch.setattr(validate_l2_report.time, "sleep", lambda seconds: calls.append(seconds))
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) is None
    assert calls == ["request", 1, "request"]
    assert "429" in capsys.readouterr().out

def _pre_audit_payload():
    return {
        "schema_version": "1.0", "gate": "G", "session_id": "S", "role": "devops-engineer",
        "scope": ["file.py"], "fingerprints": {"file.py": "a" * 64}, "verifier": {"exit_code": 0},
        "ast_findings": [], "judgments": [], "scores": [],
        "routing": {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0},
        "generated_at": "2026-09-23T00:00:00Z",
    }

def test_pre_audit_sidecar_failure_atomically_restores_both_files(tmp_path, monkeypatch):
    target = tmp_path / "pre_audit_S.json"
    sidecar = target.with_suffix(".sha256")
    target.write_bytes(b"old artifact")
    sidecar.write_bytes(b"old digest")
    replace = os.replace
    calls = 0

    def fail_sidecar_once(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("sidecar replace failed")
        replace(src, dst)

    monkeypatch.setattr(validate_l2_report.os, "replace", fail_sidecar_once)
    with pytest.raises(OSError, match="sidecar replace failed"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert target.read_bytes() == b"old artifact"
    assert sidecar.read_bytes() == b"old digest"
    assert not (tmp_path / ".pre_audit_S.lock").exists()

def test_pre_audit_live_lock_rejects_concurrent_writer(tmp_path):
    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text(str(os.getpid()), encoding="ascii")
    with pytest.raises(FileExistsError):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")

def test_pre_audit_recovers_dead_owner_lock(tmp_path):
    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text("2147483647", encoding="ascii")
    artifact, sidecar = validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert artifact.is_file() and sidecar.is_file()
    assert not lock.exists()

def test_pre_audit_does_not_remove_replaced_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".pre_audit_S.lock"
    original_close = os.close

    def replace_lock_after_close(fd):
        original_close(fd)
        if lock.exists():
            lock.write_text("another-owner", encoding="ascii")

    monkeypatch.setattr(os, "close", replace_lock_after_close)
    validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert lock.read_text(encoding="ascii") == "another-owner"

def test_decision_publication_recovers_dead_owner_lock(tmp_path):
    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text("2147483647", encoding="ascii")
    path, digest = atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not lock.exists()


def test_decision_publication_preserves_live_aged_lock(tmp_path):
    target = tmp_path / "decision.json"
    target.write_bytes(b"original")
    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text(str(os.getpid()), encoding="ascii")
    old = time.time() - 600
    os.utime(lock, (old, old))
    with pytest.raises(FileExistsError):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert target.read_bytes() == b"original"
    assert lock.read_text(encoding="ascii") == str(os.getpid())


@pytest.mark.parametrize("field,value", [
    ("lead_model", "unapproved"), ("subagent_model", "unapproved"),
    ("execution_timeout", True), ("execution_timeout", "180"),
    ("execution_timeout", 999),
])
@pytest.mark.parametrize("role", ["l2", "l3"])
def test_decision_allowlist_rejects_response_and_digest_rebound_file(tmp_path, role, field, value):
    path = tmp_path / "decision.json"
    valid = evaluate_model_decision(role=role, risk="low", response={}, decision_path=path)
    with pytest.raises(ValueError, match="allowlist"):
        evaluate_model_decision(role=role, risk="low", response={field: value}, decision_path=path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert valid["decision_digest"] != hashlib.sha256(path.read_bytes()).hexdigest()

def test_sod_pipeline_approved_report_runs_enforcer(monkeypatch, tmp_path):
    monkeypatch.setattr(sod_pipeline, "REPO_ROOT", tmp_path)
    report_path = tmp_path / "audit.md"
    monkeypatch.setattr(sod_pipeline, "_dispatch_l2", lambda *_: ({"SESSION_ID": "S", "ROLE_ID": "11"}, "l2"))
    monkeypatch.setattr(sod_pipeline, "_dispatch_l3", lambda *_: ({"REPORT": "audit.md"}, "l3"))
    monkeypatch.setattr(sod_pipeline, "capture", lambda *_: (0, "PRE_AUDIT_PATH=x\nPRE_AUDIT_SHA256=" + "a" * 64))
    calls = []

    def run(command, description, check=True):
        calls.append((command, description))
        if description.startswith("L3 Codex Audit"):
            report_path.write_text("[APPROVED]\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(sod_pipeline, "run", run)
    assert sod_pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py"]) == 0
    assert any(desc == "SoD Gate Enforcer" and command[1:] == ["scripts/sod_gate_enforcer.py"] for command, desc in calls)

def test_jev_l2_decision_uses_dispatch_session_without_republication(monkeypatch, tmp_path):
    session_date = datetime.now().strftime("%Y%m%d")
    monkeypatch.setattr(sod_pipeline, "datetime", types.SimpleNamespace(now=lambda: datetime.strptime(session_date, "%Y%m%d")))
    monkeypatch.setattr(sod_pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sod_pipeline, "_dispatch_l2", lambda *_: ({"SESSION_ID": f"l2_role11_slug_{session_date}", "ROLE_ID": "11"}, "l2"))
    monkeypatch.setattr(sod_pipeline, "_dispatch_l3", lambda *_: pytest.fail("L3 should not run"))
    monkeypatch.setattr(sod_pipeline, "capture", lambda *_: (1, "validation failed"))
    monkeypatch.setattr(sod_pipeline, "run", lambda *_args, **_kwargs: 0)
    published = []

    def decide(**kwargs):
        published.append(kwargs)
        return {"session_id": kwargs["session_id"], "decision_digest": "a" * 64}

    monkeypatch.setattr(sod_pipeline, "evaluate_model_decision", decide)
    assert sod_pipeline.main(["devops-engineer", "code-reviewer", "GATE", "slug", "task", "file.py", "--jev"]) == 1
    assert len(published) == 1
    assert published[0]["session_id"] == f"l2_role11_slug_{session_date}"

def test_standing_regression_classes_are_all_retained():
    from scripts.dispatch_l2 import build_regression_clause, load_regression_classes

    expected = (
        "literal/legacy IPv4 denial", "IPv6 embedded IPv4 payloads", "special-use ranges",
        "sparse config merge preservation", "test isolation snapshot restore", "durable TLS SNI evidence",
        "userinfo credential rejection", "URL redaction in errors",
    )
    assert tuple(load_regression_classes()) == expected
    clause = build_regression_clause()
    assert all(item in clause for item in expected)


def test_jev_api_called_with_choice_questions(monkeypatch):
    recorded = {}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, state, questions, **_):
            recorded["state"] = state
            recorded["questions"] = questions
            return types.SimpleNamespace(
                choices={
                    "lead_model": types.SimpleNamespace(choice="9router/cx/gpt-6-sol"),
                    "subagent_model": types.SimpleNamespace(choice="ag/gemini"),
                    "execution_timeout": types.SimpleNamespace(choice="180"),
                }
            )

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), MockClient
    sdk.TypeSafeAPIConnectionError = type("TypeSafeAPIConnectionError", (Exception,), {})
    sdk.TypeSafeAPITimeoutError = type("TypeSafeAPITimeoutError", (Exception,), {})
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    envelope = evaluate_model_decision(role="l2", risk="low", task="fix something", cycle=1)
    assert envelope["lead_model"] == "9router/cx/gpt-6-sol"
    assert envelope["subagent_model"] == "ag/gemini"
    assert envelope["execution_timeout"] == 180
    assert "lead_model" in recorded["questions"]
    assert "subagent_model" in recorded["questions"]


def test_fallback_active_on_low_risk_network_error(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused by api.typesafe.ai")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    envelope = evaluate_model_decision(role="l2", risk="low", cycle=1)
    assert envelope["fallback_used"] is True
    assert "Connection refused" in envelope["fallback_reason"]
    assert envelope["lead_model"] == L2_LEAD_ALLOWLIST[1]


def test_fallback_reason_redacted_before_durable_publication(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(
        role="l2", risk="low", decision_path=path,
        response={"fallback_used": True, "fallback_reason": "https://user:secret@example.org/?api_key=private"},
    )
    assert "secret" not in path.read_text(encoding="utf-8")
    assert "private" not in path.read_text(encoding="utf-8")
    assert "secret" not in envelope["fallback_reason"]
    assert load_decision(path, envelope["decision_digest"])["fallback_reason"] == envelope["fallback_reason"]


def test_fallback_forbidden_on_high_risk_network_error(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    with pytest.raises(ConnectionError):
        evaluate_model_decision(role="l2", risk="high", cycle=1)


def test_fallback_forbidden_on_remediation_cycle(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    with pytest.raises(ConnectionError):
        evaluate_model_decision(role="l2", risk="low", cycle=2)


def test_publish_decision_fails_closed_on_replace_error(tmp_path, monkeypatch):
    envelope = {"schema_version": "2.0", "gate": "G", "session_id": "S"}
    target = tmp_path / "decision.json"

    def fail_replace(src, dst):
        raise OSError("Simulated disk error")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="Simulated disk error"):
        atomic_publish_decision(envelope, target)

    assert not target.exists()
    assert not (tmp_path / f".{target.name}.lock").exists()


def test_decision_and_predecessor_exceeding_bound_fail_closed(tmp_path):
    from scripts.jev_model_router import MAX_RESPONSE_BYTES
    oversized = tmp_path / "oversized.md"
    oversized.write_bytes(b"F-001 " * (MAX_RESPONSE_BYTES // 5 + 10))
    with pytest.raises(ValueError, match="predecessor report exceeds size bound"):
        evaluate_model_decision(role="l2", risk="low", predecessor_report=oversized)

    oversized_dec = tmp_path / "decision.json"
    oversized_dec.write_bytes(b"a" * (MAX_RESPONSE_BYTES + 10))
    with pytest.raises(ValueError, match="decision payload exceeds size bound"):
        load_decision(oversized_dec, "0" * 64)
