from __future__ import annotations

from math import sqrt

import numpy as np

from omega.quant.validation.dsr import deflated_sharpe_ratio
from omega.quant.validation.sharpe_diagnostics import audit_sharpe
from omega.quant.validation.sharpe_diagnostics import assert_matches_production


def test_audit_zero_rf_matches_inline_formula():
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.01, 64)
    audit = audit_sharpe(returns, risk_free_rate=0.0)
    assert audit.sharpe_per_bar == float(np.mean(returns) / np.std(returns, ddof=1))


def test_annualization_factor():
    audit = audit_sharpe([0.01, 0.02, -0.01, 0.015])
    assert audit.sharpe_annualized == audit.sharpe_per_bar * sqrt(252)


def test_rf_subtraction_changes_result():
    returns = [0.02, 0.021, 0.019, 0.022]
    base = audit_sharpe(returns, risk_free_rate=0.0)
    shifted = audit_sharpe(returns, risk_free_rate=0.01)
    assert shifted.sharpe_per_bar < base.sharpe_per_bar
    assert shifted.excess_return_applied is True


def test_assert_matches_production_agrees():
    rng = np.random.default_rng(7)
    for size in [2, 8, 64, 252]:
        assert_matches_production(rng.normal(0.001, 0.01, size))


def test_benchmark_is_not_risk_free():
    rng = np.random.default_rng(9)
    returns = rng.normal(0.001, 0.01, 128)
    base = deflated_sharpe_ratio(returns, n_trials=10, sr_benchmark=0.0)
    shifted = deflated_sharpe_ratio(returns, n_trials=10, sr_benchmark=0.1)
    assert shifted.dsr != base.dsr
    assert shifted.sr == base.sr
    assert shifted.sr_annualized == base.sr_annualized


def test_degenerate_series():
    assert audit_sharpe([0.001, 0.001, 0.001]).sharpe_per_bar == 0.0
    assert audit_sharpe([0.001]).sharpe_per_bar == 0.0
    assert_matches_production([0.001, 0.001, 0.001])
    assert_matches_production([0.001])
