import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from omega.quant.execution.transaction_cost import VNTransactionCostModel, TransactionCostConfig


logger = logging.getLogger(__name__)

class PaperTradingEngine:
    """
    Virtual order simulation engine for Layer 08 Self-Evolving Engine.
    Simulates order execution with slippage and tracks P&L for Champion/Challenger models.
    """

    def __init__(self, log_dir: str = "logs", smart_router=None):
        self.log_dir = log_dir
        self.cost_model = VNTransactionCostModel(TransactionCostConfig())
        self.smart_router = smart_router
        self.virtual_orders_log_path = f"{self.log_dir}/virtual_orders.jsonl"
        
        # P&L tracking per portfolio (model_id)
        self.daily_pnl: Dict[str, float] = {}
        
        # Ensure log file exists or creates it
        import os
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def execute_virtual_order(self, order: Dict[str, Any], order_book_data: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a virtual order with slippage and logging. 
        Uses SmartRouter to simulate schedule, then executes each child order.
        
        Args:
            order: Dict containing symbol, side, size, price, model_id (champion/challenger), 
                   feature_ts, decision_ts
            order_book_data: Optional dict with adv_value_vnd, exchange_label, etc.
            
        Returns:
            List[Dict] containing execution results for each child order.
        """
        model_id = order.get('model_id', 'unknown')
        
        # Route order through SmartRouter if available
        child_orders = []
        if self.smart_router:
            # Map size to quantity for SmartRouter
            router_order = order.copy()
            if 'size' in router_order and 'quantity' not in router_order:
                router_order['quantity'] = router_order['size']
            child_orders = self.smart_router.route_order(router_order, algo="TWAP", duration_minutes=60)
            
            # Note: TWAP execution scheduling is deferred to the router. 
            # In paper trading, we currently simulate immediate fills for the slices 
            # but honor the slice sizing logic of the router. 
            # A future enhancement will honor the true schedule_time of each slice.
        else:
            # Execute as a single block if no router
            child_orders = [order]
            
        execution_results = []
        
        for child in child_orders:
            symbol = child.get('symbol', order.get('symbol'))
            # Get size from quantity (SmartRouter) or size (original)
            size = child.get('quantity', child.get('size', order.get('size', 0)))
            price = child.get('price', order.get('price'))
            side = child.get('side', order.get('side'))
            
            # PIT Compliance timestamps - Fail-closed validation
            if 'feature_ts' not in order or 'decision_ts' not in order:
                execution_status = "REJECTED_PIT_VIOLATION"
                executed_price = 0.0
                total_cost_vnd = 0.0
                feature_ts = order.get('feature_ts', 'MISSING')
                decision_ts = order.get('decision_ts', 'MISSING')
                execution_ts = datetime.now(timezone.utc).isoformat()
                cash_flow = 0.0
            else:
                feature_ts = order['feature_ts']
                decision_ts = order['decision_ts']
                execution_ts = datetime.now(timezone.utc).isoformat()
                
            # Check price bands (if blocked, execution fails)
            if order_book_data:
                ref_price = order_book_data.get('ref_price', price)
                is_suspended = order_book_data.get('is_suspended', False)
                adv_value_vnd = order_book_data.get('adv_value_vnd', 10e9)
                exchange_label = order_book_data.get('exchange_label')
            else:
                ref_price = price
                is_suspended = False
                adv_value_vnd = 10e9
                exchange_label = None

            is_blocked = self.cost_model.is_price_band_blocked(
                symbol=symbol,
                ref_price=ref_price,
                order_price=price,
                exchange_label=exchange_label,
                is_suspended=is_suspended
            )

            if 'feature_ts' not in order or 'decision_ts' not in order:
                pass # Handled above, execution_status is REJECTED_PIT_VIOLATION
            elif is_blocked:
                execution_status = "REJECTED_PRICE_BAND"
                executed_price = 0.0
                total_cost_vnd = 0.0
                cash_flow = 0.0
            else:
                execution_status = "FILLED"
                # Calculate slippage/costs
                cost_estimation = self.cost_model.estimate_cost(
                    symbol=symbol,
                    order_size=size,
                    price=price,
                    adv_value_vnd=adv_value_vnd,
                    side=side,
                    exchange_label=exchange_label
                )
                
                total_cost_bps = cost_estimation['total_cost_bps']
                
                # Apply slippage to executed price
                if side.lower() == 'buy':
                    executed_price = price * (1 + total_cost_bps / 10000.0)
                else:
                    executed_price = price * (1 - total_cost_bps / 10000.0)
                    
                executed_price = self.cost_model.round_to_tick(executed_price)
                total_cost_vnd = (total_cost_bps / 10000.0) * size * price
                
                # Update P&L (simplified for demonstration: just accumulating cash flow)
                cash_flow = -executed_price * size if side.lower() == 'buy' else executed_price * size
                
                if model_id not in self.daily_pnl:
                    self.daily_pnl[model_id] = 0.0
                
                self.daily_pnl[model_id] += cash_flow
    
            # Prepare log record
            notional = size * price
            log_record = {
                "execution_ts": execution_ts,
                "feature_ts": feature_ts,
                "decision_ts": decision_ts,
                "symbol": symbol,
                "side": side,
                "size": size,
                "quantity": size,
                "intended_price": price,
                "executed_price": executed_price,
                "notional": notional,
                "pnl": cash_flow,
                "execution_status": execution_status,
                "model_id": model_id,
                "total_cost_vnd": total_cost_vnd,
                "is_virtual": True
            }
            
            self._log_virtual_order(log_record)
            execution_results.append(log_record)
            
        return execution_results

    def _log_virtual_order(self, record: Dict[str, Any]):
        """Logs the virtual order to JSONL for Layer 07 to aggregate."""
        try:
            with open(self.virtual_orders_log_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
        except Exception as e:
            logger.error(f"Failed to log virtual order: {e}")

    def evaluate_shadow_mode(self, days_passed: int, min_smoke_days: int = 5, min_burn_in_days: int = 30) -> str:
        """
        Evaluate if a model can transition through shadow mode gates.
        
        Args:
            days_passed: Number of days the model has been in shadow mode.
            min_smoke_days: Minimum days for smoke test gate (default 5).
            min_burn_in_days: Minimum days for full burn-in gate (default 30).
            
        Returns:
            str: "BURN_IN_PASSED", "SMOKE_TEST_PASSED", or "IN_PROGRESS"
        """
        if days_passed >= min_burn_in_days:
            logger.info(f"Model passed full burn-in requirement ({days_passed}/{min_burn_in_days} days).")
            return "BURN_IN_PASSED"
        elif days_passed >= min_smoke_days:
            logger.info(f"Model passed smoke test requirement ({days_passed}/{min_smoke_days} days).")
            return "SMOKE_TEST_PASSED"
        else:
            logger.info(f"Model still in early shadow mode ({days_passed}/{min_smoke_days} days).")
            return "IN_PROGRESS"

    def get_daily_pnl(self, model_id: str) -> float:
        """Returns the accumulated daily P&L (cash flow) for a model."""
        return self.daily_pnl.get(model_id, 0.0)

    def reset_daily_pnl(self):
        """Resets daily P&L tracking (e.g., at end of day)."""
        self.daily_pnl = {}

