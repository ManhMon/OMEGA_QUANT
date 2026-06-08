"""
Layer 07 risk monitor for AdvancedCircuitBreaker breach events.

PIT safety: consumes precomputed `RiskBreachStatus` objects only.
Vectorization: operates on pandas/numpy bulk transforms, no metric recalculation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from omega.quant.risk.advanced_circuit_breaker import RiskBreachStatus


class RiskSeverity(str, Enum):
    """Severity ladder for Layer 07 risk events."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RiskMonitorConfig:
    """Static configuration for Layer 07 monitoring cadence and limits."""

    evaluation_interval: timedelta = field(default_factory=lambda: timedelta(minutes=30))
    var_limit: float = 0.025
    cvar_limit: float = 0.045
    event_log_path: Path = field(default_factory=lambda: Path("state") / "risk_events.jsonl")


@dataclass(frozen=True)
class RiskEvent:
    """Immutable event emitted from precomputed circuit breaker breaches."""

    monitor_layer: str
    metric_name: str
    severity: RiskSeverity
    metric_value: float
    limit: float
    breach_severity: float
    action: str
    message: str
    timestamp: datetime
    metadata: Dict[str, object] = field(default_factory=dict)


class RiskMonitorL07:
    """Layer 07 monitor consuming only `RiskBreachStatus` outputs."""

    def __init__(self, config: Optional[RiskMonitorConfig] = None) -> None:
        self.config = config or RiskMonitorConfig()
        self._last_evaluation_at: Optional[datetime] = None

    def monitor_breaches(
        self,
        breach_statuses: Sequence[RiskBreachStatus],
        evaluation_time: Optional[datetime] = None,
    ) -> List[RiskEvent]:
        """Convert circuit breaker breaches into persisted Layer 07 events."""

        event_time = self._normalize_timestamp(evaluation_time)
        if not breach_statuses:
            self._last_evaluation_at = event_time
            return []

        breach_frame = pd.DataFrame(
            {
                "metric_name": [status.metric_name for status in breach_statuses],
                "metric_value": [float(status.metric_value) for status in breach_statuses],
                "limit": [float(self._resolve_limit(status)) for status in breach_statuses],
                "is_breached": [bool(status.is_breached) for status in breach_statuses],
                "breach_severity": [float(status.breach_severity) for status in breach_statuses],
                "action": [status.action for status in breach_statuses],
                "message": [status.message for status in breach_statuses],
                "timestamp": [self._normalize_timestamp(status.timestamp) for status in breach_statuses],
            }
        )

        breached_frame = breach_frame.loc[breach_frame["is_breached"]].copy()
        if breached_frame.empty:
            self._last_evaluation_at = event_time
            return []

        breached_frame["severity"] = np.where(
            breached_frame["breach_severity"] >= 0.01,
            RiskSeverity.CRITICAL.value,
            RiskSeverity.WARNING.value,
        )
        breached_frame["monitor_layer"] = "L07"
        breached_frame["metadata"] = breached_frame.apply(
            lambda row: {
                "source": "AdvancedCircuitBreaker",
                "evaluation_time": event_time.isoformat(),
                "interval_minutes": int(self.config.evaluation_interval.total_seconds() // 60),
            },
            axis=1,
        )

        events = [
            RiskEvent(
                monitor_layer=str(row.monitor_layer),
                metric_name=str(row.metric_name),
                severity=RiskSeverity(str(row.severity)),
                metric_value=float(row.metric_value),
                limit=float(row.limit),
                breach_severity=float(row.breach_severity),
                action=str(row.action),
                message=str(row.message),
                timestamp=self._normalize_timestamp(row.timestamp),
                metadata=dict(row.metadata),
            )
            for row in breached_frame.itertuples(index=False)
        ]

        self._append_events(events)
        self._last_evaluation_at = event_time
        return events

    def should_evaluate(self, current_time: Optional[datetime] = None) -> bool:
        """Check monitor cadence against last evaluation timestamp."""

        if self._last_evaluation_at is None:
            return True

        now = self._normalize_timestamp(current_time)
        return now - self._last_evaluation_at >= self.config.evaluation_interval

    def _append_events(self, events: Sequence[RiskEvent]) -> None:
        log_path = self.config.event_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open("a", encoding="utf-8") as handle:
            for event in events:
                payload = asdict(event)
                payload["severity"] = event.severity.value
                payload["timestamp"] = event.timestamp.isoformat()
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _resolve_limit(self, status: RiskBreachStatus) -> float:
        metric_name = status.metric_name.lower()
        if metric_name == "var":
            return self.config.var_limit
        if metric_name == "cvar":
            return self.config.cvar_limit
        return float(status.limit)

    @staticmethod
    def _normalize_timestamp(timestamp: Optional[datetime]) -> datetime:
        if timestamp is None:
            return datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
