from datetime import datetime
from unittest.mock import Mock

import pandas as pd
import requests

from omega.data.macro_client import FreeMacroClient


def _response(payload):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = payload
    return response


def test_fetch_world_bank_series_parses_non_null_rows():
    session = Mock()
    session.get.return_value = _response(
        [
            {"page": 1},
            [
                {"date": "2024", "value": 429000000000.0},
                {"date": "2023", "value": None},
                {"date": "2022", "value": 408000000000.0},
            ],
        ]
    )
    client = FreeMacroClient(session=session)

    frame = client.fetch_gdp()

    assert frame.to_dict("records") == [
        {"date": datetime(2022, 12, 31), "gdp": 408000000000.0},
        {"date": datetime(2024, 12, 31), "gdp": 429000000000.0},
    ]


def test_fetch_yahoo_series_parses_chart_closes():
    session = Mock()
    session.get.return_value = _response(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1718841600, 1718928000],
                        "indicators": {"quote": [{"close": [23500.5, None]}]},
                    }
                ]
            }
        }
    )
    client = FreeMacroClient(session=session)

    frame = client.fetch_usd_vnd(period="1mo", interval="1d")

    assert frame.to_dict("records") == [
        {"date": datetime(2024, 6, 20, 0, 0), "usd_vnd": 23500.5},
    ]


def test_fetch_all_merges_all_series_on_date():
    session = Mock()
    session.get.side_effect = [
        _response([{"page": 1}, [{"date": "2024", "value": 1.0}]]),
        _response([{"page": 1}, [{"date": "2024", "value": 2.0}]]),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [3.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [4.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [5.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [6.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [7.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [8.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [9.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [10.0]}]}}]}}),
        _response({"chart": {"result": [{"timestamp": [1718841600], "indicators": {"quote": [{"close": [11.0]}]}}]}}),
    ]
    client = FreeMacroClient(session=session)

    frame = client.fetch_all(period="1mo", interval="1d")

    assert list(frame.columns) == ["date", "gdp", "cpi", "gold", "crude_oil", "usd_vnd", "spy", "vix", "dxy", "copper", "acwi", "eem"]
    june_row = frame[frame["date"] == datetime(2024, 6, 20, 0, 0)].iloc[0]
    year_row = frame[frame["date"] == datetime(2024, 12, 31, 0, 0)].iloc[0]

    assert pd.isna(june_row["gdp"])
    assert pd.isna(june_row["cpi"])
    assert june_row["gold"] == 3.0
    assert june_row["crude_oil"] == 4.0
    assert june_row["usd_vnd"] == 5.0
    assert year_row["gdp"] == 1.0
    assert year_row["cpi"] == 2.0


def test_init_sets_default_user_agent_header():
    session = requests.Session()

    FreeMacroClient(session=session)

    assert session.headers["User-Agent"]


def test_fetch_symbol_unknown_returns_empty_frame():
    client = FreeMacroClient(session=Mock())
    frame = client.fetch_symbol("unknown")
    assert frame.empty
