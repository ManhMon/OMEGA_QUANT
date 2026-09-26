import json
import asyncio
from copy import deepcopy
import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, AsyncMock
import httpx
from datetime import datetime
from omega.core.llm_config import classify_jev
from omega.api.server import app
import omega.api.routes.copilot as copilot


@pytest.fixture(autouse=True)
def restore_llm_config():
    snapshot = deepcopy(copilot._IN_MEMORY_LLM_CONFIG)
    yield
    copilot._IN_MEMORY_LLM_CONFIG.clear()
    copilot._IN_MEMORY_LLM_CONFIG.update(snapshot)

@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("stored_as_of,stored_available,decided,caller_as_of,caller_available", [
    ("09:00", "08:00", "11:00", "10:00", "09:00"),
    ("09:00", "08:00", "09:30", "10:00", "09:00"),
    ("09:00", "08:00", "08:30", "10:00", "08:00"),
])
def test_jev_cache_rejects_future_decision(tmp_path, stored_as_of, stored_available, decided, caller_as_of, caller_available):
    import sqlite3

    def stamp(hhmm):
        return datetime.fromisoformat(f"2026-09-26T{hhmm}:00+00:00")

    path = tmp_path / "jev.db"
    choices = {"route": ("global_profile", "fallback")}
    with patch("typesafe_sdk.TypeSafeClient") as sdk:
        sdk.return_value.__enter__.return_value.system_one.return_value.choices = {
            "route": type("ChoiceResult", (), {"choice": "global_profile"})()
        }
        with patch("omega.core.llm_config.datetime") as clock:
            clock.now.return_value = stamp("08:00")
            clock.fromisoformat.side_effect = datetime.fromisoformat
            first = classify_jev(domain="copilot", facts={"query": "VCB"}, choices=choices,
                                 cache_path=path, as_of=stamp(stored_as_of),
                                 available_at=stamp(stored_available), model="jev")
    with sqlite3.connect(path) as db:
        envelope = json.loads(db.execute("SELECT envelope FROM decisions").fetchone()[0])
        envelope["decided_at"] = stamp(decided).isoformat()
        before = json.dumps(envelope)
        db.execute("UPDATE decisions SET envelope=?", (before,))
    assert json.loads(before)["fingerprint"] == first["fingerprint"]
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        classify_jev(domain="copilot", facts={"query": "VCB"}, choices=choices,
                     cache_path=path, as_of=stamp(caller_as_of),
                     available_at=stamp(caller_available), model="jev")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT envelope FROM decisions").fetchone()[0] == before


@pytest.mark.parametrize("warranted", ["yes", "no"])
def test_jev_system_two_changes_execution_prompt(client, monkeypatch, tmp_path, warranted):
    monkeypatch.setenv("OMEGA_COPILOT_JEV_CACHE_PATH", str(tmp_path / "jev.db"))
    monkeypatch.setattr(copilot, "classify_copilot_request", lambda *args, **kwargs: {
        "route": "global_profile", "intent": "GENERAL_SYNTHESIS", "tool": "none",
        "system_2_warranted": warranted, "cache_key": "hash", "attempts": 2})
    copilot._IN_MEMORY_LLM_CONFIG["global_profile"].update(
        provider="openai", api_key="sk-real-live-active-key-secret-12345",
        base_url="https://api.openai.com/v1", temperature=0.8)
    captured = []
    async def fake_post(*args, **kwargs):
        captured.append(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]},
                              request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=fake_post):
        response = client.post("/api/v1/copilot/ask", json={"query": "Evaluate VCB"})
    assert response.status_code == 200
    assert bool(response.json()["system_2_warranted"]) == (warranted == "yes")
    assert ("multi-step reasoning" in captured[0]["messages"][0]["content"]) == (warranted == "yes")
    assert captured[0]["temperature"] == (0.1 if warranted == "yes" else 0.2)
    assert response.json()["jev_provenance"]["cache_key"] == "hash"


