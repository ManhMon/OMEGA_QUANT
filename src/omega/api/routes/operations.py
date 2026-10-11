"""Operations and Resource Governor routes for OMEGA_QUANT."""

import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Literal

import psutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from omega.api.services.job_service import configured_database_path
from omega.risk import circuit_breaker

from omega.api.schemas.advanced_quant import (
    AwareUtcDateTime,
    GovernorMode,
    ProvenanceEnvelope,
    ResourceGovernorPolicyUpdateRequest,
    ResourceGovernorStateResponse,
)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


class FrozenOperationsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


Percent = Annotated[float, Field(ge=0, le=100)]
MemoryMiB = Annotated[float, Field(ge=0, le=1e12)]
Counter = Annotated[int, Field(ge=0, le=2**53 - 1)]


class OperationsProvenance(FrozenOperationsModel):
    source: Literal["PSUTIL_AND_DURABLE_JOB_QUEUE", "OMEGA_RISK_CIRCUIT_BREAKER"]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    normalized_timezone: Literal["UTC"] = "UTC"
    observation_mode: Literal["CURRENT_ONLY"] = "CURRENT_ONLY"
    is_synthetic: Literal[False] = False


class OperationsSnapshot(FrozenOperationsModel):
    schema_version: Literal["operations/v1"] = "operations/v1"
    as_of: AwareUtcDateTime
    available_at: AwareUtcDateTime
    provenance: OperationsProvenance

    @model_validator(mode="after")
    def validate_time(self) -> "OperationsSnapshot":
        if self.as_of > self.available_at:
            raise ValueError("as_of must not exceed available_at")
        return self


class GpuTelemetry(FrozenOperationsModel):
    usage_pct: Percent
    memory_usage_mb: MemoryMiB
    memory_unit: Literal["MiB"] = "MiB"


class SystemTelemetryResponse(OperationsSnapshot):
    cpu_usage_pct: Percent | None
    memory_usage_mb: MemoryMiB | None
    memory_usage_pct: Percent | None
    memory_unit: Literal["MiB"] = "MiB"
    io_read_bytes: Counter | None
    io_write_bytes: Counter | None
    io_unit: Literal["bytes_cumulative_since_boot"] = "bytes_cumulative_since_boot"
    ipc_queue_depth: Annotated[int, Field(ge=0, le=1_000_000_000)] | None
    ipc_unit: Literal["queued_jobs"] = "queued_jobs"
    gpu_telemetry: GpuTelemetry | None


class CircuitBreakerStatusResponse(OperationsSnapshot):
    state: Literal["NORMAL", "TRIGGERED"]
    circuit_broken: bool
    daily_pnl: None = None
    drawdown_pct: None = None
    max_drawdown_limit: None = None
    reasons: tuple[Literal["Risk circuit breaker activated"], ...]
    triggered_at: AwareUtcDateTime | None

    @model_validator(mode="after")
    def validate_status(self) -> "CircuitBreakerStatusResponse":
        if self.circuit_broken != (self.state == "TRIGGERED"):
            raise ValueError("inconsistent circuit breaker state")
        if self.circuit_broken != bool(self.reasons) or len(self.reasons) > 1:
            raise ValueError("inconsistent circuit breaker reasons")
        if self.circuit_broken != (self.triggered_at is not None):
            raise ValueError("inconsistent activation timestamp")
        if self.triggered_at is not None and self.triggered_at > self.as_of:
            raise ValueError("activation exceeds observation time")
        return self


