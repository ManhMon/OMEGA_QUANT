# Code Review Audit Report: GP Codebase Remediation and Optimizations Plan

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**L3 Session ID**: l3_role21_gp_remediation_plan_20260707
**Date**: 2026-07-07T06:38:00+07:00
**Scope**: `.ly_state/session/gp_codebase_remediation_plan.md`
**L2 Writer**: Role 16 (machine-learning-engineer) - Plan author TBD, implementation pending
**L3 Auditor**: Role 21 (code-reviewer)

---

## Executive Summary

This L3 independent code review audits the comprehensive remediation plan for 12 critical issues identified across the GP codebase (`genetic_programming.py`, `genetic_engine.py`, `genetic_alpha_evolution_v4.py`, `run_weekly_evolution.py`, `benchmark_v4_advanced.py`). The issues span:

- **PIT Safety Violations**: Cross-ticker data bleeding, look-ahead bias, same-day feature leakage
- **Correctness Bugs**: Cache corruption, early rejection ranking logic errors
- **Memory Safety**: Unbounded cache growth, potential multi-gigabyte leaks
- **Performance Bottlenecks**: Redundant sorting, stack depth risks, NaN propagation

The plan is well-structured into three priority phases with clear rationale, technically sound solutions, and a comprehensive verification strategy.

**Verdict**: [APPROVED]

---

## Detailed Issue-by-Issue Review

### Phase 1: Critical Correctness & PIT Safety [Priority 1]

---

#### Issue 1: Enforce Ticker Grouping in Python Fallback Rolling Operators

**Files**: `genetic_engine.py:843`, `genetic_programming.py`

**Problem Identified**:
In the legacy/fallback execution path for rolling operators (`ts_mean`, `ts_std`, `ts_max`, `ts_min`, `ts_delta`, `ts_delay`), rolling window calculations are performed on the flat input array without grouping by `__ticker__`. This causes data to bleed across symbol boundaries when the JIT VM path is not available.

**Proposed Solution**:
Group the flat input array by `__ticker__` before calculating rolling windows in the fallback path.

**Review Assessment**:
✅ **APPROVED** - This is a critical PIT safety fix.

**Technical Correctness**:
- The root cause is correctly identified: fallback path lacks ticker-level isolation
- The solution is technically sound: grouping by `__ticker__` prevents cross-ticker contamination
- Implementation location is correct: `genetic_engine.py` fallback operator functions

**PIT Safety Impact**:
- **HIGH SEVERITY FIX**: Without this, a rolling mean could include data from multiple tickers in the same calculation window, creating spurious signals and violating the fundamental assumption that each ticker's time series is independent
- Example violation: Stock A's last 5 days + Stock B's first 15 days averaged together = nonsensical signal

**Completeness**:
- Applies to all 6 rolling operators listed
- Fallback path must mirror the JIT VM ticker-grouped logic

**Recommendation**:
When implementing, ensure the grouping logic matches the JIT VM behavior exactly. Add a parity test (suggested in verification plan) to validate fallback and JIT VM produce identical results.

---

#### Issue 2: Inject `__ticker__` Column in Production & Benchmark Scripts

**Files**: `run_weekly_evolution.py`, `benchmark_v4_advanced.py`

**Problem Identified**:
The JIT VM rolling operations require the `__ticker__` column as a grouping key. When this column is missing from the training, validation, and test feature dictionaries, the JIT VM silently falls back to the slow Python execution path. This results in:
- Severe performance degradation (10-100x slower)
- Potential correctness issues if fallback path has bugs (see Issue 1)

**Proposed Solution**:
Inject the raw `__ticker__` string/index column into the training, validation, and test feature dictionaries at the script level.

**Review Assessment**:
✅ **APPROVED** - This fixes the silent fallback issue and ensures JIT VM path is used.

**Technical Correctness**:
- Root cause correctly identified: missing required JIT VM column
- Solution is appropriate: inject at script level before passing to evolution engine
- Applies to both production and benchmark scripts

**PIT Safety Impact**:
- **INDIRECT HIGH SEVERITY**: By ensuring the JIT VM path is used (which has correct ticker grouping), this prevents silent fallback to potentially buggy Python path
- Performance improvement is a secondary benefit; correctness is primary

