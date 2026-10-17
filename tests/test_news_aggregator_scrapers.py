from datetime import datetime, timedelta, timezone
from time import perf_counter
from unittest.mock import patch

import pyarrow as pa
import pytest
from bs4 import BeautifulSoup

from omega.data.news_aggregator import NewsAggregator, infer_tickers_from_text
from scripts.fetch_news_sentiment import SCHEMA, QUARANTINE_SCHEMA, _load_listing_days, build_news_sentiment, migrate_news_sentiment_schema
from scripts.migrate_news_parquet import migrate_news_parquet


HTML = """
<article><h3><a href="/alpha?utm_source=test&ref=x#section">VCB tăng mạnh</a></h3><time>15 phút trước</time></article>
<article><h3><a href="/alpha?utm_source=test&ref=x#section">VCB tăng mạnh</a></h3><time>15 phút trước</time></article>
<article><h3><a href="/future">Future</a></h3><time>2026-08-07T13:00:00</time></article>
<article><h3><a href="/old">Old</a></h3><time>2026-08-07T09:00:00</time></article>
<article><h3><a href="/bad">Bad</a></h3><time>not a date</time></article>
"""


def test_html_scraper_anchors_relative_times_canonicalizes_and_filters():
    fetched_at = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    aggregator = NewsAggregator()
    with patch.object(aggregator, "_fetch_html", return_value=BeautifulSoup(HTML, "html.parser")):
        articles = aggregator._scrape_cafef(fetched_at, hours_back=2, fetched_at=fetched_at)
    assert len(articles) == 1
    assert articles[0].timestamp == fetched_at - timedelta(minutes=15)
    assert articles[0].url == "https://cafef.vn/alpha"
    assert articles[0].ticker == "VCB"
    assert articles[0].payload_sha256
    assert articles[0].fetched_at == fetched_at


def test_html_scraper_honors_configured_article_limit():
    fetched_at = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    aggregator = NewsAggregator(max_articles_per_source=1)
    html = """
    <article><h3><a href="/one">VCB tăng</a></h3><time>15 phút trước</time></article>
    <article><h3><a href="/two">FPT tăng</a></h3><time>15 phút trước</time></article>
    """
    with patch.object(aggregator, "_fetch_html", return_value=BeautifulSoup(html, "html.parser")):
        articles = aggregator._scrape_cafef(fetched_at, hours_back=2, fetched_at=fetched_at)
    assert len(articles) == 1


@pytest.mark.parametrize("max_articles_per_source", [0, -1])
def test_news_aggregator_rejects_non_positive_article_limit(max_articles_per_source):
    with pytest.raises(ValueError, match="positive integer"):
        NewsAggregator(max_articles_per_source=max_articles_per_source)


def test_public_fetch_rejects_stale_as_of_time():
    with pytest.raises(ValueError, match="stale"):
        NewsAggregator().fetch_recent_news(datetime.now(timezone.utc) - timedelta(hours=1, seconds=1))


def test_infer_tickers_requires_uppercase_word_boundaries_and_explicit_ambiguous_tickers():
    assert infer_tickers_from_text("TP.HCM, TP HCM, Hà Nội, Việt Nam, Bộ Tài chính, NHNN, VND") == []
    assert infer_tickers_from_text("HCM tăng giá") == []
    assert infer_tickers_from_text("mã HCM và cổ phiếu VND tăng") == ["HCM", "VND"]


def test_short_dates_use_ict_year_at_utc_year_boundary():
    aggregator = NewsAggregator()
    fetched_at = datetime(2025, 12, 31, 18, 30, tzinfo=timezone.utc)
    assert aggregator._parse_html_time("01/01 00:30", fetched_at) == datetime(2025, 12, 31, 17, 30, tzinfo=timezone.utc)
    assert aggregator._parse_vietstock_time("01/01 00:30", fetched_at) == datetime(2026, 1, 1, 0, 30)
    assert aggregator._parse_vietstock_time("31/12 23:30", datetime(2025, 12, 31, 17, 30, tzinfo=timezone.utc)) == datetime(2025, 12, 31, 23, 30)


