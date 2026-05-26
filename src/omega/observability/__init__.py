"""Observability package for OMEGA_QUANT."""

from .neural_memory import NeuralMemory
from .logger import StructuredLogger
from .metrics import MetricsRegistry, registry
from .monitor import SystemMonitor, AlertRule

from .tracing import (
    SpanKind,
    SpanStatus,
    TraceContext,
    Span,
    Tracer,
    get_tracer,
    traced,
)

from .alerting import (
    AlertSeverity,
    AlertTriggerType,
    AlertState,
    Alert,
    AlertRule as AlertingRule,
    AlertManager,
    create_risk_breach_rule,
    create_model_drift_rule,
    create_execution_failure_rule,
)

__all__ = [
    "NeuralMemory",
    "StructuredLogger",
    "MetricsRegistry",
    "registry",
    "SystemMonitor",
    "AlertRule",
    # tracing
    "SpanKind",
    "SpanStatus",
    "TraceContext",
    "Span",
    "Tracer",
    "get_tracer",
    "traced",
    # alerting
    "AlertSeverity",
    "AlertTriggerType",
    "AlertState",
    "Alert",
    "AlertingRule",
    "AlertManager",
    "create_risk_breach_rule",
    "create_model_drift_rule",
    "create_execution_failure_rule",
]
