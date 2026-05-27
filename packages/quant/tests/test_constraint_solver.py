"""
OMEGA_QUANT Constraint Solver Tests
Phase 20: Comprehensive test suite for constraint validation and portfolio optimization

Author: Backend Engineer (Role 9)
Created: 2026-05-19
Version: 1.0.0
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from omega.quant.constraint_solver import (
    ConstraintConfig,
    ConstraintSolver,
    ConstraintViolation
)


@pytest.fixture
def base_config():
    """Base constraint configuration for testing."""
    return ConstraintConfig(
        max_notional_per_asset=100000.0,
        max_leverage=2.0,
        max_industry_concentration=0.4,
        max_asset_concentration=0.3,
        as_of=datetime(2026, 1, 1),
        available_at=datetime(2026, 1, 1),
        long_only=True,
        board_lot_size=100,
        min_cash_balance=10000.0
    )


@pytest.fixture
def sample_prices():
    """Sample price data."""
    return pd.DataFrame([
        {'asset': 'AAPL', 'as_of': datetime(2026, 1, 1), 'price': 150.0},
        {'asset': 'GOOGL', 'as_of': datetime(2026, 1, 1), 'price': 2800.0},
        {'asset': 'MSFT', 'as_of': datetime(2026, 1, 1), 'price': 380.0},
        {'asset': 'TSLA', 'as_of': datetime(2026, 1, 1), 'price': 250.0},
    ])


@pytest.fixture
def sample_returns():
    """Sample return data for optimization."""
    np.random.seed(42)  # Seed RNG for deterministic tests
    dates = [datetime(2026, 1, 1) - timedelta(days=i) for i in range(30, 0, -1)]
    data = []
    for date in dates:
        data.extend([
            {'asset': 'AAPL', 'as_of': date, 'return': np.random.normal(0.001, 0.02)},
            {'asset': 'GOOGL', 'as_of': date, 'return': np.random.normal(0.0012, 0.025)},
            {'asset': 'MSFT', 'as_of': date, 'return': np.random.normal(0.0008, 0.018)},
            {'asset': 'TSLA', 'as_of': date, 'return': np.random.normal(0.0015, 0.035)},
        ])
    return pd.DataFrame(data)


@pytest.fixture
def industry_map():
    """Sample industry mapping."""
    return {
        'AAPL': 'Technology',
        'GOOGL': 'Technology',
        'MSFT': 'Technology',
        'TSLA': 'Automotive'
    }


# Test 1: ConstraintConfig validation - valid config
def test_constraint_config_valid(base_config):
    """Test that valid constraint config is accepted."""
    assert base_config.max_notional_per_asset == 100000.0
    assert base_config.long_only is True
    assert base_config.board_lot_size == 100


# Test 2: ConstraintConfig validation - negative max_notional
def test_constraint_config_negative_notional():
    """Test that negative max_notional_per_asset raises ValueError."""
    with pytest.raises(ValueError, match="max_notional_per_asset must be positive"):
        ConstraintConfig(
            max_notional_per_asset=-100.0,
            max_leverage=2.0,
            max_industry_concentration=0.4,
            max_asset_concentration=0.3,
            as_of=datetime(2026, 1, 1),
            available_at=datetime(2026, 1, 1)
        )


# Test 3: ConstraintConfig validation - negative board_lot_size
def test_constraint_config_negative_board_lot():
    """Test that negative board_lot_size raises ValueError."""
    with pytest.raises(ValueError, match="board_lot_size must be positive"):
        ConstraintConfig(
            max_notional_per_asset=100000.0,
            max_leverage=2.0,
            max_industry_concentration=0.4,
            max_asset_concentration=0.3,
            as_of=datetime(2026, 1, 1),
            available_at=datetime(2026, 1, 1),
            board_lot_size=-100
        )


# Test 4: ConstraintConfig validation - negative min_cash_balance
def test_constraint_config_negative_cash():
    """Test that negative min_cash_balance raises ValueError."""
    with pytest.raises(ValueError, match="min_cash_balance cannot be negative"):
        ConstraintConfig(
            max_notional_per_asset=100000.0,
            max_leverage=2.0,
            max_industry_concentration=0.4,
            max_asset_concentration=0.3,
            as_of=datetime(2026, 1, 1),
            available_at=datetime(2026, 1, 1),
            min_cash_balance=-1000.0
        )


# Test 4.5: Max notional per asset violation
def test_max_notional_per_asset_violation(base_config, sample_prices, industry_map):
    """Test that position exceeding max_notional_per_asset triggers violation."""
    # Override config with small max_notional for easier violation triggering
    config = ConstraintConfig(
        max_notional_per_asset=10000.0,  # 10k max notional
        max_leverage=2.0,
        max_industry_concentration=0.4,
        max_asset_concentration=0.3,
        as_of=datetime(2026, 1, 1),
        available_at=datetime(2026, 1, 1),
        long_only=True,
        board_lot_size=100,
        min_cash_balance=1000.0
    )
    solver = ConstraintSolver(config)
    
    # AAPL price is 150. Quantity 100 -> notional 15000 (exceeds 10k limit)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    notional_violations = [v for v in violations if v.constraint_type == 'max_notional_per_asset']
    assert len(notional_violations) == 1
    assert notional_violations[0].asset == 'AAPL'
    assert notional_violations[0].current_value == 15000.0
    assert notional_violations[0].limit_value == 10000.0
    assert notional_violations[0].excess == 5000.0


# Test 5: Long-only constraint - no violations
def test_long_only_no_violations(base_config, sample_prices, industry_map):
    """Test that long-only positions pass validation."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},
        {'asset': 'GOOGL', 'quantity': 50},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    long_only_violations = [v for v in violations if v.constraint_type == 'long_only']
    assert len(long_only_violations) == 0


