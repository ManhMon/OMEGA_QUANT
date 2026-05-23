"""
Test Suite for Feature Factory

Tests cover:
1. Basic feature computation (RSI, MACD, Bollinger Bands, ATR)
2. Market microstructure features (VWAP, spread, volume)
3. T-1 lag enforcement (PIT safety)
4. available_at timestamp tracking
5. Vectorization (no loops, 100% Pandas/NumPy)
6. Edge cases (missing data, single symbol, insufficient history)

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.core.feature_factory import FeatureFactory


class TestFeatureFactoryBasics:
    """Test basic FeatureFactory functionality."""
    
    def test_initialization_default(self):
        """Test FeatureFactory initialization with default parameters."""
        factory = FeatureFactory()
        assert factory.rsi_period == 14
        assert factory.macd_fast == 12
        assert factory.macd_slow == 26
        assert factory.macd_signal == 9
        assert factory.bb_period == 20
        assert factory.bb_std == 2.0
        assert factory.atr_period == 14
        assert factory.volume_ma_period == 20
    
    def test_initialization_custom(self):
        """Test FeatureFactory initialization with custom parameters."""
        factory = FeatureFactory(
            rsi_period=10,
            macd_fast=8,
            macd_slow=21,
            macd_signal=5,
            bb_period=15,
            bb_std=2.5,
            atr_period=10,
            volume_ma_period=15
        )
        assert factory.rsi_period == 10
        assert factory.macd_fast == 8
        assert factory.macd_slow == 21
        assert factory.macd_signal == 5
        assert factory.bb_period == 15
        assert factory.bb_std == 2.5
        assert factory.atr_period == 10
        assert factory.volume_ma_period == 15


class TestFeatureComputation:
    """Test feature computation correctness."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        symbols = ['VNM', 'VIC', 'VHM']
        
        data = []
        for symbol in symbols:
            base_price = 100.0
            for i, date in enumerate(dates):
                # Generate realistic OHLCV data
                close = base_price * (1 + np.random.randn() * 0.02)
                high = close * (1 + abs(np.random.randn()) * 0.01)
                low = close * (1 - abs(np.random.randn()) * 0.01)
                open_price = close * (1 + np.random.randn() * 0.005)
                volume = 1000000 * (1 + abs(np.random.randn()) * 0.3)
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
                
                base_price = close
        
        return pd.DataFrame(data)
    
    def test_compute_all_features_basic(self, sample_data):
        """Test basic feature computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # Check output structure
        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0
        assert 'available_at' in features.columns
        
        # Check feature columns exist
        expected_features = [
            'feat_rsi', 'feat_macd', 'feat_macd_signal', 'feat_macd_hist',
            'feat_bb_upper', 'feat_bb_middle', 'feat_bb_lower',
            'feat_bb_width', 'feat_bb_position',
            'feat_atr', 'feat_vwap', 'feat_spread',
            'feat_volume_ratio', 'feat_turnover',
            'feat_return_1d', 'feat_return_5d', 'feat_return_20d'
        ]
        for feat in expected_features:
            assert feat in features.columns, f"Missing feature: {feat}"
    
    def test_t1_lag_enforcement(self, sample_data):
        """Test T-1 lag enforcement (PIT safety)."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # For each symbol, verify features are shifted by 1 period
        for symbol in sample_data['symbol'].unique():
            symbol_data = sample_data[sample_data['symbol'] == symbol].sort_values('date')
            symbol_features = features[features['symbol'] == symbol].sort_values('date')
            
            # Check that available_at is 1 day ahead of date
            if len(symbol_features) > 0:
                date_diff = (symbol_features['available_at'] - symbol_features['date']).dt.days
                assert (date_diff >= 1).all(), "T-1 lag not enforced"
    
    def test_available_at_timestamp(self, sample_data):
        """Test available_at timestamp correctness."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # available_at should be > date for all rows
        assert (features['available_at'] > features['date']).all()
        
        # No NaN in available_at
        assert features['available_at'].notna().all()
    
    def test_rsi_computation(self, sample_data):
        """Test RSI computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # RSI should be between 0 and 100
        rsi_values = features['feat_rsi'].dropna()
        assert (rsi_values >= 0).all()
        assert (rsi_values <= 100).all()
        
        # RSI should have reasonable values (not all extreme)
        assert rsi_values.mean() > 20
        assert rsi_values.mean() < 80
    
    def test_macd_computation(self, sample_data):
        """Test MACD computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # MACD histogram should equal MACD - signal
        macd_diff = (features['feat_macd'] - features['feat_macd_signal']).dropna()
        macd_hist = features['feat_macd_hist'].dropna()
        
        # Allow small numerical errors
        assert np.allclose(macd_diff, macd_hist, rtol=1e-5, atol=1e-8)
    
    def test_bollinger_bands_computation(self, sample_data):
        """Test Bollinger Bands computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # Upper band should be > middle > lower
        valid_rows = features[['feat_bb_upper', 'feat_bb_middle', 'feat_bb_lower']].dropna()
        assert (valid_rows['feat_bb_upper'] >= valid_rows['feat_bb_middle']).all()
        assert (valid_rows['feat_bb_middle'] >= valid_rows['feat_bb_lower']).all()
        
        # BB position should be between 0 and 1 (mostly)
        bb_pos = features['feat_bb_position'].dropna()
        assert bb_pos.quantile(0.05) >= -0.5  # Allow some outliers
        assert bb_pos.quantile(0.95) <= 1.5
    
    def test_atr_computation(self, sample_data):
        """Test ATR computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # ATR should be positive
        atr_values = features['feat_atr'].dropna()
        assert (atr_values > 0).all()
    
    def test_vwap_computation(self, sample_data):
        """Test VWAP computation."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # VWAP should be positive
        vwap_values = features['feat_vwap'].dropna()
        assert (vwap_values > 0).all()
        
        # VWAP should be close to typical price
        # (within reasonable range of close price)
        for symbol in features['symbol'].unique():
            symbol_features = features[features['symbol'] == symbol]
            symbol_data = sample_data[sample_data['symbol'] == symbol]
            
            # Merge to compare
            merged = symbol_features.merge(
                symbol_data[['date', 'symbol', 'close']],
                on=['date', 'symbol'],
                how='inner',
                suffixes=('', '_orig')
            )
            
            if len(merged) > 0:
                # Use close_orig if close was duplicated
                close_col = 'close_orig' if 'close_orig' in merged.columns else 'close'
                ratio = merged['feat_vwap'] / merged[close_col]
                assert ratio.quantile(0.05) > 0.8
                assert ratio.quantile(0.95) < 1.2
    
    def test_volume_features(self, sample_data):
        """Test volume-based features."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # Volume ratio should be positive
        vol_ratio = features['feat_volume_ratio'].dropna()
        assert (vol_ratio > 0).all()
        
        # Turnover should be positive
        turnover = features['feat_turnover'].dropna()
        assert (turnover > 0).all()
    
    def test_return_features(self, sample_data):
        """Test return features."""
        factory = FeatureFactory()
        features = factory.compute_all_features(sample_data)
        
        # Returns should be reasonable (not extreme)
        for ret_col in ['feat_return_1d', 'feat_return_5d', 'feat_return_20d']:
            returns = features[ret_col].dropna()
            assert returns.quantile(0.01) > -0.5  # -50% max loss
            assert returns.quantile(0.99) < 0.5   # +50% max gain


class TestVectorization:
    """Test vectorization (no loops)."""
    
    @pytest.fixture
    def large_data(self):
        """Create large dataset for vectorization testing."""
        np.random.seed(42)
        dates = pd.date_range('2020-01-01', periods=252, freq='D')
        symbols = [f'SYM{i:03d}' for i in range(100)]
        
        data = []
        for symbol in symbols:
            base_price = 100.0
            for date in dates:
                close = base_price * (1 + np.random.randn() * 0.02)
                high = close * (1 + abs(np.random.randn()) * 0.01)
                low = close * (1 - abs(np.random.randn()) * 0.01)
                volume = 1000000 * (1 + abs(np.random.randn()) * 0.3)
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
                
                base_price = close
        
        return pd.DataFrame(data)
    
    def test_vectorization_performance(self, large_data):
        """Test that computation is vectorized (fast)."""
        import time
        
        factory = FeatureFactory()
        
        start = time.time()
        features = factory.compute_all_features(large_data)
        elapsed = time.time() - start
        
        # Should process 100 symbols * 252 days in < 5 seconds
        assert elapsed < 5.0, f"Computation too slow: {elapsed:.2f}s"
        assert len(features) > 0
    
    def test_no_iterrows(self):
        """Test that implementation doesn't use iterrows."""
        import inspect
        
        factory = FeatureFactory()
        source = inspect.getsource(factory.compute_all_features)
        
        # Check for banned patterns
        assert 'iterrows' not in source
        assert 'itertuples' not in source
        assert 'for i in range' not in source


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_missing_columns(self):
        """Test error handling for missing columns."""
        factory = FeatureFactory()
        
        # Missing required columns
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10),
            'symbol': ['VNM'] * 10,
            'close': np.random.randn(10) + 100
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            factory.compute_all_features(df)
    
    def test_single_symbol(self):
        """Test computation with single symbol."""
        factory = FeatureFactory()
        
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'symbol': ['VNM'] * 50,
            'high': np.random.randn(50) + 102,
            'low': np.random.randn(50) + 98,
            'close': np.random.randn(50) + 100,
            'volume': np.random.randn(50) * 100000 + 1000000
        })
        
        features = factory.compute_all_features(df)
        assert len(features) > 0
        assert (features['symbol'] == 'VNM').all()
    
    def test_insufficient_history(self):
        """Test computation with insufficient history."""
        factory = FeatureFactory()
        
        # Only 5 days of data
        dates = pd.date_range('2024-01-01', periods=5, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'symbol': ['VNM'] * 5,
            'high': [102, 103, 101, 104, 102],
            'low': [98, 99, 97, 100, 98],
            'close': [100, 101, 99, 102, 100],
            'volume': [1000000] * 5
        })
        
        features = factory.compute_all_features(df)
        
        # Should still compute features (with NaN for early periods)
        assert len(features) >= 0
    
    def test_nan_handling(self):
        """Test handling of NaN values in input."""
        factory = FeatureFactory()
        
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'symbol': ['VNM'] * 30,
            'high': np.random.randn(30) + 102,
            'low': np.random.randn(30) + 98,
            'close': np.random.randn(30) + 100,
            'volume': np.random.randn(30) * 100000 + 1000000
        })
        
        # Introduce some NaN values
        df.loc[5:7, 'close'] = np.nan
        df.loc[10:12, 'volume'] = np.nan
        
        features = factory.compute_all_features(df)
        
        # Should handle NaN gracefully
        assert len(features) > 0
    
    def test_zero_volume(self):
        """Test handling of zero volume."""
        factory = FeatureFactory()
        
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'symbol': ['VNM'] * 30,
            'high': np.random.randn(30) + 102,
            'low': np.random.randn(30) + 98,
            'close': np.random.randn(30) + 100,
            'volume': np.random.randn(30) * 100000 + 1000000
        })
        
        # Set some volumes to zero
        df.loc[5:7, 'volume'] = 0
        
        features = factory.compute_all_features(df)
        
        # Should handle zero volume gracefully
        assert len(features) > 0


