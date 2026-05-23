from __future__ import annotations

import pandas as pd
import pytest

from src.risk.drawdown_monitor import (
    breach_drawdown_limit,
    drawdown_series,
    max_drawdown,
    rolling_max_drawdown,
    underwater_duration,
)


@pytest.fixture
def equity_curve() -> pd.Series:
    return pd.Series([100.0, 110.0, 105.0, 120.0, 90.0, 95.0, 130.0], dtype="float64")


def test_drawdown_series_tracks_drop_from_running_peak(equity_curve: pd.Series) -> None:
    result = drawdown_series(equity_curve)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == pytest.approx(0.0)
    assert result.iloc[5] == pytest.approx(-0.25)


def test_drawdown_series_rejects_empty() -> None:
    with pytest.raises(ValueError, match="equity_curve"):
        drawdown_series(pd.Series(dtype="float64"))


def test_max_drawdown_returns_absolute_worst_drop(equity_curve: pd.Series) -> None:
    assert max_drawdown(equity_curve) == pytest.approx(0.25)


def test_rolling_max_drawdown_applies_t_minus_1_lag(equity_curve: pd.Series) -> None:
    result = rolling_max_drawdown(equity_curve, window=3)
    assert result.iloc[3] == pytest.approx(abs((105.0 / 110.0) - 1.0), abs=1e-12)
    assert result.iloc[5] == pytest.approx(abs((90.0 / 120.0) - 1.0), abs=1e-12)


def test_max_drawdown_returns_zero_without_t_minus_1_history() -> None:
    assert max_drawdown(pd.Series([100.0], dtype="float64")) == pytest.approx(0.0)


def test_rolling_max_drawdown_rejects_bad_window(equity_curve: pd.Series) -> None:
    with pytest.raises(ValueError, match="window"):
        rolling_max_drawdown(equity_curve, window=0)


def test_underwater_duration_counts_longest_stretch(equity_curve: pd.Series) -> None:
    assert underwater_duration(equity_curve) == 2


def test_breach_drawdown_limit_flags_limit_cross(equity_curve: pd.Series) -> None:
    assert breach_drawdown_limit(equity_curve, limit=0.20) is True


def test_breach_drawdown_limit_rejects_negative_limit(equity_curve: pd.Series) -> None:
    with pytest.raises(ValueError, match="limit"):
        breach_drawdown_limit(equity_curve, limit=-0.1)
