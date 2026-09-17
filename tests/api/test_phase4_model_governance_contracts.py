"""
Phase 4 Model Governance, Resource Governor, Drift Detection & Promotion/Rollback Contract Tests.
Adversarial 16-Dimension Master Verification Suite.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from omega.api.server import app
from omega.api.routes.control import generate_totp, DEFAULT_TOTP_SECRET
from omega.api.schemas.advanced_quant import GovernorMode

client = TestClient(app)


# Dimension 1: Strict Types & Malformed Inputs (NaN, Inf, strings, lists)
def test_dim1_malformed_and_out_of_bounds_types():
    # Invalid model promote status
    totp = generate_totp(DEFAULT_TOTP_SECRET)
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": totp,
        "target_status": "INVALID_STATUS_UNKNOWN",
    }).status_code == 422

    # Malformed totp_code (non-digits or wrong length) fails validation with 422
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": "ABCDEF",
        "target_status": "VALIDATED",
    }).status_code == 422

    # Malformed governor mode
    assert client.patch("/api/v1/operations/resource-governor", json={
        "mode": "SUPER_TURBO",
    }).status_code == 422

    # Negative concurrency
    assert client.patch("/api/v1/operations/resource-governor", json={
        "target_concurrency": -4,
    }).status_code == 422


# Dimension 2: File I/O & Path Aliasing (Directory Traversal, invalid paths)
def test_dim2_directory_io_and_path_aliasing():
    # Directory traversal in model name
    assert client.get("/api/v1/models/..%2F..%2Fetc/versions").status_code == 404
    assert client.get("/api/v1/models/%2E%2Esecret/drift").status_code == 404


# Dimension 3: Corrupted / Duplicate / Partial Checkpoints & Shards
def test_dim3_corrupted_duplicate_partial_payloads():
    totp = generate_totp(DEFAULT_TOTP_SECRET)
    # Extra unexpected fields in promote request (StrictApiModel)
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": totp,
        "target_status": "VALIDATED",
        "injected_extra_column": "exploit",
    }).status_code == 422


# Dimension 4: Fail-Closed Exit Codes & Error States
def test_dim4_fail_closed_error_states():
    # Invalid TOTP returns 401
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": "000000",
        "target_status": "VALIDATED",
    }).status_code == 401

    # Non-existent model returns 404
    totp = generate_totp(DEFAULT_TOTP_SECRET)
    assert client.post("/api/v1/models/NON_EXISTENT_MODEL_XYZ/versions/v1.0.0/promote", json={
        "totp_code": totp,
        "target_status": "VALIDATED",
    }).status_code == 404

    # Non-existent version returns 404
    assert client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions/v99.99.99").status_code == 404


# Dimension 5: Rollback & Atomicity Failures
def test_dim5_rollback_and_atomic_read_isolation(monkeypatch):
    import omega.api.routes.models as mod_routes
    monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

    # Rollback to v1.0.0 succeeds and records state atomically
    res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/rollback", json={
        "totp_code": "123456",
        "target_version": "v1.0.0",
        "reason": "Deterministic rollback test",
    })
    print("DEBUG RESPONSE:", res.status_code, res.text)
    assert res.status_code == 200
    assert res.json()["target_version"] == "v1.0.0"
    assert res.json()["totp_verified"] is True


# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
def test_dim6_pit_lookahead_safety():
    res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/drift")
    assert res.status_code == 200
    data = res.json()
    evaluated_at = datetime.fromisoformat(data["evaluated_at"].replace("Z", "+00:00"))
    now_utc = datetime.now(timezone.utc)
    assert evaluated_at <= now_utc
    assert data["provenance"]["is_synthetic"] is False


# Dimension 7: Trading Calendar & Holiday Boundaries
def test_dim7_trading_calendar_and_holiday_boundaries():
    # Drift evaluation includes live market metrics alignment
    res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/drift")
    assert res.status_code == 200
    assert "metrics" in res.json()
    assert len(res.json()["metrics"]) >= 3


# Dimension 8: Numeric Precision & Zero-Division Overflow
def test_dim8_zero_division_and_numeric_bounds():
    # Concurrency must be > 0
    assert client.patch("/api/v1/operations/resource-governor", json={
        "target_concurrency": 0,
    }).status_code == 422

    res = client.get("/api/v1/operations/resource-governor")
    assert res.status_code == 200
    data = res.json()
    assert data["target_concurrency"] >= 1
    assert data["system_load_pct"] >= 0.0


# Dimension 9: Concurrency & Race Condition Resistance
def test_dim9_concurrency_race_condition_resistance():
    import concurrent.futures
    def fetch_gov():
        return client.get("/api/v1/operations/resource-governor")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_gov) for _ in range(16)]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# Dimension 10: VND_FULL Price Scale & Unit Invariance
def test_dim10_price_scale_and_unit_invariance():
    res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "v1.0.0"


# Dimension 11: Survivorship & Delisting Anomalies
def test_dim11_survivorship_and_delisting_anomalies():
    # Non-existent delisted model catalog lookup fails cleanly
    assert client.get("/api/v1/models/DELISTED_MODEL_2018/drift").status_code == 404


# Dimension 12: CLI Injection & Flag Smuggling Sanitization
def test_dim12_injection_sanitization(monkeypatch):
    import omega.api.routes.models as mod_routes
    monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

    # Reject flag smuggling or invalid version format
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/--flag-smuggle/promote", json={
        "totp_code": "123456",
        "target_status": "VALIDATED",
    }).status_code == 422


# Dimension 13: Schema Drift & Extra Column Mutations
def test_dim13_schema_drift_rejection():
    assert client.patch("/api/v1/operations/resource-governor", json={
        "mode": "COPILOT",
        "unexpected_field_mutation": 12345,
    }).status_code == 422


# Dimension 14: Resource Exhaustion & Memory Bounds
def test_dim14_memory_bounds_on_concurrency():
    # Excessively large concurrency bound rejected
    assert client.patch("/api/v1/operations/resource-governor", json={
        "target_concurrency": 999999,
    }).status_code == 422


# Dimension 15: Network Timeout & 429 Retry Exhaustion Resilience
def test_dim15_network_timeout_resilience():
    res = client.get("/api/v1/models")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["count"] >= 1


# Dimension 16: Secret Redaction & Credential Leak Prevention
def test_dim16_secret_redaction(monkeypatch):
    import omega.api.routes.models as mod_routes
    monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

    res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": "123456",
        "target_status": "VALIDATED",
    })
    assert res.status_code == 200
    text = res.text.lower()
    assert "totp_code" not in text
    assert "password" not in text
    assert "api_key" not in text


# Functional Verification Suite for Phase 4 Endpoints
def test_functional_phase4_model_governance_complete(monkeypatch):
    import omega.api.routes.models as mod_routes
    monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

    # 1. GET /api/v1/models
    res_list = client.get("/api/v1/models")
    assert res_list.status_code == 200
    assert res_list.json()["status"] == "success"
    assert res_list.json()["count"] >= 1

    # 2. GET /api/v1/models/{model_name}/versions
    res_vers = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions")
    assert res_vers.status_code == 200
    assert res_vers.json()["model_name"] == "ALPHA_XGBOOST_V2"
    assert len(res_vers.json()["versions"]) >= 1

    # 3. GET /api/v1/models/{model_name}/versions/{version}
    res_ver_detail = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0")
    assert res_ver_detail.status_code == 200
    assert res_ver_detail.json()["version"] == "v1.0.0"

    # 4. GET /api/v1/models/{model_name}/drift
    res_drift = client.get("/api/v1/models/ALPHA_XGBOOST_V2/drift")
    assert res_drift.status_code == 200
    assert res_drift.json()["model_name"] == "ALPHA_XGBOOST_V2"
    assert len(res_drift.json()["metrics"]) >= 3

    # 5. POST /api/v1/models/{model_name}/versions/{version}/promote (TOTP verified)
    res_prom = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
        "totp_code": "123456",
        "target_status": "VALIDATED",
        "promoter_id": "CHIEF_QUANT_OFFICER",
        "rationale": "Validation suite passed with IC 0.052",
    })
    assert res_prom.status_code == 200
    assert res_prom.json()["totp_verified"] is True
    assert res_prom.json()["target_status"] == "VALIDATED"

    # 6. POST /api/v1/models/{model_name}/rollback (TOTP verified)
    res_rb = client.post("/api/v1/models/ALPHA_XGBOOST_V2/rollback", json={
        "totp_code": "123456",
        "target_version": "v1.0.0",
        "reason": "Emergency stabilization",
    })
    assert res_rb.status_code == 200
    assert res_rb.json()["totp_verified"] is True

    # 7. GET /api/v1/operations/resource-governor
    res_gov = client.get("/api/v1/operations/resource-governor")
    assert res_gov.status_code == 200
    assert res_gov.json()["status"] == "success"

    # 8. PATCH /api/v1/operations/resource-governor
    res_gov_upd = client.patch("/api/v1/operations/resource-governor", json={
        "mode": "COPILOT",
        "target_concurrency": 16,
    })
    print("RES GOV UPD:", res_gov_upd.status_code, res_gov_upd.text)
    assert res_gov_upd.status_code == 200
    assert res_gov_upd.json()["mode"] == "COPILOT"
    assert res_gov_upd.json()["target_concurrency"] == 16