def test_jev_safe_tool_and_classifier_failure_provenance(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OMEGA_COPILOT_JEV_CACHE_PATH", str(tmp_path / "jev.db"))
    monkeypatch.setattr(copilot, "classify_copilot_request", lambda *args, **kwargs: {
        "route": "global_profile", "intent": "GENERAL_SYNTHESIS", "tool": "set_focus_ticker",
        "system_2_warranted": "no", "cache_key": "hash", "attempts": 1})
    response = client.post("/api/v1/copilot/ask", json={"query": "Evaluate VCB", "context_ticker": "VCB"})
    assert response.status_code == 200
    assert response.json()["executed_tools"][0]["tool_name"] == "set_focus_ticker"
    assert response.json()["jev_provenance"]["status"] == "success"
    def fail(*args, **kwargs):
        raise RuntimeError("secret message")
    monkeypatch.setattr(copilot, "classify_copilot_request", fail)
    failed = client.post("/api/v1/copilot/ask", json={"query": "Evaluate VCB"})
    assert failed.status_code == 200
    assert failed.json()["jev_provenance"]["fallback_reason"] == "RuntimeError"
    assert failed.json()["jev_provenance"]["status"] == "fallback"
    assert "secret message" not in str(failed.json())


@pytest.mark.parametrize("query,classification,tool_name", [
    ("hello", "set_focus_ticker", "set_focus_ticker"),
    ("trigger backtest", "none", "trigger_backtest"),
], ids=["hello_dispatch", "trigger_backtest_dispatch"])
def test_tool_exception_does_not_disclose_secrets(client, monkeypatch, tmp_path, query, classification, tool_name):
    monkeypatch.setenv("OMEGA_COPILOT_JEV_CACHE_PATH", str(tmp_path / "jev.db"))
    monkeypatch.setattr(copilot, "classify_copilot_request", lambda *args, **kwargs: {
        "route": "global_profile", "intent": "GENERAL_SYNTHESIS", "tool": classification,
        "system_2_warranted": "no", "cache_key": "hash", "attempts": 1})
    secret = "sk-secret-from-tool-12345"

    async def fail_tool(request):
        raise RuntimeError(f"upstream rejected {secret} at https://user:pass@example.com/private")

    monkeypatch.setattr(copilot, "execute_copilot_tool", fail_tool)
    response = client.post("/api/v1/copilot/ask", json={"query": query, "context_ticker": "VCB"})
    assert response.status_code == 200
    entry = response.json()["executed_tools"][0]
    assert entry["tool_name"] == tool_name
    assert entry["status"] == "error"
    assert entry["result"]["error"] == "RuntimeError"
    assert secret not in response.text
    assert "user:pass" not in response.text
    if tool_name == "trigger_backtest":
        assert entry["target"] == "ALPHA_HRP_V2"

# =============================================================================
# 16-DIMENSION MASTER ADVERSARIAL TEST SUITE: PHASE 17 DIRECT REAL-TIME LLM
# Grounded Real-Time LLM Direct Response Engine & Natural Language Precision
# =============================================================================

def test_dim1_strict_types_and_schema_validation(client):
    """Dim 1: Strict Types & Schema Validation - Empty or malformed queries fail fast."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "   ", "context_ticker": "VCB"})
    assert resp.status_code == 400
    assert "Query cannot be empty" in resp.json()["detail"]

    # Valid schema structure
    resp = client.post("/api/v1/copilot/ask", json={"query": "Đánh giá định giá cổ phiếu VCB", "context_ticker": "VCB"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "VCB" in data["focus_ticker"]
    assert isinstance(data["response_vi"], str)
    assert isinstance(data["response_en"], str)
    assert isinstance(data["metrics"], dict)
    assert isinstance(data["suggested_actions"], list)


def test_dim2_file_io_path_aliasing_and_auto_init_env_config(client):
    """Dim 2: Auto-initialization of _IN_MEMORY_LLM_CONFIG from environment variables."""
    from omega.api.routes.copilot import _init_llm_config
    with patch.dict("os.environ", {
        "OMEGA_LLM_API_KEY": "sk-custom-omega-env-key-9999",
        "OMEGA_LLM_BASE_URL": "http://ollama-host:11434/v1",
        "OMEGA_LLM_MODEL": "qwen2.5-coder:32b",
        "OMEGA_LLM_PROVIDER": "local",
    }):
        cfg = _init_llm_config()
        assert cfg["global_profile"]["provider"] == "local"
        assert cfg["global_profile"]["model"] == "qwen2.5-coder:32b"
        assert cfg["global_profile"]["api_key"] == "sk-custom-omega-env-key-9999"
        assert cfg["global_profile"]["base_url"] == "http://ollama-host:11434/v1"


def test_dim3_fsync_durability_and_async_llm_structured_json(client):
    """Dim 3: Async HTTPX Client LLM Call with Structured JSON response."""
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "intent": "FUNDAMENTAL_TICKER_ANALYSIS",
                        "response_vi": "LLM Live: Mã VCB đạt P/E 13.8x, ROE 21.4% dẫn đầu ngành ngân hàng.",
                        "response_en": "LLM Live: Ticker VCB achieves P/E 13.8x and ROE 21.4% leading the banking sector.",
                        "metrics": {"ticker": "VCB", "pe": 13.8, "roe": 21.4},
                        "suggested_actions": ["XEM_SCREENER", "SO_SANH_NGANH"]
                    })
                }
            }
        ]
    }
    mock_resp = httpx.Response(200, json=mock_llm_response, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-real-live-active-key-secret-12345",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout_seconds": 30,
            "enabled": True,
        }
    }):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={
                "query": "Định giá VCB thế nào?",
                "context_ticker": "VCB",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["confidence"] == 0.96
            assert "LLM Live: Mã VCB" in data["response_vi"]
            assert data["intent"] == "FUNDAMENTAL_TICKER_ANALYSIS"


def test_dim4_memory_bounds_and_raw_markdown_verbatim_preservation(client):
    """Dim 4: Direct Raw Markdown / Natural Language Text Preserved with Zero Answer Loss."""
    markdown_content = """# Phân Tích Chuyên Sâu Cổ Phiếu FPT
- **P/E Hiện Tại**: 18.2x (Định giá hợp lý)
- **Tốc độ tăng trưởng EPS**: 22.5% YoY
- **Khuyến nghị**: Tích lũy vùng giá 125,000 - 130,000 VND."""

    mock_llm_response = {
        "choices": [
            {"message": {"content": markdown_content}}
        ]
    }
    mock_resp = httpx.Response(200, json=mock_llm_response, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-real-live-active-key-secret-12345",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout_seconds": 30,
            "enabled": True,
        }
    }):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={
                "query": "Chi tiết triển vọng FPT dạng markdown",
                "context_ticker": "FPT",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["response_vi"] == markdown_content
            assert data["response_en"] == markdown_content
            assert data["metrics"]["source"] == "direct_llm_markdown"


def test_dim5_concurrency_and_local_ollama_provider_without_key(client):
    """Dim 5: Support local/ollama provider without requiring an API key when ALLOW_LOCAL_LLM=true."""
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": "Local Ollama LLM: Tín hiệu kỹ thuật HPG đang có dòng tiền vào mạnh."
                }
            }
        ]
    }
    mock_resp = httpx.Response(200, json=mock_llm_response, request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"))

    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", {
            "global_profile": {
                "provider": "local",
                "model": "qwen2.5-coder:32b",
                "api_key": None,
                "base_url": "http://localhost:11434/v1",
                "temperature": 0.2,
                "max_tokens": 4096,
                "timeout_seconds": 30,
                "enabled": True,
            }
        }):
            with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                resp = client.post("/api/v1/copilot/ask", json={
                    "query": "Đánh giá cổ phiếu HPG bằng mô hình nội bộ",
                    "context_ticker": "HPG",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "Local Ollama LLM" in data["response_vi"]


def test_dim6_point_in_time_and_temporal_iso_timestamp(client):
    """Dim 6: Point-In-Time (PIT) ISO UTC Timestamp validation."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Tình hình thị trường", "context_ticker": "MBB"})
    assert resp.status_code == 200
    data = resp.json()
    assert "T" in data["timestamp"]
    assert "+00:00" in data["timestamp"] or "Z" in data["timestamp"]


