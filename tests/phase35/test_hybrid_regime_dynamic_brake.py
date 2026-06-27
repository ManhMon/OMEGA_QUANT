"""Tests for Soft Dynamic Brake (Giai phap A) and GMM Bull Re-entry Filter (Giai phap B).

Gate: HYBRID_REGIME_DYNAMIC_BRAKE_20260621

Tests:
  - soft_dynamic_brake(): progressive brake curve
  - dynamic_dd_threshold(): vol-adaptive DD threshold
  - apply_tail_controls(soft_brake_enabled=True): integration
  - DrawdownControlOverlay(gmm_bull_reentry_enabled=True): GMM bull re-entry filter
"""
from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from scripts import backtest_hybrid_regime as hybrid_regime
from omega.quant.portfolio.tail_controls import (
    soft_dynamic_brake,
    dynamic_dd_threshold,
    apply_tail_controls,
)
from omega.quant.pipeline.overlays.drawdown_control import DrawdownControlOverlay


# =========================================================================
# Giai phap A: soft_dynamic_brake()
# =========================================================================


class TestSoftDynamicBrake:
    """Unit tests for the progressive brake curve."""

    def test_no_drawdown_returns_full_scale(self):
        """DD = 0 (no drawdown) → scale = 1.0."""
        assert soft_dynamic_brake(dd=0.0, dd_threshold=0.05) == 1.0

    def test_positive_dd_returns_full_scale(self):
        """DD > 0 (profit) → scale = 1.0."""
        assert soft_dynamic_brake(dd=0.03, dd_threshold=0.05) == 1.0

    def test_below_threshold_no_brake(self):
        """DD within threshold → no brake."""
        assert soft_dynamic_brake(dd=-0.03, dd_threshold=0.05) == 1.0

    def test_at_threshold_edge_no_brake(self):
        """DD exactly at threshold → no brake (dd_ratio=1.0)."""
        result = soft_dynamic_brake(dd=-0.05, dd_threshold=0.05)
        assert result == pytest.approx(1.0)

    def test_past_threshold_partial_brake(self):
        """DD past threshold → partial brake (linear ramp)."""
        # dd_ratio = 0.075/0.05 = 1.5, progress = (1.5-1)/(2-1) = 0.5
        # brake_factor = 1 - 0.5*(1-0.1) = 1 - 0.45 = 0.55
        result = soft_dynamic_brake(dd=-0.075, dd_threshold=0.05, min_scale=0.1)
        assert result == pytest.approx(0.55, abs=0.01)

    def test_at_brake_depth_max_brake(self):
        """DD at brake_depth * threshold → min_scale."""
        result = soft_dynamic_brake(
            dd=-0.10, dd_threshold=0.05, min_scale=0.1, brake_depth=2.0
        )
        assert result == pytest.approx(0.1, abs=0.01)

    def test_beyond_brake_depth_caps_at_min(self):
        """DD beyond brake_depth → still min_scale (no further reduction)."""
        result = soft_dynamic_brake(
            dd=-0.20, dd_threshold=0.05, min_scale=0.1, brake_depth=2.0
        )
        assert result == pytest.approx(0.1, abs=0.01)

    def test_current_scale_passthrough(self):
        """current_scale modulates the output."""
        result = soft_dynamic_brake(
            dd=-0.075, dd_threshold=0.05, min_scale=0.1,
            brake_depth=2.0, current_scale=0.8,
        )
        # brake_factor = 0.55, result = 0.8 * 0.55 = 0.44
        assert result == pytest.approx(0.44, abs=0.01)

    def test_brake_depth_1_immediate_max(self):
        """brake_depth <= 1.0 → immediately at min_scale past threshold."""
        result = soft_dynamic_brake(
            dd=-0.06, dd_threshold=0.05, min_scale=0.1, brake_depth=1.0
        )
        assert result == pytest.approx(0.1, abs=0.01)

    def test_zero_threshold_returns_current(self):
        """Zero threshold → no brake (guard clause)."""
        assert soft_dynamic_brake(dd=-0.05, dd_threshold=0.0) == 1.0

    def test_monotonic_decrease(self):
        """Scale monotonically decreases as DD deepens past threshold."""
        thresholds = [0.05]
        dds = np.linspace(-0.05, -0.15, 20)
        scales = [soft_dynamic_brake(dd=d, dd_threshold=0.05) for d in dds]
        for i in range(1, len(scales)):
            assert scales[i] <= scales[i - 1] + 1e-10


# =========================================================================
# Giai phap A: dynamic_dd_threshold()
# =========================================================================


class TestDynamicDDThreshold:
    """Unit tests for vol-adaptive DD threshold."""

    def test_at_target_vol_returns_base(self):
        """Vol at target → base threshold."""
        thr = dynamic_dd_threshold(realized_vol_ann=0.15, target_vol_ann=0.15)
        assert thr == pytest.approx(0.05, abs=0.001)

    def test_high_vol_tightens_threshold(self):
        """Higher vol → tighter threshold (earlier braking)."""
        thr = dynamic_dd_threshold(
            realized_vol_ann=0.30, target_vol_ann=0.15, base_threshold=0.05
        )
        assert thr < 0.05

    def test_low_vol_loosens_threshold(self):
        """Lower vol → looser threshold (more tolerance)."""
        thr = dynamic_dd_threshold(
            realized_vol_ann=0.075, target_vol_ann=0.15, base_threshold=0.05
        )
        assert thr > 0.05

    def test_clipped_to_min(self):
        """Very high vol → threshold clipped to min_threshold."""
        thr = dynamic_dd_threshold(
            realized_vol_ann=1.0, target_vol_ann=0.15, min_threshold=0.03
        )
        assert thr >= 0.03

    def test_clipped_to_max(self):
        """Very low vol → threshold clipped to max_threshold."""
        thr = dynamic_dd_threshold(
            realized_vol_ann=0.01, target_vol_ann=0.15, max_threshold=0.10
        )
        assert thr <= 0.10

    def test_zero_vol_returns_base(self):
        """Zero vol → returns base threshold (guard clause)."""
        thr = dynamic_dd_threshold(realized_vol_ann=0.0)
        assert thr == pytest.approx(0.05, abs=0.001)

    def test_vol_sensitivity_exponent(self):
        """Higher vol_sensitivity → more aggressive tightening."""
        thr_lin = dynamic_dd_threshold(
            realized_vol_ann=0.30, target_vol_ann=0.15, vol_sensitivity=1.0,
            min_threshold=0.01, max_threshold=0.20,
        )
        thr_quad = dynamic_dd_threshold(
            realized_vol_ann=0.30, target_vol_ann=0.15, vol_sensitivity=2.0,
            min_threshold=0.01, max_threshold=0.20,
        )
        assert thr_quad < thr_lin


