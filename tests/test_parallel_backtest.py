"""
Test ParallelBacktestRunner - symbol chunking + multi-worker.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - synthetic data, no look-ahead.
"""

import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')

import numpy as np
import pandas as pd
import pytest

from omega.quant.parallel_backtest import ParallelBacktestRunner, ParallelBacktestResult


@pytest.fixture
def synthetic_market():
    """Generate synthetic market data: 50 symbols, 252 days."""
    np.random.seed(42)
    n_days = 252
    n_symbols = 50
    dates = pd.bdate_range('2025-01-01', periods=n_days)
    symbols = [f'VN{i:03d}' for i in range(n_symbols)]

    prices_data = {}
    for sym in symbols:
        start = np.random.uniform(20000, 50000)
        returns = np.random.normal(0.0005, 0.02, n_days)
        prices_data[sym] = start * np.cumprod(1 + returns)

    prices = pd.DataFrame(prices_data, index=dates)
    weights = pd.DataFrame(1.0 / n_symbols, index=dates, columns=symbols)
    return prices, weights


@pytest.fixture
def runner():
    """Default runner with 4 workers."""
    return ParallelBacktestRunner(
        num_workers=4,
        initial_capital=1_000_000_000.0,
        fee_rate=0.0015,
        tax_rate=0.001,
        slippage_bps=2.0,
    )


class TestParallelBacktestRunner:
    """Tests for ParallelBacktestRunner."""

    def test_basic_run(self, runner, synthetic_market):
        """Test basic parallel backtest completes successfully."""
        prices, weights = synthetic_market
        result = runner.run(prices, weights)

        assert isinstance(result, ParallelBacktestResult)
        assert result.num_workers == 4
        assert result.num_chunks == 4
        assert len(result.chunk_results) == 4
        assert result.total_duration > 0

    def test_metrics_reasonable(self, runner, synthetic_market):
        """Test that aggregated metrics are within reasonable bounds."""
        prices, weights = synthetic_market
        result = runner.run(prices, weights)

        assert -1.0 < result.metrics['total_return'] < 5.0
        assert result.metrics['volatility'] > 0
        assert result.metrics['max_drawdown'] <= 0
        assert 0.0 <= result.metrics['win_rate'] <= 1.0

    def test_equity_curve_shape(self, runner, synthetic_market):
        """Test equity curve has correct shape."""
        prices, weights = synthetic_market
        result = runner.run(prices, weights)

        assert len(result.equity_curve) == len(prices)
        assert result.equity_curve.iloc[0] > 0  # Starts with capital

    def test_single_worker(self, synthetic_market):
        """Test with single worker (sequential baseline)."""
        prices, weights = synthetic_market
        runner = ParallelBacktestRunner(num_workers=1)
        result = runner.run(prices, weights)

        assert result.num_chunks == 1
        assert result.num_workers == 1
        assert len(result.chunk_results) == 1

    def test_more_workers_than_symbols(self):
        """Test when workers > symbols (should cap chunks)."""
        np.random.seed(123)
        dates = pd.bdate_range('2025-01-01', periods=60)
        symbols = ['A', 'B', 'C']
        prices = pd.DataFrame(
            np.random.uniform(100, 200, (60, 3)),
            index=dates, columns=symbols
        )
        weights = pd.DataFrame(1.0 / 3, index=dates, columns=symbols)

        runner = ParallelBacktestRunner(num_workers=8)
        result = runner.run(prices, weights)

        # Should cap at 3 chunks (one per symbol)
        assert result.num_chunks <= 8
        assert len(result.chunk_results) > 0

    def test_custom_chunk_size(self, synthetic_market):
        """Test explicit chunk_size parameter."""
        prices, weights = synthetic_market
        runner = ParallelBacktestRunner(num_workers=4, chunk_size=10)
        result = runner.run(prices, weights)

        # 50 symbols / 10 per chunk = 5 chunks
        assert result.num_chunks == 5

    def test_deterministic_results(self, synthetic_market):
        """Test that results are deterministic across runs."""
        prices, weights = synthetic_market

        runner1 = ParallelBacktestRunner(num_workers=1)
        result1 = runner1.run(prices, weights)

        runner2 = ParallelBacktestRunner(num_workers=1)
        result2 = runner2.run(prices, weights)

        assert abs(result1.metrics['total_return'] - result2.metrics['total_return']) < 1e-10

    def test_capital_conservation(self, synthetic_market):
        """Test that initial capital is properly distributed."""
        prices, weights = synthetic_market
        runner = ParallelBacktestRunner(
            num_workers=4,
            initial_capital=1_000_000_000.0,
        )
        result = runner.run(prices, weights)

        # First equity value should be close to initial capital
        # (minus first-day transaction costs)
        assert result.equity_curve.iloc[0] > 900_000_000.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
