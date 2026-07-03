"""Parity tests for the vectorized ICIR fast path in genetic_engine.

The fast path (GPIndividual._compute_combined_ic) computes a per-chunk
Spearman IC / IR without calling scipy in a Python loop. These tests assert
it matches the scipy reference (`_compute_icir_loop` semantics) even when the
old d-squared formula would diverge: ties in alpha or target, and
zero-variance (constant) chunks.
"""

import numpy as np
import pytest
from scipy.stats import spearmanr

from omega.quant.evolution.genetic_engine import (
    DATE_CHUNK_CACHE_KEY,
    GeneticEngine,
    GPConfig,
    GPIndividual,
)


def _reference_icir(alpha, target, date_chunks):
    """Scipy reference mirroring _compute_icir_loop exactly."""
    chunk_ics = []
    for idx in date_chunks:
        a = alpha[idx]
        t = target[idx]
        valid = np.isfinite(a) & np.isfinite(t)
        if np.count_nonzero(valid) < 2:
            continue
        ic, _ = spearmanr(a[valid], t[valid])
        if not np.isnan(ic):
            chunk_ics.append(float(ic))
    if not chunk_ics:
        valid = np.isfinite(alpha) & np.isfinite(target)
        if np.count_nonzero(valid) < 2:
            return 0.0
        ic, _ = spearmanr(alpha[valid], target[valid])
        return float(ic) if not np.isnan(ic) else 0.0
    std = float(np.std(chunk_ics))
    if std < 1e-9:
        return float(np.mean(chunk_ics))
    return float(np.mean(chunk_ics) / std)


def _make_panel(n_dates=12, n_stocks=8):
    """Long panel: __date__ label repeated per cross-section."""
    dates = np.repeat(np.arange(n_dates), n_stocks)
    return dates, n_dates * n_stocks


def _fast_path_ic(alpha, target, dates, window=5):
    """Drive the fast path via a real engine cache and return its IC."""
    config = GPConfig(use_icir=True, icir_window=window)
    engine = GeneticEngine(config)
    features = {'__date__': dates}
    cache = engine._precompute_date_chunks(features, target)
    features[DATE_CHUNK_CACHE_KEY] = cache

    GPIndividual.fast_path_hits = 0
    GPIndividual.fallback_hits = 0
    ind = GPIndividual(tree=None)
    ic = ind._compute_combined_ic(alpha, target, features, config)
    return ic, cache, GPIndividual.fast_path_hits, GPIndividual.fallback_hits


def _assert_parity(alpha, target, dates, window=5):
    fast_ic, cache, hits, fallbacks = _fast_path_ic(alpha, target, dates, window)
    ref_ic = _reference_icir(alpha, target, cache['date_chunks'])
    assert hits > 0, "fast path was not exercised"
    assert fallbacks == 0, "unexpected fallback to scipy loop"
    assert fast_ic == pytest.approx(ref_ic, abs=1e-9), (
        f"fast={fast_ic} ref={ref_ic}"
    )
    return fast_ic, ref_ic


def test_parity_continuous_no_ties():
    """Baseline: continuous alpha/target, essentially tie-free."""
    rng = np.random.default_rng(0)
    dates, n = _make_panel()
    alpha = rng.standard_normal(n)
    target = 0.4 * alpha + rng.standard_normal(n)
    _assert_parity(alpha, target, dates)


def test_parity_alpha_ties():
    """L3 repro shape: heavy ties in alpha break the d-squared formula."""
    rng = np.random.default_rng(1)
    dates, n = _make_panel()
    # Small integer alpha => many exact ties within each date chunk.
    alpha = rng.integers(0, 3, size=n).astype(np.float64)
    target = rng.standard_normal(n)
    _assert_parity(alpha, target, dates)


def test_parity_target_ties():
    """Heavy ties in the (cached) target ranks."""
    rng = np.random.default_rng(2)
    dates, n = _make_panel()
    alpha = rng.standard_normal(n)
    target = rng.integers(0, 3, size=n).astype(np.float64)
    _assert_parity(alpha, target, dates)


def test_parity_both_ties():
    """Ties in both alpha and target simultaneously."""
    rng = np.random.default_rng(3)
    dates, n = _make_panel()
    alpha = rng.integers(0, 4, size=n).astype(np.float64)
    target = rng.integers(0, 4, size=n).astype(np.float64)
    _assert_parity(alpha, target, dates)


def test_parity_constant_alpha_chunk():
    """A whole date-chunk has constant alpha (zero variance) -> skipped."""
    rng = np.random.default_rng(4)
    dates, n = _make_panel()
    alpha = rng.standard_normal(n)
    target = rng.standard_normal(n)
    # window=5 dates/chunk, 8 stocks/date => first chunk = rows [0:40).
    alpha[0:40] = 7.0  # constant across the entire first chunk
    _assert_parity(alpha, target, dates)


def test_parity_constant_target_chunk():
    """A whole date-chunk has constant target (zero variance) -> skipped."""
    rng = np.random.default_rng(5)
    dates, n = _make_panel()
    alpha = rng.standard_normal(n)
    target = rng.standard_normal(n)
    target[0:40] = 3.0  # constant across the entire first chunk
    _assert_parity(alpha, target, dates)


def test_parity_all_chunks_constant_alpha():
    """Every chunk constant -> no finite chunk IC -> global fallback."""
    dates, n = _make_panel()
    rng = np.random.default_rng(6)
    alpha = np.full(n, 2.0)
    target = rng.standard_normal(n)
    _assert_parity(alpha, target, dates)
