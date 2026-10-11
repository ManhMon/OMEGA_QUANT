"""Launch-bound L3 critique; never an approval or gate writer."""
from __future__ import annotations

from contextvars import ContextVar
from copy import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import logging
import os
from pathlib import Path
import re
import secrets
import sys

# ponytail: isolate transport policy globals; parameterize the shared transport if another tier needs it.
_spec = importlib.util.spec_from_file_location(
    "_omega_l3_critic_transport", Path(__file__).with_name("l4_mcp_advisor.py"))
transport = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = transport
_spec.loader.exec_module(transport)
transport.ROLE_SCHEMA.update(minimum=17, maximum=30)
transport.PURPOSE_SCHEMA["enum"] = ["adversarial_critique"]
MODELS = transport.MODELS
PURPOSES = ("adversarial_critique",)
ToolError = transport.ToolError
ProviderFailure = transport.ProviderFailure
REQUEST_SCHEMA = transport.object_schema({
    key: value for key, value in transport.REQUEST_SCHEMA["properties"].items()
    if key != "dispatch_token"
})
RESPONSE_SCHEMA = transport.RESPONSE_SCHEMA


class LaunchAuthority(transport.LaunchAuthority):
    def __post_init__(self):
        if type(self.role_id) is not int or not 17 <= self.role_id <= 30:
            raise ToolError("ERR_INVALID_LAUNCH_AUTHORITY")
        # Validate all common fields without changing the L4 role boundary.
        transport.LaunchAuthority(self.gate, self.session_id, 9, self.risk,
                                  self.token_sha256, self.current_session_started_at)

    @classmethod
    def from_environment(cls, environment=None):
        env = dict(os.environ if environment is None else environment)
        role = env.get("OMEGA_DISPATCH_ROLE_ID")
        if type(role) is not str or re.fullmatch(r"(?:1[7-9]|2[0-9]|30)", role) is None:
            raise ToolError("ERR_INVALID_LAUNCH_AUTHORITY")
        return cls(env.get("OMEGA_DISPATCH_GATE"), env.get("OMEGA_DISPATCH_SESSION_ID"),
                   int(role), env.get("OMEGA_DISPATCH_RISK"),
                   env.get("OMEGA_DISPATCH_TOKEN_SHA256"), transport.utc_now())


_consultation_cutoff = ContextVar("l3_consultation_cutoff", default=None)
_launch_accepted_context = transport.accepted_context


def trusted_cutoff(clock=transport.utc_now):
    cutoff = clock()
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ToolError("ERR_INVALID_ARGUMENTS")
    return min(cutoff.astimezone(timezone.utc), transport.utc_now().astimezone(timezone.utc))


def accepted_context(request, authority):
    if "OMEGA_ADVISOR_SKIP_PIT" in os.environ:
        raise ToolError("ERR_INVALID_LAUNCH_AUTHORITY")
    cutoff = _consultation_cutoff.get()
    if cutoff is None:
        cutoff = trusted_cutoff()
    # Only the validation view changes; launch identity and receipt binding stay immutable.
    return _launch_accepted_context(request, replace(authority, current_session_started_at=cutoff))


class ReceiptStore(transport.ReceiptStore):
    def _read(self, token="\x00", *, path=None):
        now = trusted_cutoff()
        view = copy(self)
        view.authority = replace(self.authority, current_session_started_at=now)
        ledger = super(ReceiptStore, view)._read(token, path=path)
        for entry in ledger["entries"]:
            cutoff = transport.parse_utc(entry["consultation_cutoff"], True)
            if not transport.parse_utc(entry["request"]["as_of_time"]) <= cutoff <= now:
                raise ToolError("ERR_RECEIPT_INVALID")
        return ledger

    def _write(self, ledger):
        for entry in ledger["entries"]:
            if "consultation_cutoff" not in entry:
                cutoff = _consultation_cutoff.get()
                if cutoff is None or entry["response"] is not None:
                    raise ToolError("ERR_RECEIPT_INVALID")
                entry["consultation_cutoff"] = transport.timestamp(cutoff)
        super()._write(ledger)


# This transport module is private to L3; L4 retains its startup-bound policy.
transport.accepted_context = accepted_context
transport.ReceiptStore = ReceiptStore
_entry_schema = transport.RECEIPT_SCHEMA["properties"]["entries"]["items"]
_entry_schema["properties"]["consultation_cutoff"] = transport.TIME_SCHEMA
_entry_schema["required"].append("consultation_cutoff")


