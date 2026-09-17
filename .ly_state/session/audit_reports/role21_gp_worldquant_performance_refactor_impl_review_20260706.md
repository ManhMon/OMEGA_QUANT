# Code Review Audit Report - GP WorldQuant Performance Refactor Implementation

**Role**: Code Reviewer (Role 21, L3 Codex)
**Date**: 2026-07-06
**Gate**: `GP_WORLDQUANT_PERFORMANCE_REFACTOR_IMPL`
**L2 Session**: `l2_role16_gp_worldquant_performance_refactor_20260706`
**L2 Role**: 16 machine-learning-engineer (OpenCode L2)
**L3 Session**: `l3_role21_gp_worldquant_performance_refactor_impl_review_20260706`
**Scope**: `scripts/genetic_alpha_evolution_v4.py`, `tests/quant_test_genetic_engine_optimizations.py`

---

## Writer != Auditor Verification

- **CONFIRMED**: l2_role_id=16 (machine-learning-engineer) != l3_role_id=21 (code-reviewer)
- Self-approval is not occurring. Writer and auditor are separated.

---

## Repo-Local Files Read
- .agents/agent/code-reviewer.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- scripts/genetic_alpha_evolution_v4.py
- tests/quant_test_genetic_engine_optimizations.py
- .ly_state/session/l2_role16_gp_worldquant_performance_refactor_20260706.md
---

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: confirmed not present, no reliance
- `.openclaw\skills`: confirmed not present, no reliance
- `C:\Users\GHC\.agents`: confirmed not present, no reliance
- `.codex\memories`: confirmed not present, no reliance

Forbidden paths appear only in the L2 report's scan evidence section with correct "confirmed not present, no reliance" phrasing. No authoritative reliance on any forbidden path.

---

## Code Quality Checks

### 1. Feature Bank (WorldQuant-Style)

- [x] **Pre-computation**: `_compute_feature_bank_for_ticker` (line ~1400) computes base features per-ticker using vectorized NumPy: returns_1d, returns_5d, vol_ratio, hl_range, oc_range, __log_market_cap__, traded_value, avg_traded_value.
- [x] **Aggregation**: `_build_feature_bank` (line ~1484) concatenates per-ticker frames, applies cross-sectional z-score transformations, and constructs `__sector__` proxy from volume quartiles.
- [x] **PIT-Safety**: T-1 shift applied via `.groupby("ticker")[FEATURE_COLS].shift(1)` and separately for `__log_market_cap__` and `__sector__` per-ticker group (lines ~1489-1491). **No look-ahead bias.**
- [x] **Storage**: Feature matrix stored as `FEATURE_BANK_KEY` in features dict, accessible to VM context for fast tree execution.
- [x] **Correctness**: Rolling mean uses `_window_view` with `sliding_window_view` for volume ratio. Prefix-sum approach for partial-window avg_traded_value is correct with `np.roll(avg_traded, 1)` to apply T-1 lag.

**Verdict**: APPROVED. Feature Bank correctly implements WorldQuant-style pre-computation with proper PIT safety.

### 2. Pandas Elimination in Compute Hot Paths

- [x] **Reduction**: pd. references reduced from 44 (V3) to 15 (V4).
- [x] **Remaining Pandas**: Limited to I/O paths only — `load_dataset`, `_build_feature_bank`, `_factorize_dates`, `_group_row_indices_by_date`. None in fitness evaluation hot paths.
- [x] **NumPy vectorization**: All fitness computation paths use pure NumPy arrays:
  - Tree execution via `_numba_execute_rpn` (line ~760)
  - Batch neutralization via `_numba_batch_ridge_neutralize` (line ~637)
  - Daily IC computation via `_numba_batch_daily_ics` (line ~1088)
- [x] **No Pandas in hot path**: Verified by inspecting `_execute_tree`, `_score_alpha_series`, `_batch_fold_ir_scores`, `_compute_time_fold_ir_v4` — none use Pandas.

**Verdict**: APPROVED. Pandas correctly eliminated from compute hot paths.

### 3. 3D Matrix Spearman IC (Batch Daily IC with Numba)

- [x] **Batch kernel**: `_numba_batch_daily_ics` (line ~1088) uses `@njit(cache=True, parallel=True)` with `prange(candidate_count)` — parallelism across candidate dimension, not date dimension, preserving sequential correctness.
- [x] **Per-date IC**: `_numba_daily_ics` (line ~1260) computes Spearman rank IC per date:
  - Uses `_numba_rank_average_ties` for proper tie handling (average method, compatible with scipy.stats.spearmanr)
  - Applies eval_mask per-date to filter valid observations
  - Minimum 5 valid observations per date required
