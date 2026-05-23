"""
OMEGA_QUANT Execution Package (Layer 03)
Phase 4.3: Order Routing & Broker Integration

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
    PaperTradingEngine,
)

from .order_router import (
    TradingMode,
    SSIBrokerGateway,
    OrderRouterConfig,
    OrderRouter,
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
]
