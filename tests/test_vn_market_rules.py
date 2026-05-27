"""
Unit Tests for VnMarketRules - omega.core.vn_market_rules

Tests cover:
- round_board_lot: Board lot rounding logic
- round_price_tick: Price tick rounding logic
- get_tick_size: Tick size lookup by price level
- calculate_price_limits: Ceiling/floor price calculation

PIT Safety: All tests use static/deterministic data only.
No future-looking data, no T+0 leakage.

Author: OpenCode (Role 9 - Backend Engineer)
Date: 2026-05-27
"""

import pytest

from omega.core.vn_market_rules import VnMarketRules


# =============================================================================
# round_board_lot tests
# =============================================================================

class TestRoundBoardLot:
    """Tests for VnMarketRules.round_board_lot()."""

    def test_exact_board_lot(self):
        """Exact multiples of 100 remain unchanged."""
        assert VnMarketRules.round_board_lot(100) == 100
        assert VnMarketRules.round_board_lot(200) == 200
        assert VnMarketRules.round_board_lot(1000) == 1000

    def test_rounds_down(self):
        """Values below midpoint round down."""
        assert VnMarketRules.round_board_lot(1234) == 1200
        assert VnMarketRules.round_board_lot(149) == 100
        assert VnMarketRules.round_board_lot(1249) == 1200

    def test_rounds_up(self):
        """Values above midpoint round up."""
        assert VnMarketRules.round_board_lot(1251) == 1300
        assert VnMarketRules.round_board_lot(1299) == 1300
        assert VnMarketRules.round_board_lot(151) == 200

    def test_bankers_rounding_midpoint(self):
        """Exact midpoints use banker's rounding (round to even)."""
        # 1250 / 100 = 12.5 -> rounds to 12 (even)
        assert VnMarketRules.round_board_lot(1250) == 1200
        # 1350 / 100 = 13.5 -> rounds to 14 (even)
        assert VnMarketRules.round_board_lot(1350) == 1400
        # 150 / 100 = 1.5 -> rounds to 2 (even)
        assert VnMarketRules.round_board_lot(150) == 200
        # 250 / 100 = 2.5 -> rounds to 2 (even)
        assert VnMarketRules.round_board_lot(250) == 200

    def test_minimum_board_lot(self):
        """Small positive values get at least one board lot (100)."""
        assert VnMarketRules.round_board_lot(1) == 100
        assert VnMarketRules.round_board_lot(49) == 100
        assert VnMarketRules.round_board_lot(50) == 100

    def test_zero_returns_zero(self):
        """Zero shares returns zero."""
        assert VnMarketRules.round_board_lot(0) == 0

    def test_negative_returns_zero(self):
        """Negative shares returns zero."""
        assert VnMarketRules.round_board_lot(-100) == 0
        assert VnMarketRules.round_board_lot(-1) == 0

    def test_float_input(self):
        """Float inputs are handled correctly."""
        assert VnMarketRules.round_board_lot(1234.5) == 1200
        # 1250.0 / 100 = 12.5 -> banker's rounding to 12
        assert VnMarketRules.round_board_lot(1250.0) == 1200
        assert VnMarketRules.round_board_lot(1251.0) == 1300

    def test_large_values(self):
        """Large share counts round correctly."""
        assert VnMarketRules.round_board_lot(999_999) == 1_000_000
        assert VnMarketRules.round_board_lot(1_000_001) == 1_000_000


# =============================================================================
# round_price_tick tests
# =============================================================================

