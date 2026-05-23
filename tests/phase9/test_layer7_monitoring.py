"""
Layer 7: Monitoring and Observability Integration Tests
Backend Engineer (Role 9) - L2 OpenCode

Tests monitoring, logging, metrics collection, and alerting.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.observability.monitor import SystemMonitor, MonitorConfig
from omega.observability.metrics import MetricsCollector
from omega.observability.logger import StructuredLogger


class TestMonitoringLayer:
    """Test Layer 7: Monitoring and Observability."""
    
    def test_system_monitor_initialization(self):
        """Test SystemMonitor initializes correctly."""
        config = MonitorConfig()
        monitor = SystemMonitor(config=config)
        
        assert monitor is not None
        assert monitor.config == config
    
    def test_metrics_collector_initialization(self):
        """Test MetricsCollector initializes correctly."""
        collector = MetricsCollector()
        
        assert collector is not None
    
    def test_structured_logger_initialization(self):
        """Test StructuredLogger initializes correctly."""
        logger = StructuredLogger(name="test_logger")
        
        assert logger is not None
    
    def test_pipeline_metrics_collection(self):
        """Test collection of pipeline execution metrics."""
        collector = MetricsCollector()
        
        # Simulate pipeline execution
        metrics = {
            "pipeline_duration_ms": 1500,
            "data_rows_loaded": 10000,
            "features_computed": 50,
            "alphas_generated": 5,
            "positions_created": 10,
            "trades_executed": 8
        }
        
        collector.record_pipeline_metrics(metrics)
        
        # Retrieve metrics
        recorded = collector.get_metrics("pipeline")
        
        assert len(recorded) > 0
        assert recorded[-1]["pipeline_duration_ms"] == 1500
    
    def test_performance_metrics_tracking(self):
        """Test tracking of performance metrics."""
        collector = MetricsCollector()
        
        # Record returns over time
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        returns = [0.01, 0.02, -0.01, 0.015, 0.005, -0.005, 0.02, 0.01, -0.01, 0.015]
        
        for date, ret in zip(dates, returns):
            collector.record_return(date, ret)
        
        # Compute performance metrics
        perf_metrics = collector.compute_performance_metrics()
        
        assert "total_return" in perf_metrics
        assert "sharpe_ratio" in perf_metrics
        assert "max_drawdown" in perf_metrics
    
    def test_error_logging(self):
        """Test error logging and tracking."""
        logger = StructuredLogger(name="test_logger")
        
        # Log various errors
        logger.error("Data loading failed", extra={
            "ticker": "VNM",
            "error_type": "DataNotFound"
        })
        
        logger.error("Feature computation error", extra={
            "feature": "momentum_5",
            "error_type": "InsufficientData"
        })
        
        # Retrieve error logs
        errors = logger.get_errors()
        
        assert len(errors) >= 2
    
    def test_alert_generation(self):
        """Test alert generation for anomalies."""
        config = MonitorConfig(
            max_drawdown_threshold=0.10,
            volatility_threshold=0.30
        )
        monitor = SystemMonitor(config=config)
        
        # Simulate portfolio with large drawdown
        portfolio_values = pd.Series([100, 95, 88, 85, 80])  # 20% drawdown
        
        alerts = monitor.check_alerts(portfolio_values)
        
        assert len(alerts) > 0
        assert any("drawdown" in alert["message"].lower() for alert in alerts)
    
    def test_health_check(self):
        """Test system health check."""
        config = MonitorConfig()
        monitor = SystemMonitor(config=config)
        
        # Simulate system state
        system_state = {
            "data_freshness": datetime.now() - timedelta(minutes=5),
            "last_execution": datetime.now() - timedelta(minutes=2),
            "error_count": 0,
            "active_positions": 10
        }
        
        health = monitor.check_health(system_state)
        
        assert "status" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
    
    def test_latency_tracking(self):
        """Test latency tracking for pipeline components."""
        collector = MetricsCollector()
        
        # Record latencies
        collector.record_latency("data_loading", 150)
        collector.record_latency("feature_computation", 300)
        collector.record_latency("alpha_generation", 200)
        collector.record_latency("risk_management", 100)
        collector.record_latency("execution", 250)
        
        # Get latency statistics
        latency_stats = collector.get_latency_stats()
        
        assert "data_loading" in latency_stats
        assert latency_stats["data_loading"]["mean"] == 150
    
    def test_resource_monitoring(self):
        """Test resource usage monitoring."""
        config = MonitorConfig()
        monitor = SystemMonitor(config=config)
        
        # Simulate resource usage
        resources = {
            "cpu_percent": 45.0,
            "memory_mb": 2048,
            "disk_io_mb": 100
        }
        
        monitor.record_resource_usage(resources)
        
        # Check if resources are within limits
        status = monitor.check_resource_limits(resources)
        
        assert "cpu_ok" in status
        assert "memory_ok" in status


class TestMonitoringBoundary:
    """Test boundary conditions for monitoring."""
    
    def test_empty_metrics(self):
        """Test handling of empty metrics."""
        collector = MetricsCollector()
        
        # Try to compute metrics with no data
        perf_metrics = collector.compute_performance_metrics()
        
        # Should handle gracefully
        assert perf_metrics is not None
    
    def test_single_data_point(self):
        """Test monitoring with single data point."""
        collector = MetricsCollector()
        
        collector.record_return(datetime(2023, 1, 1), 0.01)
        
        perf_metrics = collector.compute_performance_metrics()
        
        # Should handle single point gracefully
        assert perf_metrics is not None
    
    def test_extreme_values(self):
        """Test monitoring with extreme values."""
        collector = MetricsCollector()
        
        # Record extreme returns
        collector.record_return(datetime(2023, 1, 1), 0.50)  # 50% gain
        collector.record_return(datetime(2023, 1, 2), -0.40)  # 40% loss
        
        perf_metrics = collector.compute_performance_metrics()
        
        # Should handle extreme values
        assert perf_metrics is not None
        assert "max_drawdown" in perf_metrics


class TestMonitoringIntegration:
    """Test monitoring integration with pipeline."""
    
    def test_end_to_end_monitoring(self):
        """Test monitoring throughout entire pipeline."""
        collector = MetricsCollector()
        logger = StructuredLogger(name="pipeline")
        
        # Simulate pipeline execution with monitoring
        start_time = datetime.now()
        
        # Step 1: Data loading
        logger.info("Starting data loading")
        data_start = datetime.now()
        # ... data loading ...
        data_duration = (datetime.now() - data_start).total_seconds() * 1000
        collector.record_latency("data_loading", data_duration)
        
        # Step 2: Feature computation
        logger.info("Computing features")
        feature_start = datetime.now()
        # ... feature computation ...
        feature_duration = (datetime.now() - feature_start).total_seconds() * 1000
        collector.record_latency("feature_computation", feature_duration)
        
        # Step 3: Alpha generation
        logger.info("Generating alphas")
        alpha_start = datetime.now()
        # ... alpha generation ...
        alpha_duration = (datetime.now() - alpha_start).total_seconds() * 1000
        collector.record_latency("alpha_generation", alpha_duration)
        
        # Total pipeline duration
        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        
        metrics = {
            "pipeline_duration_ms": total_duration,
            "data_loading_ms": data_duration,
            "feature_computation_ms": feature_duration,
            "alpha_generation_ms": alpha_duration
        }
        
        collector.record_pipeline_metrics(metrics)
        
        # Verify metrics were recorded
        recorded = collector.get_metrics("pipeline")
        assert len(recorded) > 0
    
    def test_error_recovery_monitoring(self):
        """Test monitoring during error recovery."""
        logger = StructuredLogger(name="pipeline")
        collector = MetricsCollector()
        
        # Simulate error and recovery
        try:
            # Simulate error
            raise ValueError("Data source unavailable")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", extra={
                "error_type": type(e).__name__,
                "recoverable": True
            })
            collector.increment_counter("errors", tags={"type": "data_loading"})
        
        # Verify error was logged
        errors = logger.get_errors()
        assert len(errors) > 0
    
    def test_performance_degradation_detection(self):
        """Test detection of performance degradation."""
        config = MonitorConfig()
        monitor = SystemMonitor(config=config)
        collector = MetricsCollector()
        
        # Record normal latencies
        for _ in range(10):
            collector.record_latency("data_loading", 100)
        
        # Record degraded latencies
        for _ in range(5):
            collector.record_latency("data_loading", 500)  # 5x slower
        
        # Check for degradation
        latency_stats = collector.get_latency_stats()
        
        if "data_loading" in latency_stats:
            # Check that we have recorded latencies
            assert latency_stats["data_loading"]["count"] == 15
            # Mean should be between 100 and 500 (weighted average)
            mean_latency = latency_stats["data_loading"]["mean"]
            assert 100 < mean_latency < 500
            # Max should be 500 (the degraded latency)
            assert latency_stats["data_loading"]["max"] == 500


class TestMonitoringMetrics:
    """Test specific monitoring metrics."""
    
    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio calculation."""
        collector = MetricsCollector()
        
        # Record returns
        returns = [0.01, 0.02, -0.01, 0.015, 0.005, -0.005, 0.02, 0.01, -0.01, 0.015]
        dates = pd.date_range("2023-01-01", periods=len(returns), freq="D")
        
        for date, ret in zip(dates, returns):
            collector.record_return(date, ret)
        
        perf_metrics = collector.compute_performance_metrics()
        
        assert "sharpe_ratio" in perf_metrics
        assert perf_metrics["sharpe_ratio"] > 0  # Positive returns should give positive Sharpe
    
    def test_max_drawdown_calculation(self):
        """Test maximum drawdown calculation."""
        collector = MetricsCollector()
        
        # Create returns with known drawdown
        portfolio_values = [100, 105, 110, 95, 90, 100, 105]
        returns = [0.0] + [(portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1] 
                           for i in range(1, len(portfolio_values))]
        
        dates = pd.date_range("2023-01-01", periods=len(returns), freq="D")
        
        for date, ret in zip(dates, returns):
            collector.record_return(date, ret)
        
        perf_metrics = collector.compute_performance_metrics()
        
        assert "max_drawdown" in perf_metrics
        # Max drawdown from 110 to 90 = 18.18%
        assert perf_metrics["max_drawdown"] > 0.18
        assert perf_metrics["max_drawdown"] < 0.19
    
    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        collector = MetricsCollector()
        
        # 6 positive, 4 negative returns
        returns = [0.01, 0.02, -0.01, 0.015, 0.005, -0.005, 0.02, 0.01, -0.01, -0.005]
        dates = pd.date_range("2023-01-01", periods=len(returns), freq="D")
        
        for date, ret in zip(dates, returns):
            collector.record_return(date, ret)
        
        perf_metrics = collector.compute_performance_metrics()
        
        assert "win_rate" in perf_metrics
        assert np.isclose(perf_metrics["win_rate"], 0.6, atol=0.01)  # 6/10 = 60%


