#!/usr/bin/env python3
"""
validate_l2_report.py - Pre-L3 validation of L2 report format.

Run this immediately after L2 session completes, before dispatching L3.
Catches format errors cheaply, avoiding expensive L3 retry cycles.

Usage:
    python scripts/validate_l2_report.py <l2_session_id> [role_id] [role_name]

Example:
    python scripts/validate_l2_report.py l2_role15_synthetic_fixtures_macro_news_v12_20260814 15 data-engineer

Exit codes:
    0 = PASS (safe to dispatch L3)
    1 = FAIL (fix L2 report before dispatching L3)
"""
import sys
import re
from pathlib import Path

# Add scripts dir to path so we can import enforcer functions
sys.path.insert(0, str(Path(__file__).parent))

from sod_gate_enforcer import (
    check_l2_report_skill_sources,
    validate_forbidden_path_usage,
    _validate_l2_report_content,
    check_report_evidence_wording,
)

FORBIDDEN_PATHS = [
    r".gemini\antigravity-ide\scratch\ag-kit",
    r".openclaw\skills",
    r"C:\Users\GHC\.agents",
    r".codex\memories",
]

REQUIRED_FORBIDDEN_SUFFIX = "non-authoritative scan evidence only; no reliance."


def _check_forbidden_scan_wording(content: str) -> tuple[bool, list[str]]:
    """Each forbidden path mention must end with exact required suffix."""
    errors = []
    for fp in FORBIDDEN_PATHS:
        pattern = re.escape(fp)
        for line in content.splitlines():
            if re.search(pattern, line, re.IGNORECASE):
                if not line.rstrip().endswith(REQUIRED_FORBIDDEN_SUFFIX):
                    errors.append(
                        f"  Line missing required suffix:\n"
                        f"    Found:    {line.strip()!r}\n"
                        f"    Must end: {REQUIRED_FORBIDDEN_SUFFIX!r}"
                    )
    return (len(errors) == 0), errors


def _check_report_filename(session_id: str) -> tuple[bool, str]:
    """Report must end with _YYYYMMDD.md (no _retry suffix)."""
    report_path = Path(f".ly_state/session/{session_id}.md")
    filename = report_path.name
    if re.search(r"_retry\d*\.md$", filename):
        return False, f"Filename has _retry suffix: {filename!r} — must end with _YYYYMMDD.md"
    if not re.search(r"_\d{8}\.md$", filename):
        return False, f"Filename missing YYYYMMDD date suffix: {filename!r}"
    return True, "OK"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_l2_report.py <l2_session_id> [role_id] [role_name]")
        sys.exit(1)

    session_id = sys.argv[1]
    role_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    role_name = sys.argv[3] if len(sys.argv) > 3 else None

    report_path = Path(f".ly_state/session/{session_id}.md")
    failures = []
    passes = []

    print(f"\n{'='*60}")
    print(f"L2 Report Pre-Validation: {session_id}")
    print(f"{'='*60}")

    # 1. File exists
    if not report_path.exists():
        print(f"[FAIL] Report file not found: {report_path}")
        sys.exit(1)

    content = report_path.read_text(encoding="utf-8")

    # 2. Filename format
    ok, msg = _check_report_filename(session_id)
    if ok:
        passes.append("Filename format (YYYYMMDD suffix)")
    else:
        failures.append(f"Filename: {msg}")

    # 3. Repo-local skill sources heading + content
    ok, msg = check_l2_report_skill_sources(str(report_path), role_id, role_name)
    if ok:
        passes.append("Repo-local skill sources (## Repo-Local Files Read)")
    else:
        failures.append(f"Skill sources: {msg}")

    # 4. Forbidden path scan wording
    ok, errors = _check_forbidden_scan_wording(content)
    if ok:
        passes.append("Forbidden path scan wording")
    else:
        failures.append(f"Forbidden path wording:\n" + "\n".join(errors))

    # 5. No authoritative forbidden path usage
    # validate_forbidden_path_usage returns (has_violations, matches) — False = no violations = PASS
    has_violations, found = validate_forbidden_path_usage(content)
    if not has_violations:
        passes.append("No authoritative forbidden path usage")
    else:
        failures.append(f"Forbidden path authoritative usage detected: {found}")

    # Summary
    print()
    for p in passes:
        print(f"  [PASS] {p}")
    for f in failures:
        print(f"  [FAIL] {f}")

    print()
    if failures:
        print(f"RESULT: [NEEDS_FIX] — {len(failures)} issue(s). Fix before dispatching L3.")
        sys.exit(1)
    else:
        print(f"RESULT: [PASS] — Safe to dispatch L3 audit.")
        sys.exit(0)


if __name__ == "__main__":
    main()
