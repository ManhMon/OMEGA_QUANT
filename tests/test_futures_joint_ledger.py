from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from omega.quant.portfolio.execution_sim import (
    InsolvencyError,
    apply_realistic_tc,
    estimate_futures_trade_cost,
    resolve_margin_rates,
    run_joint_ledger_step,
)


def test_joint_ledger_nav_equation_daily():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.5, 0.3]),
        stock_returns_t=np.array([0.10, -0.05]),
        cash_free_t_minus_1=20.0,
        margin_locked_t_minus_1=10.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=1.0,
        futures_close_t_minus_1=100.0,
        futures_close_t=102.0,
        contract_multiplier=2.0,
        trade_date=pd.Timestamp("2026-07-15"),
    )
    assert result["nav_t_after_trades"] == pytest.approx(result["bucket_sum_t"])


def test_joint_ledger_no_double_count_variation_margin():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=90.0,
        margin_locked_t_minus_1=10.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=2.0,
        futures_close_t_minus_1=100.0,
        futures_close_t=105.0,
        contract_multiplier=1.0,
        trade_date=pd.Timestamp("2026-07-15"),
    )
    assert result["futures_pnl_t"] == pytest.approx(10.0)
    assert result["nav_t_before_trades"] == pytest.approx(110.0)


def test_stock_mtm_uses_prior_realized_weights():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.6, 0.2]),
        stock_returns_t=np.array([0.10, 0.10]),
        cash_free_t_minus_1=20.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
    )
    assert result["stock_pnl_t"] == pytest.approx(8.0)


def test_stock_mtm_underinvested_portfolio_uses_nav_denominator():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.4]),
        stock_returns_t=np.array([0.10]),
        cash_free_t_minus_1=60.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
    )
    assert result["stock_pnl_t"] == pytest.approx(4.0)


def test_margin_schedule_effective_date_resolution():
    schedule = (
        ("1900-01-01", {"initial": 0.13, "maintenance": 0.10}),
        ("2026-07-01", {"initial": 0.20, "maintenance": 0.15}),
    )
    assert resolve_margin_rates(pd.Timestamp("2026-06-30"), schedule)["initial"] == pytest.approx(0.13)
    assert resolve_margin_rates(pd.Timestamp("2026-07-01"), schedule)["initial"] == pytest.approx(0.20)


def test_margin_call_uses_resolved_rates_not_constants():
    schedule = (
        ("1900-01-01", {"initial": 0.13, "maintenance": 0.10}),
        ("2026-07-01", {"initial": 0.20, "maintenance": 0.15}),
    )
    rates = resolve_margin_rates(pd.Timestamp("2026-07-15"), schedule)
    assert rates["maintenance"] == pytest.approx(0.15)


def test_forced_liquidation_reduces_futures_before_stocks():
    result = run_joint_ledger_step(
        nav_t_minus_1=2590.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=-10.0,
        margin_locked_t_minus_1=2600.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=2.0,
        futures_close_t_minus_1=100.0,
        futures_close_t=100.0,
        contract_multiplier=100.0,
        stock_liquidation_order=[("AAA", 50.0, 0.0)],
    )
    assert result["forced_futures_contracts"] > 0.0
    assert result["forced_stock_sales"] == pytest.approx(0.0)
    assert result["margin_locked_t"] == pytest.approx(1300.0)
    assert result["cash_free_t"] == pytest.approx(1290.0)


def test_forced_liquidation_rounding_and_costs():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=50.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=0.0,
        futures_close_t=100.0,
        contract_multiplier=10.0,
        target_futures_contracts=1.9,
        contract_round_lot=1,
        futures_trade_cost_t=estimate_futures_trade_cost(2.0, 100.0, 10.0),
    )
    assert result["required_cash_t"] > 0.0


def test_futures_target_scales_down_when_cash_cannot_cover_margin_and_costs():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=15.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=0.0,
        futures_close_t=10.0,
        contract_multiplier=10.0,
        target_futures_contracts=2.0,
        futures_trade_cost_t=2.0,
    )
    assert result["margin_locked_t"] == pytest.approx(13.0)
    assert result["cash_free_t"] == pytest.approx(0.0)
    assert result["required_cash_t"] == pytest.approx(15.0)


def test_short_futures_target_scales_down_when_margin_and_costs_exceed_cash():
    result = run_joint_ledger_step(
        nav_t_minus_1=500.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=140.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=0.0,
        futures_close_t=100.0,
        contract_multiplier=10.0,
        target_futures_contracts=-2.0,
        futures_trade_cost_t=2.0,
    )
    assert result["margin_locked_t"] == pytest.approx(130.0)
    assert result["required_cash_t"] == pytest.approx(132.0)
    assert result["cash_free_t"] == pytest.approx(8.0)
    assert result["cash_free_t"] >= 0.0


def test_stock_notional_excludes_futures_pnl_and_avoids_double_count():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.5]),
        stock_returns_t=np.array([0.10]),
        cash_free_t_minus_1=40.0,
        margin_locked_t_minus_1=10.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=1.0,
        futures_close_t_minus_1=100.0,
        futures_close_t=110.0,
        contract_multiplier=1.0,
        trade_date=pd.Timestamp("2026-07-15"),
    )
    assert result["stock_notional_t"] == pytest.approx(55.0)
    assert result["cash_free_t"] == pytest.approx(45.7)


