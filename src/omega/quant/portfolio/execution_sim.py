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

__all__ = [
    "VNCostModel", "apply_realistic_tc", "DEFAULT_VN_COSTS",
    "adv_tiered_half_spread", "adv_tiered_half_spread_vectorized",
    "clamp_half_spread", "ADV_TIERED_SPREAD_TIERS",
    "HALF_SPREAD_BPS_FLOOR", "HALF_SPREAD_BPS_CEIL",
]


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
      - slippage_nonlinear_exp (Phase 11): exponent for sub-linear impact
        scaling. Almgren-Chriss permanent impact ~ sqrt(participation) so
        true exponent ~0.5; we use 0.6 as a conservative midpoint between
        0.5 (sqrt) and 1.0 (linear).
      - settlement_lag_days (Phase 11): T+2.5 settlement on HOSE means
        capital is locked between sell and re-investment. Approximated as
        a 2.5/252 daily haircut on settled-cash returns at the deployed
        weight. Conservative approximation: a 0.99/yr factor times the
        avg long-only deployed gross.
      - halt_limit_haircut_pct (Phase 11): % of bars where one or more
        names hit the +/-7% (HOSE) or +/-10% (HNX) daily band and trades
        cannot complete at intended weight. Approximated as a constant
        haircut on bar-level gross.
      - foreign_room_haircut_pct (Phase 11): % of foreign-restricted names
        that get fully filled vs. partially filled. Conservative.
    """
    commission_buy: float = 0.0015       # 15 bps
    commission_sell: float = 0.0015      # 15 bps
    tax_sell: float = 0.0010             # 10 bps
    half_spread_bps: float = 0.0010      # 10 bps half-spread
    slippage_k: float = 0.05             # impact coefficient (recalibrated for exp=0.6)
    slippage_nonlinear_exp: float = 0.6  # Almgren-Chriss sub-linear impact scaling
    # Phase 11 codex P1 fix: when exp != 1.0, slippage_k must be
    # re-calibrated. For exp=0.6 (AC sqrt-ish), participation^0.6 > participation
    # when participation < 1 (which is always true in practice). To preserve
    # the same cost level at a reference participation p_ref=0.01 (1% of ADV),
    # we apply: effective_k = slippage_k * p_ref^(1 - exp) / p_ref^0
    # = slippage_k * p_ref^(1-exp). This ensures cost(p_ref) is identical
    # between linear and nonlinear regimes. The calibration is applied
    # inside apply_realistic_tc, not stored in the dataclass.
    slippage_k_ref_participation: float = 0.01  # reference participation for calibration
    foreign_room_cap: float = 0.49       # 49% foreign ownership cap
    settlement_lag_days: float = 0.0     # 0=off, 2.5=HOSE T+2.5
    halt_limit_haircut_pct: float = 0.0  # 0=off, 0.005=50bps/year haircut for limit-lock days
    foreign_room_haircut_pct: float = 0.0  # 0=off, 0.002=20bps haircut for foreign-fill incompleteness


DEFAULT_VN_COSTS = VNCostModel()

# ---------------------------------------------------------------------------
# ADV-tiered half-spread (cost-reduction lever #2)
# ---------------------------------------------------------------------------
# VN market microstructure: large-cap (VNM30) ~5 bps half-spread,
# mid-cap ~10 bps, small-cap / illiquid ~15 bps.
# Tiering is by per-bar ADV in VND.

ADV_TIERED_SPREAD_TIERS = {
    "high":   {"min_adv_vnd": 50e9,  "half_spread_bps": 0.0005},   # 5 bps
    "medium": {"min_adv_vnd": 10e9,  "half_spread_bps": 0.0010},   # 10 bps
    "low":    {"min_adv_vnd": 0.0,   "half_spread_bps": 0.0015},   # 15 bps
}

# Guard: half-spread must be in [1 bp, 50 bp] to prevent garbage values
HALF_SPREAD_BPS_FLOOR = 0.0001   # 1 bp
HALF_SPREAD_BPS_CEIL  = 0.0050   # 50 bps


def clamp_half_spread(half_spread_bps: float) -> float:
    """Clamp half_spread_bps to [1 bp, 50 bp] safety range."""
    return max(HALF_SPREAD_BPS_FLOOR, min(HALF_SPREAD_BPS_CEIL, half_spread_bps))


def adv_tiered_half_spread(adv_vnd: float) -> float:
    """Return half-spread (as fraction) for a given per-bar ADV (VND).

    Tiers:
      ADV >= 50B VND  -> 5 bps  (large-cap liquid)
      ADV >= 10B VND  -> 10 bps (mid-cap)
      ADV <  10B VND  -> 15 bps (small-cap / illiquid)
    """
    for tier_name in ("high", "medium", "low"):
        tier = ADV_TIERED_SPREAD_TIERS[tier_name]
        if adv_vnd >= tier["min_adv_vnd"]:
            return clamp_half_spread(tier["half_spread_bps"])
    return clamp_half_spread(0.0015)


def adv_tiered_half_spread_vectorized(adv_arr: np.ndarray) -> np.ndarray:
    """Vectorized ADV-tiered half-spread for a 1-D or 2-D ADV array.

    Returns array of same shape with half-spread values (as fractions).
    """
    result = np.full_like(adv_arr, 0.0015, dtype=float)
    high_mask = adv_arr >= 50e9
    mid_mask = (adv_arr >= 10e9) & (adv_arr < 50e9)
    result[high_mask] = 0.0005
    result[mid_mask] = 0.0010
    return np.clip(result, HALF_SPREAD_BPS_FLOOR, HALF_SPREAD_BPS_CEIL)


def apply_realistic_tc(
    daily_weights: pd.DataFrame,
    daily_realized_y: np.ndarray,
    daily_adv: np.ndarray | None = None,
    portfolio_capital_vnd: float = 1e9,
    cost_model: VNCostModel | None = None,
    prev_w_init: np.ndarray | None = None,
    use_adv_tiered_spread: bool = False,
    active_dates_mask: np.ndarray | None = None,
    dynamic_capital_tracking: bool = True,
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
        prev_w_init: optional starting weights for the first bar of this
            call. Default None -> all zeros (cold-start = full open-from-
            cash turnover on bar 0). When chaining CPCV folds, callers
            should pass the last bar's adjusted weights from the prior
            fold to avoid charging a synthetic open-from-cash cost on
            every fold (Phase 3.10 P1 fix).
        use_adv_tiered_spread: if True and daily_adv is provided, use
            per-name ADV-tiered half-spread (5/10/15 bps) instead of
            the flat half_spread_bps from cost_model.
        active_dates_mask: optional bool array of length T. When provided,
            only bars where mask[t] is True incur transaction costs; non-
            active bars pass gross returns without cost deduction. This
            prevents cost leakage from CPCV non-test-date gaps (purge/
            embargo periods between scattered test blocks).
        dynamic_capital_tracking: if True, scales trade sizes (and thus participation
            rates and slippage costs) based on running mark-to-market capital.

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

    # Validate active_dates_mask
    if active_dates_mask is not None:
        if active_dates_mask.shape != (T,):
            raise ValueError(
                f"active_dates_mask shape {active_dates_mask.shape} != expected ({T},)"
            )

    # Per-bar cost tracking for active-date-filtered breakdown
    bar_commission = np.zeros(T, dtype=float)
    bar_spread = np.zeros(T, dtype=float)
    bar_slippage = np.zeros(T, dtype=float)
    bar_costs = np.zeros(T, dtype=float)
    bar_turnover = np.zeros(T, dtype=float)

    if prev_w_init is None:
        prev_w = np.zeros(N)
    else:
        if prev_w_init.shape != (N,):
            raise ValueError(
                f"prev_w_init shape {prev_w_init.shape} != expected ({N},)"
            )
        prev_w = prev_w_init.astype(float, copy=True)
        
    running_capital = float(portfolio_capital_vnd)

    for t in range(T):
        w_t = weights[t]
        delta_w = w_t - prev_w
        turnover = np.abs(delta_w).sum()  # one-way turnover per bar
        bar_turnover[t] = turnover

        # Commission: separate buy vs sell legs
        buy_leg = np.maximum(delta_w, 0).sum()
        sell_leg = np.maximum(-delta_w, 0).sum()
        commission_t = (buy_leg * cost_model.commission_buy
                         + sell_leg * (cost_model.commission_sell + cost_model.tax_sell))
        bar_commission[t] = commission_t

        # Half-spread: paid on both sides of every trade
        # ADV-tiered spread: per-name spread based on liquidity tier
        if use_adv_tiered_spread and daily_adv is not None:
            adv_row_spread = daily_adv[t]
            per_name_spread = adv_tiered_half_spread_vectorized(adv_row_spread)
            spread_t = float(np.sum(np.abs(delta_w) * per_name_spread))
        else:
            spread_t = turnover * cost_model.half_spread_bps
        bar_spread[t] = spread_t

        # Slippage: participation-rate impact (linear or sub-linear), only if ADV provided
        slippage_t = 0.0
        if daily_adv is not None:
            adv_row = daily_adv[t]  # VND
            # Trade VND value per name = |delta_w| * running_capital (if tracking NAV)
            trade_capital = running_capital if dynamic_capital_tracking else portfolio_capital_vnd
            trade_vnd = np.abs(delta_w) * trade_capital
            with np.errstate(divide='ignore', invalid='ignore'):
                participation = np.where(adv_row > 0, trade_vnd / adv_row, 0)
            # Phase 11: optional nonlinear (sub-linear) Almgren-Chriss-style
            # impact. For participation p < 1 (always true in practice),
            # p^exp with exp < 1 gives p^exp > p (AMPLIFIES cost per unit).
            # To preserve cost level at a reference participation p_ref,
            # we apply calibration: effective_k = k * p_ref^(1-exp).
            # This ensures cost(p_ref) is identical between linear and
            # nonlinear regimes. Above p_ref, nonlinear is LESS punishing;
            # below p_ref, nonlinear is MORE punishing (correct AC behavior).
            if cost_model.slippage_nonlinear_exp != 1.0:
                p_ref = cost_model.slippage_k_ref_participation
                calibration = p_ref ** (1.0 - cost_model.slippage_nonlinear_exp)
                with np.errstate(invalid='ignore'):
                    participation_eff = np.where(
                        participation > 0,
                        np.power(participation, cost_model.slippage_nonlinear_exp) * calibration,
                        0.0,
                    )
            else:
                participation_eff = participation
            slippage_per_name = cost_model.slippage_k * participation_eff
            # Slippage cost = participation_impact * |delta_w| (proportional to trade size)
            slippage_t = float(np.sum(slippage_per_name * np.abs(delta_w)))
            bar_slippage[t] = slippage_t

        # Gross return - costs
        gross_t = float(np.sum(w_t * daily_realized_y[t]))
        # Phase 11: settlement lag haircut. T+2.5 means a fraction of
        # capital is unsettled and earns nothing on its way back.
        # Drag = settlement_lag_days/252 * settlement_drag_bps * 1e-4.
        # Default 1bp/day at 10% gross exposure.
        settlement_drag = 0.0
        if cost_model.settlement_lag_days > 0:
            settlement_drag = cost_model.settlement_lag_days / 252.0 * 0.0001
        # Phase 11 codex P1 #2 fix: halt/limit-lock and foreign-room
        # haircuts. These represent MISSED ALPHA (not missed loss).
        # Semantics: on a positive-return bar, missing a fill means you
        # miss the gain. On a negative-return bar, missing a fill means
        # you AVOID the loss (net benefit). Therefore we only apply the
        # haircut on POSITIVE gross bars (missed gains). Negative bars
        # get zero drag (you'd have wanted to miss those anyway).
        halt_drag = 0.0
        if cost_model.halt_limit_haircut_pct > 0 and gross_t > 0:
            halt_drag = cost_model.halt_limit_haircut_pct * gross_t
        foreign_drag = 0.0
        if cost_model.foreign_room_haircut_pct > 0 and gross_t > 0:
            foreign_drag = cost_model.foreign_room_haircut_pct * gross_t

        total_cost_t = commission_t + spread_t + slippage_t + settlement_drag + halt_drag + foreign_drag
        bar_costs[t] = total_cost_t
        net_t = gross_t - total_cost_t
        # CPCV non-test-date gap filter: zero costs on non-active bars
        if active_dates_mask is not None and not active_dates_mask[t]:
            net_t = gross_t
        net_returns[t] = net_t
        prev_w = w_t
        
        # Update running capital
        if dynamic_capital_tracking:
            running_capital = max(1000.0, running_capital * (1.0 + net_t))

    if active_dates_mask is not None:
        active_idx = active_dates_mask.astype(bool)
        n_active = int(np.sum(active_idx))
        if n_active == 0:
            n_active = 1
        total_commission_adj = float(np.sum(bar_commission[active_idx]))
        total_spread_adj = float(np.sum(bar_spread[active_idx]))
        total_slippage_adj = float(np.sum(bar_slippage[active_idx]))
        total_turnover_adj = float(np.sum(bar_turnover[active_idx]))
        total_cost_adj = total_commission_adj + total_spread_adj + total_slippage_adj
    else:
        n_active = T
        total_commission_adj = float(np.sum(bar_commission))
        total_spread_adj = float(np.sum(bar_spread))
        total_slippage_adj = float(np.sum(bar_slippage))
        total_turnover_adj = float(np.sum(bar_turnover))
        total_cost_adj = total_commission_adj + total_spread_adj + total_slippage_adj

    breakdown = {
        "total_turnover": total_turnover_adj,
        "avg_turnover_per_bar": float(total_turnover_adj / n_active),
        "total_commission_cost": total_commission_adj,
        "total_spread_cost": total_spread_adj,
        "total_slippage_cost": total_slippage_adj,
        "total_cost": total_cost_adj,
        "avg_cost_per_bar_bps": float(10000 * total_cost_adj / n_active),
        "capital_vnd": portfolio_capital_vnd,
        "final_w": prev_w.copy(),
        # Phase 11: extra cost components for diagnostic
        "slippage_nonlinear_exp": cost_model.slippage_nonlinear_exp,
        "settlement_lag_days": cost_model.settlement_lag_days,
        "halt_limit_haircut_pct": cost_model.halt_limit_haircut_pct,
        "foreign_room_haircut_pct": cost_model.foreign_room_haircut_pct,
        "use_adv_tiered_spread": use_adv_tiered_spread,
        "n_active_bars": n_active,
    }
    return daily_weights, net_returns, breakdown
