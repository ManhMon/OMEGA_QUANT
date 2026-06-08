#!/usr/bin/env python3
"""
Train UniverseClassifier (Phase 1.3 - Role 9 Backend Engineer).

Builds monthly snapshots of PIT-safe universe features over 2017..train_end,
labels each ticker by whether its forward return over `label_horizon` trading
days is in the top `(1 - top_percentile)` cross-sectional bucket on the
snapshot date, then fits an XGBoost binary classifier and persists it.

PIT Safety:
- UniverseFeatureComputer enforces date < as_of_date (no look-ahead).
- Labels are built from data on/after the snapshot, never mixed into features.

Usage:
    python scripts/train_universe_classifier.py \
        --data data/market_2015_now.parquet \
        --train-end 2023-12-31 \
        --model-out models/universe_classifier.joblib
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np  # noqa: F401  (kept for downstream parity / future ops)
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omega.quant.universe.feature_computer import UniverseFeatureComputer  # noqa: E402
from omega.quant.universe.xgb_classifier import UniverseClassifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_universe_classifier")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train UniverseClassifier on historical data.")
    parser.add_argument("--data", default="data/market_2015_now.parquet")
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--label-horizon", type=int, default=63,
                        help="Forward return horizon in calendar days (default: 63 ~ 3 months).")
    parser.add_argument("--top-percentile", type=float, default=0.75,
                        help="Quantile cutoff for positive label (default: 0.75 = top 25%%).")
    parser.add_argument("--rebalance-freq", default="M",
                        help="Snapshot frequency (pandas offset alias, default: M).")
    parser.add_argument("--model-out", default="models/universe_classifier.joblib")
    parser.add_argument("--min-adv-vnd", type=float, default=5e9,
                        help="Minimum 5B VND median ADV (close*volume) to be eligible.")
    parser.add_argument("--min-price", type=float, default=5000,
                        help="Minimum 5000 VND median close price to be eligible.")
    parser.add_argument("--min-listing-days", type=int, default=365,
                        help="Minimum 1 year listing duration to be eligible.")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        return 1

    logger.info("Loading market data from %s", data_path)
    df = pd.read_parquet(data_path)
    df["date"] = pd.to_datetime(df["date"])
    logger.info("Loaded %d rows, %d tickers, range=[%s .. %s]",
                len(df), df["ticker"].nunique(), df["date"].min().date(), df["date"].max().date())

    fc = UniverseFeatureComputer()
    train_end = pd.Timestamp(args.train_end)

    # Liquidity + quality filter (PIT-safe: only data within training window).
    train_df = df[df["date"] <= train_end].copy()
    train_df["adv_vnd"] = train_df["close"] * train_df["volume"]
    df_quality = train_df.groupby("ticker").agg(
        median_adv_vnd=("adv_vnd", "median"),
        median_price=("close", "median"),
        listing_days=("date", lambda x: (x.max() - x.min()).days),
    )
    eligible_tickers = df_quality[
        (df_quality["median_adv_vnd"] >= args.min_adv_vnd)
        & (df_quality["median_price"] >= args.min_price)
        & (df_quality["listing_days"] >= args.min_listing_days)
    ].index
    logger.info(
        "Eligible tickers after filter: %d (from %d) | min_adv=%.2eVND min_price=%.0f min_days=%d",
        len(eligible_tickers), len(df_quality),
        args.min_adv_vnd, args.min_price, args.min_listing_days,
    )
    if len(eligible_tickers) < 30:
        logger.error("Too few eligible tickers (%d). Loosen filters.", len(eligible_tickers))
        return 1
    df = df[df["ticker"].isin(eligible_tickers)].copy()
    snapshots = pd.date_range("2017-01-01", train_end, freq=args.rebalance_freq)
    logger.info("Generating %d snapshots from %s to %s (freq=%s)",
                len(snapshots), snapshots[0].date(), snapshots[-1].date(), args.rebalance_freq)

    X_list: list[pd.DataFrame] = []
    y_list: list[pd.Series] = []
    skipped = 0

    for snap_date in snapshots:
        features = fc.compute(df, snap_date)
        if features.empty:
            skipped += 1
            continue

        future_end = snap_date + pd.Timedelta(days=args.label_horizon)
        future_data = df[(df["date"] >= snap_date) & (df["date"] <= future_end)]
        if future_data.empty:
            skipped += 1
            continue

        first_close = future_data.groupby("ticker")["close"].first()
        last_close = future_data.groupby("ticker")["close"].last()
        forward_ret = (last_close / first_close) - 1

        common = features.index.intersection(forward_ret.index)
        if len(common) < 30:
            skipped += 1
            continue

        X = features.loc[common]
        threshold = forward_ret.loc[common].quantile(args.top_percentile)
        y = (forward_ret.loc[common] > threshold).astype(int)

        X_list.append(X.reset_index(drop=True))
        y_list.append(y.reset_index(drop=True))

    if not X_list:
        logger.error("No training data generated (skipped=%d snapshots)", skipped)
        return 1

    X_train = pd.concat(X_list, ignore_index=True)
    y_train = pd.concat(y_list, ignore_index=True)
    logger.info(
        "Training set: %d samples, %d features, %.2f%% positive (skipped=%d snapshots)",
        len(X_train), X_train.shape[1], 100.0 * y_train.mean(), skipped,
    )

    clf = UniverseClassifier(n_estimators=300, max_depth=4, learning_rate=0.05)
    clf.fit(X_train, y_train)

    out_path = Path(args.model_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clf.save(str(out_path))
    logger.info("Model saved to %s", out_path)

    importance = clf.feature_importance().head(10)
    logger.info("Top-10 feature importances:")
    print(importance.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