# Test 6: Long-only constraint - with violations
def test_long_only_with_violations(base_config, sample_prices, industry_map):
    """Test that short positions violate long-only constraint."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},
        {'asset': 'GOOGL', 'quantity': -50},  # Short position
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    long_only_violations = [v for v in violations if v.constraint_type == 'long_only']
    assert len(long_only_violations) == 1
    assert long_only_violations[0].asset == 'GOOGL'
    assert long_only_violations[0].current_value == -50


# Test 7: Long-only disabled - short positions allowed
def test_long_only_disabled(sample_prices, industry_map):
    """Test that short positions are allowed when long_only=False."""
    config = ConstraintConfig(
        max_notional_per_asset=100000.0,
        max_leverage=2.0,
        max_industry_concentration=0.4,
        max_asset_concentration=0.3,
        as_of=datetime(2026, 1, 1),
        available_at=datetime(2026, 1, 1),
        long_only=False
    )
    solver = ConstraintSolver(config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},
        {'asset': 'GOOGL', 'quantity': -50},  # Short position
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    long_only_violations = [v for v in violations if v.constraint_type == 'long_only']
    assert len(long_only_violations) == 0


# Test 8: Board lot constraint - no violations
def test_board_lot_no_violations(base_config, sample_prices, industry_map):
    """Test that positions in multiples of board_lot_size pass validation."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},  # Multiple of 100
        {'asset': 'GOOGL', 'quantity': 200},  # Multiple of 100
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    board_lot_violations = [v for v in violations if v.constraint_type == 'board_lot']
    assert len(board_lot_violations) == 0


# Test 9: Board lot constraint - with violations
def test_board_lot_with_violations(base_config, sample_prices, industry_map):
    """Test that positions not in multiples of board_lot_size violate constraint."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 150},  # Not multiple of 100
        {'asset': 'GOOGL', 'quantity': 200},  # Multiple of 100
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    board_lot_violations = [v for v in violations if v.constraint_type == 'board_lot']
    assert len(board_lot_violations) == 1
    assert board_lot_violations[0].asset == 'AAPL'


# Test 10: Board lot constraint - zero position allowed
def test_board_lot_zero_position(base_config, sample_prices, industry_map):
    """Test that zero positions don't violate board lot constraint."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0},
        {'asset': 'GOOGL', 'quantity': 100},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    board_lot_violations = [v for v in violations if v.constraint_type == 'board_lot']
    assert len(board_lot_violations) == 0


# Test 11: Cash balance constraint - sufficient cash
def test_cash_balance_sufficient(base_config, sample_prices, industry_map):
    """Test that sufficient cash balance passes validation."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},  # Cost: 15,000
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=50000.0
    )
    
    cash_violations = [v for v in violations if v.constraint_type == 'min_cash_balance']
    assert len(cash_violations) == 0


# Test 12: Cash balance constraint - insufficient cash
def test_cash_balance_insufficient(base_config, sample_prices, industry_map):
    """Test that insufficient cash balance violates constraint."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},  # Cost: 15,000
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=20000.0  # After trade: 5,000 < min 10,000
    )
    
    cash_violations = [v for v in violations if v.constraint_type == 'min_cash_balance']
    assert len(cash_violations) == 1
    assert cash_violations[0].current_value == 5000.0
    assert cash_violations[0].limit_value == 10000.0