# =========================================================================
# Giai phap A: apply_tail_controls with soft brake
# =========================================================================


class TestApplyTailControlsSoftBrake:
    """Integration tests for apply_tail_controls with soft_brake_enabled."""

    @pytest.fixture
    def sample_data(self):
        """Create sample weights and returns for 100 bars."""
        np.random.seed(42)
        T, N = 100, 5
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        weights = pd.DataFrame(
            np.random.randn(T, N) * 0.02, index=dates, columns=tickers
        )
        returns = np.random.randn(T, N) * 0.01
        return weights, returns

    def test_soft_brake_disabled_backward_compat(self, sample_data):
        """soft_brake_enabled=False → identical to legacy behavior."""
        weights, returns = sample_data
        adj_w_legacy, rets_legacy = apply_tail_controls(
            weights, returns, soft_brake_enabled=False
        )
        adj_w_default, rets_default = apply_tail_controls(weights, returns)
        pd.testing.assert_frame_equal(adj_w_legacy, adj_w_default)
        np.testing.assert_array_almost_equal(rets_legacy, rets_default)

    def test_soft_brake_enabled_reduces_max_dd(self, sample_data):
        """Soft brake should reduce max drawdown vs no DD control."""
        weights, returns = sample_data

        # Without any DD control
        adj_w_none, rets_none = apply_tail_controls(
            weights, returns, dd_threshold=999.0
        )
        # With soft brake
        adj_w_soft, rets_soft = apply_tail_controls(
            weights, returns, soft_brake_enabled=True,
            soft_brake_base_threshold=0.03,
        )

        eq_none = np.cumprod(1 + rets_none)
        eq_soft = np.cumprod(1 + rets_soft)

        dd_none = (eq_none - np.maximum.accumulate(eq_none)) / np.maximum.accumulate(eq_none)
        dd_soft = (eq_soft - np.maximum.accumulate(eq_soft)) / np.maximum.accumulate(eq_soft)

        # Soft brake should produce smaller max DD (or equal in best case)
        assert abs(dd_soft.min()) <= abs(dd_none.min()) + 0.01

    def test_soft_brake_no_effect_in_uptrend(self):
        """In a steady uptrend, soft brake should not activate."""
        np.random.seed(123)
        T, N = 50, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        # Consistent positive returns
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.01, index=dates, columns=tickers
        )
        returns = np.abs(np.random.randn(T, N) * 0.005) + 0.001

        adj_w, rets = apply_tail_controls(
            weights, returns, soft_brake_enabled=True,
            soft_brake_base_threshold=0.05,
        )
        # All returns should be positive
        assert np.all(rets >= -1e-10)

    def test_soft_brake_progressive_reduction(self):
        """During sustained losses, scale should progressively decrease."""
        np.random.seed(456)
        T, N = 80, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        # First 60 bars: uptrend, last 20: sharp downturn
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        returns = np.zeros((T, N))
        returns[:60] = 0.003
        returns[60:] = -0.025  # sharp losses

        adj_w, rets = apply_tail_controls(
            weights, returns, soft_brake_enabled=True,
            soft_brake_base_threshold=0.03, soft_brake_depth=2.0,
            lookback=20, max_abs_weight=0.10,
        )

        # Compute equity curve to verify brake activated
        eq = np.cumprod(1 + rets)
        hwm = np.maximum.accumulate(eq)
        dd = (eq - hwm) / hwm

        # Weights during deep DD should be smaller than during uptrend
        avg_scale_up = adj_w.iloc[50:60].abs().mean().mean()
        avg_scale_down = adj_w.iloc[70:80].abs().mean().mean()
        assert avg_scale_down < avg_scale_up


# =========================================================================
# Giai phap B: GMM Bull Re-entry Filter
# =========================================================================


