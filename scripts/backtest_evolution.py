#!/usr/bin/env python3
"""
Backtest Evolution Engine - Walk-Forward Validation
Validates GP alpha discovery adds value vs momentum baseline.
PIT-safe: T-1 lag, chronological split, no future data.
"""
import sys
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "quant" / "src"))

from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_evolution")

WAREHOUSE = PROJECT_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "backtest"

FEATURE_COLS = ["open", "high", "low", "close", "volume",
                "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]

def load_and_prepare_data(top_n=30):
    logger.info("Loading market data...")
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Filter to top N liquid tickers (by median volume)
    median_vol = df.groupby("ticker")["volume"].median().nlargest(top_n)
    df = df[df["ticker"].isin(median_vol.index)].copy()
    logger.info(f"Filtered to top {top_n} liquid tickers: {list(median_vol.index[:5])}...")
    df["returns_1d"] = df.groupby("ticker")["close"].pct_change(1)
    df["returns_5d"] = df.groupby("ticker")["close"].pct_change(5)
    df["vol_ratio"] = df["volume"] / (df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1)
    df["hl_range"] = (df["high"] - df["low"]) / (df["close"] + 1e-9)
    df["oc_range"] = (df["close"] - df["open"]) / (df["close"] + 1e-9)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    df["mom_20"] = df.groupby("ticker")["close"].pct_change(20)
    # Additional baselines
    df["inverse_vol"] = 1.0 / (df.groupby("ticker")["returns_1d"].transform(lambda x: x.rolling(20).std()) + 1e-9)
    df["mean_reversion"] = -(df.groupby("ticker")["close"].pct_change(5))  # contrarian
    df["equal_weight"] = 1.0  # naive equal weight (constant signal)
    # T-1 lag on all features
    for col in FEATURE_COLS:
        df[col] = df.groupby("ticker")[col].shift(1)
    df = df.dropna(subset=FEATURE_COLS + ["fwd_ret_5"])
    logger.info(f"Data ready: {len(df)} rows, {df['ticker'].nunique()} tickers, {df['date'].min().date()} to {df['date'].max().date()}")
    return df

def compute_metrics(signals, returns):
    valid = pd.DataFrame({"sig": signals, "ret": returns}).dropna()
    if len(valid) < 50:
        return {"ic": 0.0, "sharpe": 0.0, "turnover": 0.0, "max_dd": 0.0}
    ic, _ = spearmanr(valid["sig"], valid["ret"])
    if np.isnan(ic): ic = 0.0
    positions = np.sign(valid["sig"])
    strat_ret = positions * valid["ret"]
    sharpe = (strat_ret.mean() / (strat_ret.std() + 1e-9)) * np.sqrt(252)
    turnover = positions.diff().abs().mean()
    cumret = (1 + strat_ret).cumprod()
    max_dd = ((cumret / cumret.cummax()) - 1).min()
    return {"ic": round(float(ic), 4), "sharpe": round(float(sharpe), 4),
            "turnover": round(float(turnover), 4), "max_dd": round(float(max_dd), 4)}

def run_walk_forward():
    df = load_and_prepare_data()
    years = sorted(df["date"].dt.year.unique())
    test_years = [y for y in years if y >= 2017]
    results = []
    for year in test_years:
        logger.info(f"\n{'='*60}\nYear {year}: Train on <{year}, Test on {year}\n{'='*60}")
        train_df = df[df["date"].dt.year < year]
        test_df = df[df["date"].dt.year == year]
        if len(train_df) < 1000 or len(test_df) < 100:
            logger.warning(f"Skipping {year}: insufficient data")
            continue
        # Train GP
        features_train = {col: train_df[col].values for col in FEATURE_COLS}
        target_train = train_df["fwd_ret_5"].values
        config = GPConfig(population_size=50, generations=10, min_observations=500, max_depth=4)
        engine = GeneticEngine(config)
        try:
            hof = engine.evolve(features_train, target_train)
        except Exception as e:
            logger.error(f"GP failed for {year}: {e}")
            continue
        # Generate signals on test set
        features_test = {col: test_df[col].values for col in FEATURE_COLS}
        top_n = min(5, len(hof))
        if top_n == 0:
            logger.warning(f"No alphas evolved for {year}")
            continue
        ensemble_signal = np.zeros(len(test_df))
        for ind in hof[:top_n]:
            try:
                alpha = ind._execute_tree(ind.tree, features_test)
                alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
                ensemble_signal += alpha / top_n
            except Exception:
                continue
        # Baselines
        test_returns = test_df["fwd_ret_5"].values
        evo_metrics = compute_metrics(pd.Series(ensemble_signal), pd.Series(test_returns))
        base_mom = compute_metrics(pd.Series(test_df["mom_20"].values), pd.Series(test_returns))
        base_ivol = compute_metrics(pd.Series(test_df["inverse_vol"].values), pd.Series(test_returns))
        base_mr = compute_metrics(pd.Series(test_df["mean_reversion"].values), pd.Series(test_returns))
        base_ew = compute_metrics(pd.Series(test_df["equal_weight"].values), pd.Series(test_returns))
        result = {"year": int(year), "evolution": evo_metrics,
                  "baseline_mom20": base_mom, "baseline_inverse_vol": base_ivol,
                  "baseline_mean_reversion": base_mr, "baseline_equal_weight": base_ew,
                  "alpha_count": int(top_n), "train_size": int(len(train_df)), "test_size": int(len(test_df))}
        results.append(result)
        logger.info(f"  Evolution:    IC={evo_metrics['ic']:.4f} Sharpe={evo_metrics['sharpe']:.2f}")
        logger.info(f"  Mom20:        IC={base_mom['ic']:.4f} Sharpe={base_mom['sharpe']:.2f}")
        logger.info(f"  InverseVol:   IC={base_ivol['ic']:.4f} Sharpe={base_ivol['sharpe']:.2f}")
        logger.info(f"  MeanRevert:   IC={base_mr['ic']:.4f} Sharpe={base_mr['sharpe']:.2f}")
        logger.info(f"  EqualWeight:  IC={base_ew['ic']:.4f} Sharpe={base_ew['sharpe']:.2f}")
    # Summary
    print("\n" + "="*100)
    print(f"{'Year':<6} {'Evo':<10} {'Mom20':<10} {'InvVol':<10} {'MeanRev':<10} {'EqWt':<10} {'Winner'}")
    print(f"{'':6} {'Sharpe':<10} {'Sharpe':<10} {'Sharpe':<10} {'Sharpe':<10} {'Sharpe':<10}")
    print("="*100)
    for r in results:
        sharpes = {
            "EVOLUTION": r["evolution"]["sharpe"],
            "MOM20": r["baseline_mom20"]["sharpe"],
            "INV_VOL": r["baseline_inverse_vol"]["sharpe"],
            "MEAN_REV": r["baseline_mean_reversion"]["sharpe"],
            "EQ_WT": r["baseline_equal_weight"]["sharpe"]
        }
        winner = max(sharpes, key=sharpes.get)
        print(f"{r['year']:<6} {sharpes['EVOLUTION']:<10.2f} {sharpes['MOM20']:<10.2f} {sharpes['INV_VOL']:<10.2f} {sharpes['MEAN_REV']:<10.2f} {sharpes['EQ_WT']:<10.2f} {winner}")
    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "evolution_backtest_results.json", "w") as f:
        json.dump({"run_date": datetime.now().isoformat(), "results": results}, f, indent=2)
    logger.info(f"\nResults saved to {OUTPUT_DIR / 'evolution_backtest_results.json'}")
    return results

if __name__ == "__main__":
    try:
        run_walk_forward()
        sys.exit(0)
    except Exception as e:
        logger.error(f"FATAL: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
