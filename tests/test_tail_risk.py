from __future__ import annotations

import pandas as pd
import pytest

from src.risk.tail_risk import (
    cross_sectional_tail_flags,
    downside_deviation,
    expected_tail_frequency,
    tail_loss_ratio,
    tail_risk_score,
)


@pytest.fixture
def tail_returns() -> pd.Series:
    return pd.Series([0.01, -0.01, -0.04, 0.02, -0.03, 0.01, -0.05, 0.00], dtype="float64")


def test_downside_deviation_counts_only_losses(tail_returns: pd.Series) -> None:
    assert downside_deviation(tail_returns) > 0.0


def test_downside_deviation_zero_when_all_above_target() -> None:
    assert downside_deviation(pd.Series([0.01, 0.02, 0.03])) == pytest.approx(0.0)


def test_tail_loss_ratio_counts_breach_frequency(tail_returns: pd.Series) -> None:
    assert tail_loss_ratio(tail_returns, threshold=-0.03) == pytest.approx(3 / 8)


def test_expected_tail_frequency_applies_t_minus_1_lag(tail_returns: pd.Series) -> None:
    result = expected_tail_frequency(tail_returns, window=3, threshold=-0.03)
    assert result.iloc[3] == pytest.approx((tail_returns.iloc[0:3] <= -0.03).mean())


def test_expected_tail_frequency_rejects_bad_min_periods(tail_returns: pd.Series) -> None:
    with pytest.raises(ValueError, match="min_periods"):
        expected_tail_frequency(tail_returns, window=3, min_periods=4)


def test_tail_risk_score_ranks_worse_series_higher() -> None:
    mild = pd.Series([0.01, 0.00, -0.01, 0.01, 0.00])
    severe = pd.Series([0.01, -0.10, -0.08, 0.00, -0.05])
    assert tail_risk_score(severe) > tail_risk_score(mild)


def test_cross_sectional_tail_flags_uses_latest_lagged_row() -> None:
    frame = pd.DataFrame({"A": [0.01, -0.04, 0.00], "B": [0.01, -0.01, 0.00]})
    result = cross_sectional_tail_flags(frame, threshold=-0.03)
    assert result.to_dict() == {"A": True, "B": False}


def test_cross_sectional_tail_flags_rejects_empty_frame() -> None:
    with pytest.raises(ValueError, match="asset_returns"):
        cross_sectional_tail_flags(pd.DataFrame())


def test_cross_sectional_tail_flags_rejects_missing_t_minus_1_history() -> None:
    frame = pd.DataFrame({"A": [-0.04], "B": [-0.01]})
    with pytest.raises(ValueError, match="T-1 history"):
        cross_sectional_tail_flags(frame)
