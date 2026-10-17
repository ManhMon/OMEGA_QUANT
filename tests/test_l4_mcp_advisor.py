"""Offline advisor boundaries, resilience, durability and MCP lifecycle checks."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import errno
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession, types
from mcp.shared.exceptions import McpError
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import l4_mcp_advisor as advisor  # noqa: E402

TOKEN = "private-test-dispatch-token-000000000000"
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
CUTOFF = "2026-10-04T12:00:00Z"
CREDENTIAL_LABELS = tuple(
    variant for name in ("client_secret", "refresh_token", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD",
                         "signing_key", "private_key", "signing-key", "private-key", "signingKey", "privateKey")
    for variant in (name, "_" + name.lower(), "__" + name.upper() + "__", "service_" + name.title() + "_value")
)
PROVIDER_TOKENS = tuple(prefix + "TEST_ONLY_" + "A" * 82 for prefix in (
    "sk-ant-", "sk-proj-", "sk-svcacct-", "sk-", "ghp_", "gho_", "ghu_", "ghs_", "ghr_",
    "github_pat_", "AIza", "xoxb-", "xoxp-", "xoxa-", "xoxr-", "xoxs-", "xoxe-", "gsk_",
    "pplx-", "hf_", "r8_", "glpat-",
))
PROVIDER_IDS = tuple(value.split("TEST_ONLY_")[0].rstrip("_-") for value in PROVIDER_TOKENS)


@pytest.fixture(autouse=True)
def restore_sdk_logging():
    logger = logging.getLogger("mcp")
    handlers, propagate, level = list(logger.handlers), logger.propagate, logger.level
    yield
    logger.handlers, logger.propagate, logger.level = handlers, propagate, level


def launch_env():
    return {
        "OMEGA_DISPATCH_GATE": "GATE_TEST",
        "OMEGA_DISPATCH_SESSION_ID": "l4_role9_test_20261004",
        "OMEGA_DISPATCH_ROLE_ID": "9",
        "OMEGA_DISPATCH_RISK": "high",
        "OMEGA_DISPATCH_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
    }


def authority():
    return advisor.LaunchAuthority("GATE_TEST", "l4_role9_test_20261004", 9,
                                   "high", hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)


def bind_context(request):
    text = advisor.context_text(request["context"], TOKEN)
    request["context_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return request


def request(request_id="request_1", model=advisor.MODELS[0]):
    return bind_context({
        "schema_version": "mcp-advisor-request/v1", "gate": "GATE_TEST",
        "session_id": "l4_role9_test_20261004", "request_id": request_id,
        "role_id": 9, "risk": "high", "purpose": "correctness", "model": model,
        "context": {"instructions": "Check supplied observation consistency.",
                    "observations": [{"source_id": "fixture", "available_at": CUTOFF,
                                      "data": {"price": 25000, "unit": "VND_FULL"}}]},
        "context_sha256": "0" * 64, "as_of_time": CUTOFF, "dispatch_token": TOKEN,
    })


def provider_body(model=advisor.MODELS[0], advice="Supplied data is consistent."):
    return {"model": model, "id": "provider-1", "choices": [
        {"finish_reason": "stop", "message": {"role": "assistant", "content": advice}}]}


class FakeProvider:
    def __init__(self, body=None, error=None):
        self.body = body
        self.error = error
        self.calls = []

    async def __call__(self, payload):
        self.calls.append(deepcopy(payload))
        if self.error:
            raise self.error
        body = self.body if self.body is not None else provider_body(payload["model"])
        return body if type(body) is bytes else json.dumps(body, ensure_ascii=False).encode()


async def no_sleep(_):
    pass


def bridge(provider=None, **options):
    return advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                 sleep=no_sleep, jitter=lambda: 1, **options)


def consult(instance, value):
    return anyio.run(instance.consult, value)


@pytest.mark.parametrize("name", ["NINE_ROUTER_API_KEY", "9ROUTER_API_KEY", "ROUTER_API_KEY", "OMEGA_LLM_API_KEY"])
def test_stage5_router_provider_snapshot_fixed_origin_and_bounded_client(monkeypatch, name):
    import httpx

    environment = {name: "ROUTER_PRIVATE_CANARY", "OMEGA_LLM_BASE_URL": "http://localhost:20128/v1"}
    provider = advisor.router_provider_from_environment(environment)
    environment[name] = "MUTATED_CREDENTIAL"
    original, settings, seen = httpx.AsyncClient, [], []

    def respond(outbound):
        seen.append(outbound)
        model = json.loads(outbound.content)["model"]
        return httpx.Response(200, json=provider_body(model.removeprefix("cx/"), "Advice ROUTER_PRIVATE_CANARY"))

    def client(**kwargs):
        settings.append(kwargs)
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = consult(bridge(provider), request())
    assert result["status"] == "advice" and result["advice"] == "Advice [REDACTED]"
    assert settings == [{"timeout": advisor.DEADLINE_SECONDS, "trust_env": False, "follow_redirects": False}]
    assert str(seen[0].url) == advisor.ROUTER_URL
    assert seen[0].headers["authorization"] == "Bearer ROUTER_PRIVATE_CANARY"
    assert TOKEN.encode() not in seen[0].content and b"ROUTER_PRIVATE_CANARY" not in seen[0].content


@pytest.mark.parametrize("environment", [{}, {"NINE_ROUTER_API_KEY": "bad\nkey"},
    {"NINE_ROUTER_API_KEY": "x" * 4097}, {"NINE_ROUTER_API_KEY": 42},
    {"OMEGA_LLM_API_KEY": "private", "OMEGA_LLM_BASE_URL": "https://user:private@foreign.example/v1"}],
    ids=["missing", "control", "oversize", "type", "foreign-origin"])
def test_stage5_router_credentials_rejected_before_network(environment, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("invalid credentials reached network"))
    with pytest.raises(advisor.ProviderFailure, match="^AUTH_FAILED$"):
        advisor.router_provider_from_environment(environment)


@pytest.mark.parametrize("fault,code,attempts", [
    ("auth", "AUTH_FAILED", 1), ("forbidden", "AUTH_FAILED", 1),
    ("missing-model", "MODEL_UNAVAILABLE", 1), ("redirect", "PROVIDER_SCHEMA_INVALID", 1),
    ("bad-status", "PROVIDER_SCHEMA_INVALID", 1), ("rate-limit", "RATE_LIMITED", 3),
    ("gateway", "PROVIDER_UNAVAILABLE", 3), ("unavailable", "PROVIDER_UNAVAILABLE", 3),
    ("timeout", "TIMEOUT", 3), ("connection", "PROVIDER_UNAVAILABLE", 3),
    ("oversize", "RESPONSE_TOO_LARGE", 1), ("partial", "PROVIDER_SCHEMA_INVALID", 1),
    ("wrong-model", "MODEL_UNAVAILABLE", 1), ("bad-schema", "PROVIDER_SCHEMA_INVALID", 1),
])
def test_stage5_router_transport_faults_bounded_closed_and_secret_safe(monkeypatch, fault, code, attempts):
    import httpx

    original, calls, closed = httpx.AsyncClient, [], []
    statuses = {"auth": 401, "forbidden": 403, "missing-model": 404, "redirect": 302,
                "bad-status": 400, "rate-limit": 429, "gateway": 502, "unavailable": 503}

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if fault == "oversize":
                yield b"x" * advisor.MAX_RESPONSE_BYTES
                yield b"x"
                pytest.fail("oversized stream continued")
            elif fault == "partial":
                yield b'{"partial":'
            else:
                model = "unlisted" if fault == "wrong-model" else advisor.MODELS[0].removeprefix("cx/")
                body = provider_body(model)
                if fault == "bad-schema":
                    body["choices"] = []
                yield advisor.json_bytes(body)

        async def aclose(self):
            closed.append(True)

    def respond(outbound):
        calls.append(outbound)
        if fault in ("timeout", "connection"):
            error = httpx.ReadTimeout if fault == "timeout" else httpx.ConnectError
            raise error("https://user:ROUTER_PRIVATE_CANARY@foreign.example", request=outbound)
        return httpx.Response(statuses.get(fault, 200), headers={"Retry-After": "999999999",
                              "Location": "https://user:ROUTER_PRIVATE_CANARY@foreign.example"}, stream=Stream())

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    result = consult(bridge(advisor.router_provider_from_environment({"NINE_ROUTER_API_KEY": "ROUTER_PRIVATE_CANARY"})), request())
    assert result["status"] == "error" and result["error"]["code"] == code
    assert result["attempts"] == attempts == len(calls) and result["advice"] is None
    assert len(closed) == (0 if fault in ("timeout", "connection") else attempts)
    assert "ROUTER_PRIVATE_CANARY" not in json.dumps(result)


def test_stage5_router_cancellation_closes_transport_and_releases_capacity(monkeypatch):
    import httpx

    original, closed = httpx.AsyncClient, []

    async def scenario():
        entered = anyio.Event()

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await anyio.sleep_forever()
                yield b""

            async def aclose(self):
                closed.append(True)

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Stream())), **kwargs))
        instance = bridge(advisor.router_provider_from_environment({"NINE_ROUTER_API_KEY": "private"}))
        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(instance.consult, request())
                await entered.wait()
                tasks.cancel_scope.cancel()
        assert closed == [True] and instance._active == 0 and instance.failed

    anyio.run(scenario)


@pytest.mark.parametrize("model", advisor.MODELS, ids=["sol", "astra"])
def test_bound_advice_and_exact_sanitized_digest(model):
    provider = FakeProvider()
    instance = bridge(provider)
    value = request(model=model)
    original = deepcopy(value)
    result = consult(instance, value)
    advisor.validate_response(result, value)
    assert set(result) == set(advisor.RESPONSE_SCHEMA["required"])
    assert len(result) == 20
    assert result["status"] == "advice" and result["error"] is None
    assert result["as_of_time"] == CUTOFF
    assert result["model"] == model
    assert result["attempts"] == 1 and result["retries"] == 0
    outbound = provider.calls[0]["messages"][1]["content"]
    assert hashlib.sha256(outbound.encode()).hexdigest() == result["context_sha256"]
    assert TOKEN not in json.dumps(provider.calls)
    assert value == original


@pytest.mark.parametrize("field,value", [
    ("gate", "other"), ("session_id", "other"), ("role_id", 10),
    ("role_id", True), ("role_id", 9.0), ("role_id", "9"),
    ("risk", "low"), ("dispatch_token", "x" * 40),
    ("dispatch_token", None), ("gate", "GATE_TEST\n"),
], ids=["gate", "session", "role", "boolean", "float", "string", "risk", "token", "missing_token", "newline"])
def test_identity_spoofing_precedes_all_side_effects(field, value):
    provider = FakeProvider()
    instance = bridge(provider)
    bad = request()
    bad[field] = value
    with pytest.raises(advisor.ToolError, match="ERR_UNAUTHORIZED_IDENTITY"):
        consult(instance, bad)
    assert not provider.calls and not instance._requests and instance._active == 0


@pytest.mark.parametrize("field", ["request_id", "gate", "session_id"])
@pytest.mark.parametrize("secret", [TOKEN, "prefix-" + TOKEN + "-suffix", "sk-identity-canary", *CREDENTIAL_LABELS, *PROVIDER_TOKENS],
                         ids=["dispatch", "embedded_dispatch", "api_key", *CREDENTIAL_LABELS, *PROVIDER_IDS])
@pytest.mark.parametrize("encoded", [False, True], ids=["dict", "bytes"])
def test_secret_bearing_bound_identifiers_reject_before_side_effects(field, secret, encoded, capsys, caplog):
    value = request()
    value[field] = secret
    original = deepcopy(value)
    bound = advisor.LaunchAuthority(value["gate"], value["session_id"], 9, "high",
                                    hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
    provider = FakeProvider()
    instance = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW)
    # Existing accepted work must survive rejection, not just an empty bridge.
    instance._requests.add("prior")
    instance._active = 1
    with pytest.raises(advisor.ToolError, match="^ERR_SECRET_IDENTITY$") as rejected:
        consult(instance, advisor.json_bytes(value) if encoded else value)
    assert value == original
    assert not provider.calls and instance._requests == {"prior"} and instance._active == 1
    assert secret not in str(rejected.value) + caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("field", ["request_id", "gate", "session_id"])
@pytest.mark.parametrize("outcome", ["success", "unavailable", "timeout", "schema"])
def test_secret_identifiers_fail_closed_in_both_mcp_channels(field, outcome, capsys, caplog):
    value = request()
    value[field] = TOKEN
    original = deepcopy(value)
    bound = advisor.LaunchAuthority(value["gate"], value["session_id"], 9, "high",
                                    hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
    body = provider_body()
    body["choices"][0]["message"]["role"] = "tool"
    provider = FakeProvider(body=body if outcome == "schema" else None,
                            error=TimeoutError(TOKEN) if outcome == "timeout" else None)
    instance = advisor.AdvisorBridge(bound, None if outcome == "unavailable" else provider, clock=lambda: NOW)

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(instance) as (client, _):
                for _ in range(2):
                    result = await client.call_tool("consult_advisor", value)
                    assert result.isError and result.structuredContent is None
                    assert result.content[0].text == "ERR_SECRET_IDENTITY"
                    assert TOKEN not in result.model_dump_json()
                assert not provider.calls and not instance._requests and instance._active == 0

    anyio.run(scenario)
    assert value == original
    assert TOKEN not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("field", ["source_id", "nested_source_id"])
@pytest.mark.parametrize("secret", [TOKEN, "sk-source-canary", *CREDENTIAL_LABELS, *PROVIDER_TOKENS],
                         ids=["dispatch", "api_key", *CREDENTIAL_LABELS, *PROVIDER_IDS])
def test_secret_provenance_identifiers_reject_without_rewriting(field, secret):
    value = request()
    observation = value["context"]["observations"][0]
    if field == "source_id":
        observation["source_id"] = secret
    else:
        observation["data"] = {"source_id": secret, "available_at": CUTOFF, "data": 1}
    bind_context(value)
    original = deepcopy(value)
    provider = FakeProvider()
    instance = bridge(provider)
    with pytest.raises(advisor.ToolError, match="^ERR_INVALID_PROVENANCE$"):
        consult(instance, value)
    assert value == original
    assert not provider.calls and not instance._requests and instance._active == 0


def test_dispatch_token_in_other_echoed_string_rejects_before_reservation():
    value = request()
    token = value["context_sha256"]
    value["dispatch_token"] = token
    bound = advisor.LaunchAuthority(value["gate"], value["session_id"], 9, "high",
                                    hashlib.sha256(token.encode()).hexdigest(), NOW)
    provider = FakeProvider()
    instance = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW)
    with pytest.raises(advisor.ToolError, match="^ERR_SECRET_IDENTITY$"):
        consult(instance, value)
    assert not provider.calls and not instance._requests and instance._active == 0


@pytest.mark.parametrize("key", list(launch_env()), ids=["gate", "session", "role", "risk", "digest"])
def test_missing_launch_authority_blocks_startup(key):
    env = launch_env()
    del env[key]
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_LAUNCH_AUTHORITY"):
        advisor.LaunchAuthority.from_environment(env)


@pytest.mark.parametrize("key,value", [
    ("OMEGA_DISPATCH_GATE", "--flag" + "\n"),
    ("OMEGA_DISPATCH_SESSION_ID", "../session"),
    ("OMEGA_DISPATCH_ROLE_ID", "09"), ("OMEGA_DISPATCH_ROLE_ID", "17"),
    ("OMEGA_DISPATCH_ROLE_ID", "9.0"), ("OMEGA_DISPATCH_ROLE_ID", True),
    ("OMEGA_DISPATCH_RISK", "HIGH"), ("OMEGA_DISPATCH_RISK", []),
    ("OMEGA_DISPATCH_TOKEN_SHA256", "A" * 64),
], ids=["gate", "session", "leading_zero", "audit_role", "float", "boolean", "risk_case", "risk_list", "digest_case"])
def test_malformed_launch_authority(key, value):
    env = launch_env()
    env[key] = value
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_LAUNCH_AUTHORITY"):
        advisor.LaunchAuthority.from_environment(env)


def test_environment_snapshot_is_immutable(monkeypatch):
    for key, value in launch_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(advisor, "utc_now", lambda: NOW)
    bound = advisor.LaunchAuthority.from_environment()
    instance = advisor.AdvisorBridge(bound, FakeProvider(), clock=lambda: NOW)
    for key in launch_env():
        monkeypatch.setenv(key, "ambient-override")
    assert consult(instance, request())["status"] == "advice"
    with pytest.raises(FrozenInstanceError):
        bound.gate = "changed"
    assert bound.current_session_started_at == NOW
    assert TOKEN not in repr(bound)


@pytest.mark.parametrize("variant", ["cutoff", "observation", "mixed", "nested", "derived"], ids=str)
def test_future_cutoff_and_entire_observation_batch_fail_before_io(variant):
    provider = FakeProvider()
    instance = bridge(provider)
    bad = request()
    future = "2026-10-04T12:00:01Z"
    observations = bad["context"]["observations"]
    if variant == "cutoff":
        bad["as_of_time"] = future
    elif variant == "observation":
        observations[0]["available_at"] = future
    elif variant == "mixed":
        observations.append({"source_id": "revision", "available_at": future, "data": 1})
    else:
        observations[0]["data"] = {"inputs": [{"source_id": "revision", "available_at": future, "data": 1}]}
    bind_context(bad)
    with pytest.raises(advisor.ToolError, match="ERR_LOOKAHEAD_DETECTED"):
        consult(instance, bad)
    assert not provider.calls and not instance._requests


@pytest.mark.parametrize("date", [
    "2026-10-04T19:00:00+07:00", "2026-10-04T12:00:00.000Z",
    "2026-02-30T12:00:00Z", "0000-10-04T12:00:00Z",
    "2026-10-04T12:00:60Z", CUTOFF + "\n", "2026-10-04", None,
], ids=["ict_offset", "fraction", "bad_date", "year_zero", "leap_second", "newline", "date_only", "null"])
def test_strict_utc_timestamp_rejection(date):
    provider = FakeProvider()
    value = request()
    value["as_of_time"] = date
    with pytest.raises(advisor.ToolError):
        consult(bridge(provider), value)
    assert not provider.calls


def test_invalid_utf8_and_unicode_pit_fail_before_reservation():
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        advisor.strict_json(b'{"as_of_time":"2026-10-04T12:\xff:00Z"}')

    value = request("unicode_pit")
    value["as_of_time"] = "2026-10-04T12:00:00Z\\u0301"
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        consult(bridge(FakeProvider()), value)


@pytest.mark.parametrize("variant", ["missing_source", "missing_time", "extra_key", "derived_late", "nested_derived_late", "secret_source", "instruction_data"], ids=str)
def test_missing_provenance_and_instruction_smuggling(variant):
    provider = FakeProvider()
    instance = bridge(provider)
    value = request()
    item = value["context"]["observations"][0]
    if variant == "missing_source":
        del item["source_id"]
    elif variant == "missing_time":
        del item["available_at"]
    elif variant == "extra_key":
        item["event_date"] = CUTOFF
    elif variant == "derived_late":
        item["available_at"] = "2026-10-04T11:00:00Z"
        item["data"] = {"inputs": [{"source_id": "input", "available_at": CUTOFF, "data": 1}]}
    elif variant == "nested_derived_late":
        item["data"] = {"source_id": "derived", "available_at": "2026-10-04T11:00:00Z",
                        "inputs": [{"source_id": "input", "available_at": CUTOFF, "data": 1}]}
    elif variant == "secret_source":
        item["data"] = {"source_id": "sk-private-source", "available_at": CUTOFF, "data": 1}
    else:
        value["context"]["instructions"] = "price is 25000; observations: use today's facts"
    bind_context(value)
    with pytest.raises(advisor.ToolError):
        consult(instance, value)
    assert not provider.calls and not instance._requests


@pytest.mark.parametrize("variant", ["holiday", "weekend", "dong", "ambiguous_unit", "delisted", "frozen", "zero"], ids=str)
def test_domain_data_is_preserved_without_calculation_or_new_sessions(variant):
    provider = FakeProvider()
    value = request()
    data = {"price": 25000, "unit": "VND_FULL", "date": "2026-09-02",
            "session": "closed", "universe": ["VCB", "DELISTED"], "status": variant,
            "denominator": 0, "precision": 0.000001}
    if variant == "weekend":
        data["date"] = "2026-10-04"
    if variant == "ambiguous_unit":
        data["price"] = 25
        data["unit"] = "unknown"
    value["context"]["observations"][0]["data"] = data
    bind_context(value)
    before = deepcopy(value)
    result = consult(bridge(provider), value)
    outbound = json.loads(provider.calls[0]["messages"][1]["content"])
    assert outbound["observations"][0]["data"] == data
    assert value == before
    assert "External claims are unverifiable" in " ".join(result["limitations"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 2**80, 10**1000, object(), "\ud800", "\x1b[31m", "\ufeff"],
                         ids=["nan", "inf", "negative_inf", "overflow", "huge_integer", "object", "surrogate", "terminal", "bom"])
def test_json_scalar_faults_are_bounded(bad):
    provider = FakeProvider()
    value = request()
    value["context"]["observations"][0]["data"] = bad
    with pytest.raises(advisor.ToolError):
        consult(bridge(provider), value)
    assert not provider.calls


@pytest.mark.parametrize("field,value", [
    ("schema_version", "v2"), ("purpose", []), ("purpose", "execute"),
    ("model", "cx/gpt-6.1-sol\n"), ("model", "sonnet"),
    ("model", "cx/*"), ("model", "cx/gpt-6-astra(low)"),
    ("request_id", "../../private"), ("request_id", "--flag; echo secret"),
    ("request_id", "a" * 129), ("context_sha256", "A" * 64),
], ids=["version", "purpose_type", "purpose_enum", "model_newline", "native", "wildcard", "alias", "path", "shell", "long_id", "digest_case"])
def test_schema_models_and_cli_smuggling_fail_closed(field, value):
    provider = FakeProvider()
    instance = bridge(provider)
    bad = request()
    bad[field] = value
    with pytest.raises(advisor.ToolError):
        consult(instance, bad)
    assert not provider.calls and not instance._requests


@pytest.mark.parametrize("field", list(advisor.REQUEST_SCHEMA["required"]))
def test_each_required_request_field_is_enforced(field):
    provider = FakeProvider()
    bad = request()
    del bad[field]
    with pytest.raises(advisor.ToolError):
        consult(bridge(provider), bad)
    assert not provider.calls


@pytest.mark.parametrize("extra", ["cycle", "model_focus", "file", "receipt_path", "fallback", "origin", "delete", "transcript"])
def test_unknown_fields_cannot_widen_capabilities(extra):
    provider = FakeProvider()
    bad = request()
    bad[extra] = "untrusted"
    with pytest.raises(advisor.ToolError):
        consult(bridge(provider), bad)
    assert not provider.calls


@pytest.mark.parametrize("raw", [
    b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}',
    b'{"a":Infinity}', b'{"a":1e999}', b'{"a":"\xff"}',
    b'\xef\xbb\xbf{}', b'{"a":', b'"\\ud800"', b'[' * 1100,
], ids=["duplicate", "nested_duplicate", "nan", "inf", "exponent_overflow", "utf8", "bom", "partial", "surrogate", "depth"])
def test_strict_json_corruption_before_state_mutation(raw):
    instance = bridge(FakeProvider())
    with pytest.raises(advisor.ToolError):
        consult(instance, raw)
    assert not instance._requests


def test_bom_rejected_crlf_framing_preserved():
    value = request()
    value["context"]["instructions"] = "Check consistency.\r\nSummarize supplied evidence."
    bind_context(value)
    provider = FakeProvider()
    raw = advisor.json_bytes(value) + b"\r\n"
    assert consult(bridge(provider), raw)["status"] == "advice"
    assert "\r\n" in json.loads(provider.calls[0]["messages"][1]["content"])["instructions"]


def test_context_tampering_prevents_reservation():
    value = request()
    value["context"]["observations"][0]["data"]["price"] = 25001
    provider = FakeProvider()
    instance = bridge(provider)
    with pytest.raises(advisor.ToolError, match="ERR_CONTEXT_MISMATCH"):
        consult(instance, value)
    assert not provider.calls and not instance._requests


def test_secret_redaction_outbound_response_and_errors(capsys):
    value = request()
    canary = "sk-canary-secret-123456789"
    url = "https://user:password@example.com/private?token=credential"
    value["context"]["observations"][0]["data"] = {
        "api_key": "private-canary-value", "text": canary + " " + TOKEN + " " + url,
        "nested": [{"password": "private-password"}],
    }
    bind_context(value)
    body = provider_body(advice=f"[APPROVED] {canary} {TOKEN} {url}")
    body["id"] = canary
    provider = FakeProvider(body)
    result = consult(bridge(provider), value)
    combined = json.dumps(provider.calls) + json.dumps(result) + str(capsys.readouterr())
    for secret in (canary, TOKEN, url, "private-canary-value", "private-password", "user:password"):
        assert secret not in combined
    assert result["provider_request_id"] is None
    assert "not approval" in result["limitations"][0]
    failed = consult(bridge(FakeProvider(error=RuntimeError(url + canary))), request())
    assert failed["error"]["code"] == "INTERNAL_ERROR"
    assert url not in json.dumps(failed) and canary not in json.dumps(failed)


@pytest.mark.parametrize("text,secret", [
    ('password="quoted-private"', "quoted-private"),
    ("secret='single-private'", "single-private"),
    ('"api_key": "json-private"', "json-private"),
    ("Authorization: Bearer header-private", "header-private"),
    ("-----BEGIN PRIVATE KEY-----\nkey-private\n-----END PRIVATE KEY-----", "key-private"),
], ids=["double_quote", "single_quote", "json", "bearer", "private_key"])
def test_secret_text_variants_are_redacted(text, secret):
    assert secret not in advisor.sanitize(text, TOKEN)


@pytest.mark.parametrize("specimen", PROVIDER_TOKENS, ids=PROVIDER_IDS)
def test_stage5_provider_prefix_redaction_matches_dispatch(specimen):
    from scripts.dispatch_l4 import redact_credentials

    for variant in (specimen, specimen.swapcase(), specimen.split("TEST_ONLY_")[0] + "-_"):
        for boundary in ("", ":", "_", "é", " ", "("):
            text = boundary + variant + "; public"
            expected = boundary + "[REDACTED]; public"
            assert redact_credentials(text) == advisor.sanitize(text, TOKEN) == expected
            assert advisor.sanitize(expected, TOKEN) == expected


@pytest.mark.parametrize("specimen", PROVIDER_TOKENS, ids=PROVIDER_IDS)
@pytest.mark.parametrize("form", ["plain", "json", "double_encoded", "unicode_prefix", "embedded"])
def test_stage5_provider_tokens_redacted_over_mcp_and_receipts(tmp_path, specimen, form, capsys, caplog):
    dirty, clean = specimen, "[REDACTED]"
    if form != "plain":
        dirty = json.dumps({"note": specimen}, separators=(",", ":"))
        clean = json.dumps({"note": clean}, separators=(",", ":"))
        if form == "double_encoded":
            dirty, clean = json.dumps(dirty), json.dumps(clean)
        elif form == "unicode_prefix":
            dirty = dirty.replace(specimen, f"\\u{ord(specimen[0]):04x}" + specimen[1:])
        elif form == "embedded":
            dirty, clean = "Evidence " + dirty, "Evidence " + clean
    value = request()
    value["context"]["instructions"] = "Review " + specimen
    value["context"]["observations"][0]["data"] = {
        "note": dirty, "nested": [{"note": dirty}], specimen: "public",
    }
    expected = deepcopy(value["context"])
    expected["instructions"] = "Review [REDACTED]"
    expected["observations"][0]["data"] = {
        "note": clean, "nested": [{"note": clean}], "[REDACTED]": "public",
    }
    expected_text = advisor.json_bytes(expected).decode()
    value["context_sha256"] = hashlib.sha256(expected_text.encode()).hexdigest()
    original = deepcopy(value)
    body = provider_body(advice=dirty)
    body["id"] = specimen
    provider = FakeProvider(body)
    instance = bridge(provider, receipt_directory=tmp_path)

    async def scenario():
        async with client_for(instance) as (client, _):
            result = await client.call_tool("consult_advisor", value)
            assert not result.isError
            response = result.structuredContent
            advisor.validate_response(response, value)
            assert provider.calls[0]["messages"][1]["content"] == expected_text
            assert response["context_sha256"] == hashlib.sha256(expected_text.encode()).hexdigest()
            assert response["advice"] == clean and response["provider_request_id"] is None
            assert json.loads(result.content[0].text) == response
            assert specimen not in result.model_dump_json() + json.dumps(provider.calls)

    anyio.run(scenario)
    assert value == original and instance._active == 0
    assert instance.receipts.read(value)["provider_request_id"] is None
    assert advisor.sanitize(clean, TOKEN) == clean
    assert specimen not in instance.receipts.path.read_text(encoding="utf-8") + caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("specimen", PROVIDER_TOKENS, ids=PROVIDER_IDS)
@pytest.mark.parametrize("fault", ["raw_digest", "key_collision"])
def test_stage5_provider_context_faults_fail_before_reservation(tmp_path, specimen, fault, capsys, caplog):
    prior = set(tmp_path.iterdir())
    value = request()
    value["context"]["observations"][0]["data"] = (
        {"note": specimen} if fault == "raw_digest" else {specimen: 1, specimen + "B": 2})
    value["context_sha256"] = hashlib.sha256(advisor.json_bytes(value["context"])).hexdigest()
    original = deepcopy(value)
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    code = "ERR_CONTEXT_MISMATCH" if fault == "raw_digest" else "ERR_INVALID_ARGUMENTS"

    async def scenario():
        async with client_for(instance) as (client, _):
            result = await client.call_tool("consult_advisor", value)
            assert result.isError and result.structuredContent is None
            assert result.content[0].text == code
            assert specimen not in result.model_dump_json()

    anyio.run(scenario)
    assert not provider.calls and not instance._requests and instance._active == 0
    assert value == original and set(tmp_path.iterdir()) == prior
    assert specimen not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("specimen", PROVIDER_TOKENS, ids=PROVIDER_IDS)
def test_stage5_provider_receipt_corruption_blocks_read_publish_and_recovery(tmp_path, specimen):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    value = request("prior")
    response = consult(instance, value)
    store = instance.receipts
    ledger = json.loads(store.path.read_bytes())
    ledger["entries"][0]["response"]["provider_request_id"] = specimen
    ledger["receipt_sha256"] = hashlib.sha256(advisor.json_bytes(
        {key: item for key, item in ledger.items() if key != "receipt_sha256"})).hexdigest()
    raw = advisor.json_bytes(ledger)
    store.path.write_bytes(raw)
    restarted = bridge(provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        restarted.receipts.read(value)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        restarted.receipts.publish(value, response)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        consult(restarted, request("next"))
    assert len(provider.calls) == 1 and not restarted._requests and restarted._active == 0
    store.rollback_path.write_bytes(raw)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        restarted.receipts.recover()
    assert store.path.read_bytes() == store.rollback_path.read_bytes() == raw


@pytest.mark.parametrize("name", ["credential", "credentials", "access_token", *CREDENTIAL_LABELS])
@pytest.mark.parametrize("form", [
    "bare", "double_quote", "single_quote", "json", "escaped_double",
    "escaped_single", "multiline", "unterminated",
])
def test_credential_assignments_are_sanitized_before_binding_and_advice(name, form, capsys, caplog):
    secret = "assignment-private-canary"
    formats = {
        "bare": f"{name}={secret}; public",
        "double_quote": f'{name} = "{secret} extra space"; public',
        "single_quote": f"{name} : '{secret} extra space'; public",
        "json": f'"{name.upper()}": "{secret}"; public',
        "escaped_double": f'{name}="{secret} \\" tail-{secret}"; public',
        "escaped_single": f"{name}='{secret} \\' tail-{secret}'; public",
        "multiline": f'{name}="{secret}\r\nlast-{secret}"; public',
        "unterminated": f'{name}="{secret} \\" last-{secret}',
    }
    dirty = formats[form]
    clean = '[REDACTED]' if form == "unterminated" else '[REDACTED]; public'
    if form == "json":
        clean = '"' + clean
    value = request()
    value["context"]["instructions"] = "Review " + dirty
    value["context"]["observations"][0]["data"] = {
        "note": dirty, "nested": [{"note": dirty}], name: {"value": secret}, dirty: "public label",
    }
    expected = deepcopy(value["context"])
    expected["instructions"] = "Review " + clean
    expected["observations"][0]["data"] = {
        "note": clean, "nested": [{"note": clean}], name: "[REDACTED]", clean: "[REDACTED]",
    }
    # Independent preimage: never derive the expected redaction from sanitize().
    expected_text = advisor.json_bytes(expected).decode("utf-8")
    value["context_sha256"] = hashlib.sha256(expected_text.encode()).hexdigest()
    original = deepcopy(value)
    provider = FakeProvider(provider_body(advice="Review " + dirty))
    result = consult(bridge(provider), value)
    advisor.validate_response(result, value)
    assert advisor.context_text(value["context"], TOKEN) == expected_text
    assert provider.calls[0]["messages"][1]["content"] == expected_text
    assert result["advice"] == "Review " + clean
    assert result["context_sha256"] == value["context_sha256"]
    assert value == original
    assert secret not in json.dumps(provider.calls) + json.dumps(result) + caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("name", ["access-token", "accessToken", "ACCESS_TOKEN"])
def test_access_token_assignment_aliases_are_redacted(name):
    assert advisor.sanitize(f"{name}=alias-private; public", TOKEN) == "[REDACTED]; public"


@pytest.mark.parametrize("name", ["client_secret", "signing_key", "private_key"])
@pytest.mark.parametrize("form", ["object", "array", "double_encoded", "embedded", "assignment"])
def test_credential_redaction_is_idempotent_for_response_sweep(form, name):
    dirty = json.dumps({name: "idempotence-private-canary"})
    clean = json.dumps({name: "[REDACTED]"}, separators=(",", ":"))
    if form == "array":
        dirty, clean = "[" + dirty + "]", "[" + clean + "]"
    elif form == "double_encoded":
        dirty, clean = json.dumps(dirty), json.dumps(clean)
    elif form == "embedded":
        dirty, clean = "Evidence " + dirty, "Evidence " + clean
    elif form == "assignment":
        dirty, clean = f'"{name}": "idempotence-private-canary"; public', '"[REDACTED]; public'
    assert advisor.sanitize(dirty, TOKEN) == clean
    assert advisor.sanitize(clean, TOKEN) == clean


@pytest.mark.parametrize("name", CREDENTIAL_LABELS)
@pytest.mark.parametrize("form", [
    "json", "double_encoded", "unicode_label", "embedded", "embedded_double_encoded", "embedded_unicode_label",
])
def test_serialized_credential_aliases_are_secret_safe_over_mcp(name, form, capsys, caplog):
    secret = "serialized-alias-private-canary"
    dirty = json.dumps({name: secret}, sort_keys=True, separators=(",", ":"))
    clean = json.dumps({name: "[REDACTED]"}, sort_keys=True, separators=(",", ":"))
    if form in ("double_encoded", "embedded_double_encoded"):
        dirty, clean = json.dumps(dirty), json.dumps(clean)
    elif form in ("unicode_label", "embedded_unicode_label"):
        dirty = dirty.replace(name, f"\\u{ord(name[0]):04x}" + name[1:])
    if form.startswith("embedded"):
        dirty, clean = "Evidence " + dirty, "Evidence " + clean
    value = request()
    value["context"]["instructions"] = f"Review {name}={secret}"
    value["context"]["observations"][0]["data"] = {
        "note": dirty, "nested": [{name: [secret], "note": dirty}], dirty: "public",
    }
    expected = deepcopy(value["context"])
    expected["instructions"] = "Review [REDACTED]"
    expected["observations"][0]["data"] = {
        "note": clean, "nested": [{name: "[REDACTED]", "note": clean}], clean: "[REDACTED]",
    }
    expected_text = advisor.json_bytes(expected).decode()
    value["context_sha256"] = hashlib.sha256(expected_text.encode()).hexdigest()
    original = deepcopy(value)
    body = provider_body(advice=dirty)
    body["id"] = f"{name}:{secret}"
    provider = FakeProvider(body)

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(bridge(provider)) as (client, _):
                result = await client.call_tool("consult_advisor", value)
                assert not result.isError
                response = result.structuredContent
                advisor.validate_response(response, value)
                assert response["advice"] == clean
                assert response["provider_request_id"] is None
                assert provider.calls[0]["messages"][1]["content"] == expected_text
                assert json.loads(result.content[0].text) == response
                for output in (json.dumps(provider.calls), response["advice"],
                               str(response["provider_request_id"]), result.model_dump_json()):
                    assert secret not in output and TOKEN not in output

    anyio.run(scenario)
    assert value == original
    assert secret not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("name", CREDENTIAL_LABELS)
@pytest.mark.parametrize("separator", [":", "-", "_", "."], ids=["colon", "hyphen", "underscore", "dot"])
def test_secret_bearing_provider_identifiers_are_discarded(name, separator, capsys, caplog):
    secret = "identifier-private-canary"
    body = provider_body()
    body["id"] = name + separator + secret
    result = consult(bridge(FakeProvider(body)), request())
    assert result["status"] == "advice" and result["provider_request_id"] is None
    assert secret not in advisor.json_bytes(result).decode() + caplog.text + str(capsys.readouterr())


def test_ordinary_prose_json_and_provider_identifiers_are_preserved():
    text = 'Explain client_secret handling, refresh_token rotation, DB_PASSWORD storage, signing_key and private_key handling; no credential values supplied.'
    assert advisor.sanitize(text, TOKEN) == text
    plain_json = '{"public_value": "unchanged", "notes": ["secret handling"]}'
    assert advisor.sanitize(plain_json, TOKEN) == plain_json
    body = provider_body(advice=text)
    body["id"] = "provider_ABC-123.v1:region"
    result = consult(bridge(FakeProvider(body)), request())
    assert result["advice"] == text and result["provider_request_id"] == body["id"]


@pytest.mark.parametrize("name", CREDENTIAL_LABELS)
def test_credential_assignment_masks_entire_nested_serialized_value(name):
    secret = "nested-serialization-private-canary"
    dirty = f'{name}="client_secret={secret} extra-{secret}"; public'
    assert advisor.sanitize(dirty, TOKEN) == "[REDACTED]; public"
    dirty = f"{name}=" + json.dumps(json.dumps({"refresh_token": secret})) + "; public"
    assert advisor.sanitize(dirty, TOKEN) == "[REDACTED]; public"


@pytest.mark.parametrize("name", ["client_secret", "signing_key", "private_key"])
def test_duplicate_serialized_credential_aliases_fail_closed_over_mcp(capsys, caplog, name):
    secret = "duplicate-serialization-private-canary"
    escaped = f"\\u{ord(name[0]):04x}" + name[1:]
    dirty = f'Evidence {{"{escaped}": "{secret}", "{name}": "{secret}"}}'
    provider = FakeProvider(provider_body(advice=dirty))
    instance = bridge(provider)
    value = request()
    value["context"]["observations"][0]["data"] = dirty

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(instance) as (client, _):
                rejected = await client.call_tool("consult_advisor", value)
                assert rejected.isError and rejected.content[0].text == "ERR_INVALID_ARGUMENTS"
                assert not provider.calls and not instance._requests and instance._active == 0
                failed = await client.call_tool("consult_advisor", request())
                assert failed.isError
                assert failed.structuredContent["error"]["code"] == "PROVIDER_SCHEMA_INVALID"
                assert failed.structuredContent["advice"] is None
                assert failed.structuredContent["provider_request_id"] is None
                assert instance._active == 0 and len(provider.calls) == 1
                assert secret not in rejected.model_dump_json() + failed.model_dump_json() + json.dumps(provider.calls)

    anyio.run(scenario)
    assert secret not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("name", CREDENTIAL_LABELS)
def test_unsanitized_credential_digest_is_rejected_before_provider(name):
    value = request()
    value["context"]["instructions"] = f"Review {name}=digest-private-canary"
    value["context_sha256"] = hashlib.sha256(advisor.json_bytes(value["context"])).hexdigest()
    original = deepcopy(value)
    provider = FakeProvider()
    instance = bridge(provider)
    with pytest.raises(advisor.ToolError, match="ERR_CONTEXT_MISMATCH"):
        consult(instance, value)
    assert not provider.calls and not instance._requests and instance._active == 0
    assert value == original


@pytest.mark.parametrize("name", CREDENTIAL_LABELS)
@pytest.mark.parametrize("serialized", [False, True], ids=["recursive", "serialized"])
def test_credential_redaction_collision_rejects_before_reservation(name, serialized):
    value = request()
    data = {
        f"{name}=first-private": "first", f"{name}=second-private": "second",
    }
    value["context"]["observations"][0]["data"] = json.dumps(data) if serialized else data
    original = deepcopy(value)
    provider = FakeProvider()
    instance = bridge(provider)
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        consult(instance, value)
    assert not provider.calls and not instance._requests and instance._active == 0
    assert value == original


@pytest.mark.parametrize("fault", ["timeout", "exception", "schema", "serialized_collision"])
def test_credential_provider_faults_remain_secret_safe(fault, capsys, caplog):
    dirty = "client_secret=first-private _refresh_token=second-private __AWS_SECRET_ACCESS_KEY=third-private DB_PASSWORD=fourth-private signing_key=fifth-private private_key=sixth-private"
    dirty += " " + " ".join(PROVIDER_TOKENS)
    value = request()
    value["context"]["instructions"] = "Review " + dirty
    bind_context(value)
    original = deepcopy(value)
    body = provider_body(advice=dirty)
    body["choices"][0]["message"]["role"] = "tool"
    if fault == "serialized_collision":
        body = provider_body(advice=json.dumps({"_signing_key=first-private": 1, "__PRIVATE_KEY=second-private": 2}))
    provider = FakeProvider(body=body) if fault in ("schema", "serialized_collision") else FakeProvider(
        error=TimeoutError(dirty) if fault == "timeout" else RuntimeError(dirty))
    instance = bridge(provider)
    result = consult(instance, value)
    advisor.validate_response(result, value)
    assert result["error"]["code"] == {
        "timeout": "TIMEOUT", "exception": "INTERNAL_ERROR", "schema": "PROVIDER_SCHEMA_INVALID",
        "serialized_collision": "PROVIDER_SCHEMA_INVALID",
    }[fault]
    expected_attempts = 3 if fault == "timeout" else 1
    assert result["advice"] is None and result["attempts"] == expected_attempts and result["retries"] == expected_attempts - 1
    assert instance._active == 0 and instance._requests == {value["request_id"]}
    with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
        consult(instance, value)
    assert len(provider.calls) == expected_attempts
    provider.body, provider.error = provider_body(advice=dirty), None
    if fault == "timeout":
        monkeypatch_time = instance.monotonic() + advisor.CIRCUIT_COOLDOWN_SECONDS
        instance.monotonic = lambda: monkeypatch_time
    recovered = consult(instance, request("recovered"))
    assert recovered["advice"] == " ".join(["[REDACTED]"] * (6 + len(PROVIDER_TOKENS))) and instance._active == 0
    assert value == original
    combined = json.dumps(provider.calls) + json.dumps(result) + json.dumps(recovered) + caplog.text + str(capsys.readouterr())
    for secret in ("first-private", "second-private", "third-private", "fourth-private", "fifth-private", "sixth-private", *PROVIDER_TOKENS):
        assert secret not in combined


@pytest.mark.parametrize("outcome", ["success", "unavailable", "timeout", "schema"])
def test_all_returned_strings_are_secret_safe_in_both_mcp_channels(outcome, capsys, caplog):
    secret = "response-sweep-canary"
    dirty = f"{TOKEN} client_secret={secret} https://user:{secret}@example.com/?token={secret}"
    value = request("safe_request")
    value["context"]["observations"][0]["data"] = {"note": dirty}
    bind_context(value)
    body = provider_body(advice=dirty)
    body["id"] = TOKEN
    if outcome == "schema":
        body["choices"][0]["message"]["role"] = "tool"
    provider = FakeProvider(body=body, error=TimeoutError(dirty) if outcome == "timeout" else None)
    instance = bridge(None if outcome == "unavailable" else provider)

    def check_strings(item):
        if isinstance(item, str):
            assert TOKEN not in item and secret not in item
        elif isinstance(item, dict):
            for key, child in item.items():
                check_strings(key)
                check_strings(child)
        elif isinstance(item, list):
            for child in item:
                check_strings(child)

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(instance) as (client, _):
                result = await client.call_tool("consult_advisor", value)
                response = result.structuredContent
                advisor.validate_response(response, value)
                assert json.loads(result.content[0].text) == response
                for field in ("request_id", "gate", "session_id"):
                    assert response[field] == value[field]
                expected = {"unavailable": "PROVIDER_UNAVAILABLE", "timeout": "TIMEOUT",
                            "schema": "PROVIDER_SCHEMA_INVALID"}.get(outcome)
                assert result.isError == (outcome != "success")
                assert (response["error"]["code"] if response["error"] else None) == expected
                check_strings(result.model_dump())
                check_strings(provider.calls)

    anyio.run(scenario)
    assert instance._active == 0 and instance._requests == {value["request_id"]}
    assert len(provider.calls) == (0 if outcome == "unavailable" else 3 if outcome == "timeout" else 1)
    assert TOKEN not in caplog.text + str(capsys.readouterr())
    assert secret not in caplog.text


@pytest.mark.parametrize("secret", [TOKEN, "signing_key:signing-private-canary", "private_key:key-private-canary", *PROVIDER_TOKENS],
                         ids=["dispatch", "signing_key", "private_key", *PROVIDER_IDS])
@pytest.mark.parametrize("field", ["gate", "session_id", "request_id", "advice", "limitations", "provider_request_id", "error"])
def test_response_secret_sweep_rejects_rehashed_echo_and_nested_fields(field, secret):
    if field in ("gate", "session_id", "request_id"):
        secret = secret.replace(":", "_")
    value = request()
    response = consult(bridge(FakeProvider(error=TimeoutError())) if field == "error" else bridge(FakeProvider()), value)
    response[field] = [secret] if field == "limitations" else response[field]
    if field == "error":
        response[field]["message"] = secret
    elif field != "limitations":
        response[field] = secret
    if field in ("gate", "session_id", "request_id"):
        value[field] = secret
    response["response_sha256"] = hashlib.sha256(advisor.json_bytes(
        {key: item for key, item in response.items() if key != "response_sha256"})).hexdigest()
    with pytest.raises(advisor.ToolError, match="^ERR_SECRET_RESPONSE$"):
        advisor.validate_response(response, value)


@pytest.mark.parametrize("secret", [TOKEN, "signing_key=signing-private-canary", "private_key=key-private-canary", *PROVIDER_TOKENS],
                         ids=["dispatch", "signing_key", "private_key", *PROVIDER_IDS])
def test_secret_response_fault_releases_permit_without_mcp_egress(monkeypatch, capsys, caplog, secret):
    provider = FakeProvider()
    instance = bridge(provider)
    monkeypatch.setattr(advisor, "provider_advice", lambda *args: (secret, None))

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(instance) as (client, _):
                result = await client.call_tool("consult_advisor", request())
                assert result.isError and result.structuredContent is None
                assert result.content[0].text == "ERR_SECRET_RESPONSE"
                assert secret not in result.model_dump_json()
                assert instance._active == 0 and instance._requests == {"request_1"}
                replay = await client.call_tool("consult_advisor", request())
                assert replay.content[0].text == "ERR_REPLAYED_REQUEST"

    anyio.run(scenario)
    assert len(provider.calls) == 1
    assert secret not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("fault", ["start", "complete"], ids=str)
def test_untrusted_tool_error_text_never_crosses_mcp_boundary(fault, capsys, caplog):
    secret = "client_secret=clock-private-canary " + TOKEN
    times = iter([advisor.ToolError(secret)] if fault == "start" else [NOW, advisor.ToolError(secret)])

    def clock():
        value = next(times)
        if isinstance(value, Exception):
            raise value
        return value

    provider = FakeProvider()
    instance = advisor.AdvisorBridge(authority(), provider, clock=clock)

    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(instance) as (client, _):
                result = await client.call_tool("consult_advisor", request())
                assert result.isError and result.structuredContent is None
                assert result.content[0].text == "ERR_INTERNAL_ERROR"
                assert TOKEN not in result.model_dump_json()

    anyio.run(scenario)
    assert len(provider.calls) == (0 if fault == "start" else 1)
    assert instance._active == 0 and instance._requests == {"request_1"}
    assert TOKEN not in caplog.text + str(capsys.readouterr())
    assert "clock-private-canary" not in caplog.text


@pytest.mark.parametrize("specimen", [TOKEN, *PROVIDER_TOKENS], ids=["dispatch", *PROVIDER_IDS])
def test_secret_identifier_rejection_preserves_concurrent_owner(capsys, caplog, specimen):
    async def scenario():
        entered, release = anyio.Event(), anyio.Event()
        calls, results = [], []

        async def provider(payload):
            calls.append(deepcopy(payload))
            entered.set()
            await release.wait()
            return advisor.json_bytes(provider_body())

        instance = bridge(provider)

        async def owner():
            results.append(await instance.consult(request("owner")))

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(owner)
                await entered.wait()
                with pytest.raises(advisor.ToolError, match="^ERR_SECRET_IDENTITY$"):
                    await instance.consult(request(specimen))
                assert instance._requests == {"owner"} and instance._active == 1
                assert len(calls) == 1
                release.set()
        assert instance._active == 0 and results[0]["request_id"] == "owner"

    anyio.run(scenario)
    output = caplog.text + str(capsys.readouterr())
    assert TOKEN not in output and specimen not in output


def test_scope_is_read_only_even_on_provider_and_publication_faults(monkeypatch, tmp_path):
    snapshot = tmp_path / "prior-evidence.json"
    snapshot.write_bytes(b'{"prior":"immutable"}')

    def reject(*args, **kwargs):
        raise AssertionError("Unauthorized side effect")

    with monkeypatch.context() as patches:
        patches.setattr(os, "replace", reject)
        patches.setattr(os, "fsync", reject)
        patches.setattr(Path, "read_bytes", reject)
        patches.setattr(Path, "write_bytes", reject)
        patches.setattr(subprocess, "run", reject)
        value = request()
        value["context"]["instructions"] = "Review __AWS_SECRET_ACCESS_KEY=readonly-private __DB_PASSWORD=readonly-access-private"
        bind_context(value)
        provider = FakeProvider(error=PermissionError("refresh_token=locked-private"))
        result = consult(bridge(provider), value)
        assert result["status"] == "error" and result["error"]["code"] == "INTERNAL_ERROR"
        assert "private" not in json.dumps(provider.calls) + json.dumps(result)
        result = consult(bridge(FakeProvider(provider_body(advice="client_secret=readonly-private"))), value)
        assert result["status"] == "advice" and result["advice"] == "[REDACTED]"
    assert snapshot.read_bytes() == b'{"prior":"immutable"}'


def test_standing_config_test_isolation_snapshot_restore():
    # Execute the existing fixture teardown, including nested mutations.
    import importlib.util
    import omega.api.routes.copilot as copilot

    spec = importlib.util.spec_from_file_location("_advisor_config_regression", ROOT / "tests/test_ui_llm_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = deepcopy(copilot._IN_MEMORY_LLM_CONFIG)
    fixture = module.restore_llm_config.__wrapped__()
    next(fixture)
    try:
        copilot._IN_MEMORY_LLM_CONFIG["global_profile"]["model"] = "mutated"
        copilot._IN_MEMORY_LLM_CONFIG["temporary"] = {"secret": "fixture-canary"}
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    assert copilot._IN_MEMORY_LLM_CONFIG == original


@pytest.mark.parametrize("code", ["TIMEOUT", "RATE_LIMITED", "PROVIDER_UNAVAILABLE", "AUTH_FAILED", "MODEL_UNAVAILABLE"], ids=str)
@pytest.mark.parametrize("model", advisor.MODELS, ids=["sol", "astra"])
def test_provider_failure_bounded_retry_no_implicit_downgrade(code, model):
    provider = FakeProvider(error=advisor.ProviderFailure(code))
    value = request(model=model)
    result = consult(bridge(provider), value)
    advisor.validate_response(result, value)
    assert result["status"] == "error" and result["advice"] is None
    assert result["error"] == {"code": code, "message": "Advisor provider failed: " + code, "retryable": False}
    expected_attempts = 3 if code in advisor.TRANSIENT_CODES else 1
    assert result["attempts"] == expected_attempts and result["retries"] == expected_attempts - 1
    assert [call["model"] for call in provider.calls] == [model] * expected_attempts


def test_unconfigured_runtime_never_egresses():
    value = request()
    result = consult(bridge(), value)
    advisor.validate_response(result, value)
    assert result["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert result["attempts"] == result["retries"] == 0
    assert result["provider_request_id"] is None


@pytest.mark.parametrize("variant", ["model", "missing_model", "empty", "whitespace", "truncated", "tool_call", "role", "duplicate", "oversize", "utf8", "null"], ids=str)
def test_provider_schema_is_untrusted_and_fail_closed(variant):
    body = provider_body()
    message = body["choices"][0]["message"]
    if variant == "model":
        body["model"] = advisor.MODELS[1]
    elif variant == "missing_model":
        del body["model"]
    elif variant in ("empty", "whitespace"):
        message["content"] = "" if variant == "empty" else "   "
    elif variant == "truncated":
        body["choices"][0]["finish_reason"] = "length"
    elif variant == "tool_call":
        message["tool_calls"] = [{"name": "shell"}]
    elif variant == "role":
        message["role"] = "tool"
    elif variant == "duplicate":
        body = b'{"model":"cx/gpt-6.1-sol","model":"cx/gpt-6-astra"}'
    elif variant == "oversize":
        body = b"x" * (advisor.MAX_RESPONSE_BYTES + 1)
    elif variant == "utf8":
        body = b"\xff"
    else:
        body = b"null"
    result = consult(bridge(FakeProvider(body)), request())
    assert result["status"] == "error" and result["advice"] is None
    assert result["error"]["retryable"] is False


@pytest.mark.parametrize("field", list(advisor.RESPONSE_SCHEMA["required"]))
def test_missing_response_fields_rejected(field):
    value = request()
    response = consult(bridge(FakeProvider()), value)
    del response[field]
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(response, value)


@pytest.mark.parametrize("field", [key for key in advisor.RESPONSE_SCHEMA["required"] if key not in ("advice", "error", "provider_request_id")])
def test_nonnullable_response_fields_rejected(field):
    value = request()
    response = consult(bridge(FakeProvider()), value)
    response[field] = None
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(response, value)


@pytest.mark.parametrize("field", list(advisor.RESPONSE_SCHEMA["required"]))
def test_every_response_field_tamper_is_rejected(field):
    value = request()
    response = consult(bridge(FakeProvider()), value)
    if field == "error":
        response[field] = {"code": "TIMEOUT", "message": "fixed", "retryable": False}
    elif field == "limitations":
        response[field] = ["changed"]
    elif type(response[field]) is int:
        response[field] += 1
    else:
        response[field] = "changed"
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(response, value)


def test_response_canonical_golden_preimage_and_nested_error_mutation():
    value = request()
    result = consult(bridge(FakeProvider(provider_body(advice='Việt Nam\r\n"é"'))), value)
    preimage = {key: val for key, val in result.items() if key != "response_sha256"}
    expected = json.dumps(preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert b'"error":null' in expected and b'\\r\\n' in expected
    assert result["response_sha256"] == hashlib.sha256(expected).hexdigest()
    reordered = dict(reversed(list(result.items())))
    advisor.validate_response(reordered, value)
    result["limitations"].reverse()
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(result, value)
    error = consult(bridge(FakeProvider(error=TimeoutError())), value)
    error["error"]["message"] = "changed"
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(error, value)


def test_closed_schema_jcs_golden_vector():
    preimage = {"z": None, "b": [], "a": "é\r\n\"\\", "error": {
        "retryable": False, "message": "Fixed", "code": "TIMEOUT"}, "attempts": 1}
    golden = b'{"a":"\xc3\xa9\\r\\n\\\"\\\\","attempts":1,"b":[],"error":{"code":"TIMEOUT","message":"Fixed","retryable":false},"z":null}'
    assert advisor.json_bytes(preimage) == golden
    assert hashlib.sha256(advisor.json_bytes(preimage)).digest() == hashlib.sha256(golden).digest()


def test_sdk_debug_and_unknown_tool_logs_cannot_leak(caplog):
    async def scenario():
        with caplog.at_level(logging.DEBUG, logger="mcp"):
            async with client_for(bridge(FakeProvider())) as (client, _):
                result = await client.call_tool(TOKEN, {"dispatch_token": TOKEN})
                assert result.isError and result.content[0].text == "ERR_UNKNOWN_TOOL"
    anyio.run(scenario)
    assert TOKEN not in caplog.text


def test_cross_field_response_invariants_survive_rehash():
    value = request()
    base = consult(bridge(FakeProvider()), value)
    changes = [{"attempts": True}, {"attempts": 1.0}, {"retries": 1},
               {"completed_at": "2026-10-04T11:59:59.000Z"}, {"advice": "  "},
               {"extra": None}, {"as_of_time": "2026-10-04T11:59:59Z"},
               {"started_at": "2026-02-30T12:00:00.000Z"},
               {"limitations": ["line\nbreak"]}, {"provider_request_id": "unsafe/id"}]
    for change in changes:
        result = {**base, **change}
        preimage = {key: val for key, val in result.items() if key != "response_sha256"}
        result["response_sha256"] = hashlib.sha256(advisor.json_bytes(preimage)).hexdigest()
        with pytest.raises(advisor.ToolError):
            advisor.validate_response(result, value)
    failed = consult(bridge(FakeProvider(error=TimeoutError())), value)
    failed["error"]["extra"] = "schema drift"
    failed["response_sha256"] = hashlib.sha256(advisor.json_bytes({key: val for key, val in failed.items() if key != "response_sha256"})).hexdigest()
    with pytest.raises(advisor.ToolError):
        advisor.validate_response(failed, value)


def test_byte_depth_observation_and_session_limits(monkeypatch):
    provider = FakeProvider()
    instance = bridge(provider)
    for count in (129,):
        value = request()
        value["context"]["observations"] *= count
        bind_context(value)
        with pytest.raises(advisor.ToolError):
            consult(instance, value)
    value = request()
    value["context"]["observations"][0]["data"] = "é" * 25000
    bind_context(value)
    with pytest.raises(advisor.ToolError, match="ERR_CONTEXT_TOO_LARGE"):
        consult(instance, value)
    value["context"]["observations"][0]["data"] = "a" * 65536
    with pytest.raises(advisor.ToolError):
        consult(instance, value)
    nested = 0
    for _ in range(18):
        nested = [nested]
    value["context"]["observations"][0]["data"] = nested
    with pytest.raises(advisor.ToolError):
        consult(instance, value)
    assert not provider.calls and not instance._requests
    monkeypatch.setattr(advisor, "MAX_CALLS", 2)
    consult(instance, request("first"))
    consult(instance, request("second"))
    with pytest.raises(advisor.ToolError, match="ERR_BUDGET_EXCEEDED"):
        consult(instance, request("third"))
    assert len(provider.calls) == 2 and len(instance._requests) == 2


def test_timeout_cancellation_capacity_and_duplicate_races(monkeypatch):
    async def scenario():
        entered, stopped = anyio.Event(), anyio.Event()
        scopes = []

        async def slow(payload):
            assert "cancellation-private" not in json.dumps(payload)
            entered.set()
            try:
                await anyio.sleep_forever()
            finally:
                stopped.set()

        instance = bridge(slow)

        async def invoke():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                value = request("pending")
                value["context"]["instructions"] = "Review _signing_key=cancellation-private __PRIVATE_KEY=cancellation-private"
                await instance.consult(bind_context(value))

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(invoke)
            await entered.wait()
            with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
                await instance.consult(request("pending"))
            monkeypatch.setattr(advisor, "MAX_CONCURRENT", 1)
            with pytest.raises(advisor.ToolError, match="ERR_CAPACITY_EXCEEDED"):
                await instance.consult(request("other"))
            assert "other" not in instance._requests
            scopes[0].cancel()
            await stopped.wait()
        assert instance._active == 0
        with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
            await instance.consult(request("pending"))
        monkeypatch.setattr(advisor, "DEADLINE_SECONDS", 0.01)
        value = request("timeout")
        value["context"]["instructions"] = "Review private-key=cancellation-private"
        result = await instance.consult(bind_context(value))
        assert result["error"]["code"] == "TIMEOUT" and instance._active == 0

    anyio.run(scenario)


def test_two_concurrent_calls_remain_isolated_and_third_has_no_reservation():
    async def scenario():
        both_entered, release = anyio.Event(), anyio.Event()
        seen, results = [], []

        async def provider(payload):
            seen.append(payload["model"])
            assert "concurrent-private" not in json.dumps(payload)
            if len(seen) == 2:
                both_entered.set()
            await release.wait()
            body = provider_body(payload["model"], advice="__SIGNING_KEY=response-concurrent-private")
            body["id"] = "__PRIVATE_KEY:identifier-concurrent-private"
            return advisor.json_bytes(body)

        instance = bridge(provider)

        async def invoke(name, model):
            value = request(name, model)
            value["context"]["instructions"] = f"Review _signing_key={name}-concurrent-private __PRIVATE_KEY={name}-access-concurrent-private"
            results.append(await instance.consult(bind_context(value)))

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(invoke, "first", advisor.MODELS[0])
                tasks.start_soon(invoke, "second", advisor.MODELS[1])
                await both_entered.wait()
                with pytest.raises(advisor.ToolError, match="ERR_CAPACITY_EXCEEDED"):
                    await instance.consult(request("third"))
                assert instance._active == 2 and "third" not in instance._requests
                release.set()
        assert {item["request_id"] for item in results} == {"first", "second"}
        assert {item["model"] for item in results} == set(advisor.MODELS)
        assert all(item["advice"] == "[REDACTED]" for item in results)
        assert all(item["provider_request_id"] is None for item in results)
        assert instance._active == 0 and len(seen) == 2

    anyio.run(scenario)


@asynccontextmanager
async def client_for(instance):
    server = advisor.create_server(instance)
    client_tx, server_rx = anyio.create_memory_object_stream(0)
    server_tx, client_rx = anyio.create_memory_object_stream(0)
    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, server_rx, server_tx, server.create_initialization_options())
            async with ClientSession(client_rx, client_tx) as client:
                await client.initialize()
                yield client, server
            tasks.cancel_scope.cancel()


def test_official_mcp_initialize_list_call_errors_and_reconnect(capsys):
    async def scenario():
        provider = FakeProvider()
        instance = bridge(provider)
        async with client_for(instance) as (client, server):
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["consult_advisor"]
            assert tools.tools[0].inputSchema == advisor.REQUEST_SCHEMA
            assert tools.tools[0].outputSchema == advisor.RESPONSE_SCHEMA
            result = await client.call_tool("consult_advisor", request())
            assert not result.isError
            advisor.validate_response(result.structuredContent, request())
            invalid = request("bad")
            invalid["gate"] = "spoofed"
            failure = await client.call_tool("consult_advisor", invalid)
            assert failure.isError and failure.structuredContent is None
            assert failure.content[0].text == "ERR_UNAUTHORIZED_IDENTITY"
            unknown = await client.call_tool("shell", {"command": TOKEN})
            assert unknown.isError and unknown.content[0].text == "ERR_UNKNOWN_TOOL"
            with pytest.raises(McpError):
                await client.list_resources()
            assert len(provider.calls) == 1
        async with client_for(instance) as (client, _):
            replay = await client.call_tool("consult_advisor", request())
            assert replay.isError and replay.content[0].text == "ERR_REPLAYED_REQUEST"
        async with client_for(bridge()) as (client, _):
            failed = await client.call_tool("consult_advisor", request())
            assert failed.isError and failed.structuredContent["attempts"] == 0

    anyio.run(scenario)
    assert capsys.readouterr().out == ""


def test_official_mcp_cancellation_releases_owner_permit():
    async def scenario():
        entered, stopped = anyio.Event(), anyio.Event()
        request_ids = []
        server = None

        async def slow(payload):
            request_ids.append(server.request_context.request_id)
            entered.set()
            try:
                await anyio.sleep_forever()
            finally:
                stopped.set()

        instance = bridge(slow)
        async with client_for(instance) as (client, running_server):
            server = running_server

            async def invoke():
                with pytest.raises(McpError):
                    await client.call_tool("consult_advisor", request())

            async with anyio.create_task_group() as calls:
                calls.start_soon(invoke)
                await entered.wait()
                await client.send_notification(types.ClientNotification(types.CancelledNotification(
                    params=types.CancelledNotificationParams(requestId=request_ids[0], reason="cancel"))))
                await stopped.wait()
            assert instance._active == 0
            assert instance._requests == {"request_1"}

    anyio.run(scenario)


def test_strict_bounded_stdio_adapter_and_fatal_frames():
    class Source:
        def __init__(self, raw):
            self.raw = io.BytesIO(raw)
            self.limits = []

        def readline(self, limit):
            self.limits.append(limit)
            return self.raw.readline(limit)

    async def read(raw):
        source = Source(raw)
        result = [frame async for frame in advisor.StrictStdin(source)]
        assert set(source.limits) == {advisor.MAX_REQUEST_BYTES + 1}
        return result

    valid = b'{"jsonrpc":"2.0","method":"ping","id":1}\r\n'
    assert len(anyio.run(read, valid)) == 1
    for raw in (b"\xff\n", b"\xef\xbb\xbf{}\n", b"{}\n", b'{"id":1,"id":2}\n', b"x" * 65537 + b"\n", valid.rstrip(),
                b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":123,"arguments":{"dispatch_token":"secret"}}}\n',
                b'{"jsonrpc":"2.0","method":"unknown","params":{"secret":"private"}}\n'):
        with pytest.raises(advisor.ToolError):
            anyio.run(read, raw)


def test_stdio_process_protocol_stdout_and_nonzero_failure():
    env = {key: value for key, value in os.environ.items() if not key.startswith("OMEGA_DISPATCH_")}
    env["NINE_ROUTER_API_KEY"] = "OFFLINE_ROUTER_CANARY"
    command = [sys.executable, "-c", (
        "import httpx; from scripts import l4_mcp_advisor as advisor; original = httpx.AsyncClient; "
        "httpx.AsyncClient = lambda **kwargs: original(transport=httpx.MockTransport(lambda _: httpx.Response(401)), **kwargs); "
        "raise SystemExit(advisor.main())"
    )]
    failed = subprocess.run(command, input=b"", capture_output=True, cwd=ROOT, env=env, timeout=10)
    assert failed.returncode != 0 and failed.stdout == b""
    assert failed.stderr.strip() == b"ERR_ADVISOR_STARTUP_OR_TRANSPORT"
    env.update(launch_env())
    invalid = subprocess.run(command, input=b"\xff\n", capture_output=True, cwd=ROOT, env=env, timeout=10)
    assert invalid.returncode != 0 and TOKEN.encode() not in invalid.stderr
    malformed = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": 123, "arguments": {"dispatch_token": TOKEN}}}
    invalid = subprocess.run(command, input=json.dumps(malformed).encode() + b"\n",
                             capture_output=True, cwd=ROOT, env=env, timeout=10)
    assert invalid.returncode != 0 and invalid.stdout == b""
    assert invalid.stderr.strip() == b"ERR_ADVISOR_STARTUP_OR_TRANSPORT"
    assert TOKEN.encode() not in invalid.stderr

    async def scenario():
        process = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=env,
                                                       stdin=asyncio.subprocess.PIPE,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        try:
            async def send(message):
                process.stdin.write(json.dumps(message).encode() + b"\n")
                await process.stdin.drain()

            await send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "offline-test", "version": "1"}}})
            initialized = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
            assert initialized["id"] == 1 and "result" in initialized
            await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listed = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
            assert listed["id"] == 2
            assert [tool["name"] for tool in listed["result"]["tools"]] == ["consult_advisor"]
            await send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "consult_advisor", "arguments": request()}})
            result = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
            assert result["result"]["isError"] is True
            advisor.validate_response(result["result"]["structuredContent"], request())
            assert result["result"]["structuredContent"]["attempts"] == 1
            assert result["result"]["structuredContent"]["error"]["code"] == "AUTH_FAILED"
            process.stdin.close()
            await asyncio.wait_for(process.wait(), 5)
            extra, errors = await process.communicate()
            assert extra == b"" and TOKEN.encode() not in errors
            assert process.returncode == 1
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    asyncio.run(scenario())


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.delays = []

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


def low_risk_request(model=advisor.MODELS[0]):
    value = request(model=model)
    value["risk"] = "low"
    bound = advisor.LaunchAuthority(value["gate"], value["session_id"], 9, "low",
                                    hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
    return value, bound


def receipt_metadata(response):
    return {**{key: response[key] for key in advisor.RECEIPT_RESPONSE_FIELDS},
            "error_code": response["error"]["code"] if response["error"] else None}


@pytest.mark.parametrize("code", sorted(advisor.TRANSIENT_CODES))
@pytest.mark.parametrize("retry_after,expected", [(None, 1), (0, 1), (2.5, 2.5), (1e300, 4), (10**1000, 4)],
                         ids=["none", "zero", "fraction", "large_float", "huge_int"])
def test_stage2_retry_after_jitter_shared_attempts_and_secret_safe_payload(code, retry_after, expected):
    timer, calls = FakeTime(), []

    async def provider(payload):
        calls.append(deepcopy(payload))
        if len(calls) < 3:
            raise advisor.ProviderFailure(code, retry_after)
        return advisor.json_bytes(provider_body(advice="DB_PASSWORD=private-canary"))

    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     monotonic=timer.monotonic, sleep=timer.sleep, jitter=lambda: 1)
    value = request()
    value["context"]["instructions"] = "Review client_secret=private-canary"
    bind_context(value)
    response = consult(instance, value)
    advisor.validate_response(response, value)
    assert response["status"] == "advice" and response["attempts"] == 3 and response["retries"] == 2
    assert timer.delays == [expected, expected]
    assert {call["model"] for call in calls} == {value["model"]}
    assert len({call["messages"][1]["content"] for call in calls}) == 1
    assert "private-canary" not in json.dumps(calls) + json.dumps(response)
    assert instance._provider_attempts == 3 and instance._active == 0


@pytest.mark.parametrize("bad", [True, "4", [], float("nan"), float("inf"), -1])
def test_stage2_malformed_retry_after_is_terminal(bad):
    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED", bad))
    response = consult(bridge(provider), request())
    assert response["error"]["code"] == "INTERNAL_ERROR" and response["attempts"] == 1
    assert len(provider.calls) == 1


@pytest.mark.parametrize("bad", [True, "1", [], 0, 5, float("nan"), float("inf"), 10**1000],
                         ids=["boolean", "string", "list", "zero", "large", "nan", "inf", "huge_int"])
def test_stage2_malformed_jitter_is_terminal(bad):
    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))
    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     sleep=no_sleep, jitter=lambda: bad)
    response = consult(instance, request())
    assert response["error"]["code"] == "INTERNAL_ERROR" and response["attempts"] == 1


@pytest.mark.parametrize("code", [code for code in advisor.ERROR_CODES if code not in advisor.TRANSIENT_CODES])
def test_stage2_terminal_provider_errors_never_retry_or_fallback(code):
    value, bound = low_risk_request()
    provider = FakeProvider(error=advisor.ProviderFailure(code))
    instance = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW, sleep=no_sleep,
                                     fallback_model=advisor.MODELS[1])
    response = consult(instance, value)
    assert response["error"]["code"] == code and response["attempts"] == 1
    assert [call["model"] for call in provider.calls] == [value["model"]]


@pytest.mark.parametrize("primary", advisor.MODELS, ids=["sol", "astra"])
def test_stage2_explicit_low_risk_fallback_binds_actual_model_and_shared_limits(primary):
    value, bound = low_risk_request(primary)
    fallback = next(model for model in advisor.MODELS if model != primary)
    calls = []

    async def provider(payload):
        calls.append(deepcopy(payload))
        if len(calls) < 3:
            raise advisor.ProviderFailure("RATE_LIMITED")
        return advisor.json_bytes(provider_body(payload["model"]))

    instance = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW, sleep=no_sleep,
                                     jitter=lambda: 1, fallback_model=fallback)
    response = consult(instance, value)
    advisor.validate_response(response, value, fallback)
    with pytest.raises(advisor.ToolError, match="ERR_RESPONSE_MISMATCH"):
        advisor.validate_response(response, value)
    assert response["model"] == fallback and response["attempts"] == 3 and response["retries"] == 2
    assert [call["model"] for call in calls] == [primary, fallback, fallback]
    assert len({call["messages"][1]["content"] for call in calls}) == 1


@pytest.mark.parametrize("bad", [True, [], "sonnet", "cx/*", "cx/gpt-6-astra(low)"])
def test_stage2_fallback_configuration_rejects_unlisted_models(bad):
    _, bound = low_risk_request()
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        advisor.AdvisorBridge(bound, fallback_model=bad)


def test_stage2_high_risk_fallback_configuration_fails_closed():
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        advisor.AdvisorBridge(authority(), fallback_model=advisor.MODELS[1])


@pytest.mark.parametrize("branch", ["provider", "backoff", "expired_before_attempt"],
                         ids=["elapsed_provider", "backoff", "expired_before_attempt"])
def test_stage2_monotonic_total_deadline_stops_attempts(branch, monkeypatch):
    timer, calls = FakeTime(), []
    monkeypatch.setattr(advisor, "DEADLINE_SECONDS", 2)

    async def provider(payload):
        calls.append(payload)
        timer.now += 2 if branch == "provider" else 1
        if branch == "provider":
            return advisor.json_bytes(provider_body())
        raise advisor.ProviderFailure("RATE_LIMITED")

    ticks = iter([0, 2])
    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     monotonic=(lambda: next(ticks)) if branch == "expired_before_attempt" else timer.monotonic,
                                     sleep=timer.sleep, jitter=lambda: 1)
    response = consult(instance, request())
    assert response["error"]["code"] == "TIMEOUT" and response["advice"] is None
    assert response["attempts"] == len(calls) == (0 if branch == "expired_before_attempt" else 1)
    assert timer.delays == [] and instance._active == 0


def test_stage2_total_deadline_during_backoff_preserves_counters(monkeypatch):
    monkeypatch.setattr(advisor, "DEADLINE_SECONDS", 2)
    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))

    async def slow_sleep(_):
        await anyio.sleep_forever()

    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     sleep=slow_sleep, jitter=lambda: 1, monotonic=lambda: 0)
    response = consult(instance, request())
    assert response["error"]["code"] == "TIMEOUT" and response["attempts"] == 1
    assert response["retries"] == 0 and instance._active == 0


def test_stage2_circuit_cooldown_one_probe_and_recovery():
    async def scenario():
        timer = FakeTime()
        entered, release = anyio.Event(), anyio.Event()
        calls, results = [], []

        async def provider(payload):
            calls.append(payload)
            if len(calls) <= 3:
                raise advisor.ProviderFailure("RATE_LIMITED")
            entered.set()
            await release.wait()
            return advisor.json_bytes(provider_body())

        instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                         monotonic=timer.monotonic, sleep=timer.sleep, jitter=lambda: 1)
        failed = await instance.consult(request("exhausted"))
        assert failed["attempts"] == 3
        blocked = await instance.consult(request("blocked"))
        assert blocked["error"]["code"] == "CIRCUIT_OPEN" and blocked["attempts"] == 0
        timer.now += 59
        blocked = await instance.consult(request("not_yet"))
        assert blocked["attempts"] == 0
        timer.now += 1

        async def probe():
            results.append(await instance.consult(request("probe")))

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(probe)
                await entered.wait()
                blocked = await instance.consult(request("competing_probe"))
                assert blocked["error"]["code"] == "CIRCUIT_OPEN" and blocked["attempts"] == 0
                release.set()
        assert results[0]["status"] == "advice" and instance._opened_at is None
        assert not instance._probe and instance._active == 0 and len(calls) == 4

    anyio.run(scenario)


@pytest.mark.parametrize("code", ["TIMEOUT", "AUTH_FAILED"])
def test_stage2_failed_half_open_probe_reopens_without_retry(code):
    timer = FakeTime()
    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))
    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     monotonic=timer.monotonic, sleep=timer.sleep, jitter=lambda: 1)
    consult(instance, request())
    timer.now += 60
    provider.error = advisor.ProviderFailure(code)
    response = consult(instance, request("probe"))
    assert response["attempts"] == 1 and response["error"]["code"] == code
    assert instance._opened_at == timer.now and not instance._probe
    blocked = consult(instance, request("blocked"))
    assert blocked["error"]["code"] == "CIRCUIT_OPEN" and len(provider.calls) == 4


def test_stage2_provider_attempt_budget_shared_across_requests(monkeypatch):
    monkeypatch.setattr(advisor, "MAX_PROVIDER_ATTEMPTS", 2)
    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))
    instance = bridge(provider)
    result = consult(instance, request())
    assert result["error"]["code"] == "BUDGET_EXCEEDED" and result["attempts"] == 2
    blocked = consult(instance, request("next"))
    assert blocked["error"]["code"] == "BUDGET_EXCEEDED" and blocked["attempts"] == 0
    assert instance._provider_attempts == len(provider.calls) == 2


@pytest.mark.parametrize("branch", ["backoff", "half_open"])
def test_stage2_cancellation_releases_capacity_and_probe(branch, tmp_path):
    async def scenario():
        entered = anyio.Event()
        scopes = []
        timer = FakeTime()
        provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))

        async def sleep(_):
            entered.set()
            await anyio.sleep_forever()

        instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                         monotonic=timer.monotonic, sleep=sleep, jitter=lambda: 1,
                                         receipt_directory=tmp_path)
        if branch == "half_open":
            instance._opened_at = -60

            async def waiting_provider(_):
                entered.set()
                await anyio.sleep_forever()

            instance.provider = waiting_provider

        async def invoke():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await instance.consult(request())

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(invoke)
                await entered.wait()
                assert instance._active == 1
                scopes[0].cancel()
        assert instance._active == 0 and not instance._probe
        restarted = bridge(FakeProvider(), receipt_directory=tmp_path)
        with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
            await restarted.consult(request())
        assert restarted.receipts.read(request()) is None

    anyio.run(scenario)


@pytest.mark.parametrize("outcome", ["advice", "error", "fallback"])
def test_stage2_durable_receipt_readback_restart_replay_and_no_credentials(tmp_path, outcome):
    value, bound = low_risk_request() if outcome == "fallback" else (request(), authority())
    calls = []

    async def provider(payload):
        calls.append(payload)
        if outcome == "error" or outcome == "fallback" and len(calls) == 1:
            raise advisor.ProviderFailure("RATE_LIMITED")
        return advisor.json_bytes(provider_body(payload["model"], "signing_key=receipt-private-canary"))

    instance = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW, sleep=no_sleep, jitter=lambda: 1,
                                     receipt_directory=tmp_path,
                                     fallback_model=advisor.MODELS[1] if outcome == "fallback" else None)
    value["context"]["instructions"] = "Review private_key=receipt-private-canary"
    bind_context(value)
    response = consult(instance, value)
    assert instance.receipts.read(value) == receipt_metadata(response)
    persisted = instance.receipts.path.read_bytes()
    assert TOKEN.encode() not in persisted and b"receipt-private-canary" not in persisted
    assert b'"context"' not in persisted and b'"dispatch_token"' not in persisted
    assert b'"advice":' not in persisted and b'"limitations":' not in persisted
    restarted = advisor.AdvisorBridge(bound, provider, clock=lambda: NOW, sleep=no_sleep,
                                      receipt_directory=tmp_path,
                                      fallback_model=advisor.MODELS[1] if outcome == "fallback" else None)
    with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
        consult(restarted, value)
    assert restarted._requests == set() and restarted._active == 0
    assert persisted == instance.receipts.path.read_bytes()
    tampered = deepcopy(value)
    tampered["as_of_time"] = "2026-10-04T11:59:59Z"
    tampered["context"]["observations"] = []
    bind_context(tampered)
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT_INVALID"):
        instance.receipts.read(tampered)


@pytest.mark.parametrize("bad_path", ["missing", "directory_target", "lock_directory", "traversal", "type", "file_parent"])
def test_stage2_receipt_path_faults_fail_before_provider(tmp_path, bad_path):
    provider = FakeProvider()
    path = tmp_path
    if bad_path == "missing":
        path = tmp_path / "missing"
    elif bad_path == "traversal":
        path = tmp_path / ".." / tmp_path.name
    elif bad_path == "type":
        path = []
    elif bad_path == "file_parent":
        path = tmp_path / "file"
        path.write_bytes(b"prior")
    elif bad_path in ("directory_target", "lock_directory"):
        (tmp_path / (authority().session_id + (".json" if bad_path == "directory_target" else ".lock"))).mkdir()
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
        instance = bridge(provider, receipt_directory=path)
        consult(instance, request())
    assert not provider.calls


@pytest.mark.parametrize("corruption", ["partial", "duplicate", "utf8", "bom", "digest", "duplicate_id", "response_digest", "future", "foreign", "overflow", "credential", "signing_key", "private_key", "counter", "outcome"])
def test_stage2_corrupt_receipt_cannot_mutate_state_or_establish_advice(tmp_path, corruption):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(instance, request())
    ledger = json.loads(instance.receipts.path.read_bytes())
    if corruption == "partial":
        raw = b'{"entries":'
    elif corruption == "duplicate":
        raw = b'{"entries":[],"entries":[]}'
    elif corruption == "utf8":
        raw = b'"\xff"'
    elif corruption == "bom":
        raw = b"\xef\xbb\xbf" + advisor.json_bytes(ledger)
    elif corruption == "overflow":
        raw = b"x" * (advisor.RECEIPT_LIMIT + 1)
    else:
        if corruption == "digest":
            ledger["receipt_sha256"] = "0" * 64
        elif corruption == "duplicate_id":
            ledger["entries"].append(deepcopy(ledger["entries"][0]))
        elif corruption == "response_digest":
            ledger["entries"][0]["response"]["advice"] = "Tampered."
        elif corruption == "future":
            ledger["entries"][0]["request"]["as_of_time"] = "2026-10-04T12:00:01Z"
        elif corruption == "credential":
            ledger["entries"][0]["response"]["provider_request_id"] = TOKEN
        elif corruption in ("signing_key", "private_key"):
            ledger["entries"][0]["response"]["provider_request_id"] = corruption + ":receipt-private-canary"
        elif corruption == "counter":
            ledger["entries"][0]["response"]["retries"] = 2
        elif corruption == "outcome":
            ledger["entries"][0]["response"]["error_code"] = "AUTH_FAILED"
        else:
            ledger["entries"][0]["request"]["gate"] = "FOREIGN"
        if corruption != "digest":
            ledger["receipt_sha256"] = hashlib.sha256(advisor.json_bytes({key: val for key, val in ledger.items() if key != "receipt_sha256"})).hexdigest()
        raw = advisor.json_bytes(ledger)
    instance.receipts.path.write_bytes(raw)
    provider = FakeProvider()
    restarted = bridge(provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
        consult(restarted, request("next"))
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
        restarted.receipts.read(request())
    assert restarted._active == 0 and not restarted._requests and not provider.calls
    assert restarted.receipts.path.read_bytes() == raw
    if corruption in ("signing_key", "private_key"):
        restarted.receipts.rollback_path.write_bytes(raw)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            restarted.receipts.recover()
        assert restarted.receipts.path.read_bytes() == restarted.receipts.rollback_path.read_bytes() == raw


@pytest.mark.parametrize("phase", ["reservation", "publication"])
@pytest.mark.parametrize("fault", ["temp", "fsync", "replace", "readback"],
                         ids=["temp", "fsync", "atomic_replace", "readback"])
@pytest.mark.parametrize("error_number", [errno.EACCES, errno.ENOSPC], ids=["permission", "disk_full"])
def test_stage2_receipt_atomic_faults_preserve_prior_and_cleanup(tmp_path, monkeypatch, phase, fault, error_number):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    consult(instance, request("prior"))
    prior = instance.receipts.path.read_bytes()
    original_read = instance.receipts._read
    reads = 0

    def faulty_read(*args, **kwargs):
        nonlocal reads
        reads += 1
        if reads == 2:
            raise OSError(error_number, "signing_key=filesystem-private-canary private_key=filesystem-private-canary")
        return original_read(*args, **kwargs)

    def fail(*args, **kwargs):
        raise OSError(error_number, "signing_key=filesystem-private-canary private_key=filesystem-private-canary")

    def inject():
        if fault == "temp":
            monkeypatch.setattr(advisor.tempfile, "mkstemp", fail)
        elif fault == "readback":
            monkeypatch.setattr(instance.receipts, "_read", faulty_read)
        else:
            monkeypatch.setattr(os, fault, fail)

    if phase == "publication":
        async def failing_publication(payload):
            nonlocal prior
            provider.calls.append(payload)
            prior = instance.receipts.path.read_bytes()
            inject()
            return advisor.json_bytes(provider_body())
        instance.provider = failing_publication
    else:
        inject()
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT") as error:
        consult(instance, request("faulted"))
    assert "private-canary" not in str(error.value)
    assert instance.receipts.path.read_bytes() == prior
    assert not list(tmp_path.glob("*.tmp")) and instance._active == 0
    assert len(provider.calls) == (1 if phase == "reservation" else 2)
    assert ("faulted" in instance._requests) == (phase == "publication")


@pytest.mark.parametrize("phase", ["reservation", "publication"])
@pytest.mark.parametrize("fault", ["readback", "directory_sync"])
@pytest.mark.parametrize("rollback_fault", ["replace", "readback", "marker_delete"])
def test_stage2_receipt_double_fault_blocks_uncertain_outcome_until_recovery(
        tmp_path, monkeypatch, phase, fault, rollback_fault, capsys, caplog):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    consult(instance, request("prior"))
    store = instance.receipts
    prior = store.path.read_bytes()
    reads = syncs = 0
    original_read, original_replace = store._read, store._replace_bytes
    original_sync, original_unlink = store._sync_directory, Path.unlink
    dirty = "https://rollback-user:rollback-secret@example.com/?token=rollback-secret signing_key=rollback-secret private_key=rollback-secret " + TOKEN

    def faulty_read(*args, **kwargs):
        nonlocal reads
        if kwargs.get("path") == store.path:
            reads += 1
            if fault == "readback" and reads == 1 or rollback_fault == "readback" and reads == (2 if fault == "readback" else 1):
                raise advisor.ToolError(dirty)
        return original_read(*args, **kwargs)

    def faulty_sync():
        nonlocal syncs
        syncs += 1
        if fault == "directory_sync" and syncs == 2:
            raise OSError(dirty)
        original_sync()

    def faulty_replace(raw, path=None):
        if path is None and raw == prior and rollback_fault == "replace":
            raise OSError(dirty)
        original_replace(raw, path)

    def faulty_unlink(path, *args, **kwargs):
        assert path != store.path, "Existing canonical receipts must never be deleted"
        if path == store.rollback_path and rollback_fault == "marker_delete":
            raise OSError(dirty)
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        def inject():
            patches.setattr(store, "_read", faulty_read)
            patches.setattr(store, "_replace_bytes", faulty_replace)
            patches.setattr(store, "_sync_directory", faulty_sync)
            patches.setattr(Path, "unlink", faulty_unlink)

        if phase == "publication":
            async def failing_publication(payload):
                nonlocal prior
                provider.calls.append(payload)
                prior = store.path.read_bytes()
                inject()
                return advisor.json_bytes(provider_body())
            instance.provider = failing_publication
        else:
            inject()
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            consult(instance, request("faulted"))
        assert store.rollback_path.read_bytes() == prior
        assert store.path.exists() and not list(tmp_path.glob("*.tmp"))

    restarted_provider = FakeProvider()
    restarted = bridge(restarted_provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        restarted.receipts.read(request("faulted"))
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        consult(restarted, request("unrelated"))
    assert not restarted_provider.calls and not restarted._requests
    restarted.receipts.recover()
    assert store.path.read_bytes() == prior and not store.rollback_path.exists()
    assert restarted.receipts.read(request("prior"))["status"] == "advice"
    if phase == "publication":
        assert restarted.receipts.read(request("faulted")) is None
        with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
            consult(restarted, request("faulted"))
    assert instance._active == restarted._active == 0
    assert len(provider.calls) == (1 if phase == "reservation" else 2)
    assert "rollback-secret" not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("fault", ["snapshot_sync", "snapshot_readback", "lock", "foreign"])
def test_stage2_receipt_recovery_fault_retains_snapshot_and_denies_access(tmp_path, monkeypatch, fault):
    owner = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(owner, request())
    store = owner.receipts
    prior = store.path.read_bytes()
    store._replace_bytes(prior, store.rollback_path)
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    if fault == "foreign":
        foreign = advisor.LaunchAuthority("FOREIGN", authority().session_id, 9, "high",
                                          hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
        instance = advisor.AdvisorBridge(foreign, receipt_directory=tmp_path)

    def fail(*args, **kwargs):
        raise OSError("private_key=recovery-private-canary signing_key=recovery-private-canary")

    with monkeypatch.context() as patches:
        if fault == "snapshot_sync":
            patches.setattr(instance.receipts, "_sync_directory", fail)
        elif fault == "snapshot_readback":
            patches.setattr(instance.receipts, "_read", fail)
        if fault == "lock":
            with store.locked():
                with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
                    instance.receipts.recover()
        else:
            with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
                instance.receipts.recover()
    assert store.rollback_path.read_bytes() == prior
    assert store.path.read_bytes() == prior
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        store.read(request())
    store.recover()
    assert store.read(request())["status"] == "advice"


@pytest.mark.parametrize("fault", ["snapshot_fsync", "rollback_sync", "delete_new", "delete_marker"])
def test_stage2_new_receipt_double_fault_preserves_absence_marker(tmp_path, monkeypatch, fault):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    store = instance.receipts
    original_read, original_sync, original_unlink = store._read, store._sync_directory, Path.unlink
    syncs = 0

    def faulty_read(*args, **kwargs):
        if kwargs.get("path") == store.path:
            raise OSError("client_secret=new-receipt-private-canary")
        return original_read(*args, **kwargs)

    def faulty_sync():
        nonlocal syncs
        syncs += 1
        if fault == "snapshot_fsync" and syncs == 1 or fault == "rollback_sync" and syncs == 3:
            raise OSError("client_secret=new-receipt-private-canary")
        original_sync()

    def faulty_unlink(path, *args, **kwargs):
        if fault == "delete_new" and path == store.path or fault == "delete_marker" and path == store.rollback_path:
            raise OSError("client_secret=new-receipt-private-canary")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        patches.setattr(store, "_read", faulty_read)
        patches.setattr(store, "_sync_directory", faulty_sync)
        patches.setattr(Path, "unlink", faulty_unlink)
        with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
            consult(instance, request())
    assert store.rollback_path.read_bytes() == store.binding.encode("ascii")
    restarted = bridge(FakeProvider(), receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        consult(restarted, request())
    restarted.receipts.recover()
    assert not store.path.exists() and not store.rollback_path.exists()
    assert not provider.calls and not instance._requests and instance._active == 0


def test_stage2_receipt_pending_marker_blocks_both_mcp_channels(tmp_path, capsys, caplog):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    instance.receipts._replace_bytes(instance.receipts.binding.encode("ascii"), instance.receipts.rollback_path)

    async def scenario():
        async with client_for(instance) as (client, _):
            result = await client.call_tool("consult_advisor", request())
            assert result.isError and result.structuredContent is None
            assert result.content[0].text == "ERR_RECEIPT_IO"
            assert instance.failed
    anyio.run(scenario)
    assert not provider.calls and not instance._requests and instance._active == 0
    assert TOKEN not in caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("corruption", ["empty", "truncated", "oversize", "foreign_absence"])
def test_stage2_receipt_corrupt_recovery_marker_cannot_delete_prior(tmp_path, corruption):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(instance, request())
    store = instance.receipts
    prior = store.path.read_bytes()
    corrupt = {"empty": b"", "truncated": b'{"entries":',
               "oversize": b"x" * (advisor.RECEIPT_LIMIT + 1),
               "foreign_absence": b"0" * 64}[corruption]
    store.rollback_path.write_bytes(corrupt)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        store.recover()
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        store.read(request())
    assert store.path.read_bytes() == prior and store.rollback_path.read_bytes() == corrupt


@pytest.mark.parametrize("fault", ["cleanup", "directory", "hardlink"])
def test_stage2_receipt_snapshot_boundary_fault_never_mutates_prior(tmp_path, monkeypatch, fault):
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    consult(instance, request("prior"))
    store = instance.receipts
    prior = store.path.read_bytes()
    original_unlink = Path.unlink
    if fault == "directory":
        store.rollback_path.mkdir()
    elif fault == "hardlink":
        os.link(store.path, store.rollback_path)

    def fail(*args, **kwargs):
        raise OSError("client_secret=cleanup-private-canary")

    def faulty_unlink(path, *args, **kwargs):
        if path.suffix == ".tmp":
            fail()
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        if fault == "cleanup":
            patches.setattr(os, "fsync", fail)
            patches.setattr(Path, "unlink", faulty_unlink)
        with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
            consult(instance, request("faulted"))
        if fault != "cleanup":
            with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
                store.recover()
    assert store.path.read_bytes() == prior and instance._active == 0
    assert instance._requests == {"prior"} and len(provider.calls) == 1


def test_stage2_receipt_lock_ownership_stale_file_and_concurrent_replay(tmp_path):
    provider = FakeProvider()
    first = bridge(provider, receipt_directory=tmp_path)
    second = bridge(provider, receipt_directory=tmp_path)
    first.receipts.lock_path.write_bytes(b"stale-owner-marker")
    with first.receipts.locked():
        with pytest.raises(advisor.ToolError, match="ERR_RECEIPT_LOCKED"):
            consult(second, request())
        assert not second._requests and not provider.calls
    assert consult(second, request())["status"] == "advice"
    with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
        consult(first, request())
    assert first.receipts.lock_path.read_bytes() == b"stale-owner-marker"
    assert len(provider.calls) == 1


def test_stage2_distinct_bridge_reservations_preserve_each_owner(tmp_path):
    async def scenario():
        entered, release = anyio.Event(), anyio.Event()
        results = []

        async def provider(payload):
            entered.set()
            await release.wait()
            return advisor.json_bytes(provider_body())

        first = bridge(provider, receipt_directory=tmp_path)
        second = bridge(FakeProvider(), receipt_directory=tmp_path)

        async def invoke():
            results.append(await first.consult(request("first")))

        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(invoke)
                await entered.wait()
                with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
                    await second.consult(request("first"))
                other = await second.consult(request("second"))
                release.set()
        assert first.receipts.read(request("first")) == receipt_metadata(results[0])
        assert second.receipts.read(request("second")) == receipt_metadata(other)
        assert first._active == second._active == 0

    anyio.run(scenario)


@pytest.mark.parametrize("field", ["gate", "session_id", "role_id", "risk", "dispatch_token", "context_sha256", "as_of_time"])
def test_stage2_invalid_request_never_creates_receipts(tmp_path, field):
    prior = set(tmp_path.iterdir())
    value = request()
    value[field] = "spoofed" if field != "role_id" else 17
    provider = FakeProvider()
    instance = bridge(provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError):
        consult(instance, value)
    assert set(tmp_path.iterdir()) == prior
    assert not provider.calls and not instance._requests


def test_stage2_receipt_session_budget_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(advisor, "MAX_CALLS", 2)
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(instance, request("first"))
    consult(instance, request("second"))
    provider = FakeProvider()
    restarted = bridge(provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="ERR_BUDGET_EXCEEDED"):
        consult(restarted, request("third"))
    assert not provider.calls and not restarted._requests


def test_stage2_foreign_authority_cannot_overwrite_session_receipts(tmp_path):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(instance, request())
    prior = instance.receipts.path.read_bytes()
    value = request("next")
    value["gate"] = "FOREIGN_GATE"
    bound = advisor.LaunchAuthority(value["gate"], value["session_id"], 9, "high",
                                    hashlib.sha256(TOKEN.encode()).hexdigest(), NOW)
    provider = FakeProvider()
    foreign = advisor.AdvisorBridge(bound, provider, receipt_directory=tmp_path)
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT_INVALID"):
        consult(foreign, value)
    assert not provider.calls and prior == instance.receipts.path.read_bytes()


@pytest.mark.parametrize("variant", ["symlink", "hardlink", "reparse"])
def test_stage2_receipt_regular_file_checks_reject_links(tmp_path, monkeypatch, variant):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    consult(instance, request())
    info = instance.receipts.path.lstat()

    class UnsafeInfo:
        st_mode = info.st_mode if variant != "symlink" else 0o120777
        st_nlink = 2 if variant == "hardlink" else 1
        st_file_attributes = 0x400 if variant == "reparse" else 0

    original = Path.lstat

    def injected(path, *args, **kwargs):
        return UnsafeInfo() if path == instance.receipts.path else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", injected)
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT"):
        instance.receipts.read(request())


def test_stage2_receipt_crlf_readback_and_immutable_publication(tmp_path):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    result = consult(instance, request())
    ledger = json.loads(instance.receipts.path.read_bytes())
    raw = json.dumps(ledger, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode()
    instance.receipts.path.write_bytes(raw)
    assert instance.receipts.read(request()) == receipt_metadata(result)
    with pytest.raises(advisor.ToolError, match="ERR_RECEIPT_IO"):
        instance.receipts.publish(request(), result)
    assert instance.receipts.path.read_bytes() == raw


def test_stage2_receipt_publication_lock_failure_keeps_pending_replay(tmp_path):
    owner = bridge(FakeProvider(), receipt_directory=tmp_path)
    owner.receipts.reserve(request())
    response = consult(bridge(FakeProvider()), request())
    contender = bridge(FakeProvider(), receipt_directory=tmp_path)
    prior = owner.receipts.path.read_bytes()
    with owner.receipts.locked():
        with pytest.raises(advisor.ToolError, match="ERR_RECEIPT_IO"):
            contender.receipts.publish(request(), response)
    assert prior == owner.receipts.path.read_bytes()
    assert owner.receipts.read(request()) is None


def test_stage2_faulty_backoff_remains_secret_safe_and_accounted():
    async def broken_sleep(_):
        raise RuntimeError("DB_PASSWORD=backoff-private-canary")

    provider = FakeProvider(error=advisor.ProviderFailure("RATE_LIMITED"))
    instance = advisor.AdvisorBridge(authority(), provider, clock=lambda: NOW,
                                     sleep=broken_sleep, jitter=lambda: 1)
    response = consult(instance, request())
    assert response["error"]["code"] == "INTERNAL_ERROR" and response["attempts"] == 1
    assert "backoff-private-canary" not in json.dumps(response)
    assert instance._active == 0


def test_stage2_mutated_provider_failure_cannot_smuggle_retry_metadata():
    error = advisor.ProviderFailure("RATE_LIMITED")
    error.retry_after = "DB_PASSWORD=retry-private-canary"
    response = consult(bridge(FakeProvider(error=error)), request())
    assert response["error"]["code"] == "INTERNAL_ERROR" and response["attempts"] == 1
    assert "retry-private-canary" not in json.dumps(response)


def test_stage2_serialization_flood_is_bounded_before_reservation():
    provider = FakeProvider()
    instance = bridge(provider)
    value = request()
    value["context"]["observations"][0]["data"] = ["x" * 4096] * 1024
    with pytest.raises(advisor.ToolError, match="ERR_INVALID_ARGUMENTS"):
        consult(instance, value)
    assert not provider.calls and not instance._requests


def test_stage2_full_session_receipts_fit_bound_and_enforce_budget(tmp_path):
    instance = bridge(FakeProvider(provider_body(advice="é" * 16000)), receipt_directory=tmp_path)
    for number in range(advisor.MAX_CALLS):
        value = request("request_" + str(number))
        assert consult(instance, value)["status"] == "advice"
    assert instance.receipts.path.stat().st_size < advisor.RECEIPT_LIMIT
    assert instance.receipts.read(value)["request_id"] == value["request_id"]
    with pytest.raises(advisor.ToolError, match="ERR_BUDGET_EXCEEDED"):
        consult(bridge(FakeProvider(), receipt_directory=tmp_path), request("excess"))


@pytest.mark.parametrize("fault", ["success", "oversize", "chunk_type", "partial", "timeout", "cancel"])
def test_stage2_provider_stream_incremental_bound_and_close(fault, monkeypatch):
    async def scenario():
        entered, closed = anyio.Event(), anyio.Event()
        chunks = []
        scopes = []

        async def stream():
            try:
                if fault in ("timeout", "cancel"):
                    entered.set()
                    await anyio.sleep_forever()
                elif fault == "chunk_type":
                    yield "secret=stream-private"
                elif fault == "oversize":
                    for index in range(10):
                        chunks.append(index)
                        yield b"x" * 65536
                else:
                    raw = advisor.json_bytes(provider_body()) if fault == "success" else b'{"model":'
                    yield raw[:5]
                    yield raw[5:]
            finally:
                closed.set()

        async def provider(_):
            return stream()

        instance = bridge(provider)
        if fault == "timeout":
            monkeypatch.setattr(advisor, "DEADLINE_SECONDS", 0.02)
        if fault == "cancel":
            async def invoke():
                with anyio.CancelScope() as scope:
                    scopes.append(scope)
                    await instance.consult(request())
            with anyio.fail_after(5):
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(invoke)
                    await entered.wait()
                    scopes[0].cancel()
        else:
            result = await instance.consult(request())
            assert result["status"] == ("advice" if fault == "success" else "error")
            if fault == "oversize":
                assert result["error"]["code"] == "RESPONSE_TOO_LARGE" and chunks == list(range(5))
            if fault != "timeout":
                assert result["attempts"] == 1
        assert closed.is_set() and instance._active == 0

    anyio.run(scenario)


@pytest.mark.parametrize("fault", ["success", "open", "flush", "close"], ids=str)
def test_stage2_windows_directory_sync_api_and_handle_faults(monkeypatch, fault):
    events = []
    handle = (1 << (advisor.ctypes.sizeof(advisor.ctypes.c_void_p) * 8 - 2)) + 0x7654321

    class FakeFunction:
        def __init__(self, name, callback):
            self.name, self.callback = name, callback
            self.argtypes = self.restype = None

        def __call__(self, *args):
            events.append((self.name, args))
            return self.callback(*args)

    class FakeKernel:
        pass

    kernel = FakeKernel()
    loads = []

    def load_kernel(name, use_last_error):
        loads.append((name, use_last_error))
        return kernel

    kernel.CreateFileW = FakeFunction(
        "open", lambda *args: advisor.wintypes.HANDLE(-1).value if fault == "open" else handle)
    kernel.FlushFileBuffers = FakeFunction("flush", lambda _handle: fault != "flush")
    kernel.CloseHandle = FakeFunction("close", lambda _handle: fault != "close")
    monkeypatch.setattr(advisor.ctypes, "WinDLL", load_kernel, raising=False)
    directory = Path("receipt-store")

    if fault == "success":
        advisor.sync_windows_directory(directory)
    else:
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            advisor.sync_windows_directory(directory)

    assert kernel.CreateFileW.argtypes == [advisor.wintypes.LPCWSTR, advisor.wintypes.DWORD,
                                           advisor.wintypes.DWORD, advisor.wintypes.LPVOID,
                                           advisor.wintypes.DWORD, advisor.wintypes.DWORD,
                                           advisor.wintypes.HANDLE]
    assert kernel.CreateFileW.restype == advisor.wintypes.HANDLE
    assert kernel.FlushFileBuffers.argtypes == [advisor.wintypes.HANDLE]
    assert kernel.FlushFileBuffers.restype == advisor.wintypes.BOOL
    assert kernel.CloseHandle.argtypes == [advisor.wintypes.HANDLE]
    assert kernel.CloseHandle.restype == advisor.wintypes.BOOL
    assert loads == [("kernel32", True)]
    assert events[0] == ("open", (str(directory), 0xC0000000, 7, None, 3, 0x02000000, None))
    assert [name for name, _ in events] == {
        "success": ["open", "flush", "close"], "open": ["open"],
        "flush": ["open", "flush", "close"], "close": ["open", "flush", "close"],
    }[fault]
    if fault != "open":
        assert events[1][1] == events[2][1] == (handle,)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows directory handles")
def test_stage2_windows_receipt_sync_invokes_native_directory_flush(tmp_path, monkeypatch):
    store = bridge(receipt_directory=tmp_path).receipts
    native_sync, calls = advisor.sync_windows_directory, []

    def observed(directory):
        calls.append(directory)
        native_sync(directory)

    monkeypatch.setattr(advisor, "sync_windows_directory", observed)
    store._sync_directory()
    assert calls == [store.directory]


def test_stage2_receipt_commit_barrier_precedes_cleanup_for_reserve_and_publish(tmp_path, monkeypatch):
    events = []

    async def provider(_payload):
        events.append(("provider",))
        return advisor.json_bytes(provider_body())

    instance = bridge(provider, receipt_directory=tmp_path)
    store = instance.receipts
    replace, sync, unlink = store._replace_bytes, store._sync_directory, Path.unlink

    def observed_replace(raw, path=None):
        target = store.path if path is None else path
        events.append(("replace", target, raw))
        return replace(raw, path)

    def observed_sync():
        events.append(("sync",))
        return sync()

    def observed_unlink(path, *args, **kwargs):
        if path == store.rollback_path:
            events.append(("unlink", path))
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(store, "_replace_bytes", observed_replace)
    monkeypatch.setattr(store, "_sync_directory", observed_sync)
    monkeypatch.setattr(Path, "unlink", observed_unlink)
    value = request()
    response = consult(instance, value)

    provider_index = next(index for index, event in enumerate(events) if event[0] == "provider")
    ledger_writes = [(index, json.loads(event[2])) for index, event in enumerate(events)
                     if event[0] == "replace" and event[1] == store.path]
    assert len(ledger_writes) == 2
    assert ledger_writes[0][0] < provider_index < ledger_writes[1][0]
    assert ledger_writes[0][1]["entries"][0]["response"] is None
    assert ledger_writes[1][1]["entries"][0]["response"] == receipt_metadata(response)

    commits = [index for index, event in enumerate(events)
               if event[0] == "replace" and event[1] == store.rollback_path
               and b'"schema_version":"mcp-advisor-commit/v1"' in event[2]]
    assert len(commits) == 2
    assert commits[0] + 3 < provider_index
    assert ledger_writes[1][0] < commits[1]
    for index in commits:
        assert events[index + 1] == ("sync",)
        assert events[index + 2] == ("unlink", store.rollback_path)
        assert events[index + 3] == ("sync",)


@pytest.mark.parametrize("has_prior", [False, True], ids=["new_ledger", "existing_ledger"])
@pytest.mark.parametrize("phase", ["reservation", "publication"])
@pytest.mark.parametrize("fault", ["commit_fsync", "commit_replace", "commit_directory_sync"],
                         ids=["marker_file_fsync", "marker_replace", "commit_barrier"])
def test_stage2_receipt_commit_fault_preserves_prior_or_committed_reservation(
        tmp_path, monkeypatch, has_prior, phase, fault):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    store = instance.receipts
    prior_response = consult(instance, request("prior")) if has_prior else None
    target = request("faulted")
    response = None
    if phase == "publication":
        store.reserve(target)
        response = consult(bridge(FakeProvider()), target)
    prior_raw = store.path.read_bytes() if has_prior else None
    if phase == "publication":
        prior_raw = store.path.read_bytes()
    replace, sync = store._replace_bytes, store._sync_directory
    fail_commit_sync = False
    fail_commit_fsync = False

    def injected_replace(raw, path=None):
        nonlocal fail_commit_sync, fail_commit_fsync
        target = store.path if path is None else path
        try:
            marker_schema = json.loads(raw).get("schema_version")
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
            marker_schema = None
        is_commit = target == store.rollback_path and marker_schema == "mcp-advisor-commit/v1"
        if is_commit and fault == "commit_replace":
            raise OSError("commit marker replace fault")
        if is_commit and fault == "commit_fsync":
            fail_commit_fsync = True
        if is_commit and fault == "commit_directory_sync":
            fail_commit_sync = True
        return replace(raw, path)

    fsync = os.fsync

    def injected_fsync(fd):
        nonlocal fail_commit_fsync
        if fail_commit_fsync:
            fail_commit_fsync = False
            raise OSError("commit marker file fsync fault")
        return fsync(fd)

    def injected_sync():
        nonlocal fail_commit_sync
        if fail_commit_sync:
            fail_commit_sync = False
            raise OSError("commit marker directory barrier fault")
        return sync()

    monkeypatch.setattr(store, "_replace_bytes", injected_replace)
    monkeypatch.setattr(store, "_sync_directory", injected_sync)
    monkeypatch.setattr(os, "fsync", injected_fsync)
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        store.reserve(target) if phase == "reservation" else store.publish(target, response)

    if fault in ("commit_fsync", "commit_replace"):
        assert (store.path.read_bytes() if store.path.exists() else None) == prior_raw
        assert not store.rollback_path.exists()
        if has_prior:
            assert store.read(request("prior")) == receipt_metadata(prior_response)
        assert store.read(target) is None
        if phase == "publication":
            with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
                store.reserve(target)
    else:
        ledger = json.loads(store.path.read_bytes())
        ids = [entry["request"]["request_id"] for entry in ledger["entries"]]
        assert ids == (["prior", "faulted"] if has_prior else ["faulted"])
        assert not store.rollback_path.exists()
        if has_prior:
            assert store.read(request("prior")) == receipt_metadata(prior_response)
        if phase == "publication":
            assert store.read(target) == receipt_metadata(response)
        with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
            store.reserve(target)


@pytest.mark.parametrize("has_prior", [False, True], ids=["new_ledger", "existing_ledger"])
def test_stage2_retained_commit_marker_recovers_forward_and_denies_replay(tmp_path, monkeypatch, has_prior):
    instance = bridge(FakeProvider(), receipt_directory=tmp_path)
    store = instance.receipts
    prior_response = consult(instance, request("prior")) if has_prior else None
    target = request("acknowledged")
    unlink = Path.unlink

    def retain_marker(path, *args, **kwargs):
        if path == store.rollback_path:
            raise OSError("cleanup unlink fault")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        patches.setattr(Path, "unlink", retain_marker)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            store.reserve(target)

    assert json.loads(store.rollback_path.read_bytes())["schema_version"] == "mcp-advisor-commit/v1"
    restarted = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    restarted.recover()
    ledger = json.loads(restarted.path.read_bytes())
    ids = [entry["request"]["request_id"] for entry in ledger["entries"]]
    assert ids == (["prior", "acknowledged"] if has_prior else ["acknowledged"])
    if has_prior:
        assert restarted.read(request("prior")) == receipt_metadata(prior_response)
    assert not restarted.rollback_path.exists() and restarted.read(target) is None
    with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
        restarted.reserve(target)


def test_stage2_retained_publication_commit_recovers_metadata_and_denies_replay(tmp_path, monkeypatch):
    store = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    target = request()
    store.reserve(target)
    response = consult(bridge(FakeProvider()), target)
    unlink = Path.unlink

    def retain_marker(path, *args, **kwargs):
        if path == store.rollback_path:
            raise OSError("publication cleanup unlink fault")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        patches.setattr(Path, "unlink", retain_marker)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            store.publish(target, response)

    restarted = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    restarted.recover()
    assert restarted.read(target) == receipt_metadata(response)
    with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
        restarted.reserve(target)


@pytest.mark.parametrize("corruption", ["schema", "authority", "hash", "missing_ledger"], ids=str)
def test_stage2_corrupt_commit_marker_retains_state_and_blocks_mutation(tmp_path, corruption):
    store = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    consult(bridge(FakeProvider(), receipt_directory=tmp_path), request("prior"))
    raw = store.path.read_bytes()
    marker = {"schema_version": "mcp-advisor-commit/v1", "authority_sha256": store.binding,
              "receipt_sha256": hashlib.sha256(raw).hexdigest()}
    if corruption == "schema":
        marker["receipt_sha256"] = "invalid"
    elif corruption == "authority":
        marker["authority_sha256"] = "0" * 64
    elif corruption == "hash":
        marker["receipt_sha256"] = "0" * 64
    store.rollback_path.write_bytes(advisor.json_bytes(marker))
    if corruption == "missing_ledger":
        store.path.unlink()
    marker_raw = store.rollback_path.read_bytes()
    ledger_raw = store.path.read_bytes() if store.path.exists() else None

    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        store.recover()
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        store.reserve(request("next"))
    assert store.rollback_path.read_bytes() == marker_raw
    assert (store.path.read_bytes() if store.path.exists() else None) == ledger_raw


def test_stage2_commit_recovery_lock_contention_retains_marker(tmp_path):
    store = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    store.reserve(request())
    contender = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    raw = store.path.read_bytes()
    store.rollback_path.write_bytes(advisor.json_bytes({
        "schema_version": "mcp-advisor-commit/v1", "authority_sha256": store.binding,
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }))
    marker_raw = store.rollback_path.read_bytes()
    with store.locked():
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            contender.recover()
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
        contender.reserve(request("next"))
    assert store.rollback_path.read_bytes() == marker_raw and store.path.read_bytes() == raw


@pytest.mark.parametrize("phase", ["write_cleanup", "recovery_cleanup"], ids=["cleanup", "recovery"])
def test_stage2_cleanup_directory_sync_fault_never_erases_committed_reservation(
        tmp_path, monkeypatch, phase):
    store = bridge(FakeProvider(), receipt_directory=tmp_path).receipts
    target = request("durable")
    unlink, sync = Path.unlink, store._sync_directory
    deleted_commit_marker = False

    def note_marker_unlink(path, *args, **kwargs):
        nonlocal deleted_commit_marker
        if path == store.rollback_path and path.exists():
            try:
                deleted_commit_marker = json.loads(path.read_bytes()).get("schema_version") == "mcp-advisor-commit/v1"
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        return unlink(path, *args, **kwargs)

    def fail_after_marker_delete():
        nonlocal deleted_commit_marker
        if deleted_commit_marker:
            deleted_commit_marker = False
            raise OSError("marker deletion barrier fault")
        return sync()

    if phase == "write_cleanup":
        monkeypatch.setattr(Path, "unlink", note_marker_unlink)
        monkeypatch.setattr(store, "_sync_directory", fail_after_marker_delete)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            store.reserve(target)
    else:
        def retain_marker(path, *args, **kwargs):
            if path == store.rollback_path:
                raise OSError("retained commit marker")
            return unlink(path, *args, **kwargs)

        with monkeypatch.context() as patches:
            patches.setattr(Path, "unlink", retain_marker)
            with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
                store.reserve(target)
        monkeypatch.setattr(Path, "unlink", note_marker_unlink)
        monkeypatch.setattr(store, "_sync_directory", fail_after_marker_delete)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            store.recover()

    assert not store.rollback_path.exists()
    assert [entry["request"]["request_id"] for entry in json.loads(store.path.read_bytes())["entries"]] == ["durable"]
    with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
        store.reserve(target)


@pytest.mark.parametrize("has_prior", [False, True], ids=["new_ledger", "existing_ledger"])
@pytest.mark.parametrize("phase", ["reservation", "publication"])
def test_stage2_acknowledged_commit_survives_lost_marker_deletion(tmp_path, monkeypatch, has_prior, phase):
    store = bridge(receipt_directory=tmp_path).receipts
    if has_prior:
        store.reserve(request("prior"))
    target = request("acknowledged")
    committed_markers = []
    replace = store._replace_bytes

    def capture_marker(raw, path=None):
        replace(raw, path)
        if path == store.rollback_path and b'"schema_version":"mcp-advisor-commit/v1"' in raw:
            committed_markers.append(raw)

    monkeypatch.setattr(store, "_replace_bytes", capture_marker)
    store.reserve(target)
    response = None
    if phase == "publication":
        response = consult(bridge(FakeProvider()), target)
        store.publish(target, response)
    acknowledged_raw = store.path.read_bytes()
    # Model only a lost cleanup deletion: the durable commit replaced the pending snapshot.
    store.rollback_path.write_bytes(committed_markers[-1])
    restarted = bridge(receipt_directory=tmp_path).receipts
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        restarted.read(target)
    restarted.recover()
    assert restarted.path.read_bytes() == acknowledged_raw
    assert restarted.read(target) == (receipt_metadata(response) if response else None)
    with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
        restarted.reserve(target)


@pytest.mark.parametrize("fault", ["success", "open", "fsync", "close"])
def test_stage2_posix_directory_barrier_faults_close_owned_descriptor(tmp_path, monkeypatch, fault):
    from types import SimpleNamespace

    store = bridge(receipt_directory=tmp_path).receipts
    events = []

    def operation(name, result=None):
        def call(*args):
            events.append((name, args))
            if name == fault:
                raise OSError("directory barrier fault")
            return result
        return call

    monkeypatch.setattr(advisor, "os", SimpleNamespace(
        name="posix", O_RDONLY=0, O_DIRECTORY=65536, open=operation("open", 123),
        fsync=operation("fsync"), close=operation("close")))
    if fault == "success":
        store._sync_directory()
    else:
        with pytest.raises(OSError, match="directory barrier fault"):
            store._sync_directory()
    assert events == ([("open", (store.directory, 65536))] if fault == "open" else [
        ("open", (store.directory, 65536)), ("fsync", (123,)), ("close", (123,))])


@pytest.mark.parametrize("fault", ["readback", "directory_sync", "marker_delete"])
def test_stage2_committed_recovery_fault_blocks_access_without_rollback(tmp_path, monkeypatch, fault):
    store = bridge(receipt_directory=tmp_path).receipts
    target = request()
    store.reserve(target)
    raw = store.path.read_bytes()
    marker = advisor.json_bytes({"schema_version": "mcp-advisor-commit/v1",
                                 "authority_sha256": store.binding,
                                 "receipt_sha256": hashlib.sha256(raw).hexdigest()})
    store.rollback_path.write_bytes(marker)
    read, sync, unlink = store._read, store._sync_directory, Path.unlink

    def fail(*args, **kwargs):
        raise OSError("https://user:recovery-canary@example.com/?token=recovery-canary")

    def fail_unlink(path, *args, **kwargs):
        if path == store.rollback_path:
            fail()
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patches:
        if fault == "readback":
            patches.setattr(store, "_read", fail)
        elif fault == "directory_sync":
            patches.setattr(store, "_sync_directory", fail)
        else:
            patches.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_IO$"):
            store.recover()
    assert store.path.read_bytes() == raw and store.rollback_path.read_bytes() == marker
    with pytest.raises(advisor.ToolError, match="^ERR_RECEIPT_INVALID$"):
        store.read(target)
    assert store._read == read and store._sync_directory == sync
    store.recover()
    assert store.path.read_bytes() == raw
    with pytest.raises(advisor.ToolError, match="^ERR_REPLAYED_REQUEST$"):
        store.reserve(target)


@pytest.mark.parametrize("model", advisor.MODELS)
def test_valid_different_allowlisted_model_response_rejected(model):
    """F-005: provider answering with another valid allowlisted model is a mismatch (no implicit downgrade)."""
    other = next(m for m in advisor.MODELS if m != model)
    value = request(model=model)
    provider = FakeProvider(body=provider_body(other))
    result = consult(bridge(provider), value)
    assert result["status"] == "error" or result["model"] == model
    advisor.validate_response(result, value)
    assert result["model"] == model and result["advice"] is None


def test_replayed_request_id_rejected_without_second_provider_call():
    """F-005: identical request_id replay is denied before reaching the provider."""
    value = request("replay_dispatch")
    provider = FakeProvider()
    instance = bridge(provider)
    first = consult(instance, value)
    assert first["status"] == "advice"
    with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
        consult(instance, value)
    assert len(provider.calls) == 1


def test_provider_timeout_returns_bounded_timeout_error_and_frees_capacity(monkeypatch):
    """F-005: hung provider -> TIMEOUT error response, no advice, capacity released, request id burned."""
    monkeypatch.setattr(advisor, "DEADLINE_SECONDS", 0.01)

    async def hang(_payload):
        await anyio.sleep_forever()

    value = request("timeout_dispatch")
    instance = bridge(hang)
    result = consult(instance, value)
    advisor.validate_response(result, value)
    assert result["status"] == "error" and result["error"]["code"] == "TIMEOUT" and result["advice"] is None
    assert instance._active == 0
    with pytest.raises(advisor.ToolError, match="ERR_REPLAYED_REQUEST"):
        consult(instance, value)
