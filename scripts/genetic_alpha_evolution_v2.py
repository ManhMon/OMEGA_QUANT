"""Genetic Alpha Evolution V2 - Correct API call."""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
import numpy as np
from phase35_data_loader import Phase35DataLoader
from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig

print("=" * 80)
print("GENETIC ALPHA EVOLUTION V2")
print("=" * 80)

# Load data U15
print("\nLoading data (U15)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=15, forward_horizons=[1, 3, 5, 10],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

feature_cols = ["open", "high", "low", "close", "volume"]
target_col = "fwd_ret_5"

df = df.dropna(subset=feature_cols + [target_col])
print(f"Rows after dropna: {len(df)}")

# Split train/test (70/30 chronological)
dates = sorted(df["date"].unique())
split_idx = int(len(dates) * 0.7)
train_dates = dates[:split_idx]
test_dates = dates[split_idx:]

train_df = df[df["date"].isin(train_dates)].copy()
test_df = df[df["date"].isin(test_dates)].copy()
print(f"Train: {len(train_df)} rows ({len(train_dates)} days)")
print(f"Test: {len(test_df)} rows ({len(test_dates)} days)")

# Configure GP
config = GPConfig(
    population_size=200,
    generations=50,
    max_depth=4,
    tournament_size=7,
    crossover_rate=0.7,
    mutation_rate=0.25,
    elitism_count=5,
    hall_of_fame_size=20,
    diversity_threshold=0.6,
    min_observations=500,
    terminal_prob=0.3,
)

print(f"\nGP Config: pop={config.population_size}, gen={config.generations}, depth={config.max_depth}")
print("Starting evolution...")

# Prepare features as Dict[str, np.ndarray] and target as np.ndarray
features = {col: train_df[col].values for col in feature_cols}
target = train_df[target_col].values

engine = GeneticEngine(config=config)
hall_of_fame = engine.evolve(features=features, target=target)

print(f"\nEvolution complete! Hall of Fame: {len(hall_of_fame)} alphas")

# Evaluate on test set
print("\n" + "=" * 80)
print("OUT-OF-SAMPLE EVALUATION (Test Set)")
print("=" * 80)

test_features = {col: test_df[col].values for col in feature_cols}
test_target = test_df[target_col].values

eval_results = []
for i, individual in enumerate(hall_of_fame[:20]):
    try:
        if hasattr(individual, "expression"):
            expr = str(individual.expression)
        elif hasattr(individual, "tree"):
            expr = str(individual.tree)
        else:
            expr = str(individual)

        # Evaluate signal on test
        if hasattr(individual, "evaluate"):
            individual.evaluate(test_features, test_target, [], config)
            signal = individual.predictions if hasattr(individual, "predictions") else None
        
        if signal is None and hasattr(individual, "execute"):
            signal = individual.execute(test_features)

        if signal is None and hasattr(individual, "tree"):
            # Try direct tree evaluation
            from omega.quant.evolution.genetic_engine import GPNode
            signal = individual.tree.evaluate(test_features) if hasattr(individual.tree, "evaluate") else None

        if signal is not None and len(signal) == len(test_target):
            signal_s = pd.Series(signal)
            target_s = pd.Series(test_target)
            valid_mask = signal_s.notna() & target_s.notna() & np.isfinite(signal_s)
            
            if valid_mask.sum() > 100:
                sig_valid = signal_s[valid_mask]
                tgt_valid = target_s[valid_mask]
                
                ic = sig_valid.corr(tgt_valid)
                rank_ic = sig_valid.rank().corr(tgt_valid.rank())
                hit_rate = (np.sign(sig_valid) == np.sign(tgt_valid)).mean()

                eval_results.append({
                    "rank": i + 1,
                    "expression": expr[:100],
                    "train_IC": round(individual.ic_score, 4) if hasattr(individual, "ic_score") else None,
                    "test_IC": round(ic, 4),
                    "test_RankIC": round(rank_ic, 4),
                    "hit_rate": round(hit_rate, 4),
                })
                print(f"  #{i+1}: TrainIC={individual.ic_score:.4f}, TestIC={ic:.4f}, TestRankIC={rank_ic:.4f}, Hit={hit_rate:.4f}")
                print(f"       {expr[:100]}")
    except Exception as e:
        print(f"  #{i+1}: Error: {e}")

if eval_results:
    eval_df = pd.DataFrame(eval_results).sort_values("test_RankIC", ascending=False)
    os.makedirs("data/phase35_results", exist_ok=True)
    eval_df.to_csv("data/phase35_results/genetic_alpha_evolution_results.csv", index=False)
    
    print(f"\n=== TOP 5 EVOLVED ALPHAS (by Test RankIC) ===")
    print(eval_df.head(5).to_string(index=False))
    
    best = eval_df.iloc[0]
    print(f"\nBest evolved alpha:")
    print(f"  Test RankIC: {best['test_RankIC']}")
    print(f"  Test IC: {best['test_IC']}")
    print(f"  Hit Rate: {best['hit_rate']}")
    print(f"  Expression: {best['expression']}")
    
    with open("data/phase35_results/best_evolved_alpha.json", "w") as f:
        json.dump(best.to_dict(), f, indent=2, default=str)
    print("\nSaved to data/phase35_results/genetic_alpha_evolution_results.csv")
else:
    print("\nNo alphas could be evaluated on test set.")

print("\n" + "=" * 80)
print("GENETIC ALPHA EVOLUTION V2 COMPLETE!")
print("=" * 80)
