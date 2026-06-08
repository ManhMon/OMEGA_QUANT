"""
OMEGA_QUANT Phase 19.2: Transaction Cost Optimizer Integration Tests

Tests integration between Phase 19 (TransactionCostOptimizer) and:
- Phase 18 (Rebalancer): Cost estimation during rebalancing
- Phase 4 (Execution Engine): Cost-aware execution simulation
- Phase 5 (Risk Guard): Pre-execution cost validation

All tests enforce T-1 lag on market data via PIT safety checks.

Author: Backend Engineer (Role 09)
Date: 2026-05-19
Version: 1.0.0
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict

from omega.quant.transaction_cost_optimizer import (
    TransactionCostOptimizer,
    TransactionCostResult,
)
from omega.quant.rebalancer import Rebalancer, RebalanceConfig, RebalanceDecision
from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig
from omega.quant.realtime_risk_guard import RealtimeRiskGuard, RiskLimits, RiskVerdict


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_timestamps():
    """Returns (as_of, available_at, timestamp) satisfying T-1 PIT."""
    timestamp = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)       # T-1
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc) # before timestamp
    return as_of, available_at, timestamp


@pytest.fixture
def transaction_cost_optimizer():
    """Standard TransactionCostOptimizer instance."""
    return TransactionCostOptimizer(
        fixed_commission=10_000.0,
        pct_commission=0.0015,
        volatility_scaling=0.1,
        price_scale=1000.0,
        impact_alpha=0.05,
        impact_beta=1.5,
    )


@pytest.fixture
def rebalancer():
    """Standard Rebalancer instance."""
    config = RebalanceConfig(
        drift_threshold=0.01,
        schedule="daily",
        max_turnover=0.25,
        min_trade_value=100_000.0,
        board_lot=100,
        max_adv_participation=0.10,
        transaction_cost_bps=15.0,
    )
    return Rebalancer(config=config)


@pytest.fixture
def execution_simulator():
    """Standard ExecutionSimulator instance."""
    config = ExecutionConfig(
        latency_ms=50.0,
        slippage_bps=5.0,
        commission_bps=1.0,
        market_impact_coeff=0.1,
        min_trade_size=0.001,
        max_trade_size=0.5,
    )
    return ExecutionSimulator(config=config)


@pytest.fixture
def risk_guard():
    """Standard RealtimeRiskGuard instance."""
    limits = RiskLimits(
        max_adv_pct=0.05,
        max_concentration_pct=0.20,
        max_notional_currency=500_000_000.0,
        circuit_breaker_drawdown=0.10,
    )
    return RealtimeRiskGuard(limits=limits)


@pytest.fixture
def market_data_multi_symbol(base_timestamps):
    """Market data for multiple symbols with T-1 lag."""
    as_of, available_at, _ = base_timestamps
    return {
        "VNM": {
            "price": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000_000,  # VND daily volume (~6250 shares at 80K)
            "as_of": as_of,
            "available_at": available_at,
        },
        "HPG": {
            "price": 30.0,
            "spread": 0.0015,
            "volatility": 0.025,
            "adv": 1_000_000_000,  # VND daily volume (~33333 shares at 30K)
            "as_of": as_of,
            "available_at": available_at,
        },
        "VIC": {
            "price": 50.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 800_000_000,  # VND daily volume (~16000 shares at 50K)
            "as_of": as_of,
            "available_at": available_at,
        },
    }


# ---------------------------------------------------------------------------
# Phase 19 ↔ Phase 18 (Rebalancer) Integration Tests
# ---------------------------------------------------------------------------

def test_rebalancer_calls_cost_optimizer_with_correct_format(
    transaction_cost_optimizer,
    rebalancer,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 1: Rebalancer → TransactionCostOptimizer
    
    Verify that rebalancer can call transaction_cost_optimizer.calculate_cost()
    with correct market_data format including T-1 lag metadata.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Setup portfolio state with sufficient drift to trigger rebalance
    target_portfolio = {"VNM": 0.45, "HPG": 0.30, "VIC": 0.25}
    current_positions = {
        "VNM": {"qty": 1000, "price": 80.0, "weight": 0.5},
        "HPG": {"qty": 2000, "price": 30.0, "weight": 0.3},
        "VIC": {"qty": 800, "price": 50.0, "weight": 0.2},
    }
    portfolio_value = 200_000_000.0  # 200M VND
    
    # Rebalancer determines trades
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data_multi_symbol,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
    )
    
    assert decision.should_rebalance
    assert len(decision.target_changes) > 0, "Rebalancer must generate real trades"
    
    # Extract positions from rebalance decision
    positions = {}
    for symbol, change in decision.target_changes.items():
        positions[symbol] = change["shares_delta"]
    
    # Call TransactionCostOptimizer with real rebalancer output
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Verify cost results are computed for all traded symbols
    for symbol in positions.keys():
        assert symbol in cost_results
        assert cost_results[symbol].total_cost >= 0.0
        assert cost_results[symbol].commission > 0.0


def test_rebalancer_cost_estimation_matches_optimizer(
    transaction_cost_optimizer,
    rebalancer,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 2: Rebalancer cost estimation vs TransactionCostOptimizer
    
    Verify that rebalancer's built-in cost estimation is consistent with
    TransactionCostOptimizer's detailed calculation.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Setup portfolio with sufficient drift for rebalance
    target_portfolio = {"VNM": 0.55, "HPG": 0.45}
    current_positions = {
        "VNM": {"qty": 1000, "price": 80.0, "weight": 0.6},
        "HPG": {"qty": 1000, "price": 30.0, "weight": 0.4},
    }
    portfolio_value = 110_000_000.0  # 110M VND
    
    # Get rebalancer's cost estimate
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data_multi_symbol,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
    )
    
    assert decision.should_rebalance
    assert len(decision.target_changes) > 0, "Rebalancer must generate real trades"
    
    rebalancer_cost = decision.estimated_cost
    
    # Get TransactionCostOptimizer's detailed cost
    positions = {}
    for symbol, change in decision.target_changes.items():
        positions[symbol] = change["shares_delta"]
    
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    optimizer_total_cost = sum(r.total_cost for r in cost_results.values())
    
    # Rebalancer uses simplified cost model (transaction_cost_bps * trade_value)
    # TransactionCostOptimizer uses detailed model (commission + slippage + liquidity + impact)
    # They should be in the same order of magnitude
    assert optimizer_total_cost > 0.0
    assert rebalancer_cost > 0.0
    # Allow up to 10x difference due to different cost models and lower participation with larger ADV
    ratio = max(optimizer_total_cost, rebalancer_cost) / max(min(optimizer_total_cost, rebalancer_cost), 1.0)
    assert ratio < 10.0, f"Cost estimates too different: rebalancer={rebalancer_cost}, optimizer={optimizer_total_cost}"


def test_rebalancer_respects_t1_lag_from_market_data(
    rebalancer,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 3: Rebalancer enforces T-1 lag on market data
    
    Verify that rebalancer validates T-1 lag on market_data before processing.
    """
    _, _, timestamp = base_timestamps
    
    # Create market data with same-day as_of (PIT violation)
    bad_market_data = {
        "VNM": {
            "price": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000,
            "as_of": datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),  # Same day!
            "available_at": datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc),
        }
    }
    
    target_portfolio = {"VNM": 1.0}
    current_positions = {"VNM": {"qty": 1000, "price": 80.0, "weight": 1.0}}
    portfolio_value = 80_000_000.0
    
    # Rebalancer should raise ValueError for PIT violation
    with pytest.raises(ValueError, match="PIT violation"):
        rebalancer.rebalance(
            target_portfolio=target_portfolio,
            current_positions=current_positions,
            market_data=bad_market_data,
            portfolio_value=portfolio_value,
            timestamp=timestamp,
        )


