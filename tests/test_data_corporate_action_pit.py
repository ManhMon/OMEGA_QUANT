from datetime import UTC, datetime

import pandas as pd
import pytest

from omega.data.corporate_action import CorporateAction, create_dividend_action
from omega.data.loader import DataLoader


def _base_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["VNM", "VNM"],
            "date": pd.to_datetime(["2026-05-30", "2026-06-01"]),
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 102.0],
            "volume": [1000, 1100],
            "as_of": pd.to_datetime(["2026-06-01T10:00:00Z", "2026-06-01T10:00:00Z"], utc=True),
            "available_at": pd.to_datetime(["2026-05-30T15:00:00Z", "2026-06-01T15:00:00Z"], utc=True),
        }
    )


def test_corporate_action_enforces_available_at_invariant() -> None:
    with pytest.raises(ValueError, match="available_at must equal max"):
        CorporateAction(
            symbol="VNM",
            ex_date="2026-06-01",
            action_type="dividend",
            dividend_amount=10.0,
            announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
            ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 7, 59, tzinfo=UTC),
            source="exchange_notice",
        )


def test_create_dividend_action_defaults_helper_provenance() -> None:
    action = create_dividend_action("VNM", "2026-06-01", 10.0)
    assert action.is_quarantined is False
    assert action.source == "HELPER_DEFAULT"
    assert action.announced_at == datetime(2026, 5, 25, 0, 0, tzinfo=UTC)
    assert action.ingested_at == action.announced_at
    assert action.available_at == action.announced_at


def test_apply_corporate_actions_filters_by_available_at() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = create_dividend_action(
        "VNM",
        "2026-06-01",
        10.0,
        announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        available_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        source="exchange_notice",
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 7, 59, tzinfo=UTC),
    )

    pd.testing.assert_frame_equal(adjusted_df, _base_df())
    assert adjustments == []


def test_apply_corporate_actions_quarantines_unverified_actions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = CorporateAction(symbol="VNM", ex_date="2026-06-01", action_type="dividend", dividend_amount=10.0)

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    pd.testing.assert_frame_equal(adjusted_df, _base_df())
    assert adjustments == []
    assert "Quarantined unverified corporate action" in caplog.text


def test_apply_corporate_actions_applies_verified_available_action() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = create_dividend_action(
        "VNM",
        "2026-06-01",
        10.0,
        announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        available_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        source="exchange_notice",
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert adjustments == ["dividend:2026-06-01:10.0"]
    assert adjusted_df.loc[0, "close"] == 90.0
    assert adjusted_df.loc[1, "close"] == 102.0
