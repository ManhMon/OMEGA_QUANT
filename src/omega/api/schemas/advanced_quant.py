"""Strict shared contracts for advanced-quant API boundaries."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be ISO 8601") from error
    return value


def _finite(value: float) -> float:
    if not math.isfinite(value) or abs(value) > 1e12:
        raise ValueError("value must be finite and abs(value) <= 1e12")
    return value


AwareUtcDateTime = Annotated[datetime, BeforeValidator(_parse_datetime), AfterValidator(_aware_utc)]
FiniteFloat = Annotated[float, AfterValidator(_finite)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class JobStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD_LETTERED = "DEAD_LETTERED"


class GovernorMode(str, Enum):
    MANUAL = "MANUAL"
    COPILOT = "COPILOT"


class DatasetRefRequest(StrictApiModel):
    dataset_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]
    dataset_version: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


class PitWindowRequest(StrictApiModel):
    start_date: date
    end_date: date
    as_of_time: AwareUtcDateTime
    pit_cutoff: AwareUtcDateTime | None = None

    @model_validator(mode="after")
    def validate_ordering(self) -> "PitWindowRequest":
        cutoff = self.pit_cutoff or self.as_of_time
        if self.start_date > self.end_date or self.end_date > self.as_of_time.date():
            raise ValueError("start_date <= end_date <= local date(as_of_time) required")
        if cutoff > self.as_of_time:
            raise ValueError("pit_cutoff must not exceed as_of_time")
        if self.as_of_time > datetime.now(timezone.utc) + timedelta(seconds=60):
            raise ValueError("as_of_time exceeds server clock tolerance")
        return self


class ProvenanceEnvelope(StrictApiModel):
    source: Annotated[str, Field(min_length=1, max_length=128)]
    dataset_id: Annotated[str, Field(min_length=1, max_length=128)]
    dataset_version: Annotated[str, Field(min_length=1, max_length=64)]
    as_of: AwareUtcDateTime
    computed_at: AwareUtcDateTime
    requested_pit_cutoff: AwareUtcDateTime | None = None
    effective_cutoff: AwareUtcDateTime
    input_timezone: Annotated[str, Field(min_length=1, max_length=64)]
    normalized_timezone: Literal["UTC"] = "UTC"
    cutoff_resolution: Literal["REQUESTED", "AS_OF_DEFAULT"]
    max_included_available_at: AwareUtcDateTime | None = None
    excluded_future_rows: Annotated[int, Field(ge=0)] = 0
    content_hash: Sha256
    artifact_uri: str | None = None
    is_synthetic: Literal[False] = False

    @model_validator(mode="after")
    def validate_pit(self) -> "ProvenanceEnvelope":
        if self.effective_cutoff > self.as_of:
            raise ValueError("effective_cutoff must not exceed as_of")
        if self.max_included_available_at and self.max_included_available_at > self.effective_cutoff:
            raise ValueError("included data exceeds effective_cutoff")
        return self


class ErrorEnvelope(StrictApiModel):
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
    message: Annotated[str, Field(min_length=1, max_length=512)]
    request_id: Annotated[str, Field(min_length=1, max_length=128)]
    retryable: bool
    details: dict[str, Any] | None = None
    timestamp: AwareUtcDateTime


class JobSubmitRequest(StrictApiModel):
    task_type: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
    payload: dict[str, Any]
    pit_cutoff: AwareUtcDateTime
    max_attempts: Annotated[int, Field(ge=1, le=10)] = 3

    @model_validator(mode="after")
    def validate_submission(self) -> "JobSubmitRequest":
        if self.pit_cutoff > datetime.now(timezone.utc):
            raise ValueError("pit_cutoff cannot exceed current server time")

        # Enforce payload size bound <= 512 KiB (524,288 bytes)
        payload_bytes = json.dumps(self.payload, allow_nan=False).encode("utf-8")
        if len(payload_bytes) > 512 * 1024:
            raise ValueError("payload size exceeds maximum limit of 512 KiB")
        return self


class JobAcceptedResponse(StrictApiModel):
    job_id: UUID
    status: Literal["QUEUED"]
    job_url: str
    stream_url: str
    request_id: str
    submitted_at: AwareUtcDateTime
    request_sha256: Sha256


class JobEventResponse(StrictApiModel):
    event_id: int
    job_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: AwareUtcDateTime


class JobStatusResponse(StrictApiModel):
    job_id: UUID
    task_type: str
    status: JobStatus
    progress_pct: Annotated[FiniteFloat, Field(ge=0, le=100)]
    stage: str
    message: str
    submitted_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    pit_cutoff: AwareUtcDateTime
    request_sha256: Sha256
    attempt_count: Annotated[int, Field(ge=0)]
    max_attempts: Annotated[int, Field(ge=1)]
    result: dict[str, Any] | None = None
    error: ErrorEnvelope | None = None


class JobCancelResponse(StrictApiModel):
    job_id: UUID
    status: JobStatus
    cancellation_requested_at: AwareUtcDateTime


class ResourceGovernorPolicy(StrictApiModel):
    mode: GovernorMode
    target_concurrency: Annotated[int, Field(gt=0)]
    thread_pool_size: Annotated[int, Field(gt=0)]
    batch_size: Annotated[int, Field(gt=0)]
    version: Annotated[int, Field(ge=1)] = 1


# Phase 2 Advanced Quant Request & Response Schemas

class MarketImpactRequest(StrictApiModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]
    order_size: Annotated[FiniteFloat, Field(gt=0)]
    average_daily_volume: Annotated[FiniteFloat, Field(gt=0)]
    volatility: Annotated[FiniteFloat, Field(gt=0, le=1)] = 0.02
    participation_rate: Annotated[FiniteFloat, Field(gt=0, le=1)] = 0.10
    arrival_price: Annotated[FiniteFloat, Field(gt=1000)] = 50000.0
    impact_coefficient: Annotated[FiniteFloat, Field(gt=0, le=5)] = 0.25


class FracDiffRequest(StrictApiModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]
    d: Annotated[FiniteFloat, Field(ge=0.0, le=2.0)] = 0.4
    window: Annotated[int, Field(ge=4, le=512)] = 32
    limit: Annotated[int, Field(ge=10, le=2000)] = 300


class CircuitBreakerStatusRequest(StrictApiModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    portfolio_value: Annotated[FiniteFloat, Field(gt=0)] = 1000000000.0


class StressTestSimulateRequest(StrictApiModel):
    portfolio_weights: dict[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")], Annotated[FiniteFloat, Field(ge=0, le=1)]]
    market_shock_pct: Annotated[FiniteFloat, Field(ge=-50.0, le=50.0)] = -7.0
    volatility_shock_multiplier: Annotated[FiniteFloat, Field(ge=0.5, le=10.0)] = 1.5
    include_contagion: bool = True


class LiquidityStressValidateRequest(StrictApiModel):
    positions: dict[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")], Annotated[FiniteFloat, Field(gt=0)]]
    max_adv_participation: Annotated[FiniteFloat, Field(gt=0, le=1)] = 0.10
    max_exit_days: Annotated[int, Field(ge=1, le=30)] = 3
    market_impact_coefficient: Annotated[FiniteFloat, Field(gt=0, le=2.0)] = 0.25


# Phase 2 Strict Response Schemas

class VpinHistoryPoint(StrictApiModel):
    time: Annotated[str, Field(min_length=1, max_length=32)]
    vpin: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    buy_volume: Annotated[FiniteFloat, Field(ge=0.0)]
    sell_volume: Annotated[FiniteFloat, Field(ge=0.0)]
    price: Annotated[FiniteFloat, Field(gt=0.0)]


class VpinResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    vpin: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    toxicity_level: Literal["LOW", "MODERATE", "HIGH", "TOXIC"]
    bucket_volume: Annotated[FiniteFloat, Field(ge=0.0)]
    n_buckets: Annotated[int, Field(ge=1)]
    history: list[VpinHistoryPoint]
    current_imbalance: FiniteFloat
    provenance: ProvenanceEnvelope | None = None


class DepthLadderLevel(StrictApiModel):
    level: Annotated[int, Field(ge=1)]
    price: Annotated[FiniteFloat, Field(gt=0.0)]
    volume: Annotated[FiniteFloat, Field(ge=0.0)]
    cumulative_volume: Annotated[FiniteFloat, Field(ge=0.0)]
    orders: Annotated[int, Field(ge=1)]


class OrderbookDepthResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    depth_levels: Annotated[int, Field(ge=1)]
    mid_price: Annotated[FiniteFloat, Field(gt=0.0)]
    spread: Annotated[FiniteFloat, Field(ge=0.0)]
    spread_bps: Annotated[FiniteFloat, Field(ge=0.0)]
    total_bid_depth: Annotated[FiniteFloat, Field(ge=0.0)]
    total_ask_depth: Annotated[FiniteFloat, Field(ge=0.0)]
    obi: Annotated[FiniteFloat, Field(ge=-1.0, le=1.0)]
    bids: list[DepthLadderLevel]
    asks: list[DepthLadderLevel]
    provenance: ProvenanceEnvelope | None = None


class ImpactCurvePoint(StrictApiModel):
    participation_rate: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    impact_bps: Annotated[FiniteFloat, Field(ge=0.0)]
    estimated_cost_vnd: Annotated[FiniteFloat, Field(ge=0.0)]


class MarketImpactResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    order_size: Annotated[FiniteFloat, Field(gt=0.0)]
    average_daily_volume: Annotated[FiniteFloat, Field(gt=0.0)]
    volatility: Annotated[FiniteFloat, Field(gt=0.0, le=1.0)]
    arrival_price: Annotated[FiniteFloat, Field(gt=1000.0)]
    impact_coefficient: Annotated[FiniteFloat, Field(gt=0.0, le=5.0)]
    point_impact_bps: Annotated[FiniteFloat, Field(ge=0.0)]
    point_cost_vnd: Annotated[FiniteFloat, Field(ge=0.0)]
    kyle_lambda: FiniteFloat | None = None
    amihud_illiquidity: FiniteFloat | None = None
    curve: list[ImpactCurvePoint]
    provenance: ProvenanceEnvelope | None = None


class FracDiffSeriesPoint(StrictApiModel):
    time: Annotated[str, Field(min_length=1, max_length=32)]
    close: Annotated[FiniteFloat, Field(gt=0.0)]
    frac_diff: FiniteFloat | None = None


class FracDiffResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    d: Annotated[FiniteFloat, Field(ge=0.0, le=2.0)]
    window: Annotated[int, Field(ge=4, le=512)]
    memory_retention_score: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    correlation_with_raw: FiniteFloat
    weights: list[FiniteFloat]
    series: list[FracDiffSeriesPoint]
    provenance: ProvenanceEnvelope | None = None


class CircuitBreakerDeriskInfo(StrictApiModel):
    target_multiplier: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    reason: Annotated[str, Field(min_length=1, max_length=128)]


class CircuitBreakerLimitLockInfo(StrictApiModel):
    is_locked: bool
    lock_type: Annotated[str, Field(min_length=1, max_length=32)]
    can_buy: bool
    can_sell: bool


class CircuitBreakerStatusResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    as_of: Annotated[str, Field(min_length=1, max_length=64)]
    is_safe: bool
    var_95_pct: FiniteFloat
    cvar_95_pct: FiniteFloat
    var_breached: bool
    cvar_breached: bool
    action: Annotated[str, Field(min_length=1, max_length=64)]
    derisk: CircuitBreakerDeriskInfo
    limit_lock: CircuitBreakerLimitLockInfo
    provenance: ProvenanceEnvelope | None = None


class StressScenarioResult(StrictApiModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    market_shock: FiniteFloat
    portfolio_impact_pct: FiniteFloat
    severity: Annotated[str, Field(min_length=1, max_length=32)]


class StressSimulationResponse(StrictApiModel):
    status: Literal["success"] = "success"
    timestamp: Annotated[str, Field(min_length=1, max_length=64)]
    weights_evaluated: dict[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")], FiniteFloat]
    average_loss_pct: FiniteFloat
    scenarios: list[StressScenarioResult]
    recommendation: Annotated[str, Field(min_length=1, max_length=256)]
    provenance: ProvenanceEnvelope | None = None


class ContagionNode(StrictApiModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    type: Annotated[str, Field(min_length=1, max_length=32)]
    stress: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    sri: FiniteFloat | None = None
    weight: FiniteFloat | None = None


class ContagionEdge(StrictApiModel):
    source: Annotated[str, Field(min_length=1, max_length=64)]
    target: Annotated[str, Field(min_length=1, max_length=64)]
    correlation: FiniteFloat
    transmission_bps: FiniteFloat


class ContagionGraphResponse(StrictApiModel):
    status: Literal["success"] = "success"
    is_safe: bool
    stress_level: Literal["GREEN", "YELLOW", "RED"]
    risk_multiplier: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    dominant_source: Annotated[str, Field(min_length=1, max_length=64)]
    narrative: Annotated[str, Field(min_length=1, max_length=512)]
    nodes: list[ContagionNode]
    edges: list[ContagionEdge]
    provenance: ProvenanceEnvelope | None = None


class LiquidityBreakdownItem(StrictApiModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    quantity: Annotated[FiniteFloat, Field(gt=0.0)]
    adv: Annotated[FiniteFloat, Field(gt=0.0)]
    exit_days: Annotated[FiniteFloat, Field(ge=0.0)]
    exceeds_limit: bool


class LiquidityConstraintResponse(StrictApiModel):
    status: Literal["success"] = "success"
    is_safe: bool
    max_exit_days: Annotated[FiniteFloat, Field(ge=0.0)]
    total_impact_bps: Annotated[FiniteFloat, Field(ge=0.0)]
    at_risk_symbols: list[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]]
    violation_message: Annotated[str, Field(min_length=1, max_length=512)]
    breakdown: list[LiquidityBreakdownItem]
    provenance: ProvenanceEnvelope | None = None


class CorporateGraphNode(StrictApiModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    category: Annotated[str, Field(min_length=1, max_length=64)]
    sector: Annotated[str, Field(min_length=1, max_length=128)]
    ownership_pct: Annotated[FiniteFloat, Field(ge=0.0, le=100.0)]
    role: Annotated[str, Field(min_length=1, max_length=128)]


class CorporateGraphEdge(StrictApiModel):
    source: Annotated[str, Field(min_length=1, max_length=64)]
    target: Annotated[str, Field(min_length=1, max_length=64)]
    relation: Annotated[str, Field(min_length=1, max_length=64)]
    weight: Annotated[FiniteFloat, Field(ge=0.0, le=100.0)]
    label: Annotated[str, Field(min_length=1, max_length=128)]


class CorporateGraphResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    sector: Annotated[str, Field(min_length=1, max_length=128)]
    nodes_count: Annotated[int, Field(ge=1)]
    edges_count: Annotated[int, Field(ge=0)]
    nodes: list[CorporateGraphNode]
    edges: list[CorporateGraphEdge]
    provenance: ProvenanceEnvelope | None = None

