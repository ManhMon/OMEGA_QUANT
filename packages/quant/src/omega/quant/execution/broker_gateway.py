"""
OMEGA_QUANT Execution Module - Broker Gateway
Phase 4.3: Order Routing & Broker Integration

Author: Backend Engineer (Role 09)
Date: 2026-05-14
Version: 1.0.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
import uuid


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class BrokerCredentials:
    """
    Broker API credentials.
    
    Attributes:
        broker_name: Name of the broker (e.g., "SSI", "VPS")
        api_key: API key for authentication
        api_secret: API secret for authentication
        account_id: Trading account ID
        base_url: Base URL for broker API
    """
    broker_name: str
    api_key: str
    api_secret: str
    account_id: str
    base_url: str


@dataclass
class BrokerOrder:
    """
    Broker order representation.
    
    Attributes:
        symbol: Stock symbol (e.g., "VNM", "FPT")
        side: Order side (BUY or SELL)
        quantity: Order quantity (must be board-lot multiple of 100)
        order_type: Order type (MARKET or LIMIT)
        price: Limit price (required for LIMIT orders)
    """
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    price: Optional[float] = None
    
    def __post_init__(self):
        """Validate order after initialization."""
        # Round quantity to board-lot (100 shares)
        self.quantity = (self.quantity // 100) * 100
        
        # Validate LIMIT orders have price
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require a price")


@dataclass
class OrderResponse:
    """
    Order submission response.
    
    Attributes:
        success: Whether order was successfully submitted
        broker_order_id: Broker-assigned order ID
        status: Current order status
        message: Response message
        average_fill_price: Average fill price (if filled)
    """
    success: bool
    broker_order_id: str
    status: OrderStatus
    message: str
    average_fill_price: Optional[float] = None


@dataclass
class OrderStatusResponse:
    """
    Order status query response.
    
    Attributes:
        broker_order_id: Broker-assigned order ID
        symbol: Stock symbol
        status: Current order status
        filled_quantity: Quantity filled
        average_fill_price: Average fill price
    """
    broker_order_id: str
    symbol: str
    status: OrderStatus
    filled_quantity: int
    average_fill_price: float


class PaperTradingEngine:
    """
    Paper trading engine for simulation.
    
    Simulates order execution without real broker connection.
    All orders are immediately filled at the current price.
    """
    
    def __init__(self):
        """Initialize paper trading engine."""
        self._orders: Dict[str, OrderStatusResponse] = {}
    
    def submit_order(
        self,
        order: BrokerOrder,
        current_price: float
    ) -> OrderResponse:
        """
        Submit order to paper trading engine.
        
        Args:
            order: BrokerOrder to submit
            current_price: Current market price for simulation
        
        Returns:
            OrderResponse with simulated fill
        """
        # Generate paper order ID
        order_id = f"PAPER_{uuid.uuid4().hex[:8].upper()}"
        
        # Simulate immediate fill
        fill_price = current_price
        
        # Store order status
        self._orders[order_id] = OrderStatusResponse(
            broker_order_id=order_id,
            symbol=order.symbol,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            average_fill_price=fill_price
        )
        
        return OrderResponse(
            success=True,
            broker_order_id=order_id,
            status=OrderStatus.FILLED,
            message=f"Paper order filled at {fill_price}",
            average_fill_price=fill_price
        )
    
    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        """
        Get order status.
        
        Args:
            order_id: Broker order ID
        
        Returns:
            OrderStatusResponse with current status
        """
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")
        
        return self._orders[order_id]