- [x] **Rank correctness**: `_numba_rank_average_ties` (line ~1191) uses mergesort for stability, computes average rank for ties correctly: `avg_rank = 0.5 * (i + j - 1) + 1.0` which equals `(i+1 + j) / 2` — standard 1-based average rank.
- [x] **Pearson on ranks**: `_numba_pearson_corr` (line ~1206) correctly computes Pearson correlation of ranks, which equals Spearman IC.
- [x] **Test coverage**: `test_numba_daily_ics_matches_legacy_spearman` verifies equivalence with scipy.stats.spearmanr. `test_numba_batch_daily_ics_parity_with_per_candidate_loop` verifies batch == sequential.

**Verdict**: APPROVED. Spearman IC vectorization is correct with proper tie handling.

### 4. Island Model with Ring-Topology Migration

- [x] **Configuration**: `GPConfigV4` adds `island_count=3`, `island_migration_interval=5`, `island_migration_rate=0.05`.
- [x] **Population split**: `evolve()` splits population into `island_count` islands using `np.array_split`.
- [x] **Per-island evaluation**: Each island gets independent feature caches (`SUBTREE_CACHE_KEY`, `TARGET_NEUTRALIZED_CACHE_KEY`, `BATCH_FOLD_IR_CACHE_KEY` are popped per-island).
- [x] **Ring-topology migration**: `_migrate_islands` (line ~1758) copies top `migrate_count` individuals from each island to the next island (ring: island i → island (i+1) % n), replacing worst individuals.
- [x] **Breeding isolation**: `_breed_island` saves/restores numpy and python random state, seeds per-island for reproducibility.
- [x] **Migration interval**: Migration occurs every `island_migration_interval` generations (line ~1807 in evolve loop).
- [x] **Correctness**: `_copy_individual` properly deep-copies all fitness attributes. `_stable_rank_population` deduplicates by expression for diversity.

**Verdict**: APPROVED. Island Model correctly implements ring-topology migration with proper isolation and seeded RNG.

---

## PIT Safety and Look-Ahead Risk Assessment

- [x] **Feature Bank T-1 shift**: All FEATURE_COLS shifted by 1 day per-ticker group via `.groupby("ticker").shift(1)`. `__log_market_cap__` and `__sector__` also shifted per-ticker.
- [x] **avg_traded_value**: Correctly uses `np.roll(avg_traded, 1)` followed by `avg_traded[0] = np.nan` for T-1 lag.
- [x] **Forward returns**: `returns_1d` and `returns_5d` computed from close prices — these are base features, not targets. Forward returns for target are loaded separately via `forward_horizons=[1,3,5,10]` in `load_dataset`.
- [x] **Fold locality**: Time-fold IR evaluation slices features by fold mask before scoring. No cross-fold leakage.
- [x] **Daily IC**: Per-date computation preserves temporal boundaries.
- [x] **No look-ahead bias detected.**

**Verdict**: APPROVED. PIT safety is maintained throughout.

---

## SOD Boundary Compliance

- [x] **L2 (role 16, machine-learning-engineer)**: Implemented code and tests. Did not self-approve.
- [x] **L3 (role 21, code-reviewer)**: Read-only audit. No production code modifications. Writing only to `.ly_state/session/audit_reports/` and updating `phase_gates.json`.
- [x] **Writer != Auditor**: l2_role_id=16 != l3_role_id=21. Confirmed.
- [x] **L2 report lists repo-local skill source evidence**: Confirmed — L2 report lists all 8 declared skills from `REPO_SKILL_ROOT` and role spec from `REPO_AGENT_ROOT`.
- [x] **L2 forbidden path scan**: L2 report uses correct "confirmed not present, no reliance" phrasing for all 4 forbidden paths.

**Verdict**: APPROVED. SOD boundaries fully compliant.

---

## Test Execution Results

```
pytest tests/quant_test_genetic_engine_optimizations.py -v --tb=short
16 passed, 6 warnings in 6.77s
```

All 16 tests pass, including:
- Date group index builder correctness
- Daily IC computation equivalence (legacy vs Numba)
- Batch daily IC equivalence (batch vs sequential)
- Parallel batch daily IC with sparse masks
- Parallel batch ridge neutralization with NaNs
- Parallel evaluation thread safety (concurrent.futures ThreadPoolExecutor with stress iterations)

---

## Issues Found

No blocking issues found.

### Non-Blocking Observations
1. `_group_row_indices_by_date` cache key uses `id(date_arr)` which could alias if arrays are garbage collected. Mitigated by 500-entry cache cap and setdefault pattern.
2. Consider setting `NUMBA_NUM_THREADS`/`OMP_NUM_THREADS` to avoid thread oversubscription with `np.linalg.solve` LAPACK calls inside `_numba_ridge_neutralize` prange body.
3. `_feature_array_length` uses `next(iter(features.values()))` which assumes at least one feature — safe given feature bank construction guarantees features.

---

## Verdict

**[APPROVED]**

All four components (Feature Bank, Pandas Elimination, 3D Matrix Spearman IC Vectorization, Island Model) are correctly implemented with proper PIT safety, no look-ahead bias, adequate test coverage (16/16 pass), and full SOD compliance. The L2 report lists repo-local skill source evidence and uses approved forbidden path phrasing.
