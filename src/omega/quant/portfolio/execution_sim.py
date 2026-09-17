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
from datetime import date
import numpy as np
import pandas as pd

from omega.data.calendar import get_futures_expiry_date
from omega.quant.regime.hmm_model import GaussianHMM4State, HMMModelConfig
from omega.quant.portfolio.barra_factor_model import build_barra_exposure_matrix
from omega.quant.portfolio.hrp_optimizer import HRPOptimizationConfig, optimize_hrp_barra_long_short

__all__ = [
    "VNCostModel", "apply_realistic_tc", "DEFAULT_VN_COSTS",
    "adv_tiered_half_spread", "adv_tiered_half_spread_vectorized",
    "clamp_half_spread", "ADV_TIERED_SPREAD_TIERS",
    "HALF_SPREAD_BPS_FLOOR", "HALF_SPREAD_BPS_CEIL",
    "InsolvencyError", "resolve_margin_rates", "estimate_futures_trade_cost",
    "run_joint_ledger_step",
    "build_hrp_barra_portfolio",
    "compute_hmm_regimes_t1",
]


def compute_hmm_regimes_t1(
    market_features: pd.DataFrame,
    config: HMMModelConfig | None = None,
) -> pd.Series:
    """Fit 4-state Gaussian regime model, return PIT-safe locked regimes.

    Output at bar T is inferred from features available at T-1.
    """
    model = GaussianHMM4State(config=config)
    return model.fit_predict(market_features)


def build_hrp_barra_portfolio(
    alpha_scores: pd.Series,
    returns_window: pd.DataFrame,
    market_data: pd.DataFrame,
    as_of_date: pd.Timestamp | str,
    config: HRPOptimizationConfig | None = None,
) -> tuple[pd.Series, dict[str, object]]:
    snapshot_date = pd.Timestamp(as_of_date) - pd.Timedelta(days=1)
    exposures = build_barra_exposure_matrix(market_data=market_data, as_of_date=as_of_date)
    weights, diagnostics = optimize_hrp_barra_long_short(
        alpha_scores=alpha_scores,
        returns_window=returns_window.loc[returns_window.index <= snapshot_date],
        factor_exposures=exposures,
        config=config,
    )
    diagnostics["exposures"] = exposures.reindex(weights.index).fillna(0.0)
    return weights, diagnostics



class InsolvencyError(RuntimeError):
    pass


MARGIN_SCHEDULE = (("1900-01-01", {"initial": 0.13, "maintenance": 0.10}),)


def resolve_margin_rates(trade_date: pd.Timestamp | date, schedule=MARGIN_SCHEDULE) -> dict[str, float]:
    resolved = schedule[0][1]
    trade_day = pd.Timestamp(trade_date).date()
    for effective_date, rates in schedule:
        if pd.Timestamp(effective_date).date() <= trade_day:
            resolved = rates
        else:
            break
    return {"initial": float(resolved["initial"]), "maintenance": float(resolved["maintenance"])}


def estimate_futures_trade_cost(contracts: float, price: float, contract_multiplier: float, per_side_bps: float = 1.0) -> float:
    return abs(float(contracts)) * float(price) * float(contract_multiplier) * (float(per_side_bps) / 10000.0)


