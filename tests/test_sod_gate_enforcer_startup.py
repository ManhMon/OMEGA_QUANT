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


def test_malformed_gate_json_blocks_compliance(monkeypatch):
    monkeypatch.setattr(sod_gate_enforcer, "validate_task_graph", lambda: (True, "ok"))
    monkeypatch.setattr(sod_gate_enforcer, "load_gates", lambda: None)

    assert not sod_gate_enforcer.check_sod_compliance()


@pytest.mark.parametrize("member", [None, [], 1, "gate"])
def test_dict_shaped_gates_reject_non_object_members(monkeypatch, tmp_path, member):
    gates_path = tmp_path / "phase_gates.json"
    gates_path.write_text(__import__("json").dumps({"VALID": {"phase_name": "VALID"}, "INVALID": member}), encoding="utf-8")
    monkeypatch.setattr(sod_gate_enforcer, "GATES_FILE", gates_path)

    with pytest.raises(SystemExit) as exc_info:
        sod_gate_enforcer.load_gates()

    assert exc_info.value.code == 1


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


def test_role_26_is_valid_for_plan_gate_only():
    role_specs = {
        26: {
            "name": "planning-architect",
            "tier": 3,
            "platform": "Codex",
            "sod_boundary": "planning-only, non-audit, no production code",
        }
    }

    assert sod_gate_enforcer.validate_l2_role(
        26, "planning-architect", role_specs, "macro_micro_data_v8_detailed_plan"
    ) == (True, "")
    valid, message = sod_gate_enforcer.validate_l2_role(
        26, "planning-architect", role_specs, "macro_micro_data_v8_implementation"
    )
    assert not valid
    assert message == "l2_role_id must be 6-16, got: 26"


@pytest.mark.parametrize(
    ("role_name", "spec_update"),
    [
        (None, {}),
        ("wrong-role", {}),
        ("planning-architect", {"name": "wrong-role"}),
        ("planning-architect", {"sod_boundary": "planning-only"}),
        ("planning-architect", {"sod_boundary": "planning-only, non-audit"}),
        ("planning-architect", {"sod_boundary": ""}),
        ("planning-architect", {"sod_boundary": "  "}),
        ("planning-architect", {"sod_boundary": True}),
        ("planning-architect", {"tier": 2}),
        ("planning-architect", {"platform": "OpenCode"}),
    ],
)
def test_role_26_plan_gate_requires_exact_identity_and_boundary(role_name, spec_update):
    spec = {
        "name": "planning-architect",
        "tier": 3,
        "platform": "Codex",
        "sod_boundary": "planning-only, non-audit, no production code",
    }
    spec.update(spec_update)

    valid, message = sod_gate_enforcer.validate_l2_role(
        26, role_name, {26: spec}, "macro_micro_data_v8_detailed_plan"
    )

    assert not valid
    assert message == (
        "l2_role_id 26 plan exception requires planning-architect, tier=3, platform=Codex, and sod_boundary"
    )


def test_regular_l2_role_allows_missing_name_for_grandfathered_gate():
    valid, message = sod_gate_enforcer.validate_l2_role(
        6,
        None,
        {6: {"name": "system-architect", "tier": 2, "platform": "OpenCode"}},
    )

    assert valid
    assert message == ""
