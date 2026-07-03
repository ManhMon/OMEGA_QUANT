"""
OMEGA_QUANT SQLAlchemy Models
Institutional-grade database schema with PIT compliance.

Version: 2.1
Status: Phase 2.1 Implementation
Compliance: V21_QUANT Institutional Grade

All models follow:
- PIT safety with as_of/available_at timestamps
- Versioning for reproducibility
- Audit trail for governance
- Vectorization-friendly design
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
import enum

from .base import Base, PITMixin, VersionedMixin


# ============================================================================
# ENUMS
# ============================================================================

class TaskStatus(str, enum.Enum):
    """Task lifecycle states."""
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNED = "PLANNED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    RISK_CHECK = "RISK_CHECK"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    MONITORING = "MONITORING"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"
    ESCALATED = "ESCALATED"
    ABORTED = "ABORTED"


class TaskType(str, enum.Enum):
    """Task types."""
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    CODING = "coding"
    RESEARCH = "research"
    FEATURE_ENGINEERING = "feature_engineering"
    MODEL_TRAINING = "model_training"
    BACKTESTING = "backtesting"
    RISK_REVIEW = "risk_review"
    SECURITY_REVIEW = "security_review"
    TEST = "test"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    RECOVERY = "recovery"
    EVOLUTION = "evolution"


class DeploymentState(str, enum.Enum):
    """Model deployment states."""
    DRAFT = "draft"
    TRAINED = "trained"
    VALIDATED = "validated"
    STAGED = "staged"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    RETIRED = "retired"
    ROLLED_BACK = "rolled_back"


class EventSeverity(str, enum.Enum):
    """Event severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ============================================================================
# CORE MODELS
# ============================================================================

class Task(Base, PITMixin):
    """
    Task model - represents a unit of work in the system.
    
    PIT Compliance:
    - as_of: When the task was conceptually created
    - available_at: When the task entered the system
    """
    __tablename__ = "tasks"
    
    # Primary key
    task_id = Column(String(64), primary_key=True, comment="Unique task identifier")
    
    # Hierarchy
    parent_task_id = Column(String(64), ForeignKey("tasks.task_id"), nullable=True,
                           comment="Parent task for hierarchical tasks")
    
    # Task metadata
    task_type = Column(SQLEnum(TaskType), nullable=False, index=True,
                      comment="Type of task")
    priority = Column(Integer, nullable=False, default=5, index=True,
                     comment="Priority level (1=highest, 10=lowest)")
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.CREATED,
                   index=True, comment="Current task status")
    
    # Ownership
    owner_agent = Column(String(128), nullable=False, index=True,
                        comment="Agent responsible for this task")
    
    # Context and constraints
    required_context = Column(JSON, nullable=True,
                             comment="Context required for task execution")
    constraints = Column(JSON, nullable=True,
                        comment="Task constraints and requirements")
    dependencies = Column(JSON, nullable=True,
                         comment="List of dependent task IDs")
    
    # Policies
    retry_policy = Column(JSON, nullable=True,
                         comment="Retry policy configuration")
    timeout_policy = Column(JSON, nullable=True,
                           comment="Timeout policy configuration")
    resource_budget = Column(JSON, nullable=True,
                            comment="Resource allocation budget")
    
    # References
    artifact_refs = Column(JSON, nullable=True,
                          comment="References to related artifacts")
    audit_ref = Column(String(64), nullable=True,
                      comment="Reference to audit log entry")
    
    # Relationships
    parent = relationship("Task", remote_side=[task_id], backref="children")
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")
    
    # Indexes and constraints
    _table_args_ = (
        Index("idx_task_status_priority", "status", "priority"),
        Index("idx_task_owner_status", "owner_agent", "status"),
        Index("idx_task_type_status", "task_type", "status"),
        Index("idx_task_as_of", "as_of"),
        Index("idx_task_available_at", "available_at"),
        CheckConstraint('priority >= 1 AND priority <= 10', name='ck_tasks_priority_range'),
    )


