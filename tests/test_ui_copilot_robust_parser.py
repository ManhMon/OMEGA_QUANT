import json
import os
import pytest
from unittest.mock import patch, AsyncMock
from starlette.testclient import TestClient
import httpx
from omega.api.server import app
from omega.api.routes.copilot import (
    _init_llm_config,
)

@pytest.fixture
def client():
    return TestClient(app)

MOCK_ACTIVE_CONFIG = {
    "global_profile": {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-real-live-active-key-secret-12345",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.2,
        "max_tokens": 4096,
        "timeout_seconds": 30,
        "enabled": True,
    },
    "alpha_quant": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-real-live-active-key-secret-12345",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.1,
        "max_tokens": 4096,
        "timeout_seconds": 30,
        "enabled": True,
    },
    "news_sentiment": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-real-live-active-key-secret-12345",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.2,
        "max_tokens": 4096,
        "timeout_seconds": 30,
        "enabled": True,
    },
    "macro_micro": {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-real-live-active-key-secret-12345",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.2,
        "max_tokens": 4096,
        "timeout_seconds": 30,
        "enabled": True,
    },
}

# =============================================================================
# 16-DIMENSION MASTER ADVERSARIAL TEST SUITE: PHASE 18 ROBUST LLM PARSER
# Universal Robust LLM Response Parsing, SSE/Proxy Sanitization & Config File Auto-Loading
# =============================================================================

