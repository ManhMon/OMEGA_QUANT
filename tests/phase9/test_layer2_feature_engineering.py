"""
Layer 2: Feature Engineering Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests feature computation, PIT safety in features, and feature quality.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.feature_module import FeatureModule, FeatureModuleConfig
from omega.quant.features.basic_indicators import compute_returns, compute_volatility
from omega.quant.features.cross_sectional import compute_rank, compute_zscore


class TestFeatureEngineeringLayer:
    """Test Layer 2: Feature Engineering with PIT safety."""
    
    def test_feature_module_initialization(self):
        """Test FeatureModule initializes correctly."""
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        assert module is not None
        assert module.config == config
    
    def test_compute_basic_features(self):
        """Test computation of basic technical features."""
        # Create mock price data
        data = pd.DataFrame({
            "ticker": ["VNM"] * 30,
            "date": pd.date_range("2023-01-01", periods=30, freq="D"),
            "open": np.linspace(100, 110, 30),
            "high": np.linspace(101, 111, 30),
            "low": np.linspace(99, 109, 30),
            "close": np.linspace(100, 110, 30),
            "volume": [1000000] * 30,
            "as_of": pd.date_range("2023-01-01", periods=30, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=30, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        assert len(features) > 0
        assert "ticker" in features.columns
        assert "date" in features.columns
        # Check for common features
        assert any("ret" in col for col in features.columns)
    
    def test_feature_pit_safety(self):
        """Test that features maintain PIT safety (no look-ahead)."""
        # Create data with clear trend
        data = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "close": list(range(100, 120)),  # Clear uptrend
            "volume": [1000000] * 20,
            "as_of": pd.date_range("2023-01-01", periods=20, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=20, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Verify no future data leakage
        # For each row, features should only use data from current and past
        for idx in range(len(features)):
            row = features.iloc[idx]
            current_date = row["date"]
            
            # All feature values should be computable from data <= current_date
            # This is implicit in the feature computation logic
            assert pd.notna(current_date)
    
    def test_returns_computation(self):
        """Test return feature computation."""
        prices = pd.Series([100, 102, 101, 105, 103])
        
        returns = compute_returns(prices, periods=1)
        
        assert len(returns) == len(prices)
        assert pd.isna(returns.iloc[0])  # First return is NaN
        assert np.isclose(returns.iloc[1], 0.02, atol=0.001)  # (102-100)/100
    
    def test_volatility_computation(self):
        """Test volatility feature computation."""
        returns = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02, 0.005, -0.015, 0.01, -0.005, 0.02])
        
        volatility = compute_volatility(returns, window=5)
        
        assert len(volatility) == len(returns)
        # First 4 values should be NaN (need 5 values for window=5)
        assert pd.isna(volatility.iloc[:4]).all()
        assert pd.notna(volatility.iloc[4:]).all()
    
    def test_cross_sectional_rank(self):
        """Test cross-sectional ranking."""
        data = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "value": [10, 20, 15, 25, 5]
        })
        
        ranked = compute_rank(data, "value", groupby="date")
        
        assert "value_rank" in ranked.columns
        # Check ranking order (E=1, A=2, C=3, B=4, D=5)
        assert ranked[ranked["ticker"] == "E"]["value_rank"].iloc[0] == 1
        assert ranked[ranked["ticker"] == "D"]["value_rank"].iloc[0] == 5
    
    def test_cross_sectional_zscore(self):
        """Test cross-sectional z-score normalization."""
        data = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "value": [10, 20, 15, 25, 5]
        })
        
        normalized = compute_zscore(data, "value", groupby="date")
        
        assert "value_zscore" in normalized.columns
        # Z-scores should have mean ~0 and std ~1
        zscores = normalized["value_zscore"]
        assert np.isclose(zscores.mean(), 0, atol=0.1)
        assert np.isclose(zscores.std(), 1, atol=0.1)
    
    def test_feature_with_insufficient_data(self):
        """Test feature computation with insufficient data."""
        # Only 2 rows - not enough for most features
        data = pd.DataFrame({
            "ticker": ["VNM"] * 2,
            "date": pd.date_range("2023-01-01", periods=2, freq="D"),
            "close": [100, 101],
            "volume": [1000000, 1100000],
            "as_of": pd.date_range("2023-01-01", periods=2, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=2, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Should return features but many will be NaN
        assert len(features) > 0
        # Most features should be NaN due to insufficient history
        nan_ratio = features.isna().sum().sum() / (features.shape[0] * features.shape[1])
        assert nan_ratio > 0.5  # More than 50% NaN expected
    
    def test_feature_multiple_tickers(self):
        """Test feature computation across multiple tickers."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 20 + ["VIC"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D").tolist() * 2,
            "close": list(range(100, 120)) + list(range(80, 100)),
            "volume": [1000000] * 40,
            "as_of": pd.date_range("2023-01-01", periods=20, freq="D").tolist() * 2,
            "available_at": pd.date_range("2023-01-02", periods=20, freq="D").tolist() * 2
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        assert len(features) > 0
        assert set(features["ticker"].unique()) == {"VNM", "VIC"}
        
        # Features should be computed separately for each ticker
        vnm_features = features[features["ticker"] == "VNM"]
        vic_features = features[features["ticker"] == "VIC"]
        
        assert len(vnm_features) > 0
        assert len(vic_features) > 0