class TaskEvent(Base, PITMixin):
    """
    Task event log - immutable event stream for task lifecycle.
    
    PIT Compliance:
    - as_of: When the event occurred (business time)
    - available_at: When the event was recorded (system time)
    """
    __tablename__ = "task_events"
    
    # Primary key
    event_id = Column(String(64), primary_key=True, comment="Unique event identifier")
    
    # Event metadata
    event_type = Column(String(128), nullable=False, index=True,
                       comment="Type of event")
    event_version = Column(String(32), nullable=False, default="1.0",
                          comment="Event schema version")
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                      index=True, comment="Event timestamp")
    
    # Source and target
    source = Column(String(128), nullable=False, comment="Event source")
    target = Column(String(128), nullable=True, comment="Event target")
    
    # Correlation
    task_id = Column(String(64), ForeignKey("tasks.task_id"), nullable=False,
                    index=True, comment="Related task ID")
    correlation_id = Column(String(64), nullable=True, index=True,
                           comment="Correlation ID for related events")
    causation_id = Column(String(64), nullable=True,
                         comment="Causation ID for event chain")
    trace_id = Column(String(64), nullable=True, index=True,
                     comment="Distributed trace ID")
    
    # Payload
    payload = Column(JSON, nullable=True, comment="Event payload")
    severity = Column(SQLEnum(EventSeverity), nullable=False, default=EventSeverity.INFO,
                     comment="Event severity")
    
    # Relationships
    task = relationship("Task", back_populates="events")
    
    # Indexes and constraints
    _table_args_ = (
        Index("idx_event_task_timestamp", "task_id", "timestamp"),
        Index("idx_event_type_timestamp", "event_type", "timestamp"),
        Index("idx_event_correlation", "correlation_id"),
        Index("idx_event_as_of", "as_of"),
        Index("idx_event_available_at", "available_at"),
    )


class Artifact(Base, PITMixin, VersionedMixin):
    """
    Artifact storage - versioned artifacts with provenance.
    
    PIT Compliance:
    - as_of: When the artifact was conceptually created
    - available_at: When the artifact became available
    
    Versioning: Composite PK (artifact_id, version) for true versioning
    """
    __tablename__ = "artifacts"
    
    # Composite primary key
    artifact_id = Column(String(64), primary_key=True, comment="Unique artifact identifier")
    version = Column(String(64), primary_key=True, index=True,
                    comment="Semantic version (e.g., 1.0.0)")
    
    # Artifact metadata
    artifact_type = Column(String(64), nullable=False, index=True,
                          comment="Type of artifact (model, report, etc.)")
    name = Column(String(256), nullable=False, comment="Artifact name")
    description = Column(Text, nullable=True, comment="Artifact description")
    
    # Storage
    storage_path = Column(String(512), nullable=False,
                         comment="Path to artifact storage")
    size_bytes = Column(Integer, nullable=True, comment="Artifact size in bytes")
    
    # Ownership and provenance
    owner = Column(String(128), nullable=False, index=True,
                  comment="Artifact owner")
    linked_task_id = Column(String(64), ForeignKey("tasks.task_id"), nullable=True,
                           index=True, comment="Task that created this artifact")
    
    # Reproducibility
    reproducibility_metadata = Column(JSON, nullable=True,
                                     comment="Metadata for reproducibility")
    checksum = Column(String(64), nullable=True,
                     comment="SHA256 checksum for integrity verification")
    
    # Indexes and constraints
    _table_args_ = (
        Index("idx_artifact_type_version", "artifact_type", "version"),
        Index("idx_artifact_owner", "owner"),
        Index("idx_artifact_as_of", "as_of"),
        Index("idx_artifact_available_at", "available_at"),
    )


# ============================================================================
# DATA MODELS
# ============================================================================

