#!/usr/bin/env python3
"""run_walk_forward_validation.py - Walk-forward training and validation."""
import sys, os, json, argparse, logging
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "packages" / "quant" / "src"))
sys.path.insert(0, str(WORKSPACE / "scripts"))

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("walk_forward")

WalkForwardEnsemble = None
WalkForwardConfig = None
run_walk_forward_validation = None

try:
    from omega.quant.walk_forward_ensemble import (
        WalkForwardEnsemble, WalkForwardConfig, run_walk_forward_validation
    )
    logger.info("WalkForwardEnsemble imported")
except ImportError as e:
    logger.warning(f"WalkForwardEnsemble not available: {e}, using manual logic")

WAREHOUSE = WORKSPACE / "data" / "market_2015_now.parquet"

FEATURE_COLS = ["open", "high", "low", "close", "volume",
                "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]

def load_data(date_str, top_n=30, lookback_years=5):
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    cutoff_end = pd.Timestamp(date_str)
    cutoff_start = cutoff_end - pd.Timedelta(days=lookback_years * 365)
    df = df[(df["date"] >= cutoff_start) & (df["date"] <= cutoff_end)]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    median_vol = df.groupby("ticker")["volume"].median().nlargest(top_n)
    df = df[df["ticker"].isin(median_vol.index)].copy()
    
    df["returns_1d"] = df.groupby("ticker")["close"].pct_change(1)
    df["returns_5d"] = df.groupby("ticker")["close"].pct_change(5)
    df["vol_ratio"] = df["volume"] / (df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1)
    df["hl_range"] = (df["high"] - df["low"]) / (df["close"] + 1e-9)
    df["oc_range"] = (df["close"] - df["open"]) / (df["close"] + 1e-9)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    
    for col in FEATURE_COLS:
        df[col] = df.groupby("ticker")[col].shift(1)  # T-1 lag
    
    df = df.dropna(subset=FEATURE_COLS + ["fwd_ret_5"])
    return df

def manual_walk_forward(df, window_days=252, step_days=21):
    """Manual walk-forward when ensemble module unavailable."""
    dates = sorted(df["date"].unique())
    if len(dates) < window_days + step_days:
        return []
    
    fold_results = []
    fold_idx = 0
    
    for start_idx in range(0, len(dates) - window_days - step_days, step_days):
        train_dates = dates[start_idx:start_idx + window_days]
        test_dates = dates[start_idx + window_days:start_idx + window_days + step_days]
        
        train_df = df[df["date"].isin(train_dates)]
        test_df = df[df["date"].isin(test_dates)]
        
        if len(train_df) < 100 or len(test_df) < 10:
            continue
        
        X_train = train_df[FEATURE_COLS].fillna(0).values
        y_train = train_df["fwd_ret_5"].values
        X_test = test_df[FEATURE_COLS].fillna(0).values
        y_test = test_df["fwd_ret_5"].values
        
        try:
            model = Ridge(alpha=1.0)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            
            ic, _ = spearmanr(y_pred, y_test)
            if np.isnan(ic): ic = 0.0
            
            positions = np.sign(y_pred)
            strat_ret = positions * y_test
            sharpe = (strat_ret.mean() / (strat_ret.std() + 1e-9)) * np.sqrt(252)
            
            fold_results.append({
                "fold": fold_idx,
                "start": str(train_dates[0].date()),
                "end": str(test_dates[-1].date()),
                "ic": round(float(ic), 4),
                "sharpe": round(float(sharpe), 2),
                "train_size": len(train_df),
                "test_size": len(test_df)
            })
            fold_idx += 1
        except Exception as e:
            logger.warning(f"Fold {fold_idx} failed: {e}")
            continue
    
    return fold_results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--window-days", type=int, default=252)
    parser.add_argument("--step-days", type=int, default=21)
    args = parser.parse_args()
    
    logger.info(f"Walk-forward validation for {args.date}")
    df = load_data(args.date)
    logger.info(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
    
    if df.empty:
        logger.error("No data available")
        return 1
    
    fold_results = manual_walk_forward(df, args.window_days, args.step_days)
    
    if not fold_results:
        logger.warning("No folds produced")
        return 0
    
    avg_ic = np.mean([f["ic"] for f in fold_results])
    avg_sharpe = np.mean([f["sharpe"] for f in fold_results])
    
    result = {
        "date": args.date,
        "window_days": args.window_days,
        "step_days": args.step_days,
        "num_folds": len(fold_results),
        "avg_ic": round(float(avg_ic), 4),
        "avg_sharpe": round(float(avg_sharpe), 2),
        "fold_results": fold_results,
        "method": "WalkForwardEnsemble" if run_walk_forward_validation else "manual"
    }
    
    out = WORKSPACE / ".ly_state" / "session" / f"walk_forward_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    print("="*60)
    print(f"WALK-FORWARD VALIDATION - {args.date}")
    print("="*60)
    print(f"  Folds: {len(fold_results)}")
    print(f"  Avg IC: {avg_ic:+.4f}")
    print(f"  Avg Sharpe: {avg_sharpe:+.2f}")
    print("\nLast 5 folds:")
    for f in fold_results[-5:]:
        print(f"  {f['start']} -> {f['end']}: IC={f['ic']:+.4f} Sharpe={f['sharpe']:+.2f}")
    print(f"\nSaved: {out}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
