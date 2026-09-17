import json
import pytest
import time
import socket
from copy import deepcopy
from starlette.testclient import TestClient
from unittest.mock import patch
from omega.api.server import app
from omega.api.routes.copilot import (
    _IN_MEMORY_LLM_CONFIG,
    mask_api_key,
    is_masked_key,
    MultiProfileLLMConfig,
    LLMProfileConfig
)
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

# -----------------------------------------------------------------------------
# 16-DIMENSION MASTER ADVERSARIAL TEST SUITE: PHASE 12 LLM MULTI-PROFILE CONFIG
# -----------------------------------------------------------------------------

def test_dim1_strict_types_and_schema_validation(client):
    """Dim 1: Strict Types & Malformed Inputs - rejects invalid types and boundaries."""
    # Invalid temperature > 1.0
    payload = {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 1.8, # invalid
            "max_tokens": 4096,
            "timeout_seconds": 30,
            "enabled": True
        }
    }
    resp = client.post("/api/v1/copilot/config", json=payload)
    assert resp.status_code == 422 # Pydantic Validation Error

    # Invalid max_tokens < 128
    payload2 = {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.2,
            "max_tokens": 50, # invalid
            "timeout_seconds": 30,
            "enabled": True
        }
    }
    resp2 = client.post("/api/v1/copilot/config", json=payload2)
    assert resp2.status_code == 422


