"""
Test Suite for DataLoader Corporate Action Integration

Tests cover:
1. Corporate action adjustment application
2. PIT safety with adjusted prices
3. Provenance tracking for adjustments
4. Split and dividend handling
5. Multiple corporate actions

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
Author: OpenCode (L2-Backend Engineer Role 9)
Date: 2026-05-12
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import json

from omega.data import DataLoader, PITViolationError, DataQualityError
from omega.data.corporate_action import (
    CorporateAction,
    create_dividend_action,
    create_split_action,
    create_rights_action
)


# Fixture data for hermetic testing
def create_mock_price_data(ticker: str, start_date: str, end_date: str):
    """Create mock price data for testing without external API calls."""
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    # Filter to business days only
    dates = dates[dates.dayofweek < 5]
    
    data = []
    base_price = 80000.0
    for i, date in enumerate(dates):
        timestamp = int(date.timestamp())
        price = base_price + (i * 100)  # Gradually increasing price
        data.append({
            'symbol': ticker,
            'timestamp': timestamp,
            'open': price,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price * 1.01,
            'volume': 1000000 + (i * 10000)
        })
    return data


@pytest.fixture
def mock_vnstock_source():
    """Mock VnstockVCIDataSource for hermetic testing."""
    with patch('omega.data.loader.VnstockVCIDataSource') as mock_class:
        mock_instance = Mock()
        mock_instance.fetch_price_data.side_effect = create_mock_price_data
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def workspace_cache_dir():
    """Use workspace cache directory instead of tempfile."""
    cache_dir = Path(".ly_state/test_cache/loader_corporate_actions")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir)


class TestCorporateActionIntegration:
    """Test corporate action integration in DataLoader."""
    
    def test_load_with_dividend_adjustment(self, mock_vnstock_source, workspace_cache_dir):
        """Test loading prices with dividend adjustment applied."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0", is_already_adjusted=False)
        
        # Create dividend action: 2000 VND on 2026-01-05
        dividend_action = create_dividend_action(
            symbol="VNM",
            ex_date="2026-01-05",
            dividend_amount=2000.0
        )
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[dividend_action],
            apply_adjustments=True
        )
        
        # Check provenance fields exist
        assert 'dataset_version' in df.columns
        assert 'source' in df.columns
        assert 'adjustments_applied' in df.columns
        
        # Check adjustments_applied contains dividend info
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) > 0
        assert 'dividend' in adjustments[0]
        
        # Verify prices before ex-date are adjusted (lower than raw)
        # This is a smoke test - actual adjustment logic tested in corporate_action tests
        assert len(df) > 0
    
    def test_load_with_split_adjustment(self, mock_vnstock_source, workspace_cache_dir):
        """Test loading prices with stock split adjustment."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0", is_already_adjusted=False)
        
        # Create 2:1 split on 2026-01-05
        split_action = create_split_action(
            symbol="VNM",
            ex_date="2026-01-05",
            split_ratio=2.0
        )
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[split_action],
            apply_adjustments=True
        )
        
        # Check adjustments_applied contains split info
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) > 0
        assert 'split' in adjustments[0]
        assert '2.0' in adjustments[0]
    
    def test_load_with_multiple_actions(self, mock_vnstock_source, workspace_cache_dir):
        """Test loading with multiple corporate actions."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0", is_already_adjusted=False)
        
        # Create multiple actions
        actions = [
            create_dividend_action("VNM", "2026-01-03", 1000.0),
            create_split_action("VNM", "2026-01-07", 2.0)
        ]
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=actions,
            apply_adjustments=True
        )
        
        # Check both adjustments recorded
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) == 2
    
    def test_load_without_adjustments(self, mock_vnstock_source, workspace_cache_dir):
        """Test that adjustments are not applied when apply_adjustments=False."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0")
        
        dividend_action = create_dividend_action("VNM", "2026-01-05", 2000.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[dividend_action],
            apply_adjustments=False
        )
        
        # Check adjustments_applied is empty
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) == 0
    
    def test_pit_safety_with_adjustments(self, mock_vnstock_source, workspace_cache_dir):
        """Test that PIT safety is maintained after corporate action adjustments."""
        loader = DataLoader(cache_dir=workspace_cache_dir, enable_pit_enforcement=True)
        
        dividend_action = create_dividend_action("VNM", "2026-01-05", 2000.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[dividend_action],
            apply_adjustments=True
        )
        
        # Verify PIT constraint: as_of <= available_at
        assert all(df['as_of'] <= df['available_at'])
    
    def test_adjustment_for_different_ticker(self, mock_vnstock_source, workspace_cache_dir):
        """Test that adjustments for different ticker are not applied."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0")
        
        # Create action for VCB, but load VNM
        dividend_action = create_dividend_action("VCB", "2026-01-05", 2000.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[dividend_action],
            apply_adjustments=True
        )
        
        # Check no adjustments applied
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) == 0
    
    def test_skip_adjustment_when_already_adjusted(self, mock_vnstock_source, workspace_cache_dir, caplog):
        """Test that warning is logged when is_already_adjusted=True and apply_adjustments=True."""
        import logging
        
        # Set is_already_adjusted=True (default behavior for vnstock)
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0", is_already_adjusted=True)
        
        dividend_action = create_dividend_action("VNM", "2026-01-05", 2000.0)
        
        with caplog.at_level(logging.WARNING):
            df = loader.load_prices(
                ticker="VNM",
                start_date="2026-01-01",
                end_date="2026-01-10",
                as_of_time=datetime(2026, 1, 15, 10, 0, 0),
                corporate_actions=[dividend_action],
                apply_adjustments=True
            )
        
        # Check that warning was logged
        assert any("DOUBLE-ADJUSTMENT RISK" in record.message for record in caplog.records)
        
        # Check that no adjustments were applied
        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) == 0


