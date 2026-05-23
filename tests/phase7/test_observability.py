"""
Tests for Observability & SRE - OMEGA_QUANT Phase 7 Migration
"""

import json
import io
import logging

from omega.observability.logger import StructuredLogger
from omega.observability.metrics import MetricsRegistry
from omega.observability.monitor import SystemMonitor, AlertRule


def test_structured_logger_has_ids():
    logger = StructuredLogger("TestLogger")
    
    # Capture log output
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.logger.handlers = [handler]
    
    correlation_id = logger.info("test message", service="execution")
    
    output = stream.getvalue().strip()
    log_entry = json.loads(output)
    
    assert log_entry["message"] == "test message"
    assert "correlation_id" in log_entry
    assert "trace_id" in log_entry
    assert log_entry["correlation_id"] == correlation_id


def test_metrics_registry_snapshot():
    metrics = MetricsRegistry()
    
    metrics.increment("orders_total")
    metrics.increment("orders_total", 2)
    metrics.gauge("cpu_usage", 0.75)
    metrics.record("latency_ms", 10.0)
    metrics.record("latency_ms", 20.0)
    
    snapshot = metrics.get_snapshot()
    
    assert snapshot["counters"]["orders_total"] == 3
    assert snapshot["gauges"]["cpu_usage"] == 0.75
    assert snapshot["histograms"]["latency_ms"]["count"] == 2
    assert snapshot["histograms"]["latency_ms"]["avg"] == 15.0


def test_monitor_alert_trigger():
    monitor = SystemMonitor()
    monitor.add_rule(AlertRule(
        name="high_latency",
        metric_name="latency_ms.avg",
        threshold=50.0,
        comparison=">",
        severity="CRITICAL"
    ))
    
    metrics_snapshot = {
        "counters": {},
        "gauges": {},
        "histograms": {
            "latency_ms": {
                "count": 10,
                "min": 10,
                "max": 100,
                "avg": 60.0
            }
        }
    }
    
    alerts = monitor.evaluate(metrics_snapshot)
    
    assert len(alerts) == 1
    assert alerts[0]["rule"] == "high_latency"
    assert alerts[0]["severity"] == "CRITICAL"
