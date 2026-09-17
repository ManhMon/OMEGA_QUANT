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
        if cutoff.astimezone(timezone.utc) > self.as_of_time.astimezone(timezone.utc):
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
        if self.effective_cutoff.astimezone(timezone.utc) > self.as_of.astimezone(timezone.utc):
            raise ValueError("effective_cutoff must not exceed as_of")
        if self.max_included_available_at and self.max_included_available_at.astimezone(timezone.utc) > self.effective_cutoff.astimezone(timezone.utc):
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


# Phase 4 Model Governance & Resource Governor Schemas

ModelCategory = Literal[
    "DEEP_LEARNING",
    "MACHINE_LEARNING",
    "ALPHA",
    "RISK_EXECUTION",
    "LLM",
    "HYBRID",
]

ModelLifecycleStatus = Literal["STAGING", "VALIDATED", "PRODUCTION", "ARCHIVED", "DEPRECATED"]


class ModelPITMetadata(StrictApiModel):
    train_end_date: str
    validation_start_date: str
    validation_end_date: str
    available_at: str
    effective_cutoff: str
    embargo_days: Annotated[int, Field(ge=0)] = 5


class ModelMetricProvenance(StrictApiModel):
    sharpe: FiniteFloat | None = None
    ic: FiniteFloat | None = None
    turnover: FiniteFloat | None = None
    dataset_id: str
    dataset_hash: Sha256
    oos_window: str
    computed_at: str
    artifact_checksum: Sha256
    is_synthetic: Literal[False] = False


class ModelVersionItem(StrictApiModel):
    version: Annotated[str, Field(pattern=r"^v\d+\.\d+\.\d+$")]
    status: Literal["STAGING", "VALIDATED", "PRODUCTION", "ARCHIVED", "DEPRECATED"]
    checksum: Sha256 | None = None
    artifact_path: str
    registered_at: AwareUtcDateTime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelSummaryItem(StrictApiModel):
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    model_id: str | None = None
    name: str | None = None
    category: ModelCategory = "MACHINE_LEARNING"
    framework: str | None = None
    description: str | None = None
    source_path: str | None = None
    implementation_symbol: str | None = None
    active_versions: dict[str, str | None]
    total_versions: Annotated[int, Field(ge=0)]
    latest_version: str | None = None
    last_updated: AwareUtcDateTime | None = None
    lifecycle_status: ModelLifecycleStatus = "STAGING"
    active_version: str | None = None
    is_synthetic: bool = False
    pit_metadata: ModelPITMetadata | None = None
    metric_provenance: ModelMetricProvenance | None = None


class ModelListResponse(StrictApiModel):
    status: Literal["success"] = "success"
    count: Annotated[int, Field(ge=0)]
    models: list[ModelSummaryItem]
    categories: list[ModelCategory]
    selected_category: ModelCategory | None = None
    category_counts: dict[str, int]
    provenance: ProvenanceEnvelope | None = None


class ModelVersionsResponse(StrictApiModel):
    status: Literal["success"] = "success"
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    category: ModelCategory | None = None
    framework: str | None = None
    description: str | None = None
    source_path: str | None = None
    implementation_symbol: str | None = None
    active_versions: dict[str, str | None]
    versions: list[ModelVersionItem]
    provenance: ProvenanceEnvelope | None = None


class ModelVersionDetailResponse(StrictApiModel):
    status: Literal["success"] = "success"
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    category: ModelCategory | None = None
    framework: str | None = None
    description: str | None = None
    source_path: str | None = None
    implementation_symbol: str | None = None
    version: Annotated[str, Field(pattern=r"^v\d+\.\d+\.\d+$")]
    version_info: ModelVersionItem
    provenance: ProvenanceEnvelope | None = None


class DriftMetricItem(StrictApiModel):
    metric_name: Annotated[str, Field(min_length=1, max_length=64)]
    baseline_value: FiniteFloat
    current_value: FiniteFloat
    drift_detected: bool
    threshold: FiniteFloat
    p_value: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)] | None = None


class ModelDriftResponse(StrictApiModel):
    status: Literal["success"] = "success"
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    active_version: str | None = None
    drift_detected: bool
    drift_level: Literal["LOW", "MODERATE", "CRITICAL", "NONE"]
    drift_score: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    evaluated_at: AwareUtcDateTime
    metrics: list[DriftMetricItem]
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceEnvelope | None = None


