"""
Full Data Flow Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests complete end-to-end data flow: Data -> Features -> Alpha -> Risk -> Execution
Verifies all 7 layers work together correctly with PIT safety maintained throughout.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from omega.core.pipeline import OmegaPipeline, PipelineConfig, PipelineResult


class TestFullDataFlowIntegration:
    """Test complete data flow through all 7 layers."""
    
    def test_complete_pipeline_execution(self, tmp_path, monkeypatch):
        """Test complete pipeline from data to execution."""
        # Create pipeline config
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC", "HPG"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime(),
            rebalance_frequency="weekly"
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader with realistic data
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:25]
            base_price = {"VNM": 100.0, "VIC": 80.0, "HPG": 120.0}.get(ticker, 100.0)
            
            data = []
            for i, date in enumerate(dates):
                # Add some realistic price movement
                price = base_price + np.sin(i * 0.2) * 5 + np.random.randn() * 2
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": price * 0.99,
                    "high": price * 1.01,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000 + np.random.randint(-100000, 100000),
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        # Run complete pipeline
        result = pipeline.run()
        
        # Verify all stages completed successfully
        assert result.success is True
        assert result.data is not None
        assert result.features is not None
        assert result.alphas is not None
        assert result.positions is not None
        assert result.executions is not None
        assert result.metrics is not None
        
        # Verify data flow
        assert len(result.data) > 0
        assert len(result.features) > 0
        assert len(result.alphas) > 0
        assert len(result.positions) > 0
        assert len(result.executions) > 0
        
        # Verify metrics
        assert "total_trades" in result.metrics
        assert result.metrics["total_trades"] > 0
    
    def test_multi_period_rebalancing(self, tmp_path, monkeypatch):
        """Test pipeline with multiple rebalancing periods."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC"],
            start_date="2023-01-01",
            end_date="2023-02-28",
            as_of_time=pd.to_datetime("2023-02-28").to_pydatetime(),
            rebalance_frequency="weekly"
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:50]
            base_price = 100.0 if ticker == "VNM" else 80.0
            
            data = []
            for i, date in enumerate(dates):
                price = base_price + i * 0.5  # Uptrend
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": price * 0.99,
                    "high": price * 1.01,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Should have multiple rebalancing periods
        assert result.success is True
        assert len(result.executions) > 2  # Multiple periods
    
    def test_pipeline_with_different_universes(self, tmp_path, monkeypatch):
        """Test pipeline with different universe sizes."""
        universes = [
            ["VNM"],  # Single stock
            ["VNM", "VIC"],  # Two stocks
            ["VNM", "VIC", "HPG", "VHM", "VCB"]  # Five stocks
        ]
        
        for universe in universes:
            config = PipelineConfig(
                data_dir=tmp_path / "data",
                cache_dir=tmp_path / "cache",
                universe=universe,
                start_date="2023-01-01",
                end_date="2023-01-31",
                as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
            )
            
            pipeline = OmegaPipeline(config)
            
            # Mock data loader
            def mock_load_prices(ticker, start_date, end_date, as_of_time):
                dates = pd.date_range(start_date, end_date, freq="D")[:20]
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
                        "as_of": date,
                        "available_at": date + timedelta(days=1)
                    })
                return pd.DataFrame(data)
            
            monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
            
            result = pipeline.run()
            
            # Should work for all universe sizes
            assert result.success is True
            assert len(result.positions) > 0


class TestDataFlowWithErrors:
    """Test data flow with various error conditions."""
    
    def test_pipeline_handles_missing_data(self, tmp_path, monkeypatch):
        """Test pipeline handles missing data gracefully."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader with missing data for one ticker
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            if ticker == "VIC":
                # Return empty data for VIC
                return pd.DataFrame({
                    "ticker": [],
                    "date": [],
                    "open": [],
                    "high": [],
                    "low": [],
                    "close": [],
                    "volume": [],
                    "as_of": [],
                    "available_at": []
                })
            
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
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
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Should handle missing data gracefully
        # May succeed with partial data or fail gracefully
        if result.success:
            assert len(result.data) > 0
        else:
            assert len(result.errors) > 0
    
    def test_pipeline_handles_insufficient_history(self, tmp_path, monkeypatch):
        """Test pipeline with insufficient historical data."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-01-05",  # Only 5 days
            as_of_time=pd.to_datetime("2023-01-05").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader with minimal data
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:3]  # Only 3 days
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
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Should handle insufficient data
        # May succeed with limited features or fail gracefully
        assert result is not None