@pytest.mark.parametrize("value", ["2026-08-07T19:00:00+07:00", "2026-08-07T12:00:00Z"])
def test_html_time_parses_timezone_aware_iso_dates(value):
    assert NewsAggregator()._parse_html_time(value, datetime(2026, 8, 7, 12, tzinfo=timezone.utc)) == datetime(2026, 8, 7, 12, tzinfo=timezone.utc)


def test_canonical_url_rejects_external_domains():
    aggregator = NewsAggregator()
    assert aggregator._canonical_url("https://cafef.vn/thi-truong-chung-khoan.chn", "https://sponsor.example/article") is None
    assert aggregator._canonical_url("https://cafef.vn/thi-truong-chung-khoan.chn", "https://notcafef.vn/article") is None


def test_legacy_parquet_schema_migration_adds_nullable_url():
    legacy = pa.table({
        "symbol": ["VCB"], "title": ["title"],
        "publish_time": [datetime(2026, 8, 7, tzinfo=timezone.utc)],
        "sentiment_score": [1.0], "available_at": [datetime(2026, 8, 8, tzinfo=timezone.utc)],
    })
    migrated = migrate_news_sentiment_schema(legacy)
    assert migrated.schema == SCHEMA
    assert migrated.column("url").to_pylist() == [None]
    assert migrated.column("source").to_pylist() == ["legacy"]
    assert migrated.column("legacy_row").to_pylist() == [True]


def test_legacy_parquet_schema_migration_hashes_row_identity_not_index():
    legacy = pa.table({
        "symbol": ["VCB", "VCB"],
        "title": ["title one", "title two"],
        "publish_time": [
            datetime(2026, 8, 7, tzinfo=timezone.utc),
            datetime(2026, 8, 7, tzinfo=timezone.utc),
        ],
        "sentiment_score": [1.0, 1.0],
    })
    hashes = migrate_news_sentiment_schema(legacy).column("payload_sha256").to_pylist()
    assert hashes[0] != hashes[1]


def test_legacy_parquet_schema_migration_defaults_missing_available_at():
    legacy = pa.table({
        "symbol": ["VCB"], "title": ["title"],
        "publish_time": [datetime(2026, 8, 7, tzinfo=timezone.utc)], "sentiment_score": [1.0],
    })
    assert migrate_news_sentiment_schema(legacy).column("available_at").to_pylist() == [datetime(2026, 8, 8, tzinfo=timezone.utc)]


def test_load_listing_days_accepts_ticker_column(tmp_path):
    import pyarrow.parquet as pq

    path = tmp_path / "listing_days.parquet"
    pq.write_table(pa.table({"ticker": ["AAA", "AAA", "VCB"], "date": ["2026-01-02", "2026-01-03", "2026-01-02"]}), path)
    assert _load_listing_days(path) == {
        "AAA": {datetime(2026, 1, 2).date(), datetime(2026, 1, 3).date()},
        "VCB": {datetime(2026, 1, 2).date()},
    }


def test_parquet_migration_replaces_file_only_after_schema_validation(tmp_path):
    path = tmp_path / "news.parquet"
    legacy = pa.table({
        "symbol": ["VCB"], "title": ["title"],
        "publish_time": [datetime(2026, 8, 7, tzinfo=timezone.utc)],
        "sentiment_score": [1.0], "available_at": [datetime(2026, 8, 8, tzinfo=timezone.utc)],
    })
    import pyarrow.parquet as pq
    pq.write_table(legacy, path)
    migrate_news_parquet(path)
    assert pq.read_table(path).schema == SCHEMA


