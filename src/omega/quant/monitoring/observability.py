"""
OMEGA_QUANT Observability Module
Phase 9: Integration & Testing - Observability & SRE

Author: DevOps Engineer (Role 12)
Date: 2026-05-14
Version: 1.0.0
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime


class StructuredLogger:
    """Structured logger with context support."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def info(self, message: str, **kwargs):
        """Log info message with structured context."""
        context = " ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"{message} {context}" if context else message)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured context."""
        context = " ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.warning(f"{message} {context}" if context else message)
    
    def error(self, message: str, **kwargs):
        """Log error message with structured context."""
        context = " ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.error(f"{message} {context}" if context else message)


class MetricsEngine:
    """Simple metrics collection engine."""
    
    def __init__(self, metrics_file: Optional[Path] = None):
        self.metrics_file = metrics_file or Path(".ly_state/metrics/pipeline_metrics.jsonl")
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self._buffer = []
    
    def record(self, metric_name: str, value: float):
        """Record a metric value."""
        self._buffer.append({
            "timestamp": datetime.utcnow().isoformat(),
            "metric": metric_name,
            "value": value
        })
    
    def flush(self):
        """Flush metrics to file."""
        if self._buffer:
            with open(self.metrics_file, "a") as f:
                for metric in self._buffer:
                    f.write(f"{metric}\n")
            self._buffer.clear()


class AlertManager:
    """Simple alert manager for threshold monitoring."""
    
    def __init__(self):
        self.rules = []
    
    def add_rule(self, name: str, metric: str, operator: str, threshold: float, severity: str = "WARNING"):
        """Add an alert rule."""
        self.rules.append({
            "name": name,
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "severity": severity
        })
    
    def check(self, metric: str, value: float):
        """Check if metric triggers any alerts."""
        for rule in self.rules:
            if rule["metric"] == metric:
                if rule["operator"] == ">" and value > rule["threshold"]:
                    return True
                elif rule["operator"] == "<" and value < rule["threshold"]:
                    return True
        return False


def setup_observability(
    component_name: str = "omega_quant",
    log_level: str = "INFO",
    log_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Setup observability infrastructure.
    
    Configures:
    - Structured logging
    - Metrics collection
    - Alert management
    
    Args:
        component_name: Name of the component (used for logger name)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    
    Returns:
        Dictionary with logger, metrics, and alerts instances
    """
    # Configure logging
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=handlers,
        force=True
    )
    
    # Create observability components
    logger = StructuredLogger(component_name)
    metrics = MetricsEngine()
    alerts = AlertManager()
    
    logger.info(f"Observability initialized", component=component_name, log_level=log_level)
    
    return {
        "logger": logger,
        "metrics": metrics,
        "alerts": alerts
    }


__all__ = ['setup_observability', 'StructuredLogger', 'MetricsEngine', 'AlertManager']
