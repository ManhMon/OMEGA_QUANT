"""
Tests for Phase 19 Transaction Cost Optimizer - Gap Fix v1.2.0

Covers:
- [GAP-1] Market impact model: alpha * (participation^beta) * volatility * turnover
- [GAP-2] Vietnam market constraints: limit-lock (2.0x), foreign room (1.5x)
- [GAP-3] T+2.5 settlement cash flow adjustment
- PIT Safety: T-1 lag enforcement (preserved)
- [Phase 19.1] 5 dedicated market impact model tests

15 tests total - all must PASS for L3 audit readiness.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from omega.quant.transaction_cost_optimizer import (
    TransactionCostOptimizer,
    TransactionCostResult,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def optimizer():
    return TransactionCostOptimizer(
        fixed_commission=10_000.0,
        pct_commission=0.0015,
        volatility_scaling=0.1,
        price_scale=1000.0,
        impact_alpha=0.05,
        impact_beta=1.5,
    )


@pytest.fixture
def base_timestamps():
    """Returns (as_of, available_at, timestamp) satisfying T-1 PIT."""
    timestamp = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)       # T-1
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc) # before timestamp
    return as_of, available_at, timestamp


@pytest.fixture
def base_market_data():
    return {
        "VNM": {
            "price": 80.0,        # 80 * 1000 = 80,000 VND
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 500_000,       # shares/day
        }
    }


# ---------------------------------------------------------------------------
# Test 1: Market impact is computed and positive
# ---------------------------------------------------------------------------

def test_market_impact_positive(optimizer, base_timestamps, base_market_data):
    """[GAP-1] market_impact must be > 0 for non-zero trade."""
    as_of, available_at, timestamp = base_timestamps
    results = optimizer.calculate_cost(
        positions={"VNM": 1000},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["VNM"].market_impact > 0.0


# ---------------------------------------------------------------------------
# Test 2: Market impact formula correctness
# ---------------------------------------------------------------------------

def test_market_impact_formula(optimizer, base_timestamps, base_market_data):
    """[GAP-1] impact = alpha * (participation^beta) * volatility * turnover."""
    as_of, available_at, timestamp = base_timestamps
    data = base_market_data["VNM"]
    shares = 1000
    price_vnd = data["price"] * 1000.0
    turnover = shares * price_vnd
    adv_vnd = data["adv"] * 1000.0
    participation = turnover / adv_vnd
    expected_impact = 0.05 * (participation ** 1.5) * data["volatility"] * turnover

    results = optimizer.calculate_cost(
        positions={"VNM": shares},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert abs(results["VNM"].market_impact - expected_impact) < 1e-6


# ---------------------------------------------------------------------------
# Test 3: Market impact included in total_cost
# ---------------------------------------------------------------------------

def test_market_impact_in_total_cost(optimizer, base_timestamps, base_market_data):
    """[GAP-1] total_cost must include market_impact."""
    as_of, available_at, timestamp = base_timestamps
    results = optimizer.calculate_cost(
        positions={"VNM": 1000},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    r = results["VNM"]
    # total = commission + (slippage + liquidity + market_impact) * multiplier
    expected_variable = (r.slippage + r.liquidity_cost + r.market_impact) * r.cost_multiplier
    assert abs(r.total_cost - (r.commission + expected_variable)) < 1e-6


# ---------------------------------------------------------------------------
# Test 4: Limit-lock detection sets cost_multiplier = 2.0
# ---------------------------------------------------------------------------

def test_limit_lock_upper(optimizer, base_timestamps):
    """[GAP-2] price >= upper_limit -> cost_multiplier = 2.0."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "HPG": {
            "price": 30.0,
            "upper_limit": 30.0,   # price == upper_limit -> locked
            "lower_limit": 24.0,
            "spread": 0.001,
            "volatility": 0.025,
            "adv": 1_000_000,
        }
    }
    results = optimizer.calculate_cost(
        positions={"HPG": 500},
        market_data=market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["HPG"].cost_multiplier == 2.0


def test_limit_lock_lower(optimizer, base_timestamps):
    """[GAP-2] price <= lower_limit -> cost_multiplier = 2.0."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "HPG": {
            "price": 24.0,
            "upper_limit": 30.0,
            "lower_limit": 24.0,   # price == lower_limit -> locked
            "spread": 0.001,
            "volatility": 0.025,
            "adv": 1_000_000,
        }
    }
    results = optimizer.calculate_cost(
        positions={"HPG": 500},
        market_data=market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["HPG"].cost_multiplier == 2.0


# ---------------------------------------------------------------------------
# Test 5: Foreign room breach sets cost_multiplier = 1.5
# ---------------------------------------------------------------------------

def test_foreign_room_breach(optimizer, base_timestamps):
    """[GAP-2] foreign_ownership >= 0.49 -> cost_multiplier = 1.5."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "VIC": {
            "price": 50.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 800_000,
            "foreign_ownership": 0.49,  # at threshold
        }
    }
    results = optimizer.calculate_cost(
        positions={"VIC": 200},
        market_data=market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["VIC"].cost_multiplier == 1.5


# ---------------------------------------------------------------------------
# Test 6: Limit-lock takes precedence over foreign room (2.0 > 1.5)
# ---------------------------------------------------------------------------

def test_limit_lock_overrides_foreign_room(optimizer, base_timestamps):
    """[GAP-2] limit-lock (2.0) must win over foreign room (1.5)."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "MSN": {
            "price": 100.0,
            "upper_limit": 100.0,  # locked
            "lower_limit": 80.0,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 600_000,
            "foreign_ownership": 0.50,  # also breached
        }
    }
    results = optimizer.calculate_cost(
        positions={"MSN": 300},
        market_data=market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["MSN"].cost_multiplier == 2.0


# ---------------------------------------------------------------------------
# Test 7: No Vietnam constraint -> cost_multiplier = 1.0
# ---------------------------------------------------------------------------

def test_no_vietnam_constraint(optimizer, base_timestamps, base_market_data):
    """[GAP-2] No limit/foreign fields -> cost_multiplier = 1.0."""
    as_of, available_at, timestamp = base_timestamps
    results = optimizer.calculate_cost(
        positions={"VNM": 1000},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    assert results["VNM"].cost_multiplier == 1.0


# ---------------------------------------------------------------------------
# Test 8: T+2.5 settlement cash_flow adjustment
# ---------------------------------------------------------------------------

def test_t25_settlement_cash_flow(optimizer, base_timestamps, base_market_data):
    """[GAP-3] cash_flow = total_cost * (1 + 0.0005 * 2.5)."""
    as_of, available_at, timestamp = base_timestamps
    results = optimizer.calculate_cost(
        positions={"VNM": 1000},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    r = results["VNM"]
    expected_cash_flow = r.total_cost * (1.0 + 0.0005 * 2.5)
    assert abs(r.cash_flow - expected_cash_flow) < 1e-6


# ---------------------------------------------------------------------------
# Test 9: PIT Safety - T-1 lag violation raises ValueError
# ---------------------------------------------------------------------------

def test_pit_same_day_raises(optimizer, base_market_data):
    """PIT: as_of same day as timestamp must raise ValueError."""
    timestamp = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    as_of = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)   # same day!
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="PIT violation"):
        optimizer.calculate_cost(
            positions={"VNM": 1000},
            market_data=base_market_data,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )


# ---------------------------------------------------------------------------
# Test 10: Zero position returns zero-cost result
# ---------------------------------------------------------------------------

def test_zero_position_returns_zero_cost(optimizer, base_timestamps, base_market_data):
    """Zero shares -> TransactionCostResult with all zeros."""
    as_of, available_at, timestamp = base_timestamps
    results = optimizer.calculate_cost(
        positions={"VNM": 0},
        market_data=base_market_data,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )
    r = results["VNM"]
    assert r.total_cost == 0.0
    assert r.commission == 0.0
    assert r.market_impact == 0.0
    assert r.cash_flow == 0.0


# ---------------------------------------------------------------------------
# Phase 19.1 - 5 Dedicated Market Impact Model Tests
# Formula: impact = 0.05 * (participation_rate ^ 1.5) * volatility * turnover
# T-1 lag enforced on all inputs via PIT Safety checks
# ---------------------------------------------------------------------------

def test_impact_scales_with_participation(optimizer, base_timestamps):
    """[Phase 19.1-1] Larger trade -> higher participation -> higher impact (superlinear)."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "VNM": {"price": 80.0, "spread": 0.001, "volatility": 0.02, "adv": 500_000}
    }
    r_small = optimizer.calculate_cost(
        positions={"VNM": 500},
        market_data=market_data,
        as_of=as_of, available_at=available_at, timestamp=timestamp,
    )["VNM"]
    r_large = optimizer.calculate_cost(
        positions={"VNM": 5000},
        market_data=market_data,
        as_of=as_of, available_at=available_at, timestamp=timestamp,
    )["VNM"]
    # participation doubles by 10x shares, impact grows superlinearly (beta=1.5)
    assert r_large.market_impact > r_small.market_impact * 10


