#!/usr/bin/env python3
"""Unit and integration tests for scripts/dispatch_l4.py."""
from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.dispatch_l4 import (
    DEFAULT_L4_MODELS,
    L4_MODEL_ALLOWLIST,
    L4_ADVISOR_ALLOWLIST,
    _generate_l4_dispatch,
    _publish_dispatch_artifacts,
    _parse_l4_cli_args,
    redact_credentials,
    validate_l4_report_advisor_model,
)


@pytest.mark.parametrize("mode", ["native", "none"], ids=["native", "none"])
def test_stage3_advisor_modes_parse_rejects_non_mcp(mode, capsys):
    with pytest.raises(SystemExit) as error:
        _parse_l4_cli_args(["backend-engineer", "GATE", "slug", "task", "scope", "--advisor-mode", mode])
    assert error.value.code == 2
    assert capsys.readouterr().err == "[ERROR] Only MCP advisor mode supported.\n"


def test_stage3_advisor_mode_mcp_parses():
    parsed = _parse_l4_cli_args(["backend-engineer", "GATE", "slug", "task", "scope", "--advisor-mode", "mcp"])
    assert parsed[9:11] == ("mcp", None)


@pytest.mark.parametrize("model", sorted(L4_ADVISOR_ALLOWLIST))
def test_stage3_explicit_advisor_requires_mcp_mode(model):
    with pytest.raises(SystemExit) as error:
        _parse_l4_cli_args(["backend-engineer", "GATE", "slug", "task", "scope", "--advisor-mode", "native", "--advisor", model])
    assert error.value.code == 2


@pytest.mark.parametrize("flags", [
    ["--advisor-mode"], ["--advisor-mode", "token=PRIVATE_CANARY"],
    ["--advisor-mode", "--no-advisor"], ["--advisor-mode", "mcp", "--advisor-mode", "native"],
    ["--advisor-mode", "native", "--advisor-mode", "native"], ["--no-advisor", "--no-advisor"],
    *(["--advisor-mode", mode, "--advisor", "opus"] for mode in ("mcp", "none")),
    *(["--advisor", "opus", "--advisor-mode", mode] for mode in ("mcp", "none")),
    *(["--advisor-mode", mode, "--no-advisor"] for mode in ("native", "mcp", "none")),
    *(["--no-advisor", "--advisor-mode", mode] for mode in ("native", "mcp", "none")),
], ids=["missing", "invalid", "flag-value", "duplicate-conflict", "duplicate-same", "duplicate-disable",
        "mcp-model", "none-model", "model-mcp", "model-none", "native-disable", "mcp-disable", "none-disable",
        "disable-native", "disable-mcp", "disable-none"])
def test_stage3_conflicts_fail_before_effects(flags, tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "resolve_l2_roles", lambda *_: pytest.fail("invalid mode reached role lookup"))
    baseline = set(tmp_path.iterdir())
    monkeypatch.setattr(sys, "argv", ["dispatch_l4.py", "backend-engineer", "GATE", "slug", "task", "scope", *flags])
    with pytest.raises(SystemExit) as error:
        dispatch.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "PRIVATE_CANARY" not in output.err and not output.out
    assert set(tmp_path.iterdir()) == baseline


@pytest.fixture
def stage3_dispatch(tmp_path, monkeypatch, capsys):
    import scripts.dispatch_l4 as dispatch

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch, "extract_prior_audit_outcomes", lambda *_: None)
    monkeypatch.setattr(dispatch, "load_sanitized_lesson_entries", lambda *_: [])
    monkeypatch.setattr(dispatch, "run_graph_predispatch_gate", lambda *_: {})
    monkeypatch.setattr(dispatch, "_existing_graph_evidence", lambda *_: {})

    def generate(mode="mcp", risk="low", dry_run=False, extra=()):
        args = ["dispatch_l4.py", "backend-engineer", "STAGE3_GATE", "stage3", "Review architecture",
                "scripts/dispatch_l4.py tests/test_dispatch_l4.py", "--risk", risk]
        if mode is not None:
            args += ["--advisor-mode", mode]
        if dry_run:
            args += ["--dry-run"]
        args += list(extra)
        monkeypatch.setattr(sys, "argv", args)
        code = dispatch.main()
        output = capsys.readouterr()
        command = output.out.split("---COMMAND---\n", 1)[1].strip() if code == 0 else ""
        return code, command, output

    return dispatch, tmp_path, generate


@pytest.mark.parametrize("mode", ["native", "none", "legacy"], ids=["native", "none", "no-advisor"])
@pytest.mark.parametrize("risk", ["low", "high"])
def test_stage5_disable_mcp_rejected_before_side_effects(mode, risk, stage3_dispatch, monkeypatch, capsys):
    dispatch, root, generate = stage3_dispatch
    with pytest.raises(SystemExit) as error:
        if mode == "legacy":
            generate("mcp", risk, extra=("--no-advisor",))
        else:
            generate(mode, risk)
    assert error.value.code == 2
    expected = "[ERROR] MCP advisor mandatory; --no-advisor unsupported.\n" if mode == "legacy" else "[ERROR] Only MCP advisor mode supported.\n"
    assert capsys.readouterr().err == expected
    assert not (root / ".ly_state").exists()


