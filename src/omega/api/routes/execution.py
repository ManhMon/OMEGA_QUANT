"""Execution routes for paper trading lifecycle, order execution, and worker governance."""

from __future__ import annotations

import logging
import math
import json
import threading
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fastapi import APIRouter, Depends, HTTPException, Query, status

from omega.api.dependencies import job_service_dependency
from omega.api.schemas.advanced_quant import StrictApiModel, FiniteFloat
from omega.api.services.job_service import JobService
from omega.quant.execution.paper_trading import get_paper_engine, PaperTradingEngine
from omega.api.routes._market_loader import redact_market_data_error


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])
_ENGINE_OPERATION_LOCK = threading.RLock()


class PaperDaemonStartRequest(StrictApiModel):
    initial_capital: Annotated[FiniteFloat, Field(default=1_000_000_000.0, gt=0, le=1e14)]
    mode: Annotated[str, Field(default="SHADOW", min_length=1, max_length=32)]


class PaperOrderRequest(StrictApiModel):
    symbol: Annotated[str, Field(min_length=1, max_length=16)]
    side: Annotated[str, Field(pattern=r"^(?i)(buy|sell)$")]
    size: Annotated[FiniteFloat, Field(gt=0, le=1e8)]
    price: Annotated[float, Field(ge=100, le=1e8)]
    model_id: Annotated[str, Field(default="CHAMPION_V1", min_length=1, max_length=64)]
    feature_ts: Annotated[str, Field(min_length=10, max_length=64)]
    decision_ts: Annotated[str, Field(min_length=10, max_length=64)]
    available_at: Optional[Annotated[str, Field(min_length=10, max_length=64)]] = None
    order_book_data: Optional[Dict[str, Any]] = Field(default=None, max_length=32)

    @field_validator("order_book_data")
    @classmethod
    def validate_order_book_data(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("order_book_data exceeds 64 KiB")

        def depth(item: Any, level: int = 0) -> int:
            if level > 10:
                raise ValueError("order_book_data nesting exceeds 10 levels")
            if isinstance(item, dict):
                return max((depth(child, level + 1) for child in item.values()), default=level)
            if isinstance(item, list):
                if len(item) > 30:
                    raise ValueError("order_book_data list exceeds 30 items")
                return max((depth(child, level + 1) for child in item), default=level)
            return level

        depth(value)
        return value

    @model_validator(mode="after")
    def validate_temporal_order(self) -> "PaperOrderRequest":
        now = datetime.now(timezone.utc)
        feature = datetime.fromisoformat(self.feature_ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        decision = datetime.fromisoformat(self.decision_ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        available = datetime.fromisoformat((self.available_at or self.feature_ts).replace("Z", "+00:00")).astimezone(timezone.utc)
        if not feature <= available <= decision <= now:
            raise ValueError("feature_ts <= available_at <= decision_ts <= now_utc required")
        return self

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

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> int:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("price must be a valid number")
        if v < 100:
            raise ValueError(f"price must be an integer VND value >= 100 (got {v})")
        if not float(v).is_integer():
            raise ValueError(f"price must be an integer VND value (got fractional {v})")
        return int(v)

    @field_validator("feature_ts", "decision_ts", "available_at")
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("timestamp must be a string")
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("timestamp must have an explicit timezone offset")
            return v
        except Exception as err:
            raise ValueError(f"invalid ISO timestamp format: {err}") from err


def _get_engine() -> PaperTradingEngine:
    return get_paper_engine()


@router.get("/status")
def get_paper_daemon_status(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Return status, metrics, and worker count of paper trading daemon."""
    engine = _get_engine()
    with _ENGINE_OPERATION_LOCK:
        daemon_status = engine.get_status()
    active_workers = []
    if service is not None:
        try:
            active_workers = service.list_active_workers(timeout_seconds=60)
        except Exception as e:
            logger.warning("Failed to query active workers: %s", redact_market_data_error(e))
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
    with _ENGINE_OPERATION_LOCK:
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


@router.get("/blotter")
def get_execution_blotter(limit: int = Query(default=100, ge=1, le=5000)) -> dict[str, Any]:
    orders = _get_engine().get_orders(limit=limit)
    def number(record: dict[str, Any], *keys: str) -> float:
        try:
            value = float(next((record.get(key) for key in keys if record.get(key) is not None), 0.0))
        except (TypeError, ValueError, OverflowError) as error:
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID") from error
        if not math.isfinite(value):
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
        return value
    items = [{"orderId": str(o.get("order_id", o.get("orderId", f"ORDER_{i}"))), "timestamp": str(o.get("execution_ts", o.get("timestamp", ""))), "symbol": str(o.get("symbol", "")).upper(), "side": str(o.get("side", "BUY")).upper(), "orderType": "LO", "qty": number(o, "quantity", "size"), "price": number(o, "executed_price", "intended_price"), "filledQty": number(o, "quantity", "size") if o.get("execution_status") == "FILLED" else 0, "status": "FILLED" if o.get("execution_status") == "FILLED" else "PENDING", "broker": "VPS", "algoType": "DIRECT"} for i, o in enumerate(orders)]
    return {"status": "success", "timestamp": datetime.now(timezone.utc).isoformat(), "orders": items, "count": len(items)}


@router.get("/routing-diagnostics")
def get_routing_diagnostics() -> dict[str, Any]:
    orders = _get_engine().get_orders(limit=5000)
    active = [o for o in orders if o.get("execution_status") in {"PENDING", "ROUTING"}]
    filled = sum(o.get("execution_status") == "FILLED" for o in orders)
    rejected = sum(o.get("execution_status") == "REJECTED" for o in orders)
    order_count = len(orders)
    return {"status": "success", "timestamp": datetime.now(timezone.utc).isoformat(), "engine": "paper_trading", "total_active_orders": len(active), "total_active_slices": len(active), "avg_roundtrip_latency_ms": None, "routers": [{"broker": "VPS", "channel": "paper", "ping_ms": None, "fill_rate_pct": filled / order_count * 100.0 if order_count else 0.0, "price_improvement_bps": None, "rejection_rate_pct": rejected / order_count * 100.0 if order_count else 0.0, "status": "DATA_ONLY", "active_routes": len(active)}], "active_queues": []}