class ModelPromoteRequest(StrictApiModel):
    totp_code: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]
    target_status: Literal["VALIDATED", "PRODUCTION"]
    promoter_id: Annotated[str, Field(min_length=1, max_length=128)] = "OPERATOR_CHIEF_QUANT"
    rationale: Annotated[str, Field(min_length=1, max_length=512)] = "Institutional grade validation criteria satisfied"
    pit_evidence: dict[str, Any] | None = None


class ModelPromoteResponse(StrictApiModel):
    status: Literal["success"] = "success"
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    version: Annotated[str, Field(pattern=r"^v\d+\.\d+\.\d+$")]
    target_status: Literal["VALIDATED", "PRODUCTION"]
    totp_verified: bool
    promoted_at: AwareUtcDateTime
    message: str
    provenance: ProvenanceEnvelope | None = None


class ModelRollbackRequest(StrictApiModel):
    totp_code: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]
    target_version: Annotated[str, Field(pattern=r"^v\d+\.\d+\.\d+$")]
    reason: Annotated[str, Field(min_length=1, max_length=512)] = "Emergency rollback due to performance drift"


class ModelRollbackResponse(StrictApiModel):
    status: Literal["success"] = "success"
    model_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
    target_version: Annotated[str, Field(pattern=r"^v\d+\.\d+\.\d+$")]
    totp_verified: bool
    rolled_back_at: AwareUtcDateTime
    previous_active_version: str | None = None
    message: str
    provenance: ProvenanceEnvelope | None = None


class ResourceGovernorPolicyUpdateRequest(StrictApiModel):
    mode: Literal["MANUAL", "COPILOT"] | GovernorMode | None = None
    target_concurrency: Annotated[int, Field(ge=1, le=128)] | None = None
    thread_pool_size: Annotated[int, Field(ge=1, le=256)] | None = None
    batch_size: Annotated[int, Field(ge=1, le=10000)] | None = None


class ResourceGovernorStateResponse(StrictApiModel):
    status: Literal["success"] = "success"
    mode: GovernorMode
    target_concurrency: Annotated[int, Field(ge=1)]
    thread_pool_size: Annotated[int, Field(ge=1)]
    batch_size: Annotated[int, Field(ge=1)]
    version: Annotated[int, Field(ge=1)]
    active_workers: Annotated[int, Field(ge=0)]
    queue_depth: Annotated[int, Field(ge=0)]
    system_load_pct: Annotated[FiniteFloat, Field(ge=0.0, le=100.0)]
    memory_usage_mb: Annotated[FiniteFloat, Field(ge=0.0)]
    mode_description: str
    updated_at: AwareUtcDateTime
    provenance: ProvenanceEnvelope | None = None


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


# ==========================================
# Phase 3 Active Quant Engines & Discovery Schemas
# ==========================================