def test_impact_scales_with_volatility(optimizer, base_timestamps):
    """[Phase 19.1-2] Higher volatility -> proportionally higher impact."""
    as_of, available_at, timestamp = base_timestamps
    shares = 1000
    adv = 500_000
    price = 80.0

    def _calc(vol):
        return optimizer.calculate_cost(
            positions={"VNM": shares},
            market_data={"VNM": {"price": price, "spread": 0.001, "volatility": vol, "adv": adv}},
            as_of=as_of, available_at=available_at, timestamp=timestamp,
        )["VNM"].market_impact

    impact_low = _calc(0.01)
    impact_high = _calc(0.02)
    # impact is linear in volatility -> doubling vol doubles impact
    assert abs(impact_high / impact_low - 2.0) < 1e-6


def test_impact_zero_when_adv_infinite(optimizer, base_timestamps):
    """[Phase 19.1-3] Negligible participation (tiny trade vs huge ADV) -> near-zero impact."""
    as_of, available_at, timestamp = base_timestamps
    market_data = {
        "VNM": {"price": 80.0, "spread": 0.001, "volatility": 0.02, "adv": 1_000_000_000}
    }
    r = optimizer.calculate_cost(
        positions={"VNM": 1},
        market_data=market_data,
        as_of=as_of, available_at=available_at, timestamp=timestamp,
    )["VNM"]
    assert r.market_impact < 1.0  # effectively zero at institutional scale


