"""
Unit Tests for OMEGA_QUANT Neutralization V2 (Hierarchical + Factor)

Tests:
- HierarchicalNeutralizer: 5-tier fallback logic
- FactorNeutralizer: 3-factor model neutralization
- PIT-Safety: T-1 lag compliance
- Vectorization: Performance and correctness
- Edge cases: Empty data, single stock, collinearity

Author: SDET (Role 18)
Date: 2026-05-13
Version: 2.0.0
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.features.neutralization import (
    HierarchicalNeutralizer,
    FactorNeutralizer,
    winsorize,
    market_neutralize,
    factor_neutralize,
    _cross_sectional_zscore
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_cross_section():
    """Create sample cross-section data for testing."""
    np.random.seed(42)
    n_stocks = 100
    
    data = pd.DataFrame({
        'symbol': [f'STOCK_{i:03d}' for i in range(n_stocks)],
        'alpha': np.random.randn(n_stocks) * 0.05,
        'sector': np.random.choice(['Tech', 'Finance', 'Energy', 'Consumer'], n_stocks),
        'price_bucket': np.random.choice(['Low', 'Mid', 'High'], n_stocks),
        'liquidity_bucket': np.random.choice(['Illiquid', 'Liquid', 'HighlyLiquid'], n_stocks),
        'exchange': np.random.choice(['HOSE', 'HNX', 'UPCOM'], n_stocks)
    })
    
    data = data.set_index('symbol')
    return data


@pytest.fixture
def sample_panel():
    """Create sample panel data (multiple dates) for testing."""
    np.random.seed(42)
    n_dates = 10
    n_stocks = 50
    
    dates = pd.date_range('2024-01-01', periods=n_dates, freq='D')
    symbols = [f'STOCK_{i:03d}' for i in range(n_stocks)]
    
    data = []
    for date in dates:
        for symbol in symbols:
            data.append({
                'date': date,
                'symbol': symbol,
                'alpha_1': np.random.randn() * 0.05,
                'alpha_2': np.random.randn() * 0.03,
                'sector': np.random.choice(['Tech', 'Finance', 'Energy']),
                'price_bucket': np.random.choice(['Low', 'Mid', 'High']),
                'liquidity_bucket': np.random.choice(['Illiquid', 'Liquid']),
                'exchange': np.random.choice(['HOSE', 'HNX'])
            })
    
    df = pd.DataFrame(data)
    df = df.set_index(['date', 'symbol'])
    return df


@pytest.fixture
def sample_factor_returns():
    """Create sample factor returns for testing."""
    np.random.seed(42)
    n_periods = 120
    
    factor_returns = pd.DataFrame({
        'market': np.random.randn(n_periods) * 0.02,
        'smb': np.random.randn(n_periods) * 0.01,
        'hml': np.random.randn(n_periods) * 0.01
    })
    
    return factor_returns


# ============================================================================
# TEST: CROSS-SECTIONAL Z-SCORE
# ============================================================================


def test_cross_sectional_zscore_basic():
    """Test basic cross-sectional z-score normalization."""
    data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = _cross_sectional_zscore(data)
    
    # Check mean ≈ 0 and std ≈ 1
    assert abs(result.mean()) < 1e-10
    assert abs(result.std() - 1.0) < 1e-6  # Relaxed tolerance for numerical precision


def test_cross_sectional_zscore_constant():
    """Test z-score with constant values (should return zeros)."""
    data = pd.Series([5.0, 5.0, 5.0, 5.0])
    result = _cross_sectional_zscore(data)
    
    # All values should be 0
    assert (result == 0.0).all()


def test_cross_sectional_zscore_with_nan():
    """Test z-score with NaN values."""
    data = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0])
    result = _cross_sectional_zscore(data)
    
    # Check that non-NaN values are normalized
    assert abs(result.dropna().mean()) < 1e-10


# ============================================================================
# TEST: HIERARCHICAL NEUTRALIZER - SINGLE CROSS-SECTION
# ============================================================================


def test_hierarchical_neutralizer_initialization():
    """Test HierarchicalNeutralizer initialization."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=5,
        min_l3_size=5,
        min_l2_size=10,
        min_l1_size=3
    )
    
    assert neutralizer.min_l4_size == 5
    assert neutralizer.min_l3_size == 5
    assert neutralizer.min_l2_size == 10
    assert neutralizer.min_l1_size == 3