def test_vietcap_pagination_covers_year_boundary_and_detects_cursor_loop(monkeypatch):
    aggregator = NewsAggregator()
    pages = iter([
        ([{"title": "VCB tăng", "published_at": "2026-01-01T00:00:00Z"}], "older", "a"),
        ([{"title": "VCB tăng", "published_at": "2015-01-01T00:00:01Z"}], None, "b"),
    ])
    monkeypatch.setattr(aggregator, "_fetch_vietcap_page", lambda *args: next(pages))
    items = aggregator._scrape_vietcap_news(datetime(2026, 8, 7, tzinfo=timezone.utc), hours_back=96360)
    assert [item.timestamp.year for item in items] == [2026]


def test_vietcap_24_hour_window_never_queries_before_historical_start(monkeypatch):
    aggregator = NewsAggregator()
    as_of_time = datetime(2026, 8, 7, tzinfo=timezone.utc)
    starts = []

    def fetch_page(start, *args):
        starts.append(start)
        return [], None, "hash"

    monkeypatch.setattr(aggregator, "_fetch_vietcap_page", fetch_page)
    assert aggregator._scrape_vietcap_news(as_of_time, hours_back=24) == []
    assert starts == [as_of_time - timedelta(hours=24)]


def test_vietcap_scraper_honors_configured_article_limit(monkeypatch):
    aggregator = NewsAggregator(max_articles_per_source=2)
    cursors = []

    def fetch_page(_start, _end, cursor):
        cursors.append(cursor)
        return [
            {"title": "VCB tăng 1", "published_at": "2026-08-06T23:00:00Z"},
            {"title": "VCB tăng 2", "published_at": "2026-08-06T22:00:00Z"},
            {"title": "VCB tăng 3", "published_at": "2026-08-06T21:00:00Z"},
        ], "older", "hash"

    monkeypatch.setattr(aggregator, "_fetch_vietcap_page", fetch_page)

    articles = aggregator._scrape_vietcap_news(datetime(2026, 8, 7, tzinfo=timezone.utc), hours_back=24)

    assert len(articles) == 2
    assert cursors == [None]


def test_public_fetch_keeps_fuzzy_titles_with_different_tickers(monkeypatch):
    aggregator = NewsAggregator()
    as_of_time = datetime.now(timezone.utc)
    older = as_of_time - timedelta(hours=30)
    newer = as_of_time - timedelta(hours=1)
    first = type("Article", (), {"text": "VCB lợi nhuận tăng trưởng mạnh quý 2", "source": "first", "timestamp": older, "ticker": "VCB"})()
    duplicate = type("Article", (), {"text": "VCB lợi nhuận tăng trưởng mạnh quý II", "source": "second", "timestamp": newer, "ticker": "FPT"})()
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *_: [first])
    monkeypatch.setattr(aggregator, "_scrape_vietstock", lambda *_: [duplicate])
    monkeypatch.setattr(aggregator, "_scrape_vietcap_news", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_cafef", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_tinnhanhck", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vneconomy", lambda *_: [])
    assert set(aggregator.fetch_recent_news(as_of_time, hours_back=48)) == {first, duplicate}


def test_public_fetch_tolerates_vietcap_failure_for_historical_request(monkeypatch):
    aggregator = NewsAggregator()
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vietstock", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vietcap_news", lambda *_: (_ for _ in ()).throw(RuntimeError("Vietcap unavailable")))
    monkeypatch.setattr(aggregator, "_scrape_cafef", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_tinnhanhck", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vneconomy", lambda *_: [])
    assert aggregator.fetch_recent_news(datetime.now(timezone.utc), hours_back=25) == []


def test_labeled_fixture_dedupes_cross_source_url_less_and_batch_duplicates(tmp_path):
    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    article = lambda source, url=None: type("Article", (), {"ticker": "AAA", "text": "AAA tăng mạnh", "timestamp": published, "source": source, "url": url})()
    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [article("Vietcap"), article("Vietstock", "https://other/article")]
    output = build_news_sentiment(tmp_path / "news.parquet", Aggregator())
    assert __import__("pyarrow.parquet", fromlist=["read_table"]).read_table(output).num_rows == 1


