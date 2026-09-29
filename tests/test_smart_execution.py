from __future__ import annotations

import math
import time

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
from omega.execution.microstructure_router import L2OrderBook, MicrostructureRouter
from omega.execution.smart_router import SmartRouter
from omega.quant.ensemble_optimizer import EnsembleOptimizer


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


def test_microstructure_slices_preserve_odd_and_negative_quantities() -> None:
    router = MicrostructureRouter()
    book = L2OrderBook(0, "VCB", [(100, 10)], [(101, 10)])
    for quantity in (103, -103):
        base = router.route_order({"quantity": quantity}, duration_minutes=15)
        adjusted = router.adjust_schedule(base, book, "BUY")
        assert sum(item["quantity"] for item in base) == quantity
        assert sum(item["quantity"] for item in adjusted) == quantity


def test_smart_router_twap_board_lot_slices_preserve_quantity() -> None:
    schedule = SmartRouter(use_microstructure=False)._generate_twap_schedule(
        {"quantity": 1_000}, duration_minutes=30
    )
    assert [item["quantity"] for item in schedule] == [200, 200, 200, 200, 100, 100]
    assert sum(item["quantity"] for item in schedule) == 1_000
    assert all(item["quantity"] % 100 == 0 for item in schedule)


@pytest.mark.parametrize("quantity", [1_000, -1_000])
def test_smart_router_twap_board_lot_slices_keep_sign(quantity: int) -> None:
    schedule = SmartRouter(use_microstructure=False)._generate_twap_schedule(
        {"quantity": quantity}, duration_minutes=30
    )
    assert sum(item["quantity"] for item in schedule) == quantity
    assert all(item["quantity"] * quantity > 0 and item["quantity"] % 100 == 0 for item in schedule)


def test_smart_router_twap_route_order_isolates_odd_lot_remainder() -> None:
    router = SmartRouter(use_microstructure=False)
    order = {"symbol": "VCB", "quantity": 1050, "side": "BUY"}
    child_orders = router.route_order(order, algo="TWAP", duration_minutes=30)

    assert len(child_orders) == 7
    regular_children = child_orders[:-1]
    odd_lot_child = child_orders[-1]

    assert [c["quantity"] for c in regular_children] == [200, 200, 200, 200, 100, 100]
    assert all(c["quantity"] % 100 == 0 for c in regular_children)
    assert odd_lot_child["quantity"] == 50
    assert sum(c["quantity"] for c in child_orders) == 1050
    assert all(c["symbol"] == "VCB" and c["side"] == "BUY" for c in child_orders)

    times = [float(c["scheduled_time"]) for c in child_orders]
    assert times == sorted(times)


@pytest.mark.parametrize(
    "quantity",
    [1050, -1050, 50, -50, 100, -100, 125, -125, 99, -99, 101, -101],
)
@pytest.mark.parametrize("duration_minutes", [15, 30])
def test_smart_router_twap_route_order_fault_injection_odd_lots_and_signs(
    quantity: int, duration_minutes: int
) -> None:
    router = SmartRouter(use_microstructure=False)
    side = "BUY" if quantity > 0 else "SELL"
    order = {"symbol": "VCB", "quantity": quantity, "side": side}
    child_orders = router.route_order(order, algo="TWAP", duration_minutes=duration_minutes)

    assert child_orders
    assert sum(c["quantity"] for c in child_orders) == quantity
    assert all(c["quantity"] * quantity > 0 for c in child_orders)
    assert all(c["symbol"] == "VCB" and c["side"] == side for c in child_orders)

    abs_qty = abs(quantity)
    expected_odd = abs_qty % 100
    if expected_odd > 0:
        odd_children = [c for c in child_orders if abs(c["quantity"]) < 100]
        assert len(odd_children) == 1
        assert abs(odd_children[0]["quantity"]) == expected_odd
    else:
        assert all(c["quantity"] % 100 == 0 for c in child_orders)

    board_lot_children = [c for c in child_orders if abs(c["quantity"]) >= 100]
    assert all(c["quantity"] % 100 == 0 for c in board_lot_children)

    times = [float(c["scheduled_time"]) for c in child_orders]
    assert times == sorted(times)


def test_smart_router_twap_reproduction_one_minute_150_shares_regression() -> None:
    router = SmartRouter(use_microstructure=False)
    order = {"symbol": "VCB", "quantity": 150, "side": "BUY"}
    t_before = time.time()
    child_orders = router.route_order(order, algo="TWAP", duration_minutes=1)
    t_after = time.time()

    assert len(child_orders) == 2
    regular_child, odd_child = child_orders[0], child_orders[1]

    assert regular_child["quantity"] == 100
    assert odd_child["quantity"] == 50
    assert sum(c["quantity"] for c in child_orders) == 150

    # Regular child is scheduled at start_time
    assert t_before <= float(regular_child["scheduled_time"]) <= t_after
    # Odd-lot child is bounded by duration_minutes * 60 (60s), not 300s
    max_deadline = float(regular_child["scheduled_time"]) + 60.0
    assert float(odd_child["scheduled_time"]) <= max_deadline
    assert float(odd_child["scheduled_time"]) - float(regular_child["scheduled_time"]) == pytest.approx(60.0, abs=1e-3)
    assert float(odd_child["scheduled_time"]) < float(regular_child["scheduled_time"]) + 300.0


