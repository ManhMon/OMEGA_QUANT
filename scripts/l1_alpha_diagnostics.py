"""L1 Alpha Diagnostics - IC, Rank IC, Hit Rate, Turnover per alpha signal."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from omega.quant.phase34_microstructure_alphas import compute_phase34_microstructure_alphas
from phase35_data_loader import Phase35DataLoader

print("=== L1 ALPHA DIAGNOSTICS ===")
print("Loading data (U30)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05",
    end_date="2026-05-14",
    top_n_symbols=30,
    forward_horizons=[1, 3, 5, 10],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

# Generate alphas
alpha_df = compute_phase34_microstructure_alphas(df)
alpha_cols = [c for c in alpha_df.columns if c.startswith("alpha_")]
print(f"Alpha signals generated: {len(alpha_cols)}")

# IC per alpha
results = []
for col in alpha_cols:
    valid = alpha_df[[col, "fwd_ret_1"]].dropna()
    if len(valid) > 100:
        ic = valid[col].corr(valid["fwd_ret_1"])
        rank_ic = valid[col].rank().corr(valid["fwd_ret_1"].rank())
        hit_rate = (np.sign(valid[col]) == np.sign(valid["fwd_ret_1"])).mean()
        turnover = valid[col].diff().abs().mean()
        results.append({
            "alpha": col,
            "IC": round(ic, 4),
            "RankIC": round(rank_ic, 4),
            "HitRate": round(hit_rate, 4),
            "Turnover": round(turnover, 4),
        })

results_df = pd.DataFrame(results).sort_values("RankIC", ascending=False)
print()
print("=== ALPHA IC DIAGNOSTICS (U30) ===")
print(results_df.to_string(index=False))
print()
print(f"Alphas with positive RankIC: {(results_df['RankIC'] > 0).sum()}/{len(results_df)}")
print(f"Best alpha: {results_df.iloc[0]['alpha']} (RankIC={results_df.iloc[0]['RankIC']})")
print()
print("=== L1 ALPHA DIAGNOSTICS COMPLETE ===")

os.makedirs("data/phase35_results", exist_ok=True)
results_df.to_csv("data/phase35_results/l1_alpha_diagnostics_u30.csv", index=False)
print("Saved to data/phase35_results/l1_alpha_diagnostics_u30.csv")
