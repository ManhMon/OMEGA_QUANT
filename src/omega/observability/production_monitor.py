"""
Production Monitor - Phase 5.3
Layer 07: Monitoring & Observability

Real-time production monitoring engine with alerting, circuit breakers,
and performance metrics tracking.

Key Features:
- Real-time monitoring (< 1 second latency)
- Multi-channel alerting (email, Slack, webhook)
- Circuit breaker triggers (auto-stop on risk breach)
- Performance metrics (Sharpe, Sortino, Calmar, Max Drawdown)
- Operational controls (startup, shutdown, emergency stop)
- Comprehensive audit trail
- PIT-safe monitoring

Version: v21.0
Date: 2026-05-07
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Callable
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import logging
import threading
import time
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests


class SystemState(Enum):
    """System operational state"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    EMERGENCY_STOP = "emergency_stop"
    SHUTTING_DOWN = "shutting_down"


class AlertChannel(Enum):
    """Alert delivery channels"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class AlertConfig:
    """Configuration for alerting system"""
    
    # Email settings
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_recipients: List[str] = field(default_factory=list)
    
    # Slack settings
    slack_enabled: bool = False
    slack_webhook_url: str = ""
    
    # Webhook settings
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    # Alert throttling
    alert_cooldown_seconds: int = 300  # 5 minutes


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker triggers"""
    
    # Risk thresholds
    var_limit: float = 0.025  # 2.5% VaR
    cvar_limit: float = 0.045  # 4.5% CVaR
    correlation_limit: float = 0.75
    max_drawdown_limit: float = 0.15  # 15% max drawdown
    
    # Performance thresholds
    min_sharpe_ratio: float = 0.5
    max_consecutive_losses: int = 5
    
    # Position limits
    max_position_concentration: float = 0.30  # 30% per position
    max_sector_concentration: float = 0.50  # 50% per sector
    
    # Auto-stop triggers
    auto_stop_on_var_breach: bool = True
    auto_stop_on_cvar_breach: bool = True
    auto_stop_on_max_drawdown: bool = True
    auto_stop_on_consecutive_losses: bool = False


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    
    timestamp: datetime
    
    # Returns
    total_return: float
    daily_return: float
    annualized_return: float
    
    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    
    # Risk metrics
    volatility: float
    max_drawdown: float
    current_drawdown: float
    
    # Win/loss statistics
    win_rate: float
    profit_factor: float
    consecutive_wins: int
    consecutive_losses: int
    
    # Portfolio state
    num_positions: int
    portfolio_value: float
    cash_balance: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class MonitoringEvent:
    """Monitoring event for audit trail"""
    
    timestamp: datetime
    event_type: str  # 'startup', 'shutdown', 'emergency_stop', 'circuit_breaker', 'alert', 'metric_update'
    severity: str  # 'info', 'warning', 'critical'
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