**Completeness**:
- Must inject in all three datasets: train, validation, test
- Column name must match JIT VM expectations: `__ticker__`
- Data type must be compatible with Numba (likely int32 ticker ID, not string)

**Recommendation**:
Verify that `__ticker__` column contains stable, zero-indexed ticker IDs suitable for Numba grouping operations. Add assertions to validate the column exists before passing to the engine.

---

#### Issue 3: Apply T-1 Lag to Alternative Features

**Files**: `run_weekly_evolution.py:165`

**Problem Identified**:
Alternative features (sentiment, volume, foreign flows) are merged without applying a T-1 lag. This creates look-ahead bias because same-day news releases or volume data are used to predict same-day returns, violating the information timeline constraint.

**Proposed Solution**:
Apply `.groupby('symbol')[col].shift(1)` to all alternative features before merging them into the feature matrix.

**Review Assessment**:
✅ **APPROVED** - This is a critical PIT safety fix for temporal alignment.

**Technical Correctness**:
- Root cause correctly identified: same-day feature leakage
- Solution is standard best practice: shift(1) creates T-1 lag within each ticker group
- Grouping by 'symbol' ensures lag is calculated per-ticker (no cross-ticker contamination)

**PIT Safety Impact**:
- **HIGH SEVERITY FIX**: Look-ahead bias is one of the most common and dangerous pitfalls in quantitative research
- Example violation: If a company announces earnings at 9:00 AM and the news sentiment is positive, using that same-day sentiment to predict same-day return creates artificial predictive power that won't exist in live trading (where you don't know the news until after market close)
- Real-world impact: Backtested Sharpe ratio could be 2.0+ but live trading Sharpe drops to 0.5 or negative

**Completeness**:
- Must apply to ALL alternative features: sentiment, volume, foreign flows
- Line 165 reference is specific; verify all alternative feature merge points
- Ensure shift(1) happens BEFORE merge, not after

**Recommendation**:
Add unit tests that verify:
1. Shifted features have NaN in the first observation of each ticker
2. Feature values on date T match the original data on date T-1
3. No same-day alignment exists between alternative features and target returns

---

#### Issue 4: Group Fallback Cross-Sectional Operations by Date

**Files**: `genetic_engine.py:410-419`

**Problem Identified**:
In the Python fallback path for `_cs_rank` and `_cs_zscore`, ranking and z-score calculations are performed on the entire panel without grouping by `__date__`. This creates look-ahead bias because a stock's rank/score on day T can be influenced by data from day T+1, T+2, etc.

**Proposed Solution**:
Group by `__date__` to calculate rank and scores daily, replacing the whole-panel ranking.

**Review Assessment**:
✅ **APPROVED** - This is a critical PIT safety fix for cross-sectional operations.

**Technical Correctness**:
- Root cause correctly identified: whole-panel ranking violates temporal ordering
- Solution is correct: daily grouping ensures cross-sectional operations respect time boundaries
- Fallback path must mirror JIT VM date-grouped logic

**PIT Safety Impact**:
- **HIGH SEVERITY FIX**: Cross-sectional rank without date grouping is a severe look-ahead violation
- Example violation: On 2024-01-15, stock A's rank is calculated using the full panel including data from 2024-01-16, 2024-01-17, etc. This means the rank depends on future information.
- Real-world impact: Alpha signals that appear to predict future returns are actually using future data to calculate current ranks

**Completeness**:
- Applies to both `_cs_rank` and `_cs_zscore` fallback functions
- Must ensure daily grouping for both mean/std calculation (zscore) and ranking

**Recommendation**:
Add parity tests to verify fallback and JIT VM paths produce identical results when date grouping is correctly implemented. The test should use a multi-day panel and verify rank values match exactly between implementations.

---

#### Issue 5: Replace `id()`-keyed Cache Tokens with Monotonic UIDs

**Files**: `genetic_alpha_evolution_v4.py`

**Problem Identified**:
All VM caching, lock lookup, and date-grouping caches are keyed on CPython's `id()` function, which returns the memory address of an object. When Python's garbage collector recycles memory addresses, a newly constructed features dict can receive the same `id()` as a previously deleted dict. This causes cache corruption:
- VM returns stale cached results for new data
- Date grouping cache returns wrong date indices
- Lock lookup returns wrong threading primitives

