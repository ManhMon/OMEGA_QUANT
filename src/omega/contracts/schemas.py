"""Typed OMEGA_QUANT boundary contracts.

The module intentionally uses only dataclasses and typing so these schemas can
sit at IPC/API boundaries without adding runtime dependencies.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


TaskStatus = Literal[
    "CREATED",
    "QUEUED",
    "PLANNED",
    "DISPATCHED",
    "RUNNING",
    "WAITING",
    "VERIFYING",
    "REVIEWING",
    "RISK_CHECK",
    "APPROVED",
    "DEPLOYED",
    "MONITORING",
    "ARCHIVED",
    "FAILED",
    "RETRYING",
    "FALLBACK",
    "ESCALATED",
    "ABORTED",
]
TaskType = Literal[
    "planning",
    "architecture",
    "coding",
    "research",
    "feature_engineering",
    "model_training",
    "backtesting",
    "risk_review",
    "security_review",
    "test",
    "deployment",
    "monitoring",
    "recovery",
    "evolution",
]
EventSeverity = Literal["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"]
OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "MP", "ATO", "ATC"]
OrderStatus = Literal[
    "PENDING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
]
DeploymentState = Literal[
    "draft",
    "trained",
    "validated",
    "staged",
    "approved",
    "deployed",
    "retired",
    "rolled_back",
]
ArtifactType = Literal[
    "trained_model",
    "feature_schema",
    "backtest_report",
    "risk_report",
    "deployment_bundle",
    "memory_snapshot",
    "experiment_summary",
]
ArtifactStatus = Literal["created", "validated", "archived"]

TASK_STATUSES: tuple[str, ...] = (
    "CREATED",
    "QUEUED",
    "PLANNED",
    "DISPATCHED",
    "RUNNING",
    "WAITING",
    "VERIFYING",
    "REVIEWING",
    "RISK_CHECK",
    "APPROVED",
    "DEPLOYED",
    "MONITORING",
    "ARCHIVED",
    "FAILED",
    "RETRYING",
    "FALLBACK",
    "ESCALATED",
    "ABORTED",
)
TASK_TYPES: tuple[str, ...] = (
    "planning",
    "architecture",
    "coding",
    "research",
    "feature_engineering",
    "model_training",
    "backtesting",
    "risk_review",
    "security_review",
    "test",
    "deployment",
    "monitoring",
    "recovery",
    "evolution",
)
EVENT_SEVERITIES: tuple[str, ...] = (
    "DEBUG",
    "INFO",
    "WARN",
    "WARNING",
    "ERROR",
    "CRITICAL",
)
ORDER_SIDES: tuple[str, ...] = ("BUY", "SELL")
ORDER_TYPES: tuple[str, ...] = ("MARKET", "LIMIT", "MP", "ATO", "ATC")
ORDER_STATUSES: tuple[str, ...] = (
    "PENDING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
)
DEPLOYMENT_STATES: tuple[str, ...] = (
    "draft",
    "trained",
    "validated",
    "staged",
    "approved",
    "deployed",
    "retired",
    "rolled_back",
)
ARTIFACT_TYPES: tuple[str, ...] = (
    "trained_model",
    "feature_schema",
    "backtest_report",
    "risk_report",
    "deployment_bundle",
    "memory_snapshot",
    "experiment_summary",
)
ARTIFACT_STATUSES: tuple[str, ...] = ("created", "validated", "archived")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


def _validate_in(value: str, allowed: tuple[str, ...], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}: {value}")


@dataclass(kw_only=True)
class TaskContract:
    """Task schema from spec Sections 4.1-4.5 and API Task contract."""

    task_id: str
    parent_task_id: Optional[str] = None
    task_type: TaskType
    priority: int
    status: TaskStatus
    created_at: str
    updated_at: str
    owner_agent: str
    required_context: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    timeout_policy: Dict[str, Any] = field(default_factory=dict)
    resource_budget: Dict[str, Any] = field(default_factory=dict)
    artifact_refs: List[str] = field(default_factory=list)
    audit_ref: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.owner_agent, "owner_agent")
        _require_non_empty(self.created_at, "created_at")
        _require_non_empty(self.updated_at, "updated_at")
        _validate_in(self.task_type, TASK_TYPES, "task_type")
        _validate_in(self.status, TASK_STATUSES, "status")
        if not 1 <= self.priority <= 10:
            raise ValueError("priority must be between 1 and 10")
        if not self.retry_policy:
            raise ValueError("retry_policy must be defined")
        if not self.timeout_policy:
            raise ValueError("timeout_policy must be defined")


@dataclass(kw_only=True)
class EventContract:
    """Event and IPC schema from spec Sections 5.1-5.4."""

    event_id: str
    event_type: str
    event_version: str
    timestamp: str
    source: str
    target: str
    correlation_id: str
    causation_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str
    severity: EventSeverity
    producer: str = ""
    consumer: str = ""
    delivery_guarantee: str = ""
    ordering_guarantee: str = ""
    idempotency_rule: str = ""
    retry_rule: str = ""
    dead_letter_rule: str = ""
    schema_evolution_rule: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "event_type",
            "event_version",
            "timestamp",
            "source",
            "correlation_id",
            "trace_id",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _validate_in(self.severity, EVENT_SEVERITIES, "severity")


@dataclass(kw_only=True)
class OrderContract:
    """Execution order schema from spec Section 10 and Execution API."""

    order_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: Optional[float]
    time_in_force: str
    status: OrderStatus
    created_at: str
    updated_at: str
    execution_ref: str
    pre_trade_risk_ref: str = ""
    kill_switch_checked: bool = False
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    reconciliation_ref: str = ""
    audit_ref: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "order_id",
            "strategy_id",
            "symbol",
            "time_in_force",
            "created_at",
            "updated_at",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _validate_in(self.side, ORDER_SIDES, "side")
        _validate_in(self.order_type, ORDER_TYPES, "order_type")
        _validate_in(self.status, ORDER_STATUSES, "status")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")


@dataclass(kw_only=True)
class DatasetContract:
    """Dataset registry schema from spec Section 6.3 and Dataset API."""

    dataset_id: str
    name: str
    source: str
    frequency: str
    schema_version: str
    provenance: Dict[str, Any]
    timestamp_semantics: str
    quality_score: float
    retention_policy: Dict[str, Any]
    version: str
    checksum: str
    lineage: List[str] = field(default_factory=list)
    frozen: bool = False
    quality_report_ref: str = ""
    audit_ref: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_id",
            "name",
            "source",
            "frequency",
            "schema_version",
            "timestamp_semantics",
            "version",
            "checksum",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between 0.0 and 1.0")


@dataclass(kw_only=True)
class ModelContract:
    """Model registry version schema from spec Section 6.4 and Model API."""

    model_id: str
    version: str
    training_data_ref: str
    feature_set_ref: str
    training_config: Dict[str, Any]
    evaluation_metrics: Dict[str, float]
    deployment_state: DeploymentState
    rollback_ref: Optional[str]
    created_by: str
    approved_by: Optional[str]
    lineage: List[str] = field(default_factory=list)
    artifact_refs: List[str] = field(default_factory=list)
    audit_ref: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "model_id",
            "version",
            "training_data_ref",
            "feature_set_ref",
            "created_by",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _validate_in(
            self.deployment_state,
            DEPLOYMENT_STATES,
            "deployment_state",
        )
        if self.deployment_state in ("approved", "deployed"):
            _require_non_empty(self.approved_by or "", "approved_by")


@dataclass(kw_only=True)
class ArtifactContract:
    """Artifact store schema from spec Section 6.5 and Artifact API."""

    artifact_id: str
    artifact_type: ArtifactType
    checksum: str
    version: str
    owner: str
    created_at: str
    linked_task_id: str
    reproducibility_metadata: Dict[str, Any]
    name: str = ""
    storage_uri: str = ""
    status: ArtifactStatus = "created"
    validation_ref: str = ""
    archived_at: Optional[str] = None
    audit_ref: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "artifact_id",
            "checksum",
            "version",
            "owner",
            "created_at",
            "linked_task_id",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _validate_in(self.artifact_type, ARTIFACT_TYPES, "artifact_type")
        _validate_in(self.status, ARTIFACT_STATUSES, "status")


@dataclass(kw_only=True)
class ErrorContract:
    """Structured API error schema from spec Section 21.3."""

    error_code: str
    error_type: str
    severity: EventSeverity
    retryable: bool
    message: str
    trace_id: str
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "error_code",
            "error_type",
            "message",
            "trace_id",
            "timestamp",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _validate_in(self.severity, EVENT_SEVERITIES, "severity")


__all__ = [
    "ArtifactContract",
    "ArtifactStatus",
    "ArtifactType",
    "DatasetContract",
    "DeploymentState",
    "ErrorContract",
    "EventContract",
    "EventSeverity",
    "OrderContract",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "TaskContract",
    "TaskStatus",
    "TaskType",
]