# Test 13: Cash balance constraint - zero min_cash_balance
def test_cash_balance_zero_minimum(sample_prices, industry_map):
    """Test that zero min_cash_balance allows any positive cash."""
    config = ConstraintConfig(
        max_notional_per_asset=100000.0,
        max_leverage=2.0,
        max_industry_concentration=0.4,
        max_asset_concentration=0.3,
        as_of=datetime(2026, 1, 1),
        available_at=datetime(2026, 1, 1),
        min_cash_balance=0.0
    )
    solver = ConstraintSolver(config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 100},  # Cost: 15,000
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=15001.0  # Just above cost
    )
    
    cash_violations = [v for v in violations if v.constraint_type == 'min_cash_balance']
    assert len(cash_violations) == 0


# Test 14: MVO optimization - basic functionality
def test_optimize_portfolio_mvo_basic(base_config, sample_returns, sample_prices, industry_map):
    """Test basic MVO portfolio optimization."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        current_cash=100000.0
    )
    
    assert isinstance(result, pd.DataFrame)
    assert 'asset' in result.columns
    assert 'quantity' in result.columns
    assert len(result) > 0


# Test 15: MVO optimization - respects long-only constraint
def test_optimize_portfolio_mvo_long_only(base_config, sample_returns, sample_prices, industry_map):
    """Test that MVO optimization respects long-only constraint."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        current_cash=100000.0
    )
    
    # All quantities should be non-negative (if result is not empty)
    if len(result) > 0:
        assert (result['quantity'] >= 0).all()


# Test 16: MVO optimization - with target return
def test_optimize_portfolio_mvo_target_return(base_config, sample_returns, sample_prices, industry_map):
    """Test MVO optimization with target return constraint."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        target_return=0.001,
        current_cash=100000.0
    )
    
    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0


# Test 17: MVO optimization - respects board lot constraint
def test_optimize_portfolio_mvo_board_lot(base_config, sample_returns, sample_prices, industry_map):
    """Test that MVO optimization respects board lot constraint."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        current_cash=100000.0
    )
    
    # All quantities should be multiples of board_lot_size or zero
    for _, row in result.iterrows():
        qty = abs(row['quantity'])
        if qty > 1e-9:
            assert qty % base_config.board_lot_size < 1e-9


# Test 18: Risk Parity optimization - basic functionality
def test_optimize_portfolio_risk_parity_basic(base_config, sample_returns, sample_prices, industry_map):
    """Test basic Risk Parity portfolio optimization."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='risk_parity',
        current_cash=100000.0
    )
    
    assert isinstance(result, pd.DataFrame)
    assert 'asset' in result.columns
    assert 'quantity' in result.columns
    assert len(result) > 0


# Test 19: Risk Parity optimization - respects long-only
def test_optimize_portfolio_risk_parity_long_only(base_config, sample_returns, sample_prices, industry_map):
    """Test that Risk Parity optimization respects long-only constraint."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='risk_parity',
        current_cash=100000.0
    )
    
    # All quantities should be non-negative
    assert (result['quantity'] >= 0).all()


# Test 20: Risk Parity optimization - respects board lot
def test_optimize_portfolio_risk_parity_board_lot(base_config, sample_returns, sample_prices, industry_map):
    """Test that Risk Parity optimization respects board lot constraint."""
    solver = ConstraintSolver(base_config)
    
    result = solver.optimize_portfolio(
        returns=sample_returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='risk_parity',
        current_cash=100000.0
    )
    
    # All quantities should be multiples of board_lot_size or zero
    for _, row in result.iterrows():
        qty = abs(row['quantity'])
        if qty > 1e-9:
            assert qty % base_config.board_lot_size < 1e-9


