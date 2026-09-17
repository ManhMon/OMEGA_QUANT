"""
OMEGA_QUANT Live Trading Pipeline Tests (Layer 03)
Phase 16.4: Live Trading Pipeline Safety Tests

Tests for:
- Kill switch blocks order submission (pre-routing and pre-execution)
- PreTradeGate rejection blocks order submission
- Normal order flows through full pipeline successfully
- RealtimeRiskGuard rejection still blocks orders

Author: System Architect (Role 06)
Date: 2026-06-13
Version: 1.0.0
Gate: PHASE3_PHASE4_PHASE5_DEEP_AUDIT_FIX1_20260613
"""

import pytest
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

from omega.execution.live_trading_pipeline import (
    LiveTradingPipeline,
    PipelineResult,
    PipelineState,
)
from omega.quant.execution.multi_symbol_router import MultiSymbolRouter, BrokerType
from omega.quant.risk.realtime_risk import RealtimeRiskGuard, RiskVerdict
from omega.quant.execution.live_bridge import (
    LiveExecutionBridge,
    ExecutionOrder,
    ExecutionState,
)
from omega.execution.broker_gateway import OrderSide, OrderType
from omega.execution.pre_trade_controls import PreTradeGate, PositionLimit
from omega.core.sre.kill_switch import KillSwitch, _reset_kill_switch_for_testing


# LIVE-04: helper that uses the guarded API
def _safe_reset_ks():
    _reset_kill_switch_for_testing(auth_token="OMEGA_TEST")


def _make_gate(account_id="default", margin=1_000_000.0):
    """Create a PreTradeGate with sufficient margin for tests (LIVE-02)."""
    gate = PreTradeGate()
    gate.update_margin(account_id, margin)
    return gate


class TestKillSwitchIntegration:
    """Tests proving kill switch blocks order submission."""

    @pytest.fixture(autouse=True)
    def _reset_ks(self):
        """Reset global kill switch singleton before/after each test."""
        _safe_reset_ks()
        yield
        _safe_reset_ks()

    @pytest.fixture
    def mock_router(self):
        router = MagicMock(spec=MultiSymbolRouter)
        router.get_broker_for_symbol.return_value = BrokerType.SSI
        return router

    @pytest.fixture
    def mock_risk_guard(self):
        guard = MagicMock(spec=RealtimeRiskGuard)
        guard.check_order.return_value = RiskVerdict.PASS
        return guard

    @pytest.fixture
    def mock_execution(self):
        bridge = MagicMock(spec=LiveExecutionBridge)
        bridge.submit_order.return_value = ExecutionOrder(
            order_id=str(uuid.uuid4()),
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=None,
            state=ExecutionState.SUBMITTED,
        )
        return bridge

    @pytest.fixture
    def pipeline(self, mock_router, mock_risk_guard, mock_execution):
        return LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=_make_gate(),
        )

    def test_kill_switch_active_blocks_order_before_routing(
        self, pipeline, mock_execution
    ):
        """Kill switch activated BEFORE routing must block order and NOT call execution."""
        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            ks = KillSwitch()
            ks.activate(reason="test_emergency")
            mock_get_ks.return_value = ks

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

            assert result.state == PipelineState.KILL_SWITCH_ACTIVE
            assert result.order_id == ""
            assert "kill switch" in result.error.lower()
            mock_execution.submit_order.assert_not_called()

    def test_kill_switch_active_mid_pipeline_blocks_before_execution(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """Kill switch activated AFTER risk check but BEFORE execution must block order."""
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=_make_gate(),
        )

        # Create a kill switch that starts inactive, activates during pre-trade phase
        ks = KillSwitch()

        call_count = [0]

        def side_effect_is_activated():
            call_count[0] += 1
            # First call (pre-routing): not activated
            # Second call (pre-execution): activated
            if call_count[0] >= 2:
                return True
            return False

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch", return_value=ks
        ):
            with patch.object(
                KillSwitch,
                "is_activated",
                new_callable=PropertyMock,
                side_effect=side_effect_is_activated,
            ):
                result = pipeline.submit_order(
                    symbol="VNM",
                    side=OrderSide.BUY,
                    quantity=100,
                    price=50.0,
                    adv_20d=1_000_000,
                )

        assert result.state == PipelineState.KILL_SWITCH_ACTIVE
        assert result.order_id == ""
        assert "kill switch" in result.error.lower()
        mock_execution.submit_order.assert_not_called()

    def test_kill_switch_not_active_allows_order(
        self, pipeline, mock_execution
    ):
        """When kill switch is NOT active, order proceeds normally."""
        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            ks = KillSwitch()
            mock_get_ks.return_value = ks

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

            assert result.state == PipelineState.COMPLETED
            assert result.order_id != ""
            mock_execution.submit_order.assert_called_once()


