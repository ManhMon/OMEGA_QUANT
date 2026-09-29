from typing import List, Dict, Union, Optional
import time

from .order_book_analyzer import OrderBookAnalyzer
from .microstructure_router import MicrostructureRouter
from .order_generator import OrderGenerator


class SmartRouter:
    """Selects the optimal execution schedule for orders (TWAP/VWAP).

    Supports a microstructure-aware mode that adapts slicing speed based on
    contemporaneous Order Book Imbalance (OBI) pressure.
    
    Phase 3.3.1 Wiring:
        - Accepts approved portfolio from IndividualRiskGuard (Layer 04)
        - Generates orders with board-lot enforcement (100 shares)
        - Routes orders using TWAP/VWAP algorithms
        - Enforces T+2.5 settlement awareness
    """

    def __init__(self, use_microstructure: bool = True):
        """Initializes the SmartRouter.

        Args:
            use_microstructure: When True, route orders via MicrostructureRouter.
        """
        self.queue: List[Dict[str, Union[str, int, float]]] = []
        self.schedule: List[Dict[str, Union[str, int, float]]] = []
        self.use_microstructure = use_microstructure
        self._micro_router = MicrostructureRouter()
        self._order_generator = OrderGenerator()

    def route_order(
        self,
        order: Dict[str, Union[str, int, float]],
        algo: str = "TWAP",
        duration_minutes: int = 60,
        use_microstructure: Optional[bool] = None,
        orderbook_analyzer: Optional[OrderBookAnalyzer] = None,
    ) -> List[Dict[str, Union[str, int, float]]]:
        """Routes an order using a specified algorithm (TWAP/VWAP).

        Args:
            order: The order dictionary to route.
            algo: The execution algorithm ("TWAP" or "VWAP").
            duration_minutes: Base duration for execution in minutes.
            use_microstructure: Overrides instance-level setting if provided.
            orderbook_analyzer: Optional analyzer instance used in microstructure mode.

        Returns:
            A list of child orders representing the execution schedule.
        """
        self.queue.append(order)

        if duration_minutes <= 0:
            raise ValueError(f"duration_minutes must be positive, got {duration_minutes}")

        micro = self.use_microstructure if use_microstructure is None else use_microstructure
        if micro:
            analyzer = orderbook_analyzer or OrderBookAnalyzer()
            child_orders = self._micro_router.route_order(
                order=order,
                execution_algo=algo,
                duration_minutes=duration_minutes,
                orderbook_analyzer=analyzer,
            )
            now = time.time()
            for child in child_orders:
                if "scheduled_time" not in child and "time_offset" in child:
                    child["scheduled_time"] = now + float(child["time_offset"]) * 60
        else:
            if algo == "TWAP":
                child_orders = self._generate_twap_schedule(order, duration_minutes)
            elif algo == "VWAP":
                child_orders = self._generate_vwap_schedule(order, duration_minutes)
            else:
                raise ValueError(f"Unsupported algorithm: {algo}")

        self.schedule.extend(child_orders)
        return child_orders

    def _generate_twap_schedule(self, order: Dict[str, Union[str, int, float]], duration_minutes: int) -> List[Dict[str, Union[str, int, float]]]:
        """
        Generates a TWAP (Time-Weighted Average Price) schedule for an order.
        Divides the total quantity into equal slices over the given duration.

        Args:
            order: The order dictionary.
            duration_minutes: Execution duration in minutes.

        Returns:
            A list of child orders for TWAP execution.
        """
        quantity = int(order["quantity"])
        if duration_minutes <= 0:
            raise ValueError(f"duration_minutes must be positive, got {duration_minutes}")
        slices = duration_minutes // 5  # Example: 1 slice every 5 minutes
        if slices <= 0:
            slices = 1

        child_orders: List[Dict[str, Union[str, int, float]]] = []
        start_time = time.time()

        abs_quantity = abs(quantity)
        sign = 1 if quantity >= 0 else -1
        board_lots = abs_quantity // 100
        odd_qty = abs_quantity % 100

        base_lots, remainder = divmod(board_lots, slices)
        for i in range(slices):
            qty = sign * (base_lots + (i < remainder)) * 100

            if qty == 0:
                continue

            child_order = order.copy()
            child_order["quantity"] = qty
            child_order["scheduled_time"] = start_time + (i * 5 * 60) # 5 minutes interval
            child_orders.append(child_order)

        if odd_qty > 0:
            odd_child = order.copy()
            odd_child["quantity"] = sign * odd_qty
            odd_child["scheduled_time"] = min(
                start_time + duration_minutes * 60,
                start_time + (len(child_orders) * 5 * 60),
            )
            child_orders.append(odd_child)

        return child_orders

    def _generate_vwap_schedule(self, order: Dict[str, Union[str, int, float]], duration_minutes: int, volume_profile: List[float] = None) -> List[Dict[str, Union[str, int, float]]]:
        """
        Generates a VWAP (Volume-Weighted Average Price) schedule.
        Uses historical volume profile to allocate larger slices during high-volume periods.
        
        If no volume_profile provided, uses default U-shape profile (more volume at open/close).

        Args:
            order: The order dictionary.
            duration_minutes: Execution duration in minutes.
            volume_profile: Optional list of relative volume weights per slice.

        Returns:
            A list of child orders for VWAP execution.
        """
        quantity = int(order["quantity"])
        if duration_minutes <= 0:
            raise ValueError(f"duration_minutes must be positive, got {duration_minutes}")
        slices = duration_minutes // 5  # 1 slice every 5 minutes
        if slices <= 0:
            slices = 1

        # Default volume profile: U-shape (more volume at open/close)
        if volume_profile is None:
            # Generate U-shaped profile: higher at edges, lower in middle
            t = list(range(slices))
            # Parabolic U-shape; single-slice orders get all volume in one child.
            if slices == 1:
                profile = [1.0]
            else:
                profile = [1.0 - 0.6 * ((2 * ti / (slices - 1) - 1) ** 2) for ti in t]
            volume_profile = [max(0.1, p) for p in profile]  # Floor at 10%

        # Normalize profile
        if any(weight < 0 for weight in volume_profile):
            raise ValueError("VWAP volume profile weights must be non-negative")
        total_profile = sum(volume_profile)
        if total_profile <= 0:
            raise ValueError("VWAP volume profile must have positive sum")
        volume_profile = [vp / total_profile for vp in volume_profile]

        # Allocate quantity according to profile
        child_orders: List[Dict[str, Union[str, int, float]]] = []
        start_time = time.time()
        remaining_qty = quantity

        for i in range(min(slices, len(volume_profile))):
            allocated_qty = int(quantity * volume_profile[i])
            # Round to board lot
            allocated_qty = int(round(allocated_qty / 100) * 100)
            if quantity >= 0:
                allocated_qty = max(0, min(allocated_qty, remaining_qty))
            else:
                allocated_qty = min(0, max(allocated_qty, remaining_qty))

            if i == min(slices, len(volume_profile)) - 1:
                # Last slice takes remainder
                allocated_qty = remaining_qty

            if allocated_qty == 0:
                continue
                
            child_order = order.copy()
            child_order["quantity"] = allocated_qty
            child_order["scheduled_time"] = start_time + (i * 5 * 60)
            child_orders.append(child_order)
            remaining_qty -= allocated_qty

        return child_orders

    def process_queue(self):
        """
        Processes the order queue according to the schedule.
        In a real system, this would send orders to the exchange.
        """
        current_time = time.time()
        executable_orders = []
        remaining_schedule = []

        for child_order in self.schedule:
            if "scheduled_time" not in child_order and "time_offset" in child_order:
                child_order["scheduled_time"] = current_time + float(child_order["time_offset"]) * 60
            scheduled_time = float(child_order.get("scheduled_time", 0))
            if current_time >= scheduled_time:
                executable_orders.append(child_order)
            else:
                remaining_schedule.append(child_order)

        self.schedule = remaining_schedule
        return executable_orders

    def generate_orders_from_risk_guard_result(
        self,
        approved_weights: Dict[str, float],
        current_prices: Dict[str, float],
        total_capital: float,
        current_portfolio: Optional[Dict[str, Dict[str, Union[float, str]]]] = None
    ) -> List[Dict[str, Union[str, int, float]]]:
        """
        Generate orders from IndividualRiskGuard approved weights.
        
        Phase 3.3.1 Wiring: Connects IndividualRiskGuard (Layer 04) to SmartRouter (Layer 03).
        
        Args:
            approved_weights: Dictionary mapping ticker -> weight (from IndividualRiskGuard)
            current_prices: Dictionary mapping ticker -> price (T-1 lagged)
            total_capital: Total capital in VND
            current_portfolio: Current portfolio holdings (optional)
            
        Returns:
            List of orders with board-lot enforcement (100 shares)
            
        Notes:
            - Board-lot: 100 shares (VN market rule)
            - T+2.5 settlement: Orders are aware of settlement cycle
            - PIT compliant: Uses T-1 prices from data provider
        """
        if not approved_weights:
            return []
        
        # Build target portfolio from approved weights
        target_portfolio = {}
        for ticker, weight in approved_weights.items():
            price = current_prices.get(ticker, 0.0)
            if price <= 0:
                continue
            
            # Compute target notional and quantity
            target_notional = weight * total_capital
            target_quantity = int(target_notional / price)
            
            # Round to board lot (100 shares)
            target_quantity = self._order_generator._round_to_board_lot(target_quantity)
            
            if target_quantity > 0:
                target_portfolio[ticker] = {
                    'quantity': target_quantity,
                    'weight': weight
                }
        
        # Use current portfolio or empty dict
        current_portfolio = current_portfolio or {}
        
        # Generate orders using OrderGenerator
        orders = self._order_generator.generate_orders(
            target_portfolio=target_portfolio,
            current_portfolio=current_portfolio,
            order_type='MARKET',
            time_in_force='DAY',
            current_prices=current_prices,
            allow_odd_lot=False  # Enforce board-lot 100
        )
        
        return orders
    
    def route_orders_from_risk_guard(
        self,
        approved_weights: Dict[str, float],
        current_prices: Dict[str, float],
        total_capital: float,
        current_portfolio: Optional[Dict[str, Dict[str, Union[float, str]]]] = None,
        algo: str = "TWAP",
        duration_minutes: int = 60,
        use_microstructure: Optional[bool] = None,
        orderbook_analyzer: Optional[OrderBookAnalyzer] = None
    ) -> List[Dict[str, Union[str, int, float]]]:
        """
        Complete wiring: Generate and route orders from IndividualRiskGuard result.
        
        Phase 3.3.1 Wiring: Full pipeline from Layer 04 (Risk) to Layer 03 (Execution).
        
        Args:
            approved_weights: Dictionary mapping ticker -> weight (from IndividualRiskGuard)
            current_prices: Dictionary mapping ticker -> price (T-1 lagged)
            total_capital: Total capital in VND
            current_portfolio: Current portfolio holdings (optional)
            algo: Execution algorithm ("TWAP" or "VWAP")
            duration_minutes: Execution duration in minutes
            use_microstructure: Override instance-level microstructure setting
            orderbook_analyzer: Optional OrderBookAnalyzer for microstructure routing
            
        Returns:
            List of child orders (execution schedule)
            
        Notes:
            - Board-lot: 100 shares enforced
            - T+2.5 settlement: Aware of settlement cycle
            - PIT compliant: Uses T-1 data
        """
        # Step 1: Generate orders from approved weights
        orders = self.generate_orders_from_risk_guard_result(
            approved_weights=approved_weights,
            current_prices=current_prices,
            total_capital=total_capital,
            current_portfolio=current_portfolio
        )
        
        if not orders:
            return []
        
        # Step 2: Route each order using specified algorithm
        all_child_orders = []
        
        for order in orders:
            child_orders = self.route_order(
                order=order,
                algo=algo,
                duration_minutes=duration_minutes,
                use_microstructure=use_microstructure,
                orderbook_analyzer=orderbook_analyzer
            )
            all_child_orders.extend(child_orders)
        
        return all_child_orders
