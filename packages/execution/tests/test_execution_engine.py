"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Execution Engine Orchestrator Tests

Tests for ExecutionEngine orchestrating full signal-to-order workflow
with retries, state machine, and paper fallback.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from omega.execution import (
    TradingMode,
    ExecutionEngineConfig,
    ExecutionEngine,
    OrderStatus,
    OrderSide,
)


class TestExecutionEngine:
    """Tests for ExecutionEngine class."""
    
    @pytest.fixture
    def mock_market_data(self):
        """Mock current prices, ADVs and order books."""
        prices = {"VNM": 50.0, "HPG": 25.0}
        advs = {"VNM": 100000.0, "HPG": 500000.0}
        
        books = {
            "VNM": {
                "bids": [{"price": 49.9, "volume": 5000}],
                "asks": [{"price": 50.1, "volume": 5000}],
            }
        }
        return prices, advs, books
    
    def test_workflow_generation_and_execution_paper(self, mock_market_data):
        """Test complete workflow execution in PAPER mode."""
        prices, advs, books = mock_market_data
        
        target = {"VNM": {"quantity": 1000}, "HPG": {"quantity": 2000}}
        current = {"VNM": {"quantity": 500}, "HPG": {"quantity": 2500}}
        
        # Initializing engine in PAPER mode
        config = ExecutionEngineConfig(mode=TradingMode.PAPER)
        engine = ExecutionEngine(config)
        
        summary = engine.execute_workflow(
            target_portfolio=target,
            current_portfolio=current,
            current_prices={
                "data": prices,
                "timestamp": 1716000000.0,
                "provenance": "unit-test-prices",
            },
            adv_data=advs,
            order_books={
                "data": books,
                "timestamp": 1716000001.0,
                "provenance": "unit-test-books",
            }
        )
        
        assert summary["success"] is True
        assert summary["mode"] == "PAPER"
        
        orders = summary["orders"]
        assert len(orders) == 2
        
        vnm_order = next(o for o in orders if o["symbol"] == "VNM")
        assert vnm_order["success"] is True
        assert vnm_order["status"] == OrderStatus.FILLED
        assert vnm_order["broker_order_id"].startswith("PAPER_")
        
        hpg_order = next(o for o in orders if o["symbol"] == "HPG")
        assert hpg_order["success"] is True
        assert hpg_order["status"] == OrderStatus.FILLED
        
        # Verify metrics updated
        metrics = summary["metrics"]
        assert metrics["total_submitted"] == 2
        assert metrics["total_filled"] == 2
        assert metrics["average_slippage_bps"] > 0.0
    
    def test_submit_order_with_retry_success(self, mock_market_data):
        """Test submission success on transient failures after retry."""
        prices, advs, books = mock_market_data
        
        config = ExecutionEngineConfig(mode=TradingMode.PAPER, max_retries=3, retry_delay_seconds=0.01)
        engine = ExecutionEngine(config)
        
        order = engine.order_generator.convert_signal_to_order(
            symbol="VNM",
            signal_weight=0.05,
            portfolio_value=100_000_000.0,
            current_price=50.0
        )
        
        # Mocking router submit_order to fail once then succeed
        failures = [0]
        original_submit = engine.router.submit_order
        
        def mock_submit(*args, **kwargs):
            if failures[0] < 1:
                failures[0] += 1
                raise ConnectionError("Temporary SSI connection issue")
            return original_submit(*args, **kwargs)
            
        with patch.object(engine.router, 'submit_order', side_effect=mock_submit):
            response = engine._submit_order_with_retry_and_fallback(order, current_price=50.0)
            
            assert response.success is True
            assert response.status == OrderStatus.FILLED
            assert engine.execution_metrics["total_retries"] == 1

    def test_workflow_summary_fails_when_any_order_fails(self, mock_market_data):
        """Workflow summary must fail if any child order fails."""
        prices, advs, books = mock_market_data

        config = ExecutionEngineConfig(mode=TradingMode.PAPER)
        engine = ExecutionEngine(config)

        with patch.object(engine, '_submit_order_with_retry_and_fallback') as mock_submit:
            mock_submit.side_effect = [
                MagicMock(
                    success=True,
                    broker_order_id="PAPER_1",
                    client_order_id="OK_1",
                    status=OrderStatus.FILLED,
                    message="filled",
                    error_code=None,
                ),
                MagicMock(
                    success=False,
                    broker_order_id=None,
                    client_order_id="BAD_1",
                    status=OrderStatus.REJECTED,
                    message="rejected",
                    error_code="MISSING_PRICE",
                ),
            ]

            summary = engine.execute_workflow(
                target_portfolio={"VNM": {"quantity": 1000}, "HPG": {"quantity": 2000}},
                current_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 2500}},
                current_prices={
                    "data": prices,
                    "timestamp": 1716000000.0,
                    "provenance": "unit-test-prices",
                },
                adv_data=advs,
                order_books={
                    "data": books,
                    "timestamp": 1716000001.0,
                    "provenance": "unit-test-books",
                },
            )

        assert summary["success"] is False
        assert any(order["success"] is False for order in summary["orders"])

    def test_liquidity_assessment_uses_absolute_sell_quantity(self, mock_market_data):
        """Sell liquidity path must pass negative size into analyzer for sells."""
        prices, advs, books = mock_market_data

        config = ExecutionEngineConfig(mode=TradingMode.PAPER)
        engine = ExecutionEngine(config)

        with patch.object(engine.order_book_analyzer, 'assess_liquidity', wraps=engine.order_book_analyzer.assess_liquidity) as mock_liq:
            engine.execute_workflow(
                target_portfolio={"VNM": {"quantity": 0}},
                current_portfolio={"VNM": {"quantity": 500}},
                current_prices={
                    "data": prices,
                    "timestamp": 1716000000.0,
                    "provenance": "unit-test-prices",
                },
                adv_data=advs,
                order_books={
                    "data": books,
                    "timestamp": 1716000001.0,
                    "provenance": "unit-test-books",
                },
            )

        assert mock_liq.call_args[0][2] == -500

    def test_workflow_requires_current_prices_metadata(self, mock_market_data):
        """current_prices contract must include timestamp and provenance."""
        prices, _, _ = mock_market_data

        engine = ExecutionEngine(ExecutionEngineConfig(mode=TradingMode.PAPER))

        with pytest.raises(ValueError, match="current_prices must include data, timestamp, and provenance"):
            engine.execute_workflow(
                target_portfolio={"VNM": {"quantity": 1000}},
                current_portfolio={"VNM": {"quantity": 500}},
                current_prices=prices,
            )

    def test_workflow_requires_order_books_metadata_when_enveloped(self, mock_market_data):
        """order_books envelope must include timestamp and provenance."""
        prices, _, books = mock_market_data

        engine = ExecutionEngine(ExecutionEngineConfig(mode=TradingMode.PAPER))

        with pytest.raises(ValueError, match="order_books must include data, timestamp, and provenance"):
            engine.execute_workflow(
                target_portfolio={"VNM": {"quantity": 1000}},
                current_portfolio={"VNM": {"quantity": 500}},
                current_prices={
                    "data": prices,
                    "timestamp": 1716000000.0,
                    "provenance": "unit-test-prices",
                },
                order_books={"data": books},
            )

    def test_workflow_executes_odd_lot_liquidation_without_uprounding(self, mock_market_data):
        """Odd-lot liquidation should remain exact through BrokerOrder and paper fill."""
        prices, _, _ = mock_market_data

        engine = ExecutionEngine(ExecutionEngineConfig(mode=TradingMode.PAPER))

        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 75}},
            current_prices={
                "data": prices,
                "timestamp": 1716000000.0,
                "provenance": "unit-test-prices",
            },
        )

        assert summary["success"] is True
        assert summary["orders"][0]["symbol"] == "VNM"
        assert summary["orders"][0]["status"] == OrderStatus.FILLED
        broker_order_id = summary["orders"][0]["broker_order_id"]
        assert engine.active_orders[broker_order_id].quantity == 75
    
    def test_live_failure_fallback_to_paper(self, mock_market_data):
        """Test live failure triggers paper trading fallback."""
        prices, advs, books = mock_market_data
        
        # Setting config to LIVE with fallback
        config = ExecutionEngineConfig(mode=TradingMode.LIVE, max_retries=2, retry_delay_seconds=0.01)
        engine = ExecutionEngine(config)
        engine.router.config.fallback_to_paper = True
        
        order = engine.order_generator.convert_signal_to_order(
            symbol="VNM",
            signal_weight=0.05,
            portfolio_value=100_000_000.0,
            current_price=50.0
        )
        
        # Force SSI live submit to fail completely
        with patch.object(engine.router, 'submit_order') as mock_submit:
            mock_submit.side_effect = Exception("SSI Broker down")
            
            response = engine._submit_order_with_retry_and_fallback(order, current_price=50.0)
            
            assert response.success is True
            assert "FALLBACK" in response.message
            assert response.broker_order_id.startswith("PAPER_")
            assert engine.execution_metrics["total_fallbacks"] == 1
            assert engine.execution_metrics["total_retries"] == 2

    def test_workflow_rejects_future_timestamps_pit_safety(self, mock_market_data):
        """Workflow must reject future timestamps in market data envelopes (PIT Safety)."""
        prices, advs, books = mock_market_data
        config = ExecutionEngineConfig(mode=TradingMode.PAPER)
        engine = ExecutionEngine(config)
        
        future_ts = time.time() + 3600.0  # 1 hour in future
        
        with pytest.raises(ValueError, match="PIT Safety violation"):
            engine.execute_workflow(
                target_portfolio={"VNM": {"quantity": 100}},
                current_portfolio={},
                current_prices={
                    "data": prices,
                    "timestamp": future_ts,
                    "provenance": "future-prices"
                },
                adv_data=advs
            )

    def test_live_fallback_fails_when_current_price_missing(self):
        """Fallback to paper trading must fail if current price is missing."""
        config = ExecutionEngineConfig(mode=TradingMode.LIVE, max_retries=1, retry_delay_seconds=0.0)
        engine = ExecutionEngine(config)
        engine.router.config.fallback_to_paper = True
        
        order = engine.order_generator.convert_signal_to_order(
            symbol="VNM",
            signal_weight=0.05,
            portfolio_value=100_000_000.0,
            current_price=50.0
        )
        
        with patch.object(engine.router, 'submit_order', side_effect=Exception("SSI Broker down")):
            response = engine._submit_order_with_retry_and_fallback(order, current_price=None)
            assert response.success is False
            assert response.status == OrderStatus.REJECTED
            assert response.error_code == "MISSING_PRICE"
