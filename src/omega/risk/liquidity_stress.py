"""
Liquidity Stress Validator for V21 Institutional Grade.

Implements:
- Average Daily Volume (ADV) stress testing
- Liquidation period estimation (T-days to exit)
- Market impact cost estimation (Almgren-Chriss)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class LiquidityReport:
    """Detailed liquidity stress report."""
    is_safe: bool
    max_exit_days: float
    total_impact_bps: float
    at_risk_symbols: List[str]
    violation_message: str = ""


class LiquidityStressValidator:
    """
    Validates portfolio against liquidity constraints and market stress scenarios.

    Ensures positions can be exited without catastrophic market impact.
    """

    def __init__(
        self,
        max_adv_participation: float = 0.1,  # Max 10% of ADV per day
        max_exit_days: int = 3,              # Must exit full position within 3 days
        market_impact_coefficient: float = 0.2
    ):
        self.max_adv_participation = max_adv_participation
        self.max_exit_days = max_exit_days
        self.market_impact_coefficient = market_impact_coefficient

    def validate_liquidity(
        self,
        positions_qty: Dict[str, float],
        adv_data: Dict[str, float],
        volatility_data: Dict[str, float]
    ) -> LiquidityReport:
        """Perform liquidity stress validation."""
        at_risk = []
        max_days = 0.0
        total_impact_bps = 0.0

        for symbol, qty in positions_qty.items():
            adv = adv_data.get(symbol, 0.0)
            vol = volatility_data.get(symbol, 0.01)  # Default 1% vol

            if adv <= 0:
                at_risk.append(symbol)
                continue

            # Exit days = qty / (participation * adv)
            exit_days = qty / (self.max_adv_participation * adv)
            max_days = max(max_days, exit_days)

            # Market impact (Almgren-Chriss simplified)
            # Impact BPS = coeff * sigma * sqrt(qty / daily_vol)
            impact = self.market_impact_coefficient * vol * np.sqrt(qty / adv)
            total_impact_bps += impact * 10000

            if exit_days > self.max_exit_days:
                at_risk.append(symbol)

        is_safe = len(at_risk) == 0

        msg = "Liquidity profile: PASS" if is_safe else f"Liquidity profile: FAIL - {len(at_risk)} symbols illiquid."
        if not is_safe:
            msg += f" Worst symbol requires {max_days:.1f} days to exit."

        return LiquidityReport(
            is_safe=is_safe,
            max_exit_days=max_days,
            total_impact_bps=total_impact_bps / max(1, len(positions_qty)),
            at_risk_symbols=at_risk,
            violation_message=msg
        )
