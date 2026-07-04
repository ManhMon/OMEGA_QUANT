"""Genetic Alpha Evolution V4 - performance-optimized wrapper over V3."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genetic_alpha_evolution_v3 as v3
from genetic_alpha_evolution_v3 import *  # noqa: F401,F403
from omega.quant.evolution import genetic_engine as ge

try:
    from numba import njit
except ModuleNotFoundError:  # ponytail: perf ceiling until numba installed.
    def njit(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator


ORIGINAL_GPINDIVIDUAL = ge.GPIndividual
ORIGINAL_COMPUTE_TIME_FOLD_IR = ge._compute_time_fold_ir
SESSION_REPORT_NAME = "l2_role16_gp_v4_impl_20260704.md"
SUBTREE_CACHE_KEY = "__subtree_cache__"
SUBTREE_CACHE_LOCK_KEY = "__subtree_cache_lock__"
TARGET_NEUTRALIZED_CACHE_KEY = "__target_neutralized_cache__"
FEATURE_BANK_KEY = "__feature_bank__"


def _thread_safe_feature_cache(features: dict[str, Any], key: str, factory: Any) -> Any:
    lock = features.setdefault(SUBTREE_CACHE_LOCK_KEY, threading.Lock())
    with lock:
        if key not in features:
            features[key] = factory()
        return features[key]


def _feature_array_length(features: dict[str, np.ndarray]) -> int:
    return len(next(iter(features.values())))


@njit(cache=True)
def _numba_rank_average_ties(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=np.float64)
    i = 0
    while i < values.size:
        j = i + 1
        while j < values.size and values[order[j]] == values[order[i]]:
            j += 1
        avg_rank = 0.5 * (i + j - 1) + 1.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j
    return ranks


@njit(cache=True)
def _numba_pearson_corr(a: np.ndarray, b: np.ndarray) -> float:
    n = a.size
    if n < 2:
        return np.nan
    a_mean = np.mean(a)
    b_mean = np.mean(b)
    num = 0.0
    a_var = 0.0
    b_var = 0.0
    for i in range(n):
        da = a[i] - a_mean
        db = b[i] - b_mean
        num += da * db
        a_var += da * da
        b_var += db * db
    denom = np.sqrt(a_var * b_var)
    if denom <= 1e-12:
        return np.nan
    return num / denom


@njit(cache=True)
def _numba_daily_ics(
    alpha: np.ndarray,
    target: np.ndarray,
    date_ids: np.ndarray,
    eval_mask: np.ndarray,
) -> np.ndarray:
    n_dates = 0
    for i in range(date_ids.size):
        if date_ids[i] >= n_dates:
            n_dates = date_ids[i] + 1
    out = np.empty(n_dates, dtype=np.float64)
    out[:] = np.nan
    counts = np.zeros(n_dates, dtype=np.int64)
    for i in range(date_ids.size):
        if eval_mask[i]:
            counts[date_ids[i]] += 1
    for date_id in range(n_dates):
        if counts[date_id] <= 5:
            continue
        alpha_day = np.empty(counts[date_id], dtype=np.float64)
        target_day = np.empty(counts[date_id], dtype=np.float64)
        pos = 0
        for i in range(date_ids.size):
            if eval_mask[i] and date_ids[i] == date_id:
                alpha_day[pos] = alpha[i]
                target_day[pos] = target[i]
                pos += 1
        alpha_rank = _numba_rank_average_ties(alpha_day)
        target_rank = _numba_rank_average_ties(target_day)
        out[date_id] = _numba_pearson_corr(alpha_rank, target_rank)
    return out


def _factorize_dates(dates: np.ndarray) -> np.ndarray:
    return pd.factorize(pd.Series(dates), sort=False)[0].astype(np.int64, copy=False)


def _compute_daily_ic_mean(alpha: np.ndarray, target: np.ndarray, features: dict[str, np.ndarray]) -> float:
    valid = ge._evaluation_mask(alpha, target, features)
    if not np.any(valid):
        return 0.0
    date_ids = _factorize_dates(np.asarray(features["__date__"]))
    daily_ics = _numba_daily_ics(
        np.asarray(alpha, dtype=np.float64),
        np.asarray(target, dtype=np.float64),
        date_ids,
        np.asarray(valid, dtype=np.bool_),
    )
    finite = daily_ics[np.isfinite(daily_ics)]
    return float(finite.mean()) if finite.size else 0.0


def _neutralize_target_once(
    target_fold: np.ndarray,
    fold_features: dict[str, np.ndarray],
    fold_cache_key: tuple[int, int],
) -> np.ndarray:
    cache = _thread_safe_feature_cache(fold_features, TARGET_NEUTRALIZED_CACHE_KEY, dict)
    cached = cache.get(fold_cache_key)
    if cached is not None:
        return cached
    neutralized = ge._neutralize_cross_section(
        target_fold,
        fold_features.get("__log_market_cap__"),
        fold_features.get("__sector__"),
        fold_features.get("__date__"),
        neutralization_cache=fold_features.get(ge.NEUTRALIZATION_CACHE_KEY),
    )
    cache[fold_cache_key] = neutralized
    return neutralized


def compute_engine_consistent_daily_ic(
    signal: np.ndarray,
    target: np.ndarray,
    features: dict[str, np.ndarray],
    config: ge.GPConfig,
) -> float:
    alpha = np.asarray(signal, dtype=np.float64)
    target_arr = np.asarray(target, dtype=np.float64)
    eval_features = dict(features)
    if config.neutralize_size_sector and "__sector__" in eval_features:
        alpha = ge._neutralize_cross_section(
            alpha,
            eval_features.get("__log_market_cap__"),
            eval_features.get("__sector__"),
            eval_features.get("__date__"),
            neutralization_cache=eval_features.get(ge.NEUTRALIZATION_CACHE_KEY),
        )
        target_arr = ge._neutralize_cross_section(
            target_arr,
            eval_features.get("__log_market_cap__"),
            eval_features.get("__sector__"),
            eval_features.get("__date__"),
            neutralization_cache=eval_features.get(ge.NEUTRALIZATION_CACHE_KEY),
        )
    return _compute_daily_ic_mean(alpha, target_arr, eval_features)


def _compute_time_fold_ir_v4(
    alpha: np.ndarray,
    target: np.ndarray,
    features: dict[str, np.ndarray],
    config: ge.GPConfig,
    *,
    pre_neutralized: bool = False,
) -> float:
    date_arr = features.get("__date__")
    if date_arr is None:
        return 0.0
    date_arr = np.asarray(date_arr)
    fold_count = 2 if getattr(config, "time_folds_fast_mode", False) else int(config.time_folds)
    fold_structure = features.get(ge.FOLD_STRUCTURE_CACHE_KEY)
    if fold_structure is None:
        fold_structure = ge._build_time_fold_structure(date_arr, fold_count)
    fold_ics: list[float] = []
    for fold_idx, (fold_mask, _fold_dates) in enumerate(fold_structure):
        fold_features: dict[str, np.ndarray] = {}
        for key, value in features.items():
            try:
                value_arr = np.asarray(value)
            except ValueError:
                continue
            if value_arr.ndim > 0 and len(value_arr) == len(date_arr):
                fold_features[key] = value_arr[fold_mask]
        alpha_fold = np.asarray(alpha[fold_mask], dtype=np.float64)
        target_fold = np.asarray(target[fold_mask], dtype=np.float64)
        if config.neutralize_size_sector and fold_features.get("__sector__") is not None:
            if not pre_neutralized:
                alpha_fold = ge._neutralize_cross_section(
                    alpha_fold,
                    fold_features.get("__log_market_cap__"),
                    fold_features.get("__sector__"),
                    fold_features.get("__date__"),
                    neutralization_cache=fold_features.get(ge.NEUTRALIZATION_CACHE_KEY),
                )
            target_fold = _neutralize_target_once(target_fold, fold_features, (id(target), fold_idx))
        ic_value = _compute_daily_ic_mean(alpha_fold, target_fold, fold_features)
        if np.isfinite(ic_value):
            fold_ics.append(float(ic_value))
    if len(fold_ics) < 2:
        return 0.0
    raw_ir = float(np.mean(fold_ics) / max(float(np.std(fold_ics, ddof=1)), float(config.fold_ir_std_floor)))
    return float(np.clip(raw_ir, -2.0, 2.0))


def _window_view(values: np.ndarray, window: int) -> np.ndarray:
    if values.size < window:
        return np.empty((0, window), dtype=np.float64)
    return np.lib.stride_tricks.sliding_window_view(values, window)


def _compute_feature_bank_for_ticker(frame: pd.DataFrame, avg_volume_window: int) -> pd.DataFrame:
    close = frame["close"].to_numpy(dtype=np.float64)
    volume = frame["volume"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    open_ = frame["open"].to_numpy(dtype=np.float64)
    traded_value = close * volume

    returns_1d = np.full(close.size, np.nan, dtype=np.float64)
    returns_5d = np.full(close.size, np.nan, dtype=np.float64)
    returns_1d[1:] = close[1:] / close[:-1] - 1.0
    returns_5d[5:] = close[5:] / close[:-5] - 1.0

    rolling_mean = np.full(close.size, np.nan, dtype=np.float64)
    windows = _window_view(volume, 20)
    if windows.size:
        rolling_mean[19:] = windows.mean(axis=1)
    vol_ratio = volume / rolling_mean

    avg_traded = np.full(close.size, np.nan, dtype=np.float64)
    tv_windows = _window_view(traded_value, avg_volume_window)
    min_periods = 5
    if avg_volume_window >= min_periods:
        prefix = np.cumsum(traded_value, dtype=np.float64)
        for idx in range(min_periods - 1, min(avg_volume_window - 1, close.size)):
            total = prefix[idx]
            count = idx + 1
            avg_traded[idx] = total / count
    if tv_windows.size:
        avg_traded[avg_volume_window - 1 :] = tv_windows.mean(axis=1)
    avg_traded = np.roll(avg_traded, 1)
    avg_traded[0] = np.nan

    out = frame.copy()
    out["returns_1d"] = returns_1d
    out["returns_5d"] = returns_5d
    out["vol_ratio"] = vol_ratio
    out["hl_range"] = (high - low) / close
    out["oc_range"] = (close - open_) / close
    out["__log_market_cap__"] = np.log1p(np.clip(traded_value, 0.0, None))
    out["traded_value"] = traded_value
    out["avg_traded_value"] = avg_traded
    return out


def _build_feature_bank(df: pd.DataFrame, args: Any) -> pd.DataFrame:
    parts = [_compute_feature_bank_for_ticker(group, args.avg_volume_window) for _, group in df.groupby("ticker", sort=False)]
    bank = pd.concat(parts, axis=0).sort_values(["ticker", "date"]).reset_index(drop=True)
    bank["hl_range_cs_z"] = v3._cs_zscore_by_date(bank["hl_range"], bank["date"])
    bank["oc_range_cs_z"] = v3._cs_zscore_by_date(bank["oc_range"], bank["date"])
    bank["__sector__"] = v3._volume_quartile_sector_proxy(bank["volume"], bank["date"])
    bank["liquidity_mask"] = (bank["avg_traded_value"] > args.min_avg_volume).fillna(False)
    bank[v3.FEATURE_COLS] = bank.groupby("ticker")[v3.FEATURE_COLS].shift(1)
    bank["__log_market_cap__"] = bank.groupby("ticker")["__log_market_cap__"].shift(1)
    bank["__sector__"] = bank.groupby("ticker")["__sector__"].shift(1)
    return bank


def load_dataset(args: Any) -> pd.DataFrame:
    loader = v3.Phase35DataLoader(warehouse_path="data/market_2015_now.parquet")
    df = loader.load_and_prepare(
        start_date="2015-01-05",
        end_date="2026-05-14",
        top_n_symbols=None,
        forward_horizons=[1, 3, 5, 10],
    )
    df = df.sort_values(["ticker", "date"]).copy()
    df = df.dropna(subset=["open", "high", "low", "close", "volume", "fwd_ret_5"])
    df = _build_feature_bank(df, args)
    exclusion_rate = 1.0 - float(df["liquidity_mask"].mean())
    if exclusion_rate > 0.5:
        print(
            f"Warning: liquidity filter excludes {exclusion_rate:.1%} of rows; "
            "consider lowering --min-avg-volume."
        )
    return df.dropna(subset=v3.FEATURE_COLS + ["fwd_ret_5", "__log_market_cap__", "__sector__"])


class GPIndividualV4(ORIGINAL_GPINDIVIDUAL):
    def _execute_tree(self, node: ge.GPNode, features: dict[str, np.ndarray]) -> np.ndarray:
        cache = _thread_safe_feature_cache(features, SUBTREE_CACHE_KEY, dict)
        cache_key = (id(features.get(FEATURE_BANK_KEY, features.get("__date__"))), node.to_string())
        cached = cache.get(cache_key)
        if cached is not None:
            return cached.copy()
        result = super()._execute_tree(node, features)
        cache[cache_key] = np.asarray(result, dtype=np.float64).copy()
        return result


def install_v4_optimizations() -> None:
    ge.GPIndividual = GPIndividualV4
    ge._compute_time_fold_ir = _compute_time_fold_ir_v4


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
        "scripts/genetic_alpha_evolution_v3.py",
        "src/omega/quant/evolution/genetic_engine.py",
    ]
    lines = [
        "# L2 Report - GP V4 Implementation",
        "",
        "- Session: `l2_role16_gp_v4_impl_20260704`",
        "- Gate: `GP_V4_IMPLEMENTATION`",
        "- Role: `16 machine-learning-engineer`",
        "- Scope: `scripts/genetic_alpha_evolution_v4.py`, `tests/test_genetic_alpha_evolution_v4.py`",
        "",
        "## Repo-Local Files Read",
        *[f"- `{path}`" for path in role_and_skill_files],
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
        lines.extend(
            [
                "",
                "## Gate 6 Metrics",
                f"- Feature fingerprint: `{gate6_metrics['feature_fingerprint']}`",
                f"- Failing regimes: `{gate6_metrics['failing_regimes']}`",
                f"- Permutation p-value: `{gate6_metrics['permutation']['p_value']:.6f}`",
                f"- Net IC estimate: `{gate6_metrics['cost_metrics']['net_ic_estimate']:.6f}`",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    install_v4_optimizations()
    v3.compute_engine_consistent_daily_ic = compute_engine_consistent_daily_ic
    v3.load_dataset = load_dataset
    v3.write_l2_report = write_l2_report
    v3.GATE6_REPORT_NAME = SESSION_REPORT_NAME
    v3.RESULTS_CSV_NAME = "genetic_alpha_v4_results.csv"
    v3.RESULTS_JSONL_NAME = "genetic_alpha_v4_results.jsonl"
    v3.BEST_JSON_NAME = "best_evolved_alpha_v4.json"
    return v3.main()


install_v4_optimizations()


if __name__ == "__main__":
    raise SystemExit(main())
