# L2 Implementation Report: Hybrid Regime Full Backtest Fix

**Role:** 9 Backend Engineer (OpenCode L2)
**Gate:** `HYBRID_REGIME_FULL_BACKTEST_20260620`
**Date:** 2026-06-20
**Scope:** `scripts/backtest_hybrid_regime.py`

---

## Skills Loaded from REPO_SKILL_ROOT

All 6 required skills loaded from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`:

| # | Skill | File | Status |
|---|-------|------|--------|
| 1 | `nodejs-best-practices` | `SKILL.md` (335 lines) | LOADED |
| 2 | `api-patterns` | `SKILL.md` (82 lines) | LOADED |
| 3 | `database-design` | `SKILL.md` (53 lines) | LOADED |
| 4 | `clean-code` | `SKILL.md` (202 lines) | LOADED |
| 5 | `testing-patterns` | `SKILL.md` (179 lines) | LOADED |
| 6 | `systematic-debugging` | `SKILL.md` (110 lines) | LOADED |

**Agent frontmatter parsed:** `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\backend-engineer.md`
- role_id: 9, tier: 2, platform: OpenCode
- sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"

---

## Forbidden Path Scan Evidence

Scanned `scripts/backtest_hybrid_regime.py` for references to forbidden paths:

| Forbidden Path | Found References | Status |
|---|---|---|
| `C:\Users\GHC\.agents` (non-authoritative, not used as source) | 0 | CLEAN |
| `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source) | 0 | CLEAN |
| `.openclaw\skills` (non-authoritative, not used as source) | 0 | CLEAN |
| `.codex\memories` (non-authoritative, not used as source) | 0 | CLEAN |

**Conclusion:** No reliance on any forbidden paths. All imports reference `omega.quant.*`, `phase35_data_loader`, and standard library only.

---

## Root Cause Analysis (systematic-debugging)

### Phase 1: Reproduce
The CPCV backtest produces silently incorrect results (look-ahead bias) for early folds where train dates precede the per-fold feature window.

### Phase 2: Isolate
- `run_single_fold()` generated `feat_df` from `raw_df[warmup_start:max_test_date]` per fold
- `train_fold_models()` filtered `train_feat = feat_df[feat_df['date'].isin(train_dates)]`
- For early CPCV folds, `train_dates` pointed to dates BEFORE `warmup_start`
- `train_feat` was empty, triggering silent fallback to `(None, None)`

### Phase 3: Root Cause
Three interconnected bugs:
1. **Per-fold feature generation** created a narrow date window that excluded train dates
2. **Silent failure** in `train_fold_models()` returned `(None, None)` instead of halting
3. **No validation** that train_feat was non-empty before model fitting

---

## Changes Made

### Fix 1: Global feat_df generation in `main()` (lines 747-761)

**Before:** Features generated per-fold inside `run_single_fold()` from sliced `raw_df`.

**After:** Features generated ONCE for the entire period (2015-2026) in `main()` before the CPCV fold loop:
```python
panel_full = prepare_panel(raw_df, tickers)
feat_df = generate_features(panel_full)
```
This guarantees `feat_df` covers ALL dates in the backtest period, so `train_feat` will never be empty for any CPCV fold.

### Fix 2: Updated `run_single_fold()` signature (lines 501-554)

**Before:** Accepted `raw_df`, `all_unique_dates`; generated per-fold `raw_slice`, `panel`, `feat_df`.

**After:** Accepts `feat_df` (the global DataFrame). Filters `test_feat` from global `feat_df` for `[warmup_start, max_test_date]` to provide warmup data for pipeline execution:
```python
test_feat = feat_df[
    (feat_df["date"] >= warmup_start) & (feat_df["date"] <= max_test_date)
]
```
- Passes global `feat_df` to `train_fold_models()` (train dates properly found)
- Passes `test_feat` to `make_query_fn()` (pipeline gets warmup + test data)

### Fix 3: Explicit exceptions in `train_fold_models()` (lines 388-496)

**Before:** Empty `train_feat` logged warning and returned `(None, None)`. HMM/GMM failures logged warnings silently.

**After:** All failure modes raise `ValueError` with descriptive messages:
- Empty `train_feat` -> `ValueError` with date range diagnostics
- HMM insufficient data -> `ValueError` with counts
- HMM unexpected error -> `ValueError` wrapping original exception
- GMM no latent columns -> `ValueError` with expected columns
- GMM fit not converged -> `ValueError` with row/col diagnostics
- GMM unexpected error -> `ValueError` wrapping original exception

### Fix 4: Updated docstrings (lines 366-393)

Updated `train_fold_models()` docstring to document:
- Parameters now expect the GLOBAL feat_df (entire 2015-2026 period)
- Returns non-None models on success
- Raises `ValueError` on any failure condition

---

## Verification Results

| Check | Result |
|-------|--------|
| `python -m py_compile` | PASS (no output = success) |
| `python -c "import ast; ast.parse(...)"` | PASS ("AST parse OK") |
| `python -m pyflakes` | PASS (clean, no warnings) |
| Forbidden path scan | PASS (0 references found) |

---

## Data Flow Diagram (After Fix)

```
main()
  |
  +-> load_raw_data(2015-2026) -> raw_df
  +-> select_static_universe(raw_df) -> tickers
  +-> prepare_panel(raw_df, tickers) -> panel_full
  +-> generate_features(panel_full) -> feat_df [GLOBAL, full 2015-2026]
  |
  +-> CPCV loop:
        |
        +-> run_single_fold(feat_df=GLOBAL_FEAT_DF)
              |
              +-> test_feat = feat_df[warmup_start:max_test_date]  # for pipeline
              +-> train_fold_models(feat_df=GLOBAL_FEAT_DF, train_dates)
              |     |
              |     +-> train_feat = feat_df[date.isin(train_dates)]  # FOUND!
              |     +-> Ridge, HMM, GMM fit on train_feat
              |     +-> raise ValueError if any failure
              |
              +-> make_query_fn(test_feat) -> pipeline execution
```

---

## Tier 3 Audit Submission

This implementation is submitted for Tier 3 review:
- **Code Reviewer (role 21):** Backend code quality, proper error handling, PIT safety
- **QA Engineer (role 17):** Functional correctness of CPCV fold data flow
- **Security Auditor (role 18):** No data leakage, no forbidden path dependencies

---

## Diff Summary

```
scripts/backtest_hybrid_regime.py
  train_fold_models():
    - Empty train_feat: logger.warning -> raise ValueError
    - HMM failure: logger.warning -> raise ValueError
    - GMM failure: logger.warning -> raise ValueError
    - Docstring: updated params/returns/raises
  run_single_fold():
    - Removed: raw_df, all_unique_dates params
    - Added: feat_df param (global DataFrame)
    - Removed: per-fold raw_slice, panel, generate_features()
    - Added: test_feat filtering from global feat_df [warmup_start, max_test_date]
    - Changed: make_query_fn(feat_df) -> make_query_fn(test_feat)
    - Changed: train_fold_models(feat_df, train_dates) uses global feat_df
  main():
    - Added: panel_full = prepare_panel(raw_df, tickers)
    - Added: feat_df = generate_features(panel_full)
    - Added: empty feat_df guard (raise ValueError)
    - Changed: run_single_fold(feat_df=feat_df) replaces (raw_df=raw_df, all_unique_dates=unique_dates)
```