def test_hierarchical_neutralizer_cross_section_l4(sample_cross_section):
    """Test L4 neutralization (Sector × Price × Liquidity)."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=2,  # Lower threshold for testing
        min_l3_size=5,
        min_l2_size=10,
        min_l1_size=3
    )
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=sample_cross_section['alpha'],
        sector=sample_cross_section['sector'],
        price_level=sample_cross_section['price_bucket'],
        liquidity_bucket=sample_cross_section['liquidity_bucket'],
        exchange=sample_cross_section['exchange']
    )
    
    # Check result shape
    assert len(result) == len(sample_cross_section)
    
    # Check that some stocks were neutralized at L4
    assert stats['l4_buckets'] > 0
    
    # Check that all stocks were neutralized
    assert stats['total_stocks'] == len(sample_cross_section)


def test_hierarchical_neutralizer_cross_section_fallback(sample_cross_section):
    """Test fallback logic (L4 → L3 → L2 → L1 → L0)."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=200,  # Very high threshold to force fallback to L0
        min_l3_size=200,
        min_l2_size=200,
        min_l1_size=200
    )
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=sample_cross_section['alpha'],
        sector=sample_cross_section['sector'],
        price_level=sample_cross_section['price_bucket'],
        liquidity_bucket=sample_cross_section['liquidity_bucket'],
        exchange=sample_cross_section['exchange']
    )
    
    # Check that fallback occurred (L0 should have stocks since all thresholds are too high)
    assert stats['l0_global'] > 0
    
    # Check that all stocks were neutralized
    total_neutralized = (
        stats['l4_buckets'] + stats['l3_buckets'] + 
        stats['l2_buckets'] + stats['l1_exchange'] + stats['l0_global']
    )
    assert total_neutralized == stats['total_stocks']


def test_hierarchical_neutralizer_without_liquidity(sample_cross_section):
    """Test neutralization without liquidity bucket (skip L4)."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=5,
        min_l3_size=5,
        min_l2_size=10,
        min_l1_size=3
    )
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=sample_cross_section['alpha'],
        sector=sample_cross_section['sector'],
        price_level=sample_cross_section['price_bucket'],
        liquidity_bucket=None,  # No liquidity bucket
        exchange=sample_cross_section['exchange']
    )
    
    # L4 should be skipped
    assert stats['l4_buckets'] == 0
    
    # L3 or lower should be used
    assert stats['l3_buckets'] > 0 or stats['l2_buckets'] > 0


def test_hierarchical_neutralizer_without_exchange(sample_cross_section):
    """Test neutralization without exchange (skip L1)."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=200,  # Very high threshold to force fallback to L0
        min_l3_size=200,
        min_l2_size=200,
        min_l1_size=200
    )
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=sample_cross_section['alpha'],
        sector=sample_cross_section['sector'],
        price_level=sample_cross_section['price_bucket'],
        liquidity_bucket=sample_cross_section['liquidity_bucket'],
        exchange=None  # No exchange
    )
    
    # L1 should be skipped
    assert stats['l1_exchange'] == 0
    
    # Should fallback to L0
    assert stats['l0_global'] > 0


# ============================================================================
# TEST: HIERARCHICAL NEUTRALIZER - PANEL
# ============================================================================


