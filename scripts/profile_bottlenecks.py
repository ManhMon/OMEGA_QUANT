"""Quick profiling of backtest bottlenecks."""
import argparse
import cProfile
import io
import pstats
import sys
import time
import json
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/market_2015_now.parquet")
    parser.add_argument("--start-date", default="2015-01-01")
    parser.add_argument("--end-date", default="2026-06-13")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--profile-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--no-cprofile", action="store_true", help="Run the full workload without cProfile overhead")
    args = parser.parse_args()

    profiler = cProfile.Profile() if not args.no_cprofile else None
    if profiler:
        profiler.enable()

    data_path = REPO_ROOT / args.data
    t0 = time.time()
    raw_df = pd.read_parquet(data_path)
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    mask = (raw_df["date"] >= args.start_date) & (raw_df["date"] <= args.end_date)
    raw_df = raw_df[mask]
    print(f"[{time.time()-t0:.1f}s] Data load: {len(raw_df)} rows")

    t0 = time.time()
    tickers = raw_df.groupby("ticker")["volume"].sum().nlargest(30).index.tolist()
    print(f"[{time.time()-t0:.1f}s] Universe selection: {len(tickers)} tickers")

    t0 = time.time()
    panel = raw_df[raw_df["ticker"].isin(tickers)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel = panel.rename(columns={"ticker": "symbol"})
    panel["returns"] = panel.groupby("symbol")["close"].pct_change()
    panel["adv_vnd"] = panel.groupby("symbol")["volume"].transform(lambda x: x.rolling(20, min_periods=5).mean()) * panel["close"]
    print(f"[{time.time()-t0:.1f}s] Panel prep: {len(panel)} rows, {panel['date'].nunique()} dates")

    t0 = time.time()
    panel_mi = panel.set_index(["date", "symbol"]).sort_index()
    from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
    adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True, use_llm_synth=False)
    feat_df = adapter.generate_all(panel_mi).reset_index().dropna(subset=["close", "volume", "returns"])
    feat_df = feat_df.sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"[{time.time()-t0:.1f}s] Feature generation: {len(feat_df)} rows, {len(feat_df.columns)} cols")

    alpha_cols = [c for c in feat_df.columns if c.startswith("alpha_") and not c.endswith("_lag1")]
    print(f"\nAlpha columns: {len(alpha_cols)}")
    unique_dates = np.sort(feat_df["date"].unique())
    ts_index = pd.DatetimeIndex(unique_dates)
    train_dates = ts_index[: int(len(ts_index) * 0.6)]
    train_feat = feat_df[feat_df["date"].isin(set(pd.Timestamp(d) for d in train_dates))]
    print(f"Train fold: {len(train_feat)} rows, {train_feat['symbol'].nunique()} symbols")

    t0 = time.time()
    train_sorted = train_feat.sort_values(["symbol", "date"])
    train_lag_df = pd.DataFrame({f"{col}_lag1": train_sorted.groupby("symbol")[col].shift(1) for col in alpha_cols}, index=train_sorted.index)
    print(f"[{time.time()-t0:.1f}s] Training lag computation ({len(alpha_cols)} cols)")

    t0 = time.time()
    full_sorted = feat_df.sort_values(["symbol", "date"])
    pred_lag_df = full_sorted.groupby("symbol")[alpha_cols].shift(1)
    pred_lag_df.columns = [f"{col}_lag1" for col in alpha_cols]
    print(f"[{time.time()-t0:.1f}s] Prediction lag computation (full panel, {len(alpha_cols)} cols)")

    if profiler:
        profiler.disable()
    stats = pstats.Stats(profiler).sort_stats("cumulative") if profiler else None
    if args.profile_output:
        if not stats:
            raise ValueError("--profile-output requires cProfile; remove --no-cprofile")
        args.profile_output.parent.mkdir(parents=True, exist_ok=True)
        stats.dump_stats(str(args.profile_output))
    stream = io.StringIO()
    if stats:
        stats.stream = stream
        stats.print_stats(args.top)
    profile_text = stream.getvalue()
    print(profile_text)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps({
            "data": str(args.data),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "rows": int(len(raw_df)),
            "tickers": len(tickers),
            "feature_rows": int(len(feat_df)),
            "feature_columns": int(len(feat_df.columns)),
            "profile_top": profile_text,
        }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
