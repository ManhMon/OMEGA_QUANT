"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3 / Phase 16: Order Router Tests

Tests for OrderRouter with PAPER/LIVE routing, fallback logic,
latency simulation, and liquidation exposure tracking.

Author: QA Engineer (Role 17)
Date: 2026-05-24
Version: 1.1.0
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
    LatencyConfig,
    LiquidationExposure,
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
            
    def test_pov_routing_splits_order(self, paper_config):
        """Test POV routing reduces initial order size based on historical profile."""
        router = OrderRouter(paper_config)
        router.volume_profile_enabled = True
        router.minimum_lot_size = 100
        router.historical_volume_profiles = {"VNM": [0.1]} # 10% for first period
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=10000, # Large enough to trigger POV (10 * min_lot)
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        
        # First chunk should be 10000 * 0.1 = 1000
        assert response.success is True
        assert order.quantity == 1000
        
    def test_pov_routing_minimum_lot_size(self, paper_config):
        """Test POV routing respects minimum lot sizes."""
        router = OrderRouter(paper_config)
        router.volume_profile_enabled = True
        router.minimum_lot_size = 100
        router.historical_volume_profiles = {"VNM": [0.01]} # 1% for first period
        
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=1000, # Large enough to trigger POV
            order_type=OrderType.MARKET,
            price=100000.0
        )
        
        response = router.submit_order(order, current_price=100000.0)
        
        # Target chunk 1000 * 0.01 = 10. But min lot size is 100.
        # Max(100, (10//100)*100) = Max(100, 0) = 100
        assert response.success is True
        assert order.quantity == 100


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