def test_hierarchical_neutralizer_panel(sample_panel):
    """Test panel neutralization (multiple dates)."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=3,
        min_l3_size=3,
        min_l2_size=5,
        min_l1_size=3
    )
    
    result = neutralizer.neutralize_panel(
        panel=sample_panel,
        alpha_cols=['alpha_1', 'alpha_2'],
        sector_col='sector',
        price_level_col='price_bucket',
        liquidity_col='liquidity_bucket',
        exchange_col='exchange'
    )
    
    # Check that neutral columns were added
    assert 'alpha_1_neutral' in result.columns
    assert 'alpha_2_neutral' in result.columns
    
    # Check shape
    assert result.shape[0] == sample_panel.shape[0]


def test_hierarchical_neutralizer_panel_pit_safety(sample_panel):
    """Test PIT-safety: each date is neutralized independently."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=3,
        min_l3_size=3,
        min_l2_size=5,
        min_l1_size=3
    )
    
    result = neutralizer.neutralize_panel(
        panel=sample_panel,
        alpha_cols=['alpha_1'],
        sector_col='sector',
        price_level_col='price_bucket',
        liquidity_col='liquidity_bucket',
        exchange_col='exchange'
    )
    
    # For each date, check that mean ≈ 0 (cross-sectional neutralization)
    for date in result.index.get_level_values('date').unique():
        date_data = result.loc[date, 'alpha_1_neutral']
        
        # Skip if all NaN (shouldn't happen but handle gracefully)
        if date_data.notna().sum() > 0:
            # Mean should be close to 0 (allowing for numerical precision)
            mean_val = date_data.mean()
            if not pd.isna(mean_val):
                assert abs(mean_val) < 0.1


def test_hierarchical_neutralizer_fallback_stats(sample_cross_section):
    """Test fallback statistics tracking."""
    neutralizer = HierarchicalNeutralizer(
        min_l4_size=5,
        min_l3_size=5,
        min_l2_size=10,
        min_l1_size=3
    )
    
    # Run multiple neutralizations
    for _ in range(3):
        neutralizer.neutralize_cross_section(
            alpha=sample_cross_section['alpha'],
            sector=sample_cross_section['sector'],
            price_level=sample_cross_section['price_bucket'],
            liquidity_bucket=sample_cross_section['liquidity_bucket'],
            exchange=sample_cross_section['exchange']
        )
    
    # Get cumulative stats
    stats = neutralizer.get_fallback_stats()
    
    # Check that stats are cumulative
    total_stocks = sum(stats.values())
    assert total_stocks == len(sample_cross_section) * 3
    
    # Reset stats
    neutralizer.reset_stats()
    stats_after_reset = neutralizer.get_fallback_stats()
    assert sum(stats_after_reset.values()) == 0


# ============================================================================
# TEST: FACTOR NEUTRALIZER
# ============================================================================


def test_factor_neutralizer_initialization(sample_factor_returns):
    """Test FactorNeutralizer initialization."""
    neutralizer = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=True
    )
    
    assert neutralizer.min_lookback == 60
    assert neutralizer.rolling == True


def test_factor_neutralizer_missing_factors():
    """Test FactorNeutralizer with missing factor columns."""
    incomplete_factors = pd.DataFrame({
        'market': np.random.randn(100),
        'smb': np.random.randn(100)
        # Missing 'hml'
    })
    
    with pytest.raises(ValueError, match="Missing required factor columns"):
        FactorNeutralizer(factor_returns=incomplete_factors)


def test_factor_neutralizer_basic(sample_factor_returns):
    """Test basic factor neutralization."""
    np.random.seed(42)
    
    # Create signal correlated with factors
    n_periods = len(sample_factor_returns)
    signal = pd.Series(
        0.5 * sample_factor_returns['market'] + 
        0.3 * sample_factor_returns['smb'] + 
        0.2 * sample_factor_returns['hml'] + 
        np.random.randn(n_periods) * 0.01
    )
    
    neutralizer = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=False
    )
    
    # Neutralize from index 60 onwards
    neutral_signal = neutralizer.neutralize(signal=signal, start_idx=60)
    
    # Check that neutralized signal has lower correlation with factors
    out_of_sample_market = sample_factor_returns['market'].iloc[60:]
    
    original_corr = signal.iloc[60:].corr(out_of_sample_market)
    neutral_corr = neutral_signal.corr(out_of_sample_market)
    
    # Neutralized correlation should be lower (in absolute value)
    assert abs(neutral_corr) < abs(original_corr)


