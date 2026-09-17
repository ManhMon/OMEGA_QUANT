"""
Unit Tests for OMEGA_QUANT Genetic Engine
Phase 3.3: Alpha Discovery - Genetic Programming

100% Vectorized | PIT-Safe | Institutional Grade
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.evolution.genetic_engine import (
    GeneticEngine,
    GPConfig,
    GPNode,
    GPIndividual,
    _neutralize_cross_section,
)
from scipy.stats import spearmanr


@pytest.fixture
def sample_data():
    """Create sample features and target."""
    np.random.seed(42)
    n_samples = 1000
    features = {
        'f1': np.random.randn(n_samples),
        'f2': np.random.randn(n_samples)
    }
    # Target correlated with f1
    target = 0.5 * features['f1'] + np.random.randn(n_samples) * 0.5
    return features, target


def test_gp_node_depth():
    """Test tree depth calculation."""
    # Terminal node
    root = GPNode(operator='terminal', value='f1')
    assert root.depth() == 1
    
    # Unary
    root = GPNode(operator='abs', children=[root])
    assert root.depth() == 2
    
    # Binary
    left = GPNode(operator='terminal', value='f1')
    right = GPNode(operator='terminal', value='f2')
    root = GPNode(operator='+', children=[left, right])
    assert root.depth() == 2


def test_gp_node_to_string():
    """Test tree string representation."""
    left = GPNode(operator='terminal', value='f1')
    right = GPNode(operator='terminal', value='f2')
    root = GPNode(operator='+', children=[left, right])
    assert root.to_string() == "(f1 + f2)"


def test_genetic_engine_initialization():
    """Test engine and population init."""
    config = GPConfig(population_size=10)
    engine = GeneticEngine(config)
    engine.feature_names = ['f1', 'f2']
    
    engine.initialize_population()
    assert len(engine.population) == 10
    assert isinstance(engine.population[0], GPIndividual)


def test_genetic_engine_evolution(sample_data):
    """Test full evolution cycle (short run)."""
    features, target = sample_data
    config = GPConfig(
        population_size=20,
        generations=2,
        min_observations=100,
        n_jobs=1,  # TEST-01 FIX: single-threaded to avoid Windows joblib/multiprocessing ACL
    )
    engine = GeneticEngine(config)
    
    hof = engine.evolve(features, target)
    
    assert len(hof) > 0
    assert hof[0].ic_score > 0
    assert len(engine.history) == 2


def test_gp_individual_evaluate(sample_data):
    """Test fitness evaluation."""
    features, target = sample_data
    config = GPConfig(min_observations=100)
    
    # Simple alpha: f1 (highly correlated with target)
    tree = GPNode(operator='terminal', value='f1')
    ind = GPIndividual(tree=tree)
    
    ind.evaluate(features, target, [], config)
    
    assert ind.ic_score > 0.4
    assert ind.fitness > 0
    assert ind.turnover_rate >= 0


def test_gp_constant_terminal_and_ts_operators(sample_data):
    """Test GPNode execution with constant terminals and time-series operators."""
    features, target = sample_data
    # Construct tree: ts_std(f1, 10)
    # The constant terminal is represented as a node with children=[] and value='10'
    left = GPNode(operator='terminal', value='f1')
    right = GPNode(operator='terminal', value='10')
    root = GPNode(operator='ts_std', children=[left, right])
    
    ind = GPIndividual(tree=root)
    
    # Execute tree
    res = ind._execute_tree(root, features)
    
    # If the constant terminal worked, window size should be 10, and it shouldn't be all zeros
    assert not np.all(res == 0.0)
    assert len(res) == len(features['f1'])

def test_genetic_engine_breeds_between_generations(sample_data):
    """Evolution should create offspring after each non-final generation."""
    features, target = sample_data
    config = GPConfig(
        population_size=12,
        generations=3,
        min_observations=100,
        early_stopping_rounds=0,
        n_jobs=1,
    )
    engine = GeneticEngine(config)
    calls = 0
    original_next_generation = engine._next_generation

    def counted_next_generation():
        nonlocal calls
        calls += 1
        original_next_generation()

    engine._next_generation = counted_next_generation
    engine.evolve(features, target)

    assert calls == 2

def test_tree_size_penalty_rewards_parsimony(sample_data):
    """Equivalent larger trees should score lower."""
    features, target = sample_data
    config = GPConfig(min_observations=100, tree_size_penalty_weight=0.01)
    simple = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    bloated = GPIndividual(tree=GPNode(
        operator='+',
        children=[
            GPNode(operator='terminal', value='f1'),
            GPNode(operator='terminal', value='0'),
        ],
    ))

    simple.evaluate(features, target, [], config)
    bloated.evaluate(features, target, [], config)

    assert bloated.complexity_penalty > simple.complexity_penalty
    assert bloated.fitness < simple.fitness


def test_time_fold_ir_stable_alpha_beats_spike():
    dates = np.repeat(np.arange(90), 3)
    target = np.tile(np.array([0.0, 1.0, -1.0]), 90)
    stable_alpha = np.tile(np.array([0.1, 0.9, -1.1]), 90)
    spike_alpha = np.tile(np.array([1.0, 0.0, -1.0]), 90)
    spike_alpha[30 * 3:] = np.tile(np.array([0.0, -1.0, 1.0]), 60)
    features = {
        'stable_alpha': stable_alpha,
        'spike_alpha': spike_alpha,
        '__date__': dates,
        '__log_market_cap__': np.tile(np.array([1.0, 2.0, 3.0]), 90),
    }
    config = GPConfig(
        min_observations=10,
        use_time_fold_ir=True,
        time_folds=3,
        fold_ir_std_floor=0.01,
        neutralize_size_sector=True,
    )

    stable = GPIndividual(tree=GPNode(operator='terminal', value='stable_alpha'))
    spike = GPIndividual(tree=GPNode(operator='terminal', value='spike_alpha'))

    stable.evaluate(features, target, [], config)
    spike.evaluate(features, target, [], config)

    assert stable.ic_score > spike.ic_score


def test_sector_neutralization_removes_sector_effect():
    dates = np.repeat(np.arange(30), 6)
    sectors = np.tile(np.array([0, 0, 1, 1, 2, 2]), 30)
    alpha = sectors.astype(float)
    target = sectors.astype(float)
    log_mcap = np.tile(np.array([1.0, 1.2, 2.0, 2.2, 3.0, 3.2]), 30)

    neutralized = _neutralize_cross_section(alpha, log_mcap, sectors, dates)
    ic, _ = spearmanr(neutralized, target)

    assert np.isfinite(neutralized).all()
    assert abs(0.0 if np.isnan(ic) else float(ic)) < 1e-6
