"""
OMEGA_QUANT Feature Factory - Statistical Features Tests
Phase 2.2: Feature Engineering - Test Suite

Tests for:
- 100% Vectorization (no Python loops)
- PIT Safety (T-1 lag enforcement)
- Correctness of Skewness, Kurtosis, Z-score, Correlation

Author: Backend Engineer (Role 9)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.features.statistical_features import (
    compute_rolling_skewness,
    compute_rolling_kurtosis,
    compute_rolling_zscore,
    compute_rolling_correlation,
    compute_all_statistical_features
)


@pytest.fixture
def sample_ohlcv():
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 100
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    
    # Generate realistic price data
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n) * 1)
    low = close - np.abs(np.random.randn(n) * 1)
    open_price = close + np.random.randn(n) * 0.5
    volume = np.random.randint(1000, 10000, n)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    return df


class TestRollingSkewness:
    """Test Rolling Skewness computation."""
    
    def test_skewness_basic(self, sample_ohlcv):
        """Test basic skewness computation."""
        skew = compute_rolling_skewness(sample_ohlcv['close'], period=20, lag=1)
        
        # Check output type and shape
        assert isinstance(skew, pd.Series)
        assert len(skew) == len(sample_ohlcv)
        
        # Skewness should be finite (no inf values)
        valid_skew = skew.dropna()
        assert np.isfinite(valid_skew).all()
    
    def test_skewness_pit_safety(self, sample_ohlcv):
        """Test PIT safety: Skewness at time t uses data up to t-1."""
        skew_lag1 = compute_rolling_skewness(sample_ohlcv['close'], period=20, lag=1)
        skew_lag0 = compute_rolling_skewness(sample_ohlcv['close'], period=20, lag=0)
        
        # lag=1 should shift output by 1 period
        if not pd.isna(skew_lag0.iloc[0]):
            assert skew_lag1.iloc[1] == skew_lag0.iloc[0]
        assert pd.isna(skew_lag1.iloc[0])
    
    def test_skewness_no_lookahead(self, sample_ohlcv):
        """Test no lookahead: changing future data doesn't affect past skewness."""
        close_original = sample_ohlcv['close'].copy()
        skew_original = compute_rolling_skewness(close_original, period=20, lag=1)
        
        # Modify future data
        close_modified = close_original.copy()
        close_modified.iloc[-10:] = close_modified.iloc[-10:] * 2
        skew_modified = compute_rolling_skewness(close_modified, period=20, lag=1)
        
        # Past values should be identical
        np.testing.assert_array_equal(
            skew_original.iloc[:-11].values,
            skew_modified.iloc[:-11].values
        )
    
    def test_skewness_warmup_period(self, sample_ohlcv):
        """Test that warmup period is handled correctly."""
        period = 20
        skew = compute_rolling_skewness(sample_ohlcv['close'], period=period, lag=0)
        
        # First (period-1) values should be NaN or 0 (fillna)
        # After fillna(0), they should be 0
        assert (skew.iloc[:period-1] == 0).all() or skew.iloc[:period-1].isna().all()


class TestRollingKurtosis:
    """Test Rolling Kurtosis computation."""
    
    def test_kurtosis_basic(self, sample_ohlcv):
        """Test basic kurtosis computation."""
        kurt = compute_rolling_kurtosis(sample_ohlcv['close'], period=20, lag=1)
        
        # Check output type and shape
        assert isinstance(kurt, pd.Series)
        assert len(kurt) == len(sample_ohlcv)
        
        # Kurtosis should be finite (no inf values)
        valid_kurt = kurt.dropna()
        assert np.isfinite(valid_kurt).all()
    
    def test_kurtosis_pit_safety(self, sample_ohlcv):
        """Test PIT safety: Kurtosis at time t uses data up to t-1."""
        kurt_lag1 = compute_rolling_kurtosis(sample_ohlcv['close'], period=20, lag=1)
        kurt_lag0 = compute_rolling_kurtosis(sample_ohlcv['close'], period=20, lag=0)
        
        # lag=1 should shift output by 1 period
        if not pd.isna(kurt_lag0.iloc[0]):
            assert kurt_lag1.iloc[1] == kurt_lag0.iloc[0]
        assert pd.isna(kurt_lag1.iloc[0])
    
    def test_kurtosis_no_lookahead(self, sample_ohlcv):
        """Test no lookahead: changing future data doesn't affect past kurtosis."""
        close_original = sample_ohlcv['close'].copy()
        kurt_original = compute_rolling_kurtosis(close_original, period=20, lag=1)
        
        # Modify future data
        close_modified = close_original.copy()
        close_modified.iloc[-10:] = close_modified.iloc[-10:] * 2
        kurt_modified = compute_rolling_kurtosis(close_modified, period=20, lag=1)
        
        # Past values should be identical
        np.testing.assert_array_equal(
            kurt_original.iloc[:-11].values,
            kurt_modified.iloc[:-11].values
        )
    
    def test_kurtosis_warmup_period(self, sample_ohlcv):
        """Test that warmup period is handled correctly."""
        period = 20
        kurt = compute_rolling_kurtosis(sample_ohlcv['close'], period=period, lag=0)
        
        # First (period-1) values should be NaN or 0 (fillna)
        assert (kurt.iloc[:period-1] == 0).all() or kurt.iloc[:period-1].isna().all()