class Dataset(Base, PITMixin, VersionedMixin):
    """
    Dataset registry - versioned datasets with provenance.
    
    PIT Compliance:
    - as_of: When the dataset represents (data date)
    - available_at: When the dataset became available
    
    Versioning: Composite PK (dataset_id, version) for true versioning
    """
    __tablename__ = "datasets"
    
    # Composite primary key
    dataset_id = Column(String(64), primary_key=True, comment="Unique dataset identifier")
    version = Column(String(64), primary_key=True, index=True,
                    comment="Semantic version (e.g., 1.0.0)")
    
    # Dataset metadata
    name = Column(String(256), nullable=False, index=True, comment="Dataset name")
    source = Column(String(256), nullable=False, comment="Data source")
    frequency = Column(String(32), nullable=False, comment="Data frequency (daily, hourly, etc.)")
    schema_version = Column(String(32), nullable=False, comment="Schema version")
    
    # Provenance
    provenance = Column(JSON, nullable=False, comment="Data provenance information")
    timestamp_semantics = Column(String(64), nullable=False,
                                comment="Timestamp semantics (trade_time, quote_time, etc.)")
    
    # Quality
    quality_score = Column(Float, nullable=True, comment="Data quality score (0-1)")
    
    # Storage
    storage_path = Column(String(512), nullable=False, comment="Path to dataset storage")
    retention_policy = Column(JSON, nullable=True, comment="Data retention policy")
    checksum = Column(String(64), nullable=True,
                     comment="SHA256 checksum for integrity verification")
    
    # Indexes and constraints
    _table_args_ = (
        Index("idx_dataset_name_version", "name", "version"),
        Index("idx_dataset_source", "source"),
        Index("idx_dataset_as_of", "as_of"),
        Index("idx_dataset_available_at", "available_at"),
        CheckConstraint('quality_score >= 0.0 AND quality_score <= 1.0', name='ck_datasets_quality_score_range'),
    )


class NewsArticle(Base):
    """Persisted RSS/news article cache."""
    __tablename__ = "news_articles"

    article_id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(128), nullable=False, index=True)
    headline = Column(String(512), nullable=False)
    news_short_content = Column(Text, nullable=True)
    public_date = Column(DateTime, nullable=False, index=True)
    url = Column(String(1024), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    metadata_json = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("idx_news_article_source_date", "source", "public_date"),
    )


class MacroData(Base):
    """Macro time-series observations."""
    __tablename__ = "macro_data"

    row_id = Column(Integer, primary_key=True, autoincrement=True)
    series_key = Column(String(128), nullable=False, index=True)
    observation_date = Column(DateTime, nullable=False, index=True)
    available_at = Column(DateTime, nullable=True, index=True)
    frequency = Column(String(16), nullable=True)
    value = Column(Float, nullable=True)
    source = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    metadata_json = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("series_key", "observation_date", "source", name="uq_macro_data_series_date_source"),
        Index("idx_macro_data_series_date", "series_key", "observation_date"),
        Index("idx_macro_data_series_available", "series_key", "available_at"),
        Index("idx_macro_data_source_date", "source", "observation_date"),
    )


class TickerSector(Base):
    """Latest ticker to sector mapping."""
    __tablename__ = "ticker_sectors"

    ticker = Column(String(32), primary_key=True)
    sector = Column(String(256), nullable=False)
    source = Column(String(128), nullable=False, index=True)
    effective_date = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    metadata_json = Column("metadata", JSON, nullable=True)


class Model(Base, PITMixin):
    """
    Model registry - model metadata and lineage.
    
    PIT Compliance:
    - as_of: When the model was conceptually created
    - available_at: When the model became available
    """
    __tablename__ = "models"
    
    # Primary key
    model_id = Column(String(64), primary_key=True, comment="Unique model identifier")
    
    # Model metadata
    name = Column(String(256), nullable=False, index=True, comment="Model name")
    model_type = Column(String(64), nullable=False, index=True,
                       comment="Model type (alpha, risk, execution, etc.)")
    description = Column(Text, nullable=True, comment="Model description")
    
    # Ownership
    created_by = Column(String(128), nullable=False, comment="Model creator")
    
    # Relationships
    versions = relationship("ModelVersion", back_populates="model", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("idx_model_name", "name"),
        Index("idx_model_type", "model_type"),
        Index("idx_model_as_of", "as_of"),
        Index("idx_model_available_at", "available_at"),
    )


