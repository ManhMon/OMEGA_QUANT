"""
Reconciliation & Partial Fill Handler.

Manages execution state across multiple trading days and reconciles
partial fills against the parent order.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class TradeExecutionStatus:
    symbol: str
    side: str
    target_quantity: int
    filled_quantity: int = 0
    average_fill_price: float = 0.0
    status: str = "PENDING"  # PENDING, PARTIAL, COMPLETED, CANCELLED
    fills: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def remaining_quantity(self) -> int:
        return self.target_quantity - self.filled_quantity


class ExecutionReconciler:
    """
    Handles reconciliation of child order fills against parent orders.
    Vital for multi-day VWAP/TWAP execution.
    """
    
    def __init__(self):
        self.active_orders: Dict[str, TradeExecutionStatus] = {}
        
    def register_parent_order(self, symbol: str, side: str, quantity: int) -> None:
        """Register a new parent order."""
        if quantity <= 0:
            return
            
        self.active_orders[symbol] = TradeExecutionStatus(
            symbol=symbol,
            side=side.upper(),
            target_quantity=quantity
        )
        logging.info(f"Registered parent order: {side} {quantity} {symbol}")

    def apply_fill(self, symbol: str, fill_qty: int, fill_price: float, timestamp: int) -> None:
        """
        Apply a child order fill to the parent order.
        """
        if symbol not in self.active_orders:
            logging.warning(f"Fill received for unknown order: {symbol}")
            return
            
        order = self.active_orders[symbol]
        
        if order.status in ["COMPLETED", "CANCELLED"]:
            logging.warning(f"Fill received for {order.status} order: {symbol}")
            return
            
        # Update average price
        total_value = (order.filled_quantity * order.average_fill_price) + (fill_qty * fill_price)
        new_total_qty = order.filled_quantity + fill_qty
        
        order.average_fill_price = total_value / new_total_qty
        order.filled_quantity = new_total_qty
        
        order.fills.append({
            "timestamp": timestamp,
            "quantity": fill_qty,
            "price": fill_price
        })
        
        if order.filled_quantity >= order.target_quantity:
            order.status = "COMPLETED"
            # Handle overfill if any (rare but happens in some venues)
            if order.filled_quantity > order.target_quantity:
                logging.error(f"OVERFILL DETECTED on {symbol}: {order.filled_quantity} > {order.target_quantity}")
        else:
            order.status = "PARTIAL"

    def handle_end_of_day(self) -> Dict[str, int]:
        """
        Run end of day reconciliation. 
        Returns dict of {symbol: remaining_qty} for carry-over to next day.
        """
        carry_over = {}
        for symbol, order in list(self.active_orders.items()):
            if order.status == "PARTIAL":
                rem = order.remaining_quantity
                # Only carry over if it meets board-lot requirements
                if rem >= 100:
                    carry_over[symbol] = rem
                else:
                    logging.info(f"Cancelling remainder of {symbol} (too small): {rem}")
                    order.status = "CANCELLED"
            
            # Clean up completed/cancelled
            if order.status in ["COMPLETED", "CANCELLED"]:
                del self.active_orders[symbol]
                
        return carry_over