def test_empty_collection_preserves_existing_news_sentiment_dataset(tmp_path):
    import pyarrow.parquet as pq

    output = tmp_path / "news.parquet"
    pq.write_table(pa.Table.from_pylist([{
        "symbol": "AAA", "title": "prior", "publish_time": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "sentiment_score": 1.0, "available_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
        "url": None, "source": "fixture", "fetched_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "raw_timestamp": None, "payload_sha256": "prior", "parser_version": "fixture", "legacy_row": False,
    }], schema=SCHEMA), output)
    prior = output.read_bytes()

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return []

    with pytest.raises(ValueError, match="zero collected articles"):
        build_news_sentiment(output, Aggregator())
    assert output.read_bytes() == prior


def test_incremental_empty_collection_preserves_existing_news_sentiment_dataset(tmp_path):
    import pyarrow.parquet as pq

    output = tmp_path / "news.parquet"
    pq.write_table(pa.Table.from_pylist([{
        "symbol": "AAA", "title": "prior", "publish_time": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "sentiment_score": 1.0, "available_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
        "url": None, "source": "fixture", "fetched_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "raw_timestamp": None, "payload_sha256": "prior", "parser_version": "fixture", "legacy_row": False,
    }], schema=SCHEMA), output)

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return []

    build_news_sentiment(output, Aggregator(), incremental=True)
    assert pq.read_table(output).num_rows == 1


def test_quarantine_is_schema_valid_atomic_and_uses_daily_listing_dates(tmp_path):
    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": "AAA", "text": "AAA tăng", "timestamp": published, "source": "fixture"})()]
    output, quarantine = tmp_path / "news.parquet", tmp_path / "quarantine.parquet"
    build_news_sentiment(output, Aggregator(), incremental=True, quarantine_path=quarantine, listing_days={"AAA": {datetime(2026, 1, 3).date()}})
    import pyarrow.parquet as pq
    table = pq.read_table(quarantine)
    assert table.schema == QUARANTINE_SCHEMA
    assert table.column("reason").to_pylist() == ["ticker_not_listed_on_publish_day"]
    assert pq.read_table(output).num_rows == 0


