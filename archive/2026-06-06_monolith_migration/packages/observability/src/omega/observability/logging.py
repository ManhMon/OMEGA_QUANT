"""
OMEGA_QUANT Observability & SRE (Phase 7)

Purpose:
    Provide structured logging, metrics collection, and alerting.
    - JSON-formatted structured logging
    - Correlation IDs for request/pipeline tracing
    - Metrics collection (counters, gauges, histograms)
    - Alerting engine based on configurable rules
    - Vectorized metrics operations

Contract:
    - Input: Log messages, metric updates, alert rules
    - Output: Structured logs (.jsonl), Metrics (.parquet), Alerts (.json)
    - Performance: Low latency, non-blocking I/O

Reference:
    - Phase 7: Observability & SRE
    - Institutional-grade SRE platform

Author: MLEngine (Role 16)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import pandas as pd
import numpy as np

# Standard logging level mapping
LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class StructuredLogger:
    """
    JSON-formatted structured logger with correlation IDs.
    
    Output format:
    {"timestamp": "...", "level": "...", "correlation_id": "...", "component": "...", "message": "...", "context": {...}}
    """
    
    def __init__(
        self,
        component: str,
        log_dir: str = ".ly_state/logs",
        level: str = "INFO",
        correlation_id: Optional[str] = None
    ):
        self.component = component
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{component}_{datetime.now().strftime('%Y%m%d')}.jsonl"
        self.level = LEVELS.get(level, logging.INFO)
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        
        # Internal Python logger for console output
        self.logger = logging.getLogger(f"omega.{component}")
        self.logger.setLevel(self.level)
    
    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat() + "Z"
    
    def _log(self, level_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        if LEVELS.get(level_name, logging.INFO) < self.level:
            return
            
        record = {
            "timestamp": self._now(),
            "level": level_name,
            "correlation_id": self.correlation_id,
            "component": self.component,
            "message": message,
            "context": context or {},
        }
        
        # Write to JSONL
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            
        # Console output
        log_func = getattr(self.logger, level_name.lower())
        log_func(f"[{self.correlation_id}] {message} | {json.dumps(context or {})}")

    def debug(self, message: str, **kwargs): self._log("DEBUG", message, kwargs)
    def info(self, message: str, **kwargs): self._log("INFO", message, kwargs)
    def warning(self, message: str, **kwargs): self._log("WARNING", message, kwargs)
    def error(self, message: str, **kwargs): self._log("ERROR", message, kwargs)
    def critical(self, message: str, **kwargs): self._log("CRITICAL", message, kwargs)


class MetricsEngine:
    """
    Lightweight metrics collection (Counters, Gauges).
    
    Stores metrics in-memory and persists to Parquet for analysis.
    """
    
    def __init__(self, component: str, metrics_dir: str = ".ly_state/metrics"):
        self.component = component
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.metrics_dir / f"{component}_metrics.parquet"
        
        self.data: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
    
    def record(self, name: str, value: float, unit: str = "count", tags: Optional[Dict[str, str]] = None):
        """Record a metric point."""
        point = {
            "timestamp": datetime.now(timezone.utc),
            "component": self.component,
            "name": name,
            "value": float(value),
            "unit": unit,
            "tags": json.dumps(tags or {}),
        }
        with self._lock:
            self.data.append(point)
            
        # Auto-flush if buffer too large
        if len(self.data) >= 100:
            self.flush()
    
    def flush(self):
        """Persist in-memory metrics to disk."""
        if not self.data:
            return
            
        with self._lock:
            new_df = pd.DataFrame(self.data)
            self.data = []
            
        if self.metrics_file.exists():
            old_df = pd.read_parquet(self.metrics_file)
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
            
        combined_df.to_parquet(self.metrics_file, index=False)
    
    def get_summary(self) -> pd.DataFrame:
        """Get summarized metrics (mean, max, min)."""
        if not self.metrics_file.exists():
            return pd.DataFrame()
            
        df = pd.read_parquet(self.metrics_file)
        return df.groupby("name")["value"].agg(["mean", "max", "min", "count"])


class AlertManager:
    """
    Rule-based alerting engine.
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
        self.rules: List[Dict[str, Any]] = []
    
    def add_rule(self, name: str, metric_name: str, condition: str, threshold: float, severity: str = "WARNING"):
        """
        Add an alert rule.
        Condition can be: '>', '<', '>=', '<=', '=='
        """
        self.rules.append({
            "name": name,
            "metric_name": metric_name,
            "condition": condition,
            "threshold": threshold,
            "severity": severity,
        })
    
    def check_metrics(self, metrics_summary: pd.DataFrame):
        """Evaluate all rules against metrics summary."""
        for rule in self.rules:
            if rule["metric_name"] not in metrics_summary.index:
                continue
                
            val = metrics_summary.loc[rule["metric_name"], "mean"]
            threshold = rule["threshold"]
            cond = rule["condition"]
            
            triggered = False
            if cond == ">" and val > threshold: triggered = True
            elif cond == "<" and val < threshold: triggered = True
            elif cond == ">=" and val >= threshold: triggered = True
            elif cond == "<=" and val <= threshold: triggered = True
            elif cond == "==" and val == threshold: triggered = True
            
            if triggered:
                msg = f"ALERT TRIGGERED: {rule['name']} | Metric: {rule['metric_name']}={val:.4f} {cond} {threshold}"
                if rule["severity"] == "CRITICAL":
                    self.logger.critical(msg)
                else:
                    self.logger.warning(msg)


def setup_observability(component: str) -> Dict[str, Any]:
    """Factory to setup all observability tools for a component."""
    log = StructuredLogger(component)
    metrics = MetricsEngine(component)
    alerts = AlertManager(log)
    
    return {
        "logger": log,
        "metrics": metrics,
        "alerts": alerts,
    }
