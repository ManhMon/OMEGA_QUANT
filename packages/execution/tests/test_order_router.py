"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Order Router Tests

Tests for OrderRouter with PAPER/LIVE routing and fallback logic.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
import logging
from unittest.mock import MagicMock, patch

from omega.execution import (
    TradingMode,
    OrderRouterConfig,
    OrderRouter,
    BrokerCredentials,
    BrokerOrder,
    OrderSide,
    OrderType,
    OrderStatus,
    SSIBrokerGateway,
)

logger = logging.getLogger(__name__)


class TestOrderRouter:
    """Tests for OrderRouter class."""
    
    @pytest.fixture
    def paper_config(self):
        """Create paper trading config."""
        return OrderRouterConfig(mode=TradingMode.PAPER)
    
    @pytest.fixture
    def live_config(self):
        """Create live trading config with SSI credentials."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        return OrderRouterConfig(
            mode=TradingMode.LIVE,
            ssi_credentials=credentials,
            fallback_to_paper=True
        )
    
    def test_paper_router_initialization(self, paper_config):
        """Test OrderRouter initializes in PAPER mode."""
        router = OrderRouter(paper_config)
        assert router.mode == TradingMode.PAPER
        assert router._current_gateway == router.paper_engine
    
    def test_live_router_initialization(self, live_config):
        """Test OrderRouter initializes in LIVE mode."""
        router = OrderRouter(live_config)
        assert router.mode == TradingMode.LIVE
        assert router.ssi_gateway is not None
        assert router._current_gateway == router.ssi_gateway
    
    def test_switch_mode_to_paper(self, live_config):
        """Test switching from LIVE to PAPER mode."""
        router = OrderRouter(live_config)
        router.switch_mode(TradingMode.PAPER)
        assert router.mode == TradingMode.PAPER
        assert router._current_gateway == router.paper_engine
    
    def test_switch_mode_to_live(self, paper_config):
        """Test switching from PAPER to LIVE mode."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        paper_config.ssi_credentials = credentials
        router = OrderRouter(paper_config)
        router.switch_mode(TradingMode.LIVE)
        assert router.mode == TradingMode.LIVE
        assert router._current_gateway == router.ssi_gateway
    
    def test_submit_order_paper_mode(self, paper_config):
        """Test order submission in PAPER mode."""
        router = OrderRouter(paper_config)
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        
        assert response.success is True
        assert response.status == OrderStatus.FILLED
        assert response.broker_order_id.startswith("PAPER_")
    
    def test_submit_order_live_mode(self, live_config):
        """Test order submission in LIVE mode."""
        router = OrderRouter(live_config)
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        
        assert response.success is True
        assert response.status == OrderStatus.SUBMITTED
        assert response.broker_order_id.startswith("SSI_")
    
    def test_submit_order_paper_requires_price(self, paper_config):
        """Test PAPER mode requires current_price."""
        router = OrderRouter(paper_config)
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )
        
        response = router.submit_order(order, current_price=None)
        
        assert response.success is False
        assert response.status == OrderStatus.REJECTED
        assert response.error_code == "MISSING_PRICE"
    
    def test_get_order_status_paper(self, paper_config):
        """Test getting order status from PAPER engine."""
        router = OrderRouter(paper_config)
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        status = router.get_order_status(response.broker_order_id)
        
        assert status.status == OrderStatus.FILLED
        assert status.filled_quantity == 100
    
    def test_cancel_order_paper(self, paper_config):
        """Test cancelling order in PAPER engine."""
        router = OrderRouter(paper_config)
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        
        # Manually set the status to SUBMITTED so it can be cancelled
        router.paper_engine.orders[response.broker_order_id]["status"] = OrderStatus.SUBMITTED
        
        cancel_response = router.cancel_order(response.broker_order_id)
        
        assert cancel_response.success is True
        assert cancel_response.status == OrderStatus.CANCELLED
    
    def test_fallback_to_paper_on_live_failure(self, live_config):
        """Test fallback to PAPER when LIVE gateway fails."""
        router = OrderRouter(live_config)
        
        # Simulate SSI gateway failure by mocking
        with patch.object(router.ssi_gateway, 'submit_order') as mock_submit:
            mock_submit.side_effect = Exception("Connection timeout")
            
            order = BrokerOrder(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.MARKET,
                price=100000.0
            )
            
            response = router.submit_order(order, current_price=100000.0)
            
            # Should fallback to PAPER
            assert response.success is True
            assert "FALLBACK" in response.message
            assert response.broker_order_id.startswith("PAPER_")


class TestSSIBrokerGateway:
    """Tests for SSI Broker Gateway."""
    
    def test_ssi_authentication(self):
        """Test SSI broker authentication."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        gateway = SSIBrokerGateway(credentials)
        
        result = gateway.authenticate()
        
        assert result is True
        assert gateway.authenticated is True
        assert gateway._session_token is not None
    
    def test_ssi_submit_order(self):
        """Test SSI order submission."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        gateway = SSIBrokerGateway(credentials)
        gateway.authenticate()
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = gateway.submit_order(order)
        
        assert response.success is True
        assert response.status == OrderStatus.SUBMITTED
        assert response.broker_order_id.startswith("SSI_")
    
    def test_ssi_order_status(self):
        """Test SSI order status lookup."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        gateway = SSIBrokerGateway(credentials)
        
        status = gateway.get_order_status("SSI_1234567890")
        
        assert status.status == OrderStatus.SUBMITTED
        assert status.filled_quantity == 0
    
    def test_ssi_cancel_order(self):
        """Test SSI order cancellation."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.com.vn"
        )
        gateway = SSIBrokerGateway(credentials)
        
        response = gateway.cancel_order("SSI_1234567890")
        
        assert response.success is True
        assert response.status == OrderStatus.CANCELLED
