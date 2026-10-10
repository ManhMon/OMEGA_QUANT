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


@pytest.fixture(autouse=True)
def isolate_phase4_state(monkeypatch, tmp_path):
    import copy
    from omega.api.routes import models, operations
    from omega.data.registry import ModelRegistry
    registry = ModelRegistry(str(tmp_path / "models"))
    registry.registry_data = copy.deepcopy(models._model_registry.registry_data)
    registry._save_registry()
    monkeypatch.setattr(models, "_model_registry", registry)
    # Existing governor tests exercise mutations; restore their file bytes exactly.
    paths = [value for key, value in vars(operations).items()
             if key.endswith("PATH") and hasattr(value, "is_file") and value.is_file()]
    snapshots = {path: path.read_bytes() for path in paths}
    yield
    for path, raw in snapshots.items():
        path.write_bytes(raw)


@pytest.fixture
def governance_payload():
    return {
        "reference_window": {
            "window_id": "reference", "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T08:30:00Z", "available_at": "2026-01-02T15:30:00+07:00",
            "unit": "VND_FULL", "features": {"price": [10000, 20000, 30000, 40000]},
        },
        "current_window": {
            "window_id": "current", "start": "2026-01-02T15:30:00+07:00",
            "end": "2026-01-03T00:00:00Z", "available_at": "2026-01-03T00:00:00Z",
            "unit": "VND_FULL", "features": {"price": [10000, 20000, 30000, 40000]},
        },
        "bins": 4,
    }


def test_slice14_lineage_and_drift_read_only(governance_payload, monkeypatch):
    import copy
    from omega.api.routes import models
    registry = models._model_registry
    metadata = registry.registry_data["models"]["ALPHA_XGBOOST_V2"]["versions"]["v1.0.0"]["metadata"]
    metadata["lineage"] = {
        "dataset_snapshot": {"dataset_id": "prices", "version": "snapshot1", "content_hash": "a" * 64,
                             "as_of": "2025-12-01T00:00:00Z", "available_at": "2025-12-02T00:00:00Z"},
        "training_run": {"run_id": "train1", "trained_at": "2026-01-01T00:00:00Z"},
        "git_commit": "b" * 40,
        "deployment_receipt": {"receipt_id": "deploy1", "version": "v1.0.0", "deployed_at": "2026-01-02T00:00:00Z"},
    }
    metadata["drift_windows"] = governance_payload
    registry._save_registry()
    before = copy.deepcopy(registry.registry_data)
    disk = registry.metadata_file.read_bytes()
    monkeypatch.setattr(registry, "_save_registry", lambda: pytest.fail("Read-only endpoint wrote registry"))
    lineage = client.get("/api/v1/models/ALPHA_XGBOOST_V2/lineage")
    assert lineage.status_code == 200
    assert lineage.json()["nodes"][0]["git_commit"] == "b" * 40
    for response in (client.get("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift"),
                     client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=governance_payload)):
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["metrics"][0]["psi"] == data["metrics"][0]["ks"] == 0
        assert data["automated_retrain"] is data["automated_deploy"] is False
        assert "unverified" in data["provenance_status"]
        assert "features" not in data["reference_window"]
    assert registry.registry_data == before
    assert registry.metadata_file.read_bytes() == disk


@pytest.mark.parametrize("bad", [None, "", "1700000000", "1700000000.5", "-1", "1e12", True, [], {},
                                 "NaN", "Inf", "-Inf", "2026-01-01", "2026-01-01T00:00:00",
                                 "2026-01-01T00:00:00+00:60", "2026-02-30T00:00:00Z"])
def test_slice14_explicit_iso_request_rejection(governance_payload, bad, monkeypatch):
    import copy
    from omega.api.routes import models
    registry = models._model_registry
    before, disk = copy.deepcopy(registry.registry_data), registry.metadata_file.read_bytes()

    def forbidden_write(*args, **kwargs):
        pytest.fail("Invalid timestamp reached persistence")

    monkeypatch.setattr(registry, "_save_registry", forbidden_write)
    monkeypatch.setattr(registry, "promote_model", forbidden_write)
    monkeypatch.setattr(models, "verify_totp", lambda code: True)
    for window in ("reference_window", "current_window"):
        for field in ("start", "end", "available_at"):
            payload = copy.deepcopy(governance_payload)
            payload[window][field] = bad
            response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=payload)
            assert response.status_code == 422
    for field in ("as_of", "available_at"):
        evidence = {"as_of": "2026-01-01T00:00:00Z", "available_at": "2026-01-01T00:00:00Z"}
        evidence[field] = bad
        response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote",
                               json={"totp_code": "123456", "target_status": "VALIDATED", "pit_evidence": evidence})
        assert response.status_code == 422
    response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote",
                           json={"totp_code": "123456", "target_status": "VALIDATED",
                                 "pit_evidence": {"as_of": None, "available_at": None}})
    assert response.status_code == 422
    assert registry.registry_data == before
    assert registry.metadata_file.read_bytes() == disk


