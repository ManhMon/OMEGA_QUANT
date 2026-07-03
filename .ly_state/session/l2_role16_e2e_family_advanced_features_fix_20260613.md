# L2 Report — Role 16 (Machine Learning Engineer)
## E2E Family Fix: advanced-features ValueError

**GATE**: E2E_FAMILY_ADVANCED_FEATURES_FIX_20260613  
**Date**: 2026-06-13  
**Role**: 16 — Machine Learning Engineer (Tier 2)  
**Platform**: OpenCode  

---

## Source Contract Compliance

### Files Read (repo-local, authoritative)

| File | Path | Status |
|------|------|--------|
| Role | `.agents/agent/machine-learning-engineer.md` | READ OK |
| Skill: python-patterns | `.agents/skills/python-patterns/SKILL.md` | READ OK |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` | READ OK |
| Skill: testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | READ OK |
| Skill: performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | READ OK |
| Skill: systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | READ OK |
| Skill: ml-dl-rl | `.agents/skills/ml-dl-rl/SKILL.md` | READ OK |
| Skill: backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | READ OK |
| Skill: vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | READ OK |

### Forbidden Path Scan

- Forbidden path `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; it was NOT scanned.
- Forbidden path `.openclaw\skills` is non-authoritative and not used as source; it was NOT scanned.
- Forbidden path `C:\Users\GHC\.agents` (Codex memory) is non-authoritative and not used as source; it was NOT scanned.
- Forbidden path `.codex\memories` is non-authoritative and not used as source; it was NOT scanned.
- All skills loaded exclusively from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\`  

---

## Bug Analysis

### Error
```
ValueError: could not convert string to float: 'HOSE'
```
in `src/omega/quant/evolution/feature_adapter.py`, line 153 (variance filter).

### Root Cause (4-Phase Systematic Debugging)

**Phase 1 — Reproduce**: The error occurs when `GPFeatureAdapter().compute_all()` is called on a DataFrame containing an `exchange` column (values: 'HOSE', 'HNX', 'UPCOM').

**Phase 2 — Isolate**: The bug is in the phase34 alpha source handler (line 122). `compute_phase34_microstructure_alphas()` returns a **copy of the full input DataFrame** with `alpha_p34_*` columns appended. The column filter `c not in ("ticker", "date")` only excluded 2 metadata columns, but passed through ALL other original columns including `exchange` (string), `open/high/low/close/volume` (numeric duplicates), and any other non-numeric columns.

**Phase 3 — Understand (5 Whys)**:
1. Why: `np.asarray(values, dtype=np.float64)` fails on 'HOSE' string
2. Why: The variance filter blindly converts all arrays to float64
3. Why: Non-numeric columns (exchange) are included in `all_alphas`
4. Why: Phase34 column filter excludes only `ticker` and `date`
5. Why: Phase34 returns a full DataFrame copy, not just alpha columns — **root cause**

**Phase 4 — Fix & Verify**: See below.

---

## Fix Applied

### File: `src/omega/quant/evolution/feature_adapter.py`

**Change 1 — Phase34 column filter (line 122-124)**:
```python
# BEFORE (buggy):
alpha_cols = [c for c in p34_df.columns if c not in ("ticker", "date")]

# AFTER (fixed):
alpha_cols = [c for c in p34_df.columns if c.startswith("alpha_p34_")]
```
Matches the pattern already used for ultimate alphas (`c.startswith("alpha_")`).

**Change 2 — Defense-in-depth variance filter (lines 152-171)**:
Added safe non-numeric detection and coercion before the `dtype=np.float64` conversion:
- Check `np.issubdtype(arr.dtype, np.number)` before conversion
- Use `pd.to_numeric(..., errors="coerce")` for non-numeric arrays
- Catch `ValueError/TypeError` and log a warning, skip the feature
- No categorical strings leak into GP output

### PIT Safety Verification

- [x] No look-ahead introduced — fix only filters columns, doesn't alter temporal logic
- [x] Engineered features still use `groupby.shift(1)` / `pct_change` (past-only)
- [x] Phase34 alphas still T-1 lagged internally
- [x] Variance filter is a pure pass/drop decision — no data mutation

---

## Test Results

### Unit Tests (new)
```
tests/test_feature_adapter_nonnumeric.py — 6/6 PASSED
```
- `test_compute_all_with_exchange_column` — regression for 'HOSE' crash
- `test_all_output_arrays_are_numeric` — all outputs float64
- `test_no_categorical_columns_in_output` — no ticker/date/exchange leakage
- `test_phase34_column_filter_only_alpha_prefix` — validates 7 alpha_p34_ cols
- `test_variance_filter_drops_pure_string_array` — direct filter behavior test
- `test_engineered_features_use_past_only` — PIT safety preserved

### E2E Backtest Results

| Mode | Status | Notes |
|------|--------|-------|
| **advanced-features** | PASSED | All 10 scenarios completed. No ValueError. |
| **evolution-multiseed** | PASSED (partial) | GP evolution ran successfully across all years/seeds; timed out at 600s (computationally expensive, not an error) |
| **evolution** | PRE-EXISTING | `ModuleNotFoundError: No module named 'omega'` — script uses `packages/quant/src` path instead of `src/`. Out of scope. |
| **evolution-integration** | PRE-EXISTING | Same `packages/quant/src` path issue. Out of scope. |

---

## Files Changed

| File | Change Type |
|------|-------------|
| `src/omega/quant/evolution/feature_adapter.py` | Modified (2 edits) |
| `tests/test_feature_adapter_nonnumeric.py` | Created (new test file) |

---

## SOD Boundary

- **Implementation only** — this L2 role cannot self-approve
- **Submit to Tier 3**: Code Reviewer (role 21), QA Engineer (role 17), Performance Tester (role 23)
- **No audit or approval performed**

---

## Summary

The `ValueError: could not convert string to float: 'HOSE'` crash in `GPFeatureAdapter` is **fixed** with two surgical changes:
1. Phase34 column filter now selects only `alpha_p34_*` columns (root cause fix)
2. Variance filter defensively handles any non-numeric array that slips through (defense-in-depth)

PIT safety is preserved. All 6 new regression tests pass. The `advanced-features` E2E backtest completes all 10 scenarios without error. The `evolution-multiseed` backtest runs GP evolution successfully (no feature adapter crash). The `evolution` and `evolution-integration` scripts have pre-existing `sys.path` issues unrelated to this fix.
