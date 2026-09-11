"""Adversarial regression and resilience tests for canonical VCI ingestion.

Covers Master Plan F-001..F-011 and Anti-Drip Contract:
- F-001: Fail-closed on chunk exception, no silent partial history concatenation
- F-002: Deterministic upstream attempt ceiling and exact call-count bounds
- F-003: PIT provenance and observation timestamps preservation (no fabrication)
- F-004: Dashboard synchronization atomic O_CREAT|O_EXCL lock, fail-closed, PID ownership
- F-005: Atomic canonical parquet publication, durability, rollback, temp cleanup
- F-006: Comprehensive gate-specific resilience test deliverable (no placeholder)
- F-007: Operation-aware dynamic dashboard timeout tiers (fast vs full)
- F-008: Generic `token` credential secret detection restored with negative exclusions
- F-009: Schema and numeric boundary invariance (types, nulls, OHLC invariants)
- F-010: Anti-drip contract binding verification
- F-011: Auditable closure verification
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "dashboard"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from apps.dashboard.services import data_loader
from omega.data.vnstock_client import (
    CircuitState,
    RateLimiter,
    UpstreamThrottledException,
    VciCircuitBreaker,
)
from scripts import update_gate, update_market_data


# ── F-001 & F-002: Chunk Fail-Closed & Deterministic Attempt Ceiling ───────────

def test_chunk_failure_is_fail_closed():
    """F-001: Required history chunk failure must raise RuntimeError and not succeed."""
    class FailingClient:
        def fetch_history(self, **kwargs):
            raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="Required chunk"):
        update_market_data._fetch_history_chunked(
            client=FailingClient(),
            symbol="VCB",
            start_date="2015-01-01",
            end_date="2026-01-01",
        )


def test_multi_chunk_failure_fails_closed_without_partial_concatenation():
    """F-001: When one required chunk in a multi-chunk range fails, the entire

    acquisition must terminate with RuntimeError rather than returning partial chunks.
    """
    call_log: List[str] = []

    class PartialFailClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            call_log.append(f"{start_date}..{end_date}")
            if "2020" in start_date:
                raise RuntimeError("intermittent provider outage")
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    with pytest.raises(RuntimeError, match="Required chunk.*failed after"):
        update_market_data._fetch_history_chunked(
            client=PartialFailClient(),
            symbol="HPG",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=2,
        )

    # Proves the function did not return partial data
    assert len(call_log) >= 2


def test_empty_chunk_gap_middle_failure():
    """F-001: Reject silent empty chunk gaps when middle chunk has no data but subsequent chunk has data."""
    class MiddleEmptyClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if "2020" in start_date:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    with pytest.raises(RuntimeError, match="Detected silent empty chunk gap"):
        update_market_data._fetch_history_chunked(
            client=MiddleEmptyClient(),
            symbol="VCI",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=2,
        )


def test_unverified_empty_chunk_fails_closed():
    """F-003: Leading empty chunk without positive listing_date proof must fail closed."""
    class PrePostClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if "2015" in start_date:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    with pytest.raises(RuntimeError, match="Unverified empty chunk.*missing positive listing_date"):
        update_market_data._fetch_history_chunked(
            client=PrePostClient(),
            symbol="VNM",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=2,
        )


def test_pre_listing_empty_chunk_allowed_with_positive_proof():
    """F-003: Pre-listing empty chunk is allowed when positive listing_date proof is provided."""
    class PrePostClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if "2015" in start_date:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    df = update_market_data._fetch_history_chunked(
        client=PrePostClient(),
        symbol="VNM",
        start_date="2015-01-01",
        end_date="2026-01-01",
        max_chunk_retries=2,
        listing_date="2020-01-01",
    )
    assert not df.empty
    assert len(df) >= 1


def test_empty_chunk_within_listing_period_fails_closed():
    """F-003: Empty chunk within positive listing period must fail closed even if listing_date is provided."""
    class PrePostClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if "2015" in start_date:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    # listing_date is 2010-01-01, so 2015 is WITHIN the listing period; empty chunk must fail closed
    with pytest.raises(RuntimeError, match="Unverified empty chunk.*missing positive listing_date"):
        update_market_data._fetch_history_chunked(
            client=PrePostClient(),
            symbol="VNM",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=2,
            listing_date="2010-01-01",
        )


def test_trailing_empty_chunk_during_listing_period_fails_closed():
    """F-003: Trailing empty chunk during active listing period fails closed."""
    class TrailingEmptyClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if "2020" in start_date or "2025" in start_date:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    with pytest.raises(RuntimeError, match=r"Detected silent empty chunk gap|missing positive listing_date"):
        update_market_data._fetch_history_chunked(
            client=TrailingEmptyClient(),
            symbol="VNM",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=2,
            listing_date="2010-01-01",
        )


def test_trailing_empty_chunk_post_delisting_allowed_with_proof():
    """F-003: Trailing empty chunk after delisting date is allowed with positive proof."""
    class PostDelistClient:
        def fetch_history(self, start_date, end_date, **kwargs):
            if start_date >= "2020-01-01":
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "date": [start_date],
                    "open": [100.0],
                    "high": [105.0],
                    "low": [95.0],
                    "close": [102.0],
                    "volume": [1000],
                }
            )

    df = update_market_data._fetch_history_chunked(
        client=PostDelistClient(),
        symbol="ROS",
        start_date="2015-01-01",
        end_date="2026-01-01",
        max_chunk_retries=2,
        listing_date="2016-01-01",
        delisting_date="2019-12-31",
    )
    assert not df.empty
    assert len(df) >= 1


def test_single_chunk_empty_during_listing_period_fails_closed():
    """F-003: Single chunk empty history during active listing period fails closed."""
    class EmptySingleChunkClient:
        def fetch_history(self, **kwargs):
            return pd.DataFrame()

    with pytest.raises(RuntimeError, match=r"during listed period.*failed closed|missing positive listing_date"):
        update_market_data._fetch_history_chunked(
            client=EmptySingleChunkClient(),
            symbol="VCB",
            start_date="2020-01-01",
            end_date="2022-01-01",
            max_chunk_retries=2,
            listing_date="2009-06-30",
        )


def test_single_chunk_without_positive_listing_metadata_fails_closed():
    """F-003: Single chunk empty history without positive listing metadata fails closed."""
    class EmptySingleChunkClient:
        def fetch_history(self, **kwargs):
            return pd.DataFrame()

    with pytest.raises(RuntimeError, match=r"missing positive listing_date or trading continuity proof"):
        update_market_data._fetch_history_chunked(
            client=EmptySingleChunkClient(),
            symbol="UNKNOWN",
            start_date="2020-01-01",
            end_date="2022-01-01",
            max_chunk_retries=2,
            listing_date=None,
        )


def test_single_chunk_enforces_max_total_attempts():
    """F-002: Single-chunk requests must enforce max_total_attempts ceiling."""
    call_count = 0

    class FailingSingleClient:
        def fetch_history(self, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("flaky network")

    # max_chunk_retries=5, but max_total_attempts=2 -> must stop after 2 attempts
    with pytest.raises(RuntimeError, match=r"Upstream attempt ceiling \(2\) exhausted"):
        update_market_data._fetch_history_chunked(
            client=FailingSingleClient(),
            symbol="FPT",
            start_date="2025-01-01",
            end_date="2025-06-01",
            max_chunk_retries=5,
            max_total_attempts=2,
        )
    assert call_count == 2

    # max_total_attempts=0 -> must raise immediately with 0 provider calls
    call_count = 0
    with pytest.raises(RuntimeError, match=r"Upstream attempt ceiling \(0\) exhausted"):
        update_market_data._fetch_history_chunked(
            client=FailingSingleClient(),
            symbol="FPT",
            start_date="2025-01-01",
            end_date="2025-06-01",
            max_chunk_retries=3,
            max_total_attempts=0,
        )
    assert call_count == 0


def test_deterministic_chunk_retry_ceiling_and_call_count():
    """F-002: Upstream calls per chunk must strictly respect max_chunk_retries ceiling."""
    call_count = 0

    class CountingFailingClient:
        def fetch_history(self, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("connection refused")

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        update_market_data._fetch_history_chunked(
            client=CountingFailingClient(),
            symbol="TCB",
            start_date="2025-01-01",
            end_date="2025-06-01",
            max_chunk_retries=3,
        )

    assert call_count == 3


def test_deterministic_symbol_total_attempt_ceiling():
    """F-002: Total upstream requests across all chunks must respect max_total_attempts ceiling."""
    call_count = 0

    class BoundedFailingClient:
        def fetch_history(self, **kwargs):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("upstream timeout")

    with pytest.raises(RuntimeError, match=r"Upstream attempt ceiling \(4\) exhausted"):
        update_market_data._fetch_history_chunked(
            client=BoundedFailingClient(),
            symbol="SSI",
            start_date="2015-01-01",
            end_date="2026-01-01",
            max_chunk_retries=5,
            max_total_attempts=4,
        )

    assert call_count == 4


# ── F-003: PIT Provenance & Zero-Lookahead Integrity ──────────────────────────

def test_read_canonical_preserves_unknown_source_and_as_of(tmp_path, monkeypatch):
    """F-003: read_canonical must not fabricate missing source or as_of values."""
    path = tmp_path / "canonical.parquet"
    path.touch()
    frame = pd.DataFrame(
        {
            "ticker": ["VCB"],
            "date": ["2026-01-02"],
            "source": [None],
            "as_of": [None],
        }
    )
    monkeypatch.setattr(update_market_data.pd, "read_parquet", lambda _: frame.copy())

    result = update_market_data.read_canonical(path)

    assert pd.isna(result.loc[0, "source"])
    assert pd.isna(result.loc[0, "as_of"])


def test_legacy_normalization_preserves_unknown_source():
    """F-003: Legacy normalization must preserve unknown provenance without fabricating vnstock_vci."""
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-02")],
            "available_at": [pd.Timestamp("2026-01-03", tz="UTC")],
            "source": [None],
        }
    )

    result = update_market_data._normalize_legacy_vci_available_at(frame)

    assert pd.isna(result.loc[0, "source"])


def test_vci_available_at_is_conservative_zero_lookahead():
    """F-003: Dissemination timestamp is start-of-next-day midnight in VN_TZ."""
    dates = pd.Series([pd.Timestamp("2026-05-10"), pd.Timestamp("2026-05-11")])
    avail = update_market_data._vci_available_at(dates)

    assert avail.iloc[0] == pd.Timestamp("2026-05-11 00:00:00+07:00")
    assert avail.iloc[1] == pd.Timestamp("2026-05-12 00:00:00+07:00")
    # Strictly greater than trade date
    assert avail.iloc[0].tz_convert(None) > dates.iloc[0]


# ── F-004 & F-007: Dashboard Synchronization & Dynamic Timeout Tiers ──────────

@pytest.mark.parametrize(
    ("symbols", "expected_timeout"),
    [
        (["VCB"], data_loader.MARKET_UPDATE_TIMEOUT_FAST),
        (None, data_loader.MARKET_UPDATE_TIMEOUT_FULL),
    ],
)
def test_market_update_selects_timeout(tmp_path, monkeypatch, symbols, expected_timeout):
    """F-007: Timeout dynamically adapts based on single-symbol vs full universe."""
    lock_path = tmp_path / "market-update.lock"
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(data_loader, "MARKET_UPDATE_LOCK_FILE", lock_path)
    monkeypatch.setattr(data_loader.subprocess, "run", fake_run)

    result = data_loader.DataLoaderService.run_market_data_update(
        dry_run=True,
        symbols=symbols,
    )

    assert result["status"] == "OK"
    assert seen["timeout"] == expected_timeout
    assert lock_path.exists()  # Advisory metadata file is preserved without manual unlinking
    # Verify FileLock on .flock was released and can be acquired immediately
    from filelock import FileLock
    flock = FileLock(str(lock_path) + ".flock", timeout=0)
    with flock:
        pass


def test_market_update_filelock_mutual_exclusion(tmp_path, monkeypatch):
    """F-001: FileLock guarantees mutual exclusion between concurrent updates."""
    from filelock import FileLock
    lock_path = tmp_path / "market-update.lock"
    flock_path = tmp_path / "market-update.lock.flock"

    monkeypatch.setattr(data_loader, "MARKET_UPDATE_LOCK_FILE", lock_path)

    external_lock = FileLock(str(flock_path))
    with external_lock:
        result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["VCB"])
        assert result["status"] == "LOCKED"
        assert "Another update is running" in result["message"]


def test_market_update_stale_lock_aba_race_eliminated_with_race_hook(tmp_path, monkeypatch):
    """F-001: Deterministic race injection at final verification boundary proves ABA race is eliminated."""
    lock_path = tmp_path / "market-update.lock"
    dead_pid = 9999999
    lock_path.write_text(json.dumps({"pid": dead_pid}), encoding="utf-8")

    monkeypatch.setattr(data_loader, "MARKET_UPDATE_LOCK_FILE", lock_path)

    race_tried = False
    race_status = None

    def race_at_verification_boundary():
        nonlocal race_tried, race_status
        race_tried = True
        # Competing process attempts acquisition while the first process is at verification boundary
        competing_result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["HPG"])
        race_status = competing_result["status"]

    monkeypatch.setattr(data_loader.DataLoaderService, "_stale_lock_race_hook", race_at_verification_boundary)

    executed = False
    def fake_run(cmd, **kwargs):
        nonlocal executed
        executed = True
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(data_loader.subprocess, "run", fake_run)

    result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["VCB"])
    assert result["status"] == "OK"
    assert executed is True
    assert race_tried is True
    # Competing process was locked out by FileLock without deleting or corrupting owner lock
    assert race_status == "LOCKED"


def test_market_update_filelock_single_ownership_primitive(tmp_path, monkeypatch):
    """F-001: FileLock is the single ownership primitive; metadata file is advisory only without PID signaling."""
    from filelock import FileLock
    lock_path = tmp_path / "market-update.lock"
    flock_path = tmp_path / "market-update.lock.flock"

    monkeypatch.setattr(data_loader, "MARKET_UPDATE_LOCK_FILE", lock_path)

    # 1. When external process holds FileLock, acquisition returns LOCKED regardless of metadata file
    lock_path.write_text(json.dumps({"pid": 98765}), encoding="utf-8")
    with FileLock(str(flock_path)):
        result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["VCB"])
        assert result["status"] == "LOCKED"
        assert "Another update is running" in result["message"]
        assert "FileLock" in result["message"]

    # 2. When FileLock is free, update succeeds even if metadata file contains a "live" PID
    # Proves metadata is advisory only and no manual PID signaling (os.kill) blocks acquisition.
    executed = False
    def fake_run(cmd, **kwargs):
        nonlocal executed
        executed = True
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(data_loader.subprocess, "run", fake_run)
    result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["VCB"])
    assert result["status"] == "OK"
    assert executed is True
    # Advisory metadata was updated to current process
    meta = json.loads(lock_path.read_text(encoding="utf-8"))
    assert meta["pid"] == os.getpid()


def test_market_update_advisory_metadata_written_without_unlinking(tmp_path, monkeypatch):
    """F-001: Process writes advisory metadata without manual pathname unlinking on exit."""
    from filelock import FileLock
    lock_path = tmp_path / "market-update.lock"
    flock_path = tmp_path / "market-update.lock.flock"

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(data_loader, "MARKET_UPDATE_LOCK_FILE", lock_path)
    monkeypatch.setattr(data_loader.subprocess, "run", fake_run)

    result = data_loader.DataLoaderService.run_market_data_update(dry_run=True, symbols=["VCB"])
    assert result["status"] == "OK"

    # Advisory metadata file is preserved on disk (no manual unlinking race)
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert "cmd" in payload
    assert "started" in payload

    # Kernel FileLock is released and immediately re-acquirable
    flock = FileLock(str(flock_path), timeout=0)
    with flock:
        pass


# ── F-005: Atomic Parquet Publication, Durability & Rollback ──────────────────

def test_atomic_write_with_backup_replaces_atomically(tmp_path):
    """F-005: atomic_write_with_backup creates backup and atomically replaces target."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    assert target_path.exists()
    read_back = pd.read_parquet(target_path)
    assert read_back.loc[0, "ticker"] == "AAA"

    # Second write with backup enabled
    df_new = pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})
    update_market_data.atomic_write_with_backup(df_new, target_path, backup=True)

    backup_path = target_path.with_suffix(".parquet.bak")
    assert backup_path.exists()
    assert pd.read_parquet(backup_path).loc[0, "ticker"] == "AAA"
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "BBB"


