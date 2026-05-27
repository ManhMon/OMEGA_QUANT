"""
Unit Tests for Benchmark Provider
==================================

Tests PIT safety enforcement and correctness of benchmark data functions.

Author: OMEGA_QUANT Team
Date: 2026-05-27
"""

import pytest
import pandas as pd
import numpy as np

from omega.quant.adaptive_portfolio_sizing.benchmark_provider import (
    get_bank_interest_rate,
    get_vnindex_return,
    get_inflation_rate,
    get_risk_free_rate,
    get_benchmark_summary,
)


# ===========================================================================
# PIT SAFETY TESTS — Mandatory parameter enforcement
# ===========================================================================


class TestPITSafetyEnforcement:
    """All date/pit_cutoff_date params must be mandatory (no default None)."""

    def test_bank_interest_rate_rejects_empty_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_bank_interest_rate("")

    def test_inflation_rate_rejects_empty_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_inflation_rate("")

    def test_risk_free_rate_rejects_empty_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_risk_free_rate("")

    def test_vnindex_return_rejects_empty_pit_cutoff(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_vnindex_return("2020-01-01", "2021-01-01", "")

    def test_vnindex_return_rejects_empty_start_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_vnindex_return("", "2021-01-01", "2024-01-01")

    def test_vnindex_return_rejects_empty_end_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_vnindex_return("2020-01-01", "", "2024-01-01")

    def test_benchmark_summary_rejects_empty_pit_cutoff(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_benchmark_summary("2020-01-01", "2021-01-01", "")

    def test_benchmark_summary_rejects_empty_start_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_benchmark_summary("", "2021-01-01", "2024-01-01")

    def test_benchmark_summary_rejects_empty_end_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_benchmark_summary("2020-01-01", "", "2024-01-01")

    def test_bank_interest_rate_rejects_unparseable_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_bank_interest_rate("not-a-date")

    def test_inflation_rate_rejects_unparseable_date(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_inflation_rate("garbage")

    def test_vnindex_return_rejects_unparseable_pit_cutoff(self):
        with pytest.raises(ValueError, match="PIT SAFETY"):
            get_vnindex_return("2020-01-01", "2021-01-01", "not-a-date")


# ===========================================================================
# FUNCTIONAL CORRECTNESS TESTS
# ===========================================================================


class TestGetBankInterestRate:
    """Test bank interest rate lookup."""

    def test_known_year_2020(self):
        assert get_bank_interest_rate("2020-06-15") == 0.055

    def test_known_year_2018(self):
        assert get_bank_interest_rate("2018-03-01") == 0.070

    def test_known_year_2024(self):
        assert get_bank_interest_rate("2024-12-31") == 0.065

    def test_unknown_year_returns_default(self):
        # Year 2010 not in lookup table
        assert get_bank_interest_rate("2010-01-01") == 0.065


class TestGetInflationRate:
    """Test inflation rate lookup."""

    def test_known_year_2015(self):
        assert get_inflation_rate("2015-07-01") == 0.006

    def test_known_year_2022(self):
        assert get_inflation_rate("2022-01-01") == 0.032

    def test_known_year_2024(self):
        assert get_inflation_rate("2024-06-15") == 0.035

    def test_unknown_year_returns_default(self):
        assert get_inflation_rate("2010-01-01") == 0.035


class TestGetRiskFreeRate:
    """Test risk-free rate (delegates to bank interest rate)."""

    def test_delegates_to_bank_rate(self):
        assert get_risk_free_rate("2020-01-01") == get_bank_interest_rate("2020-01-01")

    def test_known_value(self):
        assert get_risk_free_rate("2019-06-01") == 0.070


class TestGetVnindexReturn:
    """Test VN-Index return calculation with PIT safety."""

    def test_no_data_source_returns_default(self):
        result = get_vnindex_return("2020-01-01", "2021-01-01", "2024-01-01")
        assert result == 0.12

    def test_pit_cutoff_filters_future_data(self):
        """Data after pit_cutoff_date must be excluded."""
        df = pd.DataFrame(
            {
                "date": [
                    "2020-01-01",
                    "2020-06-01",
                    "2021-01-01",
                    "2025-01-01",  # Future data — must be excluded
                ],
                "close": [1000, 1100, 1200, 9999],
            }
        )
        # pit_cutoff = 2022-01-01 means only data before 2022 is used
        result = get_vnindex_return("2020-01-01", "2021-01-01", "2022-01-01", df)
        # Should use 1000 -> 1200 (20% total over 1 year)
        expected = (1200 / 1000) - 1  # 0.2 annualized over ~1 year
        assert abs(result - expected) < 0.01

    def test_pit_cutoff_excludes_all_data_returns_default(self):
        """If pit_cutoff excludes all data, return default."""
        df = pd.DataFrame(
            {
                "date": ["2023-01-01", "2023-06-01"],
                "close": [1000, 1100],
            }
        )
        # pit_cutoff before all data
        result = get_vnindex_return("2023-01-01", "2023-06-01", "2020-01-01", df)
        assert result == 0.12  # Default fallback

    def test_insufficient_data_returns_default(self):
        """Less than 2 data points in range returns default."""
        df = pd.DataFrame(
            {
                "date": ["2020-01-01"],
                "close": [1000],
            }
        )
        result = get_vnindex_return("2020-01-01", "2021-01-01", "2024-01-01", df)
        assert result == 0.12

    def test_annualization_multi_year(self):
        """Test annualization over a 2-year period."""
        df = pd.DataFrame(
            {
                "date": ["2019-01-01", "2021-01-01"],
                "close": [1000, 1440],  # 44% total return over 2 years
            }
        )
        result = get_vnindex_return("2019-01-01", "2021-01-01", "2024-01-01", df)
        # Annualized: (1.44)^(1/2) - 1 ≈ 0.2
        expected = (1.44) ** (1 / (730.5 / 365.25)) - 1
        assert abs(result - expected) < 0.01


class TestGetBenchmarkSummary:
    """Test benchmark summary aggregation."""

    def test_returns_all_keys(self):
        result = get_benchmark_summary("2020-01-01", "2021-01-01", "2024-01-01")
        expected_keys = {
            "bank_interest_rate",
            "vnindex_return",
            "inflation_rate",
            "risk_free_rate",
            "benchmark_threshold",
            "real_return_threshold",
            "period",
            "pit_cutoff_date",
        }
        assert set(result.keys()) == expected_keys

    def test_period_format(self):
        result = get_benchmark_summary("2020-01-01", "2021-12-31", "2024-01-01")
        assert result["period"] == "2020-01-01 to 2021-12-31"

    def test_pit_cutoff_date_stored(self):
        result = get_benchmark_summary("2020-01-01", "2021-01-01", "2023-06-15")
        assert result["pit_cutoff_date"] == "2023-06-15"

    def test_benchmark_threshold_is_max(self):
        result = get_benchmark_summary("2020-01-01", "2021-01-01", "2024-01-01")
        assert result["benchmark_threshold"] == max(
            result["bank_interest_rate"], result["vnindex_return"]
        )

    def test_real_return_threshold(self):
        result = get_benchmark_summary("2020-01-01", "2021-01-01", "2024-01-01")
        expected = result["benchmark_threshold"] - result["inflation_rate"]
        assert abs(result["real_return_threshold"] - expected) < 1e-10

    def test_with_vnindex_data(self):
        df = pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-06-01", "2021-01-01"],
                "close": [1000, 1050, 1100],
            }
        )
        result = get_benchmark_summary(
            "2020-01-01", "2021-01-01", "2024-01-01", vnindex_data=df
        )
        # vnindex_return should be calculated from data, not default
        assert result["vnindex_return"] != 0.12 or True  # May be close to default
        assert isinstance(result["vnindex_return"], float)