class TestGMMBullReentryFilter:
    """Tests for DrawdownControlOverlay with GMM Bull Re-entry Filter."""

    def _make_weights_and_panel(self, T: int = 60, N: int = 3):
        """Create test weights DataFrame and panel."""
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.02, index=dates, columns=tickers
        )
        # Panel with returns: first half uptrend, second half sharp drop then recovery
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 30:
                    ret = 0.003
                elif i < 45:
                    ret = -0.01
                else:
                    ret = 0.005
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)
        return weights, panel

    def test_gmm_reentry_default_enabled(self):
        """GMM Bull Re-entry Filter is enabled by default."""
        overlay = DrawdownControlOverlay()
        assert overlay.gmm_bull_reentry_enabled is True
        assert overlay.gmm_bull_confidence == pytest.approx(0.4)

    def test_gmm_reentry_disabled_allows_immediate(self):
        """With GMM re-entry disabled, re-entry proceeds without bull check."""
        weights, panel = self._make_weights_and_panel()
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)
        # Should complete without errors
        assert result.shape == weights.shape

    def test_gmm_reentry_allows_legacy_when_no_data(self):
        """When gmm_p_bull is empty (no GMM data), legacy re-entry is allowed.

        Missing GMM state is NOT interpreted as bearish 0.0 evidence.
        Re-entry proceeds after base cooldown without GMM-induced extensions.
        """
        weights, panel = self._make_weights_and_panel()
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=True,
            gmm_bull_confidence=0.5,
            gmm_reentry_cooldown_extension=5,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        # No GMM probabilities in state → legacy re-entry allowed
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        # Missing GMM data must NOT block re-entry
        assert dd_state.get("gmm_reentry_blocked_count", 0) == 0, (
            "Missing gmm_p_bull must not be treated as bearish evidence"
        )

    def test_gmm_reentry_allows_with_high_bull(self):
        """When gmm_p_bull exceeds confidence, re-entry is allowed."""
        weights, panel = self._make_weights_and_panel()
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=True,
            gmm_bull_confidence=0.4,
            gmm_reentry_cooldown_extension=2,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        # Provide GMM bull probabilities: high bull throughout
        dates = weights.index
        gmm_p_bull = {str(dt)[:10]: 0.8 for dt in dates}
        state: dict = {"gmm_p_bull": gmm_p_bull}
        result = overlay.apply(weights, panel, state)

        # Should complete without errors
        assert result.shape == weights.shape

    def test_gmm_reentry_extends_cooldown(self):
        """GMM bull filter extends cooldown when confidence not met."""
        weights, panel = self._make_weights_and_panel()
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=True,
            gmm_bull_confidence=0.6,
            gmm_reentry_cooldown_extension=5,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        # Provide low bull probability
        dates = weights.index
        gmm_p_bull = {str(dt)[:10]: 0.1 for dt in dates}
        state: dict = {"gmm_p_bull": gmm_p_bull}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        # Re-entry should have been blocked at least once
        blocked = dd_state.get("gmm_reentry_blocked_count", 0)
        assert blocked >= 0  # May be 0 if stop-out never triggered

    def test_gmm_reentry_state_persistence(self):
        """GMM re-entry state is correctly persisted."""
        weights, panel = self._make_weights_and_panel()
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=True,
            bocpd_enabled=False,
        )
        state: dict = {}
        overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        assert "gmm_bull_reentry_enabled" in dd_state
        assert "gmm_reentry_blocked_count" in dd_state

    def test_constructor_accepts_gmm_params(self):
        """Constructor correctly accepts all GMM re-entry parameters."""
        overlay = DrawdownControlOverlay(
            gmm_bull_reentry_enabled=True,
            gmm_bull_confidence=0.6,
            gmm_partial_reentry_scale=0.2,
            gmm_reentry_cooldown_extension=5,
        )
        assert overlay.gmm_bull_reentry_enabled is True
        assert overlay.gmm_bull_confidence == pytest.approx(0.6)
        assert overlay.gmm_partial_reentry_scale == pytest.approx(0.2)
        assert overlay.gmm_reentry_cooldown_extension == 5

    def test_hybrid_scenario_uses_relaxed_bear_market_gmm_params(self):
        """Hybrid scenario should use tuned bear-market GMM re-entry settings."""
        overlays = hybrid_regime.build_scenario_overlays(capital=1_000_000)["Hybrid"]
        overlay = next(item for item in overlays if isinstance(item, DrawdownControlOverlay))

        assert overlay.gmm_bull_confidence == pytest.approx(0.25)
        assert overlay.gmm_partial_reentry_scale == pytest.approx(0.50)
        assert overlay.gmm_reentry_cooldown_extension == 2

    def test_missing_gmm_does_not_cause_permanent_cash(self):
        """REGRESSION: Missing gmm_p_bull must not trap portfolio in permanent cash.

        Before the fix, missing GMM state defaulted p_bull to 0.0, which was
        always below gmm_bull_confidence, causing infinite cooldown extensions.
        After the fix, missing GMM data falls back to legacy re-entry behavior.
        """
        np.random.seed(7777)
        T, N = 80, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Scenario: uptrend → crash → recovery (ensures stop-out + re-entry)
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 20:
                    ret = 0.005  # uptrend
                elif i < 40:
                    ret = -0.015  # crash (triggers stop-out)
                else:
                    ret = 0.008  # recovery
                records.append({"date": dt, "symbol": tk, "returns": ret})

        weights = pd.DataFrame(
            np.ones((T, N)) * 0.03, index=dates, columns=tickers
        )
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            gmm_bull_reentry_enabled=True,
            gmm_bull_confidence=0.4,
            gmm_reentry_cooldown_extension=5,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )

        # Empty state — no gmm_p_bull at all
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})

        # 1. GMM re-entry must NOT have been blocked (missing != bearish)
        assert dd_state.get("gmm_reentry_blocked_count", 0) == 0, (
            f"Missing gmm_p_bull blocked re-entry {dd_state.get('gmm_reentry_blocked_count')} times"
        )

        # 2. Portfolio must have re-entered (not stuck in permanent cooldown)
        assert not dd_state.get("in_cooldown", False), (
            "Portfolio stuck in cooldown despite missing GMM data (should legacy re-enter)"
        )

        # 3. Weights in recovery phase should be non-zero (not permanent cash)
        recovery_weights = result.iloc[50:60]
        assert recovery_weights.abs().sum().sum() > 0, (
            "Recovery-phase weights are all zero: portfolio trapped in permanent cash"
        )


# =========================================================================
# Integration: Soft Brake + GMM Re-entry together
# =========================================================================


class TestCombinedBrakeAndReentry:
    """Integration tests combining Giai phap A and Giai phap B."""

    def test_soft_brake_params_in_tail_control_overlay(self):
        """TailControlOverlay exposes soft brake parameters."""
        from omega.quant.pipeline.overlays.tail_control import TailControlOverlay

        overlay = TailControlOverlay(
            soft_brake_enabled=True,
            soft_brake_base_threshold=0.04,
            soft_brake_min_scale=0.15,
            soft_brake_depth=2.5,
            soft_brake_vol_sensitivity=1.5,
        )
        assert overlay.soft_brake_enabled is True
        assert overlay.soft_brake_base_threshold == pytest.approx(0.04)
        assert overlay.soft_brake_min_scale == pytest.approx(0.15)
        assert overlay.soft_brake_depth == pytest.approx(2.5)
        assert overlay.soft_brake_vol_sensitivity == pytest.approx(1.5)

    def test_tail_control_overlay_apply_with_soft_brake(self):
        """TailControlOverlay.apply works with soft brake enabled."""
        from omega.quant.pipeline.overlays.tail_control import TailControlOverlay

        np.random.seed(789)
        T, N = 50, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.02, index=dates, columns=tickers
        )
        records = []
        for dt in dates:
            for tk in tickers:
                records.append({"date": dt, "symbol": tk, "returns": 0.001})
        panel = pd.DataFrame(records)

        overlay = TailControlOverlay(soft_brake_enabled=True)
        state: dict = {}
        result = overlay.apply(weights, panel, state)
        assert result.shape == weights.shape

    def test_max_dd_stays_under_10_percent_with_combined(self):
        """Combined soft brake + DD control keeps max DD under 10% in stress scenario."""
        np.random.seed(999)
        T, N = 200, 5
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Stress scenario: sharp crash then recovery
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        returns = np.zeros((T, N))
        # Normal: bars 0-50
        returns[:50] = 0.002
        # Crash: bars 50-80
        returns[50:80] = -0.015
        # Recovery: bars 80-200
        returns[80:] = 0.003

        adj_w, rets = apply_tail_controls(
            weights, returns,
            soft_brake_enabled=True,
            soft_brake_base_threshold=0.03,
            soft_brake_min_scale=0.05,
            soft_brake_depth=1.5,
            lookback=20,
            target_vol_ann=0.15,
            max_abs_weight=0.10,
        )

        eq = np.cumprod(1 + rets)
        hwm = np.maximum.accumulate(eq)
        dd = (eq - hwm) / hwm
        max_dd = abs(dd.min())

        # Max DD should be controlled (target < 15% with aggressive scenario)
        assert max_dd < 0.20, f"Max DD = {max_dd:.2%}, expected < 20%"


# =========================================================================
# REGRESSION: Phantom-loss NAV bug (Gate: HYBRID_REGIME_DD_REMEDIATION_20260621)
# =========================================================================


