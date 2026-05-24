"""
Dashboard Data Models
OMEGA_QUANT Phase 17: Dashboard & Monitoring
Point-in-Time Safe: All metrics use event_time for temporal accuracy
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import numpy as np


class MetricType(Enum):
    """Metric type enumeration"""
    EXECUTION = "execution"
    RISK = "risk"
    PERFORMANCE = "performance"
    SYSTEM = "system"


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ExecutionMetrics:
    """Real-time execution metrics snapshot"""
    timestamp: datetime
    strategy_id: str
    
    # Order metrics
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0
    
    # Fill metrics
    avg_fill_time_ms: float = 0.0
    fill_rate: float = 0.0  # orders_filled / orders_submitted
    
    # Slippage metrics
    avg_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    slippage_std_bps: float = 0.0
    
    # Volume metrics
    total_volume: float = 0.0
    total_notional: float = 0.0
    
    # Latency metrics
    avg_latency_us: float = 0.0
    p50_latency_us: float = 0.0
    p95_latency_us: float = 0.0
    p99_latency_us: float = 0.0
    max_latency_us: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'strategy_id': self.strategy_id,
            'orders_submitted': self.orders_submitted,
            'orders_filled': self.orders_filled,
            'orders_cancelled': self.orders_cancelled,
            'orders_rejected': self.orders_rejected,
            'avg_fill_time_ms': self.avg_fill_time_ms,
            'fill_rate': self.fill_rate,
            'avg_slippage_bps': self.avg_slippage_bps,
            'max_slippage_bps': self.max_slippage_bps,
            'slippage_std_bps': self.slippage_std_bps,
            'total_volume': self.total_volume,
            'total_notional': self.total_notional,
            'avg_latency_us': self.avg_latency_us,
            'p50_latency_us': self.p50_latency_us,
            'p95_latency_us': self.p95_latency_us,
            'p99_latency_us': self.p99_latency_us,
            'max_latency_us': self.max_latency_us
        }


@dataclass
class RiskMetrics:
    """Real-time risk metrics snapshot"""
    timestamp: datetime
    strategy_id: str
    
    # Position risk
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    leverage: float = 0.0
    
    # P&L metrics
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Drawdown metrics
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    drawdown_duration_minutes: int = 0
    
    # Risk measures
    var_95: float = 0.0  # Value at Risk 95%
    var_99: float = 0.0  # Value at Risk 99%
    expected_shortfall: float = 0.0  # CVaR
    
    # Volatility
    realized_volatility: float = 0.0
    implied_volatility: float = 0.0
    
    # Concentration
    max_position_pct: float = 0.0
    top5_concentration: float = 0.0
    
    # Limit utilization
    position_limit_utilization: float = 0.0
    order_limit_utilization: float = 0.0
    risk_limit_utilization: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'strategy_id': self.strategy_id,
            'gross_exposure': self.gross_exposure,
            'net_exposure': self.net_exposure,
            'leverage': self.leverage,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'total_pnl': self.total_pnl,
            'current_drawdown': self.current_drawdown,
            'max_drawdown': self.max_drawdown,
            'drawdown_duration_minutes': self.drawdown_duration_minutes,
            'var_95': self.var_95,
            'var_99': self.var_99,
            'expected_shortfall': self.expected_shortfall,
            'realized_volatility': self.realized_volatility,
            'implied_volatility': self.implied_volatility,
            'max_position_pct': self.max_position_pct,
            'top5_concentration': self.top5_concentration,
            'position_limit_utilization': self.position_limit_utilization,
            'order_limit_utilization': self.order_limit_utilization,
            'risk_limit_utilization': self.risk_limit_utilization
        }


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    timestamp: datetime
    strategy_id: str
    period: str  # '1m', '5m', '1h', '1d', 'inception'
    
    # Returns
    total_return: float = 0.0
    annualized_return: float = 0.0
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    
    # Win/Loss metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Consistency
    daily_return_std: float = 0.0
    monthly_return_std: float = 0.0
    
    # Benchmark comparison
    alpha: float = 0.0
    beta: float = 0.0
    correlation: float = 0.0
    tracking_error: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'strategy_id': self.strategy_id,
            'period': self.period,
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'information_ratio': self.information_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'daily_return_std': self.daily_return_std,
            'monthly_return_std': self.monthly_return_std,
            'alpha': self.alpha,
            'beta': self.beta,
            'correlation': self.correlation,
            'tracking_error': self.tracking_error
        }


@dataclass
class SystemMetrics:
    """System health and performance metrics"""
    timestamp: datetime
    
    # CPU metrics
    cpu_usage_pct: float = 0.0
    cpu_count: int = 0
    
    # Memory metrics
    memory_used_mb: float = 0.0
    memory_available_mb: float = 0.0
    memory_usage_pct: float = 0.0
    
    # Disk metrics
    disk_used_gb: float = 0.0
    disk_available_gb: float = 0.0
    disk_usage_pct: float = 0.0
    
    # Network metrics
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    
    # Process metrics
    active_strategies: int = 0
    active_orders: int = 0
    active_positions: int = 0
    
    # Queue metrics
    event_queue_size: int = 0
    order_queue_size: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'cpu_usage_pct': self.cpu_usage_pct,
            'cpu_count': self.cpu_count,
            'memory_used_mb': self.memory_used_mb,
            'memory_available_mb': self.memory_available_mb,
            'memory_usage_pct': self.memory_usage_pct,
            'disk_used_gb': self.disk_used_gb,
            'disk_available_gb': self.disk_available_gb,
            'disk_usage_pct': self.disk_usage_pct,
            'network_sent_mb': self.network_sent_mb,
            'network_recv_mb': self.network_recv_mb,
            'active_strategies': self.active_strategies,
            'active_orders': self.active_orders,
            'active_positions': self.active_positions,
            'event_queue_size': self.event_queue_size,
            'order_queue_size': self.order_queue_size
        }


@dataclass
class Alert:
    """Alert/notification model"""
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    metric_type: MetricType
    strategy_id: Optional[str]
    
    title: str
    message: str
    
    # Threshold breach details
    metric_name: str
    current_value: float
    threshold_value: float
    
    # Alert state
    is_active: bool = True
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    
    # Resolution
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'alert_id': self.alert_id,
            'timestamp': self.timestamp.isoformat(),
            'severity': self.severity.value,
            'metric_type': self.metric_type.value,
            'strategy_id': self.strategy_id,
            'title': self.title,
            'message': self.message,
            'metric_name': self.metric_name,
            'current_value': self.current_value,
            'threshold_value': self.threshold_value,
            'is_active': self.is_active,
            'acknowledged': self.acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_note': self.resolution_note
        }


@dataclass
class DashboardSnapshot:
    """Complete dashboard snapshot at a point in time"""
    timestamp: datetime
    
    execution_metrics: Dict[str, ExecutionMetrics] = field(default_factory=dict)
    risk_metrics: Dict[str, RiskMetrics] = field(default_factory=dict)
    performance_metrics: Dict[str, Dict[str, PerformanceMetrics]] = field(default_factory=dict)
    system_metrics: Optional[SystemMetrics] = None
    
    active_alerts: List[Alert] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'execution_metrics': {
                k: v.to_dict() for k, v in self.execution_metrics.items()
            },
            'risk_metrics': {
                k: v.to_dict() for k, v in self.risk_metrics.items()
            },
            'performance_metrics': {
                strategy_id: {
                    period: metrics.to_dict()
                    for period, metrics in periods.items()
                }
                for strategy_id, periods in self.performance_metrics.items()
            },
            'system_metrics': self.system_metrics.to_dict() if self.system_metrics else None,
            'active_alerts': [alert.to_dict() for alert in self.active_alerts]
        }
