"""
Risk Monitor L07 - Phase 4.2 + P1 EMERGENCY PATCH
Layer 07: Monitoring & Observability

Real-time risk monitoring with event emission and dashboard integration.
Shifts risk monitoring logic to Layer 07 per Codex recommendation.

P1 PATCH: Consumes RiskBreachStatusV14 from Layer 04 instead of recalculating metrics.

Key Features:
- Real-time risk event emission (JSON)
- 30-minute monitoring intervals
- Integration with V14 ELITE Circuit Breaker
- Historical tracking and trend analysis
- Export to state/risk_events.jsonl
- P1 PATCH: Consumes L04 breach status (no recalculation)

Version: v21.1 (P1 EMERGENCY PATCH)
Date: 2026-05-07
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import logging


@dataclass
class RiskMonitorConfig:
    """Configuration for Risk Monitor L07"""
    
    # Monitoring frequency
    monitoring_interval_minutes: int = 30  # 30-minute intervals
    
    # Export settings
    event_log_path: str = 'state/risk_events.jsonl'
    dashboard_export_path: str = '.ly_state/session/risk_monitor_status.json'
    export_enabled: bool = True
    
    # Risk thresholds (aligned with V14 ELITE)
    var_limit: float = 0.025  # 2.5% VaR
    cvar_limit: float = 0.045  # 4.5% CVaR (P1 PATCH: adjusted from 4.0%)
    correlation_hard_stop: float = 0.75
    adv_limit_pct: float = 0.40
    
    # Alert settings
    alert_cooldown_minutes: int = 60  # Cooldown between alerts
    max_history_length: int = 1000


@dataclass
class RiskEvent:
    """Risk event for logging and monitoring"""
    
    timestamp: datetime
    event_type: str  # 'var_breach', 'cvar_breach', 'correlation_breach', 'adv_breach', 'limit_lock', 'derisk_action'
    severity: str  # 'info', 'warning', 'critical'
    metric_name: str
    metric_value: float
    limit: float
    is_breached: bool
    action_taken: str
    message: str
    
    # Additional context
    portfolio_exposure: Optional[float] = None
    num_positions: Optional[int] = None
    affected_tickers: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class RiskMonitorStatus:
    """Current risk monitoring status"""
    
    timestamp: datetime
    overall_status: str  # 'normal', 'warning', 'critical'
    
    # Current metrics
    var: float
    cvar: float
    max_correlation: float
    max_adv_participation: float
    
    # Breach flags
    var_breached: bool
    cvar_breached: bool
    correlation_breached: bool
    adv_breached: bool
    limit_lock_detected: bool
    
    # Portfolio state
    portfolio_exposure: float
    num_positions: int
    num_limit_locked: int
    
    # Actions
    derisk_action_pending: bool
    derisk_target_multiplier: float
    
    # Last update
    last_monitoring_time: datetime
    next_monitoring_time: datetime


class RiskMonitorL07:
    """
    Risk Monitor for Layer 07: Monitoring & Observability.
    
    Responsibilities:
    - Real-time risk event emission
    - 30-minute monitoring intervals
    - Integration with V14 ELITE Circuit Breaker
    - Historical tracking and trend analysis
    - Dashboard export
    
    Usage:
        monitor = RiskMonitorL07()
        monitor.monitor_risk(returns, market_data, positions)
        monitor.export_dashboard()
    """
    
    def __init__(self, config: Optional[RiskMonitorConfig] = None):
        self.config = config or RiskMonitorConfig()
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self._current_status: Optional[RiskMonitorStatus] = None
        self._event_history: List[RiskEvent] = []
        self._last_monitoring_time: Optional[datetime] = None
        self._last_alert_time: Dict[str, datetime] = {}
        
        # Ensure directories exist
        if self.config.export_enabled:
            Path(self.config.event_log_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.config.dashboard_export_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(
            f"Risk Monitor L07 initialized: "
            f"interval={self.config.monitoring_interval_minutes}min, "
            f"VaR={self.config.var_limit:.2%}, CVaR={self.config.cvar_limit:.2%}"
        )
    
    def should_monitor(self) -> bool:
        """
        Check if monitoring should run based on interval.
        
        Returns:
            True if monitoring should run, False otherwise
        """
        if self._last_monitoring_time is None:
            return True
        
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_monitoring_time).total_seconds() / 60
        
        return elapsed >= self.config.monitoring_interval_minutes
    
    def monitor_risk(
        self,
        returns: np.ndarray,
        market_data: pd.DataFrame,
        positions: Optional[pd.DataFrame] = None,
        returns_matrix: Optional[np.ndarray] = None,
        tickers: Optional[List[str]] = None,
        breach_status_from_l04: Optional[Dict[str, Any]] = None
    ) -> RiskMonitorStatus:
        """
        Monitor risk metrics and emit events.
        
        P1 PATCH: Consumes RiskBreachStatusV14 from Layer 04 instead of recalculating.
        
        Args:
            returns: Portfolio returns array
            market_data: Market data with limit-lock info
            positions: Current positions DataFrame
            returns_matrix: Returns matrix for correlation (optional)
            tickers: List of tickers (optional)
            breach_status_from_l04: Dict of breach statuses from L04 (P1 PATCH)
                Expected keys: 'var', 'cvar', 'correlation', 'adv', 'limit_lock'
                Each value should be a RiskBreachStatusV14 or similar object
            
        Returns:
            RiskMonitorStatus with current state
        """
        now = datetime.now(timezone.utc)
        
        # Check if monitoring should run
        if not self.should_monitor():
            if self._current_status:
                return self._current_status
            # First run, proceed
        
        self._last_monitoring_time = now
        
        # Initialize metrics
        var_value = 0.0
        cvar_value = 0.0
        max_correlation = 0.0
        max_adv_participation = 0.0
        
        var_breached = False
        cvar_breached = False
        correlation_breached = False
        adv_breached = False
        limit_lock_detected = False
        
        portfolio_exposure = 0.0
        num_positions = 0
        num_limit_locked = 0
        
        derisk_action_pending = False
        derisk_target_multiplier = 1.0
        
        # P1 PATCH: Consume breach status from Layer 04 if provided
        if breach_status_from_l04:
            # Extract VaR breach status
            if 'var' in breach_status_from_l04:
                var_status = breach_status_from_l04['var']
                var_value = getattr(var_status, 'metric_value', 0.0)
                var_breached = getattr(var_status, 'is_breached', False)
                
                if var_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='var_breach',
                        severity='critical',
                        metric_name='VaR',
                        metric_value=var_value,
                        limit=self.config.var_limit,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=getattr(var_status, 'message', f'VaR {var_value:.2%} exceeds limit')
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # Extract CVaR breach status
            if 'cvar' in breach_status_from_l04:
                cvar_status = breach_status_from_l04['cvar']
                cvar_value = getattr(cvar_status, 'metric_value', 0.0)
                cvar_breached = getattr(cvar_status, 'is_breached', False)
                
                if cvar_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='cvar_breach',
                        severity='critical',
                        metric_name='CVaR',
                        metric_value=cvar_value,
                        limit=self.config.cvar_limit,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=getattr(cvar_status, 'message', f'CVaR {cvar_value:.2%} exceeds limit')
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # Extract Correlation breach status
            if 'correlation' in breach_status_from_l04:
                corr_status = breach_status_from_l04['correlation']
                max_correlation = getattr(corr_status, 'metric_value', 0.0)
                correlation_breached = getattr(corr_status, 'is_breached', False)
                
                if correlation_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='correlation_breach',
                        severity='critical',
                        metric_name='Correlation',
                        metric_value=max_correlation,
                        limit=self.config.correlation_hard_stop,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=getattr(corr_status, 'message', f'Correlation {max_correlation:.2f} exceeds hard stop')
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # Extract ADV breach status
            if 'adv' in breach_status_from_l04:
                adv_status = breach_status_from_l04['adv']
                max_adv_participation = getattr(adv_status, 'metric_value', 0.0)
                adv_breached = getattr(adv_status, 'is_breached', False)
                
                if adv_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='adv_breach',
                        severity='warning',
                        metric_name='ADV',
                        metric_value=max_adv_participation,
                        limit=self.config.adv_limit_pct,
                        is_breached=True,
                        action_taken='block_new_positions',
                        message=getattr(adv_status, 'message', f'ADV participation {max_adv_participation:.1%} exceeds limit')
                    ))
            
            # Extract limit-lock status
            if 'limit_lock' in breach_status_from_l04:
                limit_lock_statuses = breach_status_from_l04['limit_lock']
                if isinstance(limit_lock_statuses, dict):
                    for ticker, lock_status in limit_lock_statuses.items():
                        if getattr(lock_status, 'is_limit_locked', False):
                            limit_lock_detected = True
                            num_limit_locked += 1
                            
                            self._emit_event(RiskEvent(
                                timestamp=now,
                                event_type='limit_lock',
                                severity='critical',
                                metric_name='LimitLock',
                                metric_value=getattr(lock_status, 'price_change_pct', 0.0),
                                limit=-0.07,
                                is_breached=True,
                                action_taken='block_sell_orders',
                                message=getattr(lock_status, 'reason', f'{ticker} limit-locked'),
                                affected_tickers=[ticker]
                            ))
        else:
            # P1 PATCH: Fallback to old calculation if no L04 status provided
            # (for backward compatibility during transition)
            # 1. Check VaR
            if len(returns) > 0:
                var_percentile = (1 - 0.95) * 100
                var_value = abs(np.percentile(returns, var_percentile))
                var_breached = var_value > self.config.var_limit
                
                if var_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='var_breach',
                        severity='critical',
                        metric_name='VaR',
                        metric_value=var_value,
                        limit=self.config.var_limit,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=f'VaR {var_value:.2%} exceeds limit {self.config.var_limit:.2%}'
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # 2. Check CVaR
            if len(returns) > 0:
                var_percentile = (1 - 0.95) * 100
                var_threshold = np.percentile(returns, var_percentile)
                tail_losses = returns[returns < var_threshold]
                
                if len(tail_losses) == 0:
                    cvar_value = abs(var_threshold)
                else:
                    cvar_value = abs(np.mean(tail_losses))
                
                cvar_breached = cvar_value > self.config.cvar_limit
                
                if cvar_breached:
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='cvar_breach',
                        severity='critical',
                        metric_name='CVaR',
                        metric_value=cvar_value,
                        limit=self.config.cvar_limit,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=f'CVaR {cvar_value:.2%} exceeds limit {self.config.cvar_limit:.2%}'
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # 3. Check Correlation
            if returns_matrix is not None and returns_matrix.shape[1] >= 2:
                corr_matrix = np.corrcoef(returns_matrix, rowvar=False)
                np.fill_diagonal(corr_matrix, 0.0)
                max_correlation = np.max(np.abs(corr_matrix))
                correlation_breached = max_correlation > self.config.correlation_hard_stop
                
                if correlation_breached:
                    max_idx = np.unravel_index(np.argmax(np.abs(corr_matrix)), corr_matrix.shape)
                    ticker1 = tickers[max_idx[0]] if tickers and max_idx[0] < len(tickers) else f"Asset_{max_idx[0]}"
                    ticker2 = tickers[max_idx[1]] if tickers and max_idx[1] < len(tickers) else f"Asset_{max_idx[1]}"
                    
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='correlation_breach',
                        severity='critical',
                        metric_name='Correlation',
                        metric_value=max_correlation,
                        limit=self.config.correlation_hard_stop,
                        is_breached=True,
                        action_taken='reduce_exposure',
                        message=f'Correlation {max_correlation:.2f} between {ticker1} and {ticker2} exceeds hard stop',
                        affected_tickers=[ticker1, ticker2]
                    ))
                    derisk_action_pending = True
                    derisk_target_multiplier = 0.8
            
            # 4. Check limit-lock (vectorized, P2 PATCH)
            if not market_data.empty:
                # Vectorized limit-lock detection
                price_change_pct = np.where(
                    market_data['reference_price'] > 0,
                    (market_data['current_price'] - market_data['reference_price']) / market_data['reference_price'],
                    0.0
                )
                bid_volume = market_data.get('bid_volume', pd.Series(0.0, index=market_data.index)).fillna(0.0)
                
                is_floor_locked = (
                    (price_change_pct <= -0.065) &
                    (bid_volume < 100.0)
                )
                
                for idx in market_data.index:
                    if is_floor_locked[idx]:
                        ticker = market_data.loc[idx, 'ticker']
                        limit_lock_detected = True
                        num_limit_locked += 1
                        
                        self._emit_event(RiskEvent(
                            timestamp=now,
                            event_type='limit_lock',
                            severity='critical',
                            metric_name='LimitLock',
                            metric_value=price_change_pct[idx],
                            limit=-0.07,
                            is_breached=True,
                            action_taken='block_sell_orders',
                            message=f'{ticker} floor-locked at {price_change_pct[idx]:.2%} with zero bids',
                            affected_tickers=[ticker]
                        ))
        
        # 5. Check ADV participation (from positions)
        if positions is not None and not positions.empty:
            num_positions = len(positions)
            if 'weight' in positions.columns:
                portfolio_exposure = positions['weight'].sum()
            
            if 'adv_participation' in positions.columns and not breach_status_from_l04:
                max_adv_participation = positions['adv_participation'].max()
                adv_breached = max_adv_participation > self.config.adv_limit_pct
                
                if adv_breached:
                    breached_tickers = positions[
                        positions['adv_participation'] > self.config.adv_limit_pct
                    ]['ticker'].tolist()
                    
                    self._emit_event(RiskEvent(
                        timestamp=now,
                        event_type='adv_breach',
                        severity='warning',
                        metric_name='ADV',
                        metric_value=max_adv_participation,
                        limit=self.config.adv_limit_pct,
                        is_breached=True,
                        action_taken='block_new_positions',
                        message=f'ADV participation {max_adv_participation:.1%} exceeds limit',
                        affected_tickers=breached_tickers
                    ))
        
        # Determine overall status
        if var_breached or cvar_breached or correlation_breached or limit_lock_detected:
            overall_status = 'critical'
        elif adv_breached:
            overall_status = 'warning'
        else:
            overall_status = 'normal'
        
        # Calculate next monitoring time
        next_monitoring_time = now + timedelta(minutes=self.config.monitoring_interval_minutes)
        
        # Create status
        self._current_status = RiskMonitorStatus(
            timestamp=now,
            overall_status=overall_status,
            var=var_value,
            cvar=cvar_value,
            max_correlation=max_correlation,
            max_adv_participation=max_adv_participation,
            var_breached=var_breached,
            cvar_breached=cvar_breached,
            correlation_breached=correlation_breached,
            adv_breached=adv_breached,
            limit_lock_detected=limit_lock_detected,
            portfolio_exposure=portfolio_exposure,
            num_positions=num_positions,
            num_limit_locked=num_limit_locked,
            derisk_action_pending=derisk_action_pending,
            derisk_target_multiplier=derisk_target_multiplier,
            last_monitoring_time=now,
            next_monitoring_time=next_monitoring_time
        )
        
        self.logger.info(
            f"Risk monitoring complete: status={overall_status}, "
            f"VaR={var_value:.2%}, CVaR={cvar_value:.2%}, "
            f"next_check={next_monitoring_time.strftime('%H:%M:%S')}"
        )
        
        return self._current_status
    
    def _emit_event(self, event: RiskEvent):
        """
        Emit risk event to log and history.
        
        Args:
            event: RiskEvent to emit
        """
        # Check alert cooldown
        if event.event_type in self._last_alert_time:
            last_alert = self._last_alert_time[event.event_type]
            elapsed = (event.timestamp - last_alert).total_seconds() / 60
            
            if elapsed < self.config.alert_cooldown_minutes:
                self.logger.debug(f"Alert cooldown active for {event.event_type}, skipping")
                return
        
        # Update last alert time
        self._last_alert_time[event.event_type] = event.timestamp
        
        # Add to history
        self._event_history.append(event)
        
        # Trim history
        if len(self._event_history) > self.config.max_history_length:
            self._event_history = self._event_history[-self.config.max_history_length:]
        
        # Write to JSONL log
        if self.config.export_enabled:
            try:
                with open(self.config.event_log_path, 'a') as f:
                    f.write(json.dumps(event.to_dict()) + '\n')
            except Exception as e:
                self.logger.error(f"Failed to write event to log: {e}")
        
        # Log event
        if event.severity == 'critical':
            self.logger.error(f"RISK EVENT: {event.message}")
        elif event.severity == 'warning':
            self.logger.warning(f"RISK EVENT: {event.message}")
        else:
            self.logger.info(f"RISK EVENT: {event.message}")
    
    def export_dashboard(self) -> str:
        """
        Export current status to dashboard JSON.
        
        Returns:
            Path to exported JSON file
        """
        if not self.config.export_enabled:
            self.logger.warning("Export is disabled in config")
            return ""
        
        if self._current_status is None:
            self.logger.warning("No status to export")
            return ""
        
        # Prepare export data (convert NumPy types to Python native types)
        export_data = {
            'timestamp': self._current_status.timestamp.isoformat(),
            'overall_status': self._current_status.overall_status,
            'metrics': {
                'var': float(self._current_status.var),
                'cvar': float(self._current_status.cvar),
                'max_correlation': float(self._current_status.max_correlation),
                'max_adv_participation': float(self._current_status.max_adv_participation)
            },
            'breaches': {
                'var_breached': bool(self._current_status.var_breached),
                'cvar_breached': bool(self._current_status.cvar_breached),
                'correlation_breached': bool(self._current_status.correlation_breached),
                'adv_breached': bool(self._current_status.adv_breached),
                'limit_lock_detected': bool(self._current_status.limit_lock_detected)
            },
            'portfolio': {
                'exposure': float(self._current_status.portfolio_exposure),
                'num_positions': int(self._current_status.num_positions),
                'num_limit_locked': int(self._current_status.num_limit_locked)
            },
            'actions': {
                'derisk_action_pending': bool(self._current_status.derisk_action_pending),
                'derisk_target_multiplier': float(self._current_status.derisk_target_multiplier)
            },
            'monitoring': {
                'last_monitoring_time': self._current_status.last_monitoring_time.isoformat(),
                'next_monitoring_time': self._current_status.next_monitoring_time.isoformat(),
                'interval_minutes': int(self.config.monitoring_interval_minutes)
            },
            'recent_events': [
                event.to_dict() for event in self._event_history[-20:]
            ]
        }
        
        # Write to file
        export_path = Path(self.config.dashboard_export_path)
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        self.logger.info(f"Dashboard exported to {export_path}")
        
        return str(export_path)
    
    def get_current_status(self) -> Optional[RiskMonitorStatus]:
        """Get current monitoring status"""
        return self._current_status
    
    def get_event_history(self, limit: int = 100) -> List[RiskEvent]:
        """Get recent event history"""
        return self._event_history[-limit:]
    
    def get_events_by_type(self, event_type: str) -> List[RiskEvent]:
        """Get events filtered by type"""
        return [e for e in self._event_history if e.event_type == event_type]
    
    def reset(self):
        """Reset monitor state"""
        self._current_status = None
        self._event_history.clear()
        self._last_monitoring_time = None
        self._last_alert_time.clear()
        self.logger.info("Risk Monitor L07 reset")


if __name__ == '__main__':
    print("=" * 80)
    print("RISK MONITOR L07 - DEMO")
    print("=" * 80)
    
    # Initialize
    config = RiskMonitorConfig(
        monitoring_interval_minutes=30,
        event_log_path='state/risk_events.jsonl',
        dashboard_export_path='.ly_state/session/risk_monitor_status.json'
    )
    monitor = RiskMonitorL07(config)
    
    # Generate sample data
    np.random.seed(42)
    returns = np.random.randn(252) * 0.03  # Moderate volatility
    
    # Create sample market data
    market_data = pd.DataFrame({
        'ticker': ['VNM', 'HPG', 'VCB'],
        'current_price': [69750, 28500, 95000],
        'reference_price': [75000, 30000, 100000],
        'bid_volume': [0, 1000, 5000],
        'ask_volume': [50000, 20000, 30000]
    })
    
    # Create sample positions
    positions = pd.DataFrame({
        'ticker': ['VNM', 'HPG', 'VCB'],
        'weight': [0.30, 0.40, 0.30],
        'adv_participation': [0.35, 0.45, 0.25]
    })
    
    # Test 1: Monitor risk
    print("\n1. Monitoring Risk...")
    status = monitor.monitor_risk(returns, market_data, positions)
    print(f"   Overall Status: {status.overall_status}")
    print(f"   VaR: {status.var:.2%} (Breached: {status.var_breached})")
    print(f"   CVaR: {status.cvar:.2%} (Breached: {status.cvar_breached})")
    print(f"   Limit-Lock Detected: {status.limit_lock_detected}")
    print(f"   De-risk Pending: {status.derisk_action_pending}")
    
    # Test 2: Export dashboard
    print("\n2. Exporting Dashboard...")
    export_path = monitor.export_dashboard()
    print(f"   Exported to: {export_path}")
    
    # Verify export
    if Path(export_path).exists():
        with open(export_path, 'r') as f:
            data = json.load(f)
        print(f"   Status: {data['overall_status']}")
        print(f"   VaR: {data['metrics']['var']:.2%}")
        print(f"   CVaR: {data['metrics']['cvar']:.2%}")
        print(f"   Recent Events: {len(data['recent_events'])}")
    
    # Test 3: Event history
    print("\n3. Event History:")
    events = monitor.get_event_history(limit=10)
    for event in events:
        print(f"   [{event.severity.upper()}] {event.event_type}: {event.message}")
    
    print("\n" + "=" * 80)
    print("Risk Monitor L07 demo complete")
    print("=" * 80)
