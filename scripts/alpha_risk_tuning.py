"""Section 7+8: Alpha & Risk Tuning - Coarse Grid Search."""
import sys
import os
import itertools
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from phase35_data_loader import Phase35DataLoader
from omega.quant.phase34_microstructure_alphas import compute_phase34_microstructure_alphas

print("=" * 80)
print("ALPHA & RISK TUNING - COARSE GRID SEARCH")
print("=" * 80)

# Load data U50
print("\nLoading data (U50)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=50, forward_horizons=[1, 3, 5, 10],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

# Generate alphas
print("Generating alpha signals...")
alpha_df = compute_phase34_microstructure_alphas(df)
alpha_cols = [c for c in alpha_df.columns if c.startswith("alpha_")]

# All alphas available
ALL_ALPHAS = alpha_cols
print(f"Available alphas: {len(ALL_ALPHAS)}")

# Grid parameters (per plan Section 7.2 + 8.1)
GRID = {
    "top_n_stocks": [5, 8, 12],
    "rebalance_freq": [5, 10, 20],
    "top_n_alphas": [3, 5, 7],
    "return_horizon": ["fwd_ret_1", "fwd_ret_3", "fwd_ret_5"],
    "weighting": ["equal", "ic_weighted"],
}

SLIPPAGE_BPS = 10
COMMISSION_BPS = 15
COST_BPS = SLIPPAGE_BPS + COMMISSION_BPS

# Walk-forward engine
dates = sorted(alpha_df["date"].unique())
n_folds = 8
fold_size = len(dates) // (n_folds + 3)
train_window = fold_size * 3


def run_config(top_n_stocks, rebalance_freq, top_n_alphas, return_horizon, weighting):
    """Run one config through walk-forward and return metrics."""
    fold_results = []

    for fold_id in range(n_folds):
        test_start_idx = train_window + fold_id * fold_size
        test_end_idx = test_start_idx + fold_size
        if test_end_idx > len(dates):
            break

        train_dates = dates[test_start_idx - train_window:test_start_idx]
        test_dates_fold = dates[test_start_idx:test_end_idx]

        train_df = alpha_df[alpha_df["date"].isin(train_dates)]
        test_df = alpha_df[alpha_df["date"].isin(test_dates_fold)].copy()

        if len(test_df) == 0 or len(train_df) == 0:
            continue

        # Select top alphas by train IC
        train_ics = {}
        for col in ALL_ALPHAS:
            valid = train_df[[col, return_horizon]].dropna()
            if len(valid) > 50:
                train_ics[col] = valid[col].rank().corr(valid[return_horizon].rank())
        
        sorted_alphas = sorted(train_ics.items(), key=lambda x: abs(x[1]), reverse=True)
        selected = [a[0] for a in sorted_alphas[:top_n_alphas]]

        if len(selected) == 0:
            continue

        # Composite signal
        if weighting == "ic_weighted":
            weights_alpha = np.array([abs(train_ics[a]) for a in selected])
            weights_alpha = weights_alpha / weights_alpha.sum()
            test_df["signal"] = sum(test_df[a] * w for a, w in zip(selected, weights_alpha))
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

            # Top N by signal
            top = day_df.nlargest(top_n_stocks, "signal")
            new_positions = set(top["ticker"].values)

            # Turnover
            if prev_positions:
                turnover = len(new_positions.symmetric_difference(prev_positions)) / (2 * top_n_stocks)
            else:
                turnover = 1.0

            cost = turnover * COST_BPS / 10000

            # Next period return (equal weight)
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

        if len(fold_returns) >= 5:
            arr = np.array(fold_returns)
            sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252 / rebalance_freq)
            max_dd = (np.minimum.accumulate(np.cumsum(arr)) - np.cumsum(arr)).min()
            total_ret = arr.sum()
            fold_results.append({
                "sharpe": sharpe,
                "max_dd": max_dd,
                "total_ret": total_ret,
                "positive": 1 if total_ret > 0 else 0,
            })

    if len(fold_results) < 4:
        return None

    avg_sharpe = np.mean([f["sharpe"] for f in fold_results])
    avg_dd = np.mean([f["max_dd"] for f in fold_results])
    avg_ret = np.mean([f["total_ret"] for f in fold_results])
    pct_positive = np.mean([f["positive"] for f in fold_results])
    worst_dd = min(f["max_dd"] for f in fold_results)

    # Hard gate rejection (Section 8.3)
    if worst_dd < -0.25:
        return None
    if avg_dd < -0.15:
        return None
    if pct_positive < 0.4:
        return None

    # Score (Section 8.2 simplified)
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
print(f"\nRunning coarse grid ({len(GRID['top_n_stocks'])*len(GRID['rebalance_freq'])*len(GRID['top_n_alphas'])*len(GRID['return_horizon'])*len(GRID['weighting'])} configs)...")
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
        print(f"  Processed {config_id} configs, {len(all_results)} passed gates...")

print(f"\nTotal configs tested: {config_id}")
print(f"Configs passing hard gates: {len(all_results)}")

if len(all_results) > 0:
    results_df = pd.DataFrame(all_results).sort_values("score", ascending=False)
    print("\n=== TOP 10 CONFIGURATIONS ===")
    print(results_df.head(10)[["config", "avg_sharpe", "avg_ret", "avg_dd", "worst_dd", "pct_positive", "score"]].to_string(index=False))

    os.makedirs("data/phase35_results", exist_ok=True)
    results_df.to_csv("data/phase35_results/alpha_risk_tuning_grid.csv", index=False)
    
    # Save best config
    best = results_df.iloc[0].to_dict()
    with open("data/phase35_results/best_config.json", "w") as f:
        json.dump(best, f, indent=2, default=str)
    
    print(f"\nBest config: {best['config']}")
    print(f"  Sharpe: {best['avg_sharpe']}, Return: {best['avg_ret']}%, DD: {best['avg_dd']}%")
    print("\nSaved to data/phase35_results/alpha_risk_tuning_grid.csv")
    print("Best config saved to data/phase35_results/best_config.json")
else:
    print("\nNo configs passed hard gates. Alpha signals too weak for current cost assumptions.")
    print("Recommendation: reduce costs, increase rebalance freq, or find stronger alphas.")

print("\n" + "=" * 80)
print("ALPHA & RISK TUNING COMPLETE!")
print("=" * 80)