def test_dim2_file_io_and_endpoint_routing(client):
    """Dim 2: File I/O & Endpoint Routing Contracts."""
    resp = client.get("/api/v1/copilot/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "profiles" in data
    assert "global_profile" in data["profiles"]
    assert "alpha_quant" in data["profiles"]
    assert "news_sentiment" in data["profiles"]
    assert "macro_micro" in data["profiles"]


def test_dim3_transactional_durability_and_secret_retention(client):
    """Dim 3: Transactional Durability & Secret Preservation when masked string is posted back."""
    # Original key
    orig_key = _IN_MEMORY_LLM_CONFIG["global_profile"]["api_key"]
    assert orig_key is not None

    # Post back with masked key "sk-p••••••••5544"
    update_payload = {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o-custom",
            "api_key": "sk-p••••••••5544",
            "temperature": 0.35,
            "max_tokens": 8192,
            "timeout_seconds": 45,
            "enabled": True
        }
    }
    resp = client.post("/api/v1/copilot/config", json=update_payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "success"

    # Verify the real key in memory was preserved
    assert _IN_MEMORY_LLM_CONFIG["global_profile"]["api_key"] == orig_key
    assert _IN_MEMORY_LLM_CONFIG["global_profile"]["model"] == "gpt-4o-custom"
    assert _IN_MEMORY_LLM_CONFIG["global_profile"]["temperature"] == 0.35


def test_dim4_memory_bounds_and_sanitized_payload(client):
    """Dim 4: Memory Bounds & Sanitized Payloads - outputs must never contain unmasked secrets."""
    resp = client.get("/api/v1/copilot/config")
    assert resp.status_code == 200
    data = resp.json()
    for p_key, prof in data["profiles"].items():
        assert "api_key" in prof
        assert "•" in prof["api_key"] or prof["api_key"] == ""
        assert not prof["api_key"].startswith("sk-proj-omega-global-live-key")


def test_dim5_concurrency_and_probe_connectivity(client):
    """Dim 5: Concurrency & Live Connection Probe ping endpoint."""
    probe_req = {
        "profile_key": "alpha_quant",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "timeout_seconds": 30
    }
    resp = client.post("/api/v1/copilot/config/test", json=probe_req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["profile_key"] == "alpha_quant"
    assert data["latency_ms"] >= 0.0
    assert data["error_code"] in {"UNAUTHORIZED", "CONNECTION_FAILED", "TIMEOUT"}


def test_dim6_pit_temporal_clock_iso_formatting(client):
    """Dim 6: Point-In-Time (PIT) & Literal UTC ISO Timestamps."""
    resp = client.get("/api/v1/copilot/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "timestamp" in data
    assert "+00:00" in data["timestamp"] or data["timestamp"].endswith("Z") or "T" in data["timestamp"]


def test_dim7_sparse_calendar_and_profile_isolation(client):
    """Dim 7: Profile Isolation - Modifying one profile does not alter other sub-engine profiles."""
    initial_profiles = deepcopy(_IN_MEMORY_LLM_CONFIG)

    resp = client.post("/api/v1/copilot/config", json={"news_sentiment": {"model": "gemini-2.0-flash"}})
    assert resp.status_code == 200
    updated_profiles = resp.json()["profiles"]

    assert updated_profiles["news_sentiment"]["model"] == "gemini-2.0-flash"
    for field, value in initial_profiles["news_sentiment"].items():
        if field != "model":
            assert _IN_MEMORY_LLM_CONFIG["news_sentiment"][field] == value
    for profile_key in ("global_profile", "alpha_quant", "macro_micro"):
        assert _IN_MEMORY_LLM_CONFIG[profile_key] == initial_profiles[profile_key]

    resp = client.post("/api/v1/copilot/config", json={"news_sentiment": {"temperature": 0.25, "api_key": "sk-p••••••••5544"}})
    assert resp.status_code == 200
    assert _IN_MEMORY_LLM_CONFIG["news_sentiment"]["model"] == "gemini-2.0-flash"
    assert _IN_MEMORY_LLM_CONFIG["news_sentiment"]["api_key"] == initial_profiles["news_sentiment"]["api_key"]
    for profile_key in ("global_profile", "alpha_quant", "macro_micro"):
        assert _IN_MEMORY_LLM_CONFIG[profile_key] == initial_profiles[profile_key]


def test_dim8_mathematical_extremes_and_temperature_bounds(client):
    """Dim 8: Mathematical Extremes - Temperature limits at exact 0.0 and 1.0."""
    valid_boundary_payload = {
        "alpha_quant": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.0, # exact minimum
            "max_tokens": 128,  # exact minimum
            "timeout_seconds": 5, # exact minimum
            "enabled": True
        },
        "macro_micro": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 1.0, # exact maximum
            "max_tokens": 32768, # exact maximum
            "timeout_seconds": 180, # exact maximum
            "enabled": True
        }
    }
    resp = client.post("/api/v1/copilot/config", json=valid_boundary_payload)
    assert resp.status_code == 200
    data = resp.json()["profiles"]
    assert data["alpha_quant"]["temperature"] == 0.0
    assert data["macro_micro"]["temperature"] == 1.0


def test_dim9_financial_and_engine_specialization(client):
    """Dim 9: Financial & Engine Specialization for all 4 quantitative tiers."""
    resp = client.get("/api/v1/copilot/config")
    profiles = resp.json()["profiles"]
    keys = ["global_profile", "alpha_quant", "news_sentiment", "macro_micro"]
    for k in keys:
        assert k in profiles
        assert "has_key" in profiles[k]
        assert profiles[k]["enabled"] is True


def test_dim10_case_insensitive_and_provider_canonicalization(client):
    """Dim 10: Case-Insensitive & Provider Canonicalization."""
    probe_req = {
        "profile_key": "global_profile",
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
        "api_key": "sk-ant-api03-test-live-key-12345",
        "temperature": 0.2,
        "timeout_seconds": 30
    }
    safe_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=safe_dns):
        resp = client.post("/api/v1/copilot/config/test", json=probe_req)
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
    assert resp.json()["error_code"] in {"UNAUTHORIZED", "CONNECTION_FAILED", "TIMEOUT"}

    unsafe_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))]
    with patch("socket.getaddrinfo", return_value=unsafe_dns):
        resp = client.post("/api/v1/copilot/config/test", json=probe_req)
    assert resp.status_code == 400


def test_dim11_fail_closed_and_invalid_profile_key(client):
    """Dim 11: Fail-Closed & Explicit Error on Unknown Profile Key."""
    probe_req = {
        "profile_key": "non_existent_engine",
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.2,
        "timeout_seconds": 30
    }
    resp = client.post("/api/v1/copilot/config/test", json=probe_req)
    assert resp.status_code == 400
    assert "Unknown profile key" in resp.json()["detail"]


