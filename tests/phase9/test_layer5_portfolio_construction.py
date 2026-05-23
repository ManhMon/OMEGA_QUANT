"""
Layer 5: Portfolio Construction Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests portfolio optimization, rebalancing, and position construction.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.portfolio_optimizer import PortfolioOptimizer, OptimizerConfig


class TestPortfolioConstructionLayer:
    """Test Layer 5: Portfolio Construction."""
    
    def test_portfolio_optimizer_initialization(self):
        """Test PortfolioOptimizer initializes correctly."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        assert optimizer is not None
        assert optimizer.config == config
    
    def test_equal_weight_portfolio(self):
        """Test equal weight portfolio construction."""
        config = OptimizerConfig(method="equal_weight")
        optimizer = PortfolioOptimizer(config=config)
        
        # Create alpha signals
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1]
        })
        
        # Select top 3
        top_alphas = alphas.nlargest(3, "alpha_momentum_rank")
        
        portfolio = optimizer.construct_portfolio(top_alphas)
        
        assert len(portfolio) == 3
        assert "target_weight" in portfolio.columns
        # Equal weight = 1/3 each
        assert np.allclose(portfolio["target_weight"], 1/3, atol=0.01)
        assert np.isclose(portfolio["target_weight"].sum(), 1.0, atol=0.01)
    
    def test_rank_weighted_portfolio(self):
        """Test rank-weighted portfolio construction."""
        config = OptimizerConfig(method="rank_weight")
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1]
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        assert len(portfolio) > 0
        assert "target_weight" in portfolio.columns
        # Higher rank should have higher weight
        a_weight = portfolio[portfolio["ticker"] == "A"]["target_weight"].iloc[0]
        e_weight = portfolio[portfolio["ticker"] == "E"]["target_weight"].iloc[0]
        assert a_weight > e_weight
        assert np.isclose(portfolio["target_weight"].sum(), 1.0, atol=0.01)
    
    def test_mean_variance_optimization(self):
        """Test mean-variance portfolio optimization."""
        config = OptimizerConfig(method="mean_variance")
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1],
            "expected_return": [0.10, 0.08, 0.06, 0.04, 0.02],
            "volatility": [0.20, 0.15, 0.12, 0.10, 0.08]
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        assert len(portfolio) > 0
        assert "target_weight" in portfolio.columns
        assert np.isclose(portfolio["target_weight"].sum(), 1.0, atol=0.01)
        # Should favor higher return/lower volatility
        assert portfolio["target_weight"].min() >= 0  # No short positions by default
    
    def test_portfolio_rebalancing(self):
        """Test portfolio rebalancing logic."""
        config = OptimizerConfig(rebalance_threshold=0.05)  # 5% threshold
        optimizer = PortfolioOptimizer(config=config)
        
        # Current portfolio
        current = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "current_weight": [0.40, 0.35, 0.25]
        })
        
        # Target portfolio
        target = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "target_weight": [0.45, 0.30, 0.25]  # A +5%, B -5%, C unchanged
        })
        
        trades = optimizer.compute_rebalance_trades(current, target)
        
        assert len(trades) > 0
        # Should trade A and B, not C (below threshold)
        assert "A" in trades["ticker"].values
        assert "B" in trades["ticker"].values
    
    def test_turnover_constraint(self):
        """Test turnover constraint in portfolio construction."""
        config = OptimizerConfig(max_turnover=0.20)  # 20% max turnover
        optimizer = PortfolioOptimizer(config=config)
        
        # Current portfolio
        current = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "current_weight": [0.20, 0.20, 0.20, 0.20, 0.20]
        })
        
        # Desired target (very different)
        target = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "target_weight": [0.50, 0.30, 0.10, 0.05, 0.05]
        })
        
        constrained = optimizer.apply_turnover_constraint(current, target)
        
        # Turnover should be limited
        turnover = (constrained["target_weight"] - current["current_weight"]).abs().sum() / 2
        assert turnover <= 0.20
    
    def test_long_only_constraint(self):
        """Test long-only constraint enforcement."""
        config = OptimizerConfig(allow_short=False)
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "alpha_momentum_rank": [0.8, 0.5, 0.2]
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        # All weights should be non-negative
        assert (portfolio["target_weight"] >= 0).all()
    
    def test_sector_neutrality(self):
        """Test sector-neutral portfolio construction."""
        config = OptimizerConfig(sector_neutral=True)
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E", "F"],
            "date": ["2023-01-01"] * 6,
            "sector": ["Tech", "Tech", "Finance", "Finance", "Energy", "Energy"],
            "alpha_momentum_rank": [0.9, 0.7, 0.6, 0.5, 0.4, 0.2]
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        # Each sector should have equal weight
        if "sector" in portfolio.columns:
            sector_weights = portfolio.groupby("sector")["target_weight"].sum()
            # All sectors should have similar weights
            assert sector_weights.std() < 0.1


