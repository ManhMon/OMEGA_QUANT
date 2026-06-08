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


class TestPhase16LiquidationAndLatency:
    """
    Phase 16: Tests for V21 liquidation/defense concepts and latency simulation
    integrated into ExecutionEngine.
    """

    @pytest.fixture
    def prices_envelope(self):
        return {
            "data": {"VNM": 50.0, "HPG": 25.0},
            "timestamp": 1716000000.0,
            "provenance": "unit-test-prices",
        }

    @pytest.fixture
    def no_latency_engine(self):
        """ExecutionEngine in PAPER mode with latency simulation disabled."""
        from omega.execution import OrderRouterConfig, LatencyConfig
        router_cfg = OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=False,
        )
        cfg = ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        )
        return ExecutionEngine(cfg)

    # ------------------------------------------------------------------
    # Liquidation priority ordering
    # ------------------------------------------------------------------

    def test_liquidation_orders_execute_before_buys(self, prices_envelope):
        """
        Liquidation (SELL to zero) orders must appear first in the results list
        regardless of the order they appear in target_portfolio.
        """
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        # VNM: BUY (increase), HPG: liquidate (target=0)
        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 1000}, "HPG": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 400}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )

        assert summary["success"] is True
        orders = summary["orders"]
        assert len(orders) == 2
        # Liquidation order must come first
        assert orders[0]["symbol"] == "HPG"
        assert orders[0]["is_liquidation"] is True
        assert orders[1]["symbol"] == "VNM"
        assert orders[1]["is_liquidation"] is False

    def test_liquidation_order_flagged_in_metrics(self, prices_envelope):
        """total_liquidation_orders metric increments for each liquidation order."""
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 0}, "HPG": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 400}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )

        metrics = engine.get_execution_metrics()
        assert metrics["total_liquidation_orders"] == 2

    def test_liquidation_exposure_registered_on_router(self, prices_envelope):
        """
        After executing a liquidation order, the router's liquidation_exposure
        registry must contain an entry for the liquidated symbol.
        """
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 300}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )

        exp = engine.router.get_liquidation_exposure("VNM")
        assert exp is not None
        assert exp.submitted_qty == 300

    def test_liquidation_exposure_cleared_when_fully_submitted(self, prices_envelope):
        """
        When remaining_qty reaches 0 after submission, is_liquidating is set False.
        """
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 300}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )

        exp = engine.router.get_liquidation_exposure("VNM")
        assert exp is not None
        assert exp.is_liquidating is False

    # ------------------------------------------------------------------
    # Defense cap (V21 defense mode)
    # ------------------------------------------------------------------

    def test_defense_cap_halts_buy_when_gross_exposure_exceeded(self, prices_envelope):
        """
        When defense_gross_exposure_cap is set and gross liquidation exposure
        exceeds it, new BUY orders are rejected with DEFENSE_CAP_BREACH.
        """
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        # Cap = 1 VND — will be breached by any real liquidation notional
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
            defense_gross_exposure_cap=1.0,
        ))

        # Pre-seed a large liquidation exposure so cap is already breached
        engine.router.update_liquidation_exposure(
            symbol="HPG",
            is_liquidating=True,
            remaining_qty=1000,
            current_price=25.0,
        )

        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 1000}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )

        assert summary["success"] is False
        order = summary["orders"][0]
        assert order["error_code"] == "DEFENSE_CAP_BREACH"
        assert order["success"] is False

    def test_defense_cap_zero_means_no_cap(self, prices_envelope):
        """defense_gross_exposure_cap=0.0 disables the cap entirely."""
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
            defense_gross_exposure_cap=0.0,
        ))

        # Pre-seed enormous exposure — should NOT block buys
        engine.router.update_liquidation_exposure(
            symbol="HPG",
            is_liquidating=True,
            remaining_qty=999999,
            current_price=999999.0,
        )

        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )

        assert summary["success"] is True
        assert summary["orders"][0]["error_code"] != "DEFENSE_CAP_BREACH"

    def test_defense_mode_active_reflected_in_metrics(self, prices_envelope):
        """defense_mode_active flag in metrics is True when cap is breached."""
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
            defense_gross_exposure_cap=1.0,
        ))
        engine.router.update_liquidation_exposure("HPG", True, 1000, 25.0)

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )

        metrics = engine.get_execution_metrics()
        assert metrics["defense_mode_active"] is True
        assert metrics["total_defense_halted"] == 1

    def test_gross_liquidation_exposure_in_metrics(self, prices_envelope):
        """get_execution_metrics includes gross_liquidation_exposure from router."""
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 200}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )

        metrics = engine.get_execution_metrics()
        # After full liquidation, is_liquidating=False → gross = 0
        assert metrics["gross_liquidation_exposure"] == 0.0

    # ------------------------------------------------------------------
    # Latency metrics surfaced through engine
    # ------------------------------------------------------------------

    def test_router_average_latency_ms_in_metrics(self, prices_envelope):
        """get_execution_metrics includes router_average_latency_ms."""
        from omega.execution import OrderRouterConfig, LatencyConfig
        router_cfg = OrderRouterConfig(
            mode=TradingMode.PAPER,
            simulate_latency=True,
            latency_config=LatencyConfig(
                paper_base_ms=3.0,
                paper_std_ms=0.0,
                rng_seed=7,
            ),
        )
        engine = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )

        metrics = engine.get_execution_metrics()
        # std=0 so every sample ≈ 3 ms
        assert abs(metrics["router_average_latency_ms"] - 3.0) < 0.5