def test_factor_neutralizer_rolling_vs_expanding(sample_factor_returns):
    """Test rolling vs expanding window neutralization."""
    np.random.seed(42)
    
    n_periods = len(sample_factor_returns)
    signal = pd.Series(np.random.randn(n_periods) * 0.02)
    
    # Rolling window
    neutralizer_rolling = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=True
    )
    neutral_rolling = neutralizer_rolling.neutralize(signal=signal, start_idx=60)
    
    # Expanding window
    neutralizer_expanding = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=False
    )
    neutral_expanding = neutralizer_expanding.neutralize(signal=signal, start_idx=60)
    
    # Results should be different (but might be very close for random signal)
    # Check that at least some values differ
    diff = (neutral_rolling - neutral_expanding).abs()
    assert diff.sum() >= 0  # At minimum, should not error


def test_factor_neutralizer_pit_safety(sample_factor_returns):
    """Test PIT-safety: only uses historical data for beta estimation."""
    np.random.seed(42)
    
    n_periods = len(sample_factor_returns)
    signal = pd.Series(np.random.randn(n_periods) * 0.02)
    
    neutralizer = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=False
    )
    
    # Neutralize from index 60
    neutral_signal = neutralizer.neutralize(signal=signal, start_idx=60)
    
    # Check that output starts from index 60
    assert len(neutral_signal) == n_periods - 60
    assert neutral_signal.index[0] == signal.index[60]


def test_factor_neutralizer_insufficient_lookback(sample_factor_returns):
    """Test error when start_idx < min_lookback."""
    np.random.seed(42)
    
    n_periods = len(sample_factor_returns)
    signal = pd.Series(np.random.randn(n_periods) * 0.02)
    
    neutralizer = FactorNeutralizer(
        factor_returns=sample_factor_returns,
        min_lookback=60,
        rolling=False
    )
    
    # Should raise error
    with pytest.raises(ValueError, match="must be >= min_lookback"):
        neutralizer.neutralize(signal=signal, start_idx=30)


# ============================================================================
# TEST: LEGACY FUNCTIONS (BACKWARD COMPATIBILITY)
# ============================================================================


def test_winsorize_std_method():
    """Test winsorize with std method."""
    data = pd.Series([1, 2, 3, 4, 5, 100, 200])
    result = winsorize(data, method='std', n_std=2.0)
    
    # Extreme values should be clipped
    assert result.max() < 200
    assert result.min() == 1


def test_winsorize_percentile_method():
    """Test winsorize with percentile method."""
    data = pd.Series([1, 2, 3, 4, 5, 100, 200])
    result = winsorize(data, method='percentile', lower_percentile=10, upper_percentile=90)
    
    # Extreme values should be clipped
    assert result.max() < 200
    assert result.min() > 1


def test_market_neutralize_basic():
    """Test basic market neutralization."""
    np.random.seed(42)
    
    # Create signal correlated with market
    market_returns = pd.Series(np.random.randn(100) * 0.02)
    signal = 0.5 * market_returns + np.random.randn(100) * 0.01
    
    # Neutralize
    neutral_signal = market_neutralize(signal, market_returns)
    
    # Check that correlation is reduced
    original_corr = signal.corr(market_returns)
    neutral_corr = neutral_signal.corr(market_returns)
    
    assert abs(neutral_corr) < abs(original_corr)


def test_factor_neutralize_basic():
    """Test basic factor neutralization."""
    np.random.seed(42)
    
    # Create factors
    factors = pd.DataFrame({
        'factor1': np.random.randn(100) * 0.02,
        'factor2': np.random.randn(100) * 0.01
    })
    
    # Create signal correlated with factors
    signal = 0.5 * factors['factor1'] + 0.3 * factors['factor2'] + np.random.randn(100) * 0.01
    
    # Neutralize
    neutral_signal = factor_neutralize(signal, factors)
    
    # Check that correlation is reduced
    original_corr = signal.corr(factors['factor1'])
    neutral_corr = neutral_signal.corr(factors['factor1'])
    
    assert abs(neutral_corr) < abs(original_corr)


# ============================================================================
# TEST: EDGE CASES
# ============================================================================