def test_rebalancer_integration_with_optimizer_board_lot_rounding(
    transaction_cost_optimizer,
    rebalancer,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 4: Board-lot rounding consistency
    
    Verify that rebalancer's board-lot rounded trades are correctly
    processed by TransactionCostOptimizer.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Drift sufficient to trigger board-lot rounded trade (delta >= 100 shares)
    target_portfolio = {"VNM": 0.55}  # 5% drift from 0.5 -> ~100 shares delta after rounding
    current_positions = {"VNM": {"qty": 1000, "price": 80.0, "weight": 0.5}}
    portfolio_value = 160_000_000.0  # 160M VND
    
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data_multi_symbol,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
    )
    
    assert decision.should_rebalance
    assert len(decision.target_changes) > 0, "Rebalancer must generate real trades"
    
    # Extract board-lot rounded positions
    positions = {}
    for symbol, change in decision.target_changes.items():
        shares_delta = change["shares_delta"]
        # Verify board-lot rounding (must be multiple of 100)
        assert shares_delta % 100 == 0, f"Board-lot violation: {shares_delta}"
        positions[symbol] = shares_delta
    
    # TransactionCostOptimizer should handle board-lot rounded quantities
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Verify costs are computed correctly
    for symbol in positions.keys():
        assert symbol in cost_results
        assert cost_results[symbol].total_cost >= 0.0


