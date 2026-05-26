"""Alert engine for system monitoring and notifications.

Implements alert management with:
- AlertRule for defining alert conditions
- AlertManager for rule management and alert firing
- Multiple trigger types: risk_breach, model_drift, data_anomaly, execution_failure
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
from datetime import datetime, timedelta
import threading


logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertTriggerType(Enum):
    """Alert trigger types."""
    RISK_BREACH = "risk_breach"
    MODEL_DRIFT = "model_drift"
    DATA_ANOMALY = "data_anomaly"
    EXECUTION_FAILURE = "execution_failure"
    THRESHOLD_EXCEEDED = "threshold_exceeded"
    RATE_LIMIT = "rate_limit"
    CUSTOM = "custom"


class AlertState(Enum):
    """Alert state."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """Alert instance."""
    alert_id: str
    rule_name: str
    trigger_type: AlertTriggerType
    severity: AlertSeverity
    message: str
    state: AlertState = AlertState.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    fired_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "rule_name": self.rule_name,
            "trigger_type": self.trigger_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "state": self.state.value,
            "metadata": self.metadata,
            "fired_at": self.fired_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None
        }


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    trigger_type: AlertTriggerType
    severity: AlertSeverity
    condition: Callable[[Dict[str, Any]], bool]
    message_template: str
    enabled: bool = True
    cooldown_seconds: int = 300  # 5 minutes default cooldown
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate rule condition.
        
        Args:
            context: Context data for evaluation
            
        Returns:
            True if condition is met
        """
        if not self.enabled:
            return False
        
        try:
            return self.condition(context)
        except Exception as e:
            logger.error("Error evaluating rule %s: %s", self.name, e)
            return False
    
    def format_message(self, context: Dict[str, Any]) -> str:
        """Format alert message with context.
        
        Args:
            context: Context data for message formatting
            
        Returns:
            Formatted message string
        """
        try:
            return self.message_template.format(**context)
        except Exception as e:
            logger.error("Error formatting message for rule %s: %s", self.name, e)
            return self.message_template


