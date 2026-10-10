"""Execution routes for paper trading lifecycle, order execution, and worker governance."""

from __future__ import annotations

import logging
import math
import json
import threading
import copy
import hashlib
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from omega.api.dependencies import job_service_dependency
from omega.api.schemas.advanced_quant import AwareUtcDateTime, StrictApiModel, FiniteFloat
from omega.data.calendar import VNTradingCalendar
from omega.api.services.job_service import JobService
from omega.quant.execution.paper_trading import get_paper_engine, PaperTradingEngine
from omega.api.routes._market_loader import redact_market_data_error


logger = logging.getLogger(__name__)

class ExecutionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                if request.method == "GET" and request.url.path.rsplit("/", 1)[-1] in {
                    "status", "blotter", "timeline", "routing-diagnostics", "slippage-distribution", "settlement-timeline"
                }:
                    name = request.url.path.rsplit("/", 1)[-1]
                    allowed = set() if name == "status" else ({"as_of", "limit"} if name == "blotter" else {"as_of"})
                    keys = list(request.query_params.keys())
                    if set(keys) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in keys):
                        raise HTTPException(422, "INVALID_REQUEST")
                response = await handler(request)
                if request.method == "GET" and len(response.body) > 1024 * 1024:
                    raise HTTPException(424, "EXECUTION_RESPONSE_TOO_LARGE")
                return response
            except RequestValidationError as error:
                raise HTTPException(422, "INVALID_REQUEST") from error
            except (ValidationError, ValueError, TypeError, OverflowError) as error:
                if request.method == "GET":
                    raise HTTPException(424, "EXECUTION_DATA_INVALID") from error
                raise

        return validated


router = APIRouter(prefix="/api/v1/execution", tags=["execution"], route_class=ExecutionRoute)
_ENGINE_OPERATION_LOCK = threading.RLock()
_ICT = timezone(timedelta(hours=7))
Quantity = Annotated[FiniteFloat, Field(ge=0, le=1e8)]
Money = Annotated[FiniteFloat, Field(ge=0)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
OrderState = Literal["FILLED", "PARTIALLY_FILLED", "PENDING", "ROUTING", "CANCELLED", "REJECTED"]
Algorithm = Literal["TWAP", "VWAP", "DIRECT"]


class ExecutionRecord(StrictApiModel):
    execution_ts: AwareUtcDateTime
    feature_ts: AwareUtcDateTime | None = None
    decision_ts: AwareUtcDateTime | None = None
    available_at: AwareUtcDateTime | None = None
    recorded_at: AwareUtcDateTime | None = None
    order_id: Identifier | None = None
    parent_order_id: Identifier | None = None
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,16}$")]
    side: Literal["BUY", "SELL"]
    quantity: Quantity
    size: Quantity | None = None
    intended_price: Annotated[FiniteFloat, Field(ge=0, le=1e8)]
    executed_price: Annotated[FiniteFloat, Field(ge=0, le=1e8)] = 0.0
    filled_quantity: Quantity | None = None
    execution_status: Annotated[str, Field(pattern=r"^(FILLED|PARTIALLY_FILLED|PENDING|ROUTING|CANCELLED|REJECTED(?:_[A-Z_]+)?)$")]
    algo_type: Algorithm = "DIRECT"
    sequence: Annotated[int, Field(ge=0, le=5000)] | None = None
    broker: Identifier = "PAPER"
    venue: Literal["HOSE", "HNX", "UPCOM", "PAPER", "UNKNOWN"] = "UNKNOWN"
    order_type: Literal["LO", "ATO", "ATC", "MP"] = "LO"
    arrival_price: Annotated[FiniteFloat, Field(ge=100, le=1e8)] | None = None
    fee_vnd: Money | None = None
    total_cost_vnd: Money | None = None
    notional: Money | None = None
    pnl: FiniteFloat | None = None
    model_id: Identifier | None = None
    is_virtual: bool = True
    reject_reason: Annotated[str, Field(max_length=2048)] | None = None
    price_unit: Literal["VND_FULL"] = "VND_FULL"
    broker_effective_at: AwareUtcDateTime | None = None
    settlement_effective_at: AwareUtcDateTime | None = None
    confirmation_available_at: AwareUtcDateTime | None = None
    cash_available_vnd: Money | None = None
    shares_available: Quantity | None = None

    @property
    def state(self) -> str:
        return "REJECTED" if self.execution_status.startswith("REJECTED") else self.execution_status

    @property
    def filled(self) -> float:
        return self.filled_quantity if self.filled_quantity is not None else (self.quantity if self.state == "FILLED" else 0.0)

    @model_validator(mode="after")
    def consistent(self):
        if self.size is not None and self.size != self.quantity:
            raise ValueError("quantity aliases disagree")
        if self.filled > self.quantity or (self.state == "FILLED" and self.filled != self.quantity):
            raise ValueError("invalid fill quantity")
        if self.state == "PARTIALLY_FILLED" and not 0 < self.filled < self.quantity:
            raise ValueError("invalid partial fill")
        if self.state in {"PENDING", "ROUTING", "REJECTED"} and self.filled:
            raise ValueError("unexecuted order has fills")
        if self.filled and (self.executed_price < 100 or self.quantity <= 0):
            raise ValueError("invalid VND fill")
        if self.intended_price and self.intended_price < 100:
            raise ValueError("invalid VND price")
        if self.parent_order_id == self.order_id and self.order_id is not None:
            raise ValueError("self parent")
        if self.parent_order_id is not None and self.sequence is None:
            raise ValueError("child sequence required")
        if self.recorded_at is not None and self.recorded_at < self.execution_ts:
            raise ValueError("publication precedes event")
        if self.state != "REJECTED":
            clocks = (self.feature_ts, self.available_at, self.decision_ts, self.execution_ts)
            present = [clock for clock in clocks if clock is not None]
            if present != sorted(present):
                raise ValueError("PIT ordering")
        return self


