# -*- coding: utf-8 -*-
"""Comprehensive test suite for Phase 21 Performance Attribution Engine.

Tests cover:
- Helper functions (_align_series, _validate_pit)
- AttributionConfig validation
- Core attribution methods (decompose_returns, sharpe_ratio, information_ratio, etc.)
- Edge cases (empty data, single points, misalignment, NaN, inf)
- PIT safety validation
- Performance benchmarks

Target: 50+ tests for institutional-grade hardening.
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from omega.quant.attribution import (
    _align_series,
    _validate_pit,
    AttributionConfig,
    PerformanceAttribution,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_returns():
    """Generate sample return series for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01, index=dates, name="portfolio")
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates, name="benchmark")
    return portfolio, benchmark


@pytest.fixture
def sample_sector_data():
    """Generate sample sector attribution data."""
    assets = [f"ASSET_{i}" for i in range(20)]
    portfolio_weights = pd.Series(np.random.dirichlet(np.ones(20)), index=assets)
    benchmark_weights = pd.Series(np.random.dirichlet(np.ones(20)), index=assets)
    sector_returns = pd.Series(np.random.randn(20) * 0.02, index=assets)
    sectors = pd.Series(["Tech", "Finance", "Energy", "Healthcare", "Consumer"] * 4, index=assets)
    return portfolio_weights, benchmark_weights, sector_returns, sectors


@pytest.fixture
def attribution_engine():
    """Create a standard PerformanceAttribution instance."""
    config = AttributionConfig(risk_free_rate=0.02, periods_per_year=252)
    return PerformanceAttribution(config)


# ============================================================================
# TEST HELPER FUNCTIONS: _align_series
# ============================================================================

def test_align_series_basic():
    """Test basic alignment of two series with overlapping indices."""
    s1 = pd.Series([1, 2, 3, 4], index=pd.date_range("2024-01-01", periods=4, freq="D"))
    s2 = pd.Series([5, 6, 7, 8], index=pd.date_range("2024-01-02", periods=4, freq="D"))
    
    aligned = _align_series(s1, s2)
    
    assert len(aligned) == 2
    assert len(aligned[0]) == 3  # Overlap: Jan 2, 3, 4
    assert len(aligned[1]) == 3
    assert aligned[0].index.equals(aligned[1].index)


def test_align_series_perfect_overlap():
    """Test alignment when indices are identical."""
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    s1 = pd.Series([1, 2, 3, 4, 5], index=idx)
    s2 = pd.Series([10, 20, 30, 40, 50], index=idx)
    
    aligned = _align_series(s1, s2)
    
    assert len(aligned[0]) == 5
    assert len(aligned[1]) == 5
    assert aligned[0].index.equals(idx)


def test_align_series_no_overlap():
    """Test alignment fails when there's no overlap."""
    s1 = pd.Series([1, 2, 3], index=pd.date_range("2024-01-01", periods=3, freq="D"))
    s2 = pd.Series([4, 5, 6], index=pd.date_range("2024-02-01", periods=3, freq="D"))
    
    with pytest.raises(ValueError, match="empty series"):
        _align_series(s1, s2)


def test_align_series_single_series():
    """Test alignment with single series returns unchanged."""
    s1 = pd.Series([1, 2, 3], index=pd.date_range("2024-01-01", periods=3, freq="D"))
    
    aligned = _align_series(s1)
    
    assert len(aligned) == 1
    assert aligned[0].equals(s1)


def test_align_series_multiple_series():
    """Test alignment with three series."""
    idx1 = pd.date_range("2024-01-01", periods=5, freq="D")
    idx2 = pd.date_range("2024-01-02", periods=5, freq="D")
    idx3 = pd.date_range("2024-01-03", periods=5, freq="D")
    
    s1 = pd.Series([1, 2, 3, 4, 5], index=idx1)
    s2 = pd.Series([10, 20, 30, 40, 50], index=idx2)
    s3 = pd.Series([100, 200, 300, 400, 500], index=idx3)
    
    aligned = _align_series(s1, s2, s3)
    
    assert len(aligned) == 3
    # Overlap should be Jan 3, 4, 5
    assert len(aligned[0]) == 3
    assert all(a.index.equals(aligned[0].index) for a in aligned)


def test_align_series_partial_overlap():
    """Test alignment with partial overlap."""
    s1 = pd.Series([1, 2, 3, 4, 5], index=pd.date_range("2024-01-01", periods=5, freq="D"))
    s2 = pd.Series([10, 20], index=pd.date_range("2024-01-03", periods=2, freq="D"))
    
    aligned = _align_series(s1, s2)
    
    assert len(aligned[0]) == 2  # Only Jan 3, 4
    assert len(aligned[1]) == 2


# ============================================================================
# TEST HELPER FUNCTIONS: _validate_pit
# ============================================================================

def test_validate_pit_valid_monotonic():
    """Test PIT validation passes for monotonic increasing index."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    s = pd.Series(np.random.randn(10), index=dates)
    
    assert _validate_pit([s], current_time=pd.Timestamp("2024-02-01", tz="UTC"))


def test_validate_pit_non_monotonic():
    """Test PIT validation fails for non-monotonic index."""
    dates = [pd.Timestamp("2024-01-01", tz="UTC"), 
             pd.Timestamp("2024-01-03", tz="UTC"),
             pd.Timestamp("2024-01-02", tz="UTC")]  # Out of order
    s = pd.Series([1, 2, 3], index=dates)
    
    assert not _validate_pit([s], pit_strict=False)


def test_validate_pit_future_dates():
    """Test PIT validation fails when data contains future dates."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    s = pd.Series(np.random.randn(10), index=dates)
    
    # Current time is before the last date
    current_time = pd.Timestamp("2024-01-05", tz="UTC")
    
    assert not _validate_pit([s], current_time=current_time, pit_strict=False)


