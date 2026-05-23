"""
Unit Tests for OMEGA_QUANT Phase 18 Portfolio Rebalancing Engine
Tests cover drift-based/schedule-based triggers, board-lot constraints,
liquidity limits, turnover scaling, and PIT safety.

Author: Backend Engineer (Role 09)
Date: 2026-05-19
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta, UTC
from omega.quant.rebalancer import Rebalancer, RebalanceConfig, RebalanceDecision
from omega.quant.constraint_solver import ConstraintSolver, ConstraintConfig


@pytest.fixture
def base_config():
    """Default institutional configuration."""
    return RebalanceConfig(
        drift_threshold=0.05,
        schedule="weekly",
        schedule_day=4,  # Friday
        max_turnover=0.25,
        min_trade_value=100_000.0,
        board_lot=100,
        max_adv_participation=0.10,
        transaction_cost_bps=15.0
    )


def test_rebalancer_initialization(base_config):
    """Test rebalancer initialization with custom config."""
    rebalancer = Rebalancer(base_config)
    assert rebalancer.config.drift_threshold == 0.05
    assert rebalancer.config.max_adv_participation == 0.10
    assert rebalancer.last_rebalance_time is None


def test_rebalancer_pit_safety_missing_metadata(base_config):
    """Test rebalancer catches missing PIT safety metadata."""
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.50}
    positions = {"VNM": {"qty": 1000, "weight": 1.0}}
    
    # Missing as_of/available_at
    market_data = {
        "VNM": {"price": 100.0, "adv": 10_000_000.0}
    }
    
    with pytest.raises(ValueError, match="as_of and available_at required"):
        rebalancer.rebalance(target, positions, market_data, 100_000_000.0, timestamp)


def test_rebalancer_pit_safety_same_day_violation(base_config):
    """Test rebalancer rejects same-day market data (look-ahead bias)."""
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.50}
    positions = {"VNM": {"qty": 1000, "weight": 1.0}}
    
    # Same day as_of violates T-1 lag
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 10_000_000.0,
            "as_of": datetime(2024, 1, 15, 8, 0, 0),
            "available_at": datetime(2024, 1, 15, 8, 30, 0)
        }
    }
    
    with pytest.raises(ValueError, match="PIT violation \\(T-1\\)"):
        rebalancer.rebalance(target, positions, market_data, 100_000_000.0, timestamp)


def test_rebalancer_pit_safety_availability_violation(base_config):
    """Test rebalancer rejects future available_at timestamp."""
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.50}
    positions = {"VNM": {"qty": 1000, "weight": 1.0}}
    
    # available_at in the future relative to execution timestamp
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 10_000_000.0,
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 15, 10, 0, 0)  # Future
        }
    }
    
    with pytest.raises(ValueError, match="PIT violation \\(Availability\\)"):
        rebalancer.rebalance(target, positions, market_data, 100_000_000.0, timestamp)


def test_rebalancer_board_lot_rounding(base_config):
    """Test that generated trades are rounded to 100 board-lot multiples."""
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.60}  # Increase weight
    positions = {"VNM": {"qty": 1000, "weight": 0.40}}
    
    # 100M portfolio value. VNM target is 60M. Current qty is 1000 (100k price * 1000 * 1000 = 100M? Wait, price=100.0)
    # Price scale: price is in '1000 VND'. So 100.0 means 100,000 VND per share.
    # Current value = 1000 * 100.0 * 1000 = 100,000,000 VND. Wait, that would be 100% of portfolio.
    # Let's adjust portfolio_value to 250,000,000 VND.
    # Current value VNM = 1000 * 100,000 = 100,000,000 VND (weight = 0.40).
    # Target value VNM = 0.60 * 250,000,000 = 150,000,000 VND (shares = 150,000,000 / 100,000 = 1500 shares).
    # Shares delta = +500 shares.
    portfolio_value = 250_000_000.0
    
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 500_000_000.0,  # 5k shares ADV
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        }
    }
    
    # Let's test a non-multiple of 100 target.
    # Target weight = 0.61 -> target value = 152,500,000 -> target shares = 1525.
    # Delta raw = +525 shares. Rounded to board lot (100) -> +500 shares delta.
    target = {"VNM": 0.61}
    
    result = rebalancer.rebalance(target, positions, market_data, portfolio_value, timestamp)
    
    assert result.should_rebalance is True
    assert "VNM" in result.target_changes
    assert result.target_changes["VNM"]["shares_delta"] == 500
    assert result.target_changes["VNM"]["target_qty"] == 1500


def test_rebalancer_adv_liquidity_scaling(base_config):
    """Test trade is scaled down to meet 10% ADV participation cap."""
    base_config.max_turnover = 1.0  # Prevent turnover scaling from interfering
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.80}
    positions = {"VNM": {"qty": 0, "weight": 0.0}}
    
    # Portfolio value = 2,000,000,000 VND. Target value = 1,600,000,000 VND.
    # Target shares = 16,000 shares.
    # ADV is 50,000,000 VND (500 shares). 10% ADV cap is 50 shares.
    # Raw delta is 16,000 shares. Scaled delta must be 50 shares (rounded to board lot).
    # Since 50 is not a multiple of 100, wait! Let's check _round_to_board_lot logic.
    # It does: `int(shares / board_lot) * board_lot`. So int(50 / 100) * 100 = 0!
    # Let's increase ADV so 10% is > 100.
    # Let's set ADV = 1,500,000,000 VND (15,000 shares). 10% ADV is 1,500 shares (15 lots).
    # Delta should be capped at 1,500 shares instead of 16,000.
    portfolio_value = 2_000_000_000.0
    
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 1_500_000_000.0,  # 15,000 shares ADV
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        }
    }
    
    result = rebalancer.rebalance(target, positions, market_data, portfolio_value, timestamp)
    
    assert result.should_rebalance is True
    assert "VNM" in result.target_changes
    assert result.target_changes["VNM"]["shares_delta"] == 1500
    assert "VNM" in result.liquidity_violations


def test_rebalancer_turnover_proportional_scaling(base_config):
    """Test trades scaled down proportionally when total turnover exceeds max_turnover."""
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    # We want to change weights by a lot to exceed max_turnover (0.25)
    # Target: 50% shift. VNM 0% -> 50%, VIC 100% -> 50%.
    # Total drift = |0.50 - 0.0| + |0.50 - 1.0| = 1.00 (100% turnover).
    # Turnover cap is 25%. So all trades must scale by 25% / 100% = 0.25.
    target = {"VNM": 0.50, "VIC": 0.50}
    positions = {
        "VNM": {"qty": 0, "weight": 0.0},
        "VIC": {"qty": 1000, "weight": 1.0}
    }
    
    portfolio_value = 100_000_000.0  # VNM=100.0 (100k), VIC=100.0 (100k)
    # 1000 shares of VIC * 100k = 100,000,000 VND (100%).
    # Target VNM = 50M (500 shares). Target VIC = 50M (500 shares).
    # Scaled VNM delta = +500 * 0.25 = +125 shares -> round to 100 -> +100.
    # Scaled VIC delta = -500 * 0.25 = -125 shares -> round to -100.
    
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 500_000_000.0,
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        },
        "VIC": {
            "price": 100.0,
            "adv": 500_000_000.0,
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        }
    }
    
    result = rebalancer.rebalance(target, positions, market_data, portfolio_value, timestamp)
    
    assert result.should_rebalance is True
    assert result.target_changes["VNM"]["shares_delta"] == 100
    assert result.target_changes["VIC"]["shares_delta"] == -100
    assert result.estimated_turnover <= 0.25


def test_rebalancer_constraint_solver_integration(base_config):
    """Test that Rebalancer integrates with ConstraintSolver and flags violations."""
    base_config.max_turnover = 1.0  # Prevent turnover scaling from interfering
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    # Target portfolio has high concentration in VNM (80%)
    target = {"VNM": 0.80, "VIC": 0.20}
    positions = {
        "VNM": {"qty": 0, "weight": 0.0},
        "VIC": {"qty": 0, "weight": 0.0}
    }
    
    portfolio_value = 1_000_000_000.0  # 1B VND
    
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 10_000_000_000.0,  # 10B ADV -> 100,000 shares -> 10% cap is 10,000 shares (covers 8,000 target)
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        },
        "VIC": {
            "price": 100.0,
            "adv": 10_000_000_000.0,
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        }
    }
    
    # Configure ConstraintSolver to allow max 50% asset concentration (VNM target 80% will violate this)
    config = ConstraintConfig(
        max_notional_per_asset=900_000_000.0,  # 900M
        max_leverage=2.0,
        max_industry_concentration=0.90,
        max_asset_concentration=0.50,          # 50% limit
        as_of=timestamp - timedelta(days=1),
        available_at=timestamp - timedelta(hours=12)
    )
    solver = ConstraintSolver(config)
    
    industry_map = {"VNM": "Consumer", "VIC": "Conglomerate"}
    
    # Mock prices dataframe
    prices_df = pd.DataFrame([
        {"asset": "VNM", "price": 100.0, "as_of": datetime(2024, 1, 14, 16, 0, 0)},
        {"asset": "VIC", "price": 100.0, "as_of": datetime(2024, 1, 14, 16, 0, 0)}
    ])
    
    result = rebalancer.rebalance(
        target_portfolio=target,
        current_positions=positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
        constraint_solver=solver,
        industry_map=industry_map,
        prices_df=prices_df
    )
    
    assert result.should_rebalance is True
    # Violations should be flagged in liquidity_violations
    assert any("max_asset_concentration" in k for k in result.liquidity_violations.keys())
    assert any("VNM" in v for v in result.liquidity_violations.values())


def test_rebalancer_constraint_solver_cash_integration(base_config):
    """Test that Rebalancer correctly propagates current_cash to ConstraintSolver and avoids double count."""
    base_config.max_turnover = 1.0
    rebalancer = Rebalancer(base_config)
    
    timestamp = datetime(2024, 1, 15, 9, 0, 0)
    target = {"VNM": 0.60}  # target is 60% of 1B (600M)
    
    # We already hold 5,000 shares of VNM (worth 500M at 100.0 price, since scale is 1000)
    # Target holding is 600M. We need to buy 1,000 shares (100M).
    # Portfolio equity is 1B. Remaining cash after target position (600M) is 400M.
    # Minimum cash required is 100M. Remaining cash (400M) > 100M, so this must PASS.
    # If solver double-counts current positions and subtracts 600M target from 500M starting cash (pre-trade cash),
    # projected cash would be 500M - 600M = -100M, triggering a false-positive violation.
    positions = {"VNM": {"qty": 5000, "weight": 0.50}}
    portfolio_value = 1_000_000_000.0
    
    market_data = {
        "VNM": {
            "price": 100.0,
            "adv": 10_000_000_000.0,
            "as_of": datetime(2024, 1, 14, 16, 0, 0),
            "available_at": datetime(2024, 1, 14, 17, 0, 0)
        }
    }
    
    config = ConstraintConfig(
        max_notional_per_asset=1_000_000_000.0,
        max_leverage=10.0,
        max_industry_concentration=1.0,
        max_asset_concentration=1.0,
        as_of=timestamp - timedelta(days=1),
        available_at=timestamp - timedelta(hours=12),
        min_cash_balance=100_000_000.0,
        board_lot_size=100
    )
    solver = ConstraintSolver(config)
    industry_map = {"VNM": "Consumer"}
    # Note: prices_df has price in 1000 VND unit to test automatic VND scale normalization in rebalancer
    prices_df = pd.DataFrame([
        {"asset": "VNM", "price": 100.0, "as_of": datetime(2024, 1, 14, 16, 0, 0)}
    ])
    
    result = rebalancer.rebalance(
        target_portfolio=target,
        current_positions=positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=timestamp,
        constraint_solver=solver,
        industry_map=industry_map,
        prices_df=prices_df
    )
    
    # Should PASS with no min_cash_balance violation (400M remaining cash > 100M limit)
    assert result.should_rebalance is True
    assert "RISK_min_cash_balance" not in result.liquidity_violations



