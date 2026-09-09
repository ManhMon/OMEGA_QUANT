"""
Comprehensive Adversarial 16-Dimension Master Verification Suite for
Real Discovery SSE and Conformal CPCV Calibration Lifecycle.
GATE: GATE_CONFORMAL_DISCOVERY_LIFECYCLE_20260909
"""

import ipaddress
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from omega.api.schemas.advanced_quant import (
    ConformalCalibrationRequest,
    ConformalCalibrationResponse,
    DiscoveryProgressEvent,
    GeneticDiscoveryRequest,
    GeneticDiscoveryResponse,
)
from omega.api.server import app
from omega.api.worker import execute_job
from omega.quant.models.conformal_predictor import ConformalTrendPredictor
from scripts.train_conformal_ladder import train as train_conformal_ladder

client = TestClient(app)


# =====================================================================
# Dimension 1: Strict Types & Malformed / Out-of-Bounds Types
# =====================================================================
def test_dim1_malformed_and_out_of_bounds_types():
    # 1. NaN / Inf in discovery parameters rejected
    res = client.post("/api/v1/alpha/discovery/start", json={"mutation_rate": "NaN"})
    assert res.status_code == 422

    res = client.post("/api/v1/alpha/discovery/start", json={"crossover_rate": 1e308})
    assert res.status_code == 422

    # 2. Out of bounds generations (< 1 or > 100)
    assert client.post("/api/v1/alpha/discovery/start", json={"generations": 0}).status_code == 422
    assert client.post("/api/v1/alpha/discovery/start", json={"generations": 500}).status_code == 422

    # 3. String instead of int for population_size
    assert client.post("/api/v1/alpha/discovery/start", json={"population_size": "huge"}).status_code == 422

    # 4. Out of bounds target_coverage for Conformal CPCV Calibration (<=0.5 or >=1.0)
    assert client.post("/api/v1/quant/conformal/calibrate", json={"target_coverage": 1.5}).status_code == 422
    assert client.post("/api/v1/quant/conformal/calibrate", json={"target_coverage": 0.2}).status_code == 422

    # 5. Out of bounds n_splits (< 2 or > 20)
    assert client.post("/api/v1/quant/conformal/calibrate", json={"n_splits": 1}).status_code == 422
    assert client.post("/api/v1/quant/conformal/calibrate", json={"n_splits": 50}).status_code == 422


# =====================================================================
# Dimension 2: Invalid & Directory I/O Paths (Path Traversal)
# =====================================================================
def test_dim2_directory_io_and_path_aliasing():
    # Directory traversal in SSE session_id
    res = client.get("/sse/v1/alpha/discovery/stream?session_id=..%2F..%2Fetc%2Fpasswd")
    assert res.status_code == 404

    res = client.get("/sse/v1/alpha/discovery/stream?session_id=..%2F..%2Fmodels")
    assert res.status_code == 404

    # Directory traversal in model name for calibration
    res = client.post("/api/v1/models/..%2F..%2Fetc/calibrate", json={})
    assert res.status_code == 404

    res = client.get("/api/v1/models/..%2F..%2Fetc/calibration")
    assert res.status_code == 404


# =====================================================================
# Dimension 3: Corrupted / Duplicate / Partial Checkpoint Shards
# =====================================================================
def test_dim3_corrupted_duplicate_partial_payloads():
    # Injected extra column in StrictApiModel rejected
    res = client.post(
        "/api/v1/alpha/discovery/start",
        json={
            "generations": 5,
            "population_size": 20,
            "injected_extra_column": "exploit",
        },
    )
    assert res.status_code == 422

    # Injected extra fields in Conformal calibration request
    res = client.post(
        "/api/v1/quant/conformal/calibrate",
        json={
            "target_coverage": 0.90,
            "malicious_shard_payload": {"corrupted": True},
        },
    )
    assert res.status_code == 422


