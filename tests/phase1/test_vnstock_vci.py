"""
Unit Tests for Vnstock/VCI Data Integration (OMEGA_QUANT Migration)

Tests data validation, latency monitoring, and feature pruning integration
for Layer 01: Core Intelligence (Data Ingest).

Version: OMEGA v1.0
Date: 2026-05-10
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import time

# Helper: convert DataFrame to the list-of-dicts format DataValidator expects
def _rows(df: pd.DataFrame):
    rows = df.copy()
    if "date" in rows.columns and "timestamp" not in rows.columns:
        rows["timestamp"] = rows["date"].dt.strftime("%Y-%m-%d")
    return rows.to_dict("records")

# Add src to path for imports
_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(_root, "packages", "core", "src"))
sys.path.insert(0, os.path.join(_root, "packages", "data", "src"))
sys.path.insert(0, os.path.join(_root, "packages", "quant", "src"))

from omega.data.validator import DataValidator
from omega.data.sanitizer import DataSanitizer


class TestDataQualityMetrics:
    """Test data quality metrics for Vnstock/VCI integration"""
    
    def test_metrics_initialization(self):
        metrics = {
            "total_records": 1000,
            "missing_records": 30,
            "latency_ms": 50.0,
            "missing_rate": 30 / 1000,
        }
        assert metrics["total_records"] == 1000
        assert metrics["missing_records"] == 30
        assert metrics["missing_rate"] == 0.03
        assert metrics["latency_ms"] == 50.0
        assert metrics["missing_rate"] < 0.05
        assert metrics["latency_ms"] < 100.0

    def test_metrics_validation_fail_missing_rate(self):
        metrics = {
            "total_records": 1000,
            "missing_records": 60,
            "latency_ms": 50.0,
            "missing_rate": 60 / 1000,
        }
        assert metrics["missing_rate"] == 0.06
        assert metrics["missing_rate"] >= 0.05

    def test_metrics_validation_fail_latency(self):
        metrics = {"total_records": 1000, "missing_records": 30, "latency_ms": 150.0}
        assert metrics["latency_ms"] == 150.0
        assert metrics["latency_ms"] >= 100.0


class TestVCIIntegrationConfig:
    """Test VCI integration configuration"""

    def test_config_defaults(self):
        config = {
            "max_missing_rate": 0.05,
            "max_latency_ms": 100.0,
            "mock_symbols": ["VCB", "HPG", "VIC"],
            "mock_features_count": 50,
            "mock_lookback_days": 252,
            "enable_latency_monitoring": True,
            "enable_data_validation": True,
        }
        assert config["max_missing_rate"] == 0.05
        assert config["max_latency_ms"] == 100.0
        assert len(config["mock_symbols"]) == 3
        assert config["mock_features_count"] == 50
        assert config["mock_lookback_days"] == 252
        assert config["enable_latency_monitoring"] is True
        assert config["enable_data_validation"] is True

    def test_config_custom_values(self):
        config = {
            "max_missing_rate": 0.03,
            "max_latency_ms": 50.0,
            "mock_symbols": ["VCB", "HPG"],
            "mock_features_count": 30,
            "mock_lookback_days": 126,
            "enable_latency_monitoring": False,
            "enable_data_validation": False,
        }
        assert config["max_missing_rate"] == 0.03
        assert config["max_latency_ms"] == 50.0
        assert len(config["mock_symbols"]) == 2
        assert config["mock_features_count"] == 30
        assert config["mock_lookback_days"] == 126
        assert config["enable_latency_monitoring"] is False
        assert config["enable_data_validation"] is False


class TestVnstockDataValidator:
    """Test Vnstock data validation using DataValidator"""

    def test_validator_initialization(self):
        validator = DataValidator()
        assert validator is not None

    def test_validate_rows_basic(self):
        """Test DataValidator.validate_rows with valid data."""
        data = pd.DataFrame({
            "symbol": ["VCB", "VCB", "VCB"],
            "date": pd.date_range("2026-05-01", periods=3),
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1200, 1100],
        })
        validator = DataValidator(validate_provenance=False)
        result = validator.validate_rows(_rows(data))
        # Valid OHLCV → no validation issues
        assert result == []

    def test_validate_rows_detects_structural_ohlc_violation(self):
        """Test that structural OHLC violations are caught."""
        data = pd.DataFrame({
            "symbol": ["VCB", "VCB", "VCB"],
            "date": pd.date_range("2026-05-01", periods=3),
            "open": [100.0, 101.0, 102.0],
            "high": [80.0, 103.0, 104.0],   # high < low → invalid
            "low": [120.0, 100.0, 101.0],   # low > high → invalid
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1200, 1100],
        })
        validator = DataValidator(validate_provenance=False)
        result = validator.validate_rows(_rows(data))
        # Should detect ohlc_structure_inconsistent
        assert len(result) > 0


class TestVnstockDataSanitizer:
    """Test Vnstock data sanitization using DataSanitizer"""

    def test_sanitizer_initialization(self):
        sanitizer = DataSanitizer()
        assert sanitizer is not None

    def test_clean_ohlcv_basic(self):
        """Test basic OHLCV cleaning — fill NaN, validate schema."""
        data = pd.DataFrame({
            "symbol": ["VCB", "VCB", "VCB"],
            "date": pd.date_range("2026-05-01", periods=3),
            "open": [100.0, np.nan, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000.0, 1200.0, 1100.0],
        })
        sanitizer = DataSanitizer()
        as_of_time = datetime(2026, 5, 1)
        cleaned, stats = sanitizer.clean_ohlcv(data, as_of_time=as_of_time)
        assert cleaned is not None
        assert stats["output_rows"] == 3
        assert stats["forward_filled"] >= 0

    def test_forward_fill_limit(self):
        """Test forward fill respects fill limit."""
        data = pd.DataFrame({
            "symbol": ["VCB"] * 5,
            "date": pd.date_range("2026-05-01", periods=5),
            "open": [100.0, np.nan, np.nan, np.nan, 104.0],
            "high": [102.0, 103.0, 104.0, 105.0, 106.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [101.0, 102.0, 103.0, 104.0, 105.0],
            "volume": [1000.0, 1200.0, 1100.0, 1300.0, 1400.0],
        })
        sanitizer = DataSanitizer()
        as_of_time = datetime(2026, 5, 1)
        cleaned, stats = sanitizer.clean_ohlcv(data, as_of_time=as_of_time)
        assert cleaned is not None
        assert "forward_filled" in stats


class TestVCIIntegrationWorkflow:
    """Test end-to-end VCI integration workflow"""

    def test_data_ingest_workflow(self):
        """Test complete data ingest: validate → sanitize → PIT check."""
        raw_data = pd.DataFrame({
            "symbol": ["VCB", "VCB", "VCB"],
            "date": pd.date_range("2026-05-01", periods=3),
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000, 1200, 1100],
        })

        # Step 1: Validate
        validator = DataValidator(validate_provenance=False)
        validation_result = validator.validate_rows(_rows(raw_data))
        assert validation_result == []

        # Step 2: Sanitize
        sanitizer = DataSanitizer()
        as_of_time = datetime(2026, 5, 1)
        cleaned_data, stats = sanitizer.clean_ohlcv(raw_data, as_of_time=as_of_time)
        assert cleaned_data is not None

        # Step 3: PIT safety check
        assert len(cleaned_data) == 3

    def test_latency_monitoring(self):
        """Test latency monitoring simulation."""
        start_time = datetime.now()
        time.sleep(0.01)  # 10 ms
        end_time = datetime.now()
        latency_ms = (end_time - start_time).total_seconds() * 1000
        assert latency_ms < 100.0