def _parse_date(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError("date must be ISO 8601 YYYY-MM-DD") from error
    return value


IsoDate = Annotated[date, BeforeValidator(_parse_date)]


class WalkForwardCpcvRequest(StrictApiModel):
    dataset_id: Annotated[str, Field(default="market_2015_now", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]
    universe: list[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]] = Field(
        default_factory=lambda: ["FPT", "HPG", "MBB", "MWG", "DGC", "VNM", "TCB", "PNJ"]
    )
    start_date: IsoDate = Field(default=date(2020, 1, 1))
    end_date: IsoDate = Field(default=date(2023, 12, 31))
    n_splits: Annotated[int, Field(ge=3, le=20)] = 10
    n_test_splits: Annotated[int, Field(ge=1, le=5)] = 2
    embargo_pct: Annotated[FiniteFloat, Field(ge=0.0, lt=0.5)] = 0.01
    label_horizon: Annotated[int, Field(ge=1, le=60)] = 5
    initial_capital: Annotated[FiniteFloat, Field(gt=0)] = 1_000_000_000.0
    slippage_bps: Annotated[FiniteFloat, Field(ge=0.0, le=500.0)] = 5.0
    commission_bps: Annotated[FiniteFloat, Field(ge=0.0, le=100.0)] = 1.5

    @model_validator(mode="after")
    def validate_splits_and_dates(self) -> "WalkForwardCpcvRequest":
        if self.n_test_splits >= self.n_splits:
            raise ValueError("n_test_splits must be strictly less than n_splits")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class WalkForwardFoldResult(StrictApiModel):
    fold: Annotated[int, Field(ge=0)]
    train_size: Annotated[int, Field(ge=0)]
    test_size: Annotated[int, Field(ge=0)]
    in_sample_sharpe: FiniteFloat
    out_of_sample_sharpe: FiniteFloat
    in_sample_return_pct: FiniteFloat
    out_of_sample_return_pct: FiniteFloat
    max_drawdown_pct: FiniteFloat


class WalkForwardCpcvResponse(StrictApiModel):
    status: Literal["success"] = "success"
    task_type: Literal["WALK_FORWARD_CPCV"] = "WALK_FORWARD_CPCV"
    job_id: UUID
    dataset_id: str
    n_splits: int
    n_test_splits: int
    total_folds: int
    mean_oos_sharpe: FiniteFloat
    median_oos_sharpe: FiniteFloat
    std_oos_sharpe: FiniteFloat
    mean_oos_return_pct: FiniteFloat
    worst_drawdown_pct: FiniteFloat
    pbo: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    deflated_sharpe_ratio: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    folds: list[WalkForwardFoldResult]
    provenance: ProvenanceEnvelope | None = None


class AlphaEvaluationRequest(StrictApiModel):
    expression: Annotated[str, Field(min_length=1, max_length=4096)]
    universe: Annotated[str, Field(default="VN703", min_length=1, max_length=64)] = "VN703"
    sample_data: dict[str, list[FiniteFloat]] | None = None


class AlphaEvaluationResponse(StrictApiModel):
    status: Literal["success"] = "success"
    expression: str
    is_valid: bool
    ast_type: Annotated[str, Field(min_length=1, max_length=64)]
    ic_estimate: FiniteFloat
    ir_estimate: FiniteFloat
    turnover_estimate_pct: FiniteFloat
    complexity_score: Annotated[int, Field(ge=1)]
    sample_result: list[FiniteFloat] | None = None
    error: str | None = None
    provenance: ProvenanceEnvelope | None = None


class GeneticDiscoveryRequest(StrictApiModel):
    population_size: Annotated[int, Field(ge=10, le=500)] = 50
    generations: Annotated[int, Field(ge=1, le=100)] = 10
    mutation_rate: Annotated[FiniteFloat, Field(gt=0.0, le=1.0)] = 0.15
    crossover_rate: Annotated[FiniteFloat, Field(gt=0.0, le=1.0)] = 0.75
    target_ic: Annotated[FiniteFloat, Field(gt=0.0, le=0.5)] = 0.04
    target_ir: Annotated[FiniteFloat, Field(gt=0.0, le=10.0)] = 1.5
    allowed_operators: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list)


class GeneticDiscoveryGenerationHistory(StrictApiModel):
    generation: Annotated[int, Field(ge=1)]
    max_generations: Annotated[int, Field(ge=1)]
    best_formula: Annotated[str, Field(min_length=1, max_length=1024)]
    best_fitness: FiniteFloat
    mean_fitness: FiniteFloat
    fittest_ic: FiniteFloat


class GeneticDiscoveryResponse(StrictApiModel):
    status: Literal["success"] = "success"
    job_id: UUID | Annotated[str, Field(min_length=1, max_length=64)]
    task_type: Literal["GENETIC_ALPHA_DISCOVERY"] = "GENETIC_ALPHA_DISCOVERY"
    population_size: int
    generations: int
    best_formula: Annotated[str, Field(min_length=1, max_length=1024)]
    best_fitness: FiniteFloat
    best_ic: FiniteFloat
    best_ir: FiniteFloat
    history: list[GeneticDiscoveryGenerationHistory]
    session_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    stream_url: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    message: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    provenance: ProvenanceEnvelope | None = None


class DiscoveryProgressEvent(StrictApiModel):
    session_id: Annotated[str, Field(min_length=1, max_length=64)]
    event_type: Literal["SNAPSHOT", "GENERATION_UPDATE", "DISCOVERY_COMPLETED", "PING"]
    generation: Annotated[int, Field(ge=0)]
    max_generations: Annotated[int, Field(ge=1)]
    progress: Annotated[int, Field(ge=0, le=100)]
    best_fitness: FiniteFloat
    best_formula: Annotated[str, Field(min_length=1, max_length=1024)]
    message: str | None = None
    population_sample: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: AwareUtcDateTime


class AlphaSignalItem(StrictApiModel):
    alpha_id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    category: Annotated[str, Field(min_length=1, max_length=64)]
    formula: Annotated[str, Field(min_length=1, max_length=1024)]
    ic_mean: FiniteFloat
    ir_annualized: FiniteFloat
    turnover_pct: FiniteFloat
    status: Literal["ACTIVE", "CANDIDATE", "DECAYED", "INCUBATING"]


