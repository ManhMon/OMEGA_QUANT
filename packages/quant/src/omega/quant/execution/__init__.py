"""
OMEGA_QUANT Execution Module
Phase 4.3: Order Routing & Broker Integration

Author: Backend Engineer (Role 09)
Date: 2026-05-14
Version: 1.0.0
"""

from omega.quant.execution.broker_gateway import (
    BrokerOrder,
    BrokerCredentials,
    OrderResponse,
    OrderStatus,
    OrderStatusResponse,
    OrderSide,
    OrderType,
    PaperTradingEngine
)

from omega.quant.execution.order_router import (
    OrderRouter,
    OrderRouterConfig,
    TradingMode,
    SSIBrokerGateway
)

__all__ = [
    'BrokerOrder',
    'BrokerCredentials',
    'OrderResponse',
    'OrderStatus',
    'OrderStatusResponse',
    'OrderSide',
    'OrderType',
    'PaperTradingEngine',
    'OrderRouter',
    'OrderRouterConfig',
    'TradingMode',
    'SSIBrokerGateway'
]
