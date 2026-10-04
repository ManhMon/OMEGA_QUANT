#!/usr/bin/env python3
"""Unit and integration tests for scripts/dispatch_l4.py."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.dispatch_l4 import (
    DEFAULT_L4_ADVISOR,
    DEFAULT_L4_MODELS,
    L4_MODEL_ALLOWLIST,
    _generate_l4_dispatch,
    _publish_dispatch_artifacts,
    _parse_l4_cli_args,
    main,
    redact_credentials,
)


@pytest.mark.parametrize("case", [
    "risk", "unknown-flag", "flag-value", "model", "co-role", "digest",
    "role", "gate", "slug", "extra-positional", "control", "role-resolution", "co-role-resolution",
])
def test_l4_rejected_cli_credentials_never_reach_stderr(case, tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    secret = "OPAQUE_TEST_CREDENTIAL_927461"
    args = ["tech-lead", "GATE", "slug", "task", "tests/test_dispatch_l4.py"]
    variants = {
        "risk": ["--risk", f"token={secret}"],
        "unknown-flag": [f"--{secret}"],
        "flag-value": [f"--api_key={secret}"],
        "model": ["--model", secret],
        "co-role": ["--co-role", f"credential={secret}"],
        "digest": ["--model-decision-path", "decision.json", "--model-decision-digest", secret],
        "extra-positional": [secret],
        "control": [f"--risk\n{secret}"],
    }
    if case in ("role", "gate", "slug"):
        args[("role", "gate", "slug").index(case)] = f"credential={secret}"
    elif case == "role-resolution":
        args[0] = secret
    elif case == "co-role-resolution":
        args += ["--co-role", secret]
    else:
        args += variants[case]
    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["dispatch_l4.py", *args])
    if case in ("role-resolution", "co-role-resolution"):
        assert dispatch.main() == 2
    else:
        with pytest.raises(SystemExit) as error:
            dispatch.main()
        assert error.value.code == 2
    output = capsys.readouterr()
    assert secret not in output.err and secret.lower() not in output.err.lower()
    assert output.err and not output.out
    assert not (tmp_path / ".ly_state").exists()


@pytest.mark.parametrize("extra", [
    ["--risk", "token=OPAQUE_SUBPROCESS_CANARY"],
    ["--api_key=OPAQUE_SUBPROCESS_CANARY"],
], ids=["risk", "unknown-flag"])
def test_l4_cli_process_omits_rejected_secrets(extra):
    result = subprocess.run(
        [sys.executable, "scripts/dispatch_l4.py", "tech-lead", "GATE", "slug", "task", "tests/", *extra],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "opaque_subprocess_canary" not in (result.stdout + result.stderr).lower()
    assert "[ERROR]" in result.stderr and "Traceback" not in result.stderr


BARE_PROVIDER_TOKENS = [
    "sk-ant-TEST_ONLY_927461", "sk-proj-TEST_ONLY_927461", "sk-svcacct-TEST_ONLY_927461",
    "sk-TEST_ONLY_927461", "ghp_TEST_ONLY_927461", "gho_TEST_ONLY_927461",
    "ghu_TEST_ONLY_927461", "ghs_TEST_ONLY_927461", "ghr_TEST_ONLY_927461",
    "github_pat_TEST_ONLY_927461", "AIzaTEST_ONLY_927461", "xoxb-TEST_ONLY_927461",
    "xoxp-TEST_ONLY_927461", "xoxa-TEST_ONLY_927461", "xoxr-TEST_ONLY_927461",
    "xoxs-TEST_ONLY_927461", "xoxe-TEST_ONLY_927461", "gsk_TEST_ONLY_927461",
    "pplx-TEST_ONLY_927461", "hf_TEST_ONLY_927461", "r8_TEST_ONLY_927461",
    "glpat-TEST_ONLY_927461",
]


@pytest.fixture
def identifier_boundary(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    import scripts.jev_model_router as router
    import scripts.sod_pipeline as pipeline

    session = tmp_path / ".ly_state/session"
    session.mkdir(parents=True)
    (session / "dispatch_live.lock").write_bytes(b"live owner")
    (session / "existing.bin").write_bytes(b"existing publication")
    (session / "incomplete.tmp").write_bytes(b"other writer's staging")

    def snapshot():
        return {path.relative_to(tmp_path).as_posix(): path.read_bytes()
                for path in tmp_path.rglob("*") if path.is_file()}

    baseline = snapshot()

    def forbidden(*_args, **_kwargs):
        pytest.fail("rejected identifier reached a downstream side effect")

    for module in (dispatch, pipeline):
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    for name in (
        "resolve_l2_roles", "infer_risk", "acquire_session_lock", "release_session_lock",
        "load_sanitized_lesson_entries", "run_graph_predispatch_gate", "_existing_graph_evidence",
        "extract_prior_audit_outcomes", "build_anti_drip_contract", "ensure_session_containment",
        "_publish_dispatch_artifacts", "build_verified_prompt_read_statement",
    ):
        monkeypatch.setattr(dispatch, name, forbidden)
    monkeypatch.setattr(router, "load_decision", forbidden)
    for name in ("capture", "evaluate_model_decision", "_plan_path", "_read_graph_evidence_sha256"):
        monkeypatch.setattr(pipeline, name, forbidden)
    monkeypatch.setattr(pipeline.subprocess, "run", forbidden)

    def assert_rejected(call, token):
        with pytest.raises(SystemExit) as error:
            call()
        assert error.value.code == 2
        output = capsys.readouterr()
        assert output.err == "[ERROR] Invalid dispatch identifier.\n"
        assert not output.out
        assert token.lower() not in (output.err + output.out).lower()
        assert snapshot() == baseline
        assert all(token.lower() not in name.lower() for name in snapshot())

    return assert_rejected


@pytest.mark.parametrize("field", ["gate", "slug"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["normal", "dry-run"])
def test_l4_credential_identifiers_reject_before_effects(field, dry_run, monkeypatch, identifier_boundary):
    import scripts.dispatch_l4 as dispatch

    for token in BARE_PROVIDER_TOKENS:
        for value in (token, token.upper(), f"SAFE_{token}", f"SAFE-{token}", f"{token}_SAFE"):
            args = ["tech-lead", "SAFE_GATE", "safe_slug", "task", "tests/test_dispatch_l4.py"]
            args[1 if field == "gate" else 2] = value
            args += ["--model-decision-path", ".ly_state/session/decision.json",
                     "--model-decision-digest", "a" * 64]
            if dry_run:
                args.append("--dry-run")
            monkeypatch.setattr(sys, "argv", ["dispatch_l4.py", *args])
            identifier_boundary(dispatch.main, token)


@pytest.mark.parametrize("field", ["gate_name", "session_id"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["normal", "dry-run"])
def test_l4_direct_credential_identifiers_reject_before_effects(field, dry_run, identifier_boundary):
    values = dict(
        roles=[{"name": "tech-lead", "role_id": 7, "role_file": ".agents/agent/tech-lead.md", "skill_files": []}],
        gate_name="SAFE_GATE", task_desc="task", scope="tests/test_dispatch_l4.py",
        session_id="l4_role7_safe_20261003", lessons_block="lessons", risk="low",
        risk_reason="test", model="sonnet", advisor_model=None, graph_evidence={}, dry_run=dry_run,
    )
    for token in BARE_PROVIDER_TOKENS:
        for value in (token, token.upper(), f"SAFE_{token}", f"SAFE-{token}", f"{token}_SAFE"):
            values[field] = value if field == "gate_name" else f"l4_role7_{value}_20261003"
            identifier_boundary(lambda: _generate_l4_dispatch(**values), token)
    for value in (None, 7, b"bad", [], "../bad", "bad\nvalue", "x" * 129):
        values[field] = value
        identifier_boundary(lambda: _generate_l4_dispatch(**values), "INVALID_TYPE_CANARY")


@pytest.mark.parametrize("entry", ["main", "dispatch", "planning", "graph", "l3"])
def test_pipeline_credential_identifiers_reject_before_effects(entry, identifier_boundary):
    import scripts.sod_pipeline as pipeline

    for field in ("gate", "slug"):
        if entry == "graph" and field == "gate":
            continue
        for token in BARE_PROVIDER_TOKENS:
            argv = ["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", "task", "tests/test_dispatch_l4.py"]
            args = pipeline.parse_args([*argv, "--tier", "l4"])
            setattr(args, field, token)
            if entry == "main":
                argv[2 if field == "gate" else 3] = token
                for flags in ([], ["--dry-run"], ["--jev"], ["--with-plan"], ["--graph-evidence", "evidence.json"]):
                    identifier_boundary(lambda: pipeline.main([*argv, "--tier", "l4", *flags]), token)
            elif entry == "dispatch":
                identifier_boundary(lambda: pipeline._dispatch_l2(args, args.task), token)
            elif entry == "planning":
                identifier_boundary(lambda: pipeline._run_planning_phase(args), token)
            elif entry == "graph":
                for evidence_path in (None, "evidence.json"):
                    identifier_boundary(lambda: pipeline._current_graph_binding(token, evidence_path), token)
            else:
                session_id = f"l4_role7_{token}_20261003" if field == "slug" else "safe_session"
                identifier_boundary(lambda: pipeline._dispatch_l3(args, session_id), token)


def test_l4_safe_identifier_limits_and_near_misses_preserved(capsys):
    import scripts.dispatch_l4 as dispatch

    for value in ("GATE_L4_CLAUDECODE_SETUP_20261003", "safe_slug", "sk-", "ghp_", "AIza", "xoxb-", "x" * 64):
        assert dispatch.validate_identifier(value, "gate_name") == value
        assert dispatch.validate_identifier(value, "task_slug") == value
    assert dispatch.validate_identifier("x" * 128, "session_id") == "x" * 128
    for kind, length in (("gate_name", 65), ("task_slug", 65), ("session_id", 129)):
        with pytest.raises(SystemExit) as error:
            dispatch.validate_identifier("x" * length, kind)
        assert error.value.code == 2
    assert "x" * 65 not in capsys.readouterr().err


@pytest.mark.parametrize("field", ["gate", "slug"])
def test_l4_cli_process_omits_credential_identifiers(field):
    token = BARE_PROVIDER_TOKENS[0]
    args = ["tech-lead", "SAFE_GATE", "safe_slug", "task", "tests/test_dispatch_l4.py"]
    args[1 if field == "gate" else 2] = token
    result = subprocess.run(
        [sys.executable, "scripts/dispatch_l4.py", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2 and not result.stdout
    assert result.stderr == "[ERROR] Invalid dispatch identifier.\n"
    assert token.lower() not in result.stderr.lower()


def test_l4_bare_provider_redaction_covers_formats_and_preserves_safe_text():
    for token in BARE_PROVIDER_TOKENS:
        for value in (token, token.upper(), f'"{token}"', f"({token})", f"https://example.com/{token}?q=ok"):
            redacted = redact_credentials(value)
            assert token.lower() not in redacted.lower()
            assert "[REDACTED]" in redacted
            assert redact_credentials(redacted) == redacted
    for value in ("", "safe task", "sk-", "ghp_", "AIza", "xoxb-", "scripts/dispatch_l4.py", "sonnet opus", "risk-low task-description"):
        assert redact_credentials(value) == value


def test_l4_bare_tokens_removed_from_provider_prompt_before_lookup_and_hashing(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    task_seen, scope_seen, provider_reads = [], [], []
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda _role, task: task_seen.append(task) or [])
    monkeypatch.setattr(dispatch, "run_graph_predispatch_gate", lambda _session, scope, _root: scope_seen.append(scope) or {})
    monkeypatch.setattr(dispatch, "build_lessons_data_block", lambda _: f"LESSON {BARE_PROVIDER_TOKENS[2]}")
    monkeypatch.setattr(dispatch, "build_graph_prompt_evidence", lambda _: f"GRAPH {BARE_PROVIDER_TOKENS[3]}")
    monkeypatch.setattr(dispatch, "build_regression_clause", lambda: f"REGRESSION {BARE_PROVIDER_TOKENS[4]}")
    real_reader = dispatch.build_verified_prompt_read_statement

    def provider_read(path, digest):
        provider_reads.append((path, digest))
        return real_reader(path, digest)

    monkeypatch.setattr(dispatch, "build_verified_prompt_read_statement", provider_read)
    all_tokens = " ".join(BARE_PROVIDER_TOKENS)
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "tech-lead", "BARE_GATE", "bare_tokens",
        f"safe task {all_tokens}", f"tests/ {all_tokens}", "--risk", "low",
    ])
    assert dispatch.main() == 0
    assert task_seen and scope_seen and provider_reads
    output = capsys.readouterr()
    path, digest = provider_reads[0]
    provider_input = path.read_bytes()
    assert digest == hashlib.sha256(provider_input).hexdigest()
    assert f"PROMPT_SHA256={digest}" in output.out
    assert "claude -p" in output.out and "[REDACTED]" in provider_input.decode()
    for token in BARE_PROVIDER_TOKENS:
        assert token not in task_seen[0] and token not in scope_seen[0]
        assert token.encode() not in provider_input
        assert token not in output.out + output.err
    assert b"safe task" in provider_input
    assert not list(path.parent.glob("dispatch_*.lock"))


def test_l4_direct_generation_redacts_bare_tokens_without_main(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    token = BARE_PROVIDER_TOKENS[0]
    _generate_l4_dispatch(
        roles=[{"name": "tech-lead", "role_id": 7, "role_file": ".agents/agent/tech-lead.md", "skill_files": []}],
        gate_name="DIRECT_GATE", task_desc=f"task {token}", scope=f"scope {token}",
        session_id="l4_role7_direct_20261003", lessons_block=f"lesson {token}",
        risk="low", risk_reason="test", model="sonnet", advisor_model=None, graph_evidence={},
    )
    prompt = (tmp_path / ".ly_state/session/prompt_l4_role7_direct_20261003.txt").read_bytes()
    assert token.encode() not in prompt and b"[REDACTED]" in prompt
    assert f"PROMPT_SHA256={hashlib.sha256(prompt).hexdigest()}" in capsys.readouterr().out


@pytest.mark.parametrize("stage", ["decision", "graph", "publication", "replace", "fsync", "readback", "rollback"],
                         ids=["decision", "graph", "publication", "rename-failure", "fsync", "readback", "rollback"])
def test_l4_injected_errors_redact_bare_tokens_and_release_lock(stage, tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    token = BARE_PROVIDER_TOKENS[0]
    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda *_: [])
    monkeypatch.setattr(dispatch, "run_graph_predispatch_gate", lambda *_: {})
    args = ["dispatch_l4.py", "tech-lead", "ERROR_GATE", "bare_errors", "task", "tests/", "--risk", "low"]
    session = tmp_path / ".ly_state/session"
    session.mkdir(parents=True)
    prompt = session / f"prompt_l4_role7_bare_errors_{datetime.now().strftime('%Y%m%d')}.txt"
    prompt.write_bytes(b"previous prompt")
    if stage == "rollback":
        contract = session / f"anti_drip_contract_l4_role7_bare_errors_{datetime.now().strftime('%Y%m%d')}.json"
        contract.write_bytes(b"previous contract")
    baseline = {path.name: path.read_bytes() for path in session.iterdir()}

    def fail(*_args, **_kwargs):
        raise OSError(f"injected {stage}: {token}")

    if stage == "decision":
        import scripts.jev_model_router as router
        decision = session / "decision.json"
        decision.write_bytes(b"invalid")
        monkeypatch.setattr(router, "load_decision", fail)
        args += ["--model-decision-path", ".ly_state/session/decision.json", "--model-decision-digest", "a" * 64]
        baseline[decision.name] = decision.read_bytes()
    elif stage == "graph":
        monkeypatch.setattr(dispatch, "run_graph_predispatch_gate", fail)
    elif stage == "publication":
        monkeypatch.setattr(dispatch, "_publish_dispatch_artifacts", fail)
    elif stage == "fsync":
        monkeypatch.setattr(dispatch.os, "fsync", fail)
        monkeypatch.setattr(dispatch, "acquire_session_lock", lambda *_: None)
    elif stage in ("replace", "rollback"):
        real_replace = os.replace
        calls = 0

        def replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 2 or stage == "rollback":
                fail()
            return real_replace(source, target)

        monkeypatch.setattr(dispatch.os, "replace", replace)
    else:
        real_read = dispatch._read_artifact_bytes

        def read(path, limit):
            if path == prompt and real_read(path, limit) != b"previous prompt":
                fail()
            return real_read(path, limit)

        monkeypatch.setattr(dispatch, "_read_artifact_bytes", read)
    monkeypatch.setattr(sys, "argv", args)
    assert dispatch.main() == 2
    output = capsys.readouterr()
    assert token not in output.err + output.out
    assert "[REDACTED]" in output.err or (stage == "rollback" and "rollback failed" in output.err)
    if stage == "rollback":
        assert "rollback failed" in output.err
    assert not output.out
    assert {path.name: path.read_bytes() for path in session.iterdir()} == baseline


def test_parse_l4_cli_args_valid_positional():
    args = [
        "system-architect",
        "TEST_GATE",
        "test_slug",
        "Test task description",
        ".agents/AGENTS.md",
    ]
    (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        enable_advisor, dry_run, graph_evidence_path,
        model_decision_path, model_decision_digest,
    ) = _parse_l4_cli_args(args)

    assert role_name == "system-architect"
    assert gate_name == "TEST_GATE"
    assert task_slug == "test_slug"
    assert task_desc == "Test task description"
    assert scope == ".agents/AGENTS.md"
    assert explicit_risk is None
    assert co_roles == []
    assert token_saver is False
    assert explicit_model is None
    assert enable_advisor is True
    assert dry_run is False
    assert graph_evidence_path is None
    assert model_decision_path is None
    assert model_decision_digest is None


def test_parse_l4_cli_args_with_flags():
    args = [
        "system-architect",
        "TEST_GATE",
        "test_slug",
        "Test task description",
        ".agents/AGENTS.md",
        "--risk", "high",
        "--co-role", "tech-lead",
        "--token-saver",
        "--model", "opus",
        "--no-advisor",
    ]
    (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        enable_advisor, dry_run, graph_evidence_path,
        model_decision_path, model_decision_digest,
    ) = _parse_l4_cli_args(args)

    assert explicit_risk == "high"
    assert co_roles == ["tech-lead"]
    assert token_saver is True
    assert explicit_model == "opus"
    assert enable_advisor is False


def test_parse_l4_cli_args_rejects_extra_positionals():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "ignored"])
    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "model", ['opus; Write-Output INJECTED', '";exit 1;"', "x" * 65, "cx/gpt-6.1-sol", "sonnet`nINJECTED"],
    ids=["semicolon-injection", "quote-injection", "overlength-model", "wrong-tier-model", "newline-injection"],
)
def test_parse_l4_cli_args_rejects_unapproved_model(model):
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--model", model])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_accepts_only_allowlisted_model():
    parsed = _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--model", "opus"])
    assert parsed[8] == "opus" and "opus" in L4_MODEL_ALLOWLIST


def test_parse_l4_cli_args_enforces_input_size_limits():
    for index in (3, 4):
        args = ["system-architect", "GATE", "slug", "task", "scope"]
        args[index] = "x" * 16_385
        with pytest.raises(SystemExit) as exc_info:
            _parse_l4_cli_args(args)
        assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_overlength_model():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--model", "x" * 65])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_requires_decision_path_digest_pair():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--model-decision-path", "decision.json"])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_model_and_decision_together():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args([
            "system-architect", "GATE", "slug", "task", "scope", "--model", "opus",
            "--model-decision-path", "decision.json", "--model-decision-digest", "a" * 64,
        ])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_non_sha256_decision_digest():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args([
            "system-architect", "GATE", "slug", "task", "scope",
            "--model-decision-path", "decision.json", "--model-decision-digest", "z" * 64,
        ])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_accepts_bound_decision_flags():
    parsed = _parse_l4_cli_args([
        "system-architect", "GATE", "slug", "task", "scope",
        "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", "a" * 64,
    ])
    assert parsed[-2:] == (".ly_state/session/decision.json", "a" * 64)


def test_parse_l4_cli_args_rejects_extra_positionals_before_flags():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args([
            "system-architect", "GATE", "slug", "task", "scope", "hidden",
            "--risk", "low", "--co-role", "tech-lead",
        ])
    assert exc_info.value.code == 2


def test_l4_prompt_redacts_task_and_scope_before_hashing(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    monkeypatch.setattr(dispatch, "run_graph_predispatch_gate", lambda *_: {})
    monkeypatch.setattr(dispatch, "_existing_graph_evidence", lambda *_: {})
    captured_task = []
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda _role, task: captured_task.append(task) or [])
    monkeypatch.setattr(dispatch, "acquire_session_lock", lambda *_: None)
    monkeypatch.setattr(dispatch, "release_session_lock", lambda *_: None)
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "F002_GATE", "f002_test",
        "inspect Bearer secret-token", "scope api_key=secret-value", "--risk", "low",
    ])
    assert dispatch.main() == 0
    assert captured_task and "secret-token" not in captured_task[0]
    output = capsys.readouterr().out
    session_id = next(line.split("=", 1)[1] for line in output.splitlines() if line.startswith("SESSION_ID="))
    prompt = (tmp_path / ".ly_state/session" / f"prompt_{session_id}.txt").read_bytes()
    assert b"secret-token" not in prompt and b"secret-value" not in prompt
    digest = hashlib.sha256(prompt).hexdigest()
    assert f"PROMPT_SHA256={digest}" in output


@pytest.mark.parametrize(("replace_call", "after_replace"), [(1, False), (2, False), (2, True)])
def test_dispatch_artifact_replace_failure_restores_all_targets(tmp_path, monkeypatch, replace_call, after_replace):
    import scripts.dispatch_l4 as dispatch

    targets = [tmp_path / "contract.json", tmp_path / "prompt.txt"]
    targets[0].write_bytes(b"old-contract")
    real_replace = os.replace
    calls = 0

    def fail_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == replace_call:
            if after_replace:
                real_replace(source, target)
            raise OSError("injected replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(dispatch.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        _publish_dispatch_artifacts([(targets[0], b"new-contract"), (targets[1], b"new-prompt")])
    assert targets[0].read_bytes() == b"old-contract"
    assert not targets[1].exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))


def test_dispatch_artifact_fsync_failure_keeps_previous_state(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"previous")

    def fail_fsync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(dispatch.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected fsync failure"):
        _publish_dispatch_artifacts([(target, b"replacement")])
    assert target.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".*.tmp"))


def test_dispatch_artifact_directory_fsync_failure_rolls_back(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"previous")
    calls = 0

    def fail_directory_fsync(_directory):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected directory fsync failure")

    monkeypatch.setattr(dispatch, "_fsync_directory", fail_directory_fsync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        _publish_dispatch_artifacts([(target, b"replacement")])
    assert target.read_bytes() == b"previous"
    assert calls >= 2
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("write_call", [1, 2])
def test_dispatch_artifact_write_failure_cleans_temp_and_preserves_target(tmp_path, monkeypatch, write_call):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"previous")
    other = tmp_path / "report.md"
    other.write_bytes(b"previous-report")
    real_fdopen = os.fdopen
    writes = 0

    class FailingWriter:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            self.handle.__enter__()
            return self
        def __exit__(self, *args):
            return self.handle.__exit__(*args)
        def write(self, _data):
            nonlocal writes
            writes += 1
            if writes == write_call:
                raise OSError("injected write failure")
            return self.handle.write(_data)
        def flush(self):
            return self.handle.flush()
        def fileno(self):
            return self.handle.fileno()

    monkeypatch.setattr(dispatch.os, "fdopen", lambda fd, mode: FailingWriter(real_fdopen(fd, mode)))
    with pytest.raises(OSError, match="injected write failure"):
        _publish_dispatch_artifacts([(target, b"replacement"), (other, b"new-report")])
    assert target.read_bytes() == b"previous"
    assert other.read_bytes() == b"previous-report"
    assert not list(tmp_path.glob(".*.tmp"))


def test_dispatch_artifact_readback_failure_rolls_back(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"previous")
    real_read = dispatch._read_artifact_bytes
    reads = 0

    def fail_readback(path, limit):
        nonlocal reads
        if path == target:
            reads += 1
            if reads == 2:
                raise OSError("injected readback failure")
        return real_read(path, limit)

    monkeypatch.setattr(dispatch, "_fsync_directory", lambda _directory: None)
    monkeypatch.setattr(dispatch, "_read_artifact_bytes", fail_readback)
    with pytest.raises(OSError, match="injected readback failure"):
        _publish_dispatch_artifacts([(target, b"replacement")])
    assert target.read_bytes() == b"previous"


def test_dispatch_artifact_rollback_failure_is_explicit_and_cleans_temps(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"previous")
    calls = 0

    def fail_replace(_source, _target):
        nonlocal calls
        calls += 1
        raise OSError("injected replace and rollback failure")

    monkeypatch.setattr(dispatch.os, "replace", fail_replace)
    with pytest.raises(RuntimeError, match="publication and rollback failed"):
        _publish_dispatch_artifacts([(target, b"replacement")])
    assert calls == 2
    assert not list(tmp_path.glob(".*.tmp"))


def test_dry_run_rejects_digest_valid_foreign_contract(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch
    from scripts.dispatch_l2 import build_anti_drip_contract, canonical_json_bytes

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    session_id = "l4_role6_contract_binding_20261003"
    contract_path = tmp_path / ".ly_state/session" / f"anti_drip_contract_{session_id}.json"
    contract_path.parent.mkdir(parents=True)
    contract = build_anti_drip_contract("l4_role6_other_20261003", "GATE", tmp_path, None)
    raw = canonical_json_bytes(contract)
    contract_path.write_bytes(raw)
    contract_path.with_suffix(".sha256").write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {contract_path.name}\n", encoding="ascii"
    )
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    with pytest.raises(RuntimeError, match="validation failed"):
        _generate_l4_dispatch(
            roles=[{"name": "system-architect", "role_id": 6, "role_file": ".agents/agent/system-architect.md", "skill_files": []}],
            gate_name="GATE", task_desc="task", scope="scope", session_id=session_id,
            lessons_block="lessons", risk="low", risk_reason="test", model="sonnet",
            advisor_model=None, graph_evidence={}, dry_run=True,
        )


def test_dry_run_rejects_digest_valid_foreign_contract_context(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch
    from scripts.dispatch_l2 import build_anti_drip_contract, canonical_json_bytes

    for binding in ("session", "gate", "schema"):
        root = tmp_path / binding
        monkeypatch.setattr(dispatch, "REPO_ROOT", root)
        session_id, gate = f"l4_role6_contract_{binding}_20261003", "GATE"
        contract_path = root / ".ly_state/session" / f"anti_drip_contract_{session_id}.json"
        contract_path.parent.mkdir(parents=True)
        contract = build_anti_drip_contract(
            f"l4_role6_other_20261003" if binding == "session" else session_id,
            "OTHER_GATE" if binding == "gate" else gate,
            root,
            None,
        )
        if binding == "schema":
            contract["unexpected"] = "schema drift"
        raw = canonical_json_bytes(contract)
        contract_path.write_bytes(raw)
        contract_path.with_suffix(".sha256").write_text(
            f"{hashlib.sha256(raw).hexdigest()}  {contract_path.name}\n", encoding="ascii"
        )
        with pytest.raises(RuntimeError, match="validation failed|binding mismatch"):
            _generate_l4_dispatch(
                roles=[{"name": "system-architect", "role_id": 6, "role_file": ".agents/agent/system-architect.md", "skill_files": []}],
                gate_name=gate, task_desc="task", scope="scope", session_id=session_id,
                lessons_block="lessons", risk="low", risk_reason="test", model="sonnet",
                advisor_model=None, graph_evidence={}, dry_run=True,
            )


@pytest.mark.parametrize(("lead_model", "expected_cli_model"), [
    ("9router/cx/gpt-6.1-sol", "opus"),
    ("9router/cx/gpt-6-luna", "sonnet"),
])
def test_l4_dispatch_accepts_context_bound_jev_decision(tmp_path, monkeypatch, capsys, lead_model, expected_cli_model):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "_existing_graph_evidence", lambda *_: {})
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda *_: [])
    monkeypatch.setattr(dispatch, "acquire_session_lock", lambda *_: None)
    monkeypatch.setattr(dispatch, "release_session_lock", lambda *_: None)
    session_id = f"l4_role6_jev_decision_{datetime.now().strftime('%Y%m%d')}"
    decision_path = tmp_path / ".ly_state/session/decision.json"
    decision = evaluate_model_decision(
        role="l2", risk="high", gate="JEV_GATE", session_id=session_id,
        task="task", response={"lead_model": lead_model}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/test_dispatch_l4.py",
        "--risk", "high",
        "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", decision["decision_digest"], "--dry-run",
    ])
    assert dispatch.main() == 0
    assert f"MODEL={expected_cli_model}" in capsys.readouterr().out


def test_l4_dispatch_rejects_replayed_jev_decision_before_artifacts(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    decision_path = tmp_path / ".ly_state/session/decision.json"
    decision_path.parent.mkdir(parents=True)
    decision = evaluate_model_decision(
        role="l2", risk="low", gate="OTHER_GATE", session_id=f"l4_role6_jev_decision_{today}",
        task="task", response={}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/",
        "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", decision["decision_digest"],
    ])
    assert dispatch.main() == 2
    assert "model decision context mismatch" in capsys.readouterr().err
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))


def test_l4_dispatch_rejects_jev_risk_mismatch_before_artifacts(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    path = tmp_path / ".ly_state/session/decision.json"
    path.parent.mkdir(parents=True)
    decision = evaluate_model_decision(
        role="l2", risk="high", gate="JEV_GATE", session_id=f"l4_role6_jev_risk_{today}",
        task="task", response={}, decision_path=path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_risk", "task", "tests/",
        "--risk", "low", "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", decision["decision_digest"],
    ])
    assert dispatch.main() == 2
    assert "model decision context mismatch" in capsys.readouterr().err
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))


def test_l4_dispatch_rejects_jev_digest_mismatch_before_artifacts(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    decision_path = tmp_path / ".ly_state/session/decision.json"
    decision_path.parent.mkdir(parents=True)
    evaluate_model_decision(
        role="l2", risk="low", gate="JEV_GATE", session_id=f"l4_role6_jev_decision_{today}",
        task="task", response={}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/",
        "--risk", "low", "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", "0" * 64,
    ])
    assert dispatch.main() == 2
    assert "digest mismatch" in capsys.readouterr().err
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))


def test_l4_dispatch_rejects_digest_valid_jev_schema_drift(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    session_id = f"l4_role6_jev_schema_{datetime.now().strftime('%Y%m%d')}"
    path = tmp_path / ".ly_state/session/decision.json"
    path.parent.mkdir(parents=True)
    evaluate_model_decision(
        role="l2", risk="low", gate="JEV_GATE", session_id=session_id,
        task="task", response={}, decision_path=path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unrecognized"] = "schema drift"
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_schema", "task", "tests/",
        "--risk", "low", "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", hashlib.sha256(raw).hexdigest(),
    ])
    assert dispatch.main() == 2
    assert "schema mismatch" in capsys.readouterr().err
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))


def test_l4_dispatch_rejects_jev_path_escape_and_symlink(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    session_id = f"l4_role6_jev_decision_{today}"
    decision_path = tmp_path / ".ly_state/session/decision.json"
    decision_path.parent.mkdir(parents=True)
    decision = evaluate_model_decision(
        role="l2", risk="low", gate="JEV_GATE", session_id=session_id,
        task="task", response={}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/",
        "--risk", "low", "--model-decision-path", "../outside.json",
        "--model-decision-digest", decision["decision_digest"],
    ])
    assert dispatch.main() == 2
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))

    alias = decision_path.parent / "alias.json"
    try:
        alias.symlink_to(decision_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/",
        "--risk", "low", "--model-decision-path", ".ly_state/session/alias.json",
        "--model-decision-digest", decision["decision_digest"],
    ])
    assert dispatch.main() == 2


def test_l4_pipeline_forwards_model_decision_flags(monkeypatch):
    import scripts.sod_pipeline as pipeline

    args = pipeline.parse_args([
        "system-architect", "code-reviewer", "GATE", "slug", "task", "tests/",
        "--tier", "l4", "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", "a" * 64,
    ])
    output = "\n".join([
        "SESSION_ID=session", "ROLE_ID=6", "ROLE_NAME=system-architect", "GATE=GATE",
        "MODEL=sonnet", "RISK=low", "ANTI_DRIP_MODE=baseline",
        "ANTI_DRIP_CONTRACT=.ly_state/session/contract.json",
        "ANTI_DRIP_CONTRACT_SHA256=" + "b" * 64, "---COMMAND---", "run",
    ])
    seen = []
    monkeypatch.setattr(pipeline, "capture", lambda command: (seen.append(command) or (0, output)))
    pipeline._dispatch_l2(args, args.task)
    assert seen[0][1] == "scripts/dispatch_l4.py"
    assert seen[0][-4:] == [
        "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", "a" * 64,
    ]


def test_l4_pipeline_fails_closed_on_dispatch_decision_error(monkeypatch):
    import scripts.sod_pipeline as pipeline

    args = pipeline.parse_args([
        "system-architect", "code-reviewer", "GATE", "slug", "task", "tests/",
        "--tier", "l4", "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", "a" * 64,
    ])
    monkeypatch.setattr(pipeline, "capture", lambda _command: (2, "model decision context mismatch"))
    with pytest.raises(SystemExit, match="model decision context mismatch"):
        pipeline._dispatch_l2(args, args.task)


def test_pipeline_rejects_incomplete_or_conflicting_decision_flags():
    import scripts.sod_pipeline as pipeline

    with pytest.raises(SystemExit):
        pipeline.parse_args([
            "worker", "auditor", "GATE", "slug", "task", "file.py",
            "--model-decision-path", ".ly_state/session/decision.json",
        ])
    with pytest.raises(SystemExit):
        pipeline.parse_args([
            "worker", "auditor", "GATE", "slug", "task", "file.py", "--jev",
            "--model-decision-path", ".ly_state/session/decision.json",
            "--model-decision-digest", "a" * 64,
        ])


def test_l4_explicit_model_injection_fails_before_artifacts(monkeypatch, tmp_path, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "GATE", "hostile_model", "task", "tests/",
        "--model", 'sonnet"; Write-Output INJECTED; "',
    ])
    with pytest.raises(SystemExit) as error:
        dispatch.main()
    assert error.value.code == 2
    assert not list(tmp_path.rglob("prompt_*.txt"))
    assert "INJECTED" not in capsys.readouterr().err


def test_l4_generation_errors_redact_url_credentials(monkeypatch, tmp_path, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda *_: [])
    monkeypatch.setattr(dispatch, "acquire_session_lock", lambda *_: None)
    monkeypatch.setattr(dispatch, "release_session_lock", lambda *_: None)
    monkeypatch.setattr(
        dispatch, "run_graph_predispatch_gate",
        lambda *_: (_ for _ in ()).throw(RuntimeError("failed https://user:password@example.com/a?api_key=secret")),
    )
    monkeypatch.setattr(sys, "argv", ["dispatch_l4.py", "system-architect", "GATE", "redacted", "task", "tests/"])
    assert dispatch.main() == 2
    error = capsys.readouterr().err
    assert "password" not in error and "secret" not in error
    assert "[REDACTED]" in error


def test_dispatch_session_lock_rejects_concurrent_owner(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    first = dispatch.acquire_session_lock("l4_role6_lock_20261003", tmp_path)
    try:
        with pytest.raises(SystemExit) as error:
            dispatch.acquire_session_lock("l4_role6_lock_20261003", tmp_path)
        assert error.value.code == 2
    finally:
        dispatch.release_session_lock(first)


def test_report_validator_rejects_placeholder_completion_evidence():
    from scripts.validate_l2_report import _validate_envelope, validate_anti_drip_report

    text = """## Summary
