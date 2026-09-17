"""
OMEGA_QUANT Trading Pipeline V2 (Phase 9 - Integration & Testing)
Unified config-driven orchestration of the entire trading lifecycle.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from omega.data.sanitizer import DataSanitizer
from omega.quant.portfolio.tail_controls import apply_tail_controls
from omega.quant.portfolio.execution_sim import (
    apply_realistic_tc,
    VNCostModel,
    DEFAULT_VN_COSTS,
    adv_tiered_half_spread_vectorized,
)


def _compute_market_proxy_returns(
    returns_pivot: pd.DataFrame,
    active_mask: pd.DataFrame,
    min_breadth: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    active_returns = returns_pivot.where(active_mask)
    breadth = active_mask.sum(axis=1).to_numpy(dtype=int)
    proxy = active_returns.mean(axis=1).fillna(0.0).to_numpy(dtype=float)
    insufficient = breadth < min_breadth
    proxy[insufficient] = 0.0
    return proxy, breadth


def _validate_overlays(overlays: list["WeightOverlay"]) -> None:
    regime_positions = [i for i, overlay in enumerate(overlays) if isinstance(overlay, RegimeOverlay)]
    if len(regime_positions) > 1:
        raise ValueError("At most one RegimeOverlay is allowed")
    if regime_positions and regime_positions[0] != len(overlays) - 1:
        raise ValueError("RegimeOverlay must be the last overlay")

logger = logging.getLogger("pipeline_v2")


def _build_conviction_weights(signal_frame: pd.DataFrame, power: float = 1.0) -> pd.DataFrame:
    """Convert cross-sectional signals into conviction-weighted long/short targets."""
    if signal_frame.empty:
        return signal_frame.copy()

    centered = signal_frame.subtract(signal_frame.median(axis=1), axis=0).fillna(0.0)
    conviction = centered.abs().pow(max(power, 1e-8))

    long_mask = centered > 0
    short_mask = centered < 0

    long_strength = conviction.where(long_mask, 0.0)
    short_strength = conviction.where(short_mask, 0.0)

    long_den = long_strength.sum(axis=1).replace(0.0, np.nan)
    short_den = short_strength.sum(axis=1).replace(0.0, np.nan)

    weights_long = long_strength.div(long_den, axis=0).fillna(0.0)
    weights_short = -short_strength.div(short_den, axis=0).fillna(0.0)
    return weights_long + weights_short


def _build_expected_alpha_frame(
    signal_frame: pd.DataFrame,
    returns_frame: pd.DataFrame,
    alpha_scale: float = 1.0,
    vol_lookback: int = 20,
    active_mask: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Estimate per-name expected alpha using PIT-safe signal conviction x prior realized vol."""
    if signal_frame.empty:
        return signal_frame.copy()

    centered = signal_frame.subtract(signal_frame.median(axis=1), axis=0).fillna(0.0)
    signal_abs = centered.abs()
    if active_mask is not None:
        active_signal_abs = signal_abs.where(active_mask)
        norm_den = active_signal_abs.median(axis=1).replace(0.0, np.nan)
    else:
        norm_den = signal_abs.median(axis=1).replace(0.0, np.nan)
    signal_norm = signal_abs.div(norm_den, axis=0).fillna(0.0)
    if active_mask is not None:
        signal_norm = signal_norm.where(active_mask, 0.0)
    signal_norm = signal_norm.clip(lower=0.0, upper=5.0)

    trailing_abs_ret = (
        returns_frame.abs()
        .rolling(window=max(2, vol_lookback), min_periods=2)
        .mean()
        .shift(1)
        .fillna(0.0)
    )
    expected_alpha = signal_norm * trailing_abs_ret * max(alpha_scale, 0.0)
    return expected_alpha.reindex(index=signal_frame.index, columns=signal_frame.columns, fill_value=0.0)


def _estimate_trade_cost_frame(
    target_weights: pd.DataFrame,
    adv_frame: pd.DataFrame | None,
    capital_vnd: float,
    cost_model: VNCostModel,
    prev_w_init: np.ndarray | None,
    use_adv_tiered_spread: bool,
) -> pd.DataFrame:
    """Estimate per-name marginal trade cost using only contemporaneous target + PIT-safe ADV."""
    if target_weights.empty:
        return target_weights.copy()

    weights = target_weights.to_numpy(dtype=float)
    costs = np.zeros_like(weights)
    prev_w = np.zeros(weights.shape[1], dtype=float) if prev_w_init is None else prev_w_init.astype(float, copy=True)
    adv_arr = adv_frame.to_numpy(dtype=float) if adv_frame is not None else None

    p_ref = cost_model.slippage_k_ref_participation
    calibration = p_ref ** (1.0 - cost_model.slippage_nonlinear_exp)

    for t in range(weights.shape[0]):
        w_t = weights[t]
        delta_w = w_t - prev_w
        abs_delta = np.abs(delta_w)

        spread_per_name = np.full_like(abs_delta, cost_model.half_spread_bps, dtype=float)
        if use_adv_tiered_spread and adv_arr is not None:
            spread_per_name = np.asarray(adv_arr[t], dtype=float)
            spread_per_name = np.where(
                spread_per_name > 0,
                adv_tiered_half_spread_vectorized(spread_per_name),
                cost_model.half_spread_bps,
            )

        sell_mask = delta_w < 0
        commission_per_name = np.where(
            sell_mask,
            cost_model.commission_sell + cost_model.tax_sell,
            cost_model.commission_buy,
        )

        slippage_per_name = np.zeros_like(abs_delta)
        if adv_arr is not None:
            adv_row = adv_arr[t]
            trade_vnd = abs_delta * capital_vnd
            with np.errstate(divide="ignore", invalid="ignore"):
                participation = np.where(adv_row > 0, trade_vnd / adv_row, 0.0)
            if cost_model.slippage_nonlinear_exp != 1.0:
                with np.errstate(invalid="ignore"):
                    participation = np.where(
                        participation > 0,
                        np.power(participation, cost_model.slippage_nonlinear_exp) * calibration,
                        0.0,
                    )
            slippage_per_name = cost_model.slippage_k * participation

        costs[t] = abs_delta * (commission_per_name + spread_per_name + slippage_per_name)
        prev_w = w_t

    return pd.DataFrame(costs, index=target_weights.index, columns=target_weights.columns)


