# Code Review Audit Report

**Role**: Code Reviewer (Role 21)  
**Platform**: Codex L3 Independent Review  
**Date**: 2026-07-07  
**Session**: l3_role21_gp_vn_alphas_merge_direct_assign_plan_20260707  
**L2 Session**: l2_role9_gp_vn_alphas_merge_direct_assign_20260707  
**L2 Role**: Backend Engineer (Role 9)  
**Gate**: GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN  
**Submission**: .ly_state/session/gp_vn_alphas_merge_direct_assign_plan.md

---

## Code Quality Checks

### Alignment Safety
- [x] Both DataFrames explicitly sorted by ["ticker", "date"] with reset_index(drop=True)
- [x] Length assertion included: ssert len(result) == len(vn_features_df)
- [x] Ticker alignment assertion: ssert (result["ticker"].values == vn_features_df["ticker"].values).all()
- [x] Date alignment assertion: ssert (result["date"].values == vn_features_df["date"].values).all()

### Memory Optimization
- [x] Direct assignment via .values avoids merge overhead
- [x] Eliminates copy-on-write memory spike from merge operation
- [x] Targets root cause of ArrayMemoryError (1.50 GiB peak)

### Code Correctness
- [x] Preserves functional correctness (replaces merge with equivalent operation)
- [x] No data loss risk (assertions catch misalignment before assignment)
- [x] Maintains point-in-time (PIT) safety (no changes to T-1 lag logic)
- [x] Compatible with downstream processing

### Implementation Quality
- [x] Clear, self-documenting code with explanatory comments
- [x] Appropriate error handling via assertions
- [x] Follows pandas best practices
- [x] No code smells or anti-patterns

---

## Review Findings

### Technical Analysis

**Current Implementation** (line 346 of scripts/run_weekly_evolution.py):
`python
result = result.merge(vn_features_df[["ticker", "date"] + new_cols], 
                     on=["ticker", "date"], how="left")
`

**Problem Identified**:
- Merge operation causes pandas to copy consolidated column block manager
- Memory consumption doubles during merge (1.50 GiB peak → ArrayMemoryError)
- Both DataFrames already sorted identically by ["ticker", "date"]

**Proposed Solution**:
`python
result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
vn_features_df = vn_features_df.sort_values(["ticker", "date"]).reset_index(drop=True)
assert len(result) == len(vn_features_df), "Length mismatch between result and vn_features_df"
assert (result["ticker"].values == vn_features_df["ticker"].values).all(), "Ticker alignment mismatch"
assert (result["date"].values == vn_features_df["date"].values).all(), "Date alignment mismatch"
for col in new_cols:
    result[col] = vn_features_df[col].values
`

**Why This Works**:

1. **Sort Guarantees Deterministic Order**
   - Both DataFrames sorted by ["ticker", "date"] before assignment
   - eset_index(drop=True) ensures sequential integer indices
   - Eliminates dependency on groupby iteration order in compute_all_vn_alphas

2. **Three-Layer Assertion Defense**
   - Length assertion: catches row count mismatches
   - Ticker assertion: catches symbol ordering errors
   - Date assertion: catches temporal ordering errors
   - Fails fast before data corruption

3. **Memory Efficiency**
   - .values direct assignment avoids merge's block manager copy
   - No temporary DataFrames created
   - In-place column addition to existing DataFrame

4. **Edge Cases Handled**
   - ✅ Misaligned row counts → Length assertion fails
   - ✅ Different ticker order → Ticker assertion fails  
   - ✅ Different date order → Date assertion fails
   - ✅ Missing rows in vn_features_df → Length assertion fails
   - ✅ Extra rows in vn_features_df → Length assertion fails

**Verification of compute_all_vn_alphas Behavior**:
- Function sorts input: df_sorted = df.copy().sort_values(["ticker", "date"]).reset_index(drop=True) (line 10)
- Processes per-ticker groups and concatenates: pd.concat(processed_groups, ignore_index=True)
- **Critical**: Output order is NOT guaranteed to match input order due to groupby iteration
- **Solution**: Plan includes explicit re-sort of both DataFrames, making assumption safe

---

## Issues Found

**NONE** - The plan is technically sound and addresses all potential alignment risks.

---

## Verdict

**[APPROVED]**

The implementation plan correctly uses the sort + triple-assertion + direct assignment pattern. The solution:
- Eliminates the memory-heavy merge operation
- Provides robust alignment guarantees through three independent assertions
- Maintains functional correctness and PIT safety
- Includes appropriate verification plan (pytest tests + manual validation)

