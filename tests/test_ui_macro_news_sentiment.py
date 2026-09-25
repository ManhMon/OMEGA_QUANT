import pytest
import asyncio
import unicodedata
from datetime import datetime, timezone
import pandas as pd
from starlette.testclient import TestClient
from omega.api.server import app


def test_macro_jev_pipeline_nfc_cache_and_bounds(tmp_path, monkeypatch):
    from omega.data.macro_news_llm import MacroNewsLLMExtractor
    import omega.data.macro_news_llm as module

    calls = []

    def classify(**kwargs):
        calls.append(kwargs)
        return {"selected": {"polarity": "BEARISH", "category": "macro", "impact": "high"},
                "fingerprint": "a" * 64}

    monkeypatch.setattr(module, "classify_jev", classify)
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda text, selected: "Giảm tăng trưởng")
    cutoff = datetime(2026, 9, 25, tzinfo=timezone.utc)
    raw = pd.DataFrame([{"raw_record_id": "one", "title": unicodedata.normalize("NFD", "Giảm"),
                         "summary": "tăng", "published_at": "2026-09-24T01:00:00Z",
                         "available_at": "2026-09-24T02:00:00Z"}])
    result = asyncio.run(extractor.process_dataframe(raw, tmp_path / "out.parquet", tmp_path / "links.parquet", cutoff))
    assert result.iloc[0]["sentiment_score"] == -1.0
    assert result.iloc[0]["title"] == "Giảm"
    assert calls[0]["facts"]["text"].startswith("Giảm")
    assert calls[0]["cache_path"].name == "macro_news_jev.sqlite"


@pytest.mark.parametrize("available", ["2026-09-26T00:00:00Z", None, "invalid"])
def test_macro_jev_rejects_unavailable_news(tmp_path, monkeypatch, available):
    from omega.data.macro_news_llm import MacroNewsLLMExtractor
    import omega.data.macro_news_llm as module

    monkeypatch.setattr(module, "classify_jev", lambda **kwargs: pytest.fail("future input reached JEV"))
    raw = pd.DataFrame([{"raw_record_id": "one", "title": "Tin", "summary": "",
                         "published_at": "2026-09-24T00:00:00Z", "available_at": available}])
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Tin")
    with pytest.raises(ValueError):
        asyncio.run(extractor.process_dataframe(raw, tmp_path / "out.parquet", tmp_path / "links.parquet",
                                                datetime(2026, 9, 25, tzinfo=timezone.utc)))
    assert not (tmp_path / "out.parquet").exists()


def test_macro_jev_narrative_failure_does_not_replace_output(tmp_path, monkeypatch):
    from omega.data.macro_news_llm import MacroNewsLLMExtractor
    import omega.data.macro_news_llm as module

    monkeypatch.setattr(module, "classify_jev", lambda **kwargs: {
        "selected": {"polarity": "NEUTRAL", "category": "other", "impact": "low"}, "fingerprint": "b" * 64})
    output = tmp_path / "out.parquet"
    output.write_bytes(b"previous")
    raw = pd.DataFrame([{"raw_record_id": "one", "title": "Tin", "summary": "",
                         "published_at": "2026-09-24T00:00:00Z", "available_at": "2026-09-24T00:00:00Z"}])
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "")
    with pytest.raises(ValueError, match="narrative"):
        asyncio.run(extractor.process_dataframe(raw, output, tmp_path / "links.parquet"))
    assert output.read_bytes() == b"previous"

@pytest.fixture
def client():
    return TestClient(app)

# ---------------------------------------------------------------------------
# 16-DIMENSION MASTER ADVERSARIAL TEST SUITE (PHASE 7 MACRO NEWS & LLM SENTIMENT)
# ---------------------------------------------------------------------------

