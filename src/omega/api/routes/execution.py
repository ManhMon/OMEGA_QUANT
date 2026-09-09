"""Execution routes for paper trading lifecycle, order execution, and worker governance."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastapi import APIRouter, Depends, HTTPException, Query, status

from omega.api.dependencies import job_service_dependency
from omega.api.schemas.advanced_quant import FiniteFloat
from omega.api.services.job_service import JobService
from omega.quant.execution.paper_trading import get_paper_engine, PaperTradingEngine


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])


class PaperDaemonStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_capital: Annotated[FiniteFloat, Field(default=1_000_000_000.0, gt=0, le=1e14)]
    mode: str = Field(default="SHADOW")


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    side: str = Field(pattern=r"^(?i)(buy|sell)$")
    size: Annotated[FiniteFloat, Field(gt=0, le=1e8)]
    price: Annotated[FiniteFloat, Field(gt=0, le=1e8)]
    model_id: str = Field(default="CHAMPION_V1")
    feature_ts: str
    decision_ts: str
    available_at: Optional[str] = None
    order_book_data: Optional[Dict[str, Any]] = None

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s.isalnum():
            raise ValueError("symbol must be alphanumeric")
        return s

    @field_validator("side")
    @classmethod
    def canonical_side(cls, v: str) -> str:
        return v.strip().upper()


def _get_engine() -> PaperTradingEngine:
    return get_paper_engine()


@router.get("/status")
def get_paper_daemon_status(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Return status, metrics, and worker count of paper trading daemon."""
    engine = _get_engine()
    daemon_status = engine.get_status()
    active_workers = []
    if service is not None:
        try:
            active_workers = service.list_active_workers(timeout_seconds=60)
        except Exception as e:
            logger.warning(f"Failed to query active workers: {e}")
    daemon_status["active_workers"] = len(active_workers)
    daemon_status["workers"] = active_workers
    return daemon_status


@router.post("/start")
def start_paper_daemon(
    req: Optional[PaperDaemonStartRequest] = None,
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Start paper trading daemon lifecycle."""
    engine = _get_engine()
    initial_capital = req.initial_capital if req else 1_000_000_000.0
    mode = req.mode if req else "SHADOW"
    try:
        engine.start(initial_capital=initial_capital, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return get_paper_daemon_status(service=service)


@router.post("/stop")
def stop_paper_daemon(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Stop paper trading daemon."""
    engine = _get_engine()
    try:
        engine.stop()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return get_paper_daemon_status(service=service)


@router.post("/pause")
def pause_paper_daemon(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Pause paper trading execution."""
    engine = _get_engine()
    try:
        engine.pause()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return get_paper_daemon_status(service=service)


@router.post("/resume")
def resume_paper_daemon(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Resume paper trading execution."""
    engine = _get_engine()
    try:
        engine.resume()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return get_paper_daemon_status(service=service)


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def submit_paper_order(order: PaperOrderRequest) -> dict[str, Any]:
    """Submit a virtual paper trading order for execution."""
    engine = _get_engine()
    payload = order.model_dump()
    executions = engine.execute_virtual_order(payload, order_book_data=order.order_book_data)
    first_status = executions[0]["execution_status"] if executions else "UNKNOWN"
    return {
        "status": first_status,
        "symbol": order.symbol,
        "side": order.side,
        "executions": executions,
        "count": len(executions),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/orders")
def get_paper_orders(
    limit: int = Query(default=100, ge=1, le=5000),
    symbol: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    """Retrieve recent paper trading virtual order executions."""
    engine = _get_engine()
    return engine.get_orders(limit=limit, symbol=symbol)


@router.get("/positions")
def get_paper_positions() -> dict[str, Any]:
    """Retrieve current virtual positions and PnL."""
    engine = _get_engine()
    positions = engine.get_positions()
    return {
        "positions": positions,
        "count": len(positions),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/workers")
def get_execution_workers(
    service: Annotated[JobService, Depends(job_service_dependency)],
) -> list[dict[str, Any]]:
    """Retrieve active worker daemon lifecycle telemetry."""
    return service.list_active_workers(timeout_seconds=60)
