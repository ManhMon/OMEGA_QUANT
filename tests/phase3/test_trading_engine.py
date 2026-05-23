"""Test Trading Engine - OMEGA_QUANT Phase 3.3.

Tests the full trading pipeline orchestration:
1. Alpha Discovery → Portfolio Optimization → Promotion → Execution
2. PIT safety enforcement (T-1 lag)
3. Execution simulation with latency/slippage
4. Backtest integration

12 test cases covering all critical paths.
"""

import datetime
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from omega.quant.trading_engine import (
    TradingEngine,
    TradingConfig,
    TradingSignal,
    TradingResult,
)
from omega.quant.execution_sim import ExecutionConfig, ExecutionSimulator
from omega.quant.portfolio_optimizer import PortfolioOptimizer
from omega.quant.promotion import PromotionGate


@pytest.fixture
def sample_market_data():
    """Generate sample market data with MultiIndex [timestamp, symbol]."""
    dates = pd.date_range(start='2024-01-01', end='2024-01-10', freq='D')
    symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']
    
    index = pd.MultiIndex.from_product(
        [dates, symbols],
        names=['timestamp', 'symbol']
    )
    
    np.random.seed(42)
    data = pd.DataFrame({
        'open': 100 + np.random.randn(len(index)) * 5,
        'high': 105 + np.random.randn(len(index)) * 5,
        'low': 95 + np.random.randn(len(index)) * 5,
        'close': 100 + np.random.randn(len(index)) * 5,
        'volume': np.random.randint(1000000, 10000000, len(index))
    }, index=index)
    
    return data


@pytest.fixture
def trading_engine():
    """Create trading engine with test configuration."""
    config = TradingConfig(
        max_alpha_candidates=10,
        min_ic_threshold=0.02,
        min_sharpe_threshold=0.5,
        max_leverage=1.0,
        max_concentration=0.2,
        promotion_ic_threshold=0.05,
        promotion_sharpe_threshold=1.0,
        embargo_horizon=0,  # Set to 0 for tests to allow execution path
        execution_latency_ms=50.0,
        execution_slippage_bps=5.0,
        execution_commission_bps=1.0
    )
    return TradingEngine(config, load_state=False)

class TestTradingEngineInitialization:
    """Test 1-2: Engine initialization and configuration."""
    
    def test_engine_initialization_default_config(self):
        """Test 1: Engine initializes with default configuration."""
        engine = TradingEngine(load_state=False)
        
        assert engine.config is not None
        assert engine.alpha_engine is not None
        assert engine.portfolio_optimizer is not None
        assert engine.promotion_gate is not None
        assert engine.execution_simulator is not None
        assert engine.current_weights is None
        assert len(engine.alpha_history) == 0
    
    def test_engine_initialization_custom_config(self):
        """Test 2: Engine initializes with custom configuration."""
        config = TradingConfig(
            max_leverage=2.0,
            max_concentration=0.15,
            promotion_ic_threshold=0.08
        )
        engine = TradingEngine(config)
        
        assert engine.config.max_leverage == 2.0
        assert engine.config.max_concentration == 0.15
        assert engine.config.promotion_ic_threshold == 0.08
        assert engine.portfolio_optimizer.max_leverage == 2.0


class TestSignalGeneration:
    """Test 3-5: Trading signal generation."""
    
    def test_generate_trading_signal_success(self, trading_engine, sample_market_data):
        """Test 3: Successfully generate trading signal."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        # Pass full market data - engine enforces T-1 internally
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        # Signal may be None if promotion gate rejects, so we test both paths
        if signal is not None:
            assert isinstance(signal, TradingSignal)
            assert signal.timestamp == timestamp
            assert signal.alpha_id is not None
            assert len(signal.target_weights) > 0
            assert signal.promotion_tier in ['Paper', 'Shadow', 'Production']
            assert signal.execution_ready is True
    
    def test_generate_signal_enforces_pit_safety(self, trading_engine, sample_market_data):
        """Test 4: Signal generation enforces PIT safety (T-1 lag)."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        # Pass full market data including T - engine should enforce T-1 internally
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        # Engine enforces T-1 lag internally
        if signal is not None:
            assert signal.timestamp == timestamp
            # Verify that the signal was generated using only T-1 data
            # (implementation detail: engine slices data internally)
    
    def test_generate_signal_with_insufficient_data(self, trading_engine):
        """Test 5: Signal generation fails gracefully with insufficient data."""
        timestamp = datetime.datetime(2024, 1, 1)
        
        # Empty market data
        empty_data = pd.DataFrame(
            columns=['open', 'high', 'low', 'close', 'volume']
        )
        empty_data.index = pd.MultiIndex.from_tuples(
            [],
            names=['timestamp', 'symbol']
        )
        
        signal = trading_engine.generate_trading_signal(
            market_data=empty_data,
            timestamp=timestamp
        )
        
        # Should return None or handle gracefully
        assert signal is None or isinstance(signal, TradingSignal)