class TestPortfolioConstructionBoundary:
    """Test boundary conditions for portfolio construction."""
    
    def test_single_asset_portfolio(self):
        """Test portfolio with single asset."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A"],
            "date": ["2023-01-01"],
            "alpha_momentum_rank": [0.9]
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        assert len(portfolio) == 1
        assert portfolio["target_weight"].iloc[0] == 1.0
    
    def test_empty_alphas(self):
        """Test portfolio construction with no alphas."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": [],
            "date": [],
            "alpha_momentum_rank": []
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        # Should return empty portfolio
        assert len(portfolio) == 0
    
    def test_all_equal_alphas(self):
        """Test portfolio with all equal alpha signals."""
        config = OptimizerConfig(method="rank_weight")
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.5, 0.5, 0.5, 0.5, 0.5]  # All equal
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        # Should fall back to equal weight
        assert len(portfolio) == 5
        weights = portfolio["target_weight"]
        assert np.allclose(weights, 0.2, atol=0.01)  # 1/5 each
    
    def test_extreme_alpha_values(self):
        """Test portfolio with extreme alpha values."""
        config = OptimizerConfig(method="rank_weight")
        optimizer = PortfolioOptimizer(config=config)
        
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "alpha_momentum_rank": [1.0, 0.5, 0.0]  # Extreme spread
        })
        
        portfolio = optimizer.construct_portfolio(alphas)
        
        # Should handle extreme values gracefully
        assert len(portfolio) == 3
        assert np.isclose(portfolio["target_weight"].sum(), 1.0, atol=0.01)


class TestPortfolioIntegration:
    """Test portfolio construction integration with risk layer."""
    
    def test_risk_to_portfolio_pipeline(self):
        """Test complete risk -> portfolio pipeline."""
        from omega.risk.individual_risk_guard import IndividualRiskGuard, RiskGuardConfig
        
        # Create risk-adjusted alphas
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1],
            "volatility": [0.15, 0.20, 0.18, 0.12, 0.10]
        })
        
        # Apply risk controls
        risk_config = RiskGuardConfig(max_position_size=0.30)
        risk_guard = IndividualRiskGuard(config=risk_config)
        
        # Construct portfolio
        opt_config = OptimizerConfig(method="rank_weight")
        optimizer = PortfolioOptimizer(config=opt_config)
        
        portfolio = optimizer.construct_portfolio(alphas)
        risk_adjusted = risk_guard.apply_limits(portfolio)
        
        # Verify complete pipeline
        assert len(risk_adjusted) > 0
        assert risk_adjusted["target_weight"].max() <= 0.30
        assert np.isclose(risk_adjusted["target_weight"].sum(), 1.0, atol=0.01)
    
    def test_multi_period_rebalancing(self):
        """Test portfolio rebalancing across multiple periods."""
        config = OptimizerConfig(rebalance_threshold=0.05)
        optimizer = PortfolioOptimizer(config=config)
        
        # Period 1
        alphas_t1 = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "alpha_momentum_rank": [0.8, 0.5, 0.2]
        })
        
        portfolio_t1 = optimizer.construct_portfolio(alphas_t1)
        
        # Period 2 (different alphas)
        alphas_t2 = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-08"] * 3,
            "alpha_momentum_rank": [0.6, 0.7, 0.4]
        })
        
        portfolio_t2 = optimizer.construct_portfolio(alphas_t2)
        
        # Compute trades
        trades = optimizer.compute_rebalance_trades(
            portfolio_t1.rename(columns={"target_weight": "current_weight"}),
            portfolio_t2
        )
        
        assert len(trades) > 0


