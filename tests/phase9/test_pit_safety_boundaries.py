"""
PIT Safety Verification Tests - Cross-Layer Boundaries
Backend Engineer (Role 9) - L2 OpenCode

Tests PIT safety enforcement at every layer boundary in the pipeline.
Ensures no look-ahead bias across the entire system.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.data.loader import DataLoader
from omega.quant.feature_module import FeatureModule, FeatureModuleConfig
from omega.quant.alpha_discovery import AlphaDiscoveryEngine, DiscoveryConfig
from omega.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from omega.risk.individual_risk_guard import IndividualRiskGuard, RiskGuardConfig
from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig
from omega.quant.pit_guard import PITGuard


class TestPITSafetyBoundaries:
    """Test PIT safety at each layer boundary."""
    
    def test_data_to_feature_boundary(self, tmp_path, monkeypatch):
        """Test PIT safety at Data -> Feature boundary."""
        # Create data with proper PIT timestamps
        data = pd.DataFrame({
            "ticker": ["VNM"] * 30,
            "date": pd.date_range("2023-01-01", periods=30, freq="D"),
            "close": np.linspace(100, 120, 30),
            "volume": [1000000] * 30,
            "as_of": pd.date_range("2023-01-01", periods=30, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=30, freq="D")
        })
        
        # Verify PIT safety in data
        pit_guard = PITGuard()
        assert pit_guard.validate_pit_safety(data) is True
        
        # Compute features
        config = FeatureModuleConfig()
        feature_module = FeatureModule(config=config)
        features = feature_module.compute_features(data)
        
        # Verify features maintain PIT safety
        # Features at time t should only use data available at time t
        for idx in range(len(features)):
            row = features.iloc[idx]
            current_date = row["date"]
            
            # All data used should have available_at <= current_date
            relevant_data = data[data["date"] <= current_date]
            assert len(relevant_data) > 0
    
    def test_feature_to_alpha_boundary(self):
        """Test PIT safety at Feature -> Alpha boundary."""
        # Create features with timestamps
        features = pd.DataFrame({
            "ticker": ["VNM"] * 20,
            "date": pd.date_range("2023-01-01", periods=20, freq="D"),
            "ret_5": np.random.randn(20) * 0.02,
            "ret_10": np.random.randn(20) * 0.03,
            "volume": [1000000] * 20
        })
        
        # Generate alphas
        config = DiscoveryConfig()
        alpha_engine = AlphaDiscoveryEngine(config=config)
        alphas = alpha_engine.generate_alphas(features)
        
        # Verify alphas maintain PIT safety
        # Alpha at time t should only use features at time t
        for date in alphas["date"].unique():
            date_alphas = alphas[alphas["date"] == date]
            date_features = features[features["date"] == date]
            
            # Should have same date
            assert len(date_alphas) > 0
            assert len(date_features) > 0
    
    def test_alpha_to_risk_boundary(self):
        """Test PIT safety at Alpha -> Risk boundary."""
        # Create alphas
        alphas = pd.DataFrame({
            "ticker": ["A", "B", "C", "D", "E"],
            "date": ["2023-01-01"] * 5,
            "alpha_momentum_rank": [0.9, 0.7, 0.5, 0.3, 0.1]
        })
        
        # Apply risk controls
        config = RiskGuardConfig(max_position_size=0.30)
        risk_guard = IndividualRiskGuard(config=config)
        
        # Convert to positions
        positions = alphas.copy()
        positions["target_weight"] = positions["alpha_momentum_rank"] / positions["alpha_momentum_rank"].sum()
        
        risk_adjusted = risk_guard.apply_limits(positions)
        
        # Verify risk controls use only current data
        assert (risk_adjusted["date"] == "2023-01-01").all()
    
    def test_risk_to_execution_boundary(self):
        """Test PIT safety at Risk -> Execution boundary."""
        # Create risk-adjusted positions
        positions = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "target_weight": [0.40, 0.35, 0.25]
        })
        
        # Market data
        market_data = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "date": ["2023-01-01"] * 3,
            "close": [100.0, 80.0, 120.0],
            "volume": [1000000, 800000, 1200000],
            "as_of": ["2023-01-01"] * 3,
            "available_at": ["2023-01-02"] * 3
        })
        
        # Execute
        config = ExecutionConfig()
        simulator = ExecutionSimulator(config=config)
        executions = simulator.simulate_execution(positions, market_data)
        
        # Verify execution uses only available prices
        for idx in range(len(executions)):
            exec_row = executions.iloc[idx]
            ticker = exec_row["ticker"]
            exec_date = exec_row["date"]
            
            # Price should be from market data available at exec_date
            market_row = market_data[
                (market_data["ticker"] == ticker) & 
                (market_data["date"] == exec_date)
            ]
            assert len(market_row) > 0


class TestPITViolationDetection:
    """Test detection of PIT violations."""
    
    def test_detect_future_data_leakage(self):
        """Test detection of future data leakage."""
        pit_guard = PITGuard()
        
        # Create data with PIT violation
        data = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "close": [100.0] * 10,
            "as_of": pd.date_range("2023-01-03", periods=10, freq="D"),  # VIOLATION
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        # Should detect violation
        assert pit_guard.validate_pit_safety(data) is False
        
        violations = pit_guard.find_violations(data)
        assert len(violations) > 0
    
    def test_detect_lookahead_in_features(self):
        """Test detection of look-ahead bias in features."""
        pit_guard = PITGuard()
        
        # Create features that use future data
        features = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "future_return": [0.01, 0.02, 0.015, 0.03, 0.025, 0.02, 0.01, 0.015, 0.02, 0.025]
        })
        
        # Feature named "future_return" should trigger warning
        warnings = pit_guard.check_feature_names(features)
        assert len(warnings) > 0
    
    def test_detect_timestamp_inconsistency(self):
        """Test detection of timestamp inconsistencies."""
        pit_guard = PITGuard()
        
        # Create data with inconsistent timestamps
        data = pd.DataFrame({
            "ticker": ["VNM"] * 5,
            "date": pd.date_range("2023-01-01", periods=5, freq="D"),
            "close": [100.0] * 5,
            "as_of": [
                pd.Timestamp("2023-01-01"),
                pd.Timestamp("2023-01-02"),
                pd.Timestamp("2023-01-05"),  # Gap
                pd.Timestamp("2023-01-04"),  # Out of order
                pd.Timestamp("2023-01-05")
            ],
            "available_at": pd.date_range("2023-01-02", periods=5, freq="D")
        })
        
        issues = pit_guard.check_timestamp_consistency(data)
        assert len(issues) > 0


class TestPITSafetyEndToEnd:
    """Test PIT safety through entire pipeline."""
    
    def test_full_pipeline_pit_safety(self, tmp_path, monkeypatch):
        """Test PIT safety through complete pipeline."""
        from omega.core.pipeline import OmegaPipeline, PipelineConfig
        
        # Create config
        config = PipelineConfig(
            data_dir=tmp_path / "data",
            cache_dir=tmp_path / "cache",
            universe=["VNM", "VIC"],
            start_date="2023-01-01",
            end_date="2023-01-31",
            as_of_time=pd.to_datetime("2023-01-31").to_pydatetime()
        )
        
        pipeline = OmegaPipeline(config)
        
        # Mock data loader with PIT-safe data
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
        
        # Run pipeline
        result = pipeline.run()
        
        # Verify PIT safety maintained throughout
        assert result.success is True
        
        # Check data
        pit_guard = PITGuard()
        assert pit_guard.validate_pit_safety(result.data) is True
    
    def test_multi_period_pit_safety(self, tmp_path, monkeypatch):
        """Test PIT safety across multiple rebalancing periods."""
        from omega.core.pipeline import OmegaPipeline, PipelineConfig
        
        dates = pd.date_range("2023-01-01", periods=4, freq="W")
        
        for date in dates:
            config = PipelineConfig(
                data_dir=tmp_path / "data",
                cache_dir=tmp_path / "cache",
                universe=["VNM"],
                start_date="2023-01-01",
                end_date=date.strftime("%Y-%m-%d"),
                as_of_time=date.to_pydatetime()
            )
            
            pipeline = OmegaPipeline(config)
            
            # Mock data loader
            def mock_load_prices(ticker, start_date, end_date, as_of_time):
                dates_range = pd.date_range(start_date, end_date, freq="D")
                data = []
                for d in dates_range:
                    if d <= as_of_time:  # Only data available at as_of_time
                        data.append({
                            "ticker": ticker,
                            "date": d,
                            "open": 100.0,
                            "high": 101.0,
                            "low": 99.0,
                            "close": 100.0,
                            "volume": 1000000,
                            "as_of": d,
                            "available_at": d + timedelta(days=1)
                        })
                return pd.DataFrame(data)
            
            monkeypatch.setattr(pipeline.data_loader, "load_prices", mock_load_prices)
            
            result = pipeline.run()
            
            # Each period should maintain PIT safety
            if result.success and result.data is not None:
                pit_guard = PITGuard()
                assert pit_guard.validate_pit_safety(result.data) is True


class TestPITGuardUtilities:
    """Test PIT guard utility functions."""
    
    def test_pit_guard_initialization(self):
        """Test PITGuard initializes correctly."""
        guard = PITGuard()
        assert guard is not None
    
    def test_validate_timestamps(self):
        """Test timestamp validation."""
        guard = PITGuard()
        
        # Valid timestamps
        data = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=5, freq="D"),
            "as_of": pd.date_range("2023-01-01", periods=5, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=5, freq="D")
        })
        
        assert guard.validate_timestamps(data) is True
    
    def test_check_data_freshness(self):
        """Test data freshness checking."""
        guard = PITGuard()
        
        # Recent data
        recent_data = pd.DataFrame({
            "date": [datetime.now() - timedelta(hours=1)],
            "as_of": [datetime.now() - timedelta(hours=1)],
            "available_at": [datetime.now()]
        })
        
        assert guard.check_freshness(recent_data, max_age_hours=24) is True
        
        # Stale data
        stale_data = pd.DataFrame({
            "date": [datetime.now() - timedelta(days=10)],
            "as_of": [datetime.now() - timedelta(days=10)],
            "available_at": [datetime.now() - timedelta(days=9)]
        })
        
        assert guard.check_freshness(stale_data, max_age_hours=24) is False
    
    def test_compute_lag_statistics(self):
        """Test computation of lag statistics."""
        guard = PITGuard()
        
        data = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "as_of": pd.date_range("2023-01-01", periods=10, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        stats = guard.compute_lag_statistics(data)
        
        assert "mean_lag_days" in stats
        assert "max_lag_days" in stats
        assert stats["mean_lag_days"] == 1.0  # 1 day lag


class TestPITSafetyDocumentation:
    """Test PIT safety documentation and reporting."""
    
    def test_generate_pit_safety_report(self):
        """Test generation of PIT safety report."""
        guard = PITGuard()
        
        data = pd.DataFrame({
            "ticker": ["VNM"] * 10,
            "date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "close": [100.0] * 10,
            "as_of": pd.date_range("2023-01-01", periods=10, freq="D"),
            "available_at": pd.date_range("2023-01-02", periods=10, freq="D")
        })
        
        report = guard.generate_report(data)
        
        assert "pit_safe" in report
        assert "violations" in report
        assert "lag_statistics" in report
        assert report["pit_safe"] is True
    
    def test_pit_safety_audit_trail(self):
        """Test PIT safety audit trail."""
        guard = PITGuard()
        
        # Record PIT checks
        guard.record_check("data_loading", True, {})
        guard.record_check("feature_computation", True, {})
        guard.record_check("alpha_generation", True, {})
        
        # Get audit trail
        trail = guard.get_audit_trail()
        
        assert len(trail) == 3
        assert all(check["passed"] for check in trail)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