def _seal_snapshot(model: type[OperationsSnapshot], source: str, as_of: datetime, **values: Any) -> OperationsSnapshot:
    snapshot = model(
        as_of=as_of, available_at=datetime.now(timezone.utc),
        provenance=OperationsProvenance(source=source, sha256="0" * 64), **values,
    )
    payload = json.dumps(snapshot.model_dump(mode="json", exclude={"provenance": {"sha256"}}),
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return snapshot.model_copy(update={"provenance": OperationsProvenance(
        source=source, sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )})


def _reject_snapshot_query(request: Request) -> None:
    if request.query_params:
        raise HTTPException(status_code=422, detail="Only current observations are supported; query parameters are not accepted")


def _read_ipc_queue_depth() -> int | None:
    path = configured_database_path().resolve()
    if not path.is_file():
        return None
    # Read-only: telemetry must not create a database or change journal policy.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
        row = db.execute("SELECT COUNT(*) FROM omega_jobs WHERE status='QUEUED'").fetchone()
        return row[0]


def _read_system_metrics() -> dict[str, Any]:
    values: dict[str, Any] = dict(cpu_usage_pct=None, memory_usage_mb=None,
                                  memory_usage_pct=None, io_read_bytes=None,
                                  io_write_bytes=None, ipc_queue_depth=None, gpu_telemetry=None)
    try:
        values["cpu_usage_pct"] = psutil.cpu_percent(interval=0.05)
    except (OSError, psutil.Error, NotImplementedError):
        pass
    try:
        memory = psutil.virtual_memory()
        if type(memory.used) is not int or not 0 <= memory.used <= 10**12 * 2**20:
            raise ValueError("invalid memory byte count")
        values.update(memory_usage_mb=memory.used / 2**20, memory_usage_pct=memory.percent)
    except (OSError, psutil.Error, NotImplementedError):
        pass
    try:
        io = psutil.disk_io_counters()
        if io is not None:
            values.update(io_read_bytes=io.read_bytes, io_write_bytes=io.write_bytes)
    except (OSError, psutil.Error, NotImplementedError):
        pass
    try:
        values["ipc_queue_depth"] = _read_ipc_queue_depth()
    except (OSError, sqlite3.Error, RuntimeError):
        pass
    # ponytail: no validated GPU collector; add one before reporting GPU measurements.
    return values


@router.get("/system-telemetry", response_model=SystemTelemetryResponse)
def get_system_telemetry(request: Request) -> SystemTelemetryResponse:
    """Current non-atomic system observations; unavailable metrics are null."""
    _reject_snapshot_query(request)
    try:
        values = _read_system_metrics()
        as_of = datetime.now(timezone.utc)
        return _seal_snapshot(SystemTelemetryResponse, "PSUTIL_AND_DURABLE_JOB_QUEUE", as_of, **values)
    except Exception:
        raise HTTPException(status_code=424, detail="System telemetry observation unavailable") from None


def _read_circuit_breaker_snapshot() -> dict[str, Any]:
    switch = circuit_breaker.get_kill_switch()
    # ponytail: risk exposes no public atomic snapshot; replace with risk-owned accessor when available.
    if not switch._lock.acquire(timeout=0.1):
        raise TimeoutError("circuit breaker snapshot busy")
    try:
        active = switch.is_activated
        reason = switch._activation_reason
        triggered_at = switch._activation_time
    finally:
        switch._lock.release()
    if type(active) is not bool:
        raise ValueError("invalid activation state")
    if active:
        if type(reason) is not str or not reason or len(reason) > 2048:
            raise ValueError("invalid activation reason")
        # Arbitrary risk text is private; heuristic redaction cannot guarantee secrecy.
        reasons = ("Risk circuit breaker activated",)
    else:
        reasons = ()
        if reason or triggered_at is not None:
            raise ValueError("inconsistent inactive state")
    return dict(state="TRIGGERED" if active else "NORMAL", circuit_broken=active,
                reasons=reasons, triggered_at=triggered_at)


@router.get("/circuit-breaker-status", response_model=CircuitBreakerStatusResponse)
def get_circuit_breaker_status(request: Request) -> CircuitBreakerStatusResponse:
    """Read risk's authoritative global halt without evaluating or resetting it."""
    _reject_snapshot_query(request)
    try:
        values = _read_circuit_breaker_snapshot()
        as_of = datetime.now(timezone.utc)
        return _seal_snapshot(CircuitBreakerStatusResponse, "OMEGA_RISK_CIRCUIT_BREAKER", as_of, **values)
    except Exception:
        raise HTTPException(status_code=424, detail="Circuit breaker observation unavailable") from None

# Thread-safe in-memory Resource Governor State
_GOVERNOR_LOCK = threading.Lock()
_GOVERNOR_STATE: Dict[str, Any] = {
    "mode": GovernorMode.MANUAL,
    "target_concurrency": 8,
    "thread_pool_size": 16,
    "batch_size": 256,
    "version": 1,
    "active_workers": 4,
    "queue_depth": 0,
    "system_load_pct": 24.5,
    "memory_usage_mb": 512.0,
    "updated_at": datetime.now(timezone.utc),
}


def _make_provenance(source: str, dataset_id: str, payload_summary: Any) -> ProvenanceEnvelope:
    now_utc = datetime.now(timezone.utc)
    summary_bytes = str(payload_summary).encode("utf-8")
    c_hash = hashlib.sha256(summary_bytes).hexdigest()
    return ProvenanceEnvelope(
        source=source,
        dataset_id=dataset_id,
        dataset_version="v2026.1",
        as_of=now_utc,
        computed_at=now_utc,
        effective_cutoff=now_utc,
        input_timezone="UTC+7",
        normalized_timezone="UTC",
        cutoff_resolution="AS_OF_DEFAULT",
        content_hash=c_hash,
        is_synthetic=False,
    )


def _get_mode_description(mode: GovernorMode) -> str:
    if mode == GovernorMode.COPILOT:
        return "Autonomous dynamic resource scheduling governed by Copilot telemetry without fixed CPU/RAM ceilings."
    return "Operator manual concurrency and worker pool configuration."


@router.get("/resource-governor", response_model=ResourceGovernorStateResponse)
def get_resource_governor() -> ResourceGovernorStateResponse:
    """Retrieve current Resource Governor state, concurrency limits, and active telemetry."""
    with _GOVERNOR_LOCK:
        mode = _GOVERNOR_STATE["mode"]
        target_concurrency = _GOVERNOR_STATE["target_concurrency"]
        thread_pool_size = _GOVERNOR_STATE["thread_pool_size"]
        batch_size = _GOVERNOR_STATE["batch_size"]
        version = _GOVERNOR_STATE["version"]
        active_workers = _GOVERNOR_STATE["active_workers"]
        queue_depth = _GOVERNOR_STATE["queue_depth"]
        system_load_pct = _GOVERNOR_STATE["system_load_pct"]
        memory_usage_mb = _GOVERNOR_STATE["memory_usage_mb"]
        updated_at = _GOVERNOR_STATE["updated_at"]

    prov = _make_provenance(
        source="OMEGA_RESOURCE_GOVERNOR",
        dataset_id="governor_telemetry",
        payload_summary={"mode": mode, "concurrency": target_concurrency, "version": version},
    )
    return ResourceGovernorStateResponse(
        status="success",
        mode=mode,
        target_concurrency=target_concurrency,
        thread_pool_size=thread_pool_size,
        batch_size=batch_size,
        version=version,
        active_workers=active_workers,
        queue_depth=queue_depth,
        system_load_pct=system_load_pct,
        memory_usage_mb=memory_usage_mb,
        mode_description=_get_mode_description(mode),
        updated_at=updated_at,
        provenance=prov,
    )


@router.patch("/resource-governor", response_model=ResourceGovernorStateResponse)
def update_resource_governor(req: ResourceGovernorPolicyUpdateRequest) -> ResourceGovernorStateResponse:
    """
    Update Resource Governor policy parameters (mode switch between MANUAL and COPILOT,
    target concurrency, thread pool size, and batch size without fixed CPU/RAM ceilings).
    """
    now_utc = datetime.now(timezone.utc)
    with _GOVERNOR_LOCK:
        if req.mode is not None:
            resolved_mode = GovernorMode(req.mode) if isinstance(req.mode, str) else req.mode
            _GOVERNOR_STATE["mode"] = resolved_mode
            if resolved_mode == GovernorMode.COPILOT:
                # Dynamic adaptive allocation under Copilot
                _GOVERNOR_STATE["target_concurrency"] = max(req.target_concurrency or _GOVERNOR_STATE["target_concurrency"], 12)
                _GOVERNOR_STATE["thread_pool_size"] = max(req.thread_pool_size or _GOVERNOR_STATE["thread_pool_size"], 24)
                _GOVERNOR_STATE["active_workers"] = 8
            else:
                _GOVERNOR_STATE["active_workers"] = 4

        if req.target_concurrency is not None:
            _GOVERNOR_STATE["target_concurrency"] = req.target_concurrency
        if req.thread_pool_size is not None:
            _GOVERNOR_STATE["thread_pool_size"] = req.thread_pool_size
        if req.batch_size is not None:
            _GOVERNOR_STATE["batch_size"] = req.batch_size

        _GOVERNOR_STATE["version"] += 1
        _GOVERNOR_STATE["updated_at"] = now_utc

        mode = _GOVERNOR_STATE["mode"]
        target_concurrency = _GOVERNOR_STATE["target_concurrency"]
        thread_pool_size = _GOVERNOR_STATE["thread_pool_size"]
        batch_size = _GOVERNOR_STATE["batch_size"]
        version = _GOVERNOR_STATE["version"]
        active_workers = _GOVERNOR_STATE["active_workers"]
        queue_depth = _GOVERNOR_STATE["queue_depth"]
        system_load_pct = _GOVERNOR_STATE["system_load_pct"]
        memory_usage_mb = _GOVERNOR_STATE["memory_usage_mb"]

    prov = _make_provenance(
        source="OMEGA_RESOURCE_GOVERNOR",
        dataset_id="governor_policy_update",
        payload_summary={"mode": mode, "concurrency": target_concurrency, "version": version},
    )
    return ResourceGovernorStateResponse(
        status="success",
        mode=mode,
        target_concurrency=target_concurrency,
        thread_pool_size=thread_pool_size,
        batch_size=batch_size,
        version=version,
        active_workers=active_workers,
        queue_depth=queue_depth,
        system_load_pct=system_load_pct,
        memory_usage_mb=memory_usage_mb,
        mode_description=_get_mode_description(mode),
        updated_at=now_utc,
        provenance=prov,
    )