class TestRoundPriceTick:
    """Tests for VnMarketRules.round_price_tick()."""

    def test_tick_10_range(self):
        """Prices < 10,000 VND use tick size 10."""
        # 5005 / 10 = 500.5 -> banker's rounds to 500 (even)
        assert VnMarketRules.round_price_tick(5_005) == 5_000
        # 5006 / 10 = 500.6 -> rounds to 501
        assert VnMarketRules.round_price_tick(5_006) == 5_010
        assert VnMarketRules.round_price_tick(9_876) == 9_880
        assert VnMarketRules.round_price_tick(9_990) == 9_990

    def test_tick_50_range(self):
        """Prices 10,000 - 50,000 VND use tick size 50."""
        # 10025 / 50 = 200.5 -> banker's rounds to 200 (even)
        assert VnMarketRules.round_price_tick(10_025) == 10_000
        # 10026 / 50 = 200.52 -> rounds to 201
        assert VnMarketRules.round_price_tick(10_026) == 10_050
        assert VnMarketRules.round_price_tick(45_678) == 45_700
        assert VnMarketRules.round_price_tick(49_999) == 50_000

    def test_tick_100_range(self):
        """Prices 50,000 - 100,000 VND use tick size 100."""
        # 50050 / 100 = 500.5 -> banker's rounds to 500 (even)
        assert VnMarketRules.round_price_tick(50_050) == 50_000
        # 50051 / 100 = 500.51 -> rounds to 501
        assert VnMarketRules.round_price_tick(50_051) == 50_100
        assert VnMarketRules.round_price_tick(75_432) == 75_400
        assert VnMarketRules.round_price_tick(99_999) == 100_000

    def test_tick_500_range(self):
        """Prices 100,000 - 500,000 VND use tick size 500."""
        assert VnMarketRules.round_price_tick(123_456) == 123_500
        assert VnMarketRules.round_price_tick(250_249) == 250_000
        # 250250 / 500 = 500.5 -> banker's rounds to 500 (even)
        assert VnMarketRules.round_price_tick(250_250) == 250_000
        # 250251 / 500 = 500.502 -> rounds to 501
        assert VnMarketRules.round_price_tick(250_251) == 250_500

    def test_tick_1000_range(self):
        """Prices >= 500,000 VND use tick size 1000."""
        assert VnMarketRules.round_price_tick(567_890) == 568_000
        assert VnMarketRules.round_price_tick(500_499) == 500_000
        # 500500 / 1000 = 500.5 -> banker's rounds to 500 (even)
        assert VnMarketRules.round_price_tick(500_500) == 500_000
        # 500501 / 1000 = 500.501 -> rounds to 501
        assert VnMarketRules.round_price_tick(500_501) == 501_000

    def test_exact_tick_unchanged(self):
        """Prices already on tick boundary remain unchanged."""
        assert VnMarketRules.round_price_tick(10_000) == 10_000
        assert VnMarketRules.round_price_tick(50_000) == 50_000
        assert VnMarketRules.round_price_tick(100_000) == 100_000

    def test_zero_returns_zero(self):
        """Zero price returns 0.0."""
        assert VnMarketRules.round_price_tick(0) == 0.0

    def test_negative_returns_zero(self):
        """Negative price returns 0.0."""
        assert VnMarketRules.round_price_tick(-1000) == 0.0


# =============================================================================
# get_tick_size tests
# =============================================================================

class TestGetTickSize:
    """Tests for VnMarketRules.get_tick_size()."""

    def test_below_10k(self):
        """Prices below 10,000 VND have tick size 10."""
        assert VnMarketRules.get_tick_size(100) == 10.0
        assert VnMarketRules.get_tick_size(5_000) == 10.0
        assert VnMarketRules.get_tick_size(9_999) == 10.0

    def test_10k_to_50k(self):
        """Prices 10,000 to 50,000 VND have tick size 50."""
        assert VnMarketRules.get_tick_size(10_000) == 50.0
        assert VnMarketRules.get_tick_size(25_000) == 50.0
        assert VnMarketRules.get_tick_size(49_999) == 50.0

    def test_50k_to_100k(self):
        """Prices 50,000 to 100,000 VND have tick size 100."""
        assert VnMarketRules.get_tick_size(50_000) == 100.0
        assert VnMarketRules.get_tick_size(75_000) == 100.0
        assert VnMarketRules.get_tick_size(99_999) == 100.0

    def test_100k_to_500k(self):
        """Prices 100,000 to 500,000 VND have tick size 500."""
        assert VnMarketRules.get_tick_size(100_000) == 500.0
        assert VnMarketRules.get_tick_size(300_000) == 500.0
        assert VnMarketRules.get_tick_size(499_999) == 500.0

    def test_above_500k(self):
        """Prices >= 500,000 VND have tick size 1000."""
        assert VnMarketRules.get_tick_size(500_000) == 1000.0
        assert VnMarketRules.get_tick_size(1_000_000) == 1000.0
        assert VnMarketRules.get_tick_size(10_000_000) == 1000.0

    def test_boundary_values(self):
        """Boundary prices fall into the correct range."""
        # 9,999 is in <10k range, 10,000 is in 10k-50k range
        assert VnMarketRules.get_tick_size(9_999) == 10.0
        assert VnMarketRules.get_tick_size(10_000) == 50.0
        # 49,999 is in 10k-50k range, 50,000 is in 50k-100k range
        assert VnMarketRules.get_tick_size(49_999) == 50.0
        assert VnMarketRules.get_tick_size(50_000) == 100.0