class AlertManager:
    """Alert manager for rule management and alert firing."""
    
    def __init__(self):
        """Initialize alert manager."""
        self._rules: Dict[str, AlertRule] = {}
        self._rules_lock = threading.Lock()
        
        self._alerts: List[Alert] = []
        self._alerts_lock = threading.Lock()
        
        # Track last fire time for cooldown
        self._last_fired: Dict[str, datetime] = {}
        self._fired_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "total_alerts": 0,
            "active_alerts": 0,
            "resolved_alerts": 0,
            "by_severity": {
                "info": 0,
                "warning": 0,
                "critical": 0
            },
            "by_trigger": {}
        }
        self._stats_lock = threading.Lock()
        
        logger.info("AlertManager initialized")
    
    def register_rule(self, rule: AlertRule):
        """Register an alert rule.
        
        Args:
            rule: AlertRule to register
        """
        with self._rules_lock:
            if rule.name in self._rules:
                logger.warning("Rule %s already exists, replacing", rule.name)
            self._rules[rule.name] = rule
        
        logger.info("Registered alert rule: %s (type=%s, severity=%s)", 
                   rule.name, rule.trigger_type.value, rule.severity.value)
    
    def unregister_rule(self, rule_name: str) -> bool:
        """Unregister an alert rule.
        
        Args:
            rule_name: Name of rule to unregister
            
        Returns:
            True if rule was removed
        """
        with self._rules_lock:
            if rule_name in self._rules:
                del self._rules[rule_name]
                logger.info("Unregistered alert rule: %s", rule_name)
                return True
        return False
    
    def check(self, context: Dict[str, Any]) -> List[Alert]:
        """Check all rules and fire alerts if conditions are met.
        
        Args:
            context: Context data for rule evaluation
            
        Returns:
            List of newly fired alerts
        """
        fired_alerts = []
        
        with self._rules_lock:
            rules = list(self._rules.values())
        
        for rule in rules:
            # Check if rule condition is met
            if not rule.evaluate(context):
                continue
            
            # Check cooldown
            if not self._check_cooldown(rule.name, rule.cooldown_seconds):
                logger.debug("Rule %s in cooldown, skipping", rule.name)
                continue
            
            # Fire alert
            alert = self._fire_alert(rule, context)
            fired_alerts.append(alert)
        
        return fired_alerts
    
    def fire_alert(self, rule_name: str, context: Dict[str, Any]) -> Optional[Alert]:
        """Manually fire an alert for a specific rule.
        
        Args:
            rule_name: Name of rule to fire
            context: Context data for alert
            
        Returns:
            Alert instance or None if rule not found
        """
        with self._rules_lock:
            rule = self._rules.get(rule_name)
        
        if not rule:
            logger.warning("Rule %s not found", rule_name)
            return None
        
        # Check cooldown
        if not self._check_cooldown(rule.name, rule.cooldown_seconds):
            logger.debug("Rule %s in cooldown, skipping", rule.name)
            return None
        
        return self._fire_alert(rule, context)
    
    def _fire_alert(self, rule: AlertRule, context: Dict[str, Any]) -> Alert:
        """Fire an alert.
        
        Args:
            rule: AlertRule that triggered
            context: Context data
            
        Returns:
            Alert instance
        """
        # Generate alert ID
        alert_id = f"{rule.name}_{datetime.utcnow().timestamp()}"
        
        # Format message
        message = rule.format_message(context)
        
        # Create alert
        alert = Alert(
            alert_id=alert_id,
            rule_name=rule.name,
            trigger_type=rule.trigger_type,
            severity=rule.severity,
            message=message,
            metadata=context.copy()
        )
        
        # Store alert
        with self._alerts_lock:
            self._alerts.append(alert)
            # Keep last 10000 alerts
            if len(self._alerts) > 10000:
                self._alerts = self._alerts[-10000:]
        
        # Update last fired time
        with self._fired_lock:
            self._last_fired[rule.name] = datetime.utcnow()
        
        # Update statistics
        self._update_statistics(alert)
        
        # Log alert
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.CRITICAL
        }.get(alert.severity, logging.INFO)
        
        logger.log(log_level, "ALERT [%s] %s: %s", 
                  alert.severity.value.upper(), rule.name, message)
        
        return alert
    
    def _check_cooldown(self, rule_name: str, cooldown_seconds: int) -> bool:
        """Check if rule is in cooldown period.
        
        Args:
            rule_name: Rule name
            cooldown_seconds: Cooldown period in seconds
            
        Returns:
            True if not in cooldown
        """
        with self._fired_lock:
            last_fired = self._last_fired.get(rule_name)
        
        if not last_fired:
            return True
        
        elapsed = (datetime.utcnow() - last_fired).total_seconds()
        return elapsed >= cooldown_seconds
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert.
        
        Args:
            alert_id: Alert ID to resolve
            
        Returns:
            True if alert was resolved
        """
        with self._alerts_lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id and alert.state == AlertState.ACTIVE:
                    alert.state = AlertState.RESOLVED
                    alert.resolved_at = datetime.utcnow()
                    logger.info("Resolved alert: %s", alert_id)
                    return True
        return False
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.
        
        Args:
            alert_id: Alert ID to acknowledge
            
        Returns:
            True if alert was acknowledged
        """
        with self._alerts_lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id and alert.state == AlertState.ACTIVE:
                    alert.state = AlertState.ACKNOWLEDGED
                    alert.acknowledged_at = datetime.utcnow()
                    logger.info("Acknowledged alert: %s", alert_id)
                    return True
        return False
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get active alerts.
        
        Args:
            severity: Optional severity filter
            
        Returns:
            List of active alerts
        """
        with self._alerts_lock:
            alerts = [a for a in self._alerts if a.state == AlertState.ACTIVE]
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            return alerts.copy()
    
    def get_alerts_by_rule(self, rule_name: str) -> List[Alert]:
        """Get all alerts for a specific rule.
        
        Args:
            rule_name: Rule name
            
        Returns:
            List of alerts
        """
        with self._alerts_lock:
            return [a for a in self._alerts if a.rule_name == rule_name]
    
    def get_alerts_by_trigger(self, trigger_type: AlertTriggerType) -> List[Alert]:
        """Get all alerts for a specific trigger type.
        
        Args:
            trigger_type: Trigger type
            
        Returns:
            List of alerts
        """
        with self._alerts_lock:
            return [a for a in self._alerts if a.trigger_type == trigger_type]
    
    def enable_rule(self, rule_name: str) -> bool:
        """Enable a rule.
        
        Args:
            rule_name: Rule name
            
        Returns:
            True if rule was enabled
        """
        with self._rules_lock:
            rule = self._rules.get(rule_name)
            if rule:
                rule.enabled = True
                logger.info("Enabled rule: %s", rule_name)
                return True
        return False
    
    def disable_rule(self, rule_name: str) -> bool:
        """Disable a rule.
        
        Args:
            rule_name: Rule name
            
        Returns:
            True if rule was disabled
        """
        with self._rules_lock:
            rule = self._rules.get(rule_name)
            if rule:
                rule.enabled = False
                logger.info("Disabled rule: %s", rule_name)
                return True
        return False
    
    def _update_statistics(self, alert: Alert):
        """Update statistics for a new alert."""
        with self._stats_lock:
            self._stats["total_alerts"] += 1
            self._stats["active_alerts"] += 1
            self._stats["by_severity"][alert.severity.value] += 1
            
            trigger_key = alert.trigger_type.value
            self._stats["by_trigger"][trigger_key] = self._stats["by_trigger"].get(trigger_key, 0) + 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get alert statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        with self._alerts_lock:
            stats["active_alerts"] = sum(1 for a in self._alerts if a.state == AlertState.ACTIVE)
            stats["resolved_alerts"] = sum(1 for a in self._alerts if a.state == AlertState.RESOLVED)
        
        with self._rules_lock:
            stats["total_rules"] = len(self._rules)
            stats["enabled_rules"] = sum(1 for r in self._rules.values() if r.enabled)
        
        return stats
    
    def cleanup_old_alerts(self, max_age_hours: int = 24) -> int:
        """Remove old resolved alerts.
        
        Args:
            max_age_hours: Maximum age for resolved alerts
            
        Returns:
            Number of alerts removed
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        removed = 0
        
        with self._alerts_lock:
            original_count = len(self._alerts)
            self._alerts = [
                a for a in self._alerts
                if a.state == AlertState.ACTIVE or 
                   (a.resolved_at and a.resolved_at > cutoff)
            ]
            removed = original_count - len(self._alerts)
        
        if removed > 0:
            logger.info("Cleaned up %d old alerts", removed)
        
        return removed


