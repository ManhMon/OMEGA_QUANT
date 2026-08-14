import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from omega.quant.evolution.genetic_programming import _decay_linear, _ts_rank


def _pandas_ts_rank(x: np.ndarray, window: int) -> np.ndarray:
    return pd.Series(x).rolling(window).apply(
        lambda values: pd.Series(values).rank(pct=True).iloc[-1]
    ).fillna(0.0).to_numpy()


def _pandas_decay_linear(x: np.ndarray, window: int) -> np.ndarray:
    weights = np.arange(1, window + 1, dtype=float)
    return pd.Series(x).rolling(window).apply(
        lambda values: np.dot(values, weights) / weights.sum()
    ).fillna(0.0).to_numpy()


def test_ts_rank_matches_pandas_for_normal_values_and_ties():
    for values in (
        np.array([4.0, 1.0, 3.0, 2.0, 5.0, 2.0]),
        np.array([1.0, 2.0, 2.0, 3.0, 2.0]),
    ):
        np.testing.assert_allclose(_ts_rank(values, 3), _pandas_ts_rank(values, 3), atol=1e-10)


def test_ts_rank_masks_nan_windows_and_short_arrays():
    values = np.array([1.0, np.nan, 3.0, 4.0, 5.0, np.nan])
    np.testing.assert_allclose(_ts_rank(values, 3), _pandas_ts_rank(values, 3), atol=1e-10)
    np.testing.assert_array_equal(_ts_rank(np.array([np.nan, np.nan, 1.0]), 2), np.zeros(3))
    np.testing.assert_array_equal(_ts_rank(np.array([1.0, 2.0]), 3), np.zeros(2))


def test_decay_linear_matches_pandas_for_normal_values_and_nan_windows():
    for values in (
        np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        np.array([1.0, np.nan, 3.0, 4.0, 5.0, np.nan]),
    ):
        np.testing.assert_allclose(
            _decay_linear(values, 3), _pandas_decay_linear(values, 3), atol=1e-10
        )


def test_decay_linear_masks_all_nan_windows_and_short_arrays():
    np.testing.assert_array_equal(
        _decay_linear(np.array([np.nan, np.nan, np.nan, 1.0]), 2),
        np.zeros(4),
    )
    np.testing.assert_array_equal(_decay_linear(np.array([1.0, 2.0]), 3), np.zeros(2))


def test_diversity_corr_parity():
    for values in (
        (np.arange(1.0, 121.0), np.arange(120.0, 0.0, -1.0)),
        (
            np.array([1.0, np.nan, 3.0, 4.0, np.nan, 6.0] * 26),
            np.array([6.0, 5.0, np.nan, 3.0, 2.0, np.nan] * 26),
        ),
    ):
        alpha, hof_alpha = values
        mask = ~(np.isnan(alpha) | np.isnan(hof_alpha))
        actual = np.corrcoef(
            rankdata(alpha[mask]),
            rankdata(hof_alpha[mask]),
        )[0, 1]
        expected = spearmanr(alpha[mask], hof_alpha[mask]).correlation
        np.testing.assert_allclose(actual, expected, atol=1e-10)
