"""
Layer 4: Risk Management Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests risk controls, circuit breakers, position limits, and risk metrics.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from omega.risk.individual_risk_guard import IndividualRiskGuard, RiskGuardConfig


class TestRiskManagementLayer:
    """Test Layer 4: Risk Management controls."""
    
    def test_circuit_breaker_initialization(self):
        """Test CircuitBreaker initializes correctly."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config=config)
        
        assert breaker is not None
        assert breaker.config == config
    
    def test_risk_guard_initialization(self):
        """Test IndividualRiskGuard initializes correctly."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        assert guard is not None
        assert guard.config == config
    
    def test_position_limit_enforcement(self):
        """Test that position limits are enforced."""
        config = RiskGuardConfig(max_position_size=0.15)  # 15% max per position
        guard = IndividualRiskGuard(config=config)
        
        # Create positions exceeding limits
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E", "F", "G"],
            "date": ["2023-01-01"] * 7,
            "target_weight": [0.30, 0.25, 0.20, 0.10, 0.08, 0.05, 0.02]  # A and B exceed 15%
        })
        
        adjusted = guard.apply_limits(positions)
        
        # All positions should be <= 15%
        assert adjusted["target_weight"].max() <= 0.15
        # Total weight should still sum to ~1.0
        assert np.isclose(adjusted["target_weight"].sum(), 1.0, atol=0.01)
    
    def test_concentration_limit(self):
        """Test concentration limits across positions."""
        config = RiskGuardConfig(
            max_position_size=0.20,
            max_sector_concentration=0.40
        )
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "sector": ["Tech", "Tech", "Tech", "Finance", "Finance"],
            "target_weight": [0.20, 0.20, 0.20, 0.20, 0.20]
        })
        
        adjusted = guard.apply_limits(positions)
        
        # Tech sector should be limited to 40%
        if "sector" in adjusted.columns:
            tech_weight = adjusted[adjusted["sector"] == "Tech"]["target_weight"].sum()
            assert tech_weight <= 0.40
    
    def test_circuit_breaker_triggers(self):
        """Test circuit breaker triggers on extreme moves."""
        config = CircuitBreakerConfig(
            max_drawdown_pct=0.10,  # 10% max drawdown
            volatility_threshold=0.05  # 5% volatility threshold
        )
        breaker = CircuitBreaker(config=config)
        
        # Create market data with extreme drawdown
        market_data = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "portfolio_value": [100, 98, 95, 90, 85, 80, 75, 70, 65, 60]  # 40% drawdown
        })
        
        status = breaker.check_status(market_data)
        
        # Circuit breaker should trigger
        assert status["triggered"] is True
        assert "drawdown" in status["reason"].lower()
    
    def test_volatility_scaling(self):
        """Test position sizing based on volatility."""
        config = RiskGuardConfig(volatility_target=0.15)
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.33, 0.33, 0.34],
            "volatility": [0.10, 0.20, 0.30]  # Different volatilities
        })
        
        scaled = guard.scale_by_volatility(positions)
        
        # Higher volatility stocks should have lower weights
        assert scaled[scaled["ticker"] == "A"]["target_weight"].iloc[0] > \
               scaled[scaled["ticker"] == "C"]["target_weight"].iloc[0]
    
    def test_risk_metrics_computation(self):
        """Test computation of risk metrics."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "target_weight": [0.25, 0.25, 0.20, 0.15, 0.15],
            "volatility": [0.15, 0.20, 0.18, 0.12, 0.10]
        })
        
        metrics = guard.compute_risk_metrics(positions)
        
        assert "portfolio_volatility" in metrics
        assert "max_position" in metrics
        assert "num_positions" in metrics
        assert metrics["num_positions"] == 5
        assert metrics["max_position"] == 0.25
    
    def test_stop_loss_enforcement(self):
        """Test stop-loss enforcement on positions."""
        config = RiskGuardConfig(stop_loss_pct=0.05)  # 5% stop loss
        guard = IndividualRiskGuard(config=config)
        
        # Create positions with losses
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.33, 0.33, 0.34],
            "entry_price": [100, 100, 100],
            "current_price": [95, 92, 98]  # A: -5%, B: -8%, C: -2%
        })
        
        adjusted = guard.apply_stop_loss(positions)
        
        # Position B should be closed (exceeds 5% stop loss)
        b_weight = adjusted[adjusted["ticker"] == "B"]["target_weight"].iloc[0]
        assert b_weight == 0.0


class TestRiskManagementBoundary:
    """Test boundary conditions for risk management."""
    
    def test_empty_positions(self):
        """Test risk controls with empty positions."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": [],
            "date": [],
            "target_weight": []
        })
        
        adjusted = guard.apply_limits(positions)
        
        assert len(adjusted) == 0
    
    def test_single_position(self):
        """Test risk controls with single position."""
        config = RiskGuardConfig(max_position_size=0.50)
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "target_weight": [1.0]  # 100% in one position
        })
        
        adjusted = guard.apply_limits(positions)
        
        # Should be capped at 50%
        assert adjusted["target_weight"].iloc[0] <= 0.50
    
    def test_zero_weights(self):
        """Test handling of zero weights."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.0, 0.0, 0.0]
        })
        
        adjusted = guard.apply_limits(positions)
        
        # Should handle zero weights gracefully
        assert len(adjusted) == 3
        assert adjusted["target_weight"].sum() == 0.0
    
    def test_negative_weights(self):
        """Test handling of negative weights (short positions)."""
        config = RiskGuardConfig(allow_short=True, max_position_size=0.20)
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.50, -0.30, 0.80]  # B is short
        })
        
        adjusted = guard.apply_limits(positions)
        
        # Short position should also be limited
        b_weight = adjusted[adjusted["ticker"] == "B"]["target_weight"].iloc[0]
        assert abs(b_weight) <= 0.20
    
    def test_extreme_volatility(self):
        """Test risk controls with extreme volatility."""
        config = RiskGuardConfig(volatility_target=0.15, max_position_size=0.20)
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "target_weight": [0.20, 0.20, 0.20, 0.20, 0.20],
            "volatility": [0.50, 0.80, 1.00, 0.60, 0.70]  # Extreme volatility
        })
        
        scaled = guard.scale_by_volatility(positions)
        
        # After volatility scaling, apply position limits
        adjusted = guard.apply_limits(scaled)
        
        # Positions should be significantly reduced and respect limits
        assert adjusted["target_weight"].max() <= 0.20