# =============================================================================
# calculate_price_limits tests
# =============================================================================

class TestCalculatePriceLimits:
    """Tests for VnMarketRules.calculate_price_limits()."""

    def test_standard_limits(self):
        """Standard +/-7% price limits with tick rounding."""
        floor, ceiling = VnMarketRules.calculate_price_limits(100_000)
        # 100,000 * 0.93 = 93,000 (already on tick 500)
        # 100,000 * 1.07 = 107,000 (already on tick 500)
        assert floor == 93_000.0
        assert ceiling == 107_000.0

    def test_limits_with_rounding(self):
        """Price limits are rounded to appropriate tick size."""
        floor, ceiling = VnMarketRules.calculate_price_limits(50_000)
        # 50,000 * 0.93 = 46,500 (tick 50 range, already on tick)
        # 50,000 * 1.07 = 53,500 (tick 100 range, already on tick)
        assert floor == 46_500.0
        assert ceiling == 53_500.0

    def test_low_price_limits(self):
        """Price limits for low-priced stocks."""
        floor, ceiling = VnMarketRules.calculate_price_limits(10_000)
        # 10,000 * 0.93 = 9,300 (tick 10 range -> 9,300)
        # 10,000 * 1.07 = 10,700 (tick 50 range -> 10,700)
        assert floor == 9_300.0
        assert ceiling == 10_700.0

    def test_negative_reference_raises(self):
        """Negative reference price raises ValueError."""
        with pytest.raises(ValueError, match="Reference price must be positive"):
            VnMarketRules.calculate_price_limits(-100_000)

    def test_zero_reference_raises(self):
        """Zero reference price raises ValueError."""
        with pytest.raises(ValueError, match="Reference price must be positive"):
            VnMarketRules.calculate_price_limits(0)

    def test_floor_less_than_ceiling(self):
        """Floor is always less than ceiling."""
        test_prices = [5_000, 20_000, 75_000, 200_000, 800_000]
        for price in test_prices:
            floor, ceiling = VnMarketRules.calculate_price_limits(price)
            assert floor < ceiling, f"Floor {floor} >= Ceiling {ceiling} for price {price}"


# =============================================================================
# Integration / PIT Safety tests
# =============================================================================

class TestPITSafety:
    """Verify no future-looking data or T+0 leakage in market rules."""

    def test_no_dynamic_data(self):
        """All rules are static constants - no external data dependency."""
        # Verify constants are deterministic
        assert VnMarketRules.BOARD_LOT == 100
        assert VnMarketRules.PRICE_LIMIT_PERCENT == 0.07
        assert VnMarketRules.SETTLEMENT_DAYS == 2

    def test_deterministic_output(self):
        """Same input always produces same output (no randomness)."""
        for _ in range(10):
            assert VnMarketRules.round_board_lot(1234) == 1200
            assert VnMarketRules.round_price_tick(45_678) == 45_700
            assert VnMarketRules.get_tick_size(75_000) == 100.0

    def test_no_time_dependency(self):
        """Functions do not depend on current time."""
        # All functions are pure - input determines output
        result1 = VnMarketRules.calculate_price_limits(100_000)
        result2 = VnMarketRules.calculate_price_limits(100_000)
        assert result1 == result2
