#!/usr/bin/env python3
"""Fail-closed anti-drip validation before L3 dispatch."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError as exc:
    Draft202012Validator = None
    FormatChecker = None
    SchemaError = Exception
    JSONSCHEMA_IMPORT_ERROR: ImportError | None = exc
else:
    JSONSCHEMA_IMPORT_ERROR = None

sys.path.insert(0, str(Path(__file__).parent))
from sod_gate_enforcer import (  # noqa: E402
    _validate_l2_report_content,
    load_role_specs,
    validate_forbidden_path_usage,
    validate_l2_role,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_REL = PurePosixPath(".ly_state/session")
AUDIT_REPORTS_REL = SESSION_REL / "audit_reports"
MIN_REPORT_BYTES = 256
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CLI_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SOURCE_AUDIT_REL_RE = re.compile(r"^\.ly_state/session/audit_reports/[A-Za-z0-9_.-]+\.md$")
CONTRACT_SIDECAR_RE = re.compile(
    rb"^(?P<sha>[0-9a-f]{64})  (?P<name>anti_drip_contract_[A-Za-z0-9_-]{1,128}\.json)\n$"
)
REPORT_GATE_RE = re.compile(r"(?m)^- \*\*Gate\*\*: `(?P<value>[A-Za-z0-9_-]{1,128})`[ \t]*$")
REPORT_SESSION_RE = re.compile(r"(?m)^- \*\*Session\*\*: `(?P<value>[A-Za-z0-9_-]{1,128})`[ \t]*$")
REPORT_MODE_RE = re.compile(r"(?m)^- \*\*Anti-Drip Mode\*\*: `(?P<value>baseline|remediation)`[ \t]*$")
REPORT_CONTRACT_RE = re.compile(
    r"(?m)^- \*\*Anti-Drip Contract\*\*: `(?P<value>\.ly_state/session/anti_drip_contract_[A-Za-z0-9_-]{1,128}\.json)`[ \t]*$"
)
REPORT_SHA_RE = re.compile(r"(?m)^- \*\*Anti-Drip Contract SHA-256\*\*: `(?P<value>[0-9a-f]{64})`[ \t]*$")
ROOT_CAUSE_SWEEP_HEADING = "## Root-Cause Architectural Sweep"
ROOT_CAUSE_SWEEP_BLOCK_RE = re.compile(
    r"(?ms)^## Root-Cause Architectural Sweep[ \t]*\r?\n\r?\n```json[ \t]*\r?\n"
    r"(?P<payload>.*?)\r?\n```[ \t]*(?=\r?\n(?:\r?\n)?(?:## |\Z)|\Z)"
)
PYTEST_NODE_ID_RE = re.compile(
    r"^tests/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py::[A-Za-z0-9_:\[\].,/=+\-]+$"
)
SHELL_METACHAR_RE = re.compile(r"[;&|`$<>^%!\"'()\r\n\x00]")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
PROMPT_BEGIN_MARKER = "<<<ANTI_DRIP_CONTRACT_BEGIN>>>"
PROMPT_END_MARKER = "<<<ANTI_DRIP_CONTRACT_END>>>"
PROMPT_BLOCK_RE = re.compile(
    rf"(?ms)^{re.escape(PROMPT_BEGIN_MARKER)}\r?\n.*?\r?\n{re.escape(PROMPT_END_MARKER)}(?=\s|\Z)"
)
FORBIDDEN_PATHS = (
    r".gemini\antigravity-ide\scratch\ag-kit", r".openclaw\skills",
    r"C:\Users\GHC\.agents", r".codex\memories",
)
FORBIDDEN_SUFFIX = "non-authoritative scan evidence only; no reliance."
BASELINE_H2 = (
    "## Summary", "## Repo-Local Files Read", "## Changes Made",
    "## Verification", "## Forbidden Path Scan",
)
REMEDIATION_H2 = BASELINE_H2[:-1] + (ROOT_CAUSE_SWEEP_HEADING, BASELINE_H2[-1])
PLACEHOLDERS = tuple(re.compile(value, re.I) for value in (
    r"\[(?:placeholder|todo|passed/verified|absent\|not read)\]",
    r"\[(?:role_id|role_name|gate_name|l2_session_id|yyyymmdd)\]",
    r"\[(?:brief description|list every file|file path|what changed|test command|skill_name)[^\]]*\]",
    r"<(?:ROLE_ID|ROLE_NAME|GATE_NAME|L2_SESSION_ID|YYYY-MM-DD|CONTRACT_PATH|CONTRACT_SHA256|SOURCE_AUDIT_PATH|SOURCE_AUDIT_SHA256|FINDING_ID|ROOT_CAUSE|PROBE_STRING|SEARCH_REGEX|REPO_RELATIVE_PATH|TOTAL_MATCHES|CHANGED_MATCHES|NON_ACTIONABLE_MATCHES|NON_ACTIONABLE_JUSTIFICATIONS|PYTEST_NODE_ID|STATUS)>",
))

EXPECTED_ANTI_DRIP_DIRECTIVE_POINTS = (
    ("AD-1", "Consolidate every required finding ID from the contract; do not omit, rename, merge, or close any finding by assertion alone."),
    ("AD-2", "Trace each finding to one root cause and sweep every matching implementation pattern, call site, normalization path, read/write/list/delete symmetry, error branch, rollback branch, concurrency branch, and authorized parameter variant before editing."),
    ("AD-3", "Record every search regex, scanned path, total match count, changed match count, justified non-actionable match count, and unresolved_matches=0; a probe-specific or symptom-level single-line patch alone is forbidden."),
    ("AD-4", "Add adversarial fault-injection tests for every required finding and every affected error, rollback, durability, or concurrency branch; report exact pytest test node IDs."),
    ("AD-5", "Run pytest --collect-only for every reported node ID, then run focused tests and the full related suite; zero collection errors and zero test failures are required."),
    ("AD-6", "For remediation mode, write exactly one Root-Cause Architectural Sweep JSON object whose session, gate, mode, finding IDs, probe strings, and SHA match the contract; for baseline mode, write no Root-Cause Architectural Sweep; in both modes, never edit the contract, sidecar, or prompt artifacts."),
)

DIMENSION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["dimension", "name"],
    "properties": {"dimension": {"type": "integer", "minimum": 1, "maximum": 16},
                   "name": {"type": "string", "minLength": 1, "maxLength": 120}},
}
FINDING_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["finding_id", "severity", "title", "probe_strings"],
    "properties": {
        "finding_id": {"type": "string", "pattern": "^F-[0-9]{3}$"},
        "severity": {"enum": ["critical", "high", "medium", "low", None]},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "probe_strings": {"type": "array", "maxItems": 20, "uniqueItems": True,
                          "items": {"type": "string", "minLength": 1, "maxLength": 200}},
    },
}
SOURCE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["path", "sha256", "verdict", "timestamp", "cycle"],
    "properties": {
        "path": {"type": "string", "pattern": SOURCE_AUDIT_REL_RE.pattern},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "verdict": {"enum": ["APPROVED", "NEEDS_FIX"]},
        "timestamp": {"type": ["string", "null"], "maxLength": 40},
        "cycle": {"type": "integer", "minimum": 0, "maximum": 9999},
    },
}
DIRECTIVE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["version", "points"],
    "properties": {
        "version": {"const": "codex-anti-drip-6/v1"},
        "points": {"type": "array", "minItems": 6, "maxItems": 6, "uniqueItems": True,
                   "items": {"type": "object", "additionalProperties": False,
                             "required": ["id", "requirement"], "properties": {
                                 "id": {"type": "string", "pattern": "^AD-[1-6]$"},
                                 "requirement": {"type": "string", "minLength": 20, "maxLength": 1000}}}},
    },
}
ANTI_DRIP_CONTRACT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "contract_type", "session_id", "gate_name", "mode", "generated_at",
                 "source_audit", "required_findings", "passed_dimensions", "failed_dimensions", "directive"],
    "properties": {
        "schema_version": {"const": "anti-drip-contract/v1"},
        "contract_type": {"const": "ANTI_DRIP_PIPELINE_HARDENING"},
        "session_id": {"type": "string", "pattern": SESSION_ID_RE.pattern},
        "gate_name": {"type": "string", "pattern": SESSION_ID_RE.pattern},
        "mode": {"enum": ["baseline", "remediation"]},
        "generated_at": {"type": "string", "format": "date-time"},
        "source_audit": {"oneOf": [{"type": "null"}, SOURCE_SCHEMA]},
        "required_findings": {"type": "array", "maxItems": 100, "items": FINDING_SCHEMA},
        "passed_dimensions": {"type": "array", "maxItems": 16, "items": DIMENSION_SCHEMA},
        "failed_dimensions": {"type": "array", "maxItems": 16, "items": DIMENSION_SCHEMA},
        "directive": DIRECTIVE_SCHEMA,
    },
}

SEARCH_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["search_regex", "scanned_paths", "total_matches", "changed_matches",
                 "non_actionable_matches", "non_actionable_justifications", "unresolved_matches"],
    "properties": {
        "search_regex": {"type": "string", "minLength": 1, "maxLength": 500},
        "scanned_paths": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True,
                          "items": {"type": "string", "minLength": 1, "maxLength": 300}},
        "total_matches": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
        "changed_matches": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
        "non_actionable_matches": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
        "non_actionable_justifications": {"type": "array", "maxItems": 1000,
                                          "items": {"type": "string", "minLength": 1, "maxLength": 1000}},
        "unresolved_matches": {"type": "integer", "minimum": 0},
    },
}
NODE_ARRAY = {"type": "array", "maxItems": 500, "uniqueItems": True,
              "items": {"type": "string", "minLength": 1, "maxLength": 512}}
FINDING_SWEEP_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["finding_id", "root_cause", "probe_strings", "searches", "test_node_ids",
                 "fault_injection_test_node_ids", "unresolved_matches"],
    "properties": {
        "finding_id": {"type": "string", "pattern": "^F-[0-9]{3}$"},
        "root_cause": {"type": "string", "minLength": 20, "maxLength": 2000},
        "probe_strings": {"type": "array", "maxItems": 20, "uniqueItems": True,
                          "items": {"type": "string", "maxLength": 200}},
        "searches": {"type": "array", "maxItems": 100, "items": SEARCH_SCHEMA},
        "test_node_ids": NODE_ARRAY, "fault_injection_test_node_ids": NODE_ARRAY,
        "unresolved_matches": {"type": "integer", "minimum": 0},
    },
}
ROOT_CAUSE_SWEEP_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "session_id", "gate_name", "mode", "contract_path",
                 "contract_sha256", "source_audit_path", "source_audit_sha256", "finding_sweeps",
                 "pytest_node_ids", "fault_injection_test_node_ids", "unresolved_matches"],
    "properties": {
        "schema_version": {"const": "anti-drip-sweep/v1"},
        "session_id": {"type": "string", "pattern": SESSION_ID_RE.pattern},
        "gate_name": {"type": "string", "pattern": SESSION_ID_RE.pattern}, "mode": {"const": "remediation"},
        "contract_path": {"type": "string", "pattern": r"^\.ly_state/session/anti_drip_contract_[A-Za-z0-9_-]{1,128}\.json$"},
        "contract_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "source_audit_path": {"type": "string", "pattern": SOURCE_AUDIT_REL_RE.pattern},
        "source_audit_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "finding_sweeps": {"type": "array", "maxItems": 100, "items": FINDING_SWEEP_SCHEMA},
        "pytest_node_ids": NODE_ARRAY, "fault_injection_test_node_ids": NODE_ARRAY,
        "unresolved_matches": {"type": "integer", "minimum": 0},
    },
}


def _schema_errors(instance: object, schema: Mapping[str, Any], label: str) -> list[str]:
    if JSONSCHEMA_IMPORT_ERROR is not None:
        return ["ANTI_DRIP[E301] jsonschema dependency unavailable: install jsonschema>=4.18,<5"]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"ANTI_DRIP[E301] invalid internal {label} schema: {exc.message}"]
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
                    key=lambda item: (tuple(str(part) for part in item.absolute_path), item.message))
    result = []
    for error in errors:
        path = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
        result.append(f"ANTI_DRIP[E402] {label} schema violation at {path}: {error.message}")
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(data: str) -> object:
    return json.loads(data, object_pairs_hook=_reject_duplicate_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant: {value}")))


def _check_required_headings(content: str, *, remediation_required: bool = False) -> tuple[bool, list[str]]:
    if not content.splitlines() or not any(
        line.startswith("# ") and not line.startswith("## ") for line in content.splitlines()
    ):
        return False, ["Missing top-level header (# Header)"]
    expected = REMEDIATION_H2 if remediation_required else BASELINE_H2
    actual = tuple(line for line in content.splitlines() if line.startswith("## "))
    duplicates = sorted({heading for heading in actual if actual.count(heading) > 1})
    if duplicates:
        return False, [f"ANTI_DRIP[E203] duplicate H2 headings: {duplicates!r}"]
    unexpected = [heading for heading in actual if heading not in expected]
    if unexpected:
        return False, [f"ANTI_DRIP[E204] unexpected H2 headings: {unexpected!r}"]
    missing = [heading for heading in expected if heading not in actual]
    if missing:
        return False, [f"ANTI_DRIP[E201] missing H2 headings: {missing!r}"]
    if actual != expected:
        return False, [f"ANTI_DRIP[E202] H2 out of order: expected {expected!r}, got {actual!r}"]
    return True, []


def _check_unreplaced_placeholders(content: str) -> tuple[bool, list[str]]:
    errors = [f"Line {number}: placeholder in {line[:160]!r}" for number, line in enumerate(content.splitlines(), 1)
              if any(pattern.search(line) for pattern in PLACEHOLDERS)]
    return not errors, errors


def _check_report_filename(session_id: str) -> tuple[bool, str]:
    if SESSION_ID_RE.fullmatch(session_id) is None:
        return False, f"Path traversal or invalid session_id: {session_id!r}"
    if re.search(r"(?i)(?:^|_)retry\d*(?:_|$)", session_id) or not re.search(r"_20\d{6}$", session_id):
        return False, f"Filename/session date invariant failed: {session_id!r}"
    return True, "OK"


def _extract_root_cause_sweep(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    if content.splitlines().count(ROOT_CAUSE_SWEEP_HEADING) != 1:
        return None, ["ANTI_DRIP[E401] expected exactly one Root-Cause Architectural Sweep"]
    matches = list(ROOT_CAUSE_SWEEP_BLOCK_RE.finditer(content))
    if len(matches) != 1:
        return None, ["ANTI_DRIP[E401] sweep must contain exactly one immediate fenced JSON object"]
    try:
        payload = _strict_json(matches[0].group("payload"))
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [f"ANTI_DRIP[E401] invalid Root-Cause Architectural Sweep JSON: {exc}"]
    errors = _schema_errors(payload, ROOT_CAUSE_SWEEP_SCHEMA, "root-cause sweep")
    return (payload if isinstance(payload, dict) and not errors else None), errors


def _load_and_verify_anti_drip_contract(
    session_id: str, repo_root: Path
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    if SESSION_ID_RE.fullmatch(session_id) is None:
        return None, None, [f"ANTI_DRIP[E101] invalid session_id: {session_id!r}"]
    directory = repo_root / SESSION_REL
    contract_path = directory / f"anti_drip_contract_{session_id}.json"
    sidecar_path = directory / f"anti_drip_contract_{session_id}.sha256"
    if any(not path.exists() or path.is_symlink() or not path.is_file() for path in (contract_path, sidecar_path)):
        return None, None, ["ANTI_DRIP[E301] missing or unsafe anti-drip contract pair"]
    try:
        raw, sidecar = contract_path.read_bytes(), sidecar_path.read_bytes()
    except OSError as exc:
        return None, None, [f"ANTI_DRIP[E301] unable to read contract pair: {exc}"]
    digest = hashlib.sha256(raw).hexdigest()
    match = CONTRACT_SIDECAR_RE.fullmatch(sidecar)
    if match is None or match.group("sha").decode() != digest or match.group("name").decode() != contract_path.name:
        return None, None, ["ANTI_DRIP[E302] contract and sidecar SHA-256 binding mismatch"]
    try:
        payload = _strict_json(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return None, None, [f"ANTI_DRIP[E301] invalid contract JSON: {exc}"]
    errors = _schema_errors(payload, ANTI_DRIP_CONTRACT_SCHEMA, "contract")
    if errors or not isinstance(payload, dict):
        return None, None, errors
    if payload["session_id"] != session_id:
        return None, None, ["ANTI_DRIP[E303] contract session_id mismatch"]
    mode, source = payload["mode"], payload["source_audit"]
    if mode == "baseline" and (payload["required_findings"] or payload["failed_dimensions"] or
                               (source is not None and source["verdict"] != "APPROVED")):
        return None, None, ["ANTI_DRIP[E304] baseline contract semantics invalid"]
    if mode == "remediation" and (not payload["required_findings"] or not payload["failed_dimensions"] or
                                  source is None or source["verdict"] != "NEEDS_FIX"):
        return None, None, ["ANTI_DRIP[E304] remediation contract semantics invalid"]
    if source is not None:
        source_path = repo_root / PurePosixPath(source["path"])
        audit_root = (repo_root / AUDIT_REPORTS_REL).resolve()
        if (source_path.is_symlink() or not source_path.is_file() or
                not source_path.resolve().is_relative_to(audit_root)):
            return None, None, ["ANTI_DRIP[E301] source audit is missing or unsafe"]
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
            return None, None, ["ANTI_DRIP[E302] source audit SHA-256 mismatch"]
    return payload, digest, []


def _canonical_prompt_block(session_id: str, contract: Mapping[str, Any], digest: str) -> str:
    findings = json.dumps(contract["required_findings"], ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    lines = [PROMPT_BEGIN_MARKER,
             f"ANTI_DRIP_CONTRACT_PATH=.ly_state/session/anti_drip_contract_{session_id}.json",
             f"ANTI_DRIP_CONTRACT_SHA256={digest}", f"ANTI_DRIP_SESSION_ID={session_id}",
             f"ANTI_DRIP_GATE_NAME={contract['gate_name']}", f"ANTI_DRIP_MODE={contract['mode']}",
             f"ANTI_DRIP_REQUIRED_FINDINGS={findings}", "CODEX_ANTI_DRIP_DIRECTIVE_VERSION=codex-anti-drip-6/v1",
             *(f"({key}) {value}" for key, value in EXPECTED_ANTI_DRIP_DIRECTIVE_POINTS), PROMPT_END_MARKER]
    return "\n".join(lines)


def _load_and_verify_prompt_binding(
    session_id: str, repo_root: Path, contract: Mapping[str, Any], digest: str
) -> list[str]:
    path = repo_root / SESSION_REL / f"prompt_{session_id}.txt"
    if not path.exists():
        return [f"ANTI_DRIP[E305] prompt file not found: {path.relative_to(repo_root).as_posix()}"]
    if path.is_symlink() or not path.is_file():
        return ["ANTI_DRIP[E306] prompt must be regular non-symlink file"]
    if path.resolve().parent != (repo_root / SESSION_REL).resolve():
        return ["ANTI_DRIP[E307] prompt artifact escapes session directory"]
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise UnicodeError("UTF-8 BOM")
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return [f"ANTI_DRIP[E308] prompt must be BOM-free strict UTF-8: {exc}"]
    begin, end = text.splitlines().count(PROMPT_BEGIN_MARKER), text.splitlines().count(PROMPT_END_MARKER)
    if begin != 1:
        return [f"ANTI_DRIP[E309] expected exactly one prompt begin marker, got {begin}"]
    if end != 1:
        return [f"ANTI_DRIP[E310] expected exactly one prompt end marker, got {end}"]
    matches = list(PROMPT_BLOCK_RE.finditer(text))
    if len(matches) != 1:
        return [f"ANTI_DRIP[E311] expected exactly one complete anti-drip prompt block, got {len(matches)}"]
    block = matches[0].group(0)
    expected = _canonical_prompt_block(session_id, contract, digest)
    if "\r" in block or block != expected:
        scalar_markers = {
            "SHA-256": f"ANTI_DRIP_CONTRACT_SHA256={digest}", "session": f"ANTI_DRIP_SESSION_ID={session_id}",
            "gate": f"ANTI_DRIP_GATE_NAME={contract['gate_name']}", "mode": f"ANTI_DRIP_MODE={contract['mode']}",
        }
        for label, marker in scalar_markers.items():
            if block.splitlines().count(marker) != 1:
                return [f"ANTI_DRIP[{'E302' if label == 'SHA-256' else 'E303' if label in ('session', 'gate') else 'E304'}] prompt {label} mismatch"]
        return ["ANTI_DRIP[E319] prompt block differs from canonical expected block"]
    points = contract["directive"]["points"]
    expected_points = [{"id": key, "requirement": value} for key, value in EXPECTED_ANTI_DRIP_DIRECTIVE_POINTS]
    if points != expected_points:
        return ["ANTI_DRIP[E318] contract directive does not match codex-anti-drip-6/v1"]
    return []


def _extract_report_binding(content: str) -> tuple[dict[str, str] | None, list[str]]:
    specs = (("gate_name", REPORT_GATE_RE), ("session_id", REPORT_SESSION_RE), ("mode", REPORT_MODE_RE),
             ("contract_path", REPORT_CONTRACT_RE), ("contract_sha256", REPORT_SHA_RE))
    values: dict[str, str] = {}
    for name, pattern in specs:
        matches = list(pattern.finditer(content))
        if len(matches) != 1:
            return None, [f"ANTI_DRIP[E303] expected exactly one report {name} metadata line, got {len(matches)}"]
        values[name] = matches[0].group("value")
    return values, []


def _validate_repo_relative_posix_path(value: str, repo_root: Path) -> str | None:
    if not isinstance(value, str) or WINDOWS_DRIVE_RE.match(value) or value.startswith(("/", "\\")) or "\\" in value or "\x00" in value:
        return f"absolute or non-POSIX path forbidden: {value!r}"
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return f"path traversal component forbidden: {value!r}"
    if not repo_root.joinpath(*parts).resolve().is_relative_to(repo_root.resolve()):
        return f"path escapes repo root: {value!r}"
    return None


def _dangerous_regex(value: str) -> bool:
    return bool(re.search(r"\((?:\.\*|\.\+|[^)]*[+*][^)]*)\)[+*]", value))


def _validate_finding_sweep_coverage(contract: Mapping[str, Any], sweep: Mapping[str, Any], repo_root: Path) -> list[str]:
    expected = contract["required_findings"]
    actual = sweep["finding_sweeps"]
    if [item["finding_id"] for item in actual] != [item["finding_id"] for item in expected]:
        return ["ANTI_DRIP[E501] finding ID coverage mismatch"]
    tests: list[str] = []
    faults: list[str] = []
    for contract_finding, finding in zip(expected, actual, strict=True):
        finding_id = finding["finding_id"]
        probes = finding["probe_strings"]
        if (contract_finding["probe_strings"] and not probes) or any(not probe.strip() for probe in probes) or probes != contract_finding["probe_strings"]:
            return [f"ANTI_DRIP[E502] probe coverage mismatch for {finding_id}"]
        compiled = []
        for search in finding["searches"]:
            try:
                if _dangerous_regex(search["search_regex"]):
                    raise re.error("nested quantifier forbidden")
                compiled.append(re.compile(search["search_regex"]))
            except re.error as exc:
                return [f"ANTI_DRIP[E503] invalid or unsafe search regex for {finding_id}: {exc}"]
            for path in search["scanned_paths"]:
                reason = _validate_repo_relative_posix_path(path, repo_root)
                if reason:
                    return [f"ANTI_DRIP[E503] invalid scanned path for {finding_id}: {reason}"]
            if search["total_matches"] != search["changed_matches"] + search["non_actionable_matches"] + search["unresolved_matches"]:
                return [f"ANTI_DRIP[E403] search accounting mismatch for {finding_id}"]
            if len(search["non_actionable_justifications"]) != search["non_actionable_matches"]:
                return [f"ANTI_DRIP[E403] non-actionable accounting mismatch for {finding_id}"]
            if search["unresolved_matches"] != 0:
                return ["ANTI_DRIP[E504] unresolved_matches must equal zero at every level"]
        if not finding["searches"] or any(not any(pattern.search(probe) for pattern in compiled) for probe in probes):
            return [f"ANTI_DRIP[E502] contract probe is not covered for {finding_id}"]
        if finding["unresolved_matches"] != 0 or sweep["unresolved_matches"] != 0:
            return ["ANTI_DRIP[E504] unresolved_matches must equal zero at every level"]
        finding_tests, finding_faults = finding["test_node_ids"], finding["fault_injection_test_node_ids"]
        if not finding_tests:
            return ["ANTI_DRIP[E601] remediation finding requires pytest node IDs"]
        if contract_finding["severity"] in {"critical", "high"} and not finding_faults:
            return [f"ANTI_DRIP[E602] {finding_id} requires fault-injection test node ID"]
        if not set(finding_faults).issubset(finding_tests):
            return [f"ANTI_DRIP[E602] fault-injection nodes must be finding test nodes for {finding_id}"]
        tests.extend(finding_tests)
        faults.extend(finding_faults)
    if sweep["pytest_node_ids"] != list(dict.fromkeys(tests)) or sweep["fault_injection_test_node_ids"] != list(dict.fromkeys(faults)):
        return ["ANTI_DRIP[E601] top-level pytest node IDs do not match finding unions"]
    return []


def _validate_pytest_node_id(node_id: str, repo_root: Path) -> str | None:
    if not isinstance(node_id, str) or not 1 <= len(node_id) <= 512 or SHELL_METACHAR_RE.search(node_id):
        return f"ANTI_DRIP[E603] invalid or unsafe pytest node ID: {node_id!r}"
    if WINDOWS_DRIVE_RE.match(node_id) or node_id.startswith(("/", "\\")) or PYTEST_NODE_ID_RE.fullmatch(node_id) is None:
        return f"ANTI_DRIP[E603] invalid pytest node ID shape: {node_id!r}"
    file_part = node_id.split("::", 1)[0]
    path = PurePosixPath(file_part)
    if path.parts[0] != "tests" or any(part in {"", ".", ".."} for part in path.parts):
        return f"ANTI_DRIP[E603] pytest path traversal forbidden: {node_id!r}"
    test_path = repo_root.joinpath(*path.parts)
    if test_path.is_symlink() or not test_path.is_file() or not test_path.resolve().is_relative_to(repo_root.resolve()):
        return f"ANTI_DRIP[E603] pytest test file is not a safe regular file: {file_part!r}"
    return None


def _collect_pytest_node_ids(
    node_ids: Sequence[str], repo_root: Path, timeout_seconds: int = 60
) -> tuple[bool, list[str]]:
    if not node_ids or len(node_ids) != len(set(node_ids)):
        return False, ["ANTI_DRIP[E603] pytest node IDs must be non-empty and unique"]
    errors = [error for node_id in node_ids if (error := _validate_pytest_node_id(node_id, repo_root))]
    if errors:
        return False, errors
    try:
        completed = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-o", "addopts=", "-q", *node_ids],
                                   cwd=repo_root, shell=False, capture_output=True, text=True,
                                   timeout=timeout_seconds, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, [f"ANTI_DRIP[E603] pytest collection failed: {exc}"]
    lines = {line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}
    missing = [node_id for node_id in node_ids if node_id not in lines]
    if completed.returncode != 0 or missing:
        detail = " | ".join(line.strip() for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip())[:2000]
        return False, [f"ANTI_DRIP[E603] pytest collection failed or omitted nodes: {missing!r}; {detail}"]
    return True, []


def _validate_envelope(content: str, session_id: str, role_id: int, role_name: str, remediation: bool) -> list[str]:
    lines = content.splitlines()
    if len(lines) < 11 or lines[0] != "# L2 Implementation Report" or lines.count("# L2 Implementation Report") != 1:
        return ["ANTI_DRIP[E201] invalid L2 report H1"]
    ok, errors = _check_required_headings(content, remediation_required=remediation)
    if not ok:
        return errors
    placeholder_ok, placeholder_errors = _check_unreplaced_placeholders(content)
    if not placeholder_ok:
        return [f"ANTI_DRIP[E201] {error}" for error in placeholder_errors]
    forbidden_index = lines.index("## Forbidden Path Scan")
    body = [line for line in lines[forbidden_index + 1:] if line]
    expected = [f"- `{path}`: not read; {FORBIDDEN_SUFFIX}" for path in FORBIDDEN_PATHS]
    alternate = [f"- `{path}`: absent; {FORBIDDEN_SUFFIX}" for path in FORBIDDEN_PATHS]
    if len(body) != 4 or any(body[index] not in (expected[index], alternate[index]) for index in range(4)):
        return ["ANTI_DRIP[E703] Forbidden Path Scan requires four canonical ordered lines"]
    violations, found = validate_forbidden_path_usage(content)
    if violations:
        return [f"ANTI_DRIP[E704] authoritative forbidden path reliance detected: {found[0]}"]
    role_line = f"- **Role**: {role_id} {role_name} - OpenCode L2 Implementation"
    if role_line not in lines[:10]:
        return ["ANTI_DRIP[E303] report role metadata mismatch"]
    suffix = re.search(r"_(20\d{6})$", session_id)
    date_line = next((line for line in lines[:10] if line.startswith("- **Date**: ")), "")
    try:
        expected_date = datetime.strptime(suffix.group(1), "%Y%m%d").strftime("%Y-%m-%d") if suffix else None
    except ValueError:
        expected_date = None
    if expected_date is None or date_line != f"- **Date**: `{expected_date}`":
        return ["ANTI_DRIP[E303] report date/session suffix mismatch"]
    valid, message = _validate_l2_report_content(content, role_id, role_name)
    return [] if valid else [f"ANTI_DRIP[E704] repo-local role/skill evidence invalid: {message}"]


def validate_anti_drip_report(
    session_id: str, report_content: str, repo_root: Path, *, collect_timeout_seconds: int = 60
) -> tuple[str | None, list[str]]:
    root = repo_root.resolve()
    contract, digest, errors = _load_and_verify_anti_drip_contract(session_id, root)
    if errors:
        return None, errors
    assert contract is not None and digest is not None
    errors = _load_and_verify_prompt_binding(session_id, root, contract, digest)
    if errors:
        return None, errors
    binding, errors = _extract_report_binding(report_content)
    if errors:
        return None, errors
    assert binding is not None
    expected_path = f".ly_state/session/anti_drip_contract_{session_id}.json"
    if binding["contract_sha256"] != digest:
        return None, ["ANTI_DRIP[E302] report contract SHA-256 mismatch"]
    if binding["session_id"] != session_id or binding["gate_name"] != contract["gate_name"] or binding["contract_path"] != expected_path:
        return None, ["ANTI_DRIP[E303] report session, gate, or contract path mismatch"]
    if binding["mode"] != contract["mode"]:
        return None, ["ANTI_DRIP[E304] report mode mismatch"]
    mode = contract["mode"]
    if mode == "baseline":
        if ROOT_CAUSE_SWEEP_HEADING in report_content:
            return None, ["ANTI_DRIP[E304] baseline report must not contain Root-Cause Architectural Sweep"]
    else:
        sweep, errors = _extract_root_cause_sweep(report_content)
        if errors:
            return None, errors
        assert sweep is not None
        source = contract["source_audit"]
        if sweep["contract_sha256"] != digest or sweep["source_audit_sha256"] != source["sha256"]:
            return None, ["ANTI_DRIP[E302] sweep SHA-256 binding mismatch"]
        if sweep["session_id"] != session_id or sweep["gate_name"] != contract["gate_name"] or sweep["contract_path"] != expected_path or sweep["source_audit_path"] != source["path"]:
            return None, ["ANTI_DRIP[E303] sweep identity/path mismatch"]
        if sweep["mode"] != mode:
            return None, ["ANTI_DRIP[E304] sweep mode mismatch"]
        errors = _validate_finding_sweep_coverage(contract, sweep, root)
        if errors:
            return None, errors
        collected, errors = _collect_pytest_node_ids(sweep["pytest_node_ids"], root, collect_timeout_seconds)
        if not collected:
            return None, errors
    role_match = re.search(r"(?m)^- \*\*Role\*\*: (?P<id>\d{1,2}) (?P<name>[a-z][a-z0-9-]*) - OpenCode L2 Implementation$", report_content)
    if not role_match:
        return None, ["ANTI_DRIP[E303] missing canonical report role metadata"]
    errors = _validate_envelope(report_content, session_id, int(role_match.group("id")), role_match.group("name"), mode == "remediation")
    return (mode, []) if not errors else (None, errors)


def _emit_failures(errors: Sequence[str], *, fatal: bool = False) -> None:
    prefix = "ERROR" if fatal else "FAIL"
    for error in errors:
        print(f"[{prefix}] {error}")
    print(("RESULT: [ERROR]" if fatal else "RESULT: [NEEDS_FIX]") + f" - {len(errors)} issue(s); do not dispatch L3.")


def main(argv: Sequence[str] | None = None, repo_root: Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    collect_timeout = 60
    pos_args: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--collect-timeout", "--timeout"):
            if i + 1 >= len(args):
                _emit_failures(["ANTI_DRIP[E101] missing value for timeout option"], fatal=True)
                return 2
            try:
                collect_timeout = int(args[i + 1])
                if collect_timeout <= 0:
                    raise ValueError
            except ValueError:
                _emit_failures(["ANTI_DRIP[E101] timeout must be a positive integer"], fatal=True)
                return 2
            i += 2
        elif arg.startswith(("--collect-timeout=", "--timeout=")):
            try:
                collect_timeout = int(arg.split("=", 1)[1])
                if collect_timeout <= 0:
                    raise ValueError
            except ValueError:
                _emit_failures(["ANTI_DRIP[E101] timeout must be a positive integer"], fatal=True)
                return 2
            i += 1
        elif arg.startswith("-"):
            _emit_failures([f"ANTI_DRIP[E101] unrecognized option: {arg!r}"], fatal=True)
            return 2
        else:
            pos_args.append(arg)
            i += 1

    if len(pos_args) != 3:
        _emit_failures(["ANTI_DRIP[E101] usage: python scripts/validate_l2_report.py <session_id> <role_id> <role_name> [--collect-timeout <seconds>]"], fatal=True)
        return 2
    session_id, role_text, role_name = pos_args
    if SESSION_ID_RE.fullmatch(session_id) is None:
        _emit_failures([f"ANTI_DRIP[E101] invalid session_id: {session_id!r}"], fatal=True)
        return 2
    try:
        role_id = int(role_text)
    except ValueError:
        role_id = -1
    if not 6 <= role_id <= 16 or CLI_ROLE_NAME_RE.fullmatch(role_name) is None:
        _emit_failures(["ANTI_DRIP[E101] invalid L2 role arguments"], fatal=True)
        return 2
    root = (repo_root or REPO_ROOT).resolve()
    report_path = root / SESSION_REL / f"{session_id}.md"
    if not report_path.exists() or report_path.is_symlink() or not report_path.is_file():
        _emit_failures(["ANTI_DRIP[E102] L2 report missing or not a regular non-symlink file"])
        return 1
    try:
        raw = report_path.read_bytes()
        content = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        _emit_failures([f"ANTI_DRIP[E103] unable to read report as strict UTF-8: {exc}"])
        return 1
    if len(raw) < MIN_REPORT_BYTES:
        _emit_failures([f"ANTI_DRIP[E104] report is smaller than {MIN_REPORT_BYTES} bytes"])
        return 1
    mode, errors = validate_anti_drip_report(session_id, content, root, collect_timeout_seconds=collect_timeout)
    if errors:
        _emit_failures(errors)
        return 1
    role_match = re.search(r"(?m)^- \*\*Role\*\*: (\d{1,2}) ([a-z][a-z0-9-]*) - OpenCode L2 Implementation$", content)
    if role_match is None or (int(role_match.group(1)), role_match.group(2)) != (role_id, role_name):
        _emit_failures(["ANTI_DRIP[E303] report Role metadata does not match CLI role"])
        return 1
    binding, _ = _extract_report_binding(content)
    valid, message = validate_l2_role(role_id, role_name, load_role_specs(), gate_name=binding["gate_name"])
    if not valid:
        _emit_failures([f"ANTI_DRIP[E303] L2 role/spec validation failed: {message}"])
        return 1
    print(f"RESULT: [PASS] - anti-drip L2 report validated; session={session_id}; role={role_id} {role_name}; mode={mode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