**SoD Boundary Verification**:
- ✅ L2 (backend-engineer) authored the plan
- ✅ L3 (code-reviewer) conducted independent audit
- ✅ No conflict of interest (writer ≠ auditor)
- ✅ READ-ONLY review completed (no code modifications by auditor)

**Recommendation**: Approve gate GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN for L1 implementation.

---

**Audit Completed**: 2026-07-07T12:25:17Z  
**Code Reviewer**: Role 21 (Codex L3)  
**Next Step**: L1 must run python scripts/sod_gate_enforcer.py after phase_gates.json update

---

## Independent Deep Review — Claude (Opus 4.8), 2026-07-07

**Scope**: Verify that `result.sort_values([...])` + `vn_features_df.sort_values([...])` followed by the three alignment assertions (length, ticker, date) correctly resolve the row-ordering mismatch risk before the `for col in new_cols: result[col] = vn_features_df[col].values` direct assignment.

### Data-flow verification (source-traced)

| Frame | How its order is established | Resulting order |
|---|---|---|
| `result` | `run_weekly_evolution.py:338` — `pd.concat(temp_dfs).sort_values(["ticker","date"]).reset_index(drop=True)` | ascending `[ticker, date]` |
| `vn_features_df` | `vn.py:28` internal `sort_values(["ticker","date"]).reset_index(drop=True)` → `vn.py:43` `groupby("ticker")` (default `sort=True`) with `vn.py:44` per-group `sort_values("date")` → `vn.py:255` `pd.concat(..., ignore_index=True)` | ascending `[ticker, date]` |

**Conclusion**: Both frames already end up sorted ascending by `[ticker, date]` under normal operation. The plan's explicit re-sort is therefore a **no-op on ordering in the happy path** but correctly makes the invariant *self-enforcing and deterministic* — it removes the implicit dependency on `groupby(sort=True)` and concat ordering. The three assertions then verify the invariant element-wise. **The row-ordering mismatch risk is correctly resolved**, and the assertions will PASS under normal operation (no spurious failures). `compute_all_vn_alphas` takes `df.copy()`, so re-sorting `result` afterward is safe (the frame handed to the function is not mutated).

### Findings (hardening — not defects in the ordering logic)

1. **`assert` is stripped under `python -O` / `PYTHONOPTIMIZE` (Medium).** All three safety checks are bare `assert` statements. If the evolution script is ever launched with `-O`, the alignment guarantees silently vanish and misalignment would corrupt features/labels without error. For a production data pipeline, prefer an explicit guard that always runs, e.g. `if len(result) != len(vn_features_df): raise ValueError(...)` (and likewise for ticker/date). Recommend before L1 merge.

2. **Duplicate `(ticker, date)` keys are not fully covered by the ticker/date assertions (Low / informational).** `sort_values` defaults to a non-stable algorithm (quicksort). If duplicate `(ticker, date)` rows ever existed, the two frames could order the duplicates differently while the ticker and date assertions still compare *equal* (the keys match) — allowing silent misalignment of the OHLCV/feature payload. This is **not a regression**: the original `merge(how="left")` already assumes uniqueness (duplicate keys would cause a row-explosion cartesian product). For a daily OHLCV panel `(ticker, date)` should be unique. Optional hardening: assert `not result.duplicated(["ticker","date"]).any()` once, which closes the gap the ticker/date assertions leave open.

3. **75-column loop assignment fragments the block manager (Minor perf).** `for col in new_cols: result[col] = ...` inserts ~75 columns one at a time, which pandas may flag (`PerformanceWarning: DataFrame is highly fragmented`) and which repeatedly rebuilds blocks. This still has a lower *peak* than merge's full-frame copy (so the memory goal holds), but a single `result = pd.concat([result, vn_features_df[new_cols]], axis=1)` after the assertions + `reset_index(drop=True)` would be cleaner and reduce churn. Not blocking.

4. **Line 345 `drop(columns=...)` becomes redundant (Nit).** With direct `result[col] = ...` assignment, the pre-drop of existing `new_cols` is no longer needed (assignment overwrites). Harmless if left in place; the plan only replaces line 346 so it stays.

### Verdict

**[APPROVED]** — The core mechanism (sort both frames + triple element-wise assertion + direct `.values` assignment) **correctly resolves the row-ordering mismatch risk** and preserves functional correctness and PIT safety. The findings above are robustness/perf hardening, not correctness defects in the alignment logic. Strongly recommend adopting Finding #1 (replace bare `assert` with an always-on guard) before the L1 implementation, since assert-stripping is the one scenario that could reintroduce silent corruption. Findings #2–#4 are optional.

**Independent Review Completed**: 2026-07-07 — Claude (Opus 4.8), verifier
