"""
OMEGA_QUANT SRE Foundation
===========================
Phase 7.1 — Core SRE infrastructure.

Exports:
    sre_logger        : Structured JSON logging with trace_id propagation.
    metrics_collector : Vectorized counter, gauge, and histogram metrics.
    kill_switch       : Global emergency kill-switch with graceful shutdown.
"""

from omega.core.sre.kill_switch import KillSwitch, get_kill_switch, reset_kill_switch
from omega.core.sre.metrics_collector import (
    Counter,
    Gauge,
    Histogram,
    LatencyTimer,
    MetricsCollector,
    get_metrics_collector,
)
from omega.core.sre.sre_logger import get_sre_logger, get_trace_id, new_trace_id, set_trace_id

__all__ = [
    # logger
    "get_sre_logger",
    "get_trace_id",
    "set_trace_id",
    "new_trace_id",
    # metrics
    "Counter",
    "Gauge",
    "Histogram",
    "LatencyTimer",
    "MetricsCollector",
    "get_metrics_collector",
    # kill switch
    "KillSwitch",
    "get_kill_switch",
    "reset_kill_switch",
]
