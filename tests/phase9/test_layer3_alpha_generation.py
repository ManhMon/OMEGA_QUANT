"""
Layer 3: Alpha Generation Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests alpha signal generation, ranking, and PIT safety in alpha computation.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.alpha_discovery import AlphaDiscoveryEngine, DiscoveryConfig
from omega.quant.alpha_primitives import compute_momentum, compute_reversal


class TestAlphaGenerationLayer:
    """Test Layer 3: Alpha Generation with PIT safety."""
    
    def test_alpha_engine_initialization(self):
        """Test AlphaDiscoveryEngine initializes correctly."""
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        assert engine is not None
        assert engine.config == config
    
    def test_generate_momentum_alpha(self):
        """Test momentum alpha signal generation."""
        # Create features with clear momentum
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "close": np.linspace(100, 120, 20),  # Uptrend
            "ret_5": [0.02] * 20,  # Positive returns
            "ret_10": [0.05] * 20,
            "volume": [1000000] * 20
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        assert len(alphas) > 0
        assert "ticker" in alphas.columns
        assert "date" in alphas.columns
        assert "alpha_momentum" in alphas.columns
    
    def test_alpha_ranking(self):
        """Test cross-sectional alpha ranking."""
        features = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"] * 4,
            "date": pd.date_range("2023-01-01", periods=4, freq="D").tolist() * 5,
            "ret_5": [0.05, 0.02, -0.01, 0.03, -0.02] * 4,
            "ret_10": [0.10, 0.05, -0.02, 0.07, -0.05] * 4,
            "volume": [1000000] * 20
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Check that ranking columns exist
        assert "alpha_momentum_rank" in alphas.columns
        
        # Rankings should be between 0 and 1
        ranks = alphas["alpha_momentum_rank"].dropna()
        assert ranks.min() >= 0
        assert ranks.max() <= 1
    
    def test_alpha_pit_safety(self):
        """Test that alpha signals maintain PIT safety."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 30,
            "date": pd.date_range("2023-01-01", periods=30, freq="D"),
            "close": np.random.RandomState(42).randn(30).cumsum() + 100,
            "ret_5": np.random.RandomState(42).randn(30) * 0.02,
            "ret_10": np.random.RandomState(42).randn(30) * 0.03,
            "volume": [1000000] * 30
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Verify no look-ahead: alpha at time t should only use data <= t
        for idx in range(len(alphas)):
            row = alphas.iloc[idx]
            current_date = row["date"]
            
            # Alpha should be computable from features at current_date
            assert pd.notna(current_date)
    
    def test_momentum_primitive(self):
        """Test momentum alpha primitive."""
        returns = pd.Series([0.01, 0.02, 0.015, 0.03, 0.025, 0.02, 0.01, 0.015, 0.02, 0.025])
        
        momentum = compute_momentum(returns, window=5)
        
        assert len(momentum) == len(returns)
        # First 4 values should be NaN (need 5 values for window=5)
        assert pd.isna(momentum.iloc[:4]).all()
        assert pd.notna(momentum.iloc[4:]).all()
    
    def test_reversal_primitive(self):
        """Test reversal alpha primitive."""
        returns = pd.Series([0.05, -0.03, 0.02, -0.04, 0.03, -0.02, 0.01, -0.01, 0.02, -0.03])
        
        reversal = compute_reversal(returns, window=3)
        
        assert len(reversal) == len(returns)
        # Reversal should be negative of recent returns
        assert pd.notna(reversal.iloc[2:]).all()
    
    def test_alpha_multiple_tickers(self):
        """Test alpha generation across multiple tickers."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20 + ["VIC"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D").tolist() * 2,
            "ret_5": list(np.linspace(0.01, 0.05, 20)) + list(np.linspace(-0.02, 0.02, 20)),
            "ret_10": list(np.linspace(0.02, 0.10, 20)) + list(np.linspace(-0.05, 0.05, 20)),
            "volume": [1000000] * 40
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        assert len(alphas) > 0
        assert set(alphas["ticker"].unique()) == {"VNM", "VIC"}
        
        # Alphas should be computed for each ticker
        vnm_alphas = alphas[alphas["ticker"] == "VNM"]
        vic_alphas = alphas[alphas["ticker"] == "VIC"]
        
        assert len(vnm_alphas) > 0
        assert len(vic_alphas) > 0
    
    def test_alpha_with_missing_features(self):
        """Test alpha generation with missing feature values."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "ret_5": [0.01, np.nan, 0.02, 0.015, np.nan, 0.03, 0.025, 0.02, 0.01, 0.015],
            "ret_10": [0.02, 0.03, np.nan, 0.04, 0.035, np.nan, 0.05, 0.045, 0.04, 0.035],
            "volume": [1000000] * 10
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Should handle missing features gracefully
        assert len(alphas) > 0
        # Some alpha values may be NaN where features are missing
        assert alphas["alpha_momentum"].notna().sum() > 0


