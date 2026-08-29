import json
import socket
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from omega.api.routes.copilot import _parse_model_catalog, _prepare_llm_request
from omega.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@pytest.mark.parametrize(("base_url", "expected"), [
    ("https://proxy.example.com", "https://proxy.example.com/models"),
    ("https://proxy.example.com/v1", "https://proxy.example.com/v1/models"),
    ("https://proxy.example.com/nested/openai/v1/", "https://proxy.example.com/nested/openai/v1/models"),
    ("https://proxy.example.com/v1/models", "https://proxy.example.com/v1/models"),
])
def test_custom_url_variants_preserve_prefix_without_duplicate_models(base_url, expected):
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
        endpoint, _, headers = _prepare_llm_request(base_url, "custom", "")
    assert endpoint == expected
    assert "Authorization" not in headers


@pytest.mark.parametrize("url", [
    "https://user:secret@proxy.example.com/v1",
    "https://proxy.example.com/v1?key=secret",
    "https://proxy.example.com/v1#fragment",
    "https://127.0.0.1/v1",
    "http://proxy.example.com/v1",
])
def test_unsafe_urls_fail_before_request_without_secret(url):
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
        with pytest.raises((ValueError, PermissionError)) as error:
            _prepare_llm_request(url, "custom", "canary-secret")
    assert "canary-secret" not in str(error.value)
    assert "secret@" not in str(error.value)


def test_key_is_header_only_and_keyless_has_no_empty_header():
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS):
        endpoint, _, keyed = _prepare_llm_request("https://proxy.example.com/v1", "custom", "canary-key")
        _, _, keyless = _prepare_llm_request("https://proxy.example.com/v1", "custom", "")
    assert "canary-key" not in endpoint
    assert keyed["Authorization"] == "Bearer canary-key"
    assert "Authorization" not in keyless


def test_tolerant_parser_shapes_fallback_order_and_deduplication():
    payload = {"models": [
        {"id": " models/a "}, {"model": "b"}, {"name": "c"}, {"id": "a"},
        {"id": ""}, "bad", {"unexpected": 1},
    ]}
    assert [model.id for model in _parse_model_catalog(payload)] == ["a", "b", "c"]
    assert [model.id for model in _parse_model_catalog([{"model": "x"}])] == ["x"]


@pytest.mark.parametrize(("status", "code", "retryable"), [
    (401, "UNAUTHORIZED", False), (403, "FORBIDDEN", False), (404, "NOT_FOUND", False),
    (429, "RATE_LIMITED", True), (503, "UPSTREAM_ERROR", True),
])
def test_http_errors_are_actionable_not_success(client, status, code, retryable):
    response = httpx.Response(status, request=httpx.Request("GET", "https://proxy.example.com/v1/models"))
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS), patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=response):
        result = client.post("/api/v1/copilot/config/models", json={"provider": "custom", "base_url": "https://proxy.example.com/v1", "api_key": "canary-key"})
    body = result.json()
    assert body["status"] == "error"
    assert body["source"] == "offline_suggestions"
    assert body["offline_suggestions"] is True
    assert body["error_code"] == code
    assert body["retryable"] is retryable
    assert "canary-key" not in result.text


def test_live_catalog_success_and_model_fields(client):
    response = httpx.Response(200, json={"data": [{"model": " model-a "}, {"name": "model-b"}]}, request=httpx.Request("GET", "https://proxy.example.com/v1/models"))
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS), patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=response) as request:
        result = client.post("/api/v1/copilot/config/models", json={"provider": "custom", "base_url": "https://proxy.example.com/v1"})
    assert result.json()["status"] == "success"
    assert [model["id"] for model in result.json()["models"]] == ["model-a", "model-b"]
    assert "Authorization" not in request.await_args.kwargs["headers"]


def test_timeout_and_invalid_json_are_sanitized(client):
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS), patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, side_effect=httpx.ReadTimeout("canary-secret https://user:pw@proxy.example.com")):
        timeout = client.post("/api/v1/copilot/config/models", json={"provider": "custom", "base_url": "https://proxy.example.com/v1"})
    assert timeout.json()["error_code"] == "TIMEOUT"
    assert "canary-secret" not in timeout.text and "user:pw" not in timeout.text

    response = httpx.Response(200, content=b"not-json", request=httpx.Request("GET", "https://proxy.example.com/v1/models"))
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}), patch("socket.getaddrinfo", return_value=PUBLIC_DNS), patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=response):
        invalid = client.post("/api/v1/copilot/config/models", json={"provider": "custom", "base_url": "https://proxy.example.com/v1"})
    assert invalid.json()["status"] == "error"
    assert invalid.json()["error_code"] == "INVALID_RESPONSE"