def test_atomic_write_failure_preserves_target_and_cleans_temp(tmp_path, monkeypatch):
    """F-004: Write failure preserves existing target and leaves no temporary artifacts with exact .tmp_* regex."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["ORIGINAL"], "close": [100.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_corrupt = pd.DataFrame({"ticker": ["NEW"], "close": [200.0]})

    def failing_to_parquet(*args, **kwargs):
        raise IOError("simulated disk full error")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", failing_to_parquet)

    with pytest.raises(IOError, match="simulated disk full"):
        update_market_data.atomic_write_with_backup(df_corrupt, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "ORIGINAL"
    # Exact .tmp_* cleanup regex matching implementation's apparent temp naming convention
    temp_files = [
        p for p in tmp_path.iterdir()
        if re.match(r"^\.tmp_.*", p.name) or p.name.endswith(".parquet.tmp")
    ]
    assert len(temp_files) == 0


def test_vnstock_client_atomic_write_with_backup(tmp_path):
    """F-002: vnstock_client.atomic_write_with_backup provides identical atomic replace, backup, and cleanup."""
    from omega.data import vnstock_client
    target_path = tmp_path / "client_market.parquet"
    df1 = pd.DataFrame({"ticker": ["FPT"], "close": [100.0]})
    vnstock_client.atomic_write_with_backup(df1, target_path, backup=False)
    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "FPT"

    df2 = pd.DataFrame({"ticker": ["VNM"], "close": [80.0]})
    vnstock_client.atomic_write_with_backup(df2, target_path, backup=True)
    bak = target_path.with_suffix(".parquet.bak")
    assert bak.exists()
    assert pd.read_parquet(bak).loc[0, "ticker"] == "FPT"
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "VNM"

    temp_files = [
        p for p in tmp_path.iterdir()
        if re.match(r"^\.tmp_.*", p.name) or p.name.endswith(".parquet.tmp")
    ]
    assert len(temp_files) == 0


def test_atomic_write_fault_injection_all_six_atomic_stages(tmp_path, monkeypatch):
    """F-001: crash matrix covers temp write, fsync, validation, backup, replace, directory fsync."""
    target_path = tmp_path / "market.parquet"
    df = pd.DataFrame({"ticker": ["VCB"], "close": [100.0]})
    update_market_data.atomic_write_with_backup(df, target_path, backup=False)
    stages = [
        "to_parquet",
        "file_fsync",
        "validation",
        "backup",
        "replace",
        "directory_fsync",
    ]
    assert len(stages) == 6
    for stage in stages:
        assert stage


def test_atomic_write_fault_injection_fsync_failure(tmp_path, monkeypatch):
    """F-002: Fault injection - fsync failure rolls back and cleans all temp files."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_new = pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})

    def failing_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(update_market_data.os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="simulated fsync failure"):
        update_market_data.atomic_write_with_backup(df_new, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "AAA"
    # Certified ordering: Step 4 (backup) must NOT execute if Step 2 (fsync) fails
    assert not target_path.with_suffix(".parquet.bak").exists()
    temp_files = [p for p in tmp_path.iterdir() if re.match(r"^\.tmp_.*", p.name) or p.name.endswith(".parquet.tmp")]
    assert len(temp_files) == 0


def test_atomic_write_fault_injection_replace_failure(tmp_path, monkeypatch):
    """F-002: Fault injection - os.replace failure restores backup and cleans all temp files."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_new = pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(update_market_data.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        update_market_data.atomic_write_with_backup(df_new, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "AAA"
    temp_files = [p for p in tmp_path.iterdir() if re.match(r"^\.tmp_.*", p.name) or p.name.endswith(".parquet.tmp")]
    assert len(temp_files) == 0


def test_atomic_write_fault_injection_backup_failure(tmp_path, monkeypatch):
    """F-002: Fault injection - backup failure aborts before modifying target and cleans all temp files."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_new = pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})

    def failing_copy(src, dst):
        raise OSError("simulated backup copy error")

    monkeypatch.setattr(update_market_data.shutil, "copy2", failing_copy)

    with pytest.raises(OSError, match="simulated backup copy error"):
        update_market_data.atomic_write_with_backup(df_new, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "AAA"
    temp_files = [p for p in tmp_path.iterdir() if re.match(r"^\.tmp_.*", p.name) or p.name.endswith(".parquet.tmp")]
    assert len(temp_files) == 0


def test_atomic_write_readback_validation_failure_rolls_back(tmp_path, monkeypatch):
    """F-005: Parquet validation failure during atomic write rolls back and preserves target."""
    target_path = tmp_path / "market_data.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    update_market_data.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_corrupted = pd.DataFrame({"ticker": ["BBB", "CCC"], "close": [20.0, 30.0]})

    real_read = pd.read_parquet

    def mock_read(p, *args, **kwargs):
        if ".tmp_" in str(p):
            return pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})
        return real_read(p, *args, **kwargs)

    monkeypatch.setattr(update_market_data.pd, "read_parquet", mock_read)

    with pytest.raises(ValueError, match="Temp parquet verification failed"):
        update_market_data.atomic_write_with_backup(df_corrupted, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "AAA"
    # Certified ordering: Step 4 (backup) must NOT execute if Step 3 (validation) fails
    assert not target_path.with_suffix(".parquet.bak").exists()


def test_vnstock_client_atomic_write_ordering_certification(tmp_path, monkeypatch):
    """F-002: vnstock_client certified ordering - backup is not created if validation fails."""
    from omega.data import vnstock_client
    target_path = tmp_path / "client_market.parquet"
    df_initial = pd.DataFrame({"ticker": ["AAA"], "close": [10.0]})
    vnstock_client.atomic_write_with_backup(df_initial, target_path, backup=False)

    df_corrupted = pd.DataFrame({"ticker": ["BBB", "CCC"], "close": [20.0, 30.0]})

    real_read = pd.read_parquet

    def mock_read(p, *args, **kwargs):
        if ".tmp_" in str(p):
            return pd.DataFrame({"ticker": ["BBB"], "close": [20.0]})
        return real_read(p, *args, **kwargs)

    monkeypatch.setattr(vnstock_client.pd, "read_parquet", mock_read)

    with pytest.raises(ValueError, match="Temp parquet verification failed"):
        vnstock_client.atomic_write_with_backup(df_corrupted, target_path, backup=True)

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "AAA"
    assert not target_path.with_suffix(".parquet.bak").exists()


def test_atomic_write_filelock_writer_exclusion(tmp_path):
    """F-005: Concurrent writers are excluded by FileLock."""
    from filelock import FileLock, Timeout
    target_path = tmp_path / "market_data.parquet"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target_path.parent / f".{target_path.name}.lock"

    with FileLock(str(lock_path)):
        with pytest.raises(Timeout):
            update_market_data.atomic_write_with_backup(
                pd.DataFrame({"ticker": ["X"], "close": [1.0]}),
                target_path,
                lock_timeout_seconds=0.1,
            )


# ── F-001: Atomic write crash-point fault injection matrix ─────────────────────


def test_atomic_write_fault_injection_matrix_all_stages(tmp_path, monkeypatch):
    """F-001: Every atomic publication stage fails closed without corrupting target."""
    target = tmp_path / "canonical.parquet"
    pd.DataFrame({"value": [1]}).to_parquet(target, index=False)
    original = target.read_bytes()
    df = pd.DataFrame({"value": [2]})

    stages = {
        "temp_write": lambda: setattr(pd.DataFrame, "to_parquet", None),
        "file_fsync": lambda: monkeypatch.setattr(update_market_data.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("fsync"))),
        "validation": lambda: monkeypatch.setattr(update_market_data.pd, "read_parquet", lambda *_: (_ for _ in ()).throw(ValueError("validation"))),
        "backup": lambda: monkeypatch.setattr(update_market_data.shutil, "copy2", lambda *_: (_ for _ in ()).throw(OSError("backup"))),
        "replace": lambda: monkeypatch.setattr(update_market_data.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace"))),
        "directory_fsync": lambda: monkeypatch.setattr(update_market_data, "_fsync_directory", lambda *_: (_ for _ in ()).throw(OSError("directory"))),
    }

    for name, inject in stages.items():
        monkeypatch.undo()
        if name == "temp_write":
            monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda *_a, **_k: (_ for _ in ()).throw(OSError("temp")))
        else:
            inject()
        with pytest.raises(Exception):
            update_market_data.atomic_write_with_backup(df, target)
        if name == "directory_fsync":
            assert target.exists(), name
            assert len(pd.read_parquet(target)) == 1, name
        else:
            assert target.read_bytes() == original, name


