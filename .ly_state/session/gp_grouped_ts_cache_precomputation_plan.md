# Implementation Plan - Grouped TS Cache Precomputation Optimization

## Goal Description
Optimize `DiverseAlphaEvolution` parallel evaluation by pre-computing the grouped time-series indexing structure (`order`, `starts`, `stops`) in the main thread prior to thread dispatch. This avoids multiple worker threads concurrently executing `pd.to_datetime` and `np.lexsort` on large datasets, preventing thread-safety crashes and reducing CPU overhead.

## Proposed Changes

### Component: GP Engine & Diverse Evolution

#### [MODIFY] src/omega/quant/evolution/diverse_alpha_evolution.py
- Pre-compute the grouped time-series indexing tuple `(order, starts, stops, ticker_arr, date_arr)` inside `_build_standard_features()` using the main thread.
- Store the tuple in `features["__grouped_ts_structure__"]`.
- Update `_candidate_from_genome_standard()` to call `ge.set_active_grouped_ts_structure(train_features.get("__grouped_ts_structure__"))` and `ge.set_active_grouped_ts_structure(val_features.get("__grouped_ts_structure__"))` respectively, and clean up with `ge.set_active_grouped_ts_structure(None)` in `finally` blocks. This ensures JIT concurrency safety and strict thread-local isolation.

#### [MODIFY] src/omega/quant/evolution/genetic_engine.py
- Add thread-local state variable `active_grouped_ts_structure` (owned by `_THREAD_LOCAL_STATE`) with getter `get_active_grouped_ts_structure()` and setter `set_active_grouped_ts_structure()`.
- Update `_apply_grouped_ts_transform` to check `get_active_grouped_ts_structure()` first. If present, bypass cache lookup and sorting, using the pre-computed structure in O(1) time.

#### [MODIFY] tests/test_diverse_alpha_evolution_parallel.py
- Add a unit test to verify that the pre-computed structure is correctly resolved and applied in the parallel execution loop, asserting that no cache computation occurs during threaded evaluation.

## L2 Report Contract
L2 must write an implementation report to `.ly_state/session/l2_role16_gp_grouped_ts_cache_precomputation_20260714.md` listing all repo-local role and skill files read, and verify no authoritative reliance on forbidden paths (.gemini/antigravity-ide/scratch/ag-kit, .openclaw/skills, C:/Users/GHC/.agents, .codex/memories).

## Verification Plan

### Automated Tests
- Run parallel test suite:
  `pytest tests/test_diverse_alpha_evolution_parallel.py`
