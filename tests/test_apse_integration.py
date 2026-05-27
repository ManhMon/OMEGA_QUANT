"""Integration tests for APSE, ConstraintSolver, and PortfolioOptimizer."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from omega.quant.adaptive_portfolio_sizing import AdaptivePortfolioSizingEngine
from omega.quant.constraint_solver import ConstraintSolver
from omega.quant.portfolio_optimizer import PortfolioOptimizer, PortfolioConstraints


@pytest.fixture
def sample_market_data():
    """Sample prices and returns for 4 tickers."""
    prices = pd.DataFrame([
        {'asset': 'AAPL', 'as_of': datetime(2026, 1, 1), 'price': 150.0},
        {'asset': 'GOOGL', 'as_of': datetime(2026, 1, 1), 'price': 2800.0},
        {'asset': 'MSFT', 'as_of': datetime(2026, 1, 1), 'price': 380.0},
        {'asset': 'TSLA', 'as_of': datetime(2026, 1, 1), 'price': 250.0},
    ])
    
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) - timedelta(days=i) for i in range(30, 0, -1)]
    data = []
    for date in dates:
        data.extend([
            {'asset': 'AAPL', 'as_of': date, 'return': np.random.normal(0.001, 0.02)},
            {'asset': 'GOOGL', 'as_of': date, 'return': np.random.normal(0.0012, 0.025)},
            {'asset': 'MSFT', 'as_of': date, 'return': np.random.normal(0.0008, 0.018)},
            {'asset': 'TSLA', 'as_of': date, 'return': np.random.normal(0.0015, 0.035)},
        ])
    returns = pd.DataFrame(data)
    
    return prices, returns


@pytest.fixture
def industry_map():
    return {
        'AAPL': 'Technology',
        'GOOGL': 'Technology',
        'MSFT': 'Technology',
        'TSLA': 'Automotive'
    }


def test_apse_to_solver_and_optimizer(sample_market_data, industry_map) -> None:
    prices, returns = sample_market_data
    as_of = datetime(2026, 1, 1)
    
    # 1. Initialize APSE for Small Capital Tier (10B VND)
    apse = AdaptivePortfolioSizingEngine(
        capital=10_000_000_000,
        market_regime="neutral",
        alpha_quality=0.05
    )
    adaptive_config = apse.optimize(as_of=as_of)
    
    # 2. Convert to ConstraintConfig
    constraint_config = adaptive_config.to_constraint_config(as_of=as_of, available_at=as_of)
    solver = ConstraintSolver(constraint_config)
    
    # Verify ConstraintSolver is functional with APSE parameters
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},
        {'asset': 'GOOGL', 'quantity': 50},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, prices, industry_map, as_of, current_cash=100000.0
    )
    
    # It should run successfully (validity depends on positions)
    assert isinstance(is_valid, bool)
    
    # 3. Convert to OptimizerConfig
    optimizer_config = adaptive_config.to_optimizer_config()
    optimizer = PortfolioOptimizer(config=optimizer_config)
    
    # Verify PortfolioOptimizer is functional with APSE parameters
    alpha_scores = pd.Series({'AAPL': 0.05, 'GOOGL': 0.08, 'MSFT': 0.03, 'TSLA': 0.04})
    
    # Convert constraints
    optimizer_constraints = PortfolioConstraints(
        max_leverage=optimizer_config.max_leverage,
        max_concentration=optimizer_config.max_concentration,
        min_weight=optimizer_config.min_weight,
        max_weight=optimizer_config.max_weight
    )
    
    # Run optimization
    weights = optimizer.optimize_weights(
        alpha_scores=alpha_scores,
        constraints=optimizer_constraints
    )
    
    assert isinstance(weights, pd.Series)
    assert len(weights) == 4
    # All weights should be within max_concentration cap (APSE max_asset_cap)
    for asset, weight in weights.items():
        assert weight <= adaptive_config.max_asset_cap + 1e-6