def _apply_trade_gating(
    target_weights: pd.DataFrame,
    expected_alpha: pd.DataFrame,
    est_cost: pd.DataFrame,
    prev_w_init: np.ndarray | None,
    no_trade_band: float,
    tc_gate_multiplier: float,
    smooth_ramp_span: int,
) -> pd.DataFrame:
    """Apply no-trade band and expected-alpha-vs-cost gate bar by bar."""
    if target_weights.empty:
        return target_weights.copy()

    result = target_weights.copy()
    prev_w = np.zeros(result.shape[1], dtype=float) if prev_w_init is None else prev_w_init.astype(float, copy=True)

    for i, dt in enumerate(result.index):
        target_row = result.iloc[i].to_numpy(dtype=float)
        delta = target_row - prev_w
        alpha_row = expected_alpha.loc[dt].to_numpy(dtype=float)
        cost_row = est_cost.loc[dt].to_numpy(dtype=float)

        keep_mask = (
            (np.abs(delta) < max(no_trade_band, 0.0))
            | (np.abs(delta) * alpha_row <= max(tc_gate_multiplier, 0.0) * cost_row)
        )
        gated_row = np.where(keep_mask, prev_w, target_row)

        if smooth_ramp_span > 1:
            ramp = 1.0 / float(smooth_ramp_span)
            gated_row = prev_w + ramp * (gated_row - prev_w)

        result.iloc[i] = gated_row
        prev_w = gated_row

    return result


def _resolve_prev_weight_seed(
    columns: pd.Index,
    persisted_weights: Dict[str, Any] | None,
    live_positions: Dict[str, Any] | None,
) -> tuple[Dict[str, float], np.ndarray | None, str]:
    """Resolve prior weights, preferring live broker positions over stale disk state."""
    if live_positions:
        prev_w_dict = {col: float(live_positions.get(col, 0.0)) for col in columns}
        prev_w_init = np.asarray([prev_w_dict[col] for col in columns], dtype=float)
        return prev_w_dict, prev_w_init, "live_positions"

    if persisted_weights:
        prev_w_dict = {col: float(persisted_weights.get(col, 0.0)) for col in columns}
        prev_w_init = np.asarray([prev_w_dict[col] for col in columns], dtype=float)
        return prev_w_dict, prev_w_init, "state"

    return {}, None, "cold_start"


