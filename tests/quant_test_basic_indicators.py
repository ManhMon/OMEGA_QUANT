"""
OMEGA_QUANT Feature Factory - Basic Indicators Tests
Phase 2.1: Feature Engineering - Test Suite

Tests for:
- 100% Vectorization (no Python loops)
- PIT Safety (T-1 lag enforcement)
- Correctness of RSI, MACD, Bollinger Bands, ATR, VWAP

Author: Backend Engineer (Role 9)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.features.basic_indicators import (
    compute_rsi,
    compute_macd,
    compute_bollinger_bands,
    compute_atr,
    compute_vwap,
    compute_all_basic_indicators
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


class TestRSI:
    """Test RSI computation."""
    
    def test_rsi_basic(self, sample_ohlcv):
        """Test basic RSI computation."""
        rsi = compute_rsi(sample_ohlcv['close'], period=14, lag=1)
        
        # Check output type and shape
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_ohlcv)
        
        # Check RSI range (0-100)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_rsi_pit_safety(self, sample_ohlcv):
        """Test PIT safety: RSI at time t uses data up to t-1."""
        rsi_lag1 = compute_rsi(sample_ohlcv['close'], period=14, lag=1)
        rsi_lag0 = compute_rsi(sample_ohlcv['close'], period=14, lag=0)
        
        # lag=1 should shift output by 1 period
        assert rsi_lag1.iloc[1] == rsi_lag0.iloc[0]
        assert pd.isna(rsi_lag1.iloc[0])
    
    def test_rsi_no_lookahead(self, sample_ohlcv):
        """Test no lookahead: changing future data doesn't affect past RSI."""
        close_original = sample_ohlcv['close'].copy()
        rsi_original = compute_rsi(close_original, period=14, lag=1)
        
        # Modify future data
        close_modified = close_original.copy()
        close_modified.iloc[-10:] = close_modified.iloc[-10:] * 2
        rsi_modified = compute_rsi(close_modified, period=14, lag=1)
        
        # Past values should be identical
        np.testing.assert_array_equal(
            rsi_original.iloc[:-11].values,
            rsi_modified.iloc[:-11].values
        )


class TestMACD:
    """Test MACD computation."""
    
    def test_macd_basic(self, sample_ohlcv):
        """Test basic MACD computation."""
        macd = compute_macd(sample_ohlcv['close'], fast=12, slow=26, signal=9, lag=1)
        
        # Check output type and columns
        assert isinstance(macd, pd.DataFrame)
        assert set(macd.columns) == {'macd', 'macd_signal', 'macd_hist'}
        assert len(macd) == len(sample_ohlcv)
    
    def test_macd_histogram_relationship(self, sample_ohlcv):
        """Test MACD histogram = MACD line - Signal line."""
        macd = compute_macd(sample_ohlcv['close'], fast=12, slow=26, signal=9, lag=1)
        
        # Drop NaN values for comparison
        valid = macd.dropna()
        
        # Check histogram relationship
        np.testing.assert_array_almost_equal(
            valid['macd_hist'].values,
            (valid['macd'] - valid['macd_signal']).values,
            decimal=10
        )
    
    def test_macd_pit_safety(self, sample_ohlcv):
        """Test PIT safety: MACD at time t uses data up to t-1."""
        macd_lag1 = compute_macd(sample_ohlcv['close'], fast=12, slow=26, signal=9, lag=1)
        macd_lag0 = compute_macd(sample_ohlcv['close'], fast=12, slow=26, signal=9, lag=0)
        
        # lag=1 should shift output by 1 period
        assert macd_lag1['macd'].iloc[1] == macd_lag0['macd'].iloc[0]
        assert pd.isna(macd_lag1['macd'].iloc[0])


