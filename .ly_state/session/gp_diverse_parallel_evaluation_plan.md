# Implementation Plan - GP Diverse Engine Parallel Evaluation

This plan introduces parallel evaluation of the population within the Island Model (`DiverseAlphaEvolution`) to fully leverage multiple CPU cores (e.g. 12 workers) in WSL, eliminating the single-core CPU bottleneck.

## User Review Required

> [!IMPORTANT]
> - **Parallel Backend**: We will use Joblib's `Parallel` with `prefer="processes"` (process-based) for the WSL/Linux environment. This completely bypasses CPython's GIL (Global Interpreter Lock) for tree evaluation, yielding a near-linear speedup with core count.
> - **Thread-Safe Seeds**: Random number generation within mutations/crossovers will remain on the main process (as evolution happens sequentially on each island, and only evaluation is parallelized), ensuring 100% determinism.

## Proposed Changes

### Component: Evolution Engine

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Update `DiverseEvolutionConfig` to include a `workers: int = 1` parameter.
- Refactor `DiverseAlphaEvolution._evaluate_population` to execute `Genome.evaluate_vectorized` and metric computations in parallel across genomes using `joblib.Parallel` with process-based worker pools.
- Map the parallel results back to `AlphaCandidate` objects.

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
- Pass the `--workers` CLI parameter into the `DiverseEvolutionConfig` constructor when initializing the diverse engine.

## Verification Plan

### Automated Tests
- Run existing GP unit tests to ensure no regressions:
  ```powershell
  wsl sh -c "export PYTHONPATH=.; pytest tests/test_genetic_alpha.py"
  ```
- Run a small-scale evolution run (e.g. 40 pop, 2 gen) in WSL to verify the parallel execution path and equivalence:
  ```powershell
  wsl sh -c "export PYTHONPATH=.; python3 scripts/run_weekly_evolution.py --engine diverse --population-size 40 --generations 2 --workers 4"
  ```
- Performance comparison (sequential vs parallel).