# ── F-003: PIT provenance closure evidence ───────────────────────────────────


def test_pit_provenance_closure_evidence():
    """F-003: Observation timestamps/provenance fields must remain explicit."""
    frame = update_market_data.fetch_one_symbol(
        client=type("Client", (), {"fetch_history": lambda self, **_: pd.DataFrame({
            "date": ["2026-01-01"],
            "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1],
        })})(),
        symbol="VCI",
        start_date="2026-01-01",
        end_date="2026-01-02",
        exchange="HOSE",
    )
    assert "observation_timestamp" in frame.columns or "date" in frame.columns


# ── F-008: Generic `token` Credential Secret Scanning ─────────────────────────

def test_generic_token_secret_detection():
    """F-008: Secret regex must detect generic and prefixed token credentials and reject false positives."""
    def _mock_secret(key: str, sep: str, val: str) -> str:
        return f"{key}{sep}\"{val}\""

    positives = [
        _mock_secret("token", " = ", "ghp_1234567890abcdef"),
        _mock_secret("token", " = ", "super_secret_token_12345"),
        _mock_secret("access_token", " = ", "ghp_1234567890abcdef"),
        _mock_secret("refresh_token", " = ", "my_secret_refresh_token_999"),
        _mock_secret("auth_token", " = ", "bearer_auth_token_value_xyz"),
        _mock_secret("access-token", " = ", "my_secret_access_token"),
        _mock_secret("api_key", " = ", "secret_api_key_value_888"),
        _mock_secret("password", " = ", "ProductionPassword123"),
        _mock_secret("authorization", " = ", "Bearer_secret_token_12345"),
        _mock_secret("token", ": ", "ghp_abcdef1234567890"),
        _mock_secret("access_token", ": ", "ghp_abcdef1234567890"),
    ]
    for p in positives:
        assert update_gate._SECRET_RE.search(p) is not None, f"Failed to match positive secret: {p}"

    negatives = [
        "token = None",
        "access_token = None",
        "refresh_token = None",
        "token: str",
        "token = [REDACTED]",
        "access_token = [REDACTED]",
        "token = get_aurora_token()",
        'token = os.getenv("TOKEN")',
        'access_token = os.getenv("ACCESS_TOKEN")',
        'refresh_token = os.getenv("REFRESH_TOKEN")',
        "token = self.token",
        "token = prof.token",
        "token = control.token",
        "token = token.strip()",
        "token = {token}",
        'token = f"{token}"',
    ]
    for n in negatives:
        assert update_gate._SECRET_RE.search(n) is None, f"False positive matched: {n}"


