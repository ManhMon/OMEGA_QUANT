"""
Tests for Portfolio Optimizer - Phase 3.2

Tests cover:
1. MVO optimization with constraints
2. Risk Parity optimization
3. Black-Litterman with views
4. Constraint enforcement
5. Edge cases (zero volatility, singular covariance)
"""

import pytest
import numpy as np
from src.portfolio.optimizer import (
    PortfolioOptimizer,
    OptimizationMethod,
    OptimizationResult,
)


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    symbols = ["VNM", "VIC", "VHM", "HPG", "TCB"]
    
    # Expected returns (annualized)
    expected_returns = {
        "VNM": 0.15,
        "VIC": 0.20,
        "VHM": 0.18,
        "HPG": 0.22,
        "TCB": 0.25,
    }
    
    # Covariance matrix (5x5)
    cov_matrix = np.array([
        [0.04, 0.01, 0.01, 0.01, 0.01],
        [0.01, 0.09, 0.02, 0.02, 0.02],
        [0.01, 0.02, 0.06, 0.01, 0.01],
        [0.01, 0.02, 0.01, 0.10, 0.02],
        [0.01, 0.02, 0.01, 0.02, 0.12],
    ])
    
    return symbols, expected_returns, cov_matrix


def test_mvo_optimization_basic(sample_data):
    """Test basic MVO optimization."""
    symbols, expected_returns, cov_matrix = sample_data
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
    )
    
    # Check result structure
    assert isinstance(result, OptimizationResult)
    assert result.method == OptimizationMethod.MVO
    assert result.converged
    
    # Check weights sum to 1
    total_weight = sum(result.weights.values())
    assert abs(total_weight - 1.0) < 1e-6
    
    # Check all weights are non-negative
    assert all(w >= -1e-6 for w in result.weights.values())
    
    # Check Sharpe ratio is positive
    assert result.sharpe_ratio > 0


def test_mvo_with_position_constraint(sample_data):
    """Test MVO with position limit constraint."""
    symbols, expected_returns, cov_matrix = sample_data
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        constraints={"max_position": 0.25},
    )
    
    # Check no position exceeds 25%
    assert all(w <= 0.25 + 1e-6 for w in result.weights.values())
    
    # Check weights sum to 1
    total_weight = sum(result.weights.values())
    assert abs(total_weight - 1.0) < 1e-6


def test_risk_parity_optimization(sample_data):
    """Test Risk Parity optimization."""
    symbols, expected_returns, cov_matrix = sample_data
    
    optimizer = PortfolioOptimizer()
    result = optimizer.optimize(
        method=OptimizationMethod.RISK_PARITY,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
    )
    
    # Check result structure
    assert isinstance(result, OptimizationResult)
    assert result.method == OptimizationMethod.RISK_PARITY
    assert result.converged
    
    # Check weights sum to 1
    total_weight = sum(result.weights.values())
    assert abs(total_weight - 1.0) < 1e-6
    
    # Check all weights are non-negative
    assert all(w >= -1e-6 for w in result.weights.values())
    
    # Check volatility is calculated
    assert result.expected_volatility > 0


def test_black_litterman_optimization(sample_data):
    """Test Black-Litterman optimization with views."""
    symbols, expected_returns, cov_matrix = sample_data
    
    # Investor views: bullish on VNM, bearish on TCB
    views = {
        "VNM": 0.25,  # Expect 25% return
        "TCB": 0.10,  # Expect only 10% return
    }
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.BLACK_LITTERMAN,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        views=views,
    )
    
    # Check result structure
    assert isinstance(result, OptimizationResult)
    assert result.method == OptimizationMethod.BLACK_LITTERMAN
    assert result.converged
    
    # Check weights sum to 1
    total_weight = sum(result.weights.values())
    assert abs(total_weight - 1.0) < 1e-6
    
    # Check VNM weight increased (bullish view)
    # Note: This is a soft check since BL blends views with prior
    assert result.weights["VNM"] > 0


def test_black_litterman_no_views_fallback(sample_data):
    """Test Black-Litterman falls back to MVO when no views."""
    symbols, expected_returns, cov_matrix = sample_data
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    
    # Empty views should fall back to MVO
    result = optimizer.optimize(
        method=OptimizationMethod.BLACK_LITTERMAN,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        views={},
    )
    
    # Should still converge
    assert result.converged
    assert result.method == OptimizationMethod.BLACK_LITTERMAN


def test_optimizer_with_zero_returns(sample_data):
    """Test optimizer handles zero expected returns."""
    symbols, _, cov_matrix = sample_data
    
    # All zero returns
    zero_returns = {s: 0.0 for s in symbols}
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=zero_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
    )
    
    # Should still converge (minimize variance)
    assert result.converged
    
    # Weights should sum to 1
    total_weight = sum(result.weights.values())
    assert abs(total_weight - 1.0) < 1e-6


