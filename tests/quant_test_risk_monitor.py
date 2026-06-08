"""
Unit Tests for OMEGA_QUANT Risk Monitor
Phase 4.4: Circuit Breakers & Pre-Trade Compliance

Author: Backend Engineer (Role 09)
Date: 2026-05-13
"""

import pytest
from omega.risk.risk_monitor import (
    RiskConfig,
    CircuitBreaker,
    RiskMonitor,
    PreTradeCheckResult,
)


@pytest.fixture
def risk_config():
    return RiskConfig(
        daily_loss_limit=0.02,
        symbol_concentration_limit=0.25,
        gross_exposure_limit=1.0,
        max_position_limit=0.10,
        volatility_threshold=0.05,
        board_lot=100,
    )


@pytest.fixture
def circuit_breaker(risk_config):
    return CircuitBreaker(risk_config)


def test_circuit_breaker_daily_loss_limit(circuit_breaker):
    """Test daily loss circuit breaker."""
    circuit_breaker.reset_daily(start_equity=1_000_000_000.0)
    
    # Within limit
    circuit_breaker.update_daily_pnl(990_000_000.0)  # -1% loss
    ok, reason = circuit_breaker.check_daily_loss_limit()
    assert ok is True
    assert reason is None
    
    # Exceeds limit
    circuit_breaker.update_daily_pnl(970_000_000.0)  # -3% loss
    ok, reason = circuit_breaker.check_daily_loss_limit()
    assert ok is False
    assert reason is not None
    assert "Daily loss" in reason


def test_circuit_breaker_symbol_concentration(circuit_breaker):
    """Test symbol concentration guard."""
    portfolio_equity = 1_000_000_000.0
    
    # Within limit (20% < 25%)
    ok, reason = circuit_breaker.check_symbol_concentration(
        symbol="FPT",
        new_position=2000,  # 2000 shares * 100,000 = 200M (20%)
        current_price=100000.0,
        portfolio_equity=portfolio_equity
    )
    assert ok is True
    assert reason is None
    
    # Exceeds limit (30% > 25%)
    ok, reason = circuit_breaker.check_symbol_concentration(
        symbol="VNM",
        new_position=3000,  # 3000 shares * 100,000 = 300M (30%)
        current_price=100000.0,
        portfolio_equity=portfolio_equity
    )
    assert ok is False
    assert reason is not None
    assert "weight" in reason.lower()


def test_circuit_breaker_volatility_guard(circuit_breaker):
    """Test volatility (ATR) guard."""
    # Within limit (3% < 5%)
    ok, reason = circuit_breaker.check_volatility_guard(
        symbol="FPT",
        atr=3000.0,
        current_price=100000.0
    )
    assert ok is True
    assert reason is None
    
    # Exceeds limit (7% > 5%)
    ok, reason = circuit_breaker.check_volatility_guard(
        symbol="VNM",
        atr=7000.0,
        current_price=100000.0
    )
    assert ok is False
    assert reason is not None
    assert "ATR" in reason or "volatility" in reason.lower()


def test_circuit_breaker_board_lot(circuit_breaker):
    """Test board-lot compliance (VN market: 100 shares)."""
    # Valid (multiple of 100)
    ok, reason = circuit_breaker.check_board_lot(100)
    assert ok is True
    assert reason is None
    
    ok, reason = circuit_breaker.check_board_lot(500)
    assert ok is True
    
    # Invalid (not multiple of 100)
    ok, reason = circuit_breaker.check_board_lot(50)
    assert ok is False
    assert reason is not None
    assert "board-lot" in reason.lower()


def test_circuit_breaker_pre_trade_check(circuit_breaker):
    """Test comprehensive pre-trade compliance check."""
    circuit_breaker.reset_daily(start_equity=1_000_000_000.0)
    
    # Valid order
    result = circuit_breaker.pre_trade_check(
        symbol="FPT",
        side="BUY",
        quantity=100,
        price=100000.0,
        current_position=0,
        portfolio_equity=1_000_000_000.0,
        atr=3000.0,
        cash=1_000_000_000.0
    )
    assert result.approved is True
    assert len(result.violations) == 0
    assert result.notional == 10_000_000.0  # 100 * 100,000


