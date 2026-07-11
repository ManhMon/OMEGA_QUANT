"""
Tests for Genetic Programming Alpha Discovery - OMEGA_QUANT Phase 3.4
"""

import pandas as pd
import numpy as np
import pytest

from omega.quant.evolution.genetic_alpha import Node, Genome, enforce_t_minus_1_lag
from omega.quant.evolution.fitness import FitnessEvaluator
from omega.quant.evolution.genetic_engine import GPIndividual, GPNode, GPConfig
from scripts.run_weekly_evolution import _convert_diverse_node


@pytest.fixture
def mock_df():
    """Mock OHLCV and indicator dataframe."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100)
    return pd.DataFrame({
        'close': np.cumsum(np.random.randn(100)) + 100,
        'open': np.cumsum(np.random.randn(100)) + 100,
        'high': np.cumsum(np.random.randn(100)) + 105,
        'low': np.cumsum(np.random.randn(100)) + 95,
        'volume': np.random.randint(1000, 10000, 100),
        'rsi': np.random.uniform(0, 100, 100),
        'macd': np.random.randn(100),
    }, index=dates)


def test_new_primitives(mock_df):
    """Test newly added primitives: open, high, low, returns."""
    for prim in ['open', 'high', 'low', 'returns']:
        node = Node(prim)
        res = node.evaluate(mock_df)
        assert len(res) == 100
        assert not res.isna().all()


def test_new_functions(mock_df):
    """Test newly added unary functions: std, mean, max, min, rank, delay."""
    child = Node('close')
    for func in ['std', 'mean', 'max', 'min', 'rank', 'delay']:
        node = Node(func, [child])
        res = node.evaluate(mock_df, window=14)
        assert len(res) == 100


def test_fitness_complexity_penalty(mock_df):
    """Test tree depth complexity penalty in fitness evaluator."""
    evaluator = FitnessEvaluator(complexity_weight=0.01)
    
    # Mock identical signal and returns
    signal = mock_df['close'].diff()
    forward_returns = mock_df['close'].pct_change().shift(-1)
    
    # Evaluate with depth=0 vs depth=5
    fitness_shallow = evaluator.evaluate(signal, forward_returns, tree_depth=0)
    fitness_deep = evaluator.evaluate(signal, forward_returns, tree_depth=5)
    
    # Deep tree should have exactly 0.05 lower fitness (0.01 * 5)
    assert np.isclose(fitness_shallow - fitness_deep, 0.05)


def test_gp_engine_integrity():
    """Test crossover and mutation produce valid trees."""
    g1 = Genome(max_depth=3, seed=1)
    g2 = Genome(max_depth=3, seed=2)
    
    # Crossover
    g_child = Genome.crossover(g1, g2)
    assert isinstance(g_child.tree, Node)
    
    # Mutation
    g_mutated = g1.mutate()
    assert isinstance(g_mutated.tree, Node)


def test_pit_genome(mock_df):
    """Test PIT safety (T-1 lag)."""
    g = Genome(max_depth=2, seed=1)
    signal = g.evaluate_vectorized(mock_df)
    
    # After shift(1) + fillna(0.0), first row must be 0.0
    assert signal.iloc[0] == 0.0
    assert len(signal) == 100


def test_fitness_monotonicity():
    """Test higher sharpe = higher fitness."""
    evaluator = FitnessEvaluator()
    
    # Strategy 1: High Sharpe, Low Turnover
    sig1 = pd.Series([1, 1, 1, 1, 1])
    ret1 = pd.Series([0.01, 0.01, 0.01, 0.01, 0.01])
    fit1 = evaluator.evaluate(sig1, ret1)
    
    # Strategy 2: Low Sharpe, High Turnover
    sig2 = pd.Series([1, -1, 1, -1, 1])
    ret2 = pd.Series([-0.01, 0.01, -0.01, 0.01, -0.01])
    fit2 = evaluator.evaluate(sig2, ret2)
    
    assert fit1 > fit2


def test_performance_benchmark(mock_df):
    """Test evaluation performance."""
    import time
    start = time.time()
    
    # Evaluate 100 genomes
    for i in range(100):
        g = Genome(max_depth=3, seed=i)
        _ = g.evaluate_vectorized(mock_df)
        
    duration = time.time() - start
    # Should take < 2 seconds for 100 genomes
    assert duration < 2.0


def test_interleaved_ticker_rolling():
    features = {
        "close": np.array([1.0, 10.0, 2.0, 20.0, 3.0, 30.0]),
        "__ticker__": np.array(["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"], dtype=object),
        "__date__": pd.to_datetime([
            "2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"
        ]).to_numpy(),
    }
    tree = GPNode(
        operator="ts_mean",
        children=[
            GPNode(operator="terminal", value="close"),
            GPNode(operator="terminal", value="2"),
        ],
    )

    values = GPIndividual(tree=tree)._execute_tree(tree, features)
    np.testing.assert_allclose(values, np.array([0.0, 0.0, 1.5, 15.0, 2.5, 25.0]))


def test_converted_delay_tree():
    class LegacyNode:
        def __init__(self, value, children=None):
            self.value = value
            self.children = children or []

    converted = _convert_diverse_node(LegacyNode("delay", [LegacyNode("close")]))
    assert converted.operator == "ts_delay"
    assert converted.children[1].value == "1"

    features = {
        "close": np.array([1.0, 2.0, 3.0]),
        "__ticker__": np.array(["AAA", "AAA", "AAA"], dtype=object),
        "__date__": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]).to_numpy(),
    }
    values = GPIndividual(tree=converted)._execute_tree(converted, features)
    np.testing.assert_allclose(values, np.array([0.0, 1.0, 2.0]))


def test_multi_horizon_time_fold_ir_weighted_scoring():
    alpha = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    target_h3 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    target_h5 = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    features = {
        "target_h3": target_h3,
        "target_h5": target_h5,
        "__date__": pd.to_datetime([
            "2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01",
            "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
        ]).to_numpy(),
    }
    config = GPConfig(
        use_time_fold_ir=True,
        time_folds=2,
        fold_ir_std_floor=0.01,
        multi_target_horizons=[3, 5],
        multi_target_weights=[0.75, 0.25],
    )
    individual = GPIndividual(tree=GPNode(operator="terminal", value="close"))

    score = individual._compute_combined_ic(alpha, target_h3, features, config)
    assert score > 0.45