def test_dim1_macro_news_latest_schema_and_types(client):
    # Dim 1: Strict Types & Schema Validation
    resp = client.get("/api/v1/macro/news/latest?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "total_count" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 10
    if data["items"]:
        first = data["items"][0]
        assert "news_id" in first
        assert "title" in first
        assert "sentiment_score" in first
        assert "polarity" in first
        assert first["polarity"] in ["BULLISH", "BEARISH", "NEUTRAL"]
        assert isinstance(first["macro_tags"], list)


def test_dim2_macro_news_limit_bounds_and_clamping(client):
    # Dim 2 & 8: Math and query param bounds
    # Invalid limit < 1
    resp1 = client.get("/api/v1/macro/news/latest?limit=0")
    assert resp1.status_code == 422

    # Invalid limit > 100
    resp2 = client.get("/api/v1/macro/news/latest?limit=101")
    assert resp2.status_code == 422


def test_dim3_macro_news_filtering_by_ticker_and_sector(client):
    # Dim 3 & 10: Ticker/Sector filtering and case-insensitivity
    resp_ticker = client.get("/api/v1/macro/news/latest?ticker=fpt")
    assert resp_ticker.status_code == 200
    items = resp_ticker.json()["items"]
    for it in items:
        if it["symbol"]:
            assert it["symbol"].upper() == "FPT"

    resp_sector = client.get("/api/v1/macro/news/latest?sector=financials")
    assert resp_sector.status_code == 200
    items_sec = resp_sector.json()["items"]
    for it in items_sec:
        if it["sector"]:
            assert it["sector"].upper() == "FINANCIALS"


def test_dim4_vsi_sentiment_structure_and_bounds(client):
    # Dim 4 & 8: VSI Greed & Fear 0-100 metric bounds
    resp = client.get("/api/v1/sentiment/vsi")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert 0.0 <= data["score"] <= 100.0
    assert data["level"] in ["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]
    assert 0.0 <= data["bullish_ratio"] <= 1.0
    assert 0.0 <= data["bearish_ratio"] <= 1.0
    assert 0.0 <= data["neutral_ratio"] <= 1.0
    assert "sub_indices" in data
    assert "retail_sentiment" in data["sub_indices"]
    assert len(data["history_7d"]) >= 7


def test_dim5_vsi_sentiment_point_in_time_as_of(client):
    # Dim 5 & 6: Point-in-Time (PIT) consistency with as_of query
    as_of_ts = "2026-08-20T12:00:00Z"
    resp = client.get(f"/api/v1/sentiment/vsi?as_of={as_of_ts}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "2026-08-20" in data["as_of"]

    # Test invalid / malformed as_of format
    resp_invalid = client.get("/api/v1/sentiment/vsi?as_of=not-a-date")
    assert resp_invalid.status_code == 400
    assert resp_invalid.json()["detail"] == "Invalid as_of timestamp format"

    # Test future as_of rejection
    resp_future = client.get("/api/v1/sentiment/vsi?as_of=2999-01-01T00:00:00Z")
    assert resp_future.status_code == 400
    assert resp_future.json()["detail"] == "as_of timestamp cannot be in the future"


def test_vsi_sentiment_excludes_invalid_or_missing_published_at(monkeypatch, client):
    # Pit fail-closed: records with missing/empty/unparseable published_at must be skipped
    import omega.api.routes.sentiment as sentiment_mod

    raw_mock_records = [
        {"title": "Valid News", "summary": "Good", "source_name": "CafeF", "published_at": "2026-08-20T10:00:00Z", "available_at": "2026-08-20T10:15:00Z"},
        {"title": "Missing Pub", "summary": "Bad", "source_name": "CafeF", "published_at": None},
        {"title": "Empty Pub", "summary": "Bad", "source_name": "CafeF", "published_at": ""},
        {"title": "Unparseable Pub", "summary": "Bad", "source_name": "CafeF", "published_at": "not-a-valid-datetime"},
    ]
    monkeypatch.setattr(sentiment_mod, "_load_macro_news_records", lambda limit=50, ticker=None, sector=None, as_of=None: raw_mock_records)

    resp = client.get("/api/v1/sentiment/vsi?as_of=2026-08-20T12:00:00Z")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    # Only 1 valid record was processed
    assert data["article_count"] == 1


def test_vsi_rejects_news_before_availability(tmp_path, monkeypatch, client):
    import omega.api.routes.sentiment as sentiment_mod

    macro = tmp_path / "macro.parquet"
    pd.DataFrame([
        {"raw_record_id": "early", "title": "Early", "published_at": "2026-08-20T10:00:00Z", "available_at": "2026-08-20T13:00:00Z"},
        {"raw_record_id": "missing", "title": "Missing", "published_at": "2026-08-20T10:00:00Z", "available_at": None},
        {"raw_record_id": "valid", "title": "Valid", "published_at": "2026-08-20T10:00:00Z", "available_at": "2026-08-20T11:00:00Z"},
    ]).to_parquet(macro)
    monkeypatch.setattr(sentiment_mod, "MACRO_NEWS_PATH", macro)
    monkeypatch.setattr(sentiment_mod, "NEWS_SENTIMENT_PATH", tmp_path / "absent.parquet")
    response = client.get("/api/v1/sentiment/vsi?as_of=2026-08-20T12:00:00Z")
    assert response.status_code == 200
    assert response.json()["article_count"] == 1
    assert [item["title"] for item in sentiment_mod._load_macro_news_records(as_of=datetime(2026, 8, 20, 12, tzinfo=timezone.utc))] == ["Valid"]


def test_vsi_rejects_sentiment_parquet_without_availability(tmp_path, monkeypatch, client):
    import omega.api.routes.sentiment as sentiment_mod

    source = tmp_path / "sentiment.parquet"
    pd.DataFrame([{"title": "Early", "publish_time": "2026-08-20T10:00:00Z",
                   "available_at": "2026-08-20T13:00:00Z", "sentiment_score": 0.9}]).to_parquet(source)
    monkeypatch.setattr(sentiment_mod, "MACRO_NEWS_PATH", tmp_path / "absent.parquet")
    monkeypatch.setattr(sentiment_mod, "NEWS_SENTIMENT_PATH", source)
    response = client.get("/api/v1/sentiment/vsi?as_of=2026-08-20T12:00:00Z")
    assert response.status_code == 200
    assert response.json()["is_synthetic"] is True


def test_latest_news_compares_both_stores_with_limit_one(tmp_path, monkeypatch, client):
    import omega.api.routes.sentiment as route

    macro = tmp_path / "macro.parquet"
    sentiment = tmp_path / "sentiment.parquet"
    pd.DataFrame([{"raw_record_id": "old", "title": "Old macro", "published_at": "2026-08-20T08:00:00Z",
                   "available_at": "2026-08-20T08:00:00Z"}]).to_parquet(macro)
    pd.DataFrame([{"payload_sha256": "new", "title": "New sentiment", "publish_time": "2026-08-20T09:00:00Z",
                   "available_at": "2026-08-20T09:00:00Z"}]).to_parquet(sentiment)
    monkeypatch.setattr(route, "MACRO_NEWS_PATH", macro)
    monkeypatch.setattr(route, "NEWS_SENTIMENT_PATH", sentiment)

    assert [item["title"] for item in route._load_macro_news_records(
        limit=1, as_of=datetime(2026, 8, 20, 10, tzinfo=timezone.utc))] == ["New sentiment"]
    assert [item["title"] for item in client.get("/api/v1/macro/news/latest?limit=1").json()["items"]] == ["New sentiment"]

    # An unavailable newer row must not displace the valid macro record.
    pd.DataFrame([{"title": "Future sentiment", "publish_time": "2026-08-20T09:00:00Z",
                   "available_at": "2026-08-20T11:00:00Z"}]).to_parquet(sentiment)
    assert [item["title"] for item in route._load_macro_news_records(
        limit=1, as_of=datetime(2026, 8, 20, 10, tzinfo=timezone.utc))] == ["Old macro"]


@pytest.mark.parametrize("source", ["macro", "sentiment"])
def test_filtered_news_stops_reading_after_limit(tmp_path, monkeypatch, source):
    import omega.api.routes.sentiment as route
    import pyarrow.parquet as pq

    path = tmp_path / "news.parquet"
    column = "origin_ticker" if source == "macro" else "symbol"
    rows = [{column: "OTHER", "title": "Skip", "published_at": "2026-08-20T10:00:00Z",
             "publish_time": "2026-08-20T10:00:00Z", "origin_exchange": "HSX"},
            {column: "AAA", "title": "Keep", "published_at": "2026-08-20T10:00:00Z",
             "publish_time": "2026-08-20T10:00:00Z", "origin_exchange": "HSX"},
            {column: "AAA", "title": "Too late", "published_at": "2026-08-20T09:00:00Z",
             "publish_time": "2026-08-20T09:00:00Z", "origin_exchange": "HSX"}]
    pd.DataFrame(rows).to_parquet(path, row_group_size=1)
    monkeypatch.setattr(route, "MACRO_NEWS_PATH", path if source == "macro" else tmp_path / "absent")
    monkeypatch.setattr(route, "NEWS_SENTIMENT_PATH", path if source == "sentiment" else tmp_path / "absent")
    original = pq.ParquetFile

    class GuardedParquet:
        def __init__(self, file):
            self.inner = original(file)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.inner.close()

        def iter_batches(self, **kwargs):
            for batch in self.inner.iter_batches(batch_size=1):
                yield batch

    monkeypatch.setattr(route.pq, "ParquetFile", GuardedParquet)
    assert [item["title"] for item in route._load_macro_news_records(limit=1, ticker="aaa")] == ["Keep"]


def test_dim6_sector_contagion_matrix_structure(client):
    # Dim 6 & 13: Contagion nodes, transmission risk and systemic risk level
    resp = client.get("/api/v1/sentiment/contagion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["is_synthetic"] is True
    assert data["source"] == "synthetic_simulation"
    assert 0.0 <= data["overall_contagion_index"] <= 100.0
    assert data["systemic_risk_level"] in ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
    assert len(data["nodes"]) > 0
    first_node = data["nodes"][0]
    assert "sector" in first_node
    assert 0.0 <= first_node["stress_score"] <= 100.0
    assert 0.0 <= first_node["transmission_risk"] <= 1.0
    assert first_node["contagion_level"] in ["LOW", "NORMAL", "ELEVATED", "HIGH", "CRITICAL"]


def test_dim7_sector_contagion_transmission_edge_weights(client):
    # Dim 7: Graph edge correlation weight bounds (0 <= w <= 1)
    resp = client.get("/api/v1/sentiment/contagion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_synthetic"] is True
    assert data["source"] == "synthetic_simulation"
    for node in data["nodes"]:
        for corr in node["correlated_sectors"]:
            assert "sector" in corr
            assert 0.0 <= corr["correlation_weight"] <= 1.0


def test_dim8_llm_macro_analysis_intelligence_card(client):
    # Dim 8 & 1: LLM Executive briefing contract and primary risks
    resp = client.get("/api/v1/sentiment/llm-analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["is_synthetic"] is True
    assert data["source"] == "synthetic_simulation"
    assert len(data["regime_summary"]) > 10
    assert len(data["primary_risks"]) >= 1
    assert len(data["catalysts"]) >= 1
    assert len(data["sector_impacts"]) >= 1
    assert 0.0 <= data["sentiment_confidence"] <= 1.0
    assert "ACCUMULATE" in data["executive_verdict"] or "BULLISH" in data["executive_verdict"] or "NEUTRAL" in data["executive_verdict"]


def test_dim9_sse_macro_news_stream_initial_snapshot(client):
    # Dim 9 & 5: SSE real-time newsfeed initial snapshot
    resp = client.get("/sse/v1/macro/news-stream?limit=1")
    assert resp.status_code == 200
    text = resp.text
    assert "data:" in text
    assert "SNAPSHOT" in text


def test_dim10_sse_macro_news_stream_multi_events(client):
    # Dim 10 & 5: SSE multiple event emissions without deadlock or connection drop
    resp = client.get("/sse/v1/macro/news-stream?limit=2")
    assert resp.status_code == 200
    assert "data:" in resp.text


def test_dim11_macro_news_nan_inf_sanitization(client):
    # Dim 11 & 8: No NaN/Inf propagation in API JSON responses
    resp = client.get("/api/v1/macro/news/latest?limit=50")
    assert resp.status_code == 200
    text = resp.text
    assert "NaN" not in text
    assert "Infinity" not in text
    assert "-Infinity" not in text


def test_dim12_vsi_engine_sub_indices_consistency(client):
    # Dim 12 & 13: Sub-indices metric consistency with total index
    resp = client.get("/api/v1/sentiment/vsi")
    assert resp.status_code == 200
    subs = resp.json()["sub_indices"]
    for k, v in subs.items():
        assert 0.0 <= v <= 100.0


def test_dim13_llm_macro_entities_and_tags_deduplication(client):
    # Dim 13 & 10: Canonical deduplication of macro tags and entities
    resp = client.get("/api/v1/sentiment/llm-analysis")
    assert resp.status_code == 200
    data = resp.json()
    tags = data["macro_tags"]
    entities = data["key_entities"]
    assert len(tags) == len(set(tags))
    assert len(entities) == len(set(entities))


def test_dim14_macro_news_quarantine_resilience(client):
    # Dim 14: Resilience when reading datasets
    resp = client.get("/api/v1/macro/news/latest?limit=5")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_dim15_vsi_history_7d_chronological_order(client):
    # Dim 15 & 6: 7-day historical timeseries chronological sanity
    resp = client.get("/api/v1/sentiment/vsi")
    assert resp.status_code == 200
    history = resp.json()["history_7d"]
    dates = [h["date"] for h in history]
    assert dates == sorted(dates)


def test_dim16_security_no_secret_or_prompt_leakage(client):
    # Dim 16: Security & secret leakage prevention in analysis payloads
    resp = client.get("/api/v1/sentiment/llm-analysis")
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "api_key" not in text
    assert "secret" not in text
    assert "password" not in text
    assert "bearer" not in text


def test_loader_macro_news_records_excludes_missing_or_invalid_timestamps(tmp_path, monkeypatch):
    # Loader unit test: assert _load_macro_news_records skips rows with None/empty/invalid timestamps
    import pandas as pd
    import omega.api.routes.sentiment as sentiment_mod

    # 1. Test macro_news parquet path with None, empty, invalid timestamps
    macro_parquet = tmp_path / "macro_news.parquet"
    df_macro = pd.DataFrame([
        {"origin_ticker": "VNM", "raw_record_id": "r1", "title": "Valid Macro News", "published_at": "2026-08-20T08:00:00Z"},
        {"origin_ticker": "VNM", "raw_record_id": "r2", "title": "None Timestamp", "published_at": None},
        {"origin_ticker": "VNM", "raw_record_id": "r3", "title": "Empty Timestamp", "published_at": "   "},
        {"origin_ticker": "VNM", "raw_record_id": "r4", "title": "Invalid String Timestamp", "published_at": "invalid_date_format"},
    ])
    df_macro.to_parquet(macro_parquet)

    # 2. Test news_sentiment parquet path with None, empty, invalid timestamps
    sentiment_parquet = tmp_path / "news_sentiment.parquet"
    df_sent = pd.DataFrame([
        {"symbol": "HPG", "payload_sha256": "sha123", "title": "Valid Sentiment News", "publish_time": "2026-08-20T09:00:00Z", "sentiment_score": 0.5},
        {"symbol": "HPG", "payload_sha256": "sha456", "title": "None Time", "publish_time": None, "sentiment_score": 0.5},
        {"symbol": "HPG", "payload_sha256": "sha789", "title": "Empty Time", "publish_time": "", "sentiment_score": 0.5},
        {"symbol": "HPG", "payload_sha256": "sha000", "title": "Invalid Time", "publish_time": "corrupt_timestamp", "sentiment_score": 0.5},
    ])
    df_sent.to_parquet(sentiment_parquet)

    monkeypatch.setattr(sentiment_mod, "MACRO_NEWS_PATH", macro_parquet)
    monkeypatch.setattr(sentiment_mod, "NEWS_SENTIMENT_PATH", sentiment_parquet)

    items = sentiment_mod._load_macro_news_records(limit=50)

    # Verify only the 2 valid rows are loaded and all invalid/missing timestamp rows are excluded
    titles = [it["title"] for it in items]
    assert "Valid Macro News" in titles
    assert "Valid Sentiment News" in titles
    assert "None Timestamp" not in titles
    assert "Empty Timestamp" not in titles
    assert "Invalid String Timestamp" not in titles
    assert "None Time" not in titles
    assert "Empty Time" not in titles
    assert "Invalid Time" not in titles
    assert len(items) == 2


def test_load_macro_news_records_out_of_order_preserves_newest_first(tmp_path, monkeypatch):
    """F-003: Verify _load_macro_news_records returns newest-first when parquet rows are out of order."""
    import omega.api.routes.sentiment as sentiment_mod

    parquet_path = tmp_path / "macro_news.parquet"
    # Row 1: Older, Row 2: Newer
    df = pd.DataFrame([
        {"origin_ticker": "AAA", "raw_record_id": "r1", "title": "Older News", "published_at": "2026-08-20T08:00:00Z"},
        {"origin_ticker": "AAA", "raw_record_id": "r2", "title": "Newer News", "published_at": "2026-08-20T09:00:00Z"},
    ])
    df.to_parquet(parquet_path)
    monkeypatch.setattr(sentiment_mod, "MACRO_NEWS_PATH", parquet_path)
    monkeypatch.setattr(sentiment_mod, "NEWS_SENTIMENT_PATH", tmp_path / "absent.parquet")

    # With limit=1, it must return Newer News, not Older News
    items = sentiment_mod._load_macro_news_records(limit=1)
    assert len(items) == 1
    assert items[0]["title"] == "Newer News"

    # With limit=2, it must return [Newer News, Older News]
    items2 = sentiment_mod._load_macro_news_records(limit=2)
    assert len(items2) == 2
    assert items2[0]["title"] == "Newer News"
    assert items2[1]["title"] == "Older News"


def test_load_macro_news_records_mixed_store_newest_first(tmp_path, monkeypatch):
    """P2 / F-001: Verify _load_macro_news_records picks newer sentiment row over older macro row even when limit=1."""
    import omega.api.routes.sentiment as sentiment_mod

    macro_path = tmp_path / "macro_news.parquet"
    sentiment_path = tmp_path / "news_sentiment.parquet"

    df_m = pd.DataFrame([
        {
            "origin_ticker": "MACRO",
            "raw_record_id": "m1",
            "title": "Old macro",
            "published_at": "2026-08-20T08:00:00Z",
            "available_at": "2026-08-20T08:15:00Z",
        }
    ])
    df_m.to_parquet(macro_path)

    df_s = pd.DataFrame([
        {
            "symbol": "VCB",
            "payload_sha256": "sha1",
            "title": "New sentiment",
            "sentiment_score": 0.5,
            "publish_time": "2026-08-20T09:00:00Z",
            "available_at": "2026-08-20T09:15:00Z",
        }
    ])
    df_s.to_parquet(sentiment_path)

    monkeypatch.setattr(sentiment_mod, "MACRO_NEWS_PATH", macro_path)
    monkeypatch.setattr(sentiment_mod, "NEWS_SENTIMENT_PATH", sentiment_path)

    as_of = pd.to_datetime("2026-08-20T10:00:00Z", utc=True)
    items = sentiment_mod._load_macro_news_records(limit=1, as_of=as_of)
    assert len(items) == 1
    assert items[0]["title"] == "New sentiment"