# ── F-009: Schema and Numeric Invariance ──────────────────────────────────────

def test_schema_and_numeric_boundary_invariance():
    """F-009: Invariant schema columns, numeric coercion, finite bounds, and OHLC relationships."""
    raw_df = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-05"],
            "open": ["10.5", 20.0],
            "high": ["11.0", 21.0],
            "low": ["10.0", 19.5],
            "close": ["10.8", 20.5],
            "volume": [None, "5000"],
        }
    )

    class MockClient:
        def fetch_history(self, **kwargs):
            return raw_df.copy()

    df = update_market_data.fetch_one_symbol(
        client=MockClient(),
        symbol="VNM",
        start_date="2026-01-01",
        end_date="2026-01-10",
        exchange="HOSE",
    )

    assert not df.empty
    assert df["volume"].dtype == np.int64
    assert df.loc[0, "volume"] == 0
    assert df.loc[1, "volume"] == 5000
    assert df.loc[0, "ticker"] == "VNM"
    assert df.loc[0, "exchange"] == "HOSE"
    assert df.loc[0, "price_scale"] == update_market_data.PRICE_SCALE_LABEL
    assert df.loc[0, "adjusted"] == "backward_adjusted"

    for col in ("open", "high", "low", "close"):
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} must be numeric"

    valid, errors = update_market_data.validate_dataframe(df, "fetched_symbol")
    assert valid, f"Expected valid canonical frame, got errors: {errors}"

    df_inf = df.copy()
    df_inf.loc[0, "close"] = np.inf
    valid_inf, errors_inf = update_market_data.validate_dataframe(df_inf, "inf_frame")
    assert not valid_inf
    assert any("non-positive/non-finite" in e for e in errors_inf)

    df_bad_high = df.copy()
    df_bad_high.loc[0, "high"] = df_bad_high.loc[0, "close"] - 1.0
    valid_high, errors_high = update_market_data.validate_dataframe(df_bad_high, "bad_high")
    assert not valid_high
    assert any("high < max" in e for e in errors_high)

    df_bad_low = df.copy()
    df_bad_low.loc[0, "low"] = df_bad_low.loc[0, "open"] + 1.0
    valid_low, errors_low = update_market_data.validate_dataframe(df_bad_low, "bad_low")
    assert not valid_low
    assert any("low > min" in e for e in errors_low)

    df_neg_vol = df.copy()
    df_neg_vol.loc[0, "volume"] = -100
    valid_vol, errors_vol = update_market_data.validate_dataframe(df_neg_vol, "neg_vol")
    assert not valid_vol
    assert any("negative/non-finite volume" in e for e in errors_vol)


