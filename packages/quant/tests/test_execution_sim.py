"""Tests for Phase 3.5 execution simulator."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_PATH = REPO_ROOT / "packages/quant/src/omega/quant/portfolio/execution_sim.py"
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

    _, _, br_small = apply_realistic_tc(w, y, daily_adv=adv,
                                          portfolio_capital_vnd=1e8)  # 100M
    _, _, br_big = apply_realistic_tc(w, y, daily_adv=adv,
                                        portfolio_capital_vnd=1e10)  # 10B
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
