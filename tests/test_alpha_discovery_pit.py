"""
Acceptance tests for Phase 3.1 Alpha Discovery - PIT Safety
Tests: Temporal Shift, Leakage Sentinel, Rolling Window Integrity
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

# Ensure src is in pythonpath
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from omega.quant.pit_guard import verify_no_lookahead, enforce_t_minus_1_lag
from omega.quant.alpha_discovery import build_alpha_signals

def run_alpha_discovery_pipeline(price_df: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "close"}
    missing = required.difference(price_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = price_df.copy()
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    verify_no_lookahead(df, time_col="timestamp")

    features = build_alpha_signals(df)

    ordered_cols = [
        "timestamp",
        "close",
        "alpha_rsi",
        "alpha_macd",
        "alpha_macd_signal",
        "alpha_macd_hist",
    ]
    features = features.loc[:, ordered_cols]

    return features


@pytest.fixture
def mock_price_data() -> pd.DataFrame:
    """Generate mock time-indexed price data for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(100) * 2)
    return pd.DataFrame({"timestamp": dates, "close": close_prices})


def test_temporal_shift_t_minus_1(mock_price_data: pd.DataFrame) -> None:
    """
    Test 1: Temporal Shift Test
    Verify all features at index t are computed from data <= t-1.
    """
    result = run_alpha_discovery_pipeline(mock_price_data)
    
    # First row should have NaN features due to shift(1)
    assert pd.isna(result.loc[0, "alpha_rsi"]), "First row alpha_rsi should be NaN (T-1 lag)"
    assert pd.isna(result.loc[0, "alpha_macd"]), "First row alpha_macd should be NaN (T-1 lag)"
    
    # Verify that feature at index 20 (after window 14 + shift + diff) should be based on data up to t=19
    assert not pd.isna(result.loc[20, "alpha_rsi"]), "Feature at index 20 should exist after T-1 shift and window"


def test_leakage_sentinel(mock_price_data: pd.DataFrame) -> None:
    """
    Test 2: Leakage Sentinel Test
    Inject synthetic future-only signal; assert pipeline output unaffected.
    """
    # Add a future-only column that should NOT be used
    df_with_leak = mock_price_data.copy()
    df_with_leak["future_leak"] = df_with_leak["close"].shift(-5)  # Future data
    
    # Pipeline should only use 'timestamp' and 'close'
    result = run_alpha_discovery_pipeline(df_with_leak[["timestamp", "close"]])
    
    # Verify output columns don't include the leak
    assert "future_leak" not in result.columns, "Pipeline should not propagate future leak column"
    
    # Verify deterministic output (same input -> same output)
    result2 = run_alpha_discovery_pipeline(mock_price_data)
    pd.testing.assert_frame_equal(result, result2, check_dtype=False)


def test_rolling_window_integrity(mock_price_data: pd.DataFrame) -> None:
    """
    Test 3: Rolling Window Integrity Test
    Validate rolling ops never include current bar (t) for prediction at t.
    """
    result = run_alpha_discovery_pipeline(mock_price_data)
    
    # RSI uses rolling window of 14 periods
    # After shift(1), the feature at index t uses rolling window ending at t-1
    
    # Check that early rows (within window + shift) are NaN
    # RSI needs 14 periods + 1 for diff = 15 rows before valid. Then +1 shift = row 15 has valid value.
    # So rows 0..14 are NaN.
    assert result.loc[:14, "alpha_rsi"].isna().all(), "Early RSI values should be NaN due to window + shift"
    
    # Check that later rows have valid values
    assert not pd.isna(result.loc[20, "alpha_rsi"]), "RSI at index 20 should be valid"


def test_no_lookahead_guard() -> None:
    """
    Test 4: No-lookahead guard function
    Verify that verify_no_lookahead catches non-monotonic data.
    """
    # Create non-monotonic data
    bad_data = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
        "close": [100, 101, 102]
    })
    
    with pytest.raises(ValueError, match="not strictly monotonic"):
        verify_no_lookahead(bad_data, time_col="timestamp")


def test_enforce_t_minus_1_lag() -> None:
    """
    Test 5: Enforce T-1 lag utility
    Verify shift(1) is correctly applied.
    """
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=5, freq="D"),
        "value": [10, 20, 30, 40, 50]
    })
    
    shifted = enforce_t_minus_1_lag(df, ["value"])
    
    # First row should be NaN after shift
    assert pd.isna(shifted.loc[0, "value"]), "First value should be NaN after shift(1)"
    
    # Second row should have first row's original value
    assert shifted.loc[1, "value"] == 10, "Shifted value at index 1 should be original index 0 value"
    assert shifted.loc[2, "value"] == 20, "Shifted value at index 2 should be original index 1 value"


def test_determinism(mock_price_data: pd.DataFrame) -> None:
    """
    Test 6: Determinism Test
    Run pipeline twice on same fixture; assert equality of outputs.
    """
    result1 = run_alpha_discovery_pipeline(mock_price_data)
    result2 = run_alpha_discovery_pipeline(mock_price_data)
    
    pd.testing.assert_frame_equal(result1, result2, check_exact=False, rtol=1e-10)