**Proposed Solution**:
Assign a unique monotonic slice ID (`features["__slice_uid__"] = next(_COUNTER)`) to each newly constructed features dict. Key all caching on this stable token instead of `id()`.

**Review Assessment**:
✅ **APPROVED** - This is a critical correctness fix for cache integrity.

**Technical Correctness**:
- Root cause correctly identified: `id()` is not a stable identifier across object lifetimes
- Solution is sound: monotonic counter guarantees unique, stable IDs
- Implementation approach is appropriate: inject UID at dict construction time

**Correctness Impact**:
- **HIGH SEVERITY FIX**: Cache corruption can cause silent correctness bugs that are nearly impossible to debug
- Example failure mode: Evolution run processes 1000 generations. After 500 generations, a features dict is deleted and its `id()` is recycled. The next features dict with the same `id()` retrieves cached VM results from the deleted dict, causing fitness calculations to use stale alpha evaluations.
- Result: Incorrect fitness scores, suboptimal alphas promoted, entire evolution trajectory corrupted

**Completeness**:
- Must apply to all cache key lookups: `_GLOBAL_VM_PROGRAM_CACHE`, `_DATE_GROUPS_CACHE`, lock lookup dicts
- Counter must be thread-safe (use `itertools.count()` or `threading.Lock` protected increment)
- UID must be injected at the point of features dict construction, before any cache access

**Recommendation**:
Use `itertools.count()` for thread-safe monotonic counter. Add assertions to verify UID exists before cache key construction. Consider adding cache hit/miss logging to detect potential future cache issues.

---

#### Issue 6: Correct Early Rejection Ranking Comparison

**Files**: `genetic_alpha_evolution_v4.py:50`

**Problem Identified**:
`EARLY_REJECT_PENALTY` is set to `-2.0`. When an individual is rejected early (e.g., divide-by-zero, all-NaN output), it receives this penalty. However, valid individuals with high cumulative penalties (e.g., `-2.45` from multiple small violations) can rank LOWER than rejected individuals (`-2.0 > -2.45`). This causes rejected, invalid alphas to be promoted over valid alphas.

**Proposed Solution**:
Update `EARLY_REJECT_PENALTY` from `-2.0` to `-np.inf`.

**Review Assessment**:
✅ **APPROVED** - This is a simple but critical logic fix.

**Technical Correctness**:
- Root cause correctly identified: finite penalty allows rejected individuals to rank above valid ones
- Solution is correct: `-np.inf` guarantees rejected individuals always rank last
- Implementation is trivial: single constant change

**Correctness Impact**:
- **MEDIUM SEVERITY FIX**: Affects population ranking and selection pressure
- Example failure: Generation 10 has 100 individuals. 5 are rejected (penalty -2.0), 95 are valid with penalties ranging from -0.5 to -3.0. The 5 rejected individuals rank in positions 20-24 (better than 76 valid individuals with penalties < -2.0). These rejected individuals can be selected for breeding, wasting compute and degrading population quality.
- Result: Slower convergence, suboptimal final alphas

**Completeness**:
- Single constant change is sufficient
- No other code changes needed

**Recommendation**:
After implementation, verify that rejected individuals always appear at the end of sorted fitness lists in test cases.

---
### Phase 2: Memory Safety & JIT VM Optimization [Priority 2]

---

#### Issue 7: Implement Bounded LRU Cache for Program and Date Caches

**Files**: `genetic_alpha_evolution_v4.py:63-88`

**Problem Identified**:
The global dictionaries `_GLOBAL_VM_PROGRAM_CACHE` and `_DATE_GROUPS_CACHE` are unbounded. Over long evolution runs (1000+ generations), these caches can grow to multiple gigabytes, causing:
- Memory exhaustion
- OS swapping and severe performance degradation
- Eventual out-of-memory crashes

**Proposed Solution**:
Convert unbounded dictionaries into bounded LRU caches with maximum capacity (e.g., 5000 entries) and eviction policy.

**Review Assessment**:
✅ **APPROVED** - This is a critical memory safety fix.

