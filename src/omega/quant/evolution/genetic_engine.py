"""
OMEGA_QUANT Genetic Programming Engine (Layer 01)
Phase 3.3: Alpha Discovery - Genetic Programming

100% Vectorized | PIT-Safe | Institutional Grade

Ported from V21_QUANT layer_01_core_intelligence/genetic_programming.py
Adapted to OMEGA standards with stricter PIT compliance.

Key Features:
- Tree-based GP with protected operators
- IC-based fitness with complexity penalty
- Diversity enforcement via Hall of Fame
- Numerical stability (winsorization, z-score normalization)
- Point-in-time compliance (no look-ahead bias)
- Option D: Orthogonalization penalty with configurable baseline set
  (penalizes alphas correlated with existing signals to ensure novelty)

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0 (V21 Port)
"""

from __future__ import annotations

import logging
import random
import time
import gc
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from joblib import Parallel, delayed

try:
    import bottleneck as bn
except ImportError:  # pragma: no cover - optional fast path
    bn = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATE_CHUNK_CACHE_KEY = '__date_chunk_indices__'
NEUTRALIZATION_CACHE_KEY = '__neutralization_cache__'
HOF_ALPHA_CACHE_KEY = '__hof_alphas__'
FOLD_STRUCTURE_CACHE_KEY = '__fold_structure__'
ORTHO_RANKS_CACHE_KEY = '__ortho_ranks__'
ALPHA_CACHE_KEY = '__alpha_cache__'


def _set_rejected_fitness(individual: "GPIndividual") -> None:
    individual.fitness = -np.inf
    individual.ic_score = 0.0
    individual.complexity_penalty = 0.0
    individual.diversity_penalty = 0.0
    individual.transaction_cost_penalty = 0.0
    individual.orthogonalization_penalty = 0.0
    individual.turnover_rate = 0.0


def _pearson_corr(a: np.ndarray, b: np.ndarray) -> float:
    valid = np.isfinite(a) & np.isfinite(b)
    if np.count_nonzero(valid) < 2:
        return np.nan
    a_valid = np.asarray(a[valid], dtype=np.float64)
    b_valid = np.asarray(b[valid], dtype=np.float64)
    a_valid = a_valid - np.mean(a_valid)
    b_valid = b_valid - np.mean(b_valid)
    denom = np.sqrt(np.sum(a_valid * a_valid) * np.sum(b_valid * b_valid))
    if denom < 1e-12:
        return np.nan
    return float(np.sum(a_valid * b_valid) / denom)


def _average_rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    sorted_values = values[order]
    starts = np.r_[True, sorted_values[1:] != sorted_values[:-1]]
    group_starts = np.flatnonzero(starts)
    group_ends = np.r_[group_starts[1:] - 1, values.size - 1]
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = np.repeat((group_starts + group_ends + 2.0) / 2.0, np.diff(np.r_[group_starts, values.size]))
    return ranks


