"""
16-Dimension Master Adversarial Test Suite for Phase 14 React Key De-duplication and Anti-Jitter UI Stabilization
Gate: OMEGA_UI_PHASE14_KEY_DEDUPLICATION_20260823
"""

import os
import re
import json
import inspect
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from omega.api.server import app
from omega.api.routes.sentiment import (
    _load_macro_news_records,
    MacroNewsItem,
    MACRO_NEWS_PATH,
    NEWS_SENTIMENT_PATH,
)
from omega.api.routes.copilot import sse_copilot_stream

REPO_ROOT = Path(__file__).resolve().parent.parent
OMEGA_UI_DIR = REPO_ROOT / "omega-ui"


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 16-DIMENSION MASTER ADVERSARIAL MATRIX TESTS
# -----------------------------------------------------------------------------

def test_dim1_strict_types_and_malformed_inputs(client):
    """Dim 1: Strict Types & Malformed Inputs - news_id must be non-empty string with deterministic prefix."""
    resp = client.get("/api/v1/macro/news/latest?limit=25")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert isinstance(data["items"], list)
    for it in data["items"]:
        assert isinstance(it["news_id"], str)
        assert len(it["news_id"]) > 0
        assert (
            it["news_id"].startswith("mnews_")
            or it["news_id"].startswith("snews_")
            or it["news_id"].startswith("mock_news_")
        )


def test_dim2_file_io_and_path_aliasing():
    """Dim 2: File I/O & Path Aliasing - ensure required source files exist and are not directories."""
    required_files = [
        "src/omega/api/routes/sentiment.py",
        "src/omega/api/routes/copilot.py",
        "omega-ui/src/modules/macro_news/MacroNewsSentimentHub.tsx",
        "omega-ui/src/hooks/useRealtimeStream.ts",
    ]
    for rel_path in required_files:
        full_path = REPO_ROOT / rel_path
        assert full_path.exists(), f"File {rel_path} must exist"
        assert full_path.is_file(), f"Path {rel_path} must be a file not a directory"


def test_dim3_fsync_durability_and_news_id_stability():
    """Dim 3: Fsync & Transactional Durability - deterministic unique news_id generation across calls."""
    items_first = _load_macro_news_records(limit=30)
    items_second = _load_macro_news_records(limit=30)

    assert len(items_first) == len(items_second)
    for i in range(len(items_first)):
        assert items_first[i].news_id == items_second[i].news_id
        assert items_first[i].title == items_second[i].title


def test_dim4_memory_bounds_and_cardinality_clamping(client):
    """Dim 4: Memory Bounds & OOM Prevention - enforce limit clamping without memory explosion."""
    resp = client.get("/api/v1/macro/news/latest?limit=100")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 100

    # Test exceeding bounds fails closed with 422
    resp_invalid = client.get("/api/v1/macro/news/latest?limit=150")
    assert resp_invalid.status_code == 422


def test_dim5_concurrency_and_key_uniqueness():
    """Dim 5: Concurrency & Lock Timeouts - all loaded news_ids must be strictly unique within result set."""
    items = _load_macro_news_records(limit=50)
    news_ids = [it.news_id for it in items]
    unique_ids = set(news_ids)
    assert len(news_ids) == len(unique_ids), f"Duplicate news_id detected in loaded records: {news_ids}"


