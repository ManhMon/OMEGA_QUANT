"""
Tests for Risk Management - OMEGA_QUANT Phase 5 Migration

Tests Individual Risk Guard, Circuit Breakers, and Contagion Validator.
"""

import pytest
import pandas as pd
import numpy as np

from omega.risk.individual_risk_guard import IndividualRiskGuard, RiskGuardConfig
from omega.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from omega.risk.contagion_validator import ContagionRiskValidator, ContagionConfig

@pytest.fixture
def mock_weights():
    return pd.Series({
        'AAPL': 0.30,  # Above 25% concentration limit
        'GOOGL': 0.20,
        'MSFT': 0.50,  # Above 25% concentration limit
    })

@pytest.fixture
def mock_adv():
    return pd.Series({
        'AAPL': 1_000_000_000.0,  # ADV 1B
        'GOOGL': 2_000_000_000.0, # ADV 2B
        'MSFT': 500_000_000.0,    # ADV 500M
    })

@pytest.fixture
def mock_prices():
    return pd.Series([100, 95, 90, 85, 80], index=pd.date_range("2024-01-01", periods=5))

class TestIndividualRiskGuard:
    def test_concentration_limit(self, mock_weights, mock_adv):
        guard = IndividualRiskGuard(RiskGuardConfig(max_concentration_per_stock=0.25))
        # Total portfolio 1B
        approved = guard.validate_weights(mock_weights, mock_adv, portfolio_value=1_000_000_000.0)
        
        # Should be clipped to 0.25
        assert approved['AAPL'] <= 0.25
        assert approved['MSFT'] <= 0.25
        assert approved['GOOGL'] <= 0.25
        
    def test_adv_limit(self, mock_weights, mock_adv):
        # 40% ADV limit
        guard = IndividualRiskGuard(RiskGuardConfig(max_adv_percentage=0.40))
        
        # Portfolio value 10B
        # MSFT weight = 0.50 -> Needs 5B allocation
        # MSFT ADV = 500M -> 40% ADV = 200M limit
        # Max weight for MSFT = 200M / 10B = 0.02
        approved = guard.validate_weights(mock_weights, mock_adv, portfolio_value=10_000_000_000.0)
        
        assert approved['MSFT'] <= 0.02

    def test_drawdown_check(self):
        guard = IndividualRiskGuard(RiskGuardConfig(alert_drawdown_threshold=0.10))
        equity = pd.Series([100, 110, 105, 95, 90])  # Drop from 110 to 90 is > 10%
        assert guard.check_drawdown(equity) is True
        
        equity_safe = pd.Series([100, 105, 102])
        assert guard.check_drawdown(equity_safe) is False

class TestCircuitBreaker:
    def test_market_circuit_breaker(self, mock_prices):
        cb = CircuitBreaker(CircuitBreakerConfig(single_day_drop_limit=0.04))
        # mock_prices drops from 100->95 (-5%) which > 4% limit
        halt, reason = cb.check_market_circuit_breaker(mock_prices)
        assert halt is True
        assert "Single-day drop" in reason

    def test_asset_circuit_breaker(self):
        cb = CircuitBreaker(CircuitBreakerConfig(single_day_drop_limit=0.07))
        prices = pd.Series([100, 92])  # -8% drop
        halt, reason = cb.check_asset_circuit_breaker(prices, "AAPL")
        assert halt is True
        assert "AAPL dropped" in reason

class TestContagionValidator:
    def test_correlation_spike(self):
        cv = ContagionRiskValidator(ContagionConfig(correlation_threshold=0.8))
        
        # Highly correlated returns
        returns = pd.DataFrame({
            'A': [0.01, -0.01, 0.02, -0.02],
            'B': [0.01, -0.01, 0.02, -0.02],  # Perfect correlation with A
            'C': [0.01, 0.01, 0.01, 0.01]
        })
        
        spikes = cv.check_correlation_spikes(returns)
        assert 'A/B' in spikes
        assert spikes['A/B'] > 0.8
        
    def test_beta_jump(self):
        cv = ContagionRiskValidator(ContagionConfig(lookback_window=3, beta_jump_threshold=0.5))
        
        # Market returns
        mkt = pd.Series([0.01, -0.01, 0.02, -0.02, 0.01, 0.03])
        # Asset returns (beta jump at the end)
        asset = pd.Series([0.01, -0.01, 0.02, -0.02, 0.05, 0.15])
        
        jump, current_beta, prev_beta = cv.check_beta_jumps(asset, mkt)
        
        assert isinstance(jump, bool)