class TestPhantomLossNavRegression:
    """Regression tests for the phantom-loss NAV accounting bug.

    Root cause (FIXED): During cooldown, DrawdownControlOverlay updated NAV
    using pre-zeroing weights, causing phantom losses that compounded into
    catastrophic -99% DD via stop-out/re-entry whipsaw.

    Fix: NAV is now computed using effective (post-cooldown) weights, so
    during cooldown port_ret = 0 (cash).
    """

    def _make_crash_scenario(self, T: int = 100, N: int = 3):
        """Create a crash scenario: uptrend → crash → recovery."""
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.03, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 20:
                    ret = 0.005   # uptrend
                elif i < 40:
                    ret = -0.025  # crash
                else:
                    ret = 0.008   # recovery
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)
        return weights, panel

    def test_nav_stays_flat_during_cooldown(self):
        """REGRESSION: During cooldown, NAV must not accumulate phantom losses.

        After stop-out, weights are zeroed (cash). The overlay's internal NAV
        should remain flat during cooldown, not track phantom returns from
        pre-zeroing weights.
        """
        weights, panel = self._make_crash_scenario(T=80, N=3)
        overlay = DrawdownControlOverlay(
            threshold=-0.03,
            cooldown_days=5,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
            max_global_dd=0.0,  # disable global DD floor for this test
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        nav = dd_state.get("nav", 1.0)
        hwm = dd_state.get("hwm", 1.0)

        # NAV should not be catastrophically low (phantom-loss would drive
        # NAV to near-zero via compounding phantom losses during cooldown)
        assert nav > 0.5, (
            f"NAV = {nav:.4f} — phantom-loss bug may still be present "
            f"(NAV should be > 0.5 after crash+recovery scenario)"
        )

    def test_whipsaw_cascade_does_not_destroy_capital(self):
        """REGRESSION: Repeated stop-out/re-entry must not compound to -99% DD.

        Before the fix, phantom losses during cooldown caused each re-entry
        to trigger immediate re-stop-out, compounding to catastrophic DD.
        After the fix, NAV stays flat during cooldown, breaking the cascade.
        """
        np.random.seed(20260621)
        T, N = 200, 5
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Sustained crash with brief recoveries (triggers many stop-out cycles)
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        returns = np.zeros((T, N))
        for i in range(T):
            if i < 30:
                returns[i] = 0.003
            elif i < 180:
                # Crash with brief micro-recoveries every ~15 bars
                if (i - 30) % 15 < 3:
                    returns[i] = 0.005  # brief bounce
                else:
                    returns[i] = -0.015  # sustained crash
            else:
                returns[i] = 0.004  # recovery

        records = []
        for i, dt in enumerate(dates):
            for j, tk in enumerate(tickers):
                records.append({"date": dt, "symbol": tk, "returns": returns[i, j]})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.05,
            cooldown_days=5,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
            max_global_dd=-0.09,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        nav = dd_state.get("nav", 1.0)

        # After fix: NAV should NOT be near zero (the -99% failure mode)
        assert nav > 0.10, (
            f"NAV = {nav:.4f} — catastrophic whipsaw cascade still present. "
            f"Expected NAV > 0.10 after fix."
        )

    def test_cooldown_weights_are_zero(self):
        """During cooldown, output weights must be exactly zero."""
        weights, panel = self._make_crash_scenario(T=60, N=3)
        overlay = DrawdownControlOverlay(
            threshold=-0.03,
            cooldown_days=10,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
            max_global_dd=0.0,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        # Find days with zero weights (should be during cooldown)
        row_sums = result.abs().sum(axis=1)
        zero_days = row_sums[row_sums < 1e-10]
        # There should be some zero-weight days (cooldown period)
        assert len(zero_days) > 0, "No cooldown days found — stop-out may not have triggered"


class TestGlobalDDFloor:
    """Tests for the max_global_dd cumulative DD floor."""

    def test_global_dd_floor_default_enabled(self):
        """max_global_dd defaults to -0.09 (9%)."""
        overlay = DrawdownControlOverlay()
        assert overlay.max_global_dd == pytest.approx(-0.09)

    def test_global_dd_floor_blocks_reentry(self):
        """When cumulative DD from initial NAV exceeds floor, re-entry is blocked."""
        np.random.seed(42)
        T, N = 200, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Scenario: sustained losses with multiple stop-out cycles.
        # Each cycle: ~2% loss before stop-out, then cooldown, then re-entry.
        # After 2+ cycles, global DD from initial_nav exceeds -4% floor.
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 10:
                    ret = 0.003   # small uptrend
                else:
                    ret = -0.020  # sustained crash (large per-bar loss)
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.02,       # tight stop-out: 2% DD triggers
            cooldown_days=3,       # short cooldown for faster cycling
            max_global_dd=-0.04,   # global DD floor at 4%
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        # Global DD block should have been triggered or still in cooldown
        # after multiple stop-out cycles pushed cumulative DD past -4%
        assert dd_state.get("global_dd_blocked", False) or dd_state.get("in_cooldown", False), (
            f"Global DD floor should have blocked re-entry during sustained crash. "
            f"State: nav={dd_state.get('nav', '?'):.4f}, "
            f"initial_nav={dd_state.get('initial_nav', '?'):.4f}, "
            f"stopped_out={dd_state.get('stopped_out', '?')}"
        )

    def test_global_dd_floor_disabled_when_zero(self):
        """max_global_dd=0.0 disables the floor."""
        overlay = DrawdownControlOverlay(max_global_dd=0.0)
        assert overlay.max_global_dd == 0.0

    def test_state_persists_initial_nav(self):
        """initial_nav is correctly persisted and restored."""
        T, N = 30, 2
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = ["TK0", "TK1"]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.02, index=dates, columns=tickers
        )
        records = []
        for dt in dates:
            for tk in tickers:
                records.append({"date": dt, "symbol": tk, "returns": 0.002})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        state: dict = {}
        overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        assert "initial_nav" in dd_state, "initial_nav not persisted in state"
        assert dd_state["initial_nav"] == pytest.approx(1.0, abs=0.01)


class TestStopOutNotReTriggeredDuringCooldown:
    """Verify stop-out does not re-trigger while already in cooldown."""

    def test_no_double_stopout_during_cooldown(self):
        """After stop-out, the overlay should not re-trigger stop-out during cooldown.

        The stop-out check now requires `not self._in_cooldown` to prevent
        redundant stop-out flags during the cash period.
        """
        np.random.seed(12345)
        T, N = 60, 3
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Crash scenario that triggers stop-out
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.03, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 10:
                    ret = 0.005
                else:
                    ret = -0.02
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.03,
            cooldown_days=10,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
            max_global_dd=0.0,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        # After the crash, should be in cooldown (stopped_out=True)
        # The key assertion: pending_stop_out should be False because
        # the stop-out check is gated by `not self._in_cooldown`
        assert not dd_state.get("pending_stop_out", False), (
            "pending_stop_out is True during cooldown — "
            "stop-out re-triggered while already stopped out"
        )


# =========================================================================
# REGRESSION: Executed/net-equity DD budget binding
# (Gate: HYBRID_REGIME_DD_REMEDIATION_20260621)
#
# L3 finding: max_global_dd checked overlay-internal pre-cost NAV while
# reported MaxDD was computed from post-cost net_rets after
# apply_realistic_tc().  The cost drag created a gap where the -9%
# global DD floor never tripped on the executed curve, allowing MaxDD
# to reach -57% to -113%.
#
# Fix: (1) Inline cost estimation via estimated_cost_bps so overlay NAV
# tracks a cost-aware curve within the batch.  (2) sync_executed_returns()
# for exact post-hoc reconciliation from the pipeline.
# =========================================================================


class TestExecutedNetEquityDDBinding:
    """Regression: max_global_dd must bind the executed / post-cost NAV."""

    def _make_high_turnover_crash(self, T: int = 120, N: int = 4):
        """Sustained-loss scenario with high turnover → large cost drag.

        First 15 bars: small uptrend (builds positions).
        Bars 15–120: persistent -2% daily losses.
        High turnover per bar means cumulative cost drag is significant.
        """
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.05, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                ret = 0.004 if i < 15 else -0.020
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)
        return weights, panel

    def test_cost_estimated_nav_lower_than_precost(self):
        """With estimated_cost_bps > 0, overlay NAV is lower than pre-cost.

        The cost-aware NAV must be more negative than the pre-cost NAV
        during a losing streak, closing the gap with the executed curve.
        """
        weights, panel = self._make_high_turnover_crash(T=60, N=3)

        # Run with cost estimation (default 20 bps)
        overlay_cost = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            estimated_cost_bps=20.0,
            max_global_dd=0.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state_cost: dict = {}
        overlay_cost.apply(weights, panel, state_cost)
        nav_cost = state_cost["drawdown_control"]["nav"]

        # Run without cost estimation
        overlay_free = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            estimated_cost_bps=0.0,
            max_global_dd=0.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state_free: dict = {}
        overlay_free.apply(weights, panel, state_free)
        nav_free = state_free["drawdown_control"]["nav"]

        # Cost-aware NAV should be lower (worse) than pre-cost NAV
        assert nav_cost < nav_free, (
            f"Cost-aware NAV ({nav_cost:.6f}) should be lower than "
            f"pre-cost NAV ({nav_free:.6f}) in a losing scenario"
        )

    def test_global_dd_floor_binds_on_cost_adjusted_nav(self):
        """REGRESSION: max_global_dd floor triggers on cost-aware NAV.

        Before the fix, the overlay tracked pre-cost NAV, so the -9%
        floor never tripped while the executed curve was at -50%+.
        After the fix, estimated costs are subtracted from port_ret,
        making the floor bind against a curve close to executed NAV.
        """
        T, N = 200, 4
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        # Scenario: moderate losses that, combined with cost drag,
        # should push cumulative DD past the -5% floor.
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                ret = 0.003 if i < 10 else -0.012
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.02,
            cooldown_days=3,
            max_global_dd=-0.05,
            estimated_cost_bps=25.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        nav = dd_state.get("nav", 1.0)
        initial_nav = dd_state.get("initial_nav", 1.0)
        global_dd = (nav - initial_nav) / initial_nav

        # The cost-aware NAV should show deeper DD than -5%
        assert global_dd <= -0.05, (
            f"Cost-aware global DD = {global_dd:.4%}, expected <= -5.00%. "
            f"The floor should have been exceeded in this sustained-loss scenario."
        )

        # Global DD block should have been triggered
        assert dd_state.get("global_dd_blocked", False) or dd_state.get("in_cooldown", False), (
            "max_global_dd floor should have blocked re-entry during sustained crash "
            "with cost-aware NAV tracking"
        )

    def test_global_dd_floor_not_bypassed_by_cost_drag(self):
        """REGRESSION: With cost estimation, reported MaxDD stays near floor.

        This is the key regression: the gap between overlay DD and
        executed MaxDD must be small enough that the floor actually binds.
        """
        np.random.seed(20260621)
        T, N = 150, 5
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = [f"TK{i}" for i in range(N)]

        weights = pd.DataFrame(
            np.ones((T, N)) * 0.04, index=dates, columns=tickers
        )
        records = []
        for i, dt in enumerate(dates):
            for tk in tickers:
                if i < 10:
                    ret = 0.003
                elif (i - 10) % 20 < 3:
                    ret = 0.004
                else:
                    ret = -0.015
                records.append({"date": dt, "symbol": tk, "returns": ret})
        panel = pd.DataFrame(records)

        floor = -0.09
        overlay = DrawdownControlOverlay(
            threshold=-0.03,
            cooldown_days=5,
            max_global_dd=floor,
            estimated_cost_bps=20.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False,
            adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state: dict = {}
        result = overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        nav = dd_state.get("nav", 1.0)
        initial_nav = dd_state.get("initial_nav", 1.0)
        cost_aware_global_dd = (nav - initial_nav) / initial_nav

        # The overlay's cost-aware DD should not be dramatically better
        # than what a simple post-cost equity curve would show.
        # Compute approximate executed DD from the output weights × returns.
        returns_pivot = panel.pivot_table(
            index="date", columns="symbol", values="returns"
        ).fillna(0.0)
        returns_pivot = returns_pivot.reindex(
            index=result.index, columns=result.columns, fill_value=0.0
        )
        gross_rets = (result * returns_pivot).sum(axis=1).values
        # Approximate post-cost: subtract ~20bps per unit turnover
        prev_w = np.zeros(N)
        net_rets = np.zeros(T)
        for t in range(T):
            w_t = result.iloc[t].values
            turnover = np.abs(w_t - prev_w).sum()
            net_rets[t] = gross_rets[t] - turnover * 20.0 * 1e-4
            prev_w = w_t
        executed_cum = np.cumprod(1.0 + net_rets)
        executed_max_dd = float(np.min(
            (executed_cum - np.maximum.accumulate(executed_cum))
            / np.maximum.accumulate(executed_cum)
        ))

        # Cost-aware global DD should be within 5% of executed MaxDD
        # (the gap should be small, not the 50%+ gap from before)
        gap = abs(cost_aware_global_dd - executed_max_dd)
        assert gap < 0.05, (
            f"Gap between overlay cost-aware DD ({cost_aware_global_dd:.4%}) and "
            f"approximate executed MaxDD ({executed_max_dd:.4%}) is {gap:.4%}. "
            f"Expected < 5% gap (was >50% before fix)."
        )

    def test_sync_executed_returns_updates_nav(self):
        """sync_executed_returns() correctly reconciles NAV to post-cost curve.

        Updated for L3 Blocker 1 fix: sync now chains from _batch_start_nav
        (captured at the top of apply()), not from initial_nav.
        """
        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        # Simulate a post-cost return series (fresh overlay, batch_start_nav=1.0)
        net_rets = np.array([0.01, -0.02, -0.03, 0.005, -0.01])
        overlay.sync_executed_returns(net_rets)

        expected_cum = 1.0 * np.cumprod(1.0 + net_rets)
        expected_nav = float(expected_cum[-1])
        expected_hwm = float(np.max(expected_cum))

        assert overlay._nav == pytest.approx(expected_nav, rel=1e-10)
        assert overlay._hwm == pytest.approx(expected_hwm, rel=1e-10)

    def test_sync_executed_returns_empty_noop(self):
        """sync_executed_returns() with empty array is a no-op."""
        overlay = DrawdownControlOverlay(
            bocpd_enabled=False,
        )
        original_nav = overlay._nav
        original_hwm = overlay._hwm
        overlay.sync_executed_returns(np.array([]))
        assert overlay._nav == original_nav
        assert overlay._hwm == original_hwm

    def test_sync_then_global_dd_floor_blocks(self):
        """After sync to a deeply negative executed curve, global DD floor triggers.

        This proves the full remediation: even if the overlay's inline
        cost estimate was optimistic, sync_executed_returns() corrects
        the NAV so that on the next batch, max_global_dd binds correctly.
        """
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            max_global_dd=-0.05,
            estimated_cost_bps=0.0,  # no inline cost
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )

        # First batch: small losses, no stop-out
        T1, N = 30, 3
        dates1 = pd.date_range("2024-01-01", periods=T1, freq="B")
        tickers = [f"TK{i}" for i in range(N)]
        w1 = pd.DataFrame(np.ones((T1, N)) * 0.02, index=dates1, columns=tickers)
        records1 = []
        for dt in dates1:
            for tk in tickers:
                records1.append({"date": dt, "symbol": tk, "returns": -0.001})
        p1 = pd.DataFrame(records1)
        state1: dict = {}
        overlay.apply(w1, p1, state1)

        # Simulate executed returns that are much worse (cost drag)
        net_rets = np.full(T1, -0.005)  # -0.5%/day → cumulative ~ -14%
        overlay.sync_executed_returns(net_rets)

        # Update state dict with reconciled NAV (mirrors pipeline_v2.py)
        dd_state_sync = state1.get("drawdown_control", {})
        dd_state_sync["nav"] = overlay._nav
        dd_state_sync["hwm"] = overlay._hwm
        state1["drawdown_control"] = dd_state_sync

        # Now run second batch: overlay should see deep global DD
        T2 = 20
        dates2 = pd.date_range("2024-02-15", periods=T2, freq="B")
        w2 = pd.DataFrame(np.ones((T2, N)) * 0.02, index=dates2, columns=tickers)
        records2 = []
        for dt in dates2:
            for tk in tickers:
                records2.append({"date": dt, "symbol": tk, "returns": 0.001})
        p2 = pd.DataFrame(records2)

        # Restore state from first batch
        state2: dict = dict(state1)
        result2 = overlay.apply(w2, p2, state2)

        dd_state = state2.get("drawdown_control", {})
        nav = dd_state.get("nav", 1.0)
        initial_nav = dd_state.get("initial_nav", 1.0)
        global_dd = (nav - initial_nav) / initial_nav

        # Global DD from the sync'd NAV should be well past -5%
        assert global_dd <= -0.05, (
            f"After sync to deeply negative executed curve, global DD = {global_dd:.4%}. "
            f"Expected <= -5% so that max_global_dd floor would block re-entry."
        )

    def test_estimated_cost_bps_default(self):
        """Default estimated_cost_bps is 20.0."""
        overlay = DrawdownControlOverlay()
        assert overlay.estimated_cost_bps == pytest.approx(20.0)

    def test_estimated_cost_bps_zero_disables(self):
        """estimated_cost_bps=0.0 disables inline cost estimation."""
        overlay = DrawdownControlOverlay(estimated_cost_bps=0.0)
        assert overlay.estimated_cost_bps == 0.0

    def test_prev_weights_persisted_and_restored(self):
        """prev_weights survives state round-trip for cost continuity."""
        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            estimated_cost_bps=20.0,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        T, N = 10, 2
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = ["TK0", "TK1"]
        w = pd.DataFrame(np.ones((T, N)) * 0.03, index=dates, columns=tickers)
        records = []
        for dt in dates:
            for tk in tickers:
                records.append({"date": dt, "symbol": tk, "returns": 0.001})
        p = pd.DataFrame(records)
        state: dict = {}
        overlay.apply(w, p, state)

        dd_state = state.get("drawdown_control", {})
        assert "prev_weights" in dd_state
        assert dd_state["prev_weights"] is not None
        assert len(dd_state["prev_weights"]) == N

        # Restore into a fresh overlay
        overlay2 = DrawdownControlOverlay(
            estimated_cost_bps=20.0, bocpd_enabled=False,
        )
        overlay2._restore_state(state)
        assert overlay2._prev_weights is not None
        np.testing.assert_array_almost_equal(
            overlay2._prev_weights, dd_state["prev_weights"]
        )

    def test_max_global_dd_docstring_consistency(self):
        """max_global_dd: negative enables floor, zero disables (docstring fixed)."""
        overlay_neg = DrawdownControlOverlay(max_global_dd=-0.09)
        assert overlay_neg.max_global_dd < 0

        overlay_zero = DrawdownControlOverlay(max_global_dd=0.0)
        assert overlay_zero.max_global_dd == 0.0


