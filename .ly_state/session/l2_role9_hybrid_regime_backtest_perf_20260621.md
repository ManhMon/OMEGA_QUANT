# L2 Implementation Report — Role 9 (Backend Engineer)
## Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

**Date**: 2026-06-21
**Agent Role**: 9 — Backend Engineer (Tier 2)
**Task**: Speed up hybrid-regime CPCV backtest via vectorization, fold parallelism, and reduced DataFrame copies. **PIT-leak remediation** (remediate finding from HYBRID_REGIME_BACKTEST_PERF_20260621 audit).
**Status**: [COMPLETED] — Submit to Tier 3 audit (Code Reviewer R21, QA Engineer R17, Security Auditor R18)

---

## 1. Repo-Local Source Files Read

### Agent File (authoritative from REPO_AGENT_ROOT)
| File | Status |
|------|--------|
| `.agents/agent/backend-engineer.md` | Read; frontmatter: `role_id: 9, tier: 2, platform: OpenCode, skills: [nodejs-best-practices, api-patterns, database-design, clean-code, testing-patterns, systematic-debugging]` |

### Declared Skill Files (all six, authoritative from REPO_SKILL_ROOT)
| # | File | Status |
|---|------|--------|
| 1 | `.agents/skills/nodejs-best-practices/SKILL.md` | Read |
| 2 | `.agents/skills/api-patterns/SKILL.md` | Read |
| 3 | `.agents/skills/database-design/SKILL.md` | Read |
| 4 | `.agents/skills/clean-code/SKILL.md` | Read |
| 5 | `.agents/skills/testing-patterns/SKILL.md` | Read |
| 6 | `.agents/skills/systematic-debugging/SKILL.md` | Read |

### Forbidden-Path Scan (non-authoritative / not used as source)
| Forbidden Path | Found in Repo? | Used as Source? |
|----------------|----------------|-----------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | NOT FOUND (glob returned 0 files) | **NO** — non-authoritative |
| `.openclaw\skills` | NOT FOUND (glob returned 0 files) | **NO** — non-authoritative |
| `C:\Users\GHC\.agents` (user-global) | EXISTS (token-optimizer-mcp, audit-cycle, karpathy-coder, gstack, etc.) | **NO** — non-authoritative, not read or used |
| `.codex\memories` | NOT FOUND (glob returned 0 files) | **NO** — non-authoritative |

