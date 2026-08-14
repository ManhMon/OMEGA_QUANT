import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from omega.quant.evolution.genetic_engine import (
    _spearman_corr_via_corrcoef,
    _ts_max,
    _ts_mean,
    _ts_min,
    _ts_std,
)


@pytest.mark.parametrize("window", [3, 10, 20])
def test_ts_std_matches_pandas_ddof_one(window):
    values = np.array([1.0, np.nan, 3.0, 3.0, 5.0, np.inf, 7.0, 8.0])
    expected = pd.Series(values).rolling(window).std().fillna(0.0).to_numpy()
    np.testing.assert_allclose(_ts_std(values, window), expected, equal_nan=True)


@pytest.mark.parametrize("function", [_ts_mean, _ts_max, _ts_min])
def test_ts_rolling_functions_match_pandas(function):
    values = np.array([1.0, np.nan, 3.0, 3.0, 5.0, np.inf, 7.0, 8.0])
    window = 3
    pandas_function = {"_ts_mean": "mean", "_ts_max": "max", "_ts_min": "min"}[function.__name__]
    expected = getattr(pd.Series(values).rolling(window), pandas_function)().fillna(0.0).to_numpy()
    np.testing.assert_allclose(function(values, window), expected, equal_nan=True)


@pytest.mark.parametrize("window", [3, 20])
def test_ts_functions_short_and_constant_inputs(window):
    short = np.ones(window - 1)
    constant = np.ones(window + 2)
    for function in (_ts_std, _ts_mean, _ts_max, _ts_min):
        assert np.array_equal(function(short, window), np.zeros_like(short))
        expected = getattr(pd.Series(constant).rolling(window), {
            "_ts_std": "std", "_ts_mean": "mean", "_ts_max": "max", "_ts_min": "min"
        }[function.__name__])().fillna(0.0).to_numpy()
        np.testing.assert_allclose(function(constant, window), expected)


@pytest.mark.parametrize(
    "a,b",
    [
        (np.array([3.0, np.nan, 1.0, 2.0]), np.array([30.0, 99.0, 10.0, 20.0])),
        (np.array([1.0, 2.0, 2.0, 4.0]), np.array([4.0, 1.0, 1.0, 3.0])),
        (np.array([1.0, 2.0]), np.array([2.0])),
        (np.ones(4), np.arange(4.0)),
    ],
)
def test_spearman_via_corrcoef_matches_scipy(a, b):
    span = min(len(a), len(b))
    expected = spearmanr(a[:span], b[:span], nan_policy="omit")[0]
    actual = _spearman_corr_via_corrcoef(a, b)
    assert actual == pytest.approx(expected, abs=1e-12, rel=1e-12) if np.isfinite(expected) else np.isnan(actual)


def test_spearman_via_corrcoef_requires_two_finite_pairs():
    assert np.isnan(_spearman_corr_via_corrcoef(np.array([1.0, np.nan]), np.array([1.0, 2.0])))