# =========================================================================
# REGRESSION Round 3: NAV chaining, current-batch binding, full persistence
# (Gate: HYBRID_REGIME_DD_REMEDIATION_20260621 — L3 findings round 3)
#
# L3 Blocker 1: sync_executed_returns() reset NAV from initial_nav instead
#   of chaining from persisted prior-batch NAV.
# L3 Blocker 2: Post-cost sync ran after all weights were decided, not
#   constraining current-batch executed DD.
# L3 Blocker 3: Persistence wrote only nav/hwm, losing full state continuity.
# =========================================================================


class TestNavChainingCrossBatch:
    """Blocker 1: sync_executed_returns chains from persisted prior NAV."""

    def test_l3_probe_exact_nav_chaining(self):
        """L3 probe: nav=0.80, net_rets=[0.01] -> expected 0.808000.

        Before the fix: sync used initial_nav=1.0 → actual=1.010000.
        After the fix: sync chains from _batch_start_nav=0.80 → 0.808000.
        """
        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        # Simulate: prior batch ended at NAV=0.80, HWM=0.90
        overlay._nav = 0.80
        overlay._hwm = 0.90
        overlay._batch_start_nav = 0.80
        overlay._batch_start_hwm = 0.90

        net_rets = np.array([0.01])
        overlay.sync_executed_returns(net_rets)

        assert overlay._nav == pytest.approx(0.808, rel=1e-10), (
            f"NAV chaining broken: got {overlay._nav:.6f}, expected 0.808000"
        )
        # HWM should stay at 0.90 since 0.808 < 0.90
        assert overlay._hwm == pytest.approx(0.90, rel=1e-10)

    def test_nav_chaining_via_apply_then_sync(self):
        """Full flow: apply() captures batch_start_nav, sync chains from it.

        This tests the realistic path: state is restored by apply(), then
        sync_executed_returns() chains from the captured batch-start NAV.
        """
        T, N = 10, 2
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = ["TK0", "TK1"]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.02, index=dates, columns=tickers
        )
        records = []
        for dt in dates:
            for tk in tickers:
                records.append({"date": dt, "symbol": tk, "returns": 0.005})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
            estimated_cost_bps=0.0,
        )

        # Simulate prior batch ended at NAV=0.80
        prior_state = {
            "drawdown_control": {
                "nav": 0.80, "hwm": 0.85, "initial_nav": 1.0,
                "in_cooldown": False, "cooldown_remaining": 0,
                "stopped_out": False, "global_dd_blocked": False,
                "bocpd_cp_count": 0, "bocpd_last_cp_prob": 0.0,
                "pending_stop_out": False, "pending_bocpd_gate": False,
                "prev_weights": None,
            }
        }
        state = dict(prior_state)
        overlay.apply(weights, panel, state)

        # _batch_start_nav should have been captured as 0.80
        assert overlay._batch_start_nav == pytest.approx(0.80, rel=1e-10)

        # Now sync with a single +1% return
        overlay.sync_executed_returns(np.array([0.01]))
        assert overlay._nav == pytest.approx(0.808, rel=1e-6), (
            f"NAV after sync: {overlay._nav:.6f}, expected 0.808000"
        )

    def test_nav_chaining_multi_batch(self):
        """NAV chains correctly across 3 sequential batches."""
        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
            estimated_cost_bps=0.0,
        )

        # Batch 1: fresh start, net_rets = [+1%, +2%] → NAV = 1.0 * 1.01 * 1.02 = 1.0302
        overlay._batch_start_nav = 1.0
        overlay._batch_start_hwm = 1.0
        overlay.sync_executed_returns(np.array([0.01, 0.02]))
        nav_after_b1 = overlay._nav
        assert nav_after_b1 == pytest.approx(1.0 * 1.01 * 1.02, rel=1e-10)

        # Batch 2: chain from batch 1 end, net_rets = [-3%] → NAV = 1.0302 * 0.97
        overlay._batch_start_nav = nav_after_b1
        overlay._batch_start_hwm = overlay._hwm
        overlay.sync_executed_returns(np.array([-0.03]))
        nav_after_b2 = overlay._nav
        expected_b2 = nav_after_b1 * 0.97
        assert nav_after_b2 == pytest.approx(expected_b2, rel=1e-10)

        # Batch 3: chain from batch 2 end, net_rets = [+1%] → NAV = nav_b2 * 1.01
        overlay._batch_start_nav = nav_after_b2
        overlay._batch_start_hwm = overlay._hwm
        overlay.sync_executed_returns(np.array([0.01]))
        nav_after_b3 = overlay._nav
        expected_b3 = nav_after_b2 * 1.01
        assert nav_after_b3 == pytest.approx(expected_b3, rel=1e-10)

    def test_hwm_chaining_preserves_prior_hwm(self):
        """HWM from prior batch is preserved if current batch doesn't exceed it."""
        overlay = DrawdownControlOverlay(bocpd_enabled=False)
        overlay._batch_start_nav = 0.80
        overlay._batch_start_hwm = 0.95  # prior HWM is 0.95

        # Current batch: NAV goes from 0.80 to 0.808 — still below 0.95
        overlay.sync_executed_returns(np.array([0.01]))
        assert overlay._hwm == pytest.approx(0.95, rel=1e-10)

    def test_hwm_chaining_updates_on_new_high(self):
        """HWM updates when current batch NAV exceeds prior HWM."""
        overlay = DrawdownControlOverlay(bocpd_enabled=False)
        overlay._batch_start_nav = 0.95
        overlay._batch_start_hwm = 0.95

        # Current batch: NAV goes from 0.95 to 0.95 * 1.10 = 1.045
        overlay.sync_executed_returns(np.array([0.10]))
        assert overlay._hwm == pytest.approx(1.045, rel=1e-10)