class AlphaArsenalResponse(StrictApiModel):
    status: Literal["success"] = "success"
    total_available: Annotated[int, Field(ge=0)]
    count: Annotated[int, Field(ge=0)]
    signals: list[AlphaSignalItem]
    provenance: ProvenanceEnvelope | None = None


class DecayPoint(StrictApiModel):
    lag_days: Annotated[int, Field(ge=0)]
    ic: FiniteFloat
    ir: FiniteFloat
    correlation_decay: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]


class AlphaDecayProfileResponse(StrictApiModel):
    status: Literal["success"] = "success"
    alpha_id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    half_life_days: Annotated[int, Field(ge=1)]
    decay_regime: Annotated[str, Field(min_length=1, max_length=64)]
    profile: list[DecayPoint]
    provenance: ProvenanceEnvelope | None = None


class OverfittingDiagnosticsResponse(StrictApiModel):
    status: Literal["success"] = "success"
    strategy_id: Annotated[str, Field(min_length=1, max_length=64)]
    trials_tested: Annotated[int, Field(ge=1)]
    pbo: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    deflated_sharpe_ratio: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    observed_sharpe: FiniteFloat
    expected_max_sharpe: FiniteFloat
    variance_of_trials: FiniteFloat
    skewness: FiniteFloat
    kurtosis: FiniteFloat
    fdr_q_values: list[FiniteFloat]
    is_overfitted: bool
    verdict: Annotated[str, Field(min_length=1, max_length=128)]
    provenance: ProvenanceEnvelope | None = None


class ConformalPredictRequest(StrictApiModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    horizon_days: Annotated[int, Field(ge=1, le=60)] = 5
    confidence_levels: list[Annotated[FiniteFloat, Field(gt=0.0, lt=1.0)]] = Field(default_factory=lambda: [0.80, 0.90, 0.95])
    features: dict[str, FiniteFloat] | None = None


class ConformalInterval(StrictApiModel):
    confidence_level: Annotated[FiniteFloat, Field(gt=0.0, lt=1.0)]
    lower_price: Annotated[FiniteFloat, Field(gt=0.0)]
    upper_price: Annotated[FiniteFloat, Field(gt=0.0)]
    lower_return_pct: FiniteFloat
    upper_return_pct: FiniteFloat
    interval_width_pct: Annotated[FiniteFloat, Field(ge=0.0)]


class ConformalPredictResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    as_of: Annotated[str, Field(min_length=1, max_length=64)]
    point_forecast_price: Annotated[FiniteFloat, Field(gt=0.0)]
    point_forecast_return_pct: FiniteFloat
    regime: Annotated[str, Field(min_length=1, max_length=64)]
    liquidity_bucket: Annotated[str, Field(min_length=1, max_length=64)]
    intervals: list[ConformalInterval]
    empirical_coverage: Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]
    is_valid_mondrian: bool
    provenance: ProvenanceEnvelope | None = None


class PortfolioRebalanceExecuteRequest(StrictApiModel):
    totp_code: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]
    strategy_id: Annotated[str, Field(min_length=1, max_length=64)] = "ALPHA_HRP_V2"
    target_portfolio: dict[Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")], Annotated[FiniteFloat, Field(ge=0.0, le=1.0)]] = Field(
        default_factory=lambda: {"FPT": 0.25, "HPG": 0.25, "MBB": 0.25, "MWG": 0.25}
    )
    portfolio_value: Annotated[FiniteFloat, Field(ge=10_000_000.0)] = 1_000_000_000.0
    drift_threshold: Annotated[FiniteFloat, Field(ge=0.001, le=0.5)] = 0.01
    max_turnover: Annotated[FiniteFloat, Field(ge=0.01, le=1.0)] = 0.25
    routing_algo: Literal["TWAP", "VWAP", "POV", "DIRECT"] = "TWAP"
    duration_minutes: Annotated[int, Field(ge=5, le=480)] = 60

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "PortfolioRebalanceExecuteRequest":
        w_sum = sum(self.target_portfolio.values())
        if w_sum <= 0 or w_sum > 1.0001:
            raise ValueError("sum of target_portfolio weights must be > 0 and <= 1.0")
        return self