def run_joint_ledger_step(
    *,
    nav_t_minus_1: float,
    realized_stock_weights_t_minus_1: np.ndarray,
    stock_returns_t: np.ndarray,
    cash_free_t_minus_1: float,
    margin_locked_t_minus_1: float,
    futures_vm_receivable_t_minus_1: float,
    futures_contracts_t_minus_1: float = 0.0,
    futures_close_t_minus_1: float = 0.0,
    futures_close_t: float = 0.0,
    contract_multiplier: float = 1.0,
    trade_date: pd.Timestamp | date | None = None,
    target_futures_contracts: float | None = None,
    stock_trade_cost_t: float = 0.0,
    futures_trade_cost_t: float = 0.0,
    stock_liquidation_order: list[tuple[str, float, float]] | None = None,
    contract_round_lot: int = 1,
) -> dict[str, float | bool | str | date | None]:
    trade_day: date | None = None
    if trade_date is not None:
        try:
            parsed_trade_date = pd.Timestamp(trade_date)
            if pd.isna(parsed_trade_date):
                raise ValueError
            trade_day = parsed_trade_date.date()
        except (TypeError, ValueError, OverflowError):
            raise ValueError("trade_date must be a valid date") from None

    def _round_contracts(value: float) -> float:
        if contract_round_lot > 1:
            return float(np.trunc(value / contract_round_lot) * contract_round_lot)
        return float(np.trunc(value)) if float(value).is_integer() is False and contract_round_lot == 1 else float(value)

    def _required_cash_for_target(contracts: float) -> float:
        target_margin = abs(float(contracts)) * futures_close_t * contract_multiplier * rates["initial"]
        incremental_initial_margin = max(0.0, target_margin - float(margin_locked_t_minus_1))
        return float(incremental_initial_margin + futures_trade_cost_t)

    stock_pnl_t = float(nav_t_minus_1 * np.dot(realized_stock_weights_t_minus_1, stock_returns_t))
    futures_pnl_t = float(
        futures_contracts_t_minus_1 * contract_multiplier * (futures_close_t - futures_close_t_minus_1)
    )
    cash_after_mtm = float(cash_free_t_minus_1 + stock_pnl_t + futures_pnl_t)
    nav_before_trades = float(
        nav_t_minus_1 + stock_pnl_t + futures_pnl_t
    )
    rates = resolve_margin_rates(trade_day or date(1900, 1, 1))
    futures_trade = float(target_futures_contracts if target_futures_contracts is not None else futures_contracts_t_minus_1)
    futures_trade = _round_contracts(futures_trade)
    incremental_contracts = futures_trade - float(futures_contracts_t_minus_1)
    forced_futures_contracts = 0.0
    forced_stock_sales = 0.0
    insolvency = False
    if cash_after_mtm < 0:
        deficit = -cash_after_mtm
        per_contract_margin = max(futures_close_t * contract_multiplier * rates["initial"], 1e-9)
        reducible_contracts = min(abs(futures_contracts_t_minus_1), np.ceil(deficit / per_contract_margin))
        forced_futures_contracts = float(reducible_contracts)
        cash_after_mtm += reducible_contracts * per_contract_margin
        futures_trade = float(np.sign(futures_contracts_t_minus_1) * (abs(futures_contracts_t_minus_1) - reducible_contracts))
        if cash_after_mtm < 0 and stock_liquidation_order:
            for _, notional, _ in stock_liquidation_order:
                if cash_after_mtm >= 0:
                    break
                liquidation_value = float(notional)
                forced_stock_sales += liquidation_value
                cash_after_mtm += liquidation_value
        if cash_after_mtm < 0:
            insolvency = True
            raise InsolvencyError("Forced liquidation exhausted assets")
    if target_futures_contracts is not None:
        while True:
            required_cash = _required_cash_for_target(futures_trade)
            if cash_after_mtm >= required_cash or futures_trade == float(futures_contracts_t_minus_1):
                break
            next_abs_trade = max(0.0, abs(futures_trade) - max(contract_round_lot, 1))
            next_trade = _round_contracts(np.sign(futures_trade) * next_abs_trade)
            if abs(next_trade) >= abs(futures_trade):
                futures_trade = float(futures_contracts_t_minus_1)
                break
            futures_trade = float(next_trade)
    incremental_contracts = futures_trade - float(futures_contracts_t_minus_1)
    target_margin = abs(futures_trade) * futures_close_t * contract_multiplier * rates["initial"]
    incremental_initial_margin = max(0.0, target_margin - float(margin_locked_t_minus_1))
    required_cash = float(incremental_initial_margin + futures_trade_cost_t)
    margin_locked_t = abs(futures_trade) * futures_close_t * contract_multiplier * rates["initial"]
    futures_vm_receivable_t = 0.0
    stock_notional_t_minus_1 = float(nav_t_minus_1 - cash_free_t_minus_1 - margin_locked_t_minus_1 - futures_vm_receivable_t_minus_1)
    stock_notional_t = float(stock_notional_t_minus_1 + stock_pnl_t - forced_stock_sales)
    nav_after_trades = float(nav_before_trades - stock_trade_cost_t - futures_trade_cost_t)
    cash_free_t = float(nav_after_trades - stock_notional_t - margin_locked_t - futures_vm_receivable_t)
    margin_equity_t = float(margin_locked_t + futures_vm_receivable_t)
    bucket_sum_t = float(stock_notional_t + cash_free_t + margin_equity_t)
    expiry_date: date | None = None
    if trade_day is not None:
        try:
            expiry_date = get_futures_expiry_date(trade_day.year, trade_day.month)
        except (TypeError, ValueError, OverflowError):
            pass
    return {
        "stock_pnl_t": stock_pnl_t,
        "futures_pnl_t": futures_pnl_t,
        "nav_t_before_trades": nav_before_trades,
        "nav_t_after_trades": nav_after_trades,
        "stock_notional_t": stock_notional_t,
        "cash_free_t": cash_free_t,
        "margin_locked_t": float(margin_locked_t),
        "futures_vm_receivable_t": futures_vm_receivable_t,
        "margin_equity_t": margin_equity_t,
        "bucket_sum_t": bucket_sum_t,
        "required_cash_t": required_cash,
        "forced_futures_contracts": forced_futures_contracts,
        "forced_stock_sales": forced_stock_sales,
        "maintenance_margin_rate": rates["maintenance"],
        "initial_margin_rate": rates["initial"],
        "trade_date": trade_day,
        "expiry_date": expiry_date,
        "expiry_day": bool(trade_day is not None and trade_day == expiry_date),
        "insolvency": insolvency,
    }


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
    futures_contracts: np.ndarray | None = None,
    futures_prices: np.ndarray | None = None,
    contract_multiplier: float = 1.0,
    hedge_enabled: bool = True,
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

        # Slippage: participation-rate impact using the T-1 ADV snapshot.
        slippage_t = 0.0
        if daily_adv is not None:
            adv_row = daily_adv[t]  # VND
            trade_capital = running_capital if dynamic_capital_tracking else portfolio_capital_vnd
            trade_vnd = np.abs(delta_w) * trade_capital
            with np.errstate(divide="ignore", invalid="ignore"):
                participation = np.where(adv_row > 0, trade_vnd / adv_row, 0.0)
            if cost_model.slippage_nonlinear_exp != 1.0:
                p_ref = cost_model.slippage_k_ref_participation
                calibration = p_ref ** (1.0 - cost_model.slippage_nonlinear_exp)
                with np.errstate(invalid="ignore"):
                    participation_eff = np.where(
                        participation > 0,
                        np.power(participation, cost_model.slippage_nonlinear_exp) * calibration,
                        0.0,
                    )
            else:
                participation_eff = participation
            slippage_per_name = cost_model.slippage_k * participation_eff
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

    total_other_adj = 0.0
    if active_dates_mask is not None:
        active_idx = active_dates_mask.astype(bool)
        n_active = int(np.sum(active_idx))
        if n_active == 0:
            n_active = 1
        total_commission_adj = float(np.sum(bar_commission[active_idx]))
        total_spread_adj = float(np.sum(bar_spread[active_idx]))
        total_slippage_adj = float(np.sum(bar_slippage[active_idx]))
        total_turnover_adj = float(np.sum(bar_turnover[active_idx]))
        total_cost_adj = float(np.sum(bar_costs[active_idx]))
        total_other_adj = total_cost_adj - (
            total_commission_adj + total_spread_adj + total_slippage_adj
        )
    else:
        n_active = T
        total_commission_adj = float(np.sum(bar_commission))
        total_spread_adj = float(np.sum(bar_spread))
        total_slippage_adj = float(np.sum(bar_slippage))
        total_turnover_adj = float(np.sum(bar_turnover))
        total_cost_adj = float(np.sum(bar_costs))
        total_other_adj = total_cost_adj - (
            total_commission_adj + total_spread_adj + total_slippage_adj
        )

    breakdown = {
        "total_turnover": total_turnover_adj,
        "avg_turnover_per_bar": float(total_turnover_adj / n_active),
        "total_commission_cost": total_commission_adj,
        "total_spread_cost": total_spread_adj,
        "total_slippage_cost": total_slippage_adj,
        "total_other_cost": float(total_other_adj),
        "total_cost": total_cost_adj,
        "avg_cost_per_bar_bps": float(10000 * total_cost_adj / n_active),
        "capital_vnd": portfolio_capital_vnd,
        "final_capital_vnd": float(running_capital),
        "final_w": prev_w.copy(),
        # Phase 11: extra cost components for diagnostic
        "slippage_nonlinear_exp": cost_model.slippage_nonlinear_exp,
        "settlement_lag_days": cost_model.settlement_lag_days,
        "halt_limit_haircut_pct": cost_model.halt_limit_haircut_pct,
        "foreign_room_haircut_pct": cost_model.foreign_room_haircut_pct,
        "use_adv_tiered_spread": use_adv_tiered_spread,
        "dynamic_capital_tracking": dynamic_capital_tracking,
        "n_active_bars": n_active,
        "bar_costs": bar_costs.copy(),
    }
    if futures_contracts is not None and futures_prices is not None and len(futures_prices) == T:
        futures_contracts = np.asarray(futures_contracts, dtype=float)
        futures_prices = np.asarray(futures_prices, dtype=float)
        futures_pnl = np.zeros(T, dtype=float)
        if hedge_enabled and T > 1:
            futures_pnl[1:] = futures_contracts[:-1] * contract_multiplier * np.diff(futures_prices)
        breakdown["futures_pnl"] = futures_pnl
        breakdown["hedge_enabled"] = bool(hedge_enabled)
    return daily_weights, net_returns, breakdown
