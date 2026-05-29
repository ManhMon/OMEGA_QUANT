"""
Combinatorial Purged Cross-Validation (CPCV)
=============================================

Lopez de Prado, "Advances in Financial Machine Learning" (2018), Ch. 7.

Standard k-fold CV LEAKS in time-series finance because:
1. Sample labels overlap (e.g. 5-day forward return uses t..t+5 prices).
   → Train sample at t-1 sees future info if test contains t+3.
2. Same return event drives auto-correlation across nearby samples.
   → Train and test are NOT i.i.d.

CPCV fixes this with three ideas:
- N splits the data into N contiguous groups.
- k test groups per fold (giving C(N,k) folds; N=10, k=2 → 45 folds).
- For each fold:
    * Purge: drop train samples whose label horizon overlaps with test.
    * Embargo: drop train samples within `embargo_pct` AFTER test end
      (intra-day microstructure decay).

This produces a deflated, robust OOS estimate that is closer to live
performance and supports Deflated Sharpe Ratio (DSR) statistical tests.

PIT Safety:
- All splits are time-ordered (no shuffling).
- Purge horizon ≥ label_horizon ensures no look-ahead.
- Embargo blocks information leakage from test → train neighbors.

Usage:
    cpcv = CombinatorialPurgedKFold(
        n_splits=10, n_test_splits=2,
        embargo_pct=0.01, label_horizon=5
    )
    for fold, (train_idx, test_idx) in enumerate(cpcv.split(timestamps)):
        ...

Version: 1.0.0 (Phase 3.1, OMEGA next-gen)
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterator, List, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = ["CombinatorialPurgedKFold", "purge_train_indices"]


def purge_train_indices(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    timestamps: pd.Series,
    label_horizon: int,
) -> np.ndarray:
    """
    Remove train samples whose [t, t+label_horizon] window overlaps with
    any contiguous test block. Vectorized per block to avoid spuriously
    purging the entire train when test groups are non-contiguous.

    Args:
        train_idx: candidate train integer indices
        test_idx:  test integer indices (any order)
        timestamps: pandas Series of bar timestamps (must be sorted);
            kept for API stability, position-based purge below.
        label_horizon: forward bars used by label (e.g. 5 for 5-day return)

    Returns:
        purged train_idx (subset of input, original order preserved)
    """
    if len(train_idx) == 0 or len(test_idx) == 0:
        return train_idx

    _ = timestamps  # position-based; kept for API
    # Identify contiguous blocks in test_idx.
    test_sorted = np.sort(test_idx)
    breaks = np.where(np.diff(test_sorted) > 1)[0]
    block_starts = np.concatenate([[test_sorted[0]], test_sorted[breaks + 1]])
    block_ends = np.concatenate([test_sorted[breaks], [test_sorted[-1]]])

    # Drop train samples that overlap with ANY contiguous test block.
    drop_mask = np.zeros(len(train_idx), dtype=bool)
    for lo, hi in zip(block_starts, block_ends):
        # train at i leaks if i <= hi AND i + horizon >= lo
        block_mask = (train_idx <= hi) & (train_idx + label_horizon >= lo)
        drop_mask |= block_mask

    return train_idx[~drop_mask]


def _embargo_indices(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    timestamps: pd.Series,
    embargo_pct: float,
) -> np.ndarray:
    """
    Drop train samples within `embargo_pct * len(timestamps)` bars AFTER
    each contiguous test block. Lopez de Prado §7.4.
    """
    if embargo_pct <= 0 or len(train_idx) == 0 or len(test_idx) == 0:
        return train_idx

    n = len(timestamps)
    embargo_bars = max(1, int(np.ceil(embargo_pct * n)))

    # Find contiguous test blocks (sorted)
    test_sorted = np.sort(test_idx)
    blocks: List[Tuple[int, int]] = []
    start = test_sorted[0]
    prev = test_sorted[0]
    for idx in test_sorted[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            blocks.append((start, prev))
            start = idx
            prev = idx
    blocks.append((start, prev))

    # Embargo zone = (block_end, block_end + embargo_bars]
    embargo_set = set()
    for _, end in blocks:
        for k in range(1, embargo_bars + 1):
            embargo_set.add(end + k)

    keep_mask = np.array([i not in embargo_set for i in train_idx])
    return train_idx[keep_mask]


class CombinatorialPurgedKFold:
    """
    Combinatorial Purged K-Fold (CPCV) per Lopez de Prado.

    Args:
        n_splits: total contiguous time groups (e.g. 10).
        n_test_splits: groups assigned to test per fold (e.g. 2).
            Yields C(n_splits, n_test_splits) folds = 45 for (10, 2).
        embargo_pct: fraction of total samples to embargo after test
            (Lopez recommends 0.01 = 1%).
        label_horizon: forward-return horizon in bars used for label
            (e.g. 5 for 5-day return). Required to purge leakage.

    Note: this splitter is time-ordered (no shuffling). Caller must pass
    timestamps sorted ascending.
    """

    def __init__(
        self,
        n_splits: int = 10,
        n_test_splits: int = 2,
        embargo_pct: float = 0.01,
        label_horizon: int = 5,
    ) -> None:
        if n_splits < 3:
            raise ValueError("n_splits must be >= 3")
        if n_test_splits < 1 or n_test_splits >= n_splits:
            raise ValueError("n_test_splits must be in [1, n_splits-1]")
        if embargo_pct < 0 or embargo_pct >= 1:
            raise ValueError("embargo_pct must be in [0, 1)")
        if label_horizon < 1:
            raise ValueError("label_horizon must be >= 1")

        self.n_splits = n_splits
        self.n_test_splits = n_test_splits
        self.embargo_pct = embargo_pct
        self.label_horizon = label_horizon

    def get_n_folds(self) -> int:
        from math import comb
        return comb(self.n_splits, self.n_test_splits)

    def split(
        self,
        timestamps: Sequence,
    ) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate (train_idx, test_idx) pairs.

        Args:
            timestamps: pd.Series or array-like of bar timestamps,
                sorted ascending. Length = n_samples.

        Yields:
            (train_idx, test_idx) integer index arrays.
        """
        ts = pd.Series(timestamps).reset_index(drop=True)
        n = len(ts)
        if n < self.n_splits:
            raise ValueError(f"n_samples ({n}) < n_splits ({self.n_splits})")

        # Contiguous group boundaries
        group_size = n // self.n_splits
        groups: List[np.ndarray] = []
        for g in range(self.n_splits):
            lo = g * group_size
            hi = (g + 1) * group_size if g < self.n_splits - 1 else n
            groups.append(np.arange(lo, hi, dtype=np.int64))

        # All combinations of k test groups
        for test_groups in combinations(range(self.n_splits), self.n_test_splits):
            test_idx = np.concatenate([groups[g] for g in test_groups])
            test_idx.sort()

            train_groups = [g for g in range(self.n_splits) if g not in test_groups]
            train_idx = np.concatenate([groups[g] for g in train_groups])
            train_idx.sort()

            # Purge: drop train samples whose label window overlaps test
            train_idx = purge_train_indices(
                train_idx, test_idx, ts, self.label_horizon
            )
            # Embargo: drop train within embargo_pct after each test block
            train_idx = _embargo_indices(
                train_idx, test_idx, ts, self.embargo_pct
            )

            if len(train_idx) == 0:
                continue
            yield train_idx, test_idx