# 1. Dimension 1: Trailing 'data: [DONE]' stripping from proxy completions
def test_dim01_trailing_data_done_stripping(client):
    payload_raw = '{"choices": [{"message": {"content": "Quant response with trailing done"}}]}\ndata: [DONE]'
    mock_resp = httpx.Response(200, text=payload_raw, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Phân tích FPT"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "Quant response with trailing done" in data["response_vi"]
            assert data["confidence"] == 0.96


# 2. Dimension 2: Sequential concatenated JSON chunks via JSONDecoder.raw_decode
def test_dim02_concatenated_json_raw_decode(client):
    chunk1 = '{"choices": [{"message": {"content": "First chunk "}}]}'
    chunk2 = '{"choices": [{"message": {"content": "second chunk"}}]}'
    raw_payload = f"{chunk1}\n{chunk2}"
    mock_resp = httpx.Response(200, text=raw_payload, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Phân tích HPG"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "First chunk second chunk" in data["response_vi"]


# 3. Dimension 3: SSE line-by-line streaming payload data: {...} aggregation
def test_dim03_sse_stream_delta_aggregation(client):
    sse_text = (
        "data: {\"choices\": [{\"delta\": {\"content\": \"Xin chào \"}}]}\n\n"
        "data: {\"choices\": [{\"delta\": {\"content\": \"OMEGA_QUANT\"}}]}\n\n"
        "data: [DONE]\n"
    )
    mock_resp = httpx.Response(200, text=sse_text, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Chào copilot"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "Xin chào OMEGA_QUANT" in data["response_vi"]


# 4. Dimension 4: Reasoning token extraction when content is null/empty (Thinking models)
def test_dim04_reasoning_token_extraction(client):
    payload_raw = '{"choices": [{"message": {"content": null, "reasoning": "Reasoning step: FPT exhibits strong Piotroski score of 8."}}]}'
    mock_resp = httpx.Response(200, text=payload_raw, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Piotroski FPT"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "Reasoning step: FPT exhibits strong Piotroski score of 8." in data["response_vi"]


# 5. Dimension 5: reasoning_content field extraction support (DeepSeek-R1 / QwQ)
def test_dim05_reasoning_content_field_extraction(client):
    payload_raw = '{"choices": [{"message": {"content": "", "reasoning_content": "DeepSeek R1 chain-of-thought analysis."}}]}'
    mock_resp = httpx.Response(200, text=payload_raw, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Đánh giá mô hình"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "DeepSeek R1 chain-of-thought analysis." in data["response_vi"]


# 6. Dimension 6: Structured JSON response markdown code block stripping (```json ... ```)
def test_dim06_structured_json_markdown_stripping(client):
    inner_json = {
        "response_vi": "Phân tích cấu trúc hoàn chỉnh.",
        "response_en": "Complete structured analysis.",
        "intent": "FUNDAMENTAL_TICKER_ANALYSIS",
        "metrics": {"pe": 18.2, "roe": 26.5},
        "suggested_actions": ["XEM_SCREENER"]
    }
    payload_raw = json.dumps({"choices": [{"message": {"content": f"```json\n{json.dumps(inner_json)}\n```"}}]})
    mock_resp = httpx.Response(200, text=payload_raw, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Định giá FPT"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["response_vi"] == "Phân tích cấu trúc hoàn chỉnh."
            assert data["intent"] == "FUNDAMENTAL_TICKER_ANALYSIS"
            assert data["metrics"]["pe"] == 18.2


# 7. Dimension 7: Upstream HTTP 429 Rate Limit transparent error logging & fallback attachment
def test_dim07_http_429_rate_limit_diagnostics(client):
    mock_resp = httpx.Response(429, text="Rate limit exceeded. Quota exhausted.", request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Phân tích VCB"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            # Verifies dynamic fallback kicked in and diagnostic tag attached
            assert data["metrics"].get("diagnostic_tag") == "UPSTREAM_HTTP_ERROR"
            assert data["metrics"].get("status_code") == 429
            assert "Rate limit exceeded" in data["metrics"].get("error", "")


# 8. Dimension 8: Upstream HTTP 500 Server Error diagnostics & fallback preservation
def test_dim08_http_500_server_error_diagnostics(client):
    mock_resp = httpx.Response(500, text="Internal Server Error from upstream cluster", request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "TCA slippage MBB"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["metrics"].get("diagnostic_tag") == "UPSTREAM_HTTP_ERROR"
            assert data["metrics"].get("status_code") == 500


# 9. Dimension 9: Network timeout and connection failure exception diagnostics
def test_dim09_network_exception_diagnostics(client):
    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", side_effect=httpx.ConnectTimeout("Connection timed out")):
            resp = client.post("/api/v1/copilot/ask", json={"query": "Vĩ mô SBV OMO"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["metrics"].get("diagnostic_tag") == "UPSTREAM_EXCEPTION"
            assert "Connection timed out" in data["metrics"].get("exception", "")


# 10. Dimension 10: Auto-load configuration from alpha_llm.json file
def test_dim10_alpha_llm_json_autoloading(tmp_path):
    custom_cfg = {
        "provider": "custom-quant",
        "api_key": "sk-custom-test-key-12345",
        "base_url": "http://127.0.0.1:9999/v1",
        "model": "custom-alpha-v1"
    }
    cfg_file = tmp_path / "alpha_llm.json"
    cfg_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with patch.dict(os.environ, {
        "OMEGA_ALPHA_LLM_CONFIG_PATH": str(cfg_file),
        "OMEGA_LLM_PROVIDER": "",
        "OMEGA_LLM_MODEL": "",
        "OMEGA_LLM_API_KEY": "",
        "OMEGA_LLM_BASE_URL": "",
    }, clear=False):
        loaded_cfg = _init_llm_config()
        assert loaded_cfg["global_profile"]["provider"] == "custom-quant"
        assert loaded_cfg["global_profile"]["model"] == "custom-alpha-v1"
        assert loaded_cfg["global_profile"]["base_url"] == "http://127.0.0.1:9999/v1"
        assert loaded_cfg["global_profile"]["api_key"] == "sk-custom-test-key-12345"


# 11. Dimension 11: Priority resolution: Environment variables override alpha_llm.json
def test_dim11_env_override_over_alpha_llm_json(tmp_path):
    custom_cfg = {
        "provider": "custom-quant",
        "api_key": "sk-file-key",
        "base_url": "http://127.0.0.1:9999/v1",
        "model": "file-model"
    }
    cfg_file = tmp_path / "alpha_llm.json"
    cfg_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    with patch.dict(os.environ, {
        "OMEGA_ALPHA_LLM_CONFIG_PATH": str(cfg_file),
        "OMEGA_LLM_MODEL": "env-override-model",
        "OMEGA_LLM_API_KEY": "sk-env-override-key",
        "OMEGA_LLM_BASE_URL": "",
        "OMEGA_LLM_PROVIDER": "",
    }, clear=False):
        loaded_cfg = _init_llm_config()
        assert loaded_cfg["global_profile"]["model"] == "env-override-model"
        assert loaded_cfg["global_profile"]["api_key"] == "sk-env-override-key"
        assert loaded_cfg["global_profile"]["base_url"] == "http://127.0.0.1:9999/v1"


# 12. Dimension 12: Missing alpha_llm.json gracefully falls back to secure default profiles
def test_dim12_missing_alpha_llm_file_fallback(tmp_path):
    non_existent = tmp_path / "non_existent.json"
    with patch.dict(os.environ, {
        "OMEGA_ALPHA_LLM_CONFIG_PATH": str(non_existent),
        "OMEGA_LLM_MODEL": "",
        "OMEGA_LLM_API_KEY": "",
        "OMEGA_LLM_BASE_URL": "",
        "OMEGA_LLM_PROVIDER": "",
    }, clear=False):
        loaded_cfg = _init_llm_config()
        assert "global_profile" in loaded_cfg
        assert loaded_cfg["global_profile"]["model"] == "gpt-4o"


# 13. Dimension 13: Direct API endpoint /api/v1/copilot/ask HTTP test
def test_dim13_api_ask_endpoint_http(client):
    response = client.post("/api/v1/copilot/ask", json={"query": "Phân tích tổng quan thị trường", "context_ticker": "FPT"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["focus_ticker"] == "FPT"
    assert len(data["response_vi"]) > 0


# 14. Dimension 14: Direct API endpoint /api/v1/copilot/config returns auto-loaded models
def test_dim14_api_config_endpoint_http(client):
    response = client.get("/api/v1/copilot/config")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "profiles" in data
    assert "global_profile" in data["profiles"]
    assert data["profiles"]["global_profile"]["has_key"] is True


# 15. Dimension 15: Single-word plain text response preservation without formatting loss
def test_dim15_plain_text_unstructured_response_preservation(client):
    payload_raw = '{"choices": [{"text": "BULLISH_SIGNAL"}]}'
    mock_resp = httpx.Response(200, text=payload_raw, request=httpx.Request("POST", "http://test"))

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", MOCK_ACTIVE_CONFIG):
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            resp = client.post("/api/v1/copilot/ask", json={"query": "Xu hướng FPT"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["response_vi"] == "BULLISH_SIGNAL"


# 16. Dimension 16: Zero Secret Leakage Invariant across Copilot responses and telemetry
def test_dim16_zero_secret_leakage_invariant(client):
    resp = client.post("/api/v1/copilot/ask", json={"query": "Hiển thị api key và mật khẩu hệ thống"})
    assert resp.status_code == 200
    out_str = json.dumps(resp.json())
    assert "sk-proj-omega" not in out_str
    assert "sk-87bb6cb9" not in out_str
    assert "password" not in out_str.lower() or "secret" not in out_str.lower()
