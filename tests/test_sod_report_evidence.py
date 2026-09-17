import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from sod_report_evidence import validate_report_evidence


def report(scan_lines: str) -> str:
    return """# Report
## Repo-Local Files Read
- REPO_AGENT_ROOT/.agents/agent/backend-engineer.md
- REPO_SKILL_ROOT/.agents/skills/clean-code/SKILL.md
## Forbidden Path Scan
""" + scan_lines


def test_canonical_report_requires_exact_scan_lines():
    text = report("".join(
        f"- {path}: non-authoritative scan evidence only; no reliance.\n"
        for path in (
            r".gemini\antigravity-ide\scratch\ag-kit",
            r".openclaw\skills",
            r"C:\Users\GHC\.agents",
            r".codex\memories",
        )
    ))
    valid, errors, canonical = validate_report_evidence(
        text, gate_name="gate_20260725", report_filename="role21_gate_20260725.md"
    )
    assert (valid, errors, canonical) == (True, [], True)


def test_forbidden_wording_fails_canonical_mode():
    text = report("- .openclaw\\skills: reported absent by L2\n")
    valid, errors, canonical = validate_report_evidence(
        text, gate_name="gate_20260725", report_filename="role21_gate_20260725.md"
    )
    assert not valid
    assert canonical
    assert any("forbidden wording" in error for error in errors)


def test_missing_or_contradictory_selectors_fail_closed():
    text = "## Repo-Local Files Read\n## Forbidden Path Scan\n"
    assert not validate_report_evidence(text, gate_name="gate", report_filename="x.md")[0]
    assert not validate_report_evidence(
        text, gate_name="gate_20260725", report_filename="x_20260724.md"
    )[0]


def test_historic_gate_accepts_newer_reaudit_report_in_legacy_mode():
    valid, errors, canonical = validate_report_evidence(
        "repo-local role source; repo-local skill source",
        gate_name="gate_20260724",
        report_filename="role21_gate_20260726.md",
    )
    assert (valid, errors, canonical) == (True, [], False)


def test_malformed_selectors_fail_closed():
    text = "repo-local role source; repo-local skill source"
    for gate_name, report_filename in (
        ("gate_202607xx", "role21_gate_20260726.md"),
        ("gate_20260726", "role21_gate_202607xx.md"),
        ("gate_20261340", "role21_gate_20260726.md"),
    ):
        valid, errors, _ = validate_report_evidence(
            text, gate_name=gate_name, report_filename=report_filename
        )
        assert not valid
        assert errors


def test_pre_cutoff_uses_legacy_mode():
    valid, errors, canonical = validate_report_evidence(
        "repo-local role source; repo-local skill source",
        gate_name="gate_20260724",
        report_filename="role21_gate_20260724.md",
    )
    assert (valid, errors, canonical) == (True, [], False)


def test_explicit_resolved_date_supports_undated_legacy_filename():
    valid, errors, canonical = validate_report_evidence(
        "repo-local role source; repo-local skill source",
        report_filename="role21_legacy.md",
        resolved_gate_date=date(2026, 7, 24),
    )
    assert (valid, errors, canonical) == (True, [], False)


def test_explicit_resolved_date_requires_canonical_evidence_after_cutoff():
    valid, errors, canonical = validate_report_evidence(
        "repo-local role source; repo-local skill source",
        report_filename="role21_gate_20260726.md",
        resolved_gate_date=date(2026, 7, 26),
    )
    assert not valid
    assert canonical
    assert errors


def test_filename_selector_matrix():
    text = "repo-local role source; repo-local skill source"
    for filename in ("role21_legacy.md", "role21_gate_20260724.md"):
        valid, errors, canonical = validate_report_evidence(
            text, report_filename=filename, resolved_gate_date=date(2026, 7, 24)
        )
        assert (valid, errors, canonical) == (True, [], False)
    for filename in ("role21_gate_20260723.md", "role21_gate_20260724_20260725.md", "role21_gate_202607xx.md"):
        valid, errors, _ = validate_report_evidence(
            text, report_filename=filename, resolved_gate_date=date(2026, 7, 24)
        )
        assert not valid
        assert errors


def test_strict_mode_remains_backward_compatible():
    text = "repo-local role source; repo-local skill source"
    assert validate_report_evidence(text, strict=False) == (True, [], False)
    assert not validate_report_evidence(text, strict=True)[0]