def test_impact_custom_alpha_beta(base_timestamps):
    """[Phase 19.1-4] Custom alpha/beta params are respected in formula."""
    as_of, available_at, timestamp = base_timestamps
    opt = TransactionCostOptimizer(
        impact_alpha=0.10,   # 2x default alpha
        impact_beta=2.0,     # steeper than default 1.5
    )
    shares = 1000
    price_vnd = 80.0 * 1000.0
    turnover = shares * price_vnd
    adv_vnd = 500_000 * 1000.0
    participation = turnover / adv_vnd
    expected = 0.10 * (participation ** 2.0) * 0.02 * turnover

    r = opt.calculate_cost(
        positions={"VNM": shares},
        market_data={"VNM": {"price": 80.0, "spread": 0.001, "volatility": 0.02, "adv": 500_000}},
        as_of=as_of, available_at=available_at, timestamp=timestamp,
    )["VNM"]
    assert abs(r.market_impact - expected) < 1e-6


def test_impact_pit_t1_lag_enforced(optimizer, base_market_data):
    """[Phase 19.1-5] T-1 lag enforced on market impact inputs: future as_of raises ValueError."""
    timestamp = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    as_of_future = datetime(2026, 5, 19, 8, 0, 0, tzinfo=timezone.utc)  # same day -> PIT violation
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="PIT violation"):
        optimizer.calculate_cost(
            positions={"VNM": 1000},
            market_data=base_market_data,
            as_of=as_of_future,
            available_at=available_at,
            timestamp=timestamp,
        )
