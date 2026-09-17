from __future__ import annotations

from typing import Callable


def build_price_ladder(
    last_close: float,
    bands: dict[float, tuple[float, float]],
    tick_fn: Callable[[float], float],
    limit_fn: Callable[[float], tuple[float, float]],
) -> dict:
    floor, ceiling = limit_fn(last_close)
    rungs = []
    previous = 0.0
    degenerate = False
    point_price = min(max(tick_fn(last_close), floor), ceiling)
    for coverage in sorted(bands):
        ret_lo, ret_hi = bands[coverage]
        price_low = min(max(tick_fn(last_close * (1.0 + ret_lo)), floor), ceiling)
        price_high = min(max(tick_fn(last_close * (1.0 + ret_hi)), floor), ceiling)
        if price_low > price_high:
            price_low, price_high = price_high, price_low
            degenerate = True
        if price_low == price_high:
            degenerate = True
        if not (price_low <= point_price <= price_high):
            degenerate = True
            point_price = min(max(point_price, price_low), price_high)
        rungs.append(
            {
                "coverage": coverage,
                "marginal_prob": coverage - previous,
                "price_low": price_low,
                "price_high": price_high,
            }
        )
        previous = coverage
    return {
        "last_close": last_close,
        "floor": floor,
        "ceiling": ceiling,
        "point_price": point_price,
        "rungs": rungs,
        "degenerate": degenerate,
    }
