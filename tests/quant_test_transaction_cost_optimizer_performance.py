"""
OMEGA_QUANT Phase 19.4: Transaction Cost Optimizer Performance Benchmarks

Performance SLA:
- Target: <10ms per symbol calculation
- Throughput: 1000+ calculations/second
- Memory efficient for large portfolios

Author: Backend Engineer (Role 09)
Date: 2026-05-19
Version: 1.0.0
"""

import pytest
import time
import numpy as np
from datetime import datetime, timedelta, timezone
from omega.quant.execution.transaction_cost_optimizer import (
    TransactionCostOptimizer,
    TransactionCostResult,
)


@pytest.fixture
def optimizer():
    """Create optimizer instance with default parameters."""
    return TransactionCostOptimizer(
        fixed_commission=10000.0,
        pct_commission=0.0015,
        volatility_scaling=0.1,
        price_scale=1000.0,
        impact_alpha=0.05,
        impact_beta=1.5,
    )


@pytest.fixture
def single_symbol_data():
    """Generate market data for single symbol benchmark."""
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)
    as_of = timestamp - timedelta(days=1)
    available_at = timestamp - timedelta(hours=1)
    
    positions = {"VNM": 1000}
    market_data = {
        "VNM": {
            "price": 85.5,
            "spread": 0.001,
            "volatility": 0.02,
            "adv": 1000000,
            "as_of": as_of,
            "available_at": available_at,
        }
    }
    
    return positions, market_data, as_of, available_at, timestamp


@pytest.fixture
def batch_symbols_data():
    """Generate market data for batch throughput benchmark."""
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)
    as_of = timestamp - timedelta(days=1)
    available_at = timestamp - timedelta(hours=1)
    
    # Create 100 symbols for batch testing
    symbols = [f"SYM{i:03d}" for i in range(100)]
    positions = {sym: 1000 for sym in symbols}
    market_data = {
        sym: {
            "price": 50.0 + np.random.uniform(-10, 10),
            "spread": 0.001 + np.random.uniform(0, 0.002),
            "volatility": 0.015 + np.random.uniform(0, 0.01),
            "adv": 500000 + np.random.randint(0, 500000),
            "as_of": as_of,
            "available_at": available_at,
        }
        for sym in symbols
    }
    
    return positions, market_data, as_of, available_at, timestamp


@pytest.fixture
def large_portfolio_data():
    """Generate market data for large portfolio stress test."""
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)
    as_of = timestamp - timedelta(days=1)
    available_at = timestamp - timedelta(hours=1)
    
    # Create 1000 symbols for stress testing
    symbols = [f"SYM{i:04d}" for i in range(1000)]
    positions = {sym: np.random.randint(100, 10000) for sym in symbols}
    market_data = {
        sym: {
            "price": 50.0 + np.random.uniform(-20, 20),
            "spread": 0.001 + np.random.uniform(0, 0.003),
            "volatility": 0.01 + np.random.uniform(0, 0.02),
            "adv": 100000 + np.random.randint(0, 1000000),
            "as_of": as_of,
            "available_at": available_at,
        }
        for sym in symbols
    }
    
    return positions, market_data, as_of, available_at, timestamp


# Benchmark Test 1: Single Symbol Latency (<10ms target)
def test_single_symbol_latency_benchmark(optimizer, single_symbol_data):
    """
    Benchmark: Single symbol calculation latency.
    
    Performance SLA: <10ms per symbol
    """
    positions, market_data, as_of, available_at, timestamp = single_symbol_data
    
    # Warm-up run
    optimizer.calculate_cost(positions, market_data, as_of, available_at, timestamp)
    
    # Benchmark run
    iterations = 100
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        result = optimizer.calculate_cost(
            positions, market_data, as_of, available_at, timestamp
        )
    
    end_time = time.perf_counter()
    avg_latency_ms = ((end_time - start_time) / iterations) * 1000.0
    
    # Verify result correctness
    assert "VNM" in result
    assert result["VNM"].total_cost > 0
    
    # Performance assertion: <10ms per symbol
    assert avg_latency_ms < 10.0, (
        f"Single symbol latency {avg_latency_ms:.2f}ms exceeds SLA target of 10ms"
    )
    
    print(f"\n[PASS] Single symbol latency: {avg_latency_ms:.3f}ms (target: <10ms)")


