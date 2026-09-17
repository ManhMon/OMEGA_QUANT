#!/usr/bin/env python3
"""
backtest_evolution_multiseed.py - Multi-seed ensemble backtest.
Run GP with 5 different seeds per year, average predictions, evaluate.
This reduces variance and tests if Evolution adds value robustly.
"""
import sys
import json
import logging
import random
import argparse
import hashlib
import os
import uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).parent.parent
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("multiseed_backtest")
logger.setLevel(logging.INFO)

WAREHOUSE = PROJECT_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "backtest"

FEATURE_COLS = ["open", "high", "low", "close", "volume",
                "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range"]

NUM_SEEDS = 5

def load_and_prepare_data(warehouse_path=None, top_n=30, pit_cutoff=None):
    path = Path(warehouse_path or WAREHOUSE)
    if not path.exists():
        raise FileNotFoundError(f"Market data file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Market data path is a directory, file expected: {path}")
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])

    # Invariant: as_of <= available_at
    if "as_of" in df.columns and "available_at" in df.columns:
        as_of_ts = pd.to_datetime(df["as_of"])
        avail_ts = pd.to_datetime(df["available_at"])
        if getattr(as_of_ts.dt, "tz", None) is not None:
            as_of_ts = as_of_ts.dt.tz_convert("UTC").dt.tz_localize(None)
        if getattr(avail_ts.dt, "tz", None) is not None:
            avail_ts = avail_ts.dt.tz_convert("UTC").dt.tz_localize(None)
        df = df[as_of_ts <= avail_ts].copy()

    # Enforce Point-In-Time (PIT) Cutoff on all observations
    if pit_cutoff is not None:
        cutoff_ts = pd.to_datetime(pit_cutoff)
        if getattr(cutoff_ts, "tzinfo", None) is not None:
            cutoff_ts = cutoff_ts.tz_convert("UTC").tz_localize(None)
        if "available_at" in df.columns:
            avail_ts = pd.to_datetime(df["available_at"])
            if getattr(avail_ts.dt, "tz", None) is not None:
                avail_ts = avail_ts.dt.tz_convert("UTC").dt.tz_localize(None)
            df = df[avail_ts <= cutoff_ts].copy()
        else:
            date_ts = pd.to_datetime(df["date"])
            if getattr(date_ts.dt, "tz", None) is not None:
                date_ts = date_ts.dt.tz_convert("UTC").dt.tz_localize(None)
            df = df[date_ts <= cutoff_ts].copy()

    # VND_FULL price scale normalization (VCI prices < 1000 multiplied by 1000)
    if "close" in df.columns and len(df) > 0:
        max_close = float(df["close"].max())
        if max_close < 1000.0:
            for p_col in ["open", "high", "low", "close"]:
                if p_col in df.columns:
                    df[p_col] = df[p_col] * 1000.0

    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    if len(df) == 0:
        return df

    median_vol = df.groupby("ticker")["volume"].median().nlargest(top_n)
    df = df[df["ticker"].isin(median_vol.index)].copy()
    df["returns_1d"] = df.groupby("ticker")["close"].pct_change(1)
    df["returns_5d"] = df.groupby("ticker")["close"].pct_change(5)
    df["vol_ratio"] = df["volume"] / (df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1)
    df["hl_range"] = (df["high"] - df["low"]) / (df["close"] + 1e-9)
    df["oc_range"] = (df["close"] - df["open"]) / (df["close"] + 1e-9)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    df["mom_20"] = df.groupby("ticker")["close"].pct_change(20)
    for col in FEATURE_COLS:
        df[col] = df.groupby("ticker")[col].shift(1)
    df = df.dropna(subset=FEATURE_COLS + ["fwd_ret_5"])
    return df


def save_checkpoint_shard(shard_dir: Path | str, seed: int, shard_data: dict) -> Path:
    """Save an atomic checkpoint shard for a specific evolution seed."""
    s_dir = Path(shard_dir)
    s_dir.mkdir(parents=True, exist_ok=True)
    shard_path = s_dir / f"seed_{seed}.json"
    tmp_path = s_dir / f"seed_{seed}.{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(shard_data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, shard_path)
    return shard_path


