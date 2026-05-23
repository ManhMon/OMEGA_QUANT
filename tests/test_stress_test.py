from __future__ import annotations

import pandas as pd
import pytest

from src.risk.stress_test import (
    apply_stress_scenario,
    factor_stress_matrix,
    historical_stress_pnl,
    scenario_pnl,
    worst_historical_stress,
)


def test_apply_stress_scenario_multiplies_exposure_by_shock() -> None:
    result = apply_stress_scenario({"A": 100.0, "B": 50.0}, {"A": -0.1, "B": -0.2})
    assert result.to_dict() == {"A": -10.0, "B": -10.0}


def test_apply_stress_scenario_fills_missing_shocks_with_zero() -> None:
    result = apply_stress_scenario({"A": 100.0, "B": 50.0}, {"A": -0.1})
    assert result.to_dict() == {"A": -10.0, "B": 0.0}


def test_scenario_pnl_sums_stressed_positions() -> None:
    assert scenario_pnl({"A": 100.0, "B": 50.0}, {"A": -0.1, "B": -0.2}) == pytest.approx(-20.0)


def test_historical_stress_pnl_applies_t_minus_1_lag() -> None:
    returns = pd.DataFrame({"A": [0.01, -0.04, 0.02], "B": [0.00, -0.01, 0.01]})
    weights = {"A": 0.5, "B": 0.5}
    result = historical_stress_pnl(returns, weights)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == pytest.approx(0.005)


def test_historical_stress_pnl_rejects_missing_weight_asset() -> None:
    returns = pd.DataFrame({"A": [0.01, -0.04], "B": [0.00, -0.01]})
    with pytest.raises(ValueError, match="weights missing assets"):
        historical_stress_pnl(returns, {"A": 1.0})


def test_worst_historical_stress_returns_absolute_loss() -> None:
    returns = pd.DataFrame({"A": [0.01, -0.04, 0.02], "B": [0.00, -0.02, 0.01]})
    weights = {"A": 0.5, "B": 0.5}
    assert worst_historical_stress(returns, weights) == pytest.approx(0.03)


def test_factor_stress_matrix_multiplies_exposures_and_scenarios() -> None:
    exposures = pd.DataFrame({"market": [1.0, 0.5], "fx": [0.2, -0.1]}, index=["A", "B"])
    shocks = pd.DataFrame({"market": [-0.1, -0.2], "fx": [0.05, 0.00]}, index=["s1", "s2"])
    result = factor_stress_matrix(exposures, shocks)
    assert result.loc["A", "s1"] == pytest.approx(-0.09)
    assert result.loc["B", "s2"] == pytest.approx(-0.10)


def test_factor_stress_matrix_rejects_mismatched_factors() -> None:
    exposures = pd.DataFrame({"market": [1.0]}, index=["A"])
    shocks = pd.DataFrame({"fx": [-0.1]}, index=["s1"])
    with pytest.raises(ValueError, match="factor columns must match exactly"):
        factor_stress_matrix(exposures, shocks)
