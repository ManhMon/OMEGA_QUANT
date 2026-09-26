import json
import pytest
from starlette.testclient import TestClient
from omega.api.server import app

@pytest.fixture
def client():
    return TestClient(app)

# -----------------------------------------------------------------------------
# 16-DIMENSION MASTER ADVERSARIAL TEST SUITE: PHASE 11 OMNI-QUANT AI COPILOT
# -----------------------------------------------------------------------------

def test_dim1_system_synthesis_schema_invariants(client):
    """Dim 1: Strict Types & Schema Invariants across multi-engine synthesis."""
    resp = client.get("/api/v1/copilot/system-synthesis?context_ticker=FPT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "focus_symbol" in data
    assert data["focus_symbol"] == "FPT"
    assert "macro" in data
    assert "alpha" in data
    assert "screener" in data
    assert "risk_tca" in data
    assert "pipeline" in data
    assert isinstance(data["executive_quant_score"], (int, float))
    assert isinstance(data["holistic_verdict"], str)
    assert len(data["verdict_reasoning_vi"]) > 10
    assert len(data["verdict_reasoning_en"]) > 10


def test_dim2_actionable_recommendations_contract(client):
    """Dim 2: File I/O & Endpoint Contracts for 1-Click Action Dispatcher."""
    resp = client.get("/api/v1/copilot/actionable-recommendations?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "total_recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) >= 4
    for rec in data["recommendations"]:
        assert "id" in rec
        assert "category" in rec
        assert "impact_level" in rec
        assert rec["impact_level"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        assert "confidence_score" in rec
        assert 0.0 <= rec["confidence_score"] <= 1.0
        assert "action_type" in rec
        assert isinstance(rec["payload"], dict)


def test_dim3_ask_copilot_semantic_resolution_and_durability(client):
    """Dim 3: Durability & Interactive Semantic Query Resolution."""
    req_body = {
        "query": "Phân tích rủi ro Barra và CVaR của danh mục FPT",
        "context_ticker": "FPT",
        "active_module": "barra_risk_tca",
        "temperature": 0.2,
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["intent"] == "RISK_TCA"
    assert "response_vi" in data
    assert "response_en" in data
    assert "metrics" in data
    assert isinstance(data["suggested_actions"], list)


def test_dim4_ask_copilot_macro_intent_routing(client):
    """Dim 4: Memory Bounds & Macro Intent Routing."""
    req_body = {
        "query": "Thị trường vĩ mô và chỉ số VSI sentiment hiện tại ra sao?",
        "context_ticker": "MBB",
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "MACRO_SENTIMENT"
    assert "VSI" in data["response_vi"] or "vĩ mô" in data["response_vi"].lower()


def test_dim5_ask_copilot_alpha_ast_intent_routing(client):
    """Dim 5: Concurrency & Alpha AST Intent Routing."""
    req_body = {
        "query": "Tín hiệu alpha formula nào có IC và IR tốt nhất?",
        "context_ticker": "HPG",
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "ALPHA_AST"
    assert "IC" in data["response_vi"] or "IR" in data["response_vi"]


def test_dim6_ask_copilot_execution_intent_routing(client):
    """Dim 6: Point-In-Time & Execution / Rebalance Intent Routing."""
    req_body = {
        "query": "Lập kế hoạch rebalance và lệnh order blotter",
        "context_ticker": "MWG",
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "EXECUTION_REBALANCE"
    assert "VWAP" in data["response_vi"] or "tái cân bằng" in data["response_vi"]


def test_dim7_adversarial_empty_query_fail_closed(client):
    """Dim 7: Validation against Empty or Whitespace Query."""
    req_body = {
        "query": "   ",
        "context_ticker": "FPT",
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 400 or resp.status_code == 422


def test_dim8_adversarial_temperature_bounds(client):
    """Dim 8: Mathematical Extremes & Temperature Bound Enforcement."""
    req_body = {
        "query": "Phân tích vĩ mô",
        "temperature": 1.5,  # > 1.0 (Invalid)
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 422


def test_dim9_adversarial_negative_temperature_bounds(client):
    """Dim 9: Financial Logic Edges on Negative Temperature."""
    req_body = {
        "query": "Phân tích vĩ mô",
        "temperature": -0.5,  # < 0.0 (Invalid)
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 422


def test_dim10_case_insensitive_ticker_handling(client):
    """Dim 10: Case-Insensitive Symbol Canonicalization."""
    resp = client.get("/api/v1/copilot/system-synthesis?context_ticker=hpg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["focus_symbol"] == "HPG"


def test_dim11_malformed_context_ticker_sanitization(client):
    """Dim 11: Fail-Closed and Sanitize Malformed Ticker Input."""
    resp = client.get("/api/v1/copilot/system-synthesis?context_ticker=fpt;drop table;")
    assert resp.status_code == 200
    data = resp.json()
    assert ";" not in data["focus_symbol"]
    assert "FPT" in data["focus_symbol"]


def test_dim12_recommendations_limit_bounds(client):
    """Dim 12: Bound Check on Recommendations Limit Query Parameter."""
    resp = client.get("/api/v1/copilot/actionable-recommendations?limit=0")
    assert resp.status_code == 422
    resp_over = client.get("/api/v1/copilot/actionable-recommendations?limit=100")
    assert resp_over.status_code == 422


def test_dim13_stream_sse_endpoint_availability(client):
    """Dim 13: Metric & Artifact Consistency: SSE Stream Availability with limit=1."""
    resp = client.get("/sse/v1/copilot/stream?limit=1")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_dim14_cross_sectional_synthesis_coherence(client):
    """Dim 14: Cross-Sectional Synthesis Consistency."""
    resp = client.get("/api/v1/copilot/system-synthesis?context_ticker=DGC")
    assert resp.status_code == 200
    data = resp.json()
    assert data["screener"]["target_ticker_profile"]["ticker"] == "DGC"
    assert data["macro"]["vsi_sentiment_score"] > 0
    assert data["alpha"]["total_alpha_universe"] == 703


def test_dim15_opt_in_safety_default_context(client):
    """Dim 15: Safe Default Context Ticker."""
    resp = client.get("/api/v1/copilot/system-synthesis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["focus_symbol"] == "FPT"


def test_dim16_security_sanitization_xss_prevention(client):
    """Dim 16: Security & Script Injection Defense."""
    req_body = {
        "query": "<script>alert('XSS')</script> Tổng quan FPT",
        "context_ticker": "FPT<script>",
    }
    resp = client.post("/api/v1/copilot/ask", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert "<script>" not in data["focus_ticker"]