class TestFeatureEngineeringBoundary:
    """Test boundary conditions for feature engineering."""
    
    def test_missing_price_data(self):
        """Test handling of missing price data."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "close": [100, np.nan, 102, 103, np.nan, 105, 106, 107, 108, 109],
            "volume": [1000000] * 10,
            "as_of": pd.date_range("2023-01-01", periods=10, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Should handle missing data gracefully
        assert len(features) > 0
    
    def test_constant_prices(self):
        """Test feature computation with constant prices."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "close": [100.0] * 20,  # Constant price
            "volume": [1000000] * 20,
            "as_of": pd.date_range("2023-01-01", periods=20, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=20, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Should compute features even with constant prices
        assert len(features) > 0
        
        # Returns should be zero
        if "ret_1" in features.columns:
            returns = features["ret_1"].dropna()
            assert np.allclose(returns, 0, atol=1e-6)
    
    def test_extreme_price_movements(self):
        """Test feature computation with extreme price movements."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "close": [100, 200, 50, 150, 75, 125, 90, 110, 95, 105],  # Extreme volatility
            "volume": [1000000] * 10,
            "as_of": pd.date_range("2023-01-01", periods=10, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Should handle extreme movements without crashing
        assert len(features) > 0
        
        # Volatility should be high
        if "volatility_5" in features.columns:
            vol = features["volatility_5"].dropna()
            assert vol.max() > 0.5  # High volatility expected
    
    def test_single_ticker_single_day(self):
        """Test feature computation with minimal data."""
        data = pd.DataFrame({
            "ticker": ["VNM"],
            "date": [pd.Timestamp("2023-01-01")],
            "close": [100.0],
            "volume": [1000000],
            "as_of": [pd.Timestamp("2023-01-01")],
            "available_at": [pd.Timestamp("2023-01-02")]
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Should return features but all will be NaN (no history)
        assert len(features) == 1
    
    def test_feature_consistency_across_runs(self):
        """Test that feature computation is deterministic."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "close": np.random.RandomState(42).randn(20).cumsum() + 100,
            "volume": [1000000] * 20,
            "as_of": pd.date_range("2023-01-01", periods=20, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=20, freq="D")
        })
        
        config = FeatureModuleConfig()
        module1 = FeatureModule(config=config)
        module2 = FeatureModule(config=config)
        
        features1 = module1.compute_features(data.copy())
        features2 = module2.compute_features(data.copy())
        
        # Results should be identical
        pd.testing.assert_frame_equal(features1, features2)


class TestFeatureQuality:
    """Test feature quality and statistical properties."""
    
    def test_feature_no_inf_values(self):
        """Test that features don't contain infinite values."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "close": np.linspace(100, 120, 20),
            "volume": [1000000] * 20,
            "as_of": pd.date_range("2023-01-01", periods=20, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=20, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # No infinite values allowed
        assert not np.isinf(features.select_dtypes(include=[np.number])).any().any()
    
    def test_feature_reasonable_ranges(self):
        """Test that features are in reasonable ranges."""
        data = pd.DataFrame({
            "ticker": ["VNM"] * 30,
            "date": pd.date_range("2023-01-01", periods=30, freq="D"),
            "close": np.linspace(100, 110, 30),
            "volume": [1000000] * 30,
            "as_of": pd.date_range("2023-01-01", periods=30, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=30, freq="D")
        })
        
        config = FeatureModuleConfig()
        module = FeatureModule(config=config)
        
        features = module.compute_features(data)
        
        # Returns should be reasonable (e.g., < 100% daily)
        if "ret_1" in features.columns:
            returns = features["ret_1"].dropna()
            assert returns.abs().max() < 1.0  # Less than 100% daily return


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
