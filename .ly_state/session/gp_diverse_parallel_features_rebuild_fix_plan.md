# Plan: GP Diverse Engine Feature Rebuild Performance Optimization

## 1. Problem Description
- `_candidate_from_genome_standard` calls `_build_standard_features` on `train_df` and `val_df` for every single candidate evaluation.
- `_build_standard_features` calculates the OLS neutralization cache (`_build_neutralization_cache`) which is highly CPU and memory intensive (performing QR/SVD projections on 1.2M rows x 2500 dates).
- Under loky process parallelism, this causes `_build_neutralization_cache` to run 8,000 times per generation (4 islands x 1000 candidates x 2 datasets), resulting in a massive computational bottleneck where one generation takes over 4 hours.

## 2. Proposed Solution
- **Pre-build standard features once**: Calculate `train_features`, `train_target`, `val_features`, and `val_target` exactly once at the beginning of `DiverseAlphaEvolution.run()`.
- **Pass pre-built features to workers**: Update `_evolve_island_job`, `_evolve_island`, `_evaluate_population`, and `_evaluate_genome_job` to accept `train_features`, `train_target`, `val_features`, and `val_target` directly instead of `train_df` and `val_df`. This also significantly reduces Joblib serialization/IPC overhead.
- **Pass pre-built features to diversity filter**: Update `_filter_diverse` to accept `train_features` directly instead of calling `_build_standard_features` on `train_df`.

## 3. Proposed Changes

### [Component: Evolution Engine]

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Modify `_candidate_from_genome_standard` signature and body to accept and use pre-built features and target arrays.
- Modify `_evaluate_genome_job` to accept and pass pre-built feature dicts.
- Modify `_evaluate_population` to accept and pass pre-built feature dicts.
- Modify `_evolve_island` to accept pre-built feature dicts.
- Modify `_evolve_island_job` to accept pre-built feature dicts.
- Modify `_filter_diverse` to accept `train_features` directly.
- Modify `DiverseAlphaEvolution.run()` to build `train_features` and `val_features` once at startup, then propagate them to the islands.

## 4. Verification Plan

### Automated Tests
- Run `pytest tests/test_diverse_alpha_evolution_parallel.py` and ensure all tests pass.
- Run `pytest tests/test_genetic_alpha.py` to ensure no regression.
- Verify strict numerical parity between the optimized parallel evaluation and the original sequential results.