def test_dim7_sparse_calendar_and_vietnam_ticker_natural_extraction(client):
    """Dim 7: Natural language Vietnam market ticker extraction from query string."""
    tickers_to_test = ["VCB", "HPG", "DGC", "MWG", "SSI", "VIC", "VHM", "TCB", "MSN", "VCI"]
    for sym in tickers_to_test:
        resp = client.post("/api/v1/copilot/ask", json={"query": f"Tại sao cổ phiếu {sym} hôm nay lại biến động mạnh và nguyên nhân giảm?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["focus_ticker"] == sym
        assert sym in data["response_vi"]


def test_dim8_mathematical_extremes_and_temperature_bounds(client):
    """Dim 8: Strict mathematical boundary checks on request parameters."""
    resp_high = client.post("/api/v1/copilot/ask", json={"query": "Query", "temperature": 1.5})
    assert resp_high.status_code == 422

    resp_low = client.post("/api/v1/copilot/ask", json={"query": "Query", "temperature": -0.5})
    assert resp_low.status_code == 422


def test_dim9_financial_reasoning_domain1_price_drivers(client):
    """Dim 9: Domain 1 - Price Drop / Gain Drivers quantitative reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Tại sao mã DGC giảm mạnh và nguyên nhân biến động giá?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "PRICE_DRIVERS"
    assert data["focus_ticker"] == "DGC"
    assert "Động lực Biến động Giá" in data["response_vi"]
    assert "Beta" in data["response_vi"]
    assert "beta" in data["metrics"]


def test_dim10_financial_reasoning_domain2_valuation_fundamentals(client):
    """Dim 10: Domain 2 - Valuation & Fundamentals quantitative reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Định giá P/E, P/B và báo cáo tài chính mã MBB"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "FUNDAMENTAL_TICKER_ANALYSIS"
    assert data["focus_ticker"] == "MBB"
    assert "Piotroski" in data["response_vi"]
    assert "Altman" in data["response_vi"]
    assert data["metrics"]["pe"] == 6.2


def test_dim11_financial_reasoning_domain3_ast_alpha_signals(client):
    """Dim 11: Domain 3 - AST Alpha Signals quantitative reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Tín hiệu alpha công thức AST và IC IR hiện tại của SSI"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "ALPHA_AST"
    assert data["focus_ticker"] == "SSI"
    assert "703 Alphas" in data["response_vi"]
    assert "IC" in data["response_vi"]
    assert "mean_ic" in data["metrics"]


def test_dim12_financial_reasoning_domain4_barra_risk_tca(client):
    """Dim 12: Domain 4 - Barra Risk & TCA / Slippage quantitative reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Rủi ro danh mục Barra CVaR 99% và chi phí trượt giá TCA của VIC"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "RISK_TCA"
    assert data["focus_ticker"] == "VIC"
    assert "CVaR 99%" in data["response_vi"]
    assert "trượt giá" in data["response_vi"]


def test_dim13_financial_reasoning_domain5_portfolio_rebalancing(client):
    """Dim 13: Domain 5 - Portfolio Rebalancing & Order Execution reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Kế hoạch rebalance tỷ trọng và lệnh khớp VWAP TWAP cho VNM"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "EXECUTION_REBALANCE"
    assert data["focus_ticker"] == "VNM"
    assert "TOTP 2FA" in data["response_vi"]
    assert "VWAP/TWAP" in data["response_vi"]


def test_dim14_financial_reasoning_domain6_macro_sbv_regime(client):
    """Dim 14: Domain 6 - Macro SBV Regime & Sentiment reasoning."""
    resp = client.post("/api/v1/copilot/ask", json={"query": "Chính sách điều hành SBV OMO và chu kỳ vĩ mô hiện nay"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "MACRO_SENTIMENT"
    assert "SBV" in data["response_vi"]
    assert "VSI" in data["response_vi"]
    assert "regime" in data["metrics"]


def test_dim15_exception_chaining_and_network_fail_closed_graceful_fallback(client):
    """Dim 15: Exception Chaining & Network Timeout graceful fail-closed fallback."""
    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-real-live-timeout-key",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout_seconds": 2,
            "enabled": True,
        }
    }):
        with patch.object(httpx.AsyncClient, "post", side_effect=httpx.ConnectTimeout("Connection timed out")):
            resp = client.post("/api/v1/copilot/ask", json={
                "query": "Định giá P/E của FPT",
                "context_ticker": "FPT"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["intent"] == "FUNDAMENTAL_TICKER_ANALYSIS"
            assert "P/E" in data["response_vi"]


def test_dim16_security_and_zero_secret_leakage_in_config(client):
    """Dim 16: Zero Secret Leakage in Config APIs and deterministic mocked DNS SSRF validation defense."""
    from omega.api.routes.copilot import validate_base_url
    import socket

    resp = client.get("/api/v1/copilot/config")
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    for p_name, p_val in profiles.items():
        assert not p_val["api_key"].startswith("sk-proj-omega-")
        assert not p_val["api_key"].startswith("sk-real-")
        if p_val["api_key"]:
            assert "•" in p_val["api_key"]

    # Allowed public providers with mocked DNS resolving to public IP
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        assert validate_base_url("https://api.openai.com/v1") is True
        assert validate_base_url("https://api.anthropic.com/v1") is True
        assert validate_base_url("https://generativelanguage.googleapis.com/v1beta") is True
        assert validate_base_url("https://api.groq.com/openai/v1") is True
        assert validate_base_url("https://openrouter.ai/api/v1") is True
        assert validate_base_url("https://together.xyz/v1") is True
        assert validate_base_url("https://api.deepseek.com/v1") is True

    # Strictly reject 0.0.0.0 and ::
    assert validate_base_url("http://0.0.0.0:8000") is False
    assert validate_base_url("http://[::]:8000") is False

    # Disallowed arbitrary public hosts without custom proxy enabled
    assert validate_base_url("https://example.com/v1") is False
    assert validate_base_url("http://malicious-target.internal") is False
    assert validate_base_url("https://8.8.8.8") is False

    # Private / Localhost without ALLOW_LOCAL_LLM
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "false"}):
        assert validate_base_url("http://127.0.0.1:11434") is False
        assert validate_base_url("http://localhost:11434") is False
        assert validate_base_url("http://10.0.0.1:8000") is False
        assert validate_base_url("http://192.168.1.1:8000") is False
        assert validate_base_url("http://172.16.0.1:8000") is False


def test_dns_rebinding_is_pinned_at_models_endpoint(client):
    """The models endpoint resolves once; outbound use cannot trigger rebinding."""
    import socket

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", side_effect=[public, AssertionError("unexpected connection-time DNS lookup")]) as resolver:
            with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = httpx.Response(200, json={"data": []})
                response = client.post("/api/v1/copilot/config/models", json={
                    "provider": "custom",
                    "base_url": "https://proxy.example.com/v1",
                })
                assert response.status_code == 200
                assert response.json()["source"] == "offline_suggestions"
                assert response.json()["status"] == "error"
                mock_get.assert_awaited_once()
                assert resolver.call_count == 1


def test_dns_rebinding_is_pinned_at_ask_endpoint(client):
    """The ask endpoint resolves once; outbound use cannot trigger rebinding."""
    import socket

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    mock_response = httpx.Response(200, json={"choices": [{"message": {"content": "Pinned response"}}]})
    profile = {
        "global_profile": {
            "provider": "custom", "model": "pinned-model", "api_key": None,
            "base_url": "https://proxy.example.com/v1", "temperature": 0.2,
            "max_tokens": 4096, "timeout_seconds": 30, "enabled": True,
        }
    }
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", side_effect=[public, AssertionError("unexpected connection-time DNS lookup")]) as resolver:
            with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", profile):
                with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
                    response = client.post("/api/v1/copilot/ask", json={"query": "Kiểm tra DNS pinning"})
                    assert response.status_code == 200
                    mock_post.assert_awaited_once()
                    assert resolver.call_count == 1


def test_localhost_rebinding_is_blocked_at_models_endpoint(client):
    """The models endpoint classifies localhost before its single DNS resolution."""
    import socket

    loopback = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 11434))]
    rebound_private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 11434))]
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", side_effect=[loopback, rebound_private]) as resolver:
            with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = httpx.Response(200, json={"data": []})
                response = client.post("/api/v1/copilot/config/models", json={
                    "provider": "local",
                    "base_url": "http://localhost:11434/v1",
                })
                assert response.status_code == 200
                mock_get.assert_awaited_once()
                assert resolver.call_count == 1


def test_localhost_rebinding_is_blocked_at_ask_endpoint(client):
    """The ask endpoint keeps localhost's loopback classification through connection."""
    import socket

    loopback = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 11434))]
    rebound_private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 11434))]
    profile = {
        "global_profile": {
            "provider": "local", "model": "pinned-model", "api_key": None,
            "base_url": "http://localhost:11434/v1", "temperature": 0.2,
            "max_tokens": 4096, "timeout_seconds": 30, "enabled": True,
        }
    }
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", side_effect=[loopback, rebound_private]) as resolver:
            with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", profile):
                with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
                    mock_post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": "Pinned response"}}]})
                    response = client.post("/api/v1/copilot/ask", json={"query": "Kiểm tra localhost DNS pinning"})
                    assert response.status_code == 200
                    mock_post.assert_awaited_once()
                    assert resolver.call_count == 1


