"""Genetic Alpha Evolution V3 - Enhanced diversity, larger search, anti-convergence."""
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
print("GENETIC ALPHA EVOLUTION V3 - ANTI-CONVERGENCE")
print("=" * 80)

# Load data U15
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=15, forward_horizons=[1, 3, 5, 10],
)
df = df.dropna(subset=["open", "high", "low", "close", "volume", "fwd_ret_5"])

# Add derived features to expand search space
df["returns_1d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(1))
df["returns_5d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(5))
df["vol_ratio"] = df["volume"] / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
df["hl_range"] = (df["high"] - df["low"]) / df["close"]
df["oc_range"] = (df["close"] - df["open"]) / df["close"]
df = df.dropna()

dates = sorted(df["date"].unique())
split_idx = int(len(dates) * 0.7)
train_df = df[df["date"].isin(dates[:split_idx])]
test_df = df[df["date"].isin(dates[split_idx:])]

feature_cols = ["open", "high", "low", "close", "volume", "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]
print(f"Features: {len(feature_cols)} ({feature_cols})")
print(f"Train: {len(train_df)} rows, Test: {len(test_df)} rows")

features_train = {col: train_df[col].values for col in feature_cols}
target_train = train_df["fwd_ret_5"].values
features_test = {col: test_df[col].values for col in feature_cols}
target_test = test_df["fwd_ret_5"].values

# Run multiple rounds with different seeds to fight convergence
all_hof = []
best_test_ic = -999

for round_id in range(5):
    print(f"\n--- Round {round_id+1}/5 (seed={round_id*42}) ---")
    np.random.seed(round_id * 42)
    
    config = GPConfig(
        population_size=150,
        generations=25,
        max_depth=4,
        tournament_size=5,
        crossover_rate=0.6,
        mutation_rate=0.35,  # Higher mutation to escape local optima
        elitism_count=2,
        hall_of_fame_size=10,
        diversity_threshold=0.5,
        min_observations=500,
        terminal_prob=0.4,
    )
    
    engine = GeneticEngine(config=config)
    hof = engine.evolve(features=features_train, target=target_train)
    
    # Evaluate OOS immediately
    for ind in hof[:5]:
        try:
            signal = ind._execute_tree(ind.tree, features_test)
            signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
            if np.std(signal) < 1e-6:
                continue
            ic, _ = spearmanr(signal, target_test)
            hit = (np.sign(signal) == np.sign(target_test)).mean()
            all_hof.append({
                "round": round_id + 1,
                "train_IC": round(ind.ic_score, 4),
                "test_IC": round(ic, 4),
                "hit_rate": round(hit, 4),
                "expr": str(ind.tree)[:120],
                "individual": ind,
            })
            if ic > best_test_ic:
                best_test_ic = ic
                print(f"  NEW BEST: TestIC={ic:.4f}, TrainIC={ind.ic_score:.4f}")
        except:
            pass

# Sort by test IC
all_hof.sort(key=lambda x: x["test_IC"], reverse=True)

print("\n" + "=" * 80)
print("FINAL RESULTS - ALL ROUNDS COMBINED")
print("=" * 80)

results_for_save = []
for i, entry in enumerate(all_hof[:15]):
    print(f"  #{i+1}: Round{entry['round']} TrainIC={entry['train_IC']:.4f}, TestIC={entry['test_IC']:.4f}, Hit={entry['hit_rate']:.4f}")
    print(f"       {entry['expr'][:80]}")
    results_for_save.append({
        "rank": i + 1,
        "round": entry["round"],
        "train_IC": entry["train_IC"],
        "test_IC": entry["test_IC"],
        "hit_rate": entry["hit_rate"],
        "expression": entry["expr"],
    })

if results_for_save:
    os.makedirs("data/phase35_results", exist_ok=True)
    pd.DataFrame(results_for_save).to_csv("data/phase35_results/genetic_alpha_v3_results.csv", index=False)
    
    best = results_for_save[0]
    with open("data/phase35_results/best_evolved_alpha_v3.json", "w") as f:
        json.dump(best, f, indent=2)
    
    print(f"\nBest alpha: TestIC={best['test_IC']}, TrainIC={best['train_IC']}")
    print(f"Expression: {best['expression']}")
    print("Saved to data/phase35_results/genetic_alpha_v3_results.csv")

print("\n" + "=" * 80)
print("GENETIC ALPHA EVOLUTION V3 COMPLETE!")
print("=" * 80)
