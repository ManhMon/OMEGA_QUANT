"""Tune TradingPipelineV2 performance on the full 2015-2026 dataset."""

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
    WeightSmoothingOverlay,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tune_quant_performance")


def main():
    logger.info("Loading full feature dataset (2015-now)...")
    features_path = REPO_ROOT / "data/features_full_2015_now.parquet"
    if not features_path.exists():
        logger.error("Features file not found. Please run scripts/prepare_full_dataset.py first.")
        return
        
    feat_df = pd.read_parquet(features_path)
    feat_df["date"] = pd.to_datetime(feat_df["date"])
    
    # Extract unique tickers
    tickers = feat_df["ticker"].unique().tolist()
    logger.info("Loaded %d rows for %d tickers from %s to %s",
                len(feat_df), len(tickers), feat_df["date"].min().date(), feat_df["date"].max().date())
                
    feature_store = ParquetFeatureStoreAdapter(features_path)
    state_dir = REPO_ROOT / ".ly_state/session/pipeline_state_tune"
    state_manager = PipelineStateManager(state_dir)
    
    # 2B VND capital baseline
    capital = 2_000_000_000
    
    # 7 Scenarios to evaluate
    scenarios = {
        "0. Baseline (No overlays)": [],
        
        "1. Adaptive Sizing Only": [
            AdaptiveSizingOverlay(capital_vnd=capital)
        ],
        
        "2. Ultimate Suite (Untuned)": [
            AdaptiveSizingOverlay(capital_vnd=capital),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=10.0), # 10bps (untuned)
            CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ],
        
        "3. Tuned: High TCost Threshold": [
            AdaptiveSizingOverlay(capital_vnd=capital),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=150.0), # Increase to 150bps
            CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ],
        
        "4. Tuned: Weight Smoothing (ema=0.10)": [
            WeightSmoothingOverlay(ema_alpha=0.10), # Smooth weights first
            AdaptiveSizingOverlay(capital_vnd=capital),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=150.0),
            CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ],
        
        "5. Tuned: Heavy Smoothing & TCost (ema=0.05, threshold=200)": [
            WeightSmoothingOverlay(ema_alpha=0.05), # Stronger smoothing (95% weight retention)
            AdaptiveSizingOverlay(capital_vnd=capital),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.0),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=200.0), # 2% threshold
            CircuitBreakerOverlay(cvar_limit=-0.15, derisk_multiplier=0.7, lookback=20),
            TailControlOverlay(target_vol_ann=0.15, max_abs_weight=0.25)
        ],
        
        "6. Tuned: Institutional Elite Suite (All parameters optimized)": [
            WeightSmoothingOverlay(ema_alpha=0.03), # Ultra-smooth (97% retention)
            AdaptiveSizingOverlay(capital_vnd=capital),
            SmartMoneyOverlay(boost_scale=0.15),
            SentimentOverlay(boost_scale=0.1),
            ContagionOverlay(lookback=20, spike_threshold_std=2.5),
            TCostOverlay(cost_per_trade_bps=15.0, min_trade_threshold_bps=250.0), # 2.5% threshold
            DriftOverlay(lookback=60, ic_threshold=-0.02, drift_exposure=0.6),
            RegimeOverlay(hysteresis_days=5, dd_threshold=-0.10, bull_exposure=1.1, bear_exposure=0.6, sideways_exposure=0.8),
            CircuitBreakerOverlay(cvar_limit=-0.12, derisk_multiplier=0.5, lookback=30), # Conservative breaker
            TailControlOverlay(target_vol_ann=0.12, max_abs_weight=0.15) # Tighter target vol and individual weights
        ]
    }
    
    results = {}
    
    for name, overlays in scenarios.items():
        logger.info("-" * 80)
        logger.info("Running Scenario: %s", name)
        logger.info("-" * 80)
        
        # Clean state directory
        if state_dir.exists():
            for f in state_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
                    
        out_json = REPO_ROOT / f"data/phase35_results/tune_res_{name.replace(' ', '_').replace('.', '').replace('(', '').replace(')', '')}.json"
        out_csv = REPO_ROOT / f"data/phase35_results/tune_eq_{name.replace(' ', '_').replace('.', '').replace('(', '').replace(')', '')}.csv"
        
        output_handler = BacktestOutputHandler(out_json, out_csv)
        
        pipeline = TradingPipelineV2(
            feature_store=feature_store,
            state_manager=state_manager,
            output_handler=output_handler,
            overlays=overlays,
            config={"initial_capital_vnd": capital}
        )
        
        start_time = time.time()
        try:
            res = pipeline.execute(
                run_id="tuning_run",
                date_start=str(feat_df["date"].min().date()),
                date_end=str(feat_df["date"].max().date()),
                tickers=tickers
            )
            elapsed = time.time() - start_time
            
            # Read turnover from final JSON report (extra cost_breakdown stats)
            with open(out_json, "r") as f:
                report = json.load(f)
            
            turnover_per_bar = report.get("cost_breakdown", {}).get("avg_turnover_per_bar", 0.0)
            
            # Compute CAGR
            n_days = res["n_days"]
            years = n_days / 252.0
            tot_ret = res["total_return"]
            cagr = (1.0 + tot_ret) ** (1.0 / years) - 1.0 if tot_ret > -1.0 and years > 0 else -1.0
            
            results[name] = {
                "total_return": res["total_return"],
                "cagr": cagr,
                "annualized_sharpe": res["annualized_sharpe"],
                "max_drawdown": res["max_drawdown"],
                "avg_daily_turnover": turnover_per_bar,
                "n_days": n_days,
                "elapsed_sec": elapsed
            }
            logger.info("Result for %s: Ret=%.2f%%, CAGR=%.2f%%, Sharpe=%.4f, MaxDD=%.2f%%, Turnover=%.4f in %.1fs",
                        name, res["total_return"]*100, cagr*100, res["annualized_sharpe"], res["max_drawdown"]*100, turnover_per_bar, elapsed)
        except Exception as e:
            logger.exception("Failed scenario: %s", name)
            results[name] = {"error": str(e)}

    # Print comparative Markdown table
    print("\n" + "=" * 90)
    print("FULL 2015-2026 TUNING COMPARATIVE REPORT")
    print("=" * 90)
    print(f"| {'Scenario':<35} | {'Tot Return':<10} | {'CAGR':<8} | {'Sharpe':<7} | {'Max DD':<8} | {'Turnover':<8} | {'Time (s)':<5} |")
    print(f"| {'-':-<35} | {'-':-<10} | {'-':-<8} | {'-':-<7} | {'-':-<8} | {'-':-<8} | {'-':-<5} |")
    for name, r in results.items():
        if "error" in r:
            print(f"| {name:<35} | {'ERROR':<10} | {'-':<8} | {'-':<7} | {'-':<8} | {'-':<8} | {'-':<5} |")
        else:
            ret_str = f"{r['total_return']*100:+.1f}%" if r['total_return'] != -np.inf else "-inf%"
            cagr_str = f"{r['cagr']*100:+.1f}%" if r['cagr'] != -1.0 else "-100%"
            sharpe_str = f"{r['annualized_sharpe']:.3f}"
            dd_str = f"{r['max_drawdown']*100:.1f}%"
            turn_str = f"{r['avg_daily_turnover']*100:.2f}%"
            t_str = f"{r['elapsed_sec']:.1f}"
            print(f"| {name:<35} | {ret_str:<10} | {cagr_str:<8} | {sharpe_str:<7} | {dd_str:<8} | {turn_str:<8} | {t_str:<5} |")
    print("=" * 90 + "\n")
    
    # Save comparison to json
    with open(REPO_ROOT / "data/phase35_results/tuning_2015_now_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
