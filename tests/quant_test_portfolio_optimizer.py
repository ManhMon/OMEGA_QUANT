"""
Unit Tests for OMEGA_QUANT Portfolio Optimizer
Phase 4.1: Portfolio Management - Portfolio Optimizer

100% Vectorized | NumPy-Powered | Institutional Grade
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer


@pytest.fixture
def optimizer():
    return PortfolioOptimizer()


@pytest.fixture
def sample_returns():
    np.random.seed(42)
    assets = ['AAPL', 'MSFT', 'GOOGL', 'AMZN']
    dates = pd.date_range('2023-01-01', periods=100)
    data = np.random.randn(100, 4) * 0.02
    return pd.DataFrame(data, index=dates, columns=assets)


def test_calculate_covariance(optimizer, sample_returns):
    cov = optimizer.calculate_covariance(sample_returns)
    assert cov.shape == (4, 4)
    assert np.allclose(cov, cov.T) # Symmetric
    assert np.all(np.linalg.eigvals(cov) >= -1e-9) # Positive semi-definite


def test_risk_parity_weights(optimizer, sample_returns):
    # Make AMZN very volatile
    sample_returns['AMZN'] *= 10
    weights = optimizer.calculate_risk_parity_weights(sample_returns)
    
    assert len(weights) == 4
    assert np.isclose(weights.sum(), 1.0)
    # Volatile asset should have lower weight
    assert weights['AMZN'] < weights['AAPL']


def test_project_constraints(optimizer):
    weights = pd.Series({'A': 0.5, 'B': 0.5, 'C': 0.5}, index=['A', 'B', 'C'])
    
    # 1. Test Single Stock Cap (0.1)
    projected = optimizer.project_constraints(weights, single_stock_cap=0.1)
    assert all(projected <= 0.1 + 1e-9)
    assert projected.abs().sum() <= 0.3 + 1e-9
    
    # 2. Test Gross Cap (1.0)
    weights = pd.Series({'A': 0.6, 'B': 0.6}, index=['A', 'B'])
    # Set single_stock_cap higher than weights to test ONLY gross_cap scaling
    projected = optimizer.project_constraints(weights, single_stock_cap=1.0, gross_cap=1.0)
    assert np.isclose(projected.abs().sum(), 1.0)
    
    # 3. Test Sector Cap
    weights = pd.Series({'A': 0.4, 'B': 0.4, 'C': 0.2}, index=['A', 'B', 'C'])
    asset_sectors = {'A': 'Tech', 'B': 'Tech', 'C': 'Bank'}
    sector_caps = {'Tech': 0.5}
    projected = optimizer.project_constraints(
        weights, 
        sector_caps=sector_caps, 
        asset_sectors=asset_sectors
    )
    # Tech sector sum (A+B) should be <= 0.5
    assert (projected['A'] + projected['B']) <= 0.5 + 1e-9


def test_risk_parity_weights_zero_vol(optimizer):
    # Case where all assets have zero volatility
    returns = pd.DataFrame({'A': [0, 0, 0], 'B': [0, 0, 0]})
    weights = optimizer.calculate_risk_parity_weights(returns)
    assert len(weights) == 2
    assert np.isclose(weights.sum(), 1.0)
    assert weights['A'] == 0.5
    assert weights['B'] == 0.5


def test_optimize_mean_variance_with_sectors(optimizer, sample_returns):
    expected_returns = pd.Series({'AAPL': 0.1, 'MSFT': 0.1, 'GOOGL': 0.01, 'AMZN': 0.01}, 
                                index=['AAPL', 'MSFT', 'GOOGL', 'AMZN'])
    cov = optimizer.calculate_covariance(sample_returns)
    
    asset_sectors = {'AAPL': 'Tech', 'MSFT': 'Tech', 'GOOGL': 'Tech', 'AMZN': 'Consumer'}
    sector_caps = {'Tech': 0.3} # Cap total Tech to 0.3
    
    weights = optimizer.optimize_mean_variance(
        expected_returns, 
        cov, 
        risk_aversion=1.0,
        single_stock_cap=0.5,
        gross_cap=1.0,
        sector_caps=sector_caps,
        asset_sectors=asset_sectors
    )
    
    tech_sum = weights[['AAPL', 'MSFT', 'GOOGL']].abs().sum()
    # Tech sector should be capped at 0.3
    assert tech_sum <= 0.3 + 1e-9
    # Gross exposure should be <= gross_cap (not necessarily equal)
    assert weights.abs().sum() <= 1.0 + 1e-9


def test_transaction_cost_and_turnover_penalty():
    """Test V21-ported transaction cost and turnover penalty in objective.
    
    Verifies both terms measurably reduce turnover and keep weights closer
    to previous weights under deterministic setup.
    """
    from omega.quant.portfolio_optimizer import PortfolioOptimizer, PortfolioConstraints
    
    assets = ['A', 'B', 'C']
    alpha_scores = pd.Series([0.2, 0.15, 0.1], index=assets)
    previous_weights = pd.Series([0.33, 0.33, 0.34], index=assets)
    
    optimizer_baseline = PortfolioOptimizer(
        risk_aversion=1.0,
        turnover_penalty=0.0,
        transaction_cost_bps=0.0
    )
    constraints_baseline = PortfolioConstraints(
        max_leverage=1.0,
        max_concentration=0.5,
        turnover_penalty=0.0,
        transaction_cost_bps=0.0
    )
    weights_baseline = optimizer_baseline.optimize_weights(
        alpha_scores,
        constraints=constraints_baseline,
        previous_weights=previous_weights
    )
    turnover_baseline = (weights_baseline - previous_weights).abs().sum()
    
    optimizer_penalty = PortfolioOptimizer(
        risk_aversion=1.0,
        turnover_penalty=50.0,
        transaction_cost_bps=0.0
    )
    constraints_penalty = PortfolioConstraints(
        max_leverage=1.0,
        max_concentration=0.5,
        turnover_penalty=50.0,
        transaction_cost_bps=0.0
    )
    weights_penalty = optimizer_penalty.optimize_weights(
        alpha_scores,
        constraints=constraints_penalty,
        previous_weights=previous_weights
    )
    turnover_penalty = (weights_penalty - previous_weights).abs().sum()
    
    optimizer_cost = PortfolioOptimizer(
        risk_aversion=1.0,
        turnover_penalty=0.0,
        transaction_cost_bps=1000.0
    )
    constraints_cost = PortfolioConstraints(
        max_leverage=1.0,
        max_concentration=0.5,
        turnover_penalty=0.0,
        transaction_cost_bps=1000.0
    )
    weights_cost = optimizer_cost.optimize_weights(
        alpha_scores,
        constraints=constraints_cost,
        previous_weights=previous_weights
    )
    turnover_cost = (weights_cost - previous_weights).abs().sum()
    
    assert weights_baseline.abs().sum() <= 1.0 + 1e-6
    assert weights_penalty.abs().sum() <= 1.0 + 1e-6
    assert weights_cost.abs().sum() <= 1.0 + 1e-6
    
    assert turnover_penalty < turnover_baseline
    assert turnover_cost < turnover_baseline
    
    distance_baseline = ((weights_baseline - previous_weights) ** 2).sum()
    distance_penalty = ((weights_penalty - previous_weights) ** 2).sum()
    distance_cost = ((weights_cost - previous_weights) ** 2).sum()
    
    assert distance_penalty < distance_baseline
    assert distance_cost < distance_baseline

