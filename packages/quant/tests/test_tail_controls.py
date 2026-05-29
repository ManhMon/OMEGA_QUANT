"""Tests for Phase 3.4 tail risk controls."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_PATH = REPO_ROOT / "packages/quant/src/omega/quant/portfolio/tail_controls.py"
_spec = importlib.util.spec_from_file_location("_tc", str(_PATH))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_tc"] = _mod
_spec.loader.exec_module(_mod)

vol_target_weights = _mod.vol_target_weights
cap_weights = _mod.cap_weights
drawdown_breaker = _mod.drawdown_breaker
apply_tail_controls = _mod.apply_tail_controls


def test_cap_weights_clips():
    w = np.array([0.10, -0.08, 0.02, -0.01])
    capped = cap_weights(w, max_abs_weight=0.05)
    assert capped.max() <= 0.05 + 1e-12
    assert capped.min() >= -0.05 - 1e-12
    assert capped[0] == 0.05
    assert capped[1] == -0.05


def test_cap_no_op_when_within():
    w = np.array([0.03, -0.04, 0.01])
    capped = cap_weights(w, max_abs_weight=0.05)
    np.testing.assert_array_equal(capped, w)


def test_vol_target_short_history_no_op():
    w = np.array([0.5, -0.5])
    out = vol_target_weights(w, returns_history=np.zeros(10), target_vol_ann=0.15)
    np.testing.assert_array_equal(out, w)


def test_vol_target_scales_down_high_vol():
    """If realized vol >> target, scale should < 1."""
    w = np.array([1.0, -1.0])
    np.random.seed(0)
    high_vol_rets = np.random.normal(0, 0.05, 100)  # ann ~80%
    out = vol_target_weights(w, high_vol_rets, target_vol_ann=0.15, lookback=60)
    assert np.abs(out[0]) < np.abs(w[0])


def test_vol_target_caps_max_leverage():
    """If realized vol very low, scale capped at max_leverage."""
    w = np.array([1.0])
    low_vol_rets = np.full(100, 1e-6)
    out = vol_target_weights(w, low_vol_rets, target_vol_ann=0.15,
                              max_leverage=3.0, lookback=60)
    assert np.abs(out[0]) <= 3.0 * np.abs(w[0]) + 1e-9


def test_drawdown_breaker_no_trip_when_flat():
    eq = np.linspace(1.0, 1.05, 30)
    s = drawdown_breaker(eq, scale=1.0, window=20, dd_threshold=0.08)
    assert s == 1.0


def test_drawdown_breaker_trips_on_deep_dd():
    """Equity dropped 15% from peak in 20-bar window -> cut 50%."""
    eq = np.concatenate([np.linspace(1.0, 1.20, 10),
                          np.linspace(1.20, 1.02, 20)])
    s = drawdown_breaker(eq, scale=1.0, window=20, dd_threshold=0.08, cut_factor=0.5)
    assert s == 0.5


def test_apply_tail_controls_smoke():
    """Realistic 250-day backtest: weights X tickers."""
    np.random.seed(42)
    T, N = 250, 50
    raw_w = np.random.normal(0, 0.04, size=(T, N))
    realized_y = np.random.normal(0.0005, 0.02, size=(T, N))
    w_df = pd.DataFrame(raw_w, columns=[f"t{i}" for i in range(N)])
    adj_w, port_rets = apply_tail_controls(w_df, realized_y,
                                            target_vol_ann=0.15,
                                            max_abs_weight=0.05)
    assert len(port_rets) == T
    # All weights capped
    assert adj_w.abs().max().max() <= 0.05 * 3.0 + 1e-9  # cap * max_leverage
    # Realized vol should be in ballpark of target after warmup
    warmup = 60
    if T > warmup:
        ann_vol = np.std(port_rets[warmup:], ddof=1) * np.sqrt(252)
        # generous range: vol target imperfect with random data
        assert ann_vol < 0.50, f"Vol={ann_vol:.2f} too high"


def test_apply_tail_controls_zero_returns_safe():
    T, N = 100, 10
    w_df = pd.DataFrame(np.zeros((T, N)))
    y = np.zeros((T, N))
    adj_w, rets = apply_tail_controls(w_df, y)
    assert np.all(rets == 0)
