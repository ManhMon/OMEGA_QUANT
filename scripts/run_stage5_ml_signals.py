#!/usr/bin/env python3
"""
Stage 5 ML Signals: Daily signal generation using Ridge ML model.
Replaces inverse-vol weighting with 142-feature Ridge combination.

Author: System Architect (Role 6)
Date: 2026-05-28
"""
import argparse
import json
import sys
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
from sklearn.linear_model import Ridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ml_signals")

SHADOW_DIR = PROJECT_ROOT / ".ly_state" / "shadow_live"
WAREHOUSE = PROJECT_ROOT / "data" / "market_2015_now.parquet"
CONFIG = {
    "top_n": 30, "max_positions": 10, "max_concentration": 0.25,
    "max_adv_pct": 0.40, "ridge_alpha": 1.0, "capital": 2_000_000_000,
    "slippage_bps": 10, "commission_bps": 15, "sell_tax_bps": 10,
}

def compute_fundamental_features(df):
    """10 fundamental proxy features (T-1 PIT safe)."""
    df["feat_earnings_proxy"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(20) - x.pct_change(60)).groupby(df["ticker"]).shift(1)
    df["feat_value_proxy"] = df.groupby("ticker")["close"].transform(lambda x: x / x.rolling(252).max() - 1).groupby(df["ticker"]).shift(1)
    df["feat_quality_proxy"] = df.groupby("ticker")["returns"].transform(lambda x: x.rolling(60).mean() / (x.rolling(60).std() + 1e-10)).groupby(df["ticker"]).shift(1)
    df["feat_growth_proxy"] = df.groupby("ticker")["volume"].transform(lambda x: x.rolling(60).mean() / (x.rolling(252).mean() + 1)).groupby(df["ticker"]).shift(1)
    df["feat_size_proxy"] = np.log1p(df["close"] * df["volume"]).groupby(df["ticker"]).shift(1)
    market_vol = df.groupby("date")["returns"].transform("std")
    df["feat_leverage_proxy"] = (df.groupby("ticker")["returns"].transform(lambda x: x.rolling(20).std()) / (market_vol + 1e-10)).groupby(df["ticker"]).shift(1)
    df["feat_dividend_proxy"] = (df.groupby("ticker")["returns"].transform(lambda x: x.rolling(60).mean()) / (df.groupby("ticker")["returns"].transform(lambda x: x.rolling(60).std()) + 1e-10)).groupby(df["ticker"]).shift(1)
    df["feat_turnover_ratio"] = (df["volume"] / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(252).mean() + 1)).groupby(df["ticker"]).shift(1)
    df["market_ret"] = df.groupby("date")["returns"].transform("mean")
    df["feat_beta_proxy"] = df.groupby("ticker").apply(lambda g: g["returns"].rolling(60).corr(g["market_ret"])).reset_index(level=0, drop=True).groupby(df["ticker"]).shift(1)
    df["feat_mom_quality"] = df.groupby("ticker")["returns"].transform(lambda x: x.rolling(20).mean().rolling(20).corr(x.shift(5).rolling(5).mean())).groupby(df["ticker"]).shift(1)
    feat_cols = [c for c in df.columns if c.startswith("feat_")]
    for col in feat_cols:
        df[col] = df.groupby("date")[col].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))
    return df, feat_cols

def run_ml_signals(date_str: str):
    logger.info(f"=== ML SIGNAL GENERATION FOR {date_str} ===")
    run_date = pd.Timestamp(date_str)
    pit_cutoff = run_date - pd.Timedelta(days=1)

    # Load data up to T-1
    if not WAREHOUSE.exists():
        logger.error("Warehouse not found"); return
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= pit_cutoff].sort_values(["ticker", "date"]).reset_index(drop=True)

    # Top N by volume
    median_vol = df.groupby("ticker")["volume"].median().nlargest(CONFIG["top_n"])
    df = df[df["ticker"].isin(median_vol.index)].copy()
    df["returns"] = df.groupby("ticker")["close"].pct_change()
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    df["adv_20"] = df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["adv_vnd"] = df["adv_20"] * df["close"]

    logger.info(f"  Data: {len(df)} rows, {df['ticker'].nunique()} tickers, up to {pit_cutoff.date()}")

    # Compute all features
    alpha_df = compute_ultimate_alphas(df, symbol_col="ticker")
    alpha_cols = [c for c in alpha_df.columns if c.startswith("alpha_")]
    for col in alpha_cols:
        if col not in df.columns:
            df[col] = alpha_df[col]
    for col in alpha_cols:
        df[col] = df.groupby("date")[col].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))

    df, feat_cols = compute_fundamental_features(df)
    all_cols = alpha_cols + feat_cols
    logger.info(f"  Features: {len(all_cols)} total")

    # Train Ridge on all available data (target = fwd_ret_5)
    train_df = df.dropna(subset=["fwd_ret_5"]).copy()
    X_train = train_df[all_cols].fillna(0).values
    y_train = train_df["fwd_ret_5"].values
    ridge = Ridge(alpha=CONFIG["ridge_alpha"])
    ridge.fit(X_train, y_train)
    logger.info(f"  Ridge trained on {len(train_df)} samples")

    # Generate signal for latest date
    latest_df = df[df["date"] == df["date"].max()].copy()
    if latest_df.empty:
        logger.error("No data for latest date"); return
    latest_df["signal"] = ridge.predict(latest_df[all_cols].fillna(0).values)

    # Rank and select top positions
    latest_df = latest_df.sort_values("signal", ascending=False)
    top = latest_df.head(CONFIG["max_positions"])
    n_pos = len(top)
    weights = pd.Series(1.0 / n_pos, index=top["ticker"].values)
    weights = weights.clip(upper=CONFIG["max_concentration"])
    adv_data = top.set_index("ticker")["adv_vnd"]
    max_by_adv = (adv_data * CONFIG["max_adv_pct"]) / CONFIG["capital"]
    weights = pd.concat([weights, max_by_adv], axis=1).min(axis=1)
    if weights.sum() > 1.0:
        weights = weights / weights.sum()

    # Cost estimate
    cost_bps = (CONFIG["slippage_bps"] + CONFIG["commission_bps"]) * 2  # round-trip estimate

    # Build output
    signals = []
    for i, (ticker, w) in enumerate(weights.items()):
        sig_score = float(latest_df[latest_df["ticker"] == ticker]["signal"].iloc[0])
        signals.append({"ticker": ticker, "weight": round(w, 4), "signal_score": round(sig_score, 6), "rank": i + 1})

    result = {
        "date": date_str, "status": "OK", "num_trades": len(signals),
        "signals": signals, "slippage_bps": CONFIG["slippage_bps"],
        "cost_bps": cost_bps, "model": "Ridge_142features",
        "log_path": str(SHADOW_DIR / f"{date_str}.json"),
    }

    # Save
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_DIR / f"{date_str}.json", "w") as f:
        json.dump(result, f, indent=2)

    # Print summary for oracle pipeline
    print("=" * 50)
    print(f"STAGE 5 ML SIGNALS - {date_str}")
    print("=" * 50)
    print(f"  date: {date_str}")
    print(f"  status: OK")
    print(f"  num_trades: {len(signals)}")
    print(f"  model: Ridge_142features")
    print(f"  cost_bps: {cost_bps}")
    print(f"  log_path: {SHADOW_DIR / f'{date_str}.json'}")
    print(f"  top signals:")
    for s in signals[:5]:
        print(f"    {s['ticker']}: weight={s['weight']:.2%}, score={s['signal_score']:.4f}")
    print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    run_ml_signals(args.date)