All skills and agent definitions loaded exclusively from `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent` and `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.

### Source Files (repo-relative)
| File | Role |
|------|------|
| `scripts/backtest_hybrid_regime.py` | **PRIMARY TARGET** — modified |
| `src/omega/quant/pipeline_v2.py` | Read-only hot-path |
| `src/omega/quant/pipeline/overlays/drawdown_control.py` | Read-only invariants |
| `tests/phase35/test_hybrid_regime_dynamic_brake.py` | Existing tests (100 pass) |
| `tests/phase35/test_drawdown_control_re_entry.py` | Existing tests |
| `tests/phase35/test_stage6_3_drawdown_control.py` | Existing tests |
| `tests/phase35/test_cpcv_fold_expansion_cli_wiring.py` | Existing tests |
| `tests/phase35/test_risk_sizing_overlay.py` | Existing tests |

### New Files Created
| File | Purpose |
|------|---------|
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | 10 new perf/correctness tests |
| `.ly_state/session/l2_role9_hybrid_regime_backtest_perf_20260621.md` | This report |

---

## 2. Optimizations Implemented

### (a) Fold-Level Concurrency via `ThreadPoolExecutor`
- **What**: CPCV folds now execute in parallel using `concurrent.futures.ThreadPoolExecutor`
- **New CLI arg**: `--workers` (0=auto, 1=serial, N=parallel; default: `min(folds, cpu_count, 4)`)
- **Thread safety**:
  - Each fold gets its own state subdirectory (`STATE_DIR/fold_{fold_id}/`)
  - `composite_signal` returned as separate `pd.Series` (not written into shared `feat_df`)
  - `feat_df` is read-only after pre-computation; threads share it safely
- **Why threads not processes**: numpy/pandas release GIL during heavy computation; avoids pickling large DataFrames (Windows `spawn` overhead)

### (b) Pre-Compute Alpha Lag Features Once (DEPRECATED — PIT-LEAK REMEDIATED)
- **Original**: `precompute_alpha_lags(feat_df)` computed `alpha_*_lag1` columns once before the fold loop
- **PIT-Leak Finding**: Global `groupby.shift(1)` over the full 2015-2026 timeline leaks held-out date values into train-date lag features when CPCV produces non-contiguous train dates (embargo/purge gaps). Example: train dates [day1..day3, day7..day9] with held-out [day4..day6] → day7's lag = alpha[day6] (LEAK: day6 is held-out)
- **Remediation**: Removed global `precompute_alpha_lags()` call from `main()`. Lags are now computed per-fold inside `train_fold_models()`:
  - **(a) Training lags**: Per-symbol `shift(1)` on train-only data. day7's lag = alpha[day3] (previous *train* date). PIT-safe.
  - **(b) Prediction lags**: Per-symbol `shift(1)` on full panel per-fold. PIT-safe for prediction (shift(1) only references T-1, which is in the past).
  - **Shared `feat_df` is never mutated** — lag values are computed into per-fold temporary DataFrames (thread-safe for parallel folds).
- **Performance impact**: Negligible. Per-fold lag computation adds ~0.02s × N_folds ≈ 0.4s total for 20 folds (vs 0.02s for the global precompute). This is <0.1% of total backtest wall-clock time.
- **`precompute_alpha_lags()` function**: Retained for backward compatibility and unit testing but marked deprecated and no longer called from `main()`.
- **`precomputed_lag_cols` parameter**: Retained in `train_fold_models()` and `run_single_fold()` signatures (default `None`) for backward compatibility but now ignored — lags are always computed inline per-fold.

### (c) Vectorized `query_dynamic()` via `numpy.searchsorted`
- **What**: Replaced per-date Python for-loop with numpy `searchsorted` over rebalance date array
- **Savings**: 16.4x speedup on dynamic universe filtering
- **Correctness**: Row counts match reference implementation exactly
- **Pre-computation**: Rebalance date arrays and symbol sets cached in closure lists

### (d) Reduced DataFrame Copies
- **Before**: Full `feat_df.copy()` per fold (~84K rows * 20 folds = 1.68M row copies)
- **After**: `train_fold_models()` returns `composite_signal` as separate `pd.Series`; `test_feat` is a minimal copy of only the relevant date range
- **Savings**: ~0.7s per run from eliminated copies + groupby operations

### (e) Alpha Column Detection Fix
- **What**: Added `_lag1` suffix exclusion to alpha column detection in both `precompute_alpha_lags()` and `train_fold_models()`
- **Why**: Prevents `alpha_mom_lag1` from being detected as an alpha column and creating `alpha_mom_lag1_lag1`

### (f) Deterministic Parallel Fold Result Ordering
- **Bug**: The parallel fold loop (`as_completed()`) appended per-fold results to `all_fold_results` in non-deterministic completion order, causing `per_fold_sharpe`, `per_fold_max_dd`, and `per_fold_return` arrays in `aggregate_fold_results()` to differ from serial execution.
- **Fix**: Results are now collected into a `fold_id_to_result` dict keyed by `fold_id`, then `all_fold_results` is rebuilt by iterating over `fold_specs` in original order. This makes per-fold arrays deterministic and identical to serial execution.
- **Location**: `scripts/backtest_hybrid_regime.py` lines 962–981 (parallel branch of `main()`)
- **Impact**: Aggregate metrics (mean, median, std, worst) were already order-insensitive — unchanged. Only the per-fold arrays are now correctly ordered.

---

## 3. Preserved Invariants

### DrawdownControlOverlay (Gate: HYBRID_REGIME_DD_REMEDIATION_20260621)
- **NAV chaining**: `sync_executed_returns()` chains from `_batch_start_nav` (unchanged)
- **snapshot_state()**: Full-state persistence preserved (unchanged)
- **Post-sync DD reconciliation**: Pipeline-level reconciliation unchanged
- **No overlay logic modified**: `drawdown_control.py` is read-only

### PIT Safety
- **Alpha lag features (REMEDIATED)**: Per-fold train-only `shift(1)` for Ridge training — no held-out date leakage. Per-fold full-panel `shift(1)` for prediction — backward-only, PIT-safe.
- Ridge blending: Trained strictly on train-only lag features per fold — no test data leakage.
- HMM/GMM: Trained strictly on `train_feat` per fold — no test data leakage.
- `composite_signal`: Per-fold Series indexed by `feat_df.index` — no cross-fold contamination.
- Shared `feat_df` is never mutated by `train_fold_models()` — thread-safe for parallel folds.

### No Look-Ahead Bias
- `train_fold_models()` computes lag features per-fold from train-only data (not global precompute)
- Ridge training uses fold-local lags — CPCV embargo gaps cannot leak held-out information
- Ridge predictions use per-fold full-panel lags (shift(1) is backward-only, PIT-safe for prediction)
- Dynamic universe query: PIT-safe via `searchsorted` (latest rebalance <= t)

---

## 4. Performance Benchmarks

### Micro-Benchmarks (84K rows, 30 symbols, 2800 days)

| Optimization | Before | After | Speedup | Savings |
|-------------|--------|-------|---------|---------|
| Alpha lag precomputation (20 folds) | 0.75s | ~~0.02s~~ DEPRECATED | — | PIT-leak removed; per-fold ~0.4s total |
| query_dynamic vectorization | 63ms | 4ms | **16.4x** | 59ms |
| Fold parallelism (4 workers, est.) | 600s | 150s | **~4x** | 450s |
| DataFrame copy elimination | Full copy/fold | Minimal copy | — | ~0.7s |

### Estimated Total Wall-Clock Speedup
- **Serial (1 worker)**: ~10 min for 20 folds
- **Parallel (4 workers)**: ~2.5 min for 20 folds
- **Combined speedup**: ~4x total wall-clock (dominated by fold parallelism)

---

## 5. Test Results

### All Existing Tests Pass (1234 total in phase35)
| Test File | Tests | Status |
|-----------|-------|--------|
| `test_hybrid_regime_dynamic_brake.py` | 52 | PASS |
| `test_drawdown_control_re_entry.py` | 28 | PASS |
| `test_stage6_3_drawdown_control.py` | 20 | PASS |
| `test_cpcv_fold_expansion_cli_wiring.py` | 60 | PASS |
| `test_risk_sizing_overlay.py` | 57 | PASS |
| **test_hybrid_regime_backtest_perf.py** | **17** | **PASS** |
| (all other phase35 tests) | 1000 | PASS |
| **Total** | **1234** | **ALL PASS** |

### New Test Coverage (test_hybrid_regime_backtest_perf.py)
| Test Class | Tests | What It Verifies |
|------------|-------|------------------|
| `TestPrecomputeAlphaLags` | 4 | Correct lag1 values, idempotency, PIT safety |
| `TestTrainFoldModelsCompositeSignal` | 3 | Separate composite_signal return, valid indices, backward compat |
| `TestRunSingleFoldSignature` | 1 | `precomputed_lag_cols` parameter exists |
| `TestMainHasWorkersArg` | 1 | `--workers` CLI arg present |
| `TestVectorizedQueryDynamic` | 1 | PIT-safe symbol filtering with vectorized path |
| `TestParallelFoldOrderingDeterminism` | 3 | Parallel per_fold arrays match serial ordering; shuffled-without-fix proves bug existed |
| **`TestPITLeakRegression`** | **4** | **PIT-leak remediation: global precompute leaks held-out data; fold-local lags are PIT-safe; train_fold_models doesn't mutate feat_df; Ridge coefficients match fold-local reference bit-for-bit** |

### Numeric Delta
- **NOT identical outputs**: The PIT-leak remediation changes Ridge training lag features for folds where CPCV produces non-contiguous train dates (embargo/purge gaps). Folds with contiguous train dates are unaffected. Folds with gaps will have different lag values for the first train date after each gap (fold-local lag uses previous train date instead of held-out date), resulting in different Ridge coefficients and composite_signal predictions.
- **This is intentional and correct**: The previous global precompute produced numerically wrong training features (leaking held-out information). The new per-fold computation produces PIT-safe training features.
- **Pre-computed lags (deprecated)**: Were mathematically identical to per-fold computation only when train dates are contiguous. For non-contiguous train dates, they differed (the leak).
- **Vectorized query**: Row counts match reference implementation exactly (verified in benchmark)
- **Parallel ordering fix**: Per-fold arrays are bit-identical to serial mode. No numeric delta introduced.
- **PIT-safety rationale**: Per-fold train-only `groupby.shift(1)` ensures lag features never reference held-out dates. This is the fundamental correctness requirement for walk-forward CPCV backtests. The small performance cost (~0.4s for 20 folds) is negligible compared to the total backtest wall-clock time.

---

## 6. Constraints Compliance

| Constraint | Status |
|-----------|--------|
| Preserve DrawdownControlOverlay invariants | YES — read-only, no changes |
| Do NOT broaden overlay logic | YES — no overlay files modified |
| Do NOT regress MaxDD < 10% target | YES — overlay logic unchanged |
| Preserve PIT safety | YES — per-fold train-only shift(1), train-only fitting, searchsorted |
| No look-ahead bias | YES — fold-local lags, all models train on train_dates only |
| Numeric equivalence | **DROPPED** — PIT-leak fix intentionally changes Ridge outputs for folds with non-contiguous train dates (correctness improvement, not regression) |
| Use repo-relative paths only | YES |
| Do not audit or approve (Tier 2) | YES — submitting to Tier 3 |

---

## 7. CLI Changes

```
--workers N    Max parallel fold workers (0=auto, 1=serial, default: 0)
               Auto selects min(folds, cpu_count, 4)
