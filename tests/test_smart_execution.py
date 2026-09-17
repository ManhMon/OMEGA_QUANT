from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from omega.quant.execution.market_impact import (
    TMinusOneImpactSnapshot,
    calculate_nonlinear_slippage,
    calculate_nonlinear_slippage_bps,
)
from omega.quant.execution.smart_execution import (
    ExecutionSafetyError,
    apply_realistic_tc_kill_switch,
    build_randomized_twap_schedule,
    build_vwap_schedule,
    enforce_slippage_kill_switch,
    normalized_vwap_profile,
    slice_order_volume,
)
from omega.quant.portfolio.execution_sim import VNCostModel, apply_realistic_tc


def test_vwap_profile_has_16_intervals_and_sums_to_one() -> None:
    schedule = build_vwap_schedule()
    assert len(schedule) == 16
    assert math.isclose(sum(item.weight for item in schedule), 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert all(item.duration_minutes == 15 for item in schedule)


def test_randomized_twap_is_normalized_and_deterministic_with_seed() -> None:
    schedule = build_randomized_twap_schedule(seed=7)
    weights = [item.weight for item in schedule]
    assert len(weights) == 16
    assert math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert weights == pytest.approx([item.weight for item in build_randomized_twap_schedule(seed=7)])
    assert all(item.duration_minutes == 15 for item in schedule)


def test_slice_order_volume_preserves_total() -> None:
    weights = normalized_vwap_profile()
    slices = slice_order_volume(1_000_000.0, weights)
    assert sum(slices) == pytest.approx(1_000_000.0)


def test_nonlinear_slippage_uses_phase4_formula() -> None:
    expected = 0.5 * 0.002 + 0.15 * 0.03 * math.sqrt(100_000 / 10_000_000)
    actual = calculate_nonlinear_slippage(
        order_volume=100_000,
        daily_volume=10_000_000,
        spread=0.002,
        volatility=0.03,
    )
    assert actual == pytest.approx(expected)


def test_nonlinear_slippage_bps_uses_t_minus_one_snapshot() -> None:
    snapshot = TMinusOneImpactSnapshot(spread=0.001, volatility=0.02, daily_volume=2_000_000, as_of="T-1")
    bps = calculate_nonlinear_slippage_bps(50_000, snapshot)
    assert bps == pytest.approx(10000.0 * (0.5 * 0.001 + 0.15 * 0.02 * math.sqrt(50_000 / 2_000_000)))


def test_kill_switch_triggers_above_50_bps() -> None:
    with pytest.raises(ExecutionSafetyError):
        enforce_slippage_kill_switch(50.0001)


def test_realistic_tc_kill_switch_uses_absolute_percentage_threshold() -> None:
    with pytest.raises(ExecutionSafetyError, match="Slippage exceeds 10.0% kill switch threshold"):
        apply_realistic_tc_kill_switch(-0.100001)


def test_apply_realistic_tc_is_point_in_time_safe() -> None:
    weights = pd.DataFrame([[0.10], [0.10]])
    realized = np.array([[0.0], [0.0]])
    adv_full = np.array([[1_000_000.0], [100.0]])
    adv_truncated = np.array([[1_000_000.0], [1_000_000.0]])
    model = VNCostModel(slippage_k=0.02, half_spread_bps=0.0005)

    _, _, breakdown_full = apply_realistic_tc(
        weights,
        realized,
        daily_adv=adv_full,
        cost_model=model,
    )
    _, _, breakdown_truncated = apply_realistic_tc(
        weights,
        realized,
        daily_adv=adv_truncated,
        cost_model=model,
    )

    assert breakdown_full["bar_costs"][0] == pytest.approx(breakdown_truncated["bar_costs"][0])


def test_apply_realistic_tc_kill_switch_raises_on_extreme_slippage() -> None:
    with pytest.raises(ExecutionSafetyError):
        apply_realistic_tc_kill_switch(1.0)
