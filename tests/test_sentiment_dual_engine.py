from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow.parquet as pq
import pytest

from omega.quant.signal.sentiment_proxy import MarketImpliedSentimentProxy
from omega.quant.graph.loader import FinancialStatementLoader
from omega.data.news_aggregator import _as_utc
from scripts.fetch_news_sentiment import DEFAULT_HOURS_BACK, SCHEMA, build_news_sentiment


def test_market_proxy_is_t1_shifted_and_bounded():
    data = pd.DataFrame(
        {
            "symbol": ["AAA"] * 4,
            "date": pd.date_range("2026-01-01", periods=4),
            "high": [10, 12, 20, 25],
            "low": [8, 9, 10, 10],
            "close": [9, 11, 19, 24],
            "volume": [100, 200, 1000, 2000],
        }
    )

    result = MarketImpliedSentimentProxy(window=2).compute(data)

    assert result.iloc[0].isna().all()
    assert result.loc[2, "buying_pressure_index"] == 1 / 3
    assert result["market_implied_sentiment"].dropna().between(-1.0, 1.0).all()


def test_news_timestamp_localizes_naive_ict_before_utc_conversion():
    assert _as_utc(datetime(2026, 6, 19, 15, 0)) == datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc)


def test_market_proxy_groups_ticker_column_independently():
    data = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "AAA", "BBB"],
            "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]),
            "high": [10, 20, 12, 24],
            "low": [8, 16, 9, 18],
            "close": [9, 19, 11, 22],
            "volume": [100, 200, 150, 250],
        }
    )

    result = MarketImpliedSentimentProxy().compute(data)

    assert result.loc[[0, 1]].isna().all().all()
    assert result.loc[2, "buying_pressure_index"] == 0.0
    assert result.loc[3, "buying_pressure_index"] == 0.5


def test_compute_proxy_returns_canonical_ticker_schema():
    data = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "date": pd.date_range("2026-01-01", periods=2),
            "high": [10, 12],
            "low": [8, 9],
            "close": [9, 11],
            "volume": [100, 200],
        }
    )

    result = MarketImpliedSentimentProxy().compute_proxy(data)

    assert result.columns.tolist() == ["symbol", "date", "market_implied_sentiment", "available_at"]
    assert result["symbol"].tolist() == ["AAA", "AAA"]
    assert result["available_at"].equals(result["date"])


def test_news_engine_writes_pit_schema(tmp_path: Path):
    published = datetime(2026, 1, 2, tzinfo=timezone.utc)

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            assert as_of_time.tzinfo is timezone.utc
            assert hours_back == DEFAULT_HOURS_BACK
            return [type("Article", (), {"ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": published})()]

    output = build_news_sentiment(
        tmp_path / "news.parquet", Aggregator(),
        checkpoint_path=tmp_path / "checkpoint.json", quarantine_path=tmp_path / "quarantine.parquet",
    )
    table = pq.read_table(output)

    assert table.schema == SCHEMA
    assert table.column("available_at")[0].as_py() >= published + timedelta(days=1)
    assert table.column("available_at")[0].as_py() >= table.column("fetched_at")[0].as_py()
    assert table.column("sentiment_score")[0].as_py() == 1.0


@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["before", "equal", "after"])
@pytest.mark.parametrize("availability_offset", [None, -1, 1], ids=["missing", "premature", "delayed"])
def test_news_engine_availability_respects_observation_floor(tmp_path: Path, offset, availability_offset):
    published = datetime(2026, 1, 2, 8, 30, tzinfo=timezone.utc)
    delayed_publication = published + timedelta(days=1)
    fetched_at = delayed_publication + timedelta(microseconds=offset)
    available_at = None if availability_offset is None else delayed_publication + timedelta(microseconds=availability_offset)

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {
                "ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": published,
                "fetched_at": fetched_at, "available_at": available_at,
            })()]

    output = build_news_sentiment(
        tmp_path / "news.parquet", Aggregator(),
        checkpoint_path=tmp_path / "checkpoint.json", quarantine_path=tmp_path / "quarantine.parquet",
    )
    row = pq.read_table(output).to_pylist()[0]

    assert row["fetched_at"] == fetched_at
    assert row["available_at"] == max(fetched_at, available_at or delayed_publication)
    assert row["available_at"] >= fetched_at


def test_news_engine_passes_hours_back_to_aggregator(tmp_path: Path):
    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            assert as_of_time.tzinfo is timezone.utc
            assert hours_back == 48
            return [type("Article", (), {
                "ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": as_of_time - timedelta(hours=1),
            })()]

    build_news_sentiment(tmp_path / "news.parquet", Aggregator(), hours_back=48)


