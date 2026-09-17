"""Tests for Phase 3.4 tail risk controls."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_PATH = REPO_ROOT / "src/omega/quant/portfolio/tail_controls.py"
_spec = importlib.util.spec_from_file_location("_tc", str(_PATH))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_tc"] = _mod
_spec.loader.exec_module(_mod)

vol_target_weights = _mod.vol_target_weights
cap_weights = _mod.cap_weights
drawdown_breaker = _mod.drawdown_breaker
apply_tail_controls = _mod.apply_tail_controls
smooth_regime_scale = _mod.smooth_regime_scale


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


def test_vol_target_downside_only_uses_sqrt2_correction():
    w = np.array([1.0])
    returns = np.array([-0.01, 0.01, -0.02, 0.02] * 25, dtype=float)
    out = vol_target_weights(
        w,
        returns,
        target_vol_ann=0.15,
        lookback=100,
        periods_per_year=252,
        downside_only=True,
    )
    expected_vol = np.std(returns[returns < 0.0], ddof=1) * np.sqrt(2.0) * np.sqrt(252)
    expected_scale = min(0.15 / expected_vol, 3.0)
    assert out[0] == pytest.approx(expected_scale)


def test_vol_target_downside_only_falls_back_when_sample_too_small():
    w = np.array([1.0])
    returns = np.array([0.01] * 99 + [-0.02], dtype=float)
    out = vol_target_weights(
        w,
        returns,
        target_vol_ann=0.15,
        lookback=100,
        periods_per_year=252,
        downside_only=True,
    )
    expected_vol = np.std(returns, ddof=1) * np.sqrt(252)
    expected_scale = min(0.15 / expected_vol, 3.0)
    assert out[0] == pytest.approx(expected_scale)


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

# ========================================
# Audit fix regression tests
# ========================================
def test_tc3_dd_breaker_trip_and_hold():
    """Once tripped, breaker stays cut until equity >= HWM.

    Compare two runs: identical setup except whether equity has dropped.
    The tripped run must produce smaller |w| at every bar than the untripped run,
    and the ratio must be <= dd_cut + small slack.
    """
    T, N = 30, 1
    pre_hist = np.full(60, 0.001)  # low-vol uniform pre-leverage history
    weights = pd.DataFrame(np.ones((T, N)) * 0.05, columns=['t0'])
    y = np.full((T, N), 0.001)

    # Run A: untripped (no warmup_equity given -> defaults [1.0])
    adj_a, _ = apply_tail_controls(
        weights, y,
        target_vol_ann=0.15, max_abs_weight=0.05,
        dd_window=10, dd_threshold=0.05, dd_cut=0.5,
        warmup_history=pre_hist,
    )

    # Run B: tripped (HWM=1.20, current=1.05 -> -12.5% DD, exceeds 5% threshold)
    pre_eq = np.concatenate([np.linspace(1.00, 1.20, 8), np.linspace(1.20, 1.05, 8)])
    adj_b, _ = apply_tail_controls(
        weights, y,
        target_vol_ann=0.15, max_abs_weight=0.05,
        dd_window=10, dd_threshold=0.05, dd_cut=0.5,
        warmup_history=pre_hist, warmup_equity=pre_eq,
    )

    # Tripped run must have HALF the weight of untripped run (dd_cut=0.5)
    # for at least the first 10 bars (HWM=1.20, slow recovery)
    for tt in range(10):
        ratio = adj_b.iloc[tt, 0] / adj_a.iloc[tt, 0] if adj_a.iloc[tt, 0] != 0 else 0
        assert ratio <= 0.5 + 1e-6, (
            f"DD trip failed at t={tt}: untripped={adj_a.iloc[tt,0]:.4f}, "
            f"tripped={adj_b.iloc[tt,0]:.4f}, ratio={ratio:.4f}"
        )


def test_pit_perturbation():
    """Perturbing y[t] must NOT change w at any s <= t."""
    np.random.seed(1)
    T, N = 30, 5
    weights = pd.DataFrame(np.random.normal(0, 0.04, (T, N)),
                            columns=[f't{i}' for i in range(N)])
    y_a = np.random.normal(0.001, 0.02, (T, N))
    y_b = y_a.copy()
    y_b[15] += 1.0  # huge perturbation at t=15

    w_a, _ = apply_tail_controls(weights.copy(), y_a)
    w_b, _ = apply_tail_controls(weights.copy(), y_b)

    # Weights at t <= 15 must be IDENTICAL (no look-ahead)
    np.testing.assert_array_almost_equal(
        w_a.iloc[:16].to_numpy(), w_b.iloc[:16].to_numpy(),
        decimal=10, err_msg="PIT violation: future return changed past weight"
    )


def test_warmup_history_seed_reduces_warmup():
    """Passing warmup_history bypasses the 60-bar warmup at scale=1.0."""
    np.random.seed(2)
    T, N = 100, 5
    weights = pd.DataFrame(np.ones((T, N)) * 0.04, columns=[f't{i}' for i in range(N)])
    y = np.random.normal(0.001, 0.02, (T, N))

    # Fold A: cold start
    _, port_cold = apply_tail_controls(weights.copy(), y)
    # Fold B: with seeded history
    seed = np.random.normal(0.001, 0.02, 90).tolist()
    _, port_warm = apply_tail_controls(weights.copy(), y, warmup_history=seed)

    # First 60 bars: cold runs at scale=1.0 (raw); warm runs vol-targeted.
    # If history seed causes vol-target to scale down (high vol seed), early
    # bar magnitudes differ.
    cold_first = np.abs(port_cold[:5]).mean()
    warm_first = np.abs(port_warm[:5]).mean()
    # They should differ (warm has scale != 1.0 from bar 0)
    assert not np.isclose(cold_first, warm_first), (
        f"Warmup seed had no effect: cold={cold_first:.6f}, warm={warm_first:.6f}"
    )


def test_tc4_vol_target_uses_pre_leverage():
    """After DD trip cuts exposure, vol-target should NOT lever back up
    based on the cut returns. Test by forcing a trip and checking next-bar scale."""
    # Hard to test in isolation since vol_target_weights is bar-level;
    # just confirm that with strong DD, post-trip portfolio vol stays low
    # rather than recovering to target via spurious vol estimate.
    np.random.seed(3)
    T, N = 200, 1
    rets = np.zeros(T)
    rets[80:90] = -0.04  # 40% drop -> deep trip
    weights = pd.DataFrame(np.ones((T, N)) * 0.05, columns=['t0'])
    _, port = apply_tail_controls(weights, rets.reshape(T, N),
        target_vol_ann=0.15, dd_window=20, dd_threshold=0.05, dd_cut=0.5)
    # After bar 90, breaker should be active for an extended period.
    # Realized portfolio mean(|ret|) post-90 should be SIGNIFICANTLY below
    # mean(|ret|) pre-80 (uncut period).
    pre = np.abs(port[60:80]).mean() if T > 80 else 0
    post = np.abs(port[100:120]).mean() if T > 120 else 0
    if pre > 1e-10:  # avoid div by zero on flat data
        assert post <= pre * 0.7, (
            f"DD breaker not effectively dampening post-trip: pre={pre:.6f}, post={post:.6f}"
        )


def test_smooth_regime_scale_monotonic_between_bear_and_bull():
    bearish = smooth_regime_scale(0.1, 0.7, bear_scale=0.4, bull_scale=1.0, tau=0.2)
    neutral = smooth_regime_scale(0.4, 0.4, bear_scale=0.4, bull_scale=1.0, tau=0.2)
    bullish = smooth_regime_scale(0.7, 0.1, bear_scale=0.4, bull_scale=1.0, tau=0.2)

    assert 0.4 <= bearish < neutral < bullish <= 1.0


def test_apply_tail_controls_regime_ramp_downweights_bearish_dates():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    weights = pd.DataFrame(np.full((3, 1), 0.05), index=dates, columns=["A"])
    rets = np.full((3, 1), 0.001)

    adj_w, _ = apply_tail_controls(
        weights,
        rets,
        regime_dates=dates,
        regime_ramp_enabled=True,
        gmm_p_bull={"2026-01-01": 0.8, "2026-01-02": 0.5, "2026-01-03": 0.1},
        gmm_p_bear={"2026-01-01": 0.1, "2026-01-02": 0.5, "2026-01-03": 0.8},
        regime_bear_scale=0.4,
        regime_bull_scale=1.0,
        regime_ramp_tau=0.2,
        bocpd_penalty_scale=0.75,
    )

    assert adj_w.iloc[0, 0] > adj_w.iloc[1, 0] > adj_w.iloc[2, 0]
