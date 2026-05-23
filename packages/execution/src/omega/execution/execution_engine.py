"""
OMEGA_QUANT Execution Engine Orchestrator (Layer 03)
Phase 4.3: Unified Execution Orchestration

Unified orchestrator directing the full signal-to-order-to-broker execution workflow
with robust state machine, error retries, and paper fallback.

Author: Backend Engineer (Role 09)
Date: 2026-05-18
Version: 1.0.0
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, TypedDict

from .broker_gateway import (
    BrokerOrder,
    BrokerOrderResponse,
    BrokerOrderStatus,
    OrderStatus,
    OrderSide,
    OrderType,
)
from .order_router import OrderRouter, OrderRouterConfig, TradingMode
from .order_generator import OrderGenerator, PositionSizingConfig
from .order_book_analyzer import OrderBookAnalyzer

logger = logging.getLogger(__name__)


class MarketDataEnvelope(TypedDict):
    """Market data payload with minimal provenance contract."""
    data: Dict[str, Any]
    timestamp: float
    provenance: str


@dataclass
class ExecutionEngineConfig:
    """Configuration for the unified ExecutionEngine."""
    mode: TradingMode = TradingMode.PAPER
    router_config: Optional[OrderRouterConfig] = None
    sizing_config: Optional[PositionSizingConfig] = None
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    enable_metrics_tracking: bool = True


class ExecutionEngine:
    """
    Unified orchestrator for Layer 03 (Execution Engine).
    
    Manages the complete lifecycle:
    1. Translates target portfolio weights into raw signal changes.
    2. Uses OrderGenerator to produce board-lot compliant orders.
    3. Runs OrderBookAnalyzer to gauge current market pressure and estimated slippage.
    4. Routes orders via OrderRouter (Paper/Live) with retry and paper-trading fallback.
    5. Tracks execution performance and metrics.
    """
    
    def __init__(self, config: Optional[ExecutionEngineConfig] = None):
        """Initialize unified ExecutionEngine."""
        self.config = config or ExecutionEngineConfig()
        
        # Initialize internal components
        router_cfg = self.config.router_config or OrderRouterConfig(mode=self.config.mode)
        self.router = OrderRouter(router_cfg)
        
        sizing_cfg = self.config.sizing_config or PositionSizingConfig()
        self.order_generator = OrderGenerator(sizing_cfg)
        
        self.order_book_analyzer = OrderBookAnalyzer()
        
        # State tracking
        self.active_orders: Dict[str, BrokerOrder] = {}
        self.order_states: Dict[str, OrderStatus] = {}
        self.execution_metrics: Dict[str, Any] = {
            "total_submitted": 0,
            "total_filled": 0,
            "total_cancelled": 0,
            "total_rejected": 0,
            "total_retries": 0,
            "total_fallbacks": 0,
            "average_latency_ms": 0.0,
            "slippage_bps_list": []
        }
        
        logger.info(f"ExecutionEngine initialized in {self.config.mode.value} mode")
    
    def execute_workflow(
        self,
        target_portfolio: Dict[str, Dict[str, Union[float, str]]],
        current_portfolio: Dict[str, Dict[str, Union[float, str]]],
        current_prices: Union[Dict[str, float], MarketDataEnvelope],
        adv_data: Optional[Dict[str, float]] = None,
        order_books: Optional[Union[Dict[str, Dict[str, Any]], MarketDataEnvelope]] = None,
        allow_odd_lot: bool = False
    ) -> Dict[str, Any]:
        """
        Execute full signal-to-broker workflow.
        
        Args:
            target_portfolio: Target portfolio composition
            current_portfolio: Current portfolio composition
            current_prices: Current stock prices
            adv_data: Average daily volume
            order_books: Current L2 order books for slippage adjustment
            allow_odd_lot: Allow odd-lot orders
            
        Returns:
            Execution summary dict
        """
        logger.info("Executing unified Layer 03 execution workflow...")
        prices = self._extract_market_data(current_prices, field_name="current_prices", require_metadata=True)
        advs = adv_data or {}
        books = self._extract_market_data(order_books, field_name="order_books", require_metadata=False)
        
        # 1. Generate parent orders
        raw_orders = self.order_generator.generate_orders(
            target_portfolio=target_portfolio,
            current_portfolio=current_portfolio,
            current_prices=prices,
            allow_odd_lot=allow_odd_lot
        )
        
        results = []
        for raw_order in raw_orders:
            symbol = raw_order["symbol"]
            qty = raw_order["quantity"]
            side = OrderSide(raw_order["side"])
            order_type = OrderType(raw_order["order_type"])
            price = raw_order.get("price")
            
            # Create BrokerOrder object
            try:
                order = BrokerOrder(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    order_type=order_type,
                    price=price,
                    allow_odd_lot=bool(raw_order.get("allow_odd_lot", False)),
                )
            except Exception as e:
                logger.error(f"Invalid order specification for {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "message": f"Invalid order spec: {e}",
                    "status": OrderStatus.REJECTED
                })
                self.execution_metrics["total_rejected"] += 1
                continue
            
            # 2. Analyze market microstructure & OBI
            slippage_est = 1.5  # Default
            if symbol in books:
                book = books[symbol]
                bid_levels = book.get("bids", [])
                ask_levels = book.get("asks", [])
                
                # Compute OBI & VWMP
                obi = self.order_book_analyzer.compute_obi(bid_levels, ask_levels)
                vwmp = self.order_book_analyzer.compute_vwmp(bid_levels, ask_levels)
                pressure = self.order_book_analyzer.get_pressure(bid_levels, ask_levels)
                
                logger.info(f"Microstructure for {symbol}: OBI={obi:.2f}, VWMP={vwmp:.2f}, Pressure={pressure}")
                
                # Assess liquidity and adjust slippage estimation
                target_qty = qty if side == OrderSide.BUY else -abs(qty)
                liq = self.order_book_analyzer.assess_liquidity(bid_levels, ask_levels, target_qty)
                slippage_est = liq.get("estimated_slippage_bps", 1.5)
            else:
                # Basic slippage estimate
                adv = advs.get(symbol, 0.0)
                slippage_est = self.order_book_analyzer.estimate_slippage(
                    order_size=qty,
                    avg_daily_volume=int(adv),
                    market_depth={"spread_bps": 1.0}
                )
            
            self.execution_metrics["slippage_bps_list"].append(slippage_est)
            
            # 3. Route order via OrderRouter with retries and paper fallback
            submission_response = self._submit_order_with_retry_and_fallback(
                order=order,
                current_price=prices.get(symbol)
            )
            
            # Track order state
            if submission_response.success:
                self.active_orders[submission_response.broker_order_id] = order
                self.order_states[submission_response.broker_order_id] = submission_response.status
                self.execution_metrics["total_submitted"] += 1
                if submission_response.status == OrderStatus.FILLED:
                    self.execution_metrics["total_filled"] += 1
            else:
                self.execution_metrics["total_rejected"] += 1
            
            results.append({
                "symbol": symbol,
                "client_order_id": order.client_order_id,
                "broker_order_id": submission_response.broker_order_id,
                "success": submission_response.success,
                "status": submission_response.status,
                "estimated_slippage_bps": slippage_est,
                "message": submission_response.message,
                "error_code": submission_response.error_code
            })
            
        return {
            "success": all(result["success"] for result in results),
            "mode": self.config.mode.value,
            "orders": results,
            "metrics": self.get_execution_metrics()
        }

    def _extract_market_data(
        self,
        payload: Optional[Union[Dict[str, Any], MarketDataEnvelope]],
        field_name: str,
        require_metadata: bool,
    ) -> Dict[str, Any]:
        """Normalize market data payload and enforce provenance contract when required."""
        if payload is None:
            return {}

        now = time.time()

        if require_metadata:
            if not isinstance(payload, dict) or "data" not in payload:
                raise ValueError(f"{field_name} must include data, timestamp, and provenance")
            if payload.get("timestamp") is None or not payload.get("provenance"):
                raise ValueError(f"{field_name} must include data, timestamp, and provenance")
            
            ts = payload.get("timestamp")
            if ts is not None:
                try:
                    ts_float = float(ts)
                    if ts_float > now + 10.0:  # PIT safety look-ahead guard
                        raise ValueError(f"PIT Safety violation: {field_name} timestamp {ts_float} is in the future relative to current time {now}")
                except (ValueError, TypeError) as e:
                    if "PIT Safety violation" in str(e):
                        raise
                    raise ValueError(f"Invalid timestamp format in {field_name}")

            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"{field_name}.data must be a dict")
            return data

        if isinstance(payload, dict) and "data" in payload:
            if payload.get("timestamp") is None or not payload.get("provenance"):
                raise ValueError(f"{field_name} must include data, timestamp, and provenance")
            
            ts = payload.get("timestamp")
            if ts is not None:
                try:
                    ts_float = float(ts)
                    if ts_float > now + 10.0:  # PIT safety look-ahead guard
                        raise ValueError(f"PIT Safety violation: {field_name} timestamp {ts_float} is in the future relative to current time {now}")
                except (ValueError, TypeError) as e:
                    if "PIT Safety violation" in str(e):
                        raise
                    raise ValueError(f"Invalid timestamp format in {field_name}")

            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"{field_name}.data must be a dict")
            return data

        return payload
    
    def _submit_order_with_retry_and_fallback(
        self,
        order: BrokerOrder,
        current_price: Optional[float]
    ) -> BrokerOrderResponse:
        """
        Submit order to router with retry logic and fallback to paper trading on failure.
        """
        start_time = time.time()
        attempt = 0
        last_error = None
        
        while attempt < self.config.max_retries:
            attempt += 1
            try:
                # Submission via Router
                response = self.router.submit_order(order, current_price)
                
                # Check latency
                latency = (time.time() - start_time) * 1000.0
                self._update_latency(latency)
                
                if response.success:
                    return response
                
                last_error = response.message
                logger.warning(f"Submission failed (attempt {attempt}/{self.config.max_retries}): {last_error}")
                self.execution_metrics["total_retries"] += 1
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Error submitting order (attempt {attempt}/{self.config.max_retries}): {e}")
                self.execution_metrics["total_retries"] += 1
            
            # Backoff before retry
            if attempt < self.config.max_retries:
                time.sleep(self.config.retry_delay_seconds * (2 ** (attempt - 1)))
        
        # If live submission exhausted and fallback allowed
        if self.config.mode == TradingMode.LIVE and self.router.config.fallback_to_paper:
            logger.error(f"Live submission failed after {self.config.max_retries} attempts: {last_error}. Falling back to PAPER trading.")
            self.execution_metrics["total_fallbacks"] += 1
            
            # Re-submit to paper engine
            fallback_response = self.router.paper_engine.submit_order(order, current_price)
            fallback_response.message = f"FALLBACK ACTIVE: {fallback_response.message} (Live failure: {last_error})"
            return fallback_response
        
        return BrokerOrderResponse(
            success=False,
            client_order_id=order.client_order_id,
            status=OrderStatus.REJECTED,
            message=f"Submission failed after {self.config.max_retries} attempts: {last_error}",
            error_code="MAX_RETRIES_EXHAUSTED"
        )
    
    def _update_latency(self, latency_ms: float) -> None:
        """Update average latency metric."""
        n = self.execution_metrics["total_submitted"] + 1
        avg = self.execution_metrics["average_latency_ms"]
        self.execution_metrics["average_latency_ms"] = ((avg * (n - 1)) + latency_ms) / n
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get order status and update state machine."""
        status_info = self.router.get_order_status(broker_order_id)
        self.order_states[broker_order_id] = status_info.status
        
        # Update metrics
        if status_info.status == OrderStatus.FILLED:
            self.execution_metrics["total_filled"] += 1
        elif status_info.status == OrderStatus.CANCELLED:
            self.execution_metrics["total_cancelled"] += 1
        elif status_info.status == OrderStatus.REJECTED:
            self.execution_metrics["total_rejected"] += 1
            
        return status_info
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order."""
        response = self.router.cancel_order(broker_order_id)
        if response.success:
            self.order_states[broker_order_id] = OrderStatus.CANCELLED
            self.execution_metrics["total_cancelled"] += 1
        return response
    
    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get copy of execution metrics."""
        metrics = self.execution_metrics.copy()
        # Compute avg slippage
        sl_list = metrics["slippage_bps_list"]
        metrics["average_slippage_bps"] = sum(sl_list) / len(sl_list) if sl_list else 0.0
        del metrics["slippage_bps_list"]
        return metrics
