"""
OMEGA_QUANT Execution Engine (Layer 03)
Phase 4.3: Order Routing & Broker Integration

Vectorized/Event-based | Institutional Grade | PIT-Safe

Features:
- Abstract BrokerGateway interface
- PaperTradingEngine for simulation
- OrderRouter for live/paper routing
- SSI Gateway (simulated)

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import hashlib

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enumeration matching VN broker standards."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type enumeration for VN market."""
    MARKET = "MARKET"  # Market order (ATO/ATC)
    LIMIT = "LIMIT"    # Limit order (LO)
    MP = "MP"          # Market price order


@dataclass
class BrokerOrder:
    """
    Standardized order representation for broker submission.
    
    PIT Safety: All fields must be based on T-1 or earlier data.
    """
    symbol: str
    side: OrderSide
    quantity: int  # Must be board-lot compliant (100 shares)
    order_type: OrderType
    price: Optional[float] = None  # Required for LIMIT orders
    time_in_force: str = "DAY"
    client_order_id: Optional[str] = None
    allow_odd_lot: bool = False
    
    def __post_init__(self):
        """Validate and sanitize order constraints."""
        # Ensure side is valid
        if not isinstance(self.side, OrderSide):
             # Try to convert from string if necessary (lenient validation)
             try:
                 self.side = OrderSide(self.side)
             except ValueError:
                 raise ValueError(f"Invalid order side: {self.side}")
                 
        # Liquidation odd-lots must pass through unchanged when explicitly allowed.
        if self.allow_odd_lot:
            if self.quantity <= 0:
                raise ValueError(f"Order quantity must be positive: {self.quantity}")
        # Board-lot rounding (VN market: 100 shares minimum)
        elif self.quantity % 100 != 0:
            original_qty = self.quantity
            self.quantity = (self.quantity // 100) * 100
            if self.quantity < 100:
                self.quantity = 100 # Minimum floor
            logger.warning(f"Rounded quantity {original_qty} to board-lot {self.quantity}")
        
        # Price validation for LIMIT orders
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders require a price")
        
        # Generate client order ID if not provided
        if self.client_order_id is None:
            self.client_order_id = self._generate_order_id()
    
    def _generate_order_id(self) -> str:
        """Generate unique client order ID."""
        timestamp = int(time.time() * 1000)
        random_suffix = 1000 + (hash(f"{self.symbol}_{self.side.value}_{self.quantity}_{timestamp}") % 8999)
        data = f"{self.symbol}_{self.side.value}_{self.quantity}_{timestamp}_{random_suffix}"
        hash_suffix = hashlib.md5(data.encode()).hexdigest()[:8]
        return f"OMEGA_{timestamp}_{random_suffix}_{hash_suffix}"


@dataclass
class BrokerOrderResponse:
    """Response from broker after order submission."""
    success: bool
    broker_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    message: Optional[str] = None
    timestamp: Optional[float] = None
    error_code: Optional[str] = None


@dataclass
class BrokerOrderStatus:
    """Order status response from broker."""
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: Optional[float] = None
    last_update_time: Optional[float] = None
    reject_reason: Optional[str] = None


@dataclass
class BrokerCredentials:
    """
    Broker authentication credentials.
    
    Security: Must be loaded from environment variables or encrypted storage.
    NEVER hardcode credentials in source code.
    """
    broker_name: str
    api_key: str
    api_secret: str
    account_id: str
    base_url: str
    additional_params: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate credentials are not empty."""
        if not all([self.api_key, self.api_secret, self.account_id]):
            raise ValueError("Broker credentials cannot be empty")
    
    def __repr__(self) -> str:
        """Mask sensitive information in repr."""
        return (f"BrokerCredentials(broker_name={self.broker_name}, "
                f"api_key=*****, api_secret=*****, "
                f"account_id={self.account_id[:4]}****)")


class BrokerGateway(ABC):
    """
    Abstract base class for broker API integration.
    
    Design Principles:
    1. PIT Safety: No future data leakage during live trading
    2. Security: Credentials from env vars or encrypted files only
    3. Reliability: Exponential backoff for API calls
    4. Compliance: All orders meet VN market rules (board-lot 100, T+2.5)
    """
    
    def __init__(self, credentials: BrokerCredentials):
        """Initialize broker gateway."""
        self.credentials = credentials
        self.authenticated = False
        self.session_token: Optional[str] = None
        self.max_retries = 3
        self.base_backoff_seconds = 1.0
        
        logger.info(f"Initialized {self.__class__.__name__} for broker: {credentials.broker_name}")
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with broker API."""
        pass
    
    @abstractmethod
    def submit_order(self, order: BrokerOrder) -> BrokerOrderResponse:
        """Submit order to broker."""
        pass
    
    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get current status of an order."""
        pass
    
    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel a pending order."""
        pass
    
    def _exponential_backoff_retry(self, func, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"All retries exhausted for {func.__name__}: {e}")
                    raise
                
                backoff_time = self.base_backoff_seconds * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                             f"Retrying in {backoff_time}s...")
                time.sleep(backoff_time)
    
    def validate_order_compliance(self, order: BrokerOrder) -> tuple[bool, Optional[str]]:
        """Validate order meets VN market compliance rules."""
        # Board-lot validation (100 shares)
        if not order.allow_odd_lot and order.quantity % 100 != 0:
            return False, f"Order quantity must be board-lot compliant (100 shares): {order.quantity}"
        
        # Minimum order size
        if not order.allow_odd_lot and order.quantity < 100:
            return False, f"Order quantity must be at least 100 shares: {order.quantity}"
        
        # Price validation for LIMIT orders
        if order.order_type == OrderType.LIMIT:
            if order.price is None or order.price <= 0:
                return False, f"LIMIT order requires valid price: {order.price}"
        
        return True, None
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information (balance, positions, etc.)."""
        logger.warning(f"{self.__class__.__name__} does not implement get_account_info()")
        return {}


class VNDirectBroker(BrokerGateway):
    """
    VNDirect broker gateway implementation.

    Simulates VNDirect API for paper/test environments.
    Production use requires real VNDirect API credentials and endpoints.
    """

    def __init__(self, credentials: BrokerCredentials):
        super().__init__(credentials)
        self._session_token: Optional[str] = None
        self._order_counter: int = int(time.time() * 1000) % 10_000_000

    def authenticate(self) -> bool:
        """Authenticate with VNDirect API (simulated)."""
        if not self.credentials.api_key or not self.credentials.api_secret:
            logger.error("VNDirectBroker: missing api_key or api_secret")
            self.authenticated = False
            return False
        self._session_token = (
            f"VNDIRECT_TOKEN_{self.credentials.account_id}_{int(time.time())}"
        )
        self.authenticated = True
        logger.info(f"VNDirectBroker authenticated: account={self.credentials.account_id}")
        return True

    def submit_order(self, order: BrokerOrder) -> BrokerOrderResponse:
        """Submit order to VNDirect (simulated)."""
        # Lazy auth
        if not self.authenticated:
            ok = self.authenticate()
            if not ok:
                return BrokerOrderResponse(
                    success=False,
                    client_order_id=order.client_order_id,
                    status=OrderStatus.REJECTED,
                    message="Authentication failed",
                    error_code="NOT_AUTHENTICATED",
                    timestamp=time.time(),
                )

        # Compliance check
        compliant, reason = self.validate_order_compliance(order)
        if not compliant:
            return BrokerOrderResponse(
                success=False,
                client_order_id=order.client_order_id,
                status=OrderStatus.REJECTED,
                message=reason,
                error_code="COMPLIANCE_VIOLATION",
                timestamp=time.time(),
            )

        self._order_counter += 1
        broker_order_id = f"VNDIRECT_{self._order_counter}"

        logger.info(
            f"VNDirectBroker submitted: {broker_order_id} "
            f"{order.symbol} {order.side.value} {order.quantity}"
        )

        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=order.client_order_id,
            status=OrderStatus.SUBMITTED,
            message="Order submitted to VNDirect",
            timestamp=time.time(),
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get order status from VNDirect (simulated — returns SUBMITTED)."""
        return BrokerOrderStatus(
            broker_order_id=broker_order_id,
            client_order_id=broker_order_id,
            symbol="UNKNOWN",
            side=OrderSide.BUY,
            status=OrderStatus.SUBMITTED,
            quantity=100,
            filled_quantity=0,
            remaining_quantity=100,
            last_update_time=time.time(),
        )

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order on VNDirect (simulated)."""
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=broker_order_id,
            status=OrderStatus.CANCELLED,
            message=f"Order {broker_order_id} cancelled on VNDirect",
            timestamp=time.time(),
        )


class PaperTradingEngine(BrokerGateway):
    """
    Paper trading engine for simulation.
    
    Simulates order execution without actual broker interaction.
    Used for backtesting and strategy validation.
    """
    
    def __init__(self):
        """Initialize paper trading engine."""
        credentials = BrokerCredentials(
            broker_name="PAPER",
            api_key="PAPER_KEY",
            api_secret="PAPER_SECRET",
            account_id="PAPER_ACCOUNT",
            base_url="paper://localhost"
        )
        super().__init__(credentials)
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.order_counter = 1
        logger.info("Initialized PaperTradingEngine")
    
    def authenticate(self) -> bool:
        """Paper trading always authenticated."""
        self.authenticated = True
        return True
    
    def submit_order(self, order: BrokerOrder, current_price: Optional[float] = None) -> BrokerOrderResponse:
        """Submit order to paper trading engine."""
        if order.order_type == OrderType.MARKET and (current_price is None or current_price <= 0):
            logger.error("Paper trading requires current_price parameter for MARKET orders")
            return BrokerOrderResponse(
                success=False,
                client_order_id=order.client_order_id,
                status=OrderStatus.REJECTED,
                message="Paper trading requires current_price",
                error_code="MISSING_PRICE",
            )
            
        broker_order_id = f"PAPER_{self.order_counter}"
        self.order_counter += 1
        
        # Simulate immediate fill at current price for paper trading
        fill_price = current_price if order.order_type == OrderType.MARKET else order.price
        
        self.orders[broker_order_id] = {
            "broker_order_id": broker_order_id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "filled_quantity": order.quantity,
            "remaining_quantity": 0,
            "order_type": order.order_type,
            "price": order.price,
            "fill_price": fill_price,
            "status": OrderStatus.FILLED,
        }
        
        logger.info(f"Paper order filled: {broker_order_id} - {order.symbol} "
                   f"{order.side.value} {order.quantity} @ {fill_price}")
        
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=order.client_order_id,
            status=OrderStatus.FILLED,
            message="Order filled (PAPER)",
        )
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get order status from paper trading engine."""
        if broker_order_id not in self.orders:
            raise ValueError(f"Order not found: {broker_order_id}")
        
        order_data = self.orders[broker_order_id]
        
        return BrokerOrderStatus(
            broker_order_id=order_data["broker_order_id"],
            client_order_id=order_data["client_order_id"],
            symbol=order_data["symbol"],
            side=order_data["side"],
            status=order_data["status"],
            quantity=order_data["quantity"],
            filled_quantity=order_data["filled_quantity"],
            remaining_quantity=order_data["remaining_quantity"],
            average_fill_price=order_data.get("fill_price"),
        )
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order in paper trading engine."""
        if broker_order_id not in self.orders:
            return BrokerOrderResponse(
                success=False,
                broker_order_id=broker_order_id,
                status=OrderStatus.REJECTED,
                message=f"Order not found: {broker_order_id}",
                error_code="ORDER_NOT_FOUND",
            )
        
        order_data = self.orders[broker_order_id]
        
        if order_data["status"] == OrderStatus.FILLED:
            return BrokerOrderResponse(
                success=False,
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                message="Cannot cancel filled order",
                error_code="CANNOT_CANCEL",
            )
        
        order_data["status"] = OrderStatus.CANCELLED
        order_data["remaining_quantity"] = order_data["quantity"]
        
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            status=OrderStatus.CANCELLED,
            message="Order cancelled (PAPER)",
        )
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get simulated account info."""
        return {
            "cash": 1_000_000_000.0,  # 1B VND
            "positions": {},
            "total_equity": 1_000_000_000.0,
        }
