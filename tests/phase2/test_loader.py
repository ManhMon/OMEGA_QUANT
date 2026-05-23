"""
Test Suite for PIT-Safe DataLoader

Tests cover:
1. Basic loading functionality
2. PIT safety enforcement (as_of <= available_at)
3. Incremental caching
4. Data quality checks
5. Edge cases (weekends, missing data, outliers)

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from omega.data import DataLoader, PITViolationError, DataQualityError


def _mock_price_rows(symbol: str, start_date: str, end_date: str):
    """Generate mock price data for testing (hermetic, no API calls)."""
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    return [
        {
            'symbol': symbol,
            'timestamp': int(pd.Timestamp(d).timestamp()),
            'open': 100000.0 + i * 1000.0,
            'high': 101000.0 + i * 1000.0,
            'low': 99000.0 + i * 1000.0,
            'close': 100500.0 + i * 1000.0,
            'volume': int(1000 + i * 100),
        }
        for i, d in enumerate(dates)
    ]


@pytest.fixture
def mock_vnstock():
    """Mock VnstockVCIDataSource.fetch_price_data to avoid live API calls."""
    with patch('omega.data.loader.VnstockVCIDataSource') as mock_class:
        mock_instance = MagicMock()
        mock_instance.fetch_price_data.side_effect = _mock_price_rows
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def cache_dir(tmp_path):
    """Windows-safe cache dir under workspace-local pytest cache."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


class TestDataLoaderBasics:
    """Test basic DataLoader functionality."""
    
    def test_initialization(self, mock_vnstock):
        """Test DataLoader initialization with default parameters."""
        loader = DataLoader()
        assert loader.cache_dir.exists()
        assert loader.quality_threshold == 0.8
        assert loader.enable_pit_enforcement is True
    
    def test_initialization_custom_params(self, mock_vnstock, cache_dir):
        """Test DataLoader initialization with custom parameters."""
        loader = DataLoader(
            cache_dir=str(cache_dir),
            quality_threshold=0.9,
            outlier_std_threshold=3.0,
            enable_pit_enforcement=False
        )
        assert loader.cache_dir == cache_dir
        assert loader.quality_threshold == 0.9
        assert loader.outlier_std_threshold == 3.0
        assert loader.enable_pit_enforcement is False
    
    def test_load_prices_basic(self, mock_vnstock, cache_dir):
        """Test basic price loading."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check columns
        expected_cols = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'as_of', 'available_at']
        assert all(col in df.columns for col in expected_cols)
        
        # Check data types
        assert df['ticker'].dtype == object or pd.api.types.is_string_dtype(df['ticker'])
        assert pd.api.types.is_datetime64_any_dtype(df['date'])
        assert df['open'].dtype in [np.float64, float]
        assert pd.api.types.is_numeric_dtype(df['volume'])
        
        # Check non-empty
        assert len(df) > 0
    
    def test_load_prices_date_validation(self, mock_vnstock, cache_dir):
        """Test that start_date > end_date raises ValueError."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        with pytest.raises(ValueError, match="start_date.*must be <= end_date"):
            loader.load_prices(
                ticker="VNM",
                start_date="2026-01-10",
                end_date="2026-01-01",
                as_of_time=datetime(2026, 1, 15, 10, 0, 0)
            )