def test_safe_transport_uses_concrete_backend_and_preserves_host_header():
    """Pinned TLS transport retains HTTP Host and TLS SNI without real network I/O."""
    from omega.api.routes.copilot import SafeAsyncNetworkBackend, ValidatedLLMTarget, get_safe_httpx_client

    captured = {"connections": [], "tls_names": [], "writes": []}

    class FakeStream:
        def __init__(self):
            self._response_sent = False

        async def read(self, max_bytes, timeout=None):
            if self._response_sent:
                return b""
            self._response_sent = True
            return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"

        async def write(self, buffer, timeout=None):
            captured["writes"].append(bytes(buffer))

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            captured["tls_names"].append(server_hostname)
            return self

        def get_extra_info(self, info):
            return None

        async def aclose(self):
            return None

    class FakeBackend:
        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            captured["connections"].append((host, port))
            return FakeStream()

    target = ValidatedLLMTarget(hostname="api.openai.com", port=443, ip="93.184.216.34")
    safe_backend = SafeAsyncNetworkBackend(target.ip)
    safe_backend._real_backend = FakeBackend()

    async def request_server():
        async with get_safe_httpx_client(target) as safe_client:
            safe_client._transport._pool._network_backend = safe_backend
            return await safe_client.get("https://api.openai.com/v1/models")

    response = asyncio.run(request_server())

    assert response.status_code == 200
    assert captured["connections"] == [(target.ip, target.port)]
    assert captured["tls_names"] == [target.hostname]
    assert b"Host: api.openai.com\r\n" in captured["writes"][0]