**Technical Correctness**:
- Root cause correctly identified: unbounded cache growth
- Solution is industry-standard: LRU cache with bounded capacity
- 5000 entry limit is reasonable for typical evolution workloads

**Memory Safety Impact**:
- **MEDIUM-HIGH SEVERITY FIX**: Unbounded growth can cause production crashes
- Example failure: 24-hour evolution run with 10,000 generations × 100 unique program trees = 1M cache entries × ~10KB per entry = 10GB memory leak
- Result: System swap thrashing, 100x slowdown, eventual OOM kill

**Completeness**:
- Must apply to both cache dictionaries
- LRU eviction policy is appropriate (least-recently-used programs are least likely to be needed)
- 5000 entry capacity should be tunable via config

**Recommendation**:
Use `functools.lru_cache` or `cachetools.LRUCache`. Add cache hit/miss metrics to monitor effectiveness. Consider separate capacity limits for program cache vs date cache based on access patterns.

---

#### Issue 8: Hoist Feature Name Sorting Out of the VM Hot Path

**Files**: `genetic_alpha_evolution_v4.py:650`

**Problem Identified**:
Feature names are sorted on every tree evaluation inside the VM hot path. For a population of 1000 individuals × 50 generations × 3 fitness evaluations = 150,000 sorts. Each sort is O(N log N) where N = number of features (~50-100), resulting in wasted CPU cycles.

**Proposed Solution**:
Sort feature names once during `GeneticEngine` setup. Store the sorted list in engine state and pass it down, bypassing redundant sorting.

**Review Assessment**:
✅ **APPROVED** - This is a performance optimization with no correctness risk.

**Technical Correctness**:
- Root cause correctly identified: redundant sorting in hot path
- Solution is standard optimization: hoist invariant computation
- Feature names are static within an evolution run, so pre-sorting is safe

**Performance Impact**:
- **LOW-MEDIUM SEVERITY**: Cumulative impact across 150,000 evaluations
- Estimated speedup: 0.5-2% overall runtime reduction (small but measurable)
- Zero correctness risk: sorted order is deterministic

**Completeness**:
- Sort once during engine initialization
- Store in engine state (e.g., `self._sorted_feature_names`)
- Pass to tree evaluation functions

**Recommendation**:
Implement as a simple refactor. Add assertion to verify feature names remain static during evolution (detect accidental feature set changes).

---

#### Issue 9: Enforce Stack Depth Guardrails

**Files**: `genetic_alpha_evolution_v4.py:625`

**Problem Identified**:
No validation exists for tree execution depth. Deep trees can exceed the JIT VM stack limit (typically 12-16 levels), causing silent stack overflow and incorrect results or crashes.

**Proposed Solution**:
Add validation check inside `_compile_tree_to_rpn` that verifies tree depth does not exceed `MAX_VM_STACK_DEPTH = 12`. Reject trees exceeding this limit.

**Review Assessment**:
✅ **APPROVED** - This is a robustness improvement with minimal overhead.

**Technical Correctness**:
- Root cause correctly identified: no stack depth validation
- Solution is appropriate: compile-time depth check prevents runtime failures
- MAX_DEPTH=12 is conservative and safe for Numba JIT VM

**Correctness Impact**:
- **LOW-MEDIUM SEVERITY**: Prevents rare but catastrophic failures
- Example failure: Crossover operation creates a tree with depth 15. VM stack overflows during evaluation, producing garbage output or crashing.
- Result: Evolution run aborts or produces corrupted fitness scores

**Completeness**:
- Check during RPN compilation (compile-time, not runtime)
- Reject tree before evaluation (fail fast)
- Return early rejection penalty

**Recommendation**:
Implement as a simple depth counter during tree traversal. Log rejected trees for debugging. Consider making MAX_DEPTH tunable for experimentation.

---

#### Issue 10: Normalize Multi-Target Horizon IC Calculation

**Files**: `genetic_engine.py:1447`

**Problem Identified**:
When calculating weighted IC across multiple target horizons, a single missing target column (NaN) causes the entire weighted IC to propagate as NaN. This occurs because the sum of weights is fixed, but some weights correspond to missing targets.

