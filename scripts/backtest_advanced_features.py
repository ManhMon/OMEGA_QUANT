"""Run comparative backtests for all advanced overlays on real market data."""

import sys
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

import logging
import pandas as pd
import numpy as np
import json

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
    AdaptiveSizingOverlay,
    BlackLittermanOverlay,
    ContinuousLearningOverlay,
    DriftOverlay,
    HMMRegimeOverlay,
    RegimeAwareWFOverlay,
    RegimeOverlay,
    ThompsonSamplingWeightOverlay,
)
from omega.quant.evolution.feature_adapter import GPFeatureAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backtest_advanced_features")


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
    
    logger.info("2. Generating features (simulating offline batch features)...")
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
    
    # Save to parquet
    features_path = REPO_ROOT / "data/features_advanced_sim.parquet"
    feat_df.to_parquet(features_path)
    
    feature_store = ParquetFeatureStoreAdapter(features_path)
    state_dir = REPO_ROOT / ".ly_state/session/pipeline_state_adv"
    state_manager = PipelineStateManager(state_dir)
    
    # Define scenarios
    scenarios = {
        "0. Baseline (No overlays)": [],
        "1. Adaptive Sizing Only": [AdaptiveSizingOverlay(capital_vnd=2_000_000_000)],
        "2. Black-Litterman Only": [BlackLittermanOverlay(tau=0.05, view_confidence=0.5, l2_reg=0.01, max_weight=0.15)],
        "3. Continuous Learning Only": [ContinuousLearningOverlay(retrain_threshold_ic=0.01, retrain_lookback=40, retrain_every=20, min_train=60)],
        "4. Drift Detection Only": [DriftOverlay(lookback=40, ic_threshold=0.0, drift_exposure=0.5)],
        "5. HMM Regime Only": [HMMRegimeOverlay(bear_exposure=0.5, bull_exposure=1.1, sideways_exposure=0.8, retrain_every=30)],
        "6. Regime-Aware WF Only": [RegimeAwareWFOverlay(bear_scale=0.3, bull_scale=1.0, sideways_scale=0.7, retrain_every=30, min_train=60)],
        "7. Regime MA/Vol/DD Only": [RegimeOverlay(hysteresis_days=5, dd_threshold=-0.10)],
        "8. Thompson Sampling Only": [ThompsonSamplingWeightOverlay(lookback=20, update_every=5)],
        "9. Unified V2 (Core 6 overlays)": [
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=10.0),
            CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ],
        "10. Ultimate Suite (All compatible)": [
            AdaptiveSizingOverlay(capital_vnd=2_000_000_000),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=10.0),
            DriftOverlay(lookback=40, ic_threshold=0.0, drift_exposure=0.5),
            RegimeOverlay(hysteresis_days=5, dd_threshold=-0.10),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ]
    }
    
    results = {}
    
    for name, overlays in scenarios.items():
        logger.info("-" * 60)
        logger.info("Running Scenario: %s", name)
        logger.info("-" * 60)
        
        # Clear state directory to ensure clean run
        if state_dir.exists():
            for f in state_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
                    
        out_json = REPO_ROOT / f"data/phase35_results/adv_res_{name.replace(' ', '_').replace('.', '').replace('(', '').replace(')', '')}.json"
        out_csv = REPO_ROOT / f"data/phase35_results/adv_eq_{name.replace(' ', '_').replace('.', '').replace('(', '').replace(')', '')}.csv"
        
        output_handler = BacktestOutputHandler(out_json, out_csv)
        
        pipeline = TradingPipelineV2(
            feature_store=feature_store,
            state_manager=state_manager,
            output_handler=output_handler,
            overlays=overlays,
            config={"initial_capital_vnd": 2_000_000_000}
        )
        
        start_time = time.time()
        try:
            res = pipeline.execute(
                run_id="benchmark_run",
                date_start="2024-01-02",
                date_end=str(feat_df["date"].max().date()),
                tickers=top_tickers
            )
            elapsed = time.time() - start_time
            results[name] = {
                "total_return": res["total_return"],
                "annualized_sharpe": res["annualized_sharpe"],
                "max_drawdown": res["max_drawdown"],
                "n_days": res["n_days"],
                "elapsed_sec": elapsed
            }
            logger.info("Result for %s: Return=%.2f%%, Sharpe=%.4f, MaxDD=%.2f%% in %.1fs",
                        name, res["total_return"]*100, res["annualized_sharpe"], res["max_drawdown"]*100, elapsed)
        except Exception as e:
            logger.exception("Failed scenario: %s", name)
            results[name] = {"error": str(e)}

    # Print comparative Markdown table
    print("\n" + "=" * 70)
    print("COMPARATIVE BENCHMARK REPORT")
    print("=" * 70)
    print(f"| {'Scenario':<35} | {'Total Return':<12} | {'Sharpe':<8} | {'Max DD':<8} | {'Time (s)':<8} |")
    print(f"| {'-':-<35} | {'-':-<12} | {'-':-<8} | {'-':-<8} | {'-':-<8} |")
    for name, r in results.items():
        if "error" in r:
            print(f"| {name:<35} | {'ERROR':<12} | {'-':<8} | {'-':<8} | {'-':<8} |")
        else:
            ret_str = f"{r['total_return']*100:+.2f}%"
            sharpe_str = f"{r['annualized_sharpe']:.4f}"
            dd_str = f"{r['max_drawdown']*100:.2f}%"
            t_str = f"{r['elapsed_sec']:.1f}"
            print(f"| {name:<35} | {ret_str:<12} | {sharpe_str:<8} | {dd_str:<8} | {t_str:<8} |")
    print("=" * 70 + "\n")
    
    # Save comparison to json
    with open(REPO_ROOT / "data/phase35_results/advanced_features_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