class ModelVersion(Base, PITMixin, VersionedMixin):
    """
    Model version - specific version of a model with training metadata.
    
    PIT Compliance:
    - as_of: When the model version was trained
    - available_at: When the model version became available
    """
    __tablename__ = "model_versions"
    
    # Primary key
    version_id = Column(String(64), primary_key=True, comment="Unique version identifier")
    
    # Foreign key
    model_id = Column(String(64), ForeignKey("models.model_id"), nullable=False,
                     index=True, comment="Parent model ID")
    
    # Training metadata
    training_data_ref = Column(String(64), ForeignKey("datasets.dataset_id"), nullable=False,
                              comment="Training dataset reference")
    feature_set_ref = Column(String(64), nullable=True,
                            comment="Feature set reference")
    training_config = Column(JSON, nullable=False,
                            comment="Training configuration")
    
    # Evaluation
    evaluation_metrics = Column(JSON, nullable=False,
                               comment="Evaluation metrics")
    
    # Deployment
    deployment_state = Column(SQLEnum(DeploymentState), nullable=False,
                             default=DeploymentState.DRAFT, index=True,
                             comment="Deployment state")
    rollback_ref = Column(String(64), nullable=True,
                         comment="Reference to previous version for rollback")
    
    # Approval
    approved_by = Column(String(128), nullable=True,
                        comment="Approver identifier")
    approved_at = Column(DateTime, nullable=True,
                        comment="Approval timestamp")
    
    # Relationships
    model = relationship("Model", back_populates="versions")
    
    # Indexes
    __table_args__ = (
        Index("idx_model_version_model", "model_id", "version"),
        Index("idx_model_version_state", "deployment_state"),
        Index("idx_model_version_as_of", "as_of"),
        Index("idx_model_version_available_at", "available_at"),
        UniqueConstraint("model_id", "version", name="uq_model_version"),
    )


class Experiment(Base, PITMixin, VersionedMixin):
    """
    Experiment tracking - research experiments with full reproducibility.
    
    PIT Compliance:
    - as_of: When the experiment was run
    - available_at: When the experiment results became available
    """
    __tablename__ = "experiments"
    
    # Primary key
    experiment_id = Column(String(64), primary_key=True, comment="Unique experiment identifier")
    
    # Experiment metadata
    name = Column(String(256), nullable=False, index=True, comment="Experiment name")
    description = Column(Text, nullable=True, comment="Experiment description")
    experiment_type = Column(String(64), nullable=False, index=True,
                            comment="Experiment type")
    
    # Configuration
    config = Column(JSON, nullable=False, comment="Experiment configuration")
    
    # Data references
    dataset_refs = Column(JSON, nullable=False, comment="Dataset references")
    model_ref = Column(String(64), ForeignKey("models.model_id"), nullable=True,
                      comment="Model reference")
    
    # Results
    results = Column(JSON, nullable=True, comment="Experiment results")
    metrics = Column(JSON, nullable=True, comment="Experiment metrics")
    
    # Status
    status = Column(String(32), nullable=False, default="running", index=True,
                   comment="Experiment status")
    
    # Ownership
    created_by = Column(String(128), nullable=False, comment="Experiment creator")
    
    # Indexes
    __table_args__ = (
        Index("idx_experiment_name", "name"),
        Index("idx_experiment_type", "experiment_type"),
        Index("idx_experiment_status", "status"),
        Index("idx_experiment_as_of", "as_of"),
        Index("idx_experiment_available_at", "available_at"),
    )


# ============================================================================
# EXECUTION MODELS
# ============================================================================

