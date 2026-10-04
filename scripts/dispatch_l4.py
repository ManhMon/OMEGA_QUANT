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
    acquire_session_lock,
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
    release_session_lock,
    resolve_l2_roles,
    run_graph_predispatch_gate,
)

DEFAULT_L4_MODELS = {
    "low": "sonnet",
    "medium": "sonnet",
    "high": "opus",
}
DEFAULT_L4_ADVISOR = "opus"
L4_MODEL_ALLOWLIST = frozenset(DEFAULT_L4_MODELS.values())
MAX_TASK_CHARS = 16_384
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


def _parse_l4_cli_args(args: list[str]):
    for item in args:
        if not isinstance(item, str):
            print("[ERROR] CLI arguments must be strings.", file=sys.stderr)
            sys.exit(2)
        if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in item):
            print("[ERROR] CLI arguments must be control-free strings.", file=sys.stderr)
            sys.exit(2)

    positional = []
    co_roles = []
    explicit_risk = None
    explicit_model = None
    token_saver = False
    dry_run = False
    graph_evidence_path = None
    model_decision_path = None
    model_decision_digest = None
    enable_advisor = True

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
        elif arg == "--no-advisor":
            enable_advisor = False
            index += 1
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
        elif arg.startswith("-"):
            print("[ERROR] Unknown CLI flag.", file=sys.stderr)
            sys.exit(2)
        else:
            positional.append(arg)
            index += 1

    if len(positional) != 5:
        print(
            "Usage: python scripts/dispatch_l4.py <role_name> <gate_name> <task_slug> "
            '"<task_description>" "<scope>" [--risk low|high] [--co-role <role_name>]... [--token-saver] [--model-decision-path <path> --model-decision-digest <sha256>]',
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

    return (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_roles, token_saver, explicit_model,
        enable_advisor, dry_run, graph_evidence_path, model_decision_path, model_decision_digest,
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
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
):
    validate_identifier(gate_name, "gate_name")
    validate_identifier(session_id, "session_id")
    if model not in L4_MODEL_ALLOWLIST:
        raise ValueError("invalid or unapproved L4 model")
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
    if contract["mode"] == "remediation":
        failed_summary = ", ".join(
            f"Dim {item['dimension']} ({item['name']})" for item in contract["failed_dimensions"]
        )
        finding_summary = ", ".join(
            f"{item['finding_id']} ({item['title']})" for item in contract["required_findings"]
        )
        adversarial_clause = (
            f"{anti_drip_clause}\nANTI-DRIP REMEDIATION SUMMARY: failed dimensions [{failed_summary}]; "
            f"required findings [{finding_summary}]."
        )
    else:
        adversarial_clause = f"{anti_drip_clause}\n{ADVERSARIAL_DIRECTIVE_24D}"

    advisor_clause = (
        f"NATIVE ADVISOR: Actively consult native advisor tool (--advisor {advisor_model} / cx/gpt-6.1-sol[1m]) "
        "for complex architectural trade-offs, PIT safety boundaries, 24D invariants, and algorithm edge cases. "
        if advisor_model else ""
    )

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
        f"Do not audit or approve. Stop/NEEDS_FIX if repo-local source missing. "
        f"{advisor_clause}"
        f"{adversarial_clause}\n"
        f"L4 REPORT FORMAT (MANDATORY): "
        f"You must write the final implementation report to .ly_state/session/{session_id}.md "
        f"with exact structure: "
        f"# L4 Implementation Report\n\n"
        f"- **Role**: {role_id} {role_name} - Claude Code L4 Implementation\n"
        f"- **Gate**: `{gate_name}`\n"
        f"- **Session**: `{session_id}`\n"
        f"- **Date**: `{datetime.now().strftime('%Y-%m-%d')}`\n"
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
        f"(5) '## Verification' actual test command outputs (use safe pytest flags: -o addopts=\"\" --capture=sys -p no:terminal). "
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
    expected_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    if not dry_run:
        report_path = ensure_session_containment(prompt_dir / f"{session_id}.md", REPO_ROOT)
        report_header = (
            f"# L4 Implementation Report\n\n"
            f"- **Role**: {role_id} {role_name} - Claude Code L4 Implementation\n"
            f"- **Gate**: `{gate_name}`\n"
            f"- **Session**: `{session_id}`\n"
            f"- **Date**: `{datetime.now().strftime('%Y-%m-%d')}`\n"
            f"- **Anti-Drip Mode**: `{contract['mode']}`\n"
            f"- **Anti-Drip Contract**: `{contract_path.relative_to(REPO_ROOT).as_posix()}`\n"
            f"- **Anti-Drip Contract SHA-256**: `{contract_sha256}`\n\n"
        )
        _publish_dispatch_artifacts([
            (contract_path, canonical_json_bytes(contract)),
            (contract_path.with_suffix(".sha256"), f"{contract_sha256}  {contract_path.name}\n".encode("ascii")),
            (prompt_path, prompt.encode("utf-8")),
            (report_path, report_header.encode("utf-8")),
        ])

    read_stmt = build_verified_prompt_read_statement(prompt_path, expected_digest)
    advisor_flag = f" --advisor {advisor_model}" if advisor_model else ""
    cmd = (
        f"{read_stmt}; "
        f"$__OMEGA_PROMPT | claude -p --dangerously-skip-permissions --model {ps_quote(model)}"
        f"{f' --advisor {ps_quote(advisor_model)}' if advisor_model else ''}"
    )

    print(f"SESSION_ID={session_id}")
    print(f"ROLE_ID={role_id}")
    print(f"ROLE_NAME={role_name}")
    print(f"CO_ROLE_IDS={','.join(str(role['role_id']) for role in co_roles)}")
    print(f"CO_ROLE_NAMES={','.join(role['name'] for role in co_roles)}")
    print(f"GATE={gate_name}")
    print(f"MODEL={model}")
    print(f"ADVISOR_MODEL={advisor_model or 'none'}")
    print(f"RISK={risk} ({risk_reason})")
    print(f"ANTI_DRIP_MODE={contract['mode']}")
    print(f"ANTI_DRIP_CONTRACT={contract_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"ANTI_DRIP_CONTRACT_SHA256={contract_sha256}")
    print(f"PROMPT_FILE={prompt_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"PROMPT_SHA256={expected_digest}")
    print("---COMMAND---")
    print(cmd)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    (
        role_name, gate_name, task_slug, task_desc, scope,
        explicit_risk, co_role_names, token_saver, explicit_model,
        enable_advisor, dry_run, graph_evidence_path, model_decision_path, model_decision_digest,
    ) = _parse_l4_cli_args(sys.argv[1:])

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
            model = DEFAULT_L4_MODELS["high" if decision["lead_model"] == L2_LEAD_ALLOWLIST[0] else "low"]
            jev_dimension_focus = decision.get("dimension_focus")
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            print(f"[ERROR] {redact_credentials(str(exc))}", file=sys.stderr)
            return 2
    advisor_model = DEFAULT_L4_ADVISOR if enable_advisor else None

    lock_path = None if dry_run else acquire_session_lock(session_id, REPO_ROOT)
    try:
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
        )
    except (RuntimeError, OSError, UnicodeError, ValueError) as exc:
        print(f"[ERROR] {redact_credentials(str(exc))}", file=sys.stderr)
        return 2
    finally:
        release_session_lock(lock_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