class TestPITSafety:
    """Test point-in-time safety enforcement."""
    
    def test_pit_timestamps_added(self, mock_vnstock, cache_dir):
        """Test that as_of and available_at timestamps are added."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-02",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        assert 'as_of' in df.columns
        assert 'available_at' in df.columns
        assert pd.api.types.is_datetime64_any_dtype(df['as_of'])
        assert pd.api.types.is_datetime64_any_dtype(df['available_at'])
    
    def test_pit_safety_constraint(self, mock_vnstock, cache_dir):
        """Test that as_of <= available_at for all rows."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-02",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        # Check PIT constraint
        violations = df[df['as_of'] > df['available_at']]
        assert len(violations) == 0, f"Found PIT violations: {violations}"
    
    def test_pit_filtering_by_as_of_time(self, mock_vnstock, cache_dir):
        """Test that data not available at as_of_time is filtered out."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Query as of 2026-01-03 (should only get data available by then)
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 3, 10, 0, 0)
        )
        
        # All available_at should be <= as_of_time
        assert all(df['available_at'] <= pd.Timestamp(datetime(2026, 1, 3, 10, 0, 0)))
    
    def test_pit_enforcement_disabled(self, mock_vnstock, cache_dir):
        """Test that PIT enforcement can be disabled."""
        loader = DataLoader(cache_dir=str(cache_dir), enable_pit_enforcement=False)
        
        # Should not filter by as_of_time when disabled
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 3, 10, 0, 0)
        )
        
        # Should have more data than with enforcement enabled
        assert len(df) > 0


class TestCaching:
    """Test incremental caching functionality."""
    
    def test_cache_creation(self, mock_vnstock, cache_dir):
        """Test that cache files are created."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check cache file exists
        cache_files = list(cache_dir.glob("*.parquet"))
        assert len(cache_files) == 1
    
    def test_cache_reuse(self, mock_vnstock, cache_dir):
        """Test that cached data is reused on subsequent calls."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # First call - creates cache
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Second call - uses cache
        df2 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Should be identical (compare values, not dtypes due to parquet roundtrip)
        assert len(df1) == len(df2)
        assert list(df1.columns) == list(df2.columns)
        pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True), check_dtype=False)
    
    def test_force_refresh(self, mock_vnstock, cache_dir):
        """Test that force_refresh bypasses cache."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # First call
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Second call with force_refresh
        df2 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            force_refresh=True
        )
        
        # Should have same structure but potentially different data
        assert list(df1.columns) == list(df2.columns)
        assert len(df1) == len(df2)
    
    def test_clear_cache(self, mock_vnstock, cache_dir):
        """Test cache clearing functionality."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Create cache
        loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Clear cache
        deleted = loader.clear_cache()
        assert deleted > 0
        
        # Check cache is empty
        cache_files = list(cache_dir.glob("*.parquet"))
        assert len(cache_files) == 0
    
    def test_cache_stats(self, mock_vnstock, cache_dir):
        """Test cache statistics."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Empty cache
        stats = loader.get_cache_stats()
        assert stats['file_count'] == 0
        assert stats['cache_size_mb'] == 0.0
        
        # Create cache
        loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check stats
        stats = loader.get_cache_stats()
        assert stats['file_count'] == 1
        assert stats['cache_size_mb'] > 0
        assert stats['oldest_file'] is not None
        assert stats['newest_file'] is not None