def test_quarantine_replace_failure_preserves_prior_file(tmp_path, monkeypatch):
    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": None, "text": "missing ticker", "timestamp": published})()]
    output, quarantine = tmp_path / "news.parquet", tmp_path / "quarantine.parquet"
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist([{"reason": "prior", "source": "fixture", "fetched_at": published, "parser_version": "v", "payload_sha256": "x", "raw_payload": "{}"}], schema=QUARANTINE_SCHEMA), quarantine)
    prior = quarantine.read_bytes()
    with patch("scripts.fetch_news_sentiment.Path.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError, match="disk failure"):
            build_news_sentiment(output, Aggregator(), incremental=True, quarantine_path=quarantine)
    assert quarantine.read_bytes() == prior


def test_batch_replacement_failure_restores_all_original_files(tmp_path, monkeypatch):
    import pyarrow.parquet as pq

    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    output, quarantine, checkpoint = tmp_path / "news.parquet", tmp_path / "quarantine.parquet", tmp_path / "checkpoint.json"
    pq.write_table(pa.Table.from_pylist([{
        "symbol": "AAA", "title": "prior", "publish_time": published, "sentiment_score": 1.0,
        "available_at": published + timedelta(days=1), "url": None, "source": "fixture", "fetched_at": published,
        "raw_timestamp": None, "payload_sha256": "prior", "parser_version": "fixture", "legacy_row": False,
    }], schema=SCHEMA), output)
    pq.write_table(pa.Table.from_pylist([{
        "reason": "prior", "source": "fixture", "fetched_at": published, "parser_version": "v",
        "payload_sha256": "prior", "raw_payload": "{}",
    }], schema=QUARANTINE_SCHEMA), quarantine)
    checkpoint.write_text('{"prior": true}\n', encoding="utf-8")
    originals = {path: path.read_bytes() for path in (output, quarantine, checkpoint)}

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": "VCB", "text": "VCB tăng", "timestamp": published})()]

    original_replace = __import__("pathlib").Path.replace
    staged_replacements = 0

    def fail_second_staged_replacement(source, destination):
        nonlocal staged_replacements
        if source.suffix.endswith(".tmp"):
            staged_replacements += 1
            if staged_replacements == 2:
                raise OSError("injected replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr("scripts.fetch_news_sentiment.Path.replace", fail_second_staged_replacement)
    with pytest.raises(OSError, match="injected replacement failure"):
        build_news_sentiment(output, Aggregator(), incremental=True, checkpoint_path=checkpoint, quarantine_path=quarantine)
    assert {path: path.read_bytes() for path in originals} == originals
    assert not any(path.with_suffix(path.suffix + ".bak").exists() for path in originals)


def test_labeled_news_pairs_fixture_deduplication_precision_and_recall():
    import json
    from pathlib import Path
    fixture_path = Path("tests/fixtures/labeled_news_pairs.json")
    assert fixture_path.exists(), "tests/fixtures/labeled_news_pairs.json must exist"
    pairs = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert len(pairs) >= 100, f"Fixture must contain at least 100 pairs, found {len(pairs)}"

    aggregator = NewsAggregator()
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0

    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    for pair in pairs:
        title_a = pair["title_a"]
        title_b = pair["title_b"]
        expected_dup = pair["is_duplicate"]

        key_a = aggregator._dedupe_key(type("Article", (), {"url": "https://example.com/a", "text": title_a, "ticker": None, "timestamp": published})())
        key_b = aggregator._dedupe_key(type("Article", (), {"url": "https://example.com/a", "text": title_b, "ticker": None, "timestamp": published})())
        predicted_dup = (
            key_a[2] == key_b[2]
            or aggregator._levenshtein_similarity(key_a[2], key_b[2]) > 0.88
        )

        if predicted_dup and expected_dup:
            true_positives += 1
        elif predicted_dup and not expected_dup:
            false_positives += 1
        elif not predicted_dup and expected_dup:
            false_negatives += 1
        else:
            true_negatives += 1

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0

    assert precision >= 0.95, f"Deduplication precision {precision:.4f} < 0.95"
    assert recall >= 0.90, f"Deduplication recall {recall:.4f} < 0.90"


def test_vietcap_fuzzy_deduplicate_performance(monkeypatch):
    aggregator = NewsAggregator()
    as_of_time = datetime.now(timezone.utc)
    timestamp = as_of_time - timedelta(hours=1)
    base_title = "VCB tang truong loi nhuan ben vung "
    articles = [
        type("Article", (), {
            "text": f"{base_title}chi tiet {index:04d}", "source": "Vietcap",
            "timestamp": timestamp, "ticker": "FPT" if index == 2 else "VCB",
        })()
        for index in range(1_000)
    ]
    normalized_titles = [aggregator._dedupe_key(article)[2] for article in articles[:2]]
    assert aggregator._levenshtein_similarity(*normalized_titles) > 0.88
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vietstock", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vietcap_news", lambda *_: articles)
    monkeypatch.setattr(aggregator, "_scrape_cafef", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_tinnhanhck", lambda *_: [])
    monkeypatch.setattr(aggregator, "_scrape_vneconomy", lambda *_: [])

    started_at = perf_counter()
    deduplicated = aggregator.fetch_recent_news(as_of_time, hours_back=48)
    assert {article.ticker for article in deduplicated} == {"VCB", "FPT"}
    assert perf_counter() - started_at < 3


def test_vietcap_pagination_detects_repeated_cursor_loop_and_raises_value_error(monkeypatch):
    aggregator = NewsAggregator()
    pages = iter([
        ([{"title": "Bài 1", "published_at": "2026-08-06T23:00:00Z"}], "repeated_cursor", "hash1"),
        ([{"title": "Bài 2", "published_at": "2026-08-06T22:00:00Z"}], "repeated_cursor", "hash2"),
    ])
    monkeypatch.setattr(aggregator, "_fetch_vietcap_page", lambda *args: next(pages))
    with pytest.raises(ValueError, match="repeated a cursor"):
        aggregator._scrape_vietcap_news(datetime(2026, 8, 7, tzinfo=timezone.utc), hours_back=24)


def test_vnstock_pagination_detects_repeated_cursor_loop(monkeypatch):
    aggregator = NewsAggregator()
    frame = type("Frame", (), {"empty": False, "columns": ["news_title", "public_date"], "to_dict": lambda *_args, **_kwargs: []})()
    pages = iter([(frame, "repeated_cursor"), (frame, "repeated_cursor")])
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["VCB"])
    monkeypatch.setattr(aggregator, "_rate_limit", lambda *_: None)
    monkeypatch.setattr(aggregator, "_fetch_vnstock_page", lambda *_args, **_kwargs: next(pages))
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Company=lambda **_kwargs: object()))
    with pytest.raises(ValueError, match="repeated cursor"):
        aggregator._scrape_vnstock_news(datetime(2026, 8, 7, tzinfo=timezone.utc), hours_back=24)