def test_localhost_must_resolve_to_loopback(client):
    """Local LLM access requires the localhost hostname and all-loopback DNS."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))]
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", return_value=private):
            assert validate_base_url("https://localhost:11434/v1") is False
        assert validate_base_url("http://0.0.0.0:8000") is False

    # Local mode permits only localhost resolving entirely to loopback.
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 11434))]):
            assert validate_base_url("http://localhost:11434") is True
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 11434, 0, 0))]):
            assert validate_base_url("http://localhost:11434") is True
        # Arbitrary hostnames cannot use local mode, including loopback DNS.
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 11434))]):
            assert validate_base_url("http://local-llm.example:11434") is False
        assert validate_base_url("https://example.com/v1") is False

    # Custom public proxy with ALLOW_CUSTOM_LLM_PROXY=true (HTTPS required for non-loopback)
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        # Plaintext http rejected for non-loopback custom proxies
        assert validate_base_url("http://proxy.example.com/v1") is False
        assert validate_base_url("http://custom-llm-gateway.org/api") is False

        # Deterministic mock DNS resolutions for HTTPS custom proxies
        # 1. Valid public IP resolution -> Allowed
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
            assert validate_base_url("https://proxy.example.com/v1") is True

        # Local and custom modes compose for public HTTPS proxies without allowing mixed DNS.
        with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true", "ALLOW_CUSTOM_LLM_PROXY": "true"}):
            with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
                assert validate_base_url("https://proxy.example.com/v1") is True
            with patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443)),
            ]):
                assert validate_base_url("https://mixed-dns.example.com/v1") is False

        # 2. DNS exception (fail-closed) -> Rejected
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            assert validate_base_url("https://nonexistent-proxy.example.com/v1") is False

        # 3. Empty DNS results (fail-closed) -> Rejected
        with patch("socket.getaddrinfo", return_value=[]):
            assert validate_base_url("https://empty-dns.example.com/v1") is False

        # 4. Mixed public and private DNS answers (rebinding attack defense) -> Rejected
        with patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))
        ]):
            assert validate_base_url("https://mixed-dns.example.com/v1") is False

        # 5. Malformed DNS sockaddr -> Rejected
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ())]):
            assert validate_base_url("https://malformed-dns.example.com/v1") is False

        # Cloud metadata, 0.0.0.0, link-local, loopback, private still rejected
        assert validate_base_url("http://169.254.169.254") is False
        assert validate_base_url("http://0.0.0.0:8000") is False
        assert validate_base_url("http://[::]:8000") is False
        assert validate_base_url("http://127.0.0.1:11434") is False
        assert validate_base_url("http://10.0.0.1:8000") is False
        assert validate_base_url("http://192.168.1.1:8000") is False
        assert validate_base_url("http://172.16.0.1:8000") is False


@pytest.mark.parametrize("answers", [
    [("192.168.1.50", 443), ("93.184.216.34", 443)],
    [("93.184.216.34", 443), ("192.168.1.50", 443)],
])
def test_allowlisted_provider_rejects_mixed_private_public_dns_with_local_mode(answers):
    """Provider DNS answers remain globally routable even when local mode is enabled."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", answer) for answer in answers]
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", return_value=addr_info):
            assert validate_base_url("https://api.openai.com/v1") is False


