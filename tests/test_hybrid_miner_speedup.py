from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import spearmanr

from omega.quant.evolution.hybrid_alpha_miner import _spearman_corr_via_ranks


@pytest.mark.parametrize(
    "left,right",
    [
        (np.array([1.0, 2.0, 2.0, 4.0]), np.array([4.0, 1.0, 1.0, 3.0])),
        (np.array([1.0, 2.0, 3.0]), np.array([3.0, 2.0, 1.0])),
        (np.array([1.0, 2.0, np.nan, 4.0]), np.array([4.0, 1.0, 3.0, 2.0])),
    ],
)
def test_rank_correlation_matches_scipy(left: np.ndarray, right: np.ndarray) -> None:
    valid = np.isfinite(left) & np.isfinite(right)
    expected, _ = spearmanr(left[valid], right[valid])

    actual = _spearman_corr_via_ranks(left[valid], right[valid])

    assert actual == pytest.approx(expected)


def test_rank_correlation_returns_nan_for_constant_input() -> None:
    actual = _spearman_corr_via_ranks(
        np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]),
    )

    expected, _ = spearmanr(
        np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]),
    )
    assert np.isnan(actual)
    assert np.isnan(expected)


def test_rank_correlation_preserves_unequal_length_value_error() -> None:
    left = np.array([1.0, 2.0, 3.0])
    right = np.array([1.0, 2.0])

    with pytest.raises(ValueError):
        spearmanr(left, right)
    with pytest.raises(ValueError):
        _spearman_corr_via_ranks(left, right)