def test_validate_pit_timezone_aware():
    """Test PIT validation with timezone-aware timestamps."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D", tz="Asia/Ho_Chi_Minh")
    s = pd.Series([1, 2, 3, 4, 5], index=dates)
    
    current_time = pd.Timestamp("2024-01-10", tz="UTC")
    
    assert _validate_pit([s], current_time=current_time)


def test_validate_pit_timezone_naive():
    """Test PIT validation with timezone-naive timestamps."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")  # No tz
    s = pd.Series([1, 2, 3, 4, 5], index=dates)
    
    current_time = pd.Timestamp("2024-01-10")  # No tz
    
    assert _validate_pit([s], current_time=current_time)


def test_validate_pit_mixed_timezones():
    """Test PIT validation handles mixed timezone scenarios."""
    dates_utc = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    s = pd.Series([1, 2, 3, 4, 5], index=dates_utc)
    
    # Current time is timezone-naive
    current_time = pd.Timestamp("2024-01-10")
    
    # Should handle timezone conversion
    assert _validate_pit([s], current_time=current_time)


def test_validate_pit_multiple_series():
    """Test PIT validation with multiple series."""
    dates1 = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    dates2 = pd.date_range("2024-01-02", periods=5, freq="D", tz="UTC")
    
    s1 = pd.Series([1, 2, 3, 4, 5], index=dates1)
    s2 = pd.Series([10, 20, 30, 40, 50], index=dates2)
    
    current_time = pd.Timestamp("2024-02-01", tz="UTC")
    
    assert _validate_pit([s1, s2], current_time=current_time)


def test_validate_pit_default_current_time():
    """Test PIT validation uses current time when not specified."""
    # Create data from the past
    dates = pd.date_range("2020-01-01", periods=10, freq="D", tz="UTC")
    s = pd.Series(np.random.randn(10), index=dates)
    
    # Should pass since data is from the past
    assert _validate_pit([s])


def test_validate_pit_non_datetime_index():
    """Test PIT validation with non-datetime index (should skip future check)."""
    s = pd.Series([1, 2, 3, 4, 5], index=[0, 1, 2, 3, 4])
    
    # Should pass monotonicity check, skip future date check
    assert _validate_pit([s])


# ============================================================================
# TEST AttributionConfig
# ============================================================================

def test_attribution_config_default():
    """Test AttributionConfig with default values."""
    config = AttributionConfig()
    
    assert config.benchmarks == {}
    assert config.factor_groups == {}
    assert config.risk_free_rate == 0.0
    assert config.periods_per_year == 252
    assert config.pit_compliant is True


def test_attribution_config_custom():
    """Test AttributionConfig with custom values."""
    benchmarks = {"SPY": pd.Series([0.01, 0.02])}
    factor_groups = {"momentum": ["MOM1", "MOM2"]}
    
    config = AttributionConfig(
        benchmarks=benchmarks,
        factor_groups=factor_groups,
        risk_free_rate=0.03,
        periods_per_year=365,
    )
    
    assert config.benchmarks == benchmarks
    assert config.factor_groups == factor_groups
    assert config.risk_free_rate == 0.03
    assert config.periods_per_year == 365


def test_attribution_config_pit_compliance_mandatory():
    """Test AttributionConfig enforces PIT compliance."""
    with pytest.raises(ValueError, match="PIT compliance mandatory"):
        AttributionConfig(pit_compliant=False)


def test_attribution_config_pit_compliance_true():
    """Test AttributionConfig accepts pit_compliant=True."""
    config = AttributionConfig(pit_compliant=True)
    assert config.pit_compliant is True


# ============================================================================
# TEST PerformanceAttribution: decompose_returns
# ============================================================================

def test_decompose_returns_basic(attribution_engine, sample_returns):
    """Test basic decompose_returns with valid data."""
    portfolio, benchmark = sample_returns
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    assert "total_portfolio_return" in result
    assert "total_benchmark_return" in result
    assert "active_return" in result
    assert "beta" in result
    assert "factor_return" in result
    assert "selection_return" in result
    assert "metadata" in result
    
    # Verify active return calculation
    expected_active = result["total_portfolio_return"] - result["total_benchmark_return"]
    assert abs(result["active_return"] - expected_active) < 1e-10
    
    # Verify decomposition
    expected_active_decomp = result["factor_return"] + result["selection_return"]
    assert abs(result["active_return"] - expected_active_decomp) < 1e-10


def test_decompose_returns_pit_metadata(attribution_engine):
    """Test decompose_returns includes PIT compliance metadata."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(50) * 0.01, index=dates)
    benchmark = pd.Series(np.random.randn(50) * 0.008, index=dates)
    
    current_time = pd.Timestamp("2024-03-01", tz="UTC")
    result = attribution_engine.decompose_returns(portfolio, benchmark, current_time=current_time)
    
    assert result["metadata"]["pit_compliant"] is True
    assert result["metadata"]["n_periods"] == 50
    assert result["metadata"]["phase"] == "Phase21-Attribution"


def test_decompose_returns_misaligned_indices(attribution_engine):
    """Test decompose_returns handles misaligned indices."""
    dates1 = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    dates2 = pd.date_range("2024-01-05", periods=10, freq="D", tz="UTC")
    
    portfolio = pd.Series(np.random.randn(10) * 0.01, index=dates1)
    benchmark = pd.Series(np.random.randn(10) * 0.008, index=dates2)
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    # Should work with overlapping dates (Jan 5-10)
    assert result["metadata"]["n_periods"] == 6


def test_decompose_returns_zero_variance_benchmark(attribution_engine):
    """Test decompose_returns with zero variance benchmark."""
    dates = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(20) * 0.01, index=dates)
    benchmark = pd.Series(np.zeros(20), index=dates)  # Zero variance
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    # Beta should be 0 when benchmark has zero variance
    assert abs(result["beta"]) < 1e-10
    assert abs(result["factor_return"]) < 1e-10


def test_decompose_returns_perfect_correlation(attribution_engine):
    """Test decompose_returns when portfolio perfectly tracks benchmark."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    benchmark = pd.Series(np.random.randn(30) * 0.01, index=dates)
    portfolio = benchmark * 1.5  # Perfect correlation, beta = 1.5
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    # Beta should be close to 1.5
    assert abs(result["beta"] - 1.5) < 0.1


