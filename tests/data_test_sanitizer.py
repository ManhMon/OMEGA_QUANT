"""
Test Suite for PIT-Safe DataSanitizer

Tests cover:
1. Basic sanitization functionality
2. PIT safety enforcement (as_of <= available_at)
3. Outlier clipping
4. Forward filling logic
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.data import DataSanitizer


class TestDataSanitizer:
    """Test DataSanitizer functionality."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data with missing values, duplicates, and outliers."""
        dates = pd.date_range('2026-01-01', '2026-01-10', freq='D')
        
        data = []
        for date in dates:
            # Skip some dates for forward fill testing
            if date == pd.Timestamp('2026-01-04'):
                continue
                
            row = {
                'date': date,
                'symbol': 'VNM',
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000000
            }
            data.append(row)
            
            # Duplicate
            if date == pd.Timestamp('2026-01-02'):
                data.append(row.copy())
                
        df = pd.DataFrame(data)
        
        # Add outlier
        df.loc[df['date'] == pd.Timestamp('2026-01-05'), 'close'] = 500.0
        
        # Add invalid price
        df.loc[df['date'] == pd.Timestamp('2026-01-06'), 'close'] = 0.001
        
        return df
        
    def test_initialization(self):
        """Test initialization parameters."""
        sanitizer = DataSanitizer(max_fill_days=5, outlier_sigma=2.5, min_price=0.05)
        assert sanitizer.max_fill_days == 5
        assert sanitizer.outlier_sigma == 2.5
        assert sanitizer.min_price == 0.05
        
    def test_clean_ohlcv_legacy(self, sample_data):
        """Test legacy clean_ohlcv method with PIT enforcement."""
        sanitizer = DataSanitizer()
        as_of_time = pd.Timestamp('2026-01-10 10:00:00')
        clean_df, stats = sanitizer.clean_ohlcv(sample_data, as_of_time=as_of_time)
        
        # Check stats
        assert stats['duplicates_removed'] == 1
        assert stats['invalid_prices_removed'] == 1
        
        # Check PIT enforcement
        assert 'as_of' in clean_df.columns
        assert 'available_at' in clean_df.columns
        assert (clean_df['as_of'] <= clean_df['available_at']).all()
        
    def test_fit_apply_pattern(self, sample_data):
        """Test fit/apply pattern for strict PIT safety."""
        # Split into train/test
        train_df = sample_data[sample_data['date'] <= '2026-01-05'].copy()
        test_df = sample_data[sample_data['date'] > '2026-01-05'].copy()
        
        as_of_time = pd.Timestamp('2026-01-10 10:00:00')
        sanitizer = DataSanitizer(as_of_time=as_of_time)
        
        # Must fit before apply
        with pytest.raises(RuntimeError):
            sanitizer.apply(test_df)
            
        sanitizer.fit(train_df)
        assert sanitizer._is_fitted is True
        
        clean_df = sanitizer.apply(test_df)
        
        # Check PIT enforcement
        assert 'as_of' in clean_df.columns
        assert 'available_at' in clean_df.columns
        assert (clean_df['as_of'] <= clean_df['available_at']).all()
        
    def test_forward_fill_limit(self):
        """Test max_fill_days constraint."""
        dates = pd.date_range('2026-01-01', '2026-01-10', freq='D')
        
        data = []
        for i, date in enumerate(dates):
            # 4-day gap
            if 2 <= i <= 5:
                continue
                
            data.append({
                'date': date,
                'symbol': 'VNM',
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000000
            })
            
        df = pd.DataFrame(data)
        
        sanitizer = DataSanitizer(max_fill_days=3)
        as_of_time = pd.Timestamp('2026-01-10 10:00:00')
        clean_df, stats = sanitizer.clean_ohlcv(df, as_of_time=as_of_time)
        
        # Should not fill 4-day gap completely
        assert len(clean_df) < len(dates)