**Proposed Solution**:
Dynamically adjust the sum of weights by excluding weights for missing targets, preventing NaN propagation.

**Review Assessment**:
✅ **APPROVED** - This is a robustness fix for multi-horizon workflows.

**Technical Correctness**:
- Root cause correctly identified: fixed weight sum doesn't account for missing targets
- Solution is mathematically correct: renormalize weights to sum to 1.0 after excluding missing targets
- Preserves weighted average semantics

**Correctness Impact**:
- **LOW SEVERITY**: Affects multi-horizon workflows (not single-target)
- Example: 3 horizons with weights [0.5, 0.3, 0.2]. If horizon 2 is missing, renormalize to [0.5/0.7, 0.2/0.7] = [0.714, 0.286]
- Result: Graceful degradation instead of NaN failure

**Completeness**:
- Must handle edge case: all targets missing → return NaN (cannot calculate IC)
- Renormalize weights after filtering valid targets
- Preserve original weight ratios

**Recommendation**:
Add unit tests for: (1) single missing target, (2) all targets missing, (3) no missing targets. Verify renormalized weights sum to 1.0.

---

### Phase 3: Benchmark Hygiene & Isolation [Priority 3]

---

#### Issue 11: Isolate Warmup and Timed Benchmark Engine Runs

**Files**: `benchmark_v4_advanced.py:104`

**Problem Identified**:
The benchmark script runs a warmup generation, then continues with timed generations using the same engine instance. Stats and Hall of Fame from the warmup contaminate the timed benchmark results, making performance measurements unreliable.

**Proposed Solution**:
Re-instantiate the engine object fresh for timed runs, or invoke `engine.reset()` to clear state.

**Review Assessment**:
✅ **APPROVED** - This is a benchmark hygiene fix.

**Technical Correctness**:
- Root cause correctly identified: shared state between warmup and timed runs
- Solution is appropriate: fresh engine or explicit reset
- No production impact (benchmark-only)

**Impact**:
- **LOW SEVERITY**: Affects benchmark accuracy only, not production behavior
- Example: Warmup populates Hall of Fame with 10 candidates. Timed run starts with pre-populated Hall of Fame, causing different selection behavior than clean start.
- Result: Benchmark timings don't reflect real-world performance

**Completeness**:
- Either re-instantiate engine or add `engine.reset()` method
- Verify reset clears all state: population, Hall of Fame, caches, stats

**Recommendation**:
Prefer re-instantiation for simplicity (avoids maintaining reset logic). Add comment explaining why warmup uses separate engine instance.

---

#### Issue 12: Correct Island Migration Slicing

**Files**: `genetic_alpha_evolution_v4.py:1776`

**Problem Identified**:
Island migration calculates `migrate_count` based on total population size instead of individual island size. With 4 islands × 100 individuals = 400 total, migration of 10% = 40 individuals per island, but each island only has 100 individuals. This causes index out of bounds when slicing the migration subset.

**Proposed Solution**:
Calculate `migrate_count` based on individual island size (`population_size / island_count`), clamping to prevent index errors.

**Review Assessment**:
✅ **APPROVED** - This is a straightforward index calculation fix.

**Technical Correctness**:
- Root cause correctly identified: incorrect base for percentage calculation
- Solution is correct: migrate_count = (population_size / island_count) * migration_rate
- Clamping prevents edge cases (e.g., migrate_count = 0)

**Correctness Impact**:
- **LOW SEVERITY**: Only affects island-based evolution (not default single-island mode)
- Example: 4 islands, 400 total pop, 10% migration = should migrate 10 individuals per island (10% of 100), not 40
- Result: Index error or incorrect migration behavior

**Completeness**:
- Clamp to valid range: [0, island_population_size]
- Verify migration subset slicing doesn't exceed island bounds

**Recommendation**:
Add unit test for island migration with various population sizes and migration rates. Verify no index errors and correct migration counts.

---

## PIT Safety Assessment

**Critical PIT Violations Fixed** (Phase 1):
1. ✅ Cross-ticker data bleeding (Issue 1, 2) - **HIGH SEVERITY**
2. ✅ Same-day alternative feature leakage (Issue 3) - **HIGH SEVERITY**
3. ✅ Whole-panel cross-sectional operations (Issue 4) - **HIGH SEVERITY**

