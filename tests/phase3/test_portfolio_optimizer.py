"""Tests for PortfolioOptimizer Phase 3.2."""

import pytest
import numpy as np
import pandas as pd
from omega.quant.portfolio_optimizer import (
    PortfolioOptimizer, 
    PortfolioConstraints,
    PortfolioMetrics
)

@pytest.fixture
def sample_data():
    """Create sample alpha scores and returns for 10 assets."""
    np.random.seed(42)
    assets = [f'ASSET_{i}' for i in range(10)]
    
    # 10 assets, 100 days of returns
    returns = pd.DataFrame(
        np.random.normal(0.0005, 0.01, size=(100, 10)),
        columns=assets,
        index=pd.date_range('2023-01-01', periods=100)
    )
    
    # Alpha scores (expected returns)
    alpha_scores = pd.Series(
        np.random.normal(0.001, 0.005, size=10),
        index=assets
    )
    
    # Covariance matrix
    covariance_matrix = returns.cov()
    
    return alpha_scores, returns, covariance_matrix

def test_optimizer_initialization():
    """Test PortfolioOptimizer initialization with default and custom values."""
    optimizer = PortfolioOptimizer()
    assert optimizer.max_leverage == 1.0
    assert optimizer.max_concentration == 0.1
    
    optimizer_custom = PortfolioOptimizer(max_leverage=2.0, max_concentration=0.5)
    assert optimizer_custom.max_leverage == 2.0
    assert optimizer_custom.max_concentration == 0.5

def test_optimize_weights_long_only(sample_data):
    """Test basic long-only optimization."""
    alpha_scores, _, covariance_matrix = sample_data
    optimizer = PortfolioOptimizer(max_leverage=1.0, max_concentration=0.2)
    
    weights = optimizer.optimize_weights(alpha_scores, covariance_matrix=covariance_matrix)
    
    # Check shape and index
    assert isinstance(weights, pd.Series)
    assert len(weights) == len(alpha_scores)
    assert weights.index.equals(alpha_scores.index)
    
    # Check constraints
    assert (weights >= 0).all()  # Default min_weight is 0
    assert (weights <= 0.2 + 1e-10).all()  # Max concentration
    assert weights.sum() <= 1.0 + 1e-10  # Max leverage

def test_optimize_weights_leverage_limit(sample_data):
    """Test that optimizer respects leverage limits."""
    alpha_scores, _, covariance_matrix = sample_data
    # High alpha to force high leverage if allowed
    alpha_scores = alpha_scores * 10 
    
    max_lev = 1.5
    optimizer = PortfolioOptimizer(max_leverage=max_lev, max_concentration=0.5)
    
    weights = optimizer.optimize_weights(alpha_scores, covariance_matrix=covariance_matrix)
    
    assert weights.abs().sum() <= max_lev + 1e-10

def test_optimize_weights_concentration_limit(sample_data):
    """Test that optimizer respects concentration limits."""
    alpha_scores, _, covariance_matrix = sample_data
    # One asset has very high alpha
    alpha_scores.iloc[0] = 1.0 
    
    max_conc = 0.15
    optimizer = PortfolioOptimizer(max_leverage=1.0, max_concentration=max_conc)
    
    weights = optimizer.optimize_weights(alpha_scores, covariance_matrix=covariance_matrix)
    
    assert weights.max() <= max_conc + 1e-10

def test_calculate_portfolio_metrics(sample_data):
    """Test metric calculation logic."""
    alpha_scores, returns, covariance_matrix = sample_data
    optimizer = PortfolioOptimizer()
    
    # Create dummy weights
    weights = pd.Series(0.1, index=alpha_scores.index)
    
    metrics = optimizer.calculate_portfolio_metrics(weights, returns)
    
    assert isinstance(metrics, PortfolioMetrics)
    assert metrics.gross_leverage == pytest.approx(1.0)
    assert metrics.num_positions == 10
    assert metrics.max_weight == 0.1
    assert hasattr(metrics, 'sharpe_ratio')

def test_apply_constraints_manual(sample_data):
    """Test manual application of constraints."""
    alpha_scores, _, _ = sample_data
    optimizer = PortfolioOptimizer()
    
    # Create invalid weights
    raw_weights = pd.Series(0.5, index=alpha_scores.index) # Total = 5.0, Max = 0.5
    
    constraints = PortfolioConstraints(max_leverage=1.0, max_concentration=0.2)
    constrained_weights = optimizer.apply_constraints(raw_weights, constraints)
    
    assert constrained_weights.max() <= 0.2 + 1e-10
    assert constrained_weights.sum() <= 1.0 + 1e-10

def test_turnover_constraint(sample_data):
    """Test turnover constraint during optimization."""
    alpha_scores, _, covariance_matrix = sample_data
    optimizer = PortfolioOptimizer(max_leverage=1.0, max_concentration=0.2)
    
    # Previous weights: all in first asset
    prev_weights = pd.Series(0.0, index=alpha_scores.index)
    prev_weights.iloc[0] = 1.0
    
    # Tight turnover limit
    constraints = PortfolioConstraints(
        max_leverage=1.0,
        max_concentration=1.0,
        max_turnover=0.1
    )
    
    new_weights = optimizer.optimize_weights(
        alpha_scores, 
        constraints=constraints,
        covariance_matrix=covariance_matrix,
        previous_weights=prev_weights
    )
    
    turnover = (new_weights - prev_weights).abs().sum()
    assert turnover <= 0.1 + 1e-10

def test_input_validation():
    """Test that optimizer handles invalid inputs."""
    optimizer = PortfolioOptimizer()
    
    # Empty alpha scores
    with pytest.raises(ValueError, match="alpha_scores cannot be empty"):
        optimizer.optimize_weights(pd.Series(dtype=float))
    
    # NaN in alpha scores
    with pytest.raises(ValueError, match="alpha_scores contains NaN"):
        optimizer.optimize_weights(pd.Series([np.nan, 0.1], index=['A', 'B']))
    
    # Misaligned covariance matrix
    alpha = pd.Series([0.1, 0.2], index=['A', 'B'])
    cov = pd.DataFrame(np.eye(2), index=['A', 'C'], columns=['A', 'C'])
    with pytest.raises(ValueError, match="indices must match"):
        optimizer.optimize_weights(alpha, covariance_matrix=cov)