class Backtest(Base, PITMixin, VersionedMixin):
    """
    Backtest results - historical simulation results.
    
    PIT Compliance:
    - as_of: When the backtest was run
    - available_at: When the backtest results became available
    """
    __tablename__ = "backtests"
    
    # Primary key
    backtest_id = Column(String(64), primary_key=True, comment="Unique backtest identifier")
    
    # Backtest metadata
    name = Column(String(256), nullable=False, index=True, comment="Backtest name")
    description = Column(Text, nullable=True, comment="Backtest description")
    
    # Configuration
    config = Column(JSON, nullable=False, comment="Backtest configuration")
    
    # Time range
    start_date = Column(DateTime, nullable=False, index=True,
                       comment="Backtest start date")
    end_date = Column(DateTime, nullable=False, index=True,
                     comment="Backtest end date")
    
    # References
    model_version_ref = Column(String(64), ForeignKey("model_versions.version_id"),
                              nullable=False, comment="Model version reference")
    dataset_ref = Column(String(64), ForeignKey("datasets.dataset_id"),
                        nullable=False, comment="Dataset reference")
    
    # Results
    results = Column(JSON, nullable=False, comment="Backtest results")
    metrics = Column(JSON, nullable=False, comment="Performance metrics")
    
    # Status
    status = Column(String(32), nullable=False, default="running", index=True,
                   comment="Backtest status")
    
    # Ownership
    created_by = Column(String(128), nullable=False, comment="Backtest creator")
    
    # Indexes
    __table_args__ = (
        Index("idx_backtest_name", "name"),
        Index("idx_backtest_dates", "start_date", "end_date"),
        Index("idx_backtest_status", "status"),
        Index("idx_backtest_as_of", "as_of"),
        Index("idx_backtest_available_at", "available_at"),
    )


class RiskReport(Base, PITMixin, VersionedMixin):
    """
    Risk reports - risk analysis results.
    
    PIT Compliance:
    - as_of: When the risk analysis was performed
    - available_at: When the risk report became available
    """
    __tablename__ = "risk_reports"
    
    # Primary key
    report_id = Column(String(64), primary_key=True, comment="Unique report identifier")
    
    # Report metadata
    report_type = Column(String(64), nullable=False, index=True,
                        comment="Report type (VaR, stress, scenario, etc.)")
    name = Column(String(256), nullable=False, comment="Report name")
    
    # References
    backtest_ref = Column(String(64), ForeignKey("backtests.backtest_id"),
                         nullable=True, comment="Related backtest")
    model_version_ref = Column(String(64), ForeignKey("model_versions.version_id"),
                              nullable=True, comment="Related model version")
    
    # Risk metrics
    risk_metrics = Column(JSON, nullable=False, comment="Risk metrics")
    
    # Limits and breaches
    limits = Column(JSON, nullable=True, comment="Risk limits")
    breaches = Column(JSON, nullable=True, comment="Limit breaches")
    
    # Status
    status = Column(String(32), nullable=False, default="draft", index=True,
                   comment="Report status")
    severity = Column(SQLEnum(EventSeverity), nullable=False, default=EventSeverity.INFO,
                     comment="Risk severity")
    
    # Ownership
    created_by = Column(String(128), nullable=False, comment="Report creator")
    reviewed_by = Column(String(128), nullable=True, comment="Report reviewer")
    
    # Indexes
    __table_args__ = (
        Index("idx_risk_report_type", "report_type"),
        Index("idx_risk_report_status", "status"),
        Index("idx_risk_report_severity", "severity"),
        Index("idx_risk_report_as_of", "as_of"),
        Index("idx_risk_report_available_at", "available_at"),
    )


class Execution(Base, PITMixin):
    """
    Execution records - trade execution history.
    
    PIT Compliance:
    - as_of: When the execution occurred (trade time)
    - available_at: When the execution was recorded
    """
    __tablename__ = "executions"
    
    # Primary key
    execution_id = Column(String(64), primary_key=True, comment="Unique execution identifier")
    
    # Order metadata
    order_id = Column(String(64), nullable=False, index=True, comment="Order identifier")
    symbol = Column(String(32), nullable=False, index=True, comment="Trading symbol")
    
    # Execution details
    side = Column(String(16), nullable=False, comment="Buy or Sell")
    quantity = Column(Float, nullable=False, comment="Executed quantity")
    price = Column(Float, nullable=False, comment="Execution price")
    
    # Timestamps
    order_time = Column(DateTime, nullable=False, index=True,
                       comment="Order submission time")
    execution_time = Column(DateTime, nullable=False, index=True,
                           comment="Execution time")
    
    # Costs
    commission = Column(Float, nullable=True, comment="Commission paid")
    slippage = Column(Float, nullable=True, comment="Slippage cost")
    
    # References
    backtest_ref = Column(String(64), ForeignKey("backtests.backtest_id"),
                         nullable=True, comment="Related backtest (if simulated)")
    
    # Metadata
    execution_metadata = Column(JSON, nullable=True,
                               comment="Additional execution metadata")
    
    # Indexes
    __table_args__ = (
        Index("idx_execution_order", "order_id"),
        Index("idx_execution_symbol", "symbol"),
        Index("idx_execution_time", "execution_time"),
        Index("idx_execution_as_of", "as_of"),
        Index("idx_execution_available_at", "available_at"),
    )


