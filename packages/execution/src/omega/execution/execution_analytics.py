"""
OMEGA_QUANT Execution Analytics (Layer 03)
Phase 4.3: Execution Performance Analysis

Computes execution quality metrics: slippage, fill rate, latency,
market impact, and P&L attribution (alpha vs execution cost).

Author: Backend Engineer (Role 09)
Date: 2026-05-18
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import statistics
import time

logger = logging.getLogger(__name__)


def validate_benchmark_price(price_input: Any, name: str = "benchmark") -> float:
    """Validate benchmark price for PIT safety and provenance."""
    if price_input is None:
        raise ValueError(f"{name} price cannot be None")
        
    if isinstance(price_input, dict):
        if "price" not in price_input or "timestamp" not in price_input or "provenance" not in price_input:
            raise ValueError(f"{name} envelope must include price, timestamp, and provenance")
        ts = price_input.get("timestamp")
        if ts is not None:
            try:
                ts_float = float(ts)
                if ts_float > time.time() + 10.0:  # PIT safety look-ahead guard
                    raise ValueError(f"PIT Safety violation: {name} timestamp {ts_float} is in the future")
            except (ValueError, TypeError) as e:
                if "PIT Safety violation" in str(e):
                    raise
                raise ValueError(f"Invalid timestamp format in {name} envelope")
        price_val = price_input.get("price")
        if price_val is None or float(price_val) <= 0:
            raise ValueError(f"Invalid price value in {name} envelope")
        return float(price_val)
        
    price_float = float(price_input)
    if price_float <= 0:
        raise ValueError(f"Invalid {name} price: {price_float}")
    return price_float



@dataclass
class ExecutionMetrics:
    """Aggregated execution performance metrics."""
    symbol: str
    side: str
    quantity: int
    target_price: float
    execution_price: float
    slippage_bps: float
    fill_rate: float  # 0.0 to 1.0
    latency_ms: float
    market_impact_bps: float
    execution_cost_bps: float  # slippage + market impact + commission
    commission_bps: float


class ExecutionAnalytics:
    """
    Execution analytics engine for performance measurement.
    
    Features:
    - Slippage calculation (vs VWAP, TWAP, arrival price)
    - Fill rate tracking
    - Latency measurement
    - Market impact estimation
    - Execution cost decomposition
    - P&L attribution (alpha vs execution)
    """
    
    def __init__(self):
        """Initialize ExecutionAnalytics."""
        self.metrics_history: List[ExecutionMetrics] = []
        logger.info("Initialized ExecutionAnalytics")
    
    def calculate_slippage(
        self,
        symbol: str,
        side: str,
        execution_price: float,
        reference_price: float | Dict[str, Any],
        reference_type: str = "ARRIVAL"
    ) -> float:
        """
        Calculate execution slippage in basis points.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            execution_price: Actual execution price
            reference_price: Reference price (ARRIVAL, VWAP, TWAP, etc.) or Envelope
            reference_type: Type of reference price
            
        Returns:
            Slippage in basis points
        """
        ref_price_validated = validate_benchmark_price(reference_price, name="reference_price")
        
        if side == "BUY":
            # For BUY: positive slippage = paid more than reference
            slippage = (execution_price - ref_price_validated) / ref_price_validated * 10000
        else:  # SELL
            # For SELL: positive slippage = received less than reference
            slippage = (ref_price_validated - execution_price) / ref_price_validated * 10000
        
        logger.debug(f"Slippage for {symbol} {side}: {slippage:.2f} bps "
                    f"(exec={execution_price}, ref={ref_price_validated})")
        
        return slippage
    
    def calculate_fill_rate(
        self,
        target_quantity: int,
        filled_quantity: int
    ) -> float:
        """
        Calculate fill rate percentage.
        
        Args:
            target_quantity: Target order quantity
            filled_quantity: Actual filled quantity
            
        Returns:
            Fill rate from 0.0 to 1.0
        """
        if target_quantity <= 0:
            return 0.0
        return min(filled_quantity / target_quantity, 1.0)
    
    def calculate_market_impact(
        self,
        order_size: int,
        avg_daily_volume: int,
        volatility: float,
        participation_rate: float = 0.0
    ) -> float:
        """
        Estimate market impact in basis points.
        
        Uses Almgren-Chriss model approximation:
        Impact = lambda * (order_size / ADV)^alpha * volatility
        
        Args:
            order_size: Order size in shares
            avg_daily_volume: Average daily volume in shares
            volatility: Stock volatility (annualized)
            participation_rate: Participation rate (0.0 to 1.0)
            
        Returns:
            Market impact in basis points
        """
        if avg_daily_volume <= 0 or volatility <= 0:
            return 0.0
        
        # Participation rate
        if participation_rate == 0.0:
            participation_rate = order_size / avg_daily_volume if avg_daily_volume > 0 else 0.0
        
        # Almgren-Chriss approximation
        # lambda = 0.5 (typical value)
        # alpha = 1.5 (typical value)
        lambda_param = 0.5
        alpha = 1.5
        
        if participation_rate < 0.001:
            return 0.1  # Minimum impact
        
        impact = lambda_param * (participation_rate ** alpha) * volatility * 10000
        
        logger.debug(f"Market impact: {impact:.2f} bps "
                    f"(participation={participation_rate:.2%}, vol={volatility:.2%})")
        
        return impact
    
    def calculate_execution_cost(
        self,
        slippage_bps: float,
        market_impact_bps: float,
        commission_bps: float
    ) -> float:
        """
        Calculate total execution cost in basis points.
        
        Args:
            slippage_bps: Slippage in bps
            market_impact_bps: Market impact in bps
            commission_bps: Commission in bps
            
        Returns:
            Total execution cost in bps
        """
        total = slippage_bps + market_impact_bps + commission_bps
        return total
    
    def record_execution(
        self,
        symbol: str,
        side: str,
        quantity: int,
        target_price: float | Dict[str, Any],
        execution_price: float,
        filled_quantity: int,
        latency_ms: float,
        avg_daily_volume: int,
        volatility: float,
        commission_rate: float = 0.0015
    ) -> ExecutionMetrics:
        """
        Record and analyze a single execution.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Target quantity
            target_price: Target/arrival price or Envelope
            execution_price: Actual execution price
            filled_quantity: Actual filled quantity
            latency_ms: Execution latency in milliseconds
            avg_daily_volume: Average daily volume
            volatility: Stock volatility
            commission_rate: Commission rate
            
        Returns:
            ExecutionMetrics record
        """
        # Validate target price
        target_price_validated = validate_benchmark_price(target_price, name="target_price")
        
        # Calculate metrics
        slippage = self.calculate_slippage(symbol, side, execution_price, target_price)
        fill_rate = self.calculate_fill_rate(quantity, filled_quantity)
        
        participation = filled_quantity / avg_daily_volume if avg_daily_volume > 0 else 0.0
        market_impact = self.calculate_market_impact(
            filled_quantity, avg_daily_volume, volatility, participation
        )
        
        commission_bps = commission_rate * 10000
        execution_cost = self.calculate_execution_cost(slippage, market_impact, commission_bps)
        
        metrics = ExecutionMetrics(
            symbol=symbol,
            side=side,
            quantity=quantity,
            target_price=target_price_validated,
            execution_price=execution_price,
            slippage_bps=slippage,
            fill_rate=fill_rate,
            latency_ms=latency_ms,
            market_impact_bps=market_impact,
            execution_cost_bps=execution_cost,
            commission_bps=commission_bps
        )
        
        self.metrics_history.append(metrics)
        
        logger.info(f"Execution recorded for {symbol}: "
                   f"Slippage={slippage:.2f}bps, Impact={market_impact:.2f}bps, "
                   f"Cost={execution_cost:.2f}bps, FillRate={fill_rate:.1%}")
        
        return metrics
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """Compute aggregate execution statistics."""
        if not self.metrics_history:
            return {
                "total_executions": 0,
                "average_slippage_bps": 0.0,
                "average_market_impact_bps": 0.0,
                "average_execution_cost_bps": 0.0,
                "average_fill_rate": 0.0,
                "average_latency_ms": 0.0
            }
        
        slippages = [m.slippage_bps for m in self.metrics_history]
        impacts = [m.market_impact_bps for m in self.metrics_history]
        costs = [m.execution_cost_bps for m in self.metrics_history]
        fill_rates = [m.fill_rate for m in self.metrics_history]
        latencies = [m.latency_ms for m in self.metrics_history]
        
        return {
            "total_executions": len(self.metrics_history),
            "average_slippage_bps": statistics.mean(slippages),
            "median_slippage_bps": statistics.median(slippages),
            "stdev_slippage_bps": statistics.stdev(slippages) if len(slippages) > 1 else 0.0,
            "min_slippage_bps": min(slippages),
            "max_slippage_bps": max(slippages),
            "average_market_impact_bps": statistics.mean(impacts),
            "average_execution_cost_bps": statistics.mean(costs),
            "average_fill_rate": statistics.mean(fill_rates),
            "average_latency_ms": statistics.mean(latencies),
            "median_latency_ms": statistics.median(latencies)
        }
    
    def get_by_symbol_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get execution statistics grouped by symbol."""
        by_symbol: Dict[str, List[ExecutionMetrics]] = {}
        
        for m in self.metrics_history:
            if m.symbol not in by_symbol:
                by_symbol[m.symbol] = []
            by_symbol[m.symbol].append(m)
        
        stats = {}
        for symbol, metrics_list in by_symbol.items():
            slippages = [m.slippage_bps for m in metrics_list]
            impacts = [m.market_impact_bps for m in metrics_list]
            costs = [m.execution_cost_bps for m in metrics_list]
            
            stats[symbol] = {
                "executions": len(metrics_list),
                "average_slippage_bps": statistics.mean(slippages),
                "average_market_impact_bps": statistics.mean(impacts),
                "average_execution_cost_bps": statistics.mean(costs),
                "total_quantity": sum(m.quantity for m in metrics_list),
                "average_fill_rate": statistics.mean([m.fill_rate for m in metrics_list])
            }
        
        return stats
    
    def get_by_side_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get execution statistics grouped by side (BUY/SELL)."""
        by_side: Dict[str, List[ExecutionMetrics]] = {"BUY": [], "SELL": []}
        
        for m in self.metrics_history:
            by_side[m.side].append(m)
        
        stats = {}
        for side, metrics_list in by_side.items():
            if not metrics_list:
                continue
                
            slippages = [m.slippage_bps for m in metrics_list]
            impacts = [m.market_impact_bps for m in metrics_list]
            costs = [m.execution_cost_bps for m in metrics_list]
            
            stats[side] = {
                "executions": len(metrics_list),
                "average_slippage_bps": statistics.mean(slippages),
                "average_market_impact_bps": statistics.mean(impacts),
                "average_execution_cost_bps": statistics.mean(costs),
                "total_quantity": sum(m.quantity for m in metrics_list),
                "average_fill_rate": statistics.mean([m.fill_rate for m in metrics_list])
            }
        
        return stats
    
    def calculate_pnl_attribution(
        self,
        alpha_pnl: float,
        execution_cost_bps: float,
        notional_value: float
    ) -> Dict[str, float]:
        """
        Attribute P&L to alpha vs execution cost.
        
        Args:
            alpha_pnl: P&L from alpha signal (VND)
            execution_cost_bps: Execution cost in basis points
            notional_value: Trade notional value (VND)
            
        Returns:
            Attribution dict {alpha_pnl, execution_cost_vnd, net_pnl}
        """
        execution_cost_vnd = notional_value * (execution_cost_bps / 10000)
        net_pnl = alpha_pnl - execution_cost_vnd
        
        return {
            "alpha_pnl_vnd": alpha_pnl,
            "execution_cost_vnd": execution_cost_vnd,
            "execution_cost_bps": execution_cost_bps,
            "net_pnl_vnd": net_pnl,
            "execution_cost_ratio": execution_cost_vnd / alpha_pnl if alpha_pnl != 0 else 0.0
        }
