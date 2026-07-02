"""Genetic Alpha Evolution V3 - Enhanced diversity, larger search, anti-convergence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import parallel_backend
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(REPO_ROOT)

from omega.core.pit import to_utc_aware
from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.evolution.genetic_engine import GPConfig, GeneticEngine
from phase35_data_loader import Phase35DataLoader

LEGACY_RESULTS_DIR = REPO_ROOT / "data" / "phase35_results"
STABLE_RESULTS_DIR = REPO_ROOT / "data" / "stable"
MODEL_RESULTS_DIR = STABLE_RESULTS_DIR / "genetic_alpha_v3_models"
SESSION_DIR = REPO_ROOT / ".ly_state" / "session"
REGISTRY_DB_URL = f"sqlite:///{(SESSION_DIR / 'conformal_registry.sqlite').as_posix()}"
RESULTS_CSV_NAME = "genetic_alpha_v3_results.csv"
RESULTS_JSONL_NAME = "genetic_alpha_v3_results.jsonl"
BEST_JSON_NAME = "best_evolved_alpha_v3.json"
TOP_K = 15
FEATURE_COLS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "returns_1d",
    "returns_5d",
    "vol_ratio",
    "hl_range",
    "oc_range",
]
ORTHO_BASELINE_COLS = ["open", "high", "low", "close", "volume"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--population-size", type=int, default=150)
    parser.add_argument("--generations", type=int, default=25)
    parser.add_argument("--workers", type=int, default=-1)
    parser.add_argument(
        "--backend",
        choices=["threads", "loky", "multiprocessing"],
        default="threads",
    )
    return parser.parse_args()


def load_dataset() -> pd.DataFrame:
    loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
    df = loader.load_and_prepare(
        start_date="2015-01-05",
        end_date="2026-05-14",
        top_n_symbols=15,
        forward_horizons=[1, 3, 5, 10],
    )
    df = df.dropna(subset=["open", "high", "low", "close", "volume", "fwd_ret_5"])
    df["returns_1d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(1))
    df["returns_5d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(5))
    df["vol_ratio"] = df["volume"] / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]
    df["oc_range"] = (df["close"] - df["open"]) / df["close"]
    return df.dropna()


def build_registry_payload(entry: dict[str, object], artifact_path: Path, version: str, pit_embargo: datetime) -> dict[str, object]:
    return {
        "name": f"genetic_alpha_v3_rank_{int(entry['rank']):02d}",
        "version": version,
        "path": str(artifact_path),
        "status": "ready",
        "metrics": {
            "rank": entry["rank"],
            "round": entry["round"],
            "train_IC": entry["train_IC"],
            "test_IC": entry["test_IC"],
            "hit_rate": entry["hit_rate"],
            "expression": entry["expression"],
            "serialized_tree": entry["serialized_tree"],
        },
        "pit_embargo": pit_embargo,
    }


def export_gp_views(registry: DatabaseRegistry) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    records = registry.list_models(name_prefix="genetic_alpha_v3_rank_", status="ready")
    for record in records:
        metrics = record.metrics or {}
        rows.append(
            {
                "name": record.name,
                "version": record.version,
                "path": record.path,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
                "pit_embargo": record.pit_embargo.isoformat(),
                "rank": metrics.get("rank"),
                "round": metrics.get("round"),
                "train_IC": metrics.get("train_IC"),
                "test_IC": metrics.get("test_IC"),
                "hit_rate": metrics.get("hit_rate"),
                "expression": metrics.get("expression"),
                "serialized_tree": metrics.get("serialized_tree"),
            }
        )
    rows.sort(key=lambda row: (int(row["rank"]), str(row["version"])))
    for directory in (STABLE_RESULTS_DIR, LEGACY_RESULTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(directory / RESULTS_CSV_NAME, index=False)
        with (directory / RESULTS_JSONL_NAME).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
    return rows


def register_top_models(results_for_save: list[dict[str, object]], pit_embargo: datetime) -> list[dict[str, object]]:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    registry = DatabaseRegistry(database_url=REGISTRY_DB_URL)
    registered = 0
    for entry in results_for_save[:TOP_K]:
        version = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_r{int(entry['rank']):02d}"
        artifact_path = MODEL_RESULTS_DIR / f"{version}.json"
        with artifact_path.open("w", encoding="utf-8") as handle:
            json.dump(entry, handle, indent=2)
        registry.register_model(**build_registry_payload(entry, artifact_path, version, pit_embargo))
        registered += 1
    rows = export_gp_views(registry)
    print(f"Registered {registered} evolved models in .ly_state/session/conformal_registry.sqlite")
    return rows


def main() -> int:
    args = parse_args()

    print("=" * 80)
    print("GENETIC ALPHA EVOLUTION V3 - ANTI-CONVERGENCE")
    print("=" * 80)

    df = load_dataset()
    dates = sorted(df["date"].unique())
    split_idx = int(len(dates) * 0.7)
    train_df = df[df["date"].isin(dates[:split_idx])]
    test_df = df[df["date"].isin(dates[split_idx:])]

    print(f"Features: {len(FEATURE_COLS)} ({FEATURE_COLS})")
    print(f"Train: {len(train_df)} rows, Test: {len(test_df)} rows")

    features_train = {col: train_df[col].values for col in FEATURE_COLS}
    target_train = train_df["fwd_ret_5"].values
    features_test = {col: test_df[col].values for col in FEATURE_COLS}
    target_test = test_df["fwd_ret_5"].values
    ortho_baseline_set = {col: features_train[col] for col in ORTHO_BASELINE_COLS}

    all_hof: list[dict[str, object]] = []
    best_test_ic = -999.0

    for round_id in range(args.rounds):
        seed = round_id * 42
        print(f"\n--- Round {round_id + 1}/{args.rounds} (seed={seed}) ---")
        np.random.seed(seed)

        config = GPConfig(
            population_size=args.population_size,
            generations=args.generations,
            max_depth=4,
            tournament_size=5,
            crossover_rate=0.6,
            mutation_rate=0.35,
            elitism_count=2,
            hall_of_fame_size=10,
            diversity_threshold=0.4,
            min_observations=500,
            terminal_prob=0.4,
            ortho_baseline_set=ortho_baseline_set,
            ortho_penalty_weight=0.08,
            ortho_correlation_threshold=0.4,
            n_jobs=args.workers,
        )

        engine = GeneticEngine(config=config)
        with parallel_backend(args.backend):
            hof = engine.evolve(features=features_train, target=target_train)

        for ind in hof[:5]:
            try:
                signal = ind._execute_tree(ind.tree, features_test)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                if np.std(signal) < 1e-6:
                    continue
                ic, _ = spearmanr(signal, target_test)
                hit = (np.sign(signal) == np.sign(target_test)).mean()
                if np.isnan(ic):
                    continue
                all_hof.append(
                    {
                        "round": round_id + 1,
                        "train_IC": round(ind.ic_score, 4),
                        "test_IC": round(float(ic), 4),
                        "hit_rate": round(float(hit), 4),
                        "expr": ind.tree.to_string()[:120],
                        "expression": ind.tree.to_string(),
                        "serialized_tree": repr(ind.tree),
                    }
                )
                if ic > best_test_ic:
                    best_test_ic = float(ic)
                    print(f"  NEW BEST: TestIC={ic:.4f}, TrainIC={ind.ic_score:.4f}")
            except Exception:
                continue

    all_hof.sort(key=lambda x: x["test_IC"], reverse=True)

    print("\n" + "=" * 80)
    print("FINAL RESULTS - ALL ROUNDS COMBINED")
    print("=" * 80)

    results_for_save: list[dict[str, object]] = []
    for i, entry in enumerate(all_hof[:TOP_K]):
        print(
            f"  #{i + 1}: Round{entry['round']} TrainIC={entry['train_IC']:.4f}, "
            f"TestIC={entry['test_IC']:.4f}, Hit={entry['hit_rate']:.4f}"
        )
        print(f"       {entry['expr'][:80]}")
        results_for_save.append(
            {
                "rank": i + 1,
                "round": entry["round"],
                "train_IC": entry["train_IC"],
                "test_IC": entry["test_IC"],
                "hit_rate": entry["hit_rate"],
                "expression": entry["expression"],
                "serialized_tree": entry["serialized_tree"],
            }
        )

    if results_for_save:
        pit_embargo = to_utc_aware(
            datetime.combine(pd.Timestamp(train_df["date"].max()).date(), time.min)
        )
        exported_rows = register_top_models(results_for_save, pit_embargo)

        best = exported_rows[0]
        with (STABLE_RESULTS_DIR / BEST_JSON_NAME).open("w", encoding="utf-8") as handle:
            json.dump(best, handle, indent=2)
        with (LEGACY_RESULTS_DIR / BEST_JSON_NAME).open("w", encoding="utf-8") as handle:
            json.dump(best, handle, indent=2)

        print(f"\nBest alpha: TestIC={best['test_IC']}, TrainIC={best['train_IC']}")
        print(f"Expression: {best['expression']}")
        print("Saved DB-backed GP views to data/stable/genetic_alpha_v3_results.csv")

    print("\n" + "=" * 80)
    print("GENETIC ALPHA EVOLUTION V3 COMPLETE!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
