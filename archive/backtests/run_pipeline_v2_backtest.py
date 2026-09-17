"""Run TradingPipelineV2 Backtest on Real Market Data."""

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

import logging
import pandas as pd
import numpy as np

from omega.quant import (
    TradingPipelineV2,
    PipelineStateManager,
    ParquetFeatureStoreAdapter,
    BacktestOutputHandler,
)
from omega.quant.pipeline_v2 import (
    SmartMoneyOverlay,
    SentimentOverlay,
    ContagionOverlay,
    TCostOverlay,
    CircuitBreakerOverlay,
    TailControlOverlay,
)
from omega.quant.evolution.feature_adapter import GPFeatureAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_pipeline_v2_backtest")

REPO_ROOT = Path(__file__).resolve().parent.parent

def main():
    logger.info("1. Loading raw market data...")
    raw_df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    
    # Filter to 2024-2026 for speed and top 10 tickers by volume
    df_recent = raw_df[raw_df["date"] >= "2024-01-01"].copy()
    top_tickers = df_recent.groupby("ticker")["volume"].sum().nlargest(10).index.tolist()
    panel = df_recent[df_recent["ticker"].isin(top_tickers)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    logger.info("Selected top 10 tickers: %s", top_tickers)
    
    # Compute returns
    panel["returns"] = panel.groupby("ticker")["close"].pct_change()
    
    logger.info("2. Computing features (simulating offline batch feature generation)...")
    feat_dict = GPFeatureAdapter().compute_all(panel, top_n_features=125)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["returns"] = panel["returns"].values
    feat_df["open"] = panel["open"].values
    feat_df["high"] = panel["high"].values
    feat_df["low"] = panel["low"].values
    feat_df["close"] = panel["close"].values
    feat_df["volume"] = panel["volume"].values
    
    # ADV (20-day rolling)
    panel["adv_20"] = panel.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    feat_df["adv_vnd"] = panel["adv_20"].values * panel["close"].values
    
    # Drop NaN target/features
    valid = ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    
    # Save to simulated feature store parquet file
    features_path = REPO_ROOT / "data/features_precalculated.parquet"
    feat_df.to_parquet(features_path)
    logger.info("Saved features to simulated feature store: %s", features_path)
    
    # 3. Setup Pipeline Components
    feature_store = ParquetFeatureStoreAdapter(features_path)
    
    state_dir = REPO_ROOT / ".ly_state/session/pipeline_state"
    state_manager = PipelineStateManager(state_dir)
    
    out_json = REPO_ROOT / "data/phase35_results/pipeline_v2_backtest_results.json"
    out_csv = REPO_ROOT / "data/phase35_results/pipeline_v2_equity_curve.csv"
    output_handler = BacktestOutputHandler(out_json, out_csv)
    
    # Configure comopsable risk/cost overlays in sequence
    overlays = [
        SmartMoneyOverlay(boost_scale=0.15),
        SentimentOverlay(boost_scale=0.1),
        ContagionOverlay(lookback=20, spike_threshold_std=2.0),
        TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=10.0),
        CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
        TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
    ]
    
    pipeline = TradingPipelineV2(
        feature_store=feature_store,
        state_manager=state_manager,
        output_handler=output_handler,
        overlays=overlays,
        config={"initial_capital_vnd": 2_000_000_000}
    )
    
    # 4. Execute backtest pipeline
    logger.info("4. Running pipeline backtest...")
    date_start = "2024-01-02"
    date_end = str(feat_df["date"].max().date())
    
    results = pipeline.execute(
        run_id="real_data_run",
        date_start=date_start,
        date_end=date_end,
        tickers=top_tickers
    )
    
    logger.info("=" * 70)
    logger.info("PIPELINE V2 BACKTEST RESULTS")
    logger.info("=" * 70)
    logger.info("  Total Return:        %.2f%%", results["total_return"] * 100)
    logger.info("  Annualized Sharpe:   %.4f", results["annualized_sharpe"])
    logger.info("  Max Drawdown:        %.2f%%", results["max_drawdown"] * 100)
    logger.info("  Trading Days:        %d", results["n_days"])
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
