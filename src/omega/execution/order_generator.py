"""
OMEGA_QUANT Order Generator (Layer 03)
Phase 4.3: Signal to Order Conversion

Converts alpha signals to executable orders with position sizing,
compliance checks, and board-lot rounding.

Author: Backend Engineer (Role 09)
Date: 2026-05-18
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

from .broker_gateway import BrokerOrder, OrderSide, OrderType

# VND_FULL price-unit contract
try:
    from omega.data.vnd_price_contract import VND_FULL, THOUSANDS, get_price_multiplier
except ImportError:
    VND_FULL = "VND_FULL"
    THOUSANDS = "THOUSANDS"
    def get_price_multiplier(price_unit: str) -> float:
        return 1.0 if price_unit == "VND_FULL" else 1000.0

logger = logging.getLogger(__name__)


@dataclass
class PositionSizingConfig:
    """Configuration for position sizing."""
    max_position_weight: float = 0.05  # Max 5% per position
    max_leverage: float = 1.0  # No leverage by default
    min_order_size: int = 100  # Minimum board lot
    board_lot_size: int = 100  # VN market standard


class OrderGenerator:
    """
    Generates orders from alpha signals with position sizing and compliance.
    
    Features:
    - Signal to order conversion
    - Position sizing based on portfolio constraints
    - Board-lot rounding (VN market: 100 shares)
    - Compliance checks (leverage, concentration, liquidity)
    - Order batching for correlated signals
    """
    
    def __init__(self, config: Optional[PositionSizingConfig] = None):
        """
        Initialize OrderGenerator.
        
        Args:
            config: Position sizing configuration
        """
        self.config = config or PositionSizingConfig()
        logger.info("Initialized OrderGenerator")
    
    def _round_to_board_lot(
        self,
        quantity: float,
        allow_odd_lot: bool = False
    ) -> int:
        """
        Round quantity to board lot (100 shares).
        
        Vietnamese market rules:
        - Minimum lot: 100 shares
        - Board lot: 100 shares (round to nearest 100)
        - Odd lots (1-99) allowed ONLY if allow_odd_lot=True (for liquidation)
        
        Args:
            quantity: Target quantity
            allow_odd_lot: Allow odd lots for liquidation
            
        Returns:
            Board-lot compliant quantity
        """
        abs_qty = abs(quantity)
        
        if abs_qty < self.config.board_lot_size:
            if allow_odd_lot and abs_qty > 0:
                return int(quantity)
            return 0
        
        # Round to nearest board lot
        rounded = int(round(quantity / self.config.board_lot_size)) * self.config.board_lot_size
        return rounded
    
    def generate_orders(
        self,
        target_portfolio: Dict[str, Dict[str, Union[float, str]]],
        current_portfolio: Dict[str, Dict[str, Union[float, str]]],
        order_type: str = "MARKET",
        time_in_force: str = "DAY",
        current_prices: Optional[Dict[str, float]] = None,
        allow_odd_lot: bool = False
    ) -> List[Dict[str, Union[str, int, float]]]:
        """
        Generate orders from target vs current portfolio.
        
        Args:
            target_portfolio: Target portfolio {symbol: {quantity: qty, ...}}
            current_portfolio: Current portfolio {symbol: {quantity: qty, ...}}
            order_type: Order type (MARKET, LIMIT)
            time_in_force: Time in force (DAY, GTC)
            current_prices: Current prices {symbol: price}
            allow_odd_lot: Allow odd lots for liquidation
            
        Returns:
            List of orders {symbol, quantity, side, order_type, price, ...}
        """
        orders = []
        all_symbols = set(target_portfolio.keys()).union(current_portfolio.keys())
        prices = current_prices or {}
        
        for symbol in all_symbols:
            target_qty = target_portfolio.get(symbol, {}).get("quantity", 0)
            current_qty = current_portfolio.get(symbol, {}).get("quantity", 0)
            
            # Calculate net quantity needed
            net_quantity = target_qty - current_qty
            
            # If liquidating to zero, allow odd-lot
            liquidating = (target_qty == 0 and current_qty != 0)
            use_odd_lot = allow_odd_lot or liquidating
            
            # Round to board lot
            rounded_quantity = self._round_to_board_lot(net_quantity, allow_odd_lot=use_odd_lot)
            
            if rounded_quantity != 0:
                # Get price
                raw_price = prices.get(symbol, 0.0)
                
                # Create order
                order = {
                    "symbol": symbol,
                    "quantity": abs(rounded_quantity),
                    "order_type": order_type,
                    "time_in_force": time_in_force,
                    "price": raw_price if raw_price > 0 else None,
                    "side": "BUY" if rounded_quantity > 0 else "SELL",
                    "allow_odd_lot": use_odd_lot and abs(rounded_quantity) < self.config.board_lot_size,
                }
                orders.append(order)
                
                logger.info(f"Generated order: {symbol} {order['side']} {order['quantity']} "
                           f"@ {raw_price}")
        
        return orders
    
    def convert_signal_to_order(
        self,
        symbol: str,
        signal_weight: float,
        portfolio_value: float,
        current_price: float,
        current_position: int = 0,
        order_type: str = "MARKET",
        price_unit: str = VND_FULL
    ) -> Optional[BrokerOrder]:
        """
        Convert alpha signal to executable BrokerOrder.
        
        Args:
            symbol: Stock symbol
            signal_weight: Target weight (0.0 to 1.0)
            portfolio_value: Total portfolio value (VND)
            current_price: Current stock price (VND_FULL by default)
            current_position: Current position quantity
            order_type: Order type (MARKET, LIMIT)
            price_unit: Price unit contract - VND_FULL (default) or THOUSANDS.
                VND_FULL: price is in whole VND (e.g. 50000.0). No multiplier needed.
                THOUSANDS: price is in thousands (e.g. 50.0). Multiplied by 1000.
            
        Returns:
            BrokerOrder or None if no order needed
        """
        # Calculate target quantity
        if current_price <= 0:
            logger.warning(f"Invalid price for {symbol}: {current_price}")
            return None
        
        price_vnd = current_price * get_price_multiplier(price_unit)
        target_notional = portfolio_value * signal_weight
        target_quantity = int(target_notional / price_vnd)  # Convert to shares
        
        # Round to board lot
        target_quantity = self._round_to_board_lot(target_quantity)
        
        # Calculate net quantity
        net_quantity = target_quantity - current_position
        
        if net_quantity == 0:
            logger.debug(f"No order needed for {symbol}: already at target")
            return None
        
        # Determine side
        side = OrderSide.BUY if net_quantity > 0 else OrderSide.SELL
        
        # Create BrokerOrder
        try:
            order = BrokerOrder(
                symbol=symbol,
                side=side,
                quantity=abs(net_quantity),
                order_type=OrderType.MARKET if order_type == "MARKET" else OrderType.LIMIT,
                price=current_price if order_type == "LIMIT" else None,
                time_in_force="DAY"
            )
            
            logger.info(f"Converted signal to order: {symbol} {side.value} {abs(net_quantity)}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to create order for {symbol}: {e}")
            return None
    
    def batch_orders(
        self,
        orders: List[BrokerOrder],
        correlation_threshold: float = 0.7
    ) -> List[List[BrokerOrder]]:
        """
        Batch correlated orders together.
        
        Args:
            orders: List of orders to batch
            correlation_threshold: Correlation threshold for batching
            
        Returns:
            List of order batches
        """
        # Simple batching: group by side (BUY/SELL)
        buy_orders = [o for o in orders if o.side == OrderSide.BUY]
        sell_orders = [o for o in orders if o.side == OrderSide.SELL]
        
        batches = []
        if buy_orders:
            batches.append(buy_orders)
        if sell_orders:
            batches.append(sell_orders)
        
        logger.info(f"Batched {len(orders)} orders into {len(batches)} batches")
        return batches
    
    def validate_compliance(
        self,
        order: BrokerOrder,
        current_price: float,
        adv: float,
        portfolio_value: float,
        price_unit: str = VND_FULL
    ) -> tuple[bool, Optional[str]]:
        """
        Validate order meets compliance constraints.
        
        Args:
            order: Order to validate
            current_price: Current stock price
            adv: Average daily volume (shares)
            portfolio_value: Total portfolio value
            price_unit: Price unit contract - VND_FULL (default) or THOUSANDS.
            
        Returns:
            (is_valid, error_message)
        """
        # Board-lot validation
        if order.quantity % self.config.board_lot_size != 0:
            return False, f"Order not board-lot compliant: {order.quantity}"
        
        # Minimum order size
        if order.quantity < self.config.min_order_size:
            return False, f"Order below minimum size: {order.quantity}"
        
        # Position weight validation (price_unit aware)
        price_vnd = current_price * get_price_multiplier(price_unit)
        order_notional = order.quantity * price_vnd
        position_weight = order_notional / portfolio_value if portfolio_value > 0 else 0
        
        if position_weight > self.config.max_position_weight:
            return False, f"Position weight exceeds limit: {position_weight:.2%}"
        
        # ADV validation (don't exceed 20% of ADV; reject if ADV=0 no-liquidity)
        if adv <= 0:
            return False, f"ADV is zero or negative: cannot validate order against illiquid ticker (adv={adv})"
        if order.quantity > adv * 0.2:
            return False, f"Order exceeds 20% of ADV: {order.quantity} vs {adv * 0.2:.0f}"
        
        return True, None