class TestPreTradeGateIntegration:
    """Tests proving PreTradeGate rejection blocks order submission."""

    @pytest.fixture(autouse=True)
    def _reset_ks(self):
        _safe_reset_ks()
        yield
        _safe_reset_ks()

    @pytest.fixture
    def mock_router(self):
        router = MagicMock(spec=MultiSymbolRouter)
        router.get_broker_for_symbol.return_value = BrokerType.SSI
        return router

    @pytest.fixture
    def mock_risk_guard(self):
        guard = MagicMock(spec=RealtimeRiskGuard)
        guard.check_order.return_value = RiskVerdict.PASS
        return guard

    @pytest.fixture
    def mock_execution(self):
        bridge = MagicMock(spec=LiveExecutionBridge)
        bridge.submit_order.return_value = ExecutionOrder(
            order_id=str(uuid.uuid4()),
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=None,
            state=ExecutionState.SUBMITTED,
        )
        return bridge

    def test_pre_trade_gate_restricted_symbol_blocks_execution(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """PreTradeGate rejecting restricted symbol must NOT call execution."""
        gate = PreTradeGate(restricted_symbols=["BANNED"])
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=gate,
            account_id="test_acct",
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="BANNED",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.FAILED
        assert "PreTradeGate" in result.error
        assert result.order_id == ""
        mock_execution.submit_order.assert_not_called()

    def test_pre_trade_gate_position_limit_blocks_execution(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """PreTradeGate position limit exceeded must NOT call execution."""
        gate = PreTradeGate(
            position_limits={
                "VNM": PositionLimit(
                    symbol="VNM", max_position=500, max_order_size=200
                )
            }
        )
        # Set current position near limit
        gate.update_position("VNM", 450.0)

        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=gate,
            account_id="test_acct",
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            # Order of 100 would push position to 550, exceeding max_position of 500
            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.FAILED
        assert "PreTradeGate" in result.error
        mock_execution.submit_order.assert_not_called()

    def test_pre_trade_gate_pass_allows_execution(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """PreTradeGate passing all checks allows order to proceed."""
        gate = PreTradeGate()  # No restrictions configured
        gate.update_margin("test_acct", 1_000_000.0)  # LIVE-02: sufficient margin
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=gate,
            account_id="test_acct",
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.COMPLETED
        assert result.order_id != ""
        mock_execution.submit_order.assert_called_once()

    def test_no_pre_trade_gate_configured_blocks_execution(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """LIVE-01: When no PreTradeGate is configured, order must be BLOCKED (fail-closed)."""
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.FAILED
        assert "PreTradeGate not configured" in result.error
        assert result.order_id == ""
        mock_execution.submit_order.assert_not_called()


class TestNormalOrderFlow:
    """Tests proving normal orders execute through full pipeline."""

    @pytest.fixture(autouse=True)
    def _reset_ks(self):
        _safe_reset_ks()
        yield
        _safe_reset_ks()

    @pytest.fixture
    def mock_router(self):
        router = MagicMock(spec=MultiSymbolRouter)
        router.get_broker_for_symbol.return_value = BrokerType.SSI
        return router

    @pytest.fixture
    def mock_risk_guard(self):
        guard = MagicMock(spec=RealtimeRiskGuard)
        guard.check_order.return_value = RiskVerdict.PASS
        return guard

    @pytest.fixture
    def mock_execution(self):
        bridge = MagicMock(spec=LiveExecutionBridge)
        bridge.submit_order.return_value = ExecutionOrder(
            order_id="ORD-12345",
            symbol="FPT",
            side=OrderSide.BUY,
            quantity=500,
            order_type=OrderType.LIMIT,
            price=95.5,
            state=ExecutionState.SUBMITTED,
        )
        return bridge

    def test_full_pipeline_success(self, mock_router, mock_risk_guard, mock_execution):
        """Full pipeline: kill switch off + risk pass + pre-trade pass = order executes."""
        gate = PreTradeGate()
        # Set sufficient margin for the test account
        gate.update_margin("test_acct", 1_000_000.0)
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=gate,
            account_id="test_acct",
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="FPT",
                side=OrderSide.BUY,
                quantity=500,
                price=95.5,
                adv_20d=2_000_000,
                order_type=OrderType.LIMIT,
            )

        assert result.state == PipelineState.COMPLETED
        assert result.order_id == "ORD-12345"
        assert result.verdict == RiskVerdict.PASS
        assert result.execution_orders is not None
        assert len(result.execution_orders) == 1
        mock_execution.submit_order.assert_called_once()

    def test_risk_guard_still_blocks_orders(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """RealtimeRiskGuard rejection still blocks orders (preserves existing behavior)."""
        mock_risk_guard.check_order.return_value = RiskVerdict.FAIL_ADV
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=_make_gate(),
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100_000,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.FAILED
        assert "Risk rejected" in result.error
        assert result.verdict == RiskVerdict.FAIL_ADV
        mock_execution.submit_order.assert_not_called()

    def test_pipeline_handles_execution_exception(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """Pipeline catches execution exceptions and returns FAILED."""
        mock_execution.submit_order.side_effect = RuntimeError("Broker connection lost")
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=_make_gate(),
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="VNM",
                side=OrderSide.BUY,
                quantity=100,
                price=50.0,
                adv_20d=1_000_000,
            )

        assert result.state == PipelineState.FAILED
        assert "Broker connection lost" in result.error

    def test_no_route_defaults_to_ssi(
        self, mock_router, mock_risk_guard, mock_execution
    ):
        """When no explicit route exists, pipeline defaults to SSI broker."""
        mock_router.get_broker_for_symbol.return_value = None
        pipeline = LiveTradingPipeline(
            router=mock_router,
            risk_guard=mock_risk_guard,
            execution=mock_execution,
            pre_trade_gate=_make_gate(),
        )

        with patch(
            "omega.execution.live_trading_pipeline.get_kill_switch"
        ) as mock_get_ks:
            mock_get_ks.return_value = KillSwitch()

            result = pipeline.submit_order(
                symbol="NEW_STOCK",
                side=OrderSide.BUY,
                quantity=100,
                price=30.0,
                adv_20d=500_000,
            )

        assert result.state == PipelineState.COMPLETED
        mock_execution.submit_order.assert_called_once()
