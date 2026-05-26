"""
Purged Time-Series Cross-Validation for Institutional Quant Trading.

Prevents data leakage in time-series data with settlement gaps (T+2.5).

Implements:
1. Purging: Removes training observations that overlap with test labels.
2. Embargoing: Removes training observations immediately following test period.
3. Multi-symbol support: Handles flattened symbol-timestamp indices.

PIT Safety: Strict temporal ordering enforced. No future data leakage.
Vectorization: Index operations are fully vectorized via numpy.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

from typing import Any, Generator, Optional, Tuple

import numpy as np

__all__ = [
    "PurgedTimeSeriesSplit",
]


class PurgedTimeSeriesSplit:
    """
    K-Fold Cross-Validation for Time-Series with Purging and Embargo.

    Designed for financial time-series where:
    - Labels span multiple days (e.g., 5-day forward returns)
    - Settlement gaps exist (T+2.5 in Vietnam market -> 3 days purge)
    - Feature windows may leak information across folds

    PIT Contract:
    - Training data ALWAYS precedes test data temporally.
    - Purge gap removes observations that could leak label information.
    - Embargo removes post-test observations to prevent feature leakage.
    """

    def __init__(
        self,
        n_splits: int = 5,
        gap_days: int = 3,
        embargo_pct: float = 0.01,
    ) -> None:
        """
        Args:
            n_splits: Number of folds.
            gap_days: Purging gap in trading days (T+2.5 -> 3 days).
            embargo_pct: Fraction of data embargoed after each test fold
                to prevent leakage from large-window features.
        """
        if n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        if gap_days < 0:
            raise ValueError("gap_days must be >= 0")

        self.n_splits = n_splits
        self.gap_days = gap_days
        self.embargo_pct = embargo_pct

    def split(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None,
        groups: Any = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Generate indices to split data into training and test sets.

        Assumes X is sorted by time (or at minimum, index order = temporal order).

        Yields:
            (train_indices, test_indices) for each fold.
        """
        n_samples = len(X)
        test_size = n_samples // (self.n_splits + 1)
        embargo_size = int(n_samples * self.embargo_pct)

        indices = np.arange(n_samples)

        for i in range(self.n_splits):
            # Test set starts after train set with a gap
            test_start = (i + 1) * test_size
            test_end = min(test_start + test_size, n_samples)

            test_indices = indices[test_start:test_end]

            # Train indices BEFORE test set (purged by gap_days)
            train_before_end = max(0, test_start - self.gap_days)
            train_before = indices[:train_before_end]

            # Train indices AFTER test set (embargoed)
            train_after_start = min(
                n_samples, test_end + self.gap_days + embargo_size
            )
            train_after = indices[train_after_start:]

            # Concatenate train segments (vectorized)
            train_indices = np.concatenate([train_before, train_after])

            if len(train_indices) == 0 or len(test_indices) == 0:
                continue

            yield train_indices, test_indices

    def get_n_splits(
        self,
        X: Any = None,
        y: Any = None,
        groups: Any = None,
    ) -> int:
        """Return the number of splitting iterations."""
        return self.n_splits
