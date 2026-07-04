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
EMBARGO_TRADING_DAYS = 5
UNIVERSE_LOOKBACK_TRADING_DAYS = 252
FEATURE_COLS = [
    "returns_1d",
    "returns_5d",
    "vol_ratio",
    "hl_range",
    "oc_range",
    "hl_range_cs_z",
    "oc_range_cs_z",
]
ORTHO_BASELINE_COLS = ["returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]


def _cs_zscore_by_date(values: pd.Series, dates: pd.Series) -> pd.Series:
    return values.groupby(dates).transform(lambda x: (x - x.mean()) / (x.std(ddof=0) + 1e-9))


def _volume_quartile_sector_proxy(volumes: pd.Series, dates: pd.Series) -> pd.Series:
    def _per_date_bucket(day_volume: pd.Series) -> pd.Series:
        rank = day_volume.rank(method="first")
        return pd.qcut(rank, 4, labels=False, duplicates="drop")

    return volumes.groupby(dates).transform(_per_date_bucket).astype(np.int64)


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
        top_n_symbols=None,
        forward_horizons=[1, 3, 5, 10],
    )
    df = df.sort_values(["ticker", "date"]).copy()
    df = df.dropna(subset=["open", "high", "low", "close", "volume", "fwd_ret_5"])
    df["returns_1d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(1))
    df["returns_5d"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(5))
    df["vol_ratio"] = df["volume"] / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]
    df["oc_range"] = (df["close"] - df["open"]) / df["close"]
    df["hl_range_cs_z"] = _cs_zscore_by_date(df["hl_range"], df["date"])
    df["oc_range_cs_z"] = _cs_zscore_by_date(df["oc_range"], df["date"])
    df["__log_market_cap__"] = np.log1p((df["close"] * df["volume"]).clip(lower=0.0))
    df["__sector__"] = _volume_quartile_sector_proxy(df["volume"], df["date"])
    df[FEATURE_COLS] = df.groupby("ticker")[FEATURE_COLS].shift(1)
    df["__log_market_cap__"] = df.groupby("ticker")["__log_market_cap__"].shift(1)
    df["__sector__"] = df.groupby("ticker")["__sector__"].shift(1)
    return df.dropna(subset=FEATURE_COLS + ["fwd_ret_5", "__log_market_cap__", "__sector__"])


def compute_daily_cs_ic(signal: np.ndarray, target: np.ndarray, dates: np.ndarray) -> float:
    daily_ics: list[float] = []
    for current_date in pd.unique(pd.Series(dates).dropna()):
        mask = dates == current_date
        valid = mask & np.isfinite(signal) & np.isfinite(target)
        if np.count_nonzero(valid) <= 5:
            continue
        ic_value, _ = spearmanr(signal[valid], target[valid])
        if not np.isnan(ic_value):
            daily_ics.append(float(ic_value))
    return float(np.mean(daily_ics)) if daily_ics else 0.0


def build_split_windows(dates: list[pd.Timestamp]) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    if len(dates) <= UNIVERSE_LOOKBACK_TRADING_DAYS + (3 * EMBARGO_TRADING_DAYS) + 30:
        raise ValueError("Not enough trading days for PIT train/val/oos/lockbox split")
    usable = len(dates) - UNIVERSE_LOOKBACK_TRADING_DAYS - (3 * EMBARGO_TRADING_DAYS)
    train_len = max(int(usable * 0.55), 20)
    val_len = max(int(usable * 0.15), 10)
    oos_len = max(int(usable * 0.15), 10)
    lockbox_len = usable - train_len - val_len - oos_len
    if lockbox_len <= 0:
        raise ValueError("Lockbox window collapsed; increase data range")

    idx = UNIVERSE_LOOKBACK_TRADING_DAYS
    train = (dates[idx], dates[idx + train_len - 1])
    idx += train_len + EMBARGO_TRADING_DAYS
    val = (dates[idx], dates[idx + val_len - 1])
    idx += val_len + EMBARGO_TRADING_DAYS
    oos = (dates[idx], dates[idx + oos_len - 1])
    idx += oos_len + EMBARGO_TRADING_DAYS
    lockbox = (dates[idx], dates[-1])
    return {"train": train, "val": val, "oos": oos, "lockbox": lockbox}


