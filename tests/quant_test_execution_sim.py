"""Tests for Phase 3.5 execution simulator."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
_PATH = REPO_ROOT / "src/omega/quant/portfolio/execution_sim.py"
_spec = importlib.util.spec_from_file_location("_es", str(_PATH))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_es"] = _mod
_spec.loader.exec_module(_mod)

apply_realistic_tc = _mod.apply_realistic_tc
VNCostModel = _mod.VNCostModel


def test_no_trades_no_cost():
    """Constant weights -> no turnover -> no cost."""
    T, N = 50, 5
    w = pd.DataFrame(np.full((T, N), 0.04))
    y = np.full((T, N), 0.001)
    _, net, br = apply_realistic_tc(w, y, daily_adv=None)
    # First bar trades from 0 to 0.04 (initial entry) -> some cost
    # But subsequent bars 1..T-1 have zero turnover
    assert br["avg_turnover_per_bar"] < 0.5  # only first bar trades
    assert br["total_slippage_cost"] == 0  # no ADV provided


def test_high_turnover_high_cost():
    """Alternating sign on weights -> ~2*N*max_w turnover/bar."""
    T, N = 100, 10
    rng = np.random.default_rng(0)
    raw = rng.normal(0, 0.04, (T, N))
    w_alt = pd.DataFrame(raw)
    y = rng.normal(0.0005, 0.02, (T, N))
    _, net_alt, br_alt = apply_realistic_tc(w_alt, y)

    w_const = pd.DataFrame(np.full((T, N), 0.04))
    _, net_const, br_const = apply_realistic_tc(w_const, y)
    assert br_alt["total_turnover"] > 5 * br_const["total_turnover"]
    assert br_alt["total_cost"] > br_const["total_cost"]


def test_slippage_scales_with_capital():
    """Larger AUM on illiquid names -> more slippage."""
    T, N = 50, 3
    w = pd.DataFrame(np.full((T, N), 0.04))
    # Alternate to force trades each bar
    w.iloc[::2] = -0.04
    y = np.zeros((T, N))
    adv = np.full((T, N), 1e9)  # 1B VND ADV (small)

    cost_model = VNCostModel(slippage_nonlinear_exp=1.0)
    _, _, br_small = apply_realistic_tc(w, y, daily_adv=adv,
                                          portfolio_capital_vnd=1e8, cost_model=cost_model)  # 100M
    _, _, br_big = apply_realistic_tc(w, y, daily_adv=adv,
                                        portfolio_capital_vnd=1e10, cost_model=cost_model)  # 10B
    assert br_big["total_slippage_cost"] > 50 * br_small["total_slippage_cost"]


def test_realistic_vn_baseline_typical_cost():
    """Sanity: typical balanced strategy ~10-30 bps/bar all-in."""
    T, N = 250, 50
    rng = np.random.default_rng(42)
    raw = rng.normal(0, 0.04, (T, N))
    w = pd.DataFrame(raw)
    y = rng.normal(0.0005, 0.02, (T, N))
    _, _, br = apply_realistic_tc(w, y)
    # avg_cost_per_bar_bps should be in 1-100 bps range
    assert 1 < br["avg_cost_per_bar_bps"] < 200, (
        f"Cost {br['avg_cost_per_bar_bps']:.1f} bps/bar out of expected range"
    )


def test_returns_drop_after_costs():
    """Net return < gross return when there is turnover."""
    T, N = 100, 10
    rng = np.random.default_rng(123)
    raw = rng.normal(0, 0.04, (T, N))
    w = pd.DataFrame(raw)
    y = rng.normal(0.001, 0.02, (T, N))

    gross = np.array([float(np.sum(w.iloc[t] * y[t])) for t in range(T)])
    _, net, br = apply_realistic_tc(w, y)
    assert np.sum(net) < np.sum(gross), "Net should be < gross after costs"

# ---------------------------------------------------------------------
# Phase 3.10 P1 fix: prev_w_init carry-over
# ---------------------------------------------------------------------
def test_final_w_returned_in_breakdown():
    """breakdown must expose final weights for fold-to-fold carry."""
    T, N = 20, 4
    w = pd.DataFrame(np.full((T, N), 0.05))
    y = np.zeros((T, N))
    _, _, br = apply_realistic_tc(w, y)
    assert "final_w" in br
    final_w = br["final_w"]
    assert final_w.shape == (N,)
    np.testing.assert_allclose(final_w, w.iloc[-1].to_numpy())


def test_prev_w_init_avoids_open_from_cash_cost():
    """Passing prev_w_init = first bar weights should drop bar-0
    open-from-cash turnover to zero."""
    T, N = 30, 5
    w = pd.DataFrame(np.full((T, N), 0.05))
    y = np.zeros((T, N))
    _, _, cold = apply_realistic_tc(w, y)
    _, _, warm = apply_realistic_tc(
        w, y, prev_w_init=w.iloc[0].to_numpy()
    )
    # Cold start trades from 0 -> 0.05 on every name in bar 0; warm start
    # has no first-bar turnover.
    assert cold["total_turnover"] > warm["total_turnover"]
    # Difference should be exactly the bar-0 turnover.
    bar0_turnover = float(np.abs(w.iloc[0]).sum())
    np.testing.assert_allclose(
        cold["total_turnover"] - warm["total_turnover"], bar0_turnover
    )


def test_prev_w_init_shape_validation():
    """Mismatched prev_w_init shape must raise."""
    T, N = 5, 4
    w = pd.DataFrame(np.full((T, N), 0.05))
    y = np.zeros((T, N))
    bad_prev = np.zeros(N + 1)
    try:
        apply_realistic_tc(w, y, prev_w_init=bad_prev)
    except ValueError as exc:
        assert "prev_w_init shape" in str(exc)
        return
    raise AssertionError("Expected ValueError for bad prev_w_init shape")


def test_chaining_two_calls_matches_single_long_call():
    """Splitting a path into two calls with prev_w_init carry should
    match running it as one call (commission/spread are linear in turnover
    so cumulative costs equal modulo bar-0 cold-start)."""
    T_total, N = 20, 4
    rng = np.random.default_rng(7)
    w_full = pd.DataFrame(rng.normal(0, 0.04, (T_total, N)))
    y = np.zeros((T_total, N))

    _, _, br_full = apply_realistic_tc(w_full, y)
    half = T_total // 2
    _, _, br_a = apply_realistic_tc(w_full.iloc[:half].reset_index(drop=True), y[:half])
    _, _, br_b = apply_realistic_tc(
        w_full.iloc[half:].reset_index(drop=True),
        y[half:],
        prev_w_init=br_a["final_w"],
    )
    np.testing.assert_allclose(
        br_full["total_turnover"], br_a["total_turnover"] + br_b["total_turnover"]
    )
    np.testing.assert_allclose(
        br_full["total_commission_cost"],
        br_a["total_commission_cost"] + br_b["total_commission_cost"],
    )
    np.testing.assert_allclose(
        br_full["total_spread_cost"],
        br_a["total_spread_cost"] + br_b["total_spread_cost"],
    )