def _legacy_stage5_disabled_body(mode, risk, stage3_dispatch, monkeypatch):
    pytest.skip("legacy native/disabled advisor behavior is no longer supported")

    import socket
    from datetime import timezone
    import anyio
    from scripts import l4_mcp_advisor as advisor

    dispatch, root, generate = stage3_dispatch
    config = root / ".mcp.json"
    original_config = b'{"mcpServers":{"unrelated":{"command":"unchanged"}},"extra":true}\r\n'
    config.write_bytes(original_config)
    config_digest = hashlib.sha256(original_config).hexdigest()
    code, mcp_command, output = generate("mcp", risk)
    assert code == 0 and not output.err
    session = root / ".ly_state/session"
    receipt_directory = session / "receipts"
    receipt_directory.mkdir()
    session_id = next(session.glob("l4_*.md")).stem
    token = "stage5-private-dispatch-" + "0" * 32
    bound = advisor.LaunchAuthority("STAGE3_GATE", session_id, 9, risk,
                                    hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc))

    async def provider(payload):
        return advisor.json_bytes({"model": payload["model"], "id": "stage5-provider", "choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content": "Consistent evidence."},
        }]})

    bridge = advisor.AdvisorBridge(bound, provider, receipt_directory=receipt_directory)
    context = {"instructions": "Check supplied evidence.", "observations": []}
    value = dict(schema_version="mcp-advisor-request/v1", gate=bound.gate, session_id=session_id,
                 request_id="prior", role_id=9, risk=risk, purpose="correctness", model=advisor.MODELS[0],
                 context=context, context_sha256=hashlib.sha256(advisor.context_text(context, token).encode()).hexdigest(),
                 as_of_time="2026-01-01T00:00:00Z", dispatch_token=token)
    assert anyio.run(bridge.consult, value)["status"] == "advice" and bridge._active == 0
    original_receipts = {path.name: path.read_bytes() for path in receipt_directory.iterdir()}
    assert all(token.encode() not in raw for raw in original_receipts.values())
    original_env = dict(os.environ)

    def forbidden(*args, **kwargs):
        pytest.fail("disabled dispatch attempted MCP/provider/network activity")

    with monkeypatch.context() as patches:
        patches.setattr(dispatch, "_private_mcp_launch_command", forbidden)
        patches.setattr(dispatch, "_run_private_mcp_stdio", forbidden)
        patches.setattr(advisor.AdvisorBridge, "consult", forbidden)
        patches.setattr(socket, "getaddrinfo", forbidden)
        patches.setattr(socket, "create_connection", forbidden)
        disabled_mode = None if mode == "legacy" else mode
        code, command, output = generate(disabled_mode, risk, extra=("--no-advisor",) if mode == "legacy" else ())
    assert code == 0 and not output.err
    native = mode == "native"
    assert ("--advisor 'opus'" in command) == native
    assert "--mcp-config" not in command and "OMEGA_DISPATCH_" not in command
    prompt = next(session.glob("prompt_*.txt")).read_text(encoding="utf-8")
    assert ("NATIVE ADVISOR:" in prompt) == native and "MCP ADVISOR:" not in prompt
    assert dict(os.environ) == original_env
    assert config.read_bytes() == original_config and hashlib.sha256(config.read_bytes()).hexdigest() == config_digest
    assert {path.name: path.read_bytes() for path in receipt_directory.iterdir()} == original_receipts
    assert not list(root.rglob("*.tmp")) and not list(root.rglob("*.rollback"))
    assert not list(session.glob("*.lock"))
    # Both launch commands execute against a stub; no live model or persistent registration.
    # The old MCP command's prompt binding must fail after replacement, before Claude is called.
    retired = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              f"function claude {{ 'UNAUTHORIZED_CALL' }}; {mcp_command}"],
                             capture_output=True, text=True, timeout=30)
    assert retired.returncode == 2 and not retired.stdout
    script = ("$before = [Environment]::GetEnvironmentVariable('OMEGA_DISPATCH_TOKEN', 'Process'); "
              "function claude { $null = $input | Out-String; "
              f"if (($args -contains '--advisor') -ne ${str(native).lower()} "
              "-or $args -contains '--mcp-config') { throw 'mode' }; $global:LASTEXITCODE = 0 }; "
              f"{command}; "
              "if ([Environment]::GetEnvironmentVariable('OMEGA_DISPATCH_TOKEN', 'Process') -cne $before) { throw 'environment' }; 'ROLLBACK_OK'")
    restored = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=30)
    assert restored.returncode == 0 and restored.stdout.strip() == "ROLLBACK_OK" and not restored.stderr
    assert config.read_bytes() == original_config
    assert {path.name: path.read_bytes() for path in receipt_directory.iterdir()} == original_receipts


@pytest.mark.parametrize("mode", [None, "mcp"], ids=["default", "mcp"])
@pytest.mark.parametrize("risk", ["low", "medium", "high"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["published", "dry-run"])
def test_stage3_generated_mode_is_exclusive(mode, risk, dry_run, stage3_dispatch, monkeypatch):
    dispatch, root, generate = stage3_dispatch
    for name in ("GATE", "SESSION_ID", "ROLE_ID", "RISK", "TOKEN", "TOKEN_SHA256"):
        monkeypatch.setenv("OMEGA_DISPATCH_" + name, "AMBIENT_PRIVATE_CANARY")
    (root / ".mcp.json").write_bytes(b'{"mcpServers":{"unrelated":{}}}')
    original_env = dict(os.environ)
    code, command, output = generate(mode, risk, dry_run)
    assert code == 0 and not output.err
    assert dict(os.environ) == original_env
    assert "AMBIENT_PRIVATE_CANARY" not in output.out
    assert "ADVISOR_MODE=mcp" in output.out
    model = "opus" if risk == "high" else "sonnet"
    assert f"MODEL={model}\n" in output.out
    assert f"--model '{model}'" in command
    assert "--advisor 'opus'" not in command
    assert "--mcp-config" in command
    assert "OMEGA_DISPATCH_TOKEN" in command
    assert (root / ".mcp.json").read_bytes() == b'{"mcpServers":{"unrelated":{}}}'
    assert "--strict-mcp-config" in command
    assert "RandomNumberGenerator" in command and "finally" in command
    assert "'OMEGA_DISPATCH_ROLE_ID', '9', 'Process'" in command
    assert f"'OMEGA_DISPATCH_RISK', '{'low' if risk == 'low' else 'high'}', 'Process'" in command
    assert "--advisor 'opus'" not in command and "AMBIENT" not in command
    config_text = command.split("$__OMEGA_MCP_CONFIG = '", 1)[1].split("'; if ($PSVersionTable", 1)[0].replace("''", "'")
    config = json.loads(config_text)["mcpServers"]["omega-l4-advisor"]
    assert config["command"] == sys.executable
    assert config["args"] == [str(root / "scripts/dispatch_l4.py"), "--private-mcp-stdio"]
    assert "env" not in config
    artifacts = list((root / ".ly_state/session").glob("*"))
    assert not any(path.suffix in (".tmp", ".lock") for path in artifacts)
    if dry_run:
        assert not artifacts
    else:
        assert len(artifacts) == 4
        prompt = next(path for path in artifacts if path.suffix == ".txt").read_text(encoding="utf-8")
        assert "NATIVE ADVISOR:" not in prompt
        assert "MCP ADVISOR:" in prompt
        assert "OMEGA_DISPATCH_TOKEN" not in prompt


@pytest.mark.parametrize("mode,model", [("none", "opus"), ("bad", None), ("native", "bad")])
def test_stage3_direct_generation_rejects_conflicts_before_publication(mode, model, stage3_dispatch):
    _dispatch, root, _generate = stage3_dispatch
    baseline = set(root.iterdir())
    with pytest.raises(ValueError, match="advisor"):
        _generate_l4_dispatch(
            roles=[{"name": "backend-engineer", "role_id": 9, "role_file": ".agents/agent/backend-engineer.md", "skill_files": []}],
            gate_name="GATE", task_desc="task", scope="scope", session_id="l4_role9_stage3_20261005",
            lessons_block="lessons", risk="low", risk_reason="test", model="sonnet", advisor_model=model,
            graph_evidence={}, advisor_mode=mode,
        )
    assert set(root.iterdir()) == baseline


@pytest.mark.parametrize("fault", ["publication", "replace", "fsync", "readback", "rollback", "command"],
                         ids=["publication", "rename-failure", "fsync", "readback", "rollback", "command"])
@pytest.mark.parametrize("risk", ["low", "high"])
def test_stage3_mcp_faults_fail_closed_preserve_prior_state(fault, risk, stage3_dispatch, monkeypatch):
    dispatch, root, generate = stage3_dispatch
    code, _command, _output = generate(risk=risk)
    assert code == 0
    session = root / ".ly_state/session"
    baseline = {path.name: path.read_bytes() for path in session.iterdir()}
    original_env = dict(os.environ)

    def fail(*_a, **_kw):
        raise OSError("injected token=PRIVATE_FAULT_CANARY")

    if fault == "publication":
        monkeypatch.setattr(dispatch, "_publish_dispatch_artifacts", fail)
    elif fault == "command":
        monkeypatch.setattr(dispatch, "_private_mcp_launch_command", fail)
    elif fault == "fsync":
        monkeypatch.setattr(dispatch, "acquire_session_lock", lambda *_: None)
        monkeypatch.setattr(dispatch.os, "fsync", fail)
    elif fault in ("replace", "rollback"):
        real_replace, calls = os.replace, []

        def replace(source, target):
            calls.append(target)
            if len(calls) == 2 or fault == "rollback":
                fail()
            return real_replace(source, target)

        monkeypatch.setattr(dispatch.os, "replace", replace)
    else:
        real_read, calls = dispatch._read_artifact_bytes, []

        def read(path, limit):
            calls.append(path)
            if len(calls) == 5:
                fail()
            return real_read(path, limit)

        monkeypatch.setattr(dispatch, "_read_artifact_bytes", read)
    code, command, output = generate(risk=risk)
    assert code == 2 and not command and not output.out
    assert "PRIVATE_FAULT_CANARY" not in output.err
    assert {path.name: path.read_bytes() for path in session.iterdir()} == baseline
    assert dict(os.environ) == original_env


def test_stage3_mcp_lock_contention_preserves_owner(stage3_dispatch):
    dispatch, root, generate = stage3_dispatch
    session_id = f"l4_role9_stage3_{datetime.now().strftime('%Y%m%d')}"
    owned = dispatch.acquire_session_lock(session_id, root)
    lock = owned[0]
    owner = lock.read_bytes()
    try:
        with pytest.raises(SystemExit) as error:
            generate()
        assert error.value.code == 2
        assert lock.read_bytes() == owner
        assert list(lock.parent.iterdir()) == [lock]
    finally:
        dispatch.release_session_lock(owned)


def test_stage3_mcp_stale_lock_is_reclaimed_without_touching_live_owner(stage3_dispatch, monkeypatch):
    dispatch, root, _generate = stage3_dispatch
    session_id = "l4_role9_stale_lock_20261016"
    lock = root / ".ly_state/session" / f"dispatch_{session_id}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"123456789:" + b"a" * 32)
    monkeypatch.setattr(dispatch, "_pid_is_stale", lambda _pid: True)

    acquired = dispatch.acquire_session_lock(session_id, root)
    try:
        assert acquired[0].read_bytes() == acquired[2]
    finally:
        dispatch.release_session_lock(acquired)
    assert not lock.exists()


def test_l4_live_owner_probe_never_signals_windows_process(monkeypatch):
    import scripts.dispatch_l4 as dispatch

    if os.name == "nt":
        monkeypatch.setattr(dispatch.os, "kill", lambda *_: pytest.fail("Windows liveness sent a signal"))
    assert not dispatch._pid_is_stale(os.getpid())
    assert not dispatch._pid_is_stale(0)


@pytest.mark.skipif(os.name != "nt", reason="Windows process handles")
@pytest.mark.parametrize("fault", ["missing", "access-denied", "wait-failed", "exited"])
def test_l4_windows_owner_probe_fails_closed_and_closes_handle(fault, monkeypatch):
    import ctypes
    import scripts.dispatch_l4 as dispatch

    closed = []

    class Call:
        def __init__(self, callback):
            self.callback = callback
        def __call__(self, *args):
            return self.callback(*args)

    class Kernel:
        OpenProcess = Call(lambda *_: None if fault in ("missing", "access-denied") else 123)
        WaitForSingleObject = Call(lambda *_: 0 if fault == "exited" else 0xFFFFFFFF)
        CloseHandle = Call(lambda handle: closed.append(handle))

    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_kw: Kernel())
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87 if fault == "missing" else 5)
    assert dispatch._pid_is_stale(12345) == (fault in ("missing", "exited"))
    assert closed == ([] if fault in ("missing", "access-denied") else [123])


