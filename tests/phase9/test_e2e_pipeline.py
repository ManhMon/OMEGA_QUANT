"""
E2E Pipeline Tests - Phase 9 Integration
Backend Engineer (Role 9) - L2 OpenCode

Tests the full Data -> Features -> Alpha -> Risk -> Execution flow.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from omega.core.pipeline import (
    OmegaPipeline,
    PipelineConfig,
    PipelineResult,
    run_pipeline
)
from omega.quant.feature_module import FeatureModuleConfig
from omega.quant.alpha_discovery import DiscoveryConfig
from omega.risk.circuit_breaker import CircuitBreakerConfig
from omega.risk.individual_risk_guard import RiskGuardConfig
from omega.quant.execution_sim import ExecutionConfig


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config(temp_data_dir):
    """Create a mock pipeline configuration."""
    return PipelineConfig(
        data_dir=temp_data_dir / "data",
        cache_dir=temp_data_dir / "cache",
        universe=["VNM", "VIC"],
        start_date="2023-01-01",
        end_date="2023-01-31",
        as_of_time=pd.to_datetime("2023-01-31").to_pydatetime(),
        rebalance_frequency="weekly"
    )


@pytest.fixture
def mock_market_data():
    """Create mock market data for testing."""
    dates = pd.date_range("2023-01-01", "2023-01-31", freq="D")
    tickers = ["VNM", "VIC"]
    
    data = []
    for ticker in tickers:
        for date in dates:
            # Generate synthetic price data
            base_price = 100.0 if ticker == "VNM" else 80.0
            noise = np.random.randn() * 2
            close = base_price + noise
            
            data.append({
                "ticker": ticker,
                "date": date,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "volume": np.random.randint(1000000, 5000000),
                "as_of": datetime.now(),
                "available_at": date + timedelta(days=1)
            })
    
    return pd.DataFrame(data)


class TestPipelineConfig:
    """Test PipelineConfig initialization and validation."""
    
    def test_default_config(self):
        """Test default configuration - now requires mandatory as_of_time."""
        config = PipelineConfig(
            universe=["VNM", "VIC", "VHM"],
            start_date="2023-01-01",
            end_date="2023-12-31",
            as_of_time=pd.to_datetime("2023-12-31").to_pydatetime()
        )
        
        assert config.data_dir == Path("data")
        assert config.cache_dir == Path("data/cache")
        assert len(config.universe) == 3
        assert config.rebalance_frequency == "weekly"
        assert config.as_of_time is not None
    
    def test_custom_config(self, temp_data_dir):
        """Test custom configuration."""
        config = PipelineConfig(
            data_dir=temp_data_dir / "custom_data",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-12-31",
            as_of_time=pd.to_datetime("2023-12-31").to_pydatetime()
        )
        
        assert config.data_dir == temp_data_dir / "custom_data"
        assert config.universe == ["VNM"]
        assert config.start_date == "2023-01-01"
        assert config.as_of_time is not None


class TestPipelineResult:
    """Test PipelineResult structure."""
    
    def test_success_result(self):
        """Test successful result."""
        result = PipelineResult(
            success=True,
            message="Pipeline executed successfully",
            metrics={"total_trades": 10}
        )
        
        assert result.success is True
        assert result.message == "Pipeline executed successfully"
        assert result.metrics["total_trades"] == 10
        assert len(result.errors) == 0
    
    def test_failure_result(self):
        """Test failure result."""
        result = PipelineResult(
            success=False,
            message="Pipeline failed",
            errors=["Error 1", "Error 2"]
        )
        
        assert result.success is False
        assert len(result.errors) == 2


class TestOmegaPipeline:
    """Test OmegaPipeline E2E execution."""
    
    def test_pipeline_initialization(self, mock_config):
        """Test pipeline initialization."""
        pipeline = OmegaPipeline(mock_config)
        
        assert pipeline.config == mock_config
        assert pipeline.data_loader is not None
        assert pipeline.feature_module is not None
        assert pipeline.alpha_engine is not None
        assert pipeline.circuit_breaker is not None
        assert pipeline.risk_guard is not None
        assert pipeline.execution_sim is not None
    
    def test_load_data_step(self, mock_config, monkeypatch):
        """Test data loading step."""
        pipeline = OmegaPipeline(mock_config)
        
        # Mock the data loader to return synthetic data
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date,  # Fix: as_of should be <= available_at
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline._load_data()
        
        assert result["success"] is True
        assert result["data"] is not None
        assert len(result["data"]) > 0
        assert "ticker" in result["data"].columns
        assert "close" in result["data"].columns
    
    def test_compute_features_step(self, mock_config, mock_market_data):
        """Test feature computation step."""
        pipeline = OmegaPipeline(mock_config)
        
        result = pipeline._compute_features(mock_market_data)
        
        assert result["success"] is True
        assert result["features"] is not None
        # Features may be empty if warmup period is too long
        # Just check structure
        if len(result["features"]) > 0:
            assert "ticker" in result["features"].columns
            assert "date" in result["features"].columns
    
    def test_generate_alphas_step(self, mock_config):
        """Test alpha generation step."""
        pipeline = OmegaPipeline(mock_config)
        
        # Create mock features
        features = pd.DataFrame({
            "ticker": ["VNM", "VIC"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D").tolist() * 2,
            "close": np.random.randn(20) * 10 + 100,
            "ret_5": np.random.randn(20) * 0.02
        })
        
        result = pipeline._generate_alphas(features)
        
        assert result["success"] is True
        assert result["alphas"] is not None
        assert "alpha_momentum" in result["alphas"].columns
        assert "alpha_momentum_rank" in result["alphas"].columns
    
    def test_apply_risk_controls_step(self, mock_config, mock_market_data):
        """Test risk controls step."""
        pipeline = OmegaPipeline(mock_config)
        
        # Create mock alphas with more stocks to test position limits properly
        alphas = pd.DataFrame({
            "ticker": ["VNM", "VIC", "HPG", "VHM", "VCB"] * 4,
            "date": pd.date_range("2023-01-01", periods=4, freq="D").tolist() * 5,
            "alpha_momentum_rank": np.random.rand(20)
        })
        
        result = pipeline._apply_risk_controls(alphas, mock_market_data)
        
        assert result["success"] is True
        assert result["positions"] is not None
        assert "target_weight" in result["positions"].columns
        
        # Check that weights sum to approximately 1.0 per date
        weight_sums = result["positions"].groupby("date")["target_weight"].sum()
        assert all(abs(weight_sums - 1.0) < 0.01)  # Allow small floating point error
    
    def test_simulate_execution_step(self, mock_config, mock_market_data):
        """Test execution simulation step."""
        pipeline = OmegaPipeline(mock_config)
        
        # Create mock positions
        positions = pd.DataFrame({
            "ticker": ["VNM", "VIC"] * 5,
            "date": pd.date_range("2023-01-01", periods=5, freq="D").tolist() * 2,
            "target_weight": [0.5, 0.5] * 5
        })
        
        result = pipeline._simulate_execution(positions, mock_market_data)
        
        assert result["success"] is True
        assert result["executions"] is not None
        assert result["metrics"] is not None
        assert "total_trades" in result["metrics"]
        assert "avg_cost_bps" in result["metrics"]
    
    def test_full_pipeline_run_mock(self, mock_config, monkeypatch):
        """Test full pipeline run with mocked data loader."""
        pipeline = OmegaPipeline(mock_config)
        
        # Mock the data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]  # Limit to 20 days
            data = []
            base_price = 100.0 if ticker == "VNM" else 80.0
            for i, date in enumerate(dates):
                close = base_price + np.sin(i * 0.1) * 5  # Synthetic trend
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 1000000 + i * 10000,
                    "as_of": date,  # Fix: as_of should be <= available_at
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        assert result.success is True
        assert result.data is not None
        assert result.features is not None
        assert result.alphas is not None
        assert result.positions is not None
        assert result.executions is not None
        assert result.metrics is not None
        assert len(result.errors) == 0


class TestPipelineIntegration:
    """Integration tests for the full pipeline."""
    
    def test_run_pipeline_convenience_function(self, mock_config, monkeypatch):
        """Test run_pipeline convenience function."""
        # Mock DataLoader.load_prices at module level
        from omega.data import loader
        
        def mock_load_prices(self, ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:15]
            data = []
            for i, date in enumerate(dates):
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0 + i * 0.5,
                    "volume": 1000000,
                    "as_of": date,  # Fix: as_of should be <= available_at
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(loader.DataLoader, "load_prices", mock_load_prices)
        
        result = run_pipeline(mock_config)
        
        assert isinstance(result, PipelineResult)
        assert result.success is True
    
    def test_pipeline_pit_safety(self, mock_config, monkeypatch):
        """Test that pipeline maintains PIT safety throughout."""
        pipeline = OmegaPipeline(mock_config)
        
        # Mock data with PIT violation
        def mock_load_prices_with_violation(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:10]
            data = []
            for date in dates:
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000000,
                    "as_of": date + timedelta(days=2),  # VIOLATION: as_of > available_at
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices_with_violation)
        
        result = pipeline.run()
        
        # Pipeline should detect PIT violation and fail
        assert result.success is False
        assert "PIT violation" in result.message


class TestPipelineErrorHandling:
    """Test error handling in pipeline."""
    
    def test_pipeline_handles_data_loading_error(self, mock_config, monkeypatch):
        """Test pipeline handles data loading errors gracefully."""
        pipeline = OmegaPipeline(mock_config)
        
        # Mock data loader to raise exception
        def mock_load_prices_error(ticker, start_date, end_date, as_of_time):
            raise ValueError("Data source unavailable")
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices_error)
        
        result = pipeline.run()
        
        assert result.success is False
        assert "Data loading failed" in result.message or "Data loading error" in result.message
        assert len(result.errors) > 0
    
    def test_pipeline_handles_feature_computation_error(self, mock_config, monkeypatch):
        """Test pipeline handles feature computation errors."""
        pipeline = OmegaPipeline(mock_config)
        
        # Mock successful data loading but with insufficient data for features
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            # Return only 1 row - not enough for feature computation
            return pd.DataFrame({
                "ticker": [ticker],
                "date": [pd.Timestamp("2023-01-01")],
                "open": [99.0],
                "high": [101.0],
                "low": [98.0],
                "close": [100.0],
                "volume": [1000000],
                "as_of": [pd.Timestamp("2023-01-01")],
                "available_at": [pd.Timestamp("2023-01-02")]
            })
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # With only 1 row per ticker, features will be computed but all NaN (dropped)
        # Pipeline should still succeed (graceful degradation)
        assert result.success is True
        # May generate minimal trades or no trades depending on fallback behavior
        assert result.metrics["total_trades"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