class TestRollingZScore:
    """Test Rolling Z-score computation."""
    
    def test_zscore_basic(self, sample_ohlcv):
        """Test basic z-score computation."""
        zscore = compute_rolling_zscore(sample_ohlcv['close'], period=20, lag=1)
        
        # Check output type and shape
        assert isinstance(zscore, pd.Series)
        assert len(zscore) == len(sample_ohlcv)
        
        # Z-score should be finite (no inf values)
        valid_zscore = zscore.dropna()
        assert np.isfinite(valid_zscore).all()
    
    def test_zscore_interpretation(self, sample_ohlcv):
        """Test z-score interpretation: most values should be within [-3, 3]."""
        zscore = compute_rolling_zscore(sample_ohlcv['close'], period=20, lag=1)
        
        valid_zscore = zscore.dropna()
        
        # In normal distribution, ~99.7% of values are within 3 std devs
        # For financial data, we expect most (>80%) to be within [-3, 3]
        within_3std = ((valid_zscore >= -3) & (valid_zscore <= 3)).sum()
        total = len(valid_zscore)
        
        assert within_3std / total > 0.8
    
    def test_zscore_pit_safety(self, sample_ohlcv):
        """Test PIT safety: Z-score at time t uses data up to t-1."""
        zscore_lag1 = compute_rolling_zscore(sample_ohlcv['close'], period=20, lag=1)
        zscore_lag0 = compute_rolling_zscore(sample_ohlcv['close'], period=20, lag=0)
        
        # lag=1 should shift output by 1 period
        if not pd.isna(zscore_lag0.iloc[0]):
            assert zscore_lag1.iloc[1] == zscore_lag0.iloc[0]
        assert pd.isna(zscore_lag1.iloc[0])
    
    def test_zscore_no_lookahead(self, sample_ohlcv):
        """Test no lookahead: changing future data doesn't affect past z-score."""
        close_original = sample_ohlcv['close'].copy()
        zscore_original = compute_rolling_zscore(close_original, period=20, lag=1)
        
        # Modify future data
        close_modified = close_original.copy()
        close_modified.iloc[-10:] = close_modified.iloc[-10:] * 2
        zscore_modified = compute_rolling_zscore(close_modified, period=20, lag=1)
        
        # Past values should be identical
        np.testing.assert_array_equal(
            zscore_original.iloc[:-11].values,
            zscore_modified.iloc[:-11].values
        )
    
    def test_zscore_zero_std_handling(self):
        """Test z-score handles zero standard deviation (constant prices)."""
        # Create constant price series
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        close = pd.Series([100.0] * 50, index=dates)
        
        zscore = compute_rolling_zscore(close, period=20, lag=1)
        
        # Should not have inf values (fillna(0) handles division by zero)
        # Drop NaN from lag shift before checking
        valid_zscore = zscore.dropna()
        assert np.isfinite(valid_zscore).all()