def test_stage3_powershell_channel_fresh_private_bound_and_restored(stage3_dispatch):
    _dispatch, _root, generate = stage3_dispatch
    code, command, _output = generate()
    assert code == 0
    # Mock only Claude; execute the generated PowerShell launch boundary itself.
    script = (
        "$script:tokens = @(); function claude { "
        "$null = $input | Out-String; "
        "if ($env:OMEGA_DISPATCH_GATE -cne 'STAGE3_GATE' -or $env:OMEGA_DISPATCH_ROLE_ID -cne '9' "
        "-or $env:OMEGA_DISPATCH_RISK -cne 'low' -or $env:OMEGA_DISPATCH_SESSION_ID -notmatch '^l4_role9_stage3_[0-9]{8}$') { throw 'authority' }; "
        "if ($env:OMEGA_DISPATCH_TOKEN -notmatch '^[0-9a-f]{64}$') { throw 'token' }; "
        "$digest = -join ([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($env:OMEGA_DISPATCH_TOKEN)) | ForEach-Object { $_.ToString('x2') }); "
        "if ($digest -cne $env:OMEGA_DISPATCH_TOKEN_SHA256 -or $args -contains $env:OMEGA_DISPATCH_TOKEN) { throw 'private-channel' }; "
        "if ($script:tokens -contains $env:OMEGA_DISPATCH_TOKEN) { throw 'reused-token' }; "
        "$script:tokens += $env:OMEGA_DISPATCH_TOKEN; $global:LASTEXITCODE = 0 }; "
        f"{command}; {command}; "
        "if ($env:OMEGA_DISPATCH_TOKEN -cne 'AMBIENT_PRIVATE_CANARY' -or $env:OMEGA_DISPATCH_GATE -cne 'AMBIENT_GATE') { throw 'restore' }; "
        "if (Test-Path Env:OMEGA_DISPATCH_TOKEN_SHA256) { throw 'missing-env-restore' }; 'CHANNEL_OK'"
    )
    environment = {key: value for key, value in os.environ.items() if not key.startswith("OMEGA_DISPATCH_")}
    environment.update(OMEGA_DISPATCH_TOKEN="AMBIENT_PRIVATE_CANARY", OMEGA_DISPATCH_GATE="AMBIENT_GATE")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CHANNEL_OK" and not result.stderr


def test_stage3_mcp_config_reaches_native_argv(stage3_dispatch):
    _dispatch, root, generate = stage3_dispatch
    code, command, _output = generate()
    assert code == 0
    child = root / "native_check.py"
    child.write_text(
        "import json, os, sys\n"
        "sys.stdin.read()\n"
        "config = json.loads(sys.argv[sys.argv.index('--mcp-config') + 1])\n"
        "assert config['mcpServers']['omega-l4-advisor']['args'][-1] == '--private-mcp-stdio'\n"
        "assert os.environ['OMEGA_DISPATCH_TOKEN'] not in str(sys.argv)\n"
        "print('NATIVE_CONFIG_OK')\n", encoding="utf-8",
    )
    command = command.replace("claude -p", f"& '{sys.executable}' '{child}' -p")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NATIVE_CONFIG_OK" and not result.stderr


@pytest.mark.parametrize("fault", ["claude-exit", "claude-throw", "prompt-tamper", "prompt-missing", "random", "hash", "environment"])
def test_stage3_powershell_launch_errors_nonzero_without_secret(fault, stage3_dispatch):
    _dispatch, root, generate = stage3_dispatch
    code, command, _output = generate()
    assert code == 0
    prompt = next((root / ".ly_state/session").glob("prompt_*.txt"))
    if fault == "prompt-tamper":
        prompt.write_bytes(b"tampered")
    elif fault == "prompt-missing":
        prompt.unlink()
    body = "$null = $input | Out-String; $global:LASTEXITCODE = 7"
    if fault == "claude-throw":
        body = "throw $env:OMEGA_DISPATCH_TOKEN"
    if fault.startswith("prompt-"):
        body = "'UNAUTHORIZED_CLAUDE_CALL'; $global:LASTEXITCODE = 0"
    if fault in ("random", "hash", "environment"):
        statement = {"random": "$__OMEGA_RNG.GetBytes($__OMEGA_RANDOM)",
                     "hash": "$__OMEGA_SHA = [System.Security.Cryptography.SHA256]::Create()",
                     "environment": "[Environment]::SetEnvironmentVariable('OMEGA_DISPATCH_TOKEN_SHA256', $__OMEGA_TOKEN_HASH, 'Process')"}[fault]
        command = command.replace(statement, "throw 'PRIVATE_ERROR_CANARY'")
        body = "'UNAUTHORIZED_CLAUDE_CALL'; $global:LASTEXITCODE = 0"
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                             f"function claude {{ {body} }}; {command}"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == (7 if fault == "claude-exit" else 2)
    assert not result.stdout and not __import__("re").search(r"\b[0-9a-f]{64}\b", result.stderr)
    assert "PRIVATE_ERROR_CANARY" not in result.stderr


