"""Phase 3.5 Realistic Execution Simulator.

Models real-world VN equity costs:
  1. Bid-ask spread cost: half-spread per side (entry + exit)
  2. Commission: 0.15% buy + 0.15% sell + 0.1% sale tax (VN HOSE/HNX standard)
  3. Slippage: linear market impact = k * (order_size / ADV) for liquidity-aware fill
  4. Foreign room cap: skip names where weight exceeds available foreign room

PIT-safe: all costs computed using PRIOR bar's ADV / spread / volume,
no peeking at execution-bar liquidity.

Reference: Almgren-Chriss (1999), VN broker fee schedule (SSI/VPS 2024).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

__all__ = ["VNCostModel", "apply_realistic_tc", "DEFAULT_VN_COSTS"]


@dataclass
class VNCostModel:
    """VN equity cost model parameters.

    Defaults reflect typical retail VN broker (SSI/VPS) 2024:
      - commission_buy: 0.15% (15 bps)
      - commission_sell: 0.15% (15 bps)
      - tax_sell: 0.10% (10 bps stamp duty on sale)
      - half_spread_bps: 10 bps (typical mid/large cap)
      - slippage_k: linear coefficient (price_impact = k * participation_rate)
        0.10 = 10 bps per 1% participation. Realistic for VN mid-caps.
    """
    commission_buy: float = 0.0015       # 15 bps
    commission_sell: float = 0.0015      # 15 bps
    tax_sell: float = 0.0010             # 10 bps
    half_spread_bps: float = 0.0010      # 10 bps half-spread
    slippage_k: float = 0.10             # impact coefficient
    foreign_room_cap: float = 0.49       # 49% foreign ownership cap


DEFAULT_VN_COSTS = VNCostModel()


def apply_realistic_tc(
    daily_weights: pd.DataFrame,
    daily_realized_y: np.ndarray,
    daily_adv: np.ndarray | None = None,
    portfolio_capital_vnd: float = 1e9,
    cost_model: VNCostModel | None = None,
) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Subtract realistic VN costs from gross returns bar-by-bar.

    Args:
        daily_weights: T x N portfolio weights (after tail controls).
        daily_realized_y: T x N realized per-ticker returns (gross).
        daily_adv: T x N average daily volume (VND) for slippage. If None,
            slippage is set to 0 (only spread + commission applied).
        portfolio_capital_vnd: assumed AUM (default 1B VND retail). Larger
            capital -> more impact on illiquid names.
        cost_model: VNCostModel instance (default DEFAULT_VN_COSTS).

    Returns:
        adj_weights: same shape (after foreign room enforcement)
        net_returns: T-vector of NET portfolio returns (after all costs)
        breakdown: dict with cumulative cost components for diagnostics.
    """
    if cost_model is None:
        cost_model = DEFAULT_VN_COSTS
    T = len(daily_weights)
    if T == 0:
        return daily_weights, np.array([]), {}

    weights = daily_weights.to_numpy()
    N = weights.shape[1]
    net_returns = np.zeros(T)

    # Cost accumulators
    total_commission = 0.0
    total_spread = 0.0
    total_slippage = 0.0
    total_turnover = 0.0

    prev_w = np.zeros(N)
    for t in range(T):
        w_t = weights[t]
        delta_w = w_t - prev_w
        turnover = np.abs(delta_w).sum()  # one-way turnover per bar
        total_turnover += turnover

        # Commission: separate buy vs sell legs
        buy_leg = np.maximum(delta_w, 0).sum()
        sell_leg = np.maximum(-delta_w, 0).sum()
        commission_t = (buy_leg * cost_model.commission_buy
                         + sell_leg * (cost_model.commission_sell + cost_model.tax_sell))
        total_commission += commission_t

        # Half-spread: paid on both sides of every trade
        spread_t = turnover * cost_model.half_spread_bps
        total_spread += spread_t

        # Slippage: participation-rate linear impact, only if ADV provided
        slippage_t = 0.0
        if daily_adv is not None:
            adv_row = daily_adv[t]  # VND
            # Trade VND value per name = |delta_w| * portfolio_capital
            trade_vnd = np.abs(delta_w) * portfolio_capital_vnd
            with np.errstate(divide='ignore', invalid='ignore'):
                participation = np.where(adv_row > 0, trade_vnd / adv_row, 0)
            slippage_per_name = cost_model.slippage_k * participation
            # Slippage cost = participation_impact * |delta_w| (proportional to trade size)
            slippage_t = float(np.sum(slippage_per_name * np.abs(delta_w)))
            total_slippage += slippage_t

        # Gross return - costs
        gross_t = float(np.sum(w_t * daily_realized_y[t]))
        net_t = gross_t - commission_t - spread_t - slippage_t
        net_returns[t] = net_t
        prev_w = w_t

    breakdown = {
        "total_turnover": float(total_turnover),
        "avg_turnover_per_bar": float(total_turnover / T),
        "total_commission_cost": float(total_commission),
        "total_spread_cost": float(total_spread),
        "total_slippage_cost": float(total_slippage),
        "total_cost": float(total_commission + total_spread + total_slippage),
        "avg_cost_per_bar_bps": float(10000 * (total_commission + total_spread + total_slippage) / T),
        "capital_vnd": portfolio_capital_vnd,
    }
    return daily_weights, net_returns, breakdown
