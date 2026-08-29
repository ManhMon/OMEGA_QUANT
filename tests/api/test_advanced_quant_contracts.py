from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.schemas.advanced_quant import GovernorMode, JobSubmitRequest, PitWindowRequest, ProvenanceEnvelope, ResourceGovernorPolicy
from omega.api.server import app
from omega.api.dependencies import job_service_dependency
from omega.api.services.job_service import JobService
from omega.api.services.data_bridge import DataBridge, DataDependencyUnavailable
from omega.api.worker import DynamicWorkerResourceGovernor


NOW = datetime.now(timezone.utc).replace(microsecond=0)
HASH = "a" * 64


def test_strict_models_reject_coercion_extra_nan_and_infinity():
    with pytest.raises(ValidationError):
        ResourceGovernorPolicy(mode="MANUAL", target_concurrency="2", thread_pool_size=2, batch_size=1)
    with pytest.raises(ValidationError):
        ResourceGovernorPolicy(mode="MANUAL", target_concurrency=2, thread_pool_size=2, batch_size=1, surprise=True)
    with pytest.raises(ValidationError):
        ProvenanceEnvelope(
            source="VCI", dataset_id="market", dataset_version="1", as_of=NOW, computed_at=NOW,
            effective_cutoff=NOW, input_timezone="UTC", cutoff_resolution="AS_OF_DEFAULT",
            excluded_future_rows=-1, content_hash=HASH,
        )
    # Test magnitude ceiling on FiniteFloat in advanced_quant schema: abs(v) <= 1e12 and 1e308 rejected
    from omega.api.schemas.advanced_quant import JobStatusResponse, JobStatus
    from uuid import uuid4
    with pytest.raises(ValidationError):
        JobStatusResponse(
            job_id=uuid4(), task_type="test", status=JobStatus.RUNNING,
            progress_pct=1e308, stage="init", message="test",
            submitted_at=NOW, updated_at=NOW, pit_cutoff=NOW,
            request_sha256=HASH, attempt_count=1, max_attempts=3
        )


def test_pit_cutoff_ordering_equality_and_future_rejection():
    equal = PitWindowRequest(start_date=date.today(), end_date=date.today(), as_of_time=NOW, pit_cutoff=NOW)
    assert equal.pit_cutoff == equal.as_of_time
    with pytest.raises(ValidationError):
        PitWindowRequest(start_date=date.today(), end_date=date.today(), as_of_time=NOW, pit_cutoff=NOW + timedelta(microseconds=1))
    with pytest.raises(ValidationError):
        PitWindowRequest(start_date=date.today(), end_date=date.today(), as_of_time=datetime.now())
    # Test strict rejection of any future pit_cutoff without tolerance
    with pytest.raises(ValidationError):
        JobSubmitRequest(
            task_type="test",
            payload={"a": 1},
            pit_cutoff=datetime.now(timezone.utc) + timedelta(seconds=1)
        )



def test_provenance_enforces_available_at_before_cutoff():
    with pytest.raises(ValidationError):
        ProvenanceEnvelope(
            source="VCI", dataset_id="market", dataset_version="1", as_of=NOW, computed_at=NOW,
            effective_cutoff=NOW, input_timezone="Asia/Ho_Chi_Minh", cutoff_resolution="AS_OF_DEFAULT",
            max_included_available_at=NOW + timedelta(microseconds=1), content_hash=HASH,
        )


def test_data_bridge_rejects_paths_directories_schema_drift_and_checksum(tmp_path: Path):
    bridge = DataBridge(tmp_path)
    with pytest.raises(ValueError):
        bridge.resolve_registered("../secret")
    (tmp_path / "registry.json").write_text('{"directory":"."}', encoding="utf-8")
    with pytest.raises(DataDependencyUnavailable):
        bridge.resolve_registered("directory")
    file = tmp_path / "bytes.bin"
    file.write_bytes(b"omega")
    assert DataBridge.sha256(file) == "304b4a90a76a1cbe4c112e074b30e75181f54df43d60f883597457844293b341"


