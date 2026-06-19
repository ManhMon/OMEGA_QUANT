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
from omega.quant.portfolio.execution_sim import apply_realistic_tc, VNCostModel, DEFAULT_VN_COSTS
from omega.quant.pipeline.overlays import (
    WeightOverlay,
    SmartMoneyOverlay,
    SentimentOverlay,
    ContagionOverlay,
    TCostOverlay,
    CircuitBreakerOverlay,
    TailControlOverlay,
    AdaptiveSizingOverlay,
    BlackLittermanOverlay,
    ContinuousLearningOverlay,
    DriftOverlay,
    RegimeOverlay,
    ThompsonSamplingWeightOverlay,
    WeightSmoothingOverlay,
)

logger = logging.getLogger("pipeline_v2")


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

    def get_features(
        self,
        date_start: pd.Timestamp,
        date_end: pd.Timestamp,
        tickers: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError


class ParquetFeatureStoreAdapter(FeatureStoreAdapter):
    """Loads features from a local Parquet file (offline backtest)."""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    def get_features(
        self,
        date_start: pd.Timestamp,
        date_end: pd.Timestamp,
        tickers: Optional[List[str]] = None,
    ) -> pd.DataFrame:
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

    def get_features(
        self,
        date_start: pd.Timestamp,
        date_end: pd.Timestamp,
        tickers: Optional[List[str]] = None,
    ) -> pd.DataFrame:
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

    def handle(
        self,
        final_weights: pd.DataFrame,
        daily_rets: np.ndarray,
        extra_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
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


# Backward compatibility aliases
class HMMRegimeOverlay(RegimeOverlay):
    """Alias for RegimeOverlay with HMM strategy. Deprecated: use RegimeOverlay(strategy='hmm') instead."""

    def __init__(
        self,
        bear_exposure=0.5,
        bull_exposure=1.1,
        sideways_exposure=0.8,
        retrain_every=60,
    ):
        super().__init__(
            strategy='hmm',
            hysteresis_days=5,
            dd_threshold=-0.10,
            bull_exposure=bull_exposure,
            bear_exposure=bear_exposure,
            sideways_exposure=sideways_exposure,
            retrain_every=retrain_every
        )


class RegimeAwareWFOverlay(RegimeOverlay):
    """Alias for RegimeOverlay with HMM strategy. Deprecated: use RegimeOverlay(strategy='hmm') instead."""

    def __init__(
        self,
        bear_scale=0.3,
        bull_scale=1.0,
        sideways_scale=0.7,
        retrain_every=60,
        min_train=252,
    ):
        super().__init__(
            strategy='hmm',
            hysteresis_days=5,
            dd_threshold=-0.10,
            bull_exposure=bull_scale,
            bear_exposure=bear_scale,
            sideways_exposure=sideways_scale,
            retrain_every=retrain_every
        )
        self.min_train = min_train


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

    def execute(self, run_id: str, date_start: str, date_end: str, tickers: Optional[List[str]] = None) -> Any:
        start_date = pd.Timestamp(date_start)
        end_date = pd.Timestamp(date_end)

        logger.info("Fetching features for period %s to %s", date_start, date_end)
        panel = self.feature_store.get_features(start_date, end_date, tickers)
        if panel.empty:
            logger.error("No data fetched from feature store")
            raise ValueError("Feature store returned empty data")

        if "symbol" not in panel.columns and "ticker" in panel.columns:
            panel = panel.rename(columns={"ticker": "symbol"})

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

                warmup_days = min(252, max(60, n_dates // 4))
                if n_dates > warmup_days:
                    date_to_idx = {d: i for i, d in enumerate(dates)}
                    panel_date_idx = panel["date"].map(date_to_idx).to_numpy()

                    # Shift features by 1 day per symbol to avoid look-ahead leakage (T-1 lag)
                    X_df = panel.groupby("symbol")[signal_cols].shift(1).fillna(0.0)
                    X = X_df.to_numpy()
                    y = panel["returns"].fillna(0.0).to_numpy()

                    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

                    retrain_step = 40
                    from sklearn.linear_model import Ridge

                    train_mask = panel_date_idx < warmup_days
                    if train_mask.any():
                        model = Ridge(alpha=100.0)
                        model.fit(X[train_mask], y[train_mask])
                        preds[train_mask] = model.predict(X[train_mask])

                    for t in range(warmup_days, n_dates, retrain_step):
                        train_mask = panel_date_idx < t
                        model = Ridge(alpha=100.0)
                        model.fit(X[train_mask], y[train_mask])

                        test_mask = (panel_date_idx >= t) & (panel_date_idx < t + retrain_step)
                        if test_mask.any():
                            preds[test_mask] = model.predict(X[test_mask])

                    panel["composite_signal"] = preds
                else:
                    panel["composite_signal"] = panel[signal_cols].mean(axis=1)
            else:
                panel["composite_signal"] = 0.0

        logger.info("Constructing target portfolio weights")
        pivot_sig = panel.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
        demedian = pivot_sig.subtract(pivot_sig.median(axis=1), axis=0)

        pos = np.sign(demedian)
        longs = (pos > 0).sum(axis=1).replace(0, 1.0)
        shorts = (pos < 0).sum(axis=1).replace(0, 1.0)

        # Standardize weights: sum of longs = 1.0, sum of shorts = -1.0 (gross exposure = 2.0)
        weights_long = (pos > 0).astype(float).div(longs, axis=0)
        weights_short = -(pos < 0).astype(float).div(shorts, axis=0)
        weights = weights_long + weights_short

        state = self.state_manager.load_state(run_id)

        for overlay in self.overlays:
            logger.info("Applying overlay: %s", overlay.__class__.__name__)
            weights = overlay.apply(weights, panel, state)

        returns_pivot = panel.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        common_idx = weights.index.intersection(returns_pivot.index)
        common_cols = weights.columns.intersection(returns_pivot.columns)

        r_arr = returns_pivot.loc[common_idx, common_cols].to_numpy()

        adv_arr = None
        if "adv_vnd" in panel.columns:
            adv_pivot = panel.pivot_table(index="date", columns="symbol", values="adv_vnd").fillna(0.0)
            adv_pivot = adv_pivot.reindex(index=common_idx, columns=common_cols, fill_value=0.0)
            adv_arr = adv_pivot.to_numpy()

        capital = self.config.get("initial_capital_vnd", 1e9)
        cost_model = VNCostModel(
            commission_buy=self.config.get("commission_buy", DEFAULT_VN_COSTS.commission_buy),
            commission_sell=self.config.get("commission_sell", DEFAULT_VN_COSTS.commission_sell),
            tax_sell=self.config.get("tax_sell", DEFAULT_VN_COSTS.tax_sell),
            half_spread_bps=self.config.get("half_spread_bps", DEFAULT_VN_COSTS.half_spread_bps),
            slippage_k=self.config.get("slippage_k", DEFAULT_VN_COSTS.slippage_k),
            slippage_nonlinear_exp=self.config.get("slippage_nonlinear_exp", DEFAULT_VN_COSTS.slippage_nonlinear_exp)
        )

        prev_w_dict = state.get("last_weights", {})
        prev_w_init = None
        if prev_w_dict:
            prev_w_init = np.asarray([prev_w_dict.get(c, 0.0) for c in common_cols], dtype=float)

        _, net_rets, cost_breakdown = apply_realistic_tc(
            weights.loc[common_idx, common_cols],
            r_arr,
            daily_adv=adv_arr,
            portfolio_capital_vnd=capital,
            cost_model=cost_model,
            prev_w_init=prev_w_init
        )

        new_state = {
            "last_weights": weights.iloc[-1].to_dict(),
            "portfolio_returns_history": net_rets,
            "warmup_history": net_rets[-120:] if len(net_rets) >= 120 else net_rets
        }
        self.state_manager.save_state(run_id, new_state)

        return self.output_handler.handle(weights, net_rets, {"cost_breakdown": cost_breakdown})
