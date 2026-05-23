from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.risk.t25_risk_guard import T25RiskGuard


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "t25_risk_guard_state.json"


@pytest.fixture
def guard(state_file: Path) -> T25RiskGuard:
    return T25RiskGuard(initial_cash=1_000_000.0, safety_buffer=0.05, state_file=state_file)


def test_update_state_buckets_settlement_horizons_with_business_days(guard: T25RiskGuard) -> None:
    state = guard.update_state(
        as_of_date="2026-05-01",
        current_cash=1_000_000.0,
        pending_trades=[
            {"trade_date": "2026-04-29", "ticker": "AAA", "quantity": 10, "price": 1_000.0, "direction": "BUY"},
            {"trade_date": "2026-04-30", "ticker": "BBB", "quantity": 20, "price": 2_000.0, "direction": "BUY"},
            {"trade_date": "2026-05-01", "ticker": "CCC", "quantity": 30, "price": 3_000.0, "direction": "BUY"},
        ],
    )
    assert state.unsettled_buy_t0 == pytest.approx(10_000.0)
    assert state.unsettled_buy_t1 == pytest.approx(40_000.0)
    assert state.unsettled_buy_t2 == pytest.approx(90_000.0)


def test_update_state_projects_cash_across_buy_and_sell_horizons(guard: T25RiskGuard) -> None:
    state = guard.update_state(
        as_of_date="2026-05-01",
        current_cash=500_000.0,
        pending_trades=[
            {"trade_date": "2026-04-29", "ticker": "AAA", "quantity": 10, "price": 1_000.0, "direction": "BUY"},
            {"trade_date": "2026-04-29", "ticker": "BBB", "quantity": 5, "price": 2_000.0, "direction": "SELL"},
            {"trade_date": "2026-04-30", "ticker": "CCC", "quantity": 20, "price": 1_500.0, "direction": "BUY"},
            {"trade_date": "2026-05-01", "ticker": "DDD", "quantity": 4, "price": 5_000.0, "direction": "SELL"},
        ],
    )
    assert state.projected_t1 == pytest.approx(500_000.0)
    assert state.projected_t2 == pytest.approx(470_000.0)
    assert state.projected_t3 == pytest.approx(490_000.0)


def test_update_state_applies_available_now_buffer_and_floor_zero(guard: T25RiskGuard) -> None:
    state = guard.update_state(
        as_of_date="2026-05-01",
        current_cash=100_000.0,
        pending_trades=[
            {"trade_date": "2026-04-29", "ticker": "AAA", "quantity": 10, "price": 2_000.0, "direction": "BUY"},
            {"trade_date": "2026-04-30", "ticker": "BBB", "quantity": 10, "price": 2_000.0, "direction": "BUY"},
            {"trade_date": "2026-05-01", "ticker": "CCC", "quantity": 10, "price": 2_000.0, "direction": "BUY"},
        ],
    )
    assert state.available_now == pytest.approx(37_000.0)


def test_update_state_ignores_trades_beyond_t2_in_available_now(guard: T25RiskGuard) -> None:
    state = guard.update_state(
        as_of_date="2026-05-01",
        current_cash=100_000.0,
        pending_trades=[
            {"trade_date": "2026-05-04", "ticker": "AAA", "quantity": 10, "price": 2_000.0, "direction": "BUY"},
        ],
    )
    assert state.unsettled_buy_t0 == pytest.approx(0.0)
    assert state.unsettled_buy_t1 == pytest.approx(0.0)
    assert state.unsettled_buy_t2 == pytest.approx(0.0)
    assert state.available_now == pytest.approx(100_000.0)


def test_check_allocation_rejects_over_allocation(guard: T25RiskGuard) -> None:
    guard.update_state(
        as_of_date="2026-05-01",
        current_cash=100_000.0,
        pending_trades=[{"trade_date": "2026-05-01", "ticker": "AAA", "quantity": 10, "price": 5_000.0, "direction": "BUY"}],
    )
    is_safe, message, details = guard.check_allocation([
        {"ticker": "BBB", "quantity": 15, "price": 4_000.0, "direction": "BUY"}
    ])
    assert is_safe is False
    assert "OVER-ALLOCATION DETECTED" in message
    assert details["shortage"] == pytest.approx(12_500.0)


def test_check_allocation_accepts_empty_trade_list(guard: T25RiskGuard) -> None:
    guard.update_state(as_of_date="2026-05-01", current_cash=100_000.0, pending_trades=[])
    is_safe, _, details = guard.check_allocation([])
    assert is_safe is True
    assert details["proposed_buy_value"] == pytest.approx(0.0)


def test_get_max_position_size_rounds_down_to_vn_lot_size(guard: T25RiskGuard) -> None:
    guard.update_state(as_of_date="2026-05-01", current_cash=123_456.0, pending_trades=[])
    assert guard.get_max_position_size("AAA", price=123.0) == pytest.approx(1_000.0)


def test_get_settlement_schedule_returns_sorted_frame(guard: T25RiskGuard) -> None:
    guard.update_state(
        as_of_date="2026-05-01",
        current_cash=100_000.0,
        pending_trades=[
            {"trade_date": "2026-05-01", "ticker": "CCC", "quantity": 10, "price": 1_000.0, "direction": "BUY"},
            {"trade_date": "2026-04-29", "ticker": "AAA", "quantity": 10, "price": 1_000.0, "direction": "SELL"},
        ],
    )
    result = guard.get_settlement_schedule()
    assert list(result["ticker"]) == ["AAA", "CCC"]
    assert list(result["settlement_date"]) == ["2026-05-01", "2026-05-05"]


def test_state_round_trip_loads_saved_projection(state_file: Path) -> None:
    writer = T25RiskGuard(initial_cash=200_000.0, state_file=state_file)
    writer.update_state(
        as_of_date="2026-05-01",
        current_cash=200_000.0,
        pending_trades=[{"trade_date": "2026-04-30", "ticker": "AAA", "quantity": 10, "price": 1_000.0, "direction": "BUY"}],
    )
    reader = T25RiskGuard(initial_cash=0.0, state_file=state_file)
    assert reader.load_state() is True
    assert reader.current_state is not None
    assert reader.current_state.projected_t2 == pytest.approx(writer.current_state.projected_t2)


def test_update_state_rejects_invalid_direction(guard: T25RiskGuard) -> None:
    with pytest.raises(ValueError, match="direction"):
        guard.update_state(
            as_of_date="2026-05-01",
            current_cash=100_000.0,
            pending_trades=[{"trade_date": "2026-05-01", "ticker": "AAA", "quantity": 1, "price": 1_000.0, "direction": "HOLD"}],
        )


def test_business_days_between_skips_weekend(guard: T25RiskGuard) -> None:
    assert guard._business_days_between(pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-05")) == 2
