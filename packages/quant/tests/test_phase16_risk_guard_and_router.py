"""
Phase 16 test coverage for real-time risk guard and order router.
"""

import pytest

from omega.quant.execution.broker_gateway import (
    BrokerCredentials,
    BrokerOrder,
    OrderSide,
    OrderStatus,
    OrderType,
)
from omega.quant.execution.order_router import OrderRouter, OrderRouterConfig, TradingMode
from omega.quant.realtime_risk_guard import RealtimeRiskGuard, RiskLimits, RiskVerdict


@pytest.fixture
def broker_order() -> BrokerOrder:
    return BrokerOrder(
        symbol="VNM",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        price=100000.0,
    )


@pytest.fixture
def credentials() -> BrokerCredentials:
    return BrokerCredentials(
        broker_name="SSI",
        api_key="SSI_KEY",
        api_secret="SSI_SECRET",
        account_id="SSI_ACCOUNT",
        base_url="https://api.ssi.com.vn",
    )


def test_realtime_risk_guard_passes_within_limits() -> None:
    guard = RealtimeRiskGuard(
        RiskLimits(
            max_adv_pct=0.05,
            max_concentration_pct=0.20,
            max_notional_currency=500_000_000.0,
            circuit_breaker_drawdown=0.10,
        )
    )
    guard.set_portfolio_state(total_equity=2_000_000_000.0, exposures={"VNM": 100_000_000.0})

    verdict = guard.check_order(symbol="VNM", quantity=1_000, price=100000.0, adv_20d=100_000)

    assert verdict == RiskVerdict.PASS


def test_realtime_risk_guard_rejects_notional_before_other_checks() -> None:
    guard = RealtimeRiskGuard(RiskLimits(max_notional_currency=50_000_000.0, max_adv_pct=1.0))

    verdict = guard.check_order(symbol="VNM", quantity=1_000, price=100000.0, adv_20d=10_000_000)

    assert verdict == RiskVerdict.FAIL_NOTIONAL


def test_realtime_risk_guard_rejects_adv_breach() -> None:
    guard = RealtimeRiskGuard(RiskLimits(max_adv_pct=0.05, max_notional_currency=500_000_000.0))

    verdict = guard.check_order(symbol="VNM", quantity=6_000, price=10000.0, adv_20d=100_000)

    assert verdict == RiskVerdict.FAIL_ADV


def test_realtime_risk_guard_rejects_concentration_breach() -> None:
    guard = RealtimeRiskGuard(RiskLimits(max_concentration_pct=0.20))
    guard.set_portfolio_state(total_equity=1_000_000_000.0, exposures={"VNM": 190_000_000.0})

    verdict = guard.check_order(symbol="VNM", quantity=200, price=100000.0, adv_20d=1_000_000)

    assert verdict == RiskVerdict.FAIL_CONCENTRATION


def test_realtime_risk_guard_rejects_circuit_breaker() -> None:
    guard = RealtimeRiskGuard(RiskLimits(circuit_breaker_drawdown=0.10))
    guard._daily_pnl = -250_000_000.0

    verdict = guard.check_order(symbol="VNM", quantity=100, price=100000.0, adv_20d=1_000_000)

    assert verdict == RiskVerdict.FAIL_CIRCUIT_BREAKER


def test_realtime_risk_guard_updates_exposure_after_fill() -> None:
    guard = RealtimeRiskGuard()

    guard.update_exposure(symbol="VNM", filled_quantity=500, fill_price=100000.0)
    guard.update_exposure(symbol="VNM", filled_quantity=200, fill_price=110000.0)

    assert guard._exposure["VNM"] == 72_000_000.0


def test_realtime_risk_guard_rejects_zero_equity() -> None:
    """P2.3 regression: check_order() must raise on zero equity, not divide by zero."""
    guard = RealtimeRiskGuard()
    guard._total_equity = 0.0

    with pytest.raises(ValueError, match="Invalid total_equity"):
        guard.check_order(symbol="VNM", quantity=100, price=100.0, adv_20d=1_000_000)


def test_realtime_risk_guard_rejects_negative_equity() -> None:
    """P2.3 regression: check_order() must raise on negative equity."""
    guard = RealtimeRiskGuard()
    guard._total_equity = -1.0

    with pytest.raises(ValueError, match="Invalid total_equity"):
        guard.check_order(symbol="VNM", quantity=100, price=100.0, adv_20d=1_000_000)


def test_order_router_paper_requires_current_price(broker_order: BrokerOrder) -> None:
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.PAPER))

    with pytest.raises(ValueError, match="current_price required for PAPER mode"):
        router.submit_order(broker_order)


def test_order_router_live_requires_credentials_for_authentication() -> None:
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.LIVE))

    with pytest.raises(ValueError, match="SSI credentials not provided"):
        router.authenticate()


def test_order_router_live_requires_credentials_for_submission(broker_order: BrokerOrder) -> None:
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.LIVE))

    with pytest.raises(ValueError, match="SSI credentials not provided"):
        router.submit_order(broker_order)


def test_order_router_live_rejects_unauthenticated_submission(
    broker_order: BrokerOrder,
    credentials: BrokerCredentials,
) -> None:
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.LIVE, ssi_credentials=credentials))

    response = router.submit_order(broker_order)

    assert response.success is False
    assert response.status == OrderStatus.REJECTED
    assert response.message == "Not authenticated"


def test_order_router_switch_mode_reuses_live_gateway(
    broker_order: BrokerOrder,
    credentials: BrokerCredentials,
) -> None:
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.PAPER, ssi_credentials=credentials))

    router.switch_mode(TradingMode.LIVE)
    assert router.authenticate() is True

    response = router.submit_order(broker_order)

    assert response.success is True
    assert response.status == OrderStatus.SUBMITTED
    assert response.broker_order_id.startswith("SSI_")