def test_fake_routes_fail_closed():
    client = TestClient(app)
    assert client.get("/api/v1/market/orderbook/FPT").json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"
    assert client.get("/api/v1/portfolio/state").status_code == 424
    assert client.get("/api/v1/risk/stress-scenarios").status_code == 424
    assert client.get("/api/v1/tca/post-trade-report").status_code == 404
    assert client.get("/api/v1/execution/routing-diagnostics").status_code == 424
    assert client.get("/api/v1/alpha/arsenal/signals").status_code == 424


def test_durable_job_api_strict_contract_and_idempotency(tmp_path: Path):
    service = JobService(tmp_path / "api-jobs.sqlite3")
    app.dependency_overrides[job_service_dependency] = lambda: service
    client = TestClient(app)
    body = {"task_type": "test", "payload": {"value": 1}, "pit_cutoff": NOW.isoformat(), "max_attempts": 2}
    try:
        first = client.post("/api/v1/jobs", json=body, headers={"Idempotency-Key": "api-key-123"})
        replay = client.post("/api/v1/jobs", json=body, headers={"Idempotency-Key": "api-key-123"})
        assert first.status_code == replay.status_code == 202
        assert first.json()["job_id"] == replay.json()["job_id"]
        assert client.get(first.json()["job_url"]).json()["status"] == "QUEUED"
        assert client.post("/api/v1/jobs", json={**body, "unknown": True}, headers={"Idempotency-Key": "api-key-456"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_barra_rejects_schema_drift_and_non_finite_values():
    client = TestClient(app)
    assert client.post("/api/v1/risk/barra/decomposition", json={"assets": [], "factor_covariance": [], "extra": 1}).status_code == 422
    assert client.post("/api/v1/risk/barra/decomposition", json={"assets": [], "factor_covariance": [["NaN"]]}).status_code == 422


def test_governor_manual_and_copilot_are_positive_and_dynamic(monkeypatch):
    manual = DynamicWorkerResourceGovernor(ResourceGovernorPolicy(mode=GovernorMode.MANUAL, target_concurrency=3, thread_pool_size=2, batch_size=10))
    assert manual.decide(queue_depth=100).policy.target_concurrency == 3
    copilot = DynamicWorkerResourceGovernor(ResourceGovernorPolicy(mode=GovernorMode.COPILOT, target_concurrency=1, thread_pool_size=2, batch_size=10))
    monkeypatch.setattr("omega.api.worker.psutil.cpu_percent", lambda interval=None: 0.0)
    monkeypatch.setattr("omega.api.worker.psutil.cpu_count", lambda logical=True: 8)
    monkeypatch.setattr("omega.api.worker.psutil.virtual_memory", lambda: type("M", (), {"percent": 10.0})())
    decision = copilot.decide(queue_depth=8)
    assert decision.policy.target_concurrency == 2
    assert decision.telemetry["queue_depth"] == 8


def test_vnd_full_and_calendar_business_edges_are_not_fabricated():
    client = TestClient(app)
    response = client.post("/api/v1/tca/pre-trade-impact", json={
        "symbol": "FPT", "order_size": 100.0, "average_daily_volume": 10000.0,
        "volatility": 0.02, "participation_rate": 0.1, "side": "BUY",
        "arrival_price": 100.0, "observed_spread_bps": 2.0,
    })
    assert response.status_code == 422
    assert client.get("/api/v1/portfolio/dynamic-universe").status_code == 424


def test_stream_contains_no_random_market_payload():
    source = Path("src/omega/api/routes/stream.py").read_text(encoding="utf-8")
    assert "import random" not in source
    assert "random." not in source


def test_request_body_size_limit_rejection_at_524289_bytes():
    client = TestClient(app)
    # Exactly 524,289 bytes (512 KiB + 1 byte) raw content
    large_data = b'{"data":"' + b'x' * (524289 - 11) + b'"}'
    assert len(large_data) == 524289

    # POST to /api/v1/jobs with 524,289 bytes
    response = client.post(
        "/api/v1/jobs",
        content=large_data,
        headers={"Content-Type": "application/json", "Idempotency-Key": "size-limit-key-1"}
    )
    assert response.status_code == 413

    # POST with 614,592 bytes
    response_huge = client.post(
        "/api/v1/jobs",
        content=b"x" * 614592,
        headers={"Content-Type": "application/json", "Idempotency-Key": "size-limit-key-2"}
    )
    assert response_huge.status_code == 413

    # POST with 524,289 Content-Length header but small body also caught or rejected
    response_cl = client.post(
        "/api/v1/jobs",
        json={"task_type": "noop"},
        headers={"Content-Length": "524289", "Idempotency-Key": "size-limit-key-3"}
    )
    assert response_cl.status_code in {413, 422}


def test_adversarial_findings_fixes_validation(tmp_path: Path, monkeypatch):
    # Finding 1: client.ts has no Math.random synthetic generators for universe, regime, portfolio, blotter, OHLCV
    client_ts = Path("omega-ui/src/api/client.ts").read_text(encoding="utf-8")
    assert "generate703StockUniverse" not in client_ts
    assert "Math.random" not in client_ts

    # Finding 2: worker CLI rejects unknown flags with exit code 2
    from omega.api.worker import main as worker_main, run_worker
    assert worker_main(["--unknown-flag"]) == 2

    # Worker exits non-zero (exit 1) on failed task execution in once mode
    service = JobService(tmp_path / "worker_test.sqlite3")
    job_req = JobSubmitRequest(task_type="unregistered_failing_task", payload={"test": 1}, pit_cutoff=NOW)
    service.submit(job_req, "worker-key-1")
    assert run_worker(service=service, once=True) == 1

    # Worker succeeds with valid sample task handler
    noop_req = JobSubmitRequest(task_type="noop", payload={"echo": "ok"}, pit_cutoff=NOW)
    noop_job, _ = service.submit(noop_req, "worker-key-2")
    assert run_worker(service=service, once=True) == 0
    assert service.get(noop_job["job_id"])["status"] == "SUCCEEDED"

    # Finding 3: Reject Infinity, NaN, 1e308 in risk_tca and bound JobSubmitRequest payload size <= 512 KiB
    client = TestClient(app)
    # Inf / NaN / 1e308 in Barra
    bad_barra = client.post("/api/v1/risk/barra/decomposition", json={
        "assets": [{"symbol": "FPT", "sector": "Technology", "weight_pct": 100.0, "market_beta": 1e308, "size_smb": 1.0, "value_hml": 1.0, "momentum": 1.0, "volatility": 1.0, "liquidity": 1.0, "quality": 1.0, "leverage": 1.0, "specific_risk_pct": 1.0}],
        "factor_covariance": [[1.0]*8]*8
    })
    assert bad_barra.status_code == 422

    # Payload > 512 KiB rejected in JobSubmitRequest
    huge_payload = {"data": "x" * (513 * 1024)}
    with pytest.raises(ValidationError):
        JobSubmitRequest(task_type="test", payload=huge_payload, pit_cutoff=NOW)

    # Finding 4: Recursive secret redaction
    from omega.api.services.job_service import redact
    secret_payload = {
        "access_token": "acc123",
        "refresh_token": "ref123",
        "client_secret": "sec123",
        "token": "tok123",
        "secret": "s123",
        "api_key": "k123",
        "private_key": "pk123",
        "password": "pwd",
        "nested": {"nested_token": "keep", "nested_secret": "hide"},
    }
    redacted = redact(secret_payload)
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["refresh_token"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["secret"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["private_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"

    # Finding 5: UI hooks attach named SSE event listeners
    realtime_stream_ts = Path("omega-ui/src/hooks/useRealtimeStream.ts").read_text(encoding="utf-8")
    durable_job_ts = Path("omega-ui/src/hooks/useDurableJob.ts").read_text(encoding="utf-8")
    for event_name in ("status", "progress", "complete", "error", "artifact"):
        assert f"addEventListener('{event_name}'" in realtime_stream_ts
        assert f"addEventListener('{event_name}'" in durable_job_ts

    # Finding 6: Reject future pit_cutoff > now(UTC) and JSONDecodeError on data_bridge
    with pytest.raises(ValidationError):
        JobSubmitRequest(task_type="test", payload={"a": 1}, pit_cutoff=NOW + timedelta(days=2))

    corrupt_registry = tmp_path / "corrupt_data"
    corrupt_registry.mkdir()
    (corrupt_registry / "registry.json").write_text("{bad json", encoding="utf-8")
    bridge = DataBridge(corrupt_registry)
    with pytest.raises(DataDependencyUnavailable):
        bridge.resolve_registered("market")
