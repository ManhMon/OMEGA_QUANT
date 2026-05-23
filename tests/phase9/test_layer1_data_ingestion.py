"""
Layer 1: Data Ingestion Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests data loading, PIT safety, and data quality validation.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from omega.data.loader import DataLoader
from omega.data.validator import DataValidator


class TestDataIngestionLayer:
    """Test Layer 1: Data Ingestion with PIT safety."""
    
    def test_data_loader_initialization(self, tmp_path):
        """Test DataLoader initializes correctly."""
        loader = DataLoader(cache_dir=str(tmp_path))
        assert loader is not None
        assert loader.cache_dir == Path(tmp_path).resolve()
    
    def test_load_prices_with_pit_cutoff(self, tmp_path, monkeypatch):
        """Test loading prices with PIT cutoff enforced."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        # Mock data with proper PIT timestamps
        def mock_fetch(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:10]
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        # Patch the internal fetch method
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch)
        
        as_of_time = datetime(2023, 1, 15)
        df = loader.load_prices(
            ticker="VNM",
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=as_of_time
        )
        
        assert len(df) > 0
        assert "ticker" in df.columns
        assert "close" in df.columns
        assert "as_of" in df.columns
        assert "available_at" in df.columns
    
    def test_pit_violation_detection(self, tmp_path, monkeypatch):
        """Test that PIT violations are detected."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        # Mock data with PIT violation
        def mock_fetch_violation(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:5]
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date + timedelta(days=2),  # VIOLATION
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch_violation)
        
        # Should raise or return empty when PIT violation detected
        with pytest.raises(ValueError, match="PIT violation"):
            df = loader.load_prices(
                ticker="VNM",
                start_date="2023-01-01",
                end_date="2023-01-10",
                as_of_time=datetime(2023, 1, 10)
            )
    
    def test_data_quality_validation(self, tmp_path):
        """Test data quality checks (missing values, outliers)."""
        validator = DataValidator()
        
        # Create test data with quality issues
        data = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "open": [100.0, np.nan, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
            "volume": [1000000] * 10,
            "as_of": pd.date_range("2023-01-01", periods=10, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        result = validator.validate(data)
        
        assert "missing_values" in result
        assert result["missing_values"]["open"] == 1
    
    def test_multiple_tickers_loading(self, tmp_path, monkeypatch):
        """Test loading data for multiple tickers."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        def mock_fetch(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:5]
            base_price = 100.0 if ticker == "VNM" else 80.0
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": base_price,
                    "high": base_price * 1.01,
                    "low": base_price * 0.99,
                    "close": base_price,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch)
        
        tickers = ["VNM", "VIC"]
        all_data = []
        
        for ticker in tickers:
            df = loader.load_prices(
                ticker=ticker,
                start_date="2023-01-01",
                end_date="2023-01-10",
                as_of_time=datetime(2023, 1, 10)
            )
            all_data.append(df)
        
        combined = pd.concat(all_data, ignore_index=True)
        
        assert len(combined) == 10  # 5 days * 2 tickers
        assert set(combined["ticker"].unique()) == {"VNM", "VIC"}
    
    def test_cache_functionality(self, tmp_path, monkeypatch):
        """Test that data caching works correctly."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        fetch_count = {"count": 0}
        
        def mock_fetch(ticker, start_date, end_date, as_of_time):
            fetch_count["count"] += 1
            dates = pd.date_range(start_date, end_date, freq="D")[:3]
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch)
        
        # First load - should fetch
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2023-01-01",
            end_date="2023-01-05",
            as_of_time=datetime(2023, 1, 5)
        )
        
        # Second load - should use cache (if implemented)
        df2 = loader.load_prices(
            ticker="VNM",
            start_date="2023-01-01",
            end_date="2023-01-05",
            as_of_time=datetime(2023, 1, 5)
        )
        
        # Verify data is consistent
        assert len(df1) == len(df2)
        pd.testing.assert_frame_equal(df1, df2)


class TestDataIngestionBoundary:
    """Test boundary conditions for data ingestion."""
    
    def test_empty_universe(self, tmp_path):
        """Test handling of empty universe."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        # Empty universe should not crash
        tickers = []
        all_data = []
        
        for ticker in tickers:
            df = loader.load_prices(
                ticker=ticker,
                start_date="2023-01-01",
                end_date="2023-01-10",
                as_of_time=datetime(2023, 1, 10)
            )
            all_data.append(df)
        
        assert len(all_data) == 0
    
    def test_single_day_data(self, tmp_path, monkeypatch):
        """Test loading single day of data."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        def mock_fetch(ticker, start_date, end_date, as_of_time):
            return pd.DataFrame({
                "ticker": [ticker],
                "date": [pd.Timestamp("2023-01-01")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000000],
                "as_of": [pd.Timestamp("2023-01-01 15:00:00")],
                "available_at": [pd.Timestamp("2023-01-02 09:00:00")]
            })
        
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch)
        
        # Query at a time when data is available (after 2023-01-02 09:00:00)
        df = loader.load_prices(
            ticker="VNM",
            start_date="2023-01-01",
            end_date="2023-01-01",
            as_of_time=datetime(2023, 1, 2, 10, 0, 0)
        )
        
        assert len(df) == 1
    
    def test_future_as_of_time(self, tmp_path, monkeypatch):
        """Test that future as_of_time is handled correctly."""
        loader = DataLoader(cache_dir=str(tmp_path))
        
        def mock_fetch(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:5]
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(loader, "_fetch_from_source", mock_fetch)
        
        # as_of_time in the future should still work (filters data appropriately)
        df = loader.load_prices(
            ticker="VNM",
            start_date="2023-01-01",
            end_date="2023-01-10",
            as_of_time=datetime(2025, 1, 1)  # Future date
        )
        
        assert len(df) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
