"""Walk-forward CPCV backtest for Hybrid GMM-BOCPD Regime Detection system.

Gate: HYBRID_REGIME_FULL_BACKTEST_20260620

Runs CombinatorialPurgedKFold over the full historical period (2015-2026),
generating features per fold via UnifiedFeatureAdapter and executing
TradingPipelineV2 for both Baseline and Hybrid GMM-BOCPD scenarios.

Supports dynamic universe selection via DynamicUniverseSelector and
aggregates Sharpe, Max DD, and Return across all folds.
"""

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys
import gc
import time
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from joblib import Parallel, delayed

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

import logging
import pandas as pd
import numpy as np
import json
from datetime import datetime

from sklearn.linear_model import Ridge

try:
    from lightgbm import LGBMRegressor
except Exception:  # pragma: no cover - exercised when optional dep absent
    LGBMRegressor = None

from omega.quant import (
    TradingPipelineV2,
    PipelineStateManager,
    DatabaseFeatureStoreAdapter,
    BacktestOutputHandler,
)
from omega.quant.pipeline.overlays.base import WeightOverlay
from omega.quant.pipeline.overlays.weight_smoothing import WeightSmoothingOverlay
from omega.quant.pipeline.overlays.sector_concentration import SectorConcentrationOverlay
from omega.quant.pipeline.overlays.board_lot_rounding import BoardLotRoundingOverlay
from omega.quant.pipeline.overlays.drawdown_control import DrawdownControlOverlay
from omega.quant.pipeline.overlays.risk_sizing import RiskSizingOverlay
from omega.quant.pipeline.overlays.tail_control import TailControlOverlay
from omega.quant.pipeline.overlays.tcost import TCostOverlay
from omega.quant.pipeline.overlays.rebalance_frequency import RebalanceFrequencyOverlay
from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.validation.cpcv import CombinatorialPurgedKFold
from omega.quant.walk_forward.risk_sizing_overlay import SimpleGaussianHMM
from omega.quant.strategy.latent_gmm import LatentGMMRegime, LatentGMMConfig
from phase35_data_loader import DynamicUniverseSelector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest_hybrid_regime")

WARMUP_TRADING_DAYS = 252
DEFAULT_DATA_PATH = "data/market_2015_now.parquet"
SECTOR_MAPPING_FILE = "data/sector_mapping_level2.csv"
LATENT_AE_PATH = "data/latent_alphas_components.parquet"
OUTPUT_DIR = "data/phase35_results"
STATE_DIR = ".ly_state/session/pipeline_state_hybrid"


class LongOnlyConcentratedOverlay(WeightOverlay):
    """Clips weights to non-negative (long-only), keeps top_k, normalizes to sum to 1.0."""
    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        # Clip to non-negative (long-only)
        long_only = weights.clip(lower=0.0)
        
        # Select top_k largest weights on each date, zeroes others
        # We can do this efficiently per row.
        # Find the threshold value for the top_kth largest element per row
        # If the row has fewer elements than top_k, we just keep all non-zero elements.
        processed_rows = []
        for idx, row in long_only.iterrows():
            if row.sum() == 0:
                processed_rows.append(row)
                continue
            
            # Find the top_k largest value
            sorted_vals = row.sort_values(ascending=False)
            if len(sorted_vals) > self.top_k:
                kth_val = sorted_vals.iloc[self.top_k - 1]
                # Zero out anything less than kth_val
                # To handle ties or zeroes properly, we can mask
                # If kth_val is 0, we only keep positive values up to top_k
                mask = row >= kth_val
                new_row = row.where(mask, 0.0)
                
                # If there are ties resulting in more than top_k elements, let's keep only top_k elements
                if (new_row > 0.0).sum() > self.top_k:
                    # Keep only the top_k elements by index
                    keep_idx = sorted_vals.index[:self.top_k]
                    new_row = new_row.copy()
                    new_row.loc[~new_row.index.isin(keep_idx)] = 0.0
            else:
                new_row = row
            
            # Normalize to sum to 1.0 (or 0.0 if all zero)
            row_sum = new_row.sum()
            if row_sum > 0.0:
                new_row = new_row / row_sum
            else:
                new_row = new_row * 0.0
            processed_rows.append(new_row)
            
        return pd.DataFrame(processed_rows, index=weights.index, columns=weights.columns)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Walk-forward CPCV backtest for Hybrid GMM-BOCPD Regime Detection"
    )
    parser.add_argument(
        "--start-date", default="2015-01-01",
        help="Backtest period start (default: 2015-01-01)",
    )
    parser.add_argument(
        "--end-date", default="2026-12-31",
        help="Backtest period end (default: 2026-12-31)",
    )
    parser.add_argument(
        "--capital", type=float, default=2_000_000_000.0,
        help="Initial capital in VND (default: 2B)",
    )
    parser.add_argument(
        "--folds", type=int, default=10,
        help="CPCV n_splits (default: 10)",
    )
    parser.add_argument(
        "--n-test-folds", type=int, default=2,
        help="CPCV n_test_splits (default: 2)",
    )
    parser.add_argument(
        "--train-window", type=int, default=3,
        help="Walk-forward train window in years (default: 3)",
    )
    parser.add_argument(
        "--test-window", type=int, default=1,
        help="Walk-forward test window in years (default: 1)",
    )
    parser.add_argument(
        "--dynamic-universe", action="store_true",
        help="Enable DynamicUniverseSelector for per-rebalance filtering",
    )
    parser.add_argument(
        "--symbol-count", type=int, default=30,
        help="Top N symbols for static or dynamic universe (default: 30)",
    )
    parser.add_argument(
        "--quick-mode", action="store_true",
        help="Reduce folds and symbol count for faster iteration",
    )
    parser.add_argument(
        "--output-tag", default="",
        help="Suffix tag for output file names",
    )
    parser.add_argument(
        "--embargo-pct", type=float, default=0.01,
        help="CPCV embargo fraction (default: 0.01)",
    )
    parser.add_argument(
        "--label-horizon", type=int, default=60,
        help="CPCV label horizon in bars (default: 60)",
    )
    parser.add_argument(
        "--workers", type=int, default=0,
        help="Max parallel fold workers (0=auto, 1=serial, default: 0)",
    )
    parser.add_argument(
        "--alpha-group", type=str, default=None,
        help="Alpha group to track explicitly for ablation diagnostics "
             "(e.g. 'hybrid_regime'). When set, produces an alpha improvement "
             "diagnostic JSON with REALIZED gross/TC/net from 45-fold CPCV.",
    )
    parser.add_argument(
        "--model-type", choices=["ridge", "lightgbm"], default="lightgbm",
        help="Alpha blending model type (default: lightgbm)",
    )
    parser.add_argument(
        "--hmm-reentry-threshold", type=float, default=0.6,
        help="Block drawdown re-entry while HMM bear prob exceeds this threshold (default: 0.6)",
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Number of top assets to select in concentrated overlay (default: 5)",
    )
    return parser.parse_args()


def apply_quick_mode_overrides(args: argparse.Namespace) -> None:
    args.folds = min(args.folds, 5)
    args.n_test_folds = min(args.n_test_folds, 1)
    args.symbol_count = min(args.symbol_count, 10)
    logger.info(
        "Quick mode: folds=%d, n_test=%d, symbols=%d",
        args.folds, args.n_test_folds, args.symbol_count,
    )


def load_raw_data(start_date: str, end_date: str) -> pd.DataFrame:
    raw_df = pd.read_parquet(REPO_ROOT / DEFAULT_DATA_PATH)
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    mask = (raw_df["date"] >= start_date) & (raw_df["date"] <= end_date)
    filtered = raw_df[mask].copy()
    logger.info(
        "Loaded %d rows, %d tickers, date range %s to %s",
        len(filtered),
        filtered["ticker"].nunique(),
        filtered["date"].min().date(),
        filtered["date"].max().date(),
    )
    return filtered


