"""Pre-trade risk controls and validation gate.

Implements pre-trade checks before order submission:
- Position limit validation
- Order size vs ADV (Average Daily Volume)
- Margin requirement checks
- Restricted list validation
- Duplicate order detection
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging
from datetime import datetime, timedelta
import threading


logger = logging.getLogger(__name__)


class RejectionReason(Enum):
    """Pre-trade rejection reasons."""
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    ORDER_SIZE_TOO_LARGE = "order_size_too_large"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    RESTRICTED_SYMBOL = "restricted_symbol"
    DUPLICATE_ORDER = "duplicate_order"
    INVALID_PRICE = "invalid_price"
    MARKET_CLOSED = "market_closed"
    UNKNOWN_SYMBOL = "unknown_symbol"


@dataclass
class Order:
    """Order representation for pre-trade checks."""
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    price: Optional[float]
    order_type: str  # LIMIT, MARKET, STOP
    account_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reference_price: Optional[float] = None  # LIVE-02: last/reference price for market orders
    
    def __hash__(self):
        return hash((self.symbol, self.side, self.quantity, self.price, self.account_id))


@dataclass
class PreTradeCheckResult:
    """Result of pre-trade validation."""
    passed: bool
    reason: Optional[RejectionReason] = None
    message: str = ""
    details: Dict = field(default_factory=dict)


@dataclass
class PositionLimit:
    """Position limit configuration."""
    symbol: str
    max_position: float
    max_order_size: float
    max_adv_percentage: float = 0.1  # 10% of ADV


class PreTradeGate:
    """Pre-trade risk gate with comprehensive validation checks."""
    
    def __init__(
        self,
        position_limits: Optional[Dict[str, PositionLimit]] = None,
        restricted_symbols: Optional[List[str]] = None,
        margin_requirement: float = 0.5,
        duplicate_window_seconds: int = 60
    ):
        """Initialize pre-trade gate.
        
        Args:
            position_limits: Symbol-specific position limits
            restricted_symbols: List of restricted trading symbols
            margin_requirement: Margin requirement ratio (0.5 = 50%)
            duplicate_window_seconds: Time window for duplicate detection
        """
        self.position_limits = position_limits or {}
        self.restricted_symbols = set(restricted_symbols or [])
        self.margin_requirement = margin_requirement
        self.duplicate_window_seconds = duplicate_window_seconds
        
        # Current positions tracking
        self._positions: Dict[str, float] = {}
        self._positions_lock = threading.Lock()
        
        # ADV (Average Daily Volume) cache
        self._adv_cache: Dict[str, float] = {}
        self._adv_lock = threading.Lock()
        
        # Recent orders for duplicate detection
        self._recent_orders: List[Tuple[Order, datetime]] = []
        self._orders_lock = threading.Lock()
        
        # Account margin tracking
        self._account_margins: Dict[str, float] = {}
        self._margin_lock = threading.Lock()
        
        logger.info("PreTradeGate initialized with %d position limits", len(self.position_limits))
    
    def check(self, order: Order) -> Tuple[bool, Optional[str]]:
        """Run all pre-trade checks on an order.
        
        Args:
            order: Order to validate
            
        Returns:
            Tuple of (pass/reject boolean, rejection reason string)
        """
        result = self._run_checks(order)
        
        if result.passed:
            self._record_order(order)
            logger.info("Order %s passed pre-trade checks", order.order_id)
        else:
            logger.warning(
                "Order %s rejected: %s - %s",
                order.order_id,
                result.reason.value if result.reason else "unknown",
                result.message
            )
        
        return result.passed, result.message
    
    def _run_checks(self, order: Order) -> PreTradeCheckResult:
        """Execute all validation checks."""
        # Check 1: Restricted list
        result = self._check_restricted_list(order)
        if not result.passed:
            return result
        
        # Check 2: Position limits
        result = self._check_position_limits(order)
        if not result.passed:
            return result
        
        # Check 3: Order size vs ADV
        result = self._check_adv_limit(order)
        if not result.passed:
            return result
        
        # Check 4: Margin requirements
        result = self._check_margin(order)
        if not result.passed:
            return result
        
        # Check 5: Duplicate order detection
        result = self._check_duplicate(order)
        if not result.passed:
            return result
        
        # Check 6: Price validation
        result = self._check_price_validity(order)
        if not result.passed:
            return result
        
        return PreTradeCheckResult(passed=True, message="All checks passed")
    
    def _check_restricted_list(self, order: Order) -> PreTradeCheckResult:
        """Check if symbol is on restricted list."""
        if order.symbol in self.restricted_symbols:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.RESTRICTED_SYMBOL,
                message=f"Symbol {order.symbol} is on restricted list"
            )
        return PreTradeCheckResult(passed=True)
    
    def _check_position_limits(self, order: Order) -> PreTradeCheckResult:
        """Check position and order size limits."""
        limit = self.position_limits.get(order.symbol)
        if not limit:
            # No limit configured, pass
            return PreTradeCheckResult(passed=True)
        
        with self._positions_lock:
            current_position = self._positions.get(order.symbol, 0.0)
        
        # Calculate new position after order
        position_delta = order.quantity if order.side == "BUY" else -order.quantity
        new_position = current_position + position_delta
        
        # Check absolute position limit
        if abs(new_position) > limit.max_position:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.POSITION_LIMIT_EXCEEDED,
                message=f"Position limit exceeded: {abs(new_position):.2f} > {limit.max_position:.2f}",
                details={"current_position": current_position, "new_position": new_position}
            )
        
        # Check order size limit
        if order.quantity > limit.max_order_size:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.ORDER_SIZE_TOO_LARGE,
                message=f"Order size {order.quantity:.2f} exceeds limit {limit.max_order_size:.2f}"
            )
        
        return PreTradeCheckResult(passed=True)
    
    def _check_adv_limit(self, order: Order) -> PreTradeCheckResult:
        """Check order size against Average Daily Volume."""
        limit = self.position_limits.get(order.symbol)
        if not limit:
            return PreTradeCheckResult(passed=True)
        
        with self._adv_lock:
            adv = self._adv_cache.get(order.symbol, 0.0)
        
        if adv == 0.0:
            # No ADV data, pass (or could reject for safety)
            logger.warning("No ADV data for %s, skipping ADV check", order.symbol)
            return PreTradeCheckResult(passed=True)
        
        max_order_vs_adv = adv * limit.max_adv_percentage
        if order.quantity > max_order_vs_adv:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.ORDER_SIZE_TOO_LARGE,
                message=f"Order size {order.quantity:.2f} exceeds {limit.max_adv_percentage*100:.1f}% of ADV ({max_order_vs_adv:.2f})",
                details={"adv": adv, "max_allowed": max_order_vs_adv}
            )
        
        return PreTradeCheckResult(passed=True)
    
    def _check_margin(self, order: Order) -> PreTradeCheckResult:
        """Check margin requirements.
        
        LIVE-02 FIX: For market orders (price=None), use reference_price to
        compute required margin. If no reference_price is available, reject
        the order (fail-closed) to prevent zero-margin bypass.
        """
        with self._margin_lock:
            available_margin = self._account_margins.get(order.account_id, 0.0)
        
        # Determine effective price for margin computation
        effective_price = order.price
        if effective_price is None and order.order_type == "MARKET":
            effective_price = order.reference_price
        
        # LIVE-02: Fail-closed — market order with no price reference is unsafe
        if effective_price is None or effective_price <= 0:
            if order.order_type == "MARKET":
                return PreTradeCheckResult(
                    passed=False,
                    reason=RejectionReason.INSUFFICIENT_MARGIN,
                    message=(
                        f"Market order for {order.symbol} has no reference price — "
                        "cannot compute margin (fail-closed)"
                    ),
                )
            # Limit orders without price are caught by _check_price_validity
            return PreTradeCheckResult(passed=True)
        
        # Calculate required margin for this order
        order_value = order.quantity * effective_price
        required_margin = order_value * self.margin_requirement
        
        if required_margin > available_margin:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.INSUFFICIENT_MARGIN,
                message=f"Insufficient margin: required {required_margin:.2f}, available {available_margin:.2f}",
                details={"required": required_margin, "available": available_margin}
            )
        
        return PreTradeCheckResult(passed=True)
    
    def _check_duplicate(self, order: Order) -> PreTradeCheckResult:
        """Check for duplicate orders within time window."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.duplicate_window_seconds)
        
        with self._orders_lock:
            # Clean old orders
            self._recent_orders = [
                (o, t) for o, t in self._recent_orders if t > cutoff
            ]
            
            # Check for duplicates
            for recent_order, _ in self._recent_orders:
                if self._is_duplicate(order, recent_order):
                    return PreTradeCheckResult(
                        passed=False,
                        reason=RejectionReason.DUPLICATE_ORDER,
                        message=f"Duplicate order detected within {self.duplicate_window_seconds}s window"
                    )
        
        return PreTradeCheckResult(passed=True)
    
    def _check_price_validity(self, order: Order) -> PreTradeCheckResult:
        """Validate order price is reasonable."""
        if order.order_type == "MARKET":
            return PreTradeCheckResult(passed=True)
        
        if order.price is None or order.price <= 0:
            return PreTradeCheckResult(
                passed=False,
                reason=RejectionReason.INVALID_PRICE,
                message=f"Invalid price: {order.price}"
            )
        
        return PreTradeCheckResult(passed=True)
    
    def _is_duplicate(self, order1: Order, order2: Order) -> bool:
        """Check if two orders are duplicates."""
        return (
            order1.symbol == order2.symbol and
            order1.side == order2.side and
            abs(order1.quantity - order2.quantity) < 0.01 and
            order1.account_id == order2.account_id and
            (order1.price is None or order2.price is None or abs(order1.price - order2.price) < 0.01)
        )
    
    def _record_order(self, order: Order):
        """Record order for duplicate detection."""
        with self._orders_lock:
            self._recent_orders.append((order, datetime.utcnow()))
    
    # Configuration and state management methods
    
    def update_position(self, symbol: str, position: float):
        """Update current position for a symbol."""
        with self._positions_lock:
            self._positions[symbol] = position
        logger.debug("Updated position for %s: %.2f", symbol, position)
    
    def update_adv(self, symbol: str, adv: float):
        """Update Average Daily Volume for a symbol."""
        with self._adv_lock:
            self._adv_cache[symbol] = adv
        logger.debug("Updated ADV for %s: %.2f", symbol, adv)
    
    def update_margin(self, account_id: str, margin: float):
        """Update available margin for an account."""
        with self._margin_lock:
            self._account_margins[account_id] = margin
        logger.debug("Updated margin for %s: %.2f", account_id, margin)
    
    def add_position_limit(self, limit: PositionLimit):
        """Add or update position limit for a symbol."""
        self.position_limits[limit.symbol] = limit
        logger.info("Added position limit for %s", limit.symbol)
    
    def add_restricted_symbol(self, symbol: str):
        """Add symbol to restricted list."""
        self.restricted_symbols.add(symbol)
        logger.info("Added %s to restricted list", symbol)
    
    def remove_restricted_symbol(self, symbol: str):
        """Remove symbol from restricted list."""
        self.restricted_symbols.discard(symbol)
        logger.info("Removed %s from restricted list", symbol)
    
    def get_statistics(self) -> Dict:
        """Get current gate statistics."""
        with self._positions_lock:
            position_count = len(self._positions)
        
        with self._orders_lock:
            recent_order_count = len(self._recent_orders)
        
        return {
            "position_limits_configured": len(self.position_limits),
            "restricted_symbols": len(self.restricted_symbols),
            "tracked_positions": position_count,
            "recent_orders": recent_order_count,
            "margin_requirement": self.margin_requirement,
            "duplicate_window_seconds": self.duplicate_window_seconds
        }
