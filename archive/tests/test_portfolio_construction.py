"""
Tests for Portfolio Construction Engine - Phase 3.3 Fix Round 2

Tests cover:
1. Risk budgeting (Equal Risk Contribution, Risk Parity)
2. Factor exposure targeting
3. Hierarchical Risk Parity (HRP)
4. PIT safety validation (T-1 lag)
5. Institutional constraints validation (Position & Sector)
6. HRP Correctness (Recursive bisection)
7. PIT Bypass Prevention
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from src.portfolio.construction import PortfolioConstructionEngine
from src.portfolio.optimizer import OptimizationResult

@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    symbols = ["VNM", "VIC", "VHM", "HPG", "TCB"]
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    
    # Returns (5 symbols, 100 days)
    # Set seed for reproducibility
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.normal(0.001, 0.02, (100, 5)),
        index=dates,
        columns=symbols
    )
    
    # Factor exposures (5 symbols, 4 factors)
    factors = pd.DataFrame({
        "market": [1.0, 1.1, 1.2, 1.3, 1.4],
        "value": [0.5, -0.2, 0.3, 0.8, -0.1],
        "momentum": [-0.1, 0.5, 0.2, -0.3, 0.7],
        "quality": [0.8, 0.6, 0.9, 0.1, 0.4]
    }, index=symbols)
    
    sector_map = {
        "VNM": "Consumer",
        "VIC": "Real Estate",
        "VHM": "Real Estate",
        "HPG": "Materials",
        "TCB": "Financials"
    }
    
    return symbols, returns, factors, sector_map

@pytest.fixture
def engine():
    """Portfolio Construction Engine instance."""
    return PortfolioConstructionEngine()

def test_erc_construction(engine, sample_market_data):
    """Test Equal Risk Contribution (ERC) construction via PIT entry point."""
    symbols, returns, factors, sector_map = sample_market_data
    as_of_date = returns.index[-1]
    
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="erc"
    )
    
    assert isinstance(result, OptimizationResult)
    assert result.converged
    assert abs(sum(result.weights.values()) - 1.0) < 1e-6
    
    # Check risk contributions are roughly equal
    w = np.array([result.weights[s] for s in symbols])
    cov = returns.iloc[:-1].cov().values # T-1 cov
    port_vol = np.sqrt(w @ cov @ w)
    rc = w * (cov @ w) / port_vol
    target_rc = port_vol / len(symbols)
    relative_deviations = np.abs(rc - target_rc) / (target_rc + 1e-10)
    assert np.mean(relative_deviations) < 0.4

def test_factor_targeting(engine, sample_market_data):
    """Test factor exposure targeting via PIT entry point."""
    symbols, returns, factors, _ = sample_market_data
    as_of_date = returns.index[-1]
    
    # Target: High quality, low market beta
    targets = {"quality": 0.7, "market": 1.0}
    
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="factor_targeting",
        factor_exposures=factors, target_exposures=targets
    )
    
    assert result.converged
    w = np.array([result.weights[s] for s in symbols])
    
    # Verify exposures
    for factor, target in targets.items():
        exposure = np.dot(w, factors[factor].values)
        assert abs(exposure - target) < 0.25

def test_hrp_construction(engine, sample_market_data):
    """Test Hierarchical Risk Parity (HRP) construction via PIT entry point."""
    symbols, returns, _, _ = sample_market_data
    as_of_date = returns.index[-1]
    
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="hrp"
    )
    
    assert result.converged
    assert abs(sum(result.weights.values()) - 1.0) < 1e-6
    assert all(w >= 0 for w in result.weights.values())
    # HRP should be diversified
    assert all(w < 0.6 for w in result.weights.values())

def test_pit_safety_enforcement(engine, sample_market_data):
    """Test PIT safety (T-1 lag enforcement)."""
    symbols, returns, _, _ = sample_market_data
    as_of_date = returns.index[-1]
    
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="erc"
    )
    
    assert result.converged
    assert "T-1 lag applied" in result.message
    # Cutoff should be as_of_date - 1 day
    cutoff_date = (as_of_date - pd.Timedelta(days=1)).date()
    assert str(cutoff_date) in result.message

def test_sector_constraints_erc(engine, sample_market_data):
    """Test sector constraints in ERC."""
    symbols, returns, factors, sector_map = sample_market_data
    as_of_date = returns.index[-1]
    
    # Real Estate has VIC and VHM. Set max sector to 30%.
    max_sec = 0.30
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="erc",
        sector_map=sector_map, max_sector=max_sec
    )
    
    re_weight = result.weights["VIC"] + result.weights["VHM"]
    assert re_weight <= max_sec + 1e-5

def test_sector_constraints_factor(engine, sample_market_data):
    """Test sector constraints in Factor Targeting."""
    symbols, returns, factors, sector_map = sample_market_data
    as_of_date = returns.index[-1]
    targets = {"market": 1.0}
    
    max_sec = 0.25
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="factor_targeting",
        factor_exposures=factors, target_exposures=targets,
        sector_map=sector_map, max_sector=max_sec
    )
    
    re_weight = result.weights["VIC"] + result.weights["VHM"]
    assert re_weight <= max_sec + 1e-5

def test_sector_constraints_hrp(engine, sample_market_data):
    """Test sector constraints in HRP."""
    symbols, returns, factors, sector_map = sample_market_data
    as_of_date = returns.index[-1]
    
    # Feasible because 4 sectors x 27% >= 100%; still binding for Real Estate cluster
    max_sec = 0.27
    result = engine.build_portfolio_at_date(
        as_of_date, symbols, returns, method="hrp",
        max_position=0.40,
        sector_map=sector_map, max_sector=max_sec
    )
    
    re_weight = result.weights["VIC"] + result.weights["VHM"]
    assert re_weight <= max_sec + 1e-5

def test_pit_bypass_prevention(engine, sample_market_data):
    """Verify direct build methods are internal and not easily bypassable."""
    assert not hasattr(engine, "build_erc_portfolio")
    assert hasattr(engine, "_build_erc_portfolio")
    assert not hasattr(engine, "build_hrp_portfolio")
    assert hasattr(engine, "_build_hrp_portfolio")

def test_insufficient_data_error(engine, sample_market_data):
    """Test error handling for insufficient data."""
    symbols, returns, _, _ = sample_market_data
    # Use only 10 days of data
    short_returns = returns.iloc[:10]
    as_of_date = short_returns.index[-1]
    
    with pytest.raises(ValueError, match="Insufficient data"):
        engine.build_portfolio_at_date(as_of_date, symbols, short_returns)

def test_hrp_correctness_logic(engine, sample_market_data):
    """Sanity check for HRP recursive allocation logic."""
    symbols, returns, _, _ = sample_market_data
    # 2 assets, highly correlated
    syms = ["A", "B"]
    cov = np.array([[1.0, 0.9], [0.9, 1.0]])
    corr = np.array([[1.0, 0.9], [0.9, 1.0]])
    
    # Internal call for logic check
    result = engine._build_hrp_portfolio(syms, cov, corr)
    # For identical risk, should be 50/50
    assert abs(result.weights["A"] - 0.5) < 1e-2
    assert abs(result.weights["B"] - 0.5) < 1e-2
    
    # 2 assets, A much riskier than B
    cov2 = np.array([[10.0, 0.0], [0.0, 1.0]])
    corr2 = np.eye(2)
    result2 = engine._build_hrp_portfolio(syms, cov2, corr2, max_position=1.0)
    # B should have higher weight
    assert result2.weights["B"] > result2.weights["A"]
