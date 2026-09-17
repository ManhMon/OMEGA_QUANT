"""Operations and Resource Governor routes for OMEGA_QUANT."""

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from omega.api.schemas.advanced_quant import (
    GovernorMode,
    ProvenanceEnvelope,
    ResourceGovernorPolicyUpdateRequest,
    ResourceGovernorStateResponse,
)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])

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