def test_provider_and_custom_proxy_reject_cgnat_dns():
    """CGNAT is non-global and cannot be used by external LLM hostnames."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    cgnat = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=cgnat):
        assert validate_base_url("https://api.openai.com/v1") is False
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", return_value=cgnat):
            assert validate_base_url("https://proxy.example.com/v1") is False


def test_custom_proxy_rejects_public_ip_literals_and_accepts_public_hostname():
    """Custom proxies require an HTTPS hostname; its one resolved global IP is pinned."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        assert validate_base_url("https://8.8.8.8/v1") is False
        with patch("socket.getaddrinfo", return_value=public):
            assert validate_base_url("https://proxy.example.com/v1") is True


@pytest.mark.parametrize("hostname", [
    "010.010.010.010", "0x08080808", "134744072", "3758096385", "127.1", "0x7f.1",
    "127.0.0.1.", "0177.0.0.1.", "0x7f000001.", "2130706433.",
])
def test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns(hostname):
    """Legacy IPv4 spellings must never reach a platform-dependent resolver."""
    from omega.api.routes.copilot import validate_base_url

    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", side_effect=AssertionError("legacy numeric host must not resolve")):
            assert validate_base_url(f"https://{hostname}/v1") is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/v1", "https://127.0.0.1/v1", "https://10.0.0.1/v1",
    "https://172.16.0.1/v1", "https://192.168.1.1/v1", "https://100.64.0.1/v1",
    "https://169.254.169.254/v1", "https://192.0.2.1/v1", "https://198.51.100.1/v1",
    "https://203.0.113.1/v1", "https://224.0.0.1/v1", "https://0.0.0.0/v1",
    "http://[::1]:11434/v1", "https://[fc00::1]/v1", "https://[fe80::1]/v1",
    "https://[2001:db8::1]/v1", "https://[ff02::1]/v1", "https://[::]/v1",
    "https://[2001:4860:4860::8888]/v1",
])
def test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins(url):
    """IP literals never receive local, provider, or custom-proxy exemptions."""
    from omega.api.routes.copilot import validate_base_url

    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true", "ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", side_effect=AssertionError("IP literal must not resolve through DNS")):
            assert validate_base_url(url) is False


