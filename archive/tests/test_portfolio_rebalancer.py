"""
Tests for PIT-Safe Rebalancer - Phase 3.2

Tests cover:
1. PIT safety enforcement (T-1 lag validation)
2. Drift-based rebalancing triggers
3. Schedule-based rebalancing triggers
4. Board-lot rounding in trades
5. Liquidity constraint enforcement
6. Turnover limit enforcement
"""

import pytest
from datetime import datetime, timedelta
from src.portfolio.rebalancer import (
    PITRebalancer,
    RebalanceConfig,
    RebalanceDecision,
)
from src.portfolio.constraints import PortfolioConstraints


@pytest.fixture
def sample_config():
    """Sample rebalance configuration."""
    return RebalanceConfig(
        drift_threshold=0.05,
        schedule="weekly",
        schedule_day=4,  # Friday
        max_turnover=0.25,
        min_trade_value=100_000.0,
        transaction_cost_bps=15.0,
        constraints=PortfolioConstraints(
            max_position=0.25,
            max_sector=0.40,
            max_adv_participation=0.40,
            board_lot=100,
        ),
    )


def test_pit_safety_timestamp_required():
    """Test PIT safety: timestamp parameter is required."""
    rebalancer = PITRebalancer()
    
    target_portfolio = {"VNM": 0.50, "VIC": 0.50}
    current_positions = {}
    market_data = {}
    portfolio_value = 100_000_000.0
    data_time = datetime(2024, 1, 14, 16, 0, 0)
    
    # Should raise ValueError when timestamp is None
    with pytest.raises(ValueError, match="timestamp is REQUIRED"):
        rebalancer.rebalance(
            target_portfolio=target_portfolio,
            current_positions=current_positions,
            market_data=market_data,
            portfolio_value=portfolio_value,
            timestamp=None,  # PIT violation
            data_timestamp=data_time,
        )


def test_pit_safety_data_timestamp_validation():
    """Test PIT safety: data_timestamp must be T-1 or earlier."""
    rebalancer = PITRebalancer()
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 15, 8, 0, 0)  # Same day (look-ahead bias)
    
    target_portfolio = {"VNM": 0.50, "VIC": 0.50}
    current_positions = {}
    market_data = {}
    portfolio_value = 100_000_000.0
    
    # Should raise ValueError for look-ahead bias
    with pytest.raises(ValueError, match="PIT Safety violation"):
        rebalancer.rebalance(
            target_portfolio=target_portfolio,
            current_positions=current_positions,
            market_data=market_data,
            portfolio_value=portfolio_value,
            timestamp=current_time,
            data_timestamp=data_time,  # Same day = look-ahead
        )


def test_pit_safety_valid_t1_lag():
    """Test PIT safety: T-1 data is accepted."""
    rebalancer = PITRebalancer()
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # Previous day (T-1)
    
    target_portfolio = {"VNM": 0.50, "VIC": 0.50}
    current_positions = {}
    market_data = {
        "VNM": {"price": 100.0, "adv": 50_000_000.0},
        "VIC": {"price": 50.0, "adv": 100_000_000.0},
    }
    portfolio_value = 100_000_000.0
    
    # Should NOT raise error (T-1 is valid)
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    assert isinstance(result, RebalanceDecision)
    assert result.data_timestamp == data_time


def test_drift_based_rebalancing(sample_config):
    """Test drift-based rebalancing trigger."""
    rebalancer = PITRebalancer(sample_config)
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    
    # Current portfolio
    current_positions = {
        "VNM": {"qty": 1000, "price": 100.0, "weight": 0.50},
        "VIC": {"qty": 2000, "price": 50.0, "weight": 0.50},
    }
    
    # Target portfolio (significant drift)
    target_portfolio = {
        "VNM": 0.30,  # -20% drift
        "VIC": 0.70,  # +20% drift
    }
    
    market_data = {
        "VNM": {"price": 100.0, "adv": 50_000_000.0},
        "VIC": {"price": 50.0, "adv": 100_000_000.0},
    }
    
    portfolio_value = 200_000_000.0
    
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    # Should trigger rebalance due to drift
    assert result.should_rebalance
    assert "drift" in result.reason.lower() or "initial" in result.reason.lower()


