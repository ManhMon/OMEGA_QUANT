import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_lesson_extraction


def test_sidecar_exposes_only_approved_provider_modes(monkeypatch):
    calls = []
    monkeypatch.setattr(run_lesson_extraction, "extract_lessons", lambda provider_mode: calls.append(provider_mode) or 0)

    assert run_lesson_extraction.main(["--provider-mode", "fallback-only"]) == 0
    assert calls == ["fallback-only"]


def test_sidecar_uses_shared_external_config_path(monkeypatch, tmp_path):
    config_path = tmp_path / "lesson.json"
    monkeypatch.setenv("OMEGA_LESSON_LLM_CONFIG_PATH", str(config_path))
    assert run_lesson_extraction.extract_lessons.__module__ == "extract_lessons"