# Predefined alert rule factories

def create_risk_breach_rule(
    name: str,
    threshold: float,
    metric_key: str,
    severity: AlertSeverity = AlertSeverity.CRITICAL
) -> AlertRule:
    """Create a risk breach alert rule.
    
    Args:
        name: Rule name
        threshold: Threshold value
        metric_key: Key in context to check
        severity: Alert severity
        
    Returns:
        AlertRule instance
    """
    def condition(context: Dict[str, Any]) -> bool:
        value = context.get(metric_key, 0.0)
        return value > threshold
    
    return AlertRule(
        name=name,
        trigger_type=AlertTriggerType.RISK_BREACH,
        severity=severity,
        condition=condition,
        message_template=f"{metric_key} exceeded threshold: {{{metric_key}}} > {threshold}"
    )


def create_model_drift_rule(
    name: str,
    max_drift: float,
    severity: AlertSeverity = AlertSeverity.WARNING
) -> AlertRule:
    """Create a model drift alert rule.
    
    Args:
        name: Rule name
        max_drift: Maximum allowed drift
        severity: Alert severity
        
    Returns:
        AlertRule instance
    """
    def condition(context: Dict[str, Any]) -> bool:
        drift = context.get("model_drift", 0.0)
        return drift > max_drift
    
    return AlertRule(
        name=name,
        trigger_type=AlertTriggerType.MODEL_DRIFT,
        severity=severity,
        condition=condition,
        message_template=f"Model drift detected: {{model_drift:.4f}} > {max_drift}"
    )


def create_execution_failure_rule(
    name: str,
    max_failure_rate: float = 0.05,
    severity: AlertSeverity = AlertSeverity.CRITICAL
) -> AlertRule:
    """Create an execution failure alert rule.
    
    Args:
        name: Rule name
        max_failure_rate: Maximum failure rate (0.05 = 5%)
        severity: Alert severity
        
    Returns:
        AlertRule instance
    """
    def condition(context: Dict[str, Any]) -> bool:
        failure_rate = context.get("failure_rate", 0.0)
        return failure_rate > max_failure_rate
    
    return AlertRule(
        name=name,
        trigger_type=AlertTriggerType.EXECUTION_FAILURE,
        severity=severity,
        condition=condition,
        message_template=f"Execution failure rate high: {{failure_rate:.2%}} > {max_failure_rate:.2%}"
    )