@pytest.mark.parametrize("unsafe_ip", [
    "169.254.169.254", "192.0.2.1", "100.64.0.1", "192.168.1.50", "fe80::1", "2001:db8::1", "ff02::1", "::",
])
def test_localhost_rejects_unsafe_dns_answers(unsafe_ip):
    """Local mode rejects metadata, reserved, LAN, and other non-loopback DNS answers."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    family = socket.AF_INET6 if ":" in unsafe_ip else socket.AF_INET
    sockaddr = (unsafe_ip, 11434, 0, 0) if family == socket.AF_INET6 else (unsafe_ip, 11434)
    with patch.dict("os.environ", {"ALLOW_LOCAL_LLM": "true"}):
        with patch("socket.getaddrinfo", return_value=[(family, socket.SOCK_STREAM, 6, "", sockaddr)]):
            assert validate_base_url("https://localhost:11434/v1") is False


@pytest.mark.parametrize("unsafe_ip", [
    "224.0.0.1", "ff02::1", "fec0::1", "64:ff9b::7f00:1", "64:ff9b::a00:1",
    "::127.0.0.1", "::ffff:127.0.0.1", "::ffff:0:7f00:1", "2002:7f00:1::1",
])
@pytest.mark.parametrize("hostname, environment", [
    ("api.openai.com", {}),
    ("proxy.example.com", {"ALLOW_CUSTOM_LLM_PROXY": "true"}),
])
def test_provider_and_custom_proxy_reject_unsafe_global_looking_dns(unsafe_ip, hostname, environment):
    """DNS answers need safe unicast semantics, not Python's evolving is_global flag."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    family = socket.AF_INET6 if ":" in unsafe_ip else socket.AF_INET
    sockaddr = (unsafe_ip, 443, 0, 0) if family == socket.AF_INET6 else (unsafe_ip, 443)
    with patch.dict("os.environ", environment, clear=False):
        with patch("socket.getaddrinfo", return_value=[(family, socket.SOCK_STREAM, 6, "", sockaddr)]):
            assert validate_base_url(f"https://{hostname}/v1") is False


