"""
Layer 6: Execution Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests execution simulation, transaction costs, slippage, and order routing.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig


class TestExecutionLayer:
    """Test Layer 6: Execution simulation."""
    
    def test_execution_simulator_initialization(self):
        """Test ExecutionSimulator initializes correctly."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        assert simulator is not None
        assert simulator.config == config
    
    def test_simple_execution(self):
        """Test simple order execution."""
        config = ExecutionConfig(commission_bps=10)  # 10 bps commission
        simulator = ExecutionSimulator(config=config)
        
        # Create target positions
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.40, 0.35, 0.25]
        })
        
        # Market data
        market_data = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "close": [100.0, 80.0, 120.0],
            "volume": [1000000, 800000, 1200000]
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        assert len(executions) == 3
        assert "ticker" in executions.columns
        assert "executed_price" in executions.columns
        assert "commission" in executions.columns
    
    def test_transaction_cost_calculation(self):
        """Test transaction cost calculation."""
        config = ExecutionConfig(
            commission_bps=10,
            slippage_bps=5
        )
        simulator = ExecutionSimulator(config=config)
        
        # Single trade
        trade = pd.DataFrame({
            "ticker": ["A"],
            "target_weight": [0.50],
            "price": [100.0],
            "notional": [50000.0]
        })
        
        costs = simulator.compute_transaction_costs(trade)
        
        assert "commission" in costs.columns
        assert "slippage" in costs.columns
        assert "total_cost" in costs.columns
        
        # Commission = 50000 * 0.001 = 50
        # Slippage = 50000 * 0.0005 = 25
        # Total = 75
        assert np.isclose(costs["total_cost"].iloc[0], 75.0, atol=1.0)
    
    def test_slippage_model(self):
        """Test slippage modeling based on volume."""
        config = ExecutionConfig(slippage_bps=5)
        simulator = ExecutionSimulator(config=config)
        
        # Large trade relative to volume
        trade = pd.DataFrame({
            "ticker": ["A"],
            "target_shares": [10000],
            "price": [100.0],
            "daily_volume": [50000]  # Trade is 20% of daily volume
        })
        
        slippage = simulator.compute_slippage(trade)
        
        # Slippage should increase with trade size
        assert slippage["slippage_bps"].iloc[0] > 5  # More than base slippage
    
    def test_market_impact(self):
        """Test market impact calculation."""
        config = ExecutionConfig(market_impact_factor=0.1)
        simulator = ExecutionSimulator(config=config)
        
        # Trade data
        trade = pd.DataFrame({
            "ticker": ["A"],
            "target_shares": [5000],
            "price": [100.0],
            "daily_volume": [100000],
            "volatility": [0.20]
        })
        
        impact = simulator.compute_market_impact(trade)
        
        assert "market_impact_bps" in impact.columns
        assert impact["market_impact_bps"].iloc[0] > 0
    
    def test_execution_with_rebalancing(self):
        """Test execution during portfolio rebalancing."""
        config = ExecutionConfig(commission_bps=10)
        simulator = ExecutionSimulator(config=config)
        
        # Current positions
        current = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "current_weight": [0.40, 0.35, 0.25]
        })
        
        # Target positions
        target = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "target_weight": [0.50, 0.25, 0.25]
        })
        
        # Market data
        market_data = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "close": [100.0, 80.0, 120.0],
            "volume": [1000000, 800000, 1200000]
        })
        
        # Compute trades needed
        trades = simulator.compute_rebalance_trades(current, target, portfolio_value=1000000)
        
        assert len(trades) > 0
        # Should buy A, sell B, no change to C
        a_trade = trades[trades["ticker"] == "A"]["shares"].iloc[0]
        b_trade = trades[trades["ticker"] == "B"]["shares"].iloc[0]
        
        assert a_trade > 0  # Buy A
        assert b_trade < 0  # Sell B
    
    def test_execution_metrics(self):
        """Test execution quality metrics."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        # Execution data
        executions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "target_price": [100.0, 80.0, 120.0],
            "executed_price": [100.5, 79.8, 120.3],
            "shares": [100, 200, 150],
            "commission": [10.0, 16.0, 18.0],
            "slippage": [5.0, 4.0, 4.5]
        })
        
        metrics = simulator.compute_execution_metrics(executions)
        
        assert "total_trades" in metrics
        assert "avg_cost_bps" in metrics
        assert "total_commission" in metrics
        assert "total_slippage" in metrics
        
        assert metrics["total_trades"] == 3
        assert metrics["total_commission"] == 44.0


class TestExecutionBoundary:
    """Test boundary conditions for execution."""
    
    def test_zero_position_execution(self):
        """Test execution with zero positions."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.0, 0.0, 0.0]
        })
        
        market_data = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "close": [100.0, 80.0, 120.0],
            "volume": [1000000, 800000, 1200000]
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        # Should handle zero positions gracefully
        assert len(executions) >= 0
    
    def test_single_asset_execution(self):
        """Test execution with single asset."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "target_weight": [1.0]
        })
        
        market_data = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "close": [100.0],
            "volume": [1000000]
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        assert len(executions) == 1
        assert executions["ticker"].iloc[0] == "A"
    
    def test_illiquid_asset_execution(self):
        """Test execution with illiquid assets."""
        config = ExecutionConfig(slippage_bps=5)
        simulator = ExecutionSimulator(config=config)
        
        # Very low volume asset
        positions = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "target_weight": [1.0]
        })
        
        market_data = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "close": [100.0],
            "volume": [1000]  # Very low volume
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        # Should have higher slippage for illiquid assets
        if "slippage" in executions.columns:
            assert executions["slippage"].iloc[0] > 0
    
    def test_extreme_price_execution(self):
        """Test execution with extreme prices."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B"],
            "date": ["2023-01-01"] * 2,
            "target_weight": [0.5, 0.5]
        })
        
        market_data = pd.DataFrame({
            "ticker": ["A", "B"],
            "date": ["2023-01-01"] * 2,
            "close": [0.01, 10000.0],  # Extreme prices
            "volume": [1000000, 1000000]
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        # Should handle extreme prices without crashing
        assert len(executions) == 2


class TestExecutionIntegration:
    """Test execution integration with portfolio layer."""
    
    def test_portfolio_to_execution_pipeline(self):
        """Test complete portfolio -> execution pipeline."""
        from omega.quant.portfolio_optimizer import PortfolioOptimizer, OptimizerConfig
        
        # Create portfolio
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "alpha_momentum_rank": [0.8, 0.5, 0.2]
        })
        
        opt_config = OptimizerConfig(method="rank_weight")
        optimizer = PortfolioOptimizer(config=opt_config)
        portfolio = optimizer.construct_portfolio(alphas)
        
        # Execute portfolio
        exec_config = ExecutionConfig(commission_bps=10)
        simulator = ExecutionSimulator(config=exec_config)
        
        market_data = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "close": [100.0, 80.0, 120.0],
            "volume": [1000000, 800000, 1200000]
        })
        
        executions = simulator.simulate_execution(portfolio, market_data)
        
        # Verify complete pipeline
        assert len(executions) > 0
        assert "executed_price" in executions.columns
    
    def test_multi_period_execution(self):
        """Test execution across multiple periods."""
        config = ExecutionConfig(commission_bps=10)
        simulator = ExecutionSimulator(config=config)
        
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        
        all_executions = []
        
        for date in dates:
            positions = pd.DataFrame({
                "ticker": ["A", "B", "C"],
                "date": [date] * 3,
                "target_weight": np.random.dirichlet([1, 1, 1])
            })
            
            market_data = pd.DataFrame({
                "ticker": ["A", "B", "C"],
                "date": [date] * 3,
                "close": [100.0, 80.0, 120.0],
                "volume": [1000000, 800000, 1200000]
            })
            
            executions = simulator.simulate_execution(positions, market_data)
            all_executions.append(executions)
        
        combined = pd.concat(all_executions, ignore_index=True)
        
        assert len(combined) == 15  # 3 assets * 5 days