def test_vnstock_pagination_stops_at_cutoff_without_requesting_next_cursor(monkeypatch):
    aggregator = NewsAggregator()
    frame = type("Frame", (), {
        "empty": False,
        "attrs": {"news_order": "descending"},
        "columns": ["news_title", "public_date"],
        "to_dict": lambda *_args, **_kwargs: [{
            "news_title": "VCB tăng", "public_date": "2026-08-06T23:00:00Z",
        }, {
            "news_title": "Older article", "public_date": "2026-08-06T00:00:00Z",
        }],
    })()
    cursors = []

    def fetch_page(_company, cursor):
        cursors.append(cursor)
        return frame, "older_cursor"

    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["VCB"])
    monkeypatch.setattr(aggregator, "_rate_limit", lambda *_: None)
    monkeypatch.setattr(aggregator, "_fetch_vnstock_page", fetch_page)
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Company=lambda **_kwargs: object()))

    articles = aggregator._scrape_vnstock_news(datetime(2026, 8, 7, tzinfo=timezone.utc), hours_back=24)

    assert cursors == [None]
    assert [article.text for article in articles] == ["VCB tăng"]


@pytest.mark.parametrize("metadata", [None, {}, {"news_order": None}, {"news_order": "Descending"},
                                      {"news_order": []}, {"pagination": {"news_order": "descending"}},
                                      {"news_order": "descending"}])
def test_news_pagination_untrusted_or_violated_order_continues(monkeypatch, metadata):
    import pandas as pd

    aggregator = NewsAggregator()
    calls = []
    pages = [
        [("Old", "2026-08-05T00:00:00Z"), ("VCB tăng", "2026-08-06T23:00:00Z")],
        [("VCB tăng tiếp", "2026-08-06T22:00:00Z"), ("Future", "2026-08-07T00:00:00Z")],
    ]

    def fetch_page(_company, cursor):
        calls.append(cursor)
        frame = pd.DataFrame(pages[len(calls) - 1], columns=["news_title", "public_date"])
        frame.attrs = metadata if isinstance(metadata, dict) else {}
        return frame, "next" if cursor is None else None

    monkeypatch.setattr(aggregator, "_fetch_vnstock_page", fetch_page)
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["VCB"])
    monkeypatch.setattr(aggregator, "_rate_limit", lambda *_: None)
    articles = aggregator._scrape_vnstock_news(datetime(2026, 8, 7, tzinfo=timezone.utc))
    assert calls == [None, "next"]
    assert [article.text for article in articles] == ["VCB tăng", "VCB tăng tiếp"]


@pytest.mark.parametrize("initial_order,later_order", [(None, None), (None, "descending"),
                                                        (None, "ascending"), ("descending", None),
                                                        ("descending", "ascending")])