@pytest.mark.parametrize("fault", ["missing", "token", "digest", "role", "risk", "gate", "session"])
def test_stage3_private_adapter_invalid_authority_exits_without_leaks(fault):
    token = "a" * 64
    env = {**os.environ, "OMEGA_DISPATCH_GATE": "GATE_TEST", "OMEGA_DISPATCH_SESSION_ID": "l4_role9_private_20261005",
           "OMEGA_DISPATCH_ROLE_ID": "9", "OMEGA_DISPATCH_RISK": "low", "OMEGA_DISPATCH_TOKEN": token,
           "OMEGA_DISPATCH_TOKEN_SHA256": hashlib.sha256(token.encode()).hexdigest()}
    if fault == "missing":
        env.pop("OMEGA_DISPATCH_TOKEN")
    else:
        key = "OMEGA_DISPATCH_" + {"token": "TOKEN", "digest": "TOKEN_SHA256", "role": "ROLE_ID", "risk": "RISK",
                                    "gate": "GATE", "session": "SESSION_ID"}[fault]
        env[key] = "PRIVATE_STARTUP_CANARY!"
    result = subprocess.run([sys.executable, "scripts/dispatch_l4.py", "--private-mcp-stdio"], env=env,
                            input="", capture_output=True, text=True, timeout=30, cwd=REPO_ROOT)
    assert result.returncode == 1 and not result.stdout
    assert result.stderr == "ERR_ADVISOR_STARTUP_OR_TRANSPORT\n"


@pytest.mark.parametrize("model", ["cx/gpt-6.1-sol", "cx/gpt-6-astra"], ids=["sol", "astra"])
@pytest.mark.parametrize("risk", ["low", "high"])
def test_stage3_private_adapter_mcp_lifecycle_token_never_enters_model_arguments(model, risk, monkeypatch):
    import io
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from scripts import l4_mcp_advisor as advisor

    token = "b" * 64
    env = {"OMEGA_DISPATCH_GATE": "GATE_TEST", "OMEGA_DISPATCH_SESSION_ID": "l4_role9_private_20261005",
           "OMEGA_DISPATCH_ROLE_ID": "9", "OMEGA_DISPATCH_RISK": risk, "OMEGA_DISPATCH_TOKEN": token,
           "OMEGA_DISPATCH_TOKEN_SHA256": hashlib.sha256(token.encode()).hexdigest(),
           "NINE_ROUTER_API_KEY": "PRIVATE_ROUTER_CANARY"}
    # Fault: CaptureIO/StringIO has no OS descriptor. Only the HTTP transport is mocked.
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    child = (
        "import httpx, json, sys; from scripts import dispatch_l4; "
        "original = httpx.AsyncClient; "
        "handler = lambda request: httpx.Response(200, json={'model': json.loads(request.content)['model'].removeprefix('cx/'), "
        "'id': 'private-provider', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Bound advice.'}}]}); "
        "httpx.AsyncClient = lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs); "
        "sys.argv = ['scripts/dispatch_l4.py', '--private-mcp-stdio']; raise SystemExit(dispatch_l4.main())"
    )

    async def scenario(errors):
        params = StdioServerParameters(command=sys.executable, args=["-c", child], env=env, cwd=str(REPO_ROOT))
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tool = (await client.list_tools()).tools[0]
                assert "dispatch_token" not in json.dumps(tool.inputSchema)
                request = dict(schema_version="mcp-advisor-request/v1", gate="GATE_TEST", session_id=env["OMEGA_DISPATCH_SESSION_ID"],
                               request_id="first", role_id=9, risk=risk, purpose="architecture", model=model,
                               context={"instructions": "Review supplied evidence.", "observations": [
                                   {"source_id": "fixture", "available_at": "2026-01-01T00:00:00Z", "data": {"price": 10}},
                               ]}, as_of_time="2026-01-01T00:00:00Z")
                request["context_sha256"] = hashlib.sha256(advisor.context_text(request["context"], token).encode()).hexdigest()
                result = await client.call_tool("consult_advisor", request)
                assert not result.isError and result.structuredContent["status"] == "advice"
                assert result.structuredContent["advice"] == "Bound advice."
                assert result.structuredContent["attempts"] == 1 and result.structuredContent["model"] == model
                advisor.validate_response(result.structuredContent, {**request, "dispatch_token": token})
                assert token not in result.model_dump_json()
                for context, code in (
                    ({"instructions": "Review 2026-01-02; price is 10; available_at: 2026-01-01T00:00:00Z", "observations": []}, "ERR_INVALID_PROVENANCE"),
                    ({"instructions": "Review supplied evidence.", "observations": [
                        {"source_id": "fixture", "available_at": "2026-01-02T00:00:00Z", "data": {"price": 10}},
                    ]}, "ERR_LOOKAHEAD_DETECTED"),
                ):
                    denied = await client.call_tool("consult_advisor", {**request, "context": context})
                    assert denied.isError and denied.content[0].text == code
                    assert denied.structuredContent is None
                for index, context in enumerate((
                    None, [], ["instructions"], 0, False, 1.5, "", " ",
                    {"instructions": None}, {"instructions": []},
                    {"instructions": "x" * 4097},
                    {"observations": None}, {"observations": {}}, {"observations": [None]},
                    {"observations": [{}]}, {"observations": [{}] * 129}, {"extra": True},
                )):
                    denied = await client.call_tool("consult_advisor", {
                        **request, "request_id": f"context-{index}", "context": context,
                    })
                    assert denied.isError and denied.content[0].text == "ERR_INVALID_ARGUMENTS"
                    assert denied.structuredContent is None and token not in denied.model_dump_json()
                for index, context in enumerate(({}, {"instructions": "Review architecture."},
                                                  {"observations": []}, "Review architecture.")):
                    accepted = await client.call_tool("consult_advisor", {
                        **request, "request_id": f"defaults-{index}", "context": context,
                    })
                    assert not accepted.isError and accepted.structuredContent["attempts"] == 1
                omitted = {key: value for key, value in request.items() if key != "context"}
                accepted = await client.call_tool("consult_advisor", {**omitted, "request_id": "omitted"})
                assert not accepted.isError
                for invalid, field in ((None, "as_of_time"), ("invalid", "purpose"), ("invalid", "model")):
                    malformed = {**request, "request_id": f"invalid-{field}", field: invalid}
                    malformed["context_sha256"] = hashlib.sha256(advisor.context_text(malformed["context"], token).encode()).hexdigest()
                    denied = await client.call_tool("consult_advisor", malformed)
                    assert denied.isError and denied.content[0].text == "ERR_INVALID_ARGUMENTS"
                for spoof in ({"dispatch_token": token}, {"gate": "OTHER_GATE"}, {"role_id": 7},
                              {"risk": "high" if risk == "low" else "low"}, {"session_id": "other"}):
                    denied = await client.call_tool("consult_advisor", {**request, **spoof, "request_id": "spoof"})
                    assert denied.isError and denied.structuredContent is None
                    assert denied.content[0].text == "ERR_UNAUTHORIZED_IDENTITY"
                    assert token not in denied.model_dump_json()
                replay = await client.call_tool("consult_advisor", request)
                assert replay.isError and replay.content[0].text == "ERR_REPLAYED_REQUEST"
    with tempfile.TemporaryFile(mode="w+b") as errors:
        anyio.run(scenario, errors)
        errors.seek(0)
        assert errors.read() == b""


