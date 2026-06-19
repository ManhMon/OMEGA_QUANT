# OMEGA_QUANT Restructuring Migration Guide (v2.0)

This document provides a guide for migrating external code and references to the new domain-reorganized package layout introduced in OMEGA_QUANT v2.0.

## Overview of Layout Changes

To improve modularity, simplify dependency graphs, and prevent circular imports, files previously located at the root of `src/omega/quant/` have been moved to domain-specific subdirectories under `src/omega/quant/`.

Compatibility shim wrappers have been left at the legacy paths. However, these shims will now issue a runtime `DeprecationWarning` when imported and should be replaced by their canonical paths in all production code.

## Legacy vs. Canonical Import Mapping

| Legacy Path (Wrapper Shim) | Canonical Path (Domain Package) | Primary Exports / Classes |
| :--- | :--- | :--- |
| `omega.quant.ultimate_alpha_arsenal` | `omega.quant.alpha.arsenal` | `compute_ultimate_alphas` |
| `omega.quant.phase35_walk_forward` | `omega.quant.alpha.phase35` | `Phase35WalkForwardEngine` |
| `omega.quant.phase34_microstructure_alphas` | `omega.quant.alpha.phase34` | `compute_phase34_microstructure_alphas` |
| `omega.quant.ml_gate_validator` | `omega.quant.ml.gate_validator` | `MLGateValidator` |
| `omega.quant.alpha.discovery` | `omega.quant.alpha` submodules | `AlphaDiscoveryEngine`, `AlphaAlchemist`, `AlphaJudge` |
| `omega.quant.feature.pruning` | `omega.quant.feature.pruning_core` | `FeaturePruning` (configs in `pruning_config`) |
| `omega.quant.ml.voting_stacking` | `omega.quant.ml.voting` / `.stacking` | `VotingEnsemble`, `StackingEnsemble` |
| `omega.quant.neutralization` | `omega.quant.features.neutralization` | `HierarchicalNeutralizer`, `FactorNeutralizer` |
| `omega.quant.neutralization_engine` | `omega.quant.features.neutralization` | `HierarchicalNeutralizer` |
| `omega.quant.portfolio_optimizer` | `omega.quant.portfolio.portfolio_optimizer` | `PortfolioOptimizer` |

---

## Migration Examples

### 1. Portfolio Optimizer
**Before:**
```python
from omega.quant.portfolio_optimizer import PortfolioOptimizer
```
**After:**
```python
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer
```

### 2. Signal Neutralization
**Before:**
```python
from omega.quant.neutralization_engine import NeutralizationEngine
```
**After:**
```python
from omega.quant.features.neutralization import HierarchicalNeutralizer
```

### 3. Ultimate Alpha Arsenal
**Before:**
```python
from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
```
**After:**
```python
from omega.quant.alpha.arsenal import compute_ultimate_alphas
```

### 4. Machine Learning Gate Validator
**Before:**
```python
from omega.quant.ml_gate_validator import MLGateValidator
```
**After:**
```python
from omega.quant.ml.gate_validator import MLGateValidator
```
