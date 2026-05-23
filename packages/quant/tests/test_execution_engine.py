"""
Unit Tests for OMEGA_QUANT Execution Engine
Phase 4.3: Order Routing & Broker Integration

Author: Backend Engineer (Role 09)
Date: 2026-05-13
"""

import pytest
from omega.quant.execution.broker_gateway import (
    BrokerOrder,
    OrderSide,
    OrderType,
    OrderStatus,
    PaperTradingEngine,
    BrokerCredentials,
)
from omega.quant.execution.order_router import (
    OrderRouter,
    OrderRouterConfig,
    TradingMode,
    SSIBrokerGateway,
)


@pytest.fixture
def broker_order():
    return BrokerOrder(
        symbol="FPT",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        price=120000.0
    )


@pytest.fixture
def credentials():
    return BrokerCredentials(
        broker_name="SSI",
        api_key="SSI_KEY",
        api_secret="SSI_SECRET",
        account_id="SSI_ACCOUNT",
        base_url="https://api.ssi.com.vn"
    )


def test_broker_order_validation():
    """Test board-lot and price validation in BrokerOrder."""
    # Valid order
    order = BrokerOrder("VNM", OrderSide.BUY, 100, OrderType.LIMIT, 100000.0)
    assert order.symbol == "VNM"
    
    # Rounded quantity (150 -> 100 board-lot)
    order_rounded = BrokerOrder("VNM", OrderSide.BUY, 150, OrderType.LIMIT, 100000.0)
    assert order_rounded.quantity == 100
    
    # Missing price for LIMIT
    with pytest.raises(ValueError, match="LIMIT orders require a price"):
        BrokerOrder("VNM", OrderSide.BUY, 100, OrderType.LIMIT, None)


def test_paper_trading_engine(broker_order):
    """Test PaperTradingEngine submission and status."""
    engine = PaperTradingEngine()
    response = engine.submit_order(broker_order, current_price=120000.0)
    
    assert response.success is True
    assert response.status == OrderStatus.FILLED
    assert response.broker_order_id.startswith("PAPER_")
    
    status = engine.get_order_status(response.broker_order_id)
    assert status.status == OrderStatus.FILLED
    assert status.symbol == "FPT"
    assert status.average_fill_price == 120000.0


def test_order_router_paper(broker_order):
    """Test OrderRouter in PAPER mode."""
    config = OrderRouterConfig(mode=TradingMode.PAPER)
    router = OrderRouter(config)
    
    response = router.submit_order(broker_order, current_price=120000.0)
    assert response.success is True
    assert response.status == OrderStatus.FILLED
    assert "PAPER" in response.broker_order_id


def test_order_router_live_mock(broker_order, credentials):
    """Test OrderRouter in LIVE mode (simulated SSI)."""
    config = OrderRouterConfig(
        mode=TradingMode.LIVE,
        ssi_credentials=credentials
    )
    router = OrderRouter(config)
    
    # Live mode needs authentication
    assert router.authenticate() is True
    
    response = router.submit_order(broker_order)
    assert response.success is True
    assert "SSI" in response.broker_order_id
    assert response.message == "Order submitted to SSI"


def test_order_router_mode_switching(broker_order, credentials):
    """Test switching modes in OrderRouter."""
    config = OrderRouterConfig(
        mode=TradingMode.PAPER,
        ssi_credentials=credentials
    )
    router = OrderRouter(config)
    assert router.mode == TradingMode.PAPER
    
    # Submit paper order
    res1 = router.submit_order(broker_order, 120000.0)
    assert "PAPER" in res1.broker_order_id
    
    # Switch to LIVE
    router.switch_mode(TradingMode.LIVE)
    assert router.mode == TradingMode.LIVE
    assert router.authenticate() is True
    
    # Submit live order
    res2 = router.submit_order(broker_order)
    assert "SSI" in res2.broker_order_id