@pytest.mark.parametrize(
    "quantity",
    [150, -150, 50, -50, 1050, 99, 101],
)
@pytest.mark.parametrize("duration_minutes", [1, 2, 3, 4])
def test_smart_router_twap_short_duration_odd_lot_bounds_scheduled_time(
    quantity: int, duration_minutes: int
) -> None:
    router = SmartRouter(use_microstructure=False)
    side = "BUY" if quantity > 0 else "SELL"
    order = {"symbol": "VCB", "quantity": quantity, "side": side}
    child_orders = router.route_order(order, algo="TWAP", duration_minutes=duration_minutes)

    assert child_orders
    assert sum(c["quantity"] for c in child_orders) == quantity
    assert all(c["quantity"] * quantity > 0 for c in child_orders)

    times = [float(c["scheduled_time"]) for c in child_orders]
    assert times == sorted(times)

    start_time = times[0]
    deadline = start_time + duration_minutes * 60.0
    for child in child_orders:
        assert float(child["scheduled_time"]) <= deadline + 1e-6

    abs_qty = abs(quantity)
    expected_odd = abs_qty % 100
    if expected_odd > 0:
        odd_children = [c for c in child_orders if abs(c["quantity"]) < 100]
        assert len(odd_children) == 1
        assert abs(odd_children[0]["quantity"]) == expected_odd
        assert float(odd_children[0]["scheduled_time"]) <= deadline + 1e-6


@pytest.mark.parametrize("duration_minutes", [0, -1, -5])
def test_smart_router_fault_injection_fail_closed_non_positive_duration(
    duration_minutes: int,
) -> None:
    router = SmartRouter(use_microstructure=False)
    order = {"symbol": "VCB", "quantity": 100, "side": "BUY"}
    with pytest.raises(ValueError, match="duration_minutes must be positive"):
        router.route_order(order, algo="TWAP", duration_minutes=duration_minutes)

    with pytest.raises(ValueError, match="duration_minutes must be positive"):
        router.route_order(order, algo="VWAP", duration_minutes=duration_minutes)

    with pytest.raises(ValueError, match="duration_minutes must be positive"):
        router._generate_twap_schedule(order, duration_minutes=duration_minutes)

    with pytest.raises(ValueError, match="duration_minutes must be positive"):
        router._generate_vwap_schedule(order, duration_minutes=duration_minutes)

    micro_router = MicrostructureRouter()
    with pytest.raises(ValueError, match="duration_minutes must be positive"):
        micro_router.route_order(order, duration_minutes=duration_minutes)


@pytest.mark.parametrize(
    ("quantity", "duration_minutes", "volume_profile"),
    [
        (100, 5, None),
        (1_000, 30, None),
        (1_050, 30, None),
        (-1_000, 10, [0.3, 0.7]),
    ],
)
def test_smart_router_vwap_preserves_signed_quantity_and_residual(
    quantity: int, duration_minutes: int, volume_profile: list[float] | None
) -> None:
    schedule = SmartRouter(use_microstructure=False)._generate_vwap_schedule(
        {"quantity": quantity}, duration_minutes, volume_profile
    )

    assert schedule
    assert sum(item["quantity"] for item in schedule) == quantity
    assert all(item["quantity"] * quantity > 0 for item in schedule)


@pytest.mark.parametrize("volume_profile", [[-0.5, 1.5], [1.0, -0.1]])
def test_smart_router_vwap_rejects_negative_profile_weights(volume_profile: list[float]) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SmartRouter(use_microstructure=False)._generate_vwap_schedule(
            {"quantity": 1_000}, duration_minutes=10, volume_profile=volume_profile
        )


@pytest.mark.parametrize("volume_profile", [[0.0, 0.0], []])
def test_smart_router_vwap_rejects_nonpositive_profile_sum(volume_profile: list[float]) -> None:
    with pytest.raises(ValueError, match="positive sum"):
        SmartRouter(use_microstructure=False)._generate_vwap_schedule(
            {"quantity": 1_000}, duration_minutes=10, volume_profile=volume_profile
        )


