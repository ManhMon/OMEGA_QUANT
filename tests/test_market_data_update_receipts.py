import json
import base64

import pytest

from scripts import update_market_data as updater


@pytest.fixture(autouse=True)
def receipt_keyring(monkeypatch):
    monkeypatch.setenv(updater.MARKET_DATA_RECEIPT_ACTIVE_KEY_ID, "test-20260729")
    monkeypatch.setenv(updater.MARKET_DATA_RECEIPT_KEYRING, json.dumps({"test-20260729": base64.b64encode(b"x" * 32).decode()}))


def test_published_caller_status_without_pit_evidence_is_denied(tmp_path):
    attempt = updater.start_market_data_attempt(tmp_path)
    assert attempt["path"].exists()
    with pytest.raises(RuntimeError):
        updater._write_immutable_json(attempt["path"], {})

    projection = tmp_path / "projection.json"
    projection.write_text(json.dumps({"market_data_attempt_id": attempt["attempt_id"]}), encoding="utf-8")
    terminal = updater.finish_market_data_attempt(
        attempt,
        {"status": "published", "run_id": "release", "gate_report": {"expected_completed_session": "2026-07-29"}},
        receipt_dir=tmp_path,
        projection_path=projection,
    )
    receipt = json.loads(terminal["path"].read_text(encoding="utf-8"))
    assert receipt["execution_allowed"] is False
    assert receipt["reason"] == "pit_evidence_invalid"


@pytest.mark.parametrize("result", [
    {"status": "gates_failed"},
    {"status": "published", "gate_report": {}},
    {"status": "error", "message": "calendar unknown"},
])
def test_terminal_failure_or_unknown_calendar_denies(tmp_path, result):
    attempt = updater.start_market_data_attempt(tmp_path)
    receipt = updater.finish_market_data_attempt(attempt, result, receipt_dir=tmp_path)["record"]
    assert receipt["execution_allowed"] is False
    assert receipt["stale"] is True or receipt["calendar_status"] == "unknown"


def test_projection_failure_writes_stale_blocked_terminal_receipt(tmp_path):
    attempt = updater.start_market_data_attempt(tmp_path)
    receipt = updater.finish_market_data_attempt(
        attempt,
        {"status": "published", "gate_report": {"expected_completed_session": "2026-07-29"}},
        projection_error="disk full",
        receipt_dir=tmp_path,
    )["record"]

    assert receipt["execution_allowed"] is False
    assert receipt["stale"] is True
    assert receipt["reason"] == "projection_failed: disk full"


def test_missing_key_blocks_before_receipt_write(tmp_path, monkeypatch):
    monkeypatch.delenv(updater.MARKET_DATA_RECEIPT_ACTIVE_KEY_ID)
    with pytest.raises(RuntimeError):
        updater.start_market_data_attempt(tmp_path)
    assert not list(tmp_path.glob("*.json"))


def test_signature_tamper_and_duplicate_key_are_rejected(tmp_path):
    attempt = updater.start_market_data_attempt(tmp_path)
    record = json.loads(attempt["path"].read_text(encoding="utf-8"))
    assert updater.verify_market_data_receipt(record)
    record["state"] = "terminal"
    assert not updater.verify_market_data_receipt(record)
    bad = tmp_path / "bad.json"
    bad.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError):
        updater._load_strict_json(bad)


def test_unknown_receipt_field_is_rejected(tmp_path):
    attempt = updater.start_market_data_attempt(tmp_path)
    record = json.loads(attempt["path"].read_text(encoding="utf-8"))
    record["unexpected"] = True
    assert not updater.verify_market_data_receipt(record)