@pytest.mark.parametrize("fault,code", [("success", None), ("auth", "AUTH_FAILED"),
    ("schema", "PROVIDER_SCHEMA_INVALID"), ("oversize", "RESPONSE_TOO_LARGE"), ("missing-key", None)])
def test_stage5_private_launch_provider_outcome_controls_process_exit(fault, code):
    import asyncio
    from scripts import l4_mcp_advisor as advisor

    token = "c" * 64
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env.update(OMEGA_DISPATCH_GATE="GATE_TEST", OMEGA_DISPATCH_SESSION_ID="l4_role9_private_20261005",
               OMEGA_DISPATCH_ROLE_ID="9", OMEGA_DISPATCH_RISK="high", OMEGA_DISPATCH_TOKEN=token,
               OMEGA_DISPATCH_TOKEN_SHA256=hashlib.sha256(token.encode()).hexdigest())
    if fault != "missing-key":
        env["NINE_ROUTER_API_KEY"] = "PRIVATE_ROUTER_CANARY"
    body = {"model": "gpt-6.1-sol", "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": "Bound advice."}}]}
    if fault == "schema":
        body["choices"] = []
    response = ("httpx.Response(401)" if fault == "auth" else
                f"httpx.Response(200, content=b'x' * {advisor.MAX_RESPONSE_BYTES + 1})" if fault == "oversize" else
                f"httpx.Response(200, json={body!r})")
    child = ("import httpx, sys; from scripts import dispatch_l4; original = httpx.AsyncClient; "
             f"httpx.AsyncClient = lambda **kwargs: original(transport=httpx.MockTransport(lambda _: {response}), **kwargs); "
             "sys.argv = ['scripts/dispatch_l4.py', '--private-mcp-stdio']; raise SystemExit(dispatch_l4.main())")

    async def scenario():
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", child, cwd=REPO_ROOT, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            if fault != "missing-key":
                async def exchange(frame):
                    process.stdin.write(advisor.json_bytes(frame) + b"\n")
                    await process.stdin.drain()
                    return advisor.strict_json(await asyncio.wait_for(process.stdout.readline(), 10), advisor.MAX_RESPONSE_BYTES)

                await exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "stage5", "version": "1"}}})
                process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                context = {"instructions": "Review architecture.", "observations": []}
                value = dict(schema_version="mcp-advisor-request/v1", gate="GATE_TEST", session_id=env["OMEGA_DISPATCH_SESSION_ID"],
                    role_id=9, risk="high", purpose="architecture", model=advisor.MODELS[0], request_id="first",
                    context=context, context_sha256=hashlib.sha256(advisor.context_text(context, token).encode()).hexdigest(),
                    as_of_time="2026-01-01T00:00:00Z")
                result = (await exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "consult_advisor", "arguments": value}}))["result"]
                bound = result["structuredContent"]
                advisor.validate_response(bound, {**value, "dispatch_token": token})
                assert bound["attempts"] == 1 and result["isError"] == (fault != "success")
                assert (bound["error"]["code"] if bound["error"] else None) == code
                assert token not in json.dumps(result) and "PRIVATE_ROUTER_CANARY" not in json.dumps(result)
            process.stdin.close()
            await process.stdin.wait_closed()
            await asyncio.wait_for(process.wait(), 10)
            extra = await process.stdout.read()
            errors = await process.stderr.read()
            assert process.returncode == (0 if fault == "success" else 1) and extra == b""
            assert errors.strip() == (b"ERR_ADVISOR_STARTUP_OR_TRANSPORT" if fault == "missing-key" else b"")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    asyncio.run(scenario())


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
        advisor_mode, explicit_advisor, dry_run, graph_evidence_path,
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
    assert advisor_mode == "mcp"
    assert explicit_advisor is None
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
    ]
    (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        advisor_mode, explicit_advisor, dry_run, graph_evidence_path,
        model_decision_path, model_decision_digest,
    ) = _parse_l4_cli_args(args)

    assert explicit_risk == "high"
    assert co_roles == ["tech-lead"]
    assert token_saver is True
    assert explicit_model == "opus"
    assert advisor_mode == "mcp"
    assert explicit_advisor is None


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


@pytest.mark.parametrize("fault", ["success", "open", "flush", "close", "rollback-restore", "rollback-final", "persistent"])
@pytest.mark.parametrize("prior", [False, True], ids=["new", "existing"])
def test_stage5_windows_dispatch_directory_barriers_and_rollback(tmp_path, monkeypatch, fault, prior):
    from types import SimpleNamespace
    from scripts import dispatch_l4 as dispatch, l4_mcp_advisor as advisor

    target = tmp_path / "prompt.txt"
    if prior:
        target.write_bytes(b"previous")
    events, flushes = [], []
    handle = (1 << (advisor.ctypes.sizeof(advisor.ctypes.c_void_p) * 8 - 2)) + 17

    class Function:
        def __init__(self, callback):
            self.callback = callback
        def __call__(self, *args):
            return self.callback(*args)

    def opened(*args):
        events.append(("open", args))
        return advisor.wintypes.HANDLE(-1).value if fault == "open" and len(events) == 1 else handle

    def flushed(value):
        events.append(("flush", value))
        flushes.append(target.read_bytes() if target.exists() else None)
        index = len(flushes)
        return not (fault == "persistent" or fault == "flush" and index == 1
                    or fault == "rollback-restore" and index == 2
                    or fault == "rollback-final" and index == (3 if prior else 2))

    def closed(value):
        events.append(("close", value))
        return not (fault == "close" and len(flushes) == 1)

    kernel = SimpleNamespace(CreateFileW=Function(opened), FlushFileBuffers=Function(flushed), CloseHandle=Function(closed))
    monkeypatch.setattr(advisor.ctypes, "WinDLL", lambda *_args, **_kwargs: kernel, raising=False)
    monkeypatch.setattr(dispatch, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    if fault.startswith("rollback"):
        original = dispatch._read_artifact_bytes
        monkeypatch.setattr(dispatch, "_read_artifact_bytes", lambda path, limit:
            (_ for _ in ()).throw(OSError("injected readback failure"))
            if path.read_bytes() == b"replacement" else original(path, limit))
    if fault == "success":
        _publish_dispatch_artifacts([(target, b"replacement")])
        assert flushes == [b"replacement"]
    else:
        error = RuntimeError if fault.startswith("rollback") or fault == "persistent" else OSError
        with pytest.raises(error, match="rollback failed|durability failed"):
            _publish_dispatch_artifacts([(target, b"replacement")])
        assert (target.read_bytes() if target.exists() else None) == (b"previous" if prior else None)
        assert len([event for event in events if event[0] == "open"]) >= 2
    assert kernel.CreateFileW.restype == advisor.wintypes.HANDLE
    assert events[0] == ("open", (str(tmp_path), 0xC0000000, 7, None, 3, 0x02000000, None))
    assert sum(event[0] == "close" for event in events) == len(flushes)
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows directory handles")
def test_stage5_native_windows_dispatch_flush_before_success(tmp_path, monkeypatch):
    from scripts import l4_mcp_advisor as advisor

    native, calls = advisor.sync_windows_directory, []

    def observed(directory):
        calls.append(directory)
        native(directory)

    monkeypatch.setattr(advisor, "sync_windows_directory", observed)
    target = tmp_path / "prompt.txt"
    _publish_dispatch_artifacts([(target, b"durable")])
    assert target.read_bytes() == b"durable" and calls == [tmp_path]


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
            "l4_role6_other_20261003" if binding == "session" else session_id,
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


@pytest.mark.parametrize("risk", ["low", "medium", "high"])
@pytest.mark.parametrize("lead_model", ["9router/cx/gpt-6.1-sol", "9router/cx/gpt-6-luna"])
def test_l4_dispatch_accepts_context_bound_jev_decision(tmp_path, monkeypatch, capsys, lead_model, risk):
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
        role="l2", risk="low" if risk == "low" else "high", gate="JEV_GATE", session_id=session_id,
        task="task", response={"lead_model": lead_model}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/test_dispatch_l4.py",
        "--risk", risk,
        "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", decision["decision_digest"], "--dry-run",
    ])
    assert dispatch.main() == 0
    expected_cli_model = "opus" if risk == "high" or lead_model == "9router/cx/gpt-6.1-sol" else "sonnet"
    output = capsys.readouterr()
    assert not output.err
    assert f"MODEL={expected_cli_model}\n" in output.out
    assert f"--model '{expected_cli_model}'" in output.out


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