def test_forced_liquidation_insolvency_raises():
    with pytest.raises(InsolvencyError):
        run_joint_ledger_step(
            nav_t_minus_1=10.0,
            realized_stock_weights_t_minus_1=np.array([0.0]),
            stock_returns_t=np.array([0.0]),
            cash_free_t_minus_1=-100.0,
            margin_locked_t_minus_1=0.0,
            futures_vm_receivable_t_minus_1=0.0,
            futures_contracts_t_minus_1=0.0,
        )


def test_intraday_roll_uses_preceding_trading_day_expiry():
    from omega.quant.portfolio import execution_sim as exec_mod

    original = exec_mod.get_futures_expiry_date
    exec_mod.get_futures_expiry_date = lambda year, month: date(2024, 9, 18)
    try:
        result = run_joint_ledger_step(
            nav_t_minus_1=100.0,
            realized_stock_weights_t_minus_1=np.array([0.0]),
            stock_returns_t=np.array([0.0]),
            cash_free_t_minus_1=100.0,
            margin_locked_t_minus_1=0.0,
            futures_vm_receivable_t_minus_1=0.0,
            trade_date=pd.Timestamp("2024-09-18"),
        )
    finally:
        exec_mod.get_futures_expiry_date = original
    assert result["expiry_date"] == date(2024, 9, 18)
    assert result["expiry_day"] is True


def test_ledger_skips_expiry_when_trade_date_is_absent_or_uncovered():
    kwargs = dict(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=100.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
    )

    assert run_joint_ledger_step(**kwargs)["expiry_date"] is None
    result = run_joint_ledger_step(**kwargs, trade_date=pd.Timestamp("2030-01-15"))
    assert result["expiry_date"] is None
    assert result["expiry_day"] is False


@pytest.mark.parametrize("trade_date", ["not-a-date", float("nan"), pd.NaT])
def test_joint_ledger_rejects_invalid_trade_date_before_calculation(trade_date):
    with pytest.raises(ValueError, match="trade_date must be a valid date"):
        run_joint_ledger_step(
            nav_t_minus_1=100.0,
            realized_stock_weights_t_minus_1=np.array([0.0]),
            stock_returns_t=np.array([0.0]),
            cash_free_t_minus_1=100.0,
            margin_locked_t_minus_1=0.0,
            futures_vm_receivable_t_minus_1=0.0,
            trade_date=trade_date,
        )


def test_pretrade_margin_check_includes_futures_trade_costs():
    cost = estimate_futures_trade_cost(1.0, 100.0, 10.0)
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=150.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        target_futures_contracts=1.0,
        futures_close_t=100.0,
        contract_multiplier=10.0,
        futures_trade_cost_t=cost,
    )
    assert result["required_cash_t"] > cost


def test_roll_affordability_counts_both_close_and_open_legs():
    close_cost = estimate_futures_trade_cost(1.0, 100.0, 10.0)
    open_cost = estimate_futures_trade_cost(1.0, 102.0, 10.0)
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=100.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=1.0,
        target_futures_contracts=1.0,
        futures_close_t=102.0,
        contract_multiplier=10.0,
        futures_trade_cost_t=close_cost + open_cost,
    )
    assert result["required_cash_t"] >= close_cost + open_cost


def test_roll_then_retarget_state_transition():
    result = run_joint_ledger_step(
        nav_t_minus_1=100.0,
        realized_stock_weights_t_minus_1=np.array([0.0]),
        stock_returns_t=np.array([0.0]),
        cash_free_t_minus_1=100.0,
        margin_locked_t_minus_1=0.0,
        futures_vm_receivable_t_minus_1=0.0,
        futures_contracts_t_minus_1=1.0,
        target_futures_contracts=2.0,
        futures_close_t=100.0,
        contract_multiplier=10.0,
    )
    assert result["margin_locked_t"] > 0.0


def test_same_day_roll_and_rehedge_no_double_count():
    w = pd.DataFrame([[0.5], [0.5]])
    y = np.array([[0.0], [0.0]])
    _, _, br = apply_realistic_tc(
        w,
        y,
        futures_contracts=np.array([1.0, 1.0]),
        futures_prices=np.array([100.0, 101.0]),
        contract_multiplier=10.0,
    )
    assert br["futures_pnl"][1] == pytest.approx(10.0)


def test_hedge_off_matches_legacy_execution_path():
    w = pd.DataFrame([[0.5], [0.5]])
    y = np.array([[0.01], [0.01]])
    _, net_legacy, _ = apply_realistic_tc(w, y)
    _, net_hedge_off, br = apply_realistic_tc(
        w,
        y,
        futures_contracts=np.array([1.0, 1.0]),
        futures_prices=np.array([100.0, 101.0]),
        contract_multiplier=10.0,
        hedge_enabled=False,
    )
    np.testing.assert_allclose(net_legacy, net_hedge_off)
    assert br["hedge_enabled"] is False
