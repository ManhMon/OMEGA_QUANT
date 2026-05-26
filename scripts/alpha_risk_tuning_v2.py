"""Alpha Tuning V2 - Fundamental + Momentum + Reduced Cost + Small Universe."""
import sys
import os
import json
import itertools

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from phase35_data_loader import Phase35DataLoader

print("=" * 80)
print("ALPHA TUNING V2 - FUNDAMENTAL + MOMENTUM + SMALL UNIVERSE")
print("=" * 80)

# Load data - TOP 15 most liquid
print("\nLoading data (U15 - top liquid)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=15, forward_horizons=[1, 3, 5, 10],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")
print(f"Tickers: {sorted(df['ticker'].unique())}")

# === GENERATE NEW ALPHAS ===
print("\nGenerating new alpha signals...")

# 1. Momentum alphas (longer horizon)
for window in [20, 40, 60]:
    df[f"alpha_momentum_{window}d"] = df.groupby("ticker")["close"].transform(
        lambda x: x.pct_change(window)
    )

# 2. Mean reversion (short-term)
df["alpha_mean_reversion_5d"] = -df.groupby("ticker")["close"].transform(
    lambda x: x.pct_change(5)
)

# 3. Volume momentum
df["alpha_volume_momentum_20d"] = df.groupby("ticker")["volume"].transform(
    lambda x: x.rolling(5).mean() / x.rolling(20).mean() - 1
)

# 4. Volatility-adjusted momentum
df["alpha_vol_adj_momentum_20d"] = df.groupby("ticker").apply(
    lambda g: g["close"].pct_change(20) / g["close"].pct_change(1).rolling(20).std(),
    include_groups=False
).reset_index(level=0, drop=True)

# 5. Price relative to moving average
for window in [20, 60]:
    df[f"alpha_price_vs_ma_{window}d"] = df.groupby("ticker")["close"].transform(
        lambda x: x / x.rolling(window).mean() - 1
    )

# 6. High-low range compression (breakout signal)
df["alpha_range_compression_20d"] = df.groupby("ticker").apply(
    lambda g: (g["high"].rolling(20).max() - g["low"].rolling(20).min()) / g["close"],
    include_groups=False
).reset_index(level=0, drop=True)

# 7. Volume-price divergence
df["alpha_vol_price_divergence"] = df.groupby("ticker").apply(
    lambda g: g["volume"].pct_change(10).rank(pct=True) - g["close"].pct_change(10).rank(pct=True),
    include_groups=False
).reset_index(level=0, drop=True)

alpha_cols = [c for c in df.columns if c.startswith("alpha_")]
print(f"Total alpha signals: {len(alpha_cols)}")
print(f"Alphas: {alpha_cols}")

# Drop NaN rows
df = df.dropna(subset=alpha_cols + ["fwd_ret_1", "fwd_ret_3", "fwd_ret_5", "fwd_ret_10"])
print(f"Rows after dropna: {len(df)}")

# === GRID SEARCH ===
print("\n" + "=" * 80)
print("GRID SEARCH - REDUCED COST + LONGER REBALANCE")
print("=" * 80)

GRID = {
    "top_n_stocks": [5, 8, 10],
    "rebalance_freq": [10, 20],
    "top_n_alphas": [3, 5],
    "return_horizon": ["fwd_ret_3", "fwd_ret_5", "fwd_ret_10"],
    "weighting": ["equal", "ic_weighted"],
}

SLIPPAGE_BPS = 10
COMMISSION_BPS = 15
COST_BPS = SLIPPAGE_BPS + COMMISSION_BPS

dates = sorted(df["date"].unique())
n_folds = 8
fold_size = len(dates) // (n_folds + 3)
train_window = fold_size * 3


