#!/usr/bin/env python3
"""
Integration Test: Evolution modules wiring into backtest pipeline.
Verifies all evolution modules import and run without crashing.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "quant" / "src"))

results = []

def test_step(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        results.append(False)

def test_genetic_engine():
    from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
    np.random.seed(42)
    features = {f"f{i}": np.random.randn(500) for i in range(5)}
    target = 0.5 * features["f0"] + np.random.randn(500) * 0.3
    config = GPConfig(population_size=20, generations=5, min_observations=100)
    engine = GeneticEngine(config)
    hof = engine.evolve(features, target)
    assert len(hof) > 0, "No individuals in hall of fame"

def test_fitness():
    from omega.quant.evolution.fitness import FitnessEvaluator
    evaluator = FitnessEvaluator()
    signals = pd.DataFrame({"a": np.random.randn(200), "b": np.random.randn(200)})
    returns = pd.Series(np.random.randn(200) * 0.01)
    result = evaluator.evaluate_batch(signals, returns)
    assert len(result) == 2, "Batch fitness should return 2 scores"

def test_continuous_learning():
    from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
    config = ContinuousLearningConfig(retraining_interval_days=7)
    engine = ContinuousLearningEngine(config)
    assert engine.should_retrain(pd.Timestamp("2026-01-08")) == True

def test_drift_detector():
    from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig
    config = DriftDetectorConfig(sharpe_drop_threshold=0.30)
    detector = DriftDetectorEnsemble(config)
    for i in range(5):
        detector.record_metrics(pd.Timestamp(f"2026-01-{i+1:02d}"), 1.5, 0.15, 0.12)
    result = detector.check_drift(0.5, 0.05, 0.30)
    assert "drift_detected" in result

def test_alpha_bridge():
    from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge
    bridge = AlphaToExecutionBridge()
    ok = bridge.register_alpha(
        alpha_id="test_alpha_1", formula="(f0 + f1)", horizon=5,
        train_end_date=pd.Timestamp("2026-01-01"), ic=0.12, sharpe=1.5
    )
    assert ok == True, "Alpha registration should succeed"

def test_all_imports():
    from omega.quant.evolution.rollback_handler import RollbackHandler
    from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager
    from omega.quant.evolution.sre_alerting_engine import SREAlertingEngine
    assert True

if __name__ == "__main__":
    print("="*60)
    print("EVOLUTION INTEGRATION TEST")
    print("="*60)
    test_step("Import all modules", test_all_imports)
    test_step("Genetic Engine (mini evolution)", test_genetic_engine)
    test_step("Fitness Evaluator (batch)", test_fitness)
    test_step("Continuous Learning Engine", test_continuous_learning)
    test_step("Drift Detector Ensemble", test_drift_detector)
    test_step("Alpha-to-Execution Bridge", test_alpha_bridge)
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} PASS")
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
