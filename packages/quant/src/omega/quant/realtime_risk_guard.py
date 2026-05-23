import logging
import numpy as np
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

logger = logging.getLogger(__name__)

class RiskVerdict(Enum):
    PASS = "PASS"
    FAIL_ADV = "FAIL_ADV"
    FAIL_CONCENTRATION = "FAIL_CONCENTRATION"
    FAIL_NOTIONAL = "FAIL_NOTIONAL"
    FAIL_CIRCUIT_BREAKER = "FAIL_CIRCUIT_BREAKER"
    FAIL_COST = "FAIL_COST"

@dataclass
class RiskLimits:
    max_adv_pct: float = 0.05  # Max 5% of 20-day ADV
    max_concentration_pct: float = 0.20  # Max 20% of total portfolio per symbol
    max_notional_currency: float = 500_000_000.0  # Max 500M VND per order
    circuit_breaker_drawdown: float = 0.10  # Stop if daily DD > 10%

class RealtimeRiskGuard:
    """
    Institutional Real-time Risk Guard (L4).
    Intercepts orders before execution to enforce strict risk limits.
    """
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self._exposure: Dict[str, float] = {}  # Symbol -> Notional exposure
        self._total_equity: float = 2_000_000_000.0  # 2B VND base
        self._daily_pnl: float = 0.0

    def set_portfolio_state(self, total_equity: float, exposures: Dict[str, float]):
        """Update current portfolio state for concentration checks."""
        self._total_equity = total_equity
        self._exposure = exposures

    def check_order(
        self,
        symbol: str,
        quantity: int,
        price: float,
        adv_20d: float,
        side: OrderSide = OrderSide.BUY,
        cost_estimate: Optional[float] = None,
        cost_limit: Optional[float] = None
    ) -> RiskVerdict:
        """
        Check if an order violates any risk limits.

        SELL orders reduce existing exposure and are exempt from notional,
        ADV, and concentration checks (they de-risk the portfolio).
        Only circuit-breaker and cost checks apply to sells.

        Args:
            symbol: Stock symbol
            quantity: Order quantity (always positive)
            price: Order price
            adv_20d: 20-day Average Daily Volume
            side: OrderSide.BUY (default) or OrderSide.SELL
            cost_estimate: Estimated transaction cost from TransactionCostOptimizer
            cost_limit: Maximum allowable transaction cost

        Returns:
            RiskVerdict: PASS or failure reason
        """
        notional = quantity * price

        # 0. Cost check (applies to both sides)
        if cost_estimate is not None and cost_limit is not None:
            if cost_estimate > cost_limit:
                logger.warning(
                    f"Risk Reject {symbol}: Cost {cost_estimate:,.0f} > Limit {cost_limit:,.0f}"
                )
                return RiskVerdict.FAIL_COST

        # 4. Circuit Breaker (Drawdown) — applies to both sides
        if self._daily_pnl / self._total_equity < -self.limits.circuit_breaker_drawdown:
            return RiskVerdict.FAIL_CIRCUIT_BREAKER

        # SELL reduces exposure — skip buy-side capacity checks
        if side == OrderSide.SELL:
            return RiskVerdict.PASS

        # 1. Max Notional Check (BUY only)
        if notional > self.limits.max_notional_currency:
            logger.warning(
                f"Risk Reject {symbol}: Notional {notional:,.0f} > Limit {self.limits.max_notional_currency:,.0f}"
            )
            return RiskVerdict.FAIL_NOTIONAL

        # 2. ADV Check (BUY only)
        if quantity > adv_20d * self.limits.max_adv_pct:
            limit_qty = adv_20d * self.limits.max_adv_pct
            logger.warning(f"Risk Reject {symbol}: Qty {quantity} > ADV Limit {limit_qty:.0f}")
            return RiskVerdict.FAIL_ADV

        # 3. Concentration Check (BUY only)
        current_notional = self._exposure.get(symbol, 0.0)
        new_total_notional = current_notional + notional
        concentration = new_total_notional / self._total_equity

        if concentration > self.limits.max_concentration_pct:
            logger.warning(
                f"Risk Reject {symbol}: Concentration {concentration:.1%} > Limit {self.limits.max_concentration_pct:.1%}"
            )
            return RiskVerdict.FAIL_CONCENTRATION

        return RiskVerdict.PASS

    def update_exposure(
        self,
        symbol: str,
        filled_quantity: int,
        fill_price: float,
        side: OrderSide = OrderSide.BUY,
    ) -> None:
        """Update exposure after order fill.

        BUY increases exposure; SELL decreases it (floored at 0).
        """
        notional = filled_quantity * fill_price
        current = self._exposure.get(symbol, 0.0)
        if side == OrderSide.SELL:
            self._exposure[symbol] = max(0.0, current - notional)
        else:
            self._exposure[symbol] = current + notional