class CriticBridge(transport.AdvisorBridge):
    def __init__(self, authority, provider=None, *, token, **kwargs):
        authority.authorize({"gate": authority.gate, "session_id": authority.session_id,
                             "role_id": authority.role_id, "risk": authority.risk,
                             "dispatch_token": token})
        self._token = token
        async def critique(payload):
            payload = {**payload, "messages": [dict(message) for message in payload["messages"]]}
            payload["messages"][0]["content"] = (
                "Adversarial critique: seek concrete counterexamples and evidence gaps; never approve. "
                + payload["messages"][0]["content"])
            return await provider(payload)
        super().__init__(authority, critique if provider is not None else None, **kwargs)

    async def consult(self, arguments):
        cutoff_token = None
        try:
            cutoff_token = _consultation_cutoff.set(trusted_cutoff(self.clock))
            request = transport.strict_json(arguments) if type(arguments) is bytes else transport.strict_json(
                transport.json_bytes(arguments, transport.MAX_REQUEST_BYTES))
            transport.validate_schema(request, REQUEST_SCHEMA)
            if "OMEGA_ADVISOR_SKIP_PIT" in os.environ:
                raise ToolError("ERR_INVALID_LAUNCH_AUTHORITY")
            return await super().consult({**request, "dispatch_token": self._token})
        except BaseException:
            self.failed = True
            raise
        finally:
            if cutoff_token is not None:
                _consultation_cutoff.reset(cutoff_token)

    async def _consult_accepted(self, request, text):
        response = await super()._consult_accepted(request, text)
        response["limitations"][0] = "Adversarial critique only; not approval or an independent L3 verdict."
        response.pop("response_sha256")
        response["response_sha256"] = hashlib.sha256(transport.json_bytes(response)).hexdigest()
        transport.validate_response(response, request, self.fallback_model)
        return response


def create_server(bridge):
    logger = logging.getLogger("mcp")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    server = transport.Server("omega-l3-critic", version="1.0.0")

    @server.list_tools()
    async def list_tools():
        return [transport.types.Tool(
            name="consult_critic", description="Private launch-bound adversarial critique; never approval.",
            inputSchema=REQUEST_SCHEMA, outputSchema=RESPONSE_SCHEMA,
            annotations=transport.types.ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=False))]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        try:
            if name != "consult_critic":
                raise ToolError("ERR_UNKNOWN_TOOL")
            response = await bridge.consult(arguments)
            return transport.types.CallToolResult(
                content=[transport.types.TextContent(type="text", text=transport.json_bytes(response).decode())],
                structuredContent=response, isError=response["status"] == "error")
        except Exception as exc:
            bridge.failed = True
            code = str(exc) if isinstance(exc, ToolError) and str(exc) in transport.TOOL_ERROR_CODES | {"ERR_UNKNOWN_TOOL"} else "ERR_INTERNAL_ERROR"
            return transport.types.CallToolResult(
                content=[transport.types.TextContent(type="text", text=code)], isError=True)

    return server


async def run_stdio(authority, *, token, provider=None, receipt_directory=None):
    logging.disable(logging.CRITICAL)
    bridge = CriticBridge(authority, provider if provider is not None else transport.router_provider_from_environment(),
                          token=token, receipt_directory=receipt_directory)
    server = create_server(bridge)
    async with transport.stdio_server(stdin=transport.StrictStdin(sys.stdin.buffer)) as (read, write):
        await server.run(read, write, server.create_initialization_options())
    return bridge.failed or not bridge._requests


def main() -> int:
    try:
        if len(sys.argv) != 1 or "OMEGA_ADVISOR_SKIP_PIT" in os.environ:
            raise ToolError("ERR_INVALID_ARGUMENTS")
        # Authorization never crosses MCP, argv, environment, or receipt boundaries.
        token = secrets.token_urlsafe(32)
        env = dict(os.environ, OMEGA_DISPATCH_TOKEN_SHA256=hashlib.sha256(token.encode()).hexdigest())
        authority = LaunchAuthority.from_environment(env)
        root = Path(__file__).resolve().parent.parent
        directory = root / ".ly_state" / "session" / "l3_critic_receipts"
        for parent in (root / ".ly_state", root / ".ly_state" / "session", directory):
            if parent.exists() or parent.is_symlink():
                info = parent.lstat()
                if not parent.is_dir() or parent.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ToolError("ERR_RECEIPT_IO")
        directory.mkdir(exist_ok=True)
        directory = directory / (authority.session_id + "_" + secrets.token_hex(16))
        directory.mkdir()
        async def run():
            return await run_stdio(authority, token=token, receipt_directory=directory)
        return 1 if transport.anyio.run(run) else 0
    except Exception:
        print("ERR_CRITIC_STARTUP_OR_TRANSPORT", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