- Initial implementation pending L2 worker updates.
## Repo-Local Files Read
- .agents/agent/tech-lead.md
- .agents/skills/clean-code/skill.md
## Changes Made
- Updated code.
## Verification
- Tests passed.
## Forbidden Path Scan
- scan evidence
"""
    report = "\n".join([
        "# L2 Implementation Report", "", "- **Role**: 7 tech-lead - OpenCode L2 Implementation",
        "- **Gate**: `GATE`", "- **Session**: `l2_role7_task_20261003`", "- **Date**: `2026-10-03`",
        "- **Anti-Drip Mode**: `baseline`", "- **Anti-Drip Contract**: `.ly_state/session/anti_drip_contract_l2_role7_task_20261003.json`",
        "- **Anti-Drip Contract SHA-256**: `" + "a" * 64 + "`", text,
    ])
    errors = _validate_envelope(report, "l2_role7_task_20261003", 7, "tech-lead", False)
    assert any("placeholder" in error.lower() for error in errors)
    mode, errors = validate_anti_drip_report("l2_role7_task_20261003", report, REPO_ROOT)
    assert mode is None and any("placeholder" in error.lower() for error in errors)


def test_report_validator_rejects_scaffold_text_in_valid_bound_report(tmp_path):
    from scripts.validate_l2_report import validate_anti_drip_report

    text = "# L2 Implementation Report\n\n## Summary\n- Pending L2 worker implementation.\n"
    mode, errors = validate_anti_drip_report("l2_role7_task_20261003", text, tmp_path)
    assert mode is None and any("placeholder" in error.lower() for error in errors)


def test_parse_l4_cli_args_missing_args(capsys):
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE"])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_invalid_risk(capsys):
    args = [
        "system-architect", "GATE", "slug", "desc", "scope",
        "--risk", "critical",
    ]
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(args)
    assert exc_info.value.code == 2


def test_dispatch_l4_cli_execution_valid():
    cmd = [
        sys.executable,
        "scripts/dispatch_l4.py",
        "system-architect",
        "TEST_L4_GATE",
        "test_l4_slug",
        "Verify L4 dispatch generation",
        ".agents/AGENTS.md",
        "--risk", "low",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    stdout = res.stdout
    today = datetime.now().strftime("%Y%m%d")
    expected_session = f"l4_role6_test_l4_slug_{today}"

    assert f"SESSION_ID={expected_session}" in stdout
    assert "ROLE_ID=6" in stdout
    assert "ROLE_NAME=system-architect" in stdout
    assert "GATE=TEST_L4_GATE" in stdout
    assert "MODEL=sonnet" in stdout
    assert "ADVISOR_MODEL=opus" in stdout
    assert "---COMMAND---" in stdout

    command_part = stdout.split("---COMMAND---", 1)[1].strip()
    assert "$__OMEGA_PROMPT | claude -p --dangerously-skip-permissions --model 'sonnet' --advisor 'opus'" in command_part
    assert "System.Security.Cryptography.SHA256" in command_part

    # Verify prompt file was created and contains required L4 sections
    prompt_file = REPO_ROOT / ".ly_state" / "session" / f"prompt_{expected_session}.txt"
    assert prompt_file.is_file()
    prompt_content = prompt_file.read_text(encoding="utf-8")
    assert "ROLE: 6 system-architect - Claude Code L4 Implementation Work" in prompt_content
    assert "# L4 Implementation Report" in prompt_content
    assert "- **Role**: 6 system-architect - Claude Code L4 Implementation" in prompt_content
    assert "--advisor opus" in prompt_content

    # Clean up generated test artifacts
    prompt_file.unlink(missing_ok=True)
    report_file = REPO_ROOT / ".ly_state" / "session" / f"{expected_session}.md"
    report_file.unlink(missing_ok=True)
    contract_file = REPO_ROOT / ".ly_state" / "session" / f"anti_drip_contract_{expected_session}.json"
    contract_file.unlink(missing_ok=True)
    contract_sidecar = contract_file.with_suffix(".sha256")
    contract_sidecar.unlink(missing_ok=True)


def test_dispatch_l4_invalid_role():
    cmd = [
        sys.executable,
        "scripts/dispatch_l4.py",
        "invalid-role-name",
        "GATE",
        "slug",
        "desc",
        ".agents/AGENTS.md",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert res.returncode == 2
    assert "[ERROR]" in res.stderr


PIPELINE_CANARIES = [*BARE_PROVIDER_TOKENS, "BEARER_TEST_927461", "USER_TEST_927461",
                     "PASSWORD_TEST_927461", "QUERY_TEST_927461", "KEY_TEST_927461"]
PIPELINE_SECRETS = " ".join([
    *BARE_PROVIDER_TOKENS, *(token.upper() for token in BARE_PROVIDER_TOKENS),
    "Bearer BEARER_TEST_927461",
    "https://USER_TEST_927461:PASSWORD_TEST_927461@example.com/?api%5Fkey=QUERY_TEST_927461",
    '"api_key": "KEY_TEST_927461"',
])


def _assert_pipeline_zero_leaks(value):
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    assert all(token.casefold() not in text.casefold() for token in PIPELINE_CANARIES)


@pytest.fixture
def planner_sandbox(tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / "file.py").write_text("pass\n", encoding="utf-8")
    args = pipeline.parse_args(["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug",
                                "safe task", "file.py", "--with-plan"])
    plan = tmp_path / ".ly_state/session/implementation_plan.md"

    def respond(_command, **kwargs):
        prompt = kwargs["input"].decode("utf-8")
        _assert_pipeline_zero_leaks(prompt)
        run_id = prompt.split("PLANNING_RUN_ID: ", 1)[1].splitlines()[0]
        raw = (f"# Implementation Plan\n## Planning Run ID\n{run_id}\n"
               f"## Gate\nSAFE_GATE\n## Goal\nGoal {PIPELINE_SECRETS}\n"
               f"## Authorized Scope\n- file.py\n## Technical Design\nDesign {PIPELINE_SECRETS}\n"
               f"## Verification Plan\npytest file.py {PIPELINE_SECRETS}\n").encode("utf-8")
        return subprocess.CompletedProcess(_command, 0, raw, PIPELINE_SECRETS.encode("utf-8"))

    monkeypatch.setattr(pipeline, "_bounded_process", respond)
    return pipeline, args, plan, respond


@pytest.mark.parametrize("entry", ["parse", "planning", "l2", "l4", "l3", "jev"])
def test_pipeline_context_redacted_before_lookup_dispatch_and_hash(entry, planner_sandbox, monkeypatch, capsys):
    pipeline, args, plan, _ = planner_sandbox
    raw = f"safe task {PIPELINE_SECRETS}"
    if entry == "parse":
        parsed = pipeline.parse_args(["worker", "auditor", "SAFE_GATE", "safe_slug", raw, raw])
        assert parsed.task == parsed.scope == redact_credentials(raw)
        return
    args.task, args.scope = raw, raw
    if entry == "planning":
        args.dry_run = True
        real_path = pipeline._plan_path

        def lookup():
            _assert_pipeline_zero_leaks(args.task + args.scope)
            return real_path()

        monkeypatch.setattr(pipeline, "_plan_path", lookup)
        hashes = []
        real_hash = hashlib.sha256
        monkeypatch.setattr(pipeline.hashlib, "sha256", lambda data: hashes.append(data) or real_hash(data))
        pipeline._run_planning_phase(args)
        assert hashes and b"[REDACTED]" in hashes[0]
        _assert_pipeline_zero_leaks(hashes[0])
        assert f"PLAN_SHA256={real_hash(hashes[0]).hexdigest()}" in capsys.readouterr().out
        assert not plan.exists()
        return

    def capture(command):
        _assert_pipeline_zero_leaks(" ".join(command))
        assert "[REDACTED]" in " ".join(command)
        return 2, PIPELINE_SECRETS

    monkeypatch.setattr(pipeline, "capture", capture)
    if entry == "jev":
        def decision(**kwargs):
            _assert_pipeline_zero_leaks(kwargs["task"])
            raise RuntimeError(PIPELINE_SECRETS)
        monkeypatch.setattr(pipeline, "evaluate_model_decision", decision)
        assert pipeline.main(["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", raw,
                              "file.py", "--jev"]) == 2
        _assert_pipeline_zero_leaks(capsys.readouterr().err)
    else:
        args.tier = "l4" if entry == "l4" else "l2"
        with pytest.raises(SystemExit) as error:
            if entry == "l3":
                pipeline._dispatch_l3(args, "safe_session")
            else:
                pipeline._dispatch_l2(args, raw)
        _assert_pipeline_zero_leaks(error.value)


def test_pipeline_planner_validates_publishes_hashes_only_sanitized_bytes(planner_sandbox, monkeypatch, capsys):
    pipeline, args, plan, _ = planner_sandbox
    args.task += " " + PIPELINE_SECRETS
    validated, hashed = [], []
    real_validate, real_hash = pipeline._validate_plan, hashlib.sha256

    def validate(raw, *binding):
        _assert_pipeline_zero_leaks(raw)
        validated.append(raw.encode("utf-8"))
        return real_validate(raw, *binding)

    monkeypatch.setattr(pipeline, "_validate_plan", validate)
    monkeypatch.setattr(pipeline.hashlib, "sha256", lambda data: hashed.append(data) or real_hash(data))
    pipeline._run_planning_phase(args)
    published = plan.read_bytes()
    assert validated == [published, published]
    assert hashed == [published, published]
    assert b"[REDACTED]" in published and b"Goal " in published
    assert not list(plan.parent.glob(".*.tmp")) and not list(plan.parent.glob("*.lock"))
    _assert_pipeline_zero_leaks(published + capsys.readouterr().out.encode())


@pytest.mark.parametrize("field", ["task", "scope"])
@pytest.mark.parametrize("entry", ["parse", "planning", "l2", "l3", "main"])
def test_pipeline_raw_input_bounds_precede_all_effects(field, entry, planner_sandbox, monkeypatch, capsys):
    pipeline, args, plan, _ = planner_sandbox

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid context reached a downstream effect")

    for name in ("_plan_path", "capture", "evaluate_model_decision", "_current_graph_binding"):
        monkeypatch.setattr(pipeline, name, forbidden)
    for value in (None, 7, b"bad", [], "", "   ", "x" * 16_385,
                  "Bearer " + "x" * 16_385):
        args.task, args.scope = "safe task", "file.py"
        setattr(args, field, value)
        if entry in ("parse", "main"):
            if not isinstance(value, str):
                continue
            argv = ["worker", "auditor", "SAFE_GATE", "safe_slug", args.task, args.scope,
                    "--with-plan", "--jev", "--graph-evidence", "evidence.json"]
            with pytest.raises(SystemExit) as error:
                (pipeline.main if entry == "main" else pipeline.parse_args)(argv)
            assert error.value.code == 2
        else:
            with pytest.raises(ValueError):
                if entry == "planning":
                    pipeline._run_planning_phase(args)
                elif entry == "l3":
                    pipeline._dispatch_l3(args, "safe_session")
                else:
                    pipeline._dispatch_l2(args, args.task)
    assert not plan.parent.exists()
    args.task, args.scope = "x" * 16_384, "x" * 16_384
    pipeline._sanitize_context(args)
    assert len(args.task) == len(args.scope) == 16_384
    assert "x" * 100 not in capsys.readouterr().err


@pytest.mark.parametrize("stage", ["path", "lock-create", "spawn", "unexpected", "timeout", "process",
    "utf8", "stdout-limit", "stderr-limit", "validation", "write", "fsync", "rename", "rename-after",
    "readback", "readback-digest", "directory-fsync", "directory-fsync-after",
    "stale-delete", "temp-cleanup", "lock-cleanup"])
def test_pipeline_planner_faults_zero_leaks_and_cleanup(stage, planner_sandbox, monkeypatch, capsys):
    import builtins
    pipeline, args, plan, respond = planner_sandbox
    plan.parent.mkdir(parents=True)
    plan.write_bytes(b"stale plan")
    lock = plan.parent / ".implementation_plan.md.lock"
    real_open, real_unlink, real_replace = builtins.open, Path.unlink, os.replace

    def fail(*_args, **_kwargs):
        raise OSError(PIPELINE_SECRETS)

    if stage == "path":
        monkeypatch.setattr(pipeline, "_plan_path", fail)
    elif stage == "lock-create":
        monkeypatch.setattr(pipeline.os, "open", fail)
    elif stage in ("spawn", "unexpected", "timeout", "process", "utf8", "stdout-limit", "stderr-limit"):
        def fault(command, **kwargs):
            if stage == "spawn":
                fail()
            if stage == "unexpected":
                raise LookupError(PIPELINE_SECRETS)
            if stage == "timeout":
                raise subprocess.TimeoutExpired(PIPELINE_SECRETS, 900,
                                                output=PIPELINE_SECRETS.encode(), stderr=PIPELINE_SECRETS.encode())
            if stage == "process":
                return subprocess.CompletedProcess(command, 1, b"", PIPELINE_SECRETS.encode())
            if stage in ("stdout-limit", "stderr-limit"):
                raise RuntimeError("process output exceeds capture limit")
            return subprocess.CompletedProcess(command, 0, PIPELINE_SECRETS.encode() + b"\xff", b"")
        monkeypatch.setattr(pipeline, "_bounded_process", fault)
    elif stage == "validation":
        monkeypatch.setattr(pipeline, "_validate_plan", fail)
    elif stage in ("write", "readback", "readback-digest"):
        def open_fault(path, mode="r", *a, **kw):
            if stage == "readback-digest" and path == plan and mode == "rb":
                import io
                return io.BytesIO(PIPELINE_SECRETS.encode())
            if (stage == "write" and mode == "wb") or (stage == "readback" and path == plan and mode == "rb"):
                fail()
            return real_open(path, mode, *a, **kw)
        monkeypatch.setattr(builtins, "open", open_fault)
    elif stage == "fsync":
        real_fsync = os.fsync

        def fail_plan_fsync(fd):
            if os.fstat(fd).st_ino == lock.stat().st_ino:
                return real_fsync(fd)
            fail()

        monkeypatch.setattr(pipeline.os, "fsync", fail_plan_fsync)
    elif stage in ("rename", "rename-after"):
        def rename(source, target):
            if target != plan:
                return real_replace(source, target)
            if stage == "rename-after":
                real_replace(source, target)
            fail()
        monkeypatch.setattr(pipeline.os, "replace", rename)
    elif stage in ("directory-fsync", "directory-fsync-after"):
        def directory_fsync(_directory):
            if stage == "directory-fsync" or (plan.exists() and plan.read_bytes() != b"stale plan"):
                fail()

        monkeypatch.setattr(pipeline, "_fsync_directory", directory_fsync)
    else:
        def unlink(path, *a, **kw):
            if ((stage == "stale-delete" and path == plan) or
                (stage == "temp-cleanup" and path.suffix == ".tmp") or
                (stage == "lock-cleanup" and path.suffix == ".trash")):
                fail()
            return real_unlink(path, *a, **kw)
        monkeypatch.setattr(Path, "unlink", unlink)

    with pytest.raises(RuntimeError) as error:
        pipeline._run_planning_phase(args)
    _assert_pipeline_zero_leaks(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__
    # Repeat through the CLI sink; owned-lock cleanup failure must fail closed.
    assert pipeline.main(["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", "task",
                          "file.py", "--with-plan"]) == 2
    output = capsys.readouterr()
    _assert_pipeline_zero_leaks(output.out + output.err)
    assert not list(plan.parent.glob(".*.tmp"))
    if stage not in ("path", "lock-create", "stale-delete", "temp-cleanup", "lock-cleanup"):
        assert not plan.exists()
    if stage != "lock-cleanup":
        assert not lock.exists()


def test_pipeline_planner_contention_preserves_live_owner(planner_sandbox):
    pipeline, args, plan, _ = planner_sandbox
    plan.parent.mkdir(parents=True)
    lock = plan.parent / ".implementation_plan.md.lock"
    lock.write_bytes(b"live owner")
    plan.write_bytes(b"existing plan")
    with pytest.raises(RuntimeError, match="lock contention"):
        pipeline._run_planning_phase(args)
    assert lock.read_bytes() == b"live owner" and plan.read_bytes() == b"existing plan"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("oversized", [False, True], ids=["boundary", "oversized"])
def test_pipeline_process_capture_bounded_during_execution(stream, oversized, tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline
    import tracemalloc

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    limit = 4096
    size = 8 * 1024 * 1024 if oversized else limit
    script = f"import sys; sys.{stream}.buffer.write(b'x' * {size})"
    def snapshot():
        return {path.name: path.read_bytes() if path.is_file() else None for path in tmp_path.iterdir()}

    baseline = snapshot()
    tracemalloc.start()
    try:
        if oversized:
            with pytest.raises(RuntimeError, match="capture limit"):
                pipeline._bounded_process([sys.executable, "-c", script], limit=limit, timeout=10)
        else:
            result = pipeline._bounded_process([sys.executable, "-c", script], limit=limit, timeout=10)
            assert result.returncode == 0 and len(getattr(result, stream)) == limit
        assert tracemalloc.get_traced_memory()[1] < 2 * 1024 * 1024
    finally:
        tracemalloc.stop()
    assert snapshot() == baseline


def test_pipeline_capture_redacts_streams_before_error_sinks(tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    code = "import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr); sys.exit(1)"
    rc, output = pipeline.capture([sys.executable, "-c", code, PIPELINE_SECRETS])
    assert rc == 1 and "[REDACTED]" in output
    _assert_pipeline_zero_leaks(output)


def test_pipeline_findings_redacted_before_remediation_truncation(tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / "audit.md").write_text("F-012: " + PIPELINE_SECRETS, encoding="utf-8")
    _assert_pipeline_zero_leaks(pipeline.extract_findings("audit.md"))


def test_pipeline_redaction_precedes_diagnostic_truncation():
    import scripts.sod_pipeline as pipeline
    for token in BARE_PROVIDER_TOKENS:
        value = "safe " * 3 + token
        for raw in (value, value.encode()):
            assert pipeline._redact(raw, limit=20) == "safe " * 3 + "[REDA"


@pytest.mark.parametrize("stage", ["format", "validation", "dispatch", "graph", "systemexit"])
def test_pipeline_main_diagnostic_sinks_zero_leaks(stage, tmp_path, monkeypatch, capsys):
    import scripts.sod_pipeline as pipeline
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "run", lambda *_a, **_kw: 0)
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda *_: ({"SESSION_ID": "safe_session", "ROLE_ID": "7"}, "run"))
    calls = []

    def capture(command):
        calls.append(command)
        return 1, PIPELINE_SECRETS

    monkeypatch.setattr(pipeline, "capture", capture)
    argv = ["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", "task", "file.py"]
    if stage in ("dispatch", "graph", "systemexit"):
        def fail(*_a, **_kw):
            if stage == "systemexit":
                raise SystemExit(PIPELINE_SECRETS)
            raise RuntimeError(PIPELINE_SECRETS)
        monkeypatch.setattr(pipeline, "_dispatch_l2" if stage != "graph" else "_current_graph_binding", fail)
        if stage == "graph":
            argv += ["--graph-evidence", "evidence.json"]
    if stage == "systemexit":
        with pytest.raises(SystemExit) as error:
            pipeline.main(argv)
        _assert_pipeline_zero_leaks(error.value)
    else:
        assert pipeline.main(argv) == (1 if stage in ("format", "validation") else 2)
    output = capsys.readouterr()
    _assert_pipeline_zero_leaks(output.out + output.err)
    if stage in ("format", "validation"):
        assert len(calls) == 2
        assert "[REDACTED]" in output.out and "[REDACTED]" in output.err


def test_pipeline_cli_parser_errors_redact_provider_canaries(capsys):
    import scripts.sod_pipeline as pipeline
    for token in BARE_PROVIDER_TOKENS:
        with pytest.raises(SystemExit) as error:
            pipeline.parse_args(["worker", "auditor", "SAFE_GATE", "safe_slug", "task", "file.py",
                                 "--risk", token])
        assert error.value.code == 2
    _assert_pipeline_zero_leaks(capsys.readouterr().err)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("limit", [4096, 8388608])
def test_process_quota_kills_live_producer_without_disk_spooling(stream, limit, tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    real_popen = subprocess.Popen
    children = []
    baseline = set(tmp_path.iterdir())

    def spawn(*args, **kwargs):
        assert kwargs["stdout"] == kwargs["stderr"] == subprocess.PIPE
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def forbid_spooling(*_args, **_kwargs):
        pytest.fail("output reached disk before its quota was enforced")

    monkeypatch.setattr(pipeline.subprocess, "Popen", spawn)
    monkeypatch.setattr(pipeline.tempfile, "TemporaryFile", forbid_spooling)
    code = f"import os; block=b'x'*4096\nwhile True: os.write({1 if stream == 'stdout' else 2}, block)"
    with pytest.raises(RuntimeError, match="process output exceeds capture limit"):
        pipeline._bounded_process([sys.executable, "-c", code], limit=limit, timeout=10)
    assert len(children) == 1 and children[0].returncode is not None
    assert children[0].stdout.closed and children[0].stderr.closed
    assert set(tmp_path.iterdir()) == baseline


def test_process_quota_drains_both_streams_while_writing_stdin(tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    limit = 65536
    code = ("import os,sys; os.write(1,b'o'*65536); os.write(2,b'e'*65536); "
            "data=sys.stdin.buffer.read(); sys.exit(0 if len(data)==262144 else 1)")
    result = pipeline._bounded_process([sys.executable, "-c", code], input=b'i' * 262144,
                                       limit=limit, timeout=10)
    assert result.returncode == 0
    assert result.stdout == b'o' * limit and result.stderr == b'e' * limit


def test_process_early_exit_closes_stdin_without_masking_exit_code(tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    result = pipeline._bounded_process([sys.executable, "-c", "import sys; sys.exit(7)"],
                                       input=b'x' * 1048576, limit=4096, timeout=10)
    assert result.returncode == 7 and result.stdout == result.stderr == b""


@pytest.mark.parametrize("input", [None, b""], ids=["no-input", "empty-input"])
def test_process_zero_quota_accepts_empty_output(input, tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    result = pipeline._bounded_process([sys.executable, "-c", "pass"], input=input, limit=0, timeout=10)
    assert result.returncode == 0 and result.stdout == result.stderr == b""


@pytest.mark.parametrize("fault", ["timeout", "reader", "writer", "thread-start"])
def test_process_failure_kills_reaps_and_closes_pipes(fault, tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    real_popen = subprocess.Popen
    children = []

    class FaultyPipe:
        def __init__(self, pipe):
            self.pipe = pipe
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            self.pipe.close()
        def read(self, _limit):
            raise OSError(PIPELINE_SECRETS)
        def write(self, _data):
            raise OSError(PIPELINE_SECRETS)
        def close(self):
            self.pipe.close()
        @property
        def closed(self):
            return self.pipe.closed

    def spawn(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        if fault in ("reader", "writer"):
            name = "stdout" if fault == "reader" else "stdin"
            setattr(child, name, FaultyPipe(getattr(child, name)))
        return child

    monkeypatch.setattr(pipeline.subprocess, "Popen", spawn)
    if fault == "thread-start":
        monkeypatch.setattr(pipeline.threading.Thread, "start",
                            lambda _self: (_ for _ in ()).throw(OSError(PIPELINE_SECRETS)))
    with pytest.raises(RuntimeError) as error:
        pipeline._bounded_process([sys.executable, "-c", "import time; time.sleep(30)"],
                                  input=b"input", timeout=0.2 if fault == "timeout" else 10)
    _assert_pipeline_zero_leaks(error.value)
    assert children[0].returncode is not None
    assert all(pipe.closed for pipe in (children[0].stdin, children[0].stdout, children[0].stderr))


@pytest.mark.parametrize("kwargs", [
    {"limit": -1}, {"limit": True}, {"limit": 1.0}, {"limit": None},
    {"timeout": 0}, {"timeout": float("inf")}, {"timeout": float("nan")},
    {"timeout": True}, {"input": "not bytes"},
], ids=["negative", "bool", "float", "none", "zero-timeout", "inf", "nan", "bool-timeout", "input"])
def test_process_invalid_quotas_reject_before_spawn(kwargs, monkeypatch):
    import scripts.sod_pipeline as pipeline

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid quota reached spawn")

    monkeypatch.setattr(pipeline.subprocess, "Popen", forbidden)
    monkeypatch.setattr(pipeline.subprocess, "run", forbidden)
    with pytest.raises(RuntimeError):
        pipeline._bounded_process([sys.executable], **kwargs)


@pytest.mark.parametrize(("stdout", "stderr", "limit", "error"), [
    (b"", b"", 0, None),
    (b"1234", b"abcd", 4, None),
    (b"x", b"", 0, "capture limit"),
    (b"", b"x", 0, "capture limit"),
    (b"12345", b"abcd", 4, "capture limit"),
    (b"1234", b"abcde", 4, "capture limit"),
    ("1234", b"", 4, "output must be bytes"),
    (b"", None, 4, "output must be bytes"),
], ids=["empty", "exact-both", "zero-stdout", "zero-stderr", "stdout-overflow",
        "stderr-overflow", "stdout-type", "stderr-type"])
def test_process_patched_run_preserves_contract_and_quotas(stdout, stderr, limit, error, monkeypatch):
    import scripts.sod_pipeline as pipeline

    original = subprocess.run
    assert original is pipeline._ORIGINAL_SUBPROCESS_RUN
    command, payload, calls = ["test-only-planner"], b"prompt", []
    result = subprocess.CompletedProcess(command, 7, stdout, stderr)

    def respond(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", respond)
        patch.setattr(subprocess, "Popen", lambda *_a, **_kw: pytest.fail("patched run bypassed"))
        if error:
            with pytest.raises(RuntimeError, match=error):
                pipeline._bounded_process(command, input=payload, limit=limit, timeout=7)
        else:
            assert pipeline._bounded_process(command, input=payload, limit=limit, timeout=7) is result
        assert calls == [(command, {"input": payload, "capture_output": True, "timeout": 7})]
    assert subprocess.run is original


@pytest.mark.parametrize("fault", ["timeout", "spawn", "unexpected"])
def test_process_patched_run_errors_redacted(fault, monkeypatch):
    import scripts.sod_pipeline as pipeline

    def fail(*_a, **_kw):
        if fault == "timeout":
            raise subprocess.TimeoutExpired(PIPELINE_SECRETS, 7,
                                            output=PIPELINE_SECRETS.encode(), stderr=PIPELINE_SECRETS.encode())
        raise (OSError if fault == "spawn" else LookupError)(PIPELINE_SECRETS)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError) as error:
        pipeline._bounded_process(["test-only-planner"], timeout=7)
    _assert_pipeline_zero_leaks(error.value)
    assert "[REDACTED]" in str(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__


@pytest.mark.parametrize("returncode", [0, 7], ids=["success", "failure"])
def test_capture_patched_run_defaults_and_redaction(returncode, monkeypatch):
    import scripts.sod_pipeline as pipeline

    command, calls = ["test-only-dispatch"], []

    def respond(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, PIPELINE_SECRETS.encode(), b"stderr marker " + PIPELINE_SECRETS.encode())

    monkeypatch.setattr(subprocess, "run", respond)
    code, output = pipeline.capture(command)
    assert code == returncode and "[REDACTED]" in output
    _assert_pipeline_zero_leaks(output)
    assert ("stderr marker" in output) == bool(returncode)
    assert calls == [(command, {"input": None, "capture_output": True, "timeout": 900})]


@pytest.mark.parametrize("fault", ["stdout", "stderr", "timeout", "process"])
def test_planner_patched_run_failure_cleans_state_and_preserves_live_owner(fault, tmp_path, monkeypatch):
    import scripts.sod_pipeline as pipeline

    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / "file.py").write_bytes(b"pass\n")
    args = pipeline.parse_args(["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", "task", "file.py"])
    plan = tmp_path / ".ly_state/session/implementation_plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_bytes(b"stale plan")
    calls = []

    def respond(cmd, **kwargs):
        calls.append(cmd)
        assert isinstance(kwargs["input"], bytes)
        assert kwargs["capture_output"] is True and kwargs["timeout"] == 900
        if fault == "timeout":
            raise subprocess.TimeoutExpired(PIPELINE_SECRETS, 900)
        streams = {"stdout": b"", "stderr": b""}
        if fault in streams:
            streams[fault] = b"x" * (pipeline.PLANNER_STREAM_MAX_BYTES + 1)
        else:
            streams["stderr"] = PIPELINE_SECRETS.encode()
        return subprocess.CompletedProcess(cmd, 1, **streams)

    monkeypatch.setattr(subprocess, "run", respond)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_kw: pytest.fail("patched run bypassed"))
    with pytest.raises(RuntimeError) as error:
        pipeline._run_planning_phase(args)
    _assert_pipeline_zero_leaks(error.value)
    assert "capture limit" in str(error.value) if fault in ("stdout", "stderr") else "[REDACTED]" in str(error.value)
    assert not plan.exists() and not list(plan.parent.glob(".*.tmp"))
    lock = plan.parent / ".implementation_plan.md.lock"
    assert not lock.exists() and len(calls) == 1

    lock.write_bytes(b"live owner")
    plan.write_bytes(b"existing publication")
    with pytest.raises(RuntimeError, match="lock contention"):
        pipeline._run_planning_phase(args)
    assert lock.read_bytes() == b"live owner" and plan.read_bytes() == b"existing publication"
    assert len(calls) == 1


@pytest.mark.parametrize("position", [0, 1])
def test_artifact_oversized_original_rejected_before_any_reads(position, tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    targets = [tmp_path / "prompt.txt", tmp_path / "report.md"]
    for target in targets:
        target.write_bytes(b"original")
    with targets[position].open("r+b") as handle:
        handle.truncate(8388608)
    before = [(target.stat().st_size, target.stat().st_ino) for target in targets]
    with targets[position].open("rb") as handle:
        original_digest = hashlib.file_digest(handle, "sha256").digest()
    baseline = set(tmp_path.iterdir())

    def forbidden(*_args, **_kwargs):
        pytest.fail("oversized original reached reading or staging")

    monkeypatch.setattr(dispatch, "_read_artifact_bytes", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(dispatch.tempfile, "mkstemp", forbidden)
    with pytest.raises(OSError, match="size limit"):
        dispatch._publish_dispatch_artifacts([(target, b"replacement") for target in targets])
    assert [(target.stat().st_size, target.stat().st_ino) for target in targets] == before
    for target in targets:
        with target.open("rb") as handle:
            assert handle.read(8) == b"original"
    with targets[position].open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").digest() == original_digest
    assert set(tmp_path.iterdir()) == baseline


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_artifact_nonregular_original_rejected_before_staging(kind, tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    original = tmp_path / "original.txt"
    original.write_bytes(b"original")
    if kind == "directory":
        target.mkdir()
    else:
        try:
            target.symlink_to(original)
        except OSError:
            pytest.skip("symlink creation unavailable")
    monkeypatch.setattr(dispatch.tempfile, "mkstemp", lambda **_kw: pytest.fail("nonregular file reached staging"))
    with pytest.raises(OSError, match="regular file"):
        dispatch._publish_dispatch_artifacts([(target, b"replacement")])
    assert original.read_bytes() == b"original"
    assert target.is_dir() if kind == "directory" else target.is_symlink()


@pytest.mark.parametrize("fault", ["growth-before-open", "growth-during-read", "identity-change"])
def test_artifact_snapshot_race_reads_under_quota(fault, tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "MAX_ARTIFACT_SIZE", 4096)
    target = tmp_path / "prompt.txt"
    target.write_bytes(b"original")
    real_open = Path.open
    read_sizes = []
    if fault == "identity-change":
        from types import SimpleNamespace
        real_fstat = os.fstat

        def changed_identity(fd):
            metadata = real_fstat(fd)
            return SimpleNamespace(st_mode=metadata.st_mode, st_size=metadata.st_size,
                                   st_dev=metadata.st_dev, st_ino=metadata.st_ino + 1)

        monkeypatch.setattr(dispatch.os, "fstat", changed_identity)

    class GrowingReader:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, size):
            read_sizes.append(size)
            assert size == 4097
            with real_open(target, "r+b") as writer:
                writer.truncate(8388608)
            return self.handle.read(size)

    def open_race(path, mode="r", *args, **kwargs):
        if path == target and mode == "rb":
            if fault == "growth-before-open":
                with real_open(target, "r+b") as writer:
                    writer.truncate(8388608)
            handle = real_open(path, mode, *args, **kwargs)
            return GrowingReader(handle) if fault == "growth-during-read" else handle
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_race)
    monkeypatch.setattr(dispatch.tempfile, "mkstemp", lambda **_kw: pytest.fail("unsafe snapshot reached staging"))
    with pytest.raises(OSError, match="changed|size limit"):
        dispatch._publish_dispatch_artifacts([(target, b"replacement")])
    assert read_sizes == ([4097] if fault == "growth-during-read" else [])
    with real_open(target, "rb") as handle:
        assert handle.read(8) == b"original"
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("fault", ["oversized", "growth", "mismatch", "missing", "rollback"])
def test_artifact_readback_quota_failure_restores_originals(fault, tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target, new = tmp_path / "prompt.txt", tmp_path / "report.md"
    target.write_bytes(b"original")
    real_sync, real_open = dispatch._fsync_directory, Path.open
    read_sizes = []

    def corrupt(directory):
        if new.exists():
            if fault == "missing":
                new.unlink()
            else:
                new.write_bytes(b"other" if fault == "mismatch" else b"a" * 8388608)
        real_sync(directory)

    class ReadbackReader:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, size):
            read_sizes.append(size)
            assert size == 6
            with real_open(new, "r+b") as writer:
                writer.truncate(8388608)
            return self.handle.read(size)

    def open_growth(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        return ReadbackReader(handle) if path == new and mode == "rb" else handle

    if fault == "growth":
        monkeypatch.setattr(Path, "open", open_growth)
    else:
        monkeypatch.setattr(dispatch, "_fsync_directory", corrupt)
    if fault == "rollback":
        monkeypatch.setattr(dispatch, "_atomic_write_bytes",
                            lambda *_args: (_ for _ in ()).throw(OSError("injected rollback failure")))
    expected = RuntimeError if fault == "rollback" else OSError
    with pytest.raises(expected, match="rollback failed|size limit|readback mismatch|cannot find|No such file"):
        dispatch._publish_dispatch_artifacts([(target, b"replacement"), (new, b"new!!")])
    with real_open(target, "rb") as handle:
        assert handle.read() == (b"replacement" if fault == "rollback" else b"original")
    assert not new.exists() and not list(tmp_path.glob(".*.tmp"))
    assert read_sizes == ([6] if fault == "growth" else [])


def test_artifact_exact_file_and_count_limits_publish(tmp_path):
    import scripts.dispatch_l4 as dispatch

    targets = [tmp_path / f"artifact-{i}" for i in range(dispatch.MAX_ARTIFACT_FILES)]
    data = b"x" * dispatch.MAX_ARTIFACT_SIZE
    for target in targets:
        target.write_bytes(data)
    dispatch._publish_dispatch_artifacts([(target, data) for target in targets])
    assert all(target.read_bytes() == data for target in targets)
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("fault", ["count", "data-size", "data-type", "record", "path", "duplicate"])
def test_artifact_invalid_batch_rejected_before_reads(fault, tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    target = tmp_path / "prompt.txt"
    target.write_bytes(b"original")
    baseline = set(tmp_path.iterdir())
    batches = {
        "count": [(tmp_path / str(i), b"new") for i in range(dispatch.MAX_ARTIFACT_FILES + 1)],
        "data-size": [(target, b"x" * (dispatch.MAX_ARTIFACT_SIZE + 1))],
        "data-type": [(target, "not bytes")], "record": [(target,)],
        "path": [(str(target), b"new")], "duplicate": [(target, b"new"), (target, b"other")],
    }
    monkeypatch.setattr(dispatch, "_read_artifact_bytes", lambda *_args: pytest.fail("invalid batch reached reading"))
    monkeypatch.setattr(dispatch.tempfile, "mkstemp", lambda **_kw: pytest.fail("invalid batch reached staging"))
    with pytest.raises(ValueError):
        dispatch._publish_dispatch_artifacts(batches[fault])
    assert target.read_bytes() == b"original" and set(tmp_path.iterdir()) == baseline


@pytest.fixture
def planning_lock_sandbox(planner_sandbox, tmp_path, monkeypatch):
    pipeline, args, _plan, respond = planner_sandbox
    # Keep fault-injection paths below Windows MAX_PATH, independent of node ID length.
    root = tmp_path.parent / hashlib.sha256(tmp_path.name.encode()).hexdigest()[:12]
    root.mkdir()
    (root / "file.py").write_bytes(b"pass\n")
    monkeypatch.setattr(pipeline, "REPO_ROOT", root)
    return pipeline, args, root / ".ly_state/session/implementation_plan.md", respond


def _watch_planner_lock_close(monkeypatch, pipeline, lock, before_close=None, after_close=None):
    real_open, real_close, real_fstat = os.open, os.close, os.fstat
    state = {}

    def tracked_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if Path(path) == lock and "fd" not in state:
            state["fd"] = fd
            state["inode"] = real_fstat(fd).st_ino
        return fd

    def tracked_close(fd):
        if fd == state.get("fd") and not state.get("closed"):
            state["owner"] = lock.read_bytes()
            if before_close:
                before_close(state)
            real_close(fd)
            try:
                real_fstat(fd)
            except OSError:
                state["closed"] = True
            if after_close:
                after_close(state)
                state["replacement_created"] = True
            return
        real_close(fd)

    monkeypatch.setattr(pipeline.os, "open", tracked_open)
    monkeypatch.setattr(pipeline.os, "close", tracked_close)
    return state


@pytest.mark.parametrize("outcome", ["success", "dry-run", "failure"], ids=["success", "dry-run", "planner-failure"])
@pytest.mark.parametrize("replacement", [
    "different-inode-same-token", "same-inode-new-owner", "different-inode-new-owner",
], ids=["different-inode-same-token", "same-inode-new-owner", "different-inode-new-owner"])
def test_pipeline_planner_lock_cleanup_preserves_replacement_owner(
    outcome, replacement, planning_lock_sandbox, monkeypatch,
):
    pipeline, args, plan, respond = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    sibling = lock.with_name("replacement.lock")
    args.dry_run = outcome == "dry-run"
    prompts = []

    def plan_response(command, **kwargs):
        prompts.append(kwargs["input"])
        if outcome == "failure":
            return subprocess.CompletedProcess(command, 1, b"", b"planner failed")
        return respond(command, **kwargs)

    monkeypatch.setattr(pipeline, "_bounded_process", plan_response)
    foreign_owner = f"{os.getpid() + 1}:planning_foreign_owner".encode()

    def prepare(state):
        if replacement.startswith("different-inode"):
            sibling.write_bytes(state["owner"] if replacement.endswith("same-token") else foreign_owner)
            state["replacement_inode"] = sibling.stat().st_ino
            assert state["replacement_inode"] != state["inode"]

    def replace_after_close(state):
        if replacement == "same-inode-new-owner":
            lock.write_bytes(foreign_owner)
            state["replacement_inode"] = lock.stat().st_ino
        else:
            os.replace(sibling, lock)

    state = _watch_planner_lock_close(monkeypatch, pipeline, lock, prepare, replace_after_close)
    if outcome == "failure":
        with pytest.raises(RuntimeError, match="planning process failed"):
            pipeline._run_planning_phase(args)
    else:
        pipeline._run_planning_phase(args)

    assert state["closed"] and str(os.getpid()).encode() in state["owner"]
    assert state["replacement_created"]
    owner_pid, run_id = state["owner"].split(b":", 1)
    assert owner_pid == str(os.getpid()).encode() and run_id.startswith(b"planning_safe_slug_")
    if outcome == "dry-run":
        assert not prompts and not plan.exists()
    else:
        assert len(prompts) == 1
        assert run_id.decode() == prompts[0].decode().split("PLANNING_RUN_ID: ", 1)[1].splitlines()[0]
        assert plan.exists() == (outcome == "success")

    assert lock.read_bytes() == (state["owner"] if replacement.endswith("same-token") else foreign_owner)
    assert lock.stat().st_ino == state["replacement_inode"]
    assert not sibling.exists() and not list(plan.parent.glob(".*.tmp"))


@pytest.mark.parametrize("outcome", ["success", "dry-run", "failure"], ids=["success", "dry-run", "planner-failure"])
def test_pipeline_planner_releases_original_lock_on_exit(outcome, planning_lock_sandbox, monkeypatch):
    pipeline, args, plan, respond = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    args.dry_run = outcome == "dry-run"
    if outcome == "failure":
        monkeypatch.setattr(
            pipeline, "_bounded_process",
            lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, b"", b"planner failed"),
        )
    elif outcome == "success":
        monkeypatch.setattr(pipeline, "_bounded_process", respond)
    state = _watch_planner_lock_close(monkeypatch, pipeline, lock)

    if outcome == "failure":
        with pytest.raises(RuntimeError, match="planning process failed"):
            pipeline._run_planning_phase(args)
    else:
        pipeline._run_planning_phase(args)

    assert state["closed"] and not lock.exists()
    assert plan.exists() == (outcome == "success")
    assert not list(plan.parent.glob(".*.tmp"))


@pytest.mark.parametrize("fault", ["fstat", "write-zero", "write-error", "partial-write-error", "fsync"],
                         ids=["fstat", "write-zero", "write-error", "partial-write-error", "fsync"])
def test_pipeline_planner_lock_initialization_failures_close_and_preserve_plan(
    fault, planning_lock_sandbox, monkeypatch,
):
    pipeline, args, plan, _ = planning_lock_sandbox
    plan.parent.mkdir(parents=True)
    plan.write_bytes(b"stale plan")
    original_plan = plan.read_bytes()
    lock = plan.parent / ".implementation_plan.md.lock"
    state = _watch_planner_lock_close(monkeypatch, pipeline, lock)
    real_fstat, real_write, real_fsync = os.fstat, os.write, os.fsync
    calls = 0

    def fail_fstat(fd):
        if fault == "fstat" and fd == state.get("fd"):
            raise OSError("injected fstat failure")
        return real_fstat(fd)

    def fail_write(fd, data):
        nonlocal calls
        if fd != state.get("fd"):
            return real_write(fd, data)
        calls += 1
        if fault == "write-zero":
            return 0
        if fault == "write-error" or (fault == "partial-write-error" and calls == 2):
            raise OSError("injected write failure")
        if fault == "partial-write-error":
            return real_write(fd, data[:max(1, len(data) // 2)])
        return real_write(fd, data)

    def fail_fsync(fd):
        if fault == "fsync" and fd == state.get("fd"):
            raise OSError("injected fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(pipeline.os, "fstat", fail_fstat)
    monkeypatch.setattr(pipeline.os, "write", fail_write)
    monkeypatch.setattr(pipeline.os, "fsync", fail_fsync)
    monkeypatch.setattr(pipeline, "_bounded_process", lambda *_a, **_kw: pytest.fail("planner ran before lock initialization"))
    with pytest.raises(RuntimeError):
        pipeline._run_planning_phase(args)

    assert state["closed"] and plan.read_bytes() == original_plan
    assert lock.exists() == (fault == "fstat")
    assert not list(plan.parent.glob(".*.tmp"))


def test_pipeline_planner_init_failure_preserves_replacement_lock(planning_lock_sandbox, monkeypatch):
    pipeline, args, plan, _ = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    sibling = lock.with_name("replacement.lock")
    real_write = os.write
    replacement_owner = f"{os.getpid() + 1}:planning_init_replacement".encode()

    def prepare(state):
        sibling.write_bytes(replacement_owner)
        state["replacement_inode"] = sibling.stat().st_ino
        assert state["replacement_inode"] != state["inode"]

    state = _watch_planner_lock_close(monkeypatch, pipeline, lock, prepare,
                                    lambda _state: os.replace(sibling, lock))

    def fail_write(fd, data):
        if fd != state.get("fd"):
            return real_write(fd, data)
        raise OSError("injected initialization write failure")

    monkeypatch.setattr(pipeline.os, "write", fail_write)
    monkeypatch.setattr(pipeline, "_bounded_process", lambda *_a, **_kw: pytest.fail("planner ran before lock initialization"))
    with pytest.raises(RuntimeError):
        pipeline._run_planning_phase(args)

    assert state["closed"] and lock.read_bytes() == replacement_owner
    assert lock.stat().st_ino == state["replacement_inode"] and not sibling.exists()
    assert not plan.exists() and not list(plan.parent.glob(".*.tmp"))


def test_pipeline_planner_missing_lock_after_close_is_harmless(planning_lock_sandbox, monkeypatch):
    pipeline, args, plan, respond = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    state = _watch_planner_lock_close(monkeypatch, pipeline, lock, after_close=lambda _state: lock.unlink())
    monkeypatch.setattr(pipeline, "_bounded_process", respond)

    pipeline._run_planning_phase(args)

    assert state["closed"] and not lock.exists() and plan.exists()
    assert not list(plan.parent.glob(".*.tmp"))


def test_pipeline_planner_owner_permission_error_preserves_lock_and_plan(planning_lock_sandbox, monkeypatch):
    pipeline, args, plan, _ = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    real_lstat = Path.lstat

    def denied(path, *args, **kwargs):
        if path == lock:
            raise PermissionError("owner verification denied")
        return real_lstat(path, *args, **kwargs)

    def deny_after_close(_state):
        monkeypatch.setattr(Path, "lstat", denied)

    args.dry_run = True
    state = _watch_planner_lock_close(monkeypatch, pipeline, lock, after_close=deny_after_close)
    monkeypatch.setattr(pipeline, "_bounded_process", lambda *_a, **_kw: pytest.fail("planner ran in dry-run"))
    with pytest.raises(RuntimeError, match="owner verification denied"):
        pipeline._run_planning_phase(args)

    assert state["closed"] and lock.read_bytes() == state["owner"]
    assert not plan.exists()


@pytest.mark.parametrize("fault", ["temp-cleanup", "plan-cleanup"], ids=["temp-cleanup", "plan-cleanup"])
def test_pipeline_planner_rollback_cleanup_fault_retains_replacement_lock(
    fault, planning_lock_sandbox, monkeypatch,
):
    pipeline, args, plan, respond = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    sibling = lock.with_name("replacement.lock")
    real_replace = os.replace
    if fault == "plan-cleanup":
        plan.parent.mkdir(parents=True)
        monkeypatch.setattr(pipeline, "_bounded_process", respond)
        real_validate = pipeline._validate_plan
        validations = 0

        def fail_after_publish(*binding):
            nonlocal validations
            validations += 1
            if validations == 2:
                raise RuntimeError("injected post-publication validation failure")
            return real_validate(*binding)

        monkeypatch.setattr(pipeline, "_validate_plan", fail_after_publish)
    else:
        monkeypatch.setattr(pipeline, "_bounded_process", respond)
        monkeypatch.setattr(
            pipeline.os, "replace",
            lambda *_args: (_ for _ in ()).throw(OSError("injected publication failure")),
        )
    real_unlink = Path.unlink
    replacement_owner = f"{os.getpid() + 1}:planning_cleanup_replacement".encode()

    def fail_cleanup(path, *args, **kwargs):
        if (fault == "temp-cleanup" and path.suffix == ".tmp") or (fault == "plan-cleanup" and path == plan):
            raise OSError("injected rollback cleanup failure")
        return real_unlink(path, *args, **kwargs)

    def prepare(state):
        sibling.write_bytes(replacement_owner)
        state["replacement_inode"] = sibling.stat().st_ino
        assert state["replacement_inode"] != state["inode"]
        state["replacement_created"] = True

    def replace_after_close(_state):
        real_replace(sibling, lock)

    state = _watch_planner_lock_close(monkeypatch, pipeline, lock, prepare, replace_after_close)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(RuntimeError, match="rollback cleanup failure"):
        pipeline._run_planning_phase(args)

    assert state["closed"] and state["replacement_created"] and lock.read_bytes() == replacement_owner
    assert lock.stat().st_ino == state["replacement_inode"] and not sibling.exists()
    if fault == "temp-cleanup":
        assert len(list(plan.parent.glob(".*.tmp"))) == 1 and not plan.exists()
    else:
        assert plan.exists() and not list(plan.parent.glob(".*.tmp"))


@pytest.mark.parametrize("outcome", ["success", "dry-run", "planner-failure"])
@pytest.mark.parametrize("fault", ["mismatch", "verification-error"])
def test_pipeline_planner_restore_reacquisition_fails_closed(outcome, fault, planning_lock_sandbox, monkeypatch):
    pipeline, _args, plan, respond = planning_lock_sandbox
    lock = plan.parent / ".implementation_plan.md.lock"
    real_replace, real_open = os.replace, Path.open
    captured, newer = [], []
    captured_owner = []

    def capture(source, target):
        if source != lock:
            return real_replace(source, target)
        if fault == "mismatch":
            sibling = lock.with_name("foreign.lock")
            sibling.write_bytes(b"captured-foreign-owner")
            real_replace(sibling, lock)
        captured_owner.append((lock.read_bytes(), lock.stat()))
        real_replace(source, target)
        captured.append(target)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            assert os.write(fd, b"new-live-owner") == len(b"new-live-owner")
            os.fsync(fd)
            newer.append(os.fstat(fd))
        finally:
            os.close(fd)

    def verify(path, *args, **kwargs):
        if path.suffix == ".trash" and fault == "verification-error":
            raise PermissionError("verification denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", capture)
    monkeypatch.setattr(Path, "open", verify)
    monkeypatch.setattr(pipeline, "_bounded_process", respond if outcome != "planner-failure" else
                        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, b"", b"planner failed"))
    monkeypatch.setattr(pipeline, "_dispatch_l2", lambda *_args: pytest.fail("unsafe cleanup reached L2"))
    argv = ["tech-lead", "code-reviewer", "SAFE_GATE", "safe_slug", "task", "file.py", "--with-plan"]
    if outcome == "dry-run":
        argv.append("--dry-run")
    assert pipeline.main(argv) == 2
    assert len(newer) == len(captured) == 1
    assert lock.read_bytes() == b"new-live-owner"
    assert (lock.stat().st_dev, lock.stat().st_ino) == (newer[0].st_dev, newer[0].st_ino)
    with real_open(captured[0], "rb") as handle:
        assert handle.read() == captured_owner[0][0]
    evidence_identity = captured_owner[0][1]
    assert (captured[0].stat().st_dev, captured[0].stat().st_ino) == (evidence_identity.st_dev, evidence_identity.st_ino)
