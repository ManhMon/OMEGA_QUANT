"""
Embargo & Purging Cross-Validation for V21 Quant System.

Implements walk-forward CV with:
- Embargo: Gap after test set to avoid autocorrelation leak
- Purging: Remove data near split points to prevent information leakage

Based on: López de Prado, M. (2018). Advances in Financial Machine Learning.

Author: V21 Institutional Grade Layer 01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple, Union

import numpy as np


@dataclass
class CVSplit:
    """Single cross-validation split with train/test indices."""
    train_idx: np.ndarray
    test_idx: np.ndarray
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_start: int
    embargo_end: int


class EmbargoedPurgingCV:
    """Walk-forward cross-validation with embargo and purging.
    
    Prevents data leakage in financial time series by:
    1. Purging: Removing training samples that overlap with test period
    2. Embargo: Adding gap after test period before next training
    
    Typical settings:
    - embargo_days: 5 (avoid autocorrelation leak)
    - purge_days: 2 (remove data in [-2, +2] days around split)
    """
    
    def __init__(
        self,
        n_splits: int = 5,
        embargo_days: int = 5,
        purge_days: int = 2,
        test_size: Optional[float] = None,
        min_train_size: int = 60
    ):
        """Initialize cross-validator.
        
        Args:
            n_splits: Number of walk-forward splits
            embargo_days: Number of days gap after test set
            purge_days: Number of days to purge around split point
            test_size: Fraction of data for each test fold (default: 1/n_splits)
            min_train_size: Minimum training samples required
        """
        if n_splits < 2:
            raise ValueError(f"n_splits must be >= 2, got {n_splits}")
        if embargo_days < 0:
            raise ValueError(f"embargo_days must be >= 0, got {embargo_days}")
        if purge_days < 0:
            raise ValueError(f"purge_days must be >= 0, got {purge_days}")
        
        self.n_splits = n_splits
        self.embargo_days = embargo_days
        self.purge_days = purge_days
        self.test_size = test_size if test_size is not None else 1.0 / n_splits
        self.min_train_size = min_train_size
    
    def split(
        self,
        X: Union[np.ndarray, List],
        y: Union[np.ndarray, List],
        timestamps: Optional[np.ndarray] = None
    ) -> Iterator[CVSplit]:
        """Generate walk-forward splits with embargo and purging.
        
        Args:
            X: Feature array (n_samples, n_features) or list
            y: Target array (n_samples,) or list
            timestamps: Optional array of timestamps for date-based purging
            
        Yields:
            CVSplit objects with train/test indices
        """
        n_samples = len(X) if hasattr(X, '__len__') else len(list(X))
        
        if n_samples < self.min_train_size + 10:
            raise ValueError(
                f"Not enough samples: {n_samples} < min_train_size + 10"
            )
        
        # Calculate fold size
        test_size = max(1, int(n_samples * self.test_size))
        
        # Generate split points
        # Start test set after min_train_size, end before last test_size samples
        available_for_splits = n_samples - self.min_train_size - test_size
        
        if available_for_splits < test_size * (self.n_splits - 1):
            # Adjust n_splits if not enough data
            actual_splits = max(2, available_for_splits // test_size)
        else:
            actual_splits = self.n_splits
        
        step = available_for_splits // actual_splits
        
        for i in range(actual_splits):
            # Test set boundaries
            test_start = self.min_train_size + i * step
            test_end = test_start + test_size
            
            if test_end > n_samples:
                break
            
            # Purge: remove training samples within purge_days of test period
            # Convert days to sample indices (assuming daily data: 1 day = 1 sample)
            purge_start = max(0, test_start - self.purge_days)
            purge_end = min(n_samples, test_end + self.purge_days)
            
            # Training set: everything before purge_start
            train_start = 0
            train_end = purge_start
            
            if train_end - train_start < self.min_train_size:
                continue  # Skip if not enough training data
            
            # Embargo: gap after test set (for next fold's training)
            embargo_start = test_end
            embargo_end = min(n_samples, test_end + self.embargo_days)
            
            # Create index arrays
            train_idx = np.arange(train_start, train_end)
            test_idx = np.arange(test_start, test_end)
            
            yield CVSplit(
                train_idx=train_idx,
                test_idx=test_idx,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
            )
    
    def split_with_indices(
        self,
        X: Union[np.ndarray, List],
        y: Union[np.ndarray, List],
        timestamps: Optional[np.ndarray] = None
    ) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """Simplified interface yielding just (train_idx, test_idx) tuples.
        
        Args:
            X: Feature array
            y: Target array
            timestamps: Optional timestamps
            
        Yields:
            (train_idx, test_idx) tuples
        """
        for cv_split in self.split(X, y, timestamps):
            yield cv_split.train_idx, cv_split.test_idx
    
    def get_n_splits(
        self,
        X: Union[np.ndarray, List],
        y: Optional[Union[np.ndarray, List]] = None,
        groups: Optional[np.ndarray] = None
    ) -> int:
        """Return number of splits.
        
        Args:
            X: Feature array (used to determine n_splits)
            y: Target array (unused, for sklearn compatibility)
            groups: Group labels (unused, for sklearn compatibility)
            
        Returns:
            Number of splits
        """
        n_samples = len(X) if hasattr(X, '__len__') else len(list(X))
        test_size = max(1, int(n_samples * self.test_size))
        available = n_samples - self.min_train_size - test_size
        
        if available < test_size:
            return 1
        
        return max(2, min(self.n_splits, available // test_size))


class PurgingKFold:
    """K-fold CV with purging for financial data.
    
    Similar to EmbargoedPurgingCV but uses K-fold style splits
    instead of walk-forward. Less common for time series but
    useful for certain applications.
    """
    
    def __init__(
        self,
        n_splits: int = 5,
        purge_days: int = 2,
        shuffle: bool = False
    ):
        """Initialize purging K-fold.
        
        Args:
            n_splits: Number of folds
            purge_days: Days to purge around test fold
            shuffle: Whether to shuffle before splitting (usually False for time series)
        """
        if n_splits < 2:
            raise ValueError(f"n_splits must be >= 2, got {n_splits}")
        
        self.n_splits = n_splits
        self.purge_days = purge_days
        self.shuffle = shuffle
    
    def split(
        self,
        X: Union[np.ndarray, List],
        y: Union[np.ndarray, List],
        timestamps: Optional[np.ndarray] = None
    ) -> Iterator[CVSplit]:
        """Generate K-fold splits with purging.
        
        Args:
            X: Feature array
            y: Target array
            timestamps: Optional timestamps
            
        Yields:
            CVSplit objects with train/test indices
        """
        n_samples = len(X) if hasattr(X, '__len__') else len(list(X))
        fold_size = n_samples // self.n_splits
        
        indices = np.arange(n_samples)
        if self.shuffle:
            np.random.shuffle(indices)
        
        for i in range(self.n_splits):
            # Test fold
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_splits - 1 else n_samples
            
            test_idx = indices[test_start:test_end]
            
            # Purge: remove samples near test fold boundaries
            purge_start = max(0, test_start - self.purge_days)
            purge_end = min(n_samples, test_end + self.purge_days)
            
            # Train: everything except test and purge regions
            train_idx = np.concatenate([
                indices[:purge_start],
                indices[purge_end:]
            ])
            
            if len(train_idx) < 10:
                continue
            
            yield CVSplit(
                train_idx=train_idx,
                test_idx=test_idx,
                train_start=0,
                train_end=purge_start,
                test_start=test_start,
                test_end=test_end,
                embargo_start=test_end,
                embargo_end=test_end,
            )


def validate_no_leak(
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    timestamps: np.ndarray,
    purge_days: int = 2
) -> bool:
    """Validate that there's no data leakage between train and test.
    
    Args:
        train_idx: Training indices
        test_idx: Test indices
        timestamps: Array of timestamps
        purge_days: Expected purge window
        
    Returns:
        True if no leakage detected
    """
    if len(train_idx) == 0 or len(test_idx) == 0:
        return True
    
    train_times = timestamps[train_idx]
    test_times = timestamps[test_idx]
    
    # Check temporal order
    max_train = np.max(train_times)
    min_test = np.min(test_times)
    
    # With purging, there should be a gap
    if max_train >= min_test:
        return False
    
    return True