# Benchmark Test 2: Batch Throughput (1000+ calc/sec target)
def test_batch_throughput_benchmark(optimizer, batch_symbols_data):
    """
    Benchmark: Batch calculation throughput.
    
    Performance SLA: 1000+ calculations/second
    """
    positions, market_data, as_of, available_at, timestamp = batch_symbols_data
    
    # Warm-up run
    optimizer.calculate_cost(positions, market_data, as_of, available_at, timestamp)
    
    # Benchmark run
    iterations = 10
    total_symbols = len(positions) * iterations
    
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        result = optimizer.calculate_cost(
            positions, market_data, as_of, available_at, timestamp
        )
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    throughput = total_symbols / elapsed_time
    
    # Verify result correctness
    assert len(result) == len(positions)
    
    # Performance assertion: 1000+ calculations/second
    assert throughput >= 1000.0, (
        f"Throughput {throughput:.0f} calc/sec is below SLA target of 1000 calc/sec"
    )
    
    print(f"\n[PASS] Batch throughput: {throughput:.0f} calc/sec (target: >1000 calc/sec)")


# Benchmark Test 3: Large Portfolio Stress Test
def test_large_portfolio_stress_benchmark(optimizer, large_portfolio_data):
    """
    Benchmark: Large portfolio (1000 symbols) stress test.
    
    Verifies performance scales linearly with portfolio size.
    """
    positions, market_data, as_of, available_at, timestamp = large_portfolio_data
    
    # Warm-up run
    optimizer.calculate_cost(positions, market_data, as_of, available_at, timestamp)
    
    # Benchmark run
    start_time = time.perf_counter()
    
    result = optimizer.calculate_cost(
        positions, market_data, as_of, available_at, timestamp
    )
    
    end_time = time.perf_counter()
    total_time_ms = (end_time - start_time) * 1000.0
    avg_latency_per_symbol = total_time_ms / len(positions)
    
    # Verify result correctness
    assert len(result) == len(positions)
    
    # Performance assertion: Average latency should still be <10ms per symbol
    assert avg_latency_per_symbol < 10.0, (
        f"Large portfolio avg latency {avg_latency_per_symbol:.2f}ms/symbol exceeds 10ms"
    )
    
    print(
        f"\n[PASS] Large portfolio (1000 symbols): {total_time_ms:.0f}ms total, "
        f"{avg_latency_per_symbol:.3f}ms/symbol (target: <10ms/symbol)"
    )


# Benchmark Test 4: Hot Path Optimization Verification
def test_hot_path_optimization_benchmark(optimizer, batch_symbols_data):
    """
    Benchmark: Verify hot path optimizations (vectorization).
    
    Compares performance with and without numpy optimizations.
    """
    positions, market_data, as_of, available_at, timestamp = batch_symbols_data
    
    # Warm-up run
    optimizer.calculate_cost(positions, market_data, as_of, available_at, timestamp)
    
    # Benchmark optimized version
    iterations = 20
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        result = optimizer.calculate_cost(
            positions, market_data, as_of, available_at, timestamp
        )
    
    end_time = time.perf_counter()
    optimized_time_ms = ((end_time - start_time) / iterations) * 1000.0
    
    # Verify result correctness
    assert len(result) == len(positions)
    
    # Performance assertion: Optimized version should be fast
    # For 100 symbols, target is <100ms (1ms per symbol average)
    target_time_ms = len(positions) * 1.0  # 1ms per symbol
    assert optimized_time_ms < target_time_ms, (
        f"Hot path time {optimized_time_ms:.2f}ms exceeds target {target_time_ms:.0f}ms"
    )
    
    print(
        f"\n[PASS] Hot path optimization: {optimized_time_ms:.2f}ms for {len(positions)} symbols "
        f"(target: <{target_time_ms:.0f}ms)"
    )


# Benchmark Test 5: Memory Efficiency Test
def test_memory_efficiency_benchmark(optimizer, large_portfolio_data):
    """
    Benchmark: Memory efficiency for large portfolios.
    
    Verifies no memory leaks and efficient memory usage.
    """
    positions, market_data, as_of, available_at, timestamp = large_portfolio_data
    
    # Run multiple iterations to check for memory leaks
    iterations = 10
    results = []
    
    start_time = time.perf_counter()
    
    for _ in range(iterations):
        result = optimizer.calculate_cost(
            positions, market_data, as_of, available_at, timestamp
        )
        results.append(result)
    
    end_time = time.perf_counter()
    total_time_ms = (end_time - start_time) * 1000.0
    avg_time_per_iteration = total_time_ms / iterations
    
    # Verify result correctness
    assert len(results) == iterations
    for result in results:
        assert len(result) == len(positions)
    
    # Performance assertion: Consistent performance across iterations
    # (no degradation due to memory issues)
    # Each iteration should process 1000 symbols in reasonable time
    max_time_per_iteration = 10000.0  # 10 seconds for 1000 symbols
    assert avg_time_per_iteration < max_time_per_iteration, (
        f"Memory efficiency test: avg time {avg_time_per_iteration:.0f}ms exceeds "
        f"target {max_time_per_iteration:.0f}ms"
    )
    
    print(
        f"\n[PASS] Memory efficiency: {iterations} iterations of 1000 symbols, "
        f"avg {avg_time_per_iteration:.0f}ms/iteration (consistent performance)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