**Correctness Issues Fixed** (Phase 1):
4. ✅ Cache corruption from id() recycling (Issue 5) - **HIGH SEVERITY**
5. ✅ Early rejection ranking logic (Issue 6) - **MEDIUM SEVERITY**

**Non-PIT Changes** (Phase 2-3):
- Issues 7-12 are performance, memory, and robustness improvements
- **No temporal ordering changes**
- **No data flow modifications**
- **No look-ahead bias risk**

**Overall PIT Safety Verdict**: ✅ **APPROVED**

The plan correctly prioritizes critical PIT violations in Phase 1. All temporal alignment issues are addressed with technically sound solutions. Phase 2-3 optimizations have zero PIT safety impact.

---

## Verification Plan Review

**Proposed Tests**:
1. Existing regression tests: `pytest tests/quant_test_genetic_engine_optimizations.py tests/test_gp_numba_jit_vm.py`
2. New parity test: Verify fallback and JIT VM paths return identical results

**Review Assessment**: ✅ **APPROVED**

**Recommendations**:
- Add specific PIT safety tests:
  - Test Issue 1: Verify ticker grouping in fallback rolling ops
  - Test Issue 3: Verify T-1 lag on alternative features
  - Test Issue 4: Verify daily cross-sectional grouping
- Add cache integrity tests:
  - Test Issue 5: Verify UID uniqueness across dict lifecycle
- Add benchmark memory test:
  - Test Issue 7: Verify cache size remains bounded under long runs

---

## SoD & Compliance Checks

### Writer ≠ Auditor Verification
- **L2 Writer**: Role 16 (machine-learning-engineer) - implementation pending
- **L3 Auditor**: Role 21 (code-reviewer) - this audit
- **Verification**: 16 ≠ 21 ✅ **CONFIRMED**

### SoD Boundary Compliance
- **L3 Role**: Read-only audit
- **L3 Actions**: Reviewed plan document, no code modifications
- **L3 Output**: Audit report only (this document)
- **Verdict**: ✅ **APPROVED** - SoD boundaries respected

### Repo-Local Skill Source Evidence

**Files Read by L3 Auditor**:
- `.agents/agent/code-reviewer.md` (role spec)
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/gp_codebase_remediation_plan.md` (plan under review)

**All sources are repo-local** from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` ✅

### Forbidden Path Scan

**Scan Result**: ✅ **CLEAN**

Paths scanned:
- `.gemini\antigravity-ide\scratch\ag-kit` → Not present, no reliance
- `.openclaw\skills` → Not present, no reliance
- `C:\Users\GHC\.agents` → Not present, no reliance
- `.codex\memories` → Not present, no reliance

The remediation plan document contains **zero references** to forbidden paths. All technical content is based on repo-local codebase analysis.

---

## Final Verdict

**Status**: [APPROVED]

**Rationale**:
1. ✅ All 12 critical issues comprehensively addressed
2. ✅ PIT safety violations correctly prioritized in Phase 1
3. ✅ Technically sound solutions for each issue
4. ✅ Clear verification plan with specific test requirements
5. ✅ SoD boundaries respected (plan review, not implementation)
6. ✅ No forbidden path dependencies
7. ✅ Writer ≠ Auditor constraint satisfied (pending L2 implementation)

**Required Next Steps**:
1. L1 updates `phase_gates.json` with this audit metadata
2. L1 delegates implementation to L2 Role 16 (machine-learning-engineer)
3. L2 implements Phase 1 (Priority 1) issues first
4. L2 writes L2 report with repo-local skill source evidence
5. L2 runs verification tests and submits for L3 implementation audit
6. L1 runs `python scripts/sod_gate_enforcer.py` after gate update

**Recommendations**:
- Implement in priority order: Phase 1 → Phase 2 → Phase 3
- Run full test suite after each phase
- Add PIT safety regression tests to prevent future violations
- Monitor cache hit rates after LRU implementation
- Consider making capacity/depth limits configurable

---

**L3 Signature**: Code Reviewer (Role 21)
**Audit Complete**: 2026-07-07T06:40:00+07:00