def prepare_panel(raw_df: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    panel = raw_df[raw_df["ticker"].isin(tickers)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel = panel.rename(columns={"ticker": "symbol"})
    panel["returns"] = panel.groupby("symbol")["close"].pct_change()
    # Vectorized ADV (Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621):
    # Native groupby.rolling without lambda callback (avoids slow Python dispatch)
    panel["adv_vnd"] = (
        panel.groupby("symbol")["volume"]
        .rolling(20, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
    ) * panel["close"]
    return panel


def select_static_universe(df: pd.DataFrame, top_n: int) -> List[str]:
    return df.groupby("ticker")["volume"].sum().nlargest(top_n).index.tolist()


def build_dynamic_schedule(
    raw_df: pd.DataFrame,
    symbol_count: int,
    start_date: str,
    end_date: str,
) -> Tuple[Dict[str, List[str]], List[Dict]]:
    selector = DynamicUniverseSelector(
        lookback_days=WARMUP_TRADING_DAYS,
        rebalance_days=21,
        top_n=symbol_count,
        min_history_days=60,
    )
    schedule, evidence = selector.build_dynamic_universe_schedule(
        raw_df,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
    )
    logger.info(
        "Dynamic universe: %d rebalance dates, avg %.1f symbols/rebalance",
        len(schedule),
        np.mean([len(v) for v in schedule.values()]) if schedule else 0,
    )
    return schedule, evidence


PRECOMPUTED_FEATURES_PATH = "data/precomputed_alpha_features.parquet"


def generate_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Generate features by merging precomputed alphas with panel data.

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

    Loads precomputed alpha features from data/precomputed_alpha_features.parquet
    and merges them (left join) with the panel.  For any alpha_latent_ae_XX
    column, copies to latent_ae_XX for backward compatibility with overlays
    and the GMM regime model.

    Falls back to the original UnifiedFeatureAdapter path if the precomputed
    file does not exist.
    """
    precomputed_path = REPO_ROOT / PRECOMPUTED_FEATURES_PATH

    if precomputed_path.exists():
        logger.info("Loading precomputed alpha features from %s", precomputed_path)
        precomp_df = pd.read_parquet(precomputed_path)
        precomp_df["date"] = pd.to_datetime(precomp_df["date"])

        # Identify alpha columns and latent columns to merge
        alpha_cols = [c for c in precomp_df.columns if c.startswith("alpha_")]
        latent_ae_alpha_cols = [c for c in alpha_cols if c.startswith("alpha_latent_ae_")]
        logger.info(
            "Precomputed features: %d alpha columns, %d latent AE alpha columns",
            len(alpha_cols), len(latent_ae_alpha_cols),
        )

        # Merge alpha columns (left join to panel)
        merge_cols = ["date", "symbol"] + alpha_cols
        available_merge = [c for c in merge_cols if c in precomp_df.columns]
        panel = panel.merge(precomp_df[available_merge], on=["date", "symbol"], how="left")

        # Copy alpha_latent_ae_XX → latent_ae_XX for compatibility
        for ae_col in latent_ae_alpha_cols:
            compat_name = ae_col.replace("alpha_", "", 1)  # alpha_latent_ae_00 → latent_ae_00
            if compat_name not in panel.columns:
                panel[compat_name] = panel[ae_col]

        feat_df = panel.copy()
    else:
        logger.warning(
            "Precomputed features not found at %s — falling back to "
            "UnifiedFeatureAdapter (slower path)", precomputed_path,
        )
        panel_mi = panel.set_index(["date", "symbol"]).sort_index()
        adapter = UnifiedFeatureAdapter(
            use_arsenal=True,
            use_alt_features=True,
            use_alt_data=True,
            use_llm_synth=False,
        )
        feat_panel = adapter.generate_all(panel_mi)

        # Load latent AE components separately (not part of adapter interface)
        latent_ae_path = REPO_ROOT / LATENT_AE_PATH
        if latent_ae_path.exists():
            try:
                latent_df = pd.read_parquet(latent_ae_path)
                latent_cols = [c for c in latent_df.columns if c.startswith("latent_ae_")]
                if latent_cols and "date" in latent_df.columns:
                    symbol_col = "symbol" if "symbol" in latent_df.columns else "ticker"
                    if symbol_col in latent_df.columns:
                        latent_mi = latent_df[["date", symbol_col] + latent_cols].set_index(
                            ["date", symbol_col]
                        )
                        latent_mi.index.names = ["date", "symbol"]
                        new_cols = [c for c in latent_cols if c not in feat_panel.columns]
                        if new_cols:
                            feat_panel = feat_panel.join(latent_mi[new_cols], how="left")
                            logger.info("Latent AE: +%d columns from %s", len(new_cols), latent_ae_path)
            except Exception as exc:
                logger.warning("Latent AE loading failed: %s", exc)

        feat_df = feat_panel.reset_index()

    float32_cols = [
        col for col in feat_df.columns
        if (col.startswith("alpha_") or col.startswith("latent_ae_"))
        and pd.api.types.is_float_dtype(feat_df[col])
        and feat_df[col].dtype != np.float32
    ]
    if float32_cols:
        feat_df[float32_cols] = feat_df[float32_cols].astype(np.float32)

    feat_df = feat_df.dropna(subset=["close", "volume", "returns"])
    feat_df = feat_df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return feat_df


def make_query_fn(
    feat_df: pd.DataFrame,
    dynamic_schedule: Optional[Dict[str, List[str]]] = None,
):
    """Build a query closure with O(log N) date-range lookups via pre-sorted index.

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

    Optimization strategy:
      1. Pre-sort feat_df by date and cache the numpy date values array.
      2. Each query call uses np.searchsorted on the sorted date array for
         O(log N) range finding instead of O(N) full-DataFrame boolean masking.
      3. A single contiguous iloc slice extracts the date range — no
         per-date dict lookup or pd.concat overhead.
      4. For the dynamic path, a PIT-safe active-symbol boolean mask is
         pre-computed ONCE over the full sorted panel so that each query
         call only does a date-range iloc + pre-computed mask filter.
         This eliminates the per-query rebalance-date loop entirely.

    PIT-safe: the returned closure is read-only over precomputed structures;
    no mutation of feat_df occurs. Safe for concurrent access under
    joblib threading backend, where workers share closure data read-only.
    """
    # Pre-sort feat_df by date for contiguous iloc slicing
    _feat_sorted = feat_df.sort_values("date").reset_index(drop=True)
    _date_vals = _feat_sorted["date"].values  # numpy datetime64[ns] array

    if dynamic_schedule is None:
        _empty_df = _feat_sorted.iloc[:0]

        def query(date_start, date_end, tickers=None):
            s = np.datetime64(pd.Timestamp(date_start), "ns")
            e = np.datetime64(pd.Timestamp(date_end), "ns")
            lo = np.searchsorted(_date_vals, s, side="left")
            hi = np.searchsorted(_date_vals, e, side="right")
            if lo >= hi:
                return _empty_df.reset_index(drop=True)
            result = _feat_sorted.iloc[lo:hi]
            if tickers is not None:
                result = result[result["symbol"].isin(tickers)]
            return result.reset_index(drop=True)
        return query

    # --- Dynamic path: pre-compute active-symbol mask ONCE ---
    # For each row in _feat_sorted, determine if (date, symbol) is PIT-active:
    #   active iff there exists a rebalance_date <= row.date AND
    #   row.symbol is in the active set for the latest such rebalance.
    # This is computed once; each query call just slices by date range
    # and filters on the pre-computed mask.
    _rebal_dates_sorted = sorted(pd.Timestamp(d) for d in dynamic_schedule.keys())
    _rebal_arr = np.array(_rebal_dates_sorted, dtype="datetime64[ns]")
    _rebal_map = {pd.Timestamp(d): set(syms) for d, syms in dynamic_schedule.items()}

    _sym_vals = _feat_sorted["symbol"].values
    _rb_idx_all = np.searchsorted(_rebal_arr, _date_vals, side="right")

    _active_mask = np.zeros(len(_feat_sorted), dtype=bool)
    for rb_idx in np.unique(_rb_idx_all):
        if rb_idx == 0:
            continue
        active_rebal = _rebal_dates_sorted[rb_idx - 1]
        active_syms = _rebal_map[active_rebal]
        row_mask = _rb_idx_all == rb_idx
        _active_mask[row_mask] = np.isin(_sym_vals[row_mask], list(active_syms))

    _empty_df = _feat_sorted.iloc[:0]

    def query_dynamic(date_start, date_end, tickers=None):
        """PIT-safe dynamic query with pre-computed active mask.

        Optimized (Gate: HYBRID_REGIME_BACKTEST_PERF_20260621):
        The active-symbol mask is pre-computed at construction time.
        Each query call does only: O(log N) date range searchsorted +
        O(1) iloc slice + O(K) boolean mask filter on the sub-panel.
        """
        s = np.datetime64(pd.Timestamp(date_start), "ns")
        e = np.datetime64(pd.Timestamp(date_end), "ns")
        lo = np.searchsorted(_date_vals, s, side="left")
        hi = np.searchsorted(_date_vals, e, side="right")
        if lo >= hi:
            return _empty_df.reset_index(drop=True)
        sub_mask = _active_mask[lo:hi]
        result = _feat_sorted.iloc[lo:hi][sub_mask]
        if tickers is not None:
            result = result[result["symbol"].isin(tickers)]
        return result.reset_index(drop=True)

    return query_dynamic


def build_scenario_overlays(
    capital: float,
    gmm_model: Optional[LatentGMMRegime] = None,
    hmm_params: Optional[dict] = None,
    top_k: int = 5,
    hmm_reentry_threshold: float = 0.6,
) -> Dict[str, list]:
    """Build scenario overlay stacks with optional pre-fitted models.

    Parameters
    ----------
    capital : float
        Initial capital for BoardLotRoundingOverlay.
    gmm_model : LatentGMMRegime or None
        Pre-fitted GMM model for inference-only mode (SoD-safe).
    hmm_params : dict or None
        Pre-fitted HMM parameters for inference-only mode (SoD-safe).
    top_k : int
        Number of top assets to select in concentrated overlay.
    """
    sector_file = str(REPO_ROOT / SECTOR_MAPPING_FILE)
    return {
        "Baseline": [
            RiskSizingOverlay(
                inverse_vol_sizing=True,
                confidence_scaling=True,
                regime_sizing=True,
                regime_sizing_mode="hmm",
                regime_sizing_scale=0.5,
                latent_gmm_enabled=False,
                hmm_params=hmm_params,
            ),
            SectorConcentrationOverlay(
                max_sector_exposure=0.30,
                sector_mapping_file=sector_file,
            ),
            TailControlOverlay(target_vol_ann=0.2, max_abs_weight=0.25),
            DrawdownControlOverlay(
                threshold=-0.05,
                cooldown_days=5,
                adaptive_re_entry=True,
                hmm_bear_reentry_threshold=hmm_reentry_threshold,
                bocpd_enabled=False,
            ),
            RebalanceFrequencyOverlay(
                rebalance_every_n_days=5,
                mode="fixed_interval",
            ),
            WeightSmoothingOverlay(ema_alpha=0.08),
            LongOnlyConcentratedOverlay(top_k=top_k),
            BoardLotRoundingOverlay(lot_size=100, capital_vnd=capital),
            TCostOverlay(
                cost_per_trade_bps=35.0,
                min_trade_threshold_bps=70.0,
                use_dynamic_budgeting=True,
            ),
        ],
        "Hybrid": [
            RiskSizingOverlay(
                inverse_vol_sizing=True,
                confidence_scaling=True,
                regime_sizing=True,
                regime_sizing_mode="hmm",
                regime_sizing_scale=0.5,
                latent_gmm_enabled=True,
                latent_gmm_columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"],
                latent_gmm_bear_dampening=0.15,
                latent_gmm_bull_boost=1.25,
                latent_gmm_sideways_scale=0.9,
                latent_gmm_smooth_transition=True,
                latent_gmm_smooth_transition_temp=0.1,
                gmm_model=gmm_model,
                hmm_params=hmm_params,
            ),
            SectorConcentrationOverlay(
                max_sector_exposure=0.30,
                sector_mapping_file=sector_file,
            ),
            TailControlOverlay(target_vol_ann=0.2, max_abs_weight=0.25),
            DrawdownControlOverlay(
                threshold=-0.05,
                cooldown_days=3,
                adaptive_re_entry=True,
                hmm_bear_reentry_threshold=hmm_reentry_threshold,
                bocpd_enabled=True,
                bocpd_threshold=0.50,
                bocpd_cooldown_extension=1,
                bocpd_exposure_scale=0.5,
                gmm_bull_confidence=0.25,
                gmm_partial_reentry_scale=0.50,
                gmm_reentry_cooldown_extension=2,
            ),
            RebalanceFrequencyOverlay(
                rebalance_every_n_days=5,
                mode="fixed_interval",
            ),
            WeightSmoothingOverlay(ema_alpha=0.08),
            LongOnlyConcentratedOverlay(top_k=top_k),
            BoardLotRoundingOverlay(lot_size=100, capital_vnd=capital),
            TCostOverlay(
                cost_per_trade_bps=35.0,
                min_trade_threshold_bps=70.0,
                use_dynamic_budgeting=True,
            ),
        ],
    }


def build_pipeline_config(capital: float, hmm_reentry_threshold: float = 0.6) -> dict:
    return {
        "initial_capital_vnd": capital,
        "hmm_reentry_threshold": hmm_reentry_threshold,
        "commission_buy": 0.0015,
        "commission_sell": 0.0015,
        "tax_sell": 0.0010,
        "half_spread_bps": 0.0002,
        "slippage_k": 0.1,
        "slippage_nonlinear_exp": 1.0,
        "turnover_reduction": {
            "weight_smoothing_enabled": True,
            "weight_smoothing_ema_alpha": 0.10,
            "rebalance_throttle": 0.02,
            "rebalance_frequency": "weekly",
            "rebalance_day_of_week": 0,
            "rebalance_day_of_month": None,
        },
    }


def clear_state_dir(state_dir: Path) -> None:
    if state_dir.exists():
        for f in state_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass


def precompute_prediction_lags(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute prediction lag features ONCE on the full panel.

    Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621

    PIT-safe: shift(1) only references T-1 (past), so computing on the full
    panel is safe for prediction.  Previously called per-fold inside
    ``train_fold_models()`` — redundant O(n_folds × n_rows × n_alphas) work.

    Uses single groupby over all alpha columns simultaneously (10x faster
    than per-column loop).

    Returns a DataFrame with lag columns indexed identically to feat_df.
    """
    alpha_cols = [
        c for c in feat_df.columns
        if c.startswith("alpha_") and not c.endswith("_lag1")
    ]
    if not alpha_cols:
        return pd.DataFrame(index=feat_df.index)

    full_sorted_idx = feat_df.sort_values(["symbol", "date"]).index
    feat_sorted = feat_df.loc[full_sorted_idx]
    pred_lag_df = feat_sorted.groupby("symbol")[alpha_cols].shift(1)
    pred_lag_df.columns = [f"{c}_lag1" for c in alpha_cols]
    pred_lag_df.index = full_sorted_idx
    return pred_lag_df


def precompute_close_pivot(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute close pivot table ONCE for HMM training.

    Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621

    Returns a (date × symbol) pivot of close prices.  Per-fold HMM training
    slices this by train dates instead of pivoting from scratch each time.
    """
    close_pivot = feat_df.pivot(index="date", columns="symbol", values="close")
    return close_pivot.sort_index()


def precompute_alpha_lags(feat_df: pd.DataFrame) -> List[str]:
    """Pre-compute T-1 lagged alpha features on a feature panel.

    PIT-safe: shift(1) per symbol ensures no look-ahead within the panel.

    .. deprecated::
        No longer called from ``main()`` (PIT-leak remediation, Gate:
        HYBRID_REGIME_BACKTEST_PERF_20260621).  Global precompute leaks
        held-out date values into train-date lags when CPCV produces
        non-contiguous train dates.  Retained for backward compatibility
        and direct unit testing.  Use per-fold lag computation inside
        ``train_fold_models()`` instead.

    Returns the list of lag column names added to feat_df.
    """
    alpha_cols = [
        c for c in feat_df.columns
        if c.startswith("alpha_") and not c.endswith("_lag1")
    ]
    if not alpha_cols:
        return []

    feat_sorted = feat_df.sort_values(["symbol", "date"])
    lag_cols = []
    for col in alpha_cols:
        lag_name = f"{col}_lag1"
        if lag_name not in feat_df.columns:
            feat_df[lag_name] = feat_sorted.groupby("symbol")[col].shift(1).values
        lag_cols.append(lag_name)
    return lag_cols


def train_fold_models(
    feat_df: pd.DataFrame,
    train_dates: np.ndarray,
    precomputed_lag_cols: Optional[List[str]] = None,
    pred_lag_df: Optional[pd.DataFrame] = None,
    close_pivot_full: Optional[pd.DataFrame] = None,
    model_type: str = "lightgbm",
) -> Tuple[Optional[LatentGMMRegime], Optional[dict], Optional[pd.Series]]:
    """Train Ridge blending (per GMM regime), HMM, and GMM models on train-fold data.

    PIT-safe: all models are fitted only on train_dates, never on test data.
    Alpha lag features are computed per-fold (train-only for Ridge training,
    full-panel for prediction) to eliminate the global-precompute PIT leak
    where CPCV embargo gaps caused shift(1) to reference held-out dates.
    The shared feat_df is never mutated (safe for parallel folds under threading).

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621 — dynamic blending by GMM regime.

    Dynamic blending strategy:
      1. Train HMM and GMM models first on train data.
      2. Predict GMM regime labels for the training set.
      3. Split training set by GMM regime (Bull, Sideways, Bear) and fit
         3 separate Ridge models.  Use a global fallback model if any
         regime has < 10 training samples.
      4. For composite_signal prediction, map prediction dates to GMM regimes
         and apply the corresponding Ridge model dynamically.

    Parameters
    ----------
    feat_df : DataFrame
        Full GLOBAL feature panel (train + test, entire period 2015-2026).
        Must contain 'date', 'symbol', 'returns', and alpha columns (prefix 'alpha_').
    train_dates : ndarray
        CPCV train dates (pd.Timestamp values).
    precomputed_lag_cols : list or None
        Deprecated — retained for signature backward compatibility.
        Ignored; lags are always computed per-fold inline (PIT-safe).
    pred_lag_df : DataFrame or None
        Pre-computed prediction lags from ``precompute_prediction_lags()``.
        If provided, skips redundant per-fold shift(1) on full panel.
    close_pivot_full : DataFrame or None
        Pre-computed close pivot from ``precompute_close_pivot()``.
        If provided, skips redundant per-fold pivot for HMM training.

    Returns
    -------
    gmm_model : LatentGMMRegime
        Pre-fitted GMM model on train data.
    hmm_params : dict
        Fitted HMM parameters {'pi', 'A', 'mu', 'sigma2'}.
    composite_signal : pd.Series or None
        Per-row composite_signal predictions indexed by feat_df.index.
        Returned separately to avoid writing into shared feat_df (thread-safe under threading).

    Raises
    ------
    ValueError
        If train_feat is empty, or if HMM model fitting fails.
        Halts execution immediately to prevent silent fallback to
        test-period in-sample fitting (look-ahead bias).
        GMM failures are logged as warnings (not raised) to allow
        early CPCV folds before 2024 (where latent AE data is absent)
        to execute with fallback global Ridge configurations.
    """
    train_date_set = set(pd.Timestamp(d) for d in train_dates)
    train_feat = feat_df[feat_df["date"].isin(train_date_set)]

    if train_feat.empty:
        raise ValueError(
            f"train_fold_models: train_feat is EMPTY — "
            f"none of {len(train_date_set)} train dates found in feat_df "
            f"(feat_df date range: {feat_df['date'].min()} to {feat_df['date'].max()}). "
            f"Halt to prevent silent fallback to test-period in-sample fitting."
        )

    # --- 1. HMM: train on train_feat market returns (moved before Ridge) ---
    hmm_params = None
    try:
        # Optimized (Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621):
        # Use precomputed close pivot and slice by train dates
        if close_pivot_full is not None:
            train_date_set_cp = set(pd.Timestamp(d) for d in train_dates)
            cp_mask = close_pivot_full.index.isin(train_date_set_cp)
            close_pivot = close_pivot_full[cp_mask]
        else:
            close_pivot = train_feat.pivot(index="date", columns="symbol", values="close")
            close_pivot = close_pivot.sort_index()
        market_proxy = close_pivot.mean(axis=1)
        mp_returns = market_proxy.pct_change().dropna().values

        if len(mp_returns) >= 30:
            mask = np.isfinite(mp_returns)
            clean_returns = mp_returns[mask]
            if len(clean_returns) >= 20:
                hmm = SimpleGaussianHMM(n_states=3, max_iter=30, tol=1e-4, random_state=42)
                hmm.fit(clean_returns)
                hmm_params = hmm.get_params()
                logger.info(
                    "HMM trained on %d returns, %d iterations.",
                    len(clean_returns), hmm.n_iter_,
                )
            else:
                raise ValueError(
                    f"HMM training failed: only {len(clean_returns)} clean returns "
                    f"(need >= 20) from {len(mp_returns)} total."
                )
        else:
            raise ValueError(
                f"HMM training failed: only {len(mp_returns)} market returns "
                f"(need >= 30) from {len(train_feat)} train rows."
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"HMM training failed with unexpected error: {exc}") from exc

    # --- 2. GMM: train on train_feat latent features (moved before Ridge) ---
    # Gate: HYBRID_REGIME_BACKTEST_PERF_20260621
    # GMM failures are logged as warnings (not raised) so that early CPCV
    # folds before 2024 — where latent AE data is absent — can still execute
    # using fallback GMM/Ridge configurations (gmm_model=None → all regimes
    # default to "Sideways" → global Ridge model is used).
    gmm_model = None
    try:
        latent_cols = ["latent_ae_00", "latent_ae_01", "latent_ae_11"]
        available_latent = [c for c in latent_cols if c in train_feat.columns]
        if not available_latent:
            logger.warning(
                "GMM training skipped: no latent columns found in train_feat. "
                "Expected at least one of %s. "
                "Falling back to global Ridge (all regimes → Sideways).",
                latent_cols,
            )
        else:
            gmm_config = LatentGMMConfig(
                n_components=3,
                latent_columns=available_latent,
                bear_dampening=0.5,
                bull_boost=1.1,
                sideways_scale=0.9,
            )
            gmm_model = LatentGMMRegime(gmm_config)
            gmm_model.fit(train_feat)
            if gmm_model.is_fitted:
                logger.info("GMM trained on %d train samples.", len(train_feat))
            else:
                logger.warning(
                    "GMM fit did not produce a fitted model "
                    "(train_feat has %d rows, latent cols: %s). "
                    "Falling back to global Ridge (all regimes → Sideways).",
                    len(train_feat), available_latent,
                )
                gmm_model = None
    except Exception as exc:
        logger.warning(
            "GMM training failed with error: %s. "
            "Falling back to global Ridge (all regimes → Sideways).",
            exc,
        )
        gmm_model = None

    # --- 3. Alpha blending with dynamic GMM-regime blending ---
    # PIT-safe: training lags per-fold from train-only data.
    # Prediction lags from full panel (shift(1) is backward-only, PIT-safe).
    #
    # Dynamic blending (Gate: HYBRID_REGIME_BACKTEST_PERF_20260621):
    #   - Predict GMM regime labels for training set dates.
    #   - Split train Ridge data by regime (Bull, Sideways, Bear).
    #   - Fit 3 separate Ridge models (one per regime).
    #   - Global fallback model trained on all train data for regimes with < 10 samples.
    #   - For prediction: map each row's date to its GMM regime, then apply
    #     the corresponding Ridge model.
    composite_signal = None
    model_type = model_type.lower()
    if model_type == "lightgbm" and LGBMRegressor is None:
        raise ImportError("lightgbm is required for --model-type lightgbm")

    def _new_alpha_model():
        if model_type == "lightgbm":
            return LGBMRegressor(
                n_estimators=100,
                learning_rate=0.03,
                num_leaves=15,
                min_child_samples=10,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                n_jobs=1,
                verbosity=-1,
            )
        return Ridge(alpha=1.0)

    def _feature_values(df: pd.DataFrame) -> np.ndarray:
        values = df[lag_col_names].values
        if model_type == "ridge":
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        return values

    all_alpha_cols = [
        c for c in train_feat.columns
        if c.startswith("alpha_") and not c.endswith("_lag1")
    ]
    if all_alpha_cols and "returns" in train_feat.columns:
        # (a) Training lags: per-symbol shift(1) on train-only data
        train_sorted = train_feat.sort_values(["symbol", "date"])
        train_lag_df = train_sorted.groupby("symbol")[all_alpha_cols].shift(1)
        train_lag_df.columns = [f"{c}_lag1" for c in all_alpha_cols]
        train_lag_df.index = train_sorted.index

        # Build temporal DataFrame to calculate correlation (IC) on train set
        # Gate: HYBRID_REGIME_BACKTEST_PERF_20260621 — PIT-leak remediation:
        # NaN lag values from shift(1) must NOT be filled with 0.0 (which leaks
        # a synthetic signal into the first row of each symbol).  Instead, drop
        # the first row per symbol (where shift(1) produces NaN) and then
        # dropna on returns to ensure clean training data.
        temp_train = train_sorted[["returns", "date"]].copy()
        lag_col_names_all = [f"{c}_lag1" for c in all_alpha_cols]
        # Optimized (Gate: HYBRID_REGIME_OOM_FIX_20260624): attach the lag block
        # in one concat to avoid repeated column inserts and extra copies.
        if lag_col_names_all:
            temp_train = pd.concat(
                [temp_train, train_lag_df[lag_col_names_all]],
                axis=1,
            )  # keep NaN — do NOT fillna(0.0)

        # Drop first row per symbol where shift(1) produces NaN lags (PIT-safe)
        first_row_indices = train_sorted.groupby("symbol").head(1).index
        temp_train = temp_train.drop(index=first_row_indices, errors="ignore")
        temp_train = temp_train.dropna(subset=["returns"])

        # Calculate absolute correlation (IC) for each alpha feature
        alpha_ics = {}
        if len(temp_train) > 10:
            y_vals = temp_train["returns"].values
            # Compute correlation with target
            for lc in lag_col_names_all:
                x_vals = temp_train[lc].values
                mask = np.isfinite(x_vals) & np.isfinite(y_vals)
                # Avoid constant feature correlation warnings
                if np.nanstd(x_vals) > 1e-9 and np.nanstd(y_vals) > 1e-9 and mask.sum() > 1:
                    corr = np.corrcoef(x_vals[mask], y_vals[mask])[0, 1]
                    if not np.isnan(corr):
                        alpha_ics[lc] = corr

        # Quota-based alpha selection (Gate: HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623)
        # Select top 2 alphas by absolute IC from each of 4 categories to
        # diversify inputs and improve realization yields vs. single-block Top-K.
        #   HR  : alpha_hr_*
        #   GP  : alpha_gp_*
        #   LLM : alpha_llm_*
        #   VN  : alpha_vn_* | alpha_stock_* | alpha_macro_*
        # Max 8 alphas (2 per category). Falls back to global Top-K if no
        # category alpha has a finite IC.
        QUOTA_PER_CATEGORY = 2
        CATEGORY_PREFIXES = {
            "HR": ("alpha_hr_",),
            "GP": ("alpha_gp_",),
            "LLM": ("alpha_llm_",),
            "VN": ("alpha_vn_", "alpha_stock_", "alpha_macro_"),
        }

        def _category_of(alpha_name: str) -> Optional[str]:
            for cat, prefixes in CATEGORY_PREFIXES.items():
                if any(alpha_name.startswith(p) for p in prefixes):
                    return cat
            return None

        selected_lag_cols: List[str] = []
        used_categories: Dict[str, int] = {}
        categorized_alphas: Dict[str, List[str]] = {cat: [] for cat in CATEGORY_PREFIXES}
        for lc in lag_col_names_all:
            alpha_name = lc.replace("_lag1", "")
            cat = _category_of(alpha_name)
            if cat is None or lc not in alpha_ics:
                continue
            categorized_alphas[cat].append(lc)

        for cat, lc_list in categorized_alphas.items():
            lc_list.sort(key=lambda c: abs(alpha_ics[c]), reverse=True)
            selected_lag_cols.extend(lc_list[:QUOTA_PER_CATEGORY])
            used_categories[cat] = min(len(lc_list), QUOTA_PER_CATEGORY)

        # Fallback: if quota selection yielded zero alphas (e.g. legacy
        # fixtures with only non-categorized alphas), fall back to global
        # absolute-IC Top-K so existing tests and edge cases still train Ridge.
        FALLBACK_TOP_K = 7
        if not selected_lag_cols:
            sorted_ics = pd.Series(alpha_ics).abs().sort_values(ascending=False)
            selected_lag_cols = sorted_ics.index[:FALLBACK_TOP_K].tolist()
            if not selected_lag_cols:
                selected_lag_cols = lag_col_names_all[:FALLBACK_TOP_K]

        alpha_cols = [lc.replace("_lag1", "") for lc in selected_lag_cols]
        lag_col_names = selected_lag_cols

        logger.info(
            "Quota Feature Selection: %d alphas across %d categories "
            "(HR=%d, GP=%d, LLM=%d, VN=%d). Top-3 absolute ICs: %s",
            len(lag_col_names), len(used_categories),
            used_categories.get("HR", 0), used_categories.get("GP", 0),
            used_categories.get("LLM", 0), used_categories.get("VN", 0),
            {k: f"{alpha_ics.get(k, 0.0):.4f}" for k in lag_col_names[:3]}
            if lag_col_names else {},
        )

        # Build Ridge training matrix using ONLY the selected alpha features
        # Optimized (Gate: HYBRID_REGIME_OOM_FIX_20260624): build the selected
        # training matrix in one concat to avoid repeated block growth.
        ridge_train = temp_train[["returns", "date"]].copy()
        if lag_col_names:
            ridge_train = pd.concat(
                [ridge_train, temp_train[lag_col_names]],
                axis=1,
            )
        drop_cols = ["returns"] if model_type == "lightgbm" else ["returns"] + lag_col_names
        ridge_train = ridge_train.dropna(subset=drop_cols)
        
        if len(ridge_train) > 10:
            X_train = _feature_values(ridge_train)
            y_train = ridge_train["returns"].values

            # --- Predict GMM regime labels for training dates ---
            train_regime_map = {}
            if gmm_model is not None and gmm_model.is_fitted:
                try:
                    avail_latent = [c for c in latent_cols if c in train_feat.columns]
                    if avail_latent:
                        date_latent = (
                            train_feat.groupby("date")[avail_latent]
                            .mean()
                            .sort_index()
                        )
                        labels_arr, _ = gmm_model.predict_regime(date_latent)
                        train_regime_map = dict(zip(date_latent.index, labels_arr))
                        logger.info(
                            "GMM regime labels predicted for %d train dates. "
                            "Distribution: %s",
                            len(train_regime_map),
                            {k: int(v) for k, v in pd.Series(list(train_regime_map.values())).value_counts().items()},
                        )
                except Exception as exc:
                    logger.warning("GMM regime prediction on train set failed: %s", exc)
                    train_regime_map = {}

            # --- Map training rows to GMM regimes ---
            ridge_train["gmm_regime"] = ridge_train["date"].map(train_regime_map).fillna("Sideways")

            # --- Fit global fallback model (all train data) ---
            global_model = _new_alpha_model()
            global_model.fit(X_train, y_train)

            # --- Fit per-regime models ---
            regime_models: Dict[str, Any] = {}
            regime_names = ["Bull", "Sideways", "Bear"]
            for regime_name in regime_names:
                regime_mask = ridge_train["gmm_regime"] == regime_name
                n_regime = regime_mask.sum()
                if n_regime >= 10:
                    regime_model = _new_alpha_model()
                    regime_model.fit(
                        _feature_values(ridge_train.loc[regime_mask]),
                        ridge_train.loc[regime_mask, "returns"].values,
                    )
                    regime_models[regime_name] = regime_model
                    logger.info(
                        "%s [%s]: trained on %d samples", model_type, regime_name, n_regime,
                    )
                else:
                    # Use global fallback for under-represented regimes
                    regime_models[regime_name] = global_model
                    logger.info(
                        "%s [%s]: using global fallback (%d samples < 10)",
                        model_type, regime_name, n_regime,
                    )

            # (b) Prediction: compute lags and predict using regime-specific models.
            # LightGBM preserves NaN lag features; Ridge-compatible models still
            # receive imputed features through _feature_values().
            if pred_lag_df is not None:
                pred_indices = pred_lag_df.index
                pred_X = _feature_values(pred_lag_df)

                # Map prediction rows to GMM regimes
                pred_regime_labels = _map_rows_to_gmm_regimes(
                    feat_df, pred_indices, gmm_model, latent_cols,
                )

                # Apply regime-specific Ridge models
                composite_values = np.zeros(len(pred_indices))
                for regime_name in regime_names:
                    regime_mask_local = pred_regime_labels == regime_name
                    if regime_mask_local.any():
                        model = regime_models.get(regime_name, global_model)
                        composite_values[regime_mask_local] = model.predict(
                            pred_X[regime_mask_local]
                        )

                composite_signal = pd.Series(
                    composite_values,
                    index=pred_indices,
                    name="composite_signal",
                )
            else:
                full_sorted = feat_df.sort_values(["symbol", "date"])
                pred_lag_df_local = full_sorted.groupby("symbol")[alpha_cols].shift(1)
                pred_lag_df_local.columns = [f"{c}_lag1" for c in alpha_cols]
                pred_lag_df_local.index = full_sorted.index

                pred_indices = pred_lag_df_local.index
                pred_X = _feature_values(pred_lag_df_local)

                # Map prediction rows to GMM regimes
                pred_regime_labels = _map_rows_to_gmm_regimes(
                    feat_df, pred_indices, gmm_model, latent_cols,
                )

                # Apply regime-specific Ridge models
                composite_values = np.zeros(len(pred_indices))
                for regime_name in regime_names:
                    regime_mask_local = pred_regime_labels == regime_name
                    if regime_mask_local.any():
                        model = regime_models.get(regime_name, global_model)
                        composite_values[regime_mask_local] = model.predict(
                            pred_X[regime_mask_local]
                        )

                composite_signal = pd.Series(
                    composite_values,
                    index=pred_indices,
                    name="composite_signal",
                )

            # Log regime distribution of predictions
            if composite_signal is not None:
                n_per_regime = {}
                if len(composite_signal) > 0:
                    for rn in regime_names:
                        n_per_regime[rn] = int((pred_regime_labels == rn).sum())
                logger.info(
                    "%s dynamic blending: trained %d regime models + global fallback, "
                    "predicted composite_signal for %d rows. "
                    "Regime distribution: %s",
                    model_type,
                    len(regime_models),
                    len(composite_signal),
                    n_per_regime,
                )
        else:
            logger.warning("%s blending: insufficient train data (%d rows).", model_type, len(ridge_train))

    return gmm_model, hmm_params, composite_signal


def _map_rows_to_gmm_regimes(
    feat_df: pd.DataFrame,
    pred_indices: np.ndarray,
    gmm_model: Optional[LatentGMMRegime],
    latent_cols: List[str],
) -> np.ndarray:
    """Map prediction row indices to GMM regime labels.

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

    For each row identified by pred_indices, determines the GMM regime
    by averaging latent features per date and calling predict_regime.
    Returns an array of regime labels ('Bull', 'Sideways', 'Bear') aligned
    with pred_indices.

    Parameters
    ----------
    feat_df : DataFrame
        Full feature panel with 'date', 'symbol', and latent columns.
    pred_indices : ndarray
        Indices into feat_df identifying prediction rows.
    gmm_model : LatentGMMRegime or None
        Pre-fitted GMM model. If None, all rows get 'Sideways'.
    latent_cols : list of str
        Latent AE column names to use for regime prediction.

    Returns
    -------
    ndarray of str
        Regime labels aligned with pred_indices.
    """
    n = len(pred_indices)
    default_labels = np.full(n, "Sideways", dtype=object)

    if gmm_model is None or not gmm_model.is_fitted:
        return default_labels

    avail_latent = [c for c in latent_cols if c in feat_df.columns]
    if not avail_latent:
        return default_labels

    try:
        # Get dates for prediction rows
        pred_dates = feat_df.loc[pred_indices, "date"].values

        # Compute per-date mean latent features (from full feat_df, not just pred rows)
        date_latent = (
            feat_df.groupby("date")[avail_latent]
            .mean()
            .sort_index()
        )
        labels_arr, _ = gmm_model.predict_regime(date_latent)
        date_to_regime = dict(zip(date_latent.index, labels_arr))

        # Map each prediction row's date to its regime
        result = np.array([
            date_to_regime.get(pd.Timestamp(d), "Sideways") for d in pred_dates
        ])
        return result
    except Exception as exc:
        logger.warning("GMM regime mapping failed: %s — using default 'Sideways'", exc)
        return default_labels


def compute_fold_profitability_diagnostics(
    weights: pd.DataFrame,
    daily_rets: np.ndarray,
    cost_breakdown: dict,
    panel: Optional[pd.DataFrame] = None,
    capital: float = 1e9,
    gmm_model: Optional["LatentGMMRegime"] = None,
) -> Dict[str, float]:
    """Compute profitability diagnostic metrics for a single fold.

    Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621

    Instrumentation only — does NOT alter any strategy/risk/overlay logic.

    Parameters
    ----------
    weights : DataFrame
        Daily portfolio weights (n_days x n_symbols).
    daily_rets : ndarray
        Post-cost daily return series.
    cost_breakdown : dict
        Transaction cost breakdown from apply_realistic_tc().
    panel : DataFrame or None
        Feature panel with 'composite_signal', 'returns', 'symbol', 'date'
        columns for alpha IC computation. If None, alpha_ic is NaN.
    capital : float
        Portfolio capital in VND for TC normalization.
    gmm_model : LatentGMMRegime or None
        Pre-fitted GMM model for regime-conditional IC. If None,
        alpha_ic_per_regime is NaN for all regimes.

    Returns
    -------
    dict with keys: gross_return, total_tc_pct, cash_days_pct,
    turnover_avg, exposure_avg, alpha_ic_overall, alpha_ic_per_regime.

    Formula
    -------
    gross_return = compound(net_returns) + total_cost
      where compound(net_returns) = prod(1 + r_t) - 1
      and total_cost = total_commission + total_spread + total_slippage
      (from cost_breakdown, as fraction of notional).
      Note: this is an approximation; exact gross would require adding
      back costs per-bar before compounding.  Settlement/halt/foreign
      drag terms are NOT included in total_cost (they are small).
    """
    w_arr = weights.to_numpy()
    T = w_arr.shape[0]
    diag = {}

    # (1) gross_return: approximate as net + total_cost
    #     net = prod(1 + r_t) - 1  (compound post-cost return)
    #     total_cost = commission + spread + slippage (fraction of notional)
    #     gross ≈ net + total_cost  (additive approx to compound gross)
    net_ret = float(np.prod(1.0 + daily_rets) - 1.0) if len(daily_rets) > 0 else 0.0
    total_cost = cost_breakdown.get("total_cost", 0.0)
    gross_return = net_ret + total_cost
    diag["gross_return"] = float(gross_return)

    # (2) total_tc_pct: total cost as fraction (already in fraction of notional)
    diag["total_tc_pct"] = float(total_cost)

    # (3) cash_days_pct: fraction of days where sum(|w|) < 0.05
    exposure_per_day = np.abs(w_arr).sum(axis=1)
    cash_days = int(np.sum(exposure_per_day < 0.05))
    diag["cash_days_pct"] = float(cash_days / T) if T > 0 else 0.0

    # (5) turnover_avg: mean daily |w_t - w_{t-1}|.sum()
    if T > 1:
        turnover_per_day = np.abs(np.diff(w_arr, axis=0)).sum(axis=1)
        diag["turnover_avg"] = float(np.mean(turnover_per_day))
    else:
        diag["turnover_avg"] = float(np.abs(w_arr).sum()) if T > 0 else 0.0

    # (6) exposure_avg: mean sum(|w|)
    diag["exposure_avg"] = float(np.mean(exposure_per_day)) if T > 0 else 0.0

    # (4) alpha_ic_overall: cross-sectional IC (correlation between signal
    # and next-day returns, averaged across dates)
    diag["alpha_ic_overall"] = float("nan")
    # (7) alpha_ic_per_regime: IC segmented by GMM regime label
    diag["alpha_ic_per_regime"] = {
        "bull": float("nan"),
        "sideways": float("nan"),
        "bear": float("nan"),
    }

    if panel is not None and "composite_signal" in panel.columns:
        try:
            # Optimized (Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621):
            # Vectorized IC computation using pivot tables instead of per-date loop.
            # Cross-sectional correlation per date computed via vectorized operations.
            panel_sorted = panel.sort_values(["symbol", "date"])
            fwd_ret = panel_sorted.groupby("symbol")["returns"].shift(-1)
            panel_with_fwd = panel_sorted.copy()
            panel_with_fwd["fwd_return"] = fwd_ret

            # Predict GMM regime labels per date (market-level)
            regime_labels = None
            if gmm_model is not None and gmm_model.is_fitted:
                try:
                    latent_cols = ["latent_ae_00", "latent_ae_01", "latent_ae_11"]
                    avail = [c for c in latent_cols if c in panel_with_fwd.columns]
                    if avail:
                        date_latent = (
                            panel_with_fwd.groupby("date")[avail]
                            .mean()
                            .sort_index()
                        )
                        labels_arr, _ = gmm_model.predict_regime(date_latent)
                        regime_labels = dict(zip(date_latent.index, labels_arr))
                except Exception:
                    regime_labels = None

            # Pivot-based IC: much faster than per-date groupby loop
            sig_pivot = panel_with_fwd.pivot(
                index="date", columns="symbol", values="composite_signal"
            )
            ret_pivot = panel_with_fwd.pivot(
                index="date", columns="symbol", values="fwd_return"
            )
            common_dates = sig_pivot.index.intersection(ret_pivot.index)

            ic_vals_all = []
            ic_by_regime = {"Bull": [], "Sideways": [], "Bear": []}

            for dt in common_dates:
                s = sig_pivot.loc[dt].dropna()
                r = ret_pivot.loc[dt].dropna()
                common_syms = s.index.intersection(r.index)
                if len(common_syms) >= 5:
                    corr = np.corrcoef(
                        s[common_syms].values, r[common_syms].values
                    )[0, 1]
                    if np.isfinite(corr):
                        ic_vals_all.append(corr)
                        if regime_labels is not None:
                            regime_label = regime_labels.get(dt, "Sideways")
                            if regime_label in ic_by_regime:
                                ic_by_regime[regime_label].append(corr)

            if ic_vals_all:
                diag["alpha_ic_overall"] = float(np.mean(ic_vals_all))

            # Populate per-regime IC (case-insensitive key output)
            for regime_key, regime_label in [
                ("bull", "Bull"),
                ("sideways", "Sideways"),
                ("bear", "Bear"),
            ]:
                vals = ic_by_regime.get(regime_label, [])
                if vals:
                    diag["alpha_ic_per_regime"][regime_key] = float(np.mean(vals))

        except Exception:
            pass

    return diag


class DiagnosticBacktestOutputHandler(BacktestOutputHandler):
    """Extended output handler that emits profitability diagnostics.

    Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621

    Wraps BacktestOutputHandler.handle() to add diagnostic metrics
    to the per-fold JSON without modifying pipeline/overlay logic.
    """

    def __init__(
        self,
        out_json: Path,
        out_csv: Path,
        panel: Optional[pd.DataFrame] = None,
        capital: float = 1e9,
        gmm_model: Optional["LatentGMMRegime"] = None,
    ):
        super().__init__(out_json, out_csv)
        self._panel = panel
        self._capital = capital
        self._gmm_model = gmm_model

    def handle(
        self,
        final_weights: pd.DataFrame,
        daily_rets: np.ndarray,
        extra_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        results = super().handle(final_weights, daily_rets, extra_stats)

        cost_breakdown = extra_stats.get("cost_breakdown", {})
        if cost_breakdown:
            diag = compute_fold_profitability_diagnostics(
                final_weights,
                daily_rets,
                cost_breakdown,
                panel=self._panel,
                capital=self._capital,
                gmm_model=self._gmm_model,
            )
            results["profitability_diag"] = diag
            logger.info(
                "Profitability diag: gross=%.2f%%, tc=%.2f%%, cash_days=%.1f%%, "
                "turnover_avg=%.4f, exposure_avg=%.4f, IC=%.4f",
                diag["gross_return"] * 100,
                diag["total_tc_pct"] * 100,
                diag["cash_days_pct"] * 100,
                diag["turnover_avg"],
                diag["exposure_avg"],
                diag["alpha_ic_overall"],
            )

        return results


def run_single_fold(
    fold_id: int,
    train_idx: np.ndarray,
    test_dates: np.ndarray,
    ts_index: pd.DatetimeIndex,
    feat_df: pd.DataFrame,
    tickers: List[str],
    capital: float,
    config: dict,
    output_tag: str,
    dynamic_schedule: Optional[Dict[str, List[str]]] = None,
    precomputed_lag_cols: Optional[List[str]] = None,
    pred_lag_df: Optional[pd.DataFrame] = None,
    close_pivot_full: Optional[pd.DataFrame] = None,
    model_type: str = "lightgbm",
    top_k: int = 5,
) -> Dict[str, Dict]:
    min_test_date = pd.Timestamp(test_dates.min())
    max_test_date = pd.Timestamp(test_dates.max())
    train_dates = ts_index[train_idx]
    warmup_start = min_test_date - pd.Timedelta(days=int(WARMUP_TRADING_DAYS * 1.5))

    # Train Ridge blending, HMM, GMM strictly on train-fold data (SoD-safe).
    # Returns composite_signal separately to avoid writing into shared feat_df.
    # Optimized (Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621):
    # Passes precomputed prediction lags and close pivot to avoid per-fold recompute.
    gmm_model, hmm_params, composite_signal = train_fold_models(
        feat_df, train_dates, precomputed_lag_cols=precomputed_lag_cols,
        pred_lag_df=pred_lag_df,
        close_pivot_full=close_pivot_full,
        model_type=model_type,
    )
    logger.info(
        "Fold %d: train models — gmm=%s, hmm_params=%s",
        fold_id,
        "fitted" if gmm_model is not None else "None",
        "available" if hmm_params is not None else "None",
    )

    # Slice test_feat from feat_df (no full copy needed — read-only slice)
    date_mask = (feat_df["date"] >= warmup_start) & (feat_df["date"] <= max_test_date)
    test_feat = feat_df[date_mask].copy()

    # Inject per-fold composite_signal into test_feat (thread-safe under threading)
    if composite_signal is not None:
        common_idx = test_feat.index.intersection(composite_signal.index)
        test_feat.loc[common_idx, "composite_signal"] = composite_signal.loc[common_idx]

    if test_feat.empty:
        raise ValueError(
            f"Fold {fold_id}: test_feat is EMPTY after filtering feat_df "
            f"for [{warmup_start.date()}, {max_test_date.date()}]. "
            f"feat_df range: [{feat_df['date'].min().date()}, {feat_df['date'].max().date()}]."
        )

    # Verify composite_signal is present and varying in test_feat
    if "composite_signal" in test_feat.columns:
        cs = test_feat["composite_signal"].dropna()
        cs_nunique = cs.nunique() if len(cs) > 0 else 0
        logger.info(
            "Fold %d: composite_signal present — %d non-NaN rows, %d unique values, "
            "mean=%.6f, std=%.6f",
            fold_id, len(cs), cs_nunique,
            cs.mean() if len(cs) > 0 else float("nan"),
            cs.std() if len(cs) > 1 else float("nan"),
        )
        if cs_nunique <= 1:
            logger.warning(
                "Fold %d: composite_signal has <= 1 unique value (%d) — "
                "Ridge blending may have degenerated to constant.",
                fold_id, cs_nunique,
            )
    else:
        logger.warning(
            "Fold %d: composite_signal NOT found in test_feat columns. "
            "Ridge blending was skipped (insufficient alpha features or train data).",
            fold_id,
        )

    logger.info(
        "Fold %d: warmup=%s, test=[%s, %s], test_feat=%d rows, %d symbols",
        fold_id,
        warmup_start.date(),
        min_test_date.date(),
        max_test_date.date(),
        len(test_feat),
        test_feat["symbol"].nunique(),
    )

    # Build per-fold scenario overlays with pre-fitted models (inference-only on test)
    scenarios = build_scenario_overlays(
        capital,
        gmm_model=gmm_model,
        hmm_params=hmm_params,
        top_k=top_k,
        hmm_reentry_threshold=float(config.get("hmm_reentry_threshold", 0.6)),
    )

    query = make_query_fn(test_feat, dynamic_schedule)
    feature_store = DatabaseFeatureStoreAdapter(query)

    # Per-fold state directory to avoid cross-fold I/O conflicts (process isolation)
    fold_state_dir = REPO_ROOT / STATE_DIR / f"fold_{fold_id}"
    state_manager = PipelineStateManager(fold_state_dir)
    results = {}
    tag_suffix = f"_{output_tag}" if output_tag else ""

    for scenario_name, overlays in scenarios.items():
        clear_state_dir(fold_state_dir)

        out_json = REPO_ROOT / OUTPUT_DIR / f"hybrid_fold{fold_id}_{scenario_name}{tag_suffix}.json"
        out_csv = REPO_ROOT / OUTPUT_DIR / f"hybrid_fold{fold_id}_{scenario_name}_eq{tag_suffix}.csv"
        # Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621 — diagnostic handler
        output_handler = DiagnosticBacktestOutputHandler(
            out_json, out_csv, panel=test_feat, capital=capital,
            gmm_model=gmm_model,
        )

        pipeline = TradingPipelineV2(
            feature_store=feature_store,
            state_manager=state_manager,
            output_handler=output_handler,
            overlays=overlays,
            config=config,
        )

        run_id = f"hybrid_fold{fold_id}_{scenario_name}"
        start_time = time.time()
        try:
            res = pipeline.execute(
                run_id=run_id,
                date_start=str(min_test_date.date()),
                date_end=str(max_test_date.date()),
                tickers=tickers,
                active_dates=pd.DatetimeIndex(test_dates),
            )
            elapsed = time.time() - start_time
            results[scenario_name] = {
                "total_return": res["total_return"],
                "annualized_sharpe": res["annualized_sharpe"],
                "max_drawdown": res["max_drawdown"],
                "n_days": res["n_days"],
                "elapsed_sec": elapsed,
                "profitability_diag": res.get("profitability_diag", {}),
            }
            logger.info(
                "  Fold %d (%s): Return=%.2f%%, Sharpe=%.4f, MaxDD=%.2f%% (%.1fs)",
                fold_id, scenario_name,
                res["total_return"] * 100,
                res["annualized_sharpe"],
                res["max_drawdown"] * 100,
                elapsed,
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            logger.exception("Fold %d (%s) failed", fold_id, scenario_name)
            results[scenario_name] = {"error": str(exc), "elapsed_sec": elapsed}

    gc.collect()

    return results


def aggregate_fold_results(
    all_fold_results: List[Dict[str, Dict]],
) -> Dict[str, Dict]:
    scenario_names = set()
    for fold_res in all_fold_results:
        scenario_names.update(fold_res.keys())

    aggregated = {}
    for name in sorted(scenario_names):
        sharpes, max_dds, returns, n_days_list = [], [], [], []
        errors = 0
        for fold_res in all_fold_results:
            r = fold_res.get(name, {})
            if "error" in r:
                errors += 1
                continue
            sharpes.append(r["annualized_sharpe"])
            max_dds.append(r["max_drawdown"])
            returns.append(r["total_return"])
            n_days_list.append(r["n_days"])

        if not sharpes:
            aggregated[name] = {"error": "all_folds_failed", "n_errors": errors}
            continue

        aggregated[name] = {
            "mean_sharpe": float(np.mean(sharpes)),
            "std_sharpe": float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0,
            "median_sharpe": float(np.median(sharpes)),
            "mean_max_dd": float(np.mean(max_dds)),
            "worst_max_dd": float(np.min(max_dds)),
            "mean_return": float(np.mean(returns)),
            "median_return": float(np.median(returns)),
            "mean_n_days": float(np.mean(n_days_list)),
            "n_folds_completed": len(sharpes),
            "n_folds_errored": errors,
            "per_fold_sharpe": sharpes,
            "per_fold_max_dd": max_dds,
            "per_fold_return": returns,
        }

        # Aggregate profitability diagnostics (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621)
        diag_keys = [
            "gross_return", "total_tc_pct", "cash_days_pct",
            "turnover_avg", "exposure_avg", "alpha_ic_overall",
        ]
        regime_keys = ["bull", "sideways", "bear"]
        diag_arrays = {k: [] for k in diag_keys}
        regime_arrays = {k: [] for k in regime_keys}
        for fold_res in all_fold_results:
            r = fold_res.get(name, {})
            diag = r.get("profitability_diag", {})
            if diag:
                for k in diag_keys:
                    v = diag.get(k, float("nan"))
                    if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
                        diag_arrays[k].append(float(v))
                # Collect per-regime IC (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621 FIX)
                ic_regime = diag.get("alpha_ic_per_regime", {})
                if isinstance(ic_regime, dict):
                    for rk in regime_keys:
                        v = ic_regime.get(rk, float("nan"))
                        if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
                            regime_arrays[rk].append(float(v))

        diag_agg = {}
        for k in diag_keys:
            vals = diag_arrays[k]
            if vals:
                diag_agg[f"mean_{k}"] = float(np.mean(vals))
                diag_agg[f"median_{k}"] = float(np.median(vals))
                diag_agg[f"min_{k}"] = float(np.min(vals))
                diag_agg[f"max_{k}"] = float(np.max(vals))
                diag_agg[f"per_fold_{k}"] = vals
            else:
                diag_agg[f"mean_{k}"] = float("nan")

        # Aggregate per-regime IC (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621 FIX)
        ic_regime_agg = {}
        for rk in regime_keys:
            vals = regime_arrays[rk]
            if vals:
                ic_regime_agg[rk] = {
                    "mean_ic": float(np.mean(vals)),
                    "std_ic": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
                    "n_folds": len(vals),
                    "per_fold_ic": vals,
                }
            else:
                ic_regime_agg[rk] = {"mean_ic": float("nan"), "n_folds": 0}
        diag_agg["alpha_ic_per_regime"] = ic_regime_agg

        aggregated[name]["profitability_diag"] = diag_agg
    return aggregated


def print_comparison_table(aggregated: Dict[str, Dict], args: argparse.Namespace) -> None:
    print("\n" + "=" * 100)
    print("HYBRID GMM-BOCPD WALK-FORWARD CPCV REPORT")
    print(f"Period: {args.start_date} to {args.end_date} | "
          f"Folds: CPCV({args.folds},{args.n_test_folds}) | "
          f"Dynamic Universe: {args.dynamic_universe} | "
          f"Symbols: {args.symbol_count}")
    print("=" * 100)
    hdr = (f"| {'Scenario':<20} | {'Mean Sharpe':<12} | {'Std Sharpe':<11} | "
           f"{'Mean Return':<12} | {'Mean MaxDD':<11} | {'Folds':<6} |")
    print(hdr)
    sep = f"| {'-' * 20} | {'-' * 12} | {'-' * 11} | {'-' * 12} | {'-' * 11} | {'-' * 6} |"
    print(sep)
    for name, agg in aggregated.items():
        if "error" in agg:
            print(f"| {name:<20} | {'ERROR':<12} | {'-':<11} | {'-':<12} | {'-':<11} | {agg.get('n_errors', '?'):<6} |")
        else:
            print(
                f"| {name:<20} "
                f"| {agg['mean_sharpe']:+.4f}{'':<7} "
                f"| {agg['std_sharpe']:.4f}{'':<6} "
                f"| {agg['mean_return'] * 100:+.2f}%{'':<6} "
                f"| {agg['mean_max_dd'] * 100:.2f}%{'':<6} "
                f"| {agg['n_folds_completed']:<6} |"
            )
    print("=" * 100 + "\n")

    # Print profitability diagnostic summary (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621)
    print("PROFITABILITY DIAGNOSTICS (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621)")
    print("-" * 100)
    diag_hdr = (f"| {'Scenario':<20} | {'Gross Ret%':<11} | {'TC%':<8} | "
                f"{'Cash Days%':<11} | {'TO Avg':<8} | {'Expo Avg':<9} | {'IC':<8} |")
    print(diag_hdr)
    diag_sep = (f"| {'-' * 20} | {'-' * 11} | {'-' * 8} | "
                f"{'-' * 11} | {'-' * 8} | {'-' * 9} | {'-' * 8} |")
    print(diag_sep)
    for name, agg in aggregated.items():
        diag = agg.get("profitability_diag", {})
        if diag and not np.isnan(diag.get("mean_gross_return", float("nan"))):
            print(
                f"| {name:<20} "
                f"| {diag.get('mean_gross_return', 0) * 100:>+10.2f}% "
                f"| {diag.get('mean_total_tc_pct', 0) * 100:>7.2f}% "
                f"| {diag.get('mean_cash_days_pct', 0) * 100:>10.1f}% "
                f"| {diag.get('mean_turnover_avg', 0):>8.4f} "
                f"| {diag.get('mean_exposure_avg', 0):>9.4f} "
                f"| {diag.get('mean_alpha_ic_overall', float('nan')):>8.4f} |"
            )
    print("=" * 100 + "\n")

    # Print per-regime IC summary (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621 FIX)
    print("ALPHA IC PER REGIME (Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621)")
    print("-" * 100)
    reg_hdr = (f"| {'Scenario':<20} | {'IC Bull':<10} | {'IC Sideways':<12} | "
               f"{'IC Bear':<10} | {'n Bull':<7} | {'n Side':<7} | {'n Bear':<7} |")
    print(reg_hdr)
    reg_sep = (f"| {'-' * 20} | {'-' * 10} | {'-' * 12} | "
               f"{'-' * 10} | {'-' * 7} | {'-' * 7} | {'-' * 7} |")
    print(reg_sep)
    for name, agg in aggregated.items():
        diag = agg.get("profitability_diag", {})
        ic_regime = diag.get("alpha_ic_per_regime", {}) if diag else {}
        bull = ic_regime.get("bull", {})
        side = ic_regime.get("sideways", {})
        bear = ic_regime.get("bear", {})
        bull_ic = bull.get("mean_ic", float("nan"))
        side_ic = side.get("mean_ic", float("nan"))
        bear_ic = bear.get("mean_ic", float("nan"))
        bull_n = bull.get("n_folds", 0)
        side_n = side.get("n_folds", 0)
        bear_n = bear.get("n_folds", 0)
        bull_s = f"{bull_ic:+.4f}" if not np.isnan(bull_ic) else "  NaN"
        side_s = f"{side_ic:+.4f}" if not np.isnan(side_ic) else "  NaN"
        bear_s = f"{bear_ic:+.4f}" if not np.isnan(bear_ic) else "  NaN"
        print(
            f"| {name:<20} "
            f"| {bull_s:>10} "
            f"| {side_s:>12} "
            f"| {bear_s:>10} "
            f"| {bull_n:>7} "
            f"| {side_n:>7} "
            f"| {bear_n:>7} |"
        )
    print("=" * 100 + "\n")


def save_comparison_json(
    aggregated: Dict[str, Dict],
    args: argparse.Namespace,
    output_tag: str,
    total_elapsed_sec: float = 0.0,
) -> Path:
    tag_suffix = f"_{output_tag}" if output_tag else ""
    out_path = REPO_ROOT / OUTPUT_DIR / f"hybrid_regime_cpcv_comparison{tag_suffix}.json"
    payload = {
        "gate": "HYBRID_REGIME_FULL_BACKTEST_20260620",
        "perf_gate": "HYBRID_REGIME_BACKTEST_PERF_20260621",
        "diag_gate": "HYBRID_REGIME_PROFITABILITY_DIAG_20260621",
        "config": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "capital": args.capital,
            "folds": args.folds,
            "n_test_folds": args.n_test_folds,
            "embargo_pct": args.embargo_pct,
            "label_horizon": args.label_horizon,
            "dynamic_universe": args.dynamic_universe,
            "symbol_count": args.symbol_count,
            "quick_mode": args.quick_mode,
            "workers": args.workers,
        },
        "aggregated": aggregated,
        "perf": {
            "total_elapsed_sec": total_elapsed_sec,
            "total_elapsed_min": total_elapsed_sec / 60.0,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Saved comparison JSON to %s", out_path)
    return out_path


def save_alpha_improvement_real_json(
    aggregated: Dict[str, Dict],
    args: argparse.Namespace,
    feat_df: pd.DataFrame,
    total_elapsed_sec: float,
) -> Path:
    """Produce alpha_improvement_real_<ts>.json with REALIZED 45-fold CPCV numbers.

    Gate: HYBRID_REGIME_ALPHA_IMPROVEMENT_20260621 (FIX1)

    Compares Baseline vs Hybrid scenario profitability diagnostics from the
    same CPCV run to measure REALIZED gross/TC/net improvement.

    The Baseline scenario uses standard overlays (no latent GMM, no BOCPD)
    with weekly rebalancing and transaction-cost gating.
    The Hybrid scenario uses regime-aware overlays (latent GMM + BOCPD)
    with the same weekly rebalance cadence plus tuned GMM/TCost settings.
    Both share the same Ridge-blended composite_signal (all alpha groups
    including hybrid_regime).

    The REALIZED improvement = Hybrid gross - Baseline gross captures the
    combined value of regime-aware overlays applied to the alpha signals.
    """
    from omega.quant.alpha.hybrid_regime_alpha import HYBRID_REGIME_ALPHA_COLUMNS

    # Verify hybrid_regime alpha columns are present in feature panel
    hr_cols_found = [c for c in HYBRID_REGIME_ALPHA_COLUMNS if c in feat_df.columns]
    hr_cols_missing = [c for c in HYBRID_REGIME_ALPHA_COLUMNS if c not in feat_df.columns]
    logger.info(
        "Alpha group '%s': %d/%d columns found in feat_df. Missing: %s",
        args.alpha_group, len(hr_cols_found), len(HYBRID_REGIME_ALPHA_COLUMNS),
        hr_cols_missing if hr_cols_missing else "none",
    )

    baseline_agg = aggregated.get("Baseline", {})
    hybrid_agg = aggregated.get("Hybrid", {})

    # Extract per-fold gross/TC/net from profitability diagnostics
    def extract_fold_diagnostics(scenario_agg: Dict) -> Dict:
        diag = scenario_agg.get("profitability_diag", {})
        per_fold_gross = diag.get("per_fold_gross_return", [])
        per_fold_tc = diag.get("per_fold_total_tc_pct", [])
        mean_gross = diag.get("mean_gross_return", float("nan"))
        mean_tc = diag.get("mean_total_tc_pct", float("nan"))
        per_fold_return = scenario_agg.get("per_fold_return", [])

        # Compute net = gross - tc per fold
        per_fold_net = []
        for g, t in zip(per_fold_gross, per_fold_tc):
            per_fold_net.append(g - t)

        mean_net = float(np.mean(per_fold_net)) if per_fold_net else float("nan")

        return {
            "mean_gross": float(mean_gross) if not np.isnan(mean_gross) else None,
            "mean_tc": float(mean_tc) if not np.isnan(mean_tc) else None,
            "mean_net": float(mean_net) if not np.isnan(mean_net) else None,
            "per_fold_gross": [float(x) for x in per_fold_gross],
            "per_fold_tc": [float(x) for x in per_fold_tc],
            "per_fold_net": [float(x) for x in per_fold_net],
            "per_fold_return": [float(x) for x in per_fold_return],
            "n_folds": scenario_agg.get("n_folds_completed", 0),
            "mean_sharpe": scenario_agg.get("mean_sharpe", float("nan")),
            "mean_max_dd": scenario_agg.get("mean_max_dd", float("nan")),
            "mean_return": scenario_agg.get("mean_return", float("nan")),
        }

    baseline_diag = extract_fold_diagnostics(baseline_agg)
    hybrid_diag = extract_fold_diagnostics(hybrid_agg)

    # Compute REALIZED improvement
    bl_gross = baseline_diag["mean_gross"]
    hy_gross = hybrid_diag["mean_gross"]
    bl_tc = baseline_diag["mean_tc"]
    hy_tc = hybrid_diag["mean_tc"]
    bl_net = baseline_diag["mean_net"]
    hy_net = hybrid_diag["mean_net"]

    improvement_gross = (hy_gross - bl_gross) if (hy_gross is not None and bl_gross is not None) else None
    improvement_net = (hy_net - bl_net) if (hy_net is not None and bl_net is not None) else None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPO_ROOT / OUTPUT_DIR / f"alpha_improvement_real_{ts}.json"

    payload = {
        "gate": "HYBRID_REGIME_ALPHA_IMPROVEMENT_20260621",
        "fix_version": "FIX1",
        "timestamp": ts,
        "measurement_type": "REALIZED_45_FOLD_CPCV",
        "alpha_group": args.alpha_group,
        "alpha_columns": HYBRID_REGIME_ALPHA_COLUMNS,
        "alpha_columns_found": hr_cols_found,
        "alpha_columns_missing": hr_cols_missing,
        "cpcv_config": {
            "n_splits": args.folds,
            "n_test_splits": args.n_test_folds,
            "embargo_pct": args.embargo_pct,
            "label_horizon": args.label_horizon,
            "workers": args.workers,
        },
        "baseline": baseline_diag,
        "hybrid": hybrid_diag,
        "realized_improvement": {
            "gross_return_delta": improvement_gross,
            "net_return_delta": improvement_net,
        },
        "summary": {
            "baseline_mean_gross_pct": bl_gross * 100 if bl_gross is not None else None,
            "baseline_mean_tc_pct": bl_tc * 100 if bl_tc is not None else None,
            "baseline_mean_net_pct": bl_net * 100 if bl_net is not None else None,
            "hybrid_mean_gross_pct": hy_gross * 100 if hy_gross is not None else None,
            "hybrid_mean_tc_pct": hy_tc * 100 if hy_tc is not None else None,
            "hybrid_mean_net_pct": hy_net * 100 if hy_net is not None else None,
            "improvement_gross_pct": improvement_gross * 100 if improvement_gross is not None else None,
            "improvement_net_pct": improvement_net * 100 if improvement_net is not None else None,
            "target_mean_gross_pct": 8.76,
            "hybrid_target_met": (hy_gross * 100 > 8.76) if hy_gross is not None else False,
        },
        "pit_safe": True,
        "runtime": {
            "total_elapsed_sec": total_elapsed_sec,
            "total_elapsed_min": total_elapsed_sec / 60.0,
            "n_folds_total": baseline_diag["n_folds"],
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info(
        "Alpha improvement REAL JSON saved to %s — "
        "Baseline gross=%.2f%%, Hybrid gross=%.2f%%, Improvement=%.2f%%",
        out_path,
        bl_gross * 100 if bl_gross is not None else float("nan"),
        hy_gross * 100 if hy_gross is not None else float("nan"),
        improvement_gross * 100 if improvement_gross is not None else float("nan"),
    )
    return out_path


def main():
    args = parse_args()
    if args.quick_mode:
        apply_quick_mode_overrides(args)

    total_start_time = time.time()

    logger.info("=" * 60)
    logger.info("HYBRID GMM-BOCPD WALK-FORWARD CPCV BACKTEST")
    logger.info("Gate: HYBRID_REGIME_FULL_BACKTEST_20260620")
    logger.info("Perf: HYBRID_REGIME_BACKTEST_PERF_20260621")
    logger.info("Period: %s to %s", args.start_date, args.end_date)
    logger.info("CPCV: n_splits=%d, n_test=%d, embargo=%.3f",
                args.folds, args.n_test_folds, args.embargo_pct)
    logger.info("Dynamic universe: %s, Symbol count: %d",
                args.dynamic_universe, args.symbol_count)
    logger.info("=" * 60)

    raw_df = load_raw_data(args.start_date, args.end_date)

    tickers = select_static_universe(raw_df, args.symbol_count)
    logger.info("Static universe top %d tickers: %s", args.symbol_count, tickers[:10])

    dynamic_schedule = None
    dynamic_evidence = None
    if args.dynamic_universe:
        dynamic_schedule, dynamic_evidence = build_dynamic_schedule(
            raw_df, args.symbol_count, args.start_date, args.end_date,
        )
        all_dynamic_tickers = set()
        for syms in dynamic_schedule.values():
            all_dynamic_tickers.update(syms)
        tickers = sorted(all_dynamic_tickers)
        logger.info("Dynamic universe merged tickers (%d): %s",
                     len(tickers), tickers[:10])

    unique_dates = np.sort(raw_df["date"].unique())
    ts_index = pd.DatetimeIndex(unique_dates)

    # Generate feat_df for the ENTIRE period (2015-2026) ONCE before the fold loop.
    # This ensures train_feat = feat_df[feat_df['date'].isin(train_dates)] will NOT
    # be empty for early CPCV folds where train_idx points to dates far in the past.
    panel_full = prepare_panel(raw_df, tickers)
    feat_df = generate_features(panel_full)
    logger.info(
        "Global feat_df: %d rows, %d symbols, date range %s to %s",
        len(feat_df), feat_df["symbol"].nunique(),
        feat_df["date"].min().date(), feat_df["date"].max().date(),
    )
    if feat_df.empty:
        raise ValueError(
            "Global feat_df is EMPTY after feature generation. "
            "Cannot proceed with backtest."
        )

    # PIT-leak remediation (Gate: HYBRID_REGIME_BACKTEST_PERF_20260621):
    # Alpha lag features are NO LONGER pre-computed globally.
    # Global shift(1) leaks held-out date values into train-date lags when
    # CPCV produces non-contiguous train dates (embargo/purge gaps).
    # Lags are now computed per-fold inside train_fold_models():
    #   - Training lags: from train-only data (PIT-safe)
    #   - Prediction lags: from full panel per-fold (shift(1) is backward-only)
    # precompute_alpha_lags() is retained for backward compat but unused here.

    # Optimized (Gate: HYBRID_REGIME_ALGO_OPTIMIZATION_20260621):
    # Pre-compute prediction lags and close pivot ONCE before fold loop.
    # Prediction lags: shift(1) on full panel is PIT-safe for prediction.
    # Close pivot: shared across all folds for HMM training.
    pred_lag_df = precompute_prediction_lags(feat_df)
    close_pivot_full = precompute_close_pivot(feat_df)
    logger.info(
        "Pre-computed prediction lags (%d cols) and close pivot (%d dates, %d symbols)",
        len(pred_lag_df.columns),
        len(close_pivot_full),
        len(close_pivot_full.columns),
    )

    cpcv = CombinatorialPurgedKFold(
        n_splits=args.folds,
        n_test_splits=args.n_test_folds,
        embargo_pct=args.embargo_pct,
        label_horizon=args.label_horizon,
    )
    total_combinatorial_folds = cpcv.get_n_folds()
    logger.info("CPCV will generate %d combinatorial folds", total_combinatorial_folds)

    # Scenarios are now built per-fold inside run_single_fold with pre-fitted models.
    config = build_pipeline_config(args.capital, args.hmm_reentry_threshold)

    all_fold_results: List[Dict[str, Dict]] = []
    fold_counter = 0

    # Collect fold specs for parallel or serial execution
    fold_specs = []
    for fid, (train_idx, test_idx) in enumerate(cpcv.split(ts_index)):
        test_dates = ts_index[test_idx]
        if len(test_dates) == 0:
            logger.warning("CPCV fold %d: empty test set, skipping", fid)
            continue
        fold_counter += 1
        fold_specs.append({
            "fold_id": fold_counter,
            "train_idx": train_idx,
            "test_dates": test_dates,
            "ts_index": ts_index,
            "feat_df": feat_df,
            "tickers": tickers,
            "capital": args.capital,
            "config": config,
            "output_tag": args.output_tag,
            "dynamic_schedule": dynamic_schedule,
            "precomputed_lag_cols": None,  # PIT-leak fix: lags computed per-fold
            "pred_lag_df": pred_lag_df,
            "close_pivot_full": close_pivot_full,
            "model_type": args.model_type,
            "top_k": args.top_k,
        })

    # Determine worker count: 0=auto, 1=serial, >1=parallel
    n_workers = args.workers
    if n_workers == 0:
        n_workers = min(len(fold_specs), os.cpu_count() or 1, 4)
    if n_workers < 1:
        n_workers = 1

    logger.info(
        "Executing %d folds with %d worker(s) (%s mode)",
        len(fold_specs), n_workers,
        "parallel" if n_workers > 1 else "serial",
    )

    if n_workers > 1 and len(fold_specs) > 1:
        logger.info(
            "Launching joblib parallel with %d workers (loky backend, max_nbytes=10M)",
            n_workers,
        )

        def _run_fold_spec(spec):
            """Wrapper for joblib: unpacks spec dict into run_single_fold."""
            return run_single_fold(
                fold_id=spec["fold_id"],
                train_idx=spec["train_idx"],
                test_dates=spec["test_dates"],
                ts_index=spec["ts_index"],
                feat_df=spec["feat_df"],
                tickers=spec["tickers"],
                capital=spec["capital"],
                config=spec["config"],
                output_tag=spec["output_tag"],
                dynamic_schedule=spec["dynamic_schedule"],
                precomputed_lag_cols=spec["precomputed_lag_cols"],
                pred_lag_df=spec["pred_lag_df"],
                close_pivot_full=spec["close_pivot_full"],
                model_type=spec["model_type"],
                top_k=spec["top_k"],
            )

        for spec in fold_specs:
            logger.info(
                "Submitting CPCV Fold %d/%d: %d test days [%s .. %s]",
                spec["fold_id"], total_combinatorial_folds,
                len(spec["test_dates"]),
                pd.Timestamp(spec["test_dates"].min()).date(),
                pd.Timestamp(spec["test_dates"].max()).date(),
            )

        fold_results = Parallel(
            n_jobs=n_workers,
            backend="loky",
            max_nbytes="10M",
            verbose=10,
            batch_size=1,
        )(delayed(_run_fold_spec)(spec) for spec in fold_specs)

        gc.collect()

        # Rebuild in original fold_specs order — per_fold arrays are
        # now deterministic and identical to the serial path.
        for fold_res in fold_results:
            all_fold_results.append(fold_res)
    else:
        # Serial execution (original behavior)
        for spec in fold_specs:
            logger.info(
                "CPCV Fold %d/%d: %d test days [%s .. %s]",
                spec["fold_id"], total_combinatorial_folds,
                len(spec["test_dates"]),
                pd.Timestamp(spec["test_dates"].min()).date(),
                pd.Timestamp(spec["test_dates"].max()).date(),
            )
            fold_res = run_single_fold(
                fold_id=spec["fold_id"],
                train_idx=spec["train_idx"],
                test_dates=spec["test_dates"],
                ts_index=spec["ts_index"],
                feat_df=spec["feat_df"],
                tickers=spec["tickers"],
                capital=spec["capital"],
                config=spec["config"],
                output_tag=spec["output_tag"],
                dynamic_schedule=spec["dynamic_schedule"],
                precomputed_lag_cols=spec["precomputed_lag_cols"],
                pred_lag_df=spec["pred_lag_df"],
                close_pivot_full=spec["close_pivot_full"],
                model_type=spec["model_type"],
                top_k=spec["top_k"],
            )
            all_fold_results.append(fold_res)

    total_elapsed = time.time() - total_start_time

    aggregated = aggregate_fold_results(all_fold_results)
    print_comparison_table(aggregated, args)
    out_path = save_comparison_json(aggregated, args, args.output_tag, total_elapsed)

    # Gate: HYBRID_REGIME_ALPHA_IMPROVEMENT_20260621 (FIX1)
    # When --alpha-group is specified, produce REALIZED alpha improvement JSON
    if args.alpha_group:
        logger.info(
            "Alpha group '%s' specified — producing REALIZED alpha improvement diagnostic JSON",
            args.alpha_group,
        )
        alpha_improvement_path = save_alpha_improvement_real_json(
            aggregated, args, feat_df, total_elapsed,
        )
        logger.info("Alpha improvement REAL JSON: %s", alpha_improvement_path)

    logger.info(
        "Backtest complete. %d folds in %.1fs (%.1f min). Output: %s",
        len(fold_specs), total_elapsed, total_elapsed / 60, out_path,
    )
    gc.collect()
    return aggregated


if __name__ == "__main__":
    main()
