import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from omega.quant.evolution import genetic_programming as gp


def test_rank_node_no_series_alloc(monkeypatch):
    values = np.array([3.0, 1.0, 2.0, 2.0, 5.0], dtype=float)
    expected = pd.Series(values).rank(pct=True, method="average").to_numpy()

    original_series = gp.pd.Series

    def guard_series(*args, **kwargs):
        if args and isinstance(args[0], np.ndarray) and np.array_equal(args[0], values):
            raise AssertionError("rank path allocated pandas Series")
        return original_series(*args, **kwargs)

    monkeypatch.setattr(gp.pd, "Series", guard_series)

    actual = gp._rank_transform(values)

    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-8)


def test_rank_nan_parity():
    values = np.array([1.0, np.nan, 3.0, 2.0], dtype=float)

    actual = gp._rank_transform(values)
    expected = pd.Series(values).rank(pct=True, method="average").to_numpy()

    assert np.isnan(actual[1])
    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-8, equal_nan=True)


def test_rolling_mean_matches_pandas():
    values = np.array([1.0, 4.0, 2.0, 8.0, 16.0, 32.0], dtype=float)
    actual = gp._ts_mean(values, window=3)
    expected = pd.Series(values).rolling(3).mean().fillna(0.0).to_numpy()

    np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-8)


def test_cached_mask_corr_matches_spearmanr():
    signal = np.array([0.5, 1.5, np.nan, 4.0, 3.0, 2.0], dtype=float)
    target = np.array([1.0, 2.0, np.nan, 8.0, 5.0, 3.0], dtype=float)
    finite_mask, target_ranks = gp._precompute_target_ranks(target)
    combined_mask = finite_mask & np.isfinite(signal)

    actual = gp._cached_spearman_corr(signal, combined_mask, target_ranks)
    expected, _ = spearmanr(signal[combined_mask], target[combined_mask])

    np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-8)


def test_cached_mask_inf_parity():
    signal = np.array([5.0, 4.0, 3.0, 2.0, 1.0], dtype=float)
    target = np.array([1.0, 2.0, np.inf, 4.0, 5.0], dtype=float)

    finite_mask, target_ranks = gp._precompute_target_ranks(target)
    actual = gp._cached_spearman_corr(signal, finite_mask, target_ranks)
    expected, _ = spearmanr(pd.DataFrame({"signal": signal, "target": target}).dropna()["signal"], pd.DataFrame({"signal": signal, "target": target}).dropna()["target"])

    assert finite_mask.tolist() == [True, True, True, True, True]
    np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-8)


def test_refactor_pit_safe():
    values = np.array([10.0, -5.0, 7.0, 7.0, 3.0], dtype=float)
    before = pd.Series(values).rank(pct=True, method="average").to_numpy()
    after = gp._rank_transform(values)

    np.testing.assert_allclose(after, before, rtol=1e-5, atol=1e-8)