class RebalanceOrderItem(StrictApiModel):
    order_id: Annotated[str, Field(min_length=1, max_length=64)]
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,18}$")]
    side: Literal["BUY", "SELL", "HOLD"]
    quantity: Annotated[int, Field(ge=0)]
    price: Annotated[FiniteFloat, Field(gt=0.0)]
    estimated_notional_vnd: Annotated[FiniteFloat, Field(ge=0.0)]
    algo: Literal["TWAP", "VWAP", "POV", "DIRECT"]
    slices: Annotated[int, Field(ge=1)]
    status: Literal["QUEUED", "SUBMITTED", "EXECUTED"]


class PortfolioRebalanceExecuteResponse(StrictApiModel):
    status: Literal["success"] = "success"
    job_id: UUID
    timestamp: Annotated[str, Field(min_length=1, max_length=64)]
    totp_verified: bool
    strategy_id: str
    should_rebalance: bool
    reason: str
    estimated_turnover: Annotated[FiniteFloat, Field(ge=0.0)]
    estimated_cost_vnd: Annotated[FiniteFloat, Field(ge=0.0)]
    orders: list[RebalanceOrderItem]
    target_changes: dict[str, Any]
    liquidity_violations: list[str] | dict[str, str]
    provenance: ProvenanceEnvelope | None = None


# Phase 3: Multi-Seed Evolution, Variance Explorer & Drift Sentinel Schemas

class PitWindows(StrictApiModel):
    train_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    train_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    validation_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    validation_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    test_start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    test_end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validate_chronological_order(self) -> "PitWindows":
        d_tr_s = date.fromisoformat(self.train_start_date)
        d_tr_e = date.fromisoformat(self.train_end_date)
        d_val_s = date.fromisoformat(self.validation_start_date)
        d_val_e = date.fromisoformat(self.validation_end_date)
        d_te_s = date.fromisoformat(self.test_start_date)
        d_te_e = date.fromisoformat(self.test_end_date)

        if not (d_tr_s <= d_tr_e < d_val_s <= d_val_e < d_te_s <= d_te_e):
            raise ValueError(
                "Chronological split violation: train_start <= train_end < val_start <= val_end < test_start <= test_end required"
            )
        return self


class EvolutionRunRequest(StrictApiModel):
    dataset: Annotated[str, Field(min_length=1, max_length=256)] = "data/market_2015_now.parquet"
    pit_cutoff: AwareUtcDateTime
    strategy_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")] = "GENETIC_ALPHA_EVOLUTION"
    seeds: list[Annotated[int, Field(ge=0, le=2147483647)]] = Field(default_factory=lambda: [42, 1042, 2042, 3042, 4042])
    population: Annotated[int, Field(ge=2, le=500)] = 50
    generations: Annotated[int, Field(ge=1, le=200)] = 10
    workers: Annotated[int, Field(ge=1, le=16)] = 1
    transaction_cost_bps: Annotated[FiniteFloat, Field(ge=0.0, le=500.0)] = 25.0
    windows: PitWindows | None = None
    risk_parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evolution_params(self) -> "EvolutionRunRequest":
        if self.pit_cutoff > datetime.now(timezone.utc) + timedelta(seconds=60):
            raise ValueError("pit_cutoff cannot exceed current server time")
        if len(self.seeds) < 1 or len(self.seeds) > 32:
            raise ValueError("seeds count must be between 1 and 32")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds list must contain unique integers")
        clean_ds = self.dataset.replace("\\", "/")
        if ".." in clean_ds or clean_ds.startswith("/") or "\x00" in clean_ds:
            raise ValueError("path traversal or invalid path detected in dataset")
        if any(f in clean_ds for f in [".agents", ".gemini", ".openclaw", ".codex"]):
            raise ValueError("forbidden path reference detected in dataset")
        return self


class SeedResult(StrictApiModel):
    seed: Annotated[int, Field(ge=0)]
    status: Literal["COMPLETED", "FAILED", "SKIPPED"]
    sharpe: FiniteFloat | None = None
    ic: FiniteFloat | None = None
    max_drawdown: FiniteFloat | None = None
    turnover: FiniteFloat | None = None
    trade_count: Annotated[int, Field(ge=0)] = 0
    artifact_reference: str | None = None
    failure_code: str | None = None