# Test 21: Optimize with small universe (2 assets)
def test_optimize_portfolio_small_universe(base_config, industry_map):
    """Test optimization with only 2 assets."""
    returns = pd.DataFrame([
        {'asset': 'AAPL', 'as_of': datetime(2026, 1, 1), 'return': 0.01},
        {'asset': 'GOOGL', 'as_of': datetime(2026, 1, 1), 'return': 0.02},
    ])
    prices = pd.DataFrame([
        {'asset': 'AAPL', 'as_of': datetime(2026, 1, 1), 'price': 150.0},
        {'asset': 'GOOGL', 'as_of': datetime(2026, 1, 1), 'price': 2800.0},
    ])
    
    solver = ConstraintSolver(base_config)
    result = solver.optimize_portfolio(
        returns=returns,
        prices=prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        current_cash=100000.0
    )
    
    assert len(result) <= 2


# Test 22: Optimize with empty returns raises error
def test_optimize_portfolio_empty_returns(base_config, sample_prices, industry_map):
    """Test that empty returns raises ValueError."""
    returns = pd.DataFrame(columns=['asset', 'as_of', 'return'])
    
    solver = ConstraintSolver(base_config)
    with pytest.raises(ValueError, match="No assets available"):
        solver.optimize_portfolio(
            returns=returns,
            prices=sample_prices,
            industry_map=industry_map,
            as_of=datetime(2026, 1, 1),
            method='mvo',
            current_cash=100000.0
        )


# Test 23: Optimize handles NaN returns
def test_optimize_portfolio_nan_returns(base_config, sample_prices, industry_map):
    """Test that NaN returns are handled gracefully."""
    returns = pd.DataFrame([
        {'asset': 'AAPL', 'as_of': datetime(2026, 1, 1), 'return': 0.01},
        {'asset': 'GOOGL', 'as_of': datetime(2026, 1, 1), 'return': np.nan},
        {'asset': 'MSFT', 'as_of': datetime(2026, 1, 1), 'return': 0.02},
    ])
    
    solver = ConstraintSolver(base_config)
    result = solver.optimize_portfolio(
        returns=returns,
        prices=sample_prices,
        industry_map=industry_map,
        as_of=datetime(2026, 1, 1),
        method='mvo',
        current_cash=100000.0
    )
    
    # Should complete without error
    assert isinstance(result, pd.DataFrame)


# Test 24: PIT safety check in optimize_portfolio
def test_optimize_portfolio_pit_safety(base_config, sample_returns, sample_prices, industry_map):
    """Test that optimize_portfolio enforces PIT safety."""
    solver = ConstraintSolver(base_config)
    
    # Try to optimize at a date before config is available
    with pytest.raises(ValueError, match="not available at"):
        solver.optimize_portfolio(
            returns=sample_returns,
            prices=sample_prices,
            industry_map=industry_map,
            as_of=datetime(2025, 12, 31),  # Before config.available_at
            method='mvo',
            current_cash=100000.0
        )


# Test 25: Combined constraints (long-only + board-lot + cash)
def test_combined_constraints(base_config, sample_prices, industry_map):
    """Test multiple constraints simultaneously."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 150},  # Violates board lot
        {'asset': 'GOOGL', 'quantity': 50},  # Long position
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=5000.0  # After buying: 5000 - (150*150 + 50*2800) = 5000 - 162500 < 0, violates min cash
    )
    
    assert not is_valid
    assert len(violations) >= 2
    
    violation_types = {v.constraint_type for v in violations}
    assert 'board_lot' in violation_types
    assert 'min_cash_balance' in violation_types


# Test 26: Flat portfolio (zero positions) is valid
def test_flat_portfolio_valid(base_config, sample_prices, industry_map):
    """Test that flat portfolio with zero positions is valid."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0},
        {'asset': 'GOOGL', 'quantity': 0},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=50000.0  # Sufficient cash to meet min_cash_balance
    )
    
    assert is_valid
    assert len(violations) == 0


# Test 27: Leverage calculation with flat portfolio
def test_leverage_flat_portfolio(base_config, sample_prices, industry_map):
    """Test that flat portfolio doesn't violate leverage constraint."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0},
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    leverage_violations = [v for v in violations if v.constraint_type == 'max_leverage']
    assert len(leverage_violations) == 0


# Test 28: Notional limit violations
def test_notional_limit_violations(base_config, sample_prices, industry_map):
    """Test notional limit constraint violations."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 1000},  # Notional: 150,000 > 100,000 limit
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    notional_violations = [v for v in violations if v.constraint_type == 'max_notional_per_asset']
    assert len(notional_violations) == 1
    assert notional_violations[0].asset == 'AAPL'


