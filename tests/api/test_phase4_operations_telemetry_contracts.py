"""Operations System Telemetry & Circuit Breaker contracts (Slice 18)."""
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.server import app
from omega.api.routes import operations
from omega.core.sre.kill_switch import KillSwitch
from omega.risk.circuit_breaker import CircuitBreaker


@pytest.fixture
def switch(monkeypatch, tmp_path):
    isolated = KillSwitch(dump_dir=str(tmp_path / "kill_switch"))
    monkeypatch.setattr(operations.circuit_breaker, "get_kill_switch", lambda: isolated)
    return isolated


@pytest.fixture
def client(monkeypatch, switch):
    monkeypatch.setattr(operations.psutil, "cpu_percent", lambda interval: 25.0)
    monkeypatch.setattr(operations.psutil, "virtual_memory", lambda: SimpleNamespace(used=2**30, percent=50.0))
    monkeypatch.setattr(operations.psutil, "disk_io_counters", lambda: SimpleNamespace(read_bytes=100, write_bytes=200))
    monkeypatch.setattr(operations, "_read_ipc_queue_depth", lambda: 3)
    with TestClient(app) as connection:
        yield connection


def assert_provenance(data):
    observed = datetime.fromisoformat(data["as_of"].replace("Z", "+00:00"))
    available = datetime.fromisoformat(data["available_at"].replace("Z", "+00:00"))
    assert observed.tzinfo is not None
    assert observed <= available <= datetime.now(timezone.utc)
    payload = {**data, "provenance": {key: value for key, value in data["provenance"].items() if key != "sha256"}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert data["provenance"]["sha256"] == hashlib.sha256(encoded.encode()).hexdigest()
    assert data["provenance"]["observation_mode"] == "CURRENT_ONLY"
    assert data["provenance"]["is_synthetic"] is False
    assert data["schema_version"] == "operations/v1"


def test_system_telemetry_schema_and_bounds(client):
    response = client.get("/api/v1/operations/system-telemetry")
    assert response.status_code == 200
    data = response.json()
    assert data["cpu_usage_pct"] == 25.0
    assert data["memory_usage_mb"] == 1024.0
    assert data["memory_usage_pct"] == 50.0
    assert data["memory_unit"] == "MiB"
    assert data["io_read_bytes"] == 100
    assert data["io_write_bytes"] == 200
    assert data["io_unit"] == "bytes_cumulative_since_boot"
    assert data["ipc_queue_depth"] == 3
    assert data["ipc_unit"] == "queued_jobs"
    assert data["gpu_telemetry"] is None
    assert_provenance(data)


def test_circuit_breaker_status_authoritative(client, switch):
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "NORMAL"
    assert data["circuit_broken"] is False
    assert data["reasons"] == []
    assert data["triggered_at"] is None
    # There is no verified portfolio/config binding to the global kill switch.
    assert data["daily_pnl"] is None
    assert data["drawdown_pct"] is None
    assert data["max_drawdown_limit"] is None
    assert not switch.is_activated
    assert_provenance(data)


def test_risk_trigger_reason_read_only(client, switch, monkeypatch):
    import pandas as pd
    from omega.core.sre import kill_switch
    monkeypatch.setattr(kill_switch, "get_kill_switch", lambda: switch)
    breaker = CircuitBreaker()
    halted, reason = breaker.check_asset_circuit_breaker(pd.Series([100.0, 80.0]), "TEST")
    assert halted
    before = (switch._activation_id, switch._activation_time, switch._activation_reason)
    for _ in range(2):
        response = client.get("/api/v1/operations/circuit-breaker-status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "TRIGGERED"
        assert data["circuit_broken"] is True
        assert data["reasons"] == ["Risk circuit breaker activated"]
        assert switch._activation_reason == reason
        assert datetime.fromisoformat(data["triggered_at"].replace("Z", "+00:00")) == before[1]
        assert_provenance(data)
    assert before == (switch._activation_id, switch._activation_time, switch._activation_reason)


@pytest.mark.parametrize("value", [None, "", "25", [], True, float("nan"), float("inf"), -float("inf"), -1.0, 100.01, 1e13])
def test_invalid_cpu_fails_closed(client, monkeypatch, value):
    monkeypatch.setattr(operations.psutil, "cpu_percent", lambda interval: value)
    response = client.get("/api/v1/operations/system-telemetry")
    # Explicit None means unavailable, not an invalid numeric reading.
    assert response.status_code == (200 if value is None else 424)
    if value is None:
        assert response.json()["cpu_usage_pct"] is None
    else:
        assert response.json() == {"detail": "System telemetry observation unavailable"}


@pytest.mark.parametrize("field,value", [
    ("memory_usage_mb", -1.0), ("memory_usage_mb", 1e13),
    ("memory_usage_pct", 101.0), ("memory_usage_pct", float("nan")),
    ("io_read_bytes", -1), ("io_write_bytes", 2**53), ("io_write_bytes", 1.5),
    ("ipc_queue_depth", -1), ("ipc_queue_depth", 1_000_000_001),
    ("ipc_queue_depth", True), ("ipc_queue_depth", "3"), ("ipc_queue_depth", []),
    ("gpu_telemetry", {"usage_pct": 101.0, "memory_usage_mb": 0.0}),
    ("gpu_telemetry", {"usage_pct": float("inf"), "memory_usage_mb": 0.0}),
    ("gpu_telemetry", {"usage_pct": 0.0, "memory_usage_mb": 1e13}),
    ("gpu_telemetry", {"usage_pct": 0.0, "memory_usage_mb": 0.0, "extra": 1}),
])
def test_invalid_collector_payload_fails_closed(client, monkeypatch, field, value):
    metrics = operations._read_system_metrics()
    metrics[field] = value
    monkeypatch.setattr(operations, "_read_system_metrics", lambda: metrics)
    assert client.get("/api/v1/operations/system-telemetry").status_code == 424


@pytest.mark.parametrize("name", ["cpu_percent", "virtual_memory", "disk_io_counters", "ipc"])
def test_unavailable_collector_is_null(client, monkeypatch, name):
    def unavailable(*args, **kwargs):
        raise OSError("https://user:password@example.com/?token=secret")
    if name == "ipc":
        monkeypatch.setattr(operations, "_read_ipc_queue_depth", unavailable)
        fields = ["ipc_queue_depth"]
    else:
        monkeypatch.setattr(operations.psutil, name, unavailable)
        fields = {"cpu_percent": ["cpu_usage_pct"], "virtual_memory": ["memory_usage_mb", "memory_usage_pct"],
                  "disk_io_counters": ["io_read_bytes", "io_write_bytes"]}[name]
    response = client.get("/api/v1/operations/system-telemetry")
    assert response.status_code == 200
    assert all(response.json()[field] is None for field in fields)
    assert "password" not in response.text
    assert_provenance(response.json())


def test_missing_io_and_zero_memory(client, monkeypatch):
    monkeypatch.setattr(operations.psutil, "disk_io_counters", lambda: None)
    monkeypatch.setattr(operations.psutil, "virtual_memory", lambda: SimpleNamespace(used=0, total=0, percent=0.0))
    data = client.get("/api/v1/operations/system-telemetry").json()
    assert data["io_read_bytes"] is None
    assert data["memory_usage_mb"] == 0
    assert data["memory_usage_pct"] == 0


@pytest.mark.parametrize("endpoint", ["system-telemetry", "circuit-breaker-status"])
@pytest.mark.parametrize("query", ["as_of=2026-10-11T15:30:00%2B07:00", "pit_cutoff=2026-10-11", "as_of=nan", "extra=1"])
def test_current_only_rejects_caller_provenance(client, endpoint, query):
    assert client.get(f"/api/v1/operations/{endpoint}?{query}").status_code == 422


def test_snapshot_frozen_schema_digest_and_time(client):
    data = client.get("/api/v1/operations/system-telemetry").json()
    snapshot = operations.SystemTelemetryResponse.model_validate_json(json.dumps(data))
    with pytest.raises(ValidationError):
        snapshot.cpu_usage_pct = 1.0
    with pytest.raises(ValidationError):
        snapshot.provenance.sha256 = "f" * 64
    with pytest.raises(ValidationError):
        operations.SystemTelemetryResponse.model_validate_json(json.dumps({**data, "extra": 1}))
    for field in ["as_of", "available_at"]:
        with pytest.raises(ValidationError):
            operations.SystemTelemetryResponse.model_validate_json(json.dumps({**data, field: "2026-10-11T08:30:00"}))
    close_ict = datetime(2026, 10, 11, 15, 30, tzinfo=timezone(timedelta(hours=7)))
    equal = snapshot.model_dump()
    equal.update(as_of=close_ict, available_at=close_ict.astimezone(timezone.utc))
    normalized = operations.SystemTelemetryResponse(**equal)
    assert normalized.as_of == normalized.available_at
    with pytest.raises(ValidationError):
        operations.SystemTelemetryResponse(**{**equal, "as_of": close_ict + timedelta(microseconds=1)})


@pytest.mark.parametrize("reason,time,active", [
    (None, None, True), ("", None, True), ([], None, True), ("x" * 2049, None, True),
    ("halt", datetime(2026, 10, 11), True),
    ("halt", datetime.now(timezone.utc) + timedelta(days=100), True),
    ("halt", None, False), (None, None, "false"),
    (True, None, True), (float("nan"), None, True), (float("inf"), None, True),
    (-float("inf"), None, True), (0, None, True), (-1, None, True), (1e13, None, True),
], ids=["missing-reason", "empty-reason", "nonscalar-reason", "oversized-reason",
        "naive-time", "future-time", "inactive-metadata", "invalid-state",
        "boolean-reason", "nan-reason", "inf-reason", "negative-inf-reason",
        "zero-reason", "negative-reason", "overflow-reason"])
def test_corrupt_risk_state_fails_closed(client, switch, monkeypatch, reason, time, active):
    switch._activation_reason = reason
    switch._activation_time = time
    monkeypatch.setattr(switch._activated, "is_set", lambda: active)
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 424
    assert response.json() == {"detail": "Circuit breaker observation unavailable"}


def test_breaker_lock_contention_and_provider_failure(client, switch, monkeypatch):
    switch._lock.acquire()
    try:
        assert client.get("/api/v1/operations/circuit-breaker-status").status_code == 424
    finally:
        switch._lock.release()
    def fail():
        raise RuntimeError("https://user:password@example.com/?api_key=secret")
    monkeypatch.setattr(operations.circuit_breaker, "get_kill_switch", fail)
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 424
    assert "password" not in response.text
    assert "secret" not in response.text


def test_breaker_reason_redaction(client, switch):
    switch.activate("halt https://user:password@example.com/path?token=secret Bearer abcdefghijklmnop")
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 200
    assert "password" not in response.text
    assert "secret" not in response.text
    assert "abcdefghijklmnop" not in response.text
    assert_provenance(response.json())


@pytest.mark.parametrize("reason", [
    "halt password=secret token=abc123 api_key=short",
    "halt password=pass!word!123",
    "halt PASSWORD: 'punctuation ;,=!? value'",
    'halt {"api_key": "quoted credential", "password": "a"}',
    "halt Authorization: Basic dXNlcjpwYXNz",
    "halt Bearer x",
    "halt https://user:password@example.com/path?token=secret#private",
    "halt https%3A%2F%2Fuser%3Apassword%40example.com",
    "halt private key\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
    "halt unlabelled-credential",
    "halt\x00password=secret\r\ntoken=short",
    "halt mật_khẩu=秘密",
    "x" * 2048,
], ids=["short", "punctuation", "mixed-case", "json", "basic", "short-bearer",
        "url", "encoded-url", "multiline", "unlabelled", "controls", "unicode", "max-length"])
def test_breaker_public_reason_does_not_publish_private_text(client, switch, reason):
    switch._activated.set()
    switch._activation_reason = reason
    switch._activation_time = datetime.now(timezone.utc)
    before = (switch._activation_id, switch._activation_time, switch._activation_reason)
    for _ in range(2):
        response = client.get("/api/v1/operations/circuit-breaker-status")
        assert response.status_code == 200
        data = response.json()
        assert data["reasons"] == ["Risk circuit breaker activated"]
        assert data["state"] == "TRIGGERED"
        assert data["circuit_broken"] is True
        assert_provenance(data)
    assert before == (switch._activation_id, switch._activation_time, switch._activation_reason)
    assert switch._lock.acquire(blocking=False)
    switch._lock.release()


def test_breaker_response_rejects_unsanitized_snapshot(client, monkeypatch):
    monkeypatch.setattr(operations, "_read_circuit_breaker_snapshot", lambda: dict(
        state="TRIGGERED", circuit_broken=True, reasons=("password=secret",),
        triggered_at=datetime.now(timezone.utc),
    ))
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 424
    assert response.json() == {"detail": "Circuit breaker observation unavailable"}


def test_breaker_snapshot_read_failure_releases_lock(client, switch, monkeypatch):
    def fail():
        raise RuntimeError("password=secret token=abc123")
    monkeypatch.setattr(switch._activated, "is_set", fail)
    response = client.get("/api/v1/operations/circuit-breaker-status")
    assert response.status_code == 424
    assert response.json() == {"detail": "Circuit breaker observation unavailable"}
    assert switch._lock.acquire(blocking=False)
    switch._lock.release()


def test_concurrent_breaker_observations(switch):
    barrier = threading.Barrier(5)
    def observe():
        barrier.wait(timeout=2)
        return operations._read_circuit_breaker_snapshot()
    def activate():
        barrier.wait(timeout=2)
        switch.activate("concurrent halt")
    with ThreadPoolExecutor(max_workers=5) as pool:
        readers = [pool.submit(observe) for _ in range(4)]
        writer = pool.submit(activate)
        snapshots = [future.result(timeout=5) for future in readers]
        writer.result(timeout=5)
    for data in snapshots:
        assert data["circuit_broken"] == (data["state"] == "TRIGGERED")
        assert bool(data["reasons"]) == data["circuit_broken"]
        assert (data["triggered_at"] is not None) == data["circuit_broken"]


def test_ipc_read_only_regular_file_and_corruption(tmp_path, monkeypatch):
    path = tmp_path / "jobs.sqlite"
    monkeypatch.setattr(operations, "configured_database_path", lambda: path)
    assert operations._read_ipc_queue_depth() is None
    assert not path.exists()
    path.mkdir()
    assert operations._read_ipc_queue_depth() is None
    path.rmdir()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE omega_jobs (status TEXT)")
        db.executemany("INSERT INTO omega_jobs VALUES (?)", [("QUEUED",), ("QUEUED",), ("RUNNING",)])
    before = path.read_bytes()
    assert operations._read_ipc_queue_depth() == 2
    assert path.read_bytes() == before
    path.write_bytes(b"\xef\xbb\xbfcorrupt\r\n")
    with pytest.raises(sqlite3.DatabaseError):
        operations._read_ipc_queue_depth()


def test_ipc_corruption_is_unavailable(client, monkeypatch):
    def corrupted():
        raise sqlite3.DatabaseError("invalid checkpoint")
    monkeypatch.setattr(operations, "_read_ipc_queue_depth", corrupted)
    response = client.get("/api/v1/operations/system-telemetry")
    assert response.status_code == 200
    assert response.json()["ipc_queue_depth"] is None


def test_telemetry_bounds_and_no_governor_mutation(client, monkeypatch):
    before = dict(operations._GOVERNOR_STATE)
    monkeypatch.setattr(operations.psutil, "cpu_percent", lambda interval: 100.0)
    monkeypatch.setattr(operations.psutil, "virtual_memory", lambda: SimpleNamespace(used=10**12 * 2**20, percent=100.0))
    monkeypatch.setattr(operations.psutil, "disk_io_counters", lambda: SimpleNamespace(read_bytes=2**53 - 1, write_bytes=0))
    monkeypatch.setattr(operations, "_read_ipc_queue_depth", lambda: 1_000_000_000)
    response = client.get("/api/v1/operations/system-telemetry")
    assert response.status_code == 200
    assert len(response.content) < 2048
    assert before == operations._GOVERNOR_STATE
    assert_provenance(response.json())


def test_clock_regression_fails_closed(client, monkeypatch):
    class ReversedClock:
        calls = 0
        @classmethod
        def now(cls, tz):
            cls.calls += 1
            return datetime(2026, 10, 11, tzinfo=tz) - timedelta(seconds=cls.calls)
    monkeypatch.setattr(operations, "datetime", ReversedClock)
    assert client.get("/api/v1/operations/system-telemetry").status_code == 424
