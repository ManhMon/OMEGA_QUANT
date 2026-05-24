"""
OMEGA_QUANT Execution Engine Orchestrator (Layer 03)
Phase 4.3 / Phase 16: Unified Execution Orchestration + V21 Liquidation Defense

Unified orchestrator directing the full signal-to-order-to-broker execution workflow
with robust state machine, error retries, paper fallback, latency simulation,
and V21 liquidation/defense exposure management.

Author: Backend Engineer (Role 09)
Date: 2026-05-24
Version: 1.1.0
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
from .notifications.telegram_bot import TelegramAlertBot

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
    # V21 defense: halt new BUY orders when gross liquidation exposure exceeds this (VND notional)
    # 0.0 means no cap enforced.
    defense_gross_exposure_cap: float = 0.0
    # Liquidation mode: when True ALL SELL orders execute before ANY BUY order,
    # regardless of whether target_qty == 0.  Superset of the per-order sort.
    liquidation_mode: bool = False
    
    # Oracle Mode: If true, suppresses single trade Telegram alerts (relies on batch reporting)
    signal_oracle_mode: bool = False


class ExecutionEngine:
    """
    Unified orchestrator for Layer 03 (Execution Engine).

    Manages the complete lifecycle:
    1. Translates target portfolio weights into raw signal changes.
    2. Uses OrderGenerator to produce board-lot compliant orders.
    3. Sorts orders so liquidations execute first (V21 defense priority).
    4. Enforces defense_gross_exposure_cap: halts new BUY orders when total
       gross liquidation notional exceeds the configured cap.
    5. Runs OrderBookAnalyzer to gauge current market pressure and estimated slippage.
    6. Routes orders via OrderRouter (Paper/Live) with retry and paper-trading fallback.
    7. Updates per-symbol LiquidationExposure on the router after each submission.
    8. Tracks execution performance and metrics.
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
        self.telegram = TelegramAlertBot()

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
            "slippage_bps_list": [],
            # V21 defense metrics
            "total_defense_halted": 0,
            "total_liquidation_orders": 0,
        }

        # V21 defense: True when gross exposure cap is breached
        self._defense_mode_active: bool = False

        # Halt flag: when True, execute_workflow rejects all new orders
        self._halted: bool = False

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

        # Halt guard: reject entire workflow immediately when halted
        if self._halted:
            logger.warning("execute_workflow called while HALTED — all orders rejected")
            return {
                "success": False,
                "mode": self.config.mode.value,
                "orders": [],
                "metrics": self.get_execution_metrics(),
                "error_code": "HALTED",
            }

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

        # 2. V21 defense: sort SELL orders first so they execute with priority.
        #    liquidation_mode=True  → ALL SELLs before ALL BUYs.
        #    liquidation_mode=False → only full-liquidation SELLs (target_qty==0) first.
        def _is_liquidation(raw: dict) -> bool:
            sym = raw["symbol"]
            tgt = target_portfolio.get(sym, {})
            tgt_qty = int(tgt.get("quantity", 0))
            return tgt_qty == 0 and raw["side"] == OrderSide.SELL.value

        def _sell_first_key(raw: dict) -> int:
            if self.config.liquidation_mode:
                # All SELLs get priority 0, all BUYs get priority 1
                return 0 if raw["side"] == OrderSide.SELL.value else 1
            # Default: only full-liquidation SELLs get priority
            return 0 if _is_liquidation(raw) else 1

        raw_orders = sorted(raw_orders, key=_sell_first_key)

        results = []
        for raw_order in raw_orders:
            symbol = raw_order["symbol"]
            qty = raw_order["quantity"]
            side = OrderSide(raw_order["side"])
            order_type = OrderType(raw_order["order_type"])
            price = raw_order.get("price")
            is_liq = _is_liquidation(raw_order)

            if is_liq:
                self.execution_metrics["total_liquidation_orders"] += 1

            # 3. V21 defense cap: halt new BUY orders when gross liquidation
            #    exposure exceeds the configured cap (0.0 = no cap).
            cap = self.config.defense_gross_exposure_cap
            if cap > 0.0 and side == OrderSide.BUY and not is_liq:
                gross = self.router.get_total_gross_liquidation_exposure()
                if gross >= cap:
                    self._defense_mode_active = True
                    logger.warning(
                        f"DEFENSE MODE: halting BUY {symbol} — gross liquidation "
                        f"exposure {gross:,.0f} >= cap {cap:,.0f}"
                    )
                    self.execution_metrics["total_defense_halted"] += 1
                    results.append({
                        "symbol": symbol,
                        "success": False,
                        "message": f"DEFENSE MODE: BUY halted, gross exposure {gross:,.0f} >= cap {cap:,.0f}",
                        "status": OrderStatus.REJECTED,
                        "client_order_id": None,
                        "broker_order_id": None,
                        "estimated_slippage_bps": 0.0,
                        "error_code": "DEFENSE_CAP_BREACH",
                    })
                    self.execution_metrics["total_rejected"] += 1
                    continue
                else:
                    self._defense_mode_active = False

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
                    "status": OrderStatus.REJECTED,
                    "client_order_id": None,
                    "broker_order_id": None,
                    "estimated_slippage_bps": 0.0,
                    "error_code": "INVALID_ORDER_SPEC",
                })
                self.execution_metrics["total_rejected"] += 1
                continue

            # 4. Analyze market microstructure & OBI
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

            # 5. Update liquidation exposure on router BEFORE submission
            if is_liq:
                current_price_val = prices.get(symbol, 0.0) or 0.0
                cur_qty = int(current_portfolio.get(symbol, {}).get("quantity", 0))
                remaining_after = max(0, cur_qty - qty)
                self.router.update_liquidation_exposure(
                    symbol=symbol,
                    is_liquidating=True,
                    remaining_qty=remaining_after,
                    current_price=current_price_val,
                    submitted_qty=qty,
                )

            # 6. Route order via OrderRouter with retries and paper fallback
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
                    
                # Send Telegram Alert
                if not self.config.signal_oracle_mode:
                    self.telegram.send_trade_alert(
                        symbol=symbol,
                        side=side.name,
                        qty=qty,
                        price=price or prices.get(symbol) or 0.0,
                        mode=self.config.mode.name
                    )
                if is_liq and not self.config.signal_oracle_mode:
                    self.telegram.send_liquidation_alert(symbol=symbol, qty=qty)

                # Clear liquidation exposure when fully submitted
                if is_liq:
                    exp = self.router.get_liquidation_exposure(symbol)
                    if exp is not None and exp.remaining_qty == 0:
                        exp.is_liquidating = False
                        logger.info(f"Liquidation complete for {symbol}")
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
                "error_code": submission_response.error_code,
                "is_liquidation": is_liq,
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
    
    def halt(self) -> None:
        """
        Halt the execution engine.

        While halted, execute_workflow rejects every order immediately with
        error_code HALTED.  Active orders already submitted to the broker are
        NOT cancelled — call cancel_all_active_orders() explicitly if needed.
        """
        self._halted = True
        logger.warning("ExecutionEngine HALTED — all new order submissions blocked")

    def resume(self) -> None:
        """
        Resume the execution engine after a halt.

        Clears the halt flag so execute_workflow accepts orders again.
        """
        self._halted = False
        logger.info("ExecutionEngine RESUMED — order submissions re-enabled")

    def cancel_all_active_orders(self) -> Dict[str, Any]:
        """
        Cancel every order currently tracked in self.active_orders.

        Iterates the active_orders registry and calls cancel_order() for each
        broker_order_id.  Returns a summary dict with per-order results.

        Returns:
            {
                "total": int,
                "cancelled": int,
                "failed": int,
                "results": [{"broker_order_id": str, "success": bool, "message": str}, ...]
            }
        """
        results = []
        cancelled = 0
        failed = 0

        for broker_order_id in list(self.active_orders.keys()):
            response = self.cancel_order(broker_order_id)
            results.append({
                "broker_order_id": broker_order_id,
                "success": response.success,
                "message": response.message,
            })
            if response.success:
                cancelled += 1
            else:
                failed += 1

        logger.info(
            f"cancel_all_active_orders: {cancelled} cancelled, {failed} failed "
            f"out of {len(results)} total"
        )
        return {
            "total": len(results),
            "cancelled": cancelled,
            "failed": failed,
            "results": results,
        }

    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get copy of execution metrics."""
        metrics = self.execution_metrics.copy()
        # Compute avg slippage
        sl_list = metrics["slippage_bps_list"]
        metrics["average_slippage_bps"] = sum(sl_list) / len(sl_list) if sl_list else 0.0
        del metrics["slippage_bps_list"]
        # V21 defense state
        metrics["defense_mode_active"] = self._defense_mode_active
        metrics["gross_liquidation_exposure"] = self.router.get_total_gross_liquidation_exposure()
        metrics["router_average_latency_ms"] = self.router.get_average_latency_ms()
        return metrics
