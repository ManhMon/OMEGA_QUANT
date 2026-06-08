#!/usr/bin/env python3
"""
backtest_evolution_multiseed.py - Multi-seed ensemble backtest.
Run GP with 5 different seeds per year, average predictions, evaluate.
This reduces variance and tests if Evolution adds value robustly.
"""
import sys
import json
import logging
import random
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).parent.parent
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("multiseed_backtest")
logger.setLevel(logging.INFO)

WAREHOUSE = PROJECT_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "backtest"

FEATURE_COLS = ["open", "high", "low", "close", "volume",
                "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]

NUM_SEEDS = 5

def load_and_prepare_data(top_n=30):
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    median_vol = df.groupby("ticker")["volume"].median().nlargest(top_n)
    df = df[df["ticker"].isin(median_vol.index)].copy()
    df["returns_1d"] = df.groupby("ticker")["close"].pct_change(1)
    df["returns_5d"] = df.groupby("ticker")["close"].pct_change(5)
    df["vol_ratio"] = df["volume"] / (df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1)
    df["hl_range"] = (df["high"] - df["low"]) / (df["close"] + 1e-9)
    df["oc_range"] = (df["close"] - df["open"]) / (df["close"] + 1e-9)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    df["mom_20"] = df.groupby("ticker")["close"].pct_change(20)
    for col in FEATURE_COLS:
        df[col] = df.groupby("ticker")[col].shift(1)
    df = df.dropna(subset=FEATURE_COLS + ["fwd_ret_5"])
    return df

def compute_metrics(signals, returns, dates, fwd_horizon=5, tickers=None):
    """
    Cross-sectional metrics. Daily portfolio return (avg across tickers
    per date) is built BEFORE annualizing — fixes Sharpe inflation by
    ~sqrt(N_tickers) reported in audit 2026-05-29 Round 1.

    Bug-fix Round 2 (audit 2026-05-29):
      - Bug 4: divide Sharpe by sqrt(H) to correct for H-day overlapping
        forward returns (Newey-West-style correction).
      - Bug 5: cross-sectional median demean before sign() to force daily
        long/short balance and prevent np.sign() collapse to all +1.

    Bug-fix Round 4 (audit 2026-05-29):
      - P2: per-ticker turnover. Old code averaged positions across
        tickers per date BEFORE diff, which after Bug 5 demean ≈ 0
        always (fake zero turnover). Now diff each ticker's positions
        over time, then mean |Δpos|. `tickers=None` falls back to
        portfolio-mean turnover for backward compat.
    """
    valid = pd.DataFrame({
        "sig": np.asarray(signals),
        "ret": np.asarray(returns),
        "date": pd.to_datetime(np.asarray(dates)),
    })
    if tickers is not None:
        valid["ticker"] = np.asarray(tickers)
        valid = valid.dropna(subset=["sig", "ret", "date", "ticker"])
    else:
        valid = valid.dropna(subset=["sig", "ret", "date"])
    if len(valid) < 50:
        return {"ic": 0.0, "sharpe": 0.0, "turnover": 0.0}
    ic, _ = spearmanr(valid["sig"], valid["ret"])
    if np.isnan(ic):
        ic = 0.0
    # Bug 5 fix: cross-sectional median demean before sign()
    daily_median = valid.groupby("date")["sig"].transform("median")
    positions = np.sign(valid["sig"] - daily_median)
    valid["pos"] = positions.values
    valid["strat_ret"] = positions.values * valid["ret"].values
    daily_ret = valid.groupby("date")["strat_ret"].mean().sort_index()
    if len(daily_ret) < 2 or daily_ret.std() < 1e-12:
        sharpe = 0.0
    else:
        sharpe_raw = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * np.sqrt(252)
        # Bug 4 fix: sqrt(H) Newey-West correction for H-day overlapping returns
        sharpe = sharpe_raw / np.sqrt(max(fwd_horizon, 1))
    # P2 fix: per-ticker turnover (vs old portfolio-mean which collapsed to 0)
    if tickers is not None:
        valid_sorted = valid.sort_values(["ticker", "date"])
        per_ticker_turn = valid_sorted.groupby("ticker")["pos"].diff().abs()
        turnover = float(per_ticker_turn.mean()) if len(per_ticker_turn) else 0.0
    else:
        valid_sorted = valid.sort_values(["date"])
        daily_mean_pos = valid_sorted.groupby("date")["pos"].mean()
        turnover = float(daily_mean_pos.diff().abs().mean()) if len(daily_mean_pos) > 1 else 0.0
    return {"ic": round(float(ic), 4), "sharpe": round(float(sharpe), 4),
            "turnover": round(float(turnover), 4)}

def main():
    print("="*80)
    print(f"MULTI-SEED ENSEMBLE BACKTEST (NUM_SEEDS={NUM_SEEDS})")
    print("="*80)
    df = load_and_prepare_data()
    print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
    
    years = sorted(df["date"].dt.year.unique())
    test_years = [int(y) for y in years if y >= 2017]
    results = []
    
    for year in test_years:
        print(f"\n=== Year {year} ===")
        train_df = df[df["date"].dt.year < year]
        test_df = df[df["date"].dt.year == year]
        if len(train_df) < 1000 or len(test_df) < 100:
            continue
        
        features_train = {col: train_df[col].values for col in FEATURE_COLS}
        target_train = train_df["fwd_ret_5"].values
        features_test = {col: test_df[col].values for col in FEATURE_COLS}
        test_returns = test_df["fwd_ret_5"].values
        test_dates_arr = pd.to_datetime(test_df["date"].values)
        
        # Run GP NUM_SEEDS times, ensemble predictions
        ensemble_signal = np.zeros(len(test_df))
        successful_seeds = 0
        
        for seed_idx in range(NUM_SEEDS):
            seed = 42 + seed_idx * 1000 + int(year)
            random.seed(seed)
            np.random.seed(seed)
            
            config = GPConfig(population_size=50, generations=10, min_observations=500, max_depth=4)
            engine = GeneticEngine(config)
            try:
                hof = engine.evolve(features_train, target_train)
            except Exception as e:
                logger.warning(f"  Seed {seed_idx}: GP failed: {e}")
                continue
            
            top_n = min(5, len(hof))
            if top_n == 0:
                continue
            
            seed_signal = np.zeros(len(test_df))
            included = 0
            for ind in hof[:top_n]:
                try:
                    alpha = ind._execute_tree(ind.tree, features_test)
                    alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
                    # Bug-fix (audit 2026-05-29): skip constant alphas;
                    # they collapse np.sign() to equal-weight and bias the ensemble.
                    if np.std(alpha) < 1e-6:
                        continue
                    # P3 fix (audit 2026-05-29 Round 4): tighter sign-balance
                    # guard. std<1e-6 lets through alphas with large std but
                    # uniformly positive sign (e.g., vol_ratio - 0.999). Skip
                    # if >90% of post-demean values share one sign.
                    demean_alpha = alpha - np.median(alpha)
                    nz = demean_alpha[demean_alpha != 0]
                    if len(nz) >= 10:
                        sign_balance = float(np.mean(np.sign(nz) > 0))
                        if abs(sign_balance - 0.5) > 0.4:
                            continue
                    # Bug-fix Round 1 (audit 2026-05-29): replace per-seed z-score
                    # (which destroyed directional info and zeroed the ensemble)
                    # with rank-normalize: pct rank centered at 0 in [-0.5, +0.5].
                    # Bug-fix Round 2 - Bug 6 (audit 2026-05-29): cross-sectional
                    # rank PER DATE, not global. Global rank pools all ticker-days
                    # together, leaking time information into the cross-section.
                    alpha_series = pd.Series(alpha, index=test_dates_arr)
                    alpha_ranked = alpha_series.groupby(level=0).rank(pct=True).values - 0.5
                    seed_signal += alpha_ranked
                    included += 1
                except Exception:
                    continue
            
            if included == 0:
                logger.warning(f"  Seed {seed_idx}: all alphas constant; skipping")
                continue
            seed_signal /= included
            ensemble_signal += seed_signal
            successful_seeds += 1
            print(f"  Seed {seed_idx} ({seed}): completed ({included}/{top_n} alphas kept)")
        
        if successful_seeds == 0:
            print(f"  No seeds succeeded for {year}")
            continue
        
        ensemble_signal /= successful_seeds
        
        # Baselines
        baseline_mom = test_df["mom_20"].values
        test_dates = test_df["date"].values
        test_tickers = test_df["ticker"].values
        evo_metrics = compute_metrics(pd.Series(ensemble_signal), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_metrics = compute_metrics(pd.Series(baseline_mom), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        
        result = {
            "year": int(year),
            "num_seeds": int(successful_seeds),
            "evolution_ensemble": evo_metrics,
            "baseline_mom20": base_metrics
        }
        results.append(result)
        print(f"  Multi-Seed Evo: IC={evo_metrics['ic']:.4f} Sharpe={evo_metrics['sharpe']:.2f}")
        print(f"  Baseline Mom20: IC={base_metrics['ic']:.4f} Sharpe={base_metrics['sharpe']:.2f}")
    
    # Summary
    print("\n" + "="*80)
    print(f"{'Year':<6} {'Multi-Seed Evo':<15} {'Mom20':<12} {'Winner'}")
    print(f"{'':6} {'IC / Sharpe':<15} {'IC / Sharpe':<12}")
    print("="*80)
    evo_wins = 0
    for r in results:
        evo_sh = r["evolution_ensemble"]["sharpe"]
        base_sh = r["baseline_mom20"]["sharpe"]
        winner = "EVOLUTION" if evo_sh > base_sh else "BASELINE"
        if winner == "EVOLUTION": evo_wins += 1
        print(f"{r['year']:<6} {r['evolution_ensemble']['ic']:+.3f} / {evo_sh:+.2f}      {r['baseline_mom20']['ic']:+.3f} / {base_sh:+.2f}     {winner}")
    print("="*80)
    print(f"\nEvolution Win Rate: {evo_wins}/{len(results)} ({100*evo_wins/len(results):.0f}%)")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "multiseed_backtest_results.json", "w") as f:
        json.dump({"run_date": datetime.now().isoformat(), "num_seeds": NUM_SEEDS, "results": results}, f, indent=2)
    print(f"\nResults saved to {OUTPUT_DIR / 'multiseed_backtest_results.json'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
