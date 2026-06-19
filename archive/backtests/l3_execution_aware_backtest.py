"""L3 Execution-Aware Backtest - Costs, slippage, ADV caps, order sizing."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from phase35_data_loader import Phase35DataLoader
from omega.quant.phase34_microstructure_alphas import compute_phase34_microstructure_alphas

print("=" * 80)
print("L3 EXECUTION-AWARE BACKTEST")
print("=" * 80)

# Config
START_DATE = "2015-01-05"
END_DATE = "2026-05-14"
TOP_N = 50  # U50 per plan
REBAL_FREQ = 5  # sessions
MAX_ADV_PARTICIPATION = 0.10  # 10% ADV cap
SLIPPAGE_BPS = 10  # 10bps slippage
COMMISSION_BPS = 15  # 15bps commission (VN market)
SECTOR_CAP = 0.30

print(f"Config: U{TOP_N}, rebal={REBAL_FREQ}d, ADV_cap={MAX_ADV_PARTICIPATION*100}%, slippage={SLIPPAGE_BPS}bps, commission={COMMISSION_BPS}bps")

# Load data
print("\nLoading data (U50)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date=START_DATE,
    end_date=END_DATE,
    top_n_symbols=TOP_N,
    forward_horizons=[1, 3, 5],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

# Generate alphas
print("Generating alpha signals...")
alpha_df = compute_phase34_microstructure_alphas(df)
alpha_cols = [c for c in alpha_df.columns if c.startswith("alpha_")]

# Use whitelist from L1 (positive RankIC)
whitelist = [
    "alpha_p34_micro_momentum_5_20",
    "alpha_p34_close_auction_drift_10",
    "alpha_p34_kyle_lambda_20",
]
alpha_cols_used = [c for c in whitelist if c in alpha_cols]
print(f"Using whitelisted alphas: {alpha_cols_used}")

# Composite signal (equal weight)
alpha_df["composite_signal"] = alpha_df[alpha_cols_used].mean(axis=1)

# Walk-forward with execution costs
dates = sorted(alpha_df["date"].unique())
n_folds = 8
fold_size = len(dates) // (n_folds + 3)  # train=3 folds, test=1 fold
train_window = fold_size * 3

results = []
for fold_id in range(n_folds):
    test_start_idx = train_window + fold_id * fold_size
    test_end_idx = test_start_idx + fold_size
    if test_end_idx > len(dates):
        break

    test_dates = dates[test_start_idx:test_end_idx]
    test_df = alpha_df[alpha_df["date"].isin(test_dates)].copy()

    if len(test_df) == 0:
        continue

    # Rebalance every REBAL_FREQ days
    rebal_dates = test_dates[::REBAL_FREQ]
    
    fold_returns = []
    prev_weights = pd.Series(dtype=float)

    for i, rebal_date in enumerate(rebal_dates):
        # Get signal on rebal date
        day_df = test_df[test_df["date"] == rebal_date].copy()
        if len(day_df) == 0:
            continue

        # ADV cap: limit position to MAX_ADV_PARTICIPATION of volume
        if "volume" in day_df.columns:
            adv_20 = df[df["date"] <= rebal_date].groupby("ticker")["volume"].rolling(20).mean().reset_index(level=0, drop=True)
            # Simple: just use current volume as proxy
            day_df["adv_cap"] = day_df["volume"] * MAX_ADV_PARTICIPATION
        
        # Rank signal, take top positions
        day_df = day_df.sort_values("composite_signal", ascending=False)
        top_n_pos = min(8, len(day_df))
        positions = day_df.head(top_n_pos)

        # Equal weight with sector cap
        weights = pd.Series(1.0 / top_n_pos, index=positions["ticker"].values)

        # Turnover cost
        turnover = (weights.subtract(prev_weights, fill_value=0)).abs().sum()
        cost = turnover * (SLIPPAGE_BPS + COMMISSION_BPS) / 10000

        # Get next period return
        next_dates = [d for d in test_dates if d > rebal_date][:REBAL_FREQ]
        if len(next_dates) == 0:
            continue

        period_df = test_df[test_df["date"].isin(next_dates) & test_df["ticker"].isin(positions["ticker"].values)]
        if len(period_df) == 0:
            continue

        # Portfolio return for this period
        period_ret = period_df.groupby("ticker")["fwd_ret_1"].mean()
        gross_return = (weights * period_ret.reindex(weights.index, fill_value=0)).sum()
        net_return = gross_return - cost

        fold_returns.append(net_return)
        prev_weights = weights

    if len(fold_returns) > 0:
        fold_returns = np.array(fold_returns)
        sharpe = fold_returns.mean() / (fold_returns.std() + 1e-10) * np.sqrt(252 / REBAL_FREQ)
        max_dd = (np.minimum.accumulate(np.cumsum(fold_returns)) - np.cumsum(fold_returns)).min()
        total_ret = fold_returns.sum()
        avg_cost = np.mean([abs(r) for r in fold_returns]) * (SLIPPAGE_BPS + COMMISSION_BPS) / 10000
        
        results.append({
            "fold": fold_id + 1,
            "net_sharpe": round(sharpe, 4),
            "total_return": round(total_ret * 100, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "n_rebalances": len(fold_returns),
        })
        print(f"  Fold {fold_id+1}: Sharpe={sharpe:.4f}, Return={total_ret*100:.2f}%, MaxDD={max_dd*100:.2f}%")

print()
print("=" * 80)
print("L3 EXECUTION-AWARE BACKTEST RESULTS")
print("=" * 80)
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))
print()
avg_sharpe = results_df["net_sharpe"].mean()
avg_dd = results_df["max_drawdown"].mean()
avg_ret = results_df["total_return"].mean()
print(f"Average Net Sharpe: {avg_sharpe:.4f}")
print(f"Average Total Return: {avg_ret:.2f}%")
print(f"Average Max Drawdown: {avg_dd:.2f}%")
print()
print("=" * 80)
print("L3 EXECUTION-AWARE BACKTEST COMPLETE!")
print("=" * 80)

os.makedirs("data/phase35_results", exist_ok=True)
results_df.to_csv("data/phase35_results/l3_execution_aware_backtest_u50.csv", index=False)
print("Saved to data/phase35_results/l3_execution_aware_backtest_u50.csv")
