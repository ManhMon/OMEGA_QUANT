"""Genetic Alpha Evolution - Tự tiến hoá tìm alpha mạnh hơn."""
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
print("GENETIC ALPHA EVOLUTION")
print("=" * 80)

# Load data U15
print("\nLoading data (U15)...")
loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
df = loader.load_and_prepare(
    start_date="2015-01-05", end_date="2026-05-14",
    top_n_symbols=15, forward_horizons=[1, 3, 5, 10],
)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

# Prepare features for GP
feature_cols = ["open", "high", "low", "close", "volume"]
target_col = "fwd_ret_5"

# Drop NaN
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

# Run GP
engine = GeneticEngine(config=config)

try:
    results = engine.evolve(
        data=train_df,
        feature_columns=feature_cols,
        target_column=target_col,
    )
except Exception as e:
    print(f"Evolution error: {e}")
    print("Trying alternative approach...")
    # Fallback: run with numpy arrays
    try:
        results = engine.evolve(
            data=train_df[feature_cols + [target_col]],
            feature_columns=feature_cols,
            target_column=target_col,
        )
    except Exception as e2:
        print(f"Fallback also failed: {e2}")
        print("Checking engine.run() or engine.fit() methods...")
        import inspect
        methods = [m for m in dir(engine) if not m.startswith("_")]
        print(f"Available methods: {methods}")
        results = None

if results is not None:
    print("\n" + "=" * 80)
    print("EVOLUTION RESULTS")
    print("=" * 80)

    # Extract hall of fame
    if hasattr(results, "hall_of_fame"):
        hof = results.hall_of_fame
    elif hasattr(engine, "hall_of_fame"):
        hof = engine.hall_of_fame
    elif isinstance(results, list):
        hof = results
    elif isinstance(results, dict) and "hall_of_fame" in results:
        hof = results["hall_of_fame"]
    else:
        hof = [results] if results else []
        print(f"Results type: {type(results)}")
        print(f"Results keys: {results.keys() if isinstance(results, dict) else 'N/A'}")

    print(f"\nHall of Fame: {len(hof)} alphas")

    # Evaluate top alphas on test set
    eval_results = []
    for i, individual in enumerate(hof[:10]):
        try:
            if hasattr(individual, "expression"):
                expr = str(individual.expression)
            elif hasattr(individual, "tree"):
                expr = str(individual.tree)
            else:
                expr = str(individual)

            # Generate signal on test data
            if hasattr(individual, "evaluate"):
                signal = individual.evaluate(test_df[feature_cols])
            elif hasattr(engine, "evaluate_individual"):
                signal = engine.evaluate_individual(individual, test_df[feature_cols])
            else:
                signal = None

            if signal is not None:
                signal_series = pd.Series(signal, index=test_df.index)
                valid = pd.DataFrame({"signal": signal_series, "target": test_df[target_col]}).dropna()

                if len(valid) > 100:
                    ic = valid["signal"].corr(valid["target"])
                    rank_ic = valid["signal"].rank().corr(valid["target"].rank())
                    hit_rate = (np.sign(valid["signal"]) == np.sign(valid["target"])).mean()

                    eval_results.append({
                        "rank": i + 1,
                        "expression": expr[:80],
                        "test_IC": round(ic, 4),
                        "test_RankIC": round(rank_ic, 4),
                        "hit_rate": round(hit_rate, 4),
                    })
                    print(f"  #{i+1}: IC={ic:.4f}, RankIC={rank_ic:.4f}, HitRate={hit_rate:.4f}")
                    print(f"       Expr: {expr[:80]}")
        except Exception as e:
            print(f"  #{i+1}: Eval error: {e}")

    if eval_results:
        eval_df = pd.DataFrame(eval_results)
        os.makedirs("data/phase35_results", exist_ok=True)
        eval_df.to_csv("data/phase35_results/genetic_alpha_evolution_results.csv", index=False)
        print(f"\nSaved {len(eval_results)} evolved alphas to data/phase35_results/genetic_alpha_evolution_results.csv")

        best = eval_results[0]
        print(f"\nBest evolved alpha:")
        print(f"  IC: {best['test_IC']}, RankIC: {best['test_RankIC']}, HitRate: {best['hit_rate']}")
        print(f"  Expression: {best['expression']}")
else:
    print("\nEvolution did not produce results. Checking engine state...")
    if hasattr(engine, "hall_of_fame") and engine.hall_of_fame:
        print(f"Hall of fame has {len(engine.hall_of_fame)} entries")
    if hasattr(engine, "best_individual"):
        print(f"Best individual: {engine.best_individual}")

print("\n" + "=" * 80)
print("GENETIC ALPHA EVOLUTION COMPLETE!")
print("=" * 80)
