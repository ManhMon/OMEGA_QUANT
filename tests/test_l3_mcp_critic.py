"""Adversarial L3 policy, stdio, durability and dispatch regression checks."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from scripts import dispatch_l3, l3_mcp_critic as critic, l4_mcp_advisor as advisor

TOKEN = "private_launch_value_" + "x" * 32
NOW = datetime(2026, 10, 11, 11, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def strict_pit(monkeypatch):
    monkeypatch.delenv("OMEGA_ADVISOR_SKIP_PIT", raising=False)
    monkeypatch.setattr(critic.transport, "utc_now", lambda: NOW)


def authority(role=21, risk="high"):
    return critic.LaunchAuthority("GATE_TEST", "l3_role21_test", role, risk,
                                  hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)


def request(**changes):
    context = {"instructions": "Challenge implementation correctness.", "observations": [
        {"source_id": "implementation", "available_at": "2026-10-11T11:00:00Z", "data": {"value": 0}}]}
    result = dict(schema_version="mcp-advisor-request/v1", gate="GATE_TEST", session_id="l3_role21_test",
                  request_id="critic_01", role_id=21, risk="high", purpose="adversarial_critique",
                  model="cx/gpt-6.1-sol", context=context,
                  context_sha256=hashlib.sha256(critic.transport.context_text(context, TOKEN).encode()).hexdigest(),
                  as_of_time="2026-10-11T11:00:00Z")
    result.update(changes)
    return result


def run(awaitable):
    async def execute():
        return await awaitable
    return anyio.run(execute)


async def provider(payload):
    assert payload["messages"][0]["content"].startswith("Adversarial critique:")
    assert TOKEN not in json.dumps(payload)
    return json.dumps({"model": payload["model"], "id": "response_01", "choices": [
        {"finish_reason": "stop", "message": {"role": "assistant", "content": "Check rollback after publication failure."}}]}).encode()


def bridge(tmp_path=None, role=21, risk="high", **kwargs):
    return critic.CriticBridge(authority(role, risk), provider, token=TOKEN,
                               clock=lambda: NOW, receipt_directory=tmp_path, **kwargs)


@pytest.mark.parametrize("role", range(17, 31))
@pytest.mark.parametrize("model", critic.MODELS)
def test_all_l3_roles_models_and_l4_isolation(role, model):
    response = run(bridge(role=role).consult(request(role_id=role, model=model)))
    assert response["status"] == "advice"
    assert response["role_id"] == role
    assert response["purpose"] == "adversarial_critique"
    assert "not approval" in response["limitations"][0]
    critic.transport.validate_response(response, {**request(role_id=role, model=model), "dispatch_token": TOKEN})
    assert advisor.ROLE_SCHEMA == {"type": "integer", "minimum": 6, "maximum": 16}
    assert "adversarial_critique" not in advisor.PURPOSES


@pytest.mark.parametrize("role", [None, False, 16, 31, 21.0, "21", [], float("nan"), float("inf"), -1, 10**13])
def test_invalid_authority_role(role):
    with pytest.raises(critic.ToolError):
        authority(role)


@pytest.mark.parametrize("key,value", [
    ("gate", "OTHER"), ("session_id", "other"), ("role_id", 20), ("role_id", True), ("risk", "low"),
    ("purpose", "architecture"), ("purpose", None), ("model", "cx/gpt-6-luna"), ("model", "--run"),
    ("dispatch_token", TOKEN), ("extra", {}), ("context", None), ("context_sha256", "0" * 64),
    ("as_of_time", "2026-10-11T11:00:01Z"), ("as_of_time", "2026-10-11T15:30:00+07:00")])
def test_invalid_request_has_no_provider_or_receipt_side_effect(tmp_path, key, value):
    calls = []
    async def forbidden(payload):
        calls.append(payload)
        raise AssertionError("provider must not run")
    instance = critic.CriticBridge(authority(), forbidden, token=TOKEN, receipt_directory=tmp_path)
    with pytest.raises(critic.ToolError):
        run(instance.consult(request(**{key: value})))
    assert calls == []
    assert instance.failed
    assert not (tmp_path / "l3_role21_test.json").exists()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 2**54, "﻿", "\ud800"])
def test_nonfinite_overflow_encoding_faults(value):
    item = request()
    item["context"]["observations"][0]["data"]["value"] = value
    with pytest.raises(critic.ToolError):
        run(bridge().consult(item))


@pytest.mark.parametrize("raw", [b"", b"[]", b"null", b"\xff", b"\xef\xbb\xbf{}", b'{"a":1,"a":2}', b"{" * 70000],
                         ids=["empty", "list", "null", "utf8", "bom", "duplicate", "oversized"])
def test_malformed_bounded_json(raw):
    with pytest.raises(critic.ToolError):
        run(bridge().consult(raw))


def test_cutoff_inclusive_batch_and_nested_provenance():
    assert run(bridge().consult(request()))["status"] == "advice"
    for data in [{"available_at": "2026-10-11T11:00:01Z", "source_id": "later"},
                 {"available_at": "2026-10-11T11:00:00Z"}, {"source_id": "unbound"}]:
        item = request()
        item["context"]["observations"][0]["data"] = data
        item["context_sha256"] = hashlib.sha256(critic.transport.context_text(item["context"], TOKEN).encode()).hexdigest()
        with pytest.raises(critic.ToolError):
            run(bridge().consult(item))


def test_skip_pit_cannot_widen_critic(monkeypatch):
    monkeypatch.setenv("OMEGA_ADVISOR_SKIP_PIT", "1")
    with pytest.raises(critic.ToolError):
        run(bridge().consult(request(as_of_time="2099-01-01T00:00:00Z")))


def fresh_request(as_of="2026-10-11T11:02:00Z", available="2026-10-11T11:01:00Z", **changes):
    item = request(as_of_time=as_of, **changes)
    item["context"]["observations"][0]["available_at"] = available
    item["context_sha256"] = hashlib.sha256(
        critic.transport.context_text(item["context"], TOKEN).encode()).hexdigest()
    return item


def test_fresh_test_evidence_after_launch_before_consultation(tmp_path, monkeypatch):
    consultation = NOW + timedelta(minutes=2)
    monkeypatch.setattr(critic.transport, "utc_now", lambda: consultation)
    instance = critic.CriticBridge(authority(), provider, token=TOKEN,
                                  clock=lambda: consultation, receipt_directory=tmp_path)
    binding = instance.receipts.binding
    item = fresh_request()
    response = run(instance.consult(item))
    assert response["status"] == "advice"
    assert response["as_of_time"] == item["as_of_time"]
    assert instance.authority.current_session_started_at == NOW
    assert instance.receipts.binding == binding
    assert instance.receipts.read({**item, "dispatch_token": TOKEN})["status"] == "advice"
    ledger = json.loads(instance.receipts.path.read_bytes())
    assert ledger["entries"][0]["consultation_cutoff"] == "2026-10-11T11:02:00.000Z"
    assert critic._consultation_cutoff.get() is None
    l4_request = {**item, "role_id": 9, "purpose": "correctness", "dispatch_token": TOKEN}
    l4_authority = advisor.LaunchAuthority("GATE_TEST", "l3_role21_test", 9, "high",
                                         hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
    with pytest.raises(advisor.ToolError, match="ERR_LOOKAHEAD_DETECTED"):
        advisor.accepted_context(l4_request, l4_authority)


@pytest.mark.parametrize("fault", ["asof", "observation", "nested", "current_utc", "override"])
def test_trusted_consultation_cutoff_rejects_future_without_side_effects(tmp_path, monkeypatch, fault):
    consultation = NOW + timedelta(minutes=2)
    monkeypatch.setattr(critic.transport, "utc_now", lambda: consultation)
    calls = []
    async def forbidden(payload):
        calls.append(payload)
        raise AssertionError("future evidence reached provider")
    clock = consultation
    item = fresh_request()
    if fault == "asof":
        item["as_of_time"] = "2026-10-11T11:02:01Z"
    elif fault == "observation":
        item = fresh_request(available="2026-10-11T11:02:01Z")
    elif fault == "nested":
        item["context"]["observations"][0]["data"] = {
            "nested": [{"source_id": "later", "available_at": "2026-10-11T11:02:01Z"}]}
    elif fault == "current_utc":
        clock = consultation + timedelta(days=1)
        item = fresh_request(as_of="2026-10-11T11:02:01Z")
    else:
        item["consultation_cutoff"] = "2099-01-01T00:00:00Z"
    item["context_sha256"] = hashlib.sha256(
        critic.transport.context_text(item["context"], TOKEN).encode()).hexdigest()
    instance = critic.CriticBridge(authority(), forbidden, token=TOKEN,
                                  clock=lambda: clock, receipt_directory=tmp_path)
    with pytest.raises(critic.ToolError):
        run(instance.consult(item))
    assert not calls and not instance._requests and instance._active == 0
    assert not instance.receipts.path.exists()
    assert instance.failed and critic._consultation_cutoff.get() is None


@pytest.mark.parametrize("clock", [None, "", 0, -1, 10**13, float("nan"), float("inf"),
                                    -float("inf"), datetime(2026, 10, 11)])
def test_invalid_consultation_clock_fails_closed(clock):
    instance = critic.CriticBridge(authority(), provider, token=TOKEN, clock=lambda: clock)
    with pytest.raises(critic.ToolError, match="ERR_INVALID_ARGUMENTS"):
        run(instance.consult(request()))
    assert instance.failed and not instance._requests
    assert critic._consultation_cutoff.get() is None


@pytest.mark.parametrize("cutoff", [NOW, NOW.astimezone(timezone(timedelta(hours=7))),
                                    NOW + timedelta(microseconds=999)])
def test_consultation_cutoff_inclusive_timezone_precision(tmp_path, monkeypatch, cutoff):
    monkeypatch.setattr(critic.transport, "utc_now", lambda: cutoff)
    instance = critic.CriticBridge(authority(), provider, token=TOKEN,
                                  clock=lambda: cutoff, receipt_directory=tmp_path)
    assert run(instance.consult(request()))["status"] == "advice"
    assert instance.receipts.read({**request(), "dispatch_token": TOKEN})


def test_overlapping_consultations_keep_reserved_cutoffs(tmp_path, monkeypatch):
    times = [NOW + timedelta(minutes=2)]
    monkeypatch.setattr(critic.transport, "utc_now", lambda: times[0])
    async def execute():
        entered, release = anyio.Event(), anyio.Event()
        async def interleave(payload):
            if "first" in payload["messages"][1]["content"]:
                entered.set()
                await release.wait()
            return await provider(payload)
        instance = critic.CriticBridge(authority(), interleave, token=TOKEN,
                                      clock=lambda: times[0], receipt_directory=tmp_path)
        first = fresh_request(request_id="first")
        first["context"]["observations"][0]["data"] = "first"
        first["context_sha256"] = hashlib.sha256(
            critic.transport.context_text(first["context"], TOKEN).encode()).hexdigest()
        async with anyio.create_task_group() as group:
            group.start_soon(instance.consult, first)
            await entered.wait()
            times[0] += timedelta(minutes=1)
            second = fresh_request(as_of="2026-10-11T11:03:00Z", request_id="second")
            assert (await instance.consult(second))["status"] == "advice"
            # An earlier frozen request may finish after a later reservation.
            release.set()
        entries = json.loads(instance.receipts.path.read_bytes())["entries"]
        assert [entry["consultation_cutoff"] for entry in entries] == [
            "2026-10-11T11:02:00.000Z", "2026-10-11T11:03:00.000Z"]
        assert all(entry["response"] is not None for entry in entries)
        assert instance._active == 0 and critic._consultation_cutoff.get() is None
    anyio.run(execute)


@pytest.mark.parametrize("fault", ["missing", "before_asof", "future", "digest"])
def test_consultation_receipt_cutoff_tamper_fails_closed(tmp_path, monkeypatch, fault):
    consultation = NOW + timedelta(minutes=2)
    monkeypatch.setattr(critic.transport, "utc_now", lambda: consultation)
    instance = critic.CriticBridge(authority(), provider, token=TOKEN,
                                  clock=lambda: consultation, receipt_directory=tmp_path)
    item = fresh_request()
    run(instance.consult(item))
    ledger = json.loads(instance.receipts.path.read_bytes())
    if fault == "missing":
        del ledger["entries"][0]["consultation_cutoff"]
    else:
        ledger["entries"][0]["consultation_cutoff"] = (
            "2026-10-11T11:01:59.999Z" if fault == "before_asof" else "2026-10-11T11:02:00.001Z")
    if fault != "digest":
        ledger["receipt_sha256"] = hashlib.sha256(critic.transport.json_bytes(
            {key: value for key, value in ledger.items() if key != "receipt_sha256"})).hexdigest()
    instance.receipts.path.write_bytes(critic.transport.json_bytes(ledger))
    with pytest.raises(critic.ToolError, match="ERR_RECEIPT_INVALID"):
        instance.receipts.read({**item, "dispatch_token": TOKEN})


def test_fresh_receipt_rollback_recovery_and_clock_rollback(tmp_path, monkeypatch):
    times = [NOW + timedelta(minutes=2)]
    monkeypatch.setattr(critic.transport, "utc_now", lambda: times[0])
    instance = critic.CriticBridge(authority(), provider, token=TOKEN,
                                  clock=lambda: times[0], receipt_directory=tmp_path)
    item = fresh_request()
    run(instance.consult(item))
    prior = instance.receipts.path.read_bytes()
    instance.receipts.rollback_path.write_bytes(prior)
    instance.receipts.path.write_bytes(b"corrupted interrupted replacement")
    instance.receipts.recover()
    assert instance.receipts.path.read_bytes() == prior
    times[0] -= timedelta(seconds=1)
    with pytest.raises(critic.ToolError):
        instance.receipts.read({**item, "dispatch_token": TOKEN})
    assert instance.receipts.path.read_bytes() == prior


def test_fresh_consultation_cancellation_preserves_cutoff_and_replay(tmp_path, monkeypatch):
    times = [NOW + timedelta(minutes=2)]
    monkeypatch.setattr(critic.transport, "utc_now", lambda: times[0])
    async def execute():
        entered = anyio.Event()
        async def blocked(payload):
            entered.set()
            await anyio.sleep_forever()
        instance = critic.CriticBridge(authority(), blocked, token=TOKEN,
                                      clock=lambda: times[0], receipt_directory=tmp_path)
        item = fresh_request()
        async with anyio.create_task_group() as group:
            group.start_soon(instance.consult, item)
            await entered.wait()
            times[0] += timedelta(minutes=1)
            group.cancel_scope.cancel()
        assert instance._active == 0 and instance.failed
        entries = json.loads(instance.receipts.path.read_bytes())["entries"]
        assert entries[0]["consultation_cutoff"] == "2026-10-11T11:02:00.000Z"
        assert entries[0]["response"] is None
        assert instance.receipts.read({**item, "dispatch_token": TOKEN}) is None
        with pytest.raises(critic.ToolError, match="ERR_REPLAYED_REQUEST"):
            await instance.consult(item)
        assert critic._consultation_cutoff.get() is None
    anyio.run(execute)


@pytest.mark.parametrize("fault", ["atomic_swap", "fsync", "directory", "publish"])
def test_fresh_consultation_publication_faults_preserve_prior(tmp_path, monkeypatch, fault):
    consultation = NOW + timedelta(minutes=2)
    monkeypatch.setattr(critic.transport, "utc_now", lambda: consultation)
    instance = critic.CriticBridge(authority(), provider, token=TOKEN,
                                  clock=lambda: consultation, receipt_directory=tmp_path)
    item = fresh_request()
    run(instance.consult(item))
    prior = instance.receipts.path.read_bytes()
    def fail(*args):
        raise OSError("injected receipt failure")
    if fault == "atomic_swap":
        monkeypatch.setattr(critic.transport.os, "replace", fail)
    elif fault == "fsync":
        monkeypatch.setattr(critic.transport.os, "fsync", fail)
    elif fault == "directory":
        monkeypatch.setattr(instance.receipts, "_sync_directory", fail)
    else:
        def publish_failure(*args):
            raise critic.ToolError("ERR_RECEIPT_IO")
        monkeypatch.setattr(instance.receipts, "publish", publish_failure)
    with pytest.raises(critic.ToolError):
        run(instance.consult(fresh_request(request_id="second")))
    entries = json.loads(instance.receipts.path.read_bytes())["entries"]
    assert entries[0] == json.loads(prior)["entries"][0]
    assert not list(tmp_path.glob("*.tmp"))
    assert instance.failed and instance._active == 0
    assert critic._consultation_cutoff.get() is None


def test_receipt_validation_cannot_use_pit_bypass(tmp_path, monkeypatch):
    import json
    instance = bridge(tmp_path)
    run(instance.consult(request()))
    prior = instance.receipts.path.read_bytes()
    raw = json.loads(prior.decode("utf-8"))
    raw["entries"][0]["request"]["as_of_time"] = "2099-01-01T00:00:00Z"
    instance.receipts.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(critic.ToolError, match="ERR_RECEIPT_INVALID"):
        instance.receipts.read({**request(), "dispatch_token": TOKEN})


def test_environment_snapshot_and_wrong_private_token():
    env = dict(OMEGA_DISPATCH_GATE="GATE_TEST", OMEGA_DISPATCH_SESSION_ID="l3_role21_test",
               OMEGA_DISPATCH_ROLE_ID="21", OMEGA_DISPATCH_RISK="high",
               OMEGA_DISPATCH_TOKEN_SHA256=hashlib.sha256(TOKEN.encode()).hexdigest())
    launch = critic.LaunchAuthority.from_environment(env)
    env["OMEGA_DISPATCH_ROLE_ID"] = "9"
    assert launch.role_id == 21
    with pytest.raises(critic.ToolError):
        critic.LaunchAuthority.from_environment(env)
    with pytest.raises(critic.ToolError):
        critic.CriticBridge(launch, token="z" * 32)
    assert TOKEN not in repr(launch)


def test_receipt_readback_replay_tamper_and_fresh_launch(tmp_path):
    instance = bridge(tmp_path)
    response = run(instance.consult(request()))
    stored = instance.receipts.read({**request(), "dispatch_token": TOKEN})
    assert stored["response_sha256"] == response["response_sha256"]
    raw = instance.receipts.path.read_bytes()
    assert TOKEN.encode() not in raw
    assert b"Check rollback" not in raw
    with pytest.raises(critic.ToolError, match="ERR_REPLAYED_REQUEST"):
        run(instance.consult(request()))
    second = bridge(tmp_path)
    with pytest.raises(critic.ToolError):
        run(second.consult(request()))
    fresh = critic.LaunchAuthority("GATE_TEST", "l3_role21_test", 21, "high", "0" * 64, NOW)
    fresh_store = critic.transport.ReceiptStore(tmp_path, fresh)
    with pytest.raises(critic.ToolError):
        fresh_store.read({**request(), "dispatch_token": TOKEN})
    damaged = json.loads(raw)
    damaged["entries"][0]["response"]["role_id"] = 22
    instance.receipts.path.write_text(json.dumps(damaged), encoding="utf-8")
    with pytest.raises(critic.ToolError):
        instance.receipts.read({**request(), "dispatch_token": TOKEN})


@pytest.mark.parametrize("fault", ["replace", "fsync", "directory", "publish"])
def test_receipt_failures_fail_closed(tmp_path, monkeypatch, fault):
    instance = bridge(tmp_path)
    if fault == "replace":
        monkeypatch.setattr(critic.transport.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("private URL")))
    elif fault == "fsync":
        monkeypatch.setattr(critic.transport.os, "fsync", lambda *args: (_ for _ in ()).throw(OSError("private URL")))
    elif fault == "directory":
        monkeypatch.setattr(instance.receipts, "_sync_directory", lambda: (_ for _ in ()).throw(OSError("private URL")))
    else:
        monkeypatch.setattr(instance.receipts, "publish", lambda *args: (_ for _ in ()).throw(critic.ToolError("ERR_RECEIPT_IO")))
    with pytest.raises(critic.ToolError):
        run(instance.consult(request()))
    assert instance.failed
    assert not list(tmp_path.glob("*.tmp"))


def test_retries_timeout_redaction_and_no_high_risk_fallback():
    attempts = []
    async def unavailable(payload):
        attempts.append(payload)
        raise critic.ProviderFailure("RATE_LIMITED", 0)
    async def no_sleep(delay):
        assert 1 <= delay <= 4
    instance = critic.CriticBridge(authority(), unavailable, token=TOKEN, sleep=no_sleep, jitter=lambda: 1)
    response = run(instance.consult(request()))
    assert response["status"] == "error"
    assert response["attempts"] == 3
    assert len(attempts) == 3
    assert instance.failed
    with pytest.raises(critic.ToolError):
        bridge(fallback_model="cx/gpt-6-astra")
    async def timeout(payload):
        raise TimeoutError("https://user:private@example.invalid/")
    instance = critic.CriticBridge(authority(), timeout, token=TOKEN, sleep=no_sleep, jitter=lambda: 1)
    response = run(instance.consult(request()))
    assert response["error"]["code"] == "TIMEOUT"
    assert "private" not in json.dumps(response)


def test_capacity_duplicate_cancellation_and_release():
    async def execute():
        entered = anyio.Event()
        blocked = anyio.Event()
        async def slow(payload):
            entered.set()
            await blocked.wait()
            return await provider(payload)
        instance = critic.CriticBridge(authority(), slow, token=TOKEN)
        async with anyio.create_task_group() as group:
            group.start_soon(instance.consult, request())
            await entered.wait()
            with pytest.raises(critic.ToolError, match="ERR_REPLAYED_REQUEST"):
                await instance.consult(request())
            instance._active = critic.transport.MAX_CONCURRENT
            with pytest.raises(critic.ToolError, match="ERR_CAPACITY_EXCEEDED"):
                await instance.consult(request(request_id="second"))
            instance._active = 1
            group.cancel_scope.cancel()
        assert instance._active == 0
        assert instance.failed
    anyio.run(execute)


def test_resource_bounds_and_strict_stdin():
    for raw in [b"x" * 70000 + b"\n", b"\xff\n", b"{}"]:
        source = critic.transport.StrictStdin(io.BytesIO(raw))
        with pytest.raises((critic.ToolError, UnicodeError, ValueError)):
            async def read():
                return [line async for line in source]
            run(read())
    item = request()
    item["context"]["observations"] *= 129
    with pytest.raises(critic.ToolError):
        run(bridge().consult(item))


@pytest.mark.parametrize("role", [17, 30])
def test_codex_sparse_config_merge_public_binding(role):
    override = dispatch_l3._critic_mcp_config("GATE_TEST", "l3_test", role, "medium")
    parsed = tomllib.loads(override)["mcp_servers"]["omega-l3-critic"]
    assert parsed["required"] and parsed["enabled_tools"] == ["consult_critic"]
    assert parsed["env"]["OMEGA_DISPATCH_RISK"] == "high"
    assert "OMEGA_DISPATCH_TOKEN" not in override
    assert parsed["env_vars"] == ["NINE_ROUTER_API_KEY", "9ROUTER_API_KEY", "ROUTER_API_KEY",
                                  "OMEGA_LLM_BASE_URL", "OMEGA_LLM_API_KEY"]
    assert "l4" not in override
    assert override.startswith("mcp_servers.omega-l3-critic =")
    assert "--ignore-user-config" not in override


@pytest.mark.parametrize("role", [16, 31, True, "21"])
def test_codex_config_invalid_role(role):
    with pytest.raises(ValueError):
        dispatch_l3._critic_mcp_config("GATE_TEST", "l3_test", role, "high")


def test_dispatch_exec_resume_injection_and_verified_prompt(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dispatch_l3, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dispatch_l3, "load_sanitized_lesson_entries", lambda *args: [])
    monkeypatch.setattr(dispatch_l3, "build_graph_prompt_evidence", lambda graph: "verified graph")
    for resume in (False, True):
        dispatch_l3._dispatch_l3_body(
            "code-reviewer", "backend-engineer", "GATE_TEST", "l4_role9_test", "scripts/l3_mcp_critic.py",
            21, 9, "l3_role21_test", ".ly_state/session/audit_reports/test.md", "high", "explicit",
            "cx/gpt-6.1-sol", True, False, {}, resume=resume)
        output = capsys.readouterr().out
        assert "-c $__OMEGA_CRITIC_CONFIG" in output
        assert "omega-l3-critic" in output
        assert "OMEGA_DISPATCH_TOKEN" not in output
        assert ("codex exec resume --last" in output) == resume
        assert "Get-Content" not in output.split("---COMMAND---")[1]
        prompt = (tmp_path / ".ly_state/session/prompt_l3_role21_test.txt").read_text(encoding="utf-8")
        assert "purpose=adversarial_critique" in prompt
        assert "Required critic errors block completion" in prompt
        assert "available_at <= as_of_time <= consultation cutoff" in prompt
        assert "not startup time" in prompt


def test_startup_missing_authority_and_cli_fail_nonzero():
    script = Path(critic.__file__)
    for args in ([], ["--role", "21"]):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("OMEGA_DISPATCH_")}
        result = subprocess.run([sys.executable, str(script), *args], env=env, capture_output=True,
                                timeout=30, text=True)
        assert result.returncode != 0
        assert result.stdout == ""
        assert "ERR_CRITIC_STARTUP_OR_TRANSPORT" in result.stderr


def test_low_risk_fallback_and_secret_safe_critique():
    models = []
    async def fallback(payload):
        models.append(payload["model"])
        if len(models) == 1:
            raise critic.ProviderFailure("MODEL_UNAVAILABLE")
        return await provider(payload)
    async def no_sleep(delay):
        pass
    instance = critic.CriticBridge(authority(risk="low"), fallback, token=TOKEN,
                                  fallback_model="cx/gpt-6-astra", sleep=no_sleep, jitter=lambda: 1)
    response = run(instance.consult(request(risk="low")))
    # MODEL_UNAVAILABLE is not transient; fallback must not hide catalog failures.
    assert response["status"] == "error"
    assert models == ["cx/gpt-6.1-sol"]
    async def echo(payload):
        return json.dumps({"model": payload["model"], "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": "Bearer " + TOKEN}}]}).encode()
    instance = critic.CriticBridge(authority(), echo, token=TOKEN)
    response = run(instance.consult(request()))
    assert TOKEN not in json.dumps(response)


def test_receipt_failed_update_preserves_prior(tmp_path, monkeypatch):
    instance = bridge(tmp_path)
    run(instance.consult(request()))
    prior = instance.receipts.path.read_bytes()
    original = critic.transport.os.replace
    def reject_new(source, target):
        if Path(target) == instance.receipts.path and Path(source).name.endswith(".tmp"):
            raise OSError("replacement unavailable")
        return original(source, target)
    monkeypatch.setattr(critic.transport.os, "replace", reject_new)
    with pytest.raises(critic.ToolError):
        run(instance.consult(request(request_id="second")))
    assert instance.receipts.path.read_bytes() == prior
    assert instance.failed


def test_directory_receipt_rejected_before_provider(tmp_path):
    (tmp_path / "l3_role21_test.json").mkdir()
    with pytest.raises(critic.ToolError):
        run(bridge(tmp_path).consult(request()))


def test_main_private_launch_new_directory_and_nonzero_empty_session(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / ".ly_state/session").mkdir(parents=True)
    monkeypatch.setattr(critic, "__file__", str(scripts / "l3_mcp_critic.py"))
    monkeypatch.setattr(sys, "argv", ["l3_mcp_critic.py"])
    for key, value in {"OMEGA_DISPATCH_GATE": "GATE_TEST", "OMEGA_DISPATCH_SESSION_ID": "l3_role21_test",
                       "OMEGA_DISPATCH_ROLE_ID": "21", "OMEGA_DISPATCH_RISK": "high"}.items():
        monkeypatch.setenv(key, value)
    directories = []
    async def empty(launch, *, token, receipt_directory):
        directories.append(receipt_directory)
        assert TOKEN != token
        assert "OMEGA_DISPATCH_TOKEN" not in os.environ
        launch.authorize({"gate": launch.gate, "session_id": launch.session_id,
                          "role_id": launch.role_id, "risk": launch.risk, "dispatch_token": token})
        return True
    monkeypatch.delenv("OMEGA_DISPATCH_TOKEN", raising=False)
    monkeypatch.setattr(critic, "run_stdio", empty)
    assert critic.main() == 1
    assert critic.main() == 1
    assert directories[0] != directories[1]
    assert all(path.is_relative_to(tmp_path / ".ly_state/session/l3_critic_receipts") for path in directories)


def test_official_mcp_fresh_evidence_success_and_future_rejection(tmp_path):
    wrapper = tmp_path / "critic_success.py"
    wrapper.write_text(
        f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
        "from scripts import l3_mcp_critic as c\n"
        "from datetime import datetime, timezone\n"
        "import json\n"
        "c.transport.utc_now = lambda: datetime(2026, 10, 11, 11, 2, tzinfo=timezone.utc)\n"
        "async def provider(payload):\n"
        " return json.dumps({'model': payload['model'], 'choices': [{'finish_reason': 'stop', "
        "'message': {'role': 'assistant', 'content': 'Fresh evidence received; inspect rollback gaps.'}}]}).encode()\n"
        f"authority = c.LaunchAuthority('GATE_TEST', 'l3_role21_test', 21, 'high', "
        f"{hashlib.sha256(TOKEN.encode()).hexdigest()!r}, datetime(2026, 10, 11, 11, tzinfo=timezone.utc))\n"
        f"bridge = c.CriticBridge(authority, provider, token={TOKEN!r}, clock=c.transport.utc_now, "
        f"receipt_directory={str(tmp_path)!r})\n"
        "async def serve():\n"
        " async with c.transport.stdio_server(stdin=c.transport.StrictStdin(sys.stdin.buffer)) as (read, write):\n"
        "  server = c.create_server(bridge)\n"
        "  await server.run(read, write, server.create_initialization_options())\n"
        "c.transport.anyio.run(serve)\n", encoding="utf-8")
    async def execute():
        parameters = StdioServerParameters(command=sys.executable, args=[str(wrapper)])
        async with stdio_client(parameters, errlog=sys.__stderr__) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("consult_critic", fresh_request())
                assert not result.isError and result.structuredContent["status"] == "advice"
                assert "not approval" in result.structuredContent["limitations"][0]
                rejected = await session.call_tool("consult_critic", fresh_request(
                    as_of="2026-10-11T11:02:01Z", request_id="future"))
                assert rejected.isError and "ERR_LOOKAHEAD_DETECTED" in str(rejected)
        entries = json.loads((tmp_path / "l3_role21_test.json").read_bytes())["entries"]
        assert len(entries) == 1 and entries[0]["response"]["status"] == "advice"
    anyio.run(execute)


def test_official_mcp_lifecycle_tool_schema_and_error_exit(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / ".ly_state" / "session").mkdir(parents=True)
    for source in (Path(critic.__file__), Path(advisor.__file__)):
        (scripts / source.name).write_bytes(source.read_bytes())
    async def execute():
        env = dict(OMEGA_DISPATCH_GATE="GATE_TEST", OMEGA_DISPATCH_SESSION_ID="l3_role21_test",
                   OMEGA_DISPATCH_ROLE_ID="21", OMEGA_DISPATCH_RISK="high", NINE_ROUTER_API_KEY="test-placeholder")
        parameters = StdioServerParameters(command=sys.executable, args=[str(scripts / "l3_mcp_critic.py")], env=env)
        async with stdio_client(parameters, errlog=sys.__stderr__) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "omega-l3-critic"
                tools = (await session.list_tools()).tools
                assert [tool.name for tool in tools] == ["consult_critic"]
                assert "dispatch_token" not in tools[0].inputSchema["properties"]
                assert tools[0].inputSchema["properties"]["role_id"]["minimum"] == 17
                result = await session.call_tool("consult_critic", request(purpose="architecture"))
                assert result.isError
                assert TOKEN not in str(result)
                result = await session.call_tool("approve_gate", {})
                assert result.isError
    anyio.run(execute)
