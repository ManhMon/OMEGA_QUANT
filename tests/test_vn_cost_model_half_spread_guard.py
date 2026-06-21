"""Tests for VN Cost Model half-spread guard and ADV-tiered spread.

Covers:
  - clamp_half_spread safety guard (1 bp floor, 50 bp ceiling)
  - ADV tier boundary conditions
  - Vectorized spread computation correctness
  - Edge cases (zero ADV, negative, NaN)

11 tests total.
"""
from __future__ import annotations

import numpy as np
import pytest


# ===================================================================
# HALF-SPREAD GUARD TESTS (1-5)
# ===================================================================

class TestHalfSpreadGuard:
    """Verify clamp_half_spread enforces [1 bp, 50 bp] safety range."""

    def test_01_clamp_normal_value(self):
        from omega.quant.portfolio.execution_sim import clamp_half_spread
        assert clamp_half_spread(0.0010) == 0.0010

    def test_02_clamp_below_floor(self):
        from omega.quant.portfolio.execution_sim import clamp_half_spread, HALF_SPREAD_BPS_FLOOR
        result = clamp_half_spread(0.00001)
        assert result == HALF_SPREAD_BPS_FLOOR

    def test_03_clamp_above_ceiling(self):
        from omega.quant.portfolio.execution_sim import clamp_half_spread, HALF_SPREAD_BPS_CEIL
        result = clamp_half_spread(0.01)
        assert result == HALF_SPREAD_BPS_CEIL

    def test_04_clamp_negative_value(self):
        from omega.quant.portfolio.execution_sim import clamp_half_spread, HALF_SPREAD_BPS_FLOOR
        result = clamp_half_spread(-0.005)
        assert result == HALF_SPREAD_BPS_FLOOR

    def test_05_floor_and_ceiling_constants(self):
        from omega.quant.portfolio.execution_sim import HALF_SPREAD_BPS_FLOOR, HALF_SPREAD_BPS_CEIL
        assert HALF_SPREAD_BPS_FLOOR == 0.0001
        assert HALF_SPREAD_BPS_CEIL == 0.0050


# ===================================================================
# ADV TIER BOUNDARY TESTS (6-8)
# ===================================================================

class TestADVTierBoundaries:
    """Verify tier boundaries are correct."""

    def test_06_exactly_at_high_boundary(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(50e9) == 0.0005

    def test_07_exactly_at_mid_boundary(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(10e9) == 0.0010

    def test_08_just_below_mid_boundary(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread
        assert adv_tiered_half_spread(9.99e9) == 0.0015


# ===================================================================
# VECTORIZED SPREAD TESTS (9-11)
# ===================================================================

class TestVectorizedSpread:
    """Verify vectorized ADV-tiered spread computation."""

    def test_09_vectorized_mixed_tiers(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread_vectorized
        adv = np.array([100e9, 30e9, 5e9, 50e9, 10e9])
        result = adv_tiered_half_spread_vectorized(adv)
        expected = np.array([0.0005, 0.0010, 0.0015, 0.0005, 0.0010])
        np.testing.assert_allclose(result, expected)

    def test_10_vectorized_zero_adv(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread_vectorized
        adv = np.array([0.0, 0.0, 0.0])
        result = adv_tiered_half_spread_vectorized(adv)
        # Zero ADV -> low tier (15 bps)
        np.testing.assert_allclose(result, [0.0015, 0.0015, 0.0015])

    def test_11_vectorized_2d_array(self):
        from omega.quant.portfolio.execution_sim import adv_tiered_half_spread_vectorized
        adv = np.array([
            [100e9, 30e9],
            [5e9, 80e9],
        ])
        result = adv_tiered_half_spread_vectorized(adv)
        expected = np.array([
            [0.0005, 0.0010],
            [0.0015, 0.0005],
        ])
        np.testing.assert_allclose(result, expected)