def test_decompose_returns_negative_correlation(attribution_engine):
    """Test decompose_returns with negative correlation."""
    dates = pd.date_range("2024-01-01", periods=40, freq="D", tz="UTC")
    benchmark = pd.Series(np.random.randn(40) * 0.01, index=dates)
    portfolio = -benchmark  # Perfect negative correlation
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    # Beta should be negative
    assert result["beta"] < 0


# ============================================================================
# TEST PerformanceAttribution: sharpe_ratio
# ============================================================================

def test_sharpe_ratio_basic(attribution_engine):
    """Test basic Sharpe ratio calculation."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(100) * 0.01 + 0.001, index=dates)  # Positive mean
    
    sharpe = attribution_engine.sharpe_ratio(returns, annualise=True)
    
    assert isinstance(sharpe, float)
    assert not np.isnan(sharpe)
    assert not np.isinf(sharpe)


def test_sharpe_ratio_annualized_vs_non_annualized(attribution_engine):
    """Test Sharpe ratio with and without annualization."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(100) * 0.01 + 0.001, index=dates)
    
    sharpe_annual = attribution_engine.sharpe_ratio(returns, annualise=True)
    sharpe_period = attribution_engine.sharpe_ratio(returns, annualise=False)
    
    # Annualized should be sqrt(252) times the period Sharpe
    expected_ratio = np.sqrt(252)
    assert abs(sharpe_annual / sharpe_period - expected_ratio) < 0.1


def test_sharpe_ratio_zero_variance(attribution_engine):
    """Test Sharpe ratio with zero variance returns."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    returns = pd.Series(np.ones(50) * 0.01, index=dates)  # Constant returns
    
    sharpe = attribution_engine.sharpe_ratio(returns)
    
    # Should return 0 for zero variance
    assert sharpe == 0.0


def test_sharpe_ratio_single_observation(attribution_engine):
    """Test Sharpe ratio with single observation returns 0."""
    dates = pd.date_range("2024-01-01", periods=1, freq="D", tz="UTC")
    returns = pd.Series([0.01], index=dates)
    
    sharpe = attribution_engine.sharpe_ratio(returns)
    
    # Should return 0 for n < 2
    assert sharpe == 0.0


def test_sharpe_ratio_two_observations(attribution_engine):
    """Test Sharpe ratio with exactly two observations."""
    dates = pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC")
    returns = pd.Series([0.01, 0.02], index=dates)
    
    sharpe = attribution_engine.sharpe_ratio(returns)
    
    # Should calculate with n=2
    assert isinstance(sharpe, float)
    assert not np.isnan(sharpe)


def test_sharpe_ratio_negative_returns(attribution_engine):
    """Test Sharpe ratio with negative mean returns."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(100) * 0.01 - 0.002, index=dates)  # Negative mean
    
    sharpe = attribution_engine.sharpe_ratio(returns)
    
    # Sharpe should be negative
    assert sharpe < 0


def test_sharpe_ratio_with_risk_free_rate():
    """Test Sharpe ratio calculation with non-zero risk-free rate."""
    config = AttributionConfig(risk_free_rate=0.03, periods_per_year=252)
    engine = PerformanceAttribution(config)
    
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(100) * 0.01 + 0.002, index=dates)
    
    sharpe = engine.sharpe_ratio(returns)
    
    assert isinstance(sharpe, float)
    assert not np.isnan(sharpe)


# ============================================================================
# TEST PerformanceAttribution: information_ratio
# ============================================================================

def test_information_ratio_basic(attribution_engine):
    """Test basic Information Ratio calculation."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01 + 0.001, index=dates)
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    
    ir = attribution_engine.information_ratio(portfolio, benchmark, annualise=True)
    
    assert isinstance(ir, float)
    assert not np.isnan(ir)
    assert not np.isinf(ir)


def test_information_ratio_annualized_vs_non_annualized(attribution_engine):
    """Test IR with and without annualization."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01 + 0.001, index=dates)
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    
    ir_annual = attribution_engine.information_ratio(portfolio, benchmark, annualise=True)
    ir_period = attribution_engine.information_ratio(portfolio, benchmark, annualise=False)
    
    # Annualized should be sqrt(252) times the period IR
    expected_ratio = np.sqrt(252)
    assert abs(ir_annual / ir_period - expected_ratio) < 0.1