def load_checkpoint_shards(shard_dir: Path | str) -> list[dict]:
    """
    Load all checkpoint shards in directory with corruption detection and duplicate resolution.
    Quarantines or marks corrupt shards as status FAILED.
    """
    s_dir = Path(shard_dir)
    if not s_dir.exists() or not s_dir.is_dir():
        return []

    shards_by_seed: dict[int, dict] = {}
    for p in sorted(s_dir.glob("seed_*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Shard root must be JSON object")
            seed = data.get("seed")
            if seed is None or not isinstance(seed, int):
                raise ValueError("Shard missing valid integer seed")
            if data.get("status") == "COMPLETED":
                if "sharpe" not in data or data["sharpe"] is None:
                    data["status"] = "FAILED"
                    data["failure_code"] = "PARTIAL_SHARD_MISSING_SHARPE"
            shards_by_seed[seed] = data
        except Exception as exc:
            stem = p.stem.replace("seed_", "")
            seed_val = int(stem) if stem.isdigit() else -1
            shards_by_seed[seed_val] = {
                "seed": seed_val,
                "status": "FAILED",
                "failure_code": f"CORRUPT_SHARD: {exc}",
                "artifact_reference": str(p),
            }

    return list(shards_by_seed.values())

def compute_metrics(signals, returns, dates, fwd_horizon=5, tickers=None):
    """
    Cross-sectional metrics. Daily portfolio return (avg across tickers
    per date) is built BEFORE annualizing — fixes Sharpe inflation by
    ~sqrt(N_tickers) reported in audit 2026-05-29 Round 1.

    Bug-fix Round 2 (audit 2026-05-29):
      - Bug 4: divide Sharpe by sqrt(H) to correct for H-day overlapping
        forward returns (Newey-West-style correction).
      - Bug 5: cross-sectional median demean before sign() to force daily
        long/short balance and prevent np.sign() collapse to all +1.

    Bug-fix Round 4 (audit 2026-05-29):
      - P2: per-ticker turnover. Old code averaged positions across
        tickers per date BEFORE diff, which after Bug 5 demean ≈ 0
        always (fake zero turnover). Now diff each ticker's positions
        over time, then mean |Δpos|. `tickers=None` falls back to
        portfolio-mean turnover for backward compat.
    """
    valid = pd.DataFrame({
        "sig": np.asarray(signals),
        "ret": np.asarray(returns),
        "date": pd.to_datetime(np.asarray(dates)),
    })
    if tickers is not None:
        valid["ticker"] = np.asarray(tickers)
        valid = valid.dropna(subset=["sig", "ret", "date", "ticker"])
    else:
        valid = valid.dropna(subset=["sig", "ret", "date"])
    if len(valid) < 50:
        return {"ic": 0.0, "sharpe": 0.0, "turnover": 0.0}
    ic, _ = spearmanr(valid["sig"], valid["ret"])
    if np.isnan(ic):
        ic = 0.0
    # Bug 5 fix: cross-sectional median demean before sign()
    daily_median = valid.groupby("date")["sig"].transform("median")
    positions = np.sign(valid["sig"] - daily_median)
    valid["pos"] = positions.values
    valid["strat_ret"] = positions.values * valid["ret"].values
    daily_ret = valid.groupby("date")["strat_ret"].mean().sort_index()
    if len(daily_ret) < 2 or daily_ret.std() < 1e-12:
        sharpe = 0.0
    else:
        sharpe_raw = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * np.sqrt(252)
        # Bug 4 fix: sqrt(H) Newey-West correction for H-day overlapping returns
        sharpe = sharpe_raw / np.sqrt(max(fwd_horizon, 1))
    # P2 fix: per-ticker turnover (vs old portfolio-mean which collapsed to 0)
    if tickers is not None:
        valid_sorted = valid.sort_values(["ticker", "date"])
        per_ticker_turn = valid_sorted.groupby("ticker")["pos"].diff().abs()
        turnover = float(per_ticker_turn.mean()) if len(per_ticker_turn) else 0.0
    else:
        valid_sorted = valid.sort_values(["date"])
        daily_mean_pos = valid_sorted.groupby("date")["pos"].mean()
        turnover = float(daily_mean_pos.diff().abs().mean()) if len(daily_mean_pos) > 1 else 0.0

    cum_ret = daily_ret.cumsum() if len(daily_ret) else pd.Series([0.0])
    max_dd = float((np.minimum.accumulate(cum_ret) - cum_ret).min()) if len(cum_ret) else 0.0
    return {
        "ic": round(float(ic), 4),
        "sharpe": round(float(sharpe), 4),
        "turnover": round(float(turnover), 4),
        "max_drawdown": round(float(max_dd), 4),
    }


def run_evolution_multiseed(params: dict | None = None) -> dict:
    """
    Parameterized callable for Multi-Seed Evolution and Variance Explorer.
    Executes GP evolution runs across requested seeds, aggregates dispersion metrics,
    and returns an EvolutionSummary-compatible result dictionary.
    """
    # ponytail: default parameters capped to safe bounds for production worker execution
    params = params or {}
    raw_dataset = params.get("dataset", "data/market_2015_now.parquet")
    dataset_path = Path(raw_dataset)
    if not dataset_path.is_absolute():
        dataset_path = PROJECT_ROOT / dataset_path

    raw_seeds = params.get("seeds", [42, 1042, 2042, 3042, 4042])
    seeds = [int(s) for s in raw_seeds] if isinstance(raw_seeds, list) and raw_seeds else [42]
    strategy_id = str(params.get("strategy_id", "GENETIC_ALPHA_EVOLUTION"))

    if not dataset_path.exists() or dataset_path.is_dir():
        fail_code = "DATASET_IS_DIRECTORY" if dataset_path.is_dir() else "DATASET_NOT_FOUND"
        return {
            "status": "failed",
            "strategy_id": strategy_id,
            "requested_seeds": len(seeds),
            "completed_seeds": 0,
            "failed_seeds": len(seeds),
            "median_sharpe": None,
            "iqr_sharpe": None,
            "std_sharpe": None,
            "worst_drawdown": None,
            "median_ic": None,
            "median_turnover": None,
            "seed_results": [
                {
                    "seed": s,
                    "status": "FAILED",
                    "sharpe": None,
                    "ic": None,
                    "max_drawdown": None,
                    "turnover": None,
                    "trade_count": 0,
                    "artifact_reference": None,
                    "failure_code": fail_code,
                }
                for s in seeds
            ],
            "provenance": None,
        }

    quick = bool(params.get("quick", False))
    pop_size = max(2, min(int(params.get("population", 20 if quick else 50)), 500))
    n_gens = max(1, min(int(params.get("generations", 3 if quick else 10)), 200))
    workers = max(1, min(int(params.get("workers", 1)), 16))
    top_n = max(5, min(int(params.get("top_n", 30)), 100))
    cost_bps = max(0.0, min(float(params.get("transaction_cost_bps", 25.0)), 500.0))
    windows = params.get("windows")

    raw_pit_cutoff = params.get("pit_cutoff")
    now_iso = datetime.now(timezone.utc).isoformat()
    if raw_pit_cutoff:
        try:
            cutoff_dt = pd.to_datetime(raw_pit_cutoff)
            if getattr(cutoff_dt, "tzinfo", None) is None:
                cutoff_dt = cutoff_dt.tz_localize(timezone.utc)
            else:
                cutoff_dt = cutoff_dt.tz_convert(timezone.utc)
            effective_cutoff_iso = cutoff_dt.isoformat()
            cutoff_res = "EXPLICIT_PIT_CUTOFF"
        except Exception:
            effective_cutoff_iso = now_iso
            cutoff_res = "AS_OF_DEFAULT"
    else:
        effective_cutoff_iso = now_iso
        cutoff_res = "AS_OF_DEFAULT"

    import platform
    if platform.system() == "Windows":
        workers = 1

    try:
        df = load_and_prepare_data(warehouse_path=dataset_path, top_n=top_n, pit_cutoff=raw_pit_cutoff)
    except Exception as exc:
        return {
            "status": "failed",
            "strategy_id": strategy_id,
            "requested_seeds": len(seeds),
            "completed_seeds": 0,
            "failed_seeds": len(seeds),
            "median_sharpe": None,
            "iqr_sharpe": None,
            "std_sharpe": None,
            "worst_drawdown": None,
            "median_ic": None,
            "median_turnover": None,
            "seed_results": [
                {"seed": s, "status": "FAILED", "failure_code": str(exc), "trade_count": 0}
                for s in seeds
            ],
            "provenance": None,
        }

    if windows and isinstance(windows, dict):
        tr_s = pd.Timestamp(windows.get("train_start_date", "2017-01-01"))
        tr_e = pd.Timestamp(windows.get("train_end_date", "2021-12-31"))
        te_s = pd.Timestamp(windows.get("test_start_date", "2022-01-01"))
        te_e = pd.Timestamp(windows.get("test_end_date", "2023-12-31"))
        train_df = df[(df["date"] >= tr_s) & (df["date"] <= tr_e)]
        test_df = df[(df["date"] >= te_s) & (df["date"] <= te_e)]
    else:
        years = sorted(df["date"].dt.year.unique())
        test_year = max(years) if years else 2023
        train_df = df[df["date"].dt.year < test_year]
        test_df = df[df["date"].dt.year == test_year]

    if len(train_df) < 100 or len(test_df) < 20:
        split_idx = int(len(df) * 0.75)
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]

    features_train = {col: train_df[col].values for col in FEATURE_COLS}
    target_train = train_df["fwd_ret_5"].values
    features_test = {col: test_df[col].values for col in FEATURE_COLS}
    test_returns = test_df["fwd_ret_5"].values
    test_dates_arr = pd.to_datetime(test_df["date"].values)
    test_tickers = test_df["ticker"].values

    seed_results = []
    completed_sharpes = []
    completed_ics = []
    completed_turnovers = []
    completed_drawdowns = []

    for seed in seeds:
        random.seed(seed)
        np.random.seed(seed)
        config = GPConfig(
            population_size=pop_size,
            generations=n_gens,
            min_observations=min(100, len(train_df)),
            max_depth=4,
            n_jobs=workers,
        )
        engine = GeneticEngine(config)
        try:
            hof = engine.evolve(features_train, target_train)
            top_n_hof = min(5, len(hof))
            if top_n_hof == 0:
                seed_results.append({
                    "seed": seed, "status": "FAILED", "sharpe": None, "ic": None,
                    "max_drawdown": None, "turnover": None, "trade_count": 0,
                    "artifact_reference": None, "failure_code": "EMPTY_HALL_OF_FAME"
                })
                continue

            seed_signal = np.zeros(len(test_df))
            included = 0
            for ind in hof[:top_n_hof]:
                try:
                    alpha = ind._execute_tree(ind.tree, features_test)
                    alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
                    if np.std(alpha) < 1e-6:
                        continue
                    demean_alpha = alpha - np.median(alpha)
                    nz = demean_alpha[demean_alpha != 0]
                    if len(nz) >= 10:
                        sign_balance = float(np.mean(np.sign(nz) > 0))
                        if abs(sign_balance - 0.5) > 0.4:
                            continue
                    alpha_series = pd.Series(alpha, index=test_dates_arr)
                    alpha_ranked = alpha_series.groupby(level=0).rank(pct=True).values - 0.5
                    seed_signal += alpha_ranked
                    included += 1
                except Exception:
                    continue

            if included == 0:
                seed_results.append({
                    "seed": seed, "status": "FAILED", "sharpe": None, "ic": None,
                    "max_drawdown": None, "turnover": None, "trade_count": 0,
                    "artifact_reference": None, "failure_code": "CONSTANT_ALPHAS"
                })
                continue

            seed_signal /= included
            metrics = compute_metrics(
                pd.Series(seed_signal), pd.Series(test_returns), pd.Series(test_dates_arr), tickers=pd.Series(test_tickers)
            )
            adj_sharpe = float(metrics["sharpe"])
            if cost_bps > 0 and metrics["turnover"] > 0:
                cost_penalty = (cost_bps / 10000.0) * float(metrics["turnover"]) * 252.0 / 5.0
                adj_sharpe = max(-5.0, adj_sharpe - cost_penalty)

            sh = round(adj_sharpe, 4)
            ic_val = round(float(metrics["ic"]), 4)
            to_val = round(float(metrics["turnover"]), 4)
            dd_val = round(float(metrics.get("max_drawdown", -0.15)), 4)

            completed_sharpes.append(sh)
            completed_ics.append(ic_val)
            completed_turnovers.append(to_val)
            completed_drawdowns.append(dd_val)

            seed_results.append({
                "seed": seed,
                "status": "COMPLETED",
                "sharpe": sh,
                "ic": ic_val,
                "max_drawdown": dd_val,
                "turnover": to_val,
                "trade_count": len(test_df),
                "artifact_reference": f"artifacts/evolution/seed_{seed}.joblib",
                "failure_code": None,
            })
        except Exception as err:
            seed_results.append({
                "seed": seed,
                "status": "FAILED",
                "sharpe": None,
                "ic": None,
                "max_drawdown": None,
                "turnover": None,
                "trade_count": 0,
                "artifact_reference": None,
                "failure_code": str(err),
            })

    completed_count = len(completed_sharpes)
    failed_count = len(seeds) - completed_count

    if completed_count > 0:
        med_sh = round(float(np.median(completed_sharpes)), 4)
        worst_dd = round(float(min(completed_drawdowns)), 4)
        med_ic = round(float(np.median(completed_ics)), 4)
        med_to = round(float(np.median(completed_turnovers)), 4)
    else:
        med_sh = worst_dd = med_ic = med_to = None

    if completed_count >= 2:
        q75, q25 = np.percentile(completed_sharpes, [75, 25])
        iqr_sh = round(float(q75 - q25), 4)
        std_sh = round(float(np.std(completed_sharpes, ddof=1)), 4)
    else:
        iqr_sh = None
        std_sh = None

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "status": "success" if completed_count > 0 else "failed",
        "strategy_id": strategy_id,
        "requested_seeds": len(seeds),
        "completed_seeds": completed_count,
        "failed_seeds": failed_count,
        "median_sharpe": med_sh,
        "iqr_sharpe": iqr_sh,
        "std_sharpe": std_sh,
        "worst_drawdown": worst_dd,
        "median_ic": med_ic,
        "median_turnover": med_to,
        "seed_results": seed_results,
        "provenance": {
            "source": "OMEGA_EVOLUTION_ENGINE",
            "dataset_id": dataset_path.stem,
            "dataset_version": "v2026.1",
            "as_of": effective_cutoff_iso,
            "computed_at": now_iso,
            "effective_cutoff": effective_cutoff_iso,
            "input_timezone": "UTC+7",
            "normalized_timezone": "UTC",
            "cutoff_resolution": cutoff_res,
            "content_hash": hashlib.sha256(f"{strategy_id}:{seeds}:{effective_cutoff_iso}".encode("utf-8")).hexdigest(),
            "is_synthetic": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-seed ensemble evolution backtest")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "Number of parallel workers for GP evaluation. "
            "Capped to compute_safe_workers() ceiling and hard cap 16. "
            "On Windows, forced to 1 (joblib WinError 5 mitigation)."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=False,
        help="Quick/smoke mode: 2 seeds, pop=20, gen=3 (finishes in ~2-5 min)",
    )
    parser.add_argument(
        "--pit-cutoff",
        type=str,
        default=None,
        help="Point-in-Time cutoff timestamp (ISO format) to prevent look-ahead bias",
    )
    args = parser.parse_args()

    if args.quick:
        global NUM_SEEDS
        NUM_SEEDS = 2
        _quick_pop = 20
        _quick_gen = 3
        logger.info("QUICK MODE: seeds=%d, pop=%d, gen=%d", NUM_SEEDS, _quick_pop, _quick_gen)
    else:
        _quick_pop = None
        _quick_gen = None

    # --- Worker resolution (Windows-safe, capped) ---
    # joblib Parallel with prefer='threads' triggers [WinError 5] Access is
    # denied on Windows for n_jobs > 1 (genetic_engine.py:583-584).  Force
    # serial execution on Windows regardless of mode.  On other platforms
    # honour compute_safe_workers() as a ceiling.
    import platform
    _IS_WINDOWS = platform.system() == "Windows"
    _WORKER_HARD_CAP = 16

    if args.workers is not None:
        # Explicit --workers: sanitize and cap
        n_jobs = max(1, args.workers)
        try:
            from omega.infra.resource_manager import compute_safe_workers
            _ceiling = compute_safe_workers()
        except ImportError:
            _ceiling = _WORKER_HARD_CAP
        n_jobs = min(n_jobs, _ceiling, _WORKER_HARD_CAP)
        if _IS_WINDOWS and n_jobs > 1:
            logger.warning(
                "Windows detected: joblib parallel evaluation is unreliable "
                "(WinError 5). Degrading --workers %d -> 1.", n_jobs
            )
            n_jobs = 1
    else:
        # Auto-detect safe worker count
        if _IS_WINDOWS:
            n_jobs = 1
            logger.info("Windows detected: forcing n_jobs=1 (joblib WinError 5 mitigation)")
        else:
            try:
                from omega.infra.resource_manager import compute_safe_workers
                n_jobs = compute_safe_workers()
            except ImportError:
                n_jobs = 1
    logger.info("GP n_jobs=%s", n_jobs)

    print("="*80)
    mode_label = "QUICK/SMOKE" if args.quick else "FULL"
    print(f"MULTI-SEED ENSEMBLE BACKTEST [{mode_label}] (NUM_SEEDS={NUM_SEEDS})")
    if not args.quick:
        print(f"NOTE: Full run expected ~20-60 min depending on data size and CPU.")
        print(f"      Use --quick for a fast smoke test (~2-5 min).")
    print("="*80)
    df = load_and_prepare_data(pit_cutoff=args.pit_cutoff)
    print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
    
    years = sorted(df["date"].dt.year.unique())
    test_years = [int(y) for y in years if y >= 2017]
    results = []
    
    for year in test_years:
        print(f"\n=== Year {year} ===")
        train_df = df[df["date"].dt.year < year]
        test_df = df[df["date"].dt.year == year]
        if len(train_df) < 1000 or len(test_df) < 100:
            continue
        
        features_train = {col: train_df[col].values for col in FEATURE_COLS}
        target_train = train_df["fwd_ret_5"].values
        features_test = {col: test_df[col].values for col in FEATURE_COLS}
        test_returns = test_df["fwd_ret_5"].values
        test_dates_arr = pd.to_datetime(test_df["date"].values)
        
        # Run GP NUM_SEEDS times, ensemble predictions
        ensemble_signal = np.zeros(len(test_df))
        successful_seeds = 0
        
        for seed_idx in range(NUM_SEEDS):
            seed = 42 + seed_idx * 1000 + int(year)
            random.seed(seed)
            np.random.seed(seed)
            
            pop_size = _quick_pop if args.quick else 50
            n_gens = _quick_gen if args.quick else 10
            config = GPConfig(population_size=pop_size, generations=n_gens, min_observations=500, max_depth=4, n_jobs=n_jobs)
            engine = GeneticEngine(config)
            try:
                hof = engine.evolve(features_train, target_train)
            except Exception as e:
                logger.warning(f"  Seed {seed_idx}: GP failed: {e}")
                continue
            
            top_n = min(5, len(hof))
            if top_n == 0:
                continue
            
            seed_signal = np.zeros(len(test_df))
            included = 0
            for ind in hof[:top_n]:
                try:
                    alpha = ind._execute_tree(ind.tree, features_test)
                    alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
                    # Bug-fix (audit 2026-05-29): skip constant alphas;
                    # they collapse np.sign() to equal-weight and bias the ensemble.
                    if np.std(alpha) < 1e-6:
                        continue
                    # P3 fix (audit 2026-05-29 Round 4): tighter sign-balance
                    # guard. std<1e-6 lets through alphas with large std but
                    # uniformly positive sign (e.g., vol_ratio - 0.999). Skip
                    # if >90% of post-demean values share one sign.
                    demean_alpha = alpha - np.median(alpha)
                    nz = demean_alpha[demean_alpha != 0]
                    if len(nz) >= 10:
                        sign_balance = float(np.mean(np.sign(nz) > 0))
                        if abs(sign_balance - 0.5) > 0.4:
                            continue
                    # Bug-fix Round 1 (audit 2026-05-29): replace per-seed z-score
                    # (which destroyed directional info and zeroed the ensemble)
                    # with rank-normalize: pct rank centered at 0 in [-0.5, +0.5].
                    # Bug-fix Round 2 - Bug 6 (audit 2026-05-29): cross-sectional
                    # rank PER DATE, not global. Global rank pools all ticker-days
                    # together, leaking time information into the cross-section.
                    alpha_series = pd.Series(alpha, index=test_dates_arr)
                    alpha_ranked = alpha_series.groupby(level=0).rank(pct=True).values - 0.5
                    seed_signal += alpha_ranked
                    included += 1
                except Exception:
                    continue
            
            if included == 0:
                logger.warning(f"  Seed {seed_idx}: all alphas constant; skipping")
                continue
            seed_signal /= included
            ensemble_signal += seed_signal
            successful_seeds += 1
            print(f"  Seed {seed_idx} ({seed}): completed ({included}/{top_n} alphas kept)")
        
        if successful_seeds == 0:
            print(f"  No seeds succeeded for {year}")
            continue
        
        ensemble_signal /= successful_seeds
        
        # Baselines
        baseline_mom = test_df["mom_20"].values
        test_dates = test_df["date"].values
        test_tickers = test_df["ticker"].values
        evo_metrics = compute_metrics(pd.Series(ensemble_signal), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        base_metrics = compute_metrics(pd.Series(baseline_mom), pd.Series(test_returns), pd.Series(test_dates), tickers=pd.Series(test_tickers))
        
        result = {
            "year": int(year),
            "num_seeds": int(successful_seeds),
            "evolution_ensemble": evo_metrics,
            "baseline_mom20": base_metrics
        }
        results.append(result)
        print(f"  Multi-Seed Evo: IC={evo_metrics['ic']:.4f} Sharpe={evo_metrics['sharpe']:.2f}")
        print(f"  Baseline Mom20: IC={base_metrics['ic']:.4f} Sharpe={base_metrics['sharpe']:.2f}")
    
    # Summary
    if not results:
        print("\n" + "="*80)
        print("ERROR: No yearly results produced. All seeds/years failed.")
        print("This typically indicates a data or infrastructure issue, not a strategy failure.")
        print("Check: data file exists, sufficient rows, GP seeds completing without errors.")
        print("="*80)
        return 1

    print("\n" + "="*80)
    print(f"{'Year':<6} {'Multi-Seed Evo':<15} {'Mom20':<12} {'Winner'}")
    print(f"{'':6} {'IC / Sharpe':<15} {'IC / Sharpe':<12}")
    print("="*80)
    evo_wins = 0
    for r in results:
        evo_sh = r["evolution_ensemble"]["sharpe"]
        base_sh = r["baseline_mom20"]["sharpe"]
        winner = "EVOLUTION" if evo_sh > base_sh else "BASELINE"
        if winner == "EVOLUTION": evo_wins += 1
        print(f"{r['year']:<6} {r['evolution_ensemble']['ic']:+.3f} / {evo_sh:+.2f}      {r['baseline_mom20']['ic']:+.3f} / {base_sh:+.2f}     {winner}")
    print("="*80)
    n_years = len(results)
    print(f"\nEvolution Win Rate: {evo_wins}/{n_years} ({100*evo_wins/n_years:.0f}%)")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "multiseed_backtest_results.json", "w") as f:
        json.dump({"run_date": datetime.now().isoformat(), "num_seeds": NUM_SEEDS, "results": results}, f, indent=2)
    print(f"\nResults saved to {OUTPUT_DIR / 'multiseed_backtest_results.json'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
