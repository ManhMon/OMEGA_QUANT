# Implementation Plan: GP Codebase Remediation and Performance Optimization

This plan synthesizes the critical findings from the Codex L3 and Claude Code reviews of the GP codebase (covering `genetic_programming.py`, `genetic_engine.py`, `genetic_alpha_evolution_v4.py`, `run_weekly_evolution.py`, and `benchmark_v4_advanced.py`). 

The plan is divided into three priority phases to address PIT safety, logic correctness, unbounded memory growth, and JIT VM execution bottlenecks.

---

## Proposed Changes

### Phase 1: Critical Correctness & PIT Safety [Priority 1]

#### 1. Enforce Ticker Grouping in Python Fallback Rolling Operators
* **Files**: [genetic_engine.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py#L843), [genetic_programming.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_programming.py)
* **Change**: In the legacy/fallback execution path for rolling operators (`ts_mean`, `ts_std`, `ts_max`, `ts_min`, `ts_delta`, `ts_delay`), group the flat input array by `__ticker__` before calculating rolling windows. This prevents data from bleeding across symbol boundaries.

#### 2. Inject `__ticker__` Column in Production & Benchmark Scripts
* **Files**: [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py), [benchmark_v4_advanced.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/benchmark_v4_advanced.py)
* **Change**: Inject the raw `__ticker__` string/index column into the training, validation, and test feature dictionaries. This resolves the silent fallback issue where the JIT VM rolling operations redirected back to slow Python execution due to the missing grouping key.

#### 3. Apply T-1 Lag to Alternative Features
* **Files**: [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py#L165)
* **Change**: In the alternative feature gouping pipeline, apply `.groupby('symbol')[col].shift(1)` to all alternative features (sentiment, volume, foreign flows) before merging them. This prevents look-ahead bias from same-day news release leakage.

#### 4. Group Fallback Cross-Sectional Operations by Date
* **Files**: [genetic_engine.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py#L410-L419)
* **Change**: In the Python fallback path for `_cs_rank` and `_cs_zscore`, perform grouping by `__date__` to calculate rank and scores daily, replacing the look-ahead whole-panel ranking.

#### 5. Replace `id()`-keyed Cache Tokens with Monotonic UIDs
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)
* **Change**: Assign a unique monotonic slice ID (`features["__slice_uid__"] = next(_COUNTER)`) to each newly constructed features dict. Key all VM caching, lock lookup, and date-grouping caches on this stable token instead of CPython object `id()`, preventing cache corruption from memory address recycling.

#### 6. Correct Early Rejection Ranking Comparison
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py#L50)
* **Change**: Update `EARLY_REJECT_PENALTY` from `-2.0` to `-np.inf`. This prevents rejected individuals from ranking higher than valid individuals with high cumulative penalties (e.g., `-2.45`).

---

### Phase 2: Memory Safety & JIT VM Optimization [Priority 2]

#### 7. Implement Bounded LRU Cache for Program and Date Caches
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py#L63-L88)
* **Change**: Convert the unbounded global dictionaries `_GLOBAL_VM_PROGRAM_CACHE` and `_DATE_GROUPS_CACHE` into bounded LRU caches with a maximum capacity (e.g., 5000 entries) and an eviction policy to prevent multi-gigabyte memory leaks over long evolution runs.

#### 8. Hoist Feature Name Sorting Out of the VM Hot Path
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py#L650)
* **Change**: Sort feature names once during `GeneticEngine` setup. Store this sorted list in the engine state and pass it down, bypassing the redundant $O(N \log N)$ sorting during every tree evaluation.

#### 9. Enforce Stack Depth Guardrails
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py#L625)
* **Change**: Add validation check inside `_compile_tree_to_rpn` that verifies tree execution depth does not exceed `MAX_VM_STACK_DEPTH = 12`. Reject compiling trees exceeding this limit to prevent silent stack overflow.

#### 10. Normalize Multi-Target Horizon IC Calculation
* **Files**: [genetic_engine.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py#L1447)
* **Change**: Gracefully handle missing target columns by dynamically adjusting the sum of weights, preventing single target NaN values from propagating and turning the entire weighted IC to NaN.

---

### Phase 3: Benchmark Hygiene & Isolation [Priority 3]

#### 11. Isolate Warmup and Timed Benchmark Engine Runs
* **Files**: [benchmark_v4_advanced.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/benchmark_v4_advanced.py#L104)
* **Change**: Re-instantiate the `engine` object fresh for the timed runs (or invoke a clean `engine.reset()`). This prevents stats and the Hall of Fame from the warmup generation from contaminating the performance benchmark timings.

#### 12. Correct Island Migration Slicing
* **Files**: [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py#L1776)
* **Change**: Calculate `migrate_count` based on individual island size (`population_size / island_count`) rather than total population size, clamping the migration count to prevent index out of bounds.

---

## Verification Plan

### Automated Tests
1. **Regression & Parity Testing**:
   * Run the existing genetic engine optimization tests:
     `pytest tests/quant_test_genetic_engine_optimizations.py`
     `pytest tests/test_gp_numba_jit_vm.py`
2. **Parity Verification Test [New]**:
   * Add a test verifying that the fallback path and JIT VM path return identical results for rolling operators and cross-sectional rank/z-score operations.

### Performance & Memory Validation
1. **Benchmark Run**:
   * Execute:
     `python scripts/benchmark_v4_advanced.py --population-size 100 --workers 4 --backend threads`
   * Verify that memory growth remains flat/stable (no leak from program cache) and execution runs without silent fallbacks.