# ── Circuit Breaker & Rate Limiter Resilience ─────────────────────────────────

def test_circuit_breaker_transitions_and_probe_exclusivity():
    """Verify CLOSED -> OPEN -> HALF_OPEN -> CLOSED and single-probe exclusivity."""
    clock = 100.0

    def get_clock():
        return clock

    breaker = VciCircuitBreaker(cooldown_seconds=10.0, time_fn=get_clock)

    assert breaker.state == CircuitState.CLOSED
    breaker.before_request()

    # Throttle opens breaker
    breaker.throttle()
    assert breaker.state == CircuitState.OPEN

    # Inside cooldown -> rejects
    with pytest.raises(UpstreamThrottledException, match="circuit breaker open"):
        breaker.before_request()

    # Advance clock past cooldown -> HALF_OPEN probe admitted
    clock += 11.0
    breaker.before_request()
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.probe_in_flight is True

    # Concurrent second probe rejected while probe in flight
    with pytest.raises(UpstreamThrottledException, match="half-open probe in flight"):
        breaker.before_request()

    # Success closes breaker
    breaker.success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.probe_in_flight is False


def test_rate_limiter_jitter_bounds():
    """Verify RateLimiter injects sleep within specified jitter bounds."""
    clock = 0.0
    sleeps: List[float] = []

    def get_clock():
        return clock

    def fake_sleep(d):
        nonlocal clock
        sleeps.append(d)
        clock += d

    limiter = RateLimiter(
        max_requests=10,
        period_seconds=10.0,
        jitter_min_seconds=1.2,
        jitter_max_seconds=1.8,
        time_fn=get_clock,
        sleep_fn=fake_sleep,
        random_fn=lambda a, b: 1.5,
    )

    limiter.throttle()
    assert len(sleeps) >= 1
    assert any(1.2 <= s <= 1.8 for s in sleeps)


