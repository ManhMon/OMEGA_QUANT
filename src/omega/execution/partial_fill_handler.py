
from typing import List, Dict, Union

class PartialFillHandler:
    """
    Tracks and handles unfilled portions of orders.
    Implements logic for re-submission or cancellation.
    """

    def __init__(self):
        """
        Initializes the PartialFillHandler.
        """
        self.unfilled_orders = {} # symbol -> {original_qty, filled_qty, remaining_qty}

    def track_fill(self, symbol: str, original_qty: int, filled_qty: int):
        """
        Tracks a partial fill for a given symbol.

        Args:
            symbol: Stock symbol.
            original_qty: Original order quantity.
            filled_qty: Quantity that was successfully filled.
        """
        remaining_qty = original_qty - filled_qty
        if remaining_qty != 0:
            self.unfilled_orders[symbol] = {
                "original_qty": original_qty,
                "filled_qty": filled_qty,
                "remaining_qty": remaining_qty
            }
        elif symbol in self.unfilled_orders:
            del self.unfilled_orders[symbol]

    def get_resubmit_orders(self) -> List[Dict[str, Union[str, int, float]]]:
        """
        Generates re-submission orders for unfilled quantities.

        Returns:
            A list of new orders to be submitted.
        """
        resubmit_orders = []
        for symbol, data in self.unfilled_orders.items():
            if abs(data["remaining_qty"]) >= 100: # Min lot size check
                resubmit_orders.append({
                    "symbol": symbol,
                    "quantity": data["remaining_qty"],
                    "order_type": "MARKET", # Default to MARKET for re-submission
                    "time_in_force": "IOC" # Immediate or Cancel for faster execution
                })
        return resubmit_orders

    def cancel_remaining(self, symbol: str):
        """
        Cancels tracking for any remaining quantity of a given symbol.

        Args:
            symbol: Stock symbol.
        """
        if symbol in self.unfilled_orders:
            del self.unfilled_orders[symbol]

    def clear_all(self):
        """
        Clears all unfilled order tracking.
        """
        self.unfilled_orders = {}
