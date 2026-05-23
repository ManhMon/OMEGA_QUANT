import json
import logging
from pathlib import Path

from scripts import gateway_wakeup_server


def _write_active_tasks(workspace: Path, payload):
    active_tasks_file = workspace / ".ly_state" / "session" / "active_tasks.json"
    active_tasks_file.parent.mkdir(parents=True, exist_ok=True)
    active_tasks_file.write_text(json.dumps(payload), encoding="utf-8")


def _trigger_pending_tasks(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gateway_wakeup_server, "WORKSPACE", tmp_path)
    return gateway_wakeup_server.WakeupHandler.trigger_pending_tasks(object())


def test_trigger_pending_tasks_detects_single_in_progress_task(monkeypatch, tmp_path):
    _write_active_tasks(
        tmp_path,
        {"task_id": "task-1", "status": "in_progress", "phase": "exec"},
    )

    result = _trigger_pending_tasks(monkeypatch, tmp_path)

    assert result["pending_tasks"] == 1
    assert result["triggered"] == ["task-1"]


def test_trigger_pending_tasks_detects_only_in_progress_tasks_from_list(monkeypatch, tmp_path):
    _write_active_tasks(
        tmp_path,
        [
            {"task_id": "task-1", "status": "queued", "phase": "prep"},
            {"task_id": "task-2", "status": "in_progress", "phase": "exec"},
            {"task_id": "task-3", "status": "done", "phase": "final"},
        ],
    )

    result = _trigger_pending_tasks(monkeypatch, tmp_path)

    assert result["pending_tasks"] == 1
    assert result["triggered"] == ["task-2"]


def test_trigger_pending_tasks_returns_zero_when_no_tasks_in_progress(monkeypatch, tmp_path):
    _write_active_tasks(
        tmp_path,
        [
            {"task_id": "task-1", "status": "queued", "phase": "prep"},
            {"task_id": "task-2", "status": "done", "phase": "final"},
        ],
    )

    result = _trigger_pending_tasks(monkeypatch, tmp_path)

    assert result["pending_tasks"] == 0
    assert result["triggered"] == []


def test_trigger_pending_tasks_logs_detected_task_ids(monkeypatch, tmp_path, caplog):
    _write_active_tasks(
        tmp_path,
        [
            {"task_id": "task-9", "status": "in_progress", "phase": "exec"},
            {"task_id": "task-10", "status": "in_progress", "phase": "verify"},
        ],
    )

    with caplog.at_level(logging.INFO, logger=gateway_wakeup_server.logger.name):
        result = _trigger_pending_tasks(monkeypatch, tmp_path)

    assert result["pending_tasks"] == 2
    assert result["triggered"] == ["task-9", "task-10"]
    assert "Triggered task: task-9" in caplog.text
    assert "Triggered task: task-10" in caplog.text