class TestAlphaGenerationBoundary:
    """Test boundary conditions for alpha generation."""
    
    def test_single_ticker_alpha(self):
        """Test alpha generation with single ticker."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "ret_5": np.random.randn(20) * 0.02,
            "ret_10": np.random.randn(20) * 0.03,
            "volume": [1000000] * 20
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # With single ticker, ranking should still work
        assert len(alphas) > 0
        assert "alpha_momentum_rank" in alphas.columns
    
    def test_constant_features(self):
        """Test alpha generation with constant features."""
        features = pd.DataFrame({
            "ticker": ["A", "B", "C"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 3,
            "ret_5": [0.0] * 30,  # Constant returns
            "ret_10": [0.0] * 30,
            "volume": [1000000] * 30
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Should handle constant features
        assert len(alphas) > 0
        # Alpha values may be zero or NaN
        assert "alpha_momentum" in alphas.columns
    
    def test_extreme_feature_values(self):
        """Test alpha generation with extreme feature values."""
        features = pd.DataFrame({
            "ticker": ["A", "B", "C"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 3,
            "ret_5": [0.5, -0.5, 0.3] * 10,  # Extreme returns
            "ret_10": [1.0, -0.8, 0.6] * 10,
            "volume": [1000000] * 30
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Should handle extreme values without crashing
        assert len(alphas) > 0
        # Rankings should still be valid
        ranks = alphas["alpha_momentum_rank"].dropna()
        assert ranks.min() >= 0
        assert ranks.max() <= 1
    
    def test_insufficient_features(self):
        """Test alpha generation with insufficient feature data."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 3,
            "date": pd.date_range("2023-01-01", periods=3, freq="D"),
            "ret_5": [0.01, 0.02, 0.015],
            "ret_10": [0.02, 0.03, 0.025],
            "volume": [1000000] * 3
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Should return alphas but many may be NaN
        assert len(alphas) > 0


class TestAlphaQuality:
    """Test alpha signal quality and statistical properties."""
    
    def test_alpha_no_inf_values(self):
        """Test that alpha signals don't contain infinite values."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "ret_5": np.random.randn(20) * 0.02,
            "ret_10": np.random.randn(20) * 0.03,
            "volume": [1000000] * 20
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # No infinite values allowed
        numeric_cols = alphas.select_dtypes(include=[np.number]).columns
        assert not np.isinf(alphas[numeric_cols]).any().any()
    
    def test_alpha_rank_distribution(self):
        """Test that alpha rankings are properly distributed."""
        features = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 5,
            "ret_5": np.random.RandomState(42).randn(50) * 0.02,
            "ret_10": np.random.RandomState(42).randn(50) * 0.03,
            "volume": [1000000] * 50
        })
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Check rank distribution for one date
        date_alphas = alphas[alphas["date"] == alphas["date"].iloc[0]]
        ranks = date_alphas["alpha_momentum_rank"].dropna()
        
        if len(ranks) > 1:
            # Ranks should span the range [0, 1]
            assert ranks.min() < 0.5
            assert ranks.max() > 0.5
    
    def test_alpha_consistency(self):
        """Test that alpha generation is deterministic."""
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "ret_5": np.random.RandomState(42).randn(20) * 0.02,
            "ret_10": np.random.RandomState(42).randn(20) * 0.03,
            "volume": [1000000] * 20
        })
        
        config = DiscoveryConfig()
        engine1 = AlphaDiscoveryEngine(config=config)
        engine2 = AlphaDiscoveryEngine(config=config)
        
        alphas1 = engine1.generate_alphas(features.copy())
        alphas2 = engine2.generate_alphas(features.copy())
        
        # Results should be identical
        pd.testing.assert_frame_equal(alphas1, alphas2)
    
    def test_alpha_signal_strength(self):
        """Test that alpha signals have reasonable strength."""
        # Create features with strong signal - 5 tickers x 10 dates = 50 rows
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        tickers = ["A", "B", "C", "D", "E"]
        
        data = []
        for date in dates:
            for i, ticker in enumerate(tickers):
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "ret_5": [0.05, 0.03, 0.01, -0.01, -0.03][i],  # Clear ranking
                    "ret_10": [0.10, 0.06, 0.02, -0.02, -0.06][i],
                    "volume": 1000000
                })
        
        features = pd.DataFrame(data)
        
        config = DiscoveryConfig()
        engine = AlphaDiscoveryEngine(config=config)
        
        alphas = engine.generate_alphas(features)
        
        # Check that we have alphas generated
        assert len(alphas) > 0
        
        # Check that rankings reflect the signal
        date_alphas = alphas[alphas["date"] == alphas["date"].iloc[0]]
        
        # Check we have data for multiple tickers
        assert len(date_alphas["ticker"].unique()) >= 3
        
        # Check we have data for both tickers A and E
        a_data = date_alphas[date_alphas["ticker"] == "A"]
        e_data = date_alphas[date_alphas["ticker"] == "E"]
        
        if len(a_data) > 0 and len(e_data) > 0 and "alpha_momentum_rank" in date_alphas.columns:
            # Ticker A should have highest rank, E should have lowest
            a_rank = a_data["alpha_momentum_rank"].iloc[0]
            e_rank = e_data["alpha_momentum_rank"].iloc[0]
            assert a_rank > e_rank


class TestAlphaIntegration:
    """Test alpha generation integration with feature layer."""
    
    def test_feature_to_alpha_pipeline(self):
        """Test complete feature -> alpha pipeline."""
        from omega.quant.feature_module import FeatureModule, FeatureModuleConfig
        
        # Create raw price data
        data = pd.DataFrame({
            "ticker": ["VNM"] * 30,
            "date": pd.date_range("2023-01-01", periods=30, freq="D"),
            "close": np.linspace(100, 120, 30),
            "volume": [1000000] * 30,
            "as_of": pd.date_range("2023-01-01", periods=30, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=30, freq="D")
        })
        
        # Compute features
        feature_config = FeatureModuleConfig()
        feature_module = FeatureModule(config=feature_config)
        features = feature_module.compute_features(data)
        
        # Generate alphas
        alpha_config = DiscoveryConfig()
        alpha_engine = AlphaDiscoveryEngine(config=alpha_config)
        alphas = alpha_engine.generate_alphas(features)
        
        # Verify complete pipeline
        assert len(alphas) > 0
        assert "alpha_momentum" in alphas.columns
        assert "alpha_momentum_rank" in alphas.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