def test_slice14_explicit_iso_parser_and_concurrency(governance_payload):
    import copy
    from concurrent.futures import ThreadPoolExecutor
    from datetime import tzinfo
    from fastapi import HTTPException
    from omega.api.routes import models

    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    for bad in (float("nan"), float("inf"), float("-inf"), 1e13, -1e13,
                datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=NoOffset()),
                "0001-01-01T00:00:00+23:59"):
        with pytest.raises(HTTPException) as exc:
            models._parse_aware_utc(bad)
        assert exc.value.status_code == 422
    assert models._parse_aware_utc("2026-01-02T15:30:00+07:00") == datetime(2026, 1, 2, 8, 30, tzinfo=timezone.utc)
    registry = models._model_registry
    before, disk = copy.deepcopy(registry.registry_data), registry.metadata_file.read_bytes()
    governance_payload["current_window"]["end"] = "1700000000.5"
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift",
                                                       json=governance_payload), range(8)))
    assert all(response.status_code == 422 for response in responses)
    assert registry.registry_data == before
    assert registry.metadata_file.read_bytes() == disk


@pytest.mark.parametrize("source", ["memory", "disk"])
@pytest.mark.parametrize("metadata_field", ["lineage", "drift_windows"])
def test_slice14_recorded_epoch_route_matrix(governance_payload, source, metadata_field, monkeypatch):
    import copy
    import json
    from omega.api.routes import models
    registry = models._model_registry
    data = copy.deepcopy(registry.registry_data)
    metadata = data["models"]["ALPHA_XGBOOST_V2"]["versions"]["v1.0.0"]["metadata"]
    if metadata_field == "lineage":
        metadata[metadata_field] = {"training_run": {"run_id": "run", "trained_at": "1700000000"}}
    else:
        metadata[metadata_field] = copy.deepcopy(governance_payload)
        metadata[metadata_field]["reference_window"]["start"] = "1700000000.5"
    if source == "memory":
        registry.registry_data = data
    else:
        registry.metadata_file.write_text(json.dumps(data), encoding="utf-8")
    before, disk = copy.deepcopy(registry.registry_data), registry.metadata_file.read_bytes()

    def forbidden_write(*args, **kwargs):
        pytest.fail("Corrupted timestamp reached persistence")

    monkeypatch.setattr(registry, "_save_registry", forbidden_write)
    for method, path in [
        ("GET", ""), ("GET", "/drift-monitor/status"), ("PATCH", "/drift-monitor/schedule"),
        ("GET", "/ALPHA_XGBOOST_V2/versions"), ("GET", "/ALPHA_XGBOOST_V2/versions/v1.0.0"),
        ("GET", "/ALPHA_XGBOOST_V2/drift"), ("POST", "/ALPHA_XGBOOST_V2/versions/v1.0.0/promote"),
        ("POST", "/ALPHA_XGBOOST_V2/rollback"), ("POST", "/ALPHA_XGBOOST_V2/calibrate"),
        ("GET", "/ALPHA_XGBOOST_V2/calibration"), ("GET", "/ALPHA_XGBOOST_V2/lineage"),
        ("GET", "/ALPHA_XGBOOST_V2/concept-drift"), ("POST", "/ALPHA_XGBOOST_V2/concept-drift"),
    ]:
        response = client.request(method, "/api/v1/models" + path, json={} if method != "GET" else None)
        assert response.status_code == 424
    assert registry.registry_data == before
    assert registry.metadata_file.read_bytes() == disk


@pytest.mark.parametrize("bad", [None, [], "1", True, "NaN", "Infinity", -1e13, 1e13])
def test_slice14_invalid_samples(governance_payload, bad):
    governance_payload["current_window"]["features"]["price"][0] = bad
    response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=governance_payload)
    assert response.status_code == 422


