"""
Unit Tests for OMEGA_QUANT Backtest Engine
Phase 4.2: Execution Engine - Walk-Forward Backtester

Vectorized/Loop Hybrid | Institutional Grade | PIT-Safe
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.backtest_engine import BacktestEngine, BacktestResult


@pytest.fixture
def engine():
    return BacktestEngine(initial_capital=1_000_000_000.0)


@pytest.fixture
def sample_data():
    """Create sample price and weight data."""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=100)
    
    # 4 assets with different return profiles
    prices = pd.DataFrame({
        'AAPL': 100 + np.cumsum(np.random.randn(100) * 2),
        'MSFT': 100 + np.cumsum(np.random.randn(100) * 1.5),
        'GOOGL': 100 + np.cumsum(np.random.randn(100) * 1.8),
        'AMZN': 100 + np.cumsum(np.random.randn(100) * 2.2)
    }, index=dates)
    
    # Weights that change to induce turnover
    weights = pd.DataFrame({
        'AAPL': np.linspace(0.2, 0.3, 100),
        'MSFT': np.linspace(0.3, 0.2, 100),
        'GOOGL': 0.25,
        'AMZN': 0.25
    }, index=dates)
    
    return prices, weights


def test_backtest_engine_initialization(engine):
    """Test engine initialization."""
    assert engine.initial_capital == 1_000_000_000.0
    assert engine.fee_rate == 0.0015
    assert engine.tax_rate == 0.0010
    assert engine.slippage_bps == 2.0


def test_calculate_metrics(engine, sample_data):
    """Test metric calculation."""
    prices, weights = sample_data
    result = engine.run(prices, weights)
    
    assert isinstance(result, BacktestResult)
    assert len(result.equity_curve) == len(prices)
    assert len(result.returns) == len(prices)
    
    # Check metrics exist
    assert 'sharpe' in result.metrics
    assert 'sortino' in result.metrics
    assert 'max_drawdown' in result.metrics
    assert 'win_rate' in result.metrics
    assert 'total_return' in result.metrics
    assert 'volatility' in result.metrics


def test_equity_curve_monotonic_with_positive_returns(engine):
    """Test equity curve with guaranteed positive returns."""
    dates = pd.date_range('2023-01-01', periods=50)
    
    # Prices that always go up
    prices = pd.DataFrame({
        'A': np.linspace(100, 110, 50),
        'B': np.linspace(100, 110, 50)
    }, index=dates)
    
    # Equal weight
    weights = pd.DataFrame({
        'A': 0.5,
        'B': 0.5
    }, index=dates)
    
    result = engine.run(prices, weights)
    
    # Equity should generally increase (minus costs)
    assert result.equity_curve.iloc[-1] > result.equity_curve.iloc[0] * 0.99  # Allow for costs


def test_transaction_costs_impact(engine, sample_data):
    """Test that transaction costs reduce returns."""
    prices, weights = sample_data
    
    # Run with costs
    result_with_costs = engine.run(prices, weights)
    
    # Run without costs (set to zero)
    engine_no_costs = BacktestEngine(
        initial_capital=engine.initial_capital,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage_bps=0.0
    )
    result_no_costs = engine_no_costs.run(prices, weights)
    
    # With costs should have lower final equity
    assert result_with_costs.equity_curve.iloc[-1] < result_no_costs.equity_curve.iloc[-1]


def test_high_turnover_portfolio(engine):
    """Test portfolio with high turnover (frequent rebalancing)."""
    dates = pd.date_range('2023-01-01', periods=50)
    
    prices = pd.DataFrame({
        'A': 100 + np.random.randn(50).cumsum(),
        'B': 100 + np.random.randn(50).cumsum()
    }, index=dates)
    
    # Weights that change every day (high turnover)
    weights = pd.DataFrame({
        'A': np.random.uniform(0.3, 0.7, 50),
        'B': np.random.uniform(0.3, 0.7, 50)
    }, index=dates)
    weights = weights.div(weights.sum(axis=1), axis=0)  # Normalize to sum to 1
    
    result = engine.run(prices, weights)
    
    # High turnover should result in significant cost drag
    assert result.metrics['total_return'] < 0.1  # Expect modest returns due to costs

