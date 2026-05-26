"""Order lifecycle state machine.

Implements finite state machine for order lifecycle management:
- States: CREATED, VALIDATED, SUBMITTED, PARTIAL_FILL, FILLED, CANCELLED, REJECTED, EXPIRED
- State transitions with validation
- Event history tracking
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import logging
from datetime import datetime
import threading


logger = logging.getLogger(__name__)


class OrderState(Enum):
    """Order lifecycle states."""
    CREATED = "created"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderEvent(Enum):
    """Order lifecycle events."""
    VALIDATE = "validate"
    SUBMIT = "submit"
    PARTIAL_FILL = "partial_fill"
    FILL = "fill"
    CANCEL = "cancel"
    REJECT = "reject"
    EXPIRE = "expire"


@dataclass
class StateTransition:
    """Record of a state transition."""
    from_state: OrderState
    to_state: OrderState
    event: OrderEvent
    timestamp: datetime
    metadata: Dict = field(default_factory=dict)


@dataclass
class OrderContext:
    """Order context for state machine."""
    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    metadata: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        if self.remaining_quantity == 0.0:
            self.remaining_quantity = self.quantity


class OrderStateMachine:
    """Finite state machine for order lifecycle management."""
    
    # Valid state transitions
    TRANSITIONS: Dict[OrderState, Dict[OrderEvent, OrderState]] = {
        OrderState.CREATED: {
            OrderEvent.VALIDATE: OrderState.VALIDATED,
            OrderEvent.REJECT: OrderState.REJECTED,
        },
        OrderState.VALIDATED: {
            OrderEvent.SUBMIT: OrderState.SUBMITTED,
            OrderEvent.REJECT: OrderState.REJECTED,
            OrderEvent.CANCEL: OrderState.CANCELLED,
        },
        OrderState.SUBMITTED: {
            OrderEvent.PARTIAL_FILL: OrderState.PARTIAL_FILL,
            OrderEvent.FILL: OrderState.FILLED,
            OrderEvent.CANCEL: OrderState.CANCELLED,
            OrderEvent.REJECT: OrderState.REJECTED,
            OrderEvent.EXPIRE: OrderState.EXPIRED,
        },
        OrderState.PARTIAL_FILL: {
            OrderEvent.PARTIAL_FILL: OrderState.PARTIAL_FILL,
            OrderEvent.FILL: OrderState.FILLED,
            OrderEvent.CANCEL: OrderState.CANCELLED,
            OrderEvent.EXPIRE: OrderState.EXPIRED,
        },
        OrderState.FILLED: {},  # Terminal state
        OrderState.CANCELLED: {},  # Terminal state
        OrderState.REJECTED: {},  # Terminal state
        OrderState.EXPIRED: {},  # Terminal state
    }
    
    # Terminal states
    TERMINAL_STATES = {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED
    }
    
    def __init__(self, order_id: str, context: Optional[OrderContext] = None):
        """Initialize order state machine.
        
        Args:
            order_id: Unique order identifier
            context: Optional order context
        """
        self.order_id = order_id
        self.context = context or OrderContext(
            order_id=order_id,
            symbol="UNKNOWN",
            side="BUY",
            quantity=0.0
        )
        
        self._current_state = OrderState.CREATED
        self._history: List[StateTransition] = []
        self._lock = threading.Lock()
        
        logger.info("OrderStateMachine created for order %s", order_id)
    
    def transition(self, event: OrderEvent, metadata: Optional[Dict] = None) -> bool:
        """Attempt to transition to a new state based on event.
        
        Args:
            event: Event triggering the transition
            metadata: Optional metadata about the transition
            
        Returns:
            True if transition succeeded, False otherwise
        """
        with self._lock:
            current_state = self._current_state
            
            # Check if transition is valid
            if not self._is_valid_transition(current_state, event):
                logger.warning(
                    "Invalid transition for order %s: %s -> %s (event: %s)",
                    self.order_id,
                    current_state.value,
                    "unknown",
                    event.value
                )
                return False
            
            # Get new state
            new_state = self.TRANSITIONS[current_state][event]
            
            # Update context based on event
            self._update_context(event, metadata or {})
            
            # Record transition
            transition = StateTransition(
                from_state=current_state,
                to_state=new_state,
                event=event,
                timestamp=datetime.utcnow(),
                metadata=metadata or {}
            )
            self._history.append(transition)
            
            # Update state
            self._current_state = new_state
            
            logger.info(
                "Order %s transitioned: %s -> %s (event: %s)",
                self.order_id,
                current_state.value,
                new_state.value,
                event.value
            )
            
            return True
    
    def get_state(self) -> OrderState:
        """Get current state.
        
        Returns:
            Current OrderState
        """
        with self._lock:
            return self._current_state
    
    def history(self) -> List[StateTransition]:
        """Get state transition history.
        
        Returns:
            List of StateTransition records
        """
        with self._lock:
            return self._history.copy()
    
    def is_terminal(self) -> bool:
        """Check if order is in a terminal state.
        
        Returns:
            True if in terminal state
        """
        return self.get_state() in self.TERMINAL_STATES
    
    def is_active(self) -> bool:
        """Check if order is active (not terminal).
        
        Returns:
            True if order is active
        """
        return not self.is_terminal()
    
    def can_cancel(self) -> bool:
        """Check if order can be cancelled.
        
        Returns:
            True if cancel event is valid from current state
        """
        with self._lock:
            return self._is_valid_transition(self._current_state, OrderEvent.CANCEL)
    
    def get_fill_percentage(self) -> float:
        """Get fill percentage.
        
        Returns:
            Percentage of order filled (0.0 to 1.0)
        """
        with self._lock:
            if self.context.quantity == 0:
                return 0.0
            return self.context.filled_quantity / self.context.quantity
    
    def get_context(self) -> OrderContext:
        """Get order context.
        
        Returns:
            Copy of OrderContext
        """
        with self._lock:
            return OrderContext(
                order_id=self.context.order_id,
                symbol=self.context.symbol,
                side=self.context.side,
                quantity=self.context.quantity,
                filled_quantity=self.context.filled_quantity,
                remaining_quantity=self.context.remaining_quantity,
                metadata=self.context.metadata.copy()
            )
    
    def _is_valid_transition(self, from_state: OrderState, event: OrderEvent) -> bool:
        """Check if transition is valid."""
        return event in self.TRANSITIONS.get(from_state, {})
    
    def _update_context(self, event: OrderEvent, metadata: Dict):
        """Update order context based on event."""
        if event == OrderEvent.PARTIAL_FILL:
            fill_quantity = metadata.get("fill_quantity", 0.0)
            self.context.filled_quantity += fill_quantity
            self.context.remaining_quantity = self.context.quantity - self.context.filled_quantity
            
        elif event == OrderEvent.FILL:
            fill_quantity = metadata.get("fill_quantity", self.context.remaining_quantity)
            self.context.filled_quantity += fill_quantity
            self.context.remaining_quantity = 0.0
        
        # Store metadata
        self.context.metadata.update(metadata)
    
    def get_summary(self) -> Dict:
        """Get order summary.
        
        Returns:
            Dictionary with order summary
        """
        with self._lock:
            return {
                "order_id": self.order_id,
                "current_state": self._current_state.value,
                "is_terminal": self.is_terminal(),
                "symbol": self.context.symbol,
                "side": self.context.side,
                "quantity": self.context.quantity,
                "filled_quantity": self.context.filled_quantity,
                "remaining_quantity": self.context.remaining_quantity,
                "fill_percentage": self.get_fill_percentage(),
                "transition_count": len(self._history),
                "created_at": self._history[0].timestamp.isoformat() if self._history else None,
                "last_updated": self._history[-1].timestamp.isoformat() if self._history else None
            }
    
    def get_timeline(self) -> List[Dict]:
        """Get order timeline with all transitions.
        
        Returns:
            List of transition dictionaries
        """
        with self._lock:
            timeline = []
            for transition in self._history:
                timeline.append({
                    "from_state": transition.from_state.value,
                    "to_state": transition.to_state.value,
                    "event": transition.event.value,
                    "timestamp": transition.timestamp.isoformat(),
                    "metadata": transition.metadata
                })
            return timeline


class OrderStateMachineManager:
    """Manager for multiple order state machines."""
    
    def __init__(self):
        """Initialize manager."""
        self._machines: Dict[str, OrderStateMachine] = {}
        self._lock = threading.Lock()
        
        logger.info("OrderStateMachineManager initialized")
    
    def create_order(self, order_id: str, context: OrderContext) -> OrderStateMachine:
        """Create a new order state machine.
        
        Args:
            order_id: Unique order identifier
            context: Order context
            
        Returns:
            OrderStateMachine instance
        """
        with self._lock:
            if order_id in self._machines:
                logger.warning("Order %s already exists", order_id)
                return self._machines[order_id]
            
            machine = OrderStateMachine(order_id, context)
            self._machines[order_id] = machine
            
            logger.info("Created order state machine for %s", order_id)
            return machine
    
    def get_order(self, order_id: str) -> Optional[OrderStateMachine]:
        """Get order state machine by ID.
        
        Args:
            order_id: Order identifier
            
        Returns:
            OrderStateMachine or None if not found
        """
        with self._lock:
            return self._machines.get(order_id)
    
    def remove_order(self, order_id: str) -> bool:
        """Remove order state machine.
        
        Args:
            order_id: Order identifier
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if order_id in self._machines:
                del self._machines[order_id]
                logger.info("Removed order state machine for %s", order_id)
                return True
            return False
    
    def get_active_orders(self) -> List[OrderStateMachine]:
        """Get all active (non-terminal) orders.
        
        Returns:
            List of active OrderStateMachine instances
        """
        with self._lock:
            return [m for m in self._machines.values() if m.is_active()]
    
    def get_terminal_orders(self) -> List[OrderStateMachine]:
        """Get all terminal orders.
        
        Returns:
            List of terminal OrderStateMachine instances
        """
        with self._lock:
            return [m for m in self._machines.values() if m.is_terminal()]
    
    def get_orders_by_state(self, state: OrderState) -> List[OrderStateMachine]:
        """Get orders in a specific state.
        
        Args:
            state: OrderState to filter by
            
        Returns:
            List of OrderStateMachine instances in that state
        """
        with self._lock:
            return [m for m in self._machines.values() if m.get_state() == state]
    
    def get_statistics(self) -> Dict:
        """Get manager statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            total_orders = len(self._machines)
            active_orders = sum(1 for m in self._machines.values() if m.is_active())
            terminal_orders = total_orders - active_orders
            
            # Count by state
            state_counts = {}
            for state in OrderState:
                count = sum(1 for m in self._machines.values() if m.get_state() == state)
                state_counts[state.value] = count
            
            return {
                "total_orders": total_orders,
                "active_orders": active_orders,
                "terminal_orders": terminal_orders,
                "state_counts": state_counts
            }
    
    def cleanup_terminal_orders(self, max_age_seconds: int = 3600) -> int:
        """Remove old terminal orders.
        
        Args:
            max_age_seconds: Maximum age for terminal orders
            
        Returns:
            Number of orders removed
        """
        cutoff = datetime.utcnow().timestamp() - max_age_seconds
        removed = 0
        
        with self._lock:
            to_remove = []
            for order_id, machine in self._machines.items():
                if machine.is_terminal():
                    history = machine.history()
                    if history and history[-1].timestamp.timestamp() < cutoff:
                        to_remove.append(order_id)
            
            for order_id in to_remove:
                del self._machines[order_id]
                removed += 1
        
        if removed > 0:
            logger.info("Cleaned up %d terminal orders", removed)
        
        return removed
