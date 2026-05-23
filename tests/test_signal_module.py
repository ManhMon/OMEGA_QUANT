from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.signal_module import (
    generate_signals,
    mean_reversion_signal,
    momentum_signal,
    trend_signal,
)


@pytest.fixture
def price_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    close = pd.Series([100.0, 102.0, 101.0, 103.0, 107.0, 106.0, 108.0, 110.0])
    return pd.DataFrame({"timestamp": dates, "close": close})


def test_mean_reversion_uses_t_minus_1_prices(price_frame: pd.DataFrame) -> None:
    result = mean_reversion_signal(price_frame["close"], window=3)
    prices = price_frame["close"]
    expected = -((prices - prices.rolling(3).mean()) / prices.rolling(3).std()).fillna(0.0)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_momentum_uses_same_bar_rate_of_change(price_frame: pd.DataFrame) -> None:
    result = momentum_signal(price_frame["close"], window=2)
    expected = price_frame["close"].pct_change(periods=2).fillna(0.0)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_trend_uses_same_bar_moving_average_spread(price_frame: pd.DataFrame) -> None:
    result = trend_signal(price_frame["close"], short_window=2, long_window=4)
    expected = (
        (price_frame["close"].rolling(2).mean() - price_frame["close"].rolling(4).mean())
        / price_frame["close"].rolling(4).mean().abs()
    ).fillna(0.0)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_generate_signals_adds_expected_columns(price_frame: pd.DataFrame) -> None:
    result = generate_signals(
        price_frame,
        mean_reversion_window=3,
        momentum_window=2,
        trend_short_window=2,
        trend_long_window=4,
    )
    assert set(["signal_mean_reversion", "signal_momentum", "signal_trend"]).issubset(result.columns)
    assert len(result) == len(price_frame)


def test_generate_signals_zero_fills_warmup_periods(price_frame: pd.DataFrame) -> None:
    result = generate_signals(
        price_frame,
        mean_reversion_window=3,
        momentum_window=2,
        trend_short_window=2,
        trend_long_window=4,
    )
    assert result.loc[0, "signal_mean_reversion"] == 0.0
    assert result.loc[0, "signal_momentum"] == 0.0
    assert result.loc[0, "signal_trend"] == 0.0


def test_generate_signals_outputs_raw_same_bar_values(price_frame: pd.DataFrame) -> None:
    result = generate_signals(
        price_frame,
        mean_reversion_window=3,
        momentum_window=2,
        trend_short_window=2,
        trend_long_window=4,
    )
    assert result.loc[2, "signal_momentum"] == pytest.approx(
        price_frame.loc[2, "close"] / price_frame.loc[0, "close"] - 1.0
    )


def test_generate_signals_raises_for_missing_price_column(price_frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="Price column 'close' not found"):
        generate_signals(price_frame.drop(columns=["close"]))