# Test 29: Asset concentration violations
def test_asset_concentration_violations(base_config, sample_prices, industry_map):
    """Test asset concentration constraint violations."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 500},  # 75,000 notional
        {'asset': 'GOOGL', 'quantity': 10},  # 28,000 notional
    ])
    # AAPL concentration: 75,000 / 103,000 = 0.728 > 0.3 limit
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    concentration_violations = [v for v in violations if v.constraint_type == 'max_asset_concentration']
    assert len(concentration_violations) == 1


# Test 30: Industry concentration violations
def test_industry_concentration_violations(base_config, sample_prices, industry_map):
    """Test industry concentration constraint violations."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 300},   # Tech: 45,000
        {'asset': 'GOOGL', 'quantity': 20},   # Tech: 56,000
        {'asset': 'MSFT', 'quantity': 100},   # Tech: 38,000
        {'asset': 'TSLA', 'quantity': 100},   # Auto: 25,000
    ])
    # Tech concentration: 139,000 / 164,000 = 0.848 > 0.4 limit
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    industry_violations = [v for v in violations if v.constraint_type == 'max_industry_concentration']
    assert len(industry_violations) == 1
    assert industry_violations[0].asset == 'Technology'


# Test 31: adjust_trades with constraint violations
def test_adjust_trades_with_violations(base_config, sample_prices, industry_map):
    """Test that adjust_trades scales down violating trades."""
    solver = ConstraintSolver(base_config)
    
    current_positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0},
    ])
    
    trades = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 1000},  # Would violate notional limit
    ])
    
    adjusted = solver.adjust_trades(
        trades, current_positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    # Adjusted quantity should be less than original
    assert adjusted.loc[adjusted['asset'] == 'AAPL', 'quantity'].values[0] < 1000


# Test 32: adjust_trades binary search convergence
def test_adjust_trades_convergence(base_config, sample_prices, industry_map):
    """Test that adjust_trades converges to valid solution."""
    solver = ConstraintSolver(base_config)
    
    current_positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0},
    ])
    
    trades = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 2000},  # Large violation
    ])
    
    adjusted = solver.adjust_trades(
        trades, current_positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    # Verify adjusted trades satisfy constraints
    target_positions = current_positions.copy()
    target_positions['quantity'] = adjusted.set_index('asset')['quantity'].reindex(
        current_positions['asset']
    ).fillna(0).values
    
    is_valid, _ = solver.validate_constraints(
        adjusted, sample_prices, industry_map, datetime(2026, 1, 1),
        current_cash=500000.0  # Sufficient cash for validation
    )
    
    assert is_valid


# Test 33: get_violations method
def test_get_violations_method(base_config, sample_prices, industry_map):
    """Test get_violations convenience method."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': -100},  # Violates long-only
    ])
    
    violations = solver.get_violations(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    assert isinstance(violations, list)
    assert len(violations) > 0
    assert all(isinstance(v, ConstraintViolation) for v in violations)


# Test 34: Multiple simultaneous constraint violations
def test_multiple_simultaneous_violations(base_config, sample_prices, industry_map):
    """Test handling of multiple simultaneous violations."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': -1500},  # Violates: long-only, board-lot, notional
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    assert not is_valid
    assert len(violations) >= 2


# Test 35: Edge case - very small quantities
def test_edge_case_small_quantities(base_config, sample_prices, industry_map):
    """Test handling of very small quantities."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 0.0001},  # Very small
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    # Should handle without numerical errors
    assert isinstance(is_valid, bool)


# Test 36: Edge case - very large quantities
def test_edge_case_large_quantities(base_config, sample_prices, industry_map):
    """Test handling of very large quantities."""
    solver = ConstraintSolver(base_config)
    positions = pd.DataFrame([
        {'asset': 'AAPL', 'quantity': 1000000},  # Very large
    ])
    
    is_valid, violations = solver.validate_constraints(
        positions, sample_prices, industry_map, datetime(2026, 1, 1)
    )
    
    # Should detect violations
    assert not is_valid
    assert len(violations) > 0


# Test 37: Optimize with unknown method raises error
def test_optimize_unknown_method(base_config, sample_returns, sample_prices, industry_map):
    """Test that unknown optimization method raises ValueError."""
    solver = ConstraintSolver(base_config)
    
    with pytest.raises(ValueError, match="Unknown optimization method"):
        solver.optimize_portfolio(
            returns=sample_returns,
            prices=sample_prices,
            industry_map=industry_map,
            as_of=datetime(2026, 1, 1),
            method='unknown_method',
            current_cash=100000.0
        )