def _spearman_corr_via_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate Spearman correlation without pandas or scipy overhead."""
    span = min(len(a), len(b))
    if span < 2:
        return np.nan
    valid = np.isfinite(a[:span]) & np.isfinite(b[:span])
    if np.count_nonzero(valid) < 2:
        return np.nan
    a_rank = _average_rank(a[:span][valid])
    b_rank = _average_rank(b[:span][valid])
    return _pearson_corr(a_rank, b_rank)


def _build_time_fold_structure(
    date_arr: np.ndarray,
    fold_count: int,
) -> Tuple[Tuple[np.ndarray, np.ndarray], ...]:
    valid_dates = np.sort(pd.unique(date_arr[pd.notna(date_arr)]))
    if valid_dates.size == 0:
        return tuple()
    fold_structure: List[Tuple[np.ndarray, np.ndarray]] = []
    for fold_dates in np.array_split(valid_dates, max(1, fold_count)):
        if len(fold_dates) == 0:
            continue
        fold_mask = np.isin(date_arr, fold_dates)
        if np.count_nonzero(fold_mask) < 2:
            continue
        fold_structure.append((fold_mask, np.asarray(fold_dates)))
    return tuple(fold_structure)


def _build_neutralization_cache(
    log_mcap_arr: np.ndarray,
    sector_arr: np.ndarray,
    date_arr: np.ndarray,
) -> Dict[Any, Tuple[np.ndarray, np.ndarray]]:
    cache: Dict[Any, Tuple[np.ndarray, np.ndarray]] = {}
    for current_date in pd.unique(date_arr[pd.notna(date_arr)]):
        mask = date_arr == current_date
        if np.count_nonzero(mask) < 2:
            continue
        mcap_slice = log_mcap_arr[mask]
        sector_slice = sector_arr[mask]
        valid = np.isfinite(mcap_slice) & pd.notna(sector_slice)
        if np.count_nonzero(valid) < 2:
            continue
        valid_sector = pd.factorize(sector_slice[valid], sort=True)[0]
        sector_dummies = np.eye(max(int(valid_sector.max()) + 1, 1), dtype=np.float64)[valid_sector]
        design_parts = [
            np.ones(np.count_nonzero(valid), dtype=np.float64),
            mcap_slice[valid],
        ]
        if sector_dummies.shape[1] > 1:
            design_parts.append(sector_dummies[:, 1:])
        cache[current_date] = (valid, np.column_stack(design_parts))
    return cache


def _neutralize_cross_section(
    alpha_arr: np.ndarray,
    log_mcap_arr: np.ndarray,
    sector_arr: np.ndarray,
    date_arr: np.ndarray,
    neutralization_cache: Optional[Dict[Any, Tuple[np.ndarray, np.ndarray]]] = None,
) -> np.ndarray:
    t0 = time.perf_counter()
    residuals = np.asarray(alpha_arr, dtype=np.float64).copy()
    if log_mcap_arr is None or sector_arr is None or date_arr is None:
        return residuals

    log_mcap_arr = np.asarray(log_mcap_arr, dtype=np.float64)
    sector_arr = np.asarray(sector_arr)
    date_arr = np.asarray(date_arr)
    date_cache = neutralization_cache
    if date_cache is None:
        date_cache = _build_neutralization_cache(log_mcap_arr, sector_arr, date_arr)
    for current_date in pd.unique(date_arr[pd.notna(date_arr)]):
        mask = date_arr == current_date
        if np.count_nonzero(mask) < 2:
            continue
        alpha_slice = residuals[mask]
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
        residuals[mask] = alpha_slice
    logger.debug(
        "_neutralize_cross_section dt=%.4fs rows=%d dates=%d cache=%s",
        time.perf_counter() - t0,
        residuals.size,
        len(date_cache),
        neutralization_cache is not None,
    )
    return residuals


def _batch_neutralize_cross_section(
    alpha_matrix: np.ndarray,
    date_arr: np.ndarray,
    neutralization_cache: Dict[Any, Tuple[np.ndarray, np.ndarray]],
) -> np.ndarray:
    residuals = np.asarray(alpha_matrix, dtype=np.float64).copy()
    if residuals.ndim != 2 or residuals.size == 0:
        return residuals

    date_arr = np.asarray(date_arr)
    for current_date in pd.unique(date_arr[pd.notna(date_arr)]):
        cached = neutralization_cache.get(current_date)
        if cached is None:
            continue
        mask = date_arr == current_date
        if np.count_nonzero(mask) < 2:
            continue
        cached_valid, design = cached
        if np.count_nonzero(cached_valid) < 2:
            continue
        alpha_slice = residuals[mask]
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
        residuals[mask] = alpha_slice
    return residuals


def _evaluation_mask(
    alpha_series: np.ndarray,
    target: np.ndarray,
    features: Dict[str, np.ndarray],
) -> np.ndarray:
    mask = np.isfinite(alpha_series) & np.isfinite(target)
    liquidity_mask = features.get('__liquidity_mask__')
    if liquidity_mask is not None:
        mask &= np.asarray(liquidity_mask, dtype=bool)
    return mask


def _compute_time_fold_ir(
    alpha: np.ndarray,
    target: np.ndarray,
    features: Dict[str, np.ndarray],
    config: "GPConfig",
    *,
    pre_neutralized: bool = False,
) -> float:
    t0 = time.perf_counter()
    date_arr = features.get('__date__')
    log_mcap_arr = features.get('__log_market_cap__')
    sector_arr = features.get('__sector__')
    if date_arr is None:
        return 0.0

    date_arr = np.asarray(date_arr)
    valid_dates = np.sort(pd.unique(date_arr[pd.notna(date_arr)]))
    if valid_dates.size == 0:
        return 0.0

    fold_ics: List[float] = []
    fold_count = 2 if getattr(config, 'time_folds_fast_mode', False) else int(config.time_folds)
    neutralization_cache = features.get(NEUTRALIZATION_CACHE_KEY)
    fold_structure = features.get(FOLD_STRUCTURE_CACHE_KEY)
    if fold_structure is None:
        fold_structure = _build_time_fold_structure(date_arr, fold_count)
    for fold_mask, _fold_dates in fold_structure:
        alpha_fold = np.asarray(alpha[fold_mask], dtype=np.float64)
        target_fold = np.asarray(target[fold_mask], dtype=np.float64)
        fold_features = {}
        for key, value in features.items():
            try:
                value_arr = np.asarray(value)
            except ValueError:
                continue
            if value_arr.ndim > 0 and len(value_arr) == len(date_arr):
                fold_features[key] = value_arr[fold_mask]
        if (
            config.neutralize_size_sector
            and not pre_neutralized
            and log_mcap_arr is not None
            and sector_arr is not None
        ):
            alpha_fold = _neutralize_cross_section(
                alpha_fold,
                fold_features.get('__log_market_cap__'),
                fold_features.get('__sector__'),
                fold_features.get('__date__'),
                neutralization_cache=neutralization_cache,
            )
        if config.neutralize_size_sector and log_mcap_arr is not None and sector_arr is not None:
            target_fold = _neutralize_cross_section(
                target_fold,
                fold_features.get('__log_market_cap__'),
                fold_features.get('__sector__'),
                fold_features.get('__date__'),
                neutralization_cache=neutralization_cache,
            )
        fold_date_arr = fold_features.get('__date__')
        if fold_date_arr is None:
            continue
        fold_date_arr = np.asarray(fold_date_arr)
        daily_ics: List[float] = []
        for current_date in pd.unique(fold_date_arr[pd.notna(fold_date_arr)]):
            date_mask = fold_date_arr == current_date
            valid = date_mask & _evaluation_mask(alpha_fold, target_fold, fold_features)
            if np.count_nonzero(valid) <= 5:
                continue
            ic_value = _spearman_corr_via_corrcoef(alpha_fold[valid], target_fold[valid])
            if not np.isnan(ic_value):
                daily_ics.append(ic_value)
        if daily_ics:
            fold_ics.append(float(np.mean(daily_ics)))

    if len(fold_ics) < 2:
        return 0.0
    raw_ir = float(np.mean(fold_ics) / max(float(np.std(fold_ics, ddof=1)), float(config.fold_ir_std_floor)))
    result = float(np.clip(raw_ir, -2.0, 2.0))
    logger.debug(
        "_compute_time_fold_ir dt=%.4fs folds=%d dates=%d cache=%s result=%.6f",
        time.perf_counter() - t0,
        max(1, fold_count),
        valid_dates.size,
        neutralization_cache is not None,
        result,
    )
    return result


def _chunked_average_ranks(
    order: np.ndarray,
    values: np.ndarray,
    chunk_id: np.ndarray,
    ordinal_ranks: np.ndarray,
) -> np.ndarray:
    """Average ranks within date chunks, preserving ties (scipy 'average' method).

    `order` is a stable sort of `values` that keeps each `chunk_id` block
    contiguous and ascending within the block; `ordinal_ranks[i]` is the
    1-based ordinal rank (within its chunk) of the element at sorted
    position `i`. Consecutive equal values inside a chunk form a tie group
    and receive the mean of their ordinal ranks. Returns average ranks in
    the original (flat) element order.
    """
    n = order.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    v_sorted = values[order]
    c_sorted = chunk_id[order]
    is_new = np.empty(n, dtype=bool)
    is_new[0] = True
    # New tie group at a chunk boundary or a change in value.
    is_new[1:] = (c_sorted[1:] != c_sorted[:-1]) | (v_sorted[1:] != v_sorted[:-1])
    group_id = np.cumsum(is_new) - 1
    group_starts = np.flatnonzero(is_new)
    group_ends = np.empty_like(group_starts)
    group_ends[:-1] = group_starts[1:] - 1
    group_ends[-1] = n - 1
    # Ordinal ranks within a group are consecutive integers, so the group
    # mean is simply the average of its first and last ordinal rank.
    avg_by_group = (ordinal_ranks[group_starts] + ordinal_ranks[group_ends]) / 2.0
    out[order] = avg_by_group[group_id]
    return out


# Standalone function for joblib parallel (must be picklable for serialization)
def _evaluate_individual(ind, features, target, hof, config):
    ind.evaluate(features, target, hof, config)
    return ind


def _prepare_individual_batch(ind, features):
    try:
        alpha_series = ind._execute_tree(ind.tree, features)
        valid_fraction = float(np.mean(np.isfinite(alpha_series)))
        if np.std(alpha_series) < 1e-6:
            return ind, None, valid_fraction

        lower = np.nanpercentile(alpha_series, 1)
        upper = np.nanpercentile(alpha_series, 99)
        alpha_series = np.clip(alpha_series, lower, upper)
        alpha_series = (alpha_series - np.nanmean(alpha_series)) / (np.nanstd(alpha_series) + 1e-9)
        alpha_series = np.nan_to_num(alpha_series, nan=0.0, posinf=0.0, neginf=0.0)
        return ind, alpha_series, valid_fraction
    except Exception:
        return ind, None, 0.0

def _score_prepared_individual(
    idx,
    prepared,
    neutralized_rows,
    features,
    target,
    hall_of_fame,
    config,
):
    individual, alpha_series, valid_fraction = prepared
    if alpha_series is None:
        _set_rejected_fitness(individual)
        return individual
    individual._score_alpha_series(
        alpha_series,
        valid_fraction,
        features,
        target,
        hall_of_fame,
        config,
        neutralized_alpha_series=neutralized_rows[idx],
    )
    return individual



# =============================================================================
# Protected Operators (Numerical Stability)
# =============================================================================

def _protected_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Division with zero protection."""
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(np.abs(b) > 1e-9, a / b, 0.0)


def _signed_log(x: np.ndarray) -> np.ndarray:
    """Sign-preserving logarithm: sign(x) * log1p(|x|).

    Unlike log(|x|), this keeps the sign of the input so negative and
    positive values of equal magnitude are not folded together, and it is
    NaN-free on the whole real line (log1p(|x|) >= 0 always).
    """
    return np.sign(x) * np.log1p(np.abs(x))


def _protected_sqrt(x: np.ndarray) -> np.ndarray:
    """Square root with negative protection."""
    return np.sqrt(np.abs(x))


def _protected_exp(x: np.ndarray) -> np.ndarray:
    """Exponential with overflow protection."""
    return np.exp(np.clip(x, -10, 10))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Sigmoid activation with overflow protection."""
    return 1.0 / (1.0 + _protected_exp(-x))


def _rank_transform(x: np.ndarray) -> np.ndarray:
    """Percentile rank transformation."""
    if len(x) == 0:
        return x
    return pd.Series(x).rank(pct=True, method='average').values


def _cs_rank(x: np.ndarray) -> np.ndarray:
    """Cross-sectional rank transformation."""
    return _rank_transform(x)


def _cs_zscore(x: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score transformation."""
    if len(x) == 0:
        return x
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-9)