# ============================================================================
# AUDIT MODELS
# ============================================================================

class MemorySnapshot(Base, PITMixin, VersionedMixin):
    """
    Memory snapshots - system state snapshots for recovery.
    
    PIT Compliance:
    - as_of: When the snapshot represents
    - available_at: When the snapshot was created
    """
    __tablename__ = "memory_snapshots"
    
    # Primary key
    snapshot_id = Column(String(64), primary_key=True, comment="Unique snapshot identifier")
    
    # Snapshot metadata
    snapshot_type = Column(String(64), nullable=False, index=True,
                          comment="Snapshot type (checkpoint, recovery, etc.)")
    name = Column(String(256), nullable=False, comment="Snapshot name")
    
    # State
    current_objective = Column(Text, nullable=True, comment="Current objective")
    active_tasks = Column(JSON, nullable=True, comment="Active tasks")
    working_state = Column(JSON, nullable=True, comment="Working state")
    recent_decisions = Column(JSON, nullable=True, comment="Recent decisions")
    unresolved_issues = Column(JSON, nullable=True, comment="Unresolved issues")
    
    # References
    model_refs = Column(JSON, nullable=True, comment="Model references")
    dataset_refs = Column(JSON, nullable=True, comment="Dataset references")
    
    # Storage
    storage_path = Column(String(512), nullable=True,
                         comment="Path to full snapshot storage")
    
    # Ownership
    created_by = Column(String(128), nullable=False, comment="Snapshot creator")
    
    # Indexes
    __table_args__ = (
        Index("idx_snapshot_type", "snapshot_type"),
        Index("idx_snapshot_as_of", "as_of"),
        Index("idx_snapshot_available_at", "available_at"),
    )


class AuditLog(Base, PITMixin):
    """
    Audit log - immutable audit trail for governance.
    
    PIT Compliance:
    - as_of: When the audited action occurred
    - available_at: When the audit entry was recorded
    """
    __tablename__ = "audit_logs"
    
    # Primary key
    audit_id = Column(String(64), primary_key=True, comment="Unique audit identifier")
    
    # Audit metadata
    action = Column(String(128), nullable=False, index=True, comment="Action performed")
    action_type = Column(String(64), nullable=False, index=True,
                        comment="Action type (create, update, delete, etc.)")
    
    # Actor
    actor = Column(String(128), nullable=False, index=True, comment="Actor identifier")
    actor_type = Column(String(64), nullable=False, comment="Actor type (agent, user, system)")
    
    # Target
    target_type = Column(String(64), nullable=False, index=True,
                        comment="Target type (task, model, dataset, etc.)")
    target_id = Column(String(64), nullable=False, index=True,
                      comment="Target identifier")
    
    # Changes
    before_state = Column(JSON, nullable=True, comment="State before action")
    after_state = Column(JSON, nullable=True, comment="State after action")
    
    # Context
    context = Column(JSON, nullable=True, comment="Action context")
    reason = Column(Text, nullable=True, comment="Reason for action")
    
    # Correlation
    correlation_id = Column(String(64), nullable=True, index=True,
                           comment="Correlation ID for related actions")
    
    # Severity
    severity = Column(SQLEnum(EventSeverity), nullable=False, default=EventSeverity.INFO,
                     comment="Audit severity")
    
    # Indexes
    __table_args__ = (
        Index("idx_audit_action", "action"),
        Index("idx_audit_actor", "actor"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_correlation", "correlation_id"),
        Index("idx_audit_as_of", "as_of"),
        Index("idx_audit_available_at", "available_at"),
    )
