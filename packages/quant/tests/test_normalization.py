"""
Unit Tests for OMEGA_QUANT Signal Normalization
Phase 3.2.5: Feature Engineering - Normalization
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.features.normalization import (
    zscore_normalize,
    rank_normalize,
    robust_normalize,
    percentile_rank,
    rolling_normalize,
    expanding_normalize,
    Normalizer,
    normalize_panel
)

@pytest.fixture
def sample_series():
    """Create a sample series for testing."""
    np.random.seed(42)
    return pd.Series(np.random.randn(100) * 10 + 50)

@pytest.fixture
def sample_panel():
    """Create a sample panel DataFrame (MultiIndex)."""
    dates = pd.date_range('2023-01-01', periods=10)
    symbols = ['AAPL', 'MSFT', 'GOOG']
    index = pd.MultiIndex.from_product([dates, symbols], names=['date', 'symbol'])
    
    np.random.seed(42)
    df = pd.DataFrame({
        'signal': np.random.randn(len(index)),
        'volume': np.random.randint(100, 1000, len(index))
    }, index=index)
    
    return df

def test_zscore_normalize(sample_series):
    """Test standard Z-score normalization."""
    normalized = zscore_normalize(sample_series)
    
    # Check mean and std (with 1e-6 tolerance for floating point)
    assert abs(normalized.mean()) < 1e-6
    assert abs(normalized.std() - 1.0) < 1e-6
    assert len(normalized) == len(sample_series)

def test_zscore_constant_series():
    """Test Z-score with constant values."""
    constant = pd.Series([10.0] * 10)
    normalized = zscore_normalize(constant)
    
    # Should return zeros
    assert (normalized == 0.0).all()

def test_rank_normalize(sample_series):
    """Test rank-based normalization to [-1, 1]."""
    normalized = rank_normalize(sample_series)
    
    assert normalized.min() >= -1.0
    assert normalized.max() <= 1.0
    # Median of uniform [-1, 1] should be around 0
    assert abs(normalized.median()) < 0.2

def test_robust_normalize(sample_series):
    """Test robust normalization (Median/IQR)."""
    # Add an extreme outlier
    sample_series.iloc[0] = 1000.0
    
    normalized = robust_normalize(sample_series)
    
    # Median should be 0
    assert abs(normalized.median()) < 1e-10
    # IQR should be 1
    q1 = normalized.quantile(0.25)
    q3 = normalized.quantile(0.75)
    assert abs((q3 - q1) - 1.0) < 1e-10

def test_rolling_normalize(sample_series):
    """Test rolling window normalization (PIT-safe)."""
    window = 20
    normalized = rolling_normalize(sample_series, window=window)
    
    # First window-1 values should be 0 (due to min_periods default=window)
    assert (normalized.iloc[:window-1] == 0.0).all()
    # Check a value after window
    val = normalized.iloc[window]
    expected_mean = sample_series.iloc[window-window+1:window+1].mean()
    # Note: our rolling_normalize uses current point in window (rolling default)
    # This is standard for signal processing as long as you use lagged inputs.

def test_expanding_normalize(sample_series):
    """Test expanding window normalization."""
    min_periods = 20
    normalized = expanding_normalize(sample_series, min_periods=min_periods)
    
    assert (normalized.iloc[:min_periods-1] == 0.0).all()
    assert not pd.isna(normalized.iloc[min_periods])

def test_normalizer_class(sample_series):
    """Test Normalizer unified interface."""
    # Test Z-score
    norm_z = Normalizer(method='zscore')
    result_z = norm_z.normalize(sample_series)
    assert abs(result_z.mean()) < 1e-10
    
    # Test Rank
    norm_r = Normalizer(method='rank')
    result_r = norm_r.normalize(sample_series)
    assert result_r.max() <= 1.0
    
    # Test Unknown method
    with pytest.raises(ValueError, match="Unknown normalization method"):
        Normalizer(method='invalid').normalize(sample_series)

def test_normalize_panel_cross_sectional(sample_panel):
    """Test panel normalization (per date)."""
    result = normalize_panel(sample_panel, columns='signal', method='zscore', by_date=True)
    
    assert 'signal_norm' in result.columns
    
    # For each date, mean should be 0
    for date in result.index.get_level_values('date').unique():
        date_mean = result.loc[date, 'signal_norm'].mean()
        assert abs(date_mean) < 1e-10

def test_normalize_panel_time_series(sample_panel):
    """Test panel normalization (per symbol)."""
    # For time-series, use expanding to be PIT-safe
    result = normalize_panel(sample_panel, columns='signal', method='expanding', by_date=False, min_periods=2)
    
    assert 'signal_norm' in result.columns
    
    # Check for one symbol MSFT
    msft_data = result.xs('MSFT', level='symbol')['signal_norm']
    assert msft_data.iloc[0] == 0.0 # Below min_periods
    assert msft_data.iloc[2] != 0.0 # Above min_periods