@pytest.mark.parametrize("unsafe_ip", [
    "0.1.2.3", "192.0.0.9", "192.88.99.1", "198.18.0.1", "240.0.0.1",
    "100::1", "2001:db8::1", "3ffe::1", "fc00::1",
])
@pytest.mark.parametrize("hostname, environment", [
    ("api.openai.com", {}),
    ("proxy.example.com", {"ALLOW_CUSTOM_LLM_PROXY": "true"}),
])
def test_provider_and_custom_proxy_reject_special_use_dns_ranges(unsafe_ip, hostname, environment):
    """Provider and custom proxy DNS admission rejects explicit special-use ranges."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    family = socket.AF_INET6 if ":" in unsafe_ip else socket.AF_INET
    sockaddr = (unsafe_ip, 443, 0, 0) if family == socket.AF_INET6 else (unsafe_ip, 443)
    with patch.dict("os.environ", environment, clear=False):
        with patch("socket.getaddrinfo", return_value=[(family, socket.SOCK_STREAM, 6, "", sockaddr)]):
            assert validate_base_url(f"https://{hostname}/v1") is False


@pytest.mark.parametrize("unsafe_ip", [
    "192.31.196.1", "192.52.193.1", "192.175.48.1", "2620:4f:8000::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:192.168.1.1",
    "::ffff:172.16.0.1", "::ffff:169.254.169.254",
    "2606:4700:4700::5efe:a00:1", "2001:4860:4860::ffff:7f00:1",
])
@pytest.mark.parametrize("hostname, environment", [
    ("api.openai.com", {}),
    ("proxy.example.com", {"ALLOW_CUSTOM_LLM_PROXY": "true"}),
])
def test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns(unsafe_ip, hostname, environment):
    """Every IPv6 DNS answer is rejected when its embedded IPv4 payload is unsafe."""
    import socket
    from omega.api.routes.copilot import validate_base_url

    family = socket.AF_INET6 if ":" in unsafe_ip else socket.AF_INET
    sockaddr = (unsafe_ip, 443, 0, 0) if family == socket.AF_INET6 else (unsafe_ip, 443)
    with patch.dict("os.environ", environment, clear=False):
        with patch("socket.getaddrinfo", return_value=[(family, socket.SOCK_STREAM, 6, "", sockaddr)]):
            assert validate_base_url(f"https://{hostname}/v1") is False
