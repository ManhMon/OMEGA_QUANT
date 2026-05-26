#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 6.1 Continuous Learning - Live Execution Script
Runs champion/challenger comparison + drift detection
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

# Add packages to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "packages" / "quant" / "src"))

from omega.quant.evolution.continuous_learning import ContinuousLearningEngine, ContinuousLearningConfig
from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig

def load_sample_data():
    """Load sample market data for testing."""
    np.random.seed(42)
    dates = pd.date_range('2026-01-01', periods=252, freq='D')
    
    # Simulate 10 stocks
    n_stocks = 10
    n_days = len(dates)
    
    data = {}
    for i in range(n_stocks):
        returns = np.random.randn(n_days) * 0.02
        data[f'STOCK_{i}'] = returns
    
    df = pd.DataFrame(data, index=dates)
    return df

def run_continuous_learning():
    """Execute Phase 6.1 continuous learning cycle."""
    
    print("=" * 70)
    print("OMEGA Phase 6.1 - Continuous Learning Engine")
    print("=" * 70)
    
    # Load data
    print("\n[1/5] Loading market data...")
    df = load_sample_data()
    print(f"  [OK] Loaded {df.shape[0]} days x {df.shape[1]} stocks")
    
    # Initialize engines
    print("\n[2/5] Initializing engines...")
    learning_config = ContinuousLearningConfig(
        retraining_interval_days=7,
        min_ic_improvement=0.05,
        min_absolute_ic=0.10,
        sharpe_tolerance=0.95
    )
    learning_engine = ContinuousLearningEngine(learning_config)
    
    drift_config = DriftDetectorConfig(
        sharpe_drop_threshold=0.30,
        ic_drop_threshold=0.20,
        turnover_spike_threshold=0.50,
        lookback_window_days=30
    )
    drift_detector = DriftDetectorEnsemble(drift_config)
    print("  [OK] Continuous Learning Engine initialized")
    print("  [OK] Drift Detector Ensemble initialized")
    
    # Simulate retraining cycles
    print("\n[3/5] Running retraining cycles...")
    results = []
    
    for cycle in range(1, 6):
        current_date = pd.Timestamp('2026-01-01') + timedelta(days=cycle*7)
        
        # Prepare training data
        train_data = df.iloc[:cycle*50]
        train_labels = (df.iloc[:cycle*50].mean(axis=1) > 0).astype(int)
        
        # Run retraining
        retrain_result = learning_engine.retrain_cycle(train_data, train_labels, current_date)
        
        # Simulate metrics
        if learning_engine.champion_model:
            champion_ic = learning_engine.champion_model.get('ic', 0.0)
            champion_sharpe = learning_engine.champion_model.get('sharpe', 0.0)
        else:
            champion_ic = 0.0
            champion_sharpe = 0.0
        
        # Add some noise to simulate real drift
        current_ic = champion_ic + np.random.randn() * 0.02
        current_sharpe = champion_sharpe + np.random.randn() * 0.1
        current_turnover = 0.15 + np.random.randn() * 0.05
        
        # Record metrics for drift detection
        drift_detector.record_metrics(current_date, current_sharpe, current_ic, current_turnover)
        
        # Check for drift
        drift_result = drift_detector.check_drift(current_sharpe, current_ic, current_turnover)
        
        result = {
            "cycle": cycle,
            "date": current_date.isoformat(),
            "retrain_status": retrain_result.get("status"),
            "retrain_reason": retrain_result.get("reason"),
            "champion_ic": float(champion_ic),
            "current_ic": float(current_ic),
            "current_sharpe": float(current_sharpe),
            "current_turnover": float(current_turnover),
            "drift_detected": drift_result["drift_detected"],
            "drift_detectors": drift_result["detectors_triggered"]
        }
        results.append(result)
        
        print(f"\n  Cycle {cycle}:")
        print(f"    Retrain: {retrain_result.get('status')} ({retrain_result.get('reason')})")
        print(f"    IC: {current_ic:.4f} (champion: {champion_ic:.4f})")
        print(f"    Sharpe: {current_sharpe:.4f}")
        print(f"    Drift: {'[DRIFT] DETECTED' if drift_result['drift_detected'] else '[OK] No drift'}")
        if drift_result["detectors_triggered"]:
            print(f"    Triggers: {', '.join(drift_result['detectors_triggered'])}")
    
    # Save results
    print("\n[4/5] Saving results...")
    results_path = repo_root / ".ly_state" / "session" / "phase6_continuous_learning_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"  [OK] Results saved to {results_path}")
    
    # Summary
    print("\n[5/5] Summary")
    print("=" * 70)
    total_cycles = len(results)
    drift_cycles = sum(1 for r in results if r["drift_detected"])
    
    print(f"Total cycles: {total_cycles}")
    print(f"Drift detected: {drift_cycles}/{total_cycles}")
    print(f"Average IC: {np.mean([r['current_ic'] for r in results]):.4f}")
    print(f"Average Sharpe: {np.mean([r['current_sharpe'] for r in results]):.4f}")
    
    print("\n[OK] Phase 6.1 Continuous Learning execution complete!")
    print("=" * 70)
    
    return results

if __name__ == "__main__":
    try:
        results = run_continuous_learning()
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