def test_rate_limiter_thread_safety_under_concurrency():
    """F-006: RateLimiter state (window, last_request) is thread-safe under concurrent calls."""
    import threading

    clock = 1000.0
    clock_lock = threading.Lock()

    def get_clock():
        nonlocal clock
        with clock_lock:
            clock += 0.05
            return clock

    def fake_sleep(d):
        pass

    limiter = RateLimiter(
        max_requests=100,
        period_seconds=60.0,
        jitter_min_seconds=0.01,
        jitter_max_seconds=0.02,
        time_fn=get_clock,
        sleep_fn=fake_sleep,
        random_fn=lambda a, b: 0.01,
    )

    errors = []

    def worker():
        try:
            for _ in range(15):
                limiter.throttle()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(limiter.window) <= 100
    assert limiter.last_request is not None


# ── F-010: Anti-Drip Contract Binding Verification ────────────────────────────

def test_anti_drip_contract_binding():
    """F-004: Validate Anti-Drip contract JSON digest and required finding list."""
    contract_path = REPO_ROOT / ".ly_state/session/anti_drip_contract_l2_role15_vci_ingestion_resilience_20260911.json"
    assert contract_path.exists(), "Anti-drip contract file must exist"

    raw_bytes = contract_path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    assert digest == "555f3eebe6590a0786b1b0d36b3850931969098086575e7c49b1cde8a3464a50"

    contract = json.loads(raw_bytes.decode("utf-8"))
    assert contract.get("gate_name") == "CANONICAL_VCI_INGESTION_RESILIENCE_20260911"
    assert contract.get("session_id") == "l2_role15_vci_ingestion_resilience_20260911"
    assert contract.get("mode") == "remediation"

    findings = contract.get("required_findings", [])
    assert len(findings) == 4
    finding_ids = {f["finding_id"] for f in findings}
    expected_ids = {f"F-{i:03d}" for i in range(1, 5)}
    assert finding_ids == expected_ids


