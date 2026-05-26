from __future__ import annotations

from typing import Any

from .types import MarketState


def apply_delisted_liquidations(
    state: MarketState,
    current_date: str,
    trades: list[dict],
    data_module: Any,
) -> MarketState:
    """Force-liquidate delisted positions using metadata final_price."""
    if data_module is None or not hasattr(data_module, "get_delisting_info"):
        return state

    positions = dict(state.positions)
    cash = state.cash

    for symbol, position in list(positions.items()):
        if abs(position) <= 1e-12:
            continue

        delisting_info = data_module.get_delisting_info(symbol)
        if not delisting_info:
            continue

        delist_date = str(delisting_info.get("delist_date", ""))
        if str(current_date) < delist_date:
            continue

        final_price = float(delisting_info.get("final_price", 0.0))
        qty = abs(position)
        cash += position * final_price
        positions.pop(symbol, None)
        trades.append(
            {
                "timestamp": current_date,
                "symbol": symbol,
                "side": "FORCED_LIQUIDATION",
                "qty": qty,
                "price": final_price,
                "reason": delisting_info.get("reason", "unknown"),
            }
        )

    return MarketState(
        timestamp=state.timestamp,
        cash=cash,
        positions=positions,
        pending_cash=state.pending_cash,
        pending_settlements=state.pending_settlements,
    )
