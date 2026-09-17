from datetime import date
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("financial_fetch", ROOT / "scripts" / "fetch_financial_statements.py")
financial_fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(financial_fetch)


@pytest.mark.parametrize(
    ("endpoint", "period"),
    [(endpoint, period) for endpoint in financial_fetch.ENDPOINTS for period in financial_fetch.PERIODS],
)
def test_dispatches_each_endpoint_period_pair(tmp_path, endpoint, period):
    calls = []

    class Fetcher:
        def financial(self, symbol, endpoint, period):
            calls.append((symbol, endpoint, period))
            return pd.DataFrame([{"year": 2025, "quarter": 1, "current_assets": 10, "current_liabilities": 2}])

    financial_fetch.fetch_all(Fetcher(), ["AAA"], tmp_path)
    assert ("AAA", endpoint, period) in calls


def test_exact_pit_embargo_and_fallback():
    end = date(2025, 3, 31)
    assert financial_fetch.available_at(end, "2025-05-01", "quarter") == pd.Timestamp("2025-05-15T00:00:00Z")
    assert financial_fetch.available_at(end, None, "quarter") == pd.Timestamp("2025-05-15T00:00:00Z")
    assert financial_fetch.available_at(date(2025, 12, 31), "2026-02-01", "year") == pd.Timestamp("2026-03-31T00:00:00Z")


@pytest.mark.parametrize("invalid", [None, "not-a-date"])
def test_invalid_publish_time_fails_closed_to_embargo(invalid):
    assert financial_fetch.available_at(date(2025, 3, 31), invalid, "quarter") == pd.Timestamp("2025-05-15T00:00:00Z")


def test_safe_divide_and_ratio_prefixes():
    assert financial_fetch.safe_divide(1, 0) is None
    rows = financial_fetch.normalize_statement("AAA", "ratios", "year", pd.DataFrame([{"year": 2025, "pe": 12.5}]))
    assert rows[0]["item_code"] == "provider_ratio_pe"
    derived = financial_fetch.derive_ratios([{"item_code": "current_assets", "item_value": 10}, {"item_code": "current_liabilities", "item_value": 2}])
    assert derived[0]["item_code"] == "derived_ratio_current_ratio"
    assert derived[0]["item_value"] == 5.0


def test_atomic_write_uses_five_durability_steps(tmp_path, monkeypatch):
    events = []
    target = tmp_path / "state.json"
    original_fdopen = financial_fetch.os.fdopen
    original_replace = financial_fetch.os.replace

    class Handle:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def write(self, payload):
            events.append("write")
            return self.handle.write(payload)

        def flush(self):
            events.append("flush")
            return self.handle.flush()

        def fileno(self):
            return self.handle.fileno()

    monkeypatch.setattr(financial_fetch.os, "fdopen", lambda *args: Handle(original_fdopen(*args)))
    monkeypatch.setattr(financial_fetch.os, "fsync", lambda *_: events.append("fsync"))
    monkeypatch.setattr(financial_fetch.os, "replace", lambda *args: (events.append("replace"), original_replace(*args))[1])
    monkeypatch.setattr(financial_fetch, "_fsync_parent", lambda *_: events.append("parent_fsync"))
    financial_fetch.atomic_write_bytes(target, b"new")
    assert events == ["write", "flush", "fsync", "replace", "parent_fsync"]


def test_atomic_write_crash_keeps_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    financial_fetch.atomic_write_bytes(target, b"old")
    monkeypatch.setattr(financial_fetch.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        financial_fetch.atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.tmp"))


def test_manifest_contains_all_unique_market_symbols_by_default(tmp_path):
    market = tmp_path / "market.parquet"
    pd.DataFrame({"date": ["2026-08-04", "2026-08-05", "2026-08-05", "2026-08-05"], "ticker": ["OLD", "AAA", "BBB", "AAA"]}).to_parquet(market)
    symbols, snapshot_date, source_hash = financial_fetch.load_active_universe(market)
    manifest = tmp_path / "manifest.json"
    financial_fetch.write_universe_manifest(symbols, snapshot_date, source_hash, manifest)
    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "snapshot_date": "2026-08-05", "sorted_symbols": ["AAA", "BBB", "OLD"],
        "source_parquet_hash": financial_fetch.source_parquet_hash(market), "ticker_count": 3,
    }


def test_load_active_universe_filters_to_latest_date_when_requested(tmp_path):
    market = tmp_path / "market.parquet"
    pd.DataFrame({"date": ["2026-08-04", "2026-08-05", "2026-08-05"], "ticker": ["OLD", "AAA", "BBB"]}).to_parquet(market)
    symbols, _, _ = financial_fetch.load_active_universe(market, active_only=True)
    assert symbols == ["AAA", "BBB"]


