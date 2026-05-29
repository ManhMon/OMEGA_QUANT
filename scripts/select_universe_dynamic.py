"""Daily script to load trained universe classifier and select top-N universe.

Usage:
    python scripts/select_universe_dynamic.py [--date YYYY-MM-DD] [--n 50]

Outputs:
    .ly_state/session/universe/universe_<date>.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "packages/quant/src"))

from omega.quant.universe.feature_computer import UniverseFeatureComputer  # noqa: E402
from omega.quant.universe.xgb_classifier import UniverseClassifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("select_universe_dynamic")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select universe via trained classifier")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--data", default="data/market_2015_now.parquet")
    parser.add_argument("--model", default="models/universe_classifier.joblib")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--out-dir", default=".ly_state/session/universe")
    parser.add_argument("--min-adv-vnd", type=float, default=5e9,
                        help="Minimum 5B VND median ADV (close*volume) to be eligible.")
    parser.add_argument("--min-price", type=float, default=5000,
                        help="Minimum 5000 VND median close price to be eligible.")
    parser.add_argument("--min-listing-days", type=int, default=365,
                        help="Minimum 1 year listing duration to be eligible.")
    parser.add_argument("--quality-lookback-days", type=int, default=365,
                        help="Lookback window (days) ending strictly before target_date "
                             "for liquidity/quality stats.")
    args = parser.parse_args()

    target_date = pd.Timestamp(args.date)

    # Load model.
    model_path = Path(args.model)
    if not model_path.exists():
        logger.error("Model not found: %s", model_path)
        return 1
    clf = UniverseClassifier.load(str(model_path))

    # Load data.
    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Data not found: %s", data_path)
        return 1
    df = pd.read_parquet(data_path)
    df["date"] = pd.to_datetime(df["date"])

    # Liquidity + quality filter (PIT-safe: only data strictly before target_date).
    # - listing_days uses full history (ticker must be listed >= min_listing_days).
    # - median ADV / price use the recent lookback window.
    pre_df = df[df["date"] < target_date]
    listing_days = pre_df.groupby("ticker")["date"].agg(
        lambda x: (x.max() - x.min()).days
    ).rename("listing_days")

    lookback_start = target_date - pd.Timedelta(days=args.quality_lookback_days)
    quality_df = pre_df[pre_df["date"] >= lookback_start].copy()
    quality_df["adv_vnd"] = quality_df["close"] * quality_df["volume"]
    df_quality = quality_df.groupby("ticker").agg(
        median_adv_vnd=("adv_vnd", "median"),
        median_price=("close", "median"),
    ).join(listing_days, how="inner")

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
    if len(eligible_tickers) == 0:
        logger.error("No eligible tickers; loosen filters.")
        return 1
    df = df[df["ticker"].isin(eligible_tickers)].copy()

    # Compute PIT-safe features as of target_date.
    fc = UniverseFeatureComputer()
    features = fc.compute(df, target_date)
    if features.empty:
        logger.error("No features computed for date=%s", args.date)
        return 1

    # Predict and select.
    proba = clf.predict_proba(features)
    universe_tickers = clf.select_universe(features, n=args.n)

    proba_series = pd.Series(proba, index=features.index)
    universe_with_scores = [
        {"ticker": t, "score": float(proba_series[t]), "rank": i + 1}
        for i, t in enumerate(universe_tickers)
    ]

    result = {
        "date": args.date,
        "method": "ml_classifier_xgb",
        "n_eligible": int(len(features)),
        "n_selected": int(len(universe_tickers)),
        "filter": {
            "min_adv_vnd": args.min_adv_vnd,
            "min_price": args.min_price,
            "min_listing_days": args.min_listing_days,
            "quality_lookback_days": args.quality_lookback_days,
        },
        "universe": universe_with_scores,
    }

    # Save.
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"universe_{args.date}.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2)
    logger.info("Universe saved to %s: %d tickers", out_file, len(universe_tickers))

    print("Top 10 by score:")
    for entry in universe_with_scores[:10]:
        print(f"  {entry['rank']:2d}. {entry['ticker']:6s} score={entry['score']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