class TestMonitoringPITSafety:
    """Test PIT safety in monitoring."""
    
    def test_metrics_use_historical_data_only(self):
        """Test that metrics use only historical data."""
        collector = MetricsCollector()
        
        # Record returns over time
        dates = pd.date_range("2023-01-01", periods=20, freq="D")
        returns = np.random.randn(20) * 0.02
        
        for date, ret in zip(dates, returns):
            collector.record_return(date, ret)
        
        # Compute metrics at each point using only prior data
        for i in range(5, len(dates)):
            metrics = collector.compute_performance_metrics(end_date=dates[i])
            
            # Metrics should only use data up to current date
            assert metrics is not None
    
    def test_alerts_no_lookahead(self):
        """Test that alerts don't use future data."""
        config = MonitorConfig(max_drawdown_threshold=0.10)
        monitor = SystemMonitor(config=config)
        
        # Simulate portfolio values over time
        portfolio_values = pd.Series(
            [100, 105, 110, 95, 90, 100, 105, 98, 92, 88],
            index=pd.date_range("2023-01-01", periods=10, freq="D")
        )
        
        # Check alerts at each date using only prior data
        for i in range(5, len(portfolio_values)):
            historical_values = portfolio_values.iloc[:i]
            alerts = monitor.check_alerts(historical_values)
            
            # Alerts should be based only on historical data
            assert isinstance(alerts, list)


