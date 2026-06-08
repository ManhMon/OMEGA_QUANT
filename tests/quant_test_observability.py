"""
Unit Tests for OMEGA_QUANT Observability & SRE
Phase 7: Observability & SRE

Author: MLEngine (Role 16)
Date: 2026-05-13
"""

import pytest
import json
import pandas as pd
from pathlib import Path
from omega.observability.logging import StructuredLogger, MetricsEngine, AlertManager

@pytest.fixture
def obs_setup(tmp_path):
    log_dir = tmp_path / "logs"
    metrics_dir = tmp_path / "metrics"
    
    logger = StructuredLogger("test_comp", log_dir=str(log_dir))
    metrics = MetricsEngine("test_comp", metrics_dir=str(metrics_dir))
    alerts = AlertManager(logger)
    
    return logger, metrics, alerts

def test_structured_logger(obs_setup):
    """Test JSON structured logging."""
    logger, _, _ = obs_setup
    logger.info("Test message", key1="val1", key2=100)
    
    # Check file exists
    log_file = list(Path(logger.log_dir).glob("*.jsonl"))[0]
    assert log_file.exists()
    
    # Check content
    with open(log_file, "r") as f:
        line = f.readline()
        record = json.loads(line)
        assert record["message"] == "Test message"
        assert record["context"]["key1"] == "val1"
        assert record["context"]["key2"] == 100
        assert "correlation_id" in record

def test_metrics_engine(obs_setup):
    """Test metrics collection and persistence."""
    _, metrics, _ = obs_setup
    
    for i in range(10):
        metrics.record("latency", 0.1 * i, unit="sec")
    
    metrics.flush()
    
    assert metrics.metrics_file.exists()
    
    # Check summary
    summary = metrics.get_summary()
    assert "latency" in summary.index
    assert summary.loc["latency", "count"] == 10
    assert summary.loc["latency", "max"] == 0.9

def test_alert_manager(obs_setup):
    """Test rule evaluation and alerting."""
    logger, metrics, alerts = obs_setup
    
    # Add rule: latency > 0.5 sec -> WARNING
    alerts.add_rule("High Latency", "latency", ">", 0.5, severity="WARNING")
    
    # Record metrics that trigger alert
    for i in range(10):
        metrics.record("latency", 0.6, unit="sec")
    metrics.flush()
    
    # Check alerts
    summary = metrics.get_summary()
    alerts.check_metrics(summary)
    
    # Check log for alert
    log_file = list(Path(logger.log_dir).glob("*.jsonl"))[0]
    content = log_file.read_text()
    assert "ALERT TRIGGERED: High Latency" in content
    assert "WARNING" in content