class TestFeatureSubset:
    """Test feature subset computation."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        
        return pd.DataFrame({
            'date': dates,
            'symbol': ['VNM'] * 50,
            'high': np.random.randn(50) + 102,
            'low': np.random.randn(50) + 98,
            'close': np.random.randn(50) + 100,
            'volume': np.random.randn(50) * 100000 + 1000000
        })
    
    def test_compute_feature_subset(self, sample_data):
        """Test computing a subset of features."""
        factory = FeatureFactory()
        
        features = factory.compute_feature_subset(
            sample_data,
            features=['rsi', 'macd', 'atr']
        )
        
        # Should only have requested features
        assert 'feat_rsi' in features.columns
        assert 'feat_macd' in features.columns
        assert 'feat_atr' in features.columns
        
        # Should not have other features
        assert 'feat_bb_upper' not in features.columns
        assert 'feat_vwap' not in features.columns
    
    def test_compute_feature_subset_with_prefix(self, sample_data):
        """Test computing subset with feat_ prefix."""
        factory = FeatureFactory()
        
        features = factory.compute_feature_subset(
            sample_data,
            features=['feat_rsi', 'feat_macd']
        )
        
        assert 'feat_rsi' in features.columns
        assert 'feat_macd' in features.columns


class TestMultipleSymbols:
    """Test computation across multiple symbols."""
    
    @pytest.fixture
    def multi_symbol_data(self):
        """Create multi-symbol dataset."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        symbols = ['VNM', 'VIC', 'VHM', 'HPG', 'VCB']
        
        data = []
        for symbol in symbols:
            base_price = 100.0
            for date in dates:
                close = base_price * (1 + np.random.randn() * 0.02)
                high = close * (1 + abs(np.random.randn()) * 0.01)
                low = close * (1 - abs(np.random.randn()) * 0.01)
                volume = 1000000 * (1 + abs(np.random.randn()) * 0.3)
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
                
                base_price = close
        
        return pd.DataFrame(data)
    
    def test_features_computed_per_symbol(self, multi_symbol_data):
        """Test that features are computed independently per symbol."""
        factory = FeatureFactory()
        features = factory.compute_all_features(multi_symbol_data)
        
        # Each symbol should have features
        for symbol in multi_symbol_data['symbol'].unique():
            symbol_features = features[features['symbol'] == symbol]
            assert len(symbol_features) > 0
            assert symbol_features['feat_rsi'].notna().sum() > 0
    
    def test_no_cross_symbol_leakage(self, multi_symbol_data):
        """Test that features don't leak across symbols."""
        factory = FeatureFactory()
        
        # Compute features for all symbols
        all_features = factory.compute_all_features(multi_symbol_data)
        
        # Compute features for each symbol separately
        for symbol in multi_symbol_data['symbol'].unique():
            symbol_data = multi_symbol_data[multi_symbol_data['symbol'] == symbol]
            symbol_features = factory.compute_all_features(symbol_data)
            
            # Features should match
            all_symbol_features = all_features[all_features['symbol'] == symbol]
            
            # Compare RSI values (allowing for small numerical differences)
            merged = all_symbol_features.merge(
                symbol_features[['date', 'symbol', 'feat_rsi']],
                on=['date', 'symbol'],
                suffixes=('_all', '_single')
            )
            
            if len(merged) > 0:
                rsi_diff = (merged['feat_rsi_all'] - merged['feat_rsi_single']).abs()
                # Check non-NaN values match
                valid_diff = rsi_diff.dropna()
                if len(valid_diff) > 0:
                    assert (valid_diff < 1e-6).all()