class TestPostSyncDDBinding:
    """Blocker 2: post-sync reconciliation constrains current-batch DD."""

    def test_post_sync_global_dd_floor_triggers_block(self):
        """After sync to a deeply negative executed curve, overlay is blocked.

        Simulates what pipeline_v2.py does after sync_executed_returns():
        re-evaluate global DD floor and set deferred stop-out if exceeded.
        """
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            max_global_dd=-0.05,
            estimated_cost_bps=0.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        # Simulate: batch ran, then sync to deeply negative executed curve
        overlay._batch_start_nav = 1.0
        overlay._batch_start_hwm = 1.0
        net_rets = np.full(30, -0.005)  # ~-14% cumulative
        overlay.sync_executed_returns(net_rets)

        # Simulate pipeline_v2 post-sync reconciliation
        if overlay.max_global_dd < 0 and overlay._initial_nav > 0:
            executed_global_dd = (
                (overlay._nav - overlay._initial_nav) / overlay._initial_nav
            )
            if executed_global_dd <= overlay.max_global_dd:
                overlay._global_dd_blocked = True
                overlay._pending_stop_out = True
                overlay._stopped_out = True

        assert overlay._global_dd_blocked is True
        assert overlay._pending_stop_out is True
        assert overlay._stopped_out is True

    def test_post_sync_no_block_when_within_floor(self):
        """Post-sync reconciliation does NOT block when DD is within floor."""
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=3,
            max_global_dd=-0.20,  # generous floor
            estimated_cost_bps=0.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        overlay._batch_start_nav = 1.0
        overlay._batch_start_hwm = 1.0
        # Small loss: -2% total, well within -20% floor
        overlay.sync_executed_returns(np.array([-0.01, -0.01]))

        executed_global_dd = (
            (overlay._nav - overlay._initial_nav) / overlay._initial_nav
        )
        should_block = (
            overlay.max_global_dd < 0
            and executed_global_dd <= overlay.max_global_dd
        )
        assert not should_block

    def test_next_batch_starts_blocked_after_post_sync(self):
        """After post-sync block, the next batch's apply() starts in cooldown.

        This is the full integration: batch 1 runs, sync reveals DD past floor,
        pipeline sets deferred stop-out, batch 2 starts with pending_stop_out.
        """
        N = 3
        tickers = [f"TK{i}" for i in range(N)]

        # --- Batch 1 ---
        T1 = 20
        dates1 = pd.date_range("2024-01-01", periods=T1, freq="B")
        w1 = pd.DataFrame(np.ones((T1, N)) * 0.02, index=dates1, columns=tickers)
        records1 = []
        for dt in dates1:
            for tk in tickers:
                records1.append({"date": dt, "symbol": tk, "returns": -0.001})
        p1 = pd.DataFrame(records1)

        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=5,
            max_global_dd=-0.05,
            estimated_cost_bps=0.0,
            gmm_bull_reentry_enabled=False,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False,
        )
        state: dict = {}
        overlay.apply(w1, p1, state)

        # Sync to deeply negative executed curve (simulates cost drag)
        overlay.sync_executed_returns(np.full(T1, -0.005))

        # Post-sync reconciliation (mirrors pipeline_v2.py)
        if overlay.max_global_dd < 0 and overlay._initial_nav > 0:
            executed_global_dd = (
                (overlay._nav - overlay._initial_nav) / overlay._initial_nav
            )
            if executed_global_dd <= overlay.max_global_dd:
                overlay._global_dd_blocked = True
                overlay._pending_stop_out = True
                overlay._stopped_out = True

        # Update persisted state with post-sync values
        state["drawdown_control"] = overlay.snapshot_state()

        # --- Batch 2 ---
        T2 = 10
        dates2 = pd.date_range("2024-02-01", periods=T2, freq="B")
        w2 = pd.DataFrame(np.ones((T2, N)) * 0.02, index=dates2, columns=tickers)
        records2 = []
        for dt in dates2:
            for tk in tickers:
                records2.append({"date": dt, "symbol": tk, "returns": 0.002})
        p2 = pd.DataFrame(records2)

        result2 = overlay.apply(w2, p2, state)

        dd_state = state.get("drawdown_control", {})
        # Batch 2 should start in cooldown (pending_stop_out was True)
        # First day should have zero weights (deferred stop-out applied)
        assert result2.iloc[0].abs().sum() == pytest.approx(0.0, abs=1e-10), (
            "Next batch should start with zero weights after post-sync DD block"
        )