@pytest.mark.parametrize("risk", ["low", "high"])
def test_l4_dispatch_rejects_jev_risk_mismatch_before_artifacts(tmp_path, monkeypatch, capsys, risk):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    path = tmp_path / ".ly_state/session/decision.json"
    path.parent.mkdir(parents=True)
    decision = evaluate_model_decision(
        role="l2", risk="high" if risk == "low" else "low", gate="JEV_GATE", session_id=f"l4_role6_jev_risk_{today}",
        task="task", response={}, decision_path=path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_risk", "task", "tests/",
        "--risk", risk, "--model-decision-path", ".ly_state/session/decision.json",
        "--model-decision-digest", decision["decision_digest"],
    ])
    assert dispatch.main() == 2
    assert "model decision context mismatch" in capsys.readouterr().err
    assert not list((tmp_path / ".ly_state/session").glob("prompt_*.txt"))


@pytest.mark.parametrize("risk", ["low", "high"])
def test_l4_dispatch_rejects_jev_digest_mismatch_before_artifacts(tmp_path, monkeypatch, capsys, risk):
    import scripts.dispatch_l4 as dispatch
    from scripts.jev_model_router import evaluate_model_decision

    monkeypatch.setattr(dispatch, "REPO_ROOT", tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    decision_path = tmp_path / ".ly_state/session/decision.json"
    decision_path.parent.mkdir(parents=True)
    evaluate_model_decision(
        role="l2", risk=risk, gate="JEV_GATE", session_id=f"l4_role6_jev_decision_{today}",
        task="task", response={}, decision_path=decision_path,
    )
    monkeypatch.setattr(sys, "argv", [
        "dispatch_l4.py", "system-architect", "JEV_GATE", "jev_decision", "task", "tests/",
        "--risk", risk, "--model-decision-path", ".ly_state/session/decision.json",
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


@pytest.mark.parametrize("risk", ["high", " HIGH ", None], ids=["explicit", "normalized", "inferred"])
def test_l4_high_risk_default_is_opus(risk, stage3_dispatch, monkeypatch, capsys):
    dispatch, _root, _generate = stage3_dispatch
    assert DEFAULT_L4_MODELS == {"low": "sonnet", "medium": "sonnet", "high": "opus"}
    monkeypatch.setattr(dispatch, "infer_risk", lambda _: ("high", "injected inference"))
    args = ["dispatch_l4.py", "backend-engineer", "GATE", "high_default", "task", "scripts/dispatch_l4.py"]
    if risk is not None:
        args += ["--risk", risk]
    monkeypatch.setattr(sys, "argv", args)
    assert dispatch.main() == 0
    output = capsys.readouterr()
    assert not output.err and "MODEL=opus\n" in output.out
    assert "--model 'opus'" in output.out


@pytest.mark.parametrize("entry", ["cli", "direct"])
def test_l4_high_risk_explicit_downgrade_rejected_before_effects(entry, stage3_dispatch, monkeypatch, capsys):
    dispatch, root, _generate = stage3_dispatch

    def forbidden(*_args, **_kwargs):
        pytest.fail("high-risk downgrade reached a side effect")

    for name in ("acquire_session_lock", "load_sanitized_lesson_entries", "run_graph_predispatch_gate", "extract_prior_audit_outcomes"):
        monkeypatch.setattr(dispatch, name, forbidden)
    baseline = set(root.iterdir())
    if entry == "cli":
        monkeypatch.setattr(sys, "argv", [
            "dispatch_l4.py", "backend-engineer", "GATE", "downgrade", "task", "scope",
            "--risk", "high", "--model", "sonnet",
        ])
        assert dispatch.main() == 2
        output = capsys.readouterr()
        assert "requires opus" in output.err and not output.out
    else:
        with pytest.raises(ValueError, match="requires opus"):
            _generate_l4_dispatch(
                roles=[{"name": "backend-engineer", "role_id": 9, "role_file": ".agents/agent/backend-engineer.md", "skill_files": []}],
                gate_name="GATE", task_desc="task", scope="scope", session_id="l4_role9_downgrade_20261005",
                lessons_block="lessons", risk="high", risk_reason="test", model="sonnet", advisor_model=None,
                graph_evidence={},
            )
    assert set(root.iterdir()) == baseline


@pytest.mark.parametrize("fault", ["write", "zero-write", "fsync"], ids=str)
@pytest.mark.parametrize("replacement", [False, True], ids=["owned", "foreign"])
def test_l4_lock_initialization_faults_cleanup_only_owner(fault, replacement, stage3_dispatch, monkeypatch):
    dispatch, root, generate = stage3_dispatch
    session = root / ".ly_state/session"
    session.mkdir(parents=True)
    lock = session / f"dispatch_l4_role9_stage3_{datetime.now().strftime('%Y%m%d')}.lock"
    real_write, real_close, writes, descriptors = os.write, os.close, [], []
    replacement_bytes = b"replacement-owner"

    def fail(fd, *_args):
        descriptors.append(fd)
        if fault == "zero-write":
            return 0
        raise OSError("lock failure token=PRIVATE_LOCK_CANARY")

    def close(fd):
        real_close(fd)
        if replacement and fd in descriptors:
            other = session / "replacement.tmp"
            other.write_bytes(replacement_bytes)
            os.replace(other, lock)

    monkeypatch.setattr(dispatch.os, "close", close)
    if fault == "fsync":
        monkeypatch.setattr(dispatch.os, "fsync", fail)
    else:
        def write(fd, data):
            writes.append(data)
            if len(writes) == 1:
                return real_write(fd, data[:1])
            return fail(fd)
        monkeypatch.setattr(dispatch.os, "write", write)
    code, command, output = generate(risk="high")
    assert code == 2 and not command and not output.out
    assert "PRIVATE_LOCK_CANARY" not in output.err
    assert {path.name: path.read_bytes() for path in session.iterdir()} == ({lock.name: replacement_bytes} if replacement else {})
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_l4_lock_short_writes_complete_owner_and_release(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    real_write = os.write
    monkeypatch.setattr(dispatch.os, "write", lambda fd, data: real_write(fd, data[:1]))
    owned = dispatch.acquire_session_lock("l4_role9_short_20261005", tmp_path)
    path, _identity, owner = owned
    assert path.read_bytes() == owner
    dispatch.release_session_lock(owned)
    assert not path.exists()
    dispatch.release_session_lock(owned)
    dispatch.release_session_lock(None)


def test_l4_lock_replacement_during_owner_read_is_preserved(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    owned = dispatch.acquire_session_lock("l4_role9_race_20261005", tmp_path)
    path, _identity, owner = owned
    real_rename = os.rename

    def rename(src, dst):
        # hostile swap lands between the pre-check and the atomic rename
        replacement = Path(src).with_suffix(".tmp")
        replacement.write_bytes(owner)
        os.replace(replacement, src)
        return real_rename(src, dst)

    monkeypatch.setattr(dispatch.os, "rename", rename)
    dispatch.release_session_lock(owned)
    assert path.read_bytes() == owner


@pytest.mark.parametrize("fault", ["replacement", "same-pid", "modified", "long-owner", "missing"])
@pytest.mark.parametrize("generation_error", [False, True], ids=["success", "error"])
def test_l4_lock_cleanup_preserves_replacement_owner(fault, generation_error, stage3_dispatch, monkeypatch):
    dispatch, root, generate = stage3_dispatch
    session = root / ".ly_state/session"
    lock = session / f"dispatch_l4_role9_stage3_{datetime.now().strftime('%Y%m%d')}.lock"
    replacement_bytes = str(os.getpid()).encode() if fault == "same-pid" else b"replacement-owner"
    if fault == "long-owner":
        replacement_bytes *= 10

    def injected_generation(**_kwargs):
        if fault in ("replacement", "same-pid"):
            replacement = session / "replacement.tmp"
            replacement.write_bytes(replacement_bytes)
            os.replace(replacement, lock)
        elif fault in ("modified", "long-owner"):
            lock.write_bytes(b"x" * len(lock.read_bytes()) if fault == "modified" else replacement_bytes)
        else:
            lock.unlink()
        if generation_error:
            raise RuntimeError("generation failed token=PRIVATE_GENERATION_CANARY")
        print("---COMMAND---\nmock")

    monkeypatch.setattr(dispatch, "_generate_l4_dispatch", injected_generation)
    code, _command, output = generate(risk="high")
    assert code == (2 if generation_error else 0)
    assert "PRIVATE_GENERATION_CANARY" not in output.err
    expected = b"x" * len(lock.read_bytes()) if fault == "modified" else replacement_bytes
    assert {path.name: path.read_bytes() for path in session.iterdir()} == ({} if fault == "missing" else {lock.name: expected})


def test_l4_lock_cleanup_preserves_nonregular_replacement(tmp_path):
    import scripts.dispatch_l4 as dispatch

    owned = dispatch.acquire_session_lock("l4_role9_directory_20261005", tmp_path)
    path = owned[0]
    path.unlink()
    path.mkdir()
    dispatch.release_session_lock(owned)
    assert path.is_dir()


@pytest.mark.parametrize("fault", ["metadata", "read", "unlink"])
def test_l4_lock_cleanup_io_failure_is_nonzero_and_redacted(fault, stage3_dispatch, monkeypatch):
    dispatch, root, generate = stage3_dispatch
    real_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.suffix == ".lock":
            raise PermissionError("cleanup failed token=PRIVATE_CLEANUP_CANARY")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(dispatch, "_generate_l4_dispatch", lambda **_kwargs: None)
    if fault == "unlink":
        monkeypatch.setattr(Path, "unlink", unlink)
    else:
        def fail(*_args, **_kwargs):
            raise PermissionError("cleanup failed token=PRIVATE_CLEANUP_CANARY")

        if fault == "read":
            monkeypatch.setattr(dispatch, "open", fail, raising=False)
        else:
            monkeypatch.setattr(dispatch, "release_session_lock", lambda lock: fail())
    code, command, output = generate(risk="high")
    assert code == 2 and not command and not output.out
    assert "PRIVATE_CLEANUP_CANARY" not in output.err and "[REDACTED]" in output.err
    assert len(list((root / ".ly_state/session").iterdir())) == 1


def test_l4_report_advisor_model_validation_is_independent():
    valid = "- **MCP Advisor Model**: `cx/gpt-6-astra`\n"
    assert validate_l4_report_advisor_model(valid) == []
    assert validate_l4_report_advisor_model(
        "- **MCP Advisor Model**: `cx/gpt-6.1-sol`\n"
    )
    assert validate_l4_report_advisor_model("- **MCP Advisor Model**: `cx/gpt-6-astra`\n" * 2)
    assert validate_l4_report_advisor_model(
        "- **MCP Advisor Model**: `cx/gpt-6-astra`\n", "cx/gpt-6.1-sol"
    )


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


def test_dispatch_l4_cli_execution_rejects_native_mode():
    cmd = [
        sys.executable, "scripts/dispatch_l4.py", "system-architect", "TEST_L4_GATE",
        "test_l4_slug", "Verify L4 dispatch generation", ".agents/AGENTS.md",
        "--risk", "low", "--advisor-mode", "native",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert res.returncode == 2
    assert res.stdout == ""
    assert res.stderr == "[ERROR] Only MCP advisor mode supported.\n"


def test_parse_l4_cli_args_accepts_valid_advisor():
    for advisor in L4_ADVISOR_ALLOWLIST:
        parsed = _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--advisor", advisor])
        assert parsed[10] == advisor


def test_parse_l4_cli_args_rejects_unapproved_advisor():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--advisor", "unknown-model"])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_advisor_without_value():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--advisor"])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_advisor_conflict_with_no_advisor():
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--advisor", "opus", "--no-advisor"])
    assert exc_info.value.code == 2

    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--no-advisor", "--advisor", "opus"])
    assert exc_info.value.code == 2


def test_parse_l4_cli_args_rejects_no_advisor(capsys):
    with pytest.raises(SystemExit) as exc_info:
        _parse_l4_cli_args(["system-architect", "GATE", "slug", "task", "scope", "--no-advisor"])
    assert exc_info.value.code == 2
    assert capsys.readouterr().err == "[ERROR] MCP advisor mandatory; --no-advisor unsupported.\n"


def test_dispatch_l4_cli_execution_rejects_no_advisor():
    cmd = [
        sys.executable, "scripts/dispatch_l4.py", "system-architect", "TEST_L4_GATE_NO_ADV",
        "test_l4_no_adv_slug", "Test task description no advisor", ".agents/AGENTS.md",
        "--risk", "low", "--no-advisor",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    assert res.returncode == 2
    assert res.stdout == ""
    assert res.stderr == "[ERROR] MCP advisor mandatory; --no-advisor unsupported.\n"



def test_dispatch_l4_cli_execution_with_explicit_advisor():
    cmd = [
        sys.executable,
        "scripts/dispatch_l4.py",
        "system-architect",
        "TEST_L4_GATE_ADV",
        "test_l4_adv_slug",
        "Test task description with advisor",
        ".agents/AGENTS.md",
        "--risk",
        "low",
        "--advisor",
        "cx/gpt-6-astra",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "ADVISOR_MODE=mcp" in res.stdout
    assert "ADVISOR_MODEL=cx/gpt-6-astra" in res.stdout
    assert "--mcp-config" in res.stdout
    assert "--advisor 'opus'" not in res.stdout

    today = datetime.now().strftime("%Y%m%d")
    expected_session = f"l4_role6_test_l4_adv_slug_{today}"
    (REPO_ROOT / ".ly_state" / "session" / f"prompt_{expected_session}.txt").unlink(missing_ok=True)
    (REPO_ROOT / ".ly_state" / "session" / f"{expected_session}.md").unlink(missing_ok=True)
    contract = REPO_ROOT / ".ly_state" / "session" / f"anti_drip_contract_{expected_session}.json"
    contract.unlink(missing_ok=True)
    contract.with_suffix(".sha256").unlink(missing_ok=True)


def test_dispatch_l4_help_includes_advisor():
    cmd = [sys.executable, "scripts/dispatch_l4.py", "--help"]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    assert res.returncode == 0
    assert "--advisor MODEL" in res.stdout


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


def test_dispatch_l4_resume_flags_and_behavior():
    from scripts.dispatch_l4 import _parse_l4_cli_args

    base_args = ["system-architect", "TEST_GATE", "test_slug", "Task desc", "scope.py"]
    parsed_resume = _parse_l4_cli_args(base_args + ["--resume"])
    assert parsed_resume.resume is True
    assert parsed_resume.force_new is False

    parsed_force_new = _parse_l4_cli_args(base_args + ["--force-new"])
    assert parsed_force_new.resume is False
    assert parsed_force_new.force_new is True

    with pytest.raises(SystemExit) as exc:
        _parse_l4_cli_args(base_args + ["--resume", "--force-new"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        _parse_l4_cli_args(base_args + ["--resume", "--resume"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        _parse_l4_cli_args(base_args + ["--force-new", "--force-new"])
    assert exc.value.code == 2


def test_dispatch_l4_command_resume_detection(stage3_dispatch):
    dispatch, tmp_path, generate = stage3_dispatch

    code, cmd, output = generate(extra=())
    assert code == 0
    assert "RESUME_MODE=ACTIVE" not in output.out
    assert "claude -p" in cmd
    assert "--resume" not in cmd

    code2, cmd2, output2 = generate(extra=())
    assert code2 == 0
    assert "RESUME_MODE=ACTIVE" in output2.out
    assert "--resume 'l4_role9_stage3_" in cmd2

    code3, cmd3, output3 = generate(extra=["--force-new"])
    assert code3 == 0
    assert "RESUME_MODE=BYPASSED (--force-new)" in output3.out
    assert "--resume" not in cmd3



@pytest.mark.parametrize("advisor", sorted(L4_ADVISOR_ALLOWLIST))
@pytest.mark.parametrize("risk", ["low", "high"])
def test_rem3_mcp_command_never_emits_native_advisor_and_binds_model(stage3_dispatch, advisor, risk):
    dispatch, _, generate = stage3_dispatch
    code, command, output = generate("mcp", risk, extra=("--advisor", advisor))
    assert code == 0 and f"ADVISOR_MODEL={advisor}" in output.out
    assert not re.search(r"\s--advisor(\s|$)", command)
    assert f"'OMEGA_DISPATCH_ADVISOR_MODEL', '{advisor}', 'Process'" in command
    prompt = next((stage3_dispatch[1] / ".ly_state" / "session").glob("prompt_*.txt")).read_text(encoding="utf-8")
    assert f"model {advisor}." in prompt


def test_rem3_default_advisor_model_matches_command_and_prompt(stage3_dispatch):
    dispatch, root, generate = stage3_dispatch
    code, command, _ = generate("mcp", "high")
    assert code == 0
    assert f"'OMEGA_DISPATCH_ADVISOR_MODEL', '{dispatch.DEFAULT_L4_ADVISOR}', 'Process'" in command
    assert f"model {dispatch.DEFAULT_L4_ADVISOR}." in next((root / ".ly_state" / "session").glob("prompt_*.txt")).read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", ["", "opus", "cx/gpt-6-luna", "cx/gpt-6-astra'; calc; '", None])
def test_rem3_launch_command_rejects_unapproved_advisor_model(bad):
    import scripts.dispatch_l4 as dispatch

    with pytest.raises(ValueError):
        dispatch._private_mcp_launch_command("x", "G", "S", 9, "high", bad)


@pytest.mark.parametrize("bad", ["opus", "cx/gpt-6-luna", "x" * 65, ""])
def test_rem3_build_rejects_unapproved_advisor_in_cli(bad):
    with pytest.raises(SystemExit):
        _parse_l4_cli_args(["backend-engineer", "GATE", "slug", "task", "scope", "--advisor", bad])


def test_l4_lock_release_never_deletes_foreign_after_precheck_swap(tmp_path, monkeypatch):
    import scripts.dispatch_l4 as dispatch

    owned = dispatch.acquire_session_lock("l4_role9_toctou_20261016", tmp_path)
    path = owned[0]
    real_rename = os.rename

    def rename(src, dst):
        Path(src).unlink()
        Path(src).write_bytes(b"foreign-owner-longer-than-ours-xxxxxxxxxxxxxxxxxxxxxxxx")
        return real_rename(src, dst)

    monkeypatch.setattr(dispatch.os, "rename", rename)
    dispatch.release_session_lock(owned)
    assert path.read_bytes().startswith(b"foreign-owner")
    assert [p.name for p in path.parent.iterdir()] == [path.name]


@pytest.mark.parametrize("as_of,available_at,code", [
    ("2999-01-01T00:00:00Z", None, "ERR_LOOKAHEAD_DETECTED"),
    ("not-a-timestamp", None, "ERR_INVALID_ARGUMENTS"),
    ("", None, "ERR_INVALID_ARGUMENTS"),
    (12345, None, "ERR_INVALID_ARGUMENTS"),
    ("2026-01-01T00:00:00Z", "garbage", "ERR_INVALID_ARGUMENTS"),
    ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "ERR_LOOKAHEAD_DETECTED"),
])
@pytest.mark.parametrize("nested", [False, True], ids=["top", "data"])
def test_l4_advisor_timestamps_reject_malformed_or_future_without_overwrite(as_of, available_at, code, nested):
    import scripts.dispatch_l4 as dispatch
    from scripts import l4_mcp_advisor as advisor

    obs = {"source_id": "s", "data": {}}
    if available_at is not None:
        (obs["data"] if nested else obs)["available_at"] = available_at
    ctx = {"instructions": "x", "observations": [obs]}
    req = {"as_of_time": as_of}
    cutoff = datetime(2026, 6, 1, tzinfo=advisor.timezone.utc)
    with pytest.raises(advisor.ToolError, match=code):
        dispatch._validate_advisor_timestamps(req, ctx, cutoff)
    assert req["as_of_time"] == as_of


def test_l4_advisor_timestamps_accept_boundary_inclusive():
    import scripts.dispatch_l4 as dispatch
    from scripts import l4_mcp_advisor as advisor

    ctx = {"observations": [{"available_at": "2026-06-01T00:00:00Z", "data": {"available_at": "2026-06-01T00:00:00Z"}}]}
    dispatch._validate_advisor_timestamps({"as_of_time": "2026-06-01T00:00:00Z"}, ctx,
                                          datetime(2026, 6, 1, tzinfo=advisor.timezone.utc))
