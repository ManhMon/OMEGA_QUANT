"""
Contract tests for Phase 3.1 Alpha Discovery
Tests: Determinism, Join Causality, Module Contract
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from src.pipeline.alpha_discovery_pipeline import run_alpha_discovery_pipeline
from src.indicators.alpha_discovery import build_alpha_signals


@pytest.fixture
def contract_test_data() -> pd.DataFrame:
    """Generate deterministic test data for contract verification."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    np.random.seed(123)
    close_prices = 100 + np.cumsum(np.random.randn(50) * 1.5)
    return pd.DataFrame({"timestamp": dates, "close": close_prices})


def test_output_shape_contract(contract_test_data: pd.DataFrame) -> None:
    """
    Test 1: Output Shape Contract
    Verify output has expected columns and row count.
    """
    result = run_alpha_discovery_pipeline(contract_test_data)
    
    expected_columns = {
        "timestamp",
        "close",
        "alpha_rsi",
        "alpha_macd",
        "alpha_macd_signal",
        "alpha_macd_hist",
    }
    assert set(result.columns) == expected_columns, f"Unexpected columns: {set(result.columns)}"
    assert len(result) == len(contract_test_data), "Row count mismatch"


def test_determinism_contract(contract_test_data: pd.DataFrame) -> None:
    """
    Test 2: Determinism Contract
    Same input must produce identical output (byte-for-byte equality).
    """
    runs = [run_alpha_discovery_pipeline(contract_test_data) for _ in range(3)]
    
    for i in range(1, len(runs)):
        pd.testing.assert_frame_equal(runs[0], runs[i], check_exact=True)


def test_alpha_signal_ranges(contract_test_data: pd.DataFrame) -> None:
    """
    Test 3: Alpha Signal Range Contract
    Verify RSI is in [0, 100], MACD values are finite.
    """
    result = run_alpha_discovery_pipeline(contract_test_data)
    
    # RSI should be in [0, 100] range (after valid window)
    rsi_valid = result["alpha_rsi"].dropna()
    if len(rsi_valid) > 0:
        assert rsi_valid.min() >= 0, "RSI should be >= 0"
        assert rsi_valid.max() <= 100, "RSI should be <= 100"
    
    # MACD values should be finite
    assert np.isfinite(result["alpha_macd"].dropna()).all(), "MACD should be finite"
    assert np.isfinite(result["alpha_macd_signal"].dropna()).all(), "MACD signal should be finite"
    assert np.isfinite(result["alpha_macd_hist"].dropna()).all(), "MACD histogram should be finite"


def test_timestamp_preservation(contract_test_data: pd.DataFrame) -> None:
    """
    Test 4: Timestamp Preservation Contract
    Output timestamps must match input timestamps exactly.
    """
    result = run_alpha_discovery_pipeline(contract_test_data)
    
    pd.testing.assert_series_equal(
        result["timestamp"],
        contract_test_data["timestamp"],
        check_names=False,
        check_exact=True,
    )


def test_feature_causality(contract_test_data: pd.DataFrame) -> None:
    """
    Test 5: Feature Causality Contract
    Features at time t must be computable from data up to t-1.
    """
    result = run_alpha_discovery_pipeline(contract_test_data)
    
    # After T-1 shift, first row features should be NaN
    assert pd.isna(result.loc[0, "alpha_rsi"]), "First row RSI must be NaN (no prior data)"
    assert pd.isna(result.loc[0, "alpha_macd"]), "First row MACD must be NaN (no prior data)"
    
    # Features at t=20 (after window 14 + shift + diff) should be computable from t=19 and earlier
    assert not pd.isna(result.loc[20, "alpha_rsi"]), "RSI at t=20 should be computable from t<=19"
    assert not pd.isna(result.loc[20, "alpha_macd"]), "MACD at t=20 should be computable from t<=19"


def test_missing_column_error(contract_test_data: pd.DataFrame) -> None:
    """
    Test 6: Missing Column Error Contract
    Pipeline must raise ValueError for missing required columns.
    """
    bad_data = contract_test_data.drop(columns=["close"])
    
    with pytest.raises(ValueError, match="Missing required columns"):
        run_alpha_discovery_pipeline(bad_data)


def test_empty_input_handling() -> None:
    """
    Test 7: Empty Input Handling Contract
    Empty DataFrame should be handled gracefully.
    """
    empty_df = pd.DataFrame(columns=["timestamp", "close"])
    
    # Should return empty result with correct schema
    result = run_alpha_discovery_pipeline(empty_df)
    
    expected_columns = {
        "timestamp",
        "close",
        "alpha_rsi",
        "alpha_macd",
        "alpha_macd_signal",
        "alpha_macd_hist",
    }
    assert set(result.columns) == expected_columns
    assert len(result) == 0


def test_build_alpha_signals_contract(contract_test_data: pd.DataFrame) -> None:
    """
    Test 8: build_alpha_signals Module Contract
    Verify intermediate function produces expected columns.
    """
    result = build_alpha_signals(contract_test_data)
    
    expected_columns = {
        "timestamp",
        "close",
        "alpha_rsi",
        "alpha_macd",
        "alpha_macd_signal",
        "alpha_macd_hist",
    }
    assert set(result.columns) == expected_columns