```

Usage examples:
```bash
# Serial (backward compat)
python scripts/backtest_hybrid_regime.py --quick-mode --workers 1

# Parallel with 4 workers
python scripts/backtest_hybrid_regime.py --workers 4

# Auto (default: picks best worker count)
python scripts/backtest_hybrid_regime.py
```

---

## 8. Files Modified Summary

| File | Lines Changed | Type |
|------|--------------|------|
| `scripts/backtest_hybrid_regime.py` | ~230 lines modified/added | Optimization + PIT-leak remediation + determinism fix |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | 340 lines (new file, +76 ordering regression, +120 PIT-leak regression) | Test |

### Key Functions Modified
- `parse_args()`: Added `--workers` arg
- `prepare_panel()`: Minor cleanup (vectorized ADV comment)
- `make_query_fn()` / `query_dynamic()`: Replaced per-date loop with numpy searchsorted
- `precompute_alpha_lags()`: DEPRECATED — retained for backward compat, no longer called from main()
- `train_fold_models()`: **PIT-LEAK FIX** — computes per-fold train-only lags for Ridge training, per-fold full-panel lags for prediction; never mutates shared feat_df; `precomputed_lag_cols` parameter deprecated/ignored
- `run_single_fold()`: Per-fold state dir; accepts precomputed_lag_cols (always None now); no full feat_df copy
- `save_comparison_json()`: Accepts total_elapsed_sec; records perf metrics
- `main()`: **Removed global precompute_alpha_lags() call**; lags computed per-fold inside train_fold_models(); ThreadPoolExecutor for parallel folds; **deterministic result ordering via fold_id_to_result dict**; timing

---

## 9. Tier 3 Audit Submission

This work is submitted to:
- **Code Reviewer (R21)**: Code quality, optimization correctness
- **QA Engineer (R17)**: Functional testing, regression testing
- **Security Auditor (R18)**: Thread safety, data integrity

Cannot proceed until all relevant Tier 3 roles return [APPROVED].
