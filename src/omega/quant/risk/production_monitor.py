"""
Production monitoring for live OMEGA risk supervision.

PIT safety: time-series metrics use only values supplied up to evaluation point.
Vectorization: performance calculations rely on NumPy/Pandas array ops only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


class SystemState(Enum):
    """System lifecycle states for production monitoring."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    EMERGENCY_STOP = "emergency_stop"


class AlertChannel(Enum):
    """Supported alert delivery channels."""

    EMAIL = "email"
    SLACK = "slack"
    LOG = "log"


@dataclass(frozen=True)
class AlertConfig:
    """Static alert routing and severity configuration."""

    channel: AlertChannel
    target: str
    severity: str = "warning"
    cooldown_minutes: int = 5


@dataclass(frozen=True)
class PerformanceSnapshot:
    """Vectorized performance output for production telemetry."""

    total_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    latest_equity: float


@dataclass(frozen=True)
class AlertEvent:
    """Immutable alert event produced by monitor."""

    channel: AlertChannel
    target: str
    severity: str
    message: str
    timestamp: datetime
    state: SystemState
    metadata: Dict[str, object] = field(default_factory=dict)


class ProductionMonitor:
    """Production state manager with throttled alerting and vectorized metrics."""

    _ALLOWED_TRANSITIONS = {
        SystemState.STOPPED: frozenset({SystemState.STARTING, SystemState.EMERGENCY_STOP}),
        SystemState.STARTING: frozenset({SystemState.RUNNING, SystemState.PAUSED, SystemState.STOPPED, SystemState.EMERGENCY_STOP}),
        SystemState.RUNNING: frozenset({SystemState.PAUSED, SystemState.STOPPED, SystemState.EMERGENCY_STOP}),
        SystemState.PAUSED: frozenset({SystemState.RUNNING, SystemState.STOPPED, SystemState.EMERGENCY_STOP}),
        SystemState.EMERGENCY_STOP: frozenset({SystemState.STOPPED, SystemState.STARTING}),
    }

    def __init__(
        self,
        alert_configs: Optional[Sequence[AlertConfig]] = None,
        initial_state: SystemState = SystemState.STOPPED,
        annualization_factor: int = 252,
    ) -> None:
        self.alert_configs = list(alert_configs or ())
        self.state = initial_state
        self.annualization_factor = int(annualization_factor)
        self.state_history: List[Dict[str, object]] = []
        self.alert_history: List[AlertEvent] = []
        self._last_alert_at: Dict[str, datetime] = {}

        if self.annualization_factor <= 0:
            raise ValueError("annualization_factor must be positive")

        self._record_state(initial_state, reason="initialization")

    def transition_state(
        self,
        new_state: SystemState,
        reason: str,
        timestamp: Optional[datetime] = None,
    ) -> SystemState:
        """Transition system state with explicit lifecycle guardrails."""

        if new_state not in self._ALLOWED_TRANSITIONS[self.state] and new_state != self.state:
            raise ValueError(f"invalid state transition: {self.state.value} -> {new_state.value}")

        transition_time = self._normalize_timestamp(timestamp)
        self.state = new_state
        self._record_state(new_state, reason=reason, timestamp=transition_time)
        return self.state

    def dispatch_alert(
        self,
        message: str,
        severity: str = "warning",
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> List[AlertEvent]:
        """Dispatch alerts across configured channels with cooldown throttling."""

        if not self.alert_configs:
            return []

        alert_time = self._normalize_timestamp(timestamp)
        alert_metadata = dict(metadata or {})
        events: List[AlertEvent] = []

        for config in self.alert_configs:
            cooldown_key = self._cooldown_key(config=config, severity=severity, message=message)
            last_sent_at = self._last_alert_at.get(cooldown_key)
            cooldown_window = timedelta(minutes=config.cooldown_minutes)

            if last_sent_at is not None and alert_time - last_sent_at < cooldown_window:
                continue

            event = AlertEvent(
                channel=config.channel,
                target=config.target,
                severity=severity or config.severity,
                message=message,
                timestamp=alert_time,
                state=self.state,
                metadata=alert_metadata,
            )
            self._last_alert_at[cooldown_key] = alert_time
            self.alert_history.append(event)
            events.append(event)

        return events

    def calculate_performance(self, returns: pd.Series) -> PerformanceSnapshot:
        """Compute vectorized production performance metrics from ordered returns."""

        ordered_returns = self._coerce_returns(returns)
        if ordered_returns.empty:
            raise ValueError("returns must contain at least one observation")

        equity_curve = (1.0 + ordered_returns).cumprod()
        rolling_peak = equity_curve.cummax()
        drawdowns = equity_curve.div(rolling_peak).sub(1.0)

        mean_return = float(ordered_returns.mean())
        volatility = float(ordered_returns.std(ddof=0))
        annualized_volatility = volatility * np.sqrt(self.annualization_factor)
        sharpe_ratio = 0.0
        if annualized_volatility > 0.0:
            sharpe_ratio = (mean_return * self.annualization_factor) / annualized_volatility

        return PerformanceSnapshot(
            total_return=float(equity_curve.iloc[-1] - 1.0),
            annualized_volatility=float(annualized_volatility),
            sharpe_ratio=float(sharpe_ratio),
            max_drawdown=float(abs(drawdowns.min())),
            latest_equity=float(equity_curve.iloc[-1]),
        )

    def evaluate_returns(
        self,
        returns: pd.Series,
        max_drawdown_limit: Optional[float] = None,
        min_sharpe_limit: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> PerformanceSnapshot:
        """Calculate performance and emit alerts when thresholds breach."""

        snapshot = self.calculate_performance(returns)
        alert_time = self._normalize_timestamp(timestamp)

        if max_drawdown_limit is not None and snapshot.max_drawdown > max_drawdown_limit:
            self.dispatch_alert(
                message=(
                    f"max drawdown breach: current={snapshot.max_drawdown:.4f}, "
                    f"limit={float(max_drawdown_limit):.4f}"
                ),
                severity="critical",
                timestamp=alert_time,
                metadata={"metric": "max_drawdown", "value": snapshot.max_drawdown, "limit": float(max_drawdown_limit)},
            )

        if min_sharpe_limit is not None and snapshot.sharpe_ratio < min_sharpe_limit:
            self.dispatch_alert(
                message=(
                    f"sharpe breach: current={snapshot.sharpe_ratio:.4f}, "
                    f"limit={float(min_sharpe_limit):.4f}"
                ),
                severity="critical",
                timestamp=alert_time,
                metadata={"metric": "sharpe_ratio", "value": snapshot.sharpe_ratio, "limit": float(min_sharpe_limit)},
            )

        return snapshot

    def get_state_history(self) -> pd.DataFrame:
        """Return state history in tabular form for observability."""

        return pd.DataFrame(self.state_history)

    def get_alert_history(self) -> pd.DataFrame:
        """Return dispatched alerts in tabular form for observability."""

        return pd.DataFrame(
            [
                {
                    "channel": event.channel.value,
                    "target": event.target,
                    "severity": event.severity,
                    "message": event.message,
                    "timestamp": event.timestamp,
                    "state": event.state.value,
                    "metadata": event.metadata,
                }
                for event in self.alert_history
            ]
        )

    def _record_state(
        self,
        state: SystemState,
        reason: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        event_time = self._normalize_timestamp(timestamp)
        self.state_history.append(
            {
                "timestamp": event_time,
                "state": state.value,
                "reason": reason,
            }
        )

    @staticmethod
    def _normalize_timestamp(timestamp: Optional[datetime]) -> datetime:
        if timestamp is None:
            return datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _cooldown_key(config: AlertConfig, severity: str, message: str) -> str:
        return "|".join((config.channel.value, config.target, severity, message))

    @staticmethod
    def _coerce_returns(returns: pd.Series) -> pd.Series:
        series = pd.Series(returns, copy=False)
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if numeric.empty:
            return numeric.astype(float)
        return numeric.sort_index().astype(float)
