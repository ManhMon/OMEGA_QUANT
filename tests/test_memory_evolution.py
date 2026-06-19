"""
Tests for Memory & Evolution - OMEGA_QUANT Phase 6 Migration
"""

import pytest
import pandas as pd
import numpy as np
import json
import os

from omega.observability.neural_memory import NeuralMemory
from omega.quant.evolution.evolution_engine import EvolutionEngine, EvolutionConfig

@pytest.fixture
def mock_audit_dir(tmp_path):
    audit_dir = tmp_path / "logs"
    audit_dir.mkdir()
    
    # Create mock audit log
    audit_data = {
        "findings": [
            {
                "id": "ERR-001",
                "title": "IndexError in Vectorization",
                "fix_description": "Use pandas merge instead of loop",
                "severity": "HIGH",
                "audit_date": "2026-05-10T10:00:00Z"
            }
        ]
    }
    
    with open(audit_dir / "audit_001.json", "w") as f:
        json.dump(audit_data, f)
        
    return str(audit_dir)

@pytest.fixture
def mock_res_file(tmp_path):
    return str(tmp_path / "resolutions.md")

class TestNeuralMemory:
    def test_initialization(self, mock_audit_dir, mock_res_file):
        memory = NeuralMemory(audit_logs_dir=mock_audit_dir, resolution_log_file=mock_res_file)
        
        assert os.path.exists(mock_res_file)
        assert len(memory.error_database) == 1
        assert memory.error_database[0]["error_id"] == "ERR-001"
        
    def test_suggest_fix(self, mock_audit_dir, mock_res_file):
        memory = NeuralMemory(audit_logs_dir=mock_audit_dir, resolution_log_file=mock_res_file)
        
        suggestions = memory.suggest_fix("Index out of bounds during pandas operation")
        
        assert len(suggestions) > 0
        assert suggestions[0]["error"] == "ERR-001"
        assert suggestions[0]["similarity"] > 0.0

@pytest.fixture
def mock_features():
    np.random.seed(42)
    return pd.DataFrame(np.random.randn(100, 5))

@pytest.fixture
def mock_labels():
    np.random.seed(43)
    return pd.Series(np.random.randn(100))

class TestEvolutionEngine:
    def test_generate_hypothesis(self, mock_features, mock_labels):
        engine = EvolutionEngine()
        
        hyp1 = engine.generate_hypothesis(mock_features, mock_labels, seed=1)
        hyp2 = engine.generate_hypothesis(mock_features, mock_labels, seed=1)
        hyp3 = engine.generate_hypothesis(mock_features, mock_labels, seed=2)
        
        # Determinism check
        assert np.array_equal(hyp1["weights"], hyp2["weights"])
        assert not np.array_equal(hyp1["weights"], hyp3["weights"])
        
        # Valid hypothesis
        assert "ic" in hyp1
        assert "signal" in hyp1
        
    def test_evolve(self, mock_features, mock_labels):
        engine = EvolutionEngine(EvolutionConfig(population_size=10))
        
        # Initial population
        pop = [engine.generate_hypothesis(mock_features, mock_labels, seed=i) for i in range(10)]
        
        # Evolve
        next_gen = engine.evolve(pop, mock_features, mock_labels)
        
        assert len(next_gen) == 10
        # Check elitism (best from prev gen should be in next gen)
        best_ic_prev = max(p["ic"] for p in pop)
        best_ic_next = max(p["ic"] for p in next_gen)
        assert best_ic_next >= best_ic_prev
        
    def test_leakage_guard(self, mock_features):
        engine = EvolutionEngine()
        
        # Perfect correlation (leakage)
        signal = mock_features[0]
        labels_leak = signal.copy()
        
        assert engine.check_leakage(signal, labels_leak) is True
        
        # Uncorrelated (safe)
        np.random.seed(44)
        labels_safe = pd.Series(np.random.randn(100))
        
        assert engine.check_leakage(signal, labels_safe) is False