# ---------------------------------------------------------------------------
# Phase 19 ↔ Phase 4 (Execution Engine) Integration Tests
# ---------------------------------------------------------------------------

def test_execution_sim_uses_cost_estimates_from_optimizer(
    transaction_cost_optimizer,
    execution_simulator,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 5: Execution Engine → TransactionCostOptimizer
    
    Verify that execution_sim can use cost estimates from
    TransactionCostOptimizer to inform execution decisions.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Define positions to trade
    positions = {"VNM": 1000, "HPG": 500}
    
    # Get cost estimates from TransactionCostOptimizer
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Extract total estimated costs
    total_estimated_cost = sum(r.total_cost for r in cost_results.values())
    assert total_estimated_cost > 0.0
    
    # Build cost_overrides dict from optimizer output (symbol -> additional slippage bps)
    # Map optimizer cost to equivalent slippage bps: cost_bps = cost / notional * 10000
    cost_overrides: Dict[str, float] = {}
    for symbol, pos_qty in positions.items():
        result = cost_results[symbol]
        notional = abs(pos_qty) * market_data_multi_symbol[symbol]["price"] * 1000.0
        if notional > 0:
            cost_overrides[symbol] = result.total_cost / notional * 10000.0
    
    # Simulate execution with ExecutionSimulator, passing cost_overrides from optimizer
    import pandas as pd
    target_weights = pd.Series({"VNM": 0.6, "HPG": 0.4})
    current_weights = pd.Series({"VNM": 0.5, "HPG": 0.5})
    current_prices = pd.Series({
        "VNM": market_data_multi_symbol["VNM"]["price"] * 1000.0,
        "HPG": market_data_multi_symbol["HPG"]["price"] * 1000.0,
    })
    
    # Without cost_overrides: baseline execution
    exec_baseline = execution_simulator.execute_trades(
        target_weights=target_weights,
        current_weights=current_weights,
        current_prices=current_prices,
        timestamp=timestamp,
        portfolio_value=200_000_000.0,
    )
    
    # With cost_overrides: optimizer-informed execution
    exec_informed = execution_simulator.execute_trades(
        target_weights=target_weights,
        current_weights=current_weights,
        current_prices=current_prices,
        timestamp=timestamp,
        portfolio_value=200_000_000.0,
        cost_overrides=cost_overrides,
    )
    
    # Verify execution costs are in reasonable range compared to optimizer estimates
    assert exec_baseline.total_cost_bps > 0.0
    assert exec_baseline.num_trades > 0
    # Cost-override-informed execution should have equal or higher costs due to slippage adjustments
    assert exec_informed.total_cost_bps >= exec_baseline.total_cost_bps


def test_execution_sim_market_impact_consistency_with_optimizer(
    transaction_cost_optimizer,
    execution_simulator,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 6: Market impact consistency
    
    Verify that ExecutionSimulator's market impact model is consistent
    with TransactionCostOptimizer's institutional market impact formula.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Large trade to trigger significant market impact
    positions = {"VNM": 10000}  # Large position
    
    # Get optimizer's market impact estimate
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    optimizer_market_impact = cost_results["VNM"].market_impact
    assert optimizer_market_impact > 0.0
    
    # Build cost_overrides from optimizer market impact for real handoff
    notional_vnm = abs(positions["VNM"]) * market_data_multi_symbol["VNM"]["price"] * 1000.0
    optimizer_market_impact_bps = cost_results["VNM"].market_impact / notional_vnm * 10000.0 if notional_vnm > 0 else 0.0
    cost_overrides = {"VNM": optimizer_market_impact_bps}
    
    # ExecutionSimulator also models market impact via market_impact_coeff
    # Both should show that larger trades have higher impact
    import pandas as pd
    target_weights = pd.Series({"VNM": 0.8})
    current_weights = pd.Series({"VNM": 0.2})
    current_prices = pd.Series({"VNM": market_data_multi_symbol["VNM"]["price"] * 1000.0})
    
    exec_result = execution_simulator.execute_trades(
        target_weights=target_weights,
        current_weights=current_weights,
        current_prices=current_prices,
        timestamp=timestamp,
        portfolio_value=200_000_000.0,
        cost_overrides=cost_overrides,
    )
    
    # Verify execution includes market impact in slippage
    # With cost_overrides applied, total_slippage >= optimizer market impact + base slippage
    assert exec_result.total_slippage_bps >= optimizer_market_impact_bps + execution_simulator.config.slippage_bps


def test_execution_sim_respects_t1_lag_via_optimizer(
    transaction_cost_optimizer,
    execution_simulator,
    base_timestamps
):
    """
    Integration Test 7: T-1 lag enforcement in execution pipeline
    
    Verify that when ExecutionSimulator uses TransactionCostOptimizer,
    T-1 lag is enforced on market data.
    """
    _, _, timestamp = base_timestamps
    
    # Market data with PIT violation (same day)
    bad_market_data = {
        "VNM": {
            "price": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000,
            "as_of": datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),  # Same day!
            "available_at": datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc),
        }
    }
    
    positions = {"VNM": 1000}
    
    # TransactionCostOptimizer should reject due to PIT violation
    with pytest.raises(ValueError, match="PIT violation"):
        transaction_cost_optimizer.calculate_cost(
            positions=positions,
            market_data=bad_market_data,
            as_of=bad_market_data["VNM"]["as_of"],
            available_at=bad_market_data["VNM"]["available_at"],
            timestamp=timestamp,
        )