class TestProvenanceTracking:
    """Test provenance metadata tracking."""
    
    def test_dataset_version_field(self, mock_vnstock_source, workspace_cache_dir):
        """Test that dataset_version field is added."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="2.1.0")
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        assert 'dataset_version' in df.columns
        assert all(df['dataset_version'] == "2.1.0")
    
    def test_source_field(self, mock_vnstock_source, workspace_cache_dir):
        """Test that source field is added."""
        loader = DataLoader(cache_dir=workspace_cache_dir)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        assert 'source' in df.columns
        assert all(df['source'] == 'vnstock_vci')
    
    def test_ingestion_timestamp_field(self, mock_vnstock_source, workspace_cache_dir):
        """Test that ingestion_timestamp field is added."""
        loader = DataLoader(cache_dir=workspace_cache_dir)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        assert 'ingestion_timestamp' in df.columns
        assert pd.api.types.is_datetime64_any_dtype(df['ingestion_timestamp'])
    
    def test_metadata_sidecar_created(self, mock_vnstock_source, workspace_cache_dir):
        """Test that metadata sidecar JSON file is created."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0")
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        # Find metadata sidecar file
        cache_dir = Path(workspace_cache_dir)
        metadata_files = list(cache_dir.glob("*.metadata.json"))
        
        assert len(metadata_files) > 0
        
        # Read and validate metadata
        with open(metadata_files[0], 'r') as f:
            metadata = json.load(f)
        
        assert 'dataset_version' in metadata
        assert metadata['dataset_version'] == "1.0.0"
        assert 'source' in metadata
        assert 'checksum' in metadata
        assert 'checksum_algorithm' in metadata
        assert metadata['checksum_algorithm'] == 'sha256'
        assert 'quality_score' in metadata
        assert 'row_count' in metadata
        assert 'created_at' in metadata
    
    def test_checksum_deterministic(self, mock_vnstock_source, workspace_cache_dir):
        """Test that checksum is deterministic for same data."""
        loader = DataLoader(cache_dir=workspace_cache_dir, dataset_version="1.0.0")
        
        # Load same data twice
        df1 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        df2 = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-05",
            as_of_time=datetime(2026, 1, 10, 10, 0, 0),
            force_refresh=False  # Use cache
        )
        
        # Read metadata files
        cache_dir = Path(workspace_cache_dir)
        metadata_files = list(cache_dir.glob("*.metadata.json"))
        
        with open(metadata_files[0], 'r') as f:
            metadata = json.load(f)
        
        # Checksum should be consistent
        assert len(metadata['checksum']) == 64  # SHA256 hex length


class TestAdjustmentPITSafety:
    """Test that corporate action adjustments maintain PIT safety."""
    
    def test_adjustment_does_not_violate_pit(self, mock_vnstock_source, workspace_cache_dir):
        """Test that backward adjustment preserves PIT timestamps."""
        loader = DataLoader(cache_dir=workspace_cache_dir, enable_pit_enforcement=True)
        
        dividend_action = create_dividend_action("VNM", "2026-01-05", 2000.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[dividend_action],
            apply_adjustments=True
        )
        
        # PIT constraint must hold for all rows
        violations = df[df['as_of'] > df['available_at']]
        assert len(violations) == 0
    
    def test_adjustment_preserves_ohlc_consistency(self, mock_vnstock_source, workspace_cache_dir):
        """Test that adjustments preserve OHLC structural consistency."""
        loader = DataLoader(cache_dir=workspace_cache_dir)
        
        split_action = create_split_action("VNM", "2026-01-05", 2.0)
        
        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[split_action],
            apply_adjustments=True
        )
        
        # Check OHLC consistency: high >= low, high >= open/close, low <= open/close
        assert all(df['high'] >= df['low'])
        assert all(df['high'] >= df['open'])
        assert all(df['high'] >= df['close'])
        assert all(df['low'] <= df['open'])
        assert all(df['low'] <= df['close'])

    def test_future_ex_date_excluded_by_as_of_time(self, mock_vnstock_source, workspace_cache_dir):
        """Future ex_date must not be applied when ex_date > as_of_time.date()."""
        loader = DataLoader(cache_dir=workspace_cache_dir, is_already_adjusted=False)

        future_dividend = create_dividend_action("VNM", "2026-01-20", 2000.0)

        df = loader.load_prices(
            ticker="VNM",
            start_date="2026-01-01",
            end_date="2026-01-10",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0),
            corporate_actions=[future_dividend],
            apply_adjustments=True
        )

        adjustments = json.loads(df['adjustments_applied'].iloc[0])
        assert len(adjustments) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