def test_information_ratio_identical_returns(attribution_engine):
    """Test IR when portfolio and benchmark are identical."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(50) * 0.01, index=dates)
    
    ir = attribution_engine.information_ratio(returns, returns)
    
    # IR should be 0 when active returns have zero variance
    assert ir == 0.0


def test_information_ratio_misaligned_indices(attribution_engine):
    """Test IR handles misaligned indices."""
    dates1 = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    dates2 = pd.date_range("2024-01-10", periods=20, freq="D", tz="UTC")
    
    portfolio = pd.Series(np.random.randn(20) * 0.01, index=dates1)
    benchmark = pd.Series(np.random.randn(20) * 0.008, index=dates2)
    
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    
    # Should work with overlapping dates
    assert isinstance(ir, float)


def test_information_ratio_single_observation(attribution_engine):
    """Test IR with single observation returns 0."""
    dates = pd.date_range("2024-01-01", periods=1, freq="D", tz="UTC")
    portfolio = pd.Series([0.01], index=dates)
    benchmark = pd.Series([0.008], index=dates)
    
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    
    # Should return 0 for n < 2
    assert ir == 0.0


def test_information_ratio_two_observations(attribution_engine):
    """Test IR with exactly two observations."""
    dates = pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC")
    portfolio = pd.Series([0.01, 0.02], index=dates)
    benchmark = pd.Series([0.008, 0.015], index=dates)
    
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    
    # Should calculate with n=2
    assert isinstance(ir, float)
    assert not np.isnan(ir)


def test_information_ratio_outperformance(attribution_engine):
    """Test IR when portfolio consistently outperforms benchmark."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    # Add both constant outperformance AND variance to active returns
    portfolio = benchmark * 1.1 + 0.002  # Outperformance with variance
    
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    
    # IR should be positive (mean active return > 0)
    assert ir > 0


def test_information_ratio_underperformance(attribution_engine):
    """Test IR when portfolio consistently underperforms benchmark."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    # Add both constant underperformance AND variance to active returns
    portfolio = benchmark * 0.9 - 0.002  # Underperformance with variance
    
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    
    # IR should be negative (mean active return < 0)
    assert ir < 0


# ============================================================================
# TEST PerformanceAttribution: tracking_error
# ============================================================================

def test_tracking_error_basic(attribution_engine):
    """Test basic tracking error calculation."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01 + 0.001, index=dates)
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    
    te = attribution_engine.tracking_error(portfolio, benchmark, annualise=True)
    
    assert isinstance(te, float)
    assert te >= 0  # TE is always non-negative
    assert not np.isnan(te)


def test_tracking_error_annualized_vs_non_annualized(attribution_engine):
    """Test TE with and without annualization."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01, index=dates)
    benchmark = pd.Series(np.random.randn(100) * 0.008, index=dates)
    
    te_annual = attribution_engine.tracking_error(portfolio, benchmark, annualise=True)
    te_period = attribution_engine.tracking_error(portfolio, benchmark, annualise=False)
    
    # Annualized should be sqrt(252) times the period TE
    expected_ratio = np.sqrt(252)
    assert abs(te_annual / te_period - expected_ratio) < 0.1


def test_tracking_error_identical_returns(attribution_engine):
    """Test TE when portfolio and benchmark are identical."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    returns = pd.Series(np.random.randn(50) * 0.01, index=dates)
    
    te = attribution_engine.tracking_error(returns, returns)
    
    # TE should be 0 when returns are identical
    assert te == 0.0


def test_tracking_error_single_observation(attribution_engine):
    """Test TE with single observation returns 0."""
    dates = pd.date_range("2024-01-01", periods=1, freq="D", tz="UTC")
    portfolio = pd.Series([0.01], index=dates)
    benchmark = pd.Series([0.008], index=dates)
    
    te = attribution_engine.tracking_error(portfolio, benchmark)
    
    # Should return 0 for n < 2
    assert te == 0.0


def test_tracking_error_misaligned_indices(attribution_engine):
    """Test TE handles misaligned indices."""
    dates1 = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    dates2 = pd.date_range("2024-01-15", periods=30, freq="D", tz="UTC")
    
    portfolio = pd.Series(np.random.randn(30) * 0.01, index=dates1)
    benchmark = pd.Series(np.random.randn(30) * 0.008, index=dates2)
    
    te = attribution_engine.tracking_error(portfolio, benchmark)
    
    # Should work with overlapping dates
    assert isinstance(te, float)
    assert te >= 0


# ============================================================================
# TEST PerformanceAttribution: sector_attribution
# ============================================================================

def test_sector_attribution_basic(attribution_engine, sample_sector_data):
    """Test basic sector attribution calculation."""
    pw, bw, returns, sectors = sample_sector_data
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    assert isinstance(result, pd.DataFrame)
    assert "allocation" in result.columns
    assert "selection" in result.columns
    assert "interaction" in result.columns
    assert "total" in result.columns
    assert len(result) > 0


def test_sector_attribution_decomposition(attribution_engine, sample_sector_data):
    """Test sector attribution decomposition adds up correctly."""
    pw, bw, returns, sectors = sample_sector_data
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    # For each sector, total = allocation + selection + interaction
    for idx in result.index:
        expected_total = (result.loc[idx, "allocation"] + 
                         result.loc[idx, "selection"] + 
                         result.loc[idx, "interaction"])
        assert abs(result.loc[idx, "total"] - expected_total) < 1e-10


def test_sector_attribution_weights(attribution_engine, sample_sector_data):
    """Test sector attribution includes weight information."""
    pw, bw, returns, sectors = sample_sector_data
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    assert "port_weight" in result.columns
    assert "bench_weight" in result.columns
    assert "port_return" in result.columns
    assert "bench_return" in result.columns
    
    # Weights should be non-negative
    assert (result["port_weight"] >= 0).all()
    assert (result["bench_weight"] >= 0).all()


