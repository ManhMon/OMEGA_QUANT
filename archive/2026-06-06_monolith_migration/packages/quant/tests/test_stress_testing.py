import pytest
from datetime import datetime, timezone

from omega.quant.stress_testing import (
    ScenarioStressTester,
    StressScenario,
)


def test_stress_scenarios_pass_and_fail_thresholds():
    tester = ScenarioStressTester(price_scale=1000.0, max_loss_threshold_pct=0.10)

    positions = {"VNM": 1000, "HPG": 2000}
    prices = {"VNM": 80.0, "HPG": 30.0}
    volatilities = {"VNM": 0.02, "HPG": 0.03}

    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 30, 0, tzinfo=timezone.utc)

    scenarios = [
        StressScenario(name="mild_drop", price_shock_pct=-0.03, vol_multiplier=1.2, liquidity_haircut_pct=0.002),
        StressScenario(name="deep_crash", price_shock_pct=-0.15, vol_multiplier=2.0, liquidity_haircut_pct=0.01),
    ]

    res = tester.run_scenarios(
        positions=positions,
        prices=prices,
        volatilities=volatilities,
        scenarios=scenarios,
        portfolio_equity=100_000_000.0,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )

    assert "mild_drop" in res
    assert "deep_crash" in res
    assert res["mild_drop"].stressed_loss_pct <= res["deep_crash"].stressed_loss_pct
    assert res["mild_drop"].stressed_var95 < res["deep_crash"].stressed_var95
    assert res["mild_drop"].pass_limits is True
    assert res["deep_crash"].pass_limits is False


def test_stress_testing_pit_violation_same_day_as_of():
    tester = ScenarioStressTester()

    positions = {"VNM": 1000}
    prices = {"VNM": 80.0}
    volatilities = {"VNM": 0.02}
    scenarios = [StressScenario(name="test", price_shock_pct=-0.01)]

    # as_of same day as timestamp => PIT violation
    as_of = datetime(2026, 5, 19, 8, 0, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 30, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="PIT violation"):
        tester.run_scenarios(
            positions=positions,
            prices=prices,
            volatilities=volatilities,
            scenarios=scenarios,
            portfolio_equity=2_000_000_000.0,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )


def test_stress_zero_position_returns_safe_defaults():
    tester = ScenarioStressTester()

    positions = {"VNM": 0}
    prices = {"VNM": 80.0}
    volatilities = {"VNM": 0.02}
    scenarios = [StressScenario(name="flat", price_shock_pct=-0.20, vol_multiplier=3.0, liquidity_haircut_pct=0.1)]

    as_of = datetime(2026, 5, 18, 8, 0, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 5, 18, 9, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

    res = tester.run_scenarios(
        positions=positions,
        prices=prices,
        volatilities=volatilities,
        scenarios=scenarios,
        portfolio_equity=2_000_000_000.0,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )

    assert res["flat"].stressed_pnl == 0.0
    assert res["flat"].stressed_loss_pct == 0.0
    assert res["flat"].pass_limits is True
