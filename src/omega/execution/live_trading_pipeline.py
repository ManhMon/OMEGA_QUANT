import logging
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from omega.quant.execution.multi_symbol_router import MultiSymbolRouter, BrokerType
from omega.quant.risk.realtime_risk import RealtimeRiskGuard, RiskVerdict
from omega.quant.execution.live_bridge import LiveExecutionBridge, ExecutionOrder, ExecutionState, OrderSide, OrderType
from omega.core.sre.kill_switch import get_kill_switch
from omega.execution.pre_trade_controls import PreTradeGate, Order as PreTradeOrder

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    IDLE = "IDLE"
    ROUTING = "ROUTING"
    RISK_CHECK = "RISK_CHECK"
    PRE_TRADE_GATE = "PRE_TRADE_GATE"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


@dataclass
class PipelineResult:
    symbol: str
    order_id: str
    state: PipelineState
    verdict: Optional[RiskVerdict] = None
    execution_orders: List[ExecutionOrder] = None
    error: Optional[str] = None


class LiveTradingPipeline:
    """
    Institutional Live Trading Pipeline (Phase 16.4).
    Orchestrates Kill Switch -> MultiSymbolRouter -> RiskGuard -> PreTradeGate -> ExecutionBridge.

    Safety guarantees:
    - Global kill switch is checked before routing AND immediately before execution.
    - PreTradeGate is mandatory; orders are rejected when absent (fail-closed).
    - RealtimeRiskGuard continues to enforce real-time risk limits.
    """
    def __init__(
        self,
        router: MultiSymbolRouter,
        risk_guard: RealtimeRiskGuard,
        execution: LiveExecutionBridge,
        pre_trade_gate: Optional[PreTradeGate] = None,
        account_id: str = "default"
    ):
        """
        Args:
            pre_trade_gate: PreTradeGate instance. LIVE-01 FIX: when None,
                            the pipeline operates in fail-closed mode — all
                            orders are rejected until a PreTradeGate is wired.
        """
        self.router = router
        self.risk_guard = risk_guard
        self.execution = execution
        self.pre_trade_gate = pre_trade_gate
        self.account_id = account_id
        self._state = PipelineState.IDLE

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: float,
        adv_20d: float,
        order_type: OrderType = OrderType.MARKET
    ) -> PipelineResult:
        """
        Submit order through full pipeline with safety gates.

        Order flow:
          0. Kill switch check (pre-routing)
          1. Route to broker
          2. RealtimeRiskGuard check
          3. PreTradeGate check (mandatory — fail-closed when absent)
          4. Kill switch check (pre-execution)
          5. Execute
        """
        try:
            # Step 0: Kill switch check before routing
            kill_switch = get_kill_switch()
            if kill_switch.is_activated:
                logger.critical("Kill switch active — order blocked for %s", symbol)
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.KILL_SWITCH_ACTIVE,
                    error="Global kill switch is activated — all order submission halted"
                )

            # Step 1: Route to broker
            broker = self.router.get_broker_for_symbol(symbol)
            if not broker:
                broker = BrokerType.SSI
                logger.info("Using default broker SSI for %s", symbol)

            # Step 2: Realtime risk check
            verdict = self.risk_guard.check_order(symbol, quantity, price, adv_20d)
            if verdict != RiskVerdict.PASS:
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.FAILED,
                    verdict=verdict,
                    error=f"Risk rejected: {verdict.value}"
                )

            # Step 3: Pre-trade gate check (LIVE-01: fail-closed when absent)
            if self.pre_trade_gate is None:
                logger.critical(
                    "PreTradeGate not configured — order BLOCKED for %s (fail-closed)",
                    symbol,
                )
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.FAILED,
                    error="PreTradeGate not configured — live orders require pre-trade controls",
                )

            pre_trade_order = PreTradeOrder(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=side.value if hasattr(side, "value") else str(side),
                quantity=float(quantity),
                price=price if order_type == OrderType.LIMIT else None,
                order_type=order_type.value if hasattr(order_type, "value") else str(order_type),
                account_id=self.account_id,
                reference_price=price,  # LIVE-02: pass current price as reference for market orders
            )
            passed, rejection_msg = self.pre_trade_gate.check(pre_trade_order)
            if not passed:
                logger.warning("PreTradeGate rejected order for %s: %s", symbol, rejection_msg)
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.FAILED,
                    error=f"PreTradeGate rejected: {rejection_msg}"
                )

            # Step 4: Kill switch re-check immediately before execution
            if kill_switch.is_activated:
                logger.critical("Kill switch activated pre-execution — order blocked for %s", symbol)
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.KILL_SWITCH_ACTIVE,
                    error="Global kill switch activated before execution — order halted"
                )

            # Step 5: Execute
            execution_order = self.execution.submit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price if order_type == OrderType.LIMIT else None,
                current_price=price
            )

            return PipelineResult(
                symbol=symbol,
                order_id=execution_order.order_id,
                state=PipelineState.COMPLETED,
                verdict=RiskVerdict.PASS,
                execution_orders=[execution_order]
            )

        except Exception as e:
            logger.exception("Pipeline error for %s", symbol)
            return PipelineResult(
                symbol=symbol,
                order_id="",
                state=PipelineState.FAILED,
                error=str(e)
            )