class TestLatencySimulation:
    """Phase 16: Tests for configurable latency simulation in OrderRouter."""

    def _no_latency_config(self) -> OrderRouterConfig:
        """Paper config with latency simulation disabled (fast tests)."""
        return OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=False,
        )

    def _seeded_latency_config(self, base_ms: float = 5.0, std_ms: float = 0.0) -> OrderRouterConfig:
        """Paper config with deterministic latency (std=0 → exact base_ms)."""
        return OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=True,
            latency_config=LatencyConfig(
                paper_base_ms=base_ms,
                paper_std_ms=std_ms,
                rng_seed=42,
            ),
        )

    def test_latency_disabled_returns_zero(self):
        """When simulate_latency=False, _simulate_latency returns 0.0 and no sleep occurs."""
        router = OrderRouter(self._no_latency_config())
        result = router._simulate_latency()
        assert result == 0.0
        assert router._latency_samples == []

    def test_latency_sample_recorded(self):
        """Each _simulate_latency call appends a sample."""
        router = OrderRouter(self._seeded_latency_config(base_ms=5.0, std_ms=0.0))
        router._simulate_latency()
        assert len(router._latency_samples) == 1
        assert abs(router._latency_samples[0] - 5.0) < 0.01

    def test_get_average_latency_ms_empty(self):
        """get_average_latency_ms returns 0.0 when no samples recorded."""
        router = OrderRouter(self._no_latency_config())
        assert router.get_average_latency_ms() == 0.0

    def test_get_average_latency_ms_after_submissions(self):
        """Average latency is computed correctly across multiple submissions."""
        router = OrderRouter(self._seeded_latency_config(base_ms=10.0, std_ms=0.0))
        order = BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=50000.0,
        )
        router.submit_order(order, current_price=50000.0)
        router.submit_order(order, current_price=50000.0)
        avg = router.get_average_latency_ms()
        assert abs(avg - 10.0) < 0.5  # std=0 so both samples ≈ 10 ms

    def test_latency_clipped_to_zero(self):
        """Negative Gaussian samples are clipped to 0.0."""
        # base=0, std=0 → always 0
        router = OrderRouter(self._seeded_latency_config(base_ms=0.0, std_ms=0.0))
        result = router._simulate_latency()
        assert result >= 0.0

    def test_live_mode_uses_live_latency_params(self):
        """Live mode samples from live_base_ms / live_std_ms."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="K",
            api_secret="S",
            account_id="A",
            base_url="https://api.ssi.com.vn",
        )
        cfg = OrderRouterConfig(
            mode=TradingMode.LIVE,
            ssi_credentials=credentials,
            simulate_latency=True,
            latency_config=LatencyConfig(
                live_base_ms=50.0,
                live_std_ms=0.0,
                rng_seed=0,
            ),
        )
        router = OrderRouter(cfg)
        result = router._simulate_latency()
        assert abs(result - 50.0) < 0.5


class TestLiquidationExposure:
    """Phase 16: Tests for per-symbol liquidation exposure tracking in OrderRouter."""

    @pytest.fixture
    def router(self):
        return OrderRouter(OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=False,
        ))

    def test_update_creates_new_exposure(self, router):
        """update_liquidation_exposure creates a new entry for an unknown symbol."""
        exp = router.update_liquidation_exposure(
            symbol="VNM",
            is_liquidating=True,
            remaining_qty=500,
            current_price=50000.0,
            submitted_qty=500,
        )
        assert exp.symbol == "VNM"
        assert exp.is_liquidating is True
        assert exp.remaining_qty == 500
        assert exp.notional_value == 500 * 50000.0
        assert exp.submitted_qty == 500

    def test_update_accumulates_submitted_qty(self, router):
        """Repeated calls accumulate submitted_qty."""
        router.update_liquidation_exposure("VNM", True, 500, 50000.0, submitted_qty=200)
        router.update_liquidation_exposure("VNM", True, 300, 50000.0, submitted_qty=200)
        exp = router.get_liquidation_exposure("VNM")
        assert exp.submitted_qty == 400

    def test_gross_exposure_sums_active_symbols(self, router):
        """Gross exposure is the sum of notional across all is_liquidating=True symbols."""
        router.update_liquidation_exposure("VNM", True, 500, 50000.0)
        router.update_liquidation_exposure("HPG", True, 1000, 25000.0)
        gross = router.get_total_gross_liquidation_exposure()
        assert gross == 500 * 50000.0 + 1000 * 25000.0

    def test_gross_exposure_excludes_completed_liquidations(self, router):
        """Symbols with is_liquidating=False are excluded from gross exposure."""
        router.update_liquidation_exposure("VNM", True, 500, 50000.0)
        router.update_liquidation_exposure("HPG", False, 0, 25000.0)
        gross = router.get_total_gross_liquidation_exposure()
        assert gross == 500 * 50000.0

    def test_get_liquidation_exposure_unknown_symbol_returns_none(self, router):
        """get_liquidation_exposure returns None for symbols never registered."""
        assert router.get_liquidation_exposure("UNKNOWN") is None

    def test_zero_price_yields_zero_notional(self, router):
        """Zero current_price produces zero notional (avoids division errors)."""
        exp = router.update_liquidation_exposure("VNM", True, 500, 0.0)
        assert exp.notional_value == 0.0

    def test_gross_exposure_field_updated_on_all_entries(self, router):
        """gross_exposure field on each entry reflects the aggregate total."""
        router.update_liquidation_exposure("VNM", True, 100, 10.0)
        router.update_liquidation_exposure("HPG", True, 200, 5.0)
        vnm = router.get_liquidation_exposure("VNM")
        hpg = router.get_liquidation_exposure("HPG")
        expected = 100 * 10.0 + 200 * 5.0
        assert vnm.gross_exposure == expected
        assert hpg.gross_exposure == expected


class TestSwitchModeConfigSync:
    """Fix 1: switch_mode() must keep config.mode in sync with self.mode."""

    def test_switch_to_paper_syncs_config_mode(self):
        """After switching LIVE→PAPER, config.mode must equal PAPER."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="K",
            api_secret="S",
            account_id="A",
            base_url="https://api.ssi.com.vn",
        )
        cfg = OrderRouterConfig(
            mode=TradingMode.LIVE,
            ssi_credentials=credentials,
            simulate_latency=False,
        )
        router = OrderRouter(cfg)
        assert router.mode == TradingMode.LIVE
        assert router.config.mode == TradingMode.LIVE

        router.switch_mode(TradingMode.PAPER)

        assert router.mode == TradingMode.PAPER
        assert router.config.mode == TradingMode.PAPER

    def test_switch_to_live_syncs_config_mode(self):
        """After switching PAPER→LIVE, config.mode must equal LIVE."""
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="K",
            api_secret="S",
            account_id="A",
            base_url="https://api.ssi.com.vn",
        )
        cfg = OrderRouterConfig(
            mode=TradingMode.PAPER,
            ssi_credentials=credentials,
            simulate_latency=False,
        )
        router = OrderRouter(cfg)
        router.switch_mode(TradingMode.LIVE)

        assert router.mode == TradingMode.LIVE
        assert router.config.mode == TradingMode.LIVE

    def test_switch_live_without_credentials_falls_back_and_syncs(self):
        """Switching to LIVE with no credentials falls back to PAPER; config.mode must reflect PAPER."""
        cfg = OrderRouterConfig(
            mode=TradingMode.PAPER,
            ssi_credentials=None,
            simulate_latency=False,
        )
        router = OrderRouter(cfg)
        router.switch_mode(TradingMode.LIVE)

        # _switch_mode silently falls back to PAPER when no credentials
        assert router.mode == TradingMode.PAPER
        assert router.config.mode == TradingMode.PAPER


class TestGatewayProvenance:
    """Fix 4: Explicit gateway provenance tracking replaces startswith heuristic."""

    @pytest.fixture
    def paper_router(self):
        return OrderRouter(OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=False,
        ))

    @pytest.fixture
    def live_router(self):
        credentials = BrokerCredentials(
            broker_name="SSI",
            api_key="K",
            api_secret="S",
            account_id="A",
            base_url="https://api.ssi.com.vn",
        )
        return OrderRouter(OrderRouterConfig(
            mode=TradingMode.LIVE,
            ssi_credentials=credentials,
            simulate_latency=False,
        ))

    def _make_order(self) -> BrokerOrder:
        return BrokerOrder(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=50000.0,
        )

    def test_paper_submission_records_paper_provenance(self, paper_router):
        """Paper submission must record 'PAPER' in _order_gateway_map."""
        response = paper_router.submit_order(self._make_order(), current_price=50000.0)
        assert response.success is True
        assert paper_router._order_gateway_map[response.broker_order_id] == "PAPER"

    def test_live_submission_records_ssi_provenance(self, live_router):
        """Live submission must record 'SSI' in _order_gateway_map."""
        response = live_router.submit_order(self._make_order(), current_price=50000.0)
        assert response.success is True
        assert live_router._order_gateway_map[response.broker_order_id] == "SSI"

    def test_fallback_submission_records_paper_provenance(self, live_router):
        """Fallback-to-paper submission must record 'PAPER' provenance."""
        with patch.object(live_router.ssi_gateway, "submit_order", side_effect=Exception("down")):
            response = live_router.submit_order(self._make_order(), current_price=50000.0)
        assert response.success is True
        assert "FALLBACK" in response.message
        assert live_router._order_gateway_map[response.broker_order_id] == "PAPER"

    def test_get_order_status_uses_provenance_not_prefix(self, paper_router):
        """get_order_status dispatches via provenance map, not broker_order_id prefix."""
        response = paper_router.submit_order(self._make_order(), current_price=50000.0)
        # Manually corrupt the broker_order_id prefix to prove prefix is NOT used
        old_id = response.broker_order_id
        new_id = "SSI_FAKE_" + old_id  # Would route to SSI under old heuristic
        paper_router.paper_engine.orders[new_id] = paper_router.paper_engine.orders.pop(old_id)
        paper_router._order_gateway_map[new_id] = "PAPER"

        status = paper_router.get_order_status(new_id)
        assert status.status == OrderStatus.FILLED

    def test_cancel_order_uses_provenance_not_prefix(self, paper_router):
        """cancel_order dispatches via provenance map, not broker_order_id prefix."""
        response = paper_router.submit_order(self._make_order(), current_price=50000.0)
        old_id = response.broker_order_id
        new_id = "SSI_FAKE_" + old_id
        paper_router.paper_engine.orders[new_id] = paper_router.paper_engine.orders.pop(old_id)
        paper_router.paper_engine.orders[new_id]["status"] = OrderStatus.SUBMITTED
        paper_router._order_gateway_map[new_id] = "PAPER"

        cancel = paper_router.cancel_order(new_id)
        assert cancel.success is True
        assert cancel.status == OrderStatus.CANCELLED

    def test_unknown_provenance_falls_back_to_current_gateway(self, paper_router):
        """Orders with no provenance entry fall back to current gateway dispatch."""
        # Submit an order but then remove its provenance entry
        response = paper_router.submit_order(self._make_order(), current_price=50000.0)
        del paper_router._order_gateway_map[response.broker_order_id]

        # Should still work via current-gateway fallback (PAPER mode)
        status = paper_router.get_order_status(response.broker_order_id)
        assert status.status == OrderStatus.FILLED