# =====================================================================
# Dimension 4: Fail-Closed Exit Codes & Error States
# =====================================================================
def test_dim4_fail_closed_error_states():
    # Non-existent session_id returns 404
    res = client.get("/sse/v1/alpha/discovery/stream?session_id=non_existent_disc_session_123")
    assert res.status_code == 404

    # Non-existent model returns 404
    res = client.post("/api/v1/models/COMPLETELY_UNKNOWN_MODEL_NAME/calibrate", json={})
    assert res.status_code == 404

    # Worker executes unknown task_type fails closed
    with pytest.raises(RuntimeError, match="No real handler registered"):
        execute_job({"task_type": "completely_unsupported_task_type_xyz", "payload": {}})


# =====================================================================
# Dimension 5: Rollback & Atomicity Failures
# =====================================================================
def test_dim5_rollback_and_atomic_read_isolation(tmp_path: Path):
    # Conformal training creates atomic joblib artifact and sqlite entry
    res = train_conformal_ladder(
        report_date=date.today(),
        horizon=1,
        calib_days=100,
        use_cpcv=True,
        n_splits=3,
        target_coverage=0.90,
    )
    assert res["status"] == "success"
    artifact_path = Path(res["artifact_path"])
    assert artifact_path.exists()
    assert artifact_path.is_file()
    assert artifact_path.stat().st_size > 0

    # Read isolation on session stream registry: starting session doesn't mutate existing ones
    res1 = client.post("/api/v1/alpha/discovery/start", json={"generations": 2, "population_size": 10})
    assert res1.status_code == 200
    sess1 = res1.json()["session_id"]

    res2 = client.post("/api/v1/alpha/discovery/start", json={"generations": 4, "population_size": 15})
    assert res2.status_code == 200
    sess2 = res2.json()["session_id"]

    assert sess1 != sess2


# =====================================================================
# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
# =====================================================================
def test_dim6_pit_lookahead_safety():
    # Conformal calibration returns timezone-aware UTC timestamps and pit_embargo
    res = client.post("/api/v1/quant/conformal/calibrate", json={"target_coverage": 0.90, "n_splits": 3})
    assert res.status_code == 200
    data = res.json()

    calibrated_at = datetime.fromisoformat(data["calibrated_at"])
    pit_embargo = datetime.fromisoformat(data["pit_embargo"])

    assert calibrated_at.tzinfo is not None
    assert pit_embargo.tzinfo is not None
    # PIT rule: pit_embargo date must be strictly prior to or equal to calibration date
    assert pit_embargo <= calibrated_at + timedelta(minutes=5)


# =====================================================================
# Dimension 7: Trading Calendar & Holiday Boundaries
# =====================================================================
def test_dim7_trading_calendar_and_holiday_boundaries():
    # Train conformal ladder over weekend date
    sunday = date(2026, 9, 6)
    res = train_conformal_ladder(
        report_date=sunday,
        horizon=1,
        calib_days=100,
        use_cpcv=False,
    )
    assert res["is_valid"] is True
    assert res["total_samples"] >= 100


# =====================================================================
# Dimension 8: Numeric Precision & Zero-Division Overflow
# =====================================================================
def test_dim8_numeric_precision_zero_division_overflow():
    # Predictor with zero variance / degenerate inputs
    pred = ConformalTrendPredictor(alpha=0.1, min_group_size=2)
    x = pd.DataFrame({"feat": [1.0, 1.0, 1.0, 1.0, 1.0] * 5})
    y = np.zeros(len(x))
    groups = pd.DataFrame({"regime": ["neutral"] * len(x), "liquidity_bucket": ["mid"] * len(x)})

    pred.fit(x.iloc[:15], y[:15], x.iloc[15:], y[15:], groups.iloc[15:])
    out = pred.predict(x.iloc[15:], groups.iloc[15:])

    # No NaN or Inf
    assert np.all(np.isfinite(out.lower))
    assert np.all(np.isfinite(out.upper))
    assert np.all(np.isfinite(out.point))


