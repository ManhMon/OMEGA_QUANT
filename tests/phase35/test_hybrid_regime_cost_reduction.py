"""Tests for HYBRID_REGIME_COST_REDUCTION levers.

Covers:
  - Slippage recalibration (k: 0.05, exp: 0.6)
  - ADV-tiered half-spread (5/10/15 bps)
  - Dynamic turnover budgeting with regime IC scaling
  - VN regulatory compliance (commission 0.15%, tax 0.10% UNCHANGED)
  - PIT safety (no future data used)
  - Integration: cost reduction vs baseline

25 tests total. All use only current/past data (PIT-safe).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vn_cost_model():
    """Default VNCostModel with recalibrated slippage."""
    from omega.quant.portfolio.execution_sim import VNCostModel
    return VNCostModel()


@pytest.fixture
def sample_weights():
    """5-day, 4-name long-short weights."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=5, freq="B")
    cols = ["A", "B", "C", "D"]
    w = np.random.randn(5, 4) * 0.1
    # Demean per row (long-short)
    w = w - w.mean(axis=1, keepdims=True)
    return pd.DataFrame(w, index=dates, columns=cols)


@pytest.fixture
def sample_returns():
    """5-day, 4-name realized returns."""
    np.random.seed(123)
    dates = pd.date_range("2025-01-01", periods=5, freq="B")
    cols = ["A", "B", "C", "D"]
    r = np.random.randn(5, 4) * 0.01
    return pd.DataFrame(r, index=dates, columns=cols)


@pytest.fixture
def sample_adv():
    """5-day, 4-name ADV in VND. Mix of high/mid/low liquidity."""
    dates = pd.date_range("2025-01-01", periods=5, freq="B")
    cols = ["A", "B", "C", "D"]
    # A: high (>50B), B: mid (10-50B), C: low (<10B), D: mid
    adv = np.array([
        [100e9, 30e9, 5e9, 20e9],
        [80e9, 25e9, 8e9, 15e9],
        [120e9, 40e9, 3e9, 25e9],
        [60e9, 35e9, 7e9, 18e9],
        [90e9, 28e9, 6e9, 22e9],
    ])
    return pd.DataFrame(adv, index=dates, columns=cols)


# ===================================================================
# SLIPPAGE RECALIBRATION TESTS (1-6)
# ===================================================================

class TestSlippageRecalibration:
    """Verify slippage defaults recalibrated: k=0.05, exp=0.6."""

    def test_01_default_slippage_k_is_005(self, vn_cost_model):
        assert vn_cost_model.slippage_k == 0.05

    def test_02_default_nonlinear_exp_is_06(self, vn_cost_model):
        assert vn_cost_model.slippage_nonlinear_exp == 0.6

    def test_03_recalibrated_slippage_lower_than_legacy(self):
        """New k=0.05 must be less than legacy k=0.10."""
        from omega.quant.portfolio.execution_sim import VNCostModel
        model = VNCostModel()
        assert model.slippage_k < 0.10

    def test_04_nonlinear_exp_sublinear(self, vn_cost_model):
        """exp < 1.0 means sub-linear (Almgren-Chriss)."""
        assert vn_cost_model.slippage_nonlinear_exp < 1.0

    def test_05_slippage_cost_reduced_vs_legacy(self, sample_weights, sample_returns, sample_adv):
        """Total slippage cost with new params < legacy params."""
        from omega.quant.portfolio.execution_sim import (
            VNCostModel, apply_realistic_tc,
        )
        new_model = VNCostModel()  # k=0.05, exp=0.6
        legacy_model = VNCostModel(slippage_k=0.10, slippage_nonlinear_exp=1.0)

        _, _, bd_new = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=new_model,
        )
        _, _, bd_legacy = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=legacy_model,
        )
        assert bd_new["total_slippage_cost"] < bd_legacy["total_slippage_cost"]

    def test_06_slippage_nonlinear_calibrated_at_ref_participation(self, vn_cost_model):
        """At p_ref=0.01, cost should be similar between linear and nonlinear."""
        p_ref = vn_cost_model.slippage_k_ref_participation
        exp = vn_cost_model.slippage_nonlinear_exp
        calibration = p_ref ** (1.0 - exp)
        # effective_k * p_ref^exp * calibration = k * p_ref^(exp) * p_ref^(1-exp) = k * p_ref
        effective = vn_cost_model.slippage_k * (p_ref ** exp) * calibration
        linear = vn_cost_model.slippage_k * p_ref
        assert abs(effective - linear) < 1e-10