def build_pit_splits(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    loader = Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
    unique_dates = [pd.Timestamp(date) for date in sorted(df["date"].unique())]
    windows = build_split_windows(unique_dates)
    split_frames: dict[str, pd.DataFrame] = {}
    for split_name, (start_date, end_date) in windows.items():
        split_df, _evidence = loader.select_pit_universe_for_window(
            df,
            start_date,
            end_date,
            top_n=100,
            lookback_trading_days=UNIVERSE_LOOKBACK_TRADING_DAYS,
        )
        split_frames[split_name] = split_df.sort_values(["ticker", "date"]).copy()
    return split_frames


def build_registry_payload(entry: dict[str, object], artifact_path: Path, version: str, pit_embargo: datetime) -> dict[str, object]:
    return {
        "name": f"genetic_alpha_v3_rank_{int(entry['rank']):02d}",
        "version": version,
        "path": str(artifact_path),
        "status": "ready",
            "metrics": {
                "rank": entry["rank"],
                "round": entry["round"],
                "train_FoldIR": entry["train_FoldIR"],
                "train_IC_daily": entry["train_IC_daily"],
                "val_IC_daily": entry["val_IC_daily"],
                "oos_IC_daily": entry["oos_IC_daily"],
                "lockbox_IC_daily": entry["lockbox_IC_daily"],
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
                "train_FoldIR": metrics.get("train_FoldIR"),
                "train_IC_daily": metrics.get("train_IC_daily"),
                "val_IC_daily": metrics.get("val_IC_daily"),
                "oos_IC_daily": metrics.get("oos_IC_daily"),
                "lockbox_IC_daily": metrics.get("lockbox_IC_daily"),
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
    split_frames = build_pit_splits(df)
    train_df = split_frames["train"]
    val_df = split_frames["val"]
    oos_df = split_frames["oos"]
    lockbox_df = split_frames["lockbox"]

    print(f"Features: {len(FEATURE_COLS)} ({FEATURE_COLS})")
    print(
        f"Train/Val/OOS/Lockbox: {len(train_df)}/{len(val_df)}/{len(oos_df)}/{len(lockbox_df)} rows"
    )

    features_train = {col: train_df[col].values for col in FEATURE_COLS}
    features_train["__date__"] = train_df["date"].values
    features_train["__log_market_cap__"] = train_df["__log_market_cap__"].values
    features_train["__sector__"] = train_df["__sector__"].values
    target_train = train_df["fwd_ret_5"].values
    features_val = {col: val_df[col].values for col in FEATURE_COLS}
    features_val["__date__"] = val_df["date"].values
    features_val["__log_market_cap__"] = val_df["__log_market_cap__"].values
    features_val["__sector__"] = val_df["__sector__"].values
    target_val = val_df["fwd_ret_5"].values
    features_oos = {col: oos_df[col].values for col in FEATURE_COLS}
    features_oos["__date__"] = oos_df["date"].values
    features_oos["__log_market_cap__"] = oos_df["__log_market_cap__"].values
    features_oos["__sector__"] = oos_df["__sector__"].values
    target_oos = oos_df["fwd_ret_5"].values
    features_lockbox = {col: lockbox_df[col].values for col in FEATURE_COLS}
    features_lockbox["__date__"] = lockbox_df["date"].values
    features_lockbox["__log_market_cap__"] = lockbox_df["__log_market_cap__"].values
    features_lockbox["__sector__"] = lockbox_df["__sector__"].values
    target_lockbox = lockbox_df["fwd_ret_5"].values
    ortho_baseline_set = {col: features_train[col] for col in ORTHO_BASELINE_COLS}

    all_hof: list[dict[str, object]] = []
    best_val_ic = -999.0

    for round_id in range(args.rounds):
        seed = round_id * 42
        print(f"\n--- Round {round_id + 1}/{args.rounds} (seed={seed}) ---")
        np.random.seed(seed)

        config = GPConfig(
            population_size=args.population_size,
            generations=args.generations,
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
            time_folds=8,
            fold_ir_std_floor=0.03,
            neutralize_size_sector=True,
            icir_window=20,
            ortho_baseline_set=ortho_baseline_set,
            ortho_penalty_weight=0.08,
            ortho_correlation_threshold=0.4,
            turnover_penalty_weight=0.01,
            tree_size_penalty_weight=0.0005,
            early_stopping_rounds=10,
            tournament_diversity_weight=0.02,
            n_jobs=args.workers,
            use_fast_penalties=True,
            unary_ops=[op for op in GPConfig().unary_ops if op not in ["rank", "cs_rank", "cs_zscore"]],
            ts_ops=[],
        )

        engine = GeneticEngine(config=config)
        backend = "threading" if args.backend == "threads" else args.backend
        with parallel_backend(backend):
            hof = engine.evolve(features=features_train, target=target_train)

        for ind in hof[:5]:
            try:
                train_signal = np.nan_to_num(ind._execute_tree(ind.tree, features_train), nan=0.0, posinf=0.0, neginf=0.0)
                val_signal = np.nan_to_num(ind._execute_tree(ind.tree, features_val), nan=0.0, posinf=0.0, neginf=0.0)
                oos_signal = np.nan_to_num(ind._execute_tree(ind.tree, features_oos), nan=0.0, posinf=0.0, neginf=0.0)
                lockbox_signal = np.nan_to_num(ind._execute_tree(ind.tree, features_lockbox), nan=0.0, posinf=0.0, neginf=0.0)
                if min(np.std(train_signal), np.std(val_signal), np.std(oos_signal), np.std(lockbox_signal)) < 1e-6:
                    continue
                train_ic_daily = compute_daily_cs_ic(train_signal, target_train, train_df["date"].values)
                val_ic_daily = compute_daily_cs_ic(val_signal, target_val, val_df["date"].values)
                oos_ic_daily = compute_daily_cs_ic(oos_signal, target_oos, oos_df["date"].values)
                lockbox_ic_daily = compute_daily_cs_ic(lockbox_signal, target_lockbox, lockbox_df["date"].values)
                hit = (np.sign(val_signal) == np.sign(target_val)).mean()
                if np.isnan(val_ic_daily):
                    continue
                all_hof.append(
                    {
                        "round": round_id + 1,
                        "train_FoldIR": round(ind.ic_score, 4),
                        "train_IC_daily": round(train_ic_daily, 4),
                        "val_IC_daily": round(val_ic_daily, 4),
                        "oos_IC_daily": round(oos_ic_daily, 4),
                        "lockbox_IC_daily": round(lockbox_ic_daily, 4),
                        "hit_rate": round(float(hit), 4),
                        "expr": ind.tree.to_string()[:120],
                        "expression": ind.tree.to_string(),
                        "serialized_tree": repr(ind.tree),
                    }
                )
                if val_ic_daily > best_val_ic:
                    best_val_ic = float(val_ic_daily)
                    print(
                        f"  NEW BEST: ValIC_daily={val_ic_daily:.4f}, "
                        f"TrainFoldIR={ind.ic_score:.4f}, OOSIC_daily={oos_ic_daily:.4f}"
                    )
            except Exception:
                continue

    all_hof.sort(key=lambda x: x["val_IC_daily"], reverse=True)

    print("\n" + "=" * 80)
    print("FINAL RESULTS - ALL ROUNDS COMBINED")
    print("=" * 80)

    results_for_save: list[dict[str, object]] = []
    for i, entry in enumerate(all_hof[:TOP_K]):
        print(
            f"  #{i + 1}: Round{entry['round']} TrainFoldIR={entry['train_FoldIR']:.4f}, "
            f"ValIC_daily={entry['val_IC_daily']:.4f}, OOSIC_daily={entry['oos_IC_daily']:.4f}, "
            f"LockboxIC_daily={entry['lockbox_IC_daily']:.4f}, Hit={entry['hit_rate']:.4f}"
        )
        print(f"       {entry['expr'][:80]}")
        results_for_save.append(
            {
                "rank": i + 1,
                "round": entry["round"],
                "train_FoldIR": entry["train_FoldIR"],
                "train_IC_daily": entry["train_IC_daily"],
                "val_IC_daily": entry["val_IC_daily"],
                "oos_IC_daily": entry["oos_IC_daily"],
                "lockbox_IC_daily": entry["lockbox_IC_daily"],
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

        print(
            f"\nBest alpha: ValIC_daily={best['val_IC_daily']}, "
            f"OOSIC_daily={best['oos_IC_daily']}, TrainFoldIR={best['train_FoldIR']}"
        )
        print(f"Expression: {best['expression']}")
        print("Saved DB-backed GP views to data/stable/genetic_alpha_v3_results.csv")

    print("\n" + "=" * 80)
    print("GENETIC ALPHA EVOLUTION V3 COMPLETE!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
