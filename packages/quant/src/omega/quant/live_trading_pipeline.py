import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from omega.quant.multi_symbol_router import MultiSymbolRouter, BrokerType
from omega.quant.realtime_risk_guard import RealtimeRiskGuard, RiskVerdict, OrderSide as RiskOrderSide
from omega.quant.live_execution_bridge import LiveExecutionBridge, ExecutionOrder, ExecutionState, OrderSide, OrderType

logger = logging.getLogger(__name__)

class PipelineState(Enum):
    IDLE = "IDLE"
    ROUTING = "ROUTING"
    RISK_CHECK = "RISK_CHECK"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class PipelineResult:
    symbol: str
    order_id: str
    state: PipelineState
    verdict: Optional[RiskVerdict] = None
    broker: Optional[BrokerType] = None
    venue: Optional[str] = None
    execution_orders: List[ExecutionOrder] = None
    error: Optional[str] = None

class LiveTradingPipeline:
    """
    Institutional Live Trading Pipeline (Phase 16.4).
    Orchestrates MultiSymbolRouter -> RiskGuard -> ExecutionBridge.
    """
    def __init__(
        self,
        router: MultiSymbolRouter,
        risk_guard: RealtimeRiskGuard,
        execution: LiveExecutionBridge
    ):
        self.router = router
        self.risk_guard = risk_guard
        self.execution = execution
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
        Submit order through full pipeline.
        """
        try:
            # Step 1: Route to broker/venue
            broker = self.router.get_broker_for_symbol(symbol)
            if not broker:
                # Default to SSI for known symbols if not explicitly routed
                broker = BrokerType.SSI
                logger.info(f"Using default broker SSI for {symbol}")
            venue = broker.value

            # Step 2: Risk check — map execution OrderSide to RiskOrderSide
            risk_side = (
                RiskOrderSide.SELL if side == OrderSide.SELL else RiskOrderSide.BUY
            )
            verdict = self.risk_guard.check_order(
                symbol=symbol,
                quantity=quantity,
                price=price,
                adv_20d=adv_20d,
                side=risk_side,
            )
            if verdict != RiskVerdict.PASS:
                return PipelineResult(
                    symbol=symbol,
                    order_id="",
                    state=PipelineState.FAILED,
                    verdict=verdict,
                    broker=broker,
                    venue=venue,
                    error=f"Risk rejected: {verdict.value}"
                )

            # Step 3: Execute — broker/venue recorded in result for audit trail
            execution_order = self.execution.submit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price if order_type == OrderType.LIMIT else None,
                current_price=price,  # For paper trading
                broker=broker.value,
                venue=venue,
            )

            return PipelineResult(
                symbol=symbol,
                order_id=execution_order.order_id,
                state=PipelineState.COMPLETED,
                verdict=RiskVerdict.PASS,
                broker=broker,
                venue=venue,
                execution_orders=[execution_order]
            )

        except Exception as e:
            logger.exception(f"Pipeline error for {symbol}")
            return PipelineResult(
                symbol=symbol,
                order_id="",
                state=PipelineState.FAILED,
                error=str(e)
            )