class TestRollingCorrelation:
    """Test Rolling Correlation computation."""
    
    def test_correlation_basic(self, sample_ohlcv):
        """Test basic correlation computation."""
        corr = compute_rolling_correlation(
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=20,
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(corr, pd.Series)
        assert len(corr) == len(sample_ohlcv)
        
        # Correlation should be in [-1, 1]
        valid_corr = corr.dropna()
        assert (valid_corr >= -1).all()
        assert (valid_corr <= 1).all()
    
    def test_correlation_pit_safety(self, sample_ohlcv):
        """Test PIT safety: Correlation at time t uses data up to t-1."""
        corr_lag1 = compute_rolling_correlation(
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=20,
            lag=1
        )
        corr_lag0 = compute_rolling_correlation(
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=20,
            lag=0
        )
        
        # lag=1 should shift output by 1 period
        if not pd.isna(corr_lag0.iloc[0]):
            assert corr_lag1.iloc[1] == corr_lag0.iloc[0]
        assert pd.isna(corr_lag1.iloc[0])
    
    def test_correlation_no_lookahead(self, sample_ohlcv):
        """Test no lookahead: changing future data doesn't affect past correlation."""
        close_original = sample_ohlcv['close'].copy()
        volume_original = sample_ohlcv['volume'].copy()
        corr_original = compute_rolling_correlation(
            close_original, volume_original, period=20, lag=1
        )
        
        # Modify future data
        close_modified = close_original.copy()
        volume_modified = volume_original.copy()
        close_modified.iloc[-10:] = close_modified.iloc[-10:] * 2
        volume_modified.iloc[-10:] = volume_modified.iloc[-10:] * 2
        corr_modified = compute_rolling_correlation(
            close_modified, volume_modified, period=20, lag=1
        )
        
        # Past values should be identical
        np.testing.assert_array_equal(
            corr_original.iloc[:-11].values,
            corr_modified.iloc[:-11].values
        )
    
    def test_correlation_range_bounds(self):
        """Test correlation stays within valid range [-1, 1]."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        np.random.seed(42)
        
        # Generate random price and volume data
        close = pd.Series(100 + np.cumsum(np.random.randn(100) * 2), index=dates)
        volume = pd.Series(np.random.randint(1000, 10000, 100), index=dates)
        
        corr = compute_rolling_correlation(close, volume, period=20, lag=0)
        
        # After warmup, correlation should be in valid range [-1, 1]
        valid_corr = corr.dropna()
        
        # Check correlation is in valid range [-1, 1]
        assert (valid_corr >= -1).all()
        assert (valid_corr <= 1).all()


class TestAllStatisticalFeatures:
    """Test compute_all_statistical_features function."""
    
    def test_all_features_basic(self, sample_ohlcv):
        """Test computing all statistical features at once."""
        result = compute_all_statistical_features(sample_ohlcv, lag=1)
        
        # Check output type
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv)
        
        # Check all expected columns exist
        expected_cols = {
            'rolling_skew',
            'rolling_kurt',
            'rolling_zscore',
            'rolling_corr_ret_vol'
        }
        assert expected_cols == set(result.columns)
    
    def test_all_features_missing_columns(self):
        """Test error handling for missing columns."""
        df = pd.DataFrame({
            'close': [100, 101, 102]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            compute_all_statistical_features(df)
    
    def test_all_features_pit_safety(self, sample_ohlcv):
        """Test PIT safety for all statistical features."""
        result = compute_all_statistical_features(sample_ohlcv, lag=1)
        
        # First row should be all NaN (due to lag=1)
        assert result.iloc[0].isna().all()
        
        # Check that no feature uses future data
        # by verifying lag=1 shifts all outputs by 1 period
        result_lag0 = compute_all_statistical_features(sample_ohlcv, lag=0)
        
        for col in result.columns:
            if not pd.isna(result_lag0[col].iloc[0]):
                assert result[col].iloc[1] == result_lag0[col].iloc[0]
    
    def test_all_features_custom_periods(self, sample_ohlcv):
        """Test custom period parameters."""
        result = compute_all_statistical_features(
            sample_ohlcv,
            skew_period=10,
            kurt_period=15,
            zscore_period=25,
            corr_period=30,
            lag=1
        )
        
        # Should still produce all columns
        assert len(result.columns) == 4
        assert isinstance(result, pd.DataFrame)


class TestVectorization:
    """Test that all functions are truly vectorized (no Python loops)."""
    
    def test_no_python_loops_in_source(self):
        """
        Verify that statistical_features.py uses vectorized operations.
        
        This is a code inspection test - checks that the source code
        doesn't contain explicit Python loops over data.
        """
        import inspect
        from omega.quant.features import statistical_features
        
        source = inspect.getsource(statistical_features)
        
        # Check for common loop patterns (this is a heuristic)
        forbidden_patterns = [
            'for i in range(len(',
            'for idx in range(len(',
            'while i <',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"Found non-vectorized pattern: {pattern}"
    
    def test_performance_vectorization(self, sample_ohlcv):
        """
        Test that vectorized implementation is fast.
        
        This is a smoke test - if implementation uses Python loops,
        it will be significantly slower.
        """
        import time
        
        # Generate larger dataset
        n = 10000
        dates = pd.date_range(start='2020-01-01', periods=n, freq='D')
        close = 100 + np.cumsum(np.random.randn(n) * 2)
        high = close + np.abs(np.random.randn(n) * 1)
        low = close - np.abs(np.random.randn(n) * 1)
        open_price = close + np.random.randn(n) * 0.5
        volume = np.random.randint(1000, 10000, n)
        
        large_df = pd.DataFrame({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        }, index=dates)
        
        # Time the computation
        start = time.time()
        result = compute_all_statistical_features(large_df, lag=1)
        elapsed = time.time() - start
        
        # Should complete in under 1 second for 10k rows (vectorized)
        # If it takes longer, likely using Python loops
        assert elapsed < 1.0, f"Computation too slow ({elapsed:.2f}s), likely not vectorized"


class TestPITCompliance:
    """Comprehensive PIT (Point-in-Time) compliance tests."""
    
    def test_no_future_leakage_skewness(self, sample_ohlcv):
        """Test skewness doesn't leak future information."""
        skew_full = compute_rolling_skewness(sample_ohlcv['close'], period=20, lag=1)
        skew_partial = compute_rolling_skewness(sample_ohlcv['close'].iloc[:50], period=20, lag=1)
        
        # Values should match for overlapping period
        np.testing.assert_array_equal(
            skew_full.iloc[:50].values,
            skew_partial.values
        )
    
    def test_no_future_leakage_kurtosis(self, sample_ohlcv):
        """Test kurtosis doesn't leak future information."""
        kurt_full = compute_rolling_kurtosis(sample_ohlcv['close'], period=20, lag=1)
        kurt_partial = compute_rolling_kurtosis(sample_ohlcv['close'].iloc[:50], period=20, lag=1)
        
        np.testing.assert_array_equal(
            kurt_full.iloc[:50].values,
            kurt_partial.values
        )
    
    def test_no_future_leakage_zscore(self, sample_ohlcv):
        """Test z-score doesn't leak future information."""
        zscore_full = compute_rolling_zscore(sample_ohlcv['close'], period=20, lag=1)
        zscore_partial = compute_rolling_zscore(sample_ohlcv['close'].iloc[:50], period=20, lag=1)
        
        np.testing.assert_array_equal(
            zscore_full.iloc[:50].values,
            zscore_partial.values
        )
    
    def test_no_future_leakage_correlation(self, sample_ohlcv):
        """Test correlation doesn't leak future information."""
        corr_full = compute_rolling_correlation(
            sample_ohlcv['close'], sample_ohlcv['volume'], period=20, lag=1
        )
        corr_partial = compute_rolling_correlation(
            sample_ohlcv['close'].iloc[:50],
            sample_ohlcv['volume'].iloc[:50],
            period=20,
            lag=1
        )
        
        np.testing.assert_array_equal(
            corr_full.iloc[:50].values,
            corr_partial.values
        )
    
    def test_temporal_consistency(self, sample_ohlcv):
        """
        Test temporal consistency: recomputing with same data produces same results.
        """
        result1 = compute_all_statistical_features(sample_ohlcv, lag=1)
        result2 = compute_all_statistical_features(sample_ohlcv, lag=1)
        
        pd.testing.assert_frame_equal(result1, result2)
    
    def test_lag_enforcement(self, sample_ohlcv):
        """Test that lag parameter correctly shifts all outputs."""
        result_lag1 = compute_all_statistical_features(sample_ohlcv, lag=1)
        result_lag2 = compute_all_statistical_features(sample_ohlcv, lag=2)
        
        # lag=2 should shift output by 1 more period than lag=1
        for col in result_lag1.columns:
            if not pd.isna(result_lag1[col].iloc[1]):
                assert result_lag2[col].iloc[2] == result_lag1[col].iloc[1]