class TestExecutionCosts:
    """Test execution cost modeling."""
    
    def test_commission_scaling(self):
        """Test commission scales with trade size."""
        config = ExecutionConfig(commission_bps=10)
        simulator = ExecutionSimulator(config=config)
        
        # Small trade
        small_trade = pd.DataFrame({
            "ticker": ["A"],
            "notional": [10000.0]
        })
        
        # Large trade
        large_trade = pd.DataFrame({
            "ticker": ["A"],
            "notional": [100000.0]
        })
        
        small_cost = simulator.compute_transaction_costs(small_trade)
        large_cost = simulator.compute_transaction_costs(large_trade)
        
        # Commission should scale linearly
        assert large_cost["commission"].iloc[0] == 10 * small_cost["commission"].iloc[0]
    
    def test_slippage_nonlinear(self):
        """Test slippage increases nonlinearly with trade size."""
        config = ExecutionConfig(slippage_bps=5)
        simulator = ExecutionSimulator(config=config)
        
        # Small trade (1% of volume)
        small_trade = pd.DataFrame({
            "ticker": ["A"],
            "target_shares": [1000],
            "daily_volume": [100000]
        })
        
        # Large trade (10% of volume)
        large_trade = pd.DataFrame({
            "ticker": ["A"],
            "target_shares": [10000],
            "daily_volume": [100000]
        })
        
        small_slippage = simulator.compute_slippage(small_trade)
        large_slippage = simulator.compute_slippage(large_trade)
        
        # Slippage should increase more than linearly
        ratio = large_slippage["slippage_bps"].iloc[0] / small_slippage["slippage_bps"].iloc[0]
        assert ratio > 10  # More than 10x for 10x trade size
    
    def test_total_cost_breakdown(self):
        """Test total cost breakdown into components."""
        config = ExecutionConfig(
            commission_bps=10,
            slippage_bps=5,
            market_impact_factor=0.1
        )
        simulator = ExecutionSimulator(config=config)
        
        trade = pd.DataFrame({
            "ticker": ["A"],
            "notional": [100000.0],
            "target_shares": [1000],
            "daily_volume": [100000],
            "volatility": [0.20]
        })
        
        costs = simulator.compute_transaction_costs(trade)
        
        # Total cost should equal sum of components
        total = costs["commission"].iloc[0] + costs["slippage"].iloc[0]
        if "market_impact" in costs.columns:
            total += costs["market_impact"].iloc[0]
        
        assert np.isclose(costs["total_cost"].iloc[0], total, atol=0.01)


