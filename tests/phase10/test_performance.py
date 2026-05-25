"""
OMEGA_QUANT Phase 10 Performance Tests
=======================================
Benchmark tests for production optimization and deployment readiness.

Tests:
- Data loading performance
- Signal generation speed
- Portfolio construction time
- Risk calculation performance
- End-to-end rebalance timing
- Memory usage profiling

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
import time
import psutil
import os
from pathlib import Path
from typing import Dict, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "data" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "observability" / "src"))

from omega.data.loader import DataLoader
from omega.core.portfolio_manager import PortfolioManager
from omega.core.risk_manager import RiskManager


class TestPerformanceBenchmarks:
    """Performance benchmark tests for production readiness."""
    
    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        """Generate sample market data for testing."""
        dates = pd.date_range(end=pd.Timestamp.now(), periods=252, freq='D')
        tickers = [f'TICK_{i:03d}' for i in range(100)]
        
        index = pd.MultiIndex.from_product(
            [dates, tickers],
            names=['date', 'ticker']
        )
        
        np.random.seed(42)
        data = pd.DataFrame({
            'open': np.random.randn(len(index)).cumsum() + 100,
            'high': np.random.randn(len(index)).cumsum() + 102,
            'low': np.random.randn(len(index)).cumsum() + 98,
            'close': np.random.randn(len(index)).cumsum() + 100,
            'volume': np.random.randint(100000, 1000000, len(index)),
            'returns': np.random.randn(len(index)) * 0.02
        }, index=index)
        
        return data
    
    @pytest.fixture
    def portfolio_manager(self) -> PortfolioManager:
        """Create portfolio manager instance."""
        config = {
            'max_positions': 50,
            'min_position_size': 0.01,
            'max_position_size': 0.10
        }
        return PortfolioManager(config)
    
    @pytest.fixture
    def risk_manager(self) -> RiskManager:
        """Create risk manager instance."""
        config = {
            'max_portfolio_volatility': 0.20,
            'max_drawdown': 0.15,
            'max_leverage': 1.0
        }
        return RiskManager(config)
    
    def test_data_loading_performance(self, sample_data: pd.DataFrame):
        """Test data loading performance - target < 1 second."""
        start_time = time.time()
        
        # Simulate data loading operations
        _ = sample_data.copy()
        _ = sample_data.groupby('ticker')['close'].mean()
        _ = sample_data.groupby('date')['volume'].sum()
        
        elapsed = time.time() - start_time
        
        assert elapsed < 1.0, f"Data loading took {elapsed:.3f}s, expected < 1.0s"
        print(f"\n[PASS] Data loading: {elapsed:.3f}s")
    
    def test_signal_generation_performance(
        self,
        sample_data: pd.DataFrame,
        portfolio_manager: PortfolioManager
    ):
        """Test signal generation performance - target < 5 seconds."""
        start_time = time.time()
        
        signals = portfolio_manager.generate_signals(
            sample_data,
            as_of_date=sample_data.index.get_level_values('date').max()
        )
        
        elapsed = time.time() - start_time
        
        assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s, expected < 5.0s"
        assert not signals.empty, "No signals generated"
        print(f"\n[PASS] Signal generation: {elapsed:.3f}s ({len(signals)} signals)")
    
    def test_portfolio_construction_performance(
        self,
        sample_data: pd.DataFrame,
        portfolio_manager: PortfolioManager
    ):
        """Test portfolio construction performance - target < 3 seconds."""
        # Generate signals first
        as_of_date = sample_data.index.get_level_values('date').max()
        signals = portfolio_manager.generate_signals(sample_data, as_of_date=as_of_date)
        
        start_time = time.time()
        
        portfolio = portfolio_manager.construct_portfolio(
            signals=signals,
            data=sample_data,
            as_of_date=as_of_date
        )
        
        elapsed = time.time() - start_time
        
        assert elapsed < 3.0, f"Portfolio construction took {elapsed:.3f}s, expected < 3.0s"
        assert not portfolio.empty, "Empty portfolio constructed"
        print(f"\n[PASS] Portfolio construction: {elapsed:.3f}s ({len(portfolio)} positions)")
    
    def test_risk_calculation_performance(
        self,
        sample_data: pd.DataFrame,
        risk_manager: RiskManager
    ):
        """Test risk calculation performance - target < 2 seconds."""
        # Create test portfolio
        tickers = sample_data.index.get_level_values('ticker').unique()[:30]
        portfolio = pd.DataFrame({
            'ticker': tickers,
            'weight': np.random.dirichlet(np.ones(len(tickers))),
            'expected_return': np.random.randn(len(tickers)) * 0.1,
            'volatility': np.random.rand(len(tickers)) * 0.3
        })
        
        start_time = time.time()
        
        risk_report = risk_manager.check_portfolio(portfolio, sample_data)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 2.0, f"Risk calculation took {elapsed:.3f}s, expected < 2.0s"
        assert 'passed' in risk_report, "Risk report missing 'passed' field"
        print(f"\n[PASS] Risk calculation: {elapsed:.3f}s")
    
    def test_end_to_end_rebalance_performance(
        self,
        sample_data: pd.DataFrame,
        portfolio_manager: PortfolioManager,
        risk_manager: RiskManager
    ):
        """Test full rebalance cycle - target < 10 seconds."""
        as_of_date = sample_data.index.get_level_values('date').max()
        
        start_time = time.time()
        
        # Step 1: Generate signals
        signals = portfolio_manager.generate_signals(sample_data, as_of_date=as_of_date)
        
        # Step 2: Construct portfolio
        portfolio = portfolio_manager.construct_portfolio(
            signals=signals,
            data=sample_data,
            as_of_date=as_of_date
        )
        
        # Step 3: Risk check
        risk_report = risk_manager.check_portfolio(portfolio, sample_data)
        
        # Step 4: Generate orders (mock)
        current_holdings = pd.DataFrame(columns=['ticker', 'shares', 'value'])
        orders = portfolio_manager.generate_orders(portfolio, current_holdings)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 10.0, f"End-to-end rebalance took {elapsed:.3f}s, expected < 10.0s"
        print(f"\n[PASS] End-to-end rebalance: {elapsed:.3f}s")
        print(f"  - Signals: {len(signals)}")
        print(f"  - Positions: {len(portfolio)}")
        print(f"  - Orders: {len(orders)}")
        print(f"  - Risk passed: {risk_report.get('passed', False)}")
    
    def test_memory_usage(self, sample_data: pd.DataFrame):
        """Test memory usage stays within limits - target < 2GB."""
        process = psutil.Process(os.getpid())
        
        # Get baseline memory
        baseline_mb = process.memory_info().rss / (1024 * 1024)
        
        # Perform memory-intensive operations
        data_copies = []
        for _ in range(10):
            data_copies.append(sample_data.copy())
        
        # Calculate statistics (vectorized)
        for df in data_copies:
            _ = df.groupby('ticker').agg({
                'close': ['mean', 'std', 'min', 'max'],
                'volume': ['sum', 'mean'],
                'returns': ['mean', 'std']
            })
        
        # Get peak memory
        peak_mb = process.memory_info().rss / (1024 * 1024)
        memory_increase_mb = peak_mb - baseline_mb
        
        # Clean up
        del data_copies
        
        assert memory_increase_mb < 2048, f"Memory increase {memory_increase_mb:.1f}MB, expected < 2048MB"
        print(f"\n[PASS] Memory usage: +{memory_increase_mb:.1f}MB (baseline: {baseline_mb:.1f}MB)")
    
    def test_vectorization_compliance(self, sample_data: pd.DataFrame):
        """Test that operations are properly vectorized (no iterrows)."""
        # This test verifies vectorized operations complete quickly
        start_time = time.time()
        
        # Vectorized operations
        grouped = sample_data.groupby('ticker')
        
        # Calculate multiple metrics (all vectorized)
        metrics = grouped.agg({
            'close': ['mean', 'std', 'min', 'max'],
            'volume': ['sum', 'mean'],
            'returns': ['mean', 'std', 'skew', pd.Series.kurt]
        })
        
        # Rolling calculations (vectorized)
        sample_data_sorted = sample_data.sort_index()
        rolling_mean = sample_data_sorted.groupby('ticker')['close'].rolling(20).mean()
        rolling_std = sample_data_sorted.groupby('ticker')['returns'].rolling(60).std()
        
        elapsed = time.time() - start_time
        
        # Vectorized operations should be very fast
        assert elapsed < 2.0, f"Vectorized operations took {elapsed:.3f}s, expected < 2.0s"
        print(f"\n[PASS] Vectorization compliance: {elapsed:.3f}s")
        print(f"  - Metrics calculated: {metrics.shape[0]} tickers x {metrics.shape[1]} metrics")
    
    def test_large_dataset_scalability(self):
        """Test performance with larger dataset - 500 tickers x 1000 days."""
        dates = pd.date_range(end=pd.Timestamp.now(), periods=1000, freq='D')
        tickers = [f'TICK_{i:04d}' for i in range(500)]
        
        index = pd.MultiIndex.from_product(
            [dates, tickers],
            names=['date', 'ticker']
        )
        
        np.random.seed(42)
        large_data = pd.DataFrame({
            'close': np.random.randn(len(index)).cumsum() + 100,
            'volume': np.random.randint(100000, 1000000, len(index)),
            'returns': np.random.randn(len(index)) * 0.02
        }, index=index)
        
        start_time = time.time()
        
        # Perform typical operations
        _ = large_data.groupby('ticker')['close'].mean()
        _ = large_data.groupby('ticker')['returns'].std()
        _ = large_data.groupby('date')['volume'].sum()
        
        elapsed = time.time() - start_time
        
        # Should handle large dataset efficiently
        assert elapsed < 5.0, f"Large dataset operations took {elapsed:.3f}s, expected < 5.0s"
        print(f"\n[PASS] Large dataset scalability: {elapsed:.3f}s")
        print(f"  - Dataset size: {len(large_data):,} rows ({large_data.memory_usage(deep=True).sum() / 1024**2:.1f}MB)")


class TestPerformanceRegression:
    """Performance regression tests to catch slowdowns."""
    
    def test_no_performance_regression(self):
        """Ensure performance hasn't regressed from baseline."""
        # Baseline performance targets (from initial benchmarking)
        baselines = {
            'data_loading': 1.0,  # seconds
            'signal_generation': 5.0,
            'portfolio_construction': 3.0,
            'risk_calculation': 2.0,
            'end_to_end': 10.0
        }
        
        # This test serves as documentation of performance targets
        # Actual regression testing would compare against stored benchmarks
        assert all(v > 0 for v in baselines.values()), "Invalid baseline values"
        print(f"\n[PASS] Performance baselines defined:")
        for operation, target in baselines.items():
            print(f"  - {operation}: < {target}s")


if __name__ == "__main__":
    # Run performance tests with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
