import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sod_gate_enforcer


def test_main_has_zero_lesson_artifact_access(monkeypatch):
    calls = []

    monkeypatch.setattr(sod_gate_enforcer, "check_sod_compliance", lambda: calls.append("check") or True)

    with pytest.raises(SystemExit) as exc_info:
        sod_gate_enforcer.main([])

    assert exc_info.value.code == 0
    assert calls == ["check"]
    assert not hasattr(sod_gate_enforcer, "extract_lessons")


def test_enforcer_accepts_current_reaudit_for_historic_gate():
    valid, message = sod_gate_enforcer.check_report_evidence_wording(
        "ALPHA_WEAKNESS_DIAGNOSTICS_20260614",
        ".ly_state/session/l2_role14_alpha_weakness_diagnostics_fix6_20260726.md",
    )
    assert valid
    assert message == "legacy report evidence valid"


def test_enforcer_rejects_malformed_gate_selector():
    valid, message = sod_gate_enforcer.check_report_evidence_wording(
        "ALPHA_WEAKNESS_DIAGNOSTICS_202607xx",
        ".ly_state/session/l2_role14_alpha_weakness_diagnostics_fix6_20260726.md",
    )
    assert not valid
    assert "malformed gate YYYYMMDD selector" in message


def test_resolve_gate_date_reconciles_key_and_timestamp():
    resolved, error = sod_gate_enforcer.resolve_gate_date(
        {"timestamp": "2026-07-26T00:30:00+07:00"}, "GATE_20260726"
    )
    assert (resolved.isoformat(), error) == ("2026-07-26", None)

    resolved, error = sod_gate_enforcer.resolve_gate_date(
        {"timestamp": "2026-07-25T17:30:00Z"}, "GATE_20260726"
    )
    assert resolved is None
    assert "mismatch" in error


def test_resolve_gate_date_uses_timestamp_for_undated_key():
    resolved, error = sod_gate_enforcer.resolve_gate_date(
        {"timestamp": "2026-07-25T23:30:00-05:00"}, "LEGACY_GATE"
    )
    assert (resolved.isoformat(), error) == ("2026-07-25", None)


@pytest.mark.parametrize(
    "timestamp",
    [None, 123, "2026-07-25T23:00:00", "not-a-date", "2026-02-30T00:00:00Z"],
)
def test_resolve_gate_date_rejects_invalid_timestamp(timestamp):
    resolved, error = sod_gate_enforcer.resolve_gate_date(
        {"timestamp": timestamp}, "LEGACY_GATE"
    )
    assert resolved is None
    assert error


def test_resolve_gate_date_requires_timestamp_for_undated_key():
    resolved, error = sod_gate_enforcer.resolve_gate_date({}, "LEGACY_GATE")
    assert resolved is None
    assert "required" in error


def test_enforcer_passes_explicit_resolved_date(monkeypatch, tmp_path):
    report_path = tmp_path / "role21_legacy.md"
    report_path.write_text("repo-local role source; repo-local skill source", encoding="utf-8")
    captured = {}

    def fake_validator(text, **kwargs):
        captured.update(kwargs)
        return True, [], False

    monkeypatch.setattr(sod_gate_enforcer, "WORKSPACE", tmp_path)
    monkeypatch.setattr(sod_gate_enforcer, "validate_report_evidence", fake_validator)
    valid, _ = sod_gate_enforcer.check_report_evidence_wording(
        "LEGACY_GATE", "role21_legacy.md", {"timestamp": "2026-07-24T00:00:00Z"}
    )
    assert valid
    assert captured["resolved_gate_date"].isoformat() == "2026-07-24"