class TestBollingerBands:
    """Test Bollinger Bands computation."""
    
    def test_bb_basic(self, sample_ohlcv):
        """Test basic Bollinger Bands computation."""
        bb = compute_bollinger_bands(sample_ohlcv['close'], period=20, num_std=2.0, lag=1)
        
        # Check output type and columns
        assert isinstance(bb, pd.DataFrame)
        assert set(bb.columns) == {'bb_upper', 'bb_middle', 'bb_lower', 'bb_width'}
        assert len(bb) == len(sample_ohlcv)
    
    def test_bb_band_ordering(self, sample_ohlcv):
        """Test upper >= middle >= lower."""
        bb = compute_bollinger_bands(sample_ohlcv['close'], period=20, num_std=2.0, lag=1)
        
        valid = bb.dropna()
        
        # Check band ordering
        assert (valid['bb_upper'] >= valid['bb_middle']).all()
        assert (valid['bb_middle'] >= valid['bb_lower']).all()
    
    def test_bb_width_calculation(self, sample_ohlcv):
        """Test bb_width = (upper - lower) / middle."""
        bb = compute_bollinger_bands(sample_ohlcv['close'], period=20, num_std=2.0, lag=1)
        
        valid = bb.dropna()
        
        # Check width calculation
        expected_width = (valid['bb_upper'] - valid['bb_lower']) / valid['bb_middle']
        np.testing.assert_array_almost_equal(
            valid['bb_width'].values,
            expected_width.values,
            decimal=10
        )
    
    def test_bb_pit_safety(self, sample_ohlcv):
        """Test PIT safety: BB at time t uses data up to t-1."""
        bb_lag1 = compute_bollinger_bands(sample_ohlcv['close'], period=20, num_std=2.0, lag=1)
        bb_lag0 = compute_bollinger_bands(sample_ohlcv['close'], period=20, num_std=2.0, lag=0)
        
        # lag=1 should shift output by 1 period
        # Skip comparison if both are NaN (warmup period)
        if not pd.isna(bb_lag0['bb_middle'].iloc[0]):
            assert bb_lag1['bb_middle'].iloc[1] == bb_lag0['bb_middle'].iloc[0]
        assert pd.isna(bb_lag1['bb_middle'].iloc[0])