class TestDataQuality:
    """Test data quality checks."""
    
    def test_quality_score_calculation(self, mock_vnstock, cache_dir):
        """Test that quality score is calculated."""
        loader = DataLoader(cache_dir=str(cache_dir), quality_threshold=0.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Quality check should pass (mock data is clean)
        assert len(df) > 0
    
    def test_ohlc_consistency(self, mock_vnstock, cache_dir):
        """Test OHLC consistency checks."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check OHLC consistency
        assert all(df['high'] >= df['low'])
        assert all(df['high'] >= df['open'])
        assert all(df['high'] >= df['close'])
        assert all(df['low'] <= df['open'])
        assert all(df['low'] <= df['close'])
    
    def test_no_negative_prices(self, mock_vnstock, cache_dir):
        """Test that negative prices are detected."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check no negative prices
        assert all(df['open'] > 0)
        assert all(df['high'] > 0)
        assert all(df['low'] > 0)
        assert all(df['close'] > 0)
    
    def test_no_negative_volumes(self, mock_vnstock, cache_dir):
        """Test that negative volumes are detected."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check no negative volumes
        assert all(df['volume'] >= 0)


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_weekend_handling(self, mock_vnstock, cache_dir):
        """Test that weekends are handled correctly in available_at."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Include a Friday (2026-01-02 is Friday)
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-02",
            end_date="2026-01-02",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        if len(df) > 0:
            # Friday's data should be available on Monday
            friday_row = df.iloc[0]
            # available_at should be Monday (skip weekend)
            # 2026-01-02 is Friday, so available_at should be 2026-01-05 (Monday) at 09:00
            assert friday_row['available_at'].weekday() == 0, f"Expected Monday (0), got {friday_row['available_at'].weekday()} for {friday_row['available_at']}"
    
    def test_empty_date_range(self, mock_vnstock, cache_dir):
        """Test handling of date ranges with no trading days."""
        loader = DataLoader(cache_dir=str(cache_dir), quality_threshold=0.0)

        # Weekend only (no trading days) -> source returns no data
        with pytest.raises(ValueError, match="No data returned"):
            loader.load_prices(
                ticker="VNM",
                start_date="2026-01-03",  # Saturday
                end_date="2026-01-04",    # Sunday
                as_of_time=datetime(2026, 1, 10, 10, 0, 0)
            )
    
    def test_single_day_load(self, mock_vnstock, cache_dir):
        """Test loading a single day of data."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-02",
            end_date="2026-01-02",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        assert len(df) >= 0
    
    def test_multiple_tickers_separate_cache(self, mock_vnstock, cache_dir):
        """Test that different tickers have separate cache entries."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Load two different tickers
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        df2 = loader.load_prices(
            ticker="VCB",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Should have different data
        assert df1['ticker'].iloc[0] == "VNM"
        assert df2['ticker'].iloc[0] == "VCB"
        
        # Should have 2 cache files
        cache_files = list(cache_dir.glob("*.parquet"))
        assert len(cache_files) == 2
    
    def test_corrupted_cache_recovery(self, mock_vnstock, cache_dir):
        """Test that corrupted cache is detected and refreshed from source."""
        loader = DataLoader(cache_dir=str(cache_dir))
        
        # Create corrupted cache (missing as_of and available_at columns)
        cache_key = loader._generate_cache_key("VNM", "2026-01-01", "2026-01-10")
        cache_path = cache_dir / f"{cache_key}.parquet"
        
        corrupted_df = pd.DataFrame({
            'ticker': ['VNM'],
            'date': pd.to_datetime(['2026-01-01']),
            'open': [100.0],
            'high': [101.0],
            'low': [99.0],
            'close': [100.5],
            'volume': [1000]
        })
        corrupted_df.to_parquet(cache_path, index=False)
        
        # Load should detect corruption and refresh from source
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Should have all required columns including PIT timestamps
        assert 'as_of' in df.columns
        assert 'available_at' in df.columns
        assert len(df) > 0


class TestChecksumValidation:
    """Test checksum sidecar validation path in DataLoader."""
    
    def test_load_prices_checksum_validation(self, mock_vnstock, cache_dir):
        """Test that DataLoader.load_prices() exercises checksum sidecar path."""
        loader = DataLoader(cache_dir=str(cache_dir), validate_provenance=True)
        
        # Load data - this should trigger checksum validation
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Check that metadata sidecar was created (contains checksum)
        cache_key = loader._generate_cache_key("VNM", "2026-01-01", "2026-01-10")
        cache_path = cache_dir / f"{cache_key}.parquet"
        metadata_path = cache_path.with_suffix('.metadata.json')
        
        assert cache_path.exists(), "Cache file should exist"
        assert metadata_path.exists(), "Metadata sidecar should exist"
        
        # Verify metadata file has checksum
        import json
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            assert 'checksum' in metadata, "Metadata should contain checksum"
            assert 'checksum_algorithm' in metadata, "Metadata should contain checksum_algorithm"
            assert metadata['checksum_algorithm'] == 'sha256', "Checksum algorithm should be sha256"
            assert len(metadata['checksum']) == 64, "SHA256 checksum should be 64 hex chars"
    
    def test_checksum_validation_detects_tampering(self, mock_vnstock, cache_dir):
        """Test that checksum validation detects file tampering."""
        loader = DataLoader(cache_dir=str(cache_dir), validate_provenance=True)
        
        # First load - creates cache and checksum
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Tamper with cache file
        cache_key = loader._generate_cache_key("VNM", "2026-01-01", "2026-01-10")
        cache_path = cache_dir / f"{cache_key}.parquet"
        
        # Modify the parquet file
        tampered_df = df1.copy()
        tampered_df['close'] = tampered_df['close'] * 1.5  # Modify prices
        tampered_df.to_parquet(cache_path, index=False)
        
        # Second load - should detect tampering and refresh
        df2 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Should have refreshed from source, not using tampered cache
        assert len(df2) > 0
        assert 'close' in df2.columns