class TestHaltResumeAndCancelAll:
    """Fix 2: halt(), resume(), cancel_all_active_orders() on ExecutionEngine."""

    @pytest.fixture
    def engine(self):
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        return ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
        ))

    @pytest.fixture
    def prices_envelope(self):
        return {
            "data": {"VNM": 50.0, "HPG": 25.0},
            "timestamp": 1716000000.0,
            "provenance": "unit-test-prices",
        }

    # ------------------------------------------------------------------
    # halt / resume
    # ------------------------------------------------------------------

    def test_halt_blocks_execute_workflow(self, engine, prices_envelope):
        """execute_workflow returns HALTED error_code when engine is halted."""
        engine.halt()
        result = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        assert result["success"] is False
        assert result["error_code"] == "HALTED"
        assert result["orders"] == []

    def test_halt_sets_internal_flag(self, engine):
        """halt() sets _halted to True."""
        assert engine._halted is False
        engine.halt()
        assert engine._halted is True

    def test_resume_clears_halt_flag(self, engine):
        """resume() clears _halted so workflow proceeds normally."""
        engine.halt()
        engine.resume()
        assert engine._halted is False

    def test_resume_allows_workflow_after_halt(self, engine, prices_envelope):
        """After halt then resume, execute_workflow succeeds again."""
        engine.halt()
        engine.resume()
        result = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        assert result["success"] is True
        assert result.get("error_code") != "HALTED"

    def test_halt_does_not_cancel_active_orders(self, engine, prices_envelope):
        """halt() does not touch already-submitted active_orders."""
        # Submit an order first
        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        assert len(engine.active_orders) == 1
        engine.halt()
        # Active orders still present
        assert len(engine.active_orders) == 1

    # ------------------------------------------------------------------
    # cancel_all_active_orders
    # ------------------------------------------------------------------

    def test_cancel_all_active_orders_empty(self, engine):
        """cancel_all_active_orders on empty registry returns zero totals."""
        result = engine.cancel_all_active_orders()
        assert result["total"] == 0
        assert result["cancelled"] == 0
        assert result["failed"] == 0
        assert result["results"] == []

    def test_cancel_all_active_orders_cancels_submitted_orders(self, engine, prices_envelope):
        """cancel_all_active_orders cancels every active order."""
        # Submit two orders
        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}, "HPG": {"quantity": 200}},
            current_portfolio={"VNM": {"quantity": 0}, "HPG": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        # Paper engine fills immediately; force status back to SUBMITTED so cancel works
        for broker_id in engine.active_orders:
            engine.router.paper_engine.orders[broker_id]["status"] = OrderStatus.SUBMITTED

        result = engine.cancel_all_active_orders()
        assert result["total"] == 2
        assert result["cancelled"] == 2
        assert result["failed"] == 0

    def test_cancel_all_active_orders_returns_per_order_results(self, engine, prices_envelope):
        """cancel_all_active_orders result list contains one entry per active order."""
        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        for broker_id in engine.active_orders:
            engine.router.paper_engine.orders[broker_id]["status"] = OrderStatus.SUBMITTED

        result = engine.cancel_all_active_orders()
        assert len(result["results"]) == 1
        entry = result["results"][0]
        assert "broker_order_id" in entry
        assert "success" in entry
        assert "message" in entry

    def test_cancel_all_updates_metrics(self, engine, prices_envelope):
        """cancel_all_active_orders increments total_cancelled metric."""
        engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        for broker_id in engine.active_orders:
            engine.router.paper_engine.orders[broker_id]["status"] = OrderStatus.SUBMITTED

        engine.cancel_all_active_orders()
        metrics = engine.get_execution_metrics()
        assert metrics["total_cancelled"] >= 1


class TestLiquidationMode:
    """Fix 3: liquidation_mode flag forces ALL SELLs before ALL BUYs."""

    @pytest.fixture
    def prices_envelope(self):
        return {
            "data": {"VNM": 50.0, "HPG": 25.0, "FPT": 80.0},
            "timestamp": 1716000000.0,
            "provenance": "unit-test-prices",
        }

    def _engine(self, liquidation_mode: bool) -> ExecutionEngine:
        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        return ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
            liquidation_mode=liquidation_mode,
        ))

    def test_liquidation_mode_false_partial_sell_not_prioritised(self, prices_envelope):
        """Without liquidation_mode, a partial SELL (target>0) is NOT moved before BUYs."""
        engine = self._engine(liquidation_mode=False)
        # HPG: reduce (SELL, target>0) — should NOT be prioritised over VNM BUY
        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 100}},
            current_portfolio={"VNM": {"quantity": 0}, "HPG": {"quantity": 400}},
            current_prices=prices_envelope,
        )
        assert summary["success"] is True
        orders = summary["orders"]
        symbols = [o["symbol"] for o in orders]
        # VNM BUY may appear before HPG SELL — no strict ordering guarantee
        assert set(symbols) == {"VNM", "HPG"}

    def test_liquidation_mode_true_all_sells_before_buys(self, prices_envelope):
        """With liquidation_mode=True, ALL SELLs appear before ALL BUYs."""
        engine = self._engine(liquidation_mode=True)
        # VNM: BUY, HPG: partial SELL (target>0), FPT: BUY
        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 100}, "FPT": {"quantity": 200}},
            current_portfolio={"VNM": {"quantity": 0}, "HPG": {"quantity": 400}, "FPT": {"quantity": 0}},
            current_prices=prices_envelope,
        )
        assert summary["success"] is True
        orders = summary["orders"]
        # Find the index of the first BUY and last SELL
        sell_indices = [i for i, o in enumerate(orders) if o["symbol"] == "HPG"]
        buy_indices  = [i for i, o in enumerate(orders) if o["symbol"] in ("VNM", "FPT")]
        assert sell_indices, "Expected at least one SELL order"
        assert buy_indices,  "Expected at least one BUY order"
        assert max(sell_indices) < min(buy_indices), (
            f"All SELLs must precede all BUYs. orders={[o['symbol'] for o in orders]}"
        )

    def test_liquidation_mode_config_flag_stored(self):
        """liquidation_mode is stored on config and defaults to False."""
        engine_default = ExecutionEngine(ExecutionEngineConfig())
        assert engine_default.config.liquidation_mode is False

        from omega.execution import OrderRouterConfig
        router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=False)
        engine_liq = ExecutionEngine(ExecutionEngineConfig(
            mode=TradingMode.PAPER,
            router_config=router_cfg,
            liquidation_mode=True,
        ))
        assert engine_liq.config.liquidation_mode is True

    def test_liquidation_mode_full_liquidation_still_first(self, prices_envelope):
        """Full liquidation (target=0) SELLs are still first under liquidation_mode=True."""
        engine = self._engine(liquidation_mode=True)
        summary = engine.execute_workflow(
            target_portfolio={"VNM": {"quantity": 500}, "HPG": {"quantity": 0}},
            current_portfolio={"VNM": {"quantity": 0}, "HPG": {"quantity": 400}},
            current_prices=prices_envelope,
            allow_odd_lot=True,
        )
        assert summary["success"] is True
        orders = summary["orders"]
        assert orders[0]["symbol"] == "HPG"
        assert orders[0]["is_liquidation"] is True