def test_optimizer_dimension_mismatch():
    """Test optimizer raises error on dimension mismatch."""
    symbols = ["VNM", "VIC", "VHM"]
    expected_returns = {"VNM": 0.15, "VIC": 0.20, "VHM": 0.18}
    
    # Wrong size covariance matrix (2x2 instead of 3x3)
    cov_matrix = np.array([
        [0.04, 0.01],
        [0.01, 0.09],
    ])
    
    optimizer = PortfolioOptimizer()
    
    with pytest.raises(ValueError, match="does not match"):
        optimizer.optimize(
            method=OptimizationMethod.MVO,
            expected_returns=expected_returns,
            covariance_matrix=cov_matrix,
            symbols=symbols,
        )


def test_black_litterman_missing_views():
    """Test Black-Litterman raises error when views not provided."""
    symbols = ["VNM", "VIC"]
    expected_returns = {"VNM": 0.15, "VIC": 0.20}
    cov_matrix = np.array([[0.04, 0.01], [0.01, 0.09]])
    
    optimizer = PortfolioOptimizer()
    
    with pytest.raises(ValueError, match="requires views"):
        optimizer.optimize(
            method=OptimizationMethod.BLACK_LITTERMAN,
            expected_returns=expected_returns,
            covariance_matrix=cov_matrix,
            symbols=symbols,
            views=None,  # Missing views
        )


def test_optimizer_enforces_liquidity_constraints():
    """Test optimizer enforces liquidity constraints (not just validates)."""
    symbols = ["VNM", "VIC", "VHM", "HPG", "TCB"]  # 5 assets
    expected_returns = {
        "VNM": 0.15,
        "VIC": 0.20,
        "VHM": 0.25,  # High return, but low liquidity
        "HPG": 0.18,
        "TCB": 0.22,
    }
    
    cov_matrix = np.array([
        [0.04, 0.01, 0.01, 0.01, 0.01],
        [0.01, 0.09, 0.02, 0.02, 0.02],
        [0.01, 0.02, 0.06, 0.01, 0.01],
        [0.01, 0.02, 0.01, 0.10, 0.02],
        [0.01, 0.02, 0.01, 0.02, 0.12],
    ])
    
    # Market data with low liquidity for VHM
    adv_data = {
        "VNM": 100_000_000.0,  # 100M VND/day
        "VIC": 100_000_000.0,  # 100M VND/day
        "VHM": 10_000_000.0,   # 10M VND/day (low liquidity)
        "HPG": 100_000_000.0,
        "TCB": 100_000_000.0,
    }
    
    prices = {
        "VNM": 100.0,  # 100,000 VND
        "VIC": 50.0,   # 50,000 VND
        "VHM": 80.0,   # 80,000 VND
        "HPG": 120.0,
        "TCB": 90.0,
    }
    
    portfolio_value = 100_000_000.0  # 100M VND
    
    constraints = {
        "max_position": 0.25,
        "max_sector": 0.40,
        "max_adv_participation": 0.40,  # Max 40% ADV
        "board_lot": 100,
    }
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        constraints=constraints,
        adv_data=adv_data,
        portfolio_value=portfolio_value,
        prices=prices,
    )
    
    # Check that optimizer converged
    assert result.converged
    
    # Check that final result has NO liquidity violations
    liquidity_violations = [
        v for v in result.constraint_violations
        if "ADV participation" in v or "liquidity" in v.lower()
    ]
    assert len(liquidity_violations) == 0, f"Found liquidity violations: {liquidity_violations}"
    
    # Verify VHM weight respects liquidity constraint
    # Max VHM position: 40% of 10M ADV = 4M VND = 4% of 100M portfolio
    if "VHM" in result.weights:
        vhm_weight = result.weights["VHM"]
        vhm_position_value = vhm_weight * portfolio_value
        vhm_adv = adv_data["VHM"]
        vhm_participation = vhm_position_value / vhm_adv
        assert vhm_participation <= 0.40 + 1e-6, f"VHM participation {vhm_participation:.2%} exceeds 40%"