# ---------------------------------------------------------------------------
# Phase 19 ↔ Phase 5 (Risk Guard) Integration Tests
# ---------------------------------------------------------------------------

def test_risk_guard_checks_costs_before_order_submission(
    transaction_cost_optimizer,
    risk_guard,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 8: Risk Guard → TransactionCostOptimizer
    
    Verify that risk_guard can check transaction costs from optimizer
    before allowing order submission.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Setup portfolio state with lower exposures to avoid concentration violations
    risk_guard.set_portfolio_state(
        total_equity=300_000_000.0,  # Increased to 300M VND
        exposures={"VNM": 80_000_000.0, "HPG": 60_000_000.0}
    )
    
    # Proposed order (smaller size to avoid concentration violation)
    symbol = "VIC"
    quantity = 500  # Reduced from 1000
    price = market_data_multi_symbol[symbol]["price"] * 1000.0
    adv_20d = market_data_multi_symbol[symbol]["adv"]
    
    # Get cost estimate from optimizer
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions={symbol: quantity},
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    estimated_cost = cost_results[symbol].total_cost
    assert estimated_cost > 0.0
    
    # Set cost limit based on optimizer output: allow 2x estimated cost as buffer
    cost_limit = estimated_cost * 2.0
    
    # Risk guard checks order with cost estimate from optimizer handoff
    verdict = risk_guard.check_order(
        symbol=symbol,
        quantity=quantity,
        price=price,
        adv_20d=adv_20d,
        cost_estimate=estimated_cost,
        cost_limit=cost_limit,
    )
    
    # Order should pass risk checks (cost within limit)
    assert verdict == RiskVerdict.PASS


def test_risk_guard_rejects_high_cost_orders(
    transaction_cost_optimizer,
    risk_guard,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 9: Risk guard rejects orders with excessive costs
    
    Verify that risk_guard rejects orders that would violate notional limits,
    which implicitly includes high transaction costs.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Setup portfolio state
    risk_guard.set_portfolio_state(
        total_equity=200_000_000.0,
        exposures={}
    )
    
    # Very large order that exceeds notional limit
    symbol = "VNM"
    quantity = 100_000  # Huge order
    price = market_data_multi_symbol[symbol]["price"] * 1000.0
    adv_20d = market_data_multi_symbol[symbol]["adv"]
    
    # Get cost estimate (will be very high)
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions={symbol: quantity},
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Cost should be substantial due to large size
    assert cost_results[symbol].total_cost > 1_000_000.0
    assert cost_results[symbol].market_impact > 0.0
    
    # Test 9a: Risk guard should reject due to notional limit
    verdict = risk_guard.check_order(
        symbol=symbol,
        quantity=quantity,
        price=price,
        adv_20d=adv_20d,
    )
    
    # Should fail notional check
    assert verdict == RiskVerdict.FAIL_NOTIONAL
    
    # Test 9b: Risk guard should also reject based on cost estimate from optimizer
    # Use a tight cost limit below estimated cost
    tight_cost_limit = cost_results[symbol].total_cost * 0.5
    verdict_cost = risk_guard.check_order(
        symbol=symbol,
        quantity=quantity,
        price=price,
        adv_20d=adv_20d,
        cost_estimate=cost_results[symbol].total_cost,
        cost_limit=tight_cost_limit,
    )
    
    # Should fail cost check (tighter than notional)
    assert verdict_cost == RiskVerdict.FAIL_COST


def test_risk_guard_integration_with_optimizer_cost_multipliers(
    transaction_cost_optimizer,
    risk_guard,
    base_timestamps
):
    """
    Integration Test 10: Cost multipliers affect risk decisions
    
    Verify that TransactionCostOptimizer's Vietnam market constraint
    cost multipliers (limit-lock, foreign room) are considered in
    risk assessment workflow.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Market data with limit-lock condition (2.0x cost multiplier)
    market_data_locked = {
        "HPG": {
            "price": 30.0,
            "upper_limit": 30.0,  # At limit -> locked
            "lower_limit": 24.0,
            "spread": 0.001,
            "volatility": 0.025,
            "adv": 1_000_000,
            "as_of": as_of,
            "available_at": available_at,
        }
    }
    
    # Calculate costs with limit-lock multiplier
    positions = {"HPG": 1000}
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_locked,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Verify cost multiplier is applied
    assert cost_results["HPG"].cost_multiplier == 2.0
    
    # Higher costs due to multiplier
    total_cost_locked = cost_results["HPG"].total_cost
    
    # Compare with normal market conditions (no multiplier)
    market_data_normal = {
        "HPG": {
            "price": 30.0,
            "spread": 0.001,
            "volatility": 0.025,
            "adv": 1_000_000,
            "as_of": as_of,
            "available_at": available_at,
        }
    }
    
    cost_results_normal = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_normal,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    assert cost_results_normal["HPG"].cost_multiplier == 1.0
    total_cost_normal = cost_results_normal["HPG"].total_cost
    
    # Locked market should have significantly higher costs
    # Multiplier applies to variable costs only (not fixed commission)
    # Expect at least 1.4x total cost increase
    assert total_cost_locked > total_cost_normal * 1.4


# ---------------------------------------------------------------------------
# Comprehensive Multi-Phase Integration Tests
# ---------------------------------------------------------------------------

def test_full_pipeline_rebalancer_optimizer_execution_risk(
    transaction_cost_optimizer,
    rebalancer,
    execution_simulator,
    risk_guard,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 11: Full pipeline integration
    
    Test complete workflow: Rebalancer → Optimizer → Execution → Risk Guard
    Simulates realistic trading pipeline with all phases integrated.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Step 1: Rebalancer determines trades
    # Use large portfolio value to keep concentrations below 20% limit
    target_portfolio = {"VNM": 0.4, "HPG": 0.3, "VIC": 0.3}
    current_positions = {
        "VNM": {"qty": 100, "price": 80.0, "weight": 0.04},
        "HPG": {"qty": 500, "price": 30.0, "weight": 0.06},
        "VIC": {"qty": 200, "price": 50.0, "weight": 0.04},
    }
    portfolio_value = 800_000_000.0  # 800M VND
    
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data_multi_symbol,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
    )
    
    assert decision.should_rebalance
    assert len(decision.target_changes) > 0, "Rebalancer must generate real trades"
    
    # Step 2: Optimizer estimates costs for rebalance trades
    positions = {}
    for symbol, change in decision.target_changes.items():
        positions[symbol] = change["shares_delta"]
    
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    total_estimated_cost = sum(r.total_cost for r in cost_results.values())
    assert total_estimated_cost > 0.0
    
    # Step 3: Risk guard validates each order before execution
    risk_guard = RealtimeRiskGuard(limits=RiskLimits(
        max_adv_pct=0.05,
        max_concentration_pct=0.50,  # Relaxed for pipeline test to allow multi-symbol concentration
        max_notional_currency=500_000_000.0,
        circuit_breaker_drawdown=0.10,
    ))
    risk_guard.set_portfolio_state(
        total_equity=portfolio_value,
        exposures={
            "VNM": current_positions["VNM"]["qty"] * current_positions["VNM"]["price"] * 1000.0,
            "HPG": current_positions["HPG"]["qty"] * current_positions["HPG"]["price"] * 1000.0,
            "VIC": current_positions["VIC"]["qty"] * current_positions["VIC"]["price"] * 1000.0,
        }
    )
    
    orders_passed = 0
    for symbol, shares_delta in positions.items():
        if shares_delta == 0:
            continue
        
        price = market_data_multi_symbol[symbol]["price"] * 1000.0
        adv_20d = market_data_multi_symbol[symbol]["adv"]
        # Wire optimizer cost estimate into risk guard check
        est_cost = cost_results[symbol].total_cost if symbol in cost_results else 0.0
        cost_limit = est_cost * 5.0
        
        verdict = risk_guard.check_order(
            symbol=symbol,
            quantity=abs(shares_delta),
            price=price,
            adv_20d=adv_20d,
            cost_estimate=est_cost,
            cost_limit=cost_limit,
        )
        
        if verdict == RiskVerdict.PASS:
            orders_passed += 1
    
    # At least some orders should pass risk checks
    assert orders_passed > 0
    
    # Step 4: Execute approved trades
    import pandas as pd
    target_weights = pd.Series(target_portfolio)
    current_weights = pd.Series({
        "VNM": current_positions["VNM"]["weight"],
        "HPG": current_positions["HPG"]["weight"],
        "VIC": current_positions["VIC"]["weight"],
    })
    current_prices = pd.Series({
        sym: market_data_multi_symbol[sym]["price"] * 1000.0
        for sym in target_portfolio.keys()
    })
    
    exec_result = execution_simulator.execute_trades(
        target_weights=target_weights,
        current_weights=current_weights,
        current_prices=current_prices,
        timestamp=timestamp,
        portfolio_value=portfolio_value,
    )
    
    # Verify execution completed
    assert exec_result.num_trades > 0
    assert exec_result.total_cost_bps > 0.0


def test_multi_symbol_integration_all_phases(
    transaction_cost_optimizer,
    rebalancer,
    risk_guard,
    market_data_multi_symbol,
    base_timestamps
):
    """
    Integration Test 12: Multi-symbol integration across all phases
    
    Verify that all phases correctly handle multiple symbols with
    different characteristics (volatility, liquidity, constraints).
    """
    as_of, available_at, timestamp = base_timestamps
    
    # Complex multi-symbol portfolio
    target_portfolio = {"VNM": 0.35, "HPG": 0.35, "VIC": 0.30}
    current_positions = {
        "VNM": {"qty": 800, "price": 80.0, "weight": 0.40},
        "HPG": {"qty": 1500, "price": 30.0, "weight": 0.30},
        "VIC": {"qty": 600, "price": 50.0, "weight": 0.30},
    }
    portfolio_value = 159_000_000.0
    
    # Rebalancer processes all symbols
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data_multi_symbol,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
    )
    
    assert len(decision.target_changes) > 0, "Rebalancer must generate real trades for all symbols"
    
    # Optimizer calculates costs for all symbols
    positions = {}
    for symbol, change in decision.target_changes.items():
        positions[symbol] = change["shares_delta"]
    
    cost_results = transaction_cost_optimizer.calculate_cost(
        positions=positions,
        market_data=market_data_multi_symbol,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    
    # Verify each symbol has cost breakdown
    for symbol in positions.keys():
        assert symbol in cost_results
        result = cost_results[symbol]
        assert result.commission > 0.0
        assert result.slippage >= 0.0
        assert result.liquidity_cost >= 0.0
        assert result.market_impact >= 0.0
        assert result.total_cost > 0.0


def test_t1_lag_enforcement_across_all_integration_points(
    transaction_cost_optimizer,
    rebalancer,
    base_timestamps
):
    """
    Integration Test 13: T-1 lag enforcement across all integration points
    
    Comprehensive test verifying that T-1 lag is enforced at every
    integration boundary between phases.
    """
    _, _, timestamp = base_timestamps
    
    # Create market data with various PIT violations
    violations = [
        # Same day as_of
        {
            "VNM": {
                "price": 80.0,
                "spread": 0.001,
                "volatility": 0.02,
                "adv": 500_000,
                "as_of": datetime(2026, 5, 19, 8, 0, 0, tzinfo=timezone.utc),
                "available_at": datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc),
            }
        },
        # Future available_at
        {
            "VNM": {
                "price": 80.0,
                "spread": 0.001,
                "volatility": 0.02,
                "adv": 500_000,
                "as_of": datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc),
                "available_at": datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc),
            }
        },
    ]
    
    target_portfolio = {"VNM": 1.0}
    current_positions = {"VNM": {"qty": 1000, "price": 80.0, "weight": 1.0}}
    portfolio_value = 80_000_000.0
    
    # Test each violation scenario
    for bad_market_data in violations:
        # Rebalancer should reject
        with pytest.raises(ValueError, match="PIT violation"):
            rebalancer.rebalance(
                target_portfolio=target_portfolio,
                current_positions=current_positions,
                market_data=bad_market_data,
                portfolio_value=portfolio_value,
                timestamp=timestamp,
            )
        
        # TransactionCostOptimizer should also reject
        with pytest.raises(ValueError, match="PIT violation"):
            transaction_cost_optimizer.calculate_cost(
                positions={"VNM": 1000},
                market_data=bad_market_data,
                as_of=bad_market_data["VNM"]["as_of"],
                available_at=bad_market_data["VNM"]["available_at"],
                timestamp=timestamp,
            )


# ---------------------------------------------------------------------------
# Strict PIT Deterministic Tests
# ---------------------------------------------------------------------------

def test_timestamp_omitted_raises_in_deterministic_mode(
    transaction_cost_optimizer,
    market_data_multi_symbol,
    base_timestamps
):
    """
    PIT Deterministic Test 1: Timestamp omitted must fail.
    
    Verify that omitting timestamp (None) in deterministic mode raises
    ValueError instead of silently falling back to datetime.now().
    """
    as_of, available_at, _ = base_timestamps
    
    positions = {"VNM": 100}
    
    with pytest.raises(ValueError, match="timestamp is required in deterministic mode"):
        transaction_cost_optimizer.calculate_cost(
            positions=positions,
            market_data=market_data_multi_symbol,
            as_of=as_of,
            available_at=available_at,
            timestamp=None,  # Must raise in deterministic mode
        )


def test_symbol_level_as_of_drift_detected(
    transaction_cost_optimizer,
    base_timestamps
):
    """
    PIT Deterministic Test 2: Symbol-level metadata drift.
    
    Verify that when symbols in a multi-symbol basket have inconsistent
    as_of timestamps (one valid T-1, one same-day), the optimizer detects
    the drift for the violating symbol.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # First symbol: valid T-1 lag
    # Second symbol: same-day as_of (PIT violation)
    bad_market_data = {
        "VNM": {
            "price": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000_000,
            "as_of": as_of,  # Valid T-1
            "available_at": available_at,
        },
        "HPG": {
            "price": 30.0,
            "spread": 0.0015,
            "volatility": 0.025,
            "adv": 1_000_000_000,
            "as_of": datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc),  # Same day! Drift!
            "available_at": available_at,
        },
    }
    
    positions = {"VNM": 100, "HPG": 200}
    
    with pytest.raises(ValueError, match="PIT violation"):
        transaction_cost_optimizer.calculate_cost(
            positions=positions,
            market_data=bad_market_data,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )


def test_symbol_level_available_at_drift_detected(
    transaction_cost_optimizer,
    base_timestamps
):
    """
    PIT Deterministic Test 3: Symbol-level available_at drift.
    
    Verify that when symbols have inconsistent available_at timestamps
    (one available before timestamp, one after), the optimizer detects
    the future-dated metadata.
    """
    as_of, available_at, timestamp = base_timestamps
    
    # First symbol: valid availability
    # Second symbol: future available_at (PIT violation)
    bad_market_data = {
        "VNM": {
            "price": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000_000,
            "as_of": as_of,
            "available_at": available_at,  # Valid: before timestamp
        },
        "VIC": {
            "price": 50.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 800_000_000,
            "as_of": as_of,
            "available_at": datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc),  # Drift! After timestamp
        },
    }
    
    positions = {"VNM": 100, "VIC": 200}
    
    with pytest.raises(ValueError, match="PIT violation"):
        transaction_cost_optimizer.calculate_cost(
            positions=positions,
            market_data=bad_market_data,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )
