"""16-Dimension resilience and unit tests for direct macro and rates client."""

from datetime import timezone

import pandas as pd
import pytest

from omega.data.calendar import get_statutory_available_at
from omega.data.macro_rates import (
    DirectMacroClient,
    parse_hnx_yield_curve,
    parse_rates,
    parse_sbv_interbank_rates,
    parse_sbv_omo_operations,
    parse_usd_vnd_rates,
    statutory_available_at,
    canonical_tenor,
)


def test_circular96_q4_and_annual_pit_deadlines():
    assert statutory_available_at("2023-Q4").date().isoformat() == "2024-01-30"
    assert statutory_available_at("2023", is_audited=True).date().isoformat() == "2024-03-31"
    assert statutory_available_at("2024-Q2", is_audited=True).date().isoformat() == "2024-08-29"
    assert get_statutory_available_at("2023-Q4").isoformat() == "2024-01-30T15:30:00+07:00"


def test_rates_reject_malformed_or_out_of_bounds_rows():
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01", "rate": float("nan")}])
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01"}])


def test_rates_are_utc_independent_and_deterministic():
    rows = [{"date": "2024-01-01T00:00:00+07:00", "rate": 4.5}]
    assert DirectMacroClient().parse(rows) == [{"date": "2023-12-31", "rate": 4.5}]
    assert statutory_available_at("2023-Q4").tzinfo == timezone.utc


def test_direct_sbv_parser_normalizes_aliases_and_provider():
    rows = [{"ngay": "2024-01-02T00:00:00+00:00", "ky_han": "ON", "lai_suat": "4.25"}]
    assert parse_sbv_interbank_rates(rows)[0] == {
        "date": "2024-01-02", "tenor": "overnight", "rate": 4.25,
        "available_at": "2024-01-02T09:00:00+00:00", "provider": "SBV",
    }


def test_direct_hnx_parser_normalizes_aliases_and_provider():
    rows = [{"date": "2024-01-02T00:00:00+00:00", "ky_han": "10Y", "loi_suat": 2.45}]
    assert parse_hnx_yield_curve(rows)[0]["maturity"] == "10Y"
    assert parse_hnx_yield_curve(rows)[0]["provider"] == "HNX"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 101, [], "bad"])
def test_direct_parsers_reject_malformed_rates(value):
    with pytest.raises((TypeError, ValueError)):
        parse_sbv_interbank_rates([{"date": "2024-01-01", "rate": value}])


def test_direct_parsers_fail_closed_on_pit_lookahead():
    with pytest.raises(ValueError, match="as_of exceeds available_at"):
        parse_sbv_interbank_rates([{
            "date": "2024-01-01", "rate": 4,
            "as_of": "2024-01-02T00:00:00Z",
            "available_at": "2024-01-01T09:00:00Z",
        }])


def test_direct_parsers_preserve_bitemporal_revision_fields():
    result = parse_sbv_interbank_rates([{
        "date": "2024-01-01T00:00:00Z", "rate": 4,
        "as_of": "2024-01-02T08:00:00Z",
        "available_at": "2024-01-02T09:00:00Z",
        "vintage_at": "2024-01-02T08:30:00Z",
        "revision_at": "2024-01-03T09:00:00+00:00",
    }])[0]
    assert result["vintage_at"] == "2024-01-02T08:30:00+00:00"
    assert result["revision_at"] == "2024-01-03T09:00:00+00:00"


def test_direct_parsers_reject_naive_temporal_metadata():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_sbv_interbank_rates([{
            "date": "2024-01-01T00:00:00Z", "rate": 4,
            "available_at": "2024-01-01T09:00:00",
        }])


@pytest.mark.parametrize("period", ["", "2024-Q0", "2024-Q5", "2024-Q", "not-a-period"])
def test_circular96_rejects_invalid_periods(period):
    with pytest.raises(ValueError):
        get_statutory_available_at(period)


def test_circular96_rejects_invalid_types_and_audited_combinations():
    with pytest.raises(TypeError):
        get_statutory_available_at(2024)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        get_statutory_available_at("2024-Q1", is_audited=True)


def test_client_exposes_both_direct_parsers():
    client = DirectMacroClient()
    assert client.parse_sbv_interbank([{"date": "2024-01-01", "rate": 4}])[0]["provider"] == "SBV"
    assert client.parse_hnx_yield_curve([{"date": "2024-01-01", "maturity": "5Y", "yield": 2}])[0]["provider"] == "HNX"


def test_tenor_aliases_are_canonical():
    assert canonical_tenor("ON") == "overnight"
    assert canonical_tenor("1Y") == "12m"


def test_macro_features_allow_default_none_rows():
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02"]), "symbol": ["AAA"]}
    ).set_index(["date", "symbol"])
    output = AlternativeDataFetcher().get_macro_bitemporal_features(panel)
    assert output.shape == (1, 8)
    assert output.isna().all().all()


def test_macro_features_choose_revision_deterministically():
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02"]), "symbol": ["AAA"]}
    ).set_index(["date", "symbol"])
    rows = [
        {"tenor": "overnight", "rate": 4.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "B"},
        {"tenor": "overnight", "rate": 3.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "A"},
        {"tenor": "refinancing_rate", "rate": 1.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "A"},
    ]
    output = AlternativeDataFetcher().get_macro_bitemporal_features(panel, rows)
    assert output.loc[pd.Timestamp("2024-01-02"), "interbank_on_spread"] == 3.0
