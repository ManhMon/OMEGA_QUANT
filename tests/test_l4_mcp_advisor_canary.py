"""Hermetic process canaries; one credential-gated, bounded 9router smoke call."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from mcp import types
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import l4_mcp_advisor as advisor  # noqa: E402

GATE = "GATE_L4_MCP_ADVISOR_STAGE4_20261004"
SESSION = "l2_role9_l4_mcp_advisor_stage4_20261005"
TOKEN = "canary-dispatch-00000000000000000000000000"
SECRET = "canary-private-credential-value"
URL_SECRET = f"https://user:{SECRET}@example.com/?token={SECRET}"
PROVIDER_TOKENS = ("ghp_" + "A" * 36, "github_pat_" + "A" * 82, "AIza" + "A" * 35,
                   "xoxb-123456789012-123456789012-" + "A" * 24, "gsk_" + "A" * 52, "hf_" + "A" * 34)
CUTOFF = "2026-09-02T08:30:00Z"  # 15:30 ICT, Vietnam National Day closure.
PROCESS_SECONDS = 30
LIVE_SECONDS = 45
COMMAND = [sys.executable, "-c", (
    "import runpy; runpy.run_path('tests/test_l4_mcp_advisor_canary.py', run_name='__main__')"
)]


def bind(value):
    text = advisor.context_text(value["context"], TOKEN)
    value["context_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return value


def request(request_id="canary_1", model=advisor.MODELS[0]):
    return bind({
        "schema_version": "mcp-advisor-request/v1", "gate": GATE,
        "session_id": SESSION, "request_id": request_id, "role_id": 9,
        "risk": "high", "purpose": "correctness", "model": model,
        "dispatch_token": TOKEN, "context_sha256": "0" * 64, "as_of_time": CUTOFF,
        "context": {
            "instructions": "Reply briefly using only supplied evidence.\r\nCheck consistency.",
            "observations": [{"source_id": "canary_fixture", "available_at": CUTOFF,
                              "data": {"price": 25000, "unit": "VND_FULL", "denominator": 0,
                                       "session": "closed", "date": "2026-09-02",
                                       "universe": ["VCB", "DELISTED"], "status": "frozen",
                                        "api_key": SECRET, "note": TOKEN + " " + URL_SECRET,
                                        "snippets": list(PROVIDER_TOKENS)}}],
        },
    })


def launch_env(mode="mock", directory=None):
    # No ambient credentials, PYTHONPATH, proxy configuration or dispatch authority.
    env = {key: os.environ[key] for key in (
        "SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR", "LANG",
    ) if key in os.environ}
    env.update({
        "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "CANARY_MODE": mode,
        "OMEGA_DISPATCH_GATE": GATE, "OMEGA_DISPATCH_SESSION_ID": SESSION,
        "OMEGA_DISPATCH_ROLE_ID": "9", "OMEGA_DISPATCH_RISK": "high",
        "OMEGA_DISPATCH_TOKEN_SHA256": hashlib.sha256(TOKEN.encode()).hexdigest(),
    })
    if directory is not None:
        env["CANARY_RECEIPTS"] = str(directory)
    return env


def assert_secret_safe(raw, api_key=None):
    text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
    if any(secret in text for secret in (TOKEN, SECRET, URL_SECRET, *PROVIDER_TOKENS, api_key) if secret):
        pytest.fail("ERR_CANARY_SECRET_LEAK", pytrace=False)


def _child_main():
    """Test-only injection; actual advisor main, authority, framing and server run."""
    original = advisor.run_stdio
    mode = os.environ.get("CANARY_MODE")
    calls = 0

    async def mock_provider(payload):
        nonlocal calls
        calls += 1
        text = payload["messages"][1]["content"]
        if any(secret in text for secret in (TOKEN, SECRET, URL_SECRET, *PROVIDER_TOKENS)):
            raise RuntimeError("ERR_CANARY_OUTBOUND_SECRET")
        if mode == "exception":
            raise RuntimeError(URL_SECRET)
        if mode == "timeout":
            await asyncio.sleep(10)
        if mode == "oversize":
            return b"x" * (advisor.MAX_RESPONSE_BYTES + 1)
        body = {"model": payload["model"], "id": "canary-provider-1", "choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps({
                "calls": calls, "context": json.loads(text),
                "dispatch_digest": os.environ["OMEGA_DISPATCH_TOKEN_SHA256"],
                "dirty": "api_key=" + SECRET + " " + TOKEN + " " + URL_SECRET,
            }, ensure_ascii=False)},
        }]}
        if mode == "model_mismatch":
            body["model"] = "unlisted-model"
        elif mode == "schema":
            body["choices"][0]["message"]["role"] = "tool"
        return advisor.json_bytes(body)

    async def run(bound):
        if mode != "live":
            def deny_network(*args, **kwargs):
                raise RuntimeError("ERR_CANARY_NETWORK_FORBIDDEN")
            socket.getaddrinfo = socket.create_connection = deny_network
            socket.socket.connect = socket.socket.connect_ex = deny_network
        else:
            advisor.DEADLINE_SECONDS = LIVE_SECONDS
            advisor.MAX_ATTEMPTS = 1
        if mode == "timeout":
            advisor.DEADLINE_SECONDS = 0.1
        directory = os.environ.get("CANARY_RECEIPTS")
        return await original(bound, None if mode == "live" else mock_provider,
                              receipt_directory=Path(directory) if directory else None)

    advisor.run_stdio = run
    raise SystemExit(advisor.main())


@asynccontextmanager
async def process_client(env, *, api_key=None, timeout=PROCESS_SECONDS):
    process = await asyncio.create_subprocess_exec(
        *COMMAND, cwd=ROOT, env=env, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=advisor.MAX_RESPONSE_BYTES + 1,
    )
    transcript = []
    completed = {}
    sequence = 0

    async def exchange(method, params=None, notification=False):
        nonlocal sequence
        sequence += 1
        frame = {"jsonrpc": "2.0", "method": method}
        if not notification:
            frame["id"] = sequence
        if params is not None:
            frame["params"] = params
        process.stdin.write(json.dumps(frame, ensure_ascii=False, allow_nan=False).encode() + b"\r\n")
        await asyncio.wait_for(process.stdin.drain(), timeout)
        if notification:
            return None
        raw = await asyncio.wait_for(process.stdout.readline(), timeout)
        assert_secret_safe(raw, api_key)
        transcript.append(raw)
        response = advisor.strict_json(raw, advisor.MAX_RESPONSE_BYTES)
        types.JSONRPCMessage.model_validate(response)
        assert response["id"] == sequence and "result" in response
        return response["result"]

    try:
        initialized = await exchange("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "stage4-canary", "version": "1"},
        })
        assert initialized["serverInfo"]["name"] == "omega-l4-advisor"
        await exchange("notifications/initialized", notification=True)
        tools = types.ListToolsResult.model_validate(await exchange("tools/list", {}))
        assert [tool.name for tool in tools.tools] == ["consult_advisor"]
        assert tools.tools[0].inputSchema == advisor.REQUEST_SCHEMA
        assert tools.tools[0].outputSchema == advisor.RESPONSE_SCHEMA
        yield exchange, completed
        process.stdin.close()
        await asyncio.wait_for(process.wait(), timeout)
        extra, errors = await asyncio.wait_for(process.communicate(), timeout)
        assert_secret_safe(extra + errors + b"".join(transcript), api_key)
        assert extra == errors == b""
        completed.update(returncode=process.returncode, transcript=b"".join(transcript))
    finally:
        if process.returncode is None:
            process.kill()
            await asyncio.wait_for(process.wait(), 5)


async def call(exchange, value):
    raw = await exchange("tools/call", {"name": "consult_advisor", "arguments": value})
    result = types.CallToolResult.model_validate(raw)
    if result.structuredContent is not None:
        advisor.validate_response(result.structuredContent, value)
        assert json.loads(result.content[0].text) == result.structuredContent
    return result


@pytest.mark.parametrize("model", advisor.MODELS, ids=["sol", "astra"])
def test_mock_stdio_lifecycle_launch_tokens_pit_schema_and_receipts(tmp_path, model):
    value = request(model=model)
    before = deepcopy(value)

    async def scenario():
        async with process_client(launch_env(directory=tmp_path)) as (exchange, completed):
            result = await call(exchange, value)
            assert not result.isError
            response = result.structuredContent
            assert response["status"] == "advice" and response["model"] == model
            assert response["attempts"] == 1 and response["retries"] == 0
            evidence = json.loads(response["advice"])
            assert evidence["calls"] == 1
            assert evidence["dispatch_digest"] == hashlib.sha256(TOKEN.encode()).hexdigest()
            clean = deepcopy(value["context"])
            clean["observations"][0]["data"].update(api_key="[REDACTED]", note="[REDACTED] [REDACTED]")
            clean["observations"][0]["data"]["snippets"] = ["[REDACTED]"] * len(PROVIDER_TOKENS)
            assert evidence["context"] == clean
            canonical = json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            assert response["context_sha256"] == hashlib.sha256(canonical).hexdigest()
            assert response["as_of_time"] == CUTOFF
            assert "not approval" in response["limitations"][0]
            ledger_raw = (tmp_path / (SESSION + ".json")).read_bytes()
            assert_secret_safe(ledger_raw)
            ledger = advisor.strict_json(ledger_raw, advisor.RECEIPT_LIMIT)
            advisor.validate_schema(ledger, advisor.RECEIPT_SCHEMA)
            assert ledger["entries"][0]["response"]["response_sha256"] == response["response_sha256"]
            preimage = {key: val for key, val in ledger.items() if key != "receipt_sha256"}
            assert ledger["receipt_sha256"] == hashlib.sha256(advisor.json_bytes(preimage)).hexdigest()
            assert not any(key in ledger_raw for key in (b'"advice":', b'"context":', b'"dispatch_token":'))
        assert completed["returncode"] == 0

    asyncio.run(scenario())
    assert value == before
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob("*.rollback"))


def test_mock_stdio_rejections_precede_provider_and_durable_mutation(tmp_path):
    prior_files = set(tmp_path.iterdir())
    faults = []
    for field, bad, code in (
        ("role_id", 17, "ERR_UNAUTHORIZED_IDENTITY"),
        ("risk", "low", "ERR_UNAUTHORIZED_IDENTITY"),
        ("gate", "FOREIGN", "ERR_UNAUTHORIZED_IDENTITY"),
        ("session_id", "FOREIGN", "ERR_UNAUTHORIZED_IDENTITY"),
        ("dispatch_token", "x" * 40, "ERR_UNAUTHORIZED_IDENTITY"),
        ("purpose", [], "ERR_INVALID_ARGUMENTS"),
        ("model", "9router/cx/gpt-6-luna", "ERR_INVALID_ARGUMENTS"),
        ("request_id", "--flag; echo injected", "ERR_INVALID_ARGUMENTS"),
        ("as_of_time", "2026-09-02T15:30:00+07:00", "ERR_INVALID_ARGUMENTS"),
        ("context_sha256", "0" * 64, "ERR_CONTEXT_MISMATCH"),
    ):
        bad_request = request("invalid_" + str(len(faults)))
        bad_request[field] = bad
        faults.append((bad_request, code))
    for variant in ("future", "nested", "schema", "oversize", "cycle", "model_focus"):
        bad_request = request("invalid_" + variant)
        observation = bad_request["context"]["observations"][0]
        code = "ERR_INVALID_ARGUMENTS"
        if variant in ("future", "nested"):
            future = "2026-09-02T08:30:01Z"
            if variant == "future":
                observation["available_at"] = future
            else:
                observation["data"] = {"source_id": "revision", "available_at": future}
            code = "ERR_LOOKAHEAD_DETECTED"
        elif variant == "schema":
            observation["unexpected"] = True
        elif variant == "oversize":
            observation["data"] = "é" * 25000
            code = "ERR_CONTEXT_TOO_LARGE"
        else:
            bad_request[variant] = []
        bind(bad_request)
        faults.append((bad_request, code))

    async def scenario():
        async with process_client(launch_env(directory=tmp_path)) as (exchange, completed):
            for value, code in faults:
                result = await call(exchange, value)
                assert result.isError and result.structuredContent is None
                assert result.content[0].text == code
                assert set(tmp_path.iterdir()) == prior_files
            valid = request()
            result = await call(exchange, valid)
            assert json.loads(result.structuredContent["advice"])["calls"] == 1
            prior = (tmp_path / (SESSION + ".json")).read_bytes()
            replay = await call(exchange, valid)
            assert replay.isError and replay.content[0].text == "ERR_REPLAYED_REQUEST"
            assert (tmp_path / (SESSION + ".json")).read_bytes() == prior
        assert completed["returncode"] == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["directory_receipt", "directory_lock", "corrupt", "pending_rollback"])
def test_mock_stdio_receipt_faults_preserve_prior_before_provider(tmp_path, fault):
    path = tmp_path / (SESSION + (".lock" if fault == "directory_lock" else ".json"))
    if fault.startswith("directory"):
        path.mkdir()
    elif fault == "corrupt":
        path.write_bytes(b'{"entries":[],"entries":[]}')
    else:
        path = tmp_path / (SESSION + ".rollback")
        path.write_bytes(b'{"partial":')
    prior = path.read_bytes() if path.is_file() else None

    async def scenario():
        async with process_client(launch_env(directory=tmp_path)) as (exchange, completed):
            result = await call(exchange, request())
            assert result.isError and result.structuredContent is None
            assert result.content[0].text.startswith("ERR_RECEIPT_")
            assert (path.read_bytes() if path.is_file() else None) == prior
            assert not list(tmp_path.glob("*.tmp"))
        assert completed["returncode"] == 1
    asyncio.run(scenario())


def test_mock_stdio_concurrent_processes_isolate_authority_and_replay():
    async def worker(index):
        value = request()
        value["session_id"] += "_" + str(index)
        env = launch_env()
        env["OMEGA_DISPATCH_SESSION_ID"] = value["session_id"]
        async with process_client(env) as (exchange, completed):
            result = await call(exchange, value)
            assert not result.isError and result.structuredContent["session_id"] == value["session_id"]
            assert json.loads(result.structuredContent["advice"])["calls"] == 1
            foreign = deepcopy(value)
            foreign["session_id"] = SESSION
            rejected = await call(exchange, foreign)
            assert rejected.content[0].text == "ERR_UNAUTHORIZED_IDENTITY"
            replay = await call(exchange, value)
            assert replay.content[0].text == "ERR_REPLAYED_REQUEST"
        assert completed["returncode"] == 1

    async def scenario():
        await asyncio.gather(worker(1), worker(2))
    asyncio.run(scenario())


@pytest.mark.parametrize("returned_model", ["cx/gpt-6.1-sol", "gpt-6.1-sol", "gpt-6-astra", "unknown"],
                         ids=["router_id", "upstream_id", "other_model", "unlisted"])
@pytest.mark.parametrize("encoding", ["plain", "escaped", "serialized"])
def test_live_adapter_identity_alias_is_exact_and_key_redacted(returned_model, encoding):
    advice = "Advice " + SECRET
    if encoding == "serialized":
        advice = json.dumps({"public": advice})
    body = {"model": returned_model, "id": "provider-1", "choices": [{
        "finish_reason": "stop", "message": {"role": "assistant", "content": advice},
    }]}
    raw = advisor.json_bytes(body)
    if encoding == "escaped":
        raw = raw.replace(SECRET.encode(), b"\\u0063" + SECRET[1:].encode())
    raw = advisor.router_response(raw, advisor.MODELS[0], SECRET)
    assert_secret_safe(raw)
    if returned_model in ("cx/gpt-6.1-sol", "gpt-6.1-sol"):
        advice, _ = advisor.provider_advice(raw, advisor.MODELS[0], TOKEN)
        assert SECRET not in advice
        assert (json.loads(advice) if encoding == "serialized" else advice) == (
            {"public": "Advice [REDACTED]"} if encoding == "serialized" else "Advice [REDACTED]"
        )
    else:
        with pytest.raises(advisor.ProviderFailure, match="^MODEL_UNAVAILABLE$"):
            advisor.provider_advice(raw, advisor.MODELS[0], TOKEN)


@pytest.mark.parametrize("mode,code", [
    ("exception", "INTERNAL_ERROR"), ("schema", "PROVIDER_SCHEMA_INVALID"),
    ("model_mismatch", "MODEL_UNAVAILABLE"), ("oversize", "RESPONSE_TOO_LARGE"),
    ("timeout", "TIMEOUT"),
])
def test_mock_stdio_provider_faults_fail_closed_secret_safe(mode, code):
    async def scenario():
        async with process_client(launch_env(mode)) as (exchange, completed):
            value = request()
            result = await call(exchange, value)
            assert result.isError
            response = result.structuredContent
            assert response["advice"] is None and response["provider_request_id"] is None
            assert response["error"]["code"] == code and not response["error"]["retryable"]
            assert 1 <= response["attempts"] <= advisor.MAX_ATTEMPTS
        assert completed["returncode"] == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("missing", ["OMEGA_DISPATCH_GATE", "OMEGA_DISPATCH_SESSION_ID",
                                     "OMEGA_DISPATCH_ROLE_ID", "OMEGA_DISPATCH_RISK",
                                     "OMEGA_DISPATCH_TOKEN_SHA256"])
def test_canary_launch_requires_every_authority_env_field(missing):
    env = launch_env()
    del env[missing]
    result = subprocess.run(COMMAND, cwd=ROOT, env=env, input=b"", capture_output=True,
                            timeout=PROCESS_SECONDS)
    assert_secret_safe(result.stdout + result.stderr)
    assert result.returncode == 1 and result.stdout == b""
    assert result.stderr.strip() == b"ERR_ADVISOR_STARTUP_OR_TRANSPORT"


@pytest.mark.parametrize("raw", [
    b"\xff\n", b"\xef\xbb\xbf{}\n", b'{"id":1,"id":2}\n',
    b'{"value":NaN}\n', b'{"value":Infinity}\n', b'{"value":1e999}\n',
    b'{"value":18014398509481984}\n',
    b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
    b'{"partial":\n', b"x" * (advisor.MAX_REQUEST_BYTES + 1) + b"\n",
], ids=["utf8", "bom", "duplicate", "nan", "inf", "overflow", "integer_bound", "missing_newline", "partial", "bound"])
def test_canary_corrupted_stdio_frames_never_continue(raw):
    result = subprocess.run(COMMAND, cwd=ROOT, env=launch_env(), input=raw,
                            capture_output=True, timeout=PROCESS_SECONDS)
    assert_secret_safe(result.stdout + result.stderr)
    assert result.returncode == 1 and result.stdout == b""
    assert result.stderr.strip() == b"ERR_ADVISOR_STARTUP_OR_TRANSPORT"


def router_key():
    for name in ("NINE_ROUTER_API_KEY", "9ROUTER_API_KEY", "ROUTER_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    # Generic LLM credentials qualify only when bound to the existing local router.
    if os.environ.get("OMEGA_LLM_BASE_URL", "").rstrip("/") in (
        "http://127.0.0.1:20128/v1", "http://localhost:20128/v1",
    ):
        return os.environ.get("OMEGA_LLM_API_KEY")
    return None


def test_live_9router_sol_stdio_smoke_identity_latency_and_redaction(record_property):
    key = router_key()
    if not key:
        pytest.skip("9router API key unavailable")
    env = launch_env("live")
    env["NINE_ROUTER_API_KEY"] = key
    started = time.monotonic()

    async def scenario():
        async with process_client(env, api_key=key, timeout=LIVE_SECONDS + 10) as (exchange, completed):
            result = await call(exchange, request("live_smoke"))
            response = result.structuredContent
            if result.isError or response is None:
                code = response["error"]["code"] if response else "MCP_TOOL_ERROR"
                pytest.fail("Live 9router canary failed: " + code, pytrace=False)
            assert response["model"] == "cx/gpt-6.1-sol"
            assert response["attempts"] == 1 and response["retries"] == 0
            assert response["status"] == "advice" and response["advice"].strip()
            assert_secret_safe(result.model_dump_json(), key)
        assert completed["returncode"] == 0

    asyncio.run(scenario())
    elapsed = time.monotonic() - started
    assert 0 < elapsed <= LIVE_SECONDS + 10
    record_property("model", "cx/gpt-6.1-sol")
    record_property("latency_seconds", round(elapsed, 3))


if __name__ == "__main__":
    _child_main()
