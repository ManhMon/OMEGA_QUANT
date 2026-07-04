"""Genetic Alpha Evolution V3 - Enhanced diversity, larger search, anti-convergence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

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
from omega.data.calendar import VNTradingCalendar
from omega.execution.vn_transaction_cost_model import VNTransactionCostModel
from omega.quant.evolution.genetic_engine import (
    GPConfig,
    GeneticEngine,
    _evaluation_mask,
    _neutralize_cross_section,
)
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
ENSEMBLE_VAL_IC_THRESHOLD = 0.015
ENSEMBLE_MAX_CORR = 0.6
ENSEMBLE_MAX_ALPHAS = 10
GATE6_MIN_REGIME_IC = -0.01
GATE6_PERMUTATION_P_THRESHOLD = 0.05
GATE6_PERMUTATIONS = 500
GATE6_RANDOM_SEED = 42
GATE6_REPORT_NAME = "l2_role16_gp_gate6_20260704.md"
VN_REGIME_DEFINITIONS = {
    "COVID_2020": {
        "period": ("2020-03-01", "2020-12-31"),
        "rationale": "COVID shock, extreme volatility, intervention-heavy tape.",
    },
    "Bear_2022": {
        "period": ("2022-01-01", "2022-12-31"),
        "rationale": "VN-Index drawdown, global hikes, property stress.",
    },
    "Recovery_2023": {
        "period": ("2023-01-01", "2023-12-31"),
        "rationale": "Post-bear recovery with easing inflation and stabilization.",
    },
    "Recent_2024": {
        "period": ("2024-01-01", "2024-12-31"),
        "rationale": "Recent live-like market state before lockbox year.",
    },
    "Lockbox_2025": {
        "period": ("2025-01-01", "2025-12-31"),
        "rationale": "Held-out out-of-sample lockbox validation year.",
    },
}


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
    parser.add_argument(
        "--min-avg-volume",
        type=float,
        default=500000.0,
        help="Minimum trailing average traded value in VND (close * volume)",
    )
    parser.add_argument(
        "--avg-volume-window",
        type=int,
        default=20,
        help="Window for trailing average traded value calculation",
    )
    return parser.parse_args()


def load_dataset(args: argparse.Namespace) -> pd.DataFrame:
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
    # NOTE: 'sector' here = liquidity quartile proxy, not economic sector classification.
    df["__sector__"] = _volume_quartile_sector_proxy(df["volume"], df["date"])
    df["traded_value"] = df["close"] * df["volume"]
    df["avg_traded_value"] = (
        df.groupby("ticker")["traded_value"]
        .rolling(args.avg_volume_window, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["avg_traded_value"] = df.groupby("ticker")["avg_traded_value"].shift(1)
    df["liquidity_mask"] = (df["avg_traded_value"] > args.min_avg_volume).fillna(False)
    df[FEATURE_COLS] = df.groupby("ticker")[FEATURE_COLS].shift(1)
    df["__log_market_cap__"] = df.groupby("ticker")["__log_market_cap__"].shift(1)
    df["__sector__"] = df.groupby("ticker")["__sector__"].shift(1)
    exclusion_rate = 1.0 - float(df["liquidity_mask"].mean())
    if exclusion_rate > 0.5:
        print(
            f"Warning: liquidity filter excludes {exclusion_rate:.1%} of rows; "
            "consider lowering --min-avg-volume."
        )
    return df.dropna(subset=FEATURE_COLS + ["fwd_ret_5", "__log_market_cap__", "__sector__"])


def compute_engine_consistent_daily_ic(
    signal: np.ndarray,
    target: np.ndarray,
    features: dict[str, np.ndarray],
    config: GPConfig,
) -> float:
    alpha = np.asarray(signal, dtype=np.float64)
    target_arr = np.asarray(target, dtype=np.float64)
    eval_features = dict(features)
    if config.neutralize_size_sector and "__sector__" in eval_features:
        alpha = _neutralize_cross_section(
            alpha,
            eval_features.get("__log_market_cap__"),
            eval_features.get("__sector__"),
            eval_features.get("__date__"),
        )
        target_arr = _neutralize_cross_section(
            target_arr,
            eval_features.get("__log_market_cap__"),
            eval_features.get("__sector__"),
            eval_features.get("__date__"),
        )

    dates = np.asarray(eval_features["__date__"])
    daily_ics: list[float] = []
    for current_date in pd.unique(pd.Series(dates).dropna()):
        date_mask = dates == current_date
        valid = date_mask & _evaluation_mask(alpha, target_arr, eval_features)
        if np.count_nonzero(valid) <= 5:
            continue
        ic_value, _ = spearmanr(alpha[valid], target_arr[valid])
        if not np.isnan(ic_value):
            daily_ics.append(float(ic_value))
    return float(np.mean(daily_ics)) if daily_ics else 0.0


def compute_hit_rate(signal: np.ndarray, target: np.ndarray, features: dict[str, np.ndarray]) -> float:
    valid = _evaluation_mask(np.asarray(signal, dtype=np.float64), np.asarray(target, dtype=np.float64), features)
    if not np.any(valid):
        return 0.0
    return float((np.sign(signal[valid]) == np.sign(target[valid])).mean())


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


def build_feature_fingerprint(df: pd.DataFrame) -> str:
    fingerprint_cols = [
        "date",
        "ticker",
        "close",
        "volume",
        "fwd_ret_5",
        *FEATURE_COLS,
    ]
    present_cols = [col for col in fingerprint_cols if col in df.columns]
    fingerprint_df = df.loc[:, present_cols].sort_values(["date", "ticker"]).reset_index(drop=True)
    row_hashes = pd.util.hash_pandas_object(fingerprint_df, index=False, categorize=False)
    return hashlib.sha1(row_hashes.to_numpy().tobytes()).hexdigest()


def build_vn_trading_days(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DatetimeIndex:
    all_dates = pd.date_range(pd.Timestamp(start_date), pd.Timestamp(end_date), freq="D")
    trading_days = [dt for dt in all_dates if VNTradingCalendar.is_trading_day(dt)]
    return pd.DatetimeIndex(trading_days)


def apply_trading_day_embargo(
    end_date: pd.Timestamp,
    embargo_days: int,
    trading_calendar: pd.DatetimeIndex,
) -> pd.Timestamp:
    end_ts = pd.Timestamp(end_date)
    if end_ts not in trading_calendar:
        trading_calendar = trading_calendar.union(pd.DatetimeIndex([end_ts])).sort_values()
    idx = int(trading_calendar.get_loc(end_ts))
    return pd.Timestamp(trading_calendar[max(0, idx - embargo_days)])


def advance_trading_days(
    start_date: pd.Timestamp,
    trading_days: pd.DatetimeIndex,
    offset: int,
) -> pd.Timestamp:
    start_ts = pd.Timestamp(start_date)
    start_idx = int(trading_days.searchsorted(start_ts, side="left"))
    if start_idx >= len(trading_days):
        start_idx = len(trading_days) - 1
    target_idx = min(start_idx + offset, len(trading_days) - 1)
    return pd.Timestamp(trading_days[target_idx])


def compute_regime_ic(
    signal: np.ndarray,
    target: np.ndarray,
    dates: np.ndarray,
    regime_definitions: dict[str, dict[str, Any]] = VN_REGIME_DEFINITIONS,
) -> dict[str, dict[str, Any]]:
    dates_ts = pd.to_datetime(dates)
    results: dict[str, dict[str, Any]] = {}
    for regime_name, regime_spec in regime_definitions.items():
        start_dt, end_dt = (pd.Timestamp(v) for v in regime_spec["period"])
        mask = (dates_ts >= start_dt) & (dates_ts <= end_dt)
        if not np.any(mask):
            results[regime_name] = {
                "ic": None,
                "n_rows": 0,
                "rationale": regime_spec["rationale"],
            }
            continue
        regime_ic = compute_daily_cs_ic(signal[mask], target[mask], dates_ts[mask].to_numpy())
        if np.isnan(regime_ic):
            regime_ic = None
        results[regime_name] = {
            "ic": None if regime_ic is None else float(regime_ic),
            "n_rows": int(np.count_nonzero(mask)),
            "rationale": regime_spec["rationale"],
        }
    return results


def compute_turnover(signal: np.ndarray, dates: np.ndarray, tickers: np.ndarray) -> float:
    frame = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "ticker": tickers,
        "signal": signal,
    })
    frame = frame[np.isfinite(frame["signal"])].copy()
    if frame.empty:
        return 0.0
    pivot = frame.sort_values(["date", "ticker"]).pivot(index="date", columns="ticker", values="signal")
    daily_turnover = pivot.diff().abs().mean(axis=1, skipna=True).dropna()
    return float(daily_turnover.mean()) if not daily_turnover.empty else 0.0


def estimate_cost_drag(
    signal: np.ndarray,
    target: np.ndarray,
    dates: np.ndarray,
    tickers: np.ndarray,
    prices: np.ndarray,
    volumes: np.ndarray,
    exchanges: np.ndarray | None = None,
) -> dict[str, float]:
    valid = np.isfinite(signal) & np.isfinite(target) & np.isfinite(prices) & np.isfinite(volumes)
    gross_ic = compute_daily_cs_ic(signal[valid], target[valid], pd.to_datetime(dates)[valid].to_numpy()) if np.any(valid) else 0.0
    turnover = compute_turnover(signal, dates, tickers)
    cost_model = VNTransactionCostModel()
    cost_samples: list[float] = []
    signal_frame = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "ticker": tickers,
        "signal": signal,
        "price": prices,
        "volume": volumes,
        "exchange": exchanges if exchanges is not None else "UNKNOWN",
    })
    latest_by_ticker = signal_frame.sort_values(["ticker", "date"]).groupby("ticker", as_index=False).tail(1)
    for row in latest_by_ticker.itertuples(index=False):
        if not np.isfinite(row.signal) or not np.isfinite(row.price) or not np.isfinite(row.volume):
            continue
        adv_value_vnd = float(max(row.price * row.volume, 1.0))
        buy_cost = cost_model.estimate_cost(
            symbol=str(row.ticker),
            order_size=100.0,
            price=float(row.price),
            adv_value_vnd=adv_value_vnd,
            side="buy",
            exchange_label=str(row.exchange),
        )["total_cost_bps"]
        sell_cost = cost_model.estimate_cost(
            symbol=str(row.ticker),
            order_size=100.0,
            price=float(row.price),
            adv_value_vnd=adv_value_vnd,
            side="sell",
            exchange_label=str(row.exchange),
        )["total_cost_bps"]
        cost_samples.append(float(0.5 * (buy_cost + sell_cost)))
    avg_cost_bps = float(np.mean(cost_samples)) if cost_samples else 0.0
    cost_drag_estimate = turnover * (avg_cost_bps / 10000.0)
    return {
        "gross_ic": float(gross_ic),
        "turnover": float(turnover),
        "avg_cost_bps": avg_cost_bps,
        "cost_drag_estimate": float(cost_drag_estimate),
        "net_ic_estimate": float(gross_ic - cost_drag_estimate),
    }


def permutation_test_ic(
    signal: np.ndarray,
    target: np.ndarray,
    dates: np.ndarray,
    n_permutations: int = GATE6_PERMUTATIONS,
    random_seed: int = GATE6_RANDOM_SEED,
) -> dict[str, float]:
    dates_ts = pd.to_datetime(dates)
    observed_ic = compute_daily_cs_ic(signal, target, dates_ts.to_numpy())
    rng = np.random.RandomState(random_seed)
    frame = pd.DataFrame({"date": dates_ts, "signal": signal, "target": target})
    null_ics: list[float] = []
    for _ in range(n_permutations):
        shuffled_parts: list[pd.DataFrame] = []
        for current_date, day_frame in frame.groupby("date", sort=False):
            shuffled = day_frame.copy()
            shuffled_target = rng.permutation(shuffled["target"].to_numpy())
            shuffled["target"] = shuffled_target
            shuffled_parts.append(shuffled)
        shuffled_frame = pd.concat(shuffled_parts, ignore_index=True)
        null_ics.append(
            compute_daily_cs_ic(
                shuffled_frame["signal"].to_numpy(dtype=float),
                shuffled_frame["target"].to_numpy(dtype=float),
                shuffled_frame["date"].to_numpy(),
            )
        )
    null_arr = np.asarray(null_ics, dtype=float)
    p_value = float((np.abs(null_arr) >= abs(observed_ic)).mean()) if null_arr.size else 1.0
    return {
        "observed_ic": float(observed_ic),
        "p_value": p_value,
        "null_mean": float(null_arr.mean()) if null_arr.size else 0.0,
        "null_std": float(null_arr.std()) if null_arr.size else 0.0,
        "n_permutations": int(null_arr.size),
        "random_seed": int(random_seed),
    }


def run_gate6_validation(best_entry: dict[str, object], validation_df: pd.DataFrame) -> dict[str, Any]:
    signal = np.asarray(best_entry["validation_signal"], dtype=float)
    target = validation_df["fwd_ret_5"].to_numpy(dtype=float)
    dates = validation_df["date"].to_numpy()
    tickers = validation_df["ticker"].to_numpy()
    prices = validation_df["close"].to_numpy(dtype=float)
    volumes = validation_df["volume"].to_numpy(dtype=float)
    exchanges = validation_df["exchange"].to_numpy() if "exchange" in validation_df.columns else None
    regime_ic = compute_regime_ic(signal, target, dates)
    cost_metrics = estimate_cost_drag(signal, target, dates, tickers, prices, volumes, exchanges)
    permutation = permutation_test_ic(signal, target, dates)
    failing_regimes = [
        name for name, info in regime_ic.items() if info["ic"] is not None and float(info["ic"]) < GATE6_MIN_REGIME_IC
    ]
    feature_fingerprint = build_feature_fingerprint(validation_df)
    return {
        "feature_fingerprint": feature_fingerprint,
        "regime_ic": regime_ic,
        "failing_regimes": failing_regimes,
        "cost_metrics": cost_metrics,
        "permutation": permutation,
        "passed": not failing_regimes,
    }


def write_l2_report(report_path: Path, gate6_metrics: dict[str, Any] | None, verification: list[str]) -> None:
    role_and_skill_files = [
        ".agents/agent/machine-learning-engineer.md",
        ".agents/skills/python-patterns/SKILL.md",
        ".agents/skills/clean-code/SKILL.md",
        ".agents/skills/testing-patterns/SKILL.md",
        ".agents/skills/performance-profiling/SKILL.md",
        ".agents/skills/systematic-debugging/SKILL.md",
        ".agents/skills/ml-dl-rl/SKILL.md",
        ".agents/skills/backtesting-pit-safety/SKILL.md",
        ".agents/skills/vietnam-market-data/SKILL.md",
    ]
    lines = [
        "# L2 Report - Gate 6 Production Validation",
        "",
        "- Session: `l2_role16_gp_gate6_20260704`",
        "- Gate: `GP_PRODUCTION_VALIDATION_GATE6_20260704`",
        "- Role: `16 machine-learning-engineer`",
        "- Scope: `scripts/genetic_alpha_evolution_v3.py`, `tests/test_genetic_alpha_evolution_v3_gate6.py`",
        "",
        "## Repo-Local Files Read",
        *[f"- `{path}`" for path in role_and_skill_files],
        "- `.ly_state/session/gate6_production_validation_plan_revised.md`",
        "- `src/omega/data/calendar.py`",
        "- `src/omega/execution/vn_transaction_cost_model.py`",
        "",
        "## Forbidden Path Scan",
        "- `.gemini\\antigravity-ide\\scratch\\ag-kit`: scanned, non-authoritative, not used.",
        "- `.openclaw\\skills`: scanned, non-authoritative, not used.",
        "- `C:\\Users\\GHC\\.agents`: scanned, non-authoritative, not used.",
        "- `.codex\\memories`: scanned, non-authoritative, not used.",
        "",
        "## Verification",
        *[f"- {item}" for item in verification],
    ]
    if gate6_metrics is not None:
        lines.extend([
            "",
            "## Gate 6 Metrics",
            f"- Feature fingerprint: `{gate6_metrics['feature_fingerprint']}`",
            f"- Failing regimes: `{gate6_metrics['failing_regimes']}`",
            f"- Permutation p-value: `{gate6_metrics['permutation']['p_value']:.6f}`",
            f"- Permutation seed: `{gate6_metrics['permutation']['random_seed']}`",
            f"- Net IC estimate: `{gate6_metrics['cost_metrics']['net_ic_estimate']:.6f}`",
        ])
    lines.extend([
        "",
        "## Boundary",
        "- This L2 report is implementation evidence only. It is explicitly non-authoritative for audit approval.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_candidate_id(expression: str) -> str:
    return hashlib.sha1(expression.encode("utf-8")).hexdigest()[:12]


def select_ensemble(
    candidates: list[dict[str, object]],
    val_ic_threshold: float = ENSEMBLE_VAL_IC_THRESHOLD,
    max_corr: float = ENSEMBLE_MAX_CORR,
    max_alphas: int = ENSEMBLE_MAX_ALPHAS,
) -> tuple[list[dict[str, object]], np.ndarray]:
    pool = [candidate for candidate in candidates if float(candidate["val_IC_daily"]) >= val_ic_threshold]
    pool.sort(key=lambda candidate: float(candidate["val_IC_daily"]), reverse=True)
    if not pool:
        return [], np.array([], dtype=float)

    selected: list[dict[str, object]] = []
    for candidate in pool:
        if len(selected) >= max_alphas:
            break
        signal = np.asarray(candidate["val_signal"], dtype=float)
        is_diverse = True
        for existing in selected:
            existing_signal = np.asarray(existing["val_signal"], dtype=float)
            corr = np.corrcoef(signal, existing_signal)[0, 1]
            if np.isnan(corr):
                continue
            if abs(corr) > max_corr:
                is_diverse = False
                break
        if is_diverse:
            selected.append(candidate)

    if not selected:
        selected = [pool[0]]

    val_ics = np.array([float(candidate["val_IC_daily"]) for candidate in selected], dtype=float)
    ic_weights = val_ics / val_ics.sum()
    equal_weights = np.full(len(selected), 1.0 / len(selected), dtype=float)
    weights = 0.5 * ic_weights + 0.5 * equal_weights
    return selected, weights / weights.sum()


def evaluate_ensemble(
    selected: list[dict[str, object]],
    weights: np.ndarray,
    oos_target: np.ndarray,
    lockbox_target: np.ndarray,
    oos_dates: np.ndarray,
    lockbox_dates: np.ndarray,
) -> dict[str, float]:
    if not selected or len(weights) != len(selected):
        return {"oos_IC_daily": 0.0, "lockbox_IC_daily": 0.0}

    oos_ensemble = np.zeros_like(oos_target, dtype=float)
    lockbox_ensemble = np.zeros_like(lockbox_target, dtype=float)
    for candidate, weight in zip(selected, weights):
        oos_ensemble += float(weight) * np.asarray(candidate["oos_signal"], dtype=float)
        lockbox_ensemble += float(weight) * np.asarray(candidate["lockbox_signal"], dtype=float)

    return {
        "oos_IC_daily": compute_daily_cs_ic(oos_ensemble, oos_target, oos_dates),
        "lockbox_IC_daily": compute_daily_cs_ic(lockbox_ensemble, lockbox_target, lockbox_dates),
    }


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

    trading_calendar = build_vn_trading_days(dates[0], dates[-1])
    idx = UNIVERSE_LOOKBACK_TRADING_DAYS
    train = (dates[idx], dates[idx + train_len - 1])
    val_start = advance_trading_days(train[1], trading_calendar, EMBARGO_TRADING_DAYS + 1)
    idx = dates.index(val_start)
    val = (dates[idx], dates[idx + val_len - 1])
    oos_start = advance_trading_days(val[1], trading_calendar, EMBARGO_TRADING_DAYS + 1)
    idx = dates.index(oos_start)
    oos = (dates[idx], dates[idx + oos_len - 1])
    lockbox_start = advance_trading_days(oos[1], trading_calendar, EMBARGO_TRADING_DAYS + 1)
    idx = dates.index(lockbox_start)
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
                "id": entry["id"],
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
                "id": metrics.get("id"),
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
    verification: list[str] = []

    print("=" * 80)
    print("GENETIC ALPHA EVOLUTION V3 - ANTI-CONVERGENCE")
    print("=" * 80)

    df = load_dataset(args)
    verification.append(f"dataset_loaded rows={len(df)} fingerprint={build_feature_fingerprint(df)}")
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
    features_train["__liquidity_mask__"] = train_df["liquidity_mask"].values
    target_train = train_df["fwd_ret_5"].values
    features_val = {col: val_df[col].values for col in FEATURE_COLS}
    features_val["__date__"] = val_df["date"].values
    features_val["__log_market_cap__"] = val_df["__log_market_cap__"].values
    features_val["__sector__"] = val_df["__sector__"].values
    features_val["__liquidity_mask__"] = val_df["liquidity_mask"].values
    target_val = val_df["fwd_ret_5"].values
    features_oos = {col: oos_df[col].values for col in FEATURE_COLS}
    features_oos["__date__"] = oos_df["date"].values
    features_oos["__log_market_cap__"] = oos_df["__log_market_cap__"].values
    features_oos["__sector__"] = oos_df["__sector__"].values
    features_oos["__liquidity_mask__"] = oos_df["liquidity_mask"].values
    target_oos = oos_df["fwd_ret_5"].values
    features_lockbox = {col: lockbox_df[col].values for col in FEATURE_COLS}
    features_lockbox["__date__"] = lockbox_df["date"].values
    features_lockbox["__log_market_cap__"] = lockbox_df["__log_market_cap__"].values
    features_lockbox["__sector__"] = lockbox_df["__sector__"].values
    features_lockbox["__liquidity_mask__"] = lockbox_df["liquidity_mask"].values
    target_lockbox = lockbox_df["fwd_ret_5"].values
    validation_df = pd.concat([val_df, oos_df, lockbox_df], axis=0, ignore_index=True)
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
            time_folds=3,
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
                train_ic_daily = compute_engine_consistent_daily_ic(train_signal, target_train, features_train, config)
                val_ic_daily = compute_engine_consistent_daily_ic(val_signal, target_val, features_val, config)
                oos_ic_daily = compute_engine_consistent_daily_ic(oos_signal, target_oos, features_oos, config)
                lockbox_ic_daily = compute_engine_consistent_daily_ic(lockbox_signal, target_lockbox, features_lockbox, config)
                hit = compute_hit_rate(val_signal, target_val, features_val)
                if np.isnan(val_ic_daily):
                    continue
                all_hof.append(
                    {
                        "id": build_candidate_id(ind.tree.to_string()),
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
                        "val_signal": val_signal.copy(),
                        "oos_signal": oos_signal.copy(),
                        "lockbox_signal": lockbox_signal.copy(),
                        "validation_signal": np.concatenate([val_signal, oos_signal, lockbox_signal]).copy(),
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
    selected_ensemble, ensemble_weights = select_ensemble(all_hof)
    for i, entry in enumerate(all_hof[:TOP_K]):
        print(
            f"  #{i + 1}: Round{entry['round']} TrainFoldIR={entry['train_FoldIR']:.4f}, "
            f"ValIC_daily={entry['val_IC_daily']:.4f}, OOSIC_daily={entry['oos_IC_daily']:.4f}, "
            f"LockboxIC_daily={entry['lockbox_IC_daily']:.4f}, Hit={entry['hit_rate']:.4f}"
        )
        print(f"       {entry['expr'][:80]}")
        results_for_save.append(
            {
                "id": entry["id"],
                "rank": i + 1,
                "round": entry["round"],
                "train_FoldIR": entry["train_FoldIR"],
                "train_IC_daily": entry["train_IC_daily"],
                "val_IC_daily": entry["val_IC_daily"],
                "oos_IC_daily": entry["oos_IC_daily"],
                "lockbox_IC_daily": entry["lockbox_IC_daily"],
                "hit_rate": entry["hit_rate"],
                "val_signal": np.asarray(entry["val_signal"], dtype=float).tolist(),
                "oos_signal": np.asarray(entry["oos_signal"], dtype=float).tolist(),
                "lockbox_signal": np.asarray(entry["lockbox_signal"], dtype=float).tolist(),
                "expression": entry["expression"],
                "serialized_tree": entry["serialized_tree"],
            }
        )

    if selected_ensemble:
        ensemble_metrics = evaluate_ensemble(
            selected=selected_ensemble,
            weights=ensemble_weights,
            oos_target=target_oos,
            lockbox_target=target_lockbox,
            oos_dates=oos_df["date"].values,
            lockbox_dates=lockbox_df["date"].values,
        )
        ensemble_ids = [candidate["id"] for candidate in selected_ensemble]
        print(
            f"Ensemble: size={len(selected_ensemble)}, ids={ensemble_ids}, "
            f"weights={np.round(ensemble_weights, 4).tolist()}"
        )
        print(
            f"Ensemble report-only: OOSIC_daily={ensemble_metrics['oos_IC_daily']:.4f}, "
            f"LockboxIC_daily={ensemble_metrics['lockbox_IC_daily']:.4f}"
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

    gate6_metrics = None
    if all_hof:
        gate6_metrics = run_gate6_validation(all_hof[0], validation_df)
        verification.append(f"gate6_fingerprint={gate6_metrics['feature_fingerprint']}")
        print("\nGate 6 regime IC breakdown:")
        for regime_name, info in gate6_metrics["regime_ic"].items():
            print(
                f"  {regime_name}: IC={info['ic']} rows={info['n_rows']} rationale={info['rationale']}"
            )
        cost_metrics = gate6_metrics["cost_metrics"]
        print(
            "Gate 6 net-of-cost: "
            f"gross_ic={cost_metrics['gross_ic']:.4f}, turnover={cost_metrics['turnover']:.4f}, "
            f"avg_cost_bps={cost_metrics['avg_cost_bps']:.2f}, net_ic_estimate={cost_metrics['net_ic_estimate']:.4f}"
        )
        permutation = gate6_metrics["permutation"]
        print(
            "Gate 6 permutation: "
            f"observed_ic={permutation['observed_ic']:.4f}, p_value={permutation['p_value']:.6f}, "
            f"null_mean={permutation['null_mean']:.6f}, null_std={permutation['null_std']:.6f}, seed={permutation['random_seed']}"
        )
        if permutation["p_value"] > GATE6_PERMUTATION_P_THRESHOLD:
            print(f"Gate 6 warning: permutation p-value > {GATE6_PERMUTATION_P_THRESHOLD:.2f}")
        if gate6_metrics["failing_regimes"]:
            raise ValueError(
                f"Gate 6 failed: regime IC below {GATE6_MIN_REGIME_IC} for {gate6_metrics['failing_regimes']}"
            )

    write_l2_report(SESSION_DIR / GATE6_REPORT_NAME, gate6_metrics, verification)

    print("\n" + "=" * 80)
    print("GENETIC ALPHA EVOLUTION V3 COMPLETE!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
