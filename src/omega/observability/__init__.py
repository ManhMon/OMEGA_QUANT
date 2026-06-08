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

try:
    from . import alpha_decay_monitor
except ImportError:
    pass

try:
    from . import logging
except ImportError:
    pass

try:
    from . import production_monitor
except ImportError:
    pass

try:
    from . import risk_dashboard
except ImportError:
    pass

try:
    from . import risk_monitor_l07
except ImportError:
    pass

try:
    from . import signal_decay_analyzer
except ImportError:
    pass