def run_config(top_n_stocks, rebalance_freq, top_n_alphas, return_horizon, weighting):
    fold_results = []

    for fold_id in range(n_folds):
        test_start_idx = train_window + fold_id * fold_size
        test_end_idx = test_start_idx + fold_size
        if test_end_idx > len(dates):
            break

        train_dates = dates[test_start_idx - train_window:test_start_idx]
        test_dates_fold = dates[test_start_idx:test_end_idx]

        train_df = df[df["date"].isin(train_dates)]
        test_df = df[df["date"].isin(test_dates_fold)].copy()

        if len(test_df) == 0 or len(train_df) == 0:
            continue

        # Select top alphas by train RankIC
        train_ics = {}
        for col in alpha_cols:
            valid = train_df[[col, return_horizon]].dropna()
            if len(valid) > 50:
                train_ics[col] = valid[col].rank().corr(valid[return_horizon].rank())

        sorted_alphas = sorted(train_ics.items(), key=lambda x: x[1], reverse=True)
        selected = [a[0] for a in sorted_alphas[:top_n_alphas] if a[1] > 0]

        if len(selected) == 0:
            selected = [a[0] for a in sorted_alphas[:top_n_alphas]]

        if len(selected) == 0:
            continue

        # Composite signal
        if weighting == "ic_weighted" and all(train_ics.get(a, 0) > 0 for a in selected):
            w = np.array([train_ics[a] for a in selected])
            w = w / w.sum()
            test_df["signal"] = sum(test_df[a] * wi for a, wi in zip(selected, w))
        else:
            test_df["signal"] = test_df[selected].mean(axis=1)

        # Simulate
        rebal_dates = test_dates_fold[::rebalance_freq]
        fold_returns = []
        prev_positions = set()

        for rebal_date in rebal_dates:
            day_df = test_df[test_df["date"] == rebal_date].copy()
            if len(day_df) < top_n_stocks:
                continue

            top = day_df.nlargest(top_n_stocks, "signal")
            new_positions = set(top["ticker"].values)

            if prev_positions:
                turnover = len(new_positions.symmetric_difference(prev_positions)) / (2 * top_n_stocks)
            else:
                turnover = 1.0

            cost = turnover * COST_BPS / 10000

            next_dates = [d for d in test_dates_fold if d > rebal_date][:rebalance_freq]
            if not next_dates:
                continue

            period_df = test_df[test_df["date"].isin(next_dates) & test_df["ticker"].isin(new_positions)]
            if len(period_df) == 0:
                continue

            gross_ret = period_df.groupby("ticker")["fwd_ret_1"].mean().mean()
            net_ret = gross_ret - cost
            fold_returns.append(net_ret)
            prev_positions = new_positions

        if len(fold_returns) >= 3:
            arr = np.array(fold_returns)
            sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252 / rebalance_freq)
            max_dd = (np.minimum.accumulate(np.cumsum(arr)) - np.cumsum(arr)).min()
            total_ret = arr.sum()
            fold_results.append({
                "sharpe": sharpe, "max_dd": max_dd,
                "total_ret": total_ret, "positive": 1 if total_ret > 0 else 0,
            })

    if len(fold_results) < 4:
        return None

    avg_sharpe = np.mean([f["sharpe"] for f in fold_results])
    avg_dd = np.mean([f["max_dd"] for f in fold_results])
    avg_ret = np.mean([f["total_ret"] for f in fold_results])
    pct_positive = np.mean([f["positive"] for f in fold_results])
    worst_dd = min(f["max_dd"] for f in fold_results)

    # Hard gates
    if worst_dd < -0.25:
        return None
    if avg_dd < -0.15:
        return None

    score = 0.50 * avg_sharpe + 0.30 * (1 + avg_dd) + 0.20 * pct_positive

    return {
        "avg_sharpe": round(avg_sharpe, 4),
        "avg_dd": round(avg_dd * 100, 2),
        "avg_ret": round(avg_ret * 100, 2),
        "pct_positive": round(pct_positive, 2),
        "worst_dd": round(worst_dd * 100, 2),
        "score": round(score, 4),
    }


# Run grid
total_configs = (len(GRID["top_n_stocks"]) * len(GRID["rebalance_freq"]) *
                 len(GRID["top_n_alphas"]) * len(GRID["return_horizon"]) * len(GRID["weighting"]))
print(f"Running {total_configs} configs...")

all_results = []
config_id = 0

for top_n, rebal, n_alpha, ret_h, wt in itertools.product(
    GRID["top_n_stocks"], GRID["rebalance_freq"],
    GRID["top_n_alphas"], GRID["return_horizon"], GRID["weighting"]
):
    config_id += 1
    metrics = run_config(top_n, rebal, n_alpha, ret_h, wt)
    if metrics is not None:
        metrics["config"] = f"top{top_n}_rebal{rebal}_alpha{n_alpha}_{ret_h}_{wt}"
        metrics["top_n_stocks"] = top_n
        metrics["rebalance_freq"] = rebal
        metrics["top_n_alphas"] = n_alpha
        metrics["return_horizon"] = ret_h
        metrics["weighting"] = wt
        all_results.append(metrics)

    if config_id % 20 == 0:
        print(f"  Processed {config_id}/{total_configs}, {len(all_results)} passed gates...")

print(f"\nTotal configs tested: {config_id}")
print(f"Configs passing hard gates: {len(all_results)}")

if len(all_results) > 0:
    results_df = pd.DataFrame(all_results).sort_values("score", ascending=False)
    print("\n=== TOP 10 CONFIGURATIONS ===")
    print(results_df.head(10)[["config", "avg_sharpe", "avg_ret", "avg_dd", "worst_dd", "pct_positive", "score"]].to_string(index=False))

    os.makedirs("data/phase35_results", exist_ok=True)
    results_df.to_csv("data/phase35_results/alpha_risk_tuning_v2_grid.csv", index=False)

    best = results_df.iloc[0].to_dict()
    with open("data/phase35_results/best_config_v2.json", "w") as f:
        json.dump(best, f, indent=2, default=str)

    print(f"\nBest config: {best['config']}")
    print(f"  Sharpe: {best['avg_sharpe']}, Return: {best['avg_ret']}%, DD: {best['avg_dd']}%")
    print(f"  Positive folds: {best['pct_positive']*100}%")
else:
    print("\nNo configs passed hard gates.")
    print("Signals still too weak. Consider adding fundamental data (PE/PB/ROE) from external source.")

print("\n" + "=" * 80)
print("ALPHA TUNING V2 COMPLETE!")
print("=" * 80)