def _ts_rank(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Time-series rank within rolling window."""
    if len(x) < window:
        return np.zeros_like(x)
    # Fast vectorized rolling rank using sliding window view
    windows = np.lib.stride_tricks.sliding_window_view(x, window)
    current_elements = windows[:, -1][:, np.newaxis]
    ranks = np.sum(windows <= current_elements, axis=1) / window
    return np.concatenate([np.full(window - 1, 0.5), ranks])


def _ts_std(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling standard deviation."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_std(np.where(np.isfinite(x), x, np.nan), window=window, min_count=window, ddof=1)
        return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return pd.Series(x).rolling(window).std().fillna(0.0).values


def _ts_mean(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling mean."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_mean(np.where(np.isfinite(x), x, np.nan), window=window, min_count=window)
        return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return pd.Series(x).rolling(window).mean().fillna(0.0).values


def _decay_linear(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Linear decay weighted average."""
    if len(x) < window:
        return np.zeros_like(x)
    weights = np.arange(1, window + 1)
    weights = weights / weights.sum()
    res = np.convolve(x, weights[::-1], mode='valid')
    return np.concatenate([np.zeros(window - 1), res])


def _ts_max(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling maximum."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_max(np.where(np.isfinite(x), x, np.nan), window=window, min_count=window)
        return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return pd.Series(x).rolling(window).max().fillna(0.0).values


def _ts_min(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling minimum."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_min(np.where(np.isfinite(x), x, np.nan), window=window, min_count=window)
        return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return pd.Series(x).rolling(window).min().fillna(0.0).values


def _ts_delay(x: np.ndarray, periods: int = 1) -> np.ndarray:
    """Lag series by periods."""
    if periods <= 0:
        return x.copy()
    if len(x) <= periods:
        return np.zeros_like(x)
    out = np.empty_like(x)
    out[:periods] = 0.0
    out[periods:] = x[:-periods]
    return out


def _apply_grouped_ts_transform(
    values: np.ndarray,
    tickers: Optional[np.ndarray],
    dates: Optional[np.ndarray],
    transform: Callable[[np.ndarray], np.ndarray],
) -> np.ndarray:
    """Apply TS transform per ticker, sorted by ticker/date, then restore row order."""
    arr = np.asarray(values, dtype=np.float64)
    if tickers is None:
        return transform(arr)

    ticker_arr = np.asarray(tickers)
    if ticker_arr.shape[0] != arr.shape[0]:
        return transform(arr)

    if dates is not None:
        date_arr = pd.to_datetime(np.asarray(dates))
        order = np.lexsort((np.asarray(date_arr, dtype='datetime64[ns]'), ticker_arr))
    else:
        order = np.argsort(ticker_arr, kind='mergesort')

    sorted_values = arr[order]
    sorted_tickers = ticker_arr[order]
    out_sorted = np.empty_like(sorted_values)
    _, starts = np.unique(sorted_tickers, return_index=True)
    stops = np.concatenate((starts[1:], np.array([len(sorted_tickers)])))
    for start, stop in zip(starts, stops):
        out_sorted[start:stop] = transform(sorted_values[start:stop])

    out = np.empty_like(out_sorted)
    out[order] = out_sorted
    return out


# =============================================================================
# GP Node (Expression Tree)
# =============================================================================

@dataclass
class GPNode:
    """Node in genetic programming expression tree."""
    
    operator: str
    children: List["GPNode"] = field(default_factory=list)
    value: Optional[str] = None  # Terminal node (feature name)
    
    def depth(self) -> int:
        """Calculate tree depth."""
        if not self.children:
            return 1
        return 1 + max(child.depth() for child in self.children)
    
    def size(self) -> int:
        """Calculate tree size (node count)."""
        if not self.children:
            return 1
        return 1 + sum(child.size() for child in self.children)
    
    def to_string(self) -> str:
        """Convert tree to readable expression string."""
        if not self.children:
            return self.value or "0"
        
        if len(self.children) == 1:
            return f"{self.operator}({self.children[0].to_string()})"
        elif len(self.children) == 2:
            return f"({self.children[0].to_string()} {self.operator} {self.children[1].to_string()})"
        else:
            args = ", ".join(child.to_string() for child in self.children)
            return f"{self.operator}({args})"
    
    def copy(self) -> "GPNode":
        """Deep copy of tree."""
        return GPNode(
            operator=self.operator,
            children=[child.copy() for child in self.children],
            value=self.value
        )
    
    def get_random_subtree(self) -> "GPNode":
        """Get random subtree for crossover."""
        nodes = self._collect_nodes()
        return random.choice(nodes)
    
    def _collect_nodes(self) -> List["GPNode"]:
        """Collect all nodes in tree."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child._collect_nodes())
        return nodes
    
    def replace_subtree(self, old: "GPNode", new: "GPNode") -> None:
        """Replace subtree (for crossover)."""
        for i, child in enumerate(self.children):
            if child is old:
                self.children[i] = new.copy()
                return
            child.replace_subtree(old, new)


# =============================================================================
# GP Configuration
# =============================================================================

@dataclass
class GPConfig:
    """Configuration for genetic programming engine."""
    
    population_size: int = 500
    generations: int = 50
    max_depth: int = 5
    tournament_size: int = 5
    crossover_rate: float = 0.7
    mutation_rate: float = 0.2
    elitism_count: int = 1
    hall_of_fame_size: int = 20
    diversity_threshold: float = 0.7
    min_observations: int = 1000
    
    # Operator probabilities
    terminal_prob: float = 0.3
    unary_ops: List[str] = field(default_factory=lambda: ['abs', 'log', 'sqrt', 'rank', 'neg', 'sigmoid', 'cs_rank', 'cs_zscore'])
    binary_ops: List[str] = field(default_factory=lambda: ['+', '-', '*', '/', 'max', 'min'])
    ts_ops: List[str] = field(default_factory=lambda: ['ts_std', 'ts_mean', 'ts_rank', 'ts_max', 'ts_min', 'ts_delay', 'decay_linear'])
    ts_windows: List[int] = field(default_factory=lambda: [5, 10, 20])
    use_icir: bool = False
    neutralize_size_sector: bool = False
    use_time_fold_ir: bool = False
    time_folds: int = 3
    time_folds_fast_mode: bool = False
    fold_ir_std_floor: float = 0.01
    icir_window: int = 20
    
    # Multi-target fitness (Phase 2.2)
    # Forward return horizons (in bars) used for combined IC fitness.
    # When more than one horizon is provided, evaluate() expects
    # features['target_h{N}'] for each N and computes a weighted IC.
    multi_target_horizons: List[int] = field(default_factory=lambda: [5])
    multi_target_weights: List[float] = field(default_factory=lambda: [1.0])

    # Option D: Orthogonalization penalty with configurable baseline set
    # Ensures evolved alphas are orthogonal (uncorrelated) to existing baseline signals.
    # ortho_baseline_set maps signal_name -> np.ndarray of baseline alpha values.
    # When non-empty, each candidate alpha is penalized proportionally to its
    # maximum absolute Spearman correlation against any baseline signal.
    ortho_baseline_set: Optional[Dict[str, np.ndarray]] = None
    ortho_penalty_weight: float = 0.05          # max penalty magnitude
    ortho_correlation_threshold: float = 0.5     # |corr| above which penalty kicks in
    turnover_penalty_weight: float = 0.0025
    tree_size_penalty_weight: float = 0.00025
    early_stopping_rounds: int = 10
    tournament_diversity_weight: float = 0.01
    use_batch_neutralization: bool = True

    # Parallel evaluation (Phase 2.4)
    # n_jobs: number of parallel threads for population evaluation.
    # -1 = use all CPUs, 1 = sequential fallback.
    n_jobs: int = -1
    random_seed: Optional[int] = None
    use_fast_penalties: bool = True


# =============================================================================
# GP Individual
# =============================================================================

@dataclass
class GPIndividual:
    """Individual in genetic programming population."""

    # Class-level ICIR fast-path telemetry (unannotated -> not dataclass fields).
    # Shared across all individuals so the owning GeneticEngine can aggregate
    # hits across a population evaluated in the default 'threads' joblib backend
    # or the serial (n_jobs=1) path. See GeneticEngine.get_icir_stats().
    fast_path_hits = 0
    fallback_hits = 0

    tree: GPNode
    fitness: float = -np.inf
    ic_score: float = 0.0
    complexity_penalty: float = 0.0
    diversity_penalty: float = 0.0
    transaction_cost_penalty: float = 0.0
    orthogonalization_penalty: float = 0.0
    turnover_rate: float = 0.0
    _alpha_cache: Dict[int, float] = field(default_factory=dict, repr=False)
    
    def evaluate(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
        hall_of_fame: List["GPIndividual"],
        config: GPConfig
    ) -> None:
        """Evaluate fitness of individual."""
        try:
            prepared = self._prepare_alpha_series(features)
            if prepared is None:
                _set_rejected_fitness(self)
                logger.debug("Rejected constant alpha")
                return
            alpha_series, valid_fraction = prepared
            self._score_alpha_series(
                alpha_series,
                valid_fraction,
                features,
                target,
                hall_of_fame,
                config,
            )
        except Exception as e:
            logger.debug(f"Fitness evaluation failed: {e}")
            _set_rejected_fitness(self)

    def _prepare_alpha_series(
        self,
        features: Dict[str, np.ndarray],
    ) -> Optional[Tuple[np.ndarray, float]]:
        alpha_series = self._execute_tree(self.tree, features)
        valid_fraction = float(np.mean(np.isfinite(alpha_series)))
        if np.std(alpha_series) < 1e-6:
            return None

        lower = np.nanpercentile(alpha_series, 1)
        upper = np.nanpercentile(alpha_series, 99)
        alpha_series = np.clip(alpha_series, lower, upper)
        alpha_series = (alpha_series - np.nanmean(alpha_series)) / (np.nanstd(alpha_series) + 1e-9)
        alpha_series = np.nan_to_num(alpha_series, nan=0.0, posinf=0.0, neginf=0.0)
        return alpha_series, valid_fraction

    def _score_alpha_series(
        self,
        alpha_series: np.ndarray,
        valid_fraction: float,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
        hall_of_fame: List["GPIndividual"],
        config: GPConfig,
        *,
        neutralized_alpha_series: Optional[np.ndarray] = None,
    ) -> None:
        try:
            ic_alpha_series = alpha_series if neutralized_alpha_series is None else neutralized_alpha_series

            if getattr(config, 'use_fast_penalties', True):
                valid_mask = _evaluation_mask(ic_alpha_series, target, features)
                n_valid = int(np.count_nonzero(valid_mask))
            else:
                n_valid = int(np.count_nonzero(_evaluation_mask(ic_alpha_series, target, features)))

            # Observation threshold
            if n_valid < config.min_observations:
                _set_rejected_fitness(self)
                return

            # Calculate IC (Spearman) — multi-target aware
            ic = self._compute_combined_ic(
                ic_alpha_series,
                target,
                features,
                config,
                pre_neutralized=neutralized_alpha_series is not None,
            )
            if np.isnan(ic):
                ic = 0.0

            # Phase 6 fix: signed IC fitness. abs(ic) used to reward both
            # +alpha and -alpha equally, polluting the Hall of Fame with
            # sign-flipped trees. With signed fitness GP only optimizes
            # for IC > 0; users who want a short-only strategy can wrap
            # the signal in a unary minus operator instead.
            # Coverage penalty: scale IC by the fraction of non-NaN alpha
            # values so signals valid on only a sliver of the sample are
            # discounted proportionally.
            self.ic_score = float(ic) * valid_fraction
            
            # Turnover calculation
            alpha_sign = np.sign(alpha_series)
            signal_changes = np.sum(np.abs(np.diff(alpha_sign)) > 0)
            if len(alpha_series) > 1:
                self.turnover_rate = signal_changes / len(alpha_series)
                self.transaction_cost_penalty = config.turnover_penalty_weight * self.turnover_rate
            
            # Progressive complexity penalty: depth + node count parsimony.
            depth = self.tree.depth()
            if depth <= 2:
                self.complexity_penalty = 0.002 * depth
            elif depth <= 4:
                self.complexity_penalty = 0.003 * depth
            else:
                self.complexity_penalty = 0.008 * depth
            self.complexity_penalty += config.tree_size_penalty_weight * self.tree.size()
            
            # Diversity penalty
            self.diversity_penalty = 0.0
            self._alpha_cache = {}
            if hall_of_fame:
                hof_alphas = features.get(HOF_ALPHA_CACHE_KEY)
                if hof_alphas is None:
                    hof_alphas = []
                    for hof_individual in hall_of_fame:
                        try:
                            hof_alpha = self._execute_tree(hof_individual.tree, features)
                            hof_alphas.append(np.nan_to_num(hof_alpha, nan=0.0, posinf=0.0, neginf=0.0))
                        except Exception:
                            hof_alphas.append(None)
                generation_alpha_cache = features.get(ALPHA_CACHE_KEY)
                if generation_alpha_cache is not None:
                    candidate_cache = generation_alpha_cache.setdefault(id(self), {})
                else:
                    candidate_cache = self._alpha_cache
                for hof_individual, hof_alpha in zip(hall_of_fame, hof_alphas):
                    if hof_alpha is None:
                        continue
                    try:
                        hof_cache_key = id(hof_individual)
                        corr = candidate_cache.get(hof_cache_key)
                        if corr is None:
                            corr = _spearman_corr_via_corrcoef(alpha_series, hof_alpha)
                            candidate_cache[hof_cache_key] = float(corr) if not np.isnan(corr) else np.nan
                        if not np.isnan(corr) and abs(corr) > config.diversity_threshold:
                            self.diversity_penalty = max(self.diversity_penalty, 0.02)
                    except Exception:
                        continue
            
            # Option D: Orthogonalization penalty against configurable baseline set
            # Penalizes alphas whose Spearman |correlation| with any baseline signal
            # exceeds the configured threshold.  Penalty scales linearly from 0 at
            # threshold to ortho_penalty_weight at |corr| == 1.0.
            self.orthogonalization_penalty = 0.0
            baseline_set = getattr(config, 'ortho_baseline_set', None) or {}
            if baseline_set:
                threshold = getattr(config, 'ortho_correlation_threshold', 0.5)
                max_abs_corr = 0.0
                ortho_ranks = features.get(ORTHO_RANKS_CACHE_KEY)
                if getattr(config, 'use_fast_penalties', True) and ortho_ranks:
                    alpha_rank_cache: Dict[int, np.ndarray] = {}
                    for bl_name, baseline_ranks in ortho_ranks.items():
                        bl_signal = baseline_set.get(bl_name)
                        if bl_signal is None or len(bl_signal) == 0:
                            continue
                        span = min(len(alpha_series), len(baseline_ranks))
                        if span < 100:
                            continue
                        try:
                            alpha_ranks = alpha_rank_cache.get(span)
                            if alpha_ranks is None:
                                alpha_ranks = rankdata(alpha_series[:span])
                                alpha_rank_cache[span] = alpha_ranks
                            bl_corr = _pearson_corr(alpha_ranks, baseline_ranks[:span])
                            if not np.isnan(bl_corr):
                                max_abs_corr = max(max_abs_corr, abs(bl_corr))
                        except Exception:
                            continue
                else:
                    for _bl_name, bl_signal in baseline_set.items():
                        if bl_signal is None or len(bl_signal) == 0:
                            continue
                        try:
                            span = min(len(alpha_series), len(bl_signal))
                            if span < 100:
                                continue
                            bl_corr = _spearman_corr_via_corrcoef(alpha_series[:span], bl_signal[:span])
                            if not np.isnan(bl_corr):
                                max_abs_corr = max(max_abs_corr, abs(bl_corr))
                        except Exception:
                            continue
                # Linear penalty: 0 when max_abs_corr <= threshold,
                # scales to ortho_penalty_weight when max_abs_corr == 1.0
                if max_abs_corr > threshold and threshold < 1.0:
                    penalty_frac = (max_abs_corr - threshold) / (1.0 - threshold)
                    self.orthogonalization_penalty = (
                        getattr(config, 'ortho_penalty_weight', 0.05) * penalty_frac
                    )
            
            # Final fitness
            self.fitness = (
                self.ic_score
                - self.complexity_penalty
                - self.diversity_penalty
                - self.transaction_cost_penalty
                - self.orthogonalization_penalty
            )
        except Exception as e:
            logger.debug(f"Fitness evaluation failed: {e}")
            _set_rejected_fitness(self)
    
    def _compute_combined_ic(
        self,
        alpha_series: np.ndarray,
        target: np.ndarray,
        features: Dict[str, np.ndarray],
        config: GPConfig,
        *,
        pre_neutralized: bool = False,
    ) -> float:
        """Compute IC, supporting multi-target horizons (Phase 2.2).
        
        - Single-horizon (default): Spearman IC vs `target` (back-compat).
        - Multi-horizon: weighted average of Spearman IC across each
          features[f'target_h{N}'] for N in config.multi_target_horizons.
          Falls back to `target` when a horizon key is missing.
        """
        horizons = list(getattr(config, 'multi_target_horizons', []) or [])
        weights = list(getattr(config, 'multi_target_weights', []) or [])
        
        def _compute_spearman_ic(
            alpha_values: np.ndarray,
            target_values: np.ndarray,
            eval_features: Dict[str, np.ndarray],
        ) -> float:
            valid = _evaluation_mask(alpha_values, target_values, eval_features)
            if np.count_nonzero(valid) < 2:
                return 0.0
            ic_value = _spearman_corr_via_corrcoef(alpha_values[valid], target_values[valid])
            return ic_value if not np.isnan(ic_value) else 0.0

        if getattr(config, 'neutralize_size_sector', False):
            if not pre_neutralized:
                alpha_series = _neutralize_cross_section(
                    alpha_series,
                    features.get('__log_market_cap__'),
                    features.get('__sector__'),
                    features.get('__date__'),
                    neutralization_cache=features.get(NEUTRALIZATION_CACHE_KEY),
                )
            target = _neutralize_cross_section(
                target,
                features.get('__log_market_cap__'),
                features.get('__sector__'),
                features.get('__date__'),
                neutralization_cache=features.get(NEUTRALIZATION_CACHE_KEY),
            )

        def _compute_icir_loop(date_chunks: Tuple[np.ndarray, ...]) -> float:
            chunk_ics: List[float] = []
            for chunk_indices in date_chunks:
                alpha_chunk = alpha_series[chunk_indices]
                target_chunk = target[chunk_indices]
                chunk_features = {}
                for key, value in features.items():
                    try:
                        value_arr = np.asarray(value)
                    except ValueError:
                        continue
                    if value_arr.ndim > 0 and len(value_arr) == len(alpha_series):
                        chunk_features[key] = value_arr[chunk_indices]
                valid = _evaluation_mask(alpha_chunk, target_chunk, chunk_features)
                if np.count_nonzero(valid) < 2:
                    continue
                ic_value = _spearman_corr_via_corrcoef(alpha_chunk[valid], target_chunk[valid])
                if not np.isnan(ic_value):
                    chunk_ics.append(ic_value)

            if not chunk_ics:
                return _compute_spearman_ic(alpha_series, target, features)

            ic_std = float(np.std(chunk_ics))
            if ic_std < 1e-9:
                return float(np.mean(chunk_ics))
            return float(np.mean(chunk_ics) / ic_std)

        if getattr(config, 'use_time_fold_ir', False):
            if len(horizons) <= 1:
                return _compute_time_fold_ir(
                    alpha_series,
                    target,
                    features,
                    config,
                    pre_neutralized=True,
                )

            if len(weights) != len(horizons):
                weights = [1.0] * len(horizons)
            weighted_ir = 0.0
            used_weight = 0.0
            for horizon, weight in zip(horizons, weights):
                target_h = features.get(f'target_h{horizon}', target)
                ir_h = _compute_time_fold_ir(
                    alpha_series,
                    np.asarray(target_h, dtype=np.float64),
                    features,
                    config,
                    pre_neutralized=True,
                )
                if np.isnan(ir_h):
                    continue
                weighted_ir += float(weight) * float(ir_h)
                used_weight += float(weight)
            return 0.0 if used_weight <= 0 else weighted_ir / used_weight

        # Single-target back-compat path
        if len(horizons) <= 1:
            if getattr(config, 'use_icir', False) and '__date__' in features:
                date_chunk_cache = features.get(DATE_CHUNK_CACHE_KEY)
                if date_chunk_cache:
                    flat_idx = date_chunk_cache['flat_idx']
                    if flat_idx.size:
                        alpha_flat = alpha_series[flat_idx]
                        if (
                            date_chunk_cache['target_all_finite']
                            and np.all(np.isfinite(alpha_flat))
                        ):
                            GPIndividual.fast_path_hits += 1
                            chunk_id = date_chunk_cache['chunk_id']
                            seg_starts = date_chunk_cache['seg_starts']
                            # Stable two-key sort: chunk_id groups, alpha orders
                            # within group. Average ranks preserve ties so this
                            # matches scipy.spearmanr's tie handling exactly.
                            order_a = np.lexsort((alpha_flat, chunk_id))
                            a_rank = _chunked_average_ranks(
                                order_a, alpha_flat, chunk_id,
                                date_chunk_cache['rank_values'],
                            )
                            t_rank = date_chunk_cache['t_rank']
                            t_sum = date_chunk_cache['t_sum']
                            t_var_num = date_chunk_cache['t_var_num']
                            nf = date_chunk_cache['chunk_sizes'].astype(np.float64)
                            a_sum = np.add.reduceat(a_rank, seg_starts)
                            a_ss = np.add.reduceat(a_rank * a_rank, seg_starts)
                            cross = np.add.reduceat(a_rank * t_rank, seg_starts)
                            a_var_num = a_ss - (a_sum * a_sum) / nf
                            cov_num = cross - (a_sum * t_sum) / nf
                            # Spearman IC per chunk == Pearson on average ranks.
                            # Zero-variance (constant) chunks are reported as NaN
                            # by scipy.spearmanr and skipped by the loop, so we
                            # mask them here before aggregating.
                            valid_chunk = (a_var_num > 1e-12) & (t_var_num > 1e-12)
                            denom = np.sqrt(np.maximum(a_var_num * t_var_num, 0.0))
                            chunk_ics = np.divide(
                                cov_num, denom,
                                out=np.full(cov_num.shape, np.nan),
                                where=valid_chunk,
                            )
                            chunk_ics = chunk_ics[np.isfinite(chunk_ics)]
                            if chunk_ics.size == 0:
                                return _compute_spearman_ic(alpha_series, target, features)
                            ic_std = float(np.std(chunk_ics))
                            if ic_std < 1e-9:
                                return float(np.mean(chunk_ics))
                            return float(np.mean(chunk_ics) / ic_std)

                        GPIndividual.fallback_hits += 1
                        return _compute_icir_loop(date_chunk_cache['date_chunks'])

                valid = _evaluation_mask(alpha_series, target, features) & pd.notna(features['__date__'])
                if np.count_nonzero(valid) < 2:
                    return 0.0

                chunk_ics: List[float] = []
                valid_alpha = alpha_series[valid]
                valid_target = target[valid]
                valid_dates = features['__date__'][valid]
                unique_dates = pd.unique(valid_dates)
                window = max(1, int(getattr(config, 'icir_window', 20)))
                for start in range(0, len(unique_dates), window):
                    chunk_dates = unique_dates[start:start + window]
                    chunk_mask = np.isin(valid_dates, chunk_dates)
                    if np.count_nonzero(chunk_mask) < 2:
                        continue
                    ic_value = _spearman_corr_via_corrcoef(
                        valid_alpha[chunk_mask], valid_target[chunk_mask]
                    )
                    if not np.isnan(ic_value):
                        chunk_ics.append(ic_value)

                if not chunk_ics:
                    return _compute_spearman_ic(alpha_series, target, features)

                ic_std = float(np.std(chunk_ics))
                if ic_std < 1e-9:
                    return float(np.mean(chunk_ics))
                return float(np.mean(chunk_ics) / ic_std)

            return _compute_spearman_ic(alpha_series, target, features)
        
        # Normalize weights (default to equal weights if mismatch)
        if len(weights) != len(horizons):
            weights = [1.0] * len(horizons)
        weight_sum = float(sum(weights))
        if weight_sum <= 0:
            return 0.0
        
        weighted_ic = 0.0
        used_weight = 0.0
        for horizon, weight in zip(horizons, weights):
            key = f'target_h{horizon}'
            target_h = features.get(key, target)
            valid = _evaluation_mask(alpha_series, target_h, features)
            if np.count_nonzero(valid) < 2:
                continue
            ic_h = _spearman_corr_via_corrcoef(alpha_series[valid], target_h[valid])
            if np.isnan(ic_h):
                continue
            weighted_ic += float(weight) * float(ic_h)
            used_weight += float(weight)
        
        if used_weight <= 0:
            return 0.0
        return weighted_ic / used_weight
    
    def _execute_tree(self, node: GPNode, features: Dict[str, np.ndarray]) -> np.ndarray:
        """Execute expression tree to compute alpha values."""
        if not node.children:
            if node.value in features:
                return features[node.value].copy()
            else:
                try:
                    val = float(node.value)
                    return np.full(len(next(iter(features.values()))), val)
                except ValueError:
                    return np.zeros(len(next(iter(features.values()))))
        
        if len(node.children) == 1:
            child_val = self._execute_tree(node.children[0], features)
            if node.operator == 'abs':
                return np.abs(child_val)
            elif node.operator == 'log':
                return _signed_log(child_val)
            elif node.operator == 'sqrt':
                return _protected_sqrt(child_val)
            elif node.operator == 'exp':
                return _protected_exp(child_val)
            elif node.operator == 'sigmoid':
                return _sigmoid(child_val)
            elif node.operator == 'rank':
                return _rank_transform(child_val)
            elif node.operator == 'cs_rank':
                return _cs_rank(child_val)
            elif node.operator == 'cs_zscore':
                return _cs_zscore(child_val)
            elif node.operator == 'neg':
                return -child_val
            return child_val
        
        elif len(node.children) == 2 and node.operator in ['ts_std', 'ts_mean', 'ts_rank', 'ts_max', 'ts_min', 'ts_delay', 'decay_linear']:
            child_val = self._execute_tree(node.children[0], features)
            window = int(self._execute_tree(node.children[1], features)[0])
            if node.operator == 'ts_delay':
                window = max(1, min(window, 10))
            else:
                window = max(2, min(window, 60))
            tickers = features.get('__ticker__')
            dates = features.get('__date__')
            
            if node.operator == 'ts_std':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_std(x, window))
            elif node.operator == 'ts_mean':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_mean(x, window))
            elif node.operator == 'ts_rank':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_rank(x, window))
            elif node.operator == 'ts_max':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_max(x, window))
            elif node.operator == 'ts_min':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_min(x, window))
            elif node.operator == 'ts_delay':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _ts_delay(x, window))
            elif node.operator == 'decay_linear':
                return _apply_grouped_ts_transform(child_val, tickers, dates, lambda x: _decay_linear(x, window))

        elif len(node.children) == 2:
            left_val = self._execute_tree(node.children[0], features)
            right_val = self._execute_tree(node.children[1], features)
            
            if node.operator == '+':
                return left_val + right_val
            elif node.operator == '-':
                return left_val - right_val
            elif node.operator == '*':
                return left_val * right_val
            elif node.operator == '/':
                return _protected_div(left_val, right_val)
            elif node.operator == 'max':
                return np.maximum(left_val, right_val)
            elif node.operator == 'min':
                return np.minimum(left_val, right_val)
            return left_val
        
        return np.zeros(len(next(iter(features.values()))))


# =============================================================================
# Genetic Programming Engine
# =============================================================================

class GeneticEngine:
    """Genetic Programming Engine for alpha discovery."""
    
    def __init__(self, config: Optional[GPConfig] = None):
        self.config = config or GPConfig()
        self.population: List[GPIndividual] = []
        self.hall_of_fame: List[GPIndividual] = []
        self.history: List[Dict[str, float]] = []
        self.feature_names: List[str] = []
        self._date_chunk_cache: Tuple[Optional[int], Optional[Dict[str, Any]]] = (None, None)
        self._fold_structure_cache: Tuple[Optional[Tuple[int, int]], Optional[Tuple[Tuple[np.ndarray, np.ndarray], ...]]] = (None, None)
        # Reset ICIR telemetry so get_icir_stats() reflects this engine's runs.
        # (Counters live on GPIndividual, whose _compute_combined_ic increments
        # them; they are process-global, so constructing a new engine resets them.)
        GPIndividual.fast_path_hits = 0
        GPIndividual.fallback_hits = 0
        self._ortho_ranks = self._precompute_ortho_ranks()

    def _precompute_ortho_ranks(self) -> Dict[str, np.ndarray]:
        baseline_set = getattr(self.config, 'ortho_baseline_set', None) or {}
        precomputed: Dict[str, np.ndarray] = {}
        for name, signal in baseline_set.items():
            if signal is None or len(signal) == 0:
                continue
            signal_arr = np.asarray(signal, dtype=np.float64)
            if not np.all(np.isfinite(signal_arr)):
                raise AssertionError(f"ortho baseline '{name}' must be finite for fast ranks")
            precomputed[name] = rankdata(signal_arr)
        return precomputed

    def _build_hof_alpha_cache(
        self,
        hall_of_fame: List[GPIndividual],
        features: Dict[str, np.ndarray],
    ) -> List[Optional[np.ndarray]]:
        cache: List[Optional[np.ndarray]] = []
        for hof_individual in hall_of_fame:
            try:
                hof_alpha = hof_individual._execute_tree(hof_individual.tree, features)
                cache.append(np.nan_to_num(hof_alpha, nan=0.0, posinf=0.0, neginf=0.0))
            except Exception:
                cache.append(None)
        return cache

    def get_icir_stats(self) -> Dict[str, Any]:
        """Return ICIR fast-path telemetry.

        - fast_path_hits: vectorized composite-key argsort evaluations.
        - fallback_hits: per-chunk spearmanr loop evaluations.
        - hit_rate: fraction of ICIR evaluations that took the fast path.
        """
        fast = GPIndividual.fast_path_hits
        fallback = GPIndividual.fallback_hits
        total = fast + fallback
        hit_rate = fast / total if total else 0.0
        return {
            'fast_path_hits': fast,
            'fallback_hits': fallback,
            'hit_rate': hit_rate,
        }

    def _precompute_date_chunks(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
    ) -> Dict[str, Any]:
        """Cache ICIR chunk metadata once per feature slice."""
        date_values = features.get('__date__')
        if date_values is None:
            empty_cache = {
                'date_chunks': tuple(),
                'flat_idx': np.array([], dtype=np.int64),
                'seg_starts': np.array([], dtype=np.int64),
                'chunk_sizes': np.array([], dtype=np.int64),
                'chunk_id': np.array([], dtype=np.int64),
                'rank_values': np.array([], dtype=np.float64),
                't_rank': np.array([], dtype=np.float64),
                't_sum': np.array([], dtype=np.float64),
                't_var_num': np.array([], dtype=np.float64),
                'target_all_finite': False,
            }
            self._date_chunk_cache = (None, empty_cache)
            return empty_cache

        cache_key = id(date_values)
        cached_key, cached_chunks = self._date_chunk_cache
        if cached_key == cache_key:
            return cached_chunks

        valid_date_mask = pd.notna(date_values)
        valid_indices = np.flatnonzero(valid_date_mask)
        if valid_indices.size == 0:
            empty_cache = {
                'date_chunks': tuple(),
                'flat_idx': np.array([], dtype=np.int64),
                'seg_starts': np.array([], dtype=np.int64),
                'chunk_sizes': np.array([], dtype=np.int64),
                'chunk_id': np.array([], dtype=np.int64),
                'rank_values': np.array([], dtype=np.float64),
                't_rank': np.array([], dtype=np.float64),
                't_sum': np.array([], dtype=np.float64),
                't_var_num': np.array([], dtype=np.float64),
                'target_all_finite': False,
            }
            self._date_chunk_cache = (cache_key, empty_cache)
            return empty_cache

        unique_dates = pd.unique(date_values[valid_date_mask])
        window = max(1, int(getattr(self.config, 'icir_window', 20)))
        chunks: List[np.ndarray] = []
        for start in range(0, len(unique_dates), window):
            chunk_dates = unique_dates[start:start + window]
            chunk_mask = np.isin(date_values[valid_date_mask], chunk_dates)
            chunk_indices = valid_indices[chunk_mask]
            if chunk_indices.size >= 2:
                chunks.append(chunk_indices)

        date_chunks = tuple(chunks)
        if not date_chunks:
            empty_cache = {
                'date_chunks': tuple(),
                'flat_idx': np.array([], dtype=np.int64),
                'seg_starts': np.array([], dtype=np.int64),
                'chunk_sizes': np.array([], dtype=np.int64),
                'chunk_id': np.array([], dtype=np.int64),
                'rank_values': np.array([], dtype=np.float64),
                't_rank': np.array([], dtype=np.float64),
                't_sum': np.array([], dtype=np.float64),
                't_var_num': np.array([], dtype=np.float64),
                'target_all_finite': False,
            }
            self._date_chunk_cache = (cache_key, empty_cache)
            return empty_cache

        chunk_sizes = np.array([chunk.size for chunk in date_chunks], dtype=np.int64)
        flat_idx = np.concatenate(date_chunks)
        seg_starts = np.concatenate(([0], np.cumsum(chunk_sizes[:-1], dtype=np.int64)))
        chunk_id = np.repeat(np.arange(len(date_chunks), dtype=np.int64), chunk_sizes)
        rank_values = np.arange(1, flat_idx.size + 1, dtype=np.float64) - np.repeat(seg_starts, chunk_sizes)
        target_flat = target[flat_idx]
        target_all_finite = bool(np.all(np.isfinite(target_flat)))

        if target_all_finite:
            order_t = np.lexsort((target_flat, chunk_id))
            t_rank = _chunked_average_ranks(order_t, target_flat, chunk_id, rank_values)
            nf = chunk_sizes.astype(np.float64)
            t_sum = np.add.reduceat(t_rank, seg_starts)
            t_ss = np.add.reduceat(t_rank * t_rank, seg_starts)
            t_var_num = t_ss - (t_sum * t_sum) / nf
        else:
            t_rank = np.array([], dtype=np.float64)
            t_sum = np.array([], dtype=np.float64)
            t_var_num = np.array([], dtype=np.float64)

        cached_chunks = {
            'date_chunks': date_chunks,
            'flat_idx': flat_idx,
            'seg_starts': seg_starts,
            'chunk_sizes': chunk_sizes,
            'chunk_id': chunk_id,
            'rank_values': rank_values,
            't_rank': t_rank,
            't_sum': t_sum,
            't_var_num': t_var_num,
            'target_all_finite': target_all_finite,
        }
        self._date_chunk_cache = (cache_key, cached_chunks)
        return cached_chunks

    def _get_cached_fold_structure(
        self,
        date_values: np.ndarray,
    ) -> Tuple[Tuple[np.ndarray, np.ndarray], ...]:
        fold_count = 2 if getattr(self.config, 'time_folds_fast_mode', False) else int(self.config.time_folds)
        cache_key = (id(date_values), fold_count)
        cached_key, cached_structure = self._fold_structure_cache
        if cached_key == cache_key and cached_structure is not None:
            return cached_structure
        fold_structure = _build_time_fold_structure(np.asarray(date_values), fold_count)
        self._fold_structure_cache = (cache_key, fold_structure)
        return fold_structure
    
    def generate_random_tree(self, depth: int = 0) -> GPNode:
        """Generate random expression tree."""
        if depth >= self.config.max_depth or (depth > 0 and random.random() < self.config.terminal_prob):
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        if depth >= self.config.max_depth - 1:
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        op_types = ['binary']
        if self.config.unary_ops:
            op_types.append('unary')
        if self.config.ts_ops:
            op_types.append('ts')
        op_type = random.choice(op_types)
        
        if op_type == 'unary':
            op = random.choice(self.config.unary_ops)
            child = self.generate_random_tree(depth + 1)
            return GPNode(operator=op, children=[child])
        elif op_type == 'binary':
            op = random.choice(self.config.binary_ops)
            left = self.generate_random_tree(depth + 1)
            right = self.generate_random_tree(depth + 1)
            return GPNode(operator=op, children=[left, right])
        else:
            op = random.choice(self.config.ts_ops)
            child = self.generate_random_tree(depth + 1)
            window = GPNode(operator='terminal', value=str(random.choice(self.config.ts_windows)))
            return GPNode(operator=op, children=[child, window])
    
    def initialize_population(self) -> None:
        """Initialize random population."""
        self.population = []
        for _ in range(self.config.population_size):
            tree = self.generate_random_tree()
            self.population.append(GPIndividual(tree=tree))
    
    def tournament_selection(self) -> GPIndividual:
        """Select individual via tournament selection."""
        tournament = random.sample(self.population, min(self.config.tournament_size, len(self.population)))
        seen: set[str] = set()

        def score(ind: GPIndividual) -> float:
            expr = ind.tree.to_string()
            duplicate_penalty = self.config.tournament_diversity_weight if expr in seen else 0.0
            seen.add(expr)
            return ind.fitness - duplicate_penalty

        return max(tournament, key=score)
    
    def crossover(self, parent1: GPIndividual, parent2: GPIndividual) -> GPIndividual:
        """Crossover two individuals."""
        if random.random() > self.config.crossover_rate:
            return GPIndividual(tree=parent1.tree.copy())
        
        tree1 = parent1.tree.copy()
        tree2 = parent2.tree.copy()
        subtree1 = tree1.get_random_subtree()
        subtree2 = tree2.get_random_subtree()
        tree1.replace_subtree(subtree1, subtree2)
        return GPIndividual(tree=tree1)
    
    def mutate(self, individual: GPIndividual) -> GPIndividual:
        """Mutate individual."""
        if random.random() > self.config.mutation_rate:
            return GPIndividual(tree=individual.tree.copy())
        
        tree = individual.tree.copy()
        subtree = tree.get_random_subtree()
        new_subtree = self.generate_random_tree(depth=0)
        tree.replace_subtree(subtree, new_subtree)
        return GPIndividual(tree=tree)

    def _next_generation(self) -> None:
        """Breed offspring for the next generation."""
        next_population = [
            GPIndividual(tree=ind.tree.copy())
            for ind in self.population[:self.config.elitism_count]
        ]
        while len(next_population) < self.config.population_size:
            parent1 = self.tournament_selection()
            parent2 = self.tournament_selection()
            child = self.crossover(parent1, parent2)
            next_population.append(self.mutate(child))
        self.population = next_population[:self.config.population_size]
    
    def update_hall_of_fame(self) -> None:
        """Update Hall of Fame."""
        candidates = sorted(self.population, key=lambda ind: ind.fitness, reverse=True)
        self.hall_of_fame = []
        seen_expressions: set[str] = set()
        for candidate in candidates:
            if len(self.hall_of_fame) >= self.config.hall_of_fame_size:
                break
            expression = candidate.tree.to_string()
            if expression in seen_expressions:
                continue
            # Phase 6 fix: with signed-IC fitness, individuals with negative
            # IC have fitness < 0 (penalties only subtract). Skip them so
            # the HoF never holds anti-correlated alphas.
            if candidate.fitness <= 0:
                continue
            if candidate.diversity_penalty <= 0 or len(self.hall_of_fame) == 0:
                self.hall_of_fame.append(candidate)
                seen_expressions.add(expression)
    
    def evolve(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray
    ) -> List[GPIndividual]:
        if self.config.random_seed is not None:
            np.random.seed(self.config.random_seed)
            random.seed(self.config.random_seed)
            
        self.feature_names = [k for k in features.keys() if not k.startswith('target') and not k.startswith('__')]
        
        logger.info(f"Starting GP evolution: pop={self.config.population_size}, gen={self.config.generations}")
        
        # Log Option D orthogonalization baseline configuration
        ortho_set = getattr(self.config, 'ortho_baseline_set', None) or {}
        if ortho_set:
            logger.info(
                f"Option D orthogonalization: {len(ortho_set)} baseline signal(s) configured, "
                f"weight={self.config.ortho_penalty_weight}, "
                f"threshold={self.config.ortho_correlation_threshold}"
            )
        else:
            logger.info("Option D orthogonalization: disabled (no baseline set)")
        
        self.initialize_population()
        
        t_start = time.monotonic()
        best_fitness_seen = -np.inf
        stagnant_generations = 0
        for generation in range(self.config.generations):
            # Time-fold IR requires chronological full-sample date structure.
            if len(target) > 100000 and not self.config.use_time_fold_ir:
                if self.config.random_seed is not None:
                    # Deterministically vary indices per generation using seeded generator
                    rng = np.random.RandomState(self.config.random_seed + generation)
                    sample_idx = rng.choice(len(target), size=100000, replace=False)
                else:
                    sample_idx = np.random.choice(len(target), size=100000, replace=False)
                gen_features = {k: v[sample_idx] for k, v in features.items()}
                gen_target = target[sample_idx]
            else:
                gen_features = features
                gen_target = target

            if self.config.use_fast_penalties and '__date__' in gen_features:
                if gen_features is features:
                    gen_features = dict(gen_features)
                gen_features[FOLD_STRUCTURE_CACHE_KEY] = self._get_cached_fold_structure(gen_features['__date__'])

            if self.config.use_fast_penalties and self.hall_of_fame:
                if gen_features is features:
                    gen_features = dict(gen_features)
                gen_features[HOF_ALPHA_CACHE_KEY] = self._build_hof_alpha_cache(self.hall_of_fame, gen_features)
                gen_features[ALPHA_CACHE_KEY] = {}

            if self.config.use_fast_penalties and self._ortho_ranks:
                if gen_features is features:
                    gen_features = dict(gen_features)
                gen_features[ORTHO_RANKS_CACHE_KEY] = self._ortho_ranks

            if self.config.use_icir and '__date__' in gen_features:
                gen_features = dict(gen_features)
                gen_features[DATE_CHUNK_CACHE_KEY] = self._precompute_date_chunks(gen_features, gen_target)
            if (
                self.config.neutralize_size_sector
                and '__date__' in gen_features
                and '__log_market_cap__' in gen_features
                and '__sector__' in gen_features
            ):
                if gen_features is features:
                    gen_features = dict(gen_features)
                gen_features[NEUTRALIZATION_CACHE_KEY] = _build_neutralization_cache(
                    np.asarray(gen_features.get('__log_market_cap__'), dtype=np.float64),
                    np.asarray(gen_features.get('__sector__')),
                    np.asarray(gen_features.get('__date__')),
                )

            if self.config.n_jobs == 1:
                if self._should_use_batch_neutralization(gen_features):
                    self._evaluate_population_with_batch_neutralization(gen_features, gen_target)
                else:
                    for individual in self.population:
                        individual.evaluate(gen_features, gen_target, self.hall_of_fame, self.config)
            else:
                if self._should_use_batch_neutralization(gen_features):
                    self._evaluate_population_with_batch_neutralization(gen_features, gen_target)
                else:
                    self.population = list(Parallel(
                        n_jobs=self.config.n_jobs, batch_size='auto', prefer='threads'
                    )(
                        delayed(_evaluate_individual)(
                            ind, gen_features, gen_target, self.hall_of_fame, self.config
                        )
                        for ind in self.population
                    ))
            
            self.population.sort(key=lambda ind: ind.fitness, reverse=True)
            self.update_hall_of_fame()
            
            best = self.population[0]
            self.history.append({
                'generation': generation,
                'best_fitness': best.fitness,
                'best_ic': best.ic_score,
                'best_tree_size': best.tree.size(),
            })
            
            logger.info(f"Gen {generation+1}: Fold_IR={best.ic_score:.4f}, Fitness={best.fitness:.4f}")
            
            # Progress metadata with timing and ETA
            elapsed = time.monotonic() - t_start
            gen_time = elapsed / (generation + 1)
            remaining = gen_time * (self.config.generations - generation - 1)
            self.history[-1]['elapsed_sec'] = round(elapsed, 2)
            self.history[-1]['gen_time_sec'] = round(gen_time, 3)
            self.history[-1]['eta_sec'] = round(remaining, 1)
            if (generation + 1) % max(1, self.config.generations // 5) == 0 or generation == 0:
                logger.info(
                    f"  Progress: {generation+1}/{self.config.generations} "
                    f"({100*(generation+1)/self.config.generations:.0f}%) "
                    f"elapsed={elapsed:.1f}s eta={remaining:.1f}s"
                )

            if best.fitness > best_fitness_seen + 1e-6:
                best_fitness_seen = best.fitness
                stagnant_generations = 0
            else:
                stagnant_generations += 1
            if (
                self.config.early_stopping_rounds > 0
                and stagnant_generations >= self.config.early_stopping_rounds
            ):
                gc.collect()
                logger.info(
                    f"Early stopping: no best-fitness improvement for "
                    f"{self.config.early_stopping_rounds} generations"
                )
                break
            if generation + 1 < self.config.generations:
                self._next_generation()
            gc.collect()

        return self.hall_of_fame

    def _should_use_batch_neutralization(self, features: Dict[str, np.ndarray]) -> bool:
        return bool(
            getattr(self.config, 'use_batch_neutralization', True)
            and self.config.neutralize_size_sector
            and '__date__' in features
            and '__log_market_cap__' in features
            and '__sector__' in features
            and NEUTRALIZATION_CACHE_KEY in features
        )

    def _evaluate_population_with_batch_neutralization(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
    ) -> None:
        if self.config.n_jobs == 1:
            prepared_population = [_prepare_individual_batch(ind, features) for ind in self.population]
        else:
            prepared_population = list(Parallel(
                n_jobs=self.config.n_jobs,
                batch_size='auto',
                prefer='threads',
            )(
                delayed(_prepare_individual_batch)(ind, features)
                for ind in self.population
            ))

        self.population = [ind for ind, _, _ in prepared_population]
        prepared_alpha_rows = [alpha for _, alpha, _ in prepared_population if alpha is not None]
        neutralized_rows: List[Optional[np.ndarray]] = [None] * len(prepared_population)
        if prepared_alpha_rows:
            alpha_matrix = np.column_stack(prepared_alpha_rows)
            neutralized_matrix = _batch_neutralize_cross_section(
                alpha_matrix,
                np.asarray(features['__date__']),
                features[NEUTRALIZATION_CACHE_KEY],
            )
            valid_col = 0
            for idx, (_, alpha, _) in enumerate(prepared_population):
                if alpha is None:
                    continue
                neutralized_rows[idx] = neutralized_matrix[:, valid_col]
                valid_col += 1

        if self.config.n_jobs == 1:
            self.population = [
                _score_prepared_individual(
                    idx,
                    prepared,
                    neutralized_rows,
                    features,
                    target,
                    self.hall_of_fame,
                    self.config,
                )
                for idx, prepared in enumerate(prepared_population)
            ]
        else:
            self.population = list(Parallel(
                n_jobs=self.config.n_jobs,
                batch_size='auto',
                prefer='threads',
            )(
                delayed(_score_prepared_individual)(
                    idx,
                    prepared,
                    neutralized_rows,
                    features,
                    target,
                    self.hall_of_fame,
                    self.config,
                )
                for idx, prepared in enumerate(prepared_population)
            ))
