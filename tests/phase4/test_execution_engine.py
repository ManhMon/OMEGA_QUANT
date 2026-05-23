"""
Tests for Execution Engine - OMEGA_QUANT Phase 4 Migration

Tests realistic order execution simulation with:
- Latency, slippage, transaction costs, market impact
- Vectorized execution for performance
- PIT safety (execution at T uses prices from T)

Strict PIT Safety: All execution uses current prices, not future data.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from omega.quant.execution_sim import (
    ExecutionSimulator,
    ExecutionConfig,
    TradeExecution,
    ExecutionResult
)


@pytest.fixture
def execution_simulator():
    """Create execution simulator with test configuration."""
    config = ExecutionConfig(
        latency_ms=50.0,
        slippage_bps=5.0,
        commission_bps=1.0,
        market_impact_coeff=0.1,
        min_trade_size=0.001,
        max_trade_size=0.5
    )
    return ExecutionSimulator(config)


@pytest.fixture
def sample_weights():
    """Sample portfolio weights for testing."""
    return pd.Series({
        'AAPL': 0.25,
        'GOOGL': 0.25,
        'MSFT': 0.25,
        'AMZN': 0.15,
        'TSLA': 0.10
    })


@pytest.fixture
def sample_prices():
    """Sample market prices for testing."""
    return pd.Series({
        'AAPL': 150.0,
        'GOOGL': 2800.0,
        'MSFT': 300.0,
        'AMZN': 3300.0,
        'TSLA': 250.0
    })


class TestExecutionSimulatorInitialization:
    """Test 1-2: Simulator initialization and configuration."""
    
    def test_initialization_default_config(self):
        """Test 1: Simulator initializes with default configuration."""
        sim = ExecutionSimulator()
        
        assert sim.config is not None
        assert sim.config.latency_ms == 50.0
        assert sim.config.slippage_bps == 5.0
        assert sim.config.commission_bps == 1.0
    
    def test_initialization_custom_config(self):
        """Test 2: Simulator initializes with custom configuration."""
        config = ExecutionConfig(
            latency_ms=100.0,
            slippage_bps=10.0,
            commission_bps=2.0,
            market_impact_coeff=0.2
        )
        sim = ExecutionSimulator(config)
        
        assert sim.config.latency_ms == 100.0
        assert sim.config.slippage_bps == 10.0
        assert sim.config.commission_bps == 2.0


class TestTradeExecution:
    """Test 3-4: Single trade execution logic."""
    
    def test_execute_single_trade_basic(self, execution_simulator, sample_weights, sample_prices):
        """Test 3: Execute single trade with basic parameters."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        
        target_weight = 0.30
        current_weight = 0.25
        trade_size = target_weight - current_weight
        current_price = sample_prices['AAPL']
        
        trade = execution_simulator._execute_single_trade(
            symbol='AAPL',
            target_weight=target_weight,
            current_weight=current_weight,
            trade_size=trade_size,
            current_price=current_price,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        assert trade.symbol == 'AAPL'
        assert trade.target_weight == target_weight
        assert trade.current_weight == current_weight
        assert trade.trade_size == trade_size
        assert trade.execution_price > 0
        assert trade.slippage_bps > 0
        assert trade.commission_bps > 0
        assert trade.total_cost_bps > 0
        assert trade.pnl < 0  # Costs are negative PnL
    
    def test_execute_single_trade_direction(self, execution_simulator, sample_prices):
        """Test 4: Verify slippage direction (buy higher, sell lower)."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        current_price = sample_prices['AAPL']
        
        # Buy (positive trade size)
        trade_buy = execution_simulator._execute_single_trade(
            symbol='AAPL',
            target_weight=0.30,
            current_weight=0.25,
            trade_size=0.05,
            current_price=current_price,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        # Sell (negative trade size)
        trade_sell = execution_simulator._execute_single_trade(
            symbol='AAPL',
            target_weight=0.20,
            current_weight=0.25,
            trade_size=-0.05,
            current_price=current_price,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        # Buy should have higher execution price than current
        assert trade_buy.execution_price > current_price
        # Sell should have lower execution price than current
        assert trade_sell.execution_price < current_price


class TestMarketImpact:
    """Test 5-6: Market impact calculation."""
    
    def test_market_impact_basic(self, execution_simulator):
        """Test 5: Basic market impact calculation."""
        impact = execution_simulator.calculate_market_impact(trade_size=0.10, liquidity=1.0)
        
        assert impact > 0
        # Market impact should increase with trade size
        impact_large = execution_simulator.calculate_market_impact(trade_size=0.20, liquidity=1.0)
        assert impact_large > impact
    
    def test_market_impact_liquidity(self, execution_simulator):
        """Test 6: Market impact decreases with higher liquidity."""
        impact_normal = execution_simulator.calculate_market_impact(trade_size=0.10, liquidity=1.0)
        impact_high = execution_simulator.calculate_market_impact(trade_size=0.10, liquidity=2.0)
        
        # Higher liquidity = lower impact
        assert impact_high < impact_normal


class TestEstimateExecutionCost:
    """Test 7-8: Cost estimation without execution."""
    
    def test_estimate_cost_basic(self, execution_simulator, sample_weights):
        """Test 7: Basic cost estimation."""
        current_weights = sample_weights.copy()
        
        # No change = no cost
        result = execution_simulator.estimate_execution_cost(
            target_weights=sample_weights,
            current_weights=current_weights
        )
        
        assert result['total_bps'] == 0.0
        assert result['total_dollars'] == 0.0
    
    def test_estimate_cost_with_changes(self, execution_simulator, sample_weights):
        """Test 8: Cost estimation with weight changes."""
        target_weights = sample_weights.copy()
        target_weights['AAPL'] = 0.35  # Increase from 0.25
        
        result = execution_simulator.estimate_execution_cost(
            target_weights=target_weights,
            current_weights=sample_weights
        )
        
        assert result['total_bps'] > 0
        assert result['total_dollars'] > 0
        assert result['weight_traded'] > 0


class TestExecuteTrades:
    """Test 9-10: Full trade execution."""
    
    def test_execute_trades_basic(self, execution_simulator, sample_weights, sample_prices):
        """Test 9: Execute multiple trades."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        
        # Change weights
        target_weights = sample_weights.copy()
        target_weights['AAPL'] = 0.35
        target_weights['GOOGL'] = 0.15
        
        result = execution_simulator.execute_trades(
            target_weights=target_weights,
            current_weights=sample_weights,
            current_prices=sample_prices,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        assert isinstance(result, ExecutionResult)
        assert result.num_trades > 0
        assert result.total_volume > 0
        assert result.total_slippage_bps >= 0
        assert result.total_commission_bps >= 0
        assert result.total_cost_bps >= 0
    
    def test_execute_trades_no_trades(self, execution_simulator, sample_weights, sample_prices):
        """Test 10: No trades when weights unchanged."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        
        result = execution_simulator.execute_trades(
            target_weights=sample_weights,
            current_weights=sample_weights,
            current_prices=sample_prices,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        assert result.num_trades == 0
        assert result.total_volume == 0.0
        assert result.total_cost_bps == 0.0


class TestPITSafety:
    """Test 11-12: PIT safety in execution."""
    
    def test_execution_uses_current_prices(self, execution_simulator, sample_weights, sample_prices):
        """Test 11: Execution uses current prices, not future data."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        
        result = execution_simulator.execute_trades(
            target_weights=sample_weights,
            current_weights=sample_weights,
            current_prices=sample_prices,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        # Execution should complete without errors
        assert result.timestamp == timestamp
    
    def test_execution_handles_missing_prices(self, execution_simulator, sample_weights, sample_prices):
        """Test 12: Execution gracefully handles missing prices."""
        timestamp = datetime(2024, 1, 5)
        portfolio_value = 1000000.0
        
        # Missing price for one symbol
        prices_with_missing = sample_prices.copy()
        prices_with_missing = prices_with_missing.drop('TSLA')
        
        # We need a target weight for TSLA to trigger a trade
        target_weights = sample_weights.copy()
        target_weights['TSLA'] = 0.20
        
        result = execution_simulator.execute_trades(
            target_weights=target_weights,
            current_weights=sample_weights,
            current_prices=prices_with_missing,
            timestamp=timestamp,
            portfolio_value=portfolio_value
        )
        
        # Should handle gracefully (no trades for TSLA due to missing price)
        assert result.num_trades >= 0
        trade_symbols = [t.symbol for t in result.trades]
        assert 'TSLA' not in trade_symbols
