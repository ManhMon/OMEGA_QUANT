"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Broker Gateway Tests

Tests for VNDirectBroker and shared BrokerGateway infrastructure.
SSI broker tests live in test_order_router.py — not duplicated here.

Author: Backend Engineer (Role 09)
Date: 2026-05-23
Version: 1.0.0
Requirement: FUNCTIONALITY_GAP_ANALYSIS_20260523.md § Phase 4 – VNDirect integration
"""

import pytest
import logging

from omega.execution import (
    BrokerCredentials,
    BrokerOrder,
    BrokerOrderResponse,
    BrokerOrderStatus,
    OrderSide,
    OrderType,
    OrderStatus,
    VNDirectBroker,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def vndirect_credentials():
    """Valid VNDirect credentials fixture."""
    return BrokerCredentials(
        broker_name="VNDIRECT",
        api_key="TEST_VND_KEY",
        api_secret="TEST_VND_SECRET",
        account_id="VND_ACCT_001",
        base_url="https://api.vndirect.com.vn",
    )


@pytest.fixture
def gateway(vndirect_credentials):
    """Authenticated VNDirectBroker fixture."""
    gw = VNDirectBroker(vndirect_credentials)
    gw.authenticate()
    return gw


@pytest.fixture
def limit_order():
    """Standard board-lot LIMIT order fixture."""
    return BrokerOrder(
        symbol="VIC",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        price=45000.0,
    )


@pytest.fixture
def market_order():
    """Standard board-lot MARKET order fixture."""
    return BrokerOrder(
        symbol="VHM",
        side=OrderSide.SELL,
        quantity=200,
        order_type=OrderType.MARKET,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestVNDirectAuthentication:
    """Tests for VNDirectBroker.authenticate()."""

    def test_authenticate_success(self, vndirect_credentials):
        """Valid credentials produce authenticated state and session token."""
        gw = VNDirectBroker(vndirect_credentials)
        result = gw.authenticate()

        assert result is True
        assert gw.authenticated is True
        assert gw._session_token is not None
        assert "VNDIRECT_TOKEN" in gw._session_token

    def test_authenticate_sets_session_token(self, vndirect_credentials):
        """Session token encodes account ID."""
        gw = VNDirectBroker(vndirect_credentials)
        gw.authenticate()

        assert vndirect_credentials.account_id in gw._session_token

    def test_authenticate_missing_api_key_fails(self):
        """Empty api_key raises ValueError from BrokerCredentials."""
        with pytest.raises(ValueError):
            BrokerCredentials(
                broker_name="VNDIRECT",
                api_key="",
                api_secret="SECRET",
                account_id="ACCT",
                base_url="https://api.vndirect.com.vn",
            )

    def test_authenticate_missing_api_secret_fails(self):
        """Empty api_secret raises ValueError from BrokerCredentials."""
        with pytest.raises(ValueError):
            BrokerCredentials(
                broker_name="VNDIRECT",
                api_key="KEY",
                api_secret="",
                account_id="ACCT",
                base_url="https://api.vndirect.com.vn",
            )


# ---------------------------------------------------------------------------
# Order submission
# ---------------------------------------------------------------------------

class TestVNDirectSubmitOrder:
    """Tests for VNDirectBroker.submit_order()."""

    def test_submit_limit_order_success(self, gateway, limit_order):
        """LIMIT order returns success with VNDIRECT_ prefixed broker ID."""
        response = gateway.submit_order(limit_order)

        assert isinstance(response, BrokerOrderResponse)
        assert response.success is True
        assert response.status == OrderStatus.SUBMITTED
        assert response.broker_order_id.startswith("VNDIRECT_")
        assert response.client_order_id == limit_order.client_order_id

    def test_submit_market_order_success(self, gateway, market_order):
        """MARKET order returns success with VNDIRECT_ prefixed broker ID."""
        response = gateway.submit_order(market_order)

        assert response.success is True
        assert response.status == OrderStatus.SUBMITTED
        assert response.broker_order_id.startswith("VNDIRECT_")

    def test_submit_order_lazy_auth(self, vndirect_credentials, limit_order):
        """Unauthenticated gateway authenticates lazily on first submit."""
        gw = VNDirectBroker(vndirect_credentials)
        assert gw.authenticated is False

        response = gw.submit_order(limit_order)

        assert response.success is True
        assert gw.authenticated is True

    def test_submit_order_rejected_when_not_authenticated(self, limit_order):
        """Gateway with bad credentials returns REJECTED on submit."""
        # Construct a gateway that will fail auth by patching credentials
        # after construction (bypassing __post_init__ validation).
        creds = BrokerCredentials(
            broker_name="VNDIRECT",
            api_key="KEY",
            api_secret="SECRET",
            account_id="ACCT",
            base_url="https://api.vndirect.com.vn",
        )
        gw = VNDirectBroker(creds)
        # Force auth to fail by clearing keys post-init
        gw.credentials.api_key = ""
        gw.credentials.api_secret = ""

        response = gw.submit_order(limit_order)

        assert response.success is False
        assert response.status == OrderStatus.REJECTED
        assert response.error_code == "NOT_AUTHENTICATED"

    def test_submit_order_compliance_violation_odd_lot(self, gateway):
        """Order with non-board-lot quantity is rejected by compliance check."""
        # BrokerOrder.__post_init__ rounds to board-lot, so force a bad
        # quantity after construction with allow_odd_lot=False (default).
        order = BrokerOrder(
            symbol="VIC",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=45000.0,
        )
        # Force non-board-lot quantity after __post_init__ validation
        order.quantity = 150  # not divisible by 100

        response = gateway.submit_order(order)

        assert response.success is False
        assert response.status == OrderStatus.REJECTED
        assert response.error_code == "COMPLIANCE_VIOLATION"

    def test_submit_order_response_has_timestamp(self, gateway, limit_order):
        """Submitted order response includes a timestamp."""
        response = gateway.submit_order(limit_order)

        assert response.timestamp is not None
        assert response.timestamp > 0

    def test_submit_sell_order(self, gateway):
        """SELL order is accepted and returns correct side context."""
        order = BrokerOrder(
            symbol="HPG",
            side=OrderSide.SELL,
            quantity=300,
            order_type=OrderType.LIMIT,
            price=28000.0,
        )
        response = gateway.submit_order(order)

        assert response.success is True
        assert response.status == OrderStatus.SUBMITTED

    def test_submit_multiple_orders_unique_broker_ids(self, gateway, limit_order, market_order):
        """Each submitted order receives a unique broker order ID."""
        r1 = gateway.submit_order(limit_order)
        r2 = gateway.submit_order(market_order)

        assert r1.broker_order_id != r2.broker_order_id


# ---------------------------------------------------------------------------
# Order status
# ---------------------------------------------------------------------------

class TestVNDirectOrderStatus:
    """Tests for VNDirectBroker.get_order_status()."""

    def test_get_order_status_returns_submitted(self, gateway):
        """Mock status lookup returns SUBMITTED state."""
        status = gateway.get_order_status("VNDIRECT_1234567890")

        assert isinstance(status, BrokerOrderStatus)
        assert status.status == OrderStatus.SUBMITTED
        assert status.broker_order_id == "VNDIRECT_1234567890"

    def test_get_order_status_zero_filled(self, gateway):
        """Mock status shows no fills yet."""
        status = gateway.get_order_status("VNDIRECT_9999999999")

        assert status.filled_quantity == 0
        assert status.remaining_quantity == 100

    def test_get_order_status_has_timestamp(self, gateway):
        """Status response includes last_update_time."""
        status = gateway.get_order_status("VNDIRECT_1234567890")

        assert status.last_update_time is not None
        assert status.last_update_time > 0


# ---------------------------------------------------------------------------
# Order cancellation
# ---------------------------------------------------------------------------

class TestVNDirectCancelOrder:
    """Tests for VNDirectBroker.cancel_order()."""

    def test_cancel_order_success(self, gateway):
        """Cancel returns success with CANCELLED status."""
        response = gateway.cancel_order("VNDIRECT_1234567890")

        assert isinstance(response, BrokerOrderResponse)
        assert response.success is True
        assert response.status == OrderStatus.CANCELLED
        assert response.broker_order_id == "VNDIRECT_1234567890"

    def test_cancel_order_has_timestamp(self, gateway):
        """Cancel response includes a timestamp."""
        response = gateway.cancel_order("VNDIRECT_1234567890")

        assert response.timestamp is not None
        assert response.timestamp > 0

    def test_cancel_order_message_present(self, gateway):
        """Cancel response includes a human-readable message."""
        response = gateway.cancel_order("VNDIRECT_1234567890")

        assert response.message is not None
        assert len(response.message) > 0


# ---------------------------------------------------------------------------
# Compliance validation (shared base-class logic via VNDirect)
# ---------------------------------------------------------------------------

class TestVNDirectComplianceValidation:
    """Tests for validate_order_compliance() exercised through VNDirectBroker."""

    def test_valid_limit_order_passes(self, gateway, limit_order):
        """Board-lot LIMIT order passes compliance."""
        ok, reason = gateway.validate_order_compliance(limit_order)

        assert ok is True
        assert reason is None

    def test_limit_order_missing_price_fails(self, gateway):
        """LIMIT order with no price fails compliance."""
        order = BrokerOrder(
            symbol="VIC",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=45000.0,
        )
        order.price = None  # bypass __post_init__ guard

        ok, reason = gateway.validate_order_compliance(order)

        assert ok is False
        assert reason is not None

    def test_non_board_lot_fails_compliance(self, gateway):
        """Quantity not divisible by 100 fails compliance (allow_odd_lot=False)."""
        order = BrokerOrder(
            symbol="VIC",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        order.quantity = 150  # force non-board-lot after construction

        ok, reason = gateway.validate_order_compliance(order)

        assert ok is False
        assert "board-lot" in reason.lower()
