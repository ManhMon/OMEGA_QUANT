#!/usr/bin/env python3
"""
Backtest Evolution Engine - Walk-Forward Validation
Validates GP alpha discovery adds value vs momentum baseline.
PIT-safe: T-1 lag, chronological split, no future data.
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

# Set deterministic seeds for reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

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

def compute_metrics(signals, returns, dates, fwd_horizon=5, tickers=None):
    """
    Cross-sectional metrics. `dates` is required so we can build a daily
    portfolio return (avg across tickers per date) before annualizing.

    Bug-fix (audit 2026-05-29 Round 1):
      - Old code treated each ticker-day as an independent observation,
        inflating Sharpe by ~sqrt(N_tickers).
      - Correct: positions * ret per ticker-day, then groupby(date).mean()
        to get the equal-weighted daily portfolio return; Sharpe = mean/std
        of that daily series * sqrt(252).

    Bug-fix (audit 2026-05-29 Round 2 - Bug 4): Newey-West sqrt(H) correction.
      - fwd_ret_H is an H-day overlapping forward return: each daily obs
        contains the same H-day window data H times → autocorrelation →
        Sharpe inflated by sqrt(H). Divide final Sharpe by sqrt(H) to
        approximate Newey-West correction for H-day overlap.

    Bug-fix (audit 2026-05-29 Round 2 - Bug 5): cross-sectional median demean.
      - np.sign(alpha) collapses to all +1 when alpha is uniformly positive
        (e.g., vol_ratio - 0.999 monotonic positive). Force long/short
        balance per day by demeaning against the daily cross-sectional
        median BEFORE sign(): positions = sign(alpha - median(alpha|date)).

    Bug-fix (audit 2026-05-29 Round 4 - P2): per-ticker turnover.
      - Old code averaged positions across tickers per date BEFORE diff,
        which after Bug 5 demean collapses to ~0 always (fake zero turnover).
      - Correct: diff each ticker's position over time, then average
        |Δpos| across all ticker-day observations.
      - Backward compatible: if `tickers` is None, falls back to old
        portfolio-mean turnover (kept for callers that don't have ticker
        info available).
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
        return {"ic": 0.0, "sharpe": 0.0, "turnover": 0.0, "max_dd": 0.0}
    ic, _ = spearmanr(valid["sig"], valid["ret"])
    if np.isnan(ic):
        ic = 0.0
    # Bug 5 fix: cross-sectional median demean before sign() to force L/S balance
    daily_median = valid.groupby("date")["sig"].transform("median")
    positions = np.sign(valid["sig"] - daily_median)
    valid["pos"] = positions.values
    valid["strat_ret"] = positions.values * valid["ret"].values
    # Cross-sectional: average across tickers per date FIRST, then annualize
    daily_ret = valid.groupby("date")["strat_ret"].mean().sort_index()
    if len(daily_ret) < 2 or daily_ret.std() < 1e-12:
        sharpe = 0.0
    else:
        sharpe_raw = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * np.sqrt(252)
        # Bug 4 fix: Newey-West sqrt(H) correction for H-day overlapping forward returns
        sharpe = sharpe_raw / np.sqrt(max(fwd_horizon, 1))
    # P2 fix: per-ticker turnover (preserves per-ticker signal change info).
    # When tickers passed: diff each ticker's position over time, then mean |Δpos|.
    # When not: fall back to old portfolio-mean turnover for backward compat.
    if tickers is not None:
        valid_sorted = valid.sort_values(["ticker", "date"])
        per_ticker_turn = valid_sorted.groupby("ticker")["pos"].diff().abs()
        turnover = float(per_ticker_turn.mean()) if len(per_ticker_turn) else 0.0
    else:
        valid_sorted = valid.sort_values(["date"])
        daily_mean_pos = valid_sorted.groupby("date")["pos"].mean()
        turnover = float(daily_mean_pos.diff().abs().mean()) if len(daily_mean_pos) > 1 else 0.0
    cumret = (1 + daily_ret).cumprod()
    max_dd = float(((cumret / cumret.cummax()) - 1).min()) if len(cumret) > 0 else 0.0
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
        # Reset seeds before each year for reproducibility
        seed_for_year = int(SEED + int(year))
        random.seed(seed_for_year)
        np.random.seed(seed_for_year)
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
        included = 0
        for ind in hof[:top_n]:
            try:
                alpha = ind._execute_tree(ind.tree, features_test)
                alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
                # Bug-fix (audit 2026-05-29): reject constant GP signals.
                # GP frequently converges to a constant, which after np.sign()
                # collapses to equal-weight long/short and fakes "wins".
                if np.std(alpha) < 1e-6:
                    logger.warning(f"  Skipping constant alpha (std={np.std(alpha):.2e})")
                    continue
                # P3 fix (audit 2026-05-29 Round 4): tighter sign-balance guard.
                # std<1e-6 lets through alphas with large std but uniformly
                # positive sign (e.g., vol_ratio - 0.999). After demean, Bug 5
                # neutralizes Sharpe but constants still dilute the ensemble
                # average. Skip alpha if >90% of post-demean values share the
                # same sign (low information content).
                demean_alpha = alpha - np.median(alpha)
                nz = demean_alpha[demean_alpha != 0]
                if len(nz) >= 10:
                    sign_balance = float(np.mean(np.sign(nz) > 0))
                    if abs(sign_balance - 0.5) > 0.4:
                        logger.warning(
                            f"  Skipping mono-sign alpha (sign_balance={sign_balance:.2f})"
                        )
                        continue
                ensemble_signal += alpha
                included += 1
            except Exception:
                continue
        if included == 0:
            logger.warning(f"All {top_n} alphas were constant for {year}; skipping year")
            continue
        ensemble_signal /= included
        # Baselines
        test_returns = test_df["fwd_ret_5"].values
        test_dates = test_df["date"].values
        test_tickers = test_df["ticker"].values
        evo_metrics = compute_metrics(pd.Series(ensemble_signal), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_mom = compute_metrics(pd.Series(test_df["mom_20"].values), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_ivol = compute_metrics(pd.Series(test_df["inverse_vol"].values), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_mr = compute_metrics(pd.Series(test_df["mean_reversion"].values), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_ew = compute_metrics(pd.Series(test_df["equal_weight"].values), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        result = {"year": int(year), "evolution": evo_metrics,
                  "baseline_mom20": base_mom, "baseline_inverse_vol": base_ivol,
                  "baseline_mean_reversion": base_mr, "baseline_equal_weight": base_ew,
                  "alpha_count": int(included), "train_size": int(len(train_df)), "test_size": int(len(test_df))}
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