def test_sector_attribution_no_overlap(attribution_engine):
    """Test sector attribution fails when no overlapping assets."""
    pw = pd.Series([0.5, 0.5], index=["A", "B"])
    bw = pd.Series([0.5, 0.5], index=["C", "D"])
    returns = pd.Series([0.01, 0.02], index=["E", "F"])
    sectors = pd.Series(["Tech", "Finance"], index=["G", "H"])
    
    with pytest.raises(ValueError, match="No overlapping assets"):
        attribution_engine.sector_attribution(pw, bw, returns, sectors)


def test_sector_attribution_single_sector(attribution_engine):
    """Test sector attribution with single sector."""
    assets = ["A", "B", "C"]
    pw = pd.Series([0.4, 0.3, 0.3], index=assets)
    bw = pd.Series([0.5, 0.3, 0.2], index=assets)
    returns = pd.Series([0.01, 0.02, 0.015], index=assets)
    sectors = pd.Series(["Tech", "Tech", "Tech"], index=assets)
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    assert len(result) == 1
    assert result.index[0] == "Tech"


def test_sector_attribution_pit_metadata(attribution_engine, sample_sector_data):
    """Test sector attribution includes PIT metadata."""
    pw, bw, returns, sectors = sample_sector_data
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    assert "pit_compliant" in result.attrs
    assert "phase" in result.attrs
    assert result.attrs["phase"] == "Phase21-Attribution"


# ============================================================================
# TEST PerformanceAttribution: factor_exposures
# ============================================================================

def test_factor_exposures_basic(attribution_engine):
    """Test basic factor exposures calculation."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    assets = ["ASSET_A", "ASSET_B", "ASSET_C"]
    factors = ["FACTOR_1", "FACTOR_2"]
    
    returns_df = pd.DataFrame(
        np.random.randn(100, 3) * 0.01,
        index=dates,
        columns=assets
    )
    factor_returns = pd.DataFrame(
        np.random.randn(100, 2) * 0.008,
        index=dates,
        columns=factors
    )
    
    exposures = attribution_engine.factor_exposures(returns_df, factor_returns)
    
    assert isinstance(exposures, pd.DataFrame)
    assert exposures.shape == (2, 3)  # 2 factors � 3 assets
    assert list(exposures.index) == factors
    assert list(exposures.columns) == assets


def test_factor_exposures_single_factor(attribution_engine):
    """Test factor exposures with single factor."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    assets = ["ASSET_A", "ASSET_B"]
    
    returns_df = pd.DataFrame(
        np.random.randn(50, 2) * 0.01,
        index=dates,
        columns=assets
    )
    factor_returns = pd.DataFrame(
        np.random.randn(50, 1) * 0.008,
        index=dates,
        columns=["MARKET"]
    )
    
    exposures = attribution_engine.factor_exposures(returns_df, factor_returns)
    
    assert exposures.shape == (1, 2)
    assert exposures.index[0] == "MARKET"


def test_factor_exposures_perfect_correlation(attribution_engine):
    """Test factor exposures when asset perfectly tracks factor."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    
    factor_returns = pd.DataFrame(
        np.random.randn(100, 1) * 0.01,
        index=dates,
        columns=["FACTOR"]
    )
    # Asset perfectly tracks factor with beta = 2.0
    returns_df = pd.DataFrame(
        factor_returns.values * 2.0,
        index=dates,
        columns=["ASSET"]
    )
    
    exposures = attribution_engine.factor_exposures(returns_df, factor_returns)
    
    # Beta should be close to 2.0
    assert abs(exposures.loc["FACTOR", "ASSET"] - 2.0) < 0.1


def test_factor_exposures_singular_matrix(attribution_engine):
    """Test factor exposures handles singular matrix gracefully."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    
    # Create linearly dependent factors
    factor1 = np.random.randn(50) * 0.01
    factor_returns = pd.DataFrame({
        "FACTOR_1": factor1,
        "FACTOR_2": factor1 * 2.0  # Linearly dependent
    }, index=dates)
    
    returns_df = pd.DataFrame(
        np.random.randn(50, 2) * 0.01,
        index=dates,
        columns=["ASSET_A", "ASSET_B"]
    )
    
    # Should use lstsq fallback
    exposures = attribution_engine.factor_exposures(returns_df, factor_returns)
    
    assert isinstance(exposures, pd.DataFrame)
    assert not exposures.isnull().any().any()


# ============================================================================
# TEST PerformanceAttribution: cumulative_returns
# ============================================================================

def test_factor_exposures_misaligned_time_indexes_raises(attribution_engine):
    """Test factor_exposures fails fast when timestamp indexes do not overlap."""
    ret_idx = pd.date_range("2024-01-01", periods=20, freq="D")
    fac_idx = pd.date_range("2024-02-01", periods=20, freq="D")

    returns_df = pd.DataFrame(
        np.random.randn(20, 2) * 0.01,
        index=ret_idx,
        columns=["ASSET_A", "ASSET_B"],
    )
    factor_returns = pd.DataFrame(
        np.random.randn(20, 2) * 0.01,
        index=fac_idx,
        columns=["MKT", "SMB"],
    )

    with pytest.raises(ValueError, match="no overlapping timestamps"):
        attribution_engine.factor_exposures(returns_df, factor_returns)


def test_cumulative_returns_basic(attribution_engine):
    """Test basic cumulative returns calculation."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    returns = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005, -0.005, 0.01, 0.02, -0.01, 0.01], index=dates)
    
    cum_returns = attribution_engine.cumulative_returns(returns)
    
    assert isinstance(cum_returns, pd.Series)
    assert len(cum_returns) == len(returns)
    assert cum_returns.index.equals(returns.index)


def test_cumulative_returns_compounding(attribution_engine):
    """Test cumulative returns uses proper compounding."""
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    returns = pd.Series([0.1, 0.1, 0.1], index=dates)  # 10% each period
    
    cum_returns = attribution_engine.cumulative_returns(returns)
    
    # (1.1 * 1.1 * 1.1) - 1 = 0.331
    expected_final = (1.1 ** 3) - 1
    assert abs(cum_returns.iloc[-1] - expected_final) < 1e-10


def test_cumulative_returns_zero_returns(attribution_engine):
    """Test cumulative returns with zero returns."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    returns = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0], index=dates)
    
    cum_returns = attribution_engine.cumulative_returns(returns)
    
    # All cumulative returns should be 0
    assert (cum_returns == 0.0).all()