class EvolutionSummary(StrictApiModel):
    status: Literal["success", "partial", "failed"] = "success"
    strategy_id: Annotated[str, Field(min_length=1, max_length=64)]
    requested_seeds: Annotated[int, Field(ge=1)]
    completed_seeds: Annotated[int, Field(ge=0)]
    failed_seeds: Annotated[int, Field(ge=0)]
    median_sharpe: FiniteFloat | None = None
    iqr_sharpe: FiniteFloat | None = None
    std_sharpe: FiniteFloat | None = None
    worst_drawdown: FiniteFloat | None = None
    median_ic: FiniteFloat | None = None
    median_turnover: FiniteFloat | None = None
    seed_results: list[SeedResult] = Field(default_factory=list)
    provenance: ProvenanceEnvelope | None = None


class DriftScheduleRequest(StrictApiModel):
    enabled: bool | None = None
    schedule: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    model_ids: list[Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]] | None = None
    thresholds: dict[str, Annotated[FiniteFloat, Field(ge=0.0, le=10.0)]] | None = None
    revision: Annotated[int, Field(ge=0)]


class DriftMonitorStatus(StrictApiModel):
    status: Literal["success"] = "success"
    enabled: bool
    schedule: Annotated[str, Field(min_length=1, max_length=64)]
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    last_run: AwareUtcDateTime | None = None
    next_run: AwareUtcDateTime | None = None
    heartbeat: AwareUtcDateTime
    evaluated_model_ids: list[str]
    missing_model_ids: list[str]
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    last_job: dict[str, Any] | None = None
    thresholds: dict[str, float]
    revision: Annotated[int, Field(ge=0)]
    provenance: ProvenanceEnvelope | None = None


class ConformalCalibrationRequest(StrictApiModel):
    model_name: Annotated[str, Field(min_length=1, max_length=64)] = "CONFORMAL_PREDICTOR"
    universe: list[Annotated[str, Field(min_length=1, max_length=16)]] = Field(default_factory=lambda: ["VN30"])
    target_coverage: Annotated[FiniteFloat, Field(gt=0.5, lt=1.0)] = 0.90
    n_splits: Annotated[int, Field(ge=2, le=20)] = 5
    n_test_splits: Annotated[int, Field(ge=1, le=5)] = 1
    embargo_pct: Annotated[FiniteFloat, Field(ge=0.0, le=0.1)] = 0.01
    label_horizon: Annotated[int, Field(ge=1, le=60)] = 1
    calib_days: Annotated[int, Field(ge=20, le=2520)] = 252
    alphas: list[Annotated[FiniteFloat, Field(gt=0.0, lt=1.0)]] = Field(default_factory=lambda: [0.5, 0.2, 0.1, 0.05])
    as_of_date: date | None = None


class MondrianGroupCoverage(StrictApiModel):
    regime: Annotated[str, Field(min_length=1, max_length=64)]
    liquidity_bucket: Annotated[str, Field(min_length=1, max_length=64)]
    sample_count: Annotated[int, Field(ge=0)]
    coverage: FiniteFloat
    mean_interval_width: FiniteFloat


class ConformalCalibrationResponse(StrictApiModel):
    status: Literal["success", "calibrated"] = "success"
    model_name: Annotated[str, Field(min_length=1, max_length=64)]
    version: Annotated[str, Field(min_length=1, max_length=64)]
    n_folds: Annotated[int, Field(ge=1)]
    total_samples: Annotated[int, Field(ge=1)]
    target_coverage: FiniteFloat
    empirical_coverage: FiniteFloat
    mean_interval_width: FiniteFloat
    alphas: list[FiniteFloat]
    quantiles: dict[str, FiniteFloat]
    group_coverages: list[MondrianGroupCoverage]
    artifact_path: Annotated[str, Field(min_length=1, max_length=256)]
    calibrated_at: AwareUtcDateTime
    pit_embargo: AwareUtcDateTime
    is_valid: bool = True
    provenance: ProvenanceEnvelope | None = None


class ConformalCalibrationStatusResponse(StrictApiModel):
    status: Literal["CALIBRATED", "NOT_CALIBRATED", "CALIBRATING", "ERROR", "data_unavailable"] = "CALIBRATED"
    model_name: Annotated[str, Field(min_length=1, max_length=64)]
    is_calibrated: bool
    last_calibrated_at: AwareUtcDateTime | None = None
    latest_version: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    target_coverage: FiniteFloat | None = None
    empirical_coverage: FiniteFloat | None = None
    mean_interval_width: FiniteFloat | None = None
    group_coverages: list[MondrianGroupCoverage] = Field(default_factory=list)
    provenance: ProvenanceEnvelope | None = None