class ReadEnvelope(StrictApiModel):
    status: Literal["success"] = "success"
    timestamp: AwareUtcDateTime
    effective_cutoff: AwareUtcDateTime
    provenance: Literal["RECORDED", "LIVE_UNVERIFIED"]
    price_unit: Literal["VND_FULL"] = "VND_FULL"


class BlotterItem(StrictApiModel):
    orderId: Identifier
    parentOrderId: Identifier | None
    timestamp: AwareUtcDateTime
    availableAt: AwareUtcDateTime | None
    symbol: str
    side: Literal["BUY", "SELL"]
    orderType: Literal["LO", "ATO", "ATC", "MP"]
    qty: Quantity
    price: Money
    filledQty: Quantity
    status: OrderState
    broker: Identifier
    venue: str
    algoType: Algorithm
    sequence: int | None


class BlotterResponse(ReadEnvelope):
    orders: list[BlotterItem]
    count: Annotated[int, Field(ge=0, le=5000)]


class TimelineParent(StrictApiModel):
    parent_order_id: Identifier
    symbol: str
    side: Literal["BUY", "SELL"]
    algo_type: Algorithm
    target_qty: Quantity
    filled_qty: Quantity
    completion_pct: Annotated[FiniteFloat, Field(ge=0, le=100)] | None
    sequence_complete: bool
    slices: list[BlotterItem]


class TimelineResponse(ReadEnvelope):
    parents: list[TimelineParent]
    standalone: list[BlotterItem]


class SlippagePoint(StrictApiModel):
    order_id: Identifier
    venue: str
    side: Literal["BUY", "SELL"]
    quantity: Quantity
    arrival_price: Money
    executed_price: Money
    fee_vnd: Money
    slippage_bps: FiniteFloat


class VenueSlippage(StrictApiModel):
    venue: str
    count: int
    arrival_notional_vnd: Money
    average_slippage_bps: FiniteFloat