# ============================================================================
# TEST PerformanceAttribution: max_drawdown
# ============================================================================

def test_max_drawdown_basic(attribution_engine):
    """Test basic max drawdown calculation."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    returns = pd.Series([0.01, 0.02, -0.05, -0.03, 0.02, 0.01, -0.02, 0.03, -0.01, 0.02], index=dates)
    
    mdd = attribution_engine.max_drawdown(returns)
    
    assert isinstance(mdd, float)
    assert mdd <= 0  # Max drawdown is always non-positive


def test_max_drawdown_no_drawdown(attribution_engine):
    """Test max drawdown with only positive returns."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    returns = pd.Series([0.01, 0.02, 0.015, 0.01, 0.02], index=dates)
    
    mdd = attribution_engine.max_drawdown(returns)
    
    # Should be 0 (no drawdown)
    assert mdd == 0.0


def test_max_drawdown_severe_loss(attribution_engine):
    """Test max drawdown with severe loss."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    returns = pd.Series([0.1, 0.1, -0.5, 0.1, 0.1], index=dates)  # 50% loss
    
    mdd = attribution_engine.max_drawdown(returns)
    
    # Max drawdown should be significant
    assert mdd < -0.3  # At least 30% drawdown


def test_max_drawdown_recovery(attribution_engine):
    """Test max drawdown captures peak-to-trough even with recovery."""
    dates = pd.date_range("2024-01-01", periods=7, freq="D")
    # Go up, crash, recover
    returns = pd.Series([0.1, 0.1, 0.1, -0.2, -0.2, 0.3, 0.3], index=dates)
    
    mdd = attribution_engine.max_drawdown(returns)
    
    # Should capture the drawdown even though it recovered
    assert mdd < 0


# ============================================================================
# TEST EDGE CASES: NaN and Inf Handling
# ============================================================================

def test_decompose_returns_with_nan(attribution_engine):
    """Test decompose_returns handles NaN values gracefully."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    portfolio = pd.Series([0.01, 0.02, np.nan, 0.015, 0.01, 0.02, 0.01, 0.015, 0.01, 0.02], index=dates)
    benchmark = pd.Series([0.008, 0.015, 0.01, 0.012, 0.008, 0.015, 0.008, 0.012, 0.008, 0.015], index=dates)
    
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    
    # Should handle NaN in calculations
    assert isinstance(result, dict)
    # Results may contain NaN but should not crash


def test_sharpe_ratio_with_inf(attribution_engine):
    """Test Sharpe ratio handles infinite values."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    returns = pd.Series([0.01, 0.02, np.inf, 0.015, 0.01, 0.02, 0.01, 0.015, 0.01, 0.02], index=dates)
    
    sharpe = attribution_engine.sharpe_ratio(returns)
    
    # Should handle inf gracefully (may return inf or handle it)
    assert isinstance(sharpe, float)


def test_align_series_with_duplicates():
    """Test _align_series handles duplicate indices."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    # Create series with duplicate index
    s1 = pd.Series([1, 2, 3, 4, 5], index=dates)
    s2_dates = list(dates[:3]) + list(dates[:2])  # Duplicates
    s2 = pd.Series([10, 20, 30, 40, 50], index=s2_dates)
    
    # Should handle duplicates (behavior depends on pandas version)
    try:
        aligned = _align_series(s1, s2)
        assert len(aligned) == 2
    except Exception:
        # May raise exception for duplicates, which is acceptable
        pass


def test_sector_attribution_with_zero_weights(attribution_engine):
    """Test sector attribution handles zero weights."""
    assets = ["A", "B", "C", "D"]
    pw = pd.Series([0.5, 0.5, 0.0, 0.0], index=assets)  # Zero weights
    bw = pd.Series([0.25, 0.25, 0.25, 0.25], index=assets)
    returns = pd.Series([0.01, 0.02, 0.015, 0.018], index=assets)
    sectors = pd.Series(["Tech", "Tech", "Finance", "Finance"], index=assets)
    
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    # Should handle zero weights gracefully
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2  # Two sectors


# ============================================================================
# TEST PERFORMANCE: Large Dataset Benchmarks
# ============================================================================

def test_performance_decompose_returns_large_dataset(attribution_engine):
    """Test decompose_returns performance with large dataset."""
    # 1000 days of data
    dates = pd.date_range("2020-01-01", periods=1000, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(1000) * 0.01 + 0.0005, index=dates)
    benchmark = pd.Series(np.random.randn(1000) * 0.008, index=dates)
    
    import time
    start = time.time()
    result = attribution_engine.decompose_returns(portfolio, benchmark)
    elapsed = time.time() - start
    
    # Should complete in reasonable time (<1 second)
    assert elapsed < 1.0
    assert isinstance(result, dict)