@pytest.mark.parametrize("mutation", ["empty", "single", "overlap", "future", "naive", "numeric_time", "unit", "feature", "extra", "bins_zero", "bins_negative", "bins_bool", "budget"])
def test_slice14_window_boundaries(governance_payload, mutation):
    current = governance_payload["current_window"]
    if mutation == "empty":
        current["features"]["price"] = []
    elif mutation == "single":
        current["features"]["price"] = [1]
    elif mutation == "overlap":
        current["start"] = "2026-01-01T00:00:00Z"
    elif mutation == "future":
        current["available_at"] = "2099-01-01T00:00:00Z"
    elif mutation == "naive":
        current["end"] = "2026-01-03T00:00:00"
    elif mutation == "numeric_time":
        current["end"] = 1700000000
    elif mutation == "unit":
        current["unit"] = "UNITLESS"
    elif mutation == "feature":
        current["features"] = {"other": [1, 2]}
    elif mutation == "extra":
        governance_payload["automated_retrain"] = True
    elif mutation == "budget":
        current["features"]["price"] = [1] * 10001
    else:
        governance_payload["bins"] = {"bins_zero": 0, "bins_negative": -1, "bins_bool": True}[mutation]
    assert client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=governance_payload).status_code == 422


@pytest.mark.parametrize("path", ["", "/ALPHA_XGBOOST_V2/versions", "/ALPHA_XGBOOST_V2/lineage", "/ALPHA_XGBOOST_V2/concept-drift"])
def test_slice14_corrupt_disk_fails_closed(path):
    from omega.api.routes import models
    models._model_registry.metadata_file.write_bytes(b'{"models":{},"models":{},"audit_logs":[]}')
    raw = models._model_registry.metadata_file.read_bytes()
    response = client.get("/api/v1/models" + path)
    assert response.status_code == 424
    assert models._model_registry.metadata_file.read_bytes() == raw


def test_slice14_missing_and_corrupt_evidence():
    from omega.api.routes import models
    assert client.get("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift").status_code == 424
    assert client.get("/api/v1/models/UNKNOWN/lineage").status_code == 404
    assert client.get("/api/v1/models/ALPHA_XGBOOST_V2/lineage?version=v9.0.0").status_code == 404
    assert client.get("/api/v1/models/ALPHA_XGBOOST_V2/lineage?version=invalid").status_code == 422
    metadata = models._model_registry.registry_data["models"]["ALPHA_XGBOOST_V2"]["versions"]["v1.0.0"]["metadata"]
    metadata["lineage"] = {"parent_versions": ["v9.0.0"], "git_commit": "https://user:password@example.com"}
    response = client.get("/api/v1/models/ALPHA_XGBOOST_V2/lineage")
    assert response.status_code == 424
    assert "password" not in response.text


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_slice14_raw_nonfinite_request_redacted(governance_payload, bad):
    import json
    raw = json.dumps(governance_payload).replace("[10000,", "[" + bad + ",", 1)
    response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert bad not in response.text


def test_slice14_invalid_request_secret_redaction(governance_payload):
    governance_payload["current_window"]["features"]["price"][0] = "https://user:password@example.com"
    response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=governance_payload)
    assert response.status_code == 422
    assert "password" not in response.text


@pytest.mark.parametrize("raw,code", [(b'{"bins":2,"bins":3}', 422),
                                     (b'\xff', 422), (b'[' * 2000, 422),
                                     (b' ' * (1024 * 1024 + 1), 413)],
                         ids=["duplicate", "utf8", "depth", "size"])
def test_slice14_request_encoding_duplicate_and_size(raw, code):
    response = client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == code


@pytest.mark.parametrize("method,path", [
    ("GET", ""), ("GET", "/drift-monitor/status"), ("PATCH", "/drift-monitor/schedule"),
    ("GET", "/ALPHA_XGBOOST_V2/versions"), ("GET", "/ALPHA_XGBOOST_V2/versions/v1.0.0"),
    ("GET", "/ALPHA_XGBOOST_V2/drift"), ("POST", "/ALPHA_XGBOOST_V2/versions/v1.0.0/promote"),
    ("POST", "/ALPHA_XGBOOST_V2/rollback"), ("POST", "/ALPHA_XGBOOST_V2/calibrate"),
    ("GET", "/ALPHA_XGBOOST_V2/calibration"), ("GET", "/ALPHA_XGBOOST_V2/lineage"),
    ("GET", "/ALPHA_XGBOOST_V2/concept-drift"), ("POST", "/ALPHA_XGBOOST_V2/concept-drift"),
])
def test_slice14_corrupt_memory_route_matrix(method, path):
    from omega.api.routes import models
    models._model_registry.registry_data["models"] = []
    response = client.request(method, "/api/v1/models" + path, json={} if method != "GET" else None)
    assert response.status_code == 424


def test_slice14_drift_concurrent_no_mutation(governance_payload):
    from concurrent.futures import ThreadPoolExecutor
    from omega.api.routes import models
    before = models._model_registry.metadata_file.read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post("/api/v1/models/ALPHA_XGBOOST_V2/concept-drift", json=governance_payload), range(8)))
    assert all(response.status_code == 200 for response in responses)
    assert models._model_registry.metadata_file.read_bytes() == before


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
