"""Genetic Alpha Evolution V4 - advanced optimization wrapper over V3."""

from __future__ import annotations

import hashlib
import random
import threading
import time as pytime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genetic_alpha_evolution_v3 as v3
from genetic_alpha_evolution_v3 import *  # noqa: F401,F403
from omega.quant.evolution import genetic_engine as ge

logger = ge.logger

try:
    from numba import njit
except ModuleNotFoundError:  # ponytail: perf ceiling until numba installed.
    def njit(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator


ORIGINAL_GPINDIVIDUAL = ge.GPIndividual
ORIGINAL_GENETIC_ENGINE = ge.GeneticEngine
ORIGINAL_GPCONFIG = ge.GPConfig
ORIGINAL_COMPUTE_TIME_FOLD_IR = ge._compute_time_fold_ir
ORIGINAL_NEUTRALIZE_CROSS_SECTION = ge._neutralize_cross_section
ORIGINAL_BATCH_NEUTRALIZE_CROSS_SECTION = ge._batch_neutralize_cross_section
SESSION_REPORT_NAME = "l2_role16_gp_v4_advanced_impl_20260705.md"
SUBTREE_CACHE_KEY = "__subtree_cache__"
SUBTREE_CACHE_LOCK_KEY = "__subtree_cache_lock__"
TARGET_NEUTRALIZED_CACHE_KEY = "__target_neutralized_cache__"
FEATURE_BANK_KEY = "__feature_bank__"
BATCH_FOLD_IR_CACHE_KEY = "__batch_fold_ir_cache__"
EARLY_REJECT_PENALTY = -2.0
EARLY_REJECT_FOLD_IC_THRESHOLD = -0.02
EARLY_REJECT_CUMAVG_THRESHOLD = 0.0
AUDIT_SAMPLE_RATE = 0.05
BATCH_FITNESS_SIZE = 32
ISLAND_COUNT = 3
ISLAND_MIGRATION_INTERVAL = 5
ISLAND_MIGRATION_RATE = 0.05
_DATE_GROUPS_CACHE: dict[tuple[int, int, Any, Any], dict[Any, np.ndarray]] = {}
_DATE_GROUPS_CACHE_LOCK = threading.Lock()


@dataclass
class GPConfigV4(ORIGINAL_GPCONFIG):
    batch_fitness_size: int = BATCH_FITNESS_SIZE
    island_count: int = ISLAND_COUNT
    island_migration_interval: int = ISLAND_MIGRATION_INTERVAL
    island_migration_rate: float = ISLAND_MIGRATION_RATE
    early_reject_penalty: float = EARLY_REJECT_PENALTY
    early_reject_fold_ic_threshold: float = EARLY_REJECT_FOLD_IC_THRESHOLD
    early_reject_cumavg_threshold: float = EARLY_REJECT_CUMAVG_THRESHOLD
    early_reject_audit_rate: float = AUDIT_SAMPLE_RATE


def _thread_safe_feature_cache(features: dict[str, Any], key: str, factory: Any) -> Any:
    lock = features.setdefault(SUBTREE_CACHE_LOCK_KEY, threading.Lock())
    with lock:
        if key not in features:
            features[key] = factory()
        return features[key]


def _feature_array_length(features: dict[str, np.ndarray]) -> int:
    return len(next(iter(features.values())))


def _safe_expr_hash(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big", signed=False)


def _is_audit_sample(tree_text: str, config: ge.GPConfig) -> bool:
    rate = float(getattr(config, "early_reject_audit_rate", AUDIT_SAMPLE_RATE))
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    seed = int(getattr(config, "random_seed", 0) or 0)
    value = (_safe_expr_hash(tree_text) ^ seed) % 10_000
    return value < int(round(rate * 10_000))


def _fitness_sort_value(individual: ge.GPIndividual) -> float:
    fitness = float(getattr(individual, "fitness", np.nan))
    return fitness if np.isfinite(fitness) else -np.inf


def _stable_rank_population(population: list[ge.GPIndividual]) -> list[ge.GPIndividual]:
    by_expr = sorted(population, key=lambda ind: ind.tree.to_string())
    return sorted(by_expr, key=_fitness_sort_value, reverse=True)


def _copy_individual(individual: ge.GPIndividual) -> ge.GPIndividual:
    clone = ge.GPIndividual(tree=individual.tree.copy())
    clone.fitness = individual.fitness
    clone.ic_score = individual.ic_score
    clone.complexity_penalty = individual.complexity_penalty
    clone.diversity_penalty = individual.diversity_penalty
    clone.transaction_cost_penalty = individual.transaction_cost_penalty
    clone.orthogonalization_penalty = individual.orthogonalization_penalty
    clone.turnover_rate = individual.turnover_rate
    return clone


def _slice_row_aligned_features(features: dict[str, Any], mask: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {}
    row_count = _feature_array_length(features)
    for key, value in features.items():
        try:
            value_arr = np.asarray(value)
        except ValueError:
            continue
        if value_arr.ndim > 0 and len(value_arr) == row_count:
            out[key] = value_arr[mask]
    return out


def _build_fold_views(features: dict[str, np.ndarray], fold_structure: tuple[tuple[np.ndarray, np.ndarray], ...]) -> list[dict[str, np.ndarray]]:
    fold_views = [_slice_row_aligned_features(features, fold_mask) for fold_mask, _ in fold_structure]
    neutralization_cache = features.get(ge.NEUTRALIZATION_CACHE_KEY)
    if neutralization_cache is not None:
        for fold_view in fold_views:
            if isinstance(neutralization_cache, dict):
                fold_view[ge.NEUTRALIZATION_CACHE_KEY] = {
                    key: value for key, value in neutralization_cache.items() if key != "__date_groups__"
                }
            else:
                fold_view[ge.NEUTRALIZATION_CACHE_KEY] = neutralization_cache
    return fold_views


def _batch_post_process(alpha_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lower = np.nanpercentile(alpha_matrix, 1, axis=0)
    upper = np.nanpercentile(alpha_matrix, 99, axis=0)
    clipped = np.clip(alpha_matrix, lower[None, :], upper[None, :])
    mean = np.nanmean(clipped, axis=0)
    std = np.nanstd(clipped, axis=0)
    standardized = (clipped - mean[None, :]) / (std[None, :] + 1e-9)
    standardized = np.nan_to_num(standardized, nan=0.0, posinf=0.0, neginf=0.0)
    valid_fraction = np.mean(np.isfinite(alpha_matrix), axis=0)
    return standardized, valid_fraction.astype(np.float64, copy=False)


def _group_row_indices_by_date(date_arr: np.ndarray) -> dict[Any, np.ndarray]:
    date_arr = np.asarray(date_arr)
    first_val = date_arr[0] if date_arr.size else None
    last_val = date_arr[-1] if date_arr.size else None
    cache_key = (id(date_arr), len(date_arr), first_val, last_val)
    with _DATE_GROUPS_CACHE_LOCK:
        if len(_DATE_GROUPS_CACHE) > 500:
            _DATE_GROUPS_CACHE.clear()
        cached = _DATE_GROUPS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    date_series = pd.Series(date_arr)
    date_groups = {
        current_date: indices.to_numpy(dtype=np.int64, copy=False)
        for current_date, indices in date_series.groupby(date_series, sort=False).groups.items()
    }
    with _DATE_GROUPS_CACHE_LOCK:
        return _DATE_GROUPS_CACHE.setdefault(cache_key, date_groups)


def _get_date_groups(
    date_arr: np.ndarray,
    neutralization_cache: dict[Any, tuple[np.ndarray, np.ndarray]] | None,
) -> dict[Any, np.ndarray]:
    if isinstance(neutralization_cache, dict):
        date_groups = neutralization_cache.get("__date_groups__")
        if date_groups is not None:
            max_index = -1
            for row_idx in date_groups.values():
                if row_idx.size:
                    max_index = max(max_index, int(row_idx[-1]))
            if max_index < len(date_arr):
                return date_groups
        date_groups = _group_row_indices_by_date(date_arr)
        neutralization_cache["__date_groups__"] = date_groups
        return date_groups
    return _group_row_indices_by_date(date_arr)


def _optimized_neutralize_cross_section(
    alpha_arr: np.ndarray,
    log_mcap_arr: np.ndarray,
    sector_arr: np.ndarray,
    date_arr: np.ndarray,
    neutralization_cache: dict[Any, tuple[np.ndarray, np.ndarray]] | None = None,
) -> np.ndarray:
    t0 = pytime.perf_counter()
    residuals = np.asarray(alpha_arr, dtype=np.float64).copy()
    if log_mcap_arr is None or sector_arr is None or date_arr is None:
        return residuals

    log_mcap_arr = np.asarray(log_mcap_arr, dtype=np.float64)
    sector_arr = np.asarray(sector_arr)
    date_arr = np.asarray(date_arr)
    date_cache = neutralization_cache
    if date_cache is None:
        date_cache = ge._build_neutralization_cache(log_mcap_arr, sector_arr, date_arr)
    date_groups = _get_date_groups(date_arr, neutralization_cache)
    for current_date in pd.unique(date_arr[pd.notna(date_arr)]):
        row_idx = date_groups.get(current_date)
        if row_idx is None or row_idx.size < 2:
            continue
        alpha_slice = residuals[row_idx]
        cached = date_cache.get(current_date)
        if cached is None:
            continue
        cached_valid, design = cached
        valid_rows = cached_valid & np.isfinite(alpha_slice)
        if np.count_nonzero(valid_rows) < 2:
            continue
        alpha_valid = alpha_slice[valid_rows]
        design_valid = design[valid_rows[cached_valid]]
        try:
            beta, _, rank, _ = np.linalg.lstsq(design_valid, alpha_valid, rcond=None)
        except np.linalg.LinAlgError:
            continue
        if rank < design_valid.shape[1]:
            continue
        alpha_slice[valid_rows] = alpha_valid - design_valid @ beta
        alpha_slice[valid_rows & (np.abs(alpha_slice) < 1e-12)] = 0.0
        residuals[row_idx] = alpha_slice
    logger.debug(
        "_optimized_neutralize_cross_section dt=%.4fs rows=%d dates=%d cache=%s",
        pytime.perf_counter() - t0,
        residuals.size,
        len(date_cache),
        neutralization_cache is not None,
    )
    return residuals


def _optimized_batch_neutralize_cross_section(
    alpha_matrix: np.ndarray,
    date_arr: np.ndarray,
    neutralization_cache: dict[Any, tuple[np.ndarray, np.ndarray]],
) -> np.ndarray:
    residuals = np.asarray(alpha_matrix, dtype=np.float64).copy()
    if residuals.ndim != 2 or residuals.size == 0:
        return residuals

    date_arr = np.asarray(date_arr)
    date_groups = _get_date_groups(date_arr, neutralization_cache)
    for current_date in pd.unique(date_arr[pd.notna(date_arr)]):
        cached = neutralization_cache.get(current_date)
        if cached is None:
            continue
        row_idx = date_groups.get(current_date)
        if row_idx is None or row_idx.size < 2:
            continue
        cached_valid, design = cached
        if np.count_nonzero(cached_valid) < 2:
            continue
        alpha_slice = residuals[row_idx]
        alpha_valid = alpha_slice[cached_valid]
        try:
            beta, _, rank, _ = np.linalg.lstsq(design, alpha_valid, rcond=None)
        except np.linalg.LinAlgError:
            continue
        if rank < design.shape[1]:
            continue
        alpha_slice[cached_valid] = alpha_valid - design @ beta
        alpha_slice[cached_valid] = np.where(
            np.abs(alpha_slice[cached_valid]) < 1e-12,
            0.0,
            alpha_slice[cached_valid],
        )
        residuals[row_idx] = alpha_slice
    return residuals


@njit(cache=True)
def _numba_batch_daily_ics(
    alpha_matrix: np.ndarray,
    target: np.ndarray,
    date_ids: np.ndarray,
    eval_mask_matrix: np.ndarray,
) -> np.ndarray:
    candidate_count = alpha_matrix.shape[1]
    n_dates = 0
    for i in range(date_ids.size):
        if date_ids[i] >= n_dates:
            n_dates = date_ids[i] + 1
    out = np.empty((n_dates, candidate_count), dtype=np.float64)
    out[:] = np.nan
    for candidate_idx in range(candidate_count):
        daily_ics = _numba_daily_ics(
            alpha_matrix[:, candidate_idx],
            target,
            date_ids,
            eval_mask_matrix[:, candidate_idx],
        )
        limit = min(n_dates, daily_ics.size)
        for date_idx in range(limit):
            out[date_idx, candidate_idx] = daily_ics[date_idx]
    return out


def _batch_fold_ir_scores(
    alpha_matrix: np.ndarray,
    target: np.ndarray,
    features: dict[str, np.ndarray],
    config: ge.GPConfig,
    *,
    tree_texts: list[str],
    pre_neutralized: bool = False,
) -> dict[int, tuple[float, bool]]:
    fold_structure = features.get(ge.FOLD_STRUCTURE_CACHE_KEY)
    if fold_structure is None:
        fold_count = 2 if getattr(config, "time_folds_fast_mode", False) else int(config.time_folds)
        fold_structure = ge._build_time_fold_structure(np.asarray(features["__date__"]), fold_count)
    if not fold_structure:
        return {idx: (0.0, False) for idx in range(alpha_matrix.shape[1])}
    fold_views = _build_fold_views(features, fold_structure)
    target_arr = np.asarray(target, dtype=np.float64)
    scores: dict[int, tuple[float, bool]] = {}
    fold_means_by_candidate: list[list[float]] = [[] for _ in range(alpha_matrix.shape[1])]
    rejected = [False] * alpha_matrix.shape[1]
    audit_mask = [_is_audit_sample(tree_text, config) for tree_text in tree_texts]
    for fold_idx, (fold_mask, _fold_dates) in enumerate(fold_structure):
        fold_features = fold_views[fold_idx]
        alpha_fold = np.asarray(alpha_matrix[fold_mask], dtype=np.float64)
        target_fold = np.asarray(target_arr[fold_mask], dtype=np.float64)
        if config.neutralize_size_sector and fold_features.get("__sector__") is not None:
            if not pre_neutralized:
                alpha_fold = ge._batch_neutralize_cross_section(
                    alpha_fold,
                    np.asarray(fold_features["__date__"]),
                    fold_features[ge.NEUTRALIZATION_CACHE_KEY],
                )
            target_fold = _neutralize_target_once(
                target_fold,
                features,
                fold_features,
                (id(target), fold_idx),
            )
        eval_mask_matrix = np.column_stack(
            [ge._evaluation_mask(alpha_fold[:, idx], target_fold, fold_features) for idx in range(alpha_fold.shape[1])]
        )
        daily_ic_matrix = _numba_batch_daily_ics(
            alpha_fold,
            target_fold,
            _factorize_dates(np.asarray(fold_features["__date__"])),
            np.asarray(eval_mask_matrix, dtype=np.bool_),
        )
        fold_ics = np.nanmean(daily_ic_matrix, axis=0) if daily_ic_matrix.size else np.full(alpha_fold.shape[1], np.nan)
        for candidate_idx, fold_ic in enumerate(fold_ics.tolist()):
            if np.isfinite(fold_ic):
                fold_means_by_candidate[candidate_idx].append(float(fold_ic))
            if fold_idx == 0 and not audit_mask[candidate_idx]:
                cumulative = float(np.mean(fold_means_by_candidate[candidate_idx])) if fold_means_by_candidate[candidate_idx] else np.nan
                if (
                    np.isfinite(fold_ic)
                    and (
                        fold_ic < float(getattr(config, "early_reject_fold_ic_threshold", EARLY_REJECT_FOLD_IC_THRESHOLD))
                        or cumulative < float(getattr(config, "early_reject_cumavg_threshold", EARLY_REJECT_CUMAVG_THRESHOLD))
                    )
                ):
                    rejected[candidate_idx] = True
    for idx, fold_ics in enumerate(fold_means_by_candidate):
        if rejected[idx]:
            scores[idx] = (float(getattr(config, "early_reject_penalty", EARLY_REJECT_PENALTY)), True)
            continue
        if len(fold_ics) < 2:
            scores[idx] = (0.0, False)
            continue
        raw_ir = float(np.mean(fold_ics) / max(float(np.std(fold_ics, ddof=1)), float(config.fold_ir_std_floor)))
        scores[idx] = (float(np.clip(raw_ir, -2.0, 2.0)), False)
    return scores


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
    features: dict[str, Any],
    fold_features: dict[str, np.ndarray],
    fold_cache_key: tuple[int, int],
) -> np.ndarray:
    cache = _thread_safe_feature_cache(features, TARGET_NEUTRALIZED_CACHE_KEY, dict)
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
    batch_fold_cache = features.get(BATCH_FOLD_IR_CACHE_KEY)
    if batch_fold_cache is not None and "__batch_candidate_id__" in features:
        cached = batch_fold_cache.get(features["__batch_candidate_id__"])
        if cached is not None:
            return float(cached[0])
    date_arr = features.get("__date__")
    if date_arr is None:
        return 0.0
    date_arr = np.asarray(date_arr)
    fold_count = 2 if getattr(config, "time_folds_fast_mode", False) else int(config.time_folds)
    fold_structure = features.get(ge.FOLD_STRUCTURE_CACHE_KEY)
    if fold_structure is None:
        fold_structure = ge._build_time_fold_structure(date_arr, fold_count)
    fold_ics: list[float] = []
    audit_sample = _is_audit_sample(features.get("__candidate_tree_text__", ""), config)
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
            target_fold = _neutralize_target_once(target_fold, features, fold_features, (id(target), fold_idx))
        ic_value = _compute_daily_ic_mean(alpha_fold, target_fold, fold_features)
        if np.isfinite(ic_value):
            fold_ics.append(float(ic_value))
            if (
                fold_idx == 0
                and not audit_sample
                and (
                    ic_value < float(getattr(config, "early_reject_fold_ic_threshold", EARLY_REJECT_FOLD_IC_THRESHOLD))
                    or float(np.mean(fold_ics)) < float(getattr(config, "early_reject_cumavg_threshold", EARLY_REJECT_CUMAVG_THRESHOLD))
                )
            ):
                return float(getattr(config, "early_reject_penalty", EARLY_REJECT_PENALTY))
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
        lock = _thread_safe_feature_cache(features, SUBTREE_CACHE_LOCK_KEY, threading.Lock)
        cache = _thread_safe_feature_cache(features, SUBTREE_CACHE_KEY, dict)
        cache_key = (id(features.get(FEATURE_BANK_KEY, features.get("__date__"))), node.to_string())
        with lock:
            cached = cache.get(cache_key)
        if cached is not None:
            return cached.copy()
        result = super()._execute_tree(node, features)
        with lock:
            cache[cache_key] = np.asarray(result, dtype=np.float64).copy()
        return result

    def _score_alpha_series(
        self,
        alpha_series: np.ndarray,
        valid_fraction: float,
        features: dict[str, np.ndarray],
        target: np.ndarray,
        hall_of_fame: list[ge.GPIndividual],
        config: ge.GPConfig,
        *,
        neutralized_alpha_series: np.ndarray | None = None,
    ) -> None:
        batch_fold_cache = features.get(BATCH_FOLD_IR_CACHE_KEY)
        batch_candidate_id = features.get("__batch_candidate_id__")
        cached = None if batch_fold_cache is None or batch_candidate_id is None else batch_fold_cache.get(batch_candidate_id)
        if cached is None:
            features = dict(features)
            features["__candidate_tree_text__"] = self.tree.to_string()
            return super()._score_alpha_series(
                alpha_series,
                valid_fraction,
                features,
                target,
                hall_of_fame,
                config,
                neutralized_alpha_series=neutralized_alpha_series,
            )
        ic_value, early_rejected = cached
        if early_rejected:
            self.ic_score = float(ic_value)
            self.complexity_penalty = 0.0
            self.diversity_penalty = 0.0
            self.transaction_cost_penalty = 0.0
            self.orthogonalization_penalty = 0.0
            self.turnover_rate = 0.0
            self.fitness = float(ic_value)
            return
        features = dict(features)
        features["__candidate_tree_text__"] = self.tree.to_string()
        super()._score_alpha_series(
            alpha_series,
            valid_fraction,
            features,
            target,
            hall_of_fame,
            config,
            neutralized_alpha_series=neutralized_alpha_series,
        )


class GeneticEngineV4(ORIGINAL_GENETIC_ENGINE):
    def _prepare_generation_features(self, features: dict[str, np.ndarray], target: np.ndarray, generation: int) -> tuple[dict[str, np.ndarray], np.ndarray]:
        if len(target) > 100000 and not self.config.use_time_fold_ir:
            if self.config.random_seed is not None:
                rng = np.random.RandomState(self.config.random_seed + generation)
                sample_idx = rng.choice(len(target), size=100000, replace=False)
            else:
                sample_idx = np.random.choice(len(target), size=100000, replace=False)
            gen_features = {k: v[sample_idx] for k, v in features.items()}
            gen_target = target[sample_idx]
        else:
            gen_features = features
            gen_target = target
        if self.config.use_fast_penalties and "__date__" in gen_features:
            if gen_features is features:
                gen_features = dict(gen_features)
            fold_count = 2 if getattr(self.config, "time_folds_fast_mode", False) else int(self.config.time_folds)
            gen_features[ge.FOLD_STRUCTURE_CACHE_KEY] = ge._build_time_fold_structure(np.asarray(gen_features["__date__"]), fold_count)
        if self.config.use_fast_penalties and self.hall_of_fame:
            if gen_features is features:
                gen_features = dict(gen_features)
            gen_features[ge.HOF_ALPHA_CACHE_KEY] = self._build_hof_alpha_cache(self.hall_of_fame, gen_features)
            gen_features[ge.ALPHA_CACHE_KEY] = {}
        if self.config.use_fast_penalties and self._ortho_ranks:
            if gen_features is features:
                gen_features = dict(gen_features)
            gen_features[ge.ORTHO_RANKS_CACHE_KEY] = self._ortho_ranks
        if self.config.use_icir and "__date__" in gen_features:
            gen_features = dict(gen_features)
            gen_features[ge.DATE_CHUNK_CACHE_KEY] = self._precompute_date_chunks(gen_features, gen_target)
        if (
            self.config.neutralize_size_sector
            and "__date__" in gen_features
            and "__log_market_cap__" in gen_features
            and "__sector__" in gen_features
        ):
            if gen_features is features:
                gen_features = dict(gen_features)
            gen_features[ge.NEUTRALIZATION_CACHE_KEY] = ge._build_neutralization_cache(
                np.asarray(gen_features.get("__log_market_cap__"), dtype=np.float64),
                np.asarray(gen_features.get("__sector__")),
                np.asarray(gen_features.get("__date__")),
            )
        return gen_features, gen_target

    def _evaluate_population_with_batch_neutralization(self, features: dict[str, np.ndarray], target: np.ndarray) -> None:
        batch_size = max(1, int(getattr(self.config, "batch_fitness_size", BATCH_FITNESS_SIZE)))
        for start in range(0, len(self.population), batch_size):
            batch = self.population[start:start + batch_size]
            try:
                raw_alpha = np.column_stack([ind._execute_tree(ind.tree, features) for ind in batch])
                std = np.nanstd(raw_alpha, axis=0)
                keep_mask = np.isfinite(std) & (std >= 1e-6)
                prepared_rows: list[tuple[ge.GPIndividual, np.ndarray | None, float]] = []
                if np.any(keep_mask):
                    processed_alpha, valid_fraction = _batch_post_process(raw_alpha[:, keep_mask])
                    neutralized_alpha = ge._batch_neutralize_cross_section(
                        processed_alpha,
                        np.asarray(features["__date__"]),
                        features[ge.NEUTRALIZATION_CACHE_KEY],
                    )
                    active_indices = np.flatnonzero(keep_mask)
                    tree_texts = [batch[idx].tree.to_string() for idx in active_indices]
                    batch_scores = _batch_fold_ir_scores(
                        neutralized_alpha,
                        target,
                        features,
                        self.config,
                        tree_texts=tree_texts,
                        pre_neutralized=True,
                    )
                    score_cache = {
                        int(active_indices[idx]): batch_scores[idx]
                        for idx in range(len(active_indices))
                    }
                else:
                    processed_alpha = np.empty((len(target), 0), dtype=np.float64)
                    valid_fraction = np.empty(0, dtype=np.float64)
                    neutralized_alpha = processed_alpha
                    active_indices = np.empty(0, dtype=np.int64)
                    score_cache = {}
                active_pos = 0
                for local_idx, individual in enumerate(batch):
                    if local_idx not in score_cache:
                        prepared_rows.append((individual, None, 0.0))
                        continue
                    prepared_rows.append((individual, processed_alpha[:, active_pos], float(valid_fraction[active_pos])))
                    active_pos += 1
                for local_idx, (individual, alpha_series, valid_fraction_value) in enumerate(prepared_rows):
                    if alpha_series is None:
                        ge._set_rejected_fitness(individual)
                        continue
                    candidate_features = dict(features)
                    candidate_features[BATCH_FOLD_IR_CACHE_KEY] = score_cache
                    candidate_features["__batch_candidate_id__"] = local_idx
                    candidate_features["__candidate_tree_text__"] = individual.tree.to_string()
                    neutralized_idx = int(np.where(active_indices == local_idx)[0][0])
                    individual._score_alpha_series(
                        alpha_series,
                        valid_fraction_value,
                        candidate_features,
                        target,
                        self.hall_of_fame,
                        self.config,
                        neutralized_alpha_series=neutralized_alpha[:, neutralized_idx],
                    )
            except Exception:
                for individual in batch:
                    individual.evaluate(features, target, self.hall_of_fame, self.config)

    def _evaluate_population_group(self, population: list[ge.GPIndividual], features: dict[str, np.ndarray], target: np.ndarray) -> list[ge.GPIndividual]:
        original_population = self.population
        self.population = population
        if self._should_use_batch_neutralization(features):
            self._evaluate_population_with_batch_neutralization(features, target)
        elif self.config.n_jobs == 1:
            for individual in self.population:
                individual.evaluate(features, target, self.hall_of_fame, self.config)
        else:
            self.population = list(ge.Parallel(n_jobs=self.config.n_jobs, batch_size="auto")(
                ge.delayed(ge._evaluate_individual)(ind, features, target, self.hall_of_fame, self.config)
                for ind in self.population
            ))
        result = self.population
        self.population = original_population
        return result

    def _breed_island(self, population: list[ge.GPIndividual], rng_seed: int) -> list[ge.GPIndividual]:
        if not population:
            return []
        state_np = np.random.get_state()
        state_py = random.getstate()
        np.random.seed(rng_seed)
        random.seed(rng_seed)
        original_population = self.population
        self.population = population
        self._next_generation()
        next_population = self.population
        self.population = original_population
        np.random.set_state(state_np)
        random.setstate(state_py)
        return next_population

    def _migrate_islands(self, islands: list[list[ge.GPIndividual]]) -> list[list[ge.GPIndividual]]:
        if len(islands) < 2:
            return islands
        migrate_count = max(1, int(round(self.config.population_size * float(getattr(self.config, "island_migration_rate", ISLAND_MIGRATION_RATE)))))
        ranked = [_stable_rank_population(island) for island in islands]
        for island_idx, island in enumerate(ranked):
            migrants = [_copy_individual(ind) for ind in island[:migrate_count]]
            next_idx = (island_idx + 1) % len(ranked)
            recipient = ranked[next_idx]
            recipient[-migrate_count:] = migrants
        return ranked

    def evolve(self, features: dict[str, np.ndarray], target: np.ndarray) -> list[ge.GPIndividual]:
        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)
            random.seed(self.config.random_seed)
        self.feature_names = [k for k in features.keys() if not k.startswith("target") and not k.startswith("__")]
        logger = ge.logger
        logger.info(f"Starting GP evolution V4 advanced: pop={self.config.population_size}, gen={self.config.generations}")
        self.initialize_population()
        island_count = max(1, int(getattr(self.config, "island_count", ISLAND_COUNT)))
        islands = [list(chunk.tolist()) for chunk in np.array_split(np.asarray(self.population, dtype=object), island_count) if len(chunk) > 0]
        t_start = pytime.monotonic()
        best_fitness_seen = -np.inf
        stagnant_generations = 0
        for generation in range(self.config.generations):
            gen_features, gen_target = self._prepare_generation_features(features, target, generation)
            pre_neutralized = bool(
                self.config.neutralize_size_sector
                and gen_features.get(ge.NEUTRALIZATION_CACHE_KEY) is not None
                and self._should_use_batch_neutralization(gen_features)
            )
            evaluated_islands: list[list[ge.GPIndividual]] = []
            base_seed = int(self.config.random_seed or 0) + generation * 10_000
            for island_idx, island in enumerate(islands):
                island_features = dict(gen_features)
                island_features.pop(SUBTREE_CACHE_KEY, None)
                island_features.pop(TARGET_NEUTRALIZED_CACHE_KEY, None)
                island_features.pop(BATCH_FOLD_IR_CACHE_KEY, None)
                if pre_neutralized:
                    island_features["__pre_neutralized__"] = True
                island_seed = base_seed + island_idx * 1000
                np.random.seed(island_seed)
                random.seed(island_seed)
                evaluated_islands.append(self._evaluate_population_group(island, island_features, gen_target))
            if (generation + 1) % max(1, int(getattr(self.config, "island_migration_interval", ISLAND_MIGRATION_INTERVAL))) == 0:
                evaluated_islands = self._migrate_islands(evaluated_islands)
            self.population = [ind for island in evaluated_islands for ind in island]
            self.population = _stable_rank_population(self.population)
            self.update_hall_of_fame()
            best = self.population[0]
            self.history.append({
                "generation": generation,
                "best_fitness": best.fitness,
                "best_ic": best.ic_score,
                "best_tree_size": best.tree.size(),
            })
            logger.info(f"Gen {generation + 1}: Fold_IR={best.ic_score:.4f}, Fitness={best.fitness:.4f}")
            elapsed = pytime.monotonic() - t_start
            gen_time = elapsed / (generation + 1)
            remaining = gen_time * (self.config.generations - generation - 1)
            self.history[-1]["elapsed_sec"] = round(elapsed, 2)
            self.history[-1]["gen_time_sec"] = round(gen_time, 3)
            self.history[-1]["eta_sec"] = round(remaining, 1)
            if best.fitness > best_fitness_seen + 1e-6:
                best_fitness_seen = best.fitness
                stagnant_generations = 0
            else:
                stagnant_generations += 1
            if self.config.early_stopping_rounds > 0 and stagnant_generations >= self.config.early_stopping_rounds:
                logger.info(
                    f"Early stopping: no best-fitness improvement for {self.config.early_stopping_rounds} generations"
                )
                break
            if generation + 1 < self.config.generations:
                islands = [
                    self._breed_island(
                        island,
                        base_seed + island_idx * 1000 + 1,
                    )
                    for island_idx, island in enumerate(evaluated_islands)
                ]
        return self.hall_of_fame


def install_v4_optimizations() -> None:
    ge.GPConfig = GPConfigV4
    ge.GPIndividual = GPIndividualV4
    ge.GeneticEngine = GeneticEngineV4
    ge._compute_time_fold_ir = _compute_time_fold_ir_v4
    ge._neutralize_cross_section = _optimized_neutralize_cross_section
    ge._batch_neutralize_cross_section = _optimized_batch_neutralize_cross_section
    v3.GPConfig = GPConfigV4
    v3.GeneticEngine = GeneticEngineV4


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
        "scripts/genetic_alpha_evolution_v4.py",
        "tests/test_genetic_alpha_evolution_v4.py",
    ]
    lines = [
        "# L2 Report - GP V4 Advanced Implementation",
        "",
        "- Session: `l2_role16_gp_v4_advanced_impl_20260705`",
        "- Gate: `GP_V4_ADVANCED_IMPLEMENTATION`",
        "- Role: `16 machine-learning-engineer`",
        "- Scope: `scripts/genetic_alpha_evolution_v4.py`, `tests/test_genetic_alpha_evolution_v4.py`",
        "",
        "## Repo-Local Files Read",
        *[f"- `{path}`" for path in role_and_skill_files],
        "",
        "## Forbidden Path Scan",
        "- `.gemini\\antigravity-ide\\scratch\\ag-kit` is not present and non-authoritative.",
        "- `.openclaw\\skills` is not present and non-authoritative.",
        "- `C:\\Users\\GHC\\.agents` is outside repo scope and non-authoritative.",
        "- `.codex\\memories` is not present and non-authoritative.",
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