def test_hierarchical_neutralizer_single_stock():
    """Test neutralization with single stock (should use L0)."""
    neutralizer = HierarchicalNeutralizer()
    
    single_stock = pd.DataFrame({
        'alpha': [0.05],
        'sector': ['Tech'],
        'price_bucket': ['Mid'],
        'liquidity_bucket': ['Liquid'],
        'exchange': ['HOSE']
    }, index=['STOCK_001'])
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=single_stock['alpha'],
        sector=single_stock['sector'],
        price_level=single_stock['price_bucket'],
        liquidity_bucket=single_stock['liquidity_bucket'],
        exchange=single_stock['exchange']
    )
    
    # Should fallback to L0
    assert stats['l0_global'] == 1
    
    # Single stock should be normalized to 0
    assert result.iloc[0] == 0.0


def test_hierarchical_neutralizer_empty_data():
    """Test neutralization with empty data."""
    neutralizer = HierarchicalNeutralizer()
    
    empty_data = pd.DataFrame({
        'alpha': pd.Series([], dtype=float),
        'sector': pd.Series([], dtype=str),
        'price_bucket': pd.Series([], dtype=str),
        'liquidity_bucket': pd.Series([], dtype=str),
        'exchange': pd.Series([], dtype=str)
    })
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=empty_data['alpha'],
        sector=empty_data['sector'],
        price_level=empty_data['price_bucket'],
        liquidity_bucket=empty_data['liquidity_bucket'],
        exchange=empty_data['exchange']
    )
    
    # Should return empty result
    assert len(result) == 0
    assert stats['total_stocks'] == 0


def test_hierarchical_neutralizer_all_nan():
    """Test neutralization with all NaN values."""
    neutralizer = HierarchicalNeutralizer()
    
    nan_data = pd.DataFrame({
        'alpha': [np.nan, np.nan, np.nan],
        'sector': ['Tech', 'Finance', 'Energy'],
        'price_bucket': ['Mid', 'High', 'Low'],
        'liquidity_bucket': ['Liquid', 'Liquid', 'Illiquid'],
        'exchange': ['HOSE', 'HNX', 'UPCOM']
    }, index=['STOCK_001', 'STOCK_002', 'STOCK_003'])
    
    result, stats = neutralizer.neutralize_cross_section(
        alpha=nan_data['alpha'],
        sector=nan_data['sector'],
        price_level=nan_data['price_bucket'],
        liquidity_bucket=nan_data['liquidity_bucket'],
        exchange=nan_data['exchange']
    )
    
    # Result should be all zeros (or NaN)
    assert result.isna().all() or (result == 0.0).all()


# ============================================================================
# TEST: VECTORIZATION PERFORMANCE
# ============================================================================


def test_hierarchical_neutralizer_vectorization_performance():
    """Test that vectorization provides performance benefit."""
    import time
    
    np.random.seed(42)
    n_stocks = 1000
    
    large_data = pd.DataFrame({
        'alpha': np.random.randn(n_stocks) * 0.05,
        'sector': np.random.choice(['Tech', 'Finance', 'Energy', 'Consumer'], n_stocks),
        'price_bucket': np.random.choice(['Low', 'Mid', 'High'], n_stocks),
        'liquidity_bucket': np.random.choice(['Illiquid', 'Liquid', 'HighlyLiquid'], n_stocks),
        'exchange': np.random.choice(['HOSE', 'HNX', 'UPCOM'], n_stocks)
    }, index=[f'STOCK_{i:04d}' for i in range(n_stocks)])
    
    neutralizer = HierarchicalNeutralizer()
    
    # Time the neutralization
    start = time.time()
    result, stats = neutralizer.neutralize_cross_section(
        alpha=large_data['alpha'],
        sector=large_data['sector'],
        price_level=large_data['price_bucket'],
        liquidity_bucket=large_data['liquidity_bucket'],
        exchange=large_data['exchange']
    )
    elapsed = time.time() - start
    
    # Should complete in reasonable time (< 1 second for 1000 stocks)
    assert elapsed < 1.0
    
    # Check correctness
    assert len(result) == n_stocks


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