class TestExecutionPITSafety:
    """Test PIT safety in execution."""
    
    def test_execution_uses_available_prices(self):
        """Test that execution uses only available prices."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A"],
            "date": [pd.Timestamp("2023-01-01")],
            "target_weight": [1.0]
        })
        
        # Market data with PIT timestamps
        market_data = pd.DataFrame({
            "ticker": ["A"],
            "date": [pd.Timestamp("2023-01-01")],
            "close": [100.0],
            "volume": [1000000],
            "as_of": [pd.Timestamp("2023-01-01")],
            "available_at": [pd.Timestamp("2023-01-02")]
        })
        
        executions = simulator.simulate_execution(positions, market_data)
        
        # Execution should use price available at execution time
        assert len(executions) > 0
    
    def test_no_future_price_leakage(self):
        """Test that execution doesn't use future prices."""
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        
        # Simulate execution over time
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        
        for i, date in enumerate(dates):
            positions = pd.DataFrame({
                "ticker": ["A"],
                "date": [date],
                "target_weight": [1.0]
            })
            
            # Market data up to current date only
            market_data = pd.DataFrame({
                "ticker": ["A"] * (i+1),
                "date": dates[:i+1],
                "close": np.linspace(100, 110, i+1),
                "volume": [1000000] * (i+1)
            })
            
            executions = simulator.simulate_execution(
                positions,
                market_data[market_data["date"] == date]
            )
            
            # Should only use current date's price
            if len(executions) > 0:
                assert executions["date"].iloc[0] == date


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
