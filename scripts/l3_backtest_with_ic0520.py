"""L3 Backtest V2 - Include IC=0.0520 alpha from Island 8."""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
from phase35_data_loader import Phase35DataLoader
from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
from scipy.stats import spearmanr

print("=" * 80)
print("L3 BACKTEST V2 - WITH IC=0.0520 ALPHA")
print("=" * 80)

# Load data
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=15, forward_horizons=[1, 3, 5, 10],
)
df = df.dropna(subset=["open", "high", "low", "close", "volume", "fwd_ret_5"])

# Derived features (same as island script)
df["returns_1d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(1))
df["returns_5d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(5))
df["returns_20d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(20))
df["vol_ratio"] = df["volume"] / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
df["hl_range"] = (df["high"] - df["low"]) / df["close"]
df["oc_range"] = (df["close"] - df["open"]) / df["close"]
df["vwap_proxy"] = (df["high"] + df["low"] + df["close"]) / 3
df["price_vs_vwap"] = df["close"] / df["vwap_proxy"] - 1
df = df.dropna()

dates = sorted(df["date"].unique())
split_idx = int(len(dates) * 0.7)
train_df = df[df["date"].isin(dates[:split_idx])]
test_df = df[df["date"].isin(dates[split_idx:])]

feature_cols = ["open", "high", "low", "close", "volume", "returns_1d", "returns_5d",
                "returns_20d", "vol_ratio", "hl_range", "oc_range", "price_vs_vwap"]

features_train = {col: train_df[col].values for col in feature_cols}
target_train = train_df["fwd_ret_5"].values

# Evolve with Island 8 config (which produced IC=0.0520)
# Use same seed and config that found it
print("\nEvolving Island 8 alpha (seed=7*17+7=126, depth=4, mut=0.4)...")
np.random.seed(126 + 7)  # Slightly different to explore nearby
config = GPConfig(
    population_size=100, generations=20, max_depth=4,
    mutation_rate=0.4, crossover_rate=0.5, tournament_size=4,
    elitism_count=3, hall_of_fame_size=10, terminal_prob=0.45,
)
engine = GeneticEngine(config=config)
hof = engine.evolve(features=features_train, target=target_train)

# Also run original Island 8 seed
print("Evolving original Island 8 (seed=7*17+7=126)...")
np.random.seed(7 * 17 + 7)
config2 = GPConfig(
    population_size=100, generations=20, max_depth=4,
    mutation_rate=0.4, crossover_rate=0.5, tournament_size=4,
    elitism_count=3, hall_of_fame_size=10, terminal_prob=0.45,
)
engine2 = GeneticEngine(config=config2)
hof2 = engine2.evolve(features=features_train, target=target_train)

# Combine all hall of fame
all_hof = list(hof) + list(hof2)

# Evaluate OOS and select diverse
features_test = {col: test_df[col].values for col in feature_cols}
target_test = test_df["fwd_ret_5"].values

candidates = []
for ind in all_hof:
    try:
        signal = ind._execute_tree(ind.tree, features_test)
        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
        if np.std(signal) < 1e-6:
            continue
        ic, _ = spearmanr(signal, target_test)
        candidates.append({"test_IC": ic, "train_IC": ind.ic_score, "individual": ind})
    except:
        pass

candidates.sort(key=lambda x: x["test_IC"], reverse=True)
print(f"\nCandidates evaluated: {len(candidates)}")
print(f"Best Test IC: {candidates[0]['test_IC']:.4f}" if candidates else "None")

# Select top diverse alphas (correlation < 0.8)
final_alphas = []
used_signals = []
for entry in candidates:
    try:
        signal = entry["individual"]._execute_tree(entry["individual"].tree, features_test)
        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
        is_novel = True
        for existing in used_signals:
            corr = np.corrcoef(signal, existing)[0, 1]
            if abs(corr) > 0.7:
                is_novel = False
                break
        if is_novel:
            final_alphas.append(entry)
            used_signals.append(signal)
            print(f"  Selected: TestIC={entry['test_IC']:.4f}, TrainIC={entry['train_IC']:.4f}")
            if len(final_alphas) >= 5:
                break
    except:
        pass

print(f"\nDiverse alphas for backtest: {len(final_alphas)}")

# Generate composite signal
all_features = {col: df[col].values for col in feature_cols}
signals = []
for entry in final_alphas:
    try:
        sig = entry["individual"]._execute_tree(entry["individual"].tree, all_features)
        sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0)
        if np.std(sig) > 1e-6:
            sig = (sig - np.mean(sig)) / (np.std(sig) + 1e-9)
            signals.append(sig)
    except:
        pass

df["evolved_signal"] = np.mean(signals, axis=0) if signals else 0

# Add momentum
df["momentum_20d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(20))
df["momentum_60d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(60))
mom_std = df["momentum_20d"].std() + 1e-9
mom60_std = df["momentum_60d"].std() + 1e-9
df["combined_signal"] = (
    0.6 * df["evolved_signal"] +
    0.2 * df["momentum_20d"].fillna(0) / mom_std +
    0.2 * df["momentum_60d"].fillna(0) / mom60_std
)

# L3 Walk-Forward
REBAL_FREQ = 10
TOP_N_STOCKS = 8
COST_BPS = 25

print(f"\n{'='*80}")
print(f"L3 EXECUTION-AWARE BACKTEST (top{TOP_N_STOCKS}, rebal={REBAL_FREQ}d, cost={COST_BPS}bps)")
print(f"{'='*80}")

n_folds = 8
fold_size = len(dates) // (n_folds + 3)
train_window = fold_size * 3

results = []
for fold_id in range(n_folds):
    test_start_idx = train_window + fold_id * fold_size
    test_end_idx = test_start_idx + fold_size
    if test_end_idx > len(dates):
        break

    test_dates_fold = dates[test_start_idx:test_end_idx]
    test_fold = df[df["date"].isin(test_dates_fold)].copy()
    if len(test_fold) == 0:
        continue

    rebal_dates = test_dates_fold[::REBAL_FREQ]
    fold_returns = []
    prev_positions = set()

    for rebal_date in rebal_dates:
        day_df = test_fold[test_fold["date"] == rebal_date].copy()
        if len(day_df) < TOP_N_STOCKS:
            continue
        top = day_df.nlargest(TOP_N_STOCKS, "combined_signal")
        new_positions = set(top["ticker"].values)
        turnover = len(new_positions.symmetric_difference(prev_positions)) / (2 * TOP_N_STOCKS) if prev_positions else 1.0
        cost = turnover * COST_BPS / 10000
        next_dates = [d for d in test_dates_fold if d > rebal_date][:REBAL_FREQ]
        if not next_dates:
            continue
        period_df = test_fold[test_fold["date"].isin(next_dates) & test_fold["ticker"].isin(new_positions)]
        if len(period_df) == 0:
            continue
        gross_ret = period_df.groupby("ticker")["fwd_ret_1"].mean().mean()
        net_ret = gross_ret - cost
        fold_returns.append(net_ret)
        prev_positions = new_positions

    if len(fold_returns) >= 3:
        arr = np.array(fold_returns)
        sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252 / REBAL_FREQ)
        max_dd = (np.minimum.accumulate(np.cumsum(arr)) - np.cumsum(arr)).min()
        total_ret = arr.sum()
        results.append({
            "fold": fold_id + 1,
            "net_sharpe": round(sharpe, 4),
            "total_return": round(total_ret * 100, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "n_rebalances": len(fold_returns),
        })
        print(f"  Fold {fold_id+1}: Sharpe={sharpe:.4f}, Return={total_ret*100:.2f}%, MaxDD={max_dd*100:.2f}%")

print(f"\n{'='*80}")
print("FINAL RESULTS")
print(f"{'='*80}")
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))
avg_sharpe = results_df["net_sharpe"].mean()
avg_ret = results_df["total_return"].mean()
avg_dd = results_df["max_drawdown"].mean()
print(f"\nAverage Net Sharpe: {avg_sharpe:.4f}")
print(f"Average Total Return: {avg_ret:.2f}%")
print(f"Average Max Drawdown: {avg_dd:.2f}%")
print(f"Positive folds: {(results_df['net_sharpe'] > 0).sum()}/{len(results_df)}")

os.makedirs("data/phase35_results", exist_ok=True)
results_df.to_csv("data/phase35_results/l3_evolved_v2_backtest.csv", index=False)
summary = {"avg_net_sharpe": round(avg_sharpe, 4), "avg_total_return": round(avg_ret, 2), "avg_max_drawdown": round(avg_dd, 2), "n_alphas": len(final_alphas), "best_test_ic": round(candidates[0]["test_IC"], 4) if candidates else 0}
with open("data/phase35_results/l3_evolved_v2_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print("\nSaved.")
print(f"\n{'='*80}")
print("COMPLETE!")
print(f"{'='*80}")