def test_pyarrow_schema_roundtrip(tmp_path):
    output = tmp_path / "financial.parquet"
    financial_fetch.write_parquet([{"symbol": "AAA", "endpoint": "income_statement", "period_type": "quarter", "fiscal_year": 2025, "fiscal_quarter": 1, "item_code": "revenue", "item_value": 1.0, "fiscal_period_end": date(2025, 3, 31), "source_publish_at": pd.Timestamp("2025-05-01T00:00:00Z"), "available_at": pd.Timestamp("2025-05-15T00:00:00Z")}], output)
    assert pq.read_table(output).schema == financial_fetch.SCHEMA


def test_write_parquet_preserves_same_item_code_from_distinct_endpoints(tmp_path):
    output = tmp_path / "financial.parquet"
    rows = [
        {"symbol": "AAA", "endpoint": endpoint, "period_type": "quarter", "fiscal_year": 2025, "fiscal_quarter": 1, "item_code": "common_item", "item_value": value, "fiscal_period_end": date(2025, 3, 31), "source_publish_at": None, "available_at": pd.Timestamp("2025-05-15T00:00:00Z")}
        for endpoint, value in [("income_statement", 1.0), ("balance_sheet", 2.0), ("cash_flow", 3.0)]
    ]
    financial_fetch.write_parquet(rows, output)
    assert set(pq.read_table(output).to_pandas()["endpoint"]) == {"income_statement", "balance_sheet", "cash_flow"}


def test_derive_ratios_groups_rows_by_fiscal_period():
    rows = [
        {"symbol": "AAA", "endpoint": "balance_sheet", "period_type": "quarter", "fiscal_year": 2025, "fiscal_quarter": quarter, "fiscal_period_end": end, "item_code": item, "item_value": value}
        for quarter, end, item, value in [
            (1, date(2025, 3, 31), "current_assets", 10.0),
            (1, date(2025, 3, 31), "current_liabilities", 2.0),
            (2, date(2025, 6, 30), "current_assets", 20.0),
            (2, date(2025, 6, 30), "current_liabilities", 4.0),
        ]
    ]
    derived = financial_fetch.derive_ratios(rows)
    assert {(row["fiscal_quarter"], row["item_value"]) for row in derived if row["item_code"] == "derived_ratio_current_ratio"} == {(1, 5.0), (2, 5.0)}


def test_normalize_statement_converts_timezone_to_utc():
    rows = financial_fetch.normalize_statement("AAA", "income_statement", "quarter", [{"year": 2025, "quarter": 1, "published_at": "2025-05-15T07:00:00+07:00", "revenue": 1}])
    assert rows[0]["source_publish_at"] == pd.Timestamp("2025-05-15T00:00:00Z")


def test_normalize_statement_parses_wide_quarter_period_columns():
    raw = pd.DataFrame([
        {"item_id": "revenue", "item": "Revenue", "2026-Q2": 120, "2025-Q4": 100, "2025-Q4_1": 99},
        {"item_id": "profit", "item": "Profit", "2026-Q2": 20, "2025-Q4": 10, "2025-Q4_1": None},
    ])
    rows = financial_fetch.normalize_statement("AAA", "income_statement", "quarter", raw)
    assert {(row["item_code"], row["fiscal_year"], row["fiscal_quarter"], row["fiscal_period_end"], row["period_type"], row["item_value"]) for row in rows} == {
        ("revenue", 2026, 2, date(2026, 6, 30), "quarter", 120.0),
        ("revenue", 2025, 4, date(2025, 12, 31), "quarter", 100.0),
        ("revenue", 2025, 4, date(2025, 12, 31), "quarter", 99.0),
        ("profit", 2026, 2, date(2026, 6, 30), "quarter", 20.0),
        ("profit", 2025, 4, date(2025, 12, 31), "quarter", 10.0),
    }


def test_normalize_statement_parses_wide_annual_period_columns():
    rows = financial_fetch.normalize_statement("AAA", "balance_sheet", "year", pd.DataFrame([
        {"item_id": "assets", "item": "Assets", "2025": 200, "2024": 180},
    ]))
    assert {(row["fiscal_year"], row["fiscal_quarter"], row["fiscal_period_end"], row["period_type"], row["item_value"]) for row in rows} == {
        (2025, 0, date(2025, 12, 31), "year", 200.0),
        (2024, 0, date(2024, 12, 31), "year", 180.0),
    }


def test_atomic_parquet_replacement_keeps_previous_file_on_crash(tmp_path, monkeypatch):
    target = tmp_path / "financial.parquet"
    financial_fetch.write_parquet([], target)
    original = target.read_bytes()
    monkeypatch.setattr(financial_fetch, "durable_replace", lambda *_: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        financial_fetch.write_parquet([], target)
    assert target.read_bytes() == original


def test_empty_dataframe_writes_canonical_schema(tmp_path):
    output = tmp_path / "empty.parquet"
    financial_fetch.write_parquet([], output)
    assert pq.read_table(output).schema == financial_fetch.SCHEMA