def test_dim12_full_suite_regression_closure(client):
    """Dim 12: Full-Suite Regression - Copilot Ask endpoint still functional after config updates."""
    ask_req = {
        "query": "Đánh giá vĩ mô và thanh khoản OMO",
        "context_ticker": "FPT"
    }
    resp = client.post("/api/v1/copilot/ask", json=ask_req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["intent"] == "MACRO_SENTIMENT"


def test_dim13_metric_and_artifact_consistency(client):
    """Dim 13: Metric & Artifact Consistency - helper mask functions accuracy."""
    assert mask_api_key(None) == ""
    assert mask_api_key("") == ""
    assert mask_api_key("12345") == "•••••"
    assert mask_api_key("sk-proj-omega-live-key-1234567890") == "sk-p••••••••7890"
    assert is_masked_key("sk-p••••••••7890") is True
    assert is_masked_key("sk-proj-omega-plain-text") is False


def test_dim14_exception_chaining_and_missing_key_probe(client):
    """Dim 14: Exception Chaining & Graceful Error Probe for Missing Key."""
    probe_req = {
        "profile_key": "global_profile",
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "", # empty key override
        "temperature": 0.2,
        "timeout_seconds": 30
    }
    # Temporarily remove in-memory key
    orig = _IN_MEMORY_LLM_CONFIG["global_profile"]["api_key"]
    _IN_MEMORY_LLM_CONFIG["global_profile"]["api_key"] = ""
    try:
        resp = client.post("/api/v1/copilot/config/test", json=probe_req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["error_code"] in {"UNAUTHORIZED", "CONNECTION_FAILED", "TIMEOUT"}
    finally:
        _IN_MEMORY_LLM_CONFIG["global_profile"]["api_key"] = orig


def test_dim15_opt_in_safety_defaults(client):
    """Dim 15: Opt-in Safety - Default Pydantic initialization is robust."""
    multi_conf = MultiProfileLLMConfig()
    assert multi_conf.global_profile.model == "gpt-4o"
    assert multi_conf.alpha_quant.model == "gpt-4o-mini"
    assert multi_conf.news_sentiment.model == "gpt-4o-mini"
    assert multi_conf.macro_micro.model == "gpt-4o"


def test_dim16_security_and_secret_leakage_prevention(client):
    """Dim 16: Security & Zero Secret Leakage Prevention under adversarial inspection."""
    resp = client.get("/api/v1/copilot/config")
    body_str = resp.text
    # Ensure raw sensitive tokens are nowhere in response body
    assert "sk-proj-omega-global-live-key" not in body_str
    assert "sk-proj-omega-alpha-ast-key" not in body_str
    assert "sk-proj-omega-sentiment-key" not in body_str
    assert "sk-proj-omega-macro-key" not in body_str


@pytest.mark.parametrize("base_url, secret", [
    ("https://username-only-secret@proxy.example.com/v1", "username-only-secret"),
    ("https://user-secret:password-secret@proxy.example.com/v1", "password-secret"),
    ("https://%75serinfo%2Dsecret@proxy.example.com/v1", "%75serinfo%2Dsecret"),
    ("https://@proxy.example.com/v1", "@proxy.example.com"),
    ("https://:blank-username-password-secret@proxy.example.com/v1", "blank-username-password-secret"),
    ("https://blank-password-secret:@proxy.example.com/v1", "blank-password-secret"),
])
def test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation(client, base_url, secret):
    """Userinfo is invalid before resolution, persistence, or response serialization."""
    snapshot = deepcopy(copilot._IN_MEMORY_LLM_CONFIG)
    with patch("socket.getaddrinfo", side_effect=AssertionError("userinfo must not resolve")) as resolver:
        response = client.post("/api/v1/copilot/config", json={
            "global_profile": {"base_url": base_url},
        })

    assert response.status_code == 400
    assert secret not in response.text
    assert copilot._IN_MEMORY_LLM_CONFIG == snapshot
    resolver.assert_not_called()


@pytest.mark.parametrize("path,payload", [
    ("/api/v1/copilot/config", {"global_profile": {"base_url": "https://url-user-secret:url-password-secret@proxy.example.com:8443/v1?token=url-query-secret"}}),
    ("/api/v1/copilot/config/test", {"profile_key": "global_profile", "base_url": "https://url-user-secret:url-password-secret@proxy.example.com:8443/v1?token=url-query-secret"}),
])
def test_config_url_errors_redact_credentials_without_dns(client, path, payload):
    """Save and probe errors expose a useful origin, never URL credentials."""
    with patch("socket.getaddrinfo", side_effect=AssertionError("userinfo must not resolve")) as resolver:
        response = client.post(path, json=payload)

    assert response.status_code == 400
    assert "url-user-secret" not in response.text
    assert "url-password-secret" not in response.text
    assert "url-query-secret" not in response.text
    assert "https://proxy.example.com:8443" in response.json()["detail"]
    resolver.assert_not_called()


def test_config_allows_public_custom_hostname_when_opted_in(client):
    """Userinfo rejection preserves the explicit public custom-proxy path."""
    safe_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch.dict("os.environ", {"ALLOW_CUSTOM_LLM_PROXY": "true"}):
        with patch("socket.getaddrinfo", return_value=safe_dns) as resolver:
            response = client.post("/api/v1/copilot/config", json={
                "global_profile": {"base_url": "https://proxy.example.com/v1"},
            })

    assert response.status_code == 200
    assert response.json()["profiles"]["global_profile"]["base_url"] == "https://proxy.example.com/v1"
    resolver.assert_called_once()


@pytest.mark.parametrize("base_url, secrets", [
    ("https://username-only-secret@proxy.example.com/v1", ["username-only-secret"]),
    ("https://userinfo-secret:password-secret@proxy.example.com/v1", ["userinfo-secret", "password-secret"]),
    ("https://%75ser%2Dsecret:%70assword%2Dsecret@proxy.example.com/v1", ["%75ser%2Dsecret", "%70assword%2Dsecret", "user-secret", "password-secret"]),
    ("https://:empty-username-password-secret@proxy.example.com/v1", ["empty-username-password-secret"]),
    ("https://empty-password-username-secret:@proxy.example.com/v1", ["empty-password-username-secret"]),
])
def test_config_test_rejection_redaction_matrix(client, base_url, secrets):
    """POST /config/test rejection leaks no userinfo on the full serialized body."""
    snapshot = deepcopy(copilot._IN_MEMORY_LLM_CONFIG)
    with patch("socket.getaddrinfo", side_effect=AssertionError("userinfo must not resolve")) as resolver:
        response = client.post("/api/v1/copilot/config/test", json={
            "profile_key": "global_profile",
            "base_url": base_url,
        })

    assert response.status_code == 400
    body_dump = json.dumps(response.json(), ensure_ascii=False)
    for secret in secrets:
        assert secret not in body_dump
        assert secret not in response.text
    detail = response.json()["detail"]
    assert "SSRF validation failed" in detail
    assert "https://proxy.example.com" in detail
    assert "@" not in detail
    resolver.assert_not_called()
    assert copilot._IN_MEMORY_LLM_CONFIG == snapshot


def test_free_text_url_redaction_helper_strips_credentials_only():
    """Diagnostics text keeps origins but drops userinfo/query secrets everywhere."""
    from omega.api.routes.copilot import redact_credentials_in_text

    dirty = "probe failed for https://diag-user:diag-pass@proxy.example.com:9443/v1/chat?token=diag-query-secret"
    clean = redact_credentials_in_text(dirty)
    assert "diag-user" not in clean
    assert "diag-pass" not in clean
    assert "diag-query-secret" not in clean
    assert "https://proxy.example.com:9443" in clean
    assert redact_credentials_in_text("no urls here") == "no urls here"
    assert redact_credentials_in_text("https://[::1]:1/a") == "https://[::1]:1"
    assert redact_credentials_in_text("not a url at all") == "not a url at all"
    assert redact_credentials_in_text("https:///no-host") == "invalid URL"