def test_news_pagination_order_cannot_become_trusted_after_first_page(monkeypatch, initial_order, later_order):
    import pandas as pd

    aggregator = NewsAggregator()
    calls = []
    pages = [
        [("VCB tăng", "2026-08-06T23:00:00Z")],
        [("Old", "2026-08-06T00:00:00Z")],
        [("VCB tăng tiếp", "2026-08-06T22:00:00Z")],
    ]

    def fetch_page(_company, cursor):
        calls.append(cursor)
        frame = pd.DataFrame(pages[len(calls) - 1], columns=["news_title", "public_date"])
        frame.attrs["news_order"] = initial_order if cursor is None else later_order
        return frame, str(len(calls)) if len(calls) < len(pages) else None

    monkeypatch.setattr(aggregator, "_fetch_vnstock_page", fetch_page)
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["VCB"])
    monkeypatch.setattr(aggregator, "_rate_limit", lambda *_: None)
    articles = aggregator._scrape_vnstock_news(datetime(2026, 8, 7, tzinfo=timezone.utc))
    assert calls == [None, "1", "2"]
    assert [article.text for article in articles] == ["VCB tăng", "VCB tăng tiếp"]


@pytest.mark.parametrize("invalid", [None, "", "not-a-date", float("nan"), float("inf"),
                                     float("-inf"), [], {}, 10**13])
def test_news_pagination_invalid_dates_disable_order_shortcut(monkeypatch, invalid):
    import pandas as pd

    aggregator = NewsAggregator()
    calls = []

    def fetch_page(_company, cursor):
        calls.append(cursor)
        dates = [invalid, "2026-08-06T00:00:00Z"] if cursor is None else ["2026-08-06T22:00:00Z"]
        frame = pd.DataFrame({"news_title": ["VCB tăng"] * len(dates), "public_date": dates})
        frame.attrs["news_order"] = "descending"
        return frame, "next" if cursor is None else None

    monkeypatch.setattr(aggregator, "_fetch_vnstock_page", fetch_page)
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["VCB"])
    monkeypatch.setattr(aggregator, "_rate_limit", lambda *_: None)
    articles = aggregator._scrape_vnstock_news(datetime(2026, 8, 7, tzinfo=timezone.utc))
    assert calls == [None, "next"]
    assert [article.text for article in articles] == ["VCB tăng"]


def test_fetch_vnstock_page_allows_missing_pagination_metadata():
    frame = type("Frame", (), {"attrs": {}})()
    company = type("Company", (), {"news": lambda *_args, **_kwargs: frame})()

    assert NewsAggregator._fetch_vnstock_page(company, cursor=None) == (frame, None)


def test_quarantine_preserves_prior_evidence_and_deduplicates_checksum(tmp_path):
    import pyarrow.parquet as pq

    published = datetime(2026, 1, 2, tzinfo=timezone.utc)
    output, quarantine = tmp_path / "news.parquet", tmp_path / "quarantine.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"reason": "prior", "source": "fixture", "fetched_at": published, "parser_version": "v", "payload_sha256": "prior", "raw_payload": "{}"},
        {"reason": "old", "source": "fixture", "fetched_at": published, "parser_version": "v", "payload_sha256": "duplicate", "raw_payload": "{\"old\": true}"},
    ], schema=QUARANTINE_SCHEMA), quarantine)

    class Aggregator:
        def fetch_recent_news(self, as_of_time, hours_back):
            return [type("Article", (), {"ticker": None, "text": "missing ticker", "timestamp": published, "payload_sha256": "duplicate"})()]

    build_news_sentiment(output, Aggregator(), incremental=True, quarantine_path=quarantine)
    table = pq.read_table(quarantine)
    assert table.column("payload_sha256").to_pylist() == ["prior", "duplicate"]
    assert table.column("reason").to_pylist() == ["prior", "missing_required_article_fields"]