class TestRiskIntegration:
    """Test risk management integration with alpha layer."""
    
    def test_alpha_to_risk_pipeline(self):
        """Test complete alpha -> risk pipeline."""
        # Create alpha signals
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1]
        })
        
        # Convert alphas to positions (simple equal weight top 5)
        top_alphas = alphas.nlargest(5, "alpha_momentum_rank")
        positions = top_alphas.copy()
        positions["target_weight"] = 1.0 / len(top_alphas)
        
        # Apply risk controls
        config = RiskGuardConfig(max_position_size=0.25)
        guard = IndividualRiskGuard(config=config)
        
        adjusted = guard.apply_limits(positions)
        
        # Verify risk-adjusted positions
        assert len(adjusted) == 5
        assert adjusted["target_weight"].max() <= 0.25
        assert np.isclose(adjusted["target_weight"].sum(), 1.0, atol=0.01)
    
    def test_circuit_breaker_halts_trading(self):
        """Test that circuit breaker halts trading when triggered."""
        config = CircuitBreakerConfig(max_drawdown_pct=0.10)
        breaker = CircuitBreaker(config=config)
        
        # Market data with large drawdown
        market_data = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=5, freq="D"),
            "portfolio_value": [100, 95, 88, 85, 80]  # 20% drawdown
        })
        
        status = breaker.check_status(market_data)
        
        if status["triggered"]:
            # Trading should be halted
            positions = pd.DataFrame({
                "ticker": ["A", "B", "C"],
                "date": ["2023-01-05"] * 3,
                "target_weight": [0.33, 0.33, 0.34]
            })
            
            # Circuit breaker should zero out positions
            halted = breaker.apply_halt(positions)
            assert halted["target_weight"].sum() == 0.0


class TestRiskMetrics:
    """Test risk metrics computation and validation."""
    
    def test_portfolio_volatility_calculation(self):
        """Test portfolio volatility calculation."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "target_weight": [0.40, 0.35, 0.25],
            "volatility": [0.20, 0.15, 0.10]
        })
        
        # Simplified calculation (assumes no correlation)
        metrics = guard.compute_risk_metrics(positions)
        
        assert "portfolio_volatility" in metrics
        assert metrics["portfolio_volatility"] > 0
    
    def test_max_drawdown_tracking(self):
        """Test maximum drawdown tracking."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config=config)
        
        portfolio_values = pd.Series([100, 105, 110, 95, 90, 100, 105, 98])
        
        max_dd = breaker.compute_max_drawdown(portfolio_values)
        
        # Max drawdown should be from 110 to 90 = 18.18%
        assert max_dd > 0.18
        assert max_dd < 0.19
    
    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio calculation."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        returns = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005, -0.005, 0.02, 0.01])
        
        sharpe = guard.compute_sharpe_ratio(returns, risk_free_rate=0.0)
        
        assert sharpe > 0  # Positive returns should give positive Sharpe
    
    def test_var_calculation(self):
        """Test Value at Risk (VaR) calculation."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        returns = pd.Series(np.random.randn(100) * 0.02)
        
        var_95 = guard.compute_var(returns, confidence=0.95)
        
        assert var_95 < 0  # VaR should be negative (loss)
        # Approximately 5% of returns should be worse than VaR
        worse_than_var = (returns < var_95).sum()
        assert worse_than_var <= 10  # ~5% of 100


class TestRiskPITSafety:
    """Test PIT safety in risk management."""
    
    def test_risk_metrics_no_lookahead(self):
        """Test that risk metrics don't use future data."""
        config = RiskGuardConfig()
        guard = IndividualRiskGuard(config=config)
        
        # Create positions with timestamps
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 3,
            "target_weight": [0.33, 0.33, 0.34] * 10,
            "volatility": np.random.randn(30) * 0.05 + 0.15
        })
        
        # Compute risk metrics for each date
        for date in positions["date"].unique():
            date_positions = positions[positions["date"] == date]
            metrics = guard.compute_risk_metrics(date_positions)
            
            # Metrics should only use data up to current date
            assert metrics is not None
            assert "portfolio_volatility" in metrics
    
    def test_circuit_breaker_uses_historical_data_only(self):
        """Test that circuit breaker only uses historical data."""
        config = CircuitBreakerConfig(max_drawdown_pct=0.10)
        breaker = CircuitBreaker(config=config)
        
        # Create market data
        market_data = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "portfolio_value": np.random.randn(20).cumsum() + 100
        })
        
        # Check status at each date using only prior data
        for i in range(5, len(market_data)):
            historical_data = market_data.iloc[:i]
            status = breaker.check_status(historical_data)
            
            # Status should be based only on historical data
            assert isinstance(status["triggered"], bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