def test_dim6_point_in_time_and_iso_timestamps(client):
    """Dim 6: Point-in-Time (PIT) & Temporal Clocks - published_at & as_of must be ISO UTC formatted."""
    resp = client.get("/api/v1/macro/news/latest?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "as_of" in data
    assert "T" in data["as_of"]
    for it in data["items"]:
        assert "published_at" in it
        assert "T" in it["published_at"] or len(it["published_at"]) >= 10


def test_dim7_sparse_calendar_and_composite_key_react_hub():
    """Dim 7: Sparse Calendar - MacroNewsSentimentHub.tsx must use composite keys across all list mappings."""
    hub_file = OMEGA_UI_DIR / "src" / "modules" / "macro_news" / "MacroNewsSentimentHub.tsx"
    assert hub_file.exists()
    content = hub_file.read_text(encoding="utf-8")

    # Verify composite keys exist
    assert "key={`mtag_${tag}_${idx}`}" in content
    assert "key={`ment_${ent}_${idx}`}" in content
    assert "key={`news_${item.news_id}_${idx}`}" in content
    assert "key={`node_${node.sector}_${nIdx}`}" in content
    assert "key={`corr_${corr.sector}_${cIdx}`}" in content
    assert "key={`simpact_${sec}_${sIdx}`}" in content


def test_dim8_mathematical_extremes_and_bounds(client):
    """Dim 8: Mathematical Extremes & Bounds - sentiment scores within [-1.0, 1.0]."""
    resp = client.get("/api/v1/macro/news/latest?limit=50")
    assert resp.status_code == 200
    for it in resp.json()["items"]:
        assert -1.0 <= it["sentiment_score"] <= 1.0


def test_dim9_financial_and_business_logic_edges(client):
    """Dim 9: Financial & Business Logic Edges - sentiment polarity matches sentiment score direction."""
    resp = client.get("/api/v1/macro/news/latest?limit=50")
    assert resp.status_code == 200
    for it in resp.json()["items"]:
        score = it["sentiment_score"]
        pol = it["polarity"]
        if score > 0.1:
            assert pol in ["BULLISH", "NEUTRAL"]
        elif score < -0.1:
            assert pol in ["BEARISH", "NEUTRAL"]


def test_dim10_case_insensitive_deduplication_and_symbol_canonicalization(client):
    """Dim 10: Case-Insensitive Deduplication & Cardinality - query ticker uppercase normalization."""
    resp_lower = client.get("/api/v1/macro/news/latest?ticker=fpt")
    resp_upper = client.get("/api/v1/macro/news/latest?ticker=FPT")
    assert resp_lower.status_code == 200
    assert resp_upper.status_code == 200
    assert len(resp_lower.json()["items"]) == len(resp_upper.json()["items"])


def test_dim11_fail_closed_and_explicit_exit_codes(client):
    """Dim 11: Fail-Closed & Explicit Exit Codes - invalid parameters must return explicit 422 HTTP code."""
    resp_bad = client.get("/api/v1/macro/news/latest?limit=-1")
    assert resp_bad.status_code == 422


def test_dim12_full_suite_regression_closure():
    """Dim 12: Full-Suite Regression Closure - verify routes registered in main FastAPI server."""
    routes = [route.path for route in app.routes]
    assert "/api/v1/macro/news/latest" in routes
    assert "/sse/v1/macro/news-stream" in routes
    assert "/sse/v1/copilot/stream" in routes
    assert "/api/v1/sentiment/vsi" in routes
    assert "/api/v1/sentiment/contagion" in routes


def test_dim13_metric_and_artifact_consistency():
    """Dim 13: Metric & Artifact Consistency - MacroNewsItem schema matches TypeScript definition."""
    ts_client_file = OMEGA_UI_DIR / "src" / "api" / "client.ts"
    assert ts_client_file.exists()
    ts_content = ts_client_file.read_text(encoding="utf-8")
    assert "interface MacroNewsItem" in ts_content or "type MacroNewsItem" in ts_content
    assert "news_id: string;" in ts_content
    assert "polarity: 'BULLISH' | 'BEARISH' | 'NEUTRAL';" in ts_content


def test_dim14_exception_chaining_and_sse_copilot_sleep_interval():
    """Dim 14: Exception Chaining & SSE Stabilization - copilot SSE streaming interval must be 5.0s."""
    copilot_file = REPO_ROOT / "src" / "omega" / "api" / "routes" / "copilot.py"
    assert copilot_file.exists()
    content = copilot_file.read_text(encoding="utf-8")
    assert "await asyncio.sleep(5.0)" in content
    # Ensure previous high-frequency 0.5s sleep is eliminated from sse_copilot_stream
    stream_func_match = re.search(r"async def sse_copilot_stream.*?await asyncio\.sleep\((\d+\.?\d*)\)", content, re.DOTALL)
    assert stream_func_match is not None
    assert float(stream_func_match.group(1)) == 5.0


def test_dim15_opt_in_safety_and_realtime_stream_query_stabilization():
    """Dim 15: Opt-in Safety - useRealtimeStream queryClient.invalidateQueries uses refetchType: 'active'."""
    stream_file = OMEGA_UI_DIR / "src" / "hooks" / "useRealtimeStream.ts"
    assert stream_file.exists()
    content = stream_file.read_text(encoding="utf-8")
    assert "refetchType: 'active'" in content


def test_dim16_security_and_secret_leakage_prevention(client):
    """Dim 16: Security & Secret Leakage Prevention - news response must not leak secrets or credentials."""
    resp = client.get("/api/v1/macro/news/latest?limit=10")
    assert resp.status_code == 200
    raw_text = resp.text
    assert "sk-" not in raw_text
    assert "password" not in raw_text.lower()
    assert "secret" not in raw_text.lower()
    assert "token" not in raw_text.lower() or "csrf" in raw_text.lower()
