import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sod_gate_enforcer


def test_main_runs_extract_lessons_before_compliance(monkeypatch):
    calls = []

    monkeypatch.setattr(sod_gate_enforcer, "extract_lessons", lambda: calls.append("extract"))
    monkeypatch.setattr(sod_gate_enforcer, "check_sod_compliance", lambda: calls.append("check") or True)

    with pytest.raises(SystemExit) as exc_info:
        sod_gate_enforcer.main([])

    assert exc_info.value.code == 0
    assert calls == ["extract", "check"]
