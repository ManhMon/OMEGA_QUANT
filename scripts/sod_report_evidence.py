"""Shared SoD report wording validator.

The validator is pure so the enforcer and lint CLI cannot drift.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

CANONICAL_REPORT_EVIDENCE_CUTOFF = date(2026, 7, 25)
CANONICAL_FORBIDDEN_LINE = "non-authoritative scan evidence only; no reliance."
FORBIDDEN_PATHS = (
    r".gemini\antigravity-ide\scratch\ag-kit",
    r".openclaw\skills",
    r"C:\Users\GHC\.agents",
    r".codex\memories",
)
CANONICAL_HEADINGS = ("## Repo-Local Files Read", "## Forbidden Path Scan")
FORBIDDEN_WORDING = (
    "not referenced",
    "reported absent by l2",
    "no authoritative role/skill source read from",
)
_DATE_TOKEN = re.compile(r"(?<![0-9])([0-9]{8})(?![0-9])")
_DATE_SUFFIX = re.compile(r"(?:^|[^0-9])([0-9]{8})(?:\.md)?$")


def _suffix_date(value: str | Path | None) -> date | None:
    if not value:
        return None


def _filename_date(value: str | Path | None) -> tuple[date | None, str | None]:
    if not value:
        return None, None
    name = Path(str(value)).name
    tokens = _DATE_TOKEN.findall(name)
    if len(tokens) > 1:
        return None, "multiple YYYYMMDD selectors"
    match = _DATE_SUFFIX.search(name)
    if not match:
        if re.search(r"(?:^|[^0-9])[0-9A-Za-z]{8}(?:\.md)?$", name):
            return None, "malformed YYYYMMDD selector"
        return None, None
    try:
        return date(int(match.group(1)[:4]), int(match.group(1)[4:6]), int(match.group(1)[6:])), None
    except ValueError:
        return None, "malformed YYYYMMDD selector"
    match = _DATE_SUFFIX.search(Path(str(value)).name)
    if not match:
        return None
    try:
        return date(int(match.group(1)[:4]), int(match.group(1)[4:6]), int(match.group(1)[6:]))
    except ValueError:
        return None


def canonical_mode(gate_name: str | None, report_filename: str | None) -> tuple[bool, str]:
    gate_date, gate_error = _filename_date(gate_name)
    report_date, report_error = _filename_date(report_filename)
    if gate_error or report_error:
        return False, gate_error or report_error
    if gate_date is None or report_date is None:
        return False, "missing gate/report YYYYMMDD selector"
    if report_date < gate_date:
        return False, "report YYYYMMDD selector predates gate selector"
    return gate_date >= CANONICAL_REPORT_EVIDENCE_CUTOFF, "ok"


def _resolved_mode(resolved_gate_date: date, report_filename: str | None) -> tuple[bool, str]:
    report_date, report_error = _filename_date(report_filename)
    if report_error:
        return False, report_error
    if resolved_gate_date is None:
        return False, "resolved gate date is missing"
    canonical = resolved_gate_date >= CANONICAL_REPORT_EVIDENCE_CUTOFF
    if canonical and report_date is None:
        return False, "canonical report requires YYYYMMDD selector"
    if report_date is not None and report_date < resolved_gate_date:
        return False, "report YYYYMMDD selector predates resolved gate date"
    return canonical, "ok"


def _legacy_validate(text: str) -> list[str]:
    errors = []
    lowered = text.lower()
    if not any(marker in lowered for marker in ("repo-local", "repo_local", "repo_agent_root", ".agents/agent", ".agents\\agent")):
        errors.append("missing repo-local role source evidence")
    if not any(marker in lowered for marker in ("repo-local skill", "repo_skill_root", ".agents/skills", ".agents\\skills")):
        errors.append("missing repo-local skill source evidence")
    return errors


def _canonical_validate(text: str) -> list[str]:
    errors = [f"missing heading: {heading}" for heading in CANONICAL_HEADINGS if heading not in text]
    lowered = text.lower()
    for phrase in FORBIDDEN_WORDING:
        if phrase in lowered:
            errors.append(f"forbidden wording: {phrase}")
    lines = text.splitlines()
    for path in FORBIDDEN_PATHS:
        variants = {path.lower(), path.replace("\\", "/").lower()}
        matches = [line for line in lines if any(item in line.lower() for item in variants)]
        if not matches:
            errors.append(f"missing forbidden-path scan line: {path}")
            continue
        for line in matches:
            if sum(line.lower().count(item) for item in variants) != 1 or CANONICAL_FORBIDDEN_LINE not in line.lower():
                errors.append(f"invalid forbidden-path scan line: {path}")
    if "REPO_AGENT_ROOT" not in text or "REPO_SKILL_ROOT" not in text:
        errors.append("missing repo-local source roots")
    return errors


def validate_report_evidence(
    text: str | None,
    *,
    gate_name: str | None = None,
    report_filename: str | None = None,
    strict: bool | None = None,
    resolved_gate_date: date | None = None,
) -> tuple[bool, list[str], bool]:
    """Return ``(valid, errors, canonical)``; canonical selectors fail closed."""
    if not text:
        return False, ["report content is empty"], bool(strict)
    if resolved_gate_date is not None:
        canonical, selector_error = _resolved_mode(resolved_gate_date, report_filename)
        if selector_error != "ok":
            return False, [selector_error], False
    elif strict is None:
        canonical, selector_error = canonical_mode(gate_name, report_filename)
        if selector_error != "ok":
            return False, [selector_error], False
    else:
        canonical = strict
    errors = _canonical_validate(text) if canonical else _legacy_validate(text)
    return not errors, errors, canonical


def validate_forbidden_scan(text: str | None, *, strict: bool = True) -> tuple[bool, list[str]]:
    """Validate only forbidden-path wording for lint and enforcer callers."""
    if not text:
        return False, ["report content is empty"]
    errors = _canonical_validate(text) if strict else []
    return not errors, errors
