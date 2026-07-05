"""Benchmark GP V4 advanced optimizations."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psutil
from joblib import parallel_backend

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))
os.chdir(REPO_ROOT)

import genetic_alpha_evolution_v4 as v4
from omega.quant.evolution.genetic_engine import GPConfig, GeneticEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population-size", type=int, default=150)
    parser.add_argument("--workers", type=int, default=-1)
    parser.add_argument("--backend", choices=["threads", "loky", "multiprocessing"], default="threads")
    parser.add_argument("--min-avg-volume", type=float, default=500000.0)
    parser.add_argument("--avg-volume-window", type=int, default=20)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def _build_features(df):
    features = {col: df[col].to_numpy() for col in v4.v3.FEATURE_COLS}
    features["__date__"] = df["date"].to_numpy()
    features["__log_market_cap__"] = df["__log_market_cap__"].to_numpy()
    features["__sector__"] = df["__sector__"].to_numpy()
    features["__liquidity_mask__"] = df["liquidity_mask"].to_numpy(dtype=bool)
    target = df["fwd_ret_5"].to_numpy(dtype=float)
    return features, target


def build_engine(args: argparse.Namespace, features: dict[str, np.ndarray]) -> GeneticEngine:
    config = GPConfig(
        population_size=args.population_size,
        generations=1,
        max_depth=4,
        tournament_size=3,
        crossover_rate=0.6,
        mutation_rate=0.5,
        elitism_count=1,
        hall_of_fame_size=10,
        diversity_threshold=0.3,
        min_observations=500,
        terminal_prob=0.4,
        use_icir=False,
        use_time_fold_ir=True,
        time_folds=3,
        fold_ir_std_floor=0.03,
        neutralize_size_sector=True,
        icir_window=20,
        ortho_baseline_set={col: features[col] for col in v4.v3.ORTHO_BASELINE_COLS if col in features},
        ortho_penalty_weight=0.08,
        ortho_correlation_threshold=0.4,
        turnover_penalty_weight=0.01,
        tree_size_penalty_weight=0.0005,
        early_stopping_rounds=0,
        tournament_diversity_weight=0.02,
        n_jobs=args.workers,
        use_fast_penalties=True,
        unary_ops=[op for op in GPConfig().unary_ops if op not in ["rank", "cs_rank", "cs_zscore"]],
        ts_ops=[],
        random_seed=args.random_seed,
    )
    return GeneticEngine(config=config)


def _joblib_backend_name(name: str) -> str:
    return "threading" if name == "threads" else name


def run_benchmark(args: argparse.Namespace) -> dict[str, float | int]:
    v4.install_v4_optimizations()
    df = v4.load_dataset(args)
    features, target = _build_features(df)
    engine = build_engine(args, features)
    process = psutil.Process()
    peak_rss = {"bytes": process.memory_info().rss}
    stop_event = threading.Event()

    def sample_rss() -> None:
        while not stop_event.is_set():
            peak_rss["bytes"] = max(peak_rss["bytes"], process.memory_info().rss)
            time.sleep(0.05)

    sampler = threading.Thread(target=sample_rss, daemon=True)
    sampler.start()
    backend = _joblib_backend_name(args.backend)
    with parallel_backend(backend):
        if hasattr(engine, "config"):
            engine.config.generations = 1
        engine.evolve(features=features, target=target)
    with parallel_backend(backend):
        if hasattr(engine, "config"):
            engine.config.generations = 5
        t0 = time.perf_counter()
        engine.evolve(features=features, target=target)
        wall_clock = time.perf_counter() - t0
    stop_event.set()
    sampler.join(timeout=1.0)
    return {
        "wall_clock_seconds": float(wall_clock),
        "peak_rss_mb": float(peak_rss["bytes"] / (1024 * 1024)),
        "population_size": int(args.population_size),
        "workers": int(args.workers),
        "generations": 5,
    }


def main() -> int:
    args = parse_args()
    result = run_benchmark(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