class SlippageResponse(ReadEnvelope):
    benchmark: Literal["ARRIVAL_PRICE"] = "ARRIVAL_PRICE"
    sign_convention: Literal["POSITIVE_IS_COST"] = "POSITIVE_IS_COST"
    fees_included: Literal[True] = True
    points: list[SlippagePoint]
    venues: list[VenueSlippage]
    excluded_missing_benchmark_or_fee: int


class SettlementItem(StrictApiModel):
    order_id: Identifier
    broker: Identifier
    symbol: str
    side: Literal["BUY", "SELL"]
    trade_at: AwareUtcDateTime
    expected_settlement_at: AwareUtcDateTime
    broker_effective_at: AwareUtcDateTime | None
    settlement_effective_at: AwareUtcDateTime | None
    confirmation_available_at: AwareUtcDateTime | None
    confirmed: bool
    cash_available_vnd: Money | None
    shares_available: Quantity | None
    skipped_closed_dates: list[str]


class SettlementResponse(ReadEnvelope):
    calendar_timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    forecast_policy: Literal["T_PLUS_2_TRADING_DAYS_15_30_ICT_NOT_CONFIRMATION"] = "T_PLUS_2_TRADING_DAYS_15_30_ICT_NOT_CONFIRMATION"
    settlements: list[SettlementItem]


class RouterDiagnostic(StrictApiModel):
    broker: Identifier
    channel: Literal["paper"] = "paper"
    ping_ms: Money | None = None
    fill_rate_pct: Annotated[FiniteFloat, Field(ge=0, le=100)]
    price_improvement_bps: FiniteFloat | None = None
    rejection_rate_pct: Annotated[FiniteFloat, Field(ge=0, le=100)]
    status: Literal["DATA_ONLY"] = "DATA_ONLY"
    active_routes: int


class RoutingResponse(ReadEnvelope):
    engine: Literal["paper_trading"] = "paper_trading"
    total_active_orders: int
    total_active_slices: int
    avg_roundtrip_latency_ms: Money | None = None
    routers: list[RouterDiagnostic]
    active_queues: list[Identifier] = Field(default_factory=list)