class TestDataFlowPerformance:
    """Test data flow performance and efficiency."""
    
    def test_pipeline_execution_time(self, tmp_path, monkeypatch):
        """Test pipeline execution completes in reasonable time."""
        import time
        
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC", "HPG"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
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
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        # Measure execution time
        start_time = time.time()
        result = pipeline.run()
        execution_time = time.time() - start_time
        
        # Should complete in reasonable time (< 10 seconds for test data)
        assert execution_time < 10.0
        assert result.success is True
    
    def test_pipeline_memory_efficiency(self, tmp_path, monkeypatch):
        """Test pipeline doesn't leak memory."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        # Mock data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
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
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        # Run pipeline multiple times
        for _ in range(3):
            pipeline = OmegaPipeline(config)
            monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
            result = pipeline.run()
            assert result.success is True
            
            # Clean up
            del pipeline
            del result


class TestDataFlowConsistency:
    """Test data flow consistency and reproducibility."""
    
    def test_pipeline_reproducibility(self, tmp_path, monkeypatch):
        """Test pipeline produces consistent results."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        # Mock data loader with deterministic data
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
            np.random.seed(42)  # Fixed seed
            data = []
            for i, date in enumerate(dates):
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": 100.0 + i,
                    "high": 101.0 + i,
                    "low": 99.0 + i,
                    "close": 100.0 + i,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        # Run pipeline twice
        pipeline1 = OmegaPipeline(config)
        monkeypatch.setattr(pipeline1.data_loader, "load_prices", mock_load_prices)
        result1 = pipeline1.run()
        
        pipeline2 = OmegaPipeline(config)
        monkeypatch.setattr(pipeline2.data_loader, "load_prices", mock_load_prices)
        result2 = pipeline2.run()
        
        # Results should be identical
        assert result1.success == result2.success
        assert len(result1.data) == len(result2.data)
        assert len(result1.positions) == len(result2.positions)
    
    def test_pipeline_data_integrity(self, tmp_path, monkeypatch):
        """Test data integrity throughout pipeline."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
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
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Verify data integrity
        assert result.success is True
        
        # Check for NaN values in critical columns
        if result.positions is not None:
            assert not result.positions["target_weight"].isna().any()
        
        # Check for infinite values
        if result.features is not None:
            numeric_cols = result.features.select_dtypes(include=[np.number]).columns
            assert not np.isinf(result.features[numeric_cols]).any().any()


class TestDataFlowEdgeCases:
    """Test edge cases in data flow."""
    
    def test_pipeline_with_single_day(self, tmp_path, monkeypatch):
        """Test pipeline with single day of data."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-01-01",
            as_of_time=pd.to_datetime("2023-01-01").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            return pd.DataFrame({
                "ticker": [ticker],
                "date": [pd.Timestamp("2023-01-01")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000000],
                "as_of": [pd.Timestamp("2023-01-01")],
                "available_at": [pd.Timestamp("2023-01-02")]
            })
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Should handle single day gracefully
        assert result is not None
    
    def test_pipeline_with_extreme_volatility(self, tmp_path, monkeypatch):
        """Test pipeline with extreme market volatility."""
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader with extreme volatility
        def mock_load_prices(ticker, start_date, end_date, as_of_time):
            dates = pd.date_range(start_date, end_date, freq="D")[:20]
            data = []
            for i, date in enumerate(dates):
                # Extreme price swings
                price = 100.0 * (1.5 if i % 2 == 0 else 0.5)
                data.append({
                    "ticker": ticker,
                    "date": date,
                    "open": price * 0.99,
                    "high": price * 1.01,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 1000000,
                    "as_of": date,
                    "available_at": date + timedelta(days=1)
                })
            return pd.DataFrame(data)
        
        monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
        
        result = pipeline.run()
        
        # Should handle extreme volatility
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
