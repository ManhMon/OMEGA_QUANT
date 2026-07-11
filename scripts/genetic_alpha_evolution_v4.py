"""Genetic Alpha Evolution V4 - advanced optimization wrapper over V3."""

from __future__ import annotations

import hashlib
import gc
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
    from numba import njit, prange
except ModuleNotFoundError:  # ponytail: perf ceiling until numba installed.
    def njit(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator

    def prange(*args):
        return range(*args)


ORIGINAL_GPINDIVIDUAL = ge.GPIndividual
ORIGINAL_GENETIC_ENGINE = ge.GeneticEngine
ORIGINAL_GPCONFIG = ge.GPConfig
ORIGINAL_COMPUTE_TIME_FOLD_IR = ge._compute_time_fold_ir
ORIGINAL_NEUTRALIZE_CROSS_SECTION = ge._neutralize_cross_section
ORIGINAL_BATCH_NEUTRALIZE_CROSS_SECTION = ge._batch_neutralize_cross_section
SESSION_REPORT_NAME = "l2_role16_gp_numba_jit_vm_implementation_20260705.md"
SUBTREE_CACHE_KEY = "__subtree_cache__"
TARGET_NEUTRALIZED_CACHE_KEY = "__target_neutralized_cache__"
FEATURE_BANK_KEY = "__feature_bank__"
BATCH_FOLD_IR_CACHE_KEY = "__batch_fold_ir_cache__"
FOLD_FEATURES_CACHE_KEY = "__fold_features_cache__"
DATE_FLAT_INDICES_KEY = "__date_flat_indices__"
DATE_GROUP_OFFSETS_KEY = "__date_group_offsets__"
EARLY_REJECT_PENALTY = -2.0
EARLY_REJECT_FOLD_IC_THRESHOLD = -0.02
EARLY_REJECT_CUMAVG_THRESHOLD = 0.0
AUDIT_SAMPLE_RATE = 0.05
BATCH_FITNESS_SIZE = 32
ISLAND_COUNT = 3
ISLAND_MIGRATION_INTERVAL = 5
ISLAND_MIGRATION_RATE = 0.05
MAX_VM_STACK_DEPTH = 12
RIDGE_ALPHA = 1e-6
_DATE_GROUPS_CACHE: dict[tuple[int, int, Any, Any], dict[Any, np.ndarray]] = {}
_DATE_GROUPS_CACHE_LOCK = threading.Lock()
_FEATURE_LOCK_CACHE: dict[int, threading.Lock] = {}
_FEATURE_LOCK_CACHE_GUARD = threading.Lock()
VM_CONTEXT_KEY = "__gp_vm_context__"
VM_PROGRAM_CACHE_KEY = "__gp_vm_program_cache__"
JIT_DESIGN_MATRIX_KEY = "__jit_design_matrix__"
JIT_VALID_MASK_KEY = "__jit_valid_mask__"
JIT_DATE_FLAT_INDICES_KEY = "__jit_date_flat_indices__"
JIT_DATE_GROUP_OFFSETS_KEY = "__jit_date_group_offsets__"
JIT_MAX_GROUP_SIZE_KEY = "__jit_max_group_size__"

_THREAD_LOCAL_STACK = threading.local()
_GLOBAL_VM_PROGRAM_CACHE: dict[tuple[tuple[str, ...], str], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_GLOBAL_VM_PROGRAM_CACHE_LOCK = threading.Lock()


def _get_thread_local_stack(row_count: int) -> np.ndarray:
    """Get or create a thread-local stack for VM execution.
    
    Prevents race conditions when multiple threads execute trees in parallel.
    Each thread gets its own stack buffer.
    """
    if not hasattr(_THREAD_LOCAL_STACK, 'stacks'):
        _THREAD_LOCAL_STACK.stacks = {}
    
    stacks = _THREAD_LOCAL_STACK.stacks
    if row_count not in stacks:
        stacks[row_count] = np.empty((MAX_VM_STACK_DEPTH, row_count), dtype=np.float64)
    
    return stacks[row_count]

OP_ADD = 1
OP_SUB = 2
OP_MUL = 3
OP_DIV = 4
OP_ABS = 5
OP_LOG = 6
OP_SQRT = 7
OP_EXP = 8
OP_SIGMOID = 9
OP_RANK = 10
OP_CS_RANK = 11
OP_CS_ZSCORE = 12
OP_NEG = 13
OP_TS_STD = 14
OP_TS_MEAN = 15
OP_TS_RANK = 16
OP_DECAY_LINEAR = 17
OP_MAX = 18
OP_MIN = 19
OP_CONST = 50
OP_VAR = 100
_UNARY_OPCODE_MAP = {
    "abs": OP_ABS,
    "log": OP_LOG,
    "sqrt": OP_SQRT,
    "exp": OP_EXP,
    "sigmoid": OP_SIGMOID,
    "rank": OP_RANK,
    "cs_rank": OP_CS_RANK,
    "cs_zscore": OP_CS_ZSCORE,
    "neg": OP_NEG,
}
_BINARY_OPCODE_MAP = {
    "+": OP_ADD,
    "-": OP_SUB,
    "*": OP_MUL,
    "/": OP_DIV,
    "max": OP_MAX,
    "min": OP_MIN,
}
_TS_OPCODE_MAP = {
    "ts_std": OP_TS_STD,
    "ts_mean": OP_TS_MEAN,
    "ts_rank": OP_TS_RANK,
    "decay_linear": OP_DECAY_LINEAR,
}


def _safe_float_terminal(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_feature_fingerprint(features: dict[str, np.ndarray]) -> int:
    """Compute content-based fingerprint for feature dictionary to avoid cache aliasing.
    
    Uses feature names, array shapes, and boundary values (first/last elements) to create
    a stable hash that won't alias when feature dictionaries are recreated with same data.
    
    This prevents stale cache entries when features are resampled or sliced across
    generations, as the fingerprint changes when actual data changes rather than just
    when the dict object ID changes.
    """
    feature_names = sorted(k for k in features.keys() if not k.startswith("__") and not k.startswith("target"))
    if not feature_names:
        return 0
    
    # Build fingerprint from: feature names, shapes, and boundary values
    fingerprint_parts = [",".join(feature_names)]
    
    for name in feature_names[:10]:  # Sample first 10 features to keep fingerprint fast
        arr = np.asarray(features[name], dtype=np.float64)
        if arr.size == 0:
            fingerprint_parts.append(f"{name}:empty")
            continue
        
        # Include shape and boundary values (first, last, min, max)
        fingerprint_parts.append(f"{name}:{arr.shape}")
        if np.all(np.isfinite(arr)):
            # Use boundary statistics for finite arrays
            fingerprint_parts.append(f"{arr.flat[0]:.6e}")
            fingerprint_parts.append(f"{arr.flat[-1]:.6e}")
            fingerprint_parts.append(f"{np.min(arr):.6e}")
            fingerprint_parts.append(f"{np.max(arr):.6e}")
        else:
            # Count finite values for arrays with NaN/inf
            finite_count = int(np.sum(np.isfinite(arr)))
            fingerprint_parts.append(f"finite:{finite_count}")
    
    fingerprint_str = "|".join(fingerprint_parts)
    return _safe_expr_hash(fingerprint_str)


def _max_stack_depth(node: ge.GPNode) -> int:
    if not node.children:
        return 1
    if len(node.children) == 1:
        return _max_stack_depth(node.children[0])
    left_depth = _max_stack_depth(node.children[0])
    right_depth = _max_stack_depth(node.children[1])
    return max(left_depth, right_depth + 1)


def _compile_tree_to_rpn(node: ge.GPNode, feature_names: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    feature_index = {name: idx for idx, name in enumerate(feature_names)}
    opcodes: list[int] = []
    operands: list[int] = []
    const_values: list[float] = []

    def _compile(current: ge.GPNode) -> bool:
        if not current.children:
            if current.value in feature_index:
                opcodes.append(OP_VAR)
                operands.append(feature_index[current.value])
                return True
            const_value = _safe_float_terminal(current.value)
            if const_value is None:
                return False
            operands.append(len(const_values))
            opcodes.append(OP_CONST)
            const_values.append(const_value)
            return True

        if len(current.children) == 1:
            opcode = _UNARY_OPCODE_MAP.get(current.operator)
            if opcode is None or not _compile(current.children[0]):
                return False
            opcodes.append(opcode)
            operands.append(0)
            return True

        if len(current.children) == 2 and current.operator in _TS_OPCODE_MAP:
            window = _safe_float_terminal(current.children[1].value)
            if window is None or not _compile(current.children[0]):
                return False
            opcodes.append(_TS_OPCODE_MAP[current.operator])
            operands.append(max(2, min(int(window), 60)))
            return True

        if len(current.children) == 2:
            opcode = _BINARY_OPCODE_MAP.get(current.operator)
            if opcode is None:
                return False
            if not _compile(current.children[0]) or not _compile(current.children[1]):
                return False
            opcodes.append(opcode)
            operands.append(0)
            return True

        return False

    if not _compile(node):
        return None
    if _max_stack_depth(node) > MAX_VM_STACK_DEPTH:
        return None
    return (
        np.asarray(opcodes, dtype=np.int32),
        np.asarray(operands, dtype=np.int32),
        np.asarray(const_values, dtype=np.float64),
    )


def _build_ticker_group_offsets(tickers: np.ndarray | None, dates: np.ndarray) -> np.ndarray:
    dates = np.asarray(dates)
    if dates.ndim != 1:
        raise ValueError("date metadata must be a 1D array")
    if tickers is not None:
        tickers = np.asarray(tickers)
        if tickers.ndim != 1 or tickers.size != dates.size:
            raise ValueError("ticker/date metadata must be 1D arrays with equal length")
    if dates.size == 0:
        return np.array([0], dtype=np.int32)
    offsets = [0]
    start = 0
    current = None if tickers is None else tickers[0]
    for idx in range(1, dates.size):
        boundary = False
        if tickers is None:
            prev_date = dates[idx - 1]
            curr_date = dates[idx]
            boundary = pd.notna(prev_date) and pd.notna(curr_date) and curr_date < prev_date
        else:
            boundary = tickers[idx] != current
        if boundary:
            if pd.notna(dates[start:idx]).any():
                valid_dates = dates[start:idx][pd.notna(dates[start:idx])]
                if valid_dates.size and np.any(valid_dates[1:] < valid_dates[:-1]):
                    raise ValueError("row-order contract requires (ticker, date) sorting within each ticker")
            offsets.append(idx)
            start = idx
            if tickers is not None:
                current = tickers[idx]
    if pd.notna(dates[start:]).any():
        valid_dates = dates[start:][pd.notna(dates[start:])]
        if valid_dates.size and np.any(valid_dates[1:] < valid_dates[:-1]):
            raise ValueError("row-order contract requires (ticker, date) sorting within each ticker")
    offsets.append(dates.size)
    return np.asarray(offsets, dtype=np.int32)


def _build_date_group_index(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    date_groups = _group_row_indices_by_date(np.asarray(dates))
    if not date_groups:
        return np.empty(0, dtype=np.int32), np.array([0], dtype=np.int32)
    counts = np.fromiter((indices.size for indices in date_groups.values()), dtype=np.int32)
    offsets = np.empty(counts.size + 1, dtype=np.int32)
    offsets[0] = 0
    offsets[1:] = np.cumsum(counts, dtype=np.int32)
    flat = np.empty(int(offsets[-1]), dtype=np.int32)
    cursor = 0
    for indices in date_groups.values():
        size = int(indices.size)
        flat[cursor:cursor + size] = np.asarray(indices, dtype=np.int32)
        cursor += size
    return flat, offsets


def _build_vm_context(features: dict[str, np.ndarray]) -> dict[str, Any] | None:
    feature_names = [name for name in features.keys() if not name.startswith("__") and not name.startswith("target")]
    if not feature_names:
        return None
    row_count = len(np.asarray(features[feature_names[0]]))
    if row_count == 0:
        return None
    feature_matrix = np.column_stack([np.asarray(features[name], dtype=np.float64) for name in feature_names])
    tickers = features.get("__ticker__")
    dates = features.get("__date__")
    if tickers is not None:
        if dates is None:
            raise ValueError("row-order contract requires __date__ when __ticker__ is provided")
        ticker_group_offsets = _build_ticker_group_offsets(np.asarray(tickers), np.asarray(dates))
    elif dates is not None:
        ticker_group_offsets = _build_ticker_group_offsets(None, np.asarray(dates))
    else:
        ticker_group_offsets = np.array([0, row_count], dtype=np.int32)
    if dates is None:
        date_flat_indices = np.arange(row_count, dtype=np.int32)
        date_group_offsets = np.array([0, row_count], dtype=np.int32)
    else:
        date_flat_indices, date_group_offsets = _build_date_group_index(np.asarray(dates))
    design_matrix = None
    valid_mask = None
    log_mcap_arr = features.get("__log_market_cap__")
    sector_arr = features.get("__sector__")
    if log_mcap_arr is not None and sector_arr is not None:
        log_mcap_arr = np.asarray(log_mcap_arr, dtype=np.float64)
        sector_arr = np.asarray(sector_arr)
        valid_mask = np.isfinite(log_mcap_arr) & pd.notna(sector_arr)
        sector_col_count = 0
        design_matrix = np.empty((row_count, 2), dtype=np.float64)
        design_matrix[:, 0] = 1.0
        design_matrix[:, 1] = np.where(np.isfinite(log_mcap_arr), log_mcap_arr, 0.0)
        if np.any(valid_mask):
            sector_codes = np.full(row_count, -1, dtype=np.int32)
            factorized, uniques = pd.factorize(sector_arr[valid_mask], sort=True)
            sector_codes[valid_mask] = factorized.astype(np.int32, copy=False)
            sector_col_count = max(int(len(uniques)) - 1, 0)
            if sector_col_count > 0:
                expanded = np.zeros((row_count, 2 + sector_col_count), dtype=np.float64)
                expanded[:, :2] = design_matrix
                valid_rows = np.flatnonzero(valid_mask)
                for row_idx in valid_rows:
                    code = sector_codes[row_idx]
                    if code > 0:
                        expanded[row_idx, code + 1] = 1.0
                design_matrix = expanded
    return {
        "cache_token": _compute_feature_fingerprint(features),
        "feature_names": feature_names,
        "feature_matrix": feature_matrix,
        "ticker_group_offsets": ticker_group_offsets,
        "date_flat_indices": date_flat_indices,
        "date_group_offsets": date_group_offsets,
        "design_matrix": design_matrix,
        "valid_mask": valid_mask,
        "row_count": row_count,
    }


def _attach_neutralization_jit_context(features: dict[str, Any], context: dict[str, Any]) -> None:
    neutralization_cache = features.get(ge.NEUTRALIZATION_CACHE_KEY)
    design_matrix = context.get("design_matrix")
    valid_mask = context.get("valid_mask")
    if not isinstance(neutralization_cache, dict) or design_matrix is None or valid_mask is None:
        return
    date_group_offsets = context["date_group_offsets"]
    neutralization_cache[JIT_DESIGN_MATRIX_KEY] = design_matrix
    neutralization_cache[JIT_VALID_MASK_KEY] = valid_mask
    neutralization_cache[JIT_DATE_FLAT_INDICES_KEY] = context["date_flat_indices"]
    neutralization_cache[JIT_DATE_GROUP_OFFSETS_KEY] = date_group_offsets
    neutralization_cache[JIT_MAX_GROUP_SIZE_KEY] = int(np.max(np.diff(date_group_offsets))) if date_group_offsets.size > 1 else 0


def _get_vm_context(features: dict[str, np.ndarray]) -> dict[str, Any] | None:
    cached = features.get(VM_CONTEXT_KEY)
    if cached is not None:
        _attach_neutralization_jit_context(features, cached)
        return cached
    context = _build_vm_context(features)
    if context is not None:
        features[VM_CONTEXT_KEY] = context
        features.setdefault(FEATURE_BANK_KEY, context["feature_matrix"])
        _attach_neutralization_jit_context(features, context)
    return context


def _ensure_neutralization_jit_context(features: dict[str, Any]) -> None:
    if ge.NEUTRALIZATION_CACHE_KEY not in features:
        return
    _get_vm_context(features)


def _get_vm_program(node: ge.GPNode, feature_names: list[str], features: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    cache_key = (tuple(feature_names), node.to_string())
    
    # Try to get from global cache without lock first (fast path)
    program = _GLOBAL_VM_PROGRAM_CACHE.get(cache_key)
    if program is not None:
        return program
    
    # Compile the program
    program = _compile_tree_to_rpn(node, feature_names)
    if program is not None:
        # Store in global cache with lock
        with _GLOBAL_VM_PROGRAM_CACHE_LOCK:
            _GLOBAL_VM_PROGRAM_CACHE[cache_key] = program
    
    return program


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_protected_div(left: np.ndarray, right: np.ndarray, out: np.ndarray) -> None:
    for idx in range(left.size):
        denom = right[idx]
        if np.isfinite(left[idx]) and np.isfinite(denom) and abs(denom) > 1e-12:
            out[idx] = left[idx] / denom
        else:
            out[idx] = 0.0


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_rank_pct(x: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    order = np.argsort(values)
    valid_count = 0
    idx = 0
    while idx < x.size:
        row = order[idx]
        if not np.isfinite(values[row]):
            out[row] = np.nan
            idx += 1
            continue
        end = idx + 1
        while end < x.size and values[order[end]] == values[row]:
            end += 1
        avg_rank = 0.5 * ((idx + 1) + end)
        for pos in range(idx, end):
            out[order[pos]] = avg_rank
        valid_count += end - idx
        idx = end
    if valid_count == 0:
        for row in range(out.size):
            out[row] = np.nan
        return
    scale = float(valid_count)
    for row in range(out.size):
        if np.isfinite(out[row]):
            out[row] = out[row] / scale


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_rolling_mean(x: np.ndarray, window: int, ticker_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = 0.0
    for group_idx in range(ticker_group_offsets.size - 1):
        start = ticker_group_offsets[group_idx]
        stop = ticker_group_offsets[group_idx + 1]
        for row in range(start + window - 1, stop):
            acc = 0.0
            valid = True
            for offset in range(window):
                value = values[row - window + 1 + offset]
                if not np.isfinite(value):
                    valid = False
                    break
                acc += value
            if valid:
                out[row] = acc / window


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_rolling_std(x: np.ndarray, window: int, ticker_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = 0.0
    for group_idx in range(ticker_group_offsets.size - 1):
        start = ticker_group_offsets[group_idx]
        stop = ticker_group_offsets[group_idx + 1]
        for row in range(start + window - 1, stop):
            acc = 0.0
            acc_sq = 0.0
            valid = True
            for offset in range(window):
                value = values[row - window + 1 + offset]
                if not np.isfinite(value):
                    valid = False
                    break
                acc += value
                acc_sq += value * value
            if valid:
                mean = acc / window
                if window <= 1:
                    out[row] = 0.0
                    continue
                var = max((acc_sq - window * mean * mean) / (window - 1), 0.0)
                out[row] = np.sqrt(var)


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_rolling_rank(x: np.ndarray, window: int, ticker_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = 0.0
    for group_idx in range(ticker_group_offsets.size - 1):
        start = ticker_group_offsets[group_idx]
        stop = ticker_group_offsets[group_idx + 1]
        for row in range(start + window - 1, stop):
            current = values[row]
            if not np.isfinite(current):
                continue
            less_count = 0
            equal_count = 0
            valid = True
            for offset in range(window):
                value = values[row - window + 1 + offset]
                if not np.isfinite(value):
                    valid = False
                    break
                if value < current:
                    less_count += 1
                elif value == current:
                    equal_count += 1
            if valid:
                out[row] = (less_count + 0.5 * equal_count) / window


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_rolling_decay(x: np.ndarray, window: int, ticker_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = 0.0
    weight_sum = window * (window + 1) / 2.0
    for group_idx in range(ticker_group_offsets.size - 1):
        start = ticker_group_offsets[group_idx]
        stop = ticker_group_offsets[group_idx + 1]
        for row in range(start + window - 1, stop):
            acc = 0.0
            valid = True
            for offset in range(window):
                value = values[row - window + 1 + offset]
                if not np.isfinite(value):
                    valid = False
                    break
                acc += value * (offset + 1)
            if valid:
                out[row] = acc / weight_sum


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_cs_rank(x: np.ndarray, date_flat_indices: np.ndarray, date_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = np.nan
    for group_idx in range(date_group_offsets.size - 1):
        start = date_group_offsets[group_idx]
        stop = date_group_offsets[group_idx + 1]
        count = stop - start
        if count <= 0:
            continue
        vals = np.empty(count, dtype=np.float64)
        order = np.empty(count, dtype=np.int64)
        for local_idx in range(count):
            vals[local_idx] = values[date_flat_indices[start + local_idx]]
            order[local_idx] = local_idx
        order = order[np.argsort(vals)]
        valid_count = 0
        idx = 0
        while idx < count:
            local_row = order[idx]
            if not np.isfinite(vals[local_row]):
                idx += 1
                continue
            end = idx + 1
            while end < count and vals[order[end]] == vals[local_row]:
                end += 1
            avg_rank = 0.5 * ((valid_count + 1) + (valid_count + end - idx))
            for pos in range(idx, end):
                out[date_flat_indices[start + order[pos]]] = avg_rank
            valid_count += end - idx
            idx = end
        if valid_count > 0:
            for local_idx in range(count):
                row_idx = date_flat_indices[start + local_idx]
                if np.isfinite(out[row_idx]):
                    out[row_idx] = out[row_idx] / valid_count


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_cs_zscore(x: np.ndarray, date_flat_indices: np.ndarray, date_group_offsets: np.ndarray, out: np.ndarray) -> None:
    values = np.empty(x.size, dtype=np.float64)
    values[:] = x
    out[:] = np.nan
    for group_idx in range(date_group_offsets.size - 1):
        start = date_group_offsets[group_idx]
        stop = date_group_offsets[group_idx + 1]
        acc = 0.0
        acc_sq = 0.0
        count = 0
        for pos in range(start, stop):
            value = values[date_flat_indices[pos]]
            if np.isfinite(value):
                acc += value
                acc_sq += value * value
                count += 1
        if count == 0:
            continue
        mean = acc / count
        std = np.sqrt(max(acc_sq / count - mean * mean, 0.0)) + 1e-9
        for pos in range(start, stop):
            row_idx = date_flat_indices[pos]
            value = values[row_idx]
            if np.isfinite(value):
                out[row_idx] = (value - mean) / std


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_ridge_neutralize(
    alpha_arr: np.ndarray,
    design_matrix: np.ndarray,
    valid_mask: np.ndarray,
    date_flat_indices: np.ndarray,
    date_group_offsets: np.ndarray,
    max_group_size: int,
    ridge_alpha: float,
) -> np.ndarray:
    residuals = np.empty(alpha_arr.size, dtype=np.float64)
    residuals[:] = alpha_arr
    if residuals.size == 0:
        return residuals
    col_count = design_matrix.shape[1]
    row_buffer = np.empty(max(max_group_size, 1), dtype=np.int32)
    gram = np.empty((col_count, col_count), dtype=np.float64)
    rhs = np.empty(col_count, dtype=np.float64)
    beta = np.empty(col_count, dtype=np.float64)
    for group_idx in range(date_group_offsets.size - 1):
        start = date_group_offsets[group_idx]
        stop = date_group_offsets[group_idx + 1]
        valid_count = 0
        for pos in range(start, stop):
            row_idx = date_flat_indices[pos]
            y_val = residuals[row_idx]
            if valid_mask[row_idx] and np.isfinite(y_val):
                row_buffer[valid_count] = row_idx
                valid_count += 1
        if valid_count < 2:
            continue
        for row in range(col_count):
            rhs[row] = 0.0
            for col in range(col_count):
                gram[row, col] = 0.0
        for local_idx in range(valid_count):
            row_idx = row_buffer[local_idx]
            y_val = residuals[row_idx]
            for left_col in range(col_count):
                left_val = design_matrix[row_idx, left_col]
                rhs[left_col] += left_val * y_val
                for right_col in range(col_count):
                    gram[left_col, right_col] += left_val * design_matrix[row_idx, right_col]
        for diag_idx in range(col_count):
            gram[diag_idx, diag_idx] += ridge_alpha
        beta[:] = np.linalg.solve(gram, rhs)
        for local_idx in range(valid_count):
            row_idx = row_buffer[local_idx]
            fitted = 0.0
            for col_idx in range(col_count):
                fitted += design_matrix[row_idx, col_idx] * beta[col_idx]
            residual = residuals[row_idx] - fitted
            residuals[row_idx] = 0.0 if abs(residual) < 1e-12 else residual
    return residuals


@njit(cache=True, nogil=True, error_model="numpy", parallel=True)
def _numba_batch_ridge_neutralize(
    alpha_matrix: np.ndarray,
    design_matrix: np.ndarray,
    valid_mask: np.ndarray,
    date_flat_indices: np.ndarray,
    date_group_offsets: np.ndarray,
    max_group_size: int,
    ridge_alpha: float,
) -> np.ndarray:
    residuals = np.empty(alpha_matrix.shape, dtype=np.float64)
    residuals[:, :] = alpha_matrix
    if residuals.size == 0:
        return residuals
    candidate_count = residuals.shape[1]
    col_count = design_matrix.shape[1]
    base_row_buffer = np.empty(max(max_group_size, 1), dtype=np.int32)
    shared_gram = np.empty((col_count, col_count), dtype=np.float64)
    for group_idx in range(date_group_offsets.size - 1):
        start = date_group_offsets[group_idx]
        stop = date_group_offsets[group_idx + 1]
        base_valid_count = 0
        for pos in range(start, stop):
            row_idx = date_flat_indices[pos]
            if valid_mask[row_idx]:
                base_row_buffer[base_valid_count] = row_idx
                base_valid_count += 1
        if base_valid_count < 2:
            continue
        for row in range(col_count):
            for col in range(col_count):
                shared_gram[row, col] = 0.0
        for local_idx in range(base_valid_count):
            row_idx = base_row_buffer[local_idx]
            for left_col in range(col_count):
                left_val = design_matrix[row_idx, left_col]
                for right_col in range(col_count):
                    shared_gram[left_col, right_col] += left_val * design_matrix[row_idx, right_col]
        for diag_idx in range(col_count):
            shared_gram[diag_idx, diag_idx] += ridge_alpha
        
        # Pre-allocate workspaces per date group for parallel execution (zero-allocation optimization)
        workspace_row_buffer = np.empty((candidate_count, max(max_group_size, 1)), dtype=np.int32)
        workspace_gram = np.empty((candidate_count, col_count, col_count), dtype=np.float64)
        workspace_rhs = np.empty((candidate_count, col_count), dtype=np.float64)
        workspace_beta = np.empty((candidate_count, col_count), dtype=np.float64)
        
        for candidate_idx in prange(candidate_count):
            row_buffer = workspace_row_buffer[candidate_idx]
            gram = workspace_gram[candidate_idx]
            rhs = workspace_rhs[candidate_idx]
            beta = workspace_beta[candidate_idx]
            use_shared_gram = True
            for local_idx in range(base_valid_count):
                row_idx = base_row_buffer[local_idx]
                if not np.isfinite(residuals[row_idx, candidate_idx]):
                    use_shared_gram = False
                    break
            valid_count = base_valid_count
            for row in range(col_count):
                rhs[row] = 0.0
                for col in range(col_count):
                    gram[row, col] = shared_gram[row, col]
            if use_shared_gram:
                for local_idx in range(base_valid_count):
                    row_idx = base_row_buffer[local_idx]
                    y_val = residuals[row_idx, candidate_idx]
                    row_buffer[local_idx] = row_idx
                    for left_col in range(col_count):
                        rhs[left_col] += design_matrix[row_idx, left_col] * y_val
            else:
                valid_count = 0
                for row in range(col_count):
                    for col in range(col_count):
                        gram[row, col] = 0.0
                for local_idx in range(base_valid_count):
                    row_idx = base_row_buffer[local_idx]
                    y_val = residuals[row_idx, candidate_idx]
                    if not np.isfinite(y_val):
                        continue
                    row_buffer[valid_count] = row_idx
                    valid_count += 1
                    for left_col in range(col_count):
                        left_val = design_matrix[row_idx, left_col]
                        rhs[left_col] += left_val * y_val
                        for right_col in range(col_count):
                            gram[left_col, right_col] += left_val * design_matrix[row_idx, right_col]
                if valid_count < 2:
                    continue
                for diag_idx in range(col_count):
                    gram[diag_idx, diag_idx] += ridge_alpha
            beta[:] = np.linalg.solve(gram, rhs)
            for local_idx in range(valid_count):
                row_idx = row_buffer[local_idx]
                fitted = 0.0
                for col_idx in range(col_count):
                    fitted += design_matrix[row_idx, col_idx] * beta[col_idx]
                residual = residuals[row_idx, candidate_idx] - fitted
                residuals[row_idx, candidate_idx] = 0.0 if abs(residual) < 1e-12 else residual
    return residuals


def _get_jit_neutralization_payload(
    neutralization_cache: dict[Any, Any] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int] | None:
    if not isinstance(neutralization_cache, dict):
        return None
    design_matrix = neutralization_cache.get(JIT_DESIGN_MATRIX_KEY)
    valid_mask = neutralization_cache.get(JIT_VALID_MASK_KEY)
    date_flat_indices = neutralization_cache.get(JIT_DATE_FLAT_INDICES_KEY)
    date_group_offsets = neutralization_cache.get(JIT_DATE_GROUP_OFFSETS_KEY)
    max_group_size = neutralization_cache.get(JIT_MAX_GROUP_SIZE_KEY)
    if any(item is None for item in (design_matrix, valid_mask, date_flat_indices, date_group_offsets, max_group_size)):
        return None
    return (
        np.asarray(design_matrix, dtype=np.float64),
        np.asarray(valid_mask, dtype=np.bool_),
        np.asarray(date_flat_indices, dtype=np.int32),
        np.asarray(date_group_offsets, dtype=np.int32),
        int(max_group_size),
    )


@njit(cache=True, nogil=True, error_model="numpy")
def _numba_execute_rpn(
    opcodes: np.ndarray,
    operands: np.ndarray,
    const_values: np.ndarray,
    feature_matrix: np.ndarray,
    ticker_group_offsets: np.ndarray,
    date_flat_indices: np.ndarray,
    date_group_offsets: np.ndarray,
    stack: np.ndarray,
) -> np.ndarray:
    row_count = feature_matrix.shape[0]
    sp = -1
    for pc in range(opcodes.size):
        opcode = opcodes[pc]
        operand = operands[pc]
        if opcode == OP_VAR:
            sp += 1
            stack[sp, :] = feature_matrix[:, operand]
        elif opcode == OP_CONST:
            sp += 1
            stack[sp, :] = const_values[operand]
        elif opcode == OP_ADD:
            stack[sp - 1, :] = stack[sp - 1, :] + stack[sp, :]
            sp -= 1
        elif opcode == OP_SUB:
            stack[sp - 1, :] = stack[sp - 1, :] - stack[sp, :]
            sp -= 1
        elif opcode == OP_MUL:
            stack[sp - 1, :] = stack[sp - 1, :] * stack[sp, :]
            sp -= 1
        elif opcode == OP_DIV:
            _numba_protected_div(stack[sp - 1, :], stack[sp, :], stack[sp - 1, :])
            sp -= 1
        elif opcode == OP_MAX:
            stack[sp - 1, :] = np.maximum(stack[sp - 1, :], stack[sp, :])
            sp -= 1
        elif opcode == OP_MIN:
            stack[sp - 1, :] = np.minimum(stack[sp - 1, :], stack[sp, :])
            sp -= 1
        elif opcode == OP_ABS:
            stack[sp, :] = np.abs(stack[sp, :])
        elif opcode == OP_LOG:
            stack[sp, :] = np.sign(stack[sp, :]) * np.log1p(np.abs(stack[sp, :]))
        elif opcode == OP_SQRT:
            stack[sp, :] = np.sqrt(np.abs(stack[sp, :]))
        elif opcode == OP_EXP:
            stack[sp, :] = np.exp(np.clip(stack[sp, :], -50.0, 50.0))
        elif opcode == OP_SIGMOID:
            stack[sp, :] = 1.0 / (1.0 + np.exp(-np.clip(stack[sp, :], -50.0, 50.0)))
        elif opcode == OP_NEG:
            stack[sp, :] = -stack[sp, :]
        elif opcode == OP_RANK:
            _numba_rank_pct(stack[sp, :], stack[sp, :])
        elif opcode == OP_CS_RANK:
            _numba_cs_rank(stack[sp, :], date_flat_indices, date_group_offsets, stack[sp, :])
        elif opcode == OP_CS_ZSCORE:
            _numba_cs_zscore(stack[sp, :], date_flat_indices, date_group_offsets, stack[sp, :])
        elif opcode == OP_TS_STD:
            _numba_rolling_std(stack[sp, :], operand, ticker_group_offsets, stack[sp, :])
        elif opcode == OP_TS_MEAN:
            _numba_rolling_mean(stack[sp, :], operand, ticker_group_offsets, stack[sp, :])
        elif opcode == OP_TS_RANK:
            _numba_rolling_rank(stack[sp, :], operand, ticker_group_offsets, stack[sp, :])
        elif opcode == OP_DECAY_LINEAR:
            _numba_rolling_decay(stack[sp, :], operand, ticker_group_offsets, stack[sp, :])
    result = np.empty(row_count, dtype=np.float64)
    result[:] = stack[sp, :]
    return result


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
    lock = _get_feature_lock(features)
    with lock:
        if key not in features:
            features[key] = factory()
        return features[key]


def _feature_cache_get(features: dict[str, Any], cache_key: str, key: Any) -> Any:
    cache = features.get(cache_key)
    return None if cache is None else cache.get(key)


def _feature_cache_set(features: dict[str, Any], cache_key: str, key: Any, value: Any) -> None:
    cache = _thread_safe_feature_cache(features, cache_key, dict)
    cache[key] = value


def _get_feature_lock(features: dict[str, Any]) -> threading.Lock:
    feature_id = id(features)
    with _FEATURE_LOCK_CACHE_GUARD:
        if len(_FEATURE_LOCK_CACHE) > 4096:
            _FEATURE_LOCK_CACHE.clear()
        return _FEATURE_LOCK_CACHE.setdefault(feature_id, threading.Lock())


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
    row_count = len(np.asarray(features["__date__"])) if "__date__" in features else _feature_array_length(features)
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
            _ensure_neutralization_jit_context(fold_view)
    return fold_views

def _ensure_date_group_index(features: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    date_flat_indices = features.get(DATE_FLAT_INDICES_KEY)
    date_group_offsets = features.get(DATE_GROUP_OFFSETS_KEY)
    if date_flat_indices is not None and date_group_offsets is not None:
        return date_flat_indices, date_group_offsets
    date_flat_indices, date_group_offsets = _build_date_group_index_from_ids(
        _factorize_dates(np.asarray(features["__date__"]))
    )
    features[DATE_FLAT_INDICES_KEY] = date_flat_indices
    features[DATE_GROUP_OFFSETS_KEY] = date_group_offsets
    features["__date_group_index__"] = (date_flat_indices, date_group_offsets)
    return date_flat_indices, date_group_offsets

def _build_cached_fold_features(
    features: dict[str, np.ndarray],
    fold_structure: tuple[tuple[np.ndarray, np.ndarray], ...],
) -> list[dict[str, np.ndarray]]:
    fold_views = _build_fold_views(features, fold_structure)
    for fold_features in fold_views:
        if "__date__" in fold_features:
            _ensure_date_group_index(fold_features)
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
    alpha_arr = np.asarray(alpha_arr, dtype=np.float64)
    residuals = alpha_arr.copy()
    if log_mcap_arr is None or sector_arr is None or date_arr is None:
        return residuals

    jit_payload = _get_jit_neutralization_payload(neutralization_cache)
    if jit_payload is not None:
        residuals = _numba_ridge_neutralize(alpha_arr, *jit_payload, RIDGE_ALPHA)
        logger.debug(
            "_optimized_neutralize_cross_section dt=%.4fs rows=%d dates=%d cache=%s",
            pytime.perf_counter() - t0,
            residuals.size,
            len(neutralization_cache),
            neutralization_cache is not None,
        )
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
            beta = np.linalg.solve(design_valid.T @ design_valid + RIDGE_ALPHA * np.eye(design_valid.shape[1]), design_valid.T @ alpha_valid)
        except np.linalg.LinAlgError:
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
    alpha_matrix = np.asarray(alpha_matrix, dtype=np.float64)
    residuals = alpha_matrix.copy()
    if residuals.ndim != 2 or residuals.size == 0:
        return residuals

    jit_payload = _get_jit_neutralization_payload(neutralization_cache)
    if jit_payload is not None:
        return _numba_batch_ridge_neutralize(alpha_matrix, *jit_payload, RIDGE_ALPHA)

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
            beta = np.linalg.solve(design.T @ design + RIDGE_ALPHA * np.eye(design.shape[1]), design.T @ alpha_valid)
        except np.linalg.LinAlgError:
            continue
        alpha_slice[cached_valid] = alpha_valid - design @ beta
        alpha_slice[cached_valid] = np.where(
            np.abs(alpha_slice[cached_valid]) < 1e-12,
            0.0,
            alpha_slice[cached_valid],
        )
        residuals[row_idx] = alpha_slice
    return residuals


@njit(cache=True, parallel=True)
def _numba_batch_daily_ics(
    alpha_matrix: np.ndarray,
    target: np.ndarray,
    date_flat_indices: np.ndarray,
    date_group_offsets: np.ndarray,
    eval_mask_matrix: np.ndarray,
) -> np.ndarray:
    candidate_count = alpha_matrix.shape[1]
    n_dates = date_group_offsets.size - 1
    out = np.empty((n_dates, candidate_count), dtype=np.float64)
    out[:] = np.nan
    for candidate_idx in prange(candidate_count):
        daily_ics = _numba_daily_ics(
            alpha_matrix[:, candidate_idx],
            target,
            date_flat_indices,
            date_group_offsets,
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
    fold_views = features.get(FOLD_FEATURES_CACHE_KEY)
    if fold_views is None:
        fold_views = _build_cached_fold_features(features, fold_structure)
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
        # Vectorized eval_mask_matrix computation using numpy broadcasting
        alpha_finite_mask = np.isfinite(alpha_fold)
        target_finite_mask = np.isfinite(target_fold)
        eval_mask_matrix = alpha_finite_mask & target_finite_mask[:, np.newaxis]
        liquidity_mask = fold_features.get('__liquidity_mask__')
        if liquidity_mask is not None:
            eval_mask_matrix &= np.asarray(liquidity_mask, dtype=bool)[:, np.newaxis]
        
        date_flat_indices, date_group_offsets = _ensure_date_group_index(fold_features)
        
        daily_ic_matrix = _numba_batch_daily_ics(
            alpha_fold,
            target_fold,
            date_flat_indices,
            date_group_offsets,
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
def _numba_build_date_group_index_from_ids(date_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_dates = 0
    for i in range(date_ids.size):
        if date_ids[i] >= n_dates:
            n_dates = date_ids[i] + 1
    counts = np.zeros(n_dates, dtype=np.int64)
    for i in range(date_ids.size):
        date_id = date_ids[i]
        if date_id >= 0:
            counts[date_id] += 1
    offsets = np.empty(n_dates + 1, dtype=np.int64)
    offsets[0] = 0
    for date_id in range(n_dates):
        offsets[date_id + 1] = offsets[date_id] + counts[date_id]
    flat_indices = np.empty(offsets[-1], dtype=np.int64)
    next_positions = offsets[:-1].copy()
    for row_idx in range(date_ids.size):
        date_id = date_ids[row_idx]
        if date_id < 0:
            continue
        write_pos = next_positions[date_id]
        flat_indices[write_pos] = row_idx
        next_positions[date_id] = write_pos + 1
    return flat_indices, offsets


def _build_date_group_index_from_ids(date_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return _numba_build_date_group_index_from_ids(np.asarray(date_ids, dtype=np.int64))


@njit(cache=True)
def _numba_daily_ics(
    alpha: np.ndarray,
    target: np.ndarray,
    date_flat_indices: np.ndarray,
    date_group_offsets: np.ndarray,
    eval_mask: np.ndarray,
) -> np.ndarray:
    n_dates = date_group_offsets.size - 1
    out = np.empty(n_dates, dtype=np.float64)
    out[:] = np.nan
    for date_id in range(n_dates):
        start = date_group_offsets[date_id]
        stop = date_group_offsets[date_id + 1]
        valid_count = 0
        for group_pos in range(start, stop):
            if eval_mask[date_flat_indices[group_pos]]:
                valid_count += 1
        if valid_count <= 5:
            continue
        alpha_day = np.empty(valid_count, dtype=np.float64)
        target_day = np.empty(valid_count, dtype=np.float64)
        pos = 0
        for group_pos in range(start, stop):
            row_idx = date_flat_indices[group_pos]
            if eval_mask[row_idx]:
                alpha_day[pos] = alpha[row_idx]
                target_day[pos] = target[row_idx]
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
    date_flat_indices, date_group_offsets = _ensure_date_group_index(features)
    daily_ics = _numba_daily_ics(
        np.asarray(alpha, dtype=np.float64),
        np.asarray(target, dtype=np.float64),
        date_flat_indices,
        date_group_offsets,
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
    cached = _feature_cache_get(features, TARGET_NEUTRALIZED_CACHE_KEY, fold_cache_key)
    if cached is not None:
        return cached
    neutralized = ge._neutralize_cross_section(
        target_fold,
        fold_features.get("__log_market_cap__"),
        fold_features.get("__sector__"),
        fold_features.get("__date__"),
        neutralization_cache=fold_features.get(ge.NEUTRALIZATION_CACHE_KEY),
    )
    _feature_cache_set(features, TARGET_NEUTRALIZED_CACHE_KEY, fold_cache_key, neutralized)
    return neutralized


def _execute_tree_for_batch(individual: ge.GPIndividual, features: dict[str, np.ndarray]) -> np.ndarray:
    return individual._execute_tree(individual.tree, features)


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
        _ensure_neutralization_jit_context(eval_features)
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
    cached_fold_features = features.get(FOLD_FEATURES_CACHE_KEY)
    for fold_idx, (fold_mask, _fold_dates) in enumerate(fold_structure):
        if cached_fold_features is not None and fold_idx < len(cached_fold_features):
            fold_features = cached_fold_features[fold_idx]
        else:
            fold_features = _slice_row_aligned_features(features, fold_mask)
            if "__date__" in fold_features:
                _ensure_date_group_index(fold_features)
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
        context = _get_vm_context(features)
        # Use content-based fingerprint instead of object ID to prevent cache aliasing
        if context is not None:
            cache_token = int(context["cache_token"])
        else:
            cache_token = _compute_feature_fingerprint(features)
        cache_key = (cache_token, node.to_string())
        cached = _feature_cache_get(features, SUBTREE_CACHE_KEY, cache_key)
        if cached is not None:
            return cached.copy()
        result: np.ndarray | None = None
        if context is not None:
            program = _get_vm_program(node, context["feature_names"], features)
            if program is not None:
                opcodes, operands, const_values = program
                stack = _get_thread_local_stack(context["row_count"])
                result = _numba_execute_rpn(
                    opcodes,
                    operands,
                    const_values,
                    context["feature_matrix"],
                    context["ticker_group_offsets"],
                    context["date_flat_indices"],
                    context["date_group_offsets"],
                    stack,
                )
        if result is None:
            result = super()._execute_tree(node, features)
        _feature_cache_set(features, SUBTREE_CACHE_KEY, cache_key, np.asarray(result, dtype=np.float64).copy())
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
        if (self.config.use_fast_penalties or self.config.use_time_fold_ir) and "__date__" in gen_features:
            if gen_features is features:
                gen_features = dict(gen_features)
            gen_features[ge.FOLD_STRUCTURE_CACHE_KEY] = self._get_cached_fold_structure(gen_features["__date__"])
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
            _ensure_neutralization_jit_context(gen_features)
        if self.config.use_time_fold_ir and "__date__" in gen_features:
            if gen_features is features:
                gen_features = dict(gen_features)
            fold_structure = gen_features.get(ge.FOLD_STRUCTURE_CACHE_KEY)
            if fold_structure is None:
                fold_count = 2 if getattr(self.config, "time_folds_fast_mode", False) else int(self.config.time_folds)
                fold_structure = ge._build_time_fold_structure(np.asarray(gen_features["__date__"]), fold_count)
                gen_features[ge.FOLD_STRUCTURE_CACHE_KEY] = fold_structure
            fold_count = 2 if getattr(self.config, "time_folds_fast_mode", False) else int(self.config.time_folds)
            fold_features = self._fold_features_cache.get((id(gen_features["__date__"]), fold_count))
            if fold_features is None and gen_features is features:
                fold_features = _build_cached_fold_features(gen_features, fold_structure)
                self._fold_features_cache[(id(gen_features["__date__"]), fold_count)] = fold_features
            if fold_features is not None:
                gen_features[FOLD_FEATURES_CACHE_KEY] = fold_features
        return gen_features, gen_target

    def _evaluate_population_with_batch_neutralization(self, features: dict[str, np.ndarray], target: np.ndarray) -> None:
        batch_size = max(1, int(getattr(self.config, "batch_fitness_size", BATCH_FITNESS_SIZE)))
        use_threaded_tree_eval = int(getattr(self.config, "n_jobs", 1) or 1) > 1
        for start in range(0, len(self.population), batch_size):
            batch = self.population[start:start + batch_size]
            try:
                if use_threaded_tree_eval:
                    raw_columns = ge.Parallel(
                        n_jobs=self.config.n_jobs,
                        batch_size="auto",
                        prefer="threads",
                    )(
                        ge.delayed(_execute_tree_for_batch)(ind, features) for ind in batch
                    )
                else:
                    raw_columns = [ind._execute_tree(ind.tree, features) for ind in batch]
                raw_alpha = np.column_stack(raw_columns)
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
                active_index_lookup = {int(idx): pos for pos, idx in enumerate(active_indices)}
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
                    neutralized_idx = active_index_lookup[local_idx]
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
            self.population = list(ge.Parallel(n_jobs=self.config.n_jobs, batch_size="auto", prefer="threads")(
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
        self._fold_features_cache = {}
        self.feature_names = [k for k in features.keys() if not k.startswith("target") and not k.startswith("__")]
        logger = ge.logger
        logger.info(f"Starting GP evolution V4 advanced: pop={self.config.population_size}, gen={self.config.generations}")
        self.initialize_population()
        island_count = max(1, int(getattr(self.config, "island_count", ISLAND_COUNT)))
        islands = [list(chunk.tolist()) for chunk in np.array_split(np.asarray(self.population, dtype=object), island_count) if len(chunk) > 0]
        t_start = pytime.monotonic()
        best_fitness_seen = -np.inf
        stagnant_generations = 0
        try:
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
                    gc.collect()
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
                gc.collect()
        finally:
            self._fold_features_cache.clear()
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
        ".ly_state/session/gp_numba_jit_vm_plan.md",
        "scripts/genetic_alpha_evolution_v4.py",
        "tests/test_gp_numba_jit_vm.py",
    ]
    lines = [
        "# L2 Report - GP Numba JIT VM Implementation",
        "",
        "- Session: `l2_role16_gp_numba_jit_vm_implementation_20260705`",
        "- Gate: `GP_NUMBA_JIT_VM_IMPLEMENTATION`",
        "- Role: `16 machine-learning-engineer`",
        "- Scope: `scripts/genetic_alpha_evolution_v4.py`, `tests/test_gp_numba_jit_vm.py`",
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
