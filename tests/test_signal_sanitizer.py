from __future__ import annotations

import pandas as pd
import pytest

from src.features.signal_module import generate_signals
from src.features.signal_sanitizer import (
    SIGNAL_COLUMNS,
    enforce_t_minus_1_lag,
    sanitize_signals,
    validate_monotonic_time,
    validate_t_minus_1_lag,
)


@pytest.fixture
def raw_signal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D"),
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "signal_mean_reversion": [0.1, -0.2, 0.0, 0.3, -0.1],
            "signal_momentum": [0.05, 0.06, 0.02, 0.01, -0.02],
            "signal_trend": [0.0, 0.03, 0.04, 0.05, 0.06],
        }
    )


def test_validate_monotonic_time_accepts_sorted_frame(raw_signal_frame: pd.DataFrame) -> None:
    validate_monotonic_time(raw_signal_frame)


def test_validate_monotonic_time_rejects_unsorted_frame(raw_signal_frame: pd.DataFrame) -> None:
    bad = raw_signal_frame.iloc[[1, 0, 2, 3, 4]].reset_index(drop=True)
    with pytest.raises(ValueError, match="not strictly monotonic"):
        validate_monotonic_time(bad)


def test_validate_monotonic_time_rejects_duplicate_timestamps(raw_signal_frame: pd.DataFrame) -> None:
    bad = raw_signal_frame.copy()
    bad.loc[2, "timestamp"] = bad.loc[1, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate_monotonic_time(bad)


def test_enforce_t_minus_1_lag_shifts_signal_columns(raw_signal_frame: pd.DataFrame) -> None:
    result = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    assert pd.isna(result.loc[0, "signal_mean_reversion"])
    assert result.loc[1, "signal_momentum"] == raw_signal_frame.loc[0, "signal_momentum"]


def test_validate_t_minus_1_lag_rejects_unlagged_signals(raw_signal_frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="must be T-1 lagged"):
        validate_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)


def test_validate_t_minus_1_lag_checks_every_row_against_source(raw_signal_frame: pd.DataFrame) -> None:
    lagged = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    lagged.loc[3, "signal_trend"] = raw_signal_frame.loc[3, "signal_trend"]
    with pytest.raises(ValueError, match="does not match exact T-1 source value"):
        validate_t_minus_1_lag(lagged, SIGNAL_COLUMNS, source_df=raw_signal_frame)


def test_validate_t_minus_1_lag_rejects_unsorted_source_frame(raw_signal_frame: pd.DataFrame) -> None:
    lagged = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    bad_source = raw_signal_frame.iloc[[1, 0, 2, 3, 4]].reset_index(drop=True)

    with pytest.raises(ValueError, match="not strictly monotonic"):
        validate_t_minus_1_lag(lagged, SIGNAL_COLUMNS, source_df=bad_source)


def test_sanitize_signals_applies_lag_and_returns_safe_frame(raw_signal_frame: pd.DataFrame) -> None:
    result = sanitize_signals(raw_signal_frame, apply_lag=True)
    assert pd.isna(result.loc[0, "signal_mean_reversion"])
    assert result.loc[2, "signal_trend"] == raw_signal_frame.loc[1, "signal_trend"]


def test_sanitize_signals_rejects_future_leakage_after_partial_shift(raw_signal_frame: pd.DataFrame) -> None:
    leaked = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    leaked.loc[4, "signal_momentum"] = raw_signal_frame.loc[4, "signal_momentum"]
    with pytest.raises(ValueError, match="does not match exact T-1 source value"):
        validate_t_minus_1_lag(leaked, SIGNAL_COLUMNS, source_df=raw_signal_frame)


def test_generate_then_sanitize_enforces_single_timing_contract() -> None:
    price_frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=8, freq="D"),
            "close": [100.0, 102.0, 101.0, 103.0, 107.0, 106.0, 108.0, 110.0],
        }
    )
    raw = generate_signals(
        price_frame,
        mean_reversion_window=3,
        momentum_window=2,
        trend_short_window=2,
        trend_long_window=4,
    )

    assert raw.loc[2, "signal_momentum"] == pytest.approx(price_frame.loc[2, "close"] / price_frame.loc[0, "close"] - 1.0)

    safe = sanitize_signals(raw, apply_lag=True)
    for column in SIGNAL_COLUMNS:
        expected = raw[column].shift(1)
        pd.testing.assert_series_equal(safe[column], expected, check_names=False)


def test_generate_then_sanitize_rejects_same_bar_signal_frame_without_lag() -> None:
    price_frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=8, freq="D"),
            "close": [100.0, 102.0, 101.0, 103.0, 107.0, 106.0, 108.0, 110.0],
        }
    )
    raw = generate_signals(
        price_frame,
        mean_reversion_window=3,
        momentum_window=2,
        trend_short_window=2,
        trend_long_window=4,
    )

    with pytest.raises(ValueError, match="unsafe without source_df"):
        sanitize_signals(raw, apply_lag=False)


def test_sanitize_signals_accepts_pre_lagged_frame_with_source_proof(raw_signal_frame: pd.DataFrame) -> None:
    pre_lagged = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)

    result = sanitize_signals(pre_lagged, apply_lag=False, source_df=raw_signal_frame)

    pd.testing.assert_frame_equal(result, pre_lagged)


def test_sanitize_signals_rejects_partial_later_row_leak_in_pre_lagged_frame(raw_signal_frame: pd.DataFrame) -> None:
    pre_lagged = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    pre_lagged.loc[4, "signal_trend"] = raw_signal_frame.loc[4, "signal_trend"]

    with pytest.raises(ValueError, match="does not match exact T-1 source value"):
        sanitize_signals(pre_lagged, apply_lag=False, source_df=raw_signal_frame)


def test_sanitize_signals_rejects_mismatched_timestamps_in_pre_lagged_frame(raw_signal_frame: pd.DataFrame) -> None:
    pre_lagged = enforce_t_minus_1_lag(raw_signal_frame, SIGNAL_COLUMNS)
    pre_lagged.loc[3, "timestamp"] = pre_lagged.loc[3, "timestamp"] + pd.Timedelta(hours=12)

    with pytest.raises(ValueError, match="timestamp at row 3 does not match source frame exactly"):
        sanitize_signals(pre_lagged, apply_lag=False, source_df=raw_signal_frame)
