"""16-Dimension resilience and unit tests for direct macro and rates client."""

from datetime import timezone

import pytest

from omega.data.macro_rates import DirectMacroClient, parse_rates, statutory_available_at


def test_circular96_q4_and_annual_pit_deadlines():
    assert statutory_available_at("2023-Q4").date().isoformat() == "2024-01-30"
    assert statutory_available_at("2023", is_audited=True).date().isoformat() == "2024-03-31"
    assert statutory_available_at("2024-Q2", is_audited=True).date().isoformat() == "2024-08-29"


def test_rates_reject_malformed_or_out_of_bounds_rows():
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01", "rate": float("nan")}])
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01"}])


def test_rates_are_utc_independent_and_deterministic():
    rows = [{"date": "2024-01-01T00:00:00+07:00", "rate": 4.5}]
    assert DirectMacroClient().parse(rows) == [{"date": "2023-12-31", "rate": 4.5}]
    assert statutory_available_at("2023-Q4").tzinfo == timezone.utc