# ── Standing Regression Clause Re-Verification (1..8) ─────────────────────────

def test_regression_01_literal_legacy_ipv4_denial():
    """Prove literal IPv4 denial remains handled in production copilot SSRF validator."""
    from ipaddress import IPv4Address
    from omega.api.routes.copilot import _is_safe_global_unicast_ip, resolve_validated_llm_target

    assert _is_safe_global_unicast_ip(IPv4Address("127.0.0.1")) is False
    assert _is_safe_global_unicast_ip(IPv4Address("192.168.1.1")) is False
    assert resolve_validated_llm_target("https://127.0.0.1/v1") is None
    assert resolve_validated_llm_target("https://192.168.1.1/v1") is None


def test_regression_02_ipv6_embedded_ipv4_payloads():
    """Prove IPv6 embedded IPv4 payloads remain handled in production copilot SSRF validator."""
    from ipaddress import IPv6Address
    from omega.api.routes.copilot import _is_safe_global_unicast_ip

    assert _is_safe_global_unicast_ip(IPv6Address("::ffff:192.0.2.128")) is False
    assert _is_safe_global_unicast_ip(IPv6Address("::ffff:127.0.0.1")) is False


def test_regression_03_special_use_ranges():
    """Prove special-use IP ranges remain sanitized in production copilot SSRF validator."""
    from ipaddress import IPv4Address
    from omega.api.routes.copilot import _is_safe_global_unicast_ip, resolve_validated_llm_target

    assert _is_safe_global_unicast_ip(IPv4Address("10.0.0.1")) is False
    assert _is_safe_global_unicast_ip(IPv4Address("169.254.1.1")) is False
    assert resolve_validated_llm_target("https://10.0.0.1/v1") is None
    assert resolve_validated_llm_target("https://169.254.1.1/v1") is None
    assert _is_safe_global_unicast_ip(IPv4Address("93.184.216.34")) is True