def test_circuit_breaker_pre_trade_violations(circuit_breaker):
    """Test pre-trade check with violations."""
    circuit_breaker.reset_daily(start_equity=1_000_000_000.0)
    
    # Insufficient cash
    result = circuit_breaker.pre_trade_check(
        symbol="FPT",
        side="BUY",
        quantity=10000,  # 10000 * 100,000 = 1B
        price=100000.0,
        current_position=0,
        portfolio_equity=1_000_000_000.0,
        cash=500_000_000.0  # Only 500M available
    )
    assert result.approved is False
    assert any("insufficient_cash" in v for v in result.violations)

    # Gross exposure limit (Risk Budget)
    result = circuit_breaker.pre_trade_check(
        symbol="VNM",
        side="BUY",
        quantity=2000,
        price=100000.0,
        current_position=0,
        portfolio_equity=1_000_000_000.0,
        existing_gross_exposure=0.9,  # Already at 90%
        cash=1_000_000_000.0
    )
    # 200M / 1B = 20% -> 90% + 20% = 110% (exceeds 100% limit)
    assert result.approved is False
    assert any("gross_exposure_limit" in v for v in result.violations)

    # De-risk SELL should be approved even if at limit
    result = circuit_breaker.pre_trade_check(
        symbol="VNM",
        side="SELL",
        quantity=2000,
        price=100000.0,
        current_position=2000,
        portfolio_equity=1_000_000_000.0,
        existing_gross_exposure=1.0,  # At 100% limit
        cash=0.0
    )
    # Reducing 200M position -> Gross 100% -> 80%. Should PASS.
    assert result.approved is True
    assert result.post_gross_exposure == 0.8

    # Invalid side
    result = circuit_breaker.pre_trade_check(
        symbol="FPT",
        side="INVALID",
        quantity=100,
        price=100000.0,
        current_position=0,
        portfolio_equity=1_000_000_000.0
    )
    assert result.approved is False
    assert any("invalid_side" in v for v in result.violations)


def test_risk_monitor_var_cvar(risk_config):
    """Test VaR and CVaR calculations."""
    monitor = RiskMonitor(risk_config)
    
    # Test with known returns
    returns = [-0.05, -0.03, -0.02, 0.01, 0.02, 0.03, 0.04]
    var_95 = monitor.calculate_var_95(returns)
    cvar_95 = monitor.calculate_cvar_95(returns)
    
    assert var_95 > 0
    assert cvar_95 > 0
    assert cvar_95 >= var_95  # CVaR >= VaR


def test_risk_monitor_max_drawdown(risk_config):
    """Test max drawdown calculation."""
    monitor = RiskMonitor(risk_config)
    
    # Equity curve with clear drawdown
    equity_curve = [100, 110, 120, 115, 100, 90, 95]
    mdd = monitor.calculate_max_drawdown(equity_curve)
    
    # Expected: peak at 120, lowest after peak is 90
    # Drawdown = (120 - 90) / 120 = 25%
    assert abs(mdd) > 0.20  # Approximately 25%
    assert abs(mdd) < 0.30


def test_risk_monitor_risk_metrics(risk_config):
    """Test comprehensive risk metrics."""
    monitor = RiskMonitor(risk_config)
    
    # Add some data
    monitor.equity_curve = [100, 110, 120, 115, 100]
    monitor.returns = [0.1, 0.09, -0.04, -0.13]
    
    metrics = monitor.get_risk_metrics()
    
    assert "var_95" in metrics
    assert "cvar_95" in metrics
    assert "max_drawdown" in metrics
    assert "daily_pnl" in metrics
    assert "circuit_broken" in metrics

