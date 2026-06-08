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
    GPIndividual
)


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
        min_observations=100
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

