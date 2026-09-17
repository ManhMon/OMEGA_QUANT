import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

from omega.data.official_watermark import (
    OfficialWatermarkConfig,
    _OfficialSourceResponse,
    WatermarkContractError,
    canonical_json_bytes,
    materialize_watermark,
    parse_aware_timestamp,
    sha256_hex,
)


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_market_data.py"
SPEC = importlib.util.spec_from_file_location("vci_final_safety_updater", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(updater)


def test_shared_timestamp_parser_normalizes_utc_and_rejects_naive():
    assert parse_aware_timestamp("2026-07-24T09:00:00+07:00", "cutoff").isoformat() == "2026-07-24T02:00:00+00:00"
    with pytest.raises(ValueError):
        parse_aware_timestamp("2026-07-24T09:00:00", "cutoff")


def test_exceptions_hash_recomputed_from_versioned_entries():
    entries = [{"owner": "ops", "reason": "none", "expiry": "2026-12-31", "exchange": "HSX"}]
    expected = sha256_hex(canonical_json_bytes({"version": "v1", "entries": entries}))
    assert expected == sha256_hex(canonical_json_bytes({"version": "v1", "entries": entries}))
    assert expected != sha256_hex(canonical_json_bytes({"version": "v1", "entries": []}))


def test_exception_hash_mismatch_has_priority_over_entry_semantics(tmp_path, monkeypatch):
    entries = [{"owner": "", "reason": "", "expiry": "", "exchange": ""}]
    source = _OfficialSourceResponse("https://api.hsx.vn/m/api/v1.0/data-feed/files", "https://api.hsx.vn/m/api/v1.0/data-feed/files", 200, "application/json", b"official", "2026-07-24T09:01:00+07:00")
    result = {
            "raw": source.raw,
            "rows": [{"market": "HSX", "date": "2026-07-24", "symbol": "AAA"}],
            "coverage": {"final_session": "2026-07-24", "symbols": ["AAA"]},
            "cutoff_at": "2026-07-24T09:02:00+07:00",
            "exceptions": entries,
            "exceptions_hash": "wrong",
        }
    with pytest.raises(WatermarkContractError, match="immutable exceptions hash mismatch"):
        monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
        monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: result)
        materialize_watermark(OfficialWatermarkConfig(tmp_path / "artifacts"), "HSX", "2026-07-24")


def test_lock_owner_release_removes_lock_and_reacquire_succeeds(tmp_path):
    if os.name != "nt":
        pytest.skip("identity-bound native lock deletion is Windows-only")
    lock = tmp_path / "publication.lock"
    lease = updater._acquire_publication_lock(lock)
    with pytest.raises(RuntimeError, match="owner mismatch"):
        updater._release_publication_lock(lock, updater._PublicationLockLease("wrong-token", os.dup(lease.fd), lease.identity))
    updater._release_publication_lock(lock, lease)
    assert not lock.exists()
    replacement_lease = updater._acquire_publication_lock(lock)
    updater._release_publication_lock(lock, replacement_lease)
    assert not lock.exists()


def test_stale_path_replacement_race_fails_closed_and_preserves_active_lock(tmp_path):
    lock = tmp_path / "publication.lock"
    lock.write_text(json.dumps({"pid": 0, "expires_at": 0, "token": "stale"}), encoding="utf-8")
    replacement = lock.with_suffix(".replacement")
    active = {"pid": os.getpid(), "started_at": 1, "token": "active-replacement"}
    start = threading.Event()
    errors = []

    def replace_stale_path():
        start.wait()
        replacement.write_text(json.dumps(active), encoding="utf-8")
        os.replace(replacement, lock)

    def acquire_during_replacement():
        start.set()
        try:
            updater._acquire_publication_lock(lock)
        except RuntimeError as exc:
            errors.append(str(exc))

    racer = threading.Thread(target=replace_stale_path)
    acquirer = threading.Thread(target=acquire_during_replacement)
    racer.start()
    acquirer.start()
    acquirer.join()
    racer.join()

    assert errors == ["publication lock held; operator recovery required"]
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "active-replacement"


def test_release_does_not_unlink_actual_replaced_lock_path(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows handle semantics prevent replacing an open lock pathname")
    lock = tmp_path / "publication.lock"
    lease = updater._acquire_publication_lock(lock)
    replacement = lock.with_suffix(".replacement")
    replacement.write_text(json.dumps({"pid": os.getpid(), "expires_at": 9999999999, "token": "winner"}), encoding="utf-8")
    if os.name == "nt":
        with pytest.raises(PermissionError):
            os.replace(replacement, lock)
        replacement.unlink()
    else:
        os.replace(replacement, lock)
    with pytest.raises(RuntimeError, match="safe identity-bound lock deletion unavailable"):
        updater._release_publication_lock(lock, lease)
    assert lock.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows handle disposition stress test")
def test_windows_release_race_preserves_replacement_and_reacquisition(tmp_path, monkeypatch):
    lock = tmp_path / "publication.lock"
    replacement = tmp_path / "replacement.lock"
    lease = updater._acquire_publication_lock(lock)
    replacement_payload = {"pid": os.getpid(), "started_at": 1, "token": "replacement"}
    disposition_ready = threading.Event()
    replacement_attempted = threading.Event()
    replacement_installed = threading.Event()
    original_disposition = updater._mark_handle_delete_pending_windows
    original_replace = os.replace

    def replace_with_entry_barrier(source, destination):
        replacement_attempted.set()
        return original_replace(source, destination)

    def install_replacement_then_dispose(fd):
        disposition_ready.set()
        assert replacement_attempted.wait(timeout=5)
        original_disposition(fd)

    monkeypatch.setattr(updater, "_mark_handle_delete_pending_windows", install_replacement_then_dispose)
    monkeypatch.setattr(os, "replace", replace_with_entry_barrier)

    def replace_during_release():
        assert disposition_ready.wait(timeout=5)
        replacement.write_text(json.dumps(replacement_payload), encoding="utf-8")
        deadline = time.monotonic() + 5
        while True:
            try:
                os.replace(replacement, lock)
                replacement_installed.set()
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise

    racer = threading.Thread(target=replace_during_release)
    racer.start()
    updater._release_publication_lock(lock, lease)
    racer.join(timeout=5)

    assert not racer.is_alive()
    assert replacement_installed.is_set()
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "replacement"
    with pytest.raises(RuntimeError, match="publication lock"):
        updater._acquire_publication_lock(lock)
    lock.unlink()


def test_reader_uses_verified_private_candidate_copy(tmp_path):
    candidate = tmp_path / "candidate.parquet"
    pointer = tmp_path / "current.json"
    frame = pd.DataFrame({"ticker": ["AAA"], "date": [pd.Timestamp("2026-07-24")], "close": [1.0]})
    frame.to_parquet(candidate, index=False)
    pointer.write_text(json.dumps({"candidate": str(candidate), "sha256": updater._sha256(candidate)}), encoding="utf-8")
    original_hash = updater.sha256_hex
    replaced = pd.DataFrame({"ticker": ["BAD"], "date": [pd.Timestamp("2026-07-24")], "close": [2.0]})
    replaced_path = tmp_path / "replacement.parquet"
    replaced.to_parquet(replaced_path, index=False)
    calls = {"count": 0}
    def replace_after_read(value):
        calls["count"] += 1
        if calls["count"] == 1:
            os.replace(replaced_path, candidate)
        return original_hash(value)
    updater.sha256_hex = replace_after_read
    result = updater.read_published_candidate(pointer)
    assert result.equals(frame)