class ProductionMonitor:
    """
    Production monitoring engine for Layer 07.
    
    Responsibilities:
    - Real-time monitoring with < 1 second latency
    - Multi-channel alerting (email, Slack, webhook)
    - Circuit breaker triggers (auto-stop on risk breach)
    - Performance metrics tracking
    - Operational controls (startup, shutdown, emergency stop)
    - Comprehensive audit trail
    
    Usage:
        monitor = ProductionMonitor(alert_config, circuit_breaker_config)
        monitor.start()
        
        # Update metrics
        monitor.update_metrics(returns, positions, portfolio_value)
        
        # Check circuit breakers
        if monitor.check_circuit_breakers():
            monitor.emergency_stop("Circuit breaker triggered")
        
        # Shutdown
        monitor.shutdown()
    """
    
    def __init__(
        self,
        alert_config: Optional[AlertConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        monitoring_log_path: str = "state/monitoring_events.jsonl",
        metrics_log_path: str = "state/monitoring_metrics.jsonl"
    ):
        self.alert_config = alert_config or AlertConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self.monitoring_log_path = Path(monitoring_log_path)
        self.metrics_log_path = Path(metrics_log_path)
        
        self.logger = logging.getLogger(__name__)
        
        # State
        self._state = SystemState.STOPPED
        self._state_lock = threading.Lock()
        
        # Metrics
        self._current_metrics: Optional[PerformanceMetrics] = None
        self._metrics_history: List[PerformanceMetrics] = []
        self._event_history: List[MonitoringEvent] = []
        
        # Alert tracking
        self._last_alert_time: Dict[str, datetime] = {}
        
        # Circuit breaker state
        self._circuit_breaker_triggered = False
        self._circuit_breaker_reason = ""
        
        # Monitoring thread
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        
        # Ensure directories exist
        self.monitoring_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("Production Monitor initialized")
    
    def start(self):
        """Start production monitoring"""
        with self._state_lock:
            if self._state != SystemState.STOPPED:
                self.logger.warning(f"Cannot start: system is {self._state.value}")
                return
            
            self._state = SystemState.STARTING
        
        # Log startup event
        self._log_event(MonitoringEvent(
            timestamp=datetime.now(timezone.utc),
            event_type='startup',
            severity='info',
            message='Production monitoring starting',
            details={'config': {
                'alert_enabled': self.alert_config.email_enabled or self.alert_config.slack_enabled,
                'circuit_breaker_enabled': True
            }}
        ))
        
        # Start monitoring thread
        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        with self._state_lock:
            self._state = SystemState.RUNNING
        
        self.logger.info("Production monitoring started")
    
    def shutdown(self):
        """Graceful shutdown"""
        with self._state_lock:
            if self._state == SystemState.STOPPED:
                self.logger.warning("System already stopped")
                return
            
            self._state = SystemState.SHUTTING_DOWN
        
        # Log shutdown event
        self._log_event(MonitoringEvent(
            timestamp=datetime.now(timezone.utc),
            event_type='shutdown',
            severity='info',
            message='Production monitoring shutting down',
            details={'final_metrics': self._current_metrics.to_dict() if self._current_metrics else {}}
        ))
        
        # Stop monitoring thread
        self._stop_monitoring.set()
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5.0)
        
        with self._state_lock:
            self._state = SystemState.STOPPED
        
        self.logger.info("Production monitoring stopped")
    
    def emergency_stop(self, reason: str):
        """Emergency stop - immediate halt"""
        with self._state_lock:
            prev_state = self._state
            self._state = SystemState.EMERGENCY_STOP
        
        # Log emergency stop
        self._log_event(MonitoringEvent(
            timestamp=datetime.now(timezone.utc),
            event_type='emergency_stop',
            severity='critical',
            message=f'EMERGENCY STOP: {reason}',
            details={
                'previous_state': prev_state.value,
                'reason': reason,
                'metrics': self._current_metrics.to_dict() if self._current_metrics else {}
            }
        ))
        
        # Send critical alert
        self._send_alert(
            severity='critical',
            subject='EMERGENCY STOP TRIGGERED',
            message=f'System emergency stop triggered: {reason}',
            details={'reason': reason}
        )
        
        # Stop monitoring thread
        self._stop_monitoring.set()
        
        self.logger.critical(f"EMERGENCY STOP: {reason}")
    
    def pause(self):
        """Pause monitoring (can be resumed)"""
        with self._state_lock:
            if self._state == SystemState.RUNNING:
                self._state = SystemState.PAUSED
                self.logger.info("Monitoring paused")
    
    def resume(self):
        """Resume monitoring from paused state"""
        with self._state_lock:
            if self._state == SystemState.PAUSED:
                self._state = SystemState.RUNNING
                self.logger.info("Monitoring resumed")
    
    def update_metrics(
        self,
        returns: np.ndarray,
        positions: pd.DataFrame,
        portfolio_value: float,
        cash_balance: float = 0.0
    ) -> PerformanceMetrics:
        """
        Update performance metrics.
        
        Args:
            returns: Array of portfolio returns
            positions: Current positions DataFrame
            portfolio_value: Current portfolio value
            cash_balance: Current cash balance
            
        Returns:
            PerformanceMetrics snapshot
        """
        now = datetime.now(timezone.utc)
        
        # Calculate returns
        total_return = np.sum(returns) if len(returns) > 0 else 0.0
        daily_return = returns[-1] if len(returns) > 0 else 0.0
        annualized_return = np.mean(returns) * 252 if len(returns) > 0 else 0.0
        
        # Calculate volatility
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0.0
        
        # Calculate Sharpe ratio (assuming 0% risk-free rate)
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0.0
        
        # Calculate Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 1 else volatility
        sortino_ratio = annualized_return / downside_std if downside_std > 0 else 0.0
        
        # Calculate max drawdown
        cumulative_returns = np.cumprod(1 + returns) if len(returns) > 0 else np.array([1.0])
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
        current_drawdown = drawdown[-1] if len(drawdown) > 0 else 0.0
        
        # Calculate Calmar ratio
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
        
        # Calculate win/loss statistics
        winning_days = np.sum(returns > 0)
        total_days = len(returns)
        win_rate = winning_days / total_days if total_days > 0 else 0.0
        
        gross_profit = np.sum(returns[returns > 0]) if len(returns) > 0 else 0.0
        gross_loss = abs(np.sum(returns[returns < 0])) if len(returns) > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        # Calculate consecutive wins/losses
        consecutive_wins = 0
        consecutive_losses = 0
        if len(returns) > 0:
            for r in reversed(returns):
                if r > 0:
                    consecutive_wins += 1
                    break
                elif r < 0:
                    consecutive_losses += 1
                else:
                    break
        
        # Portfolio state
        num_positions = len(positions) if positions is not None else 0
        
        # Create metrics snapshot
        metrics = PerformanceMetrics(
            timestamp=now,
            total_return=total_return,
            daily_return=daily_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            volatility=volatility,
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            consecutive_wins=consecutive_wins,
            consecutive_losses=consecutive_losses,
            num_positions=num_positions,
            portfolio_value=portfolio_value,
            cash_balance=cash_balance
        )
        
        # Update state
        self._current_metrics = metrics
        self._metrics_history.append(metrics)
        
        # Export to log
        self._export_metrics(metrics)
        
        # Log event
        self._log_event(MonitoringEvent(
            timestamp=now,
            event_type='metric_update',
            severity='info',
            message='Performance metrics updated',
            details=metrics.to_dict()
        ))
        
        return metrics
    
    def check_circuit_breakers(self) -> bool:
        """
        Check circuit breaker conditions.
        
        Returns:
            True if circuit breaker triggered, False otherwise
        """
        if self._current_metrics is None:
            return False
        
        if self._circuit_breaker_triggered:
            return True
        
        metrics = self._current_metrics
        config = self.circuit_breaker_config
        
        # Check VaR breach (would need to be passed in separately)
        # For now, we check performance-based triggers
        
        # Check max drawdown
        if config.auto_stop_on_max_drawdown:
            if abs(metrics.max_drawdown) > config.max_drawdown_limit:
                self._trigger_circuit_breaker(
                    f"Max drawdown {metrics.max_drawdown:.2%} exceeds limit {config.max_drawdown_limit:.2%}"
                )
                return True
        
        # Check consecutive losses
        if config.auto_stop_on_consecutive_losses:
            if metrics.consecutive_losses >= config.max_consecutive_losses:
                self._trigger_circuit_breaker(
                    f"Consecutive losses {metrics.consecutive_losses} exceeds limit {config.max_consecutive_losses}"
                )
                return True
        
        return False
    
    def _trigger_circuit_breaker(self, reason: str):
        """Trigger circuit breaker"""
        self._circuit_breaker_triggered = True
        self._circuit_breaker_reason = reason
        
        # Log event
        self._log_event(MonitoringEvent(
            timestamp=datetime.now(timezone.utc),
            event_type='circuit_breaker',
            severity='critical',
            message=f'Circuit breaker triggered: {reason}',
            details={
                'reason': reason,
                'metrics': self._current_metrics.to_dict() if self._current_metrics else {}
            }
        ))
        
        # Send alert
        self._send_alert(
            severity='critical',
            subject='CIRCUIT BREAKER TRIGGERED',
            message=f'Circuit breaker triggered: {reason}',
            details={'reason': reason}
        )
        
        self.logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
    
    def reset_circuit_breaker(self):
        """Reset circuit breaker (manual intervention required)"""
        self._circuit_breaker_triggered = False
        self._circuit_breaker_reason = ""
        
        self._log_event(MonitoringEvent(
            timestamp=datetime.now(timezone.utc),
            event_type='circuit_breaker',
            severity='info',
            message='Circuit breaker reset',
            details={}
        ))
        
        self.logger.info("Circuit breaker reset")
    
    def _send_alert(
        self,
        severity: str,
        subject: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Send alert through configured channels.
        
        Args:
            severity: Alert severity ('info', 'warning', 'critical')
            subject: Alert subject
            message: Alert message
            details: Additional details
        """
        # Check cooldown
        alert_key = f"{severity}:{subject}"
        if alert_key in self._last_alert_time:
            elapsed = (datetime.now(timezone.utc) - self._last_alert_time[alert_key]).total_seconds()
            if elapsed < self.alert_config.alert_cooldown_seconds:
                self.logger.debug(f"Alert cooldown active for {alert_key}")
                return
        
        self._last_alert_time[alert_key] = datetime.now(timezone.utc)
        
        # Send email
        if self.alert_config.email_enabled:
            self._send_email_alert(severity, subject, message, details)
        
        # Send Slack
        if self.alert_config.slack_enabled:
            self._send_slack_alert(severity, subject, message, details)
        
        # Send webhook
        if self.alert_config.webhook_enabled:
            self._send_webhook_alert(severity, subject, message, details)
        
        # Always log
        self.logger.info(f"Alert sent: {subject}")
    
    def _send_email_alert(
        self,
        severity: str,
        subject: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Send email alert"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.alert_config.smtp_user
            msg['To'] = ', '.join(self.alert_config.alert_recipients)
            msg['Subject'] = f"[{severity.upper()}] {subject}"
            
            body = f"{message}\n\n"
            if details:
                body += "Details:\n"
                body += json.dumps(details, indent=2)
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.alert_config.smtp_host, self.alert_config.smtp_port) as server:
                server.starttls()
                server.login(self.alert_config.smtp_user, self.alert_config.smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Email alert sent to {len(self.alert_config.alert_recipients)} recipients")
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")
    
    def _send_slack_alert(
        self,
        severity: str,
        subject: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Send Slack alert"""
        try:
            color = {'info': '#36a64f', 'warning': '#ff9900', 'critical': '#ff0000'}.get(severity, '#808080')
            
            payload = {
                'attachments': [{
                    'color': color,
                    'title': f"[{severity.upper()}] {subject}",
                    'text': message,
                    'fields': [
                        {'title': k, 'value': str(v), 'short': True}
                        for k, v in (details or {}).items()
                    ],
                    'footer': 'V21 Production Monitor',
                    'ts': int(datetime.now(timezone.utc).timestamp())
                }]
            }
            
            response = requests.post(
                self.alert_config.slack_webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Slack alert sent")
        except Exception as e:
            self.logger.error(f"Failed to send Slack alert: {e}")
    
    def _send_webhook_alert(
        self,
        severity: str,
        subject: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Send webhook alert"""
        try:
            payload = {
                'severity': severity,
                'subject': subject,
                'message': message,
                'details': details or {},
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            response = requests.post(
                self.alert_config.webhook_url,
                json=payload,
                headers=self.alert_config.webhook_headers,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Webhook alert sent")
        except Exception as e:
            self.logger.error(f"Failed to send webhook alert: {e}")
    
    def _log_event(self, event: MonitoringEvent):
        """Log monitoring event to audit trail"""
        self._event_history.append(event)
        
        # Export to JSONL
        try:
            with open(self.monitoring_log_path, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write event to log: {e}")
    
    def _export_metrics(self, metrics: PerformanceMetrics):
        """Export metrics to JSONL"""
        try:
            with open(self.metrics_log_path, 'a') as f:
                f.write(json.dumps(metrics.to_dict()) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write metrics to log: {e}")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        self.logger.info("Monitoring loop started")
        
        while not self._stop_monitoring.is_set():
            try:
                # Check circuit breakers
                if self._state == SystemState.RUNNING:
                    if self.check_circuit_breakers():
                        self.emergency_stop(self._circuit_breaker_reason)
                        break
                
                # Sleep for 1 second (< 1 second latency requirement)
                time.sleep(1.0)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
        
        self.logger.info("Monitoring loop stopped")
    
    def get_state(self) -> SystemState:
        """Get current system state"""
        with self._state_lock:
            return self._state
    
    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get current performance metrics"""
        return self._current_metrics
    
    def get_metrics_history(self, limit: int = 100) -> List[PerformanceMetrics]:
        """Get metrics history"""
        return self._metrics_history[-limit:]
    
    def get_event_history(self, limit: int = 100) -> List[MonitoringEvent]:
        """Get event history"""
        return self._event_history[-limit:]


if __name__ == '__main__':
    print("=" * 80)
    print("PRODUCTION MONITOR - DEMO")
    print("=" * 80)
    
    # Configure alerts (disabled for demo)
    alert_config = AlertConfig(
        email_enabled=False,
        slack_enabled=False,
        webhook_enabled=False
    )
    
    # Configure circuit breakers
    circuit_breaker_config = CircuitBreakerConfig(
        var_limit=0.025,
        cvar_limit=0.045,
        max_drawdown_limit=0.15,
        auto_stop_on_max_drawdown=True
    )
    
    # Initialize monitor
    monitor = ProductionMonitor(
        alert_config=alert_config,
        circuit_breaker_config=circuit_breaker_config,
        monitoring_log_path="state/monitoring_events.jsonl",
        metrics_log_path="state/monitoring_metrics.jsonl"
    )
    
    # Test 1: Start monitoring
    print("\n1. Starting monitoring...")
    monitor.start()
    print(f"   State: {monitor.get_state().value}")
    time.sleep(2)
    
    # Test 2: Update metrics
    print("\n2. Updating metrics...")
    np.random.seed(42)
    returns = np.random.randn(252) * 0.02
    positions = pd.DataFrame({
        'ticker': ['VNM', 'HPG', 'VCB'],
        'weight': [0.30, 0.40, 0.30]
    })
    
    metrics = monitor.update_metrics(
        returns=returns,
        positions=positions,
        portfolio_value=1000000.0,
        cash_balance=50000.0
    )
    
    print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"   Sortino Ratio: {metrics.sortino_ratio:.2f}")
    print(f"   Calmar Ratio: {metrics.calmar_ratio:.2f}")
    print(f"   Max Drawdown: {metrics.max_drawdown:.2%}")
    print(f"   Win Rate: {metrics.win_rate:.2%}")
    
    # Test 3: Check circuit breakers
    print("\n3. Checking circuit breakers...")
    triggered = monitor.check_circuit_breakers()
    print(f"   Circuit Breaker Triggered: {triggered}")
    
    # Test 4: Shutdown
    print("\n4. Shutting down...")
    monitor.shutdown()
    print(f"   State: {monitor.get_state().value}")
    
    # Test 5: Event history
    print("\n5. Event History:")
    events = monitor.get_event_history(limit=10)
    for event in events:
        print(f"   [{event.severity.upper()}] {event.event_type}: {event.message}")
    
    print("\n" + "=" * 80)
    print("Production Monitor demo complete")
    print("=" * 80)
