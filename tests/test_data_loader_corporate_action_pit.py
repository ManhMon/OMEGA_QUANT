from datetime import datetime

import pandas as pd

from omega.data.corporate_action import create_dividend_action
from omega.data.loader import DataLoader


def test_apply_corporate_actions_skips_future_ex_date_boundary() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)

    df = pd.DataFrame(
        {
            "ticker": ["VNM", "VNM"],
            "date": pd.to_datetime(["2026-05-30", "2026-06-01"]),
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 102.0],
            "volume": [1000, 1100],
            "as_of": pd.to_datetime(["2026-06-01T10:00:00", "2026-06-01T10:00:00"]),
            "available_at": pd.to_datetime(["2026-05-30T15:00:00", "2026-06-01T15:00:00"]),
        }
    )
    original_df = df.copy(deep=True)

    future_dividend = create_dividend_action(
        symbol="VNM",
        ex_date="2026-06-02",
        dividend_amount=10.0,
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=df,
        ticker="VNM",
        corporate_actions=[future_dividend],
        as_of_time=datetime(2026, 6, 1, 10, 0, 0),
    )

    pd.testing.assert_frame_equal(adjusted_df, original_df)
    assert adjustments == []


def test_apply_corporate_actions_keeps_same_day_ex_date_boundary() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)

    df = pd.DataFrame(
        {
            "ticker": ["VNM", "VNM"],
            "date": pd.to_datetime(["2026-05-30", "2026-06-01"]),
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 102.0],
            "volume": [1000, 1100],
            "as_of": pd.to_datetime(["2026-06-01T10:00:00", "2026-06-01T10:00:00"]),
            "available_at": pd.to_datetime(["2026-05-30T15:00:00", "2026-06-01T15:00:00"]),
        }
    )

    same_day_dividend = create_dividend_action(
        symbol="VNM",
        ex_date="2026-06-01",
        dividend_amount=10.0,
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=df,
        ticker="VNM",
        corporate_actions=[same_day_dividend],
        as_of_time=datetime(2026, 6, 1, 10, 0, 0),
    )

    assert adjustments == ["dividend:2026-06-01:10.0"]
    assert adjusted_df.loc[0, "close"] == 90.0
    assert adjusted_df.loc[1, "close"] == 102.0
    assert adjusted_df.loc[0, "as_of"] == pd.Timestamp("2026-06-01T10:00:00")
    assert adjusted_df.loc[1, "as_of"] == pd.Timestamp("2026-06-01T10:00:00")