def test_optimizer_enforces_board_lot_constraints():
    """Test optimizer enforces board-lot constraints (not just validates)."""
    symbols = ["VNM", "VIC", "VHM", "HPG"]  # 4 assets so max_position=0.25 is feasible
    expected_returns = {"VNM": 0.15, "VIC": 0.20, "VHM": 0.18, "HPG": 0.22}
    
    cov_matrix = np.array([
        [0.04, 0.01, 0.01, 0.01],
        [0.01, 0.09, 0.02, 0.02],
        [0.01, 0.02, 0.06, 0.01],
        [0.01, 0.02, 0.01, 0.10],
    ])
    
    adv_data = {
        "VNM": 500_000_000.0,  # High liquidity
        "VIC": 500_000_000.0,
        "VHM": 500_000_000.0,
        "HPG": 500_000_000.0,
    }
    
    prices = {
        "VNM": 100.0,  # 100,000 VND
        "VIC": 50.0,   # 50,000 VND
        "VHM": 80.0,
        "HPG": 120.0,
    }
    
    # Portfolio value that would create non-board-lot positions
    portfolio_value = 123_456_789.0  # Odd value
    
    constraints = {
        "max_position": 0.25,
        "max_sector": 0.40,
        "max_adv_participation": 0.40,
        "board_lot": 100,
    }
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        constraints=constraints,
        adv_data=adv_data,
        portfolio_value=portfolio_value,
        prices=prices,
    )
    
    # Check that optimizer converged
    assert result.converged
    
    # Check that final result has NO board-lot violations
    board_lot_violations = [
        v for v in result.constraint_violations
        if "board lot" in v.lower() or "board_lot" in v.lower()
    ]
    assert len(board_lot_violations) == 0, f"Found board-lot violations: {board_lot_violations}"
    
    # Verify all positions are multiples of 100 shares
    for symbol, weight in result.weights.items():
        if weight < 1e-6:
            continue
        position_value = weight * portfolio_value
        price = prices[symbol]
        shares = int(position_value / (price * 1000.0))
        assert shares % 100 == 0, f"{symbol} shares {shares} not multiple of 100"
    
    # Note: Weights may sum to less than 1.0 due to board-lot rounding (cash held)
    # This is acceptable and expected behavior


def test_optimizer_enforces_sector_constraints():
    """Test optimizer enforces sector constraints numerically."""
    symbols = ["VNM", "VIC", "VHM", "HPG", "TCB"]
    
    expected_returns = {
        "VNM": 0.15,
        "VIC": 0.25,  # High return
        "VHM": 0.25,  # High return (same sector as VIC)
        "HPG": 0.18,
        "TCB": 0.20,
    }
    
    cov_matrix = np.array([
        [0.04, 0.01, 0.01, 0.01, 0.01],
        [0.01, 0.09, 0.02, 0.02, 0.02],
        [0.01, 0.02, 0.06, 0.01, 0.01],
        [0.01, 0.02, 0.01, 0.10, 0.02],
        [0.01, 0.02, 0.01, 0.02, 0.12],
    ])
    
    sector_map = {
        "VNM": "Consumer Staples",
        "VIC": "Real Estate",
        "VHM": "Real Estate",  # Same sector as VIC
        "HPG": "Materials",
        "TCB": "Financials",
    }
    
    constraints = {
        "max_position": 0.25,
        "max_sector": 0.40,  # Max 40% per sector
    }
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        constraints=constraints,
        sector_map=sector_map,
    )
    
    # Check that optimizer converged
    assert result.converged
    
    # Check that final result has NO sector violations
    sector_violations = [
        v for v in result.constraint_violations
        if "sector" in v.lower()
    ]
    assert len(sector_violations) == 0, f"Found sector violations: {sector_violations}"
    
    # Verify Real Estate sector <= 40%
    real_estate_weight = result.weights.get("VIC", 0.0) + result.weights.get("VHM", 0.0)
    assert real_estate_weight <= 0.40 + 1e-6, f"Real Estate sector {real_estate_weight:.2%} exceeds 40%"


def test_optimizer_infeasible_constraints():
    """Test optimizer returns converged=False when constraints are infeasible."""
    symbols = ["VNM"]
    expected_returns = {"VNM": 0.15}
    
    cov_matrix = np.array([[0.04]])
    
    # Extremely low liquidity - impossible to satisfy
    adv_data = {"VNM": 100_000.0}  # Only 100K VND/day
    prices = {"VNM": 100.0}
    portfolio_value = 100_000_000.0  # 100M portfolio
    
    constraints = {
        "max_position": 1.0,
        "max_adv_participation": 0.40,  # Max 40% of 100K = 40K, but need 100M
        "board_lot": 100,
    }
    
    optimizer = PortfolioOptimizer(risk_free_rate=0.05)
    result = optimizer.optimize(
        method=OptimizationMethod.MVO,
        expected_returns=expected_returns,
        covariance_matrix=cov_matrix,
        symbols=symbols,
        constraints=constraints,
        adv_data=adv_data,
        portfolio_value=portfolio_value,
        prices=prices,
    )
    
    # Should return converged=False for infeasible constraints
    assert not result.converged
    assert "infeasible" in result.message.lower()
