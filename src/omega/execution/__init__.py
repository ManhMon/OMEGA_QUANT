"""
OMEGA_QUANT Execution Package (Layer 03)
Phase 4.3 / Phase 16: Order Routing, Latency Simulation & Liquidation Exposure

Vectorized/Event-based | Institutional Grade | PIT-Safe
"""

from .broker_gateway import (
    OrderStatus,
    OrderSide,
    OrderType,
    BrokerOrder,
    BrokerOrderResponse,
    BrokerOrderStatus,
    BrokerCredentials,
    BrokerGateway,
    VNDirectBroker,
    PaperTradingEngine,
)

from .order_router import (
    TradingMode,
    SSIBrokerGateway,
    OrderRouterConfig,
    OrderRouter,
    LatencyConfig,
    LiquidationExposure,
)

from .order_generator import (
    PositionSizingConfig,
    OrderGenerator,
)

from .order_book_analyzer import (
    MarketDepth,
    OrderBookSnapshot,
    OrderBookAnalyzer,
)

from .execution_engine import (
    ExecutionEngineConfig,
    ExecutionEngine,
)

from .trade_blotter import (
    TradeRecord,
    TradeBlotter,
)

from .execution_analytics import (
    ExecutionMetrics,
    ExecutionAnalytics,
)

from .pre_trade_controls import (
    RejectionReason,
    Order,
    PreTradeCheckResult,
    PositionLimit,
    PreTradeGate,
)

from .post_trade_controls import (
    FillQuality,
    AlertLevel,
    Fill,
    PostTradeReport,
    VWAPData,
    PostTradeGate,
)

from .order_state_machine import (
    OrderState,
    OrderEvent,
    StateTransition,
    OrderContext,
    OrderStateMachine,
    OrderStateMachineManager,
)

__all__ = [
    # broker_gateway
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "BrokerOrder",
    "BrokerOrderResponse",
    "BrokerOrderStatus",
    "BrokerCredentials",
    "BrokerGateway",
    "PaperTradingEngine",
    # order_router
    "TradingMode",
    "SSIBrokerGateway",
    "OrderRouterConfig",
    "OrderRouter",
    "LatencyConfig",
    "LiquidationExposure",
    # order_generator
    "PositionSizingConfig",
    "OrderGenerator",
    # order_book_analyzer
    "MarketDepth",
    "OrderBookSnapshot",
    "OrderBookAnalyzer",
    # execution_engine
    "ExecutionEngineConfig",
    "ExecutionEngine",
    # trade_blotter
    "TradeRecord",
    "TradeBlotter",
    # execution_analytics
    "ExecutionMetrics",
    "ExecutionAnalytics",
    # pre_trade_controls
    "RejectionReason",
    "Order",
    "PreTradeCheckResult",
    "PositionLimit",
    "PreTradeGate",
    # post_trade_controls
    "FillQuality",
    "AlertLevel",
    "Fill",
    "PostTradeReport",
    "VWAPData",
    "PostTradeGate",
    # order_state_machine
    "OrderState",
    "OrderEvent",
    "StateTransition",
    "OrderContext",
    "OrderStateMachine",
    "OrderStateMachineManager",
]

try:
    from . import broker_adapter
except ImportError:
    pass

try:
    from . import cost_estimator
except ImportError:
    pass

try:
    from . import live_trading_pipeline
except ImportError:
    pass

try:
    from . import market_impact
except ImportError:
    pass

try:
    from . import microstructure_router
except ImportError:
    pass

try:
    from . import partial_fill_handler
except ImportError:
    pass

try:
    from . import reconciliation
except ImportError:
    pass

try:
    from . import risk_limits
except ImportError:
    pass

try:
    from . import signal_validator
except ImportError:
    pass

try:
    from . import smart_router
except ImportError:
    pass

try:
    from . import ssi_broker_gateway
except ImportError:
    pass

try:
    from . import tca
except ImportError:
    pass

try:
    from . import turnover_control
except ImportError:
    pass

try:
    from . import vn_transaction_cost_model
except ImportError:
    pass
