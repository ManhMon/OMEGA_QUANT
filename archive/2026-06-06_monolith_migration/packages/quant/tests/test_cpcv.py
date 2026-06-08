"""Tests for Combinatorial Purged K-Fold (CPCV)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Bypass namespace shadow (src/omega/quant/ vs packages/quant/src/omega/quant/)
_CPCV_PATH = REPO_ROOT / "packages" / "quant" / "src" / "omega" / "quant" / "validation" / "cpcv.py"
_spec = importlib.util.spec_from_file_location("_cpcv_under_test", str(_CPCV_PATH))
_cpcv_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cpcv_mod)

CombinatorialPurgedKFold = _cpcv_mod.CombinatorialPurgedKFold
purge_train_indices = _cpcv_mod.purge_train_indices


def _ts(n: int) -> pd.Series:
    return pd.Series(pd.date_range("2020-01-01", periods=n, freq="B"))


# ---------------------------------------------------------------------
# Init validation
# ---------------------------------------------------------------------
def test_invalid_n_splits():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=2)


def test_invalid_n_test_splits():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=10, n_test_splits=10)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=10, n_test_splits=0)


def test_invalid_embargo_pct():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(embargo_pct=1.0)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(embargo_pct=-0.1)


def test_invalid_label_horizon():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(label_horizon=0)


# ---------------------------------------------------------------------
# Combinatorial structure
# ---------------------------------------------------------------------
def test_n_folds_equals_combinations():
    cpcv = CombinatorialPurgedKFold(n_splits=10, n_test_splits=2)
    assert cpcv.get_n_folds() == 45  # C(10, 2)

    cpcv2 = CombinatorialPurgedKFold(n_splits=6, n_test_splits=2)
    assert cpcv2.get_n_folds() == 15  # C(6, 2)


def test_split_yields_unique_test_sets():
    cpcv = CombinatorialPurgedKFold(
        n_splits=6, n_test_splits=2, embargo_pct=0.0, label_horizon=1
    )
    folds = list(cpcv.split(_ts(600)))
    test_signatures = {tuple(np.sort(test_idx)) for _, test_idx in folds}
    assert len(test_signatures) == cpcv.get_n_folds()


def test_split_train_test_disjoint():
    cpcv = CombinatorialPurgedKFold(
        n_splits=10, n_test_splits=2, embargo_pct=0.01, label_horizon=5
    )
    for tr, te in cpcv.split(_ts(1000)):
        assert len(np.intersect1d(tr, te)) == 0


# ---------------------------------------------------------------------
# Purge correctness
# ---------------------------------------------------------------------
def test_purge_drops_overlapping_label_windows():
    """Train sample at t=95 has label window [95, 100]; test at [100, 105]
    must remove it."""
    ts = _ts(200)
    train_idx = np.arange(0, 100, dtype=np.int64)
    test_idx = np.arange(100, 110, dtype=np.int64)

    purged = purge_train_indices(train_idx, test_idx, ts, label_horizon=5)
    # Samples at 95, 96, 97, 98, 99 leak (their +5 window touches test).
    assert 95 not in purged
    assert 99 not in purged
    # Sample at 94 has window ending at 99 → just touches test_min=100? No: 94+5=99 < 100, safe.
    assert 94 in purged


def test_purge_no_op_when_far_apart():
    ts = _ts(200)
    train_idx = np.arange(0, 50, dtype=np.int64)
    test_idx = np.arange(150, 160, dtype=np.int64)

    purged = purge_train_indices(train_idx, test_idx, ts, label_horizon=5)
    np.testing.assert_array_equal(purged, train_idx)


# ---------------------------------------------------------------------
# Embargo
# ---------------------------------------------------------------------
def test_embargo_blocks_post_test_train():
    cpcv = CombinatorialPurgedKFold(
        n_splits=5, n_test_splits=1, embargo_pct=0.02, label_horizon=1
    )
    folds = list(cpcv.split(_ts(1000)))
    # First fold: test = [0..199], train = [200..999], embargo = 20 bars.
    # Train samples 200..219 must be dropped.
    tr, te = folds[0]
    assert te.min() == 0 and te.max() == 199
    assert 220 in tr
    for forbidden in range(200, 220):
        assert forbidden not in tr, f"embargo failed at {forbidden}"


# ---------------------------------------------------------------------
# Real-world sanity
# ---------------------------------------------------------------------
def test_realistic_5y_daily_bars():
    """5 years of daily VN data."""
    ts = _ts(1250)
    cpcv = CombinatorialPurgedKFold(
        n_splits=10, n_test_splits=2, embargo_pct=0.01, label_horizon=5
    )
    folds = list(cpcv.split(ts))
    assert len(folds) >= 40, f"expected >=40 folds, got {len(folds)}"
    for tr, te in folds:
        assert len(tr) > 0 and len(te) > 0
        # No overlap with embargo zone
        assert len(np.intersect1d(tr, te)) == 0


def test_integer_timestamps_supported():
    ts = pd.Series(np.arange(500))
    cpcv = CombinatorialPurgedKFold(
        n_splits=5, n_test_splits=1, embargo_pct=0.01, label_horizon=3
    )
    folds = list(cpcv.split(ts))
    assert len(folds) == 5


# ---------------------------------------------------------------------
# Bidirectional purge regression (audit P1-A fix)
# ---------------------------------------------------------------------
def test_purge_bidirectional_post_test_block():
    """After AFML fix: train at i in (hi, hi+horizon] must be purged
    because its label window [i, i+h] overlaps test labels [hi, hi+h]."""
    ts = _ts(200)
    train_idx = np.arange(100, 200, dtype=np.int64)  # all train AFTER test
    test_idx = np.arange(50, 100, dtype=np.int64)    # test = [50, 99]

    purged = purge_train_indices(train_idx, test_idx, ts, label_horizon=5)
    # Train at 100, 101, 102, 103, 104 has label window touching
    # the same forward-return regime as test sample 99 (window [99, 104]).
    # All five MUST be purged.
    for forbidden in (100, 101, 102, 103, 104):
        assert forbidden not in purged, f"P1-A leak at {forbidden}"
    # Train at 105 has label window [105, 110] — safe.
    assert 105 in purged


def test_purge_rejects_unsorted_timestamps():
    ts_unsorted = pd.Series(pd.date_range("2020-01-01", periods=100, freq="B")[::-1])
    train_idx = np.arange(0, 50, dtype=np.int64)
    test_idx = np.arange(60, 70, dtype=np.int64)
    with pytest.raises(ValueError, match="sorted"):
        purge_train_indices(train_idx, test_idx, ts_unsorted, label_horizon=5)
