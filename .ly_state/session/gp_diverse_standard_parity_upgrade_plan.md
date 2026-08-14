# Implementation Plan - GP Diverse Engine Standard Parity Upgrade

This plan outlines the comprehensive roadmap to upgrade the **GP Diverse Engine (Island Model)** to parity with the **Standard GP Engine V4** by reusing the standard engine's core compilation, evaluation, and validation infrastructure, completely preventing code duplication and AST/semantic drift.

## User Review Required

> [!IMPORTANT]
> - **Unified AST & VM Parity**: Instead of duplicating JIT VM execution, Diverse Engine candidates will be converted to standard `GPNode` representation *before* evaluation. This allows the Diverse Engine to immediately support all standard and advanced operators (`sum`, `rank`, `delay`, `abs`, `sign`, `neg`, `decay_linear`, `cs_rank`, `cs_neutralize`) using the Standard V4 Numba JIT VM.
> - **OLS Neutralization & Time-Folds Reuse**: Candidate evaluation will utilize Standard V4's `_batch_neutralize_cross_section()` (Gram-sharing OLS) and standard time-fold daily IC IR scoring, ensuring 100% numerical parity.
> - **Global Orthogonalization**: Incorporate baseline correlation penalties during evaluation by comparing candidate signals against the globally registered alpha database.
> - **Pre-Registration Embargo**: The embargo check `validate_embargo()` will run at a strict pre-registration checkpoint before candidates are serialized to disk.

---

## Proposed Changes

### Component 1: AST Conversion & Operator Parity

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Refactor island mutation and crossover pools to select standard V4 operators and terminals.
- Before evaluation, recursively convert Diverse candidates to standard `GPNode` AST representations using a lossless conversion contract.

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
- Align `_convert_diverse_node()` to map all advanced time-series and cross-sectional operators to standard `GPNode` equivalents without loss.

---

### Component 2: Numba VM, Neutralization, & Time-Folds Reuse

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Replace legacy Pandas-based `_evaluate_population` with the standard V4 VM evaluation flow.
- Pass pre-sliced fold feature views and JIT neutralization payloads to Numba JIT VM execution threads.
- Score candidates using the daily IC Information Ratio (IR) over rolling time folds with standard std-flooring.

---

### Component 3: Global Orthogonalization & Embargo Hardening

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Support `ortho_baseline_set` in `DiverseEvolutionConfig` to penalize candidates showing correlation above `ortho_correlation_threshold` against globally registered historical alphas.

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
- Enforce `validate_embargo()` at a strict pre-registration/pre-serialization checkpoint inside `run_evolution()` to immediately discard blocked candidates.

---

## Verification Plan

### Automated Tests
- Run full repository tests: `pytest -q`
- Run targeted diverse engine tests: `pytest tests/test_diverse_alpha_evolution_parallel.py -q`

### Parity Assertions (Unit Tests)
- **AST Conversion Parity**: Assert that converting diverse trees to standard `GPNode` and evaluating them yields identical outputs to standard engine evaluations.
- **JIT VM & Neutralization Parity**: Assert that JIT VM outputs match Pandas-based evaluation outputs within `1e-7` numerical tolerance.
- **Time-Fold IR Parity**: Assert that Diverse Engine fold scores match Standard Engine fold scores on identical inputs.
- **Embargo Enforcement**: Test that blocked alphas are correctly rejected and not registered or saved.