def test_ensemble_optimizer_fails_closed_on_bad_input_and_solver_failure(monkeypatch) -> None:
    import omega.quant.ensemble_optimizer as module

    optimizer = EnsembleOptimizer()
    scores = {f"model_{i}": np.arange(4, dtype=float) for i in range(2)}
    with pytest.raises(ValueError, match="finite, aligned"):
        optimizer.optimize(scores, np.array([1.0, np.nan, 0.0, 1.0]), 2)

    class Failed:
        success = False
        x = np.array([0.5, 0.5])
        fun = 0.0
        message = "injected failure"

    monkeypatch.setattr(module, "minimize", lambda *args, **kwargs: Failed())
    with pytest.raises(RuntimeError, match="injected failure"):
        optimizer.optimize(scores, np.arange(4, dtype=float), 2)


@pytest.mark.parametrize(
    ("quantity", "volume_profile"),
    [
        (199, [0.9, 0.1]),
        (-199, [0.9, 0.1]),
        (150, [0.35, 0.35, 0.30]),
        (299, [0.6, 0.4]),
        (99, [0.9, 0.1]),
        (101, [0.9, 0.1]),
    ],
)
def test_smart_router_vwap_caps_allocation_near_board_lot_boundary(
    quantity: int, volume_profile: list[float]
) -> None:
    router = SmartRouter(use_microstructure=False)
    order = {"quantity": quantity, "side": "BUY" if quantity > 0 else "SELL"}
    schedule = router._generate_vwap_schedule(
        order,
        duration_minutes=len(volume_profile) * 5,
        volume_profile=volume_profile,
    )

    assert schedule
    assert sum(item["quantity"] for item in schedule) == quantity
    for item in schedule:
        assert item["quantity"] * quantity > 0
        if quantity > 0:
            assert item["quantity"] > 0


@pytest.mark.parametrize(
    "volume_profile",
    [
        [0.999, 0.001],
        [0.001, 0.999],
        [100.0, 0.01],
        [1.0, 0.0],
        [0.0, 1.0],
        [1e-6, 0.5, 0.5],
    ],
)
@pytest.mark.parametrize(
    "quantity",
    [1, 49, 99, 101, 149, 199, 501, 999, -1, -99, -101, -199],
)
def test_smart_router_vwap_fault_injection_boundary_profiles(
    volume_profile: list[float], quantity: int
) -> None:
    router = SmartRouter(use_microstructure=False)
    order = {"quantity": quantity, "side": "BUY" if quantity > 0 else "SELL"}
    schedule = router._generate_vwap_schedule(
        order,
        duration_minutes=len(volume_profile) * 5,
        volume_profile=volume_profile,
    )

    assert schedule
    assert sum(item["quantity"] for item in schedule) == quantity
    for item in schedule:
        assert item["quantity"] * quantity > 0


def test_microstructure_router_and_smart_router_schedule_timing() -> None:
    micro_router = MicrostructureRouter()
    fixed_start = 1_700_000_000.0
    micro_schedule = micro_router.route_order(
        {"symbol": "VCB", "quantity": 1000, "side": "BUY"},
        duration_minutes=30,
        start_time=fixed_start,
    )
    assert len(micro_schedule) == 6
    for slice_order in micro_schedule:
        assert slice_order["scheduled_time"] == pytest.approx(
            fixed_start + slice_order["time_offset"] * 60
        )

    smart_router = SmartRouter(use_microstructure=True)
    t_start = time.time()
    child_orders = smart_router.route_order(
        {"symbol": "VCB", "quantity": 1000, "side": "BUY"},
        duration_minutes=30,
    )
    for slice_order in child_orders:
        assert "scheduled_time" in slice_order
        assert slice_order["scheduled_time"] == pytest.approx(
            t_start + slice_order["time_offset"] * 60, abs=2.0
        )

    executed = smart_router.process_queue()
    assert len(executed) == 1
    assert executed[0]["time_offset"] == 0
    assert len(smart_router.schedule) == len(child_orders) - 1
    assert all(item["time_offset"] > 0 for item in smart_router.schedule)
    assert all(item["scheduled_time"] > time.time() for item in smart_router.schedule)


def test_smart_router_process_queue_fault_injection_missing_scheduled_time() -> None:
    router = SmartRouter(use_microstructure=False)
    router.schedule = [
        {"symbol": "VCB", "quantity": 100, "side": "BUY", "time_offset": 0},
        {"symbol": "VCB", "quantity": 100, "side": "BUY", "time_offset": 5},
        {"symbol": "VCB", "quantity": 100, "side": "BUY", "time_offset": 10},
    ]
    t_before = time.time()
    executed = router.process_queue()

    assert len(executed) == 1
    assert executed[0]["time_offset"] == 0
    assert len(router.schedule) == 2
    for child in router.schedule:
        assert child["time_offset"] > 0
        assert child["scheduled_time"] >= t_before + child["time_offset"] * 60
        assert child["scheduled_time"] > time.time()

    executed_again = router.process_queue()
    assert len(executed_again) == 0
    assert len(router.schedule) == 2
