"""Smart execution market impact helpers.

Phase 4 contract:
- use only T-1 inputs supplied by caller
- nonlinear slippage = theta_1 * spread + theta_2 * volatility * sqrt(order_vol / daily_vol)
"""

from __future__ import annotations

from dataclasses import dataclass
import math


THETA_1 = 0.5
THETA_2 = 0.15


@dataclass(frozen=True)
class TMinusOneImpactSnapshot:
    spread: float
    volatility: float
    daily_volume: float
    as_of: object | None = None
    available_at: object | None = None


def calculate_nonlinear_slippage(
    order_volume: float,
    daily_volume: float,
    spread: float,
    volatility: float,
    *,
    theta_1: float = THETA_1,
    theta_2: float = THETA_2,
) -> float:
    """Return slippage as fraction, not bps."""
    if order_volume <= 0 or daily_volume <= 0:
        return float(theta_1 * max(spread, 0.0))
    participation = max(float(order_volume), 0.0) / float(daily_volume)
    return float(theta_1 * max(spread, 0.0) + theta_2 * max(volatility, 0.0) * math.sqrt(participation))


def calculate_nonlinear_slippage_bps(
    order_volume: float,
    snapshot: TMinusOneImpactSnapshot,
    *,
    theta_1: float = THETA_1,
    theta_2: float = THETA_2,
) -> float:
    return float(
        10000.0
        * calculate_nonlinear_slippage(
            order_volume=order_volume,
            daily_volume=snapshot.daily_volume,
            spread=snapshot.spread,
            volatility=snapshot.volatility,
            theta_1=theta_1,
            theta_2=theta_2,
        )
    )