def test_market_proxy_incremental_update_appends_only_new_rows_and_tracks_checkpoint(tmp_path: Path):
    market_data = pd.DataFrame(
        {
            "symbol": ["AAA"] * 3,
            "date": pd.date_range("2026-01-01", periods=3),
            "high": [10, 12, 20],
            "low": [8, 9, 10],
            "close": [9, 11, 19],
            "volume": [100, 200, 1000],
        }
    )
    output, checkpoint = tmp_path / "proxy.parquet", tmp_path / "checkpoint.json"
    proxy = MarketImpliedSentimentProxy(window=2)

    first = proxy.update_incremental(output, market_data.iloc[:2], checkpoint)
    second = proxy.update_incremental(output, market_data, checkpoint)

    assert len(first) == 2
    assert second["date"].tolist() == [pd.Timestamp("2026-01-03")]
    assert pq.read_table(output).num_rows == 3
    assert json.loads(checkpoint.read_text())["market_proxy"]["max_date"].startswith("2026-01-03")


def test_market_proxy_incremental_upsert_is_idempotent_and_has_symbol_watermarks(tmp_path: Path):
    data = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]),
            "high": [10, 20, 12, 24], "low": [8, 16, 9, 18],
            "close": [9, 19, 11, 22], "volume": [100, 200, 150, 250],
        }
    )
    output, checkpoint = tmp_path / "proxy.parquet", tmp_path / "checkpoint.json"
    proxy = MarketImpliedSentimentProxy()

    proxy.update_incremental(output, data, checkpoint)
    assert proxy.update_incremental(output, data, checkpoint).empty
    manifest = json.loads(checkpoint.read_text())["market_proxy"]

    assert pq.read_table(output).num_rows == 4
    assert manifest["symbol_watermarks"] == {"AAA": "2026-01-02T00:00:00", "BBB": "2026-01-02T00:00:00"}
    assert len(manifest["sha256"]) == 64


def test_market_proxy_incremental_atomic_write_preserves_existing_file_on_failure(tmp_path: Path):
    output, checkpoint = tmp_path / "proxy.parquet", tmp_path / "checkpoint.json"
    data = pd.DataFrame({"symbol": ["AAA"], "date": ["2026-01-01"], "high": [10], "low": [8], "close": [9], "volume": [100]})
    proxy = MarketImpliedSentimentProxy()
    proxy.update_incremental(output, data, checkpoint)
    original = output.read_bytes()

    with patch("pathlib.Path.replace", side_effect=OSError("disk failure")):
        try:
            proxy.update_incremental(output, data, checkpoint)
        except OSError:
            pass

    assert output.read_bytes() == original


def test_news_incremental_uses_24_hour_overlap_buffer(tmp_path: Path, monkeypatch):
    import scripts.fetch_news_sentiment as news_script

    now = datetime(2026, 1, 4, tzinfo=timezone.utc)
    published = now - timedelta(hours=30)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    class InitialAggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": "AAA", "text": "AAA tăng", "timestamp": published})()]

    class IncrementalAggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            assert hours_back == 54
            return []

    output = tmp_path / "news.parquet"
    build_news_sentiment(output, InitialAggregator())
    monkeypatch.setattr(news_script, "datetime", FixedDatetime)
    build_news_sentiment(output, IncrementalAggregator(), incremental=True)


def test_news_engine_incremental_update_deduplicates_and_tracks_checkpoint(tmp_path: Path):
    first_published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    second_published = first_published + timedelta(hours=1)

    class InitialAggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": first_published})()]

    class IncrementalAggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            assert hours_back > 0
            return [
                type("Article", (), {"ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": first_published})(),
                type("Article", (), {"ticker": "AAA", "text": "AAA giảm", "timestamp": second_published})(),
            ]

    output, checkpoint = tmp_path / "news.parquet", tmp_path / "checkpoint.json"
    build_news_sentiment(output, InitialAggregator(), checkpoint_path=checkpoint)
    build_news_sentiment(output, IncrementalAggregator(), incremental=True, checkpoint_path=checkpoint)

    assert pq.read_table(output).num_rows == 2
    manifest = json.loads(checkpoint.read_text())["news_sentiment"]
    assert manifest["row_count"] == 2
    assert manifest["max_publish_time"].startswith("2026-01-02T01:00:00")


def test_loader_prefers_latest_fiscal_period_when_availability_ties():
    statements = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "item_code": ["revenue", "revenue"],
            "item_value": [100.0, 200.0],
            "fiscal_period_end": ["2025-03-31", "2025-06-30"],
            "available_at": ["2025-08-15", "2025-08-15"],
        }
    )

    joined = FinancialStatementLoader(statements).asof_join_market(
        pd.DataFrame({"symbol": ["AAA"], "date": ["2025-08-16"]})
    )

    assert joined.iloc[0]["item_value"] == 200.0