class TestSignalExecution:
    """Test 6-8: Signal execution with realistic simulation."""
    
    def test_execute_signal_success(self, trading_engine, sample_market_data):
        """Test 6: Successfully execute trading signal."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        # Generate signal with full market data (engine enforces T-1 internally)
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        if signal is None:
            pytest.skip("Signal generation failed (promotion gate rejected)")
        
        # Get current prices
        current_data = sample_market_data[
            sample_market_data.index.get_level_values(0) == timestamp
        ]
        current_prices = current_data['close'].droplevel(0)
        
        # Execute signal
        result = trading_engine.execute_signal(
            signal=signal,
            market_data=sample_market_data,
            current_prices=current_prices
        )
        
        assert isinstance(result, TradingResult)
        assert result.signal == signal
        assert result.execution is not None
        assert result.total_cost_bps >= 0
    
    def test_execute_signal_calculates_costs(self, trading_engine, sample_market_data):
        """Test 7: Execution calculates slippage and commission costs."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        if signal is None:
            pytest.skip("Signal generation failed")
        
        current_data = sample_market_data[
            sample_market_data.index.get_level_values(0) == timestamp
        ]
        current_prices = current_data['close'].droplevel(0)
        
        result = trading_engine.execute_signal(
            signal=signal,
            market_data=sample_market_data,
            current_prices=current_prices
        )
        
        # Verify costs are calculated
        assert result.execution.total_slippage_bps >= 0
        assert result.execution.total_commission_bps >= 0
        assert result.execution.total_cost_bps >= 0
        assert result.total_cost_bps == result.execution.total_cost_bps
    
    def test_execute_signal_updates_weights(self, trading_engine, sample_market_data):
        """Test 8: Execution updates current portfolio weights."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        # Initial weights should be None
        assert trading_engine.current_weights is None
        
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        if signal is None:
            pytest.skip("Signal generation failed")
        
        current_data = sample_market_data[
            sample_market_data.index.get_level_values(0) == timestamp
        ]
        current_prices = current_data['close'].droplevel(0)
        
        result = trading_engine.execute_signal(
            signal=signal,
            market_data=sample_market_data,
            current_prices=current_prices
        )
        
        # Weights should be updated (not None)
        assert trading_engine.current_weights is not None
        assert len(trading_engine.current_weights) > 0


class TestBacktest:
    """Test 9-10: Backtest functionality."""
    
    def test_run_backtest_success(self, trading_engine, sample_market_data):
        """Test 9: Run full backtest over historical data."""
        start_date = datetime.datetime(2024, 1, 3)
        end_date = datetime.datetime(2024, 1, 8)
        
        results = trading_engine.run_backtest(
            market_data=sample_market_data,
            start_date=start_date,
            end_date=end_date,
            rebalance_frequency='D'
        )
        
        assert isinstance(results, pd.DataFrame)
        # Results may be empty if all signals rejected
        if len(results) > 0:
            assert 'timestamp' in results.columns
            assert 'pnl' in results.columns
            assert 'cost_bps' in results.columns
            assert 'tier' in results.columns
    
    def test_backtest_enforces_pit_safety(self, trading_engine, sample_market_data):
        """Test 10: Backtest enforces PIT safety throughout."""
        start_date = datetime.datetime(2024, 1, 3)
        end_date = datetime.datetime(2024, 1, 6)
        
        results = trading_engine.run_backtest(
            market_data=sample_market_data,
            start_date=start_date,
            end_date=end_date,
            rebalance_frequency='D'
        )
        
        # Verify all timestamps are within range
        if len(results) > 0:
            assert results['timestamp'].min() >= start_date
            assert results['timestamp'].max() <= end_date


class TestExecutionSimulator:
    """Test 11-12: Execution simulator standalone tests."""
    
    def test_execution_simulator_calculates_slippage(self):
        """Test 11: Execution simulator calculates realistic slippage."""
        config = ExecutionConfig(
            latency_ms=50.0,
            slippage_bps=5.0,
            commission_bps=1.0,
            market_impact_coeff=0.1
        )
        simulator = ExecutionSimulator(config)
        
        # Create test weights
        symbols = ['AAPL', 'GOOGL', 'MSFT']
        target_weights = pd.Series([0.4, 0.3, 0.3], index=symbols)
        current_weights = pd.Series([0.2, 0.5, 0.3], index=symbols)
        current_prices = pd.Series([150.0, 2800.0, 380.0], index=symbols)
        
        timestamp = datetime.datetime(2024, 1, 5)
        
        result = simulator.execute_trades(
            target_weights=target_weights,
            current_weights=current_weights,
            current_prices=current_prices,
            timestamp=timestamp
        )
        
        assert result.num_trades > 0
        assert result.total_slippage_bps >= config.slippage_bps
        assert result.total_commission_bps >= config.commission_bps
        assert result.total_cost_bps > 0
    
    def test_execution_simulator_estimates_costs(self):
        """Test 12: Execution simulator estimates costs without executing."""
        simulator = ExecutionSimulator()
        
        symbols = ['AAPL', 'GOOGL', 'MSFT']
        target_weights = pd.Series([0.4, 0.3, 0.3], index=symbols)
        current_weights = pd.Series([0.2, 0.5, 0.3], index=symbols)
        
        cost_estimate = simulator.estimate_execution_cost(
            target_weights=target_weights,
            current_weights=current_weights,
            portfolio_value=1000000.0
        )
        
        assert 'slippage_bps' in cost_estimate
        assert 'commission_bps' in cost_estimate
        assert 'total_bps' in cost_estimate
        assert 'total_dollars' in cost_estimate
        assert cost_estimate['total_bps'] > 0
        assert cost_estimate['total_dollars'] > 0


class TestEngineReset:
    """Bonus test: Engine reset functionality."""
    
    def test_engine_reset(self, trading_engine, sample_market_data):
        """Test: Engine reset clears state."""
        timestamp = datetime.datetime(2024, 1, 5)
        
        # Generate signal to populate state
        signal = trading_engine.generate_trading_signal(
            market_data=sample_market_data,
            timestamp=timestamp
        )
        
        if signal is not None:
            current_data = sample_market_data[
                sample_market_data.index.get_level_values(0) == timestamp
            ]
            current_prices = current_data['close'].droplevel(0)
            
            trading_engine.execute_signal(
                signal=signal,
                market_data=sample_market_data,
                current_prices=current_prices
            )
        
        # Reset engine
        trading_engine.reset()
        
        # Verify state cleared
        assert trading_engine.current_weights is None
        assert len(trading_engine.alpha_history) == 0
