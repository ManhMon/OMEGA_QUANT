"""
System Monitor & Alerting - OMEGA_QUANT Phase 7.
"""

from typing import Dict, Any, Callable, List
from dataclasses import dataclass, field
from .logger import StructuredLogger

logger = StructuredLogger("Monitor")

@dataclass
class AlertRule:
    """Rule for triggering alerts."""
    name: str
    metric_name: str
    threshold: float
    comparison: str  # ">", "<", ">=", "<=", "=="
    severity: str = "WARNING"

@dataclass
class MonitorConfig:
    """Configuration for SystemMonitor."""
    max_drawdown_threshold: float = 0.15
    volatility_threshold: float = 0.25
    max_data_age_minutes: int = 120
    alert_rules: List[AlertRule] = field(default_factory=list)

class SystemMonitor:
    """Monitors metrics against rules and triggers alerts."""
    
    def __init__(self, config: MonitorConfig = None):
        self.config = config or MonitorConfig()
        self.rules: List[AlertRule] = []
        self.active_alerts: List[Dict[str, Any]] = []
        
        # Add default rules from config
        if self.config.alert_rules:
            self.rules.extend(self.config.alert_rules)
        
    def add_rule(self, rule: AlertRule):
        """Add an alerting rule."""
        self.rules.append(rule)
        
    def evaluate(self, metrics_snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate rules against current metrics snapshot."""
        new_alerts = []
        
        # Flatten metrics for easier evaluation
        flat_metrics = {}
        flat_metrics.update(metrics_snapshot.get("counters", {}))
        flat_metrics.update(metrics_snapshot.get("gauges", {}))
        
        # Add avg from histograms
        for k, v in metrics_snapshot.get("histograms", {}).items():
            flat_metrics[f"{k}.avg"] = v.get("avg", 0.0)
            
        for rule in self.rules:
            value = flat_metrics.get(rule.metric_name)
            if value is None:
                continue
                
            triggered = False
            if rule.comparison == ">" and value > rule.threshold:
                triggered = True
            elif rule.comparison == "<" and value < rule.threshold:
                triggered = True
            elif rule.comparison == ">=" and value >= rule.threshold:
                triggered = True
            elif rule.comparison == "<=" and value <= rule.threshold:
                triggered = True
            elif rule.comparison == "==" and value == rule.threshold:
                triggered = True
                
            if triggered:
                alert = {
                    "rule": rule.name,
                    "metric": rule.metric_name,
                    "value": value,
                    "threshold": rule.threshold,
                    "severity": rule.severity
                }
                new_alerts.append(alert)
                self.active_alerts.append(alert)
                logger.warning(f"Alert Triggered: {rule.name}", alert_data=alert)
                
        return new_alerts
    
    def check_alerts(self, portfolio_values: Any) -> List[Dict[str, Any]]:
        """
        Check for alerts based on portfolio values.
        
        Args:
            portfolio_values: Series or array of portfolio values over time.
            
        Returns:
            List of triggered alerts.
        """
        import pandas as pd
        import numpy as np
        
        alerts = []
        
        if isinstance(portfolio_values, (pd.Series, np.ndarray, list)):
            values = pd.Series(portfolio_values) if not isinstance(portfolio_values, pd.Series) else portfolio_values
            
            # Check drawdown
            if len(values) > 1:
                peak = values.cummax()
                drawdown = (values - peak) / peak
                max_dd = -drawdown.min()
                
                if max_dd > self.config.max_drawdown_threshold:
                    alerts.append({
                        'type': 'drawdown',
                        'severity': 'HIGH',
                        'message': f'Max drawdown {max_dd:.2%} exceeds threshold {self.config.max_drawdown_threshold:.2%}',
                        'value': max_dd,
                        'threshold': self.config.max_drawdown_threshold
                    })
            
            # Check volatility
            if len(values) > 2:
                returns = values.pct_change().dropna()
                volatility = returns.std() * np.sqrt(252)
                
                if volatility > self.config.volatility_threshold:
                    alerts.append({
                        'type': 'volatility',
                        'severity': 'MEDIUM',
                        'message': f'Volatility {volatility:.2%} exceeds threshold {self.config.volatility_threshold:.2%}',
                        'value': volatility,
                        'threshold': self.config.volatility_threshold
                    })
        
        return alerts
    
    def check_health(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check system health status.
        
        Args:
            system_state: Dictionary with system state information.
            
        Returns:
            Health check result with status and details.
        """
        import pandas as pd
        
        health = {
            'status': 'healthy',
            'checks': {},
            'timestamp': pd.Timestamp.now()
        }
        
        # Check data freshness
        if 'last_update' in system_state:
            last_update = pd.Timestamp(system_state['last_update'])
            age_minutes = (pd.Timestamp.now() - last_update).total_seconds() / 60
            
            if age_minutes > self.config.max_data_age_minutes:
                health['status'] = 'degraded'
                health['checks']['data_freshness'] = {
                    'status': 'stale',
                    'age_minutes': age_minutes,
                    'threshold': self.config.max_data_age_minutes
                }
            else:
                health['checks']['data_freshness'] = {
                    'status': 'ok',
                    'age_minutes': age_minutes
                }
        
        # Check error rate
        if 'error_count' in system_state and 'total_count' in system_state:
            error_rate = system_state['error_count'] / max(system_state['total_count'], 1)
            if error_rate > 0.05:  # 5% error threshold
                health['status'] = 'unhealthy'
                health['checks']['error_rate'] = {
                    'status': 'high',
                    'rate': error_rate
                }
            else:
                health['checks']['error_rate'] = {
                    'status': 'ok',
                    'rate': error_rate
                }
        
        return health
    
    def record_resource_usage(self, resources: Dict[str, Any]) -> None:
        """
        Record resource usage metrics.
        
        Args:
            resources: Dictionary with resource usage (cpu, memory, etc.).
        """
        if not hasattr(self, '_resource_history'):
            self._resource_history = []
        
        import pandas as pd
        resources['timestamp'] = pd.Timestamp.now()
        self._resource_history.append(resources)
        
        # Keep only last 1000 records
        if len(self._resource_history) > 1000:
            self._resource_history = self._resource_history[-1000:]
    
    def check_resource_limits(self, resources: Dict[str, Any]) -> Dict[str, bool]:
        """
        Check if resource usage is within acceptable limits.
        
        Args:
            resources: Dictionary with resource usage (cpu_percent, memory_mb, etc.).
            
        Returns:
            Dictionary with status for each resource type.
        """
        status = {}
        
        # Check CPU usage (threshold: 80%)
        if 'cpu_percent' in resources:
            status['cpu_ok'] = resources['cpu_percent'] < 80.0
        
        # Check memory usage (threshold: 4096 MB = 4GB)
        if 'memory_mb' in resources:
            status['memory_ok'] = resources['memory_mb'] < 4096
        
        # Check disk I/O (threshold: 500 MB/s)
        if 'disk_io_mb' in resources:
            status['disk_io_ok'] = resources['disk_io_mb'] < 500
        
        return status
    
    def check_volatility_alerts(self, returns: Any) -> List[Dict[str, Any]]:
        """
        Check for volatility-based alerts.
        
        Args:
            returns: Series or array of returns.
            
        Returns:
            List of volatility alerts.
        """
        import pandas as pd
        import numpy as np
        
        alerts = []
        
        if isinstance(returns, (pd.Series, np.ndarray, list)):
            ret = pd.Series(returns) if not isinstance(returns, pd.Series) else returns
            
            if len(ret) > 2:
                volatility = ret.std() * np.sqrt(252)
                
                if volatility > self.config.volatility_threshold:
                    alerts.append({
                        'type': 'high_volatility',
                        'severity': 'MEDIUM',
                        'message': f'Volatility {volatility:.2%} exceeds threshold {self.config.volatility_threshold:.2%}',
                        'value': volatility,
                        'threshold': self.config.volatility_threshold
                    })
        
        return alerts
    
    def check_data_freshness(self, last_update: Any) -> List[Dict[str, Any]]:
        """
        Check data freshness alerts.
        
        Args:
            last_update: Timestamp of last data update.
            
        Returns:
            List of data freshness alerts.
        """
        import pandas as pd
        
        alerts = []
        
        last_update_ts = pd.Timestamp(last_update)
        age_minutes = (pd.Timestamp.now() - last_update_ts).total_seconds() / 60
        
        if age_minutes > self.config.max_data_age_minutes:
            alerts.append({
                'type': 'stale_data',
                'severity': 'HIGH',
                'message': f'Data is {age_minutes:.1f} minutes old (threshold: {self.config.max_data_age_minutes} minutes)',
                'age_minutes': age_minutes,
                'threshold': self.config.max_data_age_minutes
            })
        
        return alerts