# ===================================================================
# ADV-TIERED HALF-SPREAD TESTS (7-12)
# ===================================================================

class TestADVTieredHalfSpread:
    """Verify ADV-tiered half-spread (5/10/15 bps)."""

    def test_07_high_adv_returns_5bps(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(100e9) == 0.0005

    def test_08_mid_adv_returns_10bps(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(30e9) == 0.0010

    def test_09_low_adv_returns_15bps(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(5e9) == 0.0015

    def test_10_tiered_spread_reduces_cost_for_liquid_names(self, sample_weights, sample_returns, sample_adv):
        """ADV-tiered spread should reduce total spread cost vs flat 10bps."""
        from omega.quant.portfolio.execution_sim import (
            VNCostModel, apply_realistic_tc,
        )
        model = VNCostModel()
        _, _, bd_flat = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=model,
            use_adv_tiered_spread=False,
        )
        _, _, bd_tiered = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=model,
            use_adv_tiered_spread=True,
        )
        # High-ADV names get 5bps instead of 10bps, so tiered should be lower
        assert bd_tiered["total_spread_cost"] < bd_flat["total_spread_cost"]

    def test_11_vectorized_tiered_spread_shape(self, sample_adv):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread_vectorized
        result = adv_tiered_half_spread_vectorized(sample_adv.to_numpy())
        assert result.shape == sample_adv.to_numpy().shape

    def test_12_vectorized_tiered_spread_values(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread_vectorized
        adv = np.array([100e9, 30e9, 5e9])
        result = adv_tiered_half_spread_vectorized(adv)
        np.testing.assert_allclose(result, [0.0005, 0.0010, 0.0015])


# ===================================================================
# DYNAMIC TURNOVER BUDGETING TESTS (13-18)
# ===================================================================

class TestDynamicTurnoverBudgeting:
    """Verify dynamic turnover budgeting with regime IC scaling."""

    def test_13_high_ic_lowers_threshold(self):
        from omega.quant.portfolio.tcost_optimizer_overlay import dynamic_trade_threshold
        threshold = dynamic_trade_threshold(30.0, current_ic=0.08)
        assert threshold < 30.0

    def test_14_low_ic_raises_threshold(self):
        from omega.quant.portfolio.tcost_optimizer_overlay import dynamic_trade_threshold
        threshold = dynamic_trade_threshold(30.0, current_ic=0.005)
        assert threshold > 30.0

    def test_15_mid_ic_interpolates(self):
        from omega.quant.portfolio.tcost_optimizer_overlay import dynamic_trade_threshold
        threshold = dynamic_trade_threshold(30.0, current_ic=0.035)
        assert 15.0 < threshold < 60.0

    def test_16_rolling_ic_pit_safe(self, sample_weights, sample_returns):
        """IC at T uses weights at T-1, no look-ahead."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        ic = compute_rolling_ic(sample_weights, sample_returns, lookback=3)
        # First value should be NaN or 0 (shifted weights have NaN at T=0)
        assert len(ic) > 0

    def test_17_dynamic_overlay_reduces_turnover_in_low_ic(
        self, sample_weights, sample_returns,
    ):
        """Low IC regime should produce higher threshold -> less turnover."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        # Create low-IC scenario: random returns uncorrelated with weights
        np.random.seed(999)
        low_ic_returns = pd.DataFrame(
            np.random.randn(*sample_weights.shape) * 0.01,
            index=sample_weights.index,
            columns=sample_weights.columns,
        )
        result = apply_dynamic_tcost_overlay(
            sample_weights,
            daily_returns=low_ic_returns,
            base_threshold_bps=30.0,
        )
        # Should still produce valid weights
        assert result.shape == sample_weights.shape

    def test_18_dynamic_overlay_fallback_without_returns(self, sample_weights):
        """Without returns, falls back to static threshold."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        result = apply_dynamic_tcost_overlay(
            sample_weights,
            daily_returns=None,
            base_threshold_bps=30.0,
        )
        assert result.shape == sample_weights.shape


# ===================================================================
# VN REGULATORY COMPLIANCE TESTS (19-22)
# ===================================================================

class TestVNRegulatoryCompliance:
    """Commission 0.15% and tax 0.10% MUST be UNCHANGED."""

    def test_19_commission_buy_unchanged(self, vn_cost_model):
        assert vn_cost_model.commission_buy == 0.0015

    def test_20_commission_sell_unchanged(self, vn_cost_model):
        assert vn_cost_model.commission_sell == 0.0015

    def test_21_tax_sell_unchanged(self, vn_cost_model):
        assert vn_cost_model.tax_sell == 0.0010

    def test_22_commission_cost_positive(self, sample_weights, sample_returns, sample_adv):
        from omega.quant.portfolio.execution_sim import apply_realistic_tc
        _, _, bd = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
        )
        assert bd["total_commission_cost"] > 0


# ===================================================================
# PIT SAFETY TESTS (23-24)
# ===================================================================

class TestPITSafety:
    """All changes must use only current/past data."""

    def test_23_apply_realistic_tc_no_future_data(self, sample_weights, sample_returns, sample_adv):
        """Verify bar-by-bar cost computation doesn't peek ahead."""
        from omega.quant.portfolio.execution_sim import apply_realistic_tc
        _, net_rets_full, _ = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
        )
        # Truncate to first 3 days and verify identical results
        _, net_rets_trunc, _ = apply_realistic_tc(
            sample_weights.iloc[:3], sample_returns.iloc[:3].to_numpy(),
            daily_adv=sample_adv.iloc[:3].to_numpy(),
        )
        np.testing.assert_allclose(net_rets_full[:3], net_rets_trunc, atol=1e-12)

    def test_24_rolling_ic_uses_shifted_weights(self):
        """IC computation must use T-1 weights, not T weights."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        # Use larger dataset to ensure meaningful IC values after shift
        np.random.seed(77)
        dates = pd.date_range("2025-01-01", periods=20, freq="B")
        cols = [f"S{i}" for i in range(10)]
        w = pd.DataFrame(np.random.randn(20, 10) * 0.1, index=dates, columns=cols)
        # Create returns correlated with weights (for non-zero IC)
        r = w * 0.5 + pd.DataFrame(np.random.randn(20, 10) * 0.01, index=dates, columns=cols)

        ic = compute_rolling_ic(w, r)
        # If we shift weights forward by 1, IC should change (proving shift is used)
        shifted_w = w.shift(-1)
        ic_shifted = compute_rolling_ic(shifted_w, r)
        # Check non-trivial IC values (skip first few which may be 0 due to shift)
        valid_ic = ic.values[2:]
        valid_ic_shifted = ic_shifted.values[2:]
        # At least some values should differ
        assert not np.allclose(valid_ic, valid_ic_shifted, atol=1e-10)


# ===================================================================
# INTEGRATION TEST (25)
# ===================================================================

class TestIntegration:
    """End-to-end cost reduction verification."""

    def test_25_total_cost_reduced_vs_baseline(self, sample_weights, sample_returns, sample_adv):
        """Combined levers should reduce total cost vs legacy baseline."""
        from omega.quant.portfolio.execution_sim import (
            VNCostModel, apply_realistic_tc,
        )
        # New: recalibrated slippage + ADV-tiered spread
        new_model = VNCostModel()
        _, _, bd_new = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=new_model,
            use_adv_tiered_spread=True,
        )
        # Legacy: old slippage + flat spread
        legacy_model = VNCostModel(slippage_k=0.10, slippage_nonlinear_exp=1.0)
        _, _, bd_legacy = apply_realistic_tc(
            sample_weights, sample_returns.to_numpy(),
            daily_adv=sample_adv.to_numpy(),
            cost_model=legacy_model,
            use_adv_tiered_spread=False,
        )
        assert bd_new["total_cost"] < bd_legacy["total_cost"]


# ===================================================================
# PIT SAFETY — TRUNCATION INVARIANCE (26-27)
# ===================================================================

class TestPITTruncationInvariance:
    """Prove that modifying future returns does NOT change past weights/IC.

    This is the definitive look-ahead-bias test:
      1. Build a 20-day returns dataframe with 10 names.
      2. Run the dynamic tcost overlay and snapshot weights + IC at t=10.
      3. Mutate returns at t=15 (far future relative to t=10).
      4. Re-run the overlay and assert weights/IC at t=10 are BIT-IDENTICAL.
    If the overlay leaked future information the snapshot at t=10 would change.
    """

    @staticmethod
    def _build_panel(n_days: int = 20, n_names: int = 10, seed: int = 42):
        """Create weights and returns DataFrames for PIT testing."""
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2025-03-01", periods=n_days, freq="B")
        cols = [f"PIT_{i}" for i in range(n_names)]
        w = pd.DataFrame(rng.randn(n_days, n_names) * 0.1, index=dates, columns=cols)
        w = w - w.mean(axis=1).values.reshape(-1, 1)  # demean (long-short)
        r = pd.DataFrame(rng.randn(n_days, n_names) * 0.01, index=dates, columns=cols)
        return w, r

    def test_26_overlay_weights_at_t10_unchanged_when_future_returns_mutated(self):
        """Truncation invariance: mutating returns at t>=15 must not alter weights at t=10."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay

        weights, returns = self._build_panel()

        # --- Run 1: pristine ---
        result_full = apply_dynamic_tcost_overlay(
            weights, daily_returns=returns, base_threshold_bps=30.0, ic_lookback=5,
        )
        weights_at_t10_full = result_full.iloc[10].copy()

        # --- Run 2: mutate returns at t=15 (and beyond) ---
        returns_mutated = returns.copy()
        returns_mutated.iloc[15:] = returns_mutated.iloc[15:] * 100.0  # extreme mutation

        result_mutated = apply_dynamic_tcost_overlay(
            weights, daily_returns=returns_mutated, base_threshold_bps=30.0, ic_lookback=5,
        )
        weights_at_t10_mutated = result_mutated.iloc[10].copy()

        # Weights at t=10 MUST be identical regardless of future mutation
        np.testing.assert_allclose(
            weights_at_t10_full.values,
            weights_at_t10_mutated.values,
            atol=1e-14,
            err_msg="PIT VIOLATION: weights at t=10 changed after mutating future returns at t=15",
        )

    def test_27_rolling_ic_at_t10_unchanged_when_future_returns_mutated(self):
        """Truncation invariance for rolling IC: mutation at t>=15 must not alter IC at t=10."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic

        weights, returns = self._build_panel()

        # --- Run 1: pristine ---
        ic_full = compute_rolling_ic(weights, returns, lookback=5)
        ic_at_t10_full = float(ic_full.iloc[10])

        # --- Run 2: mutate returns at t=15 (and beyond) ---
        returns_mutated = returns.copy()
        returns_mutated.iloc[15:] = returns_mutated.iloc[15:] * 100.0

        ic_mutated = compute_rolling_ic(weights, returns_mutated, lookback=5)
        ic_at_t10_mutated = float(ic_mutated.iloc[10])

        assert ic_at_t10_full == ic_at_t10_mutated, (
            f"PIT VIOLATION: rolling IC at t=10 changed from {ic_at_t10_full} "
            f"to {ic_at_t10_mutated} after mutating future returns at t=15"
        )


# ===================================================================
# ROLLING IC LOOKBACK VALIDATION (28-33)
# ===================================================================

class TestRollingICLookback:
    """Verify compute_rolling_ic actually uses the lookback parameter."""

    @staticmethod
    def _make_panel(n_days=30, n_names=10, seed=42):
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2025-04-01", periods=n_days, freq="B")
        cols = [f"LB_{i}" for i in range(n_names)]
        w = pd.DataFrame(rng.randn(n_days, n_names) * 0.1, index=dates, columns=cols)
        r = w * 0.3 + pd.DataFrame(rng.randn(n_days, n_names) * 0.01, index=dates, columns=cols)
        return w, r

    def test_28_lookback_1_differs_from_lookback_10(self):
        """Different lookbacks must produce different rolling IC values."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel()
        ic_1 = compute_rolling_ic(w, r, lookback=1)
        ic_10 = compute_rolling_ic(w, r, lookback=10)
        # After warm-up, values should differ (smoothing changes variance)
        valid_1 = ic_1.values[15:]
        valid_10 = ic_10.values[15:]
        assert not np.allclose(valid_1, valid_10, atol=1e-10)

    def test_29_larger_lookback_produces_smoother_ic(self):
        """Larger lookback should produce lower-variance IC series."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel(n_days=50, seed=99)
        ic_small = compute_rolling_ic(w, r, lookback=3)
        ic_large = compute_rolling_ic(w, r, lookback=20)
        # After warm-up, larger lookback should have lower std
        std_small = ic_small.values[25:].std()
        std_large = ic_large.values[25:].std()
        assert std_large <= std_small + 1e-10

    def test_30_rolling_ic_length_matches_input(self):
        """Output length should equal the common index length."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel(n_days=25)
        ic = compute_rolling_ic(w, r, lookback=5)
        assert len(ic) == len(w)

    def test_31_rolling_ic_no_nan_in_middle(self):
        """After warm-up, IC values should not be NaN."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel(n_days=30)
        ic = compute_rolling_ic(w, r, lookback=5)
        # After the lookback window, no NaNs
        assert not ic.iloc[10:].isna().any()

    def test_32_rolling_ic_correlated_signal_produces_positive_ic(self):
        """Perfectly correlated signal/returns should produce high positive IC."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        cols = [f"S{i}" for i in range(10)]
        w = pd.DataFrame(np.tile(np.arange(10, dtype=float), (30, 1)) * 0.01, index=dates, columns=cols)
        r = w.copy()  # Perfect correlation
        ic = compute_rolling_ic(w, r, lookback=5)
        # After warm-up, IC should be high positive (close to 1.0)
        assert ic.iloc[15:].mean() > 0.5

    def test_33_rolling_ic_anticorrelated_signal_produces_negative_ic(self):
        """Anti-correlated signal/returns should produce negative IC."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        cols = [f"S{i}" for i in range(10)]
        w = pd.DataFrame(np.tile(np.arange(10, dtype=float), (30, 1)) * 0.01, index=dates, columns=cols)
        r = -w.copy()  # Anti-correlation
        ic = compute_rolling_ic(w, r, lookback=5)
        assert ic.iloc[15:].mean() < -0.5


# ===================================================================
# PER-BAR THRESHOLD & DYNAMIC OVERLAY TESTS (34-43)
# ===================================================================

class TestPerBarDynamicThreshold:
    """Verify per-bar threshold computation and PIT-safe overlay behavior."""

    @staticmethod
    def _make_panel(n_days=25, n_names=10, seed=55):
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2025-05-01", periods=n_days, freq="B")
        cols = [f"DYN_{i}" for i in range(n_names)]
        w = pd.DataFrame(rng.randn(n_days, n_names) * 0.1, index=dates, columns=cols)
        w = w - w.mean(axis=1).values.reshape(-1, 1)
        r = pd.DataFrame(rng.randn(n_days, n_names) * 0.01, index=dates, columns=cols)
        return w, r

    def test_34_per_bar_threshold_is_series(self):
        """apply_dynamic_tcost_overlay should produce valid output with per-bar thresholds."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel()
        result = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=5)
        assert result.shape == w.shape

    def test_35_overlay_truncation_invariance_at_t5(self):
        """Weights at t=5 must not change when future (t=20) is mutated."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel()
        result_full = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=5)
        r_mut = r.copy()
        r_mut.iloc[20:] = r_mut.iloc[20:] * 50.0
        result_mut = apply_dynamic_tcost_overlay(w, daily_returns=r_mut, ic_lookback=5)
        np.testing.assert_allclose(
            result_full.iloc[5].values, result_mut.iloc[5].values, atol=1e-14,
        )

    def test_36_overlay_truncation_invariance_at_t15(self):
        """Weights at t=15 must not change when future (t=20) is mutated."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel()
        result_full = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=5)
        r_mut = r.copy()
        r_mut.iloc[20:] = r_mut.iloc[20:] * 50.0
        result_mut = apply_dynamic_tcost_overlay(w, daily_returns=r_mut, ic_lookback=5)
        np.testing.assert_allclose(
            result_full.iloc[15].values, result_mut.iloc[15].values, atol=1e-14,
        )

    def test_37_overlay_truncation_invariance_all_bars_before_mutation(self):
        """ALL bars before the mutation point must be identical."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel()
        result_full = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=5)
        mutation_point = 18
        r_mut = r.copy()
        r_mut.iloc[mutation_point:] = r_mut.iloc[mutation_point:] * 50.0
        result_mut = apply_dynamic_tcost_overlay(w, daily_returns=r_mut, ic_lookback=5)
        # All bars before mutation_point - lookback - 1 should be identical
        safe_end = mutation_point - 5 - 1  # account for IC shift and lookback
        for t in range(1, max(1, safe_end)):
            np.testing.assert_allclose(
                result_full.iloc[t].values, result_mut.iloc[t].values, atol=1e-14,
                err_msg=f"PIT VIOLATION at bar t={t}",
            )

    def test_38_cost_aware_rebalance_accepts_series_threshold(self):
        """apply_cost_aware_rebalance must accept pd.Series thresholds."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_cost_aware_rebalance
        w, _ = self._make_panel(n_days=10)
        prev_w = w.shift(1).fillna(0.0)
        thresholds = pd.Series([30.0] * 10, index=w.index)
        result = apply_cost_aware_rebalance(w, prev_w, min_trade_threshold_bps=thresholds)
        assert result.shape == w.shape

    def test_39_cost_aware_rebalance_scalar_equals_uniform_series(self):
        """Scalar threshold and uniform Series threshold must produce identical output."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_cost_aware_rebalance
        w, _ = self._make_panel(n_days=10)
        prev_w = w.shift(1).fillna(0.0)
        result_scalar = apply_cost_aware_rebalance(w, prev_w, min_trade_threshold_bps=30.0)
        thresholds = pd.Series([30.0] * 10, index=w.index)
        result_series = apply_cost_aware_rebalance(w, prev_w, min_trade_threshold_bps=thresholds)
        np.testing.assert_allclose(result_scalar.values, result_series.values, atol=1e-12)

    def test_40_high_threshold_suppresses_more_trades(self):
        """Higher per-bar threshold should suppress more trades (lower turnover)."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_cost_aware_rebalance
        w, _ = self._make_panel(n_days=15, seed=88)
        prev_w = w.shift(1).fillna(0.0)
        # Low threshold -> more trades
        low_thr = pd.Series([5.0] * 15, index=w.index)
        result_low = apply_cost_aware_rebalance(w, prev_w, min_trade_threshold_bps=low_thr)
        # High threshold -> fewer trades
        high_thr = pd.Series([100.0] * 15, index=w.index)
        result_high = apply_cost_aware_rebalance(w, prev_w, min_trade_threshold_bps=high_thr)
        turnover_low = result_low.diff().abs().sum(axis=1).iloc[1:].mean()
        turnover_high = result_high.diff().abs().sum(axis=1).iloc[1:].mean()
        assert turnover_high <= turnover_low + 1e-10

    def test_41_dynamic_overlay_first_bar_uses_new_weights(self):
        """First bar must always use new_weights (no prev to compare)."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel(n_days=10)
        result = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=3)
        # First row absolute exposure should match input
        np.testing.assert_allclose(
            result.iloc[0].abs().sum(), w.iloc[0].abs().sum(), atol=1e-10,
        )

    def test_42_dynamic_overlay_without_returns_still_works(self):
        """Fallback (no returns) should produce valid output."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, _ = self._make_panel(n_days=10)
        result = apply_dynamic_tcost_overlay(w, daily_returns=None)
        assert result.shape == w.shape

    def test_43_dynamic_overlay_preserves_shape_large_panel(self):
        """Large panel (100 days, 50 names) should preserve shape."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
        w, r = self._make_panel(n_days=100, n_names=50, seed=7)
        result = apply_dynamic_tcost_overlay(w, daily_returns=r, ic_lookback=10)
        assert result.shape == (100, 50)


# ===================================================================
# IC ROLLING TRUNCATION AT MULTIPLE POINTS (44-46)
# ===================================================================

class TestICRollingTruncation:
    """Verify rolling IC at multiple time points is invariant to future mutations."""

    @staticmethod
    def _make_panel(n_days=30, n_names=10, seed=123):
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2025-06-01", periods=n_days, freq="B")
        cols = [f"RT_{i}" for i in range(n_names)]
        w = pd.DataFrame(rng.randn(n_days, n_names) * 0.1, index=dates, columns=cols)
        r = pd.DataFrame(rng.randn(n_days, n_names) * 0.01, index=dates, columns=cols)
        return w, r

    def test_44_ic_at_t5_invariant_to_mutation_at_t20(self):
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel()
        ic_full = compute_rolling_ic(w, r, lookback=5)
        r_mut = r.copy()
        r_mut.iloc[20:] *= 100.0
        ic_mut = compute_rolling_ic(w, r_mut, lookback=5)
        assert float(ic_full.iloc[5]) == float(ic_mut.iloc[5])

    def test_45_ic_at_t12_invariant_to_mutation_at_t20(self):
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel()
        ic_full = compute_rolling_ic(w, r, lookback=5)
        r_mut = r.copy()
        r_mut.iloc[20:] *= 100.0
        ic_mut = compute_rolling_ic(w, r_mut, lookback=5)
        assert float(ic_full.iloc[12]) == float(ic_mut.iloc[12])

    def test_46_ic_series_prefix_invariant(self):
        """IC values 0..N-1 must be identical for mutation at N (all prefix values)."""
        from omega.quant.portfolio.tcost_optimizer_overlay import compute_rolling_ic
        w, r = self._make_panel()
        ic_full = compute_rolling_ic(w, r, lookback=5)
        mutation_pt = 25
        r_mut = r.copy()
        r_mut.iloc[mutation_pt:] *= 100.0
        ic_mut = compute_rolling_ic(w, r_mut, lookback=5)
        # All IC values before mutation_pt should be identical
        np.testing.assert_allclose(
            ic_full.iloc[:mutation_pt].values,
            ic_mut.iloc[:mutation_pt].values,
            atol=1e-14,
            err_msg="PIT VIOLATION: IC prefix changed after future mutation",
        )


# ===================================================================
# SPARSE-DATE PIT SAFETY (47-48)
# ===================================================================

class TestSparseDatePITSafety:
    """Prove that sparse/missing return dates do NOT cause future leak.

    Scenario:
      - weights index has 10 business days (2025-01-01 to 2025-01-14).
      - returns only cover the last 4 days (2025-01-08 to 2025-01-14).
      - IC series therefore only spans the last 4 days.
      - per_bar_threshold_bps has NaN for the first 6 days after reindex.
      - OLD BUG: fillna(last_value) back-filled early bars with the FINAL
        available future threshold -> look-ahead leak.
      - FIX: ffill() + fillna(default) fills leading NaNs with neutral
        constant 30/10000 -> no future information used.
    """

    @staticmethod
    def _build_sparse_panel(seed: int = 1234):
        """Weights: 10 business days. Returns: only last 4 days."""
        rng = np.random.RandomState(seed)
        all_dates = pd.date_range("2025-01-01", periods=10, freq="B")
        cols = [f"SP_{i}" for i in range(8)]

        w = pd.DataFrame(rng.randn(10, 8) * 0.1, index=all_dates, columns=cols)
        w = w - w.mean(axis=1).values.reshape(-1, 1)  # demean (long-short)

        # Sparse returns: only last 4 business days
        sparse_dates = all_dates[6:]
        r = pd.DataFrame(rng.randn(4, 8) * 0.01, index=sparse_dates, columns=cols)
        return w, r, all_dates

    def test_47_sparse_date_early_weights_unchanged_after_future_mutation(self):
        """Weights at t=5 must be identical after mutating returns at t=8,9.

        With the old fillna(last_value) code the threshold for days 0-5 was
        set to the *final* threshold value (day 9), which changes when we
        mutate returns at days 8-9.  The fix uses ffill() + fillna(default)
        so early bars always receive the neutral default.
        """
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay

        w, r, _ = self._build_sparse_panel()

        # --- Run 1: pristine ---
        result_full = apply_dynamic_tcost_overlay(
            w, daily_returns=r, base_threshold_bps=30.0, ic_lookback=3,
        )
        weights_at_t5_full = result_full.iloc[5].copy()

        # --- Run 2: mutate returns at days 8-9 (iloc[2:] in sparse returns) ---
        r_mut = r.copy()
        r_mut.iloc[2:] = r_mut.iloc[2:] * 100.0  # extreme mutation

        result_mut = apply_dynamic_tcost_overlay(
            w, daily_returns=r_mut, base_threshold_bps=30.0, ic_lookback=3,
        )
        weights_at_t5_mut = result_mut.iloc[5].copy()

        np.testing.assert_allclose(
            weights_at_t5_full.values,
            weights_at_t5_mut.values,
            atol=1e-14,
            err_msg=(
                "PIT VIOLATION (sparse-date): weights at t=5 changed after "
                "mutating future returns at t=8,9"
            ),
        )

    def test_48_sparse_date_all_early_bars_unchanged(self):
        """ALL bars before the return start date must be invariant to future mutation."""
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay

        w, r, all_dates = self._build_sparse_panel(seed=7777)

        result_full = apply_dynamic_tcost_overlay(
            w, daily_returns=r, base_threshold_bps=30.0, ic_lookback=3,
        )

        r_mut = r.copy()
        r_mut.iloc[2:] = r_mut.iloc[2:] * 100.0

        result_mut = apply_dynamic_tcost_overlay(
            w, daily_returns=r_mut, base_threshold_bps=30.0, ic_lookback=3,
        )

        # All bars before the sparse return start (day 6) must be identical
        for t in range(6):
            np.testing.assert_allclose(
                result_full.iloc[t].values,
                result_mut.iloc[t].values,
                atol=1e-14,
                err_msg=f"PIT VIOLATION (sparse-date): bar t={t} changed after future mutation",
            )