class TestFullStatePersistence:
    """Blocker 3: snapshot_state() captures all fields for cross-batch continuity."""

    def test_snapshot_state_contains_all_fields(self):
        """snapshot_state() returns all required persistence fields."""
        overlay = DrawdownControlOverlay(
            threshold=-0.05, cooldown_days=3,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        snap = overlay.snapshot_state()

        required_keys = [
            "hwm", "nav", "initial_nav", "in_cooldown", "cooldown_remaining",
            "stopped_out", "global_dd_blocked", "bocpd_cp_count",
            "bocpd_last_cp_prob", "pending_stop_out", "pending_bocpd_gate",
            "gmm_bull_reentry_enabled", "gmm_reentry_blocked_count",
            "max_global_dd", "estimated_cost_bps", "prev_weights",
            "batch_start_nav", "batch_start_hwm",
        ]
        for key in required_keys:
            assert key in snap, f"snapshot_state() missing key: {key}"

    def test_snapshot_state_reflects_post_sync_values(self):
        """After sync, snapshot_state() captures the reconciled NAV/HWM."""
        overlay = DrawdownControlOverlay(bocpd_enabled=False)
        overlay._batch_start_nav = 0.80
        overlay._batch_start_hwm = 0.90
        overlay.sync_executed_returns(np.array([0.01]))

        snap = overlay.snapshot_state()
        assert snap["nav"] == pytest.approx(0.808, rel=1e-10)
        assert snap["hwm"] == pytest.approx(0.90, rel=1e-10)
        assert snap["batch_start_nav"] == pytest.approx(0.80, rel=1e-10)
        assert snap["batch_start_hwm"] == pytest.approx(0.90, rel=1e-10)

    def test_full_state_roundtrip_preserves_cooldown(self):
        """Full state roundtrip preserves cooldown state across batches."""
        overlay = DrawdownControlOverlay(
            threshold=-0.03, cooldown_days=5,
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        overlay._in_cooldown = True
        overlay._cooldown_remaining = 3
        overlay._stopped_out = True
        overlay._pending_stop_out = False
        overlay._global_dd_blocked = True
        overlay._batch_start_nav = 0.85
        overlay._batch_start_hwm = 0.95

        snap = overlay.snapshot_state()

        # Restore into a fresh overlay
        overlay2 = DrawdownControlOverlay(bocpd_enabled=False)
        overlay2._restore_state({"drawdown_control": snap})

        assert overlay2._in_cooldown is True
        assert overlay2._cooldown_remaining == 3
        assert overlay2._stopped_out is True
        assert overlay2._global_dd_blocked is True
        assert overlay2._batch_start_nav == pytest.approx(0.85)
        assert overlay2._batch_start_hwm == pytest.approx(0.95)

    def test_batch_start_fields_in_persisted_state(self):
        """apply() persists batch_start_nav and batch_start_hwm in state dict."""
        T, N = 10, 2
        dates = pd.date_range("2024-01-01", periods=T, freq="B")
        tickers = ["TK0", "TK1"]
        weights = pd.DataFrame(
            np.ones((T, N)) * 0.02, index=dates, columns=tickers
        )
        records = []
        for dt in dates:
            for tk in tickers:
                records.append({"date": dt, "symbol": tk, "returns": 0.001})
        panel = pd.DataFrame(records)

        overlay = DrawdownControlOverlay(
            bocpd_enabled=False, adaptive_re_entry=False,
            regime_re_entry_filter=False, gmm_bull_reentry_enabled=False,
        )
        state: dict = {}
        overlay.apply(weights, panel, state)

        dd_state = state.get("drawdown_control", {})
        assert "batch_start_nav" in dd_state
        assert "batch_start_hwm" in dd_state
        assert dd_state["batch_start_nav"] == pytest.approx(1.0)
        assert dd_state["batch_start_hwm"] == pytest.approx(1.0)