def test_schedule_based_rebalancing(sample_config):
    """Test schedule-based rebalancing trigger."""
    config = RebalanceConfig(
        drift_threshold=0.50,  # High threshold (won't trigger)
        schedule="daily",
        max_turnover=0.25,
    )
    rebalancer = PITRebalancer(config)
    
    # First rebalance
    day1 = datetime(2024, 1, 15, 9, 0, 0)
    data_day1 = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    result1 = rebalancer.rebalance(
        target_portfolio={"VNM": 0.50, "VIC": 0.50},
        current_positions={"VNM": {"qty": 1000, "price": 100.0, "weight": 0.50}},
        market_data={"VNM": {"price": 100.0, "adv": 50_000_000.0}},
        portfolio_value=100_000_000.0,
        timestamp=day1,
        data_timestamp=data_day1,
    )
    
    # Should rebalance on first day
    assert result1.should_rebalance
    
    # Next day (schedule trigger)
    day2 = datetime(2024, 1, 16, 9, 0, 0)
    data_day2 = datetime(2024, 1, 15, 16, 0, 0)  # T-1
    result2 = rebalancer.rebalance(
        target_portfolio={"VNM": 0.50, "VIC": 0.50},
        current_positions={"VNM": {"qty": 1000, "price": 100.0, "weight": 0.50}},
        market_data={"VNM": {"price": 100.0, "adv": 50_000_000.0}},
        portfolio_value=100_000_000.0,
        timestamp=day2,
        data_timestamp=data_day2,
    )
    
    # Should trigger due to daily schedule
    assert result2.should_rebalance
    assert "schedule" in result2.reason.lower()


def test_board_lot_rounding_in_trades(sample_config):
    """Test board-lot rounding is applied to trades."""
    rebalancer = PITRebalancer(sample_config)
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    
    # Target requires 1,234 shares (not multiple of 100)
    target_portfolio = {"VNM": 1.0}
    current_positions = {}
    market_data = {"VNM": {"price": 100.0, "adv": 500_000_000.0}}
    portfolio_value = 123_400_000.0  # Would give 1,234 shares
    
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    # Check shares are rounded to board lot
    if result.should_rebalance and "VNM" in result.target_changes:
        shares_delta = result.target_changes["VNM"]["shares_delta"]
        assert shares_delta % 100 == 0  # Must be multiple of 100


def test_liquidity_constraint_enforcement(sample_config):
    """Test liquidity constraint (ADV participation) enforcement."""
    rebalancer = PITRebalancer(sample_config)
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    
    # Large position relative to ADV
    target_portfolio = {"VNM": 1.0}
    current_positions = {}
    market_data = {
        "VNM": {"price": 100.0, "adv": 10_000_000.0}  # Low ADV
    }
    portfolio_value = 100_000_000.0  # 100M position / 10M ADV = 1000% participation
    
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    # Should have liquidity violations
    assert len(result.liquidity_violations) > 0
    
    # Trades should be scaled down
    if "VNM" in result.target_changes:
        shares_delta = result.target_changes["VNM"]["shares_delta"]
        # Should be much less than 1000 shares (100M / 100K price)
        assert shares_delta < 1000


def test_turnover_limit_enforcement(sample_config):
    """Test turnover limit enforcement."""
    config = RebalanceConfig(
        drift_threshold=0.01,
        max_turnover=0.10,  # Low turnover limit (10%)
    )
    rebalancer = PITRebalancer(config)
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    
    # Large rebalance (would exceed turnover)
    current_positions = {
        "VNM": {"qty": 1000, "price": 100.0, "weight": 1.0},
    }
    target_portfolio = {
        "VNM": 0.20,  # -80% drift
        "VIC": 0.80,  # +80% drift
    }
    market_data = {
        "VNM": {"price": 100.0, "adv": 500_000_000.0},
        "VIC": {"price": 50.0, "adv": 500_000_000.0},
    }
    portfolio_value = 100_000_000.0
    
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    # Turnover should be capped at 10%
    assert result.estimated_turnover <= 0.10 + 1e-6


def test_no_rebalance_when_no_trigger():
    """Test no rebalance when no drift or schedule trigger."""
    config = RebalanceConfig(
        drift_threshold=0.10,  # High threshold
        schedule="none",  # No schedule
    )
    rebalancer = PITRebalancer(config)
    
    # Set last rebalance time
    rebalancer.last_rebalance_time = datetime(2024, 1, 14, 9, 0, 0)
    
    current_time = datetime(2024, 1, 15, 9, 0, 0)
    data_time = datetime(2024, 1, 14, 16, 0, 0)  # T-1
    
    # Small drift (below threshold)
    current_positions = {
        "VNM": {"qty": 1000, "price": 100.0, "weight": 0.50},
    }
    target_portfolio = {"VNM": 0.52}  # Only 2% drift
    market_data = {"VNM": {"price": 100.0, "adv": 50_000_000.0}}
    portfolio_value = 100_000_000.0
    
    result = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=portfolio_value,
        timestamp=current_time,
        data_timestamp=data_time,
    )
    
    # Should NOT rebalance
    assert not result.should_rebalance
    assert "no drift" in result.reason.lower()
