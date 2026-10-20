"""Contract tests for PEAD drift features and the earnings ledger."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import itertools
import json
import math
import sqlite3
import statistics
import threading

import pandas as pd
import pytest

_DEFAULT_CONSENSUS = object()

from omega.data.earnings_ledger import (
    AccountingBasis,
    ConsensusEstimate,
    EarningsAnnouncement,
    EarningsLedger,
)
from omega.quant.strategy.pead_drift import (
    PEADDriftEngine,
    drift_decay,
    standardized_surprise,
)

ICT = timezone(timedelta(hours=7))
HASH = "a" * 64
BASIS = AccountingBasis()


def make_consensus(
    issuer: str,
    year: int,
    quarter: int,
    basis: AccountingBasis = BASIS,
    value: float = 100.0,
    *,
    announced_at: datetime | None = None,
    verified: bool = True,
    **changes,
) -> ConsensusEstimate:
    announced_at = announced_at or datetime(year + 1, 1, 15, 9, tzinfo=ICT)
    defaults = dict(
        value=value,
        vintage_at=announced_at - timedelta(hours=3),
        available_at=announced_at - timedelta(hours=2),
        source_id="consensus-source",
        sample_count=5,
        evidence_sha256=HASH,
        verified=verified,
        issuer=issuer,
        fiscal_year=year,
        fiscal_quarter=quarter,
        basis=basis,
    )
    defaults.update(changes)
    return ConsensusEstimate(**defaults)


def make_event(
    issuer: str = "AAA",
    year: int = 2024,
    quarter: int = 4,
    actual: float = 100.0,
    *,
    release_id: str | None = None,
    revision: int = 0,
    basis: AccountingBasis = BASIS,
    announced_at: datetime | None = None,
    ready_at: datetime | None = None,
    consensus=_DEFAULT_CONSENSUS,
    verified: bool = True,
    **changes,
) -> EarningsAnnouncement:
    announced_at = announced_at or datetime(year + 1, 1, 15, 9, tzinfo=ICT)
    defaults = dict(
        issuer=issuer,
        fiscal_year=year,
        fiscal_quarter=quarter,
        release_id=release_id or f"{year}Q{quarter}",
        revision=revision,
        actual=actual,
        basis=basis,
        announced_at=announced_at,
        available_at=announced_at + timedelta(minutes=1),
        first_seen_at=announced_at + timedelta(minutes=2),
        ingested_at=announced_at + timedelta(minutes=3),
        ready_at=ready_at or announced_at + timedelta(minutes=4),
        source_id="exchange-source",
        evidence_sha256=HASH,
        verified=verified,
        consensus=None if consensus is _DEFAULT_CONSENSUS else consensus,
    )
    defaults.update(changes)
    if consensus is _DEFAULT_CONSENSUS:
        defaults["consensus"] = make_consensus(
            issuer, year, quarter, basis, announced_at=announced_at
        )
    return EarningsAnnouncement(**defaults)


@pytest.fixture
def ledger_factory():
    opened = []

    def create(events=()):
        ledger = EarningsLedger(events=events)
        opened.append(ledger)
        return ledger

    yield create
    for ledger in opened:
        ledger.close()


def test_ledger_dataclasses_reject_invalid_numbers_timestamps_and_basis():
    for value in (None, [], True, float("nan"), float("inf"), -float("inf"), "100", 1e12 + 1, 10**1000):
        with pytest.raises((TypeError, ValueError)):
            make_event(actual=value)
    with pytest.raises((TypeError, ValueError)):
        make_consensus("AAA", 2024, 4, value=1e12 + 1)

    event = make_event()
    for field in ("announced_at", "available_at", "first_seen_at", "ingested_at", "ready_at"):
        with pytest.raises((TypeError, ValueError)):
            replace(event, **{field: datetime(2025, 1, 15, 9)})

    for field, invalid in (
        ("available_at", event.announced_at - timedelta(seconds=1)),
        ("first_seen_at", event.available_at - timedelta(seconds=1)),
        ("ingested_at", event.first_seen_at - timedelta(seconds=1)),
        ("ready_at", event.ingested_at - timedelta(seconds=1)),
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(event, **{field: invalid})
    with pytest.raises((TypeError, ValueError)):
        AccountingBasis(audited=1)
    with pytest.raises((TypeError, ValueError)):
        AccountingBasis(metric="OTHER")
    with pytest.raises((TypeError, ValueError)):
        make_event(revision=1001)


def test_events_are_immutable_and_revisions_have_distinct_ids():
    first = make_event(release_id="release-1", revision=0)
    second = make_event(release_id="release-1", revision=1, actual=101.0)
    assert first.event_id == "AAA:release-1:0"
    assert second.event_id == "AAA:release-1:1"
    with pytest.raises(FrozenInstanceError):
        first.actual = 0
    with pytest.raises(FrozenInstanceError):
        first.basis.metric = "REVENUE"


def test_ledger_rejects_paths_outside_repository_root(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    with pytest.raises((ValueError, OSError)):
        EarningsLedger(path="../outside.sqlite3")
    with pytest.raises((ValueError, OSError)):
        EarningsLedger(path=str(tmp_path / "absolute.sqlite3"))


def test_ledger_replay_revision_snapshot_and_sqlite_reopen(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    path = "earnings.sqlite3"
    first = make_event(release_id="release-2", revision=0)
    revised = make_event(release_id="release-2", revision=1, actual=105.0, ready_at=datetime(2025, 1, 15, 9, 5, tzinfo=ICT))
    before_ready = first.ready_at - timedelta(microseconds=1)

    with EarningsLedger(path=path) as ledger:
        assert ledger.append(first) is True
        assert ledger.append(first) is False
        assert ledger.append(revised) is True
        assert ledger.snapshot(as_of=before_ready) == ()
        assert len(ledger.snapshot(as_of=first.ready_at)) == 1
        assert ledger.snapshot(as_of=first.ready_at)[0].event_id == first.event_id
        assert set(ledger.snapshot()) == {first, revised}

    with EarningsLedger(path=path) as reopened:
        assert set(reopened.snapshot()) == {first, revised}


def test_ledger_rejects_corrupt_schema_and_payload_digest(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    path = "corrupt.sqlite3"
    event = make_event(release_id="corrupt", revision=0)
    with EarningsLedger(path=path, events=(event,)) as ledger:
        pass
    database = tmp_path / path
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE events SET digest = ?", ("0" * 64,))
    with pytest.raises(ValueError, match="checksum"):
        EarningsLedger(path=path)

    schema_path = "bad-schema.sqlite3"
    with sqlite3.connect(tmp_path / schema_path) as connection:
        connection.execute("CREATE TABLE events (event_id TEXT)")
    with pytest.raises(ValueError, match="schema"):
        EarningsLedger(path=schema_path)


def test_append_many_is_atomic_on_conflict(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    path = "atomic.sqlite3"
    existing = make_event(release_id="kept", revision=0)
    conflicting = replace(existing, actual=existing.actual + 1)
    pending = make_event(release_id="must-rollback", revision=0)
    with EarningsLedger(path=path) as ledger:
        ledger.append(existing)
        with pytest.raises((ValueError, RuntimeError)):
            ledger.append(conflicting)
        with pytest.raises((ValueError, RuntimeError)):
            ledger.append_many((pending, conflicting))
        assert ledger.snapshot() == (existing,)


def test_append_many_bounds_generator_consumption(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(ledger_module, "_MAX_EVENTS", 2)
    consumed = []

    def events():
        for i in range(4):
            consumed.append(i)
            yield make_event(issuer=f"A{i}", release_id=f"bounded-{i}")

    with EarningsLedger(path="bounded.sqlite3") as ledger:
        with pytest.raises(ValueError, match="batch exceeds"):
            ledger.append_many(events())
        assert consumed == [0, 1, 2]
        assert ledger.snapshot() == ()


def test_ledger_lock_timeout_fails_without_partial_write(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(ledger_module, "_LOCK_TIMEOUT", 0.02)
    acquired, release = threading.Event(), threading.Event()
    with EarningsLedger(path="locked.sqlite3") as ledger:
        def hold_lock():
            with ledger._lock:
                acquired.set()
                release.wait(timeout=2)

        worker = threading.Thread(target=hold_lock)
        worker.start()
        assert acquired.wait(timeout=2)
        with pytest.raises(TimeoutError):
            ledger.append(make_event(release_id="blocked"))
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert ledger.snapshot() == ()


def test_runtime_database_file_replacement_is_rejected(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    with EarningsLedger(path="runtime.sqlite3") as ledger:
        ledger._connection.close()  # Windows denies replacement while SQLite owns the handle.
        (tmp_path / "runtime.sqlite3").replace(tmp_path / "moved.sqlite3")
        (tmp_path / "runtime.sqlite3").write_bytes(b"replacement")
        ledger._connection = sqlite3.connect(":memory:", isolation_level=None)
        with pytest.raises(ValueError, match="identity changed"):
            ledger.snapshot()


def test_concurrent_duplicate_appends_are_idempotent(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as ledger_module

    monkeypatch.setattr(ledger_module, "REPO_ROOT", tmp_path, raising=False)
    path = "concurrent.sqlite3"
    event = make_event(release_id="concurrent", revision=0)

    def append_once(_):
        with EarningsLedger(path=path) as ledger:
            return ledger.append(event)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(append_once, range(16)))
    assert sum(outcomes) == 1
    with EarningsLedger(path=path) as ledger:
        assert ledger.snapshot() == (event,)


def test_ledger_validates_consensus_identity_and_all_clock_ordering():
    event = make_event()
    consensus = event.consensus
    for changes in (
        {"vintage_at": event.announced_at + timedelta(seconds=1)},
        {"available_at": event.announced_at},
        {"issuer": "OTHER"},
        {"fiscal_year": event.fiscal_year - 1},
        {"basis": replace(BASIS, metric="REVENUE")},
        {"sample_count": 0},
        {"verified": 1},
    ):
        with pytest.raises((TypeError, ValueError)):
            candidate = replace(consensus, **changes)
            replace(event, consensus=candidate)


def test_standardized_surprise_uses_latest_20_sample_errors_and_clips():
    errors = list(range(25))
    result = standardized_surprise(1000.0, 0.0, errors)
    expected_sigma = statistics.stdev(errors[-20:])
    assert math.isclose(result.sigma, expected_sigma, rel_tol=1e-12)
    assert result.value == 5.0
    assert math.isclose(result.raw, 1000.0 / expected_sigma, rel_tol=1e-12)
    assert standardized_surprise(1.0, 0.0, errors[:7]).reason == "insufficient_history"
    eight = standardized_surprise(1.0, 0.0, range(8))
    assert math.isclose(eight.sigma, statistics.stdev(range(8)), rel_tol=1e-12)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")], ids=["boolean", "nan", "infinity"])
def test_standardized_surprise_rejects_non_finite_or_boolean_inputs(value):
    with pytest.raises((TypeError, ValueError)):
        standardized_surprise(value, 0.0, range(8))


def test_drift_decay_clips_halves_and_expires():
    assert drift_decay(8.0, 0) == 5.0
    assert math.isclose(drift_decay(4.0, 20), 2.0, rel_tol=1e-12)
    assert math.isclose(drift_decay(-8.0, 20), -2.5, rel_tol=1e-12)
    assert drift_decay(5.0, 59) > 0
    assert drift_decay(5.0, 60) == 0.0
    with pytest.raises((TypeError, ValueError)):
        drift_decay(float("nan"), 0)


def test_sue_and_sec_use_prior_only_history_and_sample_sigma(ledger_factory):
    events = []
    actual_by_year = {}
    error_by_year = {}
    for year in range(2000, 2025):
        actual = 100.0 + (year - 2000) ** 2 + (year % 3)
        error = float((year % 7) - 3)
        actual_by_year[year] = actual
        error_by_year[year] = error
        announced = datetime(year + 1, 1, 15, 9, tzinfo=ICT)
        events.append(make_event(
            year=year,
            quarter=4,
            actual=actual,
            announced_at=announced,
            consensus=make_consensus(
                "AAA", year, 4, value=actual - error, announced_at=announced
            ),
        ))

    current = events[-1]
    result = PEADDriftEngine(ledger_factory(events)).event_surprises(current)
    sue_errors = [error_by_year[year] for year in range(2004, 2024)]
    sec_changes = [
        actual_by_year[year] - actual_by_year[year - 1]
        for year in range(2004, 2024)
    ]
    assert set(result) == {"sue", "sec"}
    assert math.isclose(result["sue"].sigma, statistics.stdev(sue_errors), rel_tol=1e-12)
    assert math.isclose(
        result["sue"].raw,
        error_by_year[2024] / statistics.stdev(sue_errors),
        rel_tol=1e-12,
    )
    assert math.isclose(result["sec"].sigma, statistics.stdev(sec_changes), rel_tol=1e-12)
    assert math.isclose(
        result["sec"].raw,
        (actual_by_year[2024] - actual_by_year[2023]) / statistics.stdev(sec_changes),
        rel_tol=1e-12,
    )


def test_surprise_consensus_must_be_verified_and_comparable(ledger_factory):
    event = make_event(year=2024, quarter=4)
    engine = PEADDriftEngine(ledger_factory((event,)))
    unverified = replace(event, consensus=replace(event.consensus, verified=False))
    assert PEADDriftEngine(ledger_factory((unverified,))).event_surprises(unverified)["sue"].reason == "unverified_consensus"
    with pytest.raises(ValueError, match="identity and basis"):
        replace(event, consensus=replace(event.consensus, issuer="BBB"))
    announced = event.announced_at
    stale = replace(
        event,
        consensus=None,
    )
    with pytest.raises(ValueError):
        replace(stale, consensus=replace(event.consensus, available_at=announced))


def test_cumulative_revenue_and_income_normalize_but_cumulative_eps_does_not():
    from omega.quant.strategy.pead_drift import _normalized_actual

    cumulative = replace(BASIS, period_basis="cumulative", metric="REVENUE")
    q1 = make_event(year=2024, quarter=1, actual=100.0, basis=cumulative)
    q2 = make_event(year=2024, quarter=2, actual=250.0, basis=cumulative)
    q3 = make_event(year=2024, quarter=3, actual=400.0, basis=cumulative)
    assert _normalized_actual(q2, (q1, q2), q2.ready_at)[:2] == (150.0, None)
    assert _normalized_actual(q3, (q1, q2, q3), q3.ready_at)[:2] == (150.0, None)

    net_income = replace(cumulative, metric="NET_INCOME")
    ni_q1 = make_event(year=2024, quarter=1, actual=50.0, basis=net_income)
    ni_q2 = make_event(year=2024, quarter=2, actual=120.0, basis=net_income)
    assert _normalized_actual(ni_q2, (ni_q1, ni_q2), ni_q2.ready_at)[:2] == (70.0, None)

    eps = replace(cumulative, metric="EPS")
    eps_q2 = make_event(year=2024, quarter=2, actual=3.0, basis=eps)
    assert _normalized_actual(eps_q2, (eps_q2,), eps_q2.ready_at)[:2] == (None, "unsupported_basis")


def make_panel(rows):
    index = pd.MultiIndex.from_tuples(rows, names=("date", "symbol"))
    return pd.DataFrame({"close": range(100, 100 + len(rows))}, index=index)


def test_features_are_issuer_aligned_strictly_next_session_and_cutoff_inclusive(ledger_factory):
    ready = datetime(2024, 1, 2, 9, 0, tzinfo=ICT)
    event = make_event(
        year=2023,
        quarter=4,
        announced_at=ready - timedelta(minutes=4),
        ready_at=ready,
    )
    ledger = ledger_factory((event,))
    engine = PEADDriftEngine(ledger)
    trading = {date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 5)}
    engine._calendar_day = lambda day: day in trading
    panel = make_panel([
        (date(2024, 1, 2), "AAA"),
        (date(2024, 1, 3), "AAA"),
        (date(2024, 1, 3), "BBB"),
    ])
    result = engine.features(panel)
    assert result.loc[(date(2024, 1, 2), "AAA"), "pead_sue_reason"] == "awaiting_entry"
    assert result.loc[(date(2024, 1, 3), "AAA"), "pead_age_sessions"] == 0
    assert result.loc[(date(2024, 1, 3), "BBB"), "pead_sue_reason"] == "no_event"
    assert result.index.equals(panel.index)


def test_announcement_after_open_is_excluded_and_latest_invalid_blocks_fallback(ledger_factory):
    row_date = date(2024, 2, 5)
    valid = make_event(
        year=2023,
        quarter=4,
        release_id="same-release",
        revision=0,
        announced_at=datetime(2024, 2, 2, 8, 0, tzinfo=ICT),
        ready_at=datetime(2024, 2, 2, 8, 4, tzinfo=ICT),
    )
    invalid_latest = make_event(
        year=2023,
        quarter=4,
        release_id="same-release",
        revision=1,
        announced_at=datetime(2024, 2, 2, 8, 1, tzinfo=ICT),
        ready_at=datetime(2024, 2, 2, 8, 5, tzinfo=ICT),
        consensus=None,
    )
    unknown = make_event(
        issuer="BBB",
        year=2023,
        quarter=4,
        announced_at=datetime(2024, 2, 5, 9, 1, tzinfo=ICT),
        ready_at=datetime(2024, 2, 5, 9, 5, tzinfo=ICT),
    )
    engine = PEADDriftEngine(ledger_factory((valid, invalid_latest, unknown)))
    engine._calendar_day = lambda day: day in {date(2024, 2, 5), date(2024, 2, 6)}
    panel = make_panel([(row_date, "AAA"), (row_date, "BBB")])
    result = engine.features(panel)
    assert result.loc[(row_date, "AAA"), "pead_sue_reason"] == "missing_consensus"
    assert result.loc[(row_date, "BBB"), "pead_sue_reason"] == "no_event"


def test_entry_skips_holiday_after_premarket_readiness(ledger_factory):
    ready = datetime(2024, 1, 5, 8, 30, tzinfo=ICT)
    event = make_event(year=2023, quarter=4, announced_at=ready - timedelta(minutes=4), ready_at=ready)
    engine = PEADDriftEngine(ledger_factory((event,)))
    engine._calendar_day = lambda day: day in {date(2024, 1, 5), date(2024, 1, 9)}
    panel = make_panel([
        (date(2024, 1, 5), "AAA"),
        (date(2024, 1, 8), "AAA"),
        (date(2024, 1, 9), "AAA"),
    ])
    features = engine.features(panel)
    assert features.loc[(date(2024, 1, 5), "AAA"), "pead_sue_reason"] == "awaiting_entry"
    assert features.loc[(date(2024, 1, 8), "AAA"), "pead_sue_reason"] == "non_trading_day"
    assert features.loc[(date(2024, 1, 9), "AAA"), "pead_age_sessions"] == 0


def test_after_hours_readiness_enters_following_session_inclusive_at_cutoff(ledger_factory):
    ready = datetime(2024, 1, 5, 15, 30, tzinfo=ICT)
    event = make_event(year=2023, quarter=4, announced_at=ready - timedelta(minutes=4), ready_at=ready)
    engine = PEADDriftEngine(ledger_factory((event,)))
    engine._calendar_day = lambda day: day in {date(2024, 1, 5), date(2024, 1, 8)}
    panel = make_panel([(date(2024, 1, 5), "AAA"), (date(2024, 1, 8), "AAA")])
    features = engine.features(panel)
    assert features.loc[(date(2024, 1, 5), "AAA"), "pead_sue_reason"] == "no_event"
    assert features.loc[(date(2024, 1, 8), "AAA"), "pead_age_sessions"] == 0


def test_features_exclude_announcements_not_ready_by_as_of(ledger_factory):
    announced = datetime(2024, 1, 8, 8, 59, tzinfo=ICT)
    ready = datetime(2024, 1, 8, 9, 0, 40, tzinfo=ICT)
    event = make_event(
        year=2023,
        quarter=4,
        announced_at=announced,
        available_at=announced + timedelta(seconds=10),
        first_seen_at=announced + timedelta(seconds=20),
        ingested_at=announced + timedelta(seconds=30),
        ready_at=ready,
    )
    engine = PEADDriftEngine(ledger_factory((event,)))
    engine._calendar_day = lambda day: True
    panel = make_panel([(date(2024, 1, 8), "AAA")])
    as_of = datetime(2024, 1, 8, 9, 0, tzinfo=ICT)
    features = engine.features(panel, as_of=as_of)
    assert features.iloc[0]["pead_sue_reason"] == "no_event"


def test_fetcher_pead_is_opt_in_and_default_feature_registry_stays_14(ledger_factory):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    disabled = AlternativeDataFetcher(use_api=False)
    enabled = AlternativeDataFetcher(use_api=False, earnings_ledger=ledger_factory())
    assert len(disabled.get_feature_names()) == 14
    assert len(enabled.get_feature_names()) == 19
    assert enabled.get_feature_names()[-5:] == [
        "pead_sue",
        "pead_sec",
        "pead_sue_drift",
        "pead_sec_drift",
        "pead_age_sessions",
    ]
    empty = make_panel([])
    with pytest.raises(ValueError):
        disabled.get_pead_features(make_panel([(date(2024, 1, 2), "AAA")]))
    with pytest.raises(ValueError):
        disabled.get_pead_features(empty)
    assert enabled.get_pead_features(empty).empty
    assert enabled.generate_all(empty).empty


def test_fetcher_joins_pead_without_network_and_preserves_panel_rows(monkeypatch, ledger_factory):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    fetcher = AlternativeDataFetcher(use_api=False, earnings_ledger=ledger_factory())
    rows = [
        (date(2024, 1, 3), "BBB"),
        (date(2024, 1, 2), "AAA"),
        (date(2024, 1, 3), "AAA"),
        (date(2024, 1, 2), "BBB"),
    ]
    panel = pd.DataFrame(
        {"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0, "input_tag": range(4)},
        index=pd.MultiIndex.from_tuples(rows, names=("date", "symbol")),
    )
    for name in (
        "get_foreign_flow_proxy",
        "get_margin_proxy",
        "get_sector_rotation_proxy",
        "get_order_imbalance_proxy",
        "get_liquidity_shock_proxy",
    ):
        monkeypatch.setattr(fetcher, name, lambda frame: pd.Series(0.0, index=frame.index))
    monkeypatch.setattr(
        fetcher,
        "_derive_sentiment_indicators",
        lambda frame: (pd.Series(50.0, index=frame.index), pd.Series(20.0, index=frame.index)),
    )
    monkeypatch.setattr(
        fetcher,
        "get_macro_bitemporal_features",
        lambda frame, rows: pd.DataFrame(index=pd.DatetimeIndex([])),
    )
    fetcher.pead_engine._calendar_day = lambda day: True

    result = fetcher.generate_all(panel)
    assert result.index.equals(panel.sort_index().index), "generate_all preserves its sorted index contract"
    pd.testing.assert_series_equal(result["input_tag"], panel["input_tag"].sort_index())
    assert {"pead_sue", "pead_sec", "pead_sue_drift", "pead_sec_drift", "pead_age_sessions"} <= set(result)


@pytest.mark.parametrize("operation,error", [("INSERT INTO events", RuntimeError), ("COMMIT", RuntimeError), ("INSERT INTO events", KeyboardInterrupt)], ids=["insert-runtime-error", "commit-runtime-error", "insert-keyboard-interrupt"])
def test_sql_failures_roll_back_and_allow_retry(ledger_factory, operation, error):
    ledger = ledger_factory()
    connection = ledger._connection

    class FaultConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, sql, *args):
            if sql.startswith(operation):
                raise error("injected storage failure")
            return connection.execute(sql, *args)

    ledger._connection = FaultConnection()
    event = make_event()
    try:
        with pytest.raises(error):
            ledger.append(event)
        assert not connection.in_transaction, "failed transaction must be rolled back"
    finally:
        ledger._connection = connection
    assert ledger.snapshot() == (), "failed write cannot publish a partial event"
    assert ledger.append(event), "ledger remains usable after rollback"


@pytest.mark.parametrize("mutation", ["bom", "crlf", "duplicate", "unexpected"], ids=["bom", "crlf", "duplicate", "unexpected"])
def test_rehashed_noncanonical_payloads_fail_closed(tmp_path, monkeypatch, mutation):
    import omega.data.earnings_ledger as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    with EarningsLedger("payload.sqlite", events=(make_event(),)):
        pass
    with sqlite3.connect(tmp_path / "payload.sqlite") as connection:
        payload = connection.execute("SELECT payload FROM events").fetchone()[0]
        if mutation == "bom":
            payload = "﻿" + payload
        elif mutation == "crlf":
            payload = payload.replace(",", ",\r\n", 1)
        elif mutation == "duplicate":
            payload = '{"actual":1,' + payload[1:]
        else:
            item = json.loads(payload)
            item["unexpected"] = 1
            payload = json.dumps(item)
        connection.execute("UPDATE events SET payload=?,digest=?", (payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        EarningsLedger("payload.sqlite")


def test_directory_truncated_database_and_closed_empty_batch_fail(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    (tmp_path / "directory").mkdir()
    with pytest.raises(ValueError):
        EarningsLedger("directory")
    (tmp_path / "truncated.sqlite").write_bytes(b"SQLite format 3\x00partial")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        EarningsLedger("truncated.sqlite")
    ledger = EarningsLedger()
    ledger.close()
    with pytest.raises(ValueError, match="closed"):
        ledger.append_many(())


@pytest.mark.parametrize("kwargs", [{"half_life_sessions": 0}, {"half_life_sessions": -1}, {"half_life_sessions": float("inf")}, {"age_sessions": -1}, {"age_sessions": True}, {"max_age_sessions": 0}], ids=["zero-half-life", "negative-half-life", "infinite-half-life", "negative-age", "boolean-age", "zero-max-age"])
def test_decay_rejects_invalid_parameters(kwargs):
    parameters = {"surprise": 1, "age_sessions": 0}
    parameters.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        drift_decay(**parameters)


def test_sigma_guard_negative_eps_and_bounded_history():
    for history in ([0] * 8, [1e-14 * value for value in range(8)]):
        result = standardized_surprise(-2, -1, history)
        assert result.value is None and result.reason == "near_zero_sigma", "zero sigma must remain unavailable"
    assert standardized_surprise(-2, -1, range(8)).value < 0, "negative EPS is valid"
    with pytest.raises(ValueError, match="10000"):
        standardized_surprise(1, 0, itertools.repeat(0))
    with pytest.raises((TypeError, ValueError)):
        standardized_surprise(1, 0, [10**1000] * 8)


def test_identifiers_units_and_period_bounds():
    for issuer in ("aaa", "A;exit", "A" * 13, None):
        with pytest.raises(ValueError):
            make_event(issuer=issuer)
    for field, value in (("unit", "VND_THOUSAND"), ("currency", "USD"), ("scope", "unknown")):
        with pytest.raises(ValueError):
            replace(BASIS, **{field: value})
    for changes in ({"fiscal_year": 1899}, {"fiscal_quarter": 0}, {"release_id": "--flag;exit"}, {"source_id": "../source/"}):
        with pytest.raises(ValueError):
            replace(make_event(), **changes)


def history_events():
    events = []
    for year in range(2010, 2025):
        announced = datetime(year + 1, 1, 2, 8, tzinfo=ICT)
        value = 100 + (year - 2010) ** 2
        events.append(make_event(year=year, actual=value, announced_at=announced,
            consensus=make_consensus("AAA", year, 4, value=value - (year % 7 - 3), announced_at=announced)))
    return events


def test_eligible_history_gaps_and_future_revisions_do_not_leak(ledger_factory):
    events = history_events()
    for index in (2, 4, 6, 8, 10):
        events[index] = replace(events[index], consensus=None)
    current = events[-1]
    ledger = ledger_factory(events)
    engine = PEADDriftEngine(ledger)
    before = engine.event_surprises(current)
    eligible = [event.actual - event.consensus.value for event in events[:-1] if event.consensus]
    assert math.isclose(before["sue"].sigma, statistics.stdev(eligible)), "eligible older samples must survive recent gaps"
    revised = replace(events[0], revision=1, actual=1e6, ready_at=current.ready_at + timedelta(days=1))
    future = make_event(year=2025, actual=1e6)
    ledger.append_many((revised, future))
    assert engine.event_surprises(current) == before, "later revisions/fiscal periods cannot rewrite old surprises"
    selected = set(before["sec"].history_ids)
    assert events[-2].event_id in selected, "seasonal sample lineage includes current member of each pair"
    with pytest.raises(ValueError, match="not present"):
        engine.event_surprises(replace(current, actual=current.actual + 1))


def test_premarket_replacement_sparse_age_and_expiry(ledger_factory):
    events = history_events()
    current = events[-1]
    revised = replace(current, revision=1, announced_at=datetime(2025, 1, 3, 8, tzinfo=ICT),
        available_at=datetime(2025, 1, 3, 8, 1, tzinfo=ICT), first_seen_at=datetime(2025, 1, 3, 8, 2, tzinfo=ICT),
        ingested_at=datetime(2025, 1, 3, 8, 3, tzinfo=ICT), ready_at=datetime(2025, 1, 3, 8, 4, tzinfo=ICT), consensus=None)
    engine = PEADDriftEngine(ledger_factory(events + [revised]), max_age_sessions=2)
    engine._calendar_day = lambda day: day.weekday() < 5
    panel = make_panel([(date(2025, 1, 3), "AAA"), (date(2025, 1, 6), "AAA")])
    result = engine.features(panel)
    assert bool(result.iloc[0]["pead_sue_valid"]), "new premarket event cannot suppress yesterday's eligible event"
    assert result.iloc[1]["pead_sue_reason"] == "missing_consensus", "replacement blocks stale fallback once eligible"
    old_engine = PEADDriftEngine(ledger_factory(events), max_age_sessions=2)
    old_engine._calendar_day = lambda day: day.weekday() < 5
    sparse = old_engine.features(make_panel([(date(2025, 1, 3), "AAA"), (date(2025, 1, 7), "AAA")]))
    assert sparse.iloc[1]["pead_age_sessions"] == 2, "age counts missing trading sessions, not panel rows"
    assert sparse.iloc[1]["pead_sue_drift"] == 0 and sparse.iloc[1]["pead_sue_reason"] == "expired", "bounded holding expires"


def test_panel_validation_calendar_and_provenance(ledger_factory):
    event = make_event()
    unknown = replace(event, announced_at=None)
    unverified = replace(event, verified=False)
    for candidate, reason in ((unknown, "unknown_announcement"), (unverified, "unverified")):
        engine = PEADDriftEngine(ledger_factory((candidate,)))
        assert engine.event_surprises(candidate)["sue"].reason == reason, "no inherited verification"
    engine = PEADDriftEngine(ledger_factory((event,)))
    unavailable = engine.features(make_panel([(date(2101, 1, 3), "AAA")]))
    assert unavailable.iloc[0]["pead_sue_reason"] == "calendar_unavailable", "no holiday fallback outside coverage"
    for labels in (["2025-01-16", "2025-01-16T00:00:00"], [datetime(2025, 1, 16, 12)], ["2025-01-16T12:00:00"]):
        with pytest.raises((TypeError, ValueError)):
            engine.features(make_panel([(label, "AAA") for label in labels]))
    for symbol in ("aaa", "A;exit", None):
        with pytest.raises((TypeError, ValueError)):
            engine.features(make_panel([(date(2025, 1, 16), symbol)]))
    cutoff = datetime(2025, 1, 16, 9, tzinfo=ICT)
    row = make_panel([(cutoff.date(), "AAA")])
    assert engine.features(row, as_of=cutoff).iloc[0]["pead_age_sessions"] == 0, "inclusive session-open cutoff"
    assert engine.features(row, as_of=cutoff - timedelta(microseconds=1)).iloc[0]["pead_sue_reason"] == "before_session_open", "no future session row"


def test_cumulative_surprises_use_matching_actual_predecessor_and_quarterly_changes(ledger_factory):
    basis = replace(BASIS, metric="NET_INCOME", period_basis="cumulative")
    events, quarterly, errors = [], [], []
    for year in range(2018, 2025):
        cumulative = 0
        for quarter in range(1, 5):
            position = len(quarterly)
            actual = 100 + position**2
            quarterly.append(actual)
            cumulative += actual
            error = position % 9 - 4
            errors.append(error)
            announced = datetime(year + (quarter == 4), 1 if quarter == 4 else quarter * 3 + 1, 10, 8, tzinfo=ICT)
            consensus = make_consensus("AAA", year, quarter, basis, cumulative - error, announced_at=announced)
            events.append(make_event(year=year, quarter=quarter, basis=basis, actual=cumulative,
                announced_at=announced, consensus=consensus))
    result = PEADDriftEngine(ledger_factory(events)).event_surprises(events[-1])
    expected_sue = errors[-1] / statistics.stdev(errors[:-1][-20:])
    changes = [quarterly[index] - quarterly[index - 4] for index in range(4, len(quarterly) - 1)]
    expected_sec = (quarterly[-1] - quarterly[-5]) / statistics.stdev(changes[-20:])
    assert math.isclose(result["sue"].raw, expected_sue), "cumulative actual and consensus subtract same prior actual"
    assert math.isclose(result["sec"].raw, expected_sec), "seasonal denominator includes quarterly year-over-year changes"
    assert events[-2].event_id in result["sue"].history_ids, "normalization dependency retained"
    assert events[-5].event_id in result["sec"].history_ids, "year-ago actual retained"


def test_valid_cumulative_arithmetic_can_exceed_original_input_bound(ledger_factory):
    basis = replace(BASIS, metric="NET_INCOME", period_basis="cumulative")
    events = []
    for year in range(2018, 2025):
        for quarter in range(1, 5):
            value = 1e12 if (year + quarter) % 3 else -1e12
            announced = datetime(year + (quarter == 4), 1 if quarter == 4 else quarter * 3 + 1, 10, 8, tzinfo=ICT)
            events.append(make_event(year=year, quarter=quarter, basis=basis, actual=value,
                announced_at=announced, consensus=None))
    result = PEADDriftEngine(ledger_factory(events)).event_surprises(events[-1])["sec"]
    assert result.value is not None and math.isfinite(result.raw), "derived differences can exceed 1e12 without invalidating bounded source values"


def test_authoritative_holiday_and_frozen_panel_do_not_invent_sessions_or_fills(ledger_factory):
    ready = datetime(2025, 4, 29, 15, 30, tzinfo=ICT)
    event = make_event(year=2025, quarter=1, announced_at=ready - timedelta(minutes=4), ready_at=ready)
    engine = PEADDriftEngine(ledger_factory((event,)))
    panel = make_panel([(date(2025, 4, 30), "AAA"), (date(2025, 5, 2), "AAA"), (date(2025, 5, 5), "AAA")])
    panel["volume"] = 0
    original = panel.copy(deep=True)
    result = engine.features(panel)
    assert result.iloc[0]["pead_sue_reason"] == "non_trading_day", "Reunification Day is not a session"
    assert result.iloc[1]["pead_sue_reason"] == "non_trading_day", "compensatory closure comes from authoritative calendar"
    assert result.iloc[2]["pead_age_sessions"] == 0, "first session skips the holiday block and weekend"
    pd.testing.assert_frame_equal(panel, original)
    assert not {"entry_price", "fill_price", "position"}.intersection(result), "features do not invent execution for frozen stocks"


def test_fetcher_rejects_existing_pead_columns_and_diagnostic_registry(ledger_factory):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    fetcher = AlternativeDataFetcher(earnings_ledger=ledger_factory())
    panel = make_panel([(date(2025, 1, 16), "AAA")])
    panel["pead_sue"] = 99
    with pytest.raises(ValueError, match="already contains"):
        fetcher.generate_all(panel)
    assert not any(name.endswith(("_valid", "_reason")) for name in fetcher.get_feature_names()), "GP registry only exposes numeric features"


@pytest.mark.parametrize("definition", [
    "event_id TEXT COLLATE NOCASE NOT NULL PRIMARY KEY ON CONFLICT REPLACE, payload TEXT NOT NULL, digest TEXT NOT NULL",
    "event_id TEXT NOT NULL PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL DEFAULT 'missing'",
    "event_id TEXT NOT NULL PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, hidden TEXT GENERATED ALWAYS AS (event_id) VIRTUAL",
], ids=["collation-replace", "default", "hidden-column"])
def test_noncanonical_sqlite_definitions_rejected_before_mutation(tmp_path, monkeypatch, definition):
    import omega.data.earnings_ledger as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    path = tmp_path / "schema.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE ledger_meta (schema_version INTEGER NOT NULL)")
        connection.execute("INSERT INTO ledger_meta VALUES (1)")
        connection.execute(f"CREATE TABLE events ({definition}) WITHOUT ROWID")
    with pytest.raises(ValueError, match="schema"):
        EarningsLedger("schema.sqlite", events=(make_event(release_id="release"), make_event(release_id="RELEASE")))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0, "reject schema before publishing anything"


def test_canonical_schema_keeps_case_distinct_event_ids(ledger_factory):
    first, second = make_event(release_id="release"), make_event(release_id="RELEASE")
    ledger = ledger_factory((first, second))
    assert set(ledger.snapshot()) == {first, second}, "exact identities must never use case-insensitive replacement"


def test_sqlite_prefix_lookalike_objects_cannot_hide_from_schema_check(tmp_path, monkeypatch):
    import omega.data.earnings_ledger as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    with EarningsLedger("lookalike.sqlite"):
        pass
    with sqlite3.connect(tmp_path / "lookalike.sqlite") as connection:
        connection.execute("CREATE TABLE sqliteXextra (value TEXT)")
    with pytest.raises(ValueError, match="schema"):
        EarningsLedger("lookalike.sqlite")