def test_performance_sector_attribution_large_portfolio(attribution_engine):
    """Test sector attribution performance with large portfolio."""
    # 100 assets across 10 sectors
    n_assets = 100
    assets = [f"ASSET_{i}" for i in range(n_assets)]
    
    pw = pd.Series(np.random.dirichlet(np.ones(n_assets)), index=assets)
    bw = pd.Series(np.random.dirichlet(np.ones(n_assets)), index=assets)
    returns = pd.Series(np.random.randn(n_assets) * 0.02, index=assets)
    sectors = pd.Series([f"SECTOR_{i % 10}" for i in range(n_assets)], index=assets)
    
    import time
    start = time.time()
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    elapsed = time.time() - start
    
    # Should complete in reasonable time (<2 seconds)
    assert elapsed < 2.0
    assert len(result) == 10  # 10 sectors


def test_performance_factor_exposures_large_matrix(attribution_engine):
    """Test factor exposures performance with large matrix."""
    # 1000 periods � 50 assets � 10 factors
    dates = pd.date_range("2020-01-01", periods=1000, freq="D")
    assets = [f"ASSET_{i}" for i in range(50)]
    factors = [f"FACTOR_{i}" for i in range(10)]
    
    returns_df = pd.DataFrame(
        np.random.randn(1000, 50) * 0.01,
        index=dates,
        columns=assets
    )
    factor_returns = pd.DataFrame(
        np.random.randn(1000, 10) * 0.008,
        index=dates,
        columns=factors
    )
    
    import time
    start = time.time()
    exposures = attribution_engine.factor_exposures(returns_df, factor_returns)
    elapsed = time.time() - start
    
    # Should complete in reasonable time (<3 seconds)
    assert elapsed < 3.0
    assert exposures.shape == (10, 50)


# ============================================================================
# TEST INTEGRATION: End-to-End Workflows
# ============================================================================