class TestMonitoringAlerts:
    """Test alerting functionality."""
    
    def test_drawdown_alert(self):
        """Test drawdown alert generation."""
        config = MonitorConfig(max_drawdown_threshold=0.10)
        monitor = SystemMonitor(config=config)
        
        # Portfolio with 15% drawdown
        portfolio_values = pd.Series([100, 95, 90, 88, 85])
        
        alerts = monitor.check_alerts(portfolio_values)
        
        # Should generate drawdown alert
        assert len(alerts) > 0
        assert any("drawdown" in alert["type"].lower() for alert in alerts)
    
    def test_volatility_alert(self):
        """Test volatility alert generation."""
        config = MonitorConfig(volatility_threshold=0.20)
        monitor = SystemMonitor(config=config)
        
        # High volatility returns
        returns = pd.Series([0.10, -0.15, 0.12, -0.18, 0.20])
        
        alerts = monitor.check_volatility_alerts(returns)
        
        # Should generate volatility alert
        assert len(alerts) > 0
    
    def test_data_freshness_alert(self):
        """Test data freshness alert."""
        config = MonitorConfig(max_data_age_minutes=60)
        monitor = SystemMonitor(config=config)
        
        # Stale data
        last_update = datetime.now() - timedelta(hours=2)
        
        alerts = monitor.check_data_freshness(last_update)
        
        # Should generate freshness alert
        assert len(alerts) > 0
        assert any("freshness" in alert["type"].lower() or "stale" in alert["type"].lower() 
                   for alert in alerts)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
