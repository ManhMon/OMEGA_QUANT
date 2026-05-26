"""
OMEGA_QUANT Database Models
Institutional-grade SQLAlchemy models with PIT compliance.

Version: 2.1
Status: Phase 2.1 Implementation
"""

from .base import Base, get_engine, get_session, init_db
from .models import (
    Task,
    TaskEvent,
    Artifact,
    Dataset,
    Model,
    ModelVersion,
    Experiment,
    Backtest,
    RiskReport,
    Execution,
    MemorySnapshot,
    AuditLog,
)
from .persistence import (
    AuditLogRecord,
    DatasetRecord,
    ModelRecord,
    RegistryBase,
    canonicalize_payload,
    compute_chain_hash,
    create_registry_engine,
    init_registry_db,
    make_registry_session_factory,
)

__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "init_db",
    "Task",
    "TaskEvent",
    "Artifact",
    "Dataset",
    "Model",
    "ModelVersion",
    "Experiment",
    "Backtest",
    "RiskReport",
    "Execution",
    "MemorySnapshot",
    "AuditLog",
    "RegistryBase",
    "DatasetRecord",
    "ModelRecord",
    "AuditLogRecord",
    "create_registry_engine",
    "init_registry_db",
    "make_registry_session_factory",
    "canonicalize_payload",
    "compute_chain_hash",
]