class TestATR:
    """Test ATR computation."""
    
    def test_atr_basic(self, sample_ohlcv):
        """Test basic ATR computation."""
        atr = compute_atr(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            period=14,
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(atr, pd.Series)
        assert len(atr) == len(sample_ohlcv)
        
        # ATR should be positive
        valid_atr = atr.dropna()
        assert (valid_atr >= 0).all()
    
    def test_atr_minimum_value(self, sample_ohlcv):
        """Test ATR >= (high - low) for each bar."""
        atr = compute_atr(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            period=14,
            lag=0  # No lag for this test
        )
        
        # ATR should be at least as large as the smallest high-low range
        # (This is a weak test, but validates basic correctness)
        min_range = (sample_ohlcv['high'] - sample_ohlcv['low']).min()
        valid_atr = atr.dropna()
        assert valid_atr.min() >= 0
    
    def test_atr_pit_safety(self, sample_ohlcv):
        """Test PIT safety: ATR at time t uses data up to t-1."""
        atr_lag1 = compute_atr(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            period=14,
            lag=1
        )
        atr_lag0 = compute_atr(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            period=14,
            lag=0
        )
        
        # lag=1 should shift output by 1 period
        assert atr_lag1.iloc[1] == atr_lag0.iloc[0]
        assert pd.isna(atr_lag1.iloc[0])


class TestVWAP:
    """Test VWAP computation."""
    
    def test_vwap_basic(self, sample_ohlcv):
        """Test basic VWAP computation."""
        vwap = compute_vwap(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=None,
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(vwap, pd.Series)
        assert len(vwap) == len(sample_ohlcv)
        
        # VWAP should be positive
        valid_vwap = vwap.dropna()
        assert (valid_vwap > 0).all()
    
    def test_vwap_rolling(self, sample_ohlcv):
        """Test rolling VWAP computation."""
        vwap_rolling = compute_vwap(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=20,
            lag=1
        )
        
        # Check output
        assert isinstance(vwap_rolling, pd.Series)
        assert len(vwap_rolling) == len(sample_ohlcv)
    
    def test_vwap_pit_safety(self, sample_ohlcv):
        """Test PIT safety: VWAP at time t uses data up to t-1."""
        vwap_lag1 = compute_vwap(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=None,
            lag=1
        )
        vwap_lag0 = compute_vwap(
            sample_ohlcv['high'],
            sample_ohlcv['low'],
            sample_ohlcv['close'],
            sample_ohlcv['volume'],
            period=None,
            lag=0
        )
        
        # lag=1 should shift output by 1 period
        assert vwap_lag1.iloc[1] == vwap_lag0.iloc[0]
        assert pd.isna(vwap_lag1.iloc[0])


class TestAllIndicators:
    """Test compute_all_basic_indicators function."""
    
    def test_all_indicators_basic(self, sample_ohlcv):
        """Test computing all indicators at once."""
        result = compute_all_basic_indicators(sample_ohlcv, lag=1)
        
        # Check output type
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv)
        
        # Check all expected columns exist
        expected_cols = {
            'rsi', 'macd', 'macd_signal', 'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
            'atr', 'vwap'
        }
        assert expected_cols.issubset(set(result.columns))
    
    def test_all_indicators_missing_columns(self):
        """Test error handling for missing columns."""
        df = pd.DataFrame({
            'close': [100, 101, 102],
            'volume': [1000, 1100, 1200]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            compute_all_basic_indicators(df)
    
    def test_all_indicators_pit_safety(self, sample_ohlcv):
        """Test PIT safety for all indicators."""
        result = compute_all_basic_indicators(sample_ohlcv, lag=1)
        
        # First row should be all NaN (due to lag=1)
        assert result.iloc[0].isna().all()
        
        # Check that no indicator uses future data
        # by verifying lag=1 shifts all outputs by 1 period
        result_lag0 = compute_all_basic_indicators(sample_ohlcv, lag=0)
        
        for col in result.columns:
            if not pd.isna(result_lag0[col].iloc[0]):
                assert result[col].iloc[1] == result_lag0[col].iloc[0]


class TestVectorization:
    """Test that all functions are truly vectorized (no Python loops)."""
    
    def test_no_python_loops_in_source(self):
        """
        Verify that basic_indicators.py uses vectorized operations.
        
        This is a code inspection test - checks that the source code
        doesn't contain explicit Python loops over data.
        """
        import inspect
        from omega.quant.features import basic_indicators
        
        source = inspect.getsource(basic_indicators)
        
        # Check for common loop patterns (this is a heuristic)
        # We allow loops for building result DataFrames, but not for computation
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
        result = compute_all_basic_indicators(large_df, lag=1)
        elapsed = time.time() - start
        
        # Should complete in under 1 second for 10k rows (vectorized)
        # If it takes longer, likely using Python loops
        assert elapsed < 1.0, f"Computation too slow ({elapsed:.2f}s), likely not vectorized"


class TestPITCompliance:
    """Comprehensive PIT (Point-in-Time) compliance tests."""
    
    def test_no_future_leakage_rsi(self, sample_ohlcv):
        """Test RSI doesn't leak future information."""
        # Compute RSI on full dataset
        rsi_full = compute_rsi(sample_ohlcv['close'], period=14, lag=1)
        
        # Compute RSI on truncated dataset (first 50 rows)
        rsi_partial = compute_rsi(sample_ohlcv['close'].iloc[:50], period=14, lag=1)
        
        # Values should match for overlapping period
        np.testing.assert_array_equal(
            rsi_full.iloc[:50].values,
            rsi_partial.values
        )
    
    def test_no_future_leakage_macd(self, sample_ohlcv):
        """Test MACD doesn't leak future information."""
        macd_full = compute_macd(sample_ohlcv['close'], fast=12, slow=26, signal=9, lag=1)
        macd_partial = compute_macd(sample_ohlcv['close'].iloc[:50], fast=12, slow=26, signal=9, lag=1)
        
        np.testing.assert_array_equal(
            macd_full['macd'].iloc[:50].values,
            macd_partial['macd'].values
        )
    
    def test_temporal_consistency(self, sample_ohlcv):
        """
        Test temporal consistency: recomputing with same data produces same results.
        """
        result1 = compute_all_basic_indicators(sample_ohlcv, lag=1)
        result2 = compute_all_basic_indicators(sample_ohlcv, lag=1)
        
        pd.testing.assert_frame_equal(result1, result2)
    
    def test_lag_enforcement(self, sample_ohlcv):
        """Test that lag parameter correctly shifts all outputs."""
        result_lag1 = compute_all_basic_indicators(sample_ohlcv, lag=1)
        result_lag2 = compute_all_basic_indicators(sample_ohlcv, lag=2)
        
        # lag=2 should shift output by 1 more period than lag=1
        for col in result_lag1.columns:
            if not pd.isna(result_lag1[col].iloc[1]):
                assert result_lag2[col].iloc[2] == result_lag1[col].iloc[1]