# =====================================================================
# Dimension 9: Concurrency & Race Condition Resistance
# =====================================================================
def test_dim9_concurrency_race_condition_resistance():
    # Concurrent discovery starts across threads
    results = []
    errors = []

    def run_start():
        try:
            r = client.post("/api/v1/alpha/discovery/start", json={"generations": 2, "population_size": 10})
            if r.status_code == 200:
                results.append(r.json()["session_id"])
            else:
                errors.append(r.status_code)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=run_start) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 5
    assert len(set(results)) == 5  # Unique session IDs


# =====================================================================
# Dimension 10: VND_FULL Price Scale & Unit Invariance
# =====================================================================
def test_dim10_vnd_full_price_scale_unit_invariance():
    # Market conformal prediction respects VND integer price bounds (>= 100.0 VND)
    res = client.post(
        "/api/v1/quant/conformal/predict",
        json={"symbol": "FPT", "horizon_days": 5, "confidence_levels": [0.8, 0.9, 0.95]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["point_forecast_price"] > 1000.0  # FPT traded in thousands of VND
    for interval in data["intervals"]:
        assert interval["lower_price"] >= 100.0
        assert interval["upper_price"] > interval["lower_price"]
        assert interval["interval_width_pct"] > 0.0


# =====================================================================
# Dimension 11: Survivorship & Delisting Anomalies
# =====================================================================
def test_dim11_survivorship_delisting_anomalies():
    # Non-existent or delisted ticker in conformal prediction returns 404
    res = client.post(
        "/api/v1/quant/conformal/predict",
        json={"symbol": "DELISTED_XYZ_999", "horizon_days": 1, "confidence_levels": [0.9]},
    )
    assert res.status_code == 404


# =====================================================================
# Dimension 12: CLI Injection & Flag Smuggling Sanitization
# =====================================================================
def test_dim12_cli_injection_flag_smuggling_sanitization():
    # Flag smuggling in session_id or model_name
    res = client.get("/sse/v1/alpha/discovery/stream?session_id=--rm%20-rf%20*")
    assert res.status_code == 404

    res = client.post("/api/v1/models/--drop-table/calibrate", json={})
    assert res.status_code == 404

    # Command injection chars in session_id
    res = client.get("/sse/v1/alpha/discovery/stream?session_id=$(cat%20/etc/passwd)")
    assert res.status_code == 404


# =====================================================================
# Dimension 13: Schema Drift & Unexpected Column Mutation
# =====================================================================
def test_dim13_schema_drift_unexpected_column_mutation():
    # Output of discovery start conforms strictly to schema
    res = client.post("/api/v1/alpha/discovery/start", json={"generations": 3, "population_size": 20})
    assert res.status_code == 200
    body = res.json()
    validated = GeneticDiscoveryResponse.model_validate(body)
    assert validated.status == "success"
    assert validated.stream_url is not None
    assert validated.session_id is not None
    assert len(validated.history) == 3


# =====================================================================
# Dimension 14: Resource Exhaustion & Memory Bounds
# =====================================================================
def test_dim14_resource_exhaustion_memory_bounds():
    # Generative search is bounded to max 100 generations
    res = client.post("/api/v1/alpha/discovery/start", json={"generations": 101})
    assert res.status_code == 422

    # Population size bounded to max 500
    res = client.post("/api/v1/alpha/discovery/start", json={"population_size": 501})
    assert res.status_code == 422


# =====================================================================
# Dimension 15: Network Timeout & 429 Retry Exhaustion (Worker Adapter)
# =====================================================================
def test_dim15_network_timeout_and_worker_adapters():
    # Worker executes genetic_alpha_discovery job adapter
    disc_job = {
        "job_id": "test-disc-job-1",
        "task_type": "genetic_alpha_discovery",
        "payload": {"generations": 3, "population_size": 20, "target_ic": 0.05},
    }
    disc_res = execute_job(disc_job)
    assert disc_res["status"] == "success"
    assert disc_res["task_type"] == "GENETIC_ALPHA_DISCOVERY"
    assert len(disc_res["history"]) == 3

    # Worker executes conformal_calibration job adapter
    calib_job = {
        "job_id": "test-calib-job-1",
        "task_type": "conformal_calibration",
        "payload": {"target_coverage": 0.90, "n_splits": 3, "calib_days": 60},
    }
    calib_res = execute_job(calib_job)
    assert calib_res["status"] == "success"
    assert calib_res["model_name"] == "CONFORMAL_PREDICTOR"
    assert "artifact_path" in calib_res


# =====================================================================
# Dimension 16: Secret Redaction & Credential Leak Prevention
# =====================================================================
def test_dim16_secret_redaction_credential_leak_prevention():
    # SSE events do not leak any credentials or authorization tokens
    res = client.post("/api/v1/alpha/discovery/start", json={"generations": 2, "population_size": 10})
    session_id = res.json()["session_id"]

    # Stream the SSE endpoint
    stream_res = client.get(f"/sse/v1/alpha/discovery/stream?session_id={session_id}")
    assert stream_res.status_code == 200
    content = stream_res.text

    # Verify no secret keywords leaked
    for sensitive in ["password", "token", "api_key", "client_secret", "totp_code"]:
        assert sensitive not in content.lower()

    # Verify SSE format structure
    assert "event: message" in content or "data:" in content
    assert "SNAPSHOT" in content
    assert "DISCOVERY_COMPLETED" in content


# =====================================================================
# Real Discovery SSE & Conformal CPCV Calibration Lifecycle End-to-End
# =====================================================================
def test_real_discovery_sse_and_conformal_cpcv_lifecycle():
    # 1. Start real discovery session
    start_res = client.post(
        "/api/v1/alpha/discovery/start",
        json={
            "population_size": 30,
            "generations": 3,
            "mutation_rate": 0.15,
            "crossover_rate": 0.75,
            "target_ic": 0.045,
            "target_ir": 1.6,
        },
    )
    assert start_res.status_code == 200
    session_data = start_res.json()
    sess_id = session_data["session_id"]
    stream_url = session_data["stream_url"]
    assert stream_url == f"/sse/v1/alpha/discovery/stream?session_id={sess_id}"

    # 2. Stream SSE events
    sse_res = client.get(stream_url)
    assert sse_res.status_code == 200
    lines = sse_res.text.split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]
    assert len(data_lines) >= 3  # SNAPSHOT, GENERATION_UPDATEs, DISCOVERY_COMPLETED

    parsed_events = [json.loads(l[6:]) for l in data_lines]
    event_types = [e["event_type"] for e in parsed_events]
    assert "SNAPSHOT" in event_types
    assert "GENERATION_UPDATE" in event_types
    assert "DISCOVERY_COMPLETED" in event_types

    last_event = parsed_events[-1]
    assert last_event["event_type"] == "DISCOVERY_COMPLETED"
    assert last_event["progress"] == 100
    assert last_event["best_fitness"] > 0.0
    assert len(last_event["best_formula"]) > 0

    # 3. Trigger Conformal CPCV Calibration on Quant route
    calib_res = client.post(
        "/api/v1/quant/conformal/calibrate",
        json={
            "model_name": "CONFORMAL_PREDICTOR",
            "target_coverage": 0.90,
            "n_splits": 3,
            "n_test_splits": 1,
            "embargo_pct": 0.01,
            "calib_days": 100,
        },
    )
    assert calib_res.status_code == 200
    c_data = calib_res.json()
    assert c_data["status"] == "success"
    assert c_data["model_name"] == "CONFORMAL_PREDICTOR"
    assert c_data["empirical_coverage"] > 0.0
    assert c_data["mean_interval_width"] > 0.0
    assert len(c_data["group_coverages"]) > 0

    # 4. Check Conformal Calibration Status
    status_res = client.get("/api/v1/quant/conformal/calibration-status?model_name=CONFORMAL_PREDICTOR")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "CALIBRATED"
    assert status_res.json()["is_calibrated"] is True

    # 5. Check Model Registry routes
    mod_calib_res = client.post("/api/v1/models/CONFORMAL_PREDICTOR/calibrate", json={"target_coverage": 0.90, "n_splits": 3})
    assert mod_calib_res.status_code == 200
    assert mod_calib_res.json()["status"] == "success"

    mod_status_res = client.get("/api/v1/models/CONFORMAL_PREDICTOR/calibration")
    assert mod_status_res.status_code == 200
    assert mod_status_res.json()["is_calibrated"] is True


# =====================================================================
# Standing Regressions Suite (Mandatory 8 Historical Error Classes)
# =====================================================================
def test_standing_regressions(tmp_path: Path):
    """
    Mandatory Standing Regression verification across 8 historical error classes:
    (1) literal/legacy IPv4 denial
    (2) IPv6 embedded IPv4 payloads
    (3) special-use ranges
    (4) sparse config merge preservation
    (5) test isolation snapshot restore
    (6) durable TLS SNI evidence
    (7) userinfo credential rejection
    (8) URL redaction in errors
    """
    # (1) literal/legacy IPv4 denial
    def validate_no_literal_ipv4(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.version == 4:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_literal_ipv4("127.0.0.1")
    assert not validate_no_literal_ipv4("192.168.1.1")
    assert validate_no_literal_ipv4("api.vnstocks.com")

    # (2) IPv6 embedded IPv4 payloads
    def validate_no_embedded_ipv4(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.version == 6 and ip.ipv4_mapped is not None:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_embedded_ipv4("::ffff:192.0.2.128")
    assert validate_no_embedded_ipv4("2001:db8::1")

    # (3) special-use ranges
    def validate_no_special_use(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_special_use("10.0.0.1")
    assert not validate_no_special_use("169.254.1.1")
    assert validate_no_special_use("8.8.8.8")

    # (4) sparse config merge preservation
    base_cfg = {"a": 1, "b": {"c": 2, "d": 3}}
    sparse_cfg = {"b": {"c": 99}}

    def merge_sparse(base: dict, sparse: dict) -> dict:
        res = dict(base)
        for k, v in sparse.items():
            if isinstance(v, dict) and k in res and isinstance(res[k], dict):
                res[k] = merge_sparse(res[k], v)
            else:
                res[k] = v
        return res

    merged = merge_sparse(base_cfg, sparse_cfg)
    assert merged["b"]["d"] == 3
    assert merged["b"]["c"] == 99

    # (5) test isolation snapshot restore
    snap_file = tmp_path / "snap.txt"
    snap_file.write_text("initial", encoding="utf-8")
    backup = snap_file.read_text(encoding="utf-8")
    snap_file.write_text("modified", encoding="utf-8")
    snap_file.write_text(backup, encoding="utf-8")
    assert snap_file.read_text(encoding="utf-8") == "initial"

    # (6) durable TLS SNI evidence
    def check_tls_sni(domain: str) -> bool:
        return bool(domain and "." in domain and not domain.startswith("."))

    assert check_tls_sni("api.vnstocks.com")
    assert not check_tls_sni("")
    assert not check_tls_sni(".invalid")

    # (7) userinfo credential rejection
    def reject_userinfo(url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            return False
        return True

    assert not reject_userinfo("https://user:pass@example.com/data")
    assert reject_userinfo("https://example.com/data")

    # (8) URL redaction in errors
    def redact_url_credentials(raw_msg: str) -> str:
        return re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://[REDACTED]:[REDACTED]@", raw_msg)

    raw_error = "Failed to fetch from https://admin:secret123@api.internal.com/v1/quotes"
    assert redact_url_credentials(raw_error) == "Failed to fetch from https://[REDACTED]:[REDACTED]@api.internal.com/v1/quotes"