# ============================================================
# STATE PERSISTENCE MANAGER
# ============================================================
class PipelineStateManager:
    """Handles pipeline state persistence (prev weights, vol histories, etc.) on disk."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
    def load_state(self, run_id: str) -> Dict[str, Any]:
        path = self.state_dir / f"pipeline_state_{run_id}.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load state from %s: %s", path, e)
            return {}
            
    def save_state(self, run_id: str, state: Dict[str, Any]) -> None:
        path = self.state_dir / f"pipeline_state_{run_id}.json"
        try:
            def default_encoder(o):
                if isinstance(o, np.ndarray):
                    return o.tolist()
                if isinstance(o, (np.integer, np.floating)):
                    return float(o)
                return str(o)
            with open(path, "w") as f:
                json.dump(state, f, indent=2, default=default_encoder)
        except Exception as e:
            logger.error("Failed to save state to %s: %s", path, e)


# ============================================================
# FEATURE STORE CONNECTOR
# ============================================================
class FeatureStoreAdapter:
    """Abstract interface for reading feature-engineered data."""
    def get_features(self, date_start: pd.Timestamp, date_end: pd.Timestamp, tickers: Optional[List[str]] = None) -> pd.DataFrame:
        raise NotImplementedError


class ParquetFeatureStoreAdapter(FeatureStoreAdapter):
    """Loads features from a local Parquet file (offline backtest)."""
    
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        
    def get_features(self, date_start: pd.Timestamp, date_end: pd.Timestamp, tickers: Optional[List[str]] = None) -> pd.DataFrame:
        df = pd.read_parquet(self.file_path)
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= date_start) & (df["date"] <= date_end)
        if tickers is not None:
            mask = mask & df["ticker"].isin(tickers)
        return df[mask].reset_index(drop=True)


class DatabaseFeatureStoreAdapter(FeatureStoreAdapter):
    """Loads features for live/paper trading from custom database or API."""
    
    def __init__(self, query_fn):
        self.query_fn = query_fn
        
    def get_features(self, date_start: pd.Timestamp, date_end: pd.Timestamp, tickers: Optional[List[str]] = None) -> pd.DataFrame:
        return self.query_fn(date_start, date_end, tickers)


# ============================================================
# OUTPUT HANDLERS
# ============================================================
class PipelineOutputHandler:
    """Abstract interface for handling output actions."""
    def handle(self, final_weights: pd.DataFrame, daily_rets: np.ndarray, extra_stats: Dict[str, Any]) -> Any:
        raise NotImplementedError


class BacktestOutputHandler(PipelineOutputHandler):
    """Saves metrics to JSON and equity curve to CSV (backtest mode)."""
    
    def __init__(self, out_json: Path, out_csv: Path):
        self.out_json = Path(out_json)
        self.out_csv = Path(out_csv)
        
    def handle(self, final_weights: pd.DataFrame, daily_rets: np.ndarray, extra_stats: Dict[str, Any]) -> Dict[str, Any]:
        self.out_json.parent.mkdir(parents=True, exist_ok=True)
        self.out_csv.parent.mkdir(parents=True, exist_ok=True)
        
        cum_ret = float(np.prod(1.0 + daily_rets) - 1.0) if len(daily_rets) > 0 else 0.0
        ann_factor = 252.0
        mean_ret = float(np.mean(daily_rets)) if len(daily_rets) > 0 else 0.0
        std_ret = float(np.std(daily_rets, ddof=1)) if len(daily_rets) > 1 else 0.0
        sharpe = (mean_ret * np.sqrt(ann_factor)) / std_ret if std_ret > 0 else 0.0
        
        cum_prod = np.cumprod(1.0 + daily_rets)
        running_max = np.maximum.accumulate(cum_prod)
        drawdown = (cum_prod - running_max) / running_max if len(cum_prod) > 0 else np.array([0.0])
        max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0
        
        results = {
            "total_return": cum_ret,
            "annualized_sharpe": sharpe,
            "max_drawdown": max_dd,
            "n_days": len(daily_rets),
            **extra_stats
        }
        
        with open(self.out_json, "w") as f:
            json.dump(results, f, indent=2, default=str)
        pd.DataFrame({"daily_ret": daily_rets, "cum_prod": cum_prod}).to_csv(self.out_csv, index=False)
        
        logger.info("Saved backtest reports to %s and %s", self.out_json, self.out_csv)
        return results


class LiveOutputHandler(PipelineOutputHandler):
    """Generates trades and pushes orders (live mode)."""
    
    def __init__(self, order_router, current_positions: Dict[str, float], initial_capital: float = 1e9):
        self.router = order_router
        self.positions = current_positions
        self.initial_capital = initial_capital
        
    def handle(self, final_weights: pd.DataFrame, daily_rets: np.ndarray, extra_stats: Dict[str, Any]) -> List[Any]:
        if final_weights.empty:
            return []
        latest_w = final_weights.iloc[-1]
        orders = []
        for ticker, target_w in latest_w.items():
            current_w = self.positions.get(ticker, 0.0)
            diff = target_w - current_w
            if abs(diff) > 0.001:
                orders.append({
                    "ticker": ticker,
                    "target_weight": float(target_w),
                    "current_weight": float(current_w),
                    "order_weight": float(diff)
                })
        
        if self.router:
            self.router.route_orders(orders)
            
        logger.info("Generated %d live trading orders", len(orders))
        return orders


# ============================================================
# COMPOSABLE OVERLAYS
# ============================================================
class WeightOverlay:
    """Base interface for post-optimization overlays."""
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        raise NotImplementedError


class SmartMoneyOverlay(WeightOverlay):
    def __init__(self, boost_scale: float = 0.25):
        self.boost_scale = boost_scale
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.smart_money_overlay import apply_smart_money_overlay, compute_smart_money_features
        panel_idx = panel.set_index(["date", "symbol"]) if "date" in panel.columns else panel
        res = compute_smart_money_features(panel_idx)
        scores = res["smart_money_score"].groupby(level="symbol").shift(1)
        return apply_smart_money_overlay(weights, scores, boost_scale=self.boost_scale)


class SentimentOverlay(WeightOverlay):
    def __init__(self, boost_scale: float = 0.2):
        self.boost_scale = boost_scale
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.sentiment_overlay import apply_sentiment_overlay, compute_sentiment_proxy
        panel_idx = panel.set_index(["date", "symbol"]) if "date" in panel.columns else panel
        res_sent = compute_sentiment_proxy(panel_idx)
        scores = res_sent.groupby(level="symbol").shift(1)
        return apply_sentiment_overlay(weights, scores, boost_scale=self.boost_scale)


class ContagionOverlay(WeightOverlay):
    def __init__(self, lookback: int = 60, spike_threshold_std: float = 2.0, spike_exposure: float = 0.5):
        self.lookback = lookback
        self.spike_threshold_std = spike_threshold_std
        self.spike_exposure = spike_exposure
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.contagion_overlay import apply_contagion_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_contagion_overlay(
            weights, returns_pivot.to_numpy(),
            lookback=self.lookback,
            spike_threshold_std=self.spike_threshold_std,
            spike_exposure=self.spike_exposure
        )


class TCostOverlay(WeightOverlay):
    def __init__(self, cost_per_trade_bps: float = 15.0, min_trade_threshold_bps: float = 30.0):
        self.cost_per_trade_bps = cost_per_trade_bps
        self.min_trade_threshold_bps = min_trade_threshold_bps
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_tcost_overlay
        return apply_tcost_overlay(
            weights,
            cost_per_trade_bps=self.cost_per_trade_bps,
            min_trade_threshold_bps=self.min_trade_threshold_bps
        )


class CircuitBreakerOverlay(WeightOverlay):
    def __init__(self, cvar_limit: float = -0.08, derisk_multiplier: float = 0.5, lookback: int = 60):
        self.cvar_limit = cvar_limit
        self.derisk_multiplier = derisk_multiplier
        self.lookback = lookback
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.advanced_breaker_overlay import apply_advanced_circuit_breaker
        port_rets = state.get("portfolio_returns_history", np.array([]))
        if len(port_rets) != len(weights):
            panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
            returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
            returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
            common_idx = weights.index.intersection(returns_pivot.index)
            common_cols = weights.columns.intersection(returns_pivot.columns)
            w_sub = weights.loc[common_idx, common_cols]
            r_sub = returns_pivot.loc[common_idx, common_cols]
            port_rets = (w_sub.to_numpy() * r_sub.to_numpy()).sum(axis=1)
        return apply_advanced_circuit_breaker(
            weights, port_rets,
            cvar_limit=self.cvar_limit,
            derisk_multiplier=self.derisk_multiplier,
            lookback=self.lookback
        )


class TailControlOverlay(WeightOverlay):
    def __init__(
        self,
        target_vol_ann: float = 0.15,
        max_abs_weight: float = 0.05,
        downside_only_vol_target: bool = False,
        dd_window: int = 20,
        dd_threshold: float = 0.08,
        dd_cut: float = 0.5,
        soft_brake_enabled: bool = False,
        soft_brake_base_threshold: float = 0.05,
        soft_brake_min_scale: float = 0.1,
        soft_brake_depth: float = 2.0,
        soft_brake_vol_sensitivity: float = 1.0,
        regime_ramp_enabled: bool = False,
        regime_ramp_tau: float = 0.20,
        regime_bear_scale: float = 0.50,
        regime_bull_scale: float = 1.00,
        bocpd_penalty_scale: float = 0.75,
    ):
        self.target_vol_ann = target_vol_ann
        self.max_abs_weight = max_abs_weight
        self.downside_only_vol_target = downside_only_vol_target
        self.dd_window = dd_window
        self.dd_threshold = dd_threshold
        self.dd_cut = dd_cut
        self.soft_brake_enabled = soft_brake_enabled
        self.soft_brake_base_threshold = soft_brake_base_threshold
        self.soft_brake_min_scale = soft_brake_min_scale
        self.soft_brake_depth = soft_brake_depth
        self.soft_brake_vol_sensitivity = soft_brake_vol_sensitivity
        self.regime_ramp_enabled = regime_ramp_enabled
        self.regime_ramp_tau = regime_ramp_tau
        self.regime_bear_scale = regime_bear_scale
        self.regime_bull_scale = regime_bull_scale
        self.bocpd_penalty_scale = bocpd_penalty_scale
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        warmup = state.get("warmup_history")
        gmm_p_bull = state.get("gmm_p_bull") if self.regime_ramp_enabled else None
        gmm_p_bear = state.get("gmm_p_bear") if self.regime_ramp_enabled else None
        adj_w, _ = apply_tail_controls(
            weights, returns_pivot.to_numpy(),
            target_vol_ann=self.target_vol_ann,
            downside_only_vol_target=self.downside_only_vol_target,
            max_abs_weight=self.max_abs_weight,
            dd_window=self.dd_window,
            dd_threshold=self.dd_threshold,
            dd_cut=self.dd_cut,
            warmup_history=warmup,
            soft_brake_enabled=self.soft_brake_enabled,
            soft_brake_base_threshold=self.soft_brake_base_threshold,
            soft_brake_min_scale=self.soft_brake_min_scale,
            soft_brake_depth=self.soft_brake_depth,
            soft_brake_vol_sensitivity=self.soft_brake_vol_sensitivity,
            regime_dates=weights.index,
            gmm_p_bull=gmm_p_bull,
            gmm_p_bear=gmm_p_bear,
            regime_ramp_enabled=self.regime_ramp_enabled,
            regime_ramp_tau=self.regime_ramp_tau,
            regime_bear_scale=self.regime_bear_scale,
            regime_bull_scale=self.regime_bull_scale,
            bocpd_penalty_scale=self.bocpd_penalty_scale,
        )
        return adj_w


class AdaptiveSizingOverlay(WeightOverlay):
    def __init__(self, capital_vnd: float = 1e9):
        self.capital_vnd = capital_vnd
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.adaptive_sizing_overlay import apply_adaptive_sizing
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        adv_series = None
        if "adv_vnd" in panel_flat.columns:
            adv_frame = panel_flat[["date", "symbol", "adv_vnd"]].dropna(subset=["date", "symbol"]).copy()
            adv_frame = adv_frame.sort_values(["symbol", "date"])
            adv_frame["adv_vnd_pit"] = adv_frame.groupby("symbol", sort=False)["adv_vnd"].transform(
                lambda s: s.expanding(min_periods=1).mean().shift(1)
            )
            adv_series = adv_frame.pivot_table(
                index="date",
                columns="symbol",
                values="adv_vnd_pit",
                aggfunc="last",
            ).reindex(index=weights.index, columns=weights.columns)
        return apply_adaptive_sizing(weights, self.capital_vnd, adv_series)


class BlackLittermanOverlay(WeightOverlay):
    def __init__(self, tau: float = 0.05, view_confidence: float = 0.5, l2_reg: float = 0.01, max_weight: float = 0.05):
        self.tau = tau
        self.view_confidence = view_confidence
        self.l2_reg = l2_reg
        self.max_weight = max_weight
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.black_litterman_overlay import apply_black_litterman_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        sig_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
        sig_pivot = sig_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_black_litterman_overlay(
            weights, returns_pivot.to_numpy(), sig_pivot.to_numpy(),
            tau=self.tau, view_confidence=self.view_confidence,
            l2_reg=self.l2_reg, max_weight=self.max_weight
        )


class ContinuousLearningOverlay(WeightOverlay):
    def __init__(self, retrain_threshold_ic: float = 0.01, retrain_lookback: int = 120, retrain_every: int = 60, min_train: int = 252):
        self.retrain_threshold_ic = retrain_threshold_ic
        self.retrain_lookback = retrain_lookback
        self.retrain_every = retrain_every
        self.min_train = min_train
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.continuous_learning_overlay import apply_continuous_learning_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        feat_cols = [c for c in panel_flat.columns if c.startswith("feature_") or c.startswith("alpha_")]
        if not feat_cols:
            feat_cols = ["composite_signal"]
        
        features_df = panel_flat.groupby("date")[feat_cols].mean().reindex(weights.index).fillna(0.0)
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        target_returns = returns_pivot.mean(axis=1).to_numpy()
        
        return apply_continuous_learning_overlay(
            weights, features_df.to_numpy(), target_returns,
            retrain_threshold_ic=self.retrain_threshold_ic,
            retrain_lookback=self.retrain_lookback,
            retrain_every=self.retrain_every,
            min_train=self.min_train
        )


class DriftOverlay(WeightOverlay):
    def __init__(self, lookback: int = 60, ic_threshold: float = 0.0, drift_exposure: float = 0.5):
        self.lookback = lookback
        self.ic_threshold = ic_threshold
        self.drift_exposure = drift_exposure
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.drift_overlay import apply_drift_overlay
        port_rets = state.get("portfolio_returns_history", np.array([]))
        if len(port_rets) == 0:
            panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
            returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
            returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
            common_idx = weights.index.intersection(returns_pivot.index)
            common_cols = weights.columns.intersection(returns_pivot.columns)
            w_sub = weights.loc[common_idx, common_cols]
            r_sub = returns_pivot.loc[common_idx, common_cols]
            port_rets = (w_sub.to_numpy() * r_sub.to_numpy()).sum(axis=1)
        return apply_drift_overlay(
            weights, port_rets,
            lookback=self.lookback,
            ic_threshold=self.ic_threshold,
            drift_exposure=self.drift_exposure
        )


class HMMRegimeOverlay(WeightOverlay):
    def __init__(self, bear_exposure: float = 0.5, bull_exposure: float = 1.1, sideways_exposure: float = 0.8, retrain_every: int = 60):
        self.bear_exposure = bear_exposure
        self.bull_exposure = bull_exposure
        self.sideways_exposure = sideways_exposure
        self.retrain_every = retrain_every
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.regime_overlay import apply_hmm_regime_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        active_mask = returns_pivot.ne(0.0)
        market_returns, _ = _compute_market_proxy_returns(returns_pivot, active_mask)
        return apply_hmm_regime_overlay(
            weights, market_returns,
            bear_exposure=self.bear_exposure,
            bull_exposure=self.bull_exposure,
            sideways_exposure=self.sideways_exposure,
            retrain_every=self.retrain_every
        )


class RegimeAwareWFOverlay(WeightOverlay):
    def __init__(self, bear_scale: float = 0.3, bull_scale: float = 1.0, sideways_scale: float = 0.7, retrain_every: int = 60, min_train: int = 252):
        self.bear_scale = bear_scale
        self.bull_scale = bull_scale
        self.sideways_scale = sideways_scale
        self.retrain_every = retrain_every
        self.min_train = min_train
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.regime_overlay import apply_regime_aware_walk_forward
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        active_mask = returns_pivot.ne(0.0)
        market_returns, _ = _compute_market_proxy_returns(returns_pivot, active_mask)
        return apply_regime_aware_walk_forward(
            weights, market_returns,
            bear_scale=self.bear_scale,
            bull_scale=self.bull_scale,
            sideways_scale=self.sideways_scale,
            retrain_every=self.retrain_every,
            min_train=self.min_train
        )


class RegimeOverlay(WeightOverlay):
    def __init__(self, hysteresis_days: int = 5, dd_threshold: float = -0.10, bull_exposure: float = 1.1, bear_exposure: float = 0.5, sideways_exposure: float = 0.8):
        self.hysteresis_days = hysteresis_days
        self.dd_threshold = dd_threshold
        self.bull_exposure = bull_exposure
        self.bear_exposure = bear_exposure
        self.sideways_exposure = sideways_exposure
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.regime_overlay import apply_regime_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        active_mask = returns_pivot.ne(0.0)
        market_returns, _ = _compute_market_proxy_returns(returns_pivot, active_mask)
        return apply_regime_overlay(
            weights, market_returns,
            hysteresis_days=self.hysteresis_days,
            dd_threshold=self.dd_threshold,
            bull_exposure=self.bull_exposure,
            bear_exposure=self.bear_exposure,
            sideways_exposure=self.sideways_exposure
        )


class ThompsonSamplingWeightOverlay(WeightOverlay):
    def __init__(self, lookback: int = 20, update_every: int = 5):
        self.lookback = lookback
        self.update_every = update_every
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.thompson_sampling_overlay import apply_thompson_sampling_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_thompson_sampling_overlay(
            weights, returns_pivot,
            lookback=self.lookback,
            update_every=self.update_every
        )



class WeightSmoothingOverlay(WeightOverlay):
    def __init__(self, ema_alpha: float = 0.05, exposure_blend: float = 0.0):
        self.ema_alpha = ema_alpha
        self.exposure_blend = float(exposure_blend)
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        smoothed = weights.ewm(alpha=self.ema_alpha, adjust=False).mean()
        if self.exposure_blend > 0.0:
            target_exposure = weights.abs().sum(axis=1)
            current_exposure = smoothed.abs().sum(axis=1).replace(0, 1.0)
            blend_exposure = (
                self.exposure_blend * target_exposure
                + (1.0 - self.exposure_blend) * current_exposure
            )
            smoothed = smoothed.mul(blend_exposure / current_exposure, axis=0)
        logger.info(
            "Weight smoothing applied: ema_alpha=%.2f, exposure_blend=%.2f",
            self.ema_alpha,
            self.exposure_blend,
        )
        return smoothed


# ============================================================
# MAIN TRADING PIPELINE V2 ORCHESTRATOR

# ============================================================
class TradingPipelineV2:
    """Unified Orchestration Pipeline."""
    
    def __init__(
        self,
        feature_store: FeatureStoreAdapter,
        state_manager: PipelineStateManager,
        output_handler: PipelineOutputHandler,
        overlays: List[WeightOverlay],
        config: Dict[str, Any]
    ):
        self.feature_store = feature_store
        self.state_manager = state_manager
        self.output_handler = output_handler
        self.overlays = overlays
        self.config = config
        _validate_overlays(overlays)
        
    def execute(
        self,
        run_id: str,
        date_start: str,
        date_end: str,
        tickers: Optional[List[str]] = None,
        active_dates: Optional[pd.DatetimeIndex] = None,
    ) -> Any:
        start_date = pd.Timestamp(date_start)
        end_date = pd.Timestamp(date_end)
        warmup_days = int(self.config.get("feature_warmup_days", 30))
        fetch_start_date = start_date - pd.Timedelta(days=warmup_days) if warmup_days > 0 else start_date
        
        logger.info(
            "Fetching features for period %s to %s (warmup start %s)",
            date_start,
            date_end,
            fetch_start_date.date(),
        )
        panel = self.feature_store.get_features(fetch_start_date, end_date, tickers)
        if panel.empty:
            logger.error("No data fetched from feature store")
            raise ValueError("Feature store returned empty data")
            
        if "symbol" not in panel.columns and "ticker" in panel.columns:
            panel = panel.rename(columns={"ticker": "symbol"})
        panel["date"] = pd.to_datetime(panel["date"])
            
        n0 = len(panel)
        panel = panel[panel["volume"] > 0].reset_index(drop=True)
        logger.info("Dropped %d suspended bars", n0 - len(panel))
        
        if DataSanitizer is not None:
            # Reattach symbol trick from CPCV backtester
            panel_in = panel.copy()
            panel_in["_orig_idx"] = np.arange(len(panel_in))
            max_date = pd.to_datetime(panel["date"].max())
            san = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01, as_of_time=max_date)
            san.fit(panel_in, symbol_col="symbol", date_col="date")
            panel = san.apply(panel_in, symbol_col="symbol", date_col="date")
            if "symbol" not in panel.columns:
                if "_orig_idx" not in panel.columns:
                    panel["symbol"] = panel_in.loc[panel.index, "symbol"].values
                else:
                    ticker_map = dict(zip(panel_in["_orig_idx"].values, panel_in["symbol"].values))
                    panel["symbol"] = panel["_orig_idx"].map(ticker_map)
                    panel = panel.drop(columns=["_orig_idx"])
            
        if "composite_signal" not in panel.columns or panel["composite_signal"].nunique() <= 1:
            signal_cols = [c for c in panel.columns if c.startswith("alpha_") or c.endswith("_signal") or c == "signal"]
            if signal_cols:
                logger.info("Training cross-sectional Ridge model to blend %d alphas...", len(signal_cols))
                dates = sorted(panel["date"].unique())
                n_dates = len(dates)
                preds = np.zeros(len(panel))

                start_date_idx = int(np.searchsorted(dates, start_date))
                if n_dates > start_date_idx:
                    date_to_idx = {d: i for i, d in enumerate(dates)}
                    panel_date_idx = panel["date"].map(date_to_idx).to_numpy()
                    
                    # Shift features by 1 day per symbol to avoid look-ahead leakage (T-1 lag)
                    X_df = panel.groupby("symbol")[signal_cols].shift(1).fillna(0.0)
                    X = X_df.to_numpy()
                    y = panel["returns"].fillna(0.0).to_numpy()
                    
                    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
                    
                    from sklearn.linear_model import Ridge

                    if start_date_idx > 0:
                        preds[panel_date_idx < start_date_idx] = panel.loc[
                            panel_date_idx < start_date_idx, signal_cols
                        ].mean(axis=1).fillna(0.0).to_numpy()

                    mean_alpha = panel[signal_cols].mean(axis=1).fillna(0.0).to_numpy()
                    for t in range(start_date_idx, n_dates):
                        train_mask = panel_date_idx < t
                        if len(np.unique(panel_date_idx[train_mask])) < 20:
                            preds[panel_date_idx == t] = mean_alpha[panel_date_idx == t]
                            continue

                        model = Ridge(alpha=100.0)
                        model.fit(X[train_mask], y[train_mask])
                        test_mask = panel_date_idx == t
                        if test_mask.any():
                            preds[test_mask] = model.predict(X[test_mask])
                            
                    panel["composite_signal"] = preds
                else:
                    panel["composite_signal"] = panel[signal_cols].mean(axis=1)
            else:
                panel["composite_signal"] = 0.0

        panel = panel[(panel["date"] >= start_date) & (panel["date"] <= end_date)].reset_index(drop=True)
        if panel.empty:
            raise ValueError("Feature store returned only warmup data; no rows in requested period")

        logger.info("Constructing target portfolio weights")
        pivot_sig = panel.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
        active_signal_mask = panel.pivot_table(index="date", columns="symbol", values="composite_signal").notna()
        active_signal_mask = active_signal_mask.reindex(index=pivot_sig.index, columns=pivot_sig.columns, fill_value=False)
        returns_pivot = panel.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=pivot_sig.index, columns=pivot_sig.columns, fill_value=0.0)
        adv_pivot = None
        if "adv_vnd" in panel.columns:
            adv_pivot = panel.pivot_table(index="date", columns="symbol", values="adv_vnd")
            adv_pivot = adv_pivot.sort_index().groupby(level=0).last()
            adv_pivot = adv_pivot.reindex(index=pivot_sig.index, columns=pivot_sig.columns)
            adv_pivot = adv_pivot.shift(1)

        weights = _build_conviction_weights(
            pivot_sig,
            power=float(self.config.get("conviction_power", 1.0)),
        )
        
        state = self.state_manager.load_state(run_id)
        market_active_mask = panel.pivot_table(index="date", columns="symbol", values="volume", aggfunc="last").reindex(
            index=pivot_sig.index,
            columns=pivot_sig.columns,
        ).fillna(0.0) > 0.0
        market_proxy_returns, market_breadth = _compute_market_proxy_returns(
            returns_pivot,
            market_active_mask,
        )
        state["crash_detector"] = {
            "market_proxy_returns": market_proxy_returns,
            "breadth": market_breadth,
            "breadth_insufficient": (market_breadth < 5),
        }

        capital = self.config.get("initial_capital_vnd", 1e9)
        use_adv_tiered_spread = self.config.get("use_adv_tiered_spread", False)
        dynamic_capital_tracking = self.config.get("dynamic_capital_tracking", True)
        cost_model = VNCostModel(
            commission_buy=self.config.get("commission_buy", DEFAULT_VN_COSTS.commission_buy),
            commission_sell=self.config.get("commission_sell", DEFAULT_VN_COSTS.commission_sell),
            tax_sell=self.config.get("tax_sell", DEFAULT_VN_COSTS.tax_sell),
            half_spread_bps=self.config.get("half_spread_bps", DEFAULT_VN_COSTS.half_spread_bps),
            slippage_k=self.config.get("slippage_k", DEFAULT_VN_COSTS.slippage_k),
            slippage_nonlinear_exp=self.config.get("slippage_nonlinear_exp", DEFAULT_VN_COSTS.slippage_nonlinear_exp)
        )
        live_positions = self.output_handler.positions if isinstance(self.output_handler, LiveOutputHandler) else None
        prev_w_dict, prev_w_init, prev_w_source = _resolve_prev_weight_seed(
            weights.columns,
            state.get("last_weights", {}),
            live_positions,
        )
        dynamic_tc_gate_enabled = not (
            isinstance(self.output_handler, LiveOutputHandler) and prev_w_source == "cold_start"
        )

        expected_alpha = _build_expected_alpha_frame(
            pivot_sig,
            returns_pivot,
            alpha_scale=float(self.config.get("expected_alpha_scale", 1.0)),
            vol_lookback=int(self.config.get("expected_alpha_lookback", 20)),
            active_mask=active_signal_mask,
        )
        est_cost = _estimate_trade_cost_frame(
            weights,
            adv_pivot,
            capital_vnd=capital,
            cost_model=cost_model,
            prev_w_init=prev_w_init,
            use_adv_tiered_spread=use_adv_tiered_spread,
        )
        if dynamic_tc_gate_enabled:
            weights = _apply_trade_gating(
                weights,
                expected_alpha,
                est_cost,
                prev_w_init=prev_w_init,
                no_trade_band=float(self.config.get("no_trade_band", 0.01)),
                tc_gate_multiplier=float(self.config.get("dynamic_tc_gate_multiplier", 2.5)),
                smooth_ramp_span=int(self.config.get("rebalance_smooth_ramp_span", 3)),
            )
        state["dynamic_tc_gate"] = {
            "enabled": dynamic_tc_gate_enabled,
            "prev_weight_source": prev_w_source,
            "avg_expected_alpha": float(expected_alpha.mean().mean()) if not expected_alpha.empty else 0.0,
            "avg_est_cost": float(est_cost.mean().mean()) if not est_cost.empty else 0.0,
            "no_trade_band": float(self.config.get("no_trade_band", 0.01)),
            "tc_gate_multiplier": float(self.config.get("dynamic_tc_gate_multiplier", 2.5)),
            "smooth_ramp_span": int(self.config.get("rebalance_smooth_ramp_span", 3)),
        }
        
        state["active_dates"] = active_dates

        for overlay in self.overlays:
            logger.info("Applying overlay: %s", overlay.__class__.__name__)
            weights = overlay.apply(weights, panel, state)

        common_idx = weights.index.intersection(returns_pivot.index)
        common_cols = weights.columns.intersection(returns_pivot.columns)
        
        r_arr = returns_pivot.loc[common_idx, common_cols].to_numpy()
        
        adv_arr = None
        if adv_pivot is not None:
            adv_pivot = adv_pivot.reindex(index=common_idx, columns=common_cols, fill_value=0.0)
            adv_arr = adv_pivot.to_numpy()

        prev_w_init_exec = None
        if prev_w_source != "cold_start":
            prev_w_init_exec = np.asarray([prev_w_dict.get(c, 0.0) for c in common_cols], dtype=float)

        active_dates_mask = None
        if active_dates is not None:
            active_dates_mask = pd.Index(common_idx).isin(active_dates)
            if hasattr(active_dates_mask, "to_numpy"):
                active_dates_mask = active_dates_mask.to_numpy()
            
        _, net_rets, cost_breakdown = apply_realistic_tc(
            weights.loc[common_idx, common_cols],
            r_arr,
            daily_adv=adv_arr,
            portfolio_capital_vnd=capital,
            cost_model=cost_model,
            prev_w_init=prev_w_init_exec,
            use_adv_tiered_spread=use_adv_tiered_spread,
            dynamic_capital_tracking=dynamic_capital_tracking,
            active_dates_mask=active_dates_mask,
        )

        for overlay in self.overlays:
            if hasattr(overlay, "sync_executed_returns"):
                overlay.sync_executed_returns(
                    net_rets[active_dates_mask] if active_dates_mask is not None else net_rets
                )
                if hasattr(overlay, "snapshot_state"):
                    state["drawdown_control"] = overlay.snapshot_state()

        # Filter net_rets to active test dates only (CPCV: prevent cost
        # leakage from non-test-date gaps between scattered test blocks)
        if active_dates_mask is not None:
            net_rets = net_rets[active_dates_mask]
            weights = weights.loc[common_idx[active_dates_mask]]
        
        new_state = {
            "last_weights": weights.iloc[-1].to_dict(),
            "portfolio_returns_history": net_rets,
            "warmup_history": net_rets[-120:] if len(net_rets) >= 120 else net_rets,
            "dynamic_tc_gate": state.get("dynamic_tc_gate", {}),
        }
        if "drawdown_control" in state:
            new_state["drawdown_control"] = state["drawdown_control"]
        self.state_manager.save_state(run_id, new_state)
        
        return self.output_handler.handle(weights, net_rets, {"cost_breakdown": cost_breakdown})
