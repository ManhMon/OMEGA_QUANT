# flake8: noqa
"""Feature Pruning Module - IC-based Feature Selection.

Shim wrapper preserving backward compatibility.
"""
from __future__ import annotations

import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.feature.pruning is deprecated; import from individual submodules instead.",
    DeprecationWarning,
    stacklevel=2
)

import numpy as np
import pandas as pd

from omega.quant.feature.pruning_config import FeaturePruningConfig, PruningResult
from omega.quant.feature.pruning_core import FeaturePruning

__all__ = [
    "FeaturePruningConfig",
    "PruningResult",
    "FeaturePruning",
]


if __name__ == '__main__':
    print("=" * 80)
    print("FEATURE PRUNING - DEMO")
    print("=" * 80)
    
    # Create sample data
    np.random.seed(42)
    n_samples = 500
    n_features = 30
    
    # Generate features
    features = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f'feature_{i}' for i in range(n_features)]
    )
    
    # Generate returns with some correlation to features
    returns = pd.Series(
        0.5 * features['feature_0'] +  # Strong signal
        0.3 * features['feature_1'] +  # Medium signal
        0.1 * features['feature_2'] +  # Weak signal
        np.random.randn(n_samples) * 0.5,  # Noise
        index=features.index
    )
    
    # Create pruner
    config = FeaturePruningConfig(
        min_ic_threshold=0.05,
        stability_threshold=0.8,
        progressive_rate=0.2
    )
    pruner = FeaturePruning(config)
    
    print(f"\n1. Computing IC for {n_features} features...")
    ics = pruner.compute_ic(features, returns)
    print(f"   Top 5 ICs: {sorted(ics.items(), key=lambda x: abs(x[1]), reverse=True)[:5]}")
    
    print(f"\n2. Computing stability...")
    stability = pruner.compute_stability(features, returns)
    print(f"   Top 5 stable: {sorted(stability.items(), key=lambda x: x[1])[:5]}")
    
    print(f"\n3. Pruning features...")
    result = pruner.prune_features(features, returns, progressive=True)
    print(f"   {result.summary()}")
    print(f"   Removed: {result.removed_features[:5]}...")
    
    print(f"\n4. Feature importance ranking...")
    importance = pruner.get_feature_importance(features, returns)
    print(importance.head(10))
    
    print("\n" + "=" * 80)
    print("✅ Feature Pruning demo complete")
    print("=" * 80)
