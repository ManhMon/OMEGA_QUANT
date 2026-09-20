from datetime import date, datetime, timezone

import pytest

from omega.data.interbank_rate_snapshot import (
    build_snapshot,
    fetch_with_fallback,
    latest_vintage,
    load_snapshots,
    save_snapshot,
)


VALID_VINTAGE = datetime(2026, 9, 14, 10, tzinfo=timezone.utc)


def test_build_snapshot_pit_available_time():
    snapshot = build_snapshot(date(2026, 9, 12), "overnight", "primary", 3.5, vintage_at=VALID_VINTAGE)
    assert snapshot.available_at.hour == 2
    assert snapshot.available_at.date() == date(2026, 9, 14)
    assert snapshot.available_at.tzinfo == timezone.utc


def test_build_snapshot_rejects_early_vintage():
    with pytest.raises(ValueError):
        build_snapshot(
            date(2026, 9, 12),
            "overnight",
            "primary",
            3.5,
            vintage_at=datetime(2026, 9, 14, 1, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), -1.0, 101.0])
def test_build_snapshot_rejects_invalid_numeric_rates(rate):
    with pytest.raises(ValueError):
        build_snapshot(date(2026, 9, 12), "overnight", "primary", rate, vintage_at=VALID_VINTAGE)


def test_build_snapshot_rejects_invalid_tenor():
    with pytest.raises(ValueError):
        build_snapshot(date(2026, 9, 12), "", "primary", 3.5, vintage_at=VALID_VINTAGE)


def test_secondary_provider_fallback_records_reason():
    snapshot = fetch_with_fallback(
        lambda: (_ for _ in ()).throw(RuntimeError("primary down")),
        lambda: build_snapshot(date(2026, 9, 12), "overnight", "secondary", 3.6, vintage_at=VALID_VINTAGE),
    )
    assert snapshot.provider == "secondary"
    assert snapshot.fallback_reason == "primary down"


def test_both_providers_fail_closed():
    with pytest.raises(RuntimeError):
        fetch_with_fallback(
            lambda: (_ for _ in ()).throw(RuntimeError("primary")),
            lambda: (_ for _ in ()).throw(RuntimeError("secondary")),
        )


def test_latest_vintage_selection():
    older = build_snapshot(date(2026, 9, 12), "overnight", "primary", 3.5, vintage_at=VALID_VINTAGE)
    newer = build_snapshot(
        date(2026, 9, 12),
        "overnight",
        "secondary",
        3.6,
        vintage_at=datetime(2026, 9, 14, 11, tzinfo=timezone.utc),
    )
    assert latest_vintage([older, newer]) == newer


def test_save_and_load_snapshot_atomic_persistence(tmp_path):
    path = tmp_path / "snapshots.json"
    original = build_snapshot(date(2026, 9, 12), "overnight", "primary", 3.5, vintage_at=VALID_VINTAGE)
    save_snapshot(path, [original])
    restored = load_snapshots(path)
    assert restored == [original]
    assert path.exists()


def test_load_snapshots_revalidates_corrupt_pit_payload(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("[{\"rate_date\": \"2026-09-12\", \"tenor\": \"overnight\", "
                    "\"rate\": 3.5, \"provider\": \"primary\", "
                    "\"vintage_at\": \"2026-09-14T10:00:00+00:00\", "
                    "\"available_at\": \"2026-09-12T09:00:00+00:00\"}]", encoding="utf-8")
    with pytest.raises(ValueError, match="PIT calendar"):
        load_snapshots(path)


def test_load_snapshots_rejects_naive_temporal_payload(tmp_path):
    path = tmp_path / "naive.json"
    path.write_text("[{\"rate_date\": \"2026-09-14\", \"tenor\": \"overnight\", "
                    "\"rate\": 3.5, \"provider\": \"primary\", "
                    "\"vintage_at\": \"2026-09-14T10:00:00\", "
                    "\"available_at\": \"2026-09-14T09:00:00+00:00\"}]", encoding="utf-8")
    with pytest.raises(ValueError, match="timezone-aware"):
        load_snapshots(path)