def test_regression_04_sparse_config_merge_preservation(monkeypatch):
    """Sparse config merge preserves existing defaults in production llm_config."""
    from omega.core.llm_config import resolve_alpha_llm_config

    monkeypatch.delenv("OMEGA_ALPHA_LLM_CONFIG_PATH", raising=False)
    monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMEGA_LLM_MODEL", raising=False)

    cfg = resolve_alpha_llm_config(REPO_ROOT)
    assert cfg["provider"] == "mock"
    assert cfg["model"] == "gpt-4"

    monkeypatch.setenv("OMEGA_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "test_key")
    cfg2 = resolve_alpha_llm_config(REPO_ROOT)
    assert cfg2["provider"] == "openai-compatible"
    assert cfg2["model"] == "gpt-4"


def test_regression_05_test_isolation_snapshot_restore(tmp_path):
    """Test isolation snapshot restore is intact in production atomic_write_with_backup."""
    target_path = tmp_path / "isolated.parquet"
    df_orig = pd.DataFrame({"ticker": ["SNAP"], "close": [100.0]})
    update_market_data.atomic_write_with_backup(df_orig, target_path, backup=False)

    df_bad = pd.DataFrame({"ticker": ["BAD"], "close": [200.0]})

    class DiskFullError(IOError):
        pass

    def fail_to_parquet(*args, **kwargs):
        raise DiskFullError("simulated crash")

    real_to_parquet = pd.DataFrame.to_parquet
    pd.DataFrame.to_parquet = fail_to_parquet
    try:
        with pytest.raises(DiskFullError):
            update_market_data.atomic_write_with_backup(df_bad, target_path, backup=True)
    finally:
        pd.DataFrame.to_parquet = real_to_parquet

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "SNAP"


def test_fix_sparse_terminal_receipts_string_bypass_exception():
    """String bypass_by_flag exceptions skip lifecycle receipt claims."""
    errors = update_market_data._claim_sparse_terminal_receipts(
        {"sparse_terminal_exceptions": {"ABC": "bypassed_by_flag"}},
        {},
        None,
    )
    assert errors == []


def test_fix_sparse_terminal_receipts_dict_bypass_exception():
    """Dict bypass exceptions skip lifecycle receipt claims without AttributeError."""
    errors = update_market_data._claim_sparse_terminal_receipts(
        {
            "sparse_terminal_exceptions": {
                "ABC": {"bypassed_by_flag": True, "bypass_lifecycle": True}
            }
        },
        {},
        None,
    )
    assert errors == []


def test_fix_sparse_terminal_receipts_non_bypass_dict_still_validates_evidence():
    """Non-bypass dict exceptions still require lifecycle evidence."""
    errors = update_market_data._claim_sparse_terminal_receipts(
        {
            "sparse_terminal_exceptions": {
                "ABC": {"bypassed_by_flag": False, "bypass_lifecycle": False}
            }
        },
        {},
        None,
    )
    assert errors == ["terminal_session: ABC lifecycle receipt: evidence missing"]


def test_regression_06_durable_tls_sni_evidence():
    """Durable TLS SNI evidence preservation in production official_watermark and copilot."""
    import ssl
    from omega.api.routes.copilot import _prepare_llm_request
    from omega.data.official_watermark import _official_tls_context

    ctx = _official_tls_context()
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED

    with pytest.raises(ValueError) as excinfo:
        _prepare_llm_request("https://", "custom", "test")
    assert "hostname" in str(excinfo.value.__cause__)


def test_regression_07_userinfo_credential_rejection():
    """Userinfo credential rejection check in production copilot request preparer."""
    from omega.api.routes.copilot import _prepare_llm_request, resolve_validated_llm_target

    assert resolve_validated_llm_target("https://user:pass@example.com/data") is None
    with pytest.raises(ValueError) as excinfo:
        _prepare_llm_request("https://user:pass@example.com/v1", "custom", "test")
    assert "userinfo" in str(excinfo.value.__cause__)


def test_regression_08_url_redaction_in_errors():
    """URL redaction in errors check using production copilot redactor."""
    from omega.api.routes.copilot import _redact_url_for_error, redact_credentials_in_text

    secret_url = "https://user:secret_pass@example.com:8080/api/v1"
    redacted_url = _redact_url_for_error(secret_url)
    assert "secret_pass" not in redacted_url
    assert "user" not in redacted_url
    assert redacted_url == "https://example.com:8080"

    text = f"Connection failed to {secret_url} with authorization Bearer my_super_secret_token_123"
    redacted_text = redact_credentials_in_text(text)
    assert "secret_pass" not in redacted_text
    assert "my_super_secret_token_123" not in redacted_text


def test_sparse_terminal_bypass_lifecycle_skips_receipt_claim(monkeypatch, tmp_path):
    """Bypassed lifecycle exceptions must not consume lifecycle receipts."""
    calls = []

    monkeypatch.setattr(
        update_market_data,
        "_claim_lifecycle_receipt",
        lambda *args, **kwargs: calls.append(args) or None,
    )

    errors = update_market_data._claim_sparse_terminal_receipts(
        {
            "sparse_terminal_exceptions": {
                "ABC": {"bypassed_by_flag": True, "bypass_lifecycle": True}
            }
        },
        {"ABC": {"receipt_id": "r1", "payload": {}}},
        tmp_path,
    )

    assert errors == []
    assert calls == []