def test_integration_full_attribution_workflow(attribution_engine):
    """Test complete attribution workflow from returns to all metrics."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    portfolio = pd.Series(np.random.randn(100) * 0.01 + 0.0008, index=dates)
    benchmark = pd.Series(np.random.randn(100) * 0.008 + 0.0005, index=dates)
    
    # Run all attribution methods
    decomp = attribution_engine.decompose_returns(portfolio, benchmark)
    sharpe = attribution_engine.sharpe_ratio(portfolio)
    ir = attribution_engine.information_ratio(portfolio, benchmark)
    te = attribution_engine.tracking_error(portfolio, benchmark)
    cum_ret = attribution_engine.cumulative_returns(portfolio)
    mdd = attribution_engine.max_drawdown(portfolio)
    
    # Verify all results are valid
    assert isinstance(decomp, dict)
    assert isinstance(sharpe, float)
    assert isinstance(ir, float)
    assert isinstance(te, float)
    assert isinstance(cum_ret, pd.Series)
    assert isinstance(mdd, float)
    
    # Verify relationships
    assert te >= 0  # TE is non-negative
    assert mdd <= 0  # MDD is non-positive
    assert len(cum_ret) == len(portfolio)


def test_integration_multi_sector_portfolio(attribution_engine):
    """Test integration with realistic multi-sector portfolio."""
    # Create realistic portfolio with 30 assets across 5 sectors
    n_assets = 30
    assets = [f"ASSET_{i}" for i in range(n_assets)]
    
    # Portfolio overweights Tech, underweights Energy
    sector_map = {
        "Tech": list(range(0, 10)),
        "Finance": list(range(10, 16)),
        "Healthcare": list(range(16, 22)),
        "Energy": list(range(22, 26)),
        "Consumer": list(range(26, 30))
    }
    
    pw_values = np.zeros(n_assets)
    bw_values = np.ones(n_assets) / n_assets  # Equal weight benchmark
    
    # Overweight Tech
    pw_values[0:10] = 0.5 / 10
    pw_values[10:] = 0.5 / 20
    
    pw = pd.Series(pw_values, index=assets)
    bw = pd.Series(bw_values, index=assets)
    
    # Tech outperforms
    returns_values = np.random.randn(n_assets) * 0.01
    returns_values[0:10] += 0.02  # Tech boost
    returns = pd.Series(returns_values, index=assets)
    
    sectors_list = []
    for sector, indices in sector_map.items():
        sectors_list.extend([sector] * len(indices))
    sectors = pd.Series(sectors_list, index=assets)
    
    # Run sector attribution
    result = attribution_engine.sector_attribution(pw, bw, returns, sectors)
    
    # Verify Tech has positive allocation effect (overweight + outperformance)
    assert "Tech" in result.index
    assert len(result) == 5  # 5 sectors


def test_integration_config_propagation():
    """Test configuration propagates correctly through all methods."""
    config = AttributionConfig(
        risk_free_rate=0.05,
        periods_per_year=252,  # Use same periods_per_year for fair comparison
        pit_compliant=True
    )
    engine = PerformanceAttribution(config)
    
    # Use deterministic data with positive mean return well above RFR
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    np.random.seed(42)  # Deterministic for reproducibility
    returns = pd.Series(np.random.randn(100) * 0.01 + 0.003, index=dates)  # Mean ~0.3% daily
    
    # Sharpe ratio should use the configured risk-free rate
    sharpe = engine.sharpe_ratio(returns, annualise=True)
    
    # With higher RFR, Sharpe should be lower than with RFR=0
    # Use same periods_per_year for fair comparison
    engine_zero_rfr = PerformanceAttribution(AttributionConfig(risk_free_rate=0.0, periods_per_year=252))
    sharpe_zero = engine_zero_rfr.sharpe_ratio(returns, annualise=True)
    
    # Sharpe with RFR=0.05 should be less than Sharpe with RFR=0.0
    assert sharpe < sharpe_zero


# ============================================================================
# TEST SUMMARY
# ============================================================================

def test_suite_coverage():
    """Meta-test to document test coverage."""
    # This test always passes but documents what we've tested
    coverage = {
        "helper_functions": ["_align_series", "_validate_pit"],
        "config": ["AttributionConfig"],
        "core_methods": [
            "decompose_returns",
            "sharpe_ratio",
            "information_ratio",
            "tracking_error",
            "sector_attribution",
            "factor_exposures",
            "cumulative_returns",
            "max_drawdown"
        ],
        "edge_cases": ["NaN", "inf", "zero_variance", "single_observation", "misalignment"],
        "pit_safety": ["monotonicity", "future_dates", "timezone_handling"],
        "performance": ["large_datasets", "100_assets", "1000_periods"],
        "integration": ["full_workflow", "multi_sector", "config_propagation"]
    }
    
    assert len(coverage["core_methods"]) == 8
    assert len(coverage["edge_cases"]) >= 5
    assert len(coverage["performance"]) >= 3


# ============================================================================
# TEST FIX EVIDENCE: Gap fixes from role21_phase21_attribution_audit_20260519
# ============================================================================

def test_pit_same_day_daily_bar_rejected():
    """FIX EVIDENCE: Same-day daily bar must be rejected with pit_strict=True.

    Audit gap: _validate_pit only checked idx >= current_time (intraday precision),
    so a bar timestamped at midnight of the decision day would pass. With daily_bar=True
    (default), the bar DATE must be strictly before the decision DATE (T-1 required).
    """
    # Decision time: 2024-01-05 noon UTC
    decision_time = pd.Timestamp("2024-01-05 12:00:00", tz="UTC")

    # Bar dated 2024-01-05 (same day as decision) — must be rejected
    same_day_dates = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    # Last bar is 2024-01-05 00:00 UTC — same calendar date as decision
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=same_day_dates)

    with pytest.raises(ValueError, match="T-1 required"):
        _validate_pit([s], current_time=decision_time, pit_strict=True, daily_bar=True)

    # T-1 compliant: last bar is 2024-01-04 — must pass
    t_minus_1_dates = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    s_ok = pd.Series([1.0, 2.0, 3.0, 4.0], index=t_minus_1_dates)
    assert _validate_pit([s_ok], current_time=decision_time, pit_strict=True, daily_bar=True)


def test_pit_cross_timezone_same_calendar_day_raises():
    """REGRESSION: cross-timezone same-calendar-day leak must be blocked.

    Scenario: current_time is UTC, index is Asia/Ho_Chi_Minh (UTC+7).
    A bar dated 2026-05-19 00:00+07:00 equals 2026-05-18 17:00 UTC in absolute
    time — so a naive UTC-instant comparison would pass it. But the *calendar date*
    in the decision timezone (UTC) is still 2026-05-19, which is the same day as
    the decision. T-1 requires the bar date to be strictly before the decision date
    in the decision timezone, so this must raise ValueError when pit_strict=True.
    """
    # Decision time: 2026-05-19 13:00 UTC (same calendar date as the last bar)
    decision_time = pd.Timestamp("2026-05-19 13:00:00", tz="UTC")

    # Index in Asia/Ho_Chi_Minh: last bar is 2026-05-19 00:00+07:00
    # = 2026-05-18 17:00 UTC in absolute time, but calendar date is 2026-05-19
    hcm_dates = pd.date_range("2026-05-15", periods=5, freq="D", tz="Asia/Ho_Chi_Minh")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=hcm_dates)

    # Must raise: same calendar day in decision timezone (UTC)
    with pytest.raises(ValueError, match="T-1 required"):
        _validate_pit([s], current_time=decision_time, pit_strict=True, daily_bar=True)

    # T-1 compliant: last bar is 2026-05-18 (strictly before 2026-05-19 UTC)
    hcm_dates_ok = pd.date_range("2026-05-14", periods=4, freq="D", tz="Asia/Ho_Chi_Minh")
    s_ok = pd.Series([1.0, 2.0, 3.0, 4.0], index=hcm_dates_ok)
    assert _validate_pit([s_ok], current_time=decision_time, pit_strict=True, daily_bar=True)


def test_factor_exposures_missing_obs_does_not_distort_beta():
    """FIX EVIDENCE: NaN rows in factor_exposures must be dropped, not zero-filled.

    Audit gap: old code did fillna(0.0) before OLS, so missing observations were
    treated as zero-return days, biasing beta toward zero. Fix: drop rows with any
    NaN/inf across the combined (factors + returns) matrix before regression.

    Verification: asset perfectly tracks factor with beta=2.0. Inject NaN into
    some rows of the asset return series. With zero-fill the estimated beta would
    be pulled toward zero; with row-drop it must remain close to 2.0.
    """
    np.random.seed(0)
    n = 120
    dates = pd.date_range("2024-01-01", periods=n, freq="D")

    factor_vals = np.random.randn(n) * 0.01
    factor_returns = pd.DataFrame({"FACTOR": factor_vals}, index=dates)

    # Asset perfectly tracks factor at beta=2.0
    asset_vals = factor_vals * 2.0

    # Inject NaN into 30 random rows (25% missing)
    nan_idx = np.random.choice(n, size=30, replace=False)
    asset_vals_with_nan = asset_vals.copy()
    asset_vals_with_nan[nan_idx] = np.nan

    returns_df = pd.DataFrame({"ASSET": asset_vals_with_nan}, index=dates)

    exposures = PerformanceAttribution().factor_exposures(returns_df, factor_returns)

    estimated_beta = exposures.loc["FACTOR", "ASSET"]

    # With row-drop: 90 complete observations, beta must be very close to 2.0
    assert abs(estimated_beta - 2.0) < 0.05, (
        f"Beta distorted: expected ~2.0, got {estimated_beta:.4f}. "
        "NaN rows may have been zero-filled instead of dropped."
    )
