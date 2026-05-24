"""
Real-time Execution Metrics Tracker
OMEGA_QUANT Phase 17: Dashboard & Monitoring
Point-in-Time Safe: All metrics computed from event_time timestamps
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque
import numpy as np
from threading import Lock

from .models import ExecutionMetrics


class ExecutionTracker:
    """
    Real-time execution metrics tracker
    
    Tracks order flow, fills, slippage, and latency metrics
    with rolling window aggregation for dashboard display.
    """
    
    def __init__(self, window_minutes: int = 5):
        """
        Initialize execution tracker
        
        Args:
            window_minutes: Rolling window size in minutes
        """
        self.window_minutes = window_minutes
        self.window_duration = timedelta(minutes=window_minutes)
        
        # Per-strategy tracking
        self.strategy_data: Dict[str, Dict] = {}
        self.lock = Lock()
        
    def record_order_submitted(
        self,
        strategy_id: str,
        order_id: str,
        timestamp: datetime,
        symbol: str,
        quantity: float,
        price: float
    ):
        """Record order submission"""
        with self.lock:
            data = self._get_strategy_data(strategy_id)
            
            data['orders_submitted'].append({
                'order_id': order_id,
                'timestamp': timestamp,
                'symbol': symbol,
                'quantity': quantity,
                'price': price
            })
            
            self._cleanup_old_data(data, timestamp)
    
    def record_order_filled(
        self,
        strategy_id: str,
        order_id: str,
        timestamp: datetime,
        fill_price: float,
        fill_quantity: float,
        expected_price: float,
        latency_us: float
    ):
        """Record order fill"""
        with self.lock:
            data = self._get_strategy_data(strategy_id)
            
            # Calculate slippage in basis points
            slippage_bps = abs(fill_price - expected_price) / expected_price * 10000
            
            data['orders_filled'].append({
                'order_id': order_id,
                'timestamp': timestamp,
                'fill_price': fill_price,
                'fill_quantity': fill_quantity,
                'expected_price': expected_price,
                'slippage_bps': slippage_bps,
                'latency_us': latency_us,
                'notional': fill_price * fill_quantity
            })
            
            self._cleanup_old_data(data, timestamp)
    
    def record_order_cancelled(
        self,
        strategy_id: str,
        order_id: str,
        timestamp: datetime
    ):
        """Record order cancellation"""
        with self.lock:
            data = self._get_strategy_data(strategy_id)
            
            data['orders_cancelled'].append({
                'order_id': order_id,
                'timestamp': timestamp
            })
            
            self._cleanup_old_data(data, timestamp)
    
    def record_order_rejected(
        self,
        strategy_id: str,
        order_id: str,
        timestamp: datetime,
        reason: str
    ):
        """Record order rejection"""
        with self.lock:
            data = self._get_strategy_data(strategy_id)
            
            data['orders_rejected'].append({
                'order_id': order_id,
                'timestamp': timestamp,
                'reason': reason
            })
            
            self._cleanup_old_data(data, timestamp)
    
    def get_metrics(
        self,
        strategy_id: str,
        as_of_time: Optional[datetime] = None
    ) -> ExecutionMetrics:
        """
        Get current execution metrics for strategy
        
        Args:
            strategy_id: Strategy identifier
            as_of_time: Point-in-time for metrics (default: now)
            
        Returns:
            ExecutionMetrics snapshot
        """
        if as_of_time is None:
            as_of_time = datetime.utcnow()
        
        with self.lock:
            data = self._get_strategy_data(strategy_id)
            self._cleanup_old_data(data, as_of_time)
            
            # Count orders
            orders_submitted = len(data['orders_submitted'])
            orders_filled = len(data['orders_filled'])
            orders_cancelled = len(data['orders_cancelled'])
            orders_rejected = len(data['orders_rejected'])
            
            # Calculate fill rate
            fill_rate = orders_filled / orders_submitted if orders_submitted > 0 else 0.0
            
            # Calculate slippage metrics
            if orders_filled > 0:
                slippages = [fill['slippage_bps'] for fill in data['orders_filled']]
                avg_slippage_bps = np.mean(slippages)
                max_slippage_bps = np.max(slippages)
                slippage_std_bps = np.std(slippages)
            else:
                avg_slippage_bps = 0.0
                max_slippage_bps = 0.0
                slippage_std_bps = 0.0
            
            # Calculate volume metrics
            total_volume = sum(fill['fill_quantity'] for fill in data['orders_filled'])
            total_notional = sum(fill['notional'] for fill in data['orders_filled'])
            
            # Calculate fill time (time from submission to fill)
            fill_times = []
            for fill in data['orders_filled']:
                # Find corresponding submission
                for sub in data['orders_submitted']:
                    if sub['order_id'] == fill['order_id']:
                        fill_time_ms = (fill['timestamp'] - sub['timestamp']).total_seconds() * 1000
                        fill_times.append(fill_time_ms)
                        break
            
            avg_fill_time_ms = np.mean(fill_times) if fill_times else 0.0
            
            # Calculate latency metrics
            if orders_filled > 0:
                latencies = [fill['latency_us'] for fill in data['orders_filled']]
                avg_latency_us = np.mean(latencies)
                p50_latency_us = np.percentile(latencies, 50)
                p95_latency_us = np.percentile(latencies, 95)
                p99_latency_us = np.percentile(latencies, 99)
                max_latency_us = np.max(latencies)
            else:
                avg_latency_us = 0.0
                p50_latency_us = 0.0
                p95_latency_us = 0.0
                p99_latency_us = 0.0
                max_latency_us = 0.0
            
            return ExecutionMetrics(
                timestamp=as_of_time,
                strategy_id=strategy_id,
                orders_submitted=orders_submitted,
                orders_filled=orders_filled,
                orders_cancelled=orders_cancelled,
                orders_rejected=orders_rejected,
                avg_fill_time_ms=avg_fill_time_ms,
                fill_rate=fill_rate,
                avg_slippage_bps=avg_slippage_bps,
                max_slippage_bps=max_slippage_bps,
                slippage_std_bps=slippage_std_bps,
                total_volume=total_volume,
                total_notional=total_notional,
                avg_latency_us=avg_latency_us,
                p50_latency_us=p50_latency_us,
                p95_latency_us=p95_latency_us,
                p99_latency_us=p99_latency_us,
                max_latency_us=max_latency_us
            )
    
    def get_all_metrics(
        self,
        as_of_time: Optional[datetime] = None
    ) -> Dict[str, ExecutionMetrics]:
        """
        Get execution metrics for all strategies
        
        Args:
            as_of_time: Point-in-time for metrics (default: now)
            
        Returns:
            Dictionary mapping strategy_id to ExecutionMetrics
        """
        if as_of_time is None:
            as_of_time = datetime.utcnow()
        
        with self.lock:
            return {
                strategy_id: self.get_metrics(strategy_id, as_of_time)
                for strategy_id in self.strategy_data.keys()
            }
    
    def _get_strategy_data(self, strategy_id: str) -> Dict:
        """Get or create strategy data structure"""
        if strategy_id not in self.strategy_data:
            self.strategy_data[strategy_id] = {
                'orders_submitted': deque(),
                'orders_filled': deque(),
                'orders_cancelled': deque(),
                'orders_rejected': deque()
            }
        return self.strategy_data[strategy_id]
    
    def _cleanup_old_data(self, data: Dict, current_time: datetime):
        """Remove data outside rolling window"""
        cutoff_time = current_time - self.window_duration
        
        # Clean each deque
        for key in ['orders_submitted', 'orders_filled', 'orders_cancelled', 'orders_rejected']:
            queue = data[key]
            while queue and queue[0]['timestamp'] < cutoff_time:
                queue.popleft()
    
    def reset_strategy(self, strategy_id: str):
        """Reset metrics for a strategy"""
        with self.lock:
            if strategy_id in self.strategy_data:
                del self.strategy_data[strategy_id]
    
    def reset_all(self):
        """Reset all metrics"""
        with self.lock:
            self.strategy_data.clear()
