"""
Advanced Risk Management Unit Tests - Phase 5 Gap Filling
Tests AdvancedCircuitBreaker, ContagionRiskValidator, and IndividualRiskGuard.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from omega.quant.risk.advanced_circuit_breaker import (
    AdvancedCircuitBreaker,
    AdvancedCircuitBreakerConfig,
    RiskBreachStatus
)
from omega.quant.risk.contagion_risk_validator import (
    ContagionRiskValidator,
    ContagionRiskConfig,
    GlobalIndexData,
    MarketStressLevel
)
from omega.quant.risk.individual_risk_guard import (
    IndividualRiskGuard,
    IndividualRiskGuardConfig,
    IndividualRiskGuardResult
)


@pytest.fixture
def sample_returns():
    """Generate sample normal portfolio returns."""
    np.random.seed(42)
    return np.random.normal(0.0005, 0.01, 252)  # 1 year daily returns


@pytest.fixture
def sample_returns_df():
    """Generate sample returns DataFrame for multiple stocks."""
    np.random.seed(42)
    dates = pd.date_range('2026-01-01', periods=100)
    data = {
        'FPT': np.random.normal(0.001, 0.015, 100),
        'HPG': np.random.normal(0.0005, 0.02, 100),
        'SSI': np.random.normal(0.0015, 0.025, 100),
        'VNM': np.random.normal(0.0002, 0.01, 100)
    }
    return pd.DataFrame(data, index=dates)


class TestAdvancedCircuitBreaker:
    """Test Suite for Advanced Circuit Breaker."""
    
    def test_var_breach_calculation(self, sample_returns):
        config = AdvancedCircuitBreakerConfig(var_limit=0.015)
        breaker = AdvancedCircuitBreaker(config)
        
        status = breaker.check_var_breach(sample_returns)
        assert isinstance(status, RiskBreachStatus)
        assert status.var_value > 0
        # Normal distribution 95% Var should be ~1.64 * std
        expected_var = abs(np.percentile(sample_returns, 5))
        assert pytest.approx(status.var_value, 1e-5) == expected_var
    
    def test_cvar_breach_and_auto_derisk(self, sample_returns):
        config = AdvancedCircuitBreakerConfig(cvar_limit=0.01, auto_derisk_enabled=True)
        breaker = AdvancedCircuitBreaker(config)
        
        status = breaker.check_cvar_breach(sample_returns)
        assert status.cvar_value > 0
        assert status.is_breached == (status.cvar_value > 0.01)
        
        # Test de-risking multiplier
        initial_weights = {"FPT": 0.4, "HPG": 0.6}
        adjusted_weights = breaker.auto_derisk(initial_weights, status.cvar_value)
        
        if status.is_breached:
            assert adjusted_weights["FPT"] == 0.4 * 0.6
            assert adjusted_weights["HPG"] == 0.6 * 0.6
        else:
            assert adjusted_weights == initial_weights

    def test_beta_calculation(self, sample_returns):
        np.random.seed(42)
        market_returns = np.random.normal(0.0004, 0.008, 252)
        
        breaker = AdvancedCircuitBreaker()
        status = breaker.check_beta_breach(sample_returns, market_returns)
        
        assert isinstance(status, RiskBreachStatus)
        assert status.beta_value is not None
        
        # Verify direct covariance / variance formula
        expected_beta = np.cov(sample_returns, market_returns)[0, 1] / np.var(market_returns)
        assert pytest.approx(status.beta_value, abs=1e-3) == expected_beta

    def test_pairwise_correlation_check(self, sample_returns_df):
        config = AdvancedCircuitBreakerConfig(correlation_hard_stop=0.10)
        breaker = AdvancedCircuitBreaker(config)
        
        status = breaker.check_correlation_breach(sample_returns_df)
        assert isinstance(status, RiskBreachStatus)
        assert status.correlation_value is not None
        
        # HPG vs SSI is likely over 0.10
        assert status.is_breached == (status.correlation_value > 0.10)

    def test_adv_participation_cap(self):
        breaker = AdvancedCircuitBreaker(AdvancedCircuitBreakerConfig(adv_participation_cap=0.40))
        
        # Exceeds cap: 500M / 1B = 50% (> 40%)
        status = breaker.check_adv_participation(500_000_000, 1_000_000_000)
        assert status.is_breached
        assert status.action == 'block_new_positions'
        
        # Under cap: 200M / 1B = 20% (< 40%)
        status_ok = breaker.check_adv_participation(200_000_000, 1_000_000_000)
        assert not status_ok.is_breached
        assert status_ok.action == 'allow'


class TestContagionRiskValidator:
    """Test Suite for Contagion Risk Validator."""
    
    def test_sri_calculation_and_stress_classification(self):
        config = ContagionRiskConfig(enabled=True)
        validator = ContagionRiskValidator(config)
        
        np.random.seed(42)
        vn_returns = np.random.normal(0.0005, 0.01, 60)
        
        global_indices = [
            GlobalIndexData(
                ticker="S&P500",
                log_returns=np.random.normal(0.0003, 0.008, 60),
                timestamp=datetime.now(timezone.utc)
            ),
            GlobalIndexData(
                ticker="NIKKEI",
                log_returns=np.random.normal(0.0002, 0.012, 60),
                timestamp=datetime.now(timezone.utc)
            )
        ]
        
        sri = validator.calculate_sri(vn_returns, global_indices)
        assert 0.0 <= sri <= 1.0
        
        stress_level = validator.classify_stress_level(sri)
        assert isinstance(stress_level, MarketStressLevel)
        assert stress_level.level in ['GREEN', 'YELLOW', 'RED']
        
        multiplier = validator.get_risk_multiplier(stress_level)
        assert multiplier in [1.0, 0.7, 0.3]


class TestIndividualRiskGuard:
    """Test Suite for Individual Risk Guard Bridge."""
    
    def test_portfolio_validation_approved_and_rejected_flows(self, sample_returns_df):
        config = IndividualRiskGuardConfig(
            initial_capital=2_000_000_000,  # 2B
            max_concentration_per_stock=0.25,  # 25%
            max_adv_percentage=0.40,
            min_stocks=2,
            max_stocks=4
        )
        guard = IndividualRiskGuard(config)
        
        signals = {"FPT": 0.15, "HPG": 0.12, "SSI": 0.08, "VNM": 0.05}
        adv_20 = {"FPT": 1_000_000_000, "HPG": 800_000_000, "SSI": 500_000_000, "VNM": 2_000_000_000}
        
        result = guard.validate_portfolio(signals, adv_20, sample_returns_df)
        assert isinstance(result, IndividualRiskGuardResult)
        
        # approved stocks should be equal-weighted if they fit limits
        assert len(result.approved_stocks) > 0
        for stock in result.approved_weights:
            assert result.approved_weights[stock] <= 0.25
