#!/usr/bin/env python3
"""
dispatch_l4.py - Pure generator for exact L4 Claude Code CLI dispatch command.

Generates validated PowerShell command string for Level 4 Super-Implementer execution.
Pure generator: no execution, no shell=True. Security invariant: redact credentials.

Usage:
    python scripts/dispatch_l4.py <role_name> <gate_name> <task_slug> "<task_description>" "<scope>" [--risk low|high] [--co-role <role_name>]...

Exit codes:
    0 = Success (command generated and printed)
    2 = Fail-closed CLI error (invalid flags, missing args, invalid role)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.dispatch_l2 import (
    ADVERSARIAL_DIRECTIVE_24D,
    _existing_graph_evidence,
    build_anti_drip_contract,
    build_anti_drip_prompt_clause,
    build_dimension_focus_clause,
    build_graph_prompt_evidence,
    build_regression_clause,
    build_verified_prompt_read_statement,
    canonical_json_bytes,
    ensure_session_containment,
    extract_prior_audit_outcomes,
    infer_risk,
    load_sanitized_lesson_entries,
    build_lessons_data_block,
    ps_quote,
    redact_credentials as _redact_context_credentials,
    resolve_l2_roles,
    run_graph_predispatch_gate,
)

DEFAULT_L4_MODELS = {
    "low": "sonnet",
    "medium": "sonnet",
    "high": "opus",
}
DEFAULT_L4_ADVISOR = "cx/gpt-6-astra"
L4_MODEL_ALLOWLIST = frozenset({"sonnet", "opus"})
L4_ADVISOR_ALLOWLIST = frozenset({"cx/gpt-6.1-sol", "cx/gpt-6-astra"})
_MCP_ADVISOR_MODEL_RE = re.compile(r"(?m)^- \*\*MCP Advisor Model\*\*: `(?P<model>[^`\r\n]+)`$")
MAX_TASK_CHARS = 16_384


def validate_l4_report_advisor_model(
    report_content: str, expected_model: str = DEFAULT_L4_ADVISOR
) -> list[str]:
    """Validate the independently reported MCP advisor model binding."""
    if expected_model not in L4_ADVISOR_ALLOWLIST:
        return ["invalid expected MCP advisor model"]
    matches = _MCP_ADVISOR_MODEL_RE.findall(report_content)
    if len(matches) != 1:
        return [
            "expected exactly one MCP Advisor Model metadata line; "
            f"got {len(matches)}"
        ]
    actual_model = matches[0]
    if actual_model not in L4_ADVISOR_ALLOWLIST:
        return ["report contains an unapproved MCP advisor model"]
    if actual_model != expected_model:
        return [
            "report MCP advisor model does not match dispatch model: "
            f"expected {expected_model}, got {actual_model}"
        ]
    return []


MAX_SCOPE_CHARS = 16_384
MAX_MODEL_CHARS = 64
# ponytail: Four dispatch artifacts, 1 MiB each; raise these quotas if the batch format expands.
MAX_ARTIFACT_SIZE = 1_048_576
MAX_ARTIFACT_FILES = 4

# ponytail: Known provider prefixes only; extend this pattern for new token formats.
_PROVIDER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-|gh[pousr]_|github_pat_|AIza|xox[baprs]-|xoxe-|gsk_|pplx-|hf_|r8_|glpat-)[A-Za-z0-9_-]+",
    re.IGNORECASE,
)


def redact_credentials(text: str) -> str:
    return _redact_context_credentials(_PROVIDER_TOKEN_RE.sub("[REDACTED]", text))


def validate_identifier(value: str, kind: str) -> str:
    limit = 128 if kind == "session_id" else 64
    if (not isinstance(value, str)
            or not re.fullmatch(rf"[A-Za-z0-9_-]{{1,{limit}}}", value)
            or redact_credentials(value) != value):
        print("[ERROR] Invalid dispatch identifier.", file=sys.stderr)
        raise SystemExit(2)
    return value


class ParsedL4Args(tuple):
    resume: bool = False
    force_new: bool = False

    def __new__(
        cls,
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        advisor_mode, explicit_advisor, dry_run, graph_evidence_path,
        model_decision_path, model_decision_digest,
        resume: bool = False, force_new: bool = False,
    ):
        inst = super().__new__(
            cls,
            (
                role_name, gate_name, task_slug, task_desc, scope,
                explicit_risk, co_roles, token_saver, explicit_model,
                advisor_mode, explicit_advisor, dry_run, graph_evidence_path,
                model_decision_path, model_decision_digest,
            ),
        )
        inst.resume = resume
        inst.force_new = force_new
        return inst


def _parse_l4_cli_args(args: list[str]):
    for item in args:
        if not isinstance(item, str):
            print("[ERROR] CLI arguments must be strings.", file=sys.stderr)
            sys.exit(2)
        if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in item):
            print("[ERROR] CLI arguments must be control-free strings.", file=sys.stderr)
            sys.exit(2)

    if any(a in ("-h", "--help", "-help", "help") for a in args):
        print(
            "Usage:\n"
            "    python scripts/dispatch_l4.py <role_name> <gate_name> <task_slug> \"<task_description>\" \"<scope>\" [options]\n\n"
            "Pre-dispatch validator, graph resolver, lesson retriever, and command generator for L4 Claude Code.\n\n"
            "Positional Arguments:\n"
            "  role_name                  Kebab-case L4 role name (role IDs 6-16, e.g. ui-ux-integrator, backend-engineer)\n"
            "  gate_name                  Target gate identifier (e.g. GATE_L4_VISUAL_UPGRADE_STAGE1_20261007)\n"
            "  task_slug                  Short slug for task session (e.g. l4_visual_plan)\n"
            "  task_description           Description of the task\n"
            "  scope                      Space-separated list of target files\n\n"
            "Options:\n"
            "  -h, --help                 Show this help message and exit\n"
            "  --risk {low,medium,high}   Execution risk profile\n"
            "  --model MODEL              Lead model (sonnet, opus)\n"
            "  --advisor-mode MODE        mcp (stdio MCP server) only\n"
            "  --mcp-advisor              Convenience alias for --advisor-mode mcp\n"
            "  --advisor MODEL            MCP advisor model\n"
            "  --co-role ROLE             Additional specialist co-role\n"
            "  --no-advisor               Unsupported; MCP advisor is mandatory\n"
            "  --token-saver              Enable token saver mode\n"
            "  --dry-run                  Generate artifacts without executing\n"
            "  --graph-evidence PATH      Use existing graph evidence file\n"
            "  --model-decision-path PATH Path to recorded model decision file\n"
            "  --model-decision-digest S  SHA-256 digest for model decision\n\n"
            "MCP Advisor:\n"
            "  Use --advisor-mode mcp (or --mcp-advisor) to launch Claude Code with the\n"
            "  omega-l4-advisor stdio MCP bridge, avoiding native-advisor proxy timeouts."
        )
        sys.exit(0)

    positional = []
    co_roles = []
    explicit_risk = None
    explicit_model = None
    token_saver = False
    dry_run = False
    graph_evidence_path = None
    model_decision_path = None
    model_decision_digest = None
    advisor_mode = None
    no_advisor = False
    explicit_advisor = None
    explicit_resume = False
    explicit_force_new = False

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--risk":
            if explicit_risk is not None:
                print("[ERROR] Duplicate --risk flag provided.", file=sys.stderr)
                sys.exit(2)
            if index + 1 >= len(args):
                print("[ERROR] Flag --risk requires a value: 'low', 'medium', or 'high'", file=sys.stderr)
                sys.exit(2)
            val = args[index + 1].strip().lower()
            if val not in ("low", "medium", "high"):
                print("[ERROR] Invalid risk level. Must be 'low', 'medium', or 'high'.", file=sys.stderr)
                sys.exit(2)
            explicit_risk = val
            index += 2
        elif arg == "--co-role":
            if index + 1 >= len(args):
                print("[ERROR] Flag --co-role requires one role name.", file=sys.stderr)
                sys.exit(2)
            role = args[index + 1].strip()
            if not role:
                print("[ERROR] Empty role name provided to --co-role.", file=sys.stderr)
                sys.exit(2)
            co_roles.append(validate_identifier(role, "co_role"))
            index += 2
        elif arg == "--token-saver":
            token_saver = True
            index += 1
        elif arg == "--model":
            if explicit_model is not None or index + 1 >= len(args):
                print("[ERROR] Flag --model requires a model name.", file=sys.stderr)
                sys.exit(2)
            explicit_model = args[index + 1].strip()
            if len(explicit_model) > MAX_MODEL_CHARS or explicit_model not in L4_MODEL_ALLOWLIST:
                print("[ERROR] Invalid or unapproved L4 model.", file=sys.stderr)
                sys.exit(2)
            index += 2
        elif arg == "--advisor-mode":
            if advisor_mode is not None or index + 1 >= len(args):
                print("[ERROR] --advisor-mode requires exactly one mode.", file=sys.stderr)
                sys.exit(2)
            advisor_mode = args[index + 1].strip().lower()
            if advisor_mode != "mcp":
                print("[ERROR] Only MCP advisor mode supported.", file=sys.stderr)
                sys.exit(2)
            index += 2
        elif arg == "--mcp-advisor":
            if advisor_mode is not None:
                print("[ERROR] Duplicate or conflicting advisor mode flag.", file=sys.stderr)
                sys.exit(2)
            advisor_mode = "mcp"
            index += 1
        elif arg == "--advisor":
            if explicit_advisor is not None or index + 1 >= len(args):
                print("[ERROR] Flag --advisor requires a model name.", file=sys.stderr)
                sys.exit(2)
            explicit_advisor = args[index + 1].strip()
            if len(explicit_advisor) > MAX_MODEL_CHARS or explicit_advisor not in L4_ADVISOR_ALLOWLIST:
                print("[ERROR] Invalid or unapproved L4 MCP advisor model.", file=sys.stderr)
                sys.exit(2)
            index += 2
        elif arg == "--no-advisor":
            print("[ERROR] MCP advisor mandatory; --no-advisor unsupported.", file=sys.stderr)
            sys.exit(2)
        elif arg == "--dry-run":
            dry_run = True
            index += 1
        elif arg == "--graph-evidence":
            if index + 1 >= len(args):
                print("[ERROR] Flag --graph-evidence requires exactly one value.", file=sys.stderr)
                sys.exit(2)
            graph_evidence_path = Path(args[index + 1].strip())
            index += 2
        elif arg in ("--model-decision-path", "--model-decision-digest"):
            if index + 1 >= len(args):
                print(f"[ERROR] Flag {arg} requires exactly one value.", file=sys.stderr)
                sys.exit(2)
            if arg == "--model-decision-path":
                if model_decision_path is not None or not args[index + 1].strip():
                    print("[ERROR] Duplicate --model-decision-path flag provided.", file=sys.stderr)
                    sys.exit(2)
                model_decision_path = args[index + 1].strip()
            else:
                if model_decision_digest is not None or not args[index + 1].strip():
                    print("[ERROR] Duplicate --model-decision-digest flag provided.", file=sys.stderr)
                    sys.exit(2)
                model_decision_digest = args[index + 1].strip()
            index += 2
        elif arg in ("--help", "-h"):
            print("Usage:\n    python scripts/dispatch_l4.py <role_name> <gate_name> <task_slug> \"<task_description>\" \"<scope>\" [options]\n")
            print(
                "Options:\n"
                "  --risk {low,medium,high}   Execution risk profile\n"
                "  --model MODEL              Lead model (sonnet, opus)\n"
                "  --advisor-mode MODE        mcp (stdio MCP server) only\n"
                "  --mcp-advisor              Convenience alias for --advisor-mode mcp\n"
                "  --advisor MODEL            MCP advisor model\n"
                "  --co-role ROLE             Additional specialist co-role\n"
                "  --no-advisor               Unsupported; MCP advisor is mandatory\n"
                "  --token-saver              Enable token saver mode\n"
                "  --dry-run                  Generate artifacts without executing\n"
                "  -h, --help                 Show this help message and exit\n\n"
                "MCP Advisor:\n"
                "  Use --advisor-mode mcp (or --mcp-advisor) to launch Claude Code with the\n"
                "  omega-l4-advisor stdio MCP bridge.\n\n"
                "Resume Controls:\n"
                "  --resume       Explicitly resume existing Claude Code session\n"
                "  --force-new    Force generation of a fresh new session, bypassing auto-resume"
            )
            sys.exit(0)
        elif arg == "--resume":
            if explicit_resume:
                print("[ERROR] Duplicate --resume flag provided.", file=sys.stderr)
                sys.exit(2)
            explicit_resume = True
            index += 1
        elif arg == "--force-new":
            if explicit_force_new:
                print("[ERROR] Duplicate --force-new flag provided.", file=sys.stderr)
                sys.exit(2)
            explicit_force_new = True
            index += 1
        elif arg.startswith("-"):
            print("[ERROR] Unknown CLI flag.", file=sys.stderr)
            sys.exit(2)
        else:
            positional.append(arg)
            index += 1

    if len(positional) != 5:
        print(
            "Usage: python scripts/dispatch_l4.py <role_name> <gate_name> <task_slug> "
            '"<task_description>" "<scope>" [options]\n'
            "Run 'python scripts/dispatch_l4.py --help' for available options.",
            file=sys.stderr,
        )
        sys.exit(2)

    role_name = positional[0].strip()
    gate_name = validate_identifier(positional[1].strip(), "gate_name")
    task_slug = validate_identifier(positional[2].strip(), "task_slug")
    task_desc = positional[3].strip()
    scope = positional[4].strip()

    if not task_desc:
        print("[ERROR] task_description cannot be empty.", file=sys.stderr)
        sys.exit(2)
    if not scope:
        print("[ERROR] scope cannot be empty.", file=sys.stderr)
        sys.exit(2)
    if len(task_desc) > MAX_TASK_CHARS or len(scope) > MAX_SCOPE_CHARS:
        print("[ERROR] task_description or scope exceeds the size limit.", file=sys.stderr)
        sys.exit(2)
    if (model_decision_path is None) != (model_decision_digest is None):
        print("[ERROR] model decision path and digest must be supplied together.", file=sys.stderr)
        sys.exit(2)
    if model_decision_digest is not None and not re.fullmatch(r"[0-9a-f]{64}", model_decision_digest):
        print("[ERROR] model decision digest must be lowercase SHA-256.", file=sys.stderr)
        sys.exit(2)
    if model_decision_path and explicit_model:
        print("[ERROR] --model cannot be combined with a model decision.", file=sys.stderr)
        sys.exit(2)
    if no_advisor or advisor_mode not in (None, "mcp"):
        print("[ERROR] MCP advisor is mandatory.", file=sys.stderr)
        sys.exit(2)
    advisor_mode = "mcp"
    if explicit_advisor is not None and explicit_advisor not in L4_ADVISOR_ALLOWLIST:
        print("[ERROR] Invalid or unapproved L4 MCP advisor model.", file=sys.stderr)
        sys.exit(2)
    if explicit_resume and explicit_force_new:
        print("[ERROR] Cannot specify both --resume and --force-new.", file=sys.stderr)
        sys.exit(2)

    return ParsedL4Args(
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        advisor_mode, explicit_advisor, dry_run, graph_evidence_path, model_decision_path, model_decision_digest,
        resume=explicit_resume, force_new=explicit_force_new,
    )


def _validate_advisor_timestamps(req: dict, ctx: dict, cutoff: datetime) -> None:
    """Reject (never rewrite) malformed or future as_of_time / observation available_at."""
    from scripts import l4_mcp_advisor as advisor

    as_of = advisor.parse_utc(req["as_of_time"])
    if as_of > cutoff:
        raise advisor.ToolError("ERR_LOOKAHEAD_DETECTED")
    for obs in ctx.get("observations", []):
        if isinstance(obs, dict):
            for holder in (obs, obs.get("data")):
                if isinstance(holder, dict) and "available_at" in holder:
                    if advisor.parse_utc(holder["available_at"]) > as_of:
                        raise advisor.ToolError("ERR_LOOKAHEAD_DETECTED")


def _run_private_mcp_stdio() -> int:
    """Local caller adapter: inject the private token before bridge validation."""
    try:
        from scripts import l4_mcp_advisor as advisor

        token = os.environ.pop("OMEGA_DISPATCH_TOKEN", None)
        default_model = os.environ.get("OMEGA_DISPATCH_ADVISOR_MODEL", DEFAULT_L4_ADVISOR)
        if default_model not in L4_ADVISOR_ALLOWLIST:
            raise ValueError("invalid advisor model")
        authority = advisor.LaunchAuthority.from_environment()
        if (not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token)
                or not hmac.compare_digest(hashlib.sha256(token.encode("ascii")).hexdigest(), authority.token_sha256)):
            raise ValueError("invalid private launch channel")


        class PrivateCaller(advisor.AdvisorBridge):
            async def consult(self, request):
                if type(request) is not dict or "dispatch_token" in request:
                    raise advisor.ToolError("ERR_UNAUTHORIZED_IDENTITY")
                req = dict(request)
                cutoff_str = authority.current_session_started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                # Only an omitted timestamp receives the session cutoff. Explicit null is invalid.
                if "as_of_time" not in req:
                    req["as_of_time"] = cutoff_str

                if "request_id" not in req or not req["request_id"]:
                    req["request_id"] = f"req_{os.urandom(8).hex()}"
                if "schema_version" not in req:
                    req["schema_version"] = "mcp-advisor-request/v1"
                if "gate" not in req:
                    req["gate"] = authority.gate
                elif req["gate"] != authority.gate:
                    raise advisor.ToolError("ERR_UNAUTHORIZED_IDENTITY")

                if "session_id" not in req:
                    req["session_id"] = authority.session_id
                elif req["session_id"] != authority.session_id:
                    raise advisor.ToolError("ERR_UNAUTHORIZED_IDENTITY")

                if "role_id" not in req:
                    req["role_id"] = authority.role_id
                elif req["role_id"] != authority.role_id:
                    raise advisor.ToolError("ERR_UNAUTHORIZED_IDENTITY")

                if "risk" not in req:
                    req["risk"] = authority.risk
                elif req["risk"] != authority.risk:
                    raise advisor.ToolError("ERR_UNAUTHORIZED_IDENTITY")
                if "purpose" not in req:
                    req["purpose"] = "architecture"
                elif type(req["purpose"]) is not str or req["purpose"] not in advisor.PURPOSES:
                    raise advisor.ToolError("ERR_INVALID_ARGUMENTS")
                if "model" not in req:
                    req["model"] = default_model
                elif type(req["model"]) is not str or req["model"] not in advisor.MODELS:
                    raise advisor.ToolError("ERR_INVALID_ARGUMENTS")

                ctx = req.get("context")
                if "context" not in req:
                    ctx = {"instructions": "In-session architectural advice.", "observations": []}
                if isinstance(ctx, str):
                    ctx = {"instructions": ctx, "observations": []}
                elif isinstance(ctx, dict):
                    ctx = {"instructions": "In-session architectural advice.", "observations": [], **ctx}
                else:
                    raise advisor.ToolError("ERR_INVALID_ARGUMENTS")
                advisor.validate_schema(ctx, advisor.CONTEXT_SCHEMA)
                req["context"] = ctx

                _validate_advisor_timestamps(req, ctx, authority.current_session_started_at)

                text = advisor.context_text(ctx, token)
                req["context_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
                return await super().consult({**req, "dispatch_token": token})

        async def run():
            advisor.logging.disable(advisor.logging.CRITICAL)
            bridge = PrivateCaller(authority, advisor.router_provider_from_environment())
            server = advisor.create_server(bridge)
            # ponytail: One local caller; add a separate authenticated adapter only for remote clients.
            schema = {**advisor.REQUEST_SCHEMA,
                      "properties": {key: value for key, value in advisor.REQUEST_SCHEMA["properties"].items()
                                     if key != "dispatch_token"},
                      "required": [key for key in advisor.REQUEST_SCHEMA["required"] if key != "dispatch_token"]}

            @server.list_tools()
            async def list_tools():
                return [advisor.types.Tool(name="consult_advisor", description="Private launch-bound advisory consultation; never approval.",
                                           inputSchema=schema, outputSchema=advisor.RESPONSE_SCHEMA)]

            async with advisor.stdio_server(stdin=advisor.StrictStdin(sys.stdin.buffer)) as (read, write):
                await server.run(read, write, server.create_initialization_options())
            return bridge.failed

        return 1 if advisor.anyio.run(run) else 0
    except Exception:
        print("ERR_ADVISOR_STARTUP_OR_TRANSPORT", file=sys.stderr)
        return 1


def _private_mcp_launch_command(command: str, gate: str, session: str, role: int, risk: str,
                                advisor_model: str = DEFAULT_L4_ADVISOR) -> str:
    if advisor_model not in L4_ADVISOR_ALLOWLIST:
        raise ValueError("invalid or unapproved L4 MCP advisor model")
    values = {"OMEGA_DISPATCH_GATE": gate, "OMEGA_DISPATCH_SESSION_ID": session,
              "OMEGA_DISPATCH_ROLE_ID": str(role), "OMEGA_DISPATCH_RISK": "low" if risk == "low" else "high",
              "OMEGA_DISPATCH_ADVISOR_MODEL": advisor_model}
    names = [*values, "OMEGA_DISPATCH_TOKEN_SHA256", "OMEGA_DISPATCH_TOKEN"]
    bindings = "; ".join(f"[Environment]::SetEnvironmentVariable({ps_quote(key)}, {ps_quote(value)}, 'Process')"
                         for key, value in values.items())
    return (
        "& { $ErrorActionPreference = 'Stop'; $__OMEGA_OLD_ENV = @{}; "
        f"$__OMEGA_ENV_NAMES = @({', '.join(ps_quote(name) for name in names)}); "
        "foreach ($name in $__OMEGA_ENV_NAMES) { $__OMEGA_OLD_ENV[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }; "
        "$__OMEGA_RNG = $null; $__OMEGA_SHA = $null; $__OMEGA_RANDOM = New-Object byte[] 32; "
        "try { $__OMEGA_RNG = [System.Security.Cryptography.RandomNumberGenerator]::Create(); "
        "$__OMEGA_RNG.GetBytes($__OMEGA_RANDOM); "
        "$__OMEGA_TOKEN = -join ($__OMEGA_RANDOM | ForEach-Object { $_.ToString('x2') }); "
        "$__OMEGA_SHA = [System.Security.Cryptography.SHA256]::Create(); "
        "$__OMEGA_TOKEN_HASH = -join ($__OMEGA_SHA.ComputeHash([Text.Encoding]::UTF8.GetBytes($__OMEGA_TOKEN)) | ForEach-Object { $_.ToString('x2') }); "
        f"{bindings}; "
        "[Environment]::SetEnvironmentVariable('OMEGA_DISPATCH_TOKEN', $__OMEGA_TOKEN, 'Process'); "
        "[Environment]::SetEnvironmentVariable('OMEGA_DISPATCH_TOKEN_SHA256', $__OMEGA_TOKEN_HASH, 'Process'); "
        f"{command}; $__OMEGA_EXIT = $LASTEXITCODE "
        "} catch { [Console]::Error.WriteLine('[ERROR] private MCP launch failed'); exit 2 } "
        "finally { foreach ($name in $__OMEGA_ENV_NAMES) { [Environment]::SetEnvironmentVariable($name, $__OMEGA_OLD_ENV[$name], 'Process') }; "
        "if ($null -ne $__OMEGA_RNG) { $__OMEGA_RNG.Dispose() }; if ($null -ne $__OMEGA_SHA) { $__OMEGA_SHA.Dispose() }; "
        "[Array]::Clear($__OMEGA_RANDOM, 0, $__OMEGA_RANDOM.Length); $__OMEGA_TOKEN = $null; $__OMEGA_TOKEN_HASH = $null }; "
        "if ($__OMEGA_EXIT -ne 0) { exit $__OMEGA_EXIT } }"
    )


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        _fsync_directory(target.parent)
    finally:
        temp.unlink(missing_ok=True)


def _read_artifact_bytes(path: Path, limit: int) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise OSError("dispatch artifact is not a regular file or exceeds size limit")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > limit
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise OSError("dispatch artifact changed or exceeds size limit")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise OSError("dispatch artifact exceeds size limit")
    return data


def _publish_dispatch_artifacts(artifacts: list[tuple[Path, bytes]]) -> None:
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= MAX_ARTIFACT_FILES:
        raise ValueError("dispatch artifact count exceeds limit")
    existing = []
    targets = set()
    for record in artifacts:
        if (not isinstance(record, tuple) or len(record) != 2 or not isinstance(record[0], Path)
                or not isinstance(record[1], bytes) or len(record[1]) > MAX_ARTIFACT_SIZE):
            raise ValueError("invalid dispatch artifact or size limit exceeded")
        path, _ = record
        if path in targets:
            raise ValueError("duplicate dispatch artifact target")
        targets.add(path)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            existing.append((path, False))
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARTIFACT_SIZE:
            raise OSError("dispatch artifact is not a regular file or exceeds size limit")
        existing.append((path, True))
    previous = [(path, _read_artifact_bytes(path, MAX_ARTIFACT_SIZE) if exists else None)
                for path, exists in existing]
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for target, data in artifacts:
            fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp = Path(name)
            staged.append((temp, target))
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, target in staged:
            published.append(target)
            os.replace(temp, target)
        for directory in dict.fromkeys(target.parent for target, _ in artifacts):
            _fsync_directory(directory)
        for target, expected in artifacts:
            if _read_artifact_bytes(target, len(expected)) != expected:
                raise OSError("dispatch artifact readback mismatch")
    except BaseException as exc:
        rollback_errors = []
        for target in reversed(published):
            old = next(old for path, old in previous if path == target)
            try:
                if old is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(target, old)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        for directory in dict.fromkeys(target.parent for target in published):
            try:
                _fsync_directory(directory)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError("dispatch artifact publication and rollback failed") from exc
        raise
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        from scripts.l4_mcp_advisor import ToolError, sync_windows_directory
        try:
            sync_windows_directory(directory)
        except ToolError:
            raise OSError("dispatch directory durability failed") from None
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_owned_lock(path: Path, identity: tuple[int, int], owner: bytes, *, partial: bool = False) -> None:
    # Cheap pre-check, then TOCTOU-safe delete: atomically rename whatever is at `path` to a
    # private tombstone and verify the tombstone by open descriptor. Anything not provably
    # ours is hard-linked back (never deleted); a failed restore keeps the tombstone.
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != identity:
        return
    tomb = path.with_name(f".{path.name}.{os.urandom(8).hex()}.lock")
    try:
        os.rename(path, tomb)
    except FileNotFoundError:
        return
    owned = False
    try:
        with open(tomb, "rb") as handle:
            held = os.fstat(handle.fileno())
            if (stat.S_ISREG(held.st_mode) and (held.st_dev, held.st_ino) == identity
                    and held.st_size <= len(owner) and (partial or held.st_size == len(owner))):
                contents = handle.read(len(owner) + 1)
                owned = contents == owner or (partial and owner.startswith(contents))
    except BaseException:
        _restore_lock(tomb, path)
        raise
    if owned:
        tomb.unlink()
    else:
        _restore_lock(tomb, path)


def _restore_lock(tomb: Path, path: Path) -> None:
    try:
        os.link(tomb, path)
    except OSError:
        return  # path re-created or link unsupported: keep tombstone rather than destroy foreign data
    tomb.unlink(missing_ok=True)


def _pid_is_stale(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID.
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    return False


def _lock_owner_is_stale(path: Path) -> tuple[tuple[int, int], bytes] | None:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            return None
        owner = path.read_bytes()
        pid_text, nonce = owner.decode("ascii").split(":", 1)
        if not pid_text.isdigit() or not re.fullmatch(r"[0-9a-f]{32}", nonce):
            return None
        pid = int(pid_text)
        if _pid_is_stale(pid):
            return (metadata.st_dev, metadata.st_ino), owner
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def acquire_session_lock(session_id: str, root: Path | None = None) -> tuple[Path, tuple[int, int], bytes]:
    root = root or REPO_ROOT
    validate_identifier(session_id, "session_id")
    directory = root / ".ly_state/session"
    directory.mkdir(parents=True, exist_ok=True)
    path = ensure_session_containment(directory / f"dispatch_{session_id}.lock", root)
    owner = f"{os.getpid()}:{os.urandom(16).hex()}".encode("ascii")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        stale = _lock_owner_is_stale(path)
        if stale is not None:
            _remove_owned_lock(path, *stale)
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                stale = None
        if stale is None:
            print("[ERROR] Dispatch already running; refusing duplicate dispatch.", file=sys.stderr)
            raise SystemExit(2)
    identity = None
    try:
        opened = os.fstat(fd)
        identity = (opened.st_dev, opened.st_ino)
        written = 0
        while written < len(owner):
            count = os.write(fd, owner[written:])
            if count <= 0:
                raise OSError("dispatch lock owner write made no progress")
            written += count
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        if identity is not None:
            _remove_owned_lock(path, identity, owner, partial=True)
        raise
    os.close(fd)
    return path, identity, owner


def release_session_lock(lock: tuple[Path, tuple[int, int], bytes] | None) -> None:
    if lock is not None:
        _remove_owned_lock(*lock)


def build_l4_report_scaffold(
    session_id: str,
    role_id: int,
    role_name: str,
    gate_name: str,
    contract: Mapping[str, Any],
    contract_sha256: str,
    contract_path: Path,
    source_files: Sequence[str],
    repo_root: Path,
    expected_report_date: str,
    advisor_model: str = DEFAULT_L4_ADVISOR,
) -> str:
    """Generate deterministic initial L4 report scaffold adhering strictly to format and anti-drip requirements."""
    contract_rel = contract_path.resolve().relative_to(repo_root.resolve()).as_posix()
    mode = contract.get("mode", "baseline")

    lines = [
        "# L4 Implementation Report",
        "",
        f"- **Role**: {role_id} {role_name} - Claude Code L4 Implementation",
        f"- **Gate**: `{gate_name}`",
        f"- **Session**: `{session_id}`",
        f"- **Date**: `{expected_report_date}`",
        f"- **Anti-Drip Mode**: `{mode}`",
        f"- **Anti-Drip Contract**: `{contract_rel}`",
        f"- **Anti-Drip Contract SHA-256**: `{contract_sha256}`",
        "",
        "## Summary",
        "- Initial implementation pending L4 worker updates.",
        "",
        "## Repo-Local Files Read",
    ]
    for sf in source_files:
        lines.append(f"- {sf}")
    lines.extend([
        "",
        "## Changes Made",
        "- Pending L4 worker implementation.",
        "",
        "## Verification",
        "- Pending test verification.",
        f"- **MCP Advisor Model**: `{advisor_model}`",
        "",
    ])

    if mode == "remediation":
        source = contract.get("source_audit") or {}
        source_path = source.get("path", "")
        source_sha256 = source.get("sha256", "")

        finding_sweeps = []
        for finding in contract.get("required_findings", []):
            fid = finding["finding_id"]
            title = finding.get("title", "")
            rc = f"Root-cause analysis for {fid}: {title}".strip()
            if len(rc) < 20:
                rc = rc + " - investigation pending"
            probes = list(finding.get("probe_strings", []))
            searches = []
            if probes:
                for probe in probes:
                    scanned = [probe] if ("/" in probe or probe.endswith(".py")) else ["scripts/dispatch_l4.py"]
                    searches.append({
                        "search_regex": re.escape(probe),
                        "scanned_paths": scanned,
                        "total_matches": 0,
                        "changed_matches": 0,
                        "non_actionable_matches": 0,
                        "non_actionable_justifications": [],
                        "unresolved_matches": 0,
                    })
            finding_sweeps.append({
                "finding_id": fid,
                "root_cause": rc,
                "probe_strings": probes,
                "searches": searches,
                "test_node_ids": [],
                "fault_injection_test_node_ids": [],
                "unresolved_matches": 0,
            })

        sweep_data = {
            "schema_version": "anti-drip-sweep/v1",
            "session_id": session_id,
            "gate_name": gate_name,
            "mode": mode,
            "contract_path": contract_rel,
            "contract_sha256": contract_sha256,
            "source_audit_path": source_path,
            "source_audit_sha256": source_sha256,
            "finding_sweeps": finding_sweeps,
            "pytest_node_ids": [],
            "fault_injection_test_node_ids": [],
            "unresolved_matches": 0,
        }
        sweep_json = json.dumps(sweep_data, indent=2, ensure_ascii=False)
        lines.extend([
            "## Root-Cause Architectural Sweep",
            "",
            "```json",
            sweep_json,
            "```",
            "",
        ])

    lines.extend([
        "## Forbidden Path Scan",
        r"- `.gemini\antigravity-ide\scratch\ag-kit`: not read; non-authoritative scan evidence only; no reliance.",
        r"- `.openclaw\skills`: not read; non-authoritative scan evidence only; no reliance.",
        r"- `C:\Users\GHC\.agents`: not read; non-authoritative scan evidence only; no reliance.",
        r"- `.codex\memories`: not read; non-authoritative scan evidence only; no reliance.",
        "",
    ])
    return "\n".join(lines)


def _generate_l4_dispatch(
    roles: list[dict],
    gate_name: str,
    task_desc: str,
    scope: str,
    session_id: str,
    lessons_block: str,
    risk: str,
    risk_reason: str,
    model: str,
    advisor_model: str | None,
    graph_evidence: dict,
    jev_dimension_focus: int | None = None,
    token_saver: bool = False,
    dry_run: bool = False,
    advisor_mode: str = "mcp",
    resume: bool = False,
    force_new: bool = False,
):
    validate_identifier(gate_name, "gate_name")
    validate_identifier(session_id, "session_id")
    if model not in L4_MODEL_ALLOWLIST:
        raise ValueError("invalid or unapproved L4 model")
    if advisor_mode != "mcp":
        raise ValueError("MCP advisor is mandatory")
    if advisor_model is not None and advisor_model not in L4_ADVISOR_ALLOWLIST:
        raise ValueError("invalid or unapproved L4 MCP advisor model")
    if risk not in ("low", "medium", "high") or type(roles[0]["role_id"]) is not int or not 6 <= roles[0]["role_id"] <= 16:
        raise ValueError("invalid launch authority")
    if risk == "high" and model != DEFAULT_L4_MODELS["high"]:
        raise ValueError("high-risk L4 dispatch requires opus")
    task_desc = redact_credentials(task_desc)
    scope = redact_credentials(scope)
    primary = roles[0]
    co_roles = roles[1:]
    role_name = primary["name"]
    role_id = primary["role_id"]
    role_metadata = "; ".join(
        f"role_id={role['role_id']}, role_name={role['name']}, role_file={role['role_file']}"
        for role in roles
    )
    source_files = list(dict.fromkeys(
        path for role in roles for path in [role["role_file"], *role["skill_files"]]
    ))
    source_manifest = ", ".join(source_files)
    token_saver_clause = (
        "TOKEN SAVER DIRECTIVE: Minimize token usage. Perform targeted, minimal diffs only; do not dump or rewrite untouched code. Keep L4 report concise. "
        if token_saver else ""
    )
    outcome = extract_prior_audit_outcomes(gate_name, REPO_ROOT)
    contract_path = ensure_session_containment(
        REPO_ROOT / ".ly_state" / "session" / f"anti_drip_contract_{session_id}.json", REPO_ROOT
    )
    if dry_run and contract_path.is_file():
        try:
            from scripts.validate_l2_report import _load_and_verify_anti_drip_contract
        except ImportError:
            from validate_l2_report import _load_and_verify_anti_drip_contract
        contract, contract_sha256, errors = _load_and_verify_anti_drip_contract(session_id, REPO_ROOT)
        if errors or contract is None or contract_sha256 is None:
            raise RuntimeError("dry-run anti-drip contract validation failed: " + "; ".join(errors))
    else:
        contract = build_anti_drip_contract(session_id, gate_name, REPO_ROOT, outcome)
        contract_sha256 = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    if contract.get("session_id") != session_id or contract.get("gate_name") != gate_name:
        raise RuntimeError("anti-drip contract session or gate binding mismatch")

    anti_drip_clause = build_anti_drip_prompt_clause(
        contract_path, contract_sha256, contract, REPO_ROOT
    )
    dimension_focus_clause = build_dimension_focus_clause(jev_dimension_focus)
    if dimension_focus_clause:
        anti_drip_clause = f"{anti_drip_clause}\n{dimension_focus_clause}"
    anti_drip_mandate = (
        "STRICT ANTI-DRIP DISCIPLINE & ARCHITECTURAL ROOT-CAUSE MANDATE:\n"
        "(1) ABSOLUTE BAN ON SYMPTOM-LEVEL PATCHES: Never write isolated single-line or localized patches that merely silence a specific test or failing trace. "
        "Every defect is symptom of an architectural boundary omission. You MUST trace root causes and systematically sweep ALL matching implementation patterns across the entire module.\n"
        "(2) EXHAUSTIVE SCOPE & SYMMETRY SWEEP: Search and verify every related route, function, DTO, calculation branch, and error handler across all scoped files. "
        "Enforce strict read/write/list symmetry, input validation symmetry, and error classification symmetry (e.g. 422 vs 424 vs 500). "
        "Ensure unverified caller data NEVER inherits verified historical/PIT provenance contracts.\n"
        "(3) PRE-AUDIT ADVERSARIAL SELF-FUZZING: You MUST write robust adversarial unit tests covering boundary conditions before publishing the report: "
        "None/empty values, non-finite values (NaN, Inf, -Inf), zero and negative divisors, numeric overflow (>1e12), boundary timestamps (inclusive cutoff, 15:30 ICT session close), and malformed payloads.\n"
        "(4) SINGLE-SHOT CLOSURE: Consolidate 100% of required findings and edge cases simultaneously in this single cycle. "
        "Never defer fixes to subsequent cycles; piecemeal fixes ('drip-fixing') violate the anti-drip contract and result in automatic audit rejection.\n"
        "(5) EXACT REPORT & INVARIANCE INTEGRITY: The report header Date MUST match the session suffix (YYYY-MM-DD for YYYYMMDD). "
        "Never alter contract SHA-256 or prompt markers. Ensure LF line endings without CRLF drift. "
        "For remediation mode, the Root-Cause Architectural Sweep JSON must account for 100% of required findings and probe strings with unresolved_matches=0.\n"
    )

    if contract["mode"] == "remediation":
        failed_summary = ", ".join(
            f"Dim {item['dimension']} ({item['name']})" for item in contract["failed_dimensions"]
        )
        finding_summary = ", ".join(
            f"{item['finding_id']} ({item['title']})" for item in contract["required_findings"]
        )
        adversarial_clause = (
            f"{anti_drip_clause}\n"
            f"{anti_drip_mandate}"
            f"ANTI-DRIP REMEDIATION SUMMARY: failed dimensions [{failed_summary}]; "
            f"required findings [{finding_summary}]."
        )
    else:
        adversarial_clause = (
            f"{anti_drip_clause}\n"
            f"{anti_drip_mandate}"
            f"{ADVERSARIAL_DIRECTIVE_24D}"
        )

    advisor_clause = ""
    if advisor_mode == "mcp":
        advisor_clause = (
            f"MCP ADVISOR: Consult consult_advisor for architecture and correctness; model {advisor_model}. "
            "The local caller supplies private authorization; never request or print its token. "
            f"Use gate={gate_name}, session_id={session_id}, role_id={role_id}, risk={'low' if risk == 'low' else 'high'}. "
            "Required advisor errors block completion; advice is never independent L3 approval.\n"
        )

    suffix_match = re.search(r"_(20\d{6})(?:_(20\d{6}))?$", session_id)
    if suffix_match:
        date_token = suffix_match.group(2) or suffix_match.group(1)
        expected_report_date = f"{date_token[:4]}-{date_token[4:6]}-{date_token[6:8]}"
    else:
        expected_report_date = datetime.now().strftime("%Y-%m-%d")

    prompt = (
        f"REPO_ROOT: {REPO_ROOT}. "
        f"ROLE: {role_id} {role_name} - Claude Code L4 Implementation Work. "
        f"PRIMARY AND CO-ROLE METADATA: {role_metadata}. "
        f"AUTHORIZED REPO-LOCAL ROLE/SKILL FILES: {source_manifest}. "
        f"TASK: {task_desc}. "
        f"GATE: {gate_name}. "
        f"{build_graph_prompt_evidence(graph_evidence)} "
        f"LESSONS: {lessons_block}. "
        f"{token_saver_clause}"
        f"SKILL SOURCE CONTRACT: REPO_AGENT_ROOT={REPO_ROOT}\\.agents\\agent; "
        f"REPO_SKILL_ROOT={REPO_ROOT}\\.agents\\skills. "
        f"First run Set-Location '{REPO_ROOT}'; "
        f"first read REPO_AGENT_ROOT\\{role_name}.md parse frontmatter; "
        f"then read exact declared skill.md files listed only in REPO_SKILL_ROOT. "
        f"Any skill loaded from Antigravity scratch/OpenClaw/C:\\Users\\GHC\\.agents/Codex memory is non-authoritative. "
        f"Report exact repo-local role/skill files listed above and forbidden path scan result. "
        f"SCOPE: {scope}. "
        f"REQUIREMENTS: repo-relative paths under REPO_ROOT only; implement/refactor/test only; "
        f"write L4 implementation report at .ly_state/session/{session_id}.md. "
        f"Do not audit or approve. Stop/NEEDS_FIX if repo-local source missing.\n"
        f"{advisor_clause}"
        f"{adversarial_clause}\n"
        f"L4 REPORT FORMAT (MANDATORY): "
        f"You must write the final implementation report to .ly_state/session/{session_id}.md "
        f"with exact structure: "
        f"# L4 Implementation Report\n\n"
        f"- **Role**: {role_id} {role_name} - Claude Code L4 Implementation\n"
        f"- **Gate**: `{gate_name}`\n"
        f"- **Session**: `{session_id}`\n"
        f"- **Date**: `{expected_report_date}`\n"
        f"- **Anti-Drip Mode**: `{contract['mode']}`\n"
        f"- **Anti-Drip Contract**: `{contract_path.relative_to(REPO_ROOT).as_posix()}`\n"
        f"- **Anti-Drip Contract SHA-256**: `{contract_sha256}`\n\n"
        f"Include sections in order: "
        f"(1) Header lines must remain intact as pre-created. "
        f"(2) '## Summary' concise overview. "
        f"(3) '## Repo-Local Files Read' followed by bullet list of each file actually read "
        f"from REPO_AGENT_ROOT and REPO_SKILL_ROOT (e.g. '- .agents/agent/{role_name}.md', "
        f"'- .agents/skills/{{skill}}/skill.md'). "
        f"(4) '## Changes Made' listing modified files. "
        f"(5) '## Verification' actual test command outputs (use safe pytest flags: -o addopts=\"\" --capture=sys -p no:terminal --junitxml=.ly_state/session/{session_id}_test.xml). "
        f"Include exactly one '- **MCP Advisor Model**: `{{model}}`' line; model must match `{advisor_model or DEFAULT_L4_ADVISOR}`. "
        f"(6) '## Forbidden Path Scan' EXACTLY four lines, one per forbidden path, each line "
        f"ending with EXACT phrase: 'non-authoritative scan evidence only; no reliance.' "
        f"The four lines must mention: '.gemini\\antigravity-ide\\scratch\\ag-kit', '.openclaw\\skills', "
        f"'C:\\Users\\GHC\\.agents', '.codex\\memories'. "
        f"FILENAME must be {session_id}.md with NO _retry suffix. "
        f"{build_regression_clause()}"
    )
    prompt = redact_credentials(prompt)

    prompt_dir = REPO_ROOT / ".ly_state" / "session"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = ensure_session_containment(prompt_dir / f"prompt_{session_id}.txt", REPO_ROOT)
    report_path = ensure_session_containment(prompt_dir / f"{session_id}.md", REPO_ROOT)
    expected_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    read_stmt = build_verified_prompt_read_statement(prompt_path, expected_digest)

    is_resume = False
    resume_reason = ""
    if force_new:
        is_resume = False
        resume_reason = "BYPASSED (--force-new explicitly provided)"
    elif resume:
        is_resume = True
        resume_reason = "EXPLICIT_RESUME_FLAG"
    elif prompt_path.is_file() and prompt_path.stat().st_size > 0:
        is_resume = True
        resume_reason = "EXISTING_SESSION_DETECTED"
    elif report_path.is_file() and report_path.stat().st_size > 100:
        is_resume = True
        resume_reason = "EXISTING_REPORT_DETECTED"

    if is_resume:
        cmd = (
            f"{read_stmt}; "
            f"$__OMEGA_PROMPT | claude -p --resume {ps_quote(session_id)} --dangerously-skip-permissions --model {ps_quote(model)}"
        )
    else:
        cmd = (
            f"{read_stmt}; "
            f"$__OMEGA_PROMPT | claude -p --dangerously-skip-permissions --model {ps_quote(model)}"
        )
    if advisor_mode == "mcp":
        mcp_servers: dict[str, Any] = {
            "omega-l4-advisor": {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(REPO_ROOT / "scripts" / "dispatch_l4.py"), "--private-mcp-stdio"],
            }
        }
        config = json.dumps({"mcpServers": mcp_servers}, separators=(",", ":"))
        # Windows PowerShell 5.1 strips JSON quotes when constructing native argv.
        config_setup = (
            f"$__OMEGA_MCP_CONFIG = {ps_quote(config)}; "
            "if ($PSVersionTable.PSVersion -lt [version]'7.3' -or $PSNativeCommandArgumentPassing -eq 'Legacy') "
            "{ $__OMEGA_MCP_CONFIG = $__OMEGA_MCP_CONFIG.Replace('\"', '\\\"') }; "
        )
        cmd = config_setup + cmd + " --strict-mcp-config --mcp-config $__OMEGA_MCP_CONFIG"
        cmd = _private_mcp_launch_command(cmd, gate_name, session_id, role_id, risk, advisor_model or DEFAULT_L4_ADVISOR)

    if not dry_run:
        report_scaffold = build_l4_report_scaffold(
            session_id=session_id,
            role_id=role_id,
            role_name=role_name,
            gate_name=gate_name,
            contract=contract,
            contract_sha256=contract_sha256,
            contract_path=contract_path,
            source_files=source_files,
            repo_root=REPO_ROOT,
            expected_report_date=expected_report_date,
            advisor_model=advisor_model or DEFAULT_L4_ADVISOR,
        )
        artifacts_to_publish = [
            (contract_path, canonical_json_bytes(contract)),
            (contract_path.with_suffix(".sha256"), f"{contract_sha256}  {contract_path.name}\n".encode("ascii")),
            (prompt_path, prompt.encode("utf-8")),
        ]
        is_stub = report_path.is_file() and report_path.stat().st_size <= 600
        if not is_resume or not report_path.is_file() or is_stub:
            artifacts_to_publish.append((report_path, report_scaffold.encode("utf-8")))
        _publish_dispatch_artifacts(artifacts_to_publish)

    print(f"SESSION_ID={session_id}")
    print(f"ROLE_ID={role_id}")
    print(f"ROLE_NAME={role_name}")
    print(f"CO_ROLE_IDS={','.join(str(role['role_id']) for role in co_roles)}")
    print(f"CO_ROLE_NAMES={','.join(role['name'] for role in co_roles)}")
    print(f"GATE={gate_name}")
    print(f"MODEL={model}")
    print(f"ADVISOR_MODE={advisor_mode}")
    print(f"ADVISOR_MODEL={advisor_model or 'none'}")
    print(f"MCP ADVISOR: {advisor_model or DEFAULT_L4_ADVISOR}")
    print(f"RISK={risk} ({risk_reason})")
    print(f"ANTI_DRIP_MODE={contract['mode']}")
    print(f"ANTI_DRIP_CONTRACT={contract_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"ANTI_DRIP_CONTRACT_SHA256={contract_sha256}")
    print(f"PROMPT_FILE={prompt_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"PROMPT_SHA256={expected_digest}")
    if is_resume:
        print(f"RESUME_MODE=ACTIVE (RESUME_FIRST_MANDATORY_20261008: {resume_reason})")
    elif force_new:
        print("RESUME_MODE=BYPASSED (--force-new)")
    print("---COMMAND---")
    print(cmd)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if sys.argv[1:] == ["--private-mcp-stdio"]:
        return _run_private_mcp_stdio()

    parsed_args = _parse_l4_cli_args(sys.argv[1:])
    (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_role_names, token_saver, explicit_model,
        advisor_mode, explicit_advisor, dry_run, graph_evidence_path, model_decision_path, model_decision_digest,
    ) = parsed_args
    resume = parsed_args.resume
    force_new = parsed_args.force_new

    validate_identifier(role_name, "role_name")
    validate_identifier(gate_name, "gate_name")
    validate_identifier(task_slug, "task_slug")
    task_desc = redact_credentials(task_desc)
    scope = redact_credentials(scope)

    today = datetime.now().strftime("%Y%m%d")

    if explicit_risk:
        risk = explicit_risk
        risk_reason = "explicit --risk flag"
    elif token_saver:
        risk = "low"
        risk_reason = "token-saver flag active"
    else:
        risk, risk_reason = infer_risk(scope)

    try:
        roles = resolve_l2_roles(role_name, co_role_names)
    except RuntimeError:
        print("[ERROR] Unable to resolve authorized L4 roles.", file=sys.stderr)
        return 2

    role_id = roles[0]["role_id"]
    session_id = f"l4_role{role_id}_{task_slug}_{today}"

    model = explicit_model or DEFAULT_L4_MODELS[risk]
    jev_dimension_focus = None
    if model_decision_path:
        try:
            try:
                from scripts.jev_model_router import L2_LEAD_ALLOWLIST, escape_xml_data, load_decision
            except ImportError:
                from jev_model_router import L2_LEAD_ALLOWLIST, escape_xml_data, load_decision
            relative_decision_path = PurePosixPath(model_decision_path)
            if (relative_decision_path.is_absolute() or "\\" in model_decision_path
                    or any(part in {"", ".", ".."} for part in relative_decision_path.parts)):
                raise ValueError("model decision path must be a normalized repo-relative POSIX path")
            raw_decision_path = REPO_ROOT.joinpath(*relative_decision_path.parts)
            session_root = (REPO_ROOT / ".ly_state" / "session").resolve()
            decision_path = raw_decision_path.resolve()
            parent = raw_decision_path.parent
            while parent != REPO_ROOT and parent != parent.parent:
                if parent.is_symlink():
                    raise ValueError("model decision path cannot traverse symlink directories")
                parent = parent.parent
            if (not session_root.is_relative_to(REPO_ROOT.resolve()) or raw_decision_path.is_symlink()
                    or not decision_path.is_relative_to(session_root)
                    or not decision_path.is_file()):
                raise ValueError("model decision path must name a regular file under .ly_state/session")
            decision = load_decision(
                decision_path, model_decision_digest,
                expected_role="l2", expected_gate=gate_name,
                expected_session_id=session_id,
                expected_risk="low" if risk == "low" else "high",
            )
            if decision["task"] != escape_xml_data(task_desc):
                raise ValueError("model decision task context mismatch")
            model = DEFAULT_L4_MODELS["high" if risk == "high" or decision["lead_model"] == L2_LEAD_ALLOWLIST[0] else "low"]
            jev_dimension_focus = decision.get("dimension_focus")
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            print(f"[ERROR] {redact_credentials(str(exc))}", file=sys.stderr)
            return 2
    advisor_model = explicit_advisor or DEFAULT_L4_ADVISOR

    if risk == "high" and model != DEFAULT_L4_MODELS["high"]:
        print("[ERROR] High-risk L4 dispatch requires opus.", file=sys.stderr)
        return 2

    lock_path = None
    exit_code = 0
    try:
        lock_path = None if dry_run else acquire_session_lock(session_id, REPO_ROOT)
        entries = load_sanitized_lesson_entries(role_id, task_desc)
        lessons_block = build_lessons_data_block(entries)
        graph_evidence = (
            _existing_graph_evidence(session_id, REPO_ROOT, graph_evidence_path)
            if dry_run else run_graph_predispatch_gate(session_id, scope, REPO_ROOT)
        )
        _generate_l4_dispatch(
            roles=roles,
            gate_name=gate_name,
            task_desc=task_desc,
            scope=scope,
            session_id=session_id,
            lessons_block=lessons_block,
            risk=risk,
            risk_reason=risk_reason,
            model=model,
            advisor_model=advisor_model,
            graph_evidence=graph_evidence,
            jev_dimension_focus=jev_dimension_focus,
            token_saver=token_saver,
            dry_run=dry_run,
            advisor_mode=advisor_mode,
            resume=resume,
            force_new=force_new,
        )
    except (RuntimeError, OSError, UnicodeError, ValueError) as exc:
        print(f"[ERROR] {redact_credentials(str(exc))}", file=sys.stderr)
        exit_code = 2
    finally:
        try:
            release_session_lock(lock_path)
        except OSError as exc:
            print(f"[ERROR] {redact_credentials(str(exc))}", file=sys.stderr)
            exit_code = 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
