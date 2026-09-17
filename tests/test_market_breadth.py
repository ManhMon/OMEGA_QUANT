"""16-Dimension resilience and unit tests for internal market breadth calculation."""

import pandas as pd
import pytest

from omega.data.market_breadth import MarketBreadthAggregator


def test_breadth_is_deterministic_and_zero_division_safe():
    prices = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "AAA": [10, 11, 12], "BBB": [10, 10, 10]})
    result = MarketBreadthAggregator().calculate(prices)
    assert result.iloc[-1].advance == 1
    assert result.iloc[-1].decline == 0
    assert result.iloc[-1].ad_ratio == 1
    assert result.iloc[-1].above_ma20 == 0.5


def test_breadth_rejects_schema_drift_and_handles_empty_input():
    with pytest.raises(ValueError):
        MarketBreadthAggregator().calculate(pd.DataFrame({"AAA": [1]}))
    assert MarketBreadthAggregator().calculate(pd.DataFrame()).empty


def test_breadth_rejects_non_numeric_duplicate_and_unsorted_dates():
    aggregator = MarketBreadthAggregator()
    with pytest.raises(ValueError, match="non-numeric"):
        aggregator.calculate(pd.DataFrame({"date": ["2024-01-01"], "AAA": ["bad"]}))
    with pytest.raises(ValueError, match="unique"):
        aggregator.calculate(pd.DataFrame({"date": ["2024-01-01", "2024-01-01"], "AAA": [1, 2]}))
    with pytest.raises(ValueError, match="unique"):
        aggregator.calculate(pd.DataFrame({"date": ["2024-01-02", "2024-01-01"], "AAA": [1, 2]}))