def _cutoff(as_of: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    if as_of is None:
        return now
    try:
        value = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None or value > now:
            raise ValueError("invalid cutoff")
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(422, "PIT_CUTOFF_INVALID") from error


def _json_budget(value: Any, remaining: int, depth: int = 0) -> int:
    """Count default ensure_ascii JSON bytes without allocating the encoded payload."""
    if remaining < 0 or depth > 10:
        raise ValueError("JSON byte or nesting bounds")
    if type(value) is str:
        remaining -= 2
        if len(value) > remaining:
            raise ValueError("JSON text bounds")
        for char in value:
            code = ord(char)
            remaining -= (2 if char in '\"\\\\\b\f\n\r\t' else
                          6 if code < 32 or 127 <= code <= 0xffff else
                          12 if code > 0xffff else 1)
            if remaining < 0:
                raise ValueError("JSON byte bounds")
    elif isinstance(value, dict):
        remaining -= 2 + max(0, len(value) - 1) * 2
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError("JSON key type")
            remaining = _json_budget(key, remaining, depth + 1) - 2
            remaining = _json_budget(child, remaining, depth + 1)
    elif isinstance(value, list):
        remaining -= 2 + max(0, len(value) - 1) * 2
        for child in value:
            remaining = _json_budget(child, remaining, depth + 1)
    elif value is None or type(value) is bool:
        remaining -= 4 if value is None or value is True else 5
    elif type(value) in {int, float}:
        if type(value) is int:
            if value.bit_length() > remaining * 4:
                raise ValueError("JSON integer bounds")
        elif not math.isfinite(value):
            raise ValueError("JSON non-finite value")
        remaining -= len(str(value))
    else:
        raise ValueError("JSON scalar type")
    if remaining < 0:
        raise ValueError("JSON byte bounds")
    return remaining


def _snapshot(as_of: str | None) -> tuple[dict, list[ExecutionRecord]]:
    cutoff = _cutoff(as_of)
    try:
        with _ENGINE_OPERATION_LOCK:
            raw = _get_engine().get_orders(limit=5000)
            if not isinstance(raw, list) or len(raw) >= 5000:
                # At the engine cap, completeness cannot be established.
                raise ValueError("snapshot bounds or truncated history")
            # Bound before copying/parsing; no unbounded nested provider payloads.
            remaining = 1024 * 1024 - 2 - max(0, len(raw) - 1) * 2
            for row in raw:
                if not isinstance(row, dict) or len(row) > 40:
                    raise ValueError("record bounds")
                for key, value in row.items():
                    if type(key) is not str or len(key) > 64 or type(value) not in {str, int, float, bool, type(None)}:
                        raise ValueError("record scalar types")
                    if isinstance(value, str) and len(value) > 2048:
                        raise ValueError("record text bounds")
                remaining = _json_budget(row, remaining)
            encoded = json.dumps(raw, allow_nan=False, ensure_ascii=True)
            if len(encoded) > 1024 * 1024:
                raise ValueError("snapshot byte bounds")
            records = [ExecutionRecord.model_validate(row) for row in copy.deepcopy(raw)]
        seen = set()
        visible = []
        verified = True
        for row in records:
            if row.order_id is None:
                content = row.model_dump(mode="json")
                row.order_id = "PAPER_" + hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
            if row.order_id in seen:
                raise ValueError("duplicate order identity")
            seen.add(row.order_id)
            if row.execution_ts > cutoff:
                continue
            if row.recorded_at is None:
                if as_of is not None:
                    raise ValueError("historical publication unavailable")
                verified = False
            elif row.recorded_at > cutoff:
                continue
            visible.append(row)
        visible.sort(key=lambda row: (row.execution_ts, row.order_id))
        return dict(timestamp=datetime.now(timezone.utc), effective_cutoff=cutoff,
                    provenance="RECORDED" if verified else "LIVE_UNVERIFIED"), visible
    except Exception as error:
        raise HTTPException(424, "EXECUTION_DATA_INVALID") from error


def _blotter_item(row: ExecutionRecord) -> BlotterItem:
    return BlotterItem(orderId=row.order_id, parentOrderId=row.parent_order_id,
                       timestamp=row.execution_ts, availableAt=row.recorded_at,
                       symbol=row.symbol, side=row.side, orderType=row.order_type,
                       qty=row.quantity, price=row.executed_price if row.filled else row.intended_price,
                       filledQty=row.filled, status=row.state, broker=row.broker,
                       venue=row.venue, algoType=row.algo_type, sequence=row.sequence)


class PaperDaemonStartRequest(StrictApiModel):
    initial_capital: Annotated[FiniteFloat, Field(default=1_000_000_000.0, gt=0, le=1e14)]
    mode: Annotated[Identifier, Field(default="SHADOW", min_length=1, max_length=32)]


class PaperOrderRequest(StrictApiModel):
    symbol: Annotated[str, Field(min_length=1, max_length=16)]
    side: Annotated[str, Field(pattern=r"^(?i)(buy|sell)$")]
    size: Annotated[FiniteFloat, Field(gt=0, le=1e8)]
    price: Annotated[float, Field(ge=100, le=1e8)]
    model_id: Annotated[Identifier, Field(default="CHAMPION_V1", min_length=1, max_length=64)]
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
        available_at = self.feature_ts if self.available_at is None else self.available_at
        available = datetime.fromisoformat(available_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        if not feature <= available <= decision <= now:
            raise ValueError("feature_ts <= available_at <= decision_ts <= now_utc required")
        self.available_at = available_at
        return self

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s.isascii() or not s.isalnum() or len(s) > 16:
            raise ValueError("symbol must be 1-16 ASCII alphanumeric characters")
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


class PositionStatus(StrictApiModel):
    symbol: Identifier
    shares: Quantity
    avg_price: Money
    current_price: Money
    realized_pnl_vnd: FiniteFloat
    unrealized_pnl_vnd: FiniteFloat


class WorkerStatus(StrictApiModel):
    worker_id: Identifier
    hostname: Identifier
    pid: Annotated[int, Field(gt=0)]
    status: Literal["ACTIVE"]
    started_at: AwareUtcDateTime
    last_heartbeat: AwareUtcDateTime


class ExecutionStatus(StrictApiModel):
    state: Literal["STOPPED", "RUNNING", "PAUSED"]
    active: bool
    mode: Identifier
    initial_capital_vnd: Money
    cash_vnd: Money
    portfolio_equity_vnd: Money
    total_pnl_vnd: FiniteFloat
    daily_pnl_vnd: FiniteFloat
    realized_pnl_vnd: FiniteFloat
    unrealized_pnl_vnd: FiniteFloat
    uptime_seconds: Money
    last_heartbeat: AwareUtcDateTime | None
    processed_orders_count: Annotated[int, Field(ge=0)]
    active_orders_count: Annotated[int, Field(ge=0)]
    positions_count: Annotated[int, Field(ge=0)]
    positions: dict[Identifier, PositionStatus]
    model_pnl: dict[Identifier, FiniteFloat]
    active_workers: Annotated[int, Field(ge=0)]
    workers: list[WorkerStatus]
    workers_available: bool

    @model_validator(mode="after")
    def consistent(self):
        if self.active != (self.state == "RUNNING") or self.positions_count != len(self.positions):
            raise ValueError("status mismatch")
        if self.active_orders_count > self.processed_orders_count:
            raise ValueError("order counts")
        now = datetime.now(timezone.utc)
        if self.last_heartbeat is not None and self.last_heartbeat > now:
            raise ValueError("future heartbeat")
        if any(w.started_at > w.last_heartbeat or w.last_heartbeat > now for w in self.workers):
            raise ValueError("worker clocks")
        return self


@router.get("/status", response_model=ExecutionStatus)
def get_paper_daemon_status(
    service: Annotated[JobService, Depends(job_service_dependency)] = None,
) -> dict[str, Any]:
    """Current telemetry only; historical state is not reconstructed from fills."""
    try:
        with _ENGINE_OPERATION_LOCK:
            raw_status = _get_engine().get_status()
            if not isinstance(raw_status, dict) or len(raw_status) > 32:
                raise ValueError("status bounds")
            for key in ("positions", "model_pnl"):
                if not isinstance(raw_status.get(key), dict) or len(raw_status[key]) > 5000:
                    raise ValueError("status collection bounds")
            _json_budget(raw_status, 1024 * 1024)
            if len(json.dumps(raw_status, allow_nan=False)) > 1024 * 1024:
                raise ValueError("status byte bounds")
            daemon_status = copy.deepcopy(raw_status)
        workers = []
        workers_available = service is not None
        if service is not None:
            try:
                raw = service.list_active_workers(timeout_seconds=60)
                if not isinstance(raw, list) or len(raw) > 5000:
                    raise ValueError("worker bounds")
                workers = [WorkerStatus.model_validate({k: v for k, v in w.items() if k != "metadata"}) for w in raw]
            except Exception as error:
                logger.warning("Failed to query active workers: %s", redact_market_data_error(error))
                workers_available = False
        daemon_status.update(active_workers=len(workers), workers=workers, workers_available=workers_available)
        return ExecutionStatus.model_validate(daemon_status).model_dump(mode="json")
    except Exception as error:
        raise HTTPException(424, "EXECUTION_STATUS_INVALID") from error


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


@router.get("/blotter", response_model=BlotterResponse)
def get_execution_blotter(
    limit: int = Query(default=100, ge=1, le=5000),
    as_of: str | None = Query(default=None, max_length=64),
) -> BlotterResponse:
    envelope, records = _snapshot(as_of)
    _families(records)
    items = [_blotter_item(row) for row in records[-limit:]]
    return BlotterResponse(**envelope, orders=items, count=len(items))


def _families(records: list[ExecutionRecord]) -> tuple[list[tuple[ExecutionRecord, list[ExecutionRecord]]], list[ExecutionRecord]]:
    indexed = {row.order_id: row for row in records}
    children: dict[str, list[ExecutionRecord]] = {}
    for row in records:
        if row.parent_order_id is not None:
            parent = indexed.get(row.parent_order_id)
            if parent is None or parent.parent_order_id is not None:
                raise ValueError("orphan or nested parent")
            if (row.symbol, row.side, row.algo_type) != (parent.symbol, parent.side, parent.algo_type):
                raise ValueError("child differs from parent")
            if row.execution_ts < parent.execution_ts:
                raise ValueError("child precedes parent")
            children.setdefault(row.parent_order_id, []).append(row)
    families = []
    for parent_id, slices in children.items():
        slices.sort(key=lambda row: row.sequence)
        parent = indexed[parent_id]
        if len({row.sequence for row in slices}) != len(slices):
            raise ValueError("duplicate sequence")
        if sum(row.quantity for row in slices) > parent.quantity:
            raise ValueError("child target exceeds parent")
        if sum(row.filled for row in slices) > parent.quantity:
            raise ValueError("child fills exceed parent")
        families.append((parent, slices))
    standalone = [row for row in records if row.parent_order_id is None and row.order_id not in children]
    return families, standalone


@router.get("/timeline", response_model=TimelineResponse)
def get_execution_timeline(as_of: str | None = Query(default=None, max_length=64)) -> TimelineResponse:
    envelope, records = _snapshot(as_of)
    families, standalone = _families(records)
    parents = []
    for parent, slices in families:
        filled = sum(row.filled for row in slices)
        parents.append(TimelineParent(
            parent_order_id=parent.order_id, symbol=parent.symbol, side=parent.side,
            algo_type=parent.algo_type, target_qty=parent.quantity, filled_qty=filled,
            completion_pct=filled / parent.quantity * 100 if parent.quantity else None,
            sequence_complete=[row.sequence for row in slices] == list(range(len(slices))),
            slices=[_blotter_item(row) for row in slices]))
    return TimelineResponse(**envelope, parents=parents, standalone=[_blotter_item(row) for row in standalone])


@router.get("/routing-diagnostics", response_model=RoutingResponse)
def get_routing_diagnostics(as_of: str | None = Query(default=None, max_length=64)) -> RoutingResponse:
    envelope, records = _snapshot(as_of)
    families, standalone = _families(records)
    leaves = standalone + [row for _, slices in families for row in slices]
    active = [row for row in records if row.state in {"PENDING", "ROUTING", "PARTIALLY_FILLED"}]
    routers = []
    for broker in sorted({row.broker for row in leaves}):
        orders = [row for row in leaves if row.broker == broker]
        routers.append(RouterDiagnostic(
            broker=broker, fill_rate_pct=sum(row.state == "FILLED" for row in orders) / len(orders) * 100,
            rejection_rate_pct=sum(row.state == "REJECTED" for row in orders) / len(orders) * 100,
            active_routes=sum(row in active for row in orders)))
    return RoutingResponse(**envelope, total_active_orders=sum(row.parent_order_id is None for row in active),
                           total_active_slices=sum(row.parent_order_id is not None for row in active), routers=routers)


@router.get("/slippage-distribution", response_model=SlippageResponse)
def get_slippage_distribution(as_of: str | None = Query(default=None, max_length=64)) -> SlippageResponse:
    envelope, records = _snapshot(as_of)
    families, standalone = _families(records)
    leaves = standalone + [row for _, slices in families for row in slices]
    points = []
    excluded = 0
    for row in leaves:
        if not row.filled:
            continue
        # total_cost_vnd includes estimated impact; it is not an explicit fee.
        if row.arrival_price is None or row.fee_vnd is None:
            excluded += 1
            continue
        notional = row.arrival_price * row.filled
        if not math.isfinite(notional) or not 0 < notional <= 1e12:
            raise ValueError("arrival notional bounds")
        bps = ((1 if row.side == "BUY" else -1) * (row.executed_price - row.arrival_price)
               / row.arrival_price + row.fee_vnd / notional) * 10000
        points.append(SlippagePoint(order_id=row.order_id, venue=row.venue, side=row.side,
                                    quantity=row.filled, arrival_price=row.arrival_price,
                                    executed_price=row.executed_price, fee_vnd=row.fee_vnd, slippage_bps=bps))
    venues = []
    for venue in sorted({point.venue for point in points}):
        selected = [point for point in points if point.venue == venue]
        total = sum(point.arrival_price * point.quantity for point in selected)
        average = sum(point.slippage_bps * (point.arrival_price * point.quantity / total) for point in selected)
        venues.append(VenueSlippage(venue=venue, count=len(selected), arrival_notional_vnd=total,
                                   average_slippage_bps=average))
    return SlippageResponse(**envelope, points=points, venues=venues, excluded_missing_benchmark_or_fee=excluded)


def _settlement_forecast(trade_at: datetime) -> tuple[datetime, list[str]]:
    day = trade_at.astimezone(_ICT).date()
    if not VNTradingCalendar.is_trading_day(datetime.combine(day, time(), _ICT)):
        raise ValueError("trade on closed day")
    skipped = []
    remaining = 2
    # ponytail: bounded T+2 forecast, not broker confirmation or an intraday SLA.
    for _ in range(32):
        day += timedelta(days=1)
        if VNTradingCalendar.is_trading_day(datetime.combine(day, time(), _ICT)):
            remaining -= 1
            if remaining == 0:
                return datetime.combine(day, time(15, 30), _ICT).astimezone(timezone.utc), skipped
        else:
            skipped.append(day.isoformat())
    raise ValueError("settlement calendar unavailable")


@router.get("/settlement-timeline", response_model=SettlementResponse)
def get_settlement_timeline(as_of: str | None = Query(default=None, max_length=64)) -> SettlementResponse:
    envelope, records = _snapshot(as_of)
    families, standalone = _families(records)
    leaves = standalone + [row for _, slices in families for row in slices]
    items = []
    cutoff = envelope["effective_cutoff"]
    for row in leaves:
        if not row.filled:
            continue
        expected, skipped = _settlement_forecast(row.execution_ts)
        confirmation = row.confirmation_available_at
        confirmed = confirmation is not None and confirmation <= cutoff
        if confirmed:
            broker_at, settled_at = row.broker_effective_at, row.settlement_effective_at
            if broker_at is None or settled_at is None or not row.execution_ts <= broker_at <= confirmation or not expected <= settled_at <= confirmation:
                raise ValueError("invalid settlement confirmation")
            if not VNTradingCalendar.is_trading_day(settled_at.astimezone(_ICT)) or not VNTradingCalendar.is_trading_day(broker_at.astimezone(_ICT)):
                raise ValueError("confirmation effective on closed day")
            if row.cash_available_vnd is None or row.shares_available is None:
                raise ValueError("confirmed amounts required")
            if row.shares_available > row.filled or (row.side == "BUY" and row.cash_available_vnd != 0) or (row.side == "SELL" and row.shares_available != 0):
                raise ValueError("availability side mismatch")
        items.append(SettlementItem(
            order_id=row.order_id, broker=row.broker, symbol=row.symbol, side=row.side, trade_at=row.execution_ts,
            expected_settlement_at=expected, skipped_closed_dates=skipped, confirmed=confirmed,
            broker_effective_at=row.broker_effective_at if confirmed else None,
            settlement_effective_at=row.settlement_effective_at if confirmed else None,
            confirmation_available_at=confirmation if confirmed else None,
            cash_available_vnd=row.cash_available_vnd if confirmed else None,
            shares_available=row.shares_available if confirmed else None))
    return SettlementResponse(**envelope, settlements=items)