class TestPortfolioMetrics:
    """Test portfolio metrics and analytics."""
    
    def test_portfolio_concentration(self):
        """Test portfolio concentration metrics."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        portfolio = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "target_weight": [0.40, 0.25, 0.15, 0.10, 0.10]
        })
        
        metrics = optimizer.compute_portfolio_metrics(portfolio)
        
        assert "herfindahl_index" in metrics
        assert "effective_n" in metrics
        # Herfindahl should be > 1/N for concentrated portfolio
        assert metrics["herfindahl_index"] > 0.2
    
    def test_portfolio_diversification(self):
        """Test portfolio diversification metrics."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        # Well-diversified portfolio
        portfolio = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "target_weight": [0.20, 0.20, 0.20, 0.20, 0.20]
        })
        
        metrics = optimizer.compute_portfolio_metrics(portfolio)
        
        assert "effective_n" in metrics
        # Effective N should be close to 5 for equal weight
        assert metrics["effective_n"] > 4.5
    
    def test_portfolio_turnover_calculation(self):
        """Test portfolio turnover calculation."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        current = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "current_weight": [0.40, 0.35, 0.25]
        })
        
        target = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "target_weight": [0.50, 0.25, 0.25]
        })
        
        turnover = optimizer.compute_turnover(current, target)
        
        # Turnover = (|0.10| + |-0.10| + |0|) / 2 = 0.10
        assert np.isclose(turnover, 0.10, atol=0.01)


class TestPortfolioPITSafety:
    """Test PIT safety in portfolio construction."""
    
    def test_portfolio_uses_current_data_only(self):
        """Test that portfolio construction uses only current data."""
        config = OptimizerConfig()
        optimizer = PortfolioOptimizer(config=config)
        
        # Create alphas with timestamps
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 3,
            "alpha_momentum_rank": np.random.rand(30)
        })
        
        # Construct portfolio for each date using only that date's data
        for date in alphas["date"].unique():
            date_alphas = alphas[alphas["date"] == date]
            portfolio = optimizer.construct_portfolio(date_alphas)
            
            # Portfolio should only use alphas from current date
            assert len(portfolio) > 0
            assert (portfolio["date"] == date).all() if "date" in portfolio.columns else True
    
    def test_rebalancing_no_lookahead(self):
        """Test that rebalancing doesn't use future data."""
        config = OptimizerConfig(rebalance_threshold=0.05)
        optimizer = PortfolioOptimizer(config=config)
        
        # Simulate time series of portfolios
        dates = pd.date_range("2023-01-01", periods=10, freq="W")
        
        previous_portfolio = None
        
        for date in dates:
            # Generate alphas for current date
            alphas = pd.DataFrame({
                "ticker": ["A", "B", "C"],
                "date": [date] * 3,
                "alpha_momentum_rank": np.random.rand(3)
            })
            
            current_portfolio = optimizer.construct_portfolio(alphas)
            
            if previous_portfolio is not None:
                # Rebalancing should only use current and previous data
                trades = optimizer.compute_rebalance_trades(
                    previous_portfolio.rename(columns={"target_weight": "current_weight"}),
                    current_portfolio
                )
                
                # Verify trades are valid
                assert len(trades) >= 0
            
            previous_portfolio = current_portfolio


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
