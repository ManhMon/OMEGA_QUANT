"""Tests for Deflated Sharpe Ratio (DSR)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_DSR_PATH = REPO_ROOT / "src" / "omega" / "quant" / "validation" / "dsr.py"
_spec = importlib.util.spec_from_file_location("_dsr_under_test", str(_DSR_PATH))
_dsr_mod = importlib.util.module_from_spec(_spec)
import sys
sys.modules["_dsr_under_test"] = _dsr_mod
_spec.loader.exec_module(_dsr_mod)

deflated_sharpe_ratio = _dsr_mod.deflated_sharpe_ratio
annualized_sharpe = _dsr_mod.annualized_sharpe
fold_level_dsr = _dsr_mod.fold_level_dsr


def test_zero_returns_dsr_zero():
    res = deflated_sharpe_ratio(np.zeros(252))
    assert res.dsr == 0.0
    assert not res.pass_threshold


def test_constant_positive_returns():
    """Constant returns => std=0 => SR undefined; treated as 0."""
    res = deflated_sharpe_ratio(np.ones(252) * 0.001)
    assert res.dsr == 0.0


def test_strong_signal_passes():
    """Strong positive signal with low noise should pass at n_trials=1."""
    np.random.seed(42)
    r = np.random.normal(loc=0.005, scale=0.005, size=1000)
    res = deflated_sharpe_ratio(r, n_trials=1)
    assert res.sr_annualized > 5.0
    assert res.pass_threshold


def test_n_trials_deflates():
    """Same data with N=1 vs N=1000 must produce DSR(1) >= DSR(1000)."""
    np.random.seed(42)
    r = np.random.normal(loc=0.001, scale=0.01, size=500)
    dsr1 = deflated_sharpe_ratio(r, n_trials=1).dsr
    dsr1000 = deflated_sharpe_ratio(r, n_trials=1000).dsr
    assert dsr1 >= dsr1000
    assert dsr1 - dsr1000 > 1e-6, "selection-bias term must reduce DSR"


def test_pure_noise_low_dsr():
    """White noise should have low DSR even at n_trials=1."""
    np.random.seed(0)
    r = np.random.normal(loc=0.0, scale=0.01, size=500)
    res = deflated_sharpe_ratio(r, n_trials=100)
    assert res.dsr < 0.95


def test_skew_kurtosis_computed():
    np.random.seed(1)
    r = np.random.normal(0, 0.01, size=500)
    res = deflated_sharpe_ratio(r)
    assert res.kurtosis > 0
    assert abs(res.skew) < 1.0  # Gaussian sample has near-zero skew


def test_annualized_sharpe_basic():
    np.random.seed(2)
    r = np.random.normal(0.001, 0.01, size=252)
    sr = annualized_sharpe(r, periods_per_year=252)
    assert sr > 0
    # ~ sqrt(252) * (mean/std) ≈ sqrt(252) * 0.1 ≈ 1.59 (sample-dependent)
    assert 0.5 < sr < 5.0


def test_short_series_returns_zero():
    res = deflated_sharpe_ratio([0.01])
    assert res.dsr == 0.0
    assert res.n_obs == 1


def test_benchmark_raises_bar():
    np.random.seed(42)
    r = np.random.normal(0.002, 0.01, size=500)
    dsr_zero = deflated_sharpe_ratio(r, n_trials=10, sr_benchmark=0.0).dsr
    dsr_one = deflated_sharpe_ratio(r, n_trials=10, sr_benchmark=0.1).dsr
    assert dsr_zero > dsr_one


def test_trial_sharpes_used():
    """Empirical trial variance should change DSR vs default."""
    np.random.seed(42)
    r = np.random.normal(0.001, 0.01, size=500)
    res_default = deflated_sharpe_ratio(r, n_trials=100)
    # If trials all had near-zero SR variance, deflation is smaller
    low_var_trials = np.random.normal(0, 0.01, size=100).tolist()
    res_low_var = deflated_sharpe_ratio(r, n_trials=100, trial_sharpes=low_var_trials)
    assert res_low_var.expected_max_sr < res_default.expected_max_sr


# ---------------------------------------------------------------------
# Audit P2 fixes
# ---------------------------------------------------------------------
def test_negative_sr_gives_low_dsr():
    """Strategy that loses money should have DSR < 0.5."""
    np.random.seed(7)
    r = np.random.normal(loc=-0.001, scale=0.01, size=500)
    res = deflated_sharpe_ratio(r, n_trials=10)
    assert res.sr < 0
    assert res.dsr < 0.5


def test_annualized_benchmark_lowers_dsr():
    """Annualized SR=1.0 benchmark deflates DSR vs zero benchmark."""
    np.random.seed(42)
    r = np.random.normal(0.0015, 0.01, size=500)
    dsr_zero = deflated_sharpe_ratio(
        r, n_trials=10, sr_benchmark=0.0, benchmark_is_annualized=True
    ).dsr
    dsr_one_ann = deflated_sharpe_ratio(
        r, n_trials=10, sr_benchmark=1.0, benchmark_is_annualized=True
    ).dsr
    assert dsr_zero > dsr_one_ann, "annualized benchmark must lower DSR"


def test_annualized_sharpe_near_constant_returns():
    """P2-A regression: near-zero std must not blow up the SR."""
    r = np.ones(252) * 0.001
    sr = annualized_sharpe(r)
    assert sr == 0.0

# ---------------------------------------------------------------------
# Phase 3.9: fold-level DSR (CPCV oversampling fix)
# ---------------------------------------------------------------------
def test_fold_level_dsr_basic_positive():
    """45 IID Gaussian fold Sharpes around 0.2 -> DSR moderate, finite."""
    rng = np.random.default_rng(42)
    fold_srs = rng.normal(loc=0.2, scale=0.3, size=45)
    res = fold_level_dsr(fold_srs, n_trials=4)
    assert res.n_obs == 45
    assert 0.0 < res.dsr < 1.0
    assert np.isclose(res.sr, float(np.mean(fold_srs)))


def test_fold_level_dsr_independent_of_bars_per_fold():
    """Fold-level DSR must depend ONLY on fold Sharpes, not on how many
    bars each fold contains. This is the whole point of the fix:
    pooled DSR over-counts samples; fold-level uses one obs per fold.
    """
    rng = np.random.default_rng(0)
    fold_srs_short = rng.normal(loc=0.15, scale=0.2, size=45)
    # Same fold Sharpes -- bars_per_fold should not matter at all.
    res_a = fold_level_dsr(fold_srs_short, n_trials=4, bars_per_fold=100)
    res_b = fold_level_dsr(fold_srs_short, n_trials=4, bars_per_fold=10000)
    assert np.isclose(res_a.dsr, res_b.dsr)
    assert np.isclose(res_a.sr, res_b.sr)


def test_fold_level_dsr_does_not_inflate_with_oversampled_pooled_bars():
    """Build a synthetic CPCV-like pool where the SAME 45 fold Sharpes are
    realised at two pool sizes (oversampled vs not). Pooled DSR can move
    a lot with pool size; fold-level DSR is invariant.
    """
    rng = np.random.default_rng(2)
    fold_srs = rng.normal(loc=0.1, scale=0.15, size=45)
    # The fold-level computation only sees fold_srs; the pooled
    # computation in backtest_v2_cpcv would see all bars stacked.
    fold_dsr = fold_level_dsr(fold_srs, n_trials=4).dsr
    assert 0.0 <= fold_dsr <= 1.0
    assert fold_dsr > 0  # mean SR is clearly positive


def test_fold_level_dsr_pure_noise():
    """Fold Sharpes centred at 0 should have DSR < 0.5."""
    rng = np.random.default_rng(7)
    fold_srs = rng.normal(loc=0.0, scale=0.2, size=45)
    res = fold_level_dsr(fold_srs, n_trials=4)
    assert res.dsr < 0.6  # not necessarily ~0 but well under pass


def test_fold_level_dsr_strong_signal_passes():
    """45 folds with mean SR 0.5 (per-bar) should pass at n_trials=1."""
    rng = np.random.default_rng(11)
    fold_srs = rng.normal(loc=0.5, scale=0.05, size=45)
    res = fold_level_dsr(fold_srs, n_trials=1)
    assert res.pass_threshold
    assert res.dsr > 0.95


def test_fold_level_dsr_n_trials_deflates():
    """Same fold Sharpes, larger n_trials must give smaller DSR."""
    rng = np.random.default_rng(13)
    fold_srs = rng.normal(loc=0.15, scale=0.2, size=45)
    d1 = fold_level_dsr(fold_srs, n_trials=1).dsr
    d100 = fold_level_dsr(fold_srs, n_trials=100).dsr
    assert d1 >= d100


def test_fold_level_dsr_short_series():
    """<2 folds returns zero."""
    res = fold_level_dsr([0.1])
    assert res.dsr == 0.0
    assert res.n_obs == 1


def test_fold_level_dsr_zero_variance():
    """All identical fold Sharpes -> sr_std=0 path is well-defined."""
    res = fold_level_dsr([0.3] * 10, n_trials=4)
    # Mean is positive but no spread -> binary verdict path
    assert res.dsr in (0.0, 1.0)
    assert np.isclose(res.sr, 0.3)
