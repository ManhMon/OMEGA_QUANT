"""Macro News Hub contracts: PIT, finite arithmetic, bounded streaming."""
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omega.api.routes import sentiment as route

CUTOFF = "2026-08-20T08:30:00Z"  # 15:30 ICT, inclusive close.
DT = datetime(2026, 8, 20, 8, 30, tzinfo=timezone.utc)
LATEST = "/api/v1/macro/news/latest"
STREAM = "/sse/v1/macro/news-stream"
VSI = "/api/v1/sentiment/vsi"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "MACRO_NEWS_PATH", tmp_path / "macro.parquet")
    monkeypatch.setattr(route, "NEWS_SENTIMENT_PATH", tmp_path / "sentiment.parquet")
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as client:
        yield client


def store(rows, source="macro"):
    column = "published_at" if source == "macro" else "publish_time"
    path = route.MACRO_NEWS_PATH if source == "macro" else route.NEWS_SENTIMENT_PATH
    defaults = {column: CUTOFF, "available_at": CUTOFF, "title": "tăng mạnh",
                "origin_ticker": "FPT", "symbol": "FPT", "sector": "Technology"}
    pd.DataFrame([{**defaults, **row} for row in rows]).to_parquet(path, row_group_size=1)


@pytest.mark.parametrize("path", [LATEST, STREAM])
@pytest.mark.parametrize("limit", ["0", "-1", "101", "1e13", "NaN", "Inf", "[]", "abc", "1.5"])
def test_limit_rejected(client, path, limit):
    assert client.get(path, params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("limit", [1, 100])
def test_limit_inclusive(client, limit):
    store([{"raw_record_id": str(i)} for i in range(120)])
    response = client.get(LATEST, params={"limit": limit, "as_of": CUTOFF})
    assert response.status_code == 200
    assert response.json()["total_count"] == limit


@pytest.mark.parametrize("path", [LATEST, VSI])
@pytest.mark.parametrize("cutoff", ["", " ", "bad", "NaN", "2026-13-01", "2999-01-01T00:00:00Z"])
def test_invalid_cutoff(client, path, cutoff):
    response = client.get(path, params={"as_of": cutoff})
    assert response.status_code == 400
    assert cutoff not in response.json()["detail"] if cutoff.strip() else True


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("published,available", [
    (CUTOFF, None), (CUTOFF, ""), (CUTOFF, "bad"),
    (None, CUTOFF), ("", CUTOFF), ("bad", CUTOFF),
    (CUTOFF, "2026-08-20T08:29:59Z"),
    (CUTOFF, "2026-08-20T08:30:01Z"),
    ("2026-08-20T08:30:01Z", "2026-08-20T08:30:01Z"),
])
def test_pit_fail_closed(client, source, published, available):
    column = "published_at" if source == "macro" else "publish_time"
    store([{column: published, "available_at": available}], source)
    assert route._load_macro_news_records(as_of=DT) == []
    assert client.get(LATEST, params={"as_of": CUTOFF}).json()["items"] == []
    data = client.get(VSI, params={"as_of": CUTOFF}).json()
    assert data["article_count"] == 0
    assert data["score"] == 50.0
    assert data["level"] == "neutral"
    assert not data["is_synthetic"]


@pytest.mark.parametrize("cutoff", [CUTOFF, "2026-08-20T15:30:00+07:00", "2026-08-20T08:30:00"])
def test_inclusive_timezone_close(client, cutoff):
    store([{}])
    data = client.get(LATEST, params={"as_of": cutoff}).json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["published_at"] == item["available_at"] == data["as_of"]
    assert client.get(VSI, params={"as_of": cutoff}).json()["article_count"] == 1


@pytest.mark.parametrize("value", [None, "", "bad", [], {}, [1, 2], float("nan"), float("inf"), -float("inf"), True, pytest.param(10 ** 1000, id="overflow")])
def test_numeric_sanitizer(value):
    assert route._sanitize_float(value) == 0.0


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("value,expected", [(float("nan"), 0), (float("inf"), 0), (-float("inf"), 0),
                                          (1e13, 1), (-1e13, -1), (0, 0), (0.5, 0.5)])
def test_store_finite_scores(client, source, value, expected):
    store([{"sentiment_score": value}], source)
    response = client.get(LATEST, params={"as_of": CUTOFF})
    assert response.status_code == 200
    assert response.json()["items"][0]["sentiment_score"] == expected
    assert "NaN" not in response.text and "Infinity" not in response.text


@pytest.mark.parametrize("value", [None, "", [], {}, 1, float("nan"), float("inf")])
def test_timestamp_malformed(value):
    assert route._timestamp(value) is None


@pytest.mark.parametrize("limit", [0, -1, 101, 1.5, True, None, "1"])
def test_loader_limit_boundary(limit):
    with pytest.raises(ValueError):
        route._load_macro_news_records(limit=limit)


def test_newest_across_stores_and_batches(client):
    store([{"title": "older", "published_at": "2026-08-19T00:00:00Z"},
           {"title": "newer", "published_at": "2026-08-20T07:00:00Z"}])
    store([{"title": "newest"}], "sentiment")
    items = route._load_macro_news_records(limit=2, as_of=DT)
    assert [item.title for item in items] == ["newest", "newer"]
    first = items[0].news_id
    store([{"title": "inserted older", "publish_time": "2026-08-18T00:00:00Z"},
           {"title": "newest"}], "sentiment")
    assert route._load_macro_news_records(limit=2, as_of=DT)[0].news_id == first
    store([{"title": "duplicate"}] * 300)
    assert len(route._load_macro_news_records(limit=100, as_of=DT)) == 100


def test_filters_and_empty_data(client):
    store([{"origin_ticker": "OTHER"}, {}, {"sector": "Banking"}])
    data = client.get(LATEST, params={"ticker": " fpt ", "sector": " technology ", "as_of": CUTOFF}).json()
    assert data["total_count"] == 1
    assert client.get(LATEST, params={"ticker": "ABSENT", "as_of": CUTOFF}).json()["items"] == []
    assert client.get(LATEST, params={"ticker": "x" * 33}).status_code == 422
    assert client.get(LATEST, params={"sector": "x" * 101}).status_code == 422


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("fault", ["directory", "utf8", "bom", "partial", "permission", "mid_batch"])
@pytest.mark.parametrize("as_of", [None, CUTOFF])
def test_store_fault_no_partial_snapshot(client, monkeypatch, source, fault, as_of):
    store([{}], "macro")
    path = route.MACRO_NEWS_PATH if source == "macro" else route.NEWS_SENTIMENT_PATH
    if fault == "directory":
        if path.exists():
            path.unlink()
        path.mkdir()
    elif fault in ["utf8", "bom", "partial"]:
        path.write_bytes({"utf8": b"\xff\xfe", "bom": b"\xef\xbb\xbf\r\n", "partial": b"PAR1"}[fault])
    elif fault == "permission":
        def fail(*args, **kwargs):
            raise PermissionError("https://user:password@example.com/api?api_key=secret")
        monkeypatch.setattr(route.pq, "ParquetFile", fail)
    else:
        class Broken:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def iter_batches(self, **kwargs):
                import pyarrow as pa
                yield pa.RecordBatch.from_pylist([{"title": "partial", "published_at": CUTOFF, "available_at": CUTOFF}])
                raise OSError("private error")
        monkeypatch.setattr(route.pq, "ParquetFile", lambda *args: Broken())
    for endpoint in [LATEST, VSI]:
        response = client.get(endpoint, params={"as_of": as_of} if as_of is not None else {})
        assert response.status_code == 424
        assert response.json() == {"detail": "Macro news store unavailable"}


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def fast_stream(monkeypatch):
    async def no_wait(*args):
        return None
    monkeypatch.setattr(route.asyncio, "sleep", no_wait)


def test_stream_snapshot_heartbeat_provenance(client, fast_stream):
    store([{}])
    response = client.get(STREAM, params={"limit": 3})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    data = events(response)
    assert [event["event_type"] for event in data] == ["SNAPSHOT", "HEARTBEAT", "HEARTBEAT"]
    assert len({event["event_id"] for event in data}) == 3
    assert data[0]["items"][0]["published_at"] == DT.isoformat()
    for event in data:
        assert event["as_of"] == event["timestamp"]
        assert not event["is_synthetic"]
        assert event["source"] == "parquet_store"


def test_stream_new_item_preserves_publication(client, monkeypatch):
    async def add_article(*args):
        store([{}, {"title": "new article", "published_at": "2026-08-20T08:00:00Z"}])
    monkeypatch.setattr(route.asyncio, "sleep", add_article)
    store([{}])
    data = events(client.get(STREAM, params={"limit": 3}))
    assert [event["event_type"] for event in data] == ["SNAPSHOT", "NEWS_ITEM", "HEARTBEAT"]
    assert data[1]["item"]["title"] == "new article"
    assert data[1]["item"]["published_at"] == "2026-08-20T08:00:00+00:00"


def test_stream_empty_error_and_isolation(client, fast_stream):
    first = events(client.get(STREAM, params={"limit": 2}))
    second = events(client.get(STREAM, params={"limit": 1}))
    assert first[0]["items"] == [] and first[1]["event_type"] == "HEARTBEAT"
    assert first[0]["event_id"] != second[0]["event_id"]
    route.MACRO_NEWS_PATH.write_bytes(b"corrupted")
    data = events(client.get(STREAM, params={"limit": 100}))
    assert len(data) == 1
    assert data[0]["event_type"] == "ERROR"
    assert data[0]["code"] == "NEWS_STREAM_UNAVAILABLE"
    assert "corrupted" not in json.dumps(data)


def test_stream_cancellation_propagates(client, monkeypatch):
    def cancel(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(route, "_load_macro_news_records", cancel)
    async def consume():
        response = await route.sse_macro_news_stream(limit=1)
        with pytest.raises(asyncio.CancelledError):
            await anext(response.body_iterator)
    asyncio.run(consume())


def test_vsi_history_has_own_cutoffs(client):
    store([{}])
    response = client.get(VSI, params={"as_of": CUTOFF})
    assert response.status_code == 200
    data = response.json()
    assert data["article_count"] == 1
    assert [point["article_count"] for point in data["history_7d"]] == [0] * 7 + [1]
    assert all(point["vsi_score"] == 50 for point in data["history_7d"][:-1])
    assert data["history_7d"][-1]["as_of"] == data["as_of"]
    assert sum(data[key] for key in ["bullish_ratio", "bearish_ratio", "neutral_ratio"]) == pytest.approx(1)


def test_vsi_rechecks_unverified_records(client, monkeypatch):
    monkeypatch.setattr(route, "_load_macro_news_records", lambda **kwargs: [
        {"title": "future", "published_at": CUTOFF, "available_at": "2026-08-20T09:00:00Z"},
        {"title": "missing", "published_at": CUTOFF},
        {"title": "bad", "published_at": [], "available_at": CUTOFF}])
    assert client.get(VSI, params={"as_of": CUTOFF}).json()["article_count"] == 0


def test_vsi_nonfinite_engine_boundary(client, monkeypatch):
    monkeypatch.setattr(route, "_vsi_at", lambda *args: SimpleNamespace(
        score=float("nan"), avg_sentiment=float("inf"), bullish_ratio=-float("inf"),
        bearish_ratio=1e13, neutral_ratio=-1e13, article_count=0))
    response = client.get(VSI, params={"as_of": CUTOFF})
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 50 and data["avg_sentiment"] == 0
    assert data["bullish_ratio"] == 0 and data["bearish_ratio"] == 1 and data["neutral_ratio"] == 0
    assert "NaN" not in response.text and "Infinity" not in response.text


def test_contagion_index_and_simulation_contract(client):
    response = client.get("/api/v1/sentiment/contagion")
    assert response.status_code == 200
    data = response.json()
    nodes = data["nodes"]
    assert data["is_synthetic"] and data["source"] == "synthetic_simulation"
    assert data["overall_contagion_index"] == round(sum(node["stress_score"] for node in nodes) / len(nodes), 1)
    assert data["systemic_risk_level"] == "MODERATE"
    for node in nodes:
        stress = node["stress_score"]
        expected = "CRITICAL" if stress >= 80 else "HIGH" if stress >= 65 else "ELEVATED" if stress >= 50 else "NORMAL" if stress >= 30 else "LOW"
        assert node["contagion_level"] == expected
        assert 0 <= node["transmission_risk"] <= 1
        assert all(0 <= sector["correlation_weight"] <= 1 for sector in node["correlated_sectors"])


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("available", [None, "", " ", float("nan")])
def test_live_legacy_availability_never_enters_history(client, source, available):
    store([{"available_at": available}], source)
    records = route._load_macro_news_records()
    assert len(records) == 1
    assert records[0]["available_at"] == records[0]["published_at"]
    assert route._load_macro_news_records(as_of=DT) == []
    latest = client.get(LATEST).json()
    assert latest["total_count"] == 1 and not latest["is_synthetic"]
    assert latest["items"][0]["available_at"] == latest["items"][0]["published_at"]
    assert client.get(LATEST, params={"as_of": CUTOFF}).json()["items"] == []
    live_vsi = client.get(VSI).json()
    assert live_vsi["article_count"] == 1 and not live_vsi["is_synthetic"]
    assert all(point["article_count"] == 0 for point in live_vsi["history_7d"])
    historical_vsi = client.get(VSI, params={"as_of": CUTOFF}).json()
    assert historical_vsi["article_count"] == 0 and historical_vsi["score"] == 50
    assert not historical_vsi["is_synthetic"]
    snapshot = events(client.get(STREAM, params={"limit": 1}))[0]
    assert snapshot["event_type"] == "SNAPSHOT" and snapshot["count"] == 1
    assert not snapshot["is_synthetic"]


@pytest.mark.parametrize("source", ["macro", "sentiment"])
def test_live_missing_availability_column(client, source):
    column = "published_at" if source == "macro" else "publish_time"
    path = route.MACRO_NEWS_PATH if source == "macro" else route.NEWS_SENTIMENT_PATH
    pd.DataFrame([{column: CUTOFF, "title": "Legacy"}]).to_parquet(path)
    assert client.get(LATEST).json()["total_count"] == 1
    assert route._load_macro_news_records(as_of=DT) == []


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("available", ["invalid", "2026-08-20T08:29:59Z", "2099-01-01T00:00:00Z",
                                       [], {"invalid": "value"}, True, 0, 1e13, float("inf"), -float("inf")])
def test_live_invalid_availability_never_falls_back(client, source, available):
    store([{"available_at": available}], source)
    assert route._load_macro_news_records() == []
    assert client.get(LATEST).json()["items"] == []
    assert client.get(VSI).json()["article_count"] == 0
    assert events(client.get(STREAM, params={"limit": 1}))[0]["count"] == 0


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("published", [None, "", "invalid", "2099-01-01T00:00:00Z", [], {"invalid": "value"}, True,
                                       0, 1e13, float("nan"), float("inf"), -float("inf")])
def test_live_fallback_requires_valid_publication(client, source, published):
    column = "published_at" if source == "macro" else "publish_time"
    store([{column: published, "available_at": None}], source)
    assert route._load_macro_news_records() == []
    assert client.get(LATEST).json()["total_count"] == 0
    assert client.get(VSI).json()["article_count"] == 0


@pytest.mark.parametrize("endpoint", [LATEST, VSI])
def test_live_unverified_records_keep_strict_availability(client, monkeypatch, endpoint):
    monkeypatch.setattr(route, "_load_macro_news_records", lambda *args, **kwargs: [
        {"title": "Missing", "published_at": CUTOFF},
        {"title": "Invalid", "published_at": CUTOFF, "available_at": "invalid"},
        {"title": "Future", "published_at": CUTOFF, "available_at": "2099-01-01T00:00:00Z"},
    ])
    data = client.get(endpoint).json()
    assert data["total_count" if endpoint == LATEST else "article_count"] == 0
    assert not data["is_synthetic"]


@pytest.mark.parametrize("value", [
    "2026-08-20T08:30:00.000000001Z",
    "2026-08-20T15:30:00.000000001+07:00",
    "2026-08-20T08:30:00.123456789Z",
    "2026-08-20T08:30:00.0000000001Z",
    pd.Timestamp("2026-08-20T08:30:00.000000001Z"),
])
def test_submicrosecond_normalizer_rejects_before_truncation(value):
    assert route._timestamp(value) is None
    for field in ["published_at", "available_at"]:
        assert route._pit_times({"published_at": CUTOFF, "available_at": CUTOFF, field: value}, DT) is None
    assert route._pit_times({"published_at": CUTOFF, "available_at": CUTOFF}, value) is None


@pytest.mark.parametrize("source", ["macro", "sentiment"])
@pytest.mark.parametrize("published,available", [
    (CUTOFF, "2026-08-20T08:30:00.000000001Z"),
    ("2026-08-20T08:29:59.000000002Z", "2026-08-20T08:29:59.000000001Z"),
    ("2026-08-20T08:30:00.000000001Z", None),
])
def test_submicrosecond_store_rows_fail_closed(client, fast_stream, source, published, available):
    column = "published_at" if source == "macro" else "publish_time"
    store([{column: published, "available_at": available}], source)
    assert route._load_macro_news_records(as_of=DT) == []
    assert client.get(LATEST, params={"as_of": CUTOFF}).json()["items"] == []
    assert client.get(VSI, params={"as_of": CUTOFF}).json()["article_count"] == 0
    assert client.get(LATEST).json()["items"] == []
    assert events(client.get(STREAM, params={"limit": 1}))[0]["count"] == 0


@pytest.mark.parametrize("endpoint", [LATEST, VSI])
def test_submicrosecond_unverified_records_rechecked(client, monkeypatch, endpoint):
    monkeypatch.setattr(route, "_load_macro_news_records", lambda *args, **kwargs: [
        {"title": "future", "published_at": CUTOFF, "available_at": "2026-08-20T08:30:00.000000001Z"},
        {"title": "reversed", "published_at": "2026-08-20T08:29:59.000000002Z",
         "available_at": "2026-08-20T08:29:59.000000001Z"},
    ])
    data = client.get(endpoint, params={"as_of": CUTOFF}).json()
    assert data["total_count" if endpoint == LATEST else "article_count"] == 0


@pytest.mark.parametrize("endpoint", [LATEST, VSI])
@pytest.mark.parametrize("as_of", ["2026-08-20T08:30:00.000000001Z", "2026-08-20T08:30:00.0000000001Z"])
def test_submicrosecond_cutoff_rejected_before_io(client, monkeypatch, endpoint, as_of):
    def unexpected_io(*args, **kwargs):
        pytest.fail("Invalid cutoff reached store")
    monkeypatch.setattr(route, "_load_macro_news_records", unexpected_io)
    response = client.get(endpoint, params={"as_of": as_of})
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid as_of timestamp format"}


def test_submicrosecond_direct_loader_cutoff_rejected(client):
    with pytest.raises(ValueError, match="Invalid as_of timestamp format"):
        route._load_macro_news_records(as_of=pd.Timestamp("2026-08-20T08:30:00.000000001Z"))


@pytest.mark.parametrize("cutoff", [
    "2026-08-20T08:30:00.123456Z", "2026-08-20T15:30:00.123456000+07:00",
])
def test_microsecond_precision_inclusive_boundary(client, cutoff):
    store([{"published_at": "2026-08-20T08:30:00.123456000Z", "available_at": cutoff}])
    data = client.get(LATEST, params={"as_of": cutoff}).json()
    assert data["total_count"] == 1
    assert data["items"][0]["available_at"] == data["as_of"] == "2026-08-20T08:30:00.123456+00:00"
    assert client.get(VSI, params={"as_of": cutoff}).json()["article_count"] == 1
    assert client.get(LATEST, params={"as_of": "2026-08-20T08:30:00.123455Z"}).json()["items"] == []


@pytest.mark.parametrize("as_of", [
    "0001-01-01", "0001-01-07T23:59:59.999999Z", "0001-01-08T00:00:00+07:00",
    "0001-01-01T00:00:00+07:00",
])
def test_vsi_ancient_cutoff_rejected_before_io(client, monkeypatch, as_of):
    def unexpected_io(*args, **kwargs):
        pytest.fail("Unsupported VSI window reached store")
    monkeypatch.setattr(route, "_load_macro_news_records", unexpected_io)
    response = client.get(VSI, params={"as_of": as_of})
    assert response.status_code == 400
    assert as_of not in response.json()["detail"]


@pytest.mark.parametrize("as_of", ["0001-01-08T00:00:00Z", "0001-01-08T07:00:00+07:00"])
def test_vsi_minimum_window_inclusive(client, as_of):
    response = client.get(VSI, params={"as_of": as_of})
    assert response.status_code == 200
    history = response.json()["history_7d"]
    assert len(history) == 8
    assert history[0]["as_of"] == "0001-01-01T00:00:00+00:00"
    assert history[-1]["as_of"] == response.json()["as_of"]
    assert all(point["article_count"] == 0 for point in history)


@pytest.mark.parametrize("source", ["macro", "sentiment"])
def test_news_id_prefix_digest_stability_and_stream_contract(client, fast_stream, source):
    store([{"raw_record_id": "same", "payload_sha256": "same"}], source)
    item = client.get(LATEST, params={"as_of": CUTOFF}).json()["items"][0]
    source_name = "parquet_macro_news" if source == "macro" else "parquet_news_sentiment"
    digest = hashlib.sha256(json.dumps([source_name, "FPT", "same", "tăng mạnh",
                                       DT.isoformat(), DT.isoformat()], ensure_ascii=False).encode("utf-8")).hexdigest()
    assert item["news_id"] == "mnews_" + digest
    assert re.fullmatch(r"mnews_[0-9a-f]{64}", item["news_id"])
    column = "published_at" if source == "macro" else "publish_time"
    store([{column: "2026-08-19T00:00:00Z", "raw_record_id": "old", "payload_sha256": "old"},
           {"raw_record_id": "same", "payload_sha256": "same"}], source)
    assert client.get(LATEST, params={"as_of": CUTOFF, "limit": 1}).json()["items"][0]["news_id"] == item["news_id"]
    snapshot = events(client.get(STREAM, params={"limit": 2}))
    assert snapshot[0]["items"][0]["news_id"] == item["news_id"]
    assert snapshot[1]["event_type"] == "HEARTBEAT"
    other = "sentiment" if source == "macro" else "macro"
    store([{"raw_record_id": "same", "payload_sha256": "same"}], other)
    ids = [entry["news_id"] for entry in client.get(LATEST, params={"as_of": CUTOFF}).json()["items"]]
    assert len(ids) == len(set(ids)) == 3


def test_intelligence_honest_provenance(client):
    response = client.get("/api/v1/sentiment/llm-analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["is_synthetic"] and data["source"] == "synthetic_simulation"
    assert data["model"] == "synthetic_macro_template"
    assert data["sentiment_confidence"] == 0
    assert data["executive_verdict"] == "NEUTRAL"
    assert data["primary_risks"] and data["catalysts"] and data["sector_impacts"]
    assert not any(secret in response.text.lower() for secret in ["api_key", "password", "bearer"])
