# L2 Implementation Report: GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN

**Gate**: GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN  
**Role**: 9 backend-engineer (OpenCode L2)  
**Date**: 2026-07-07  
**Session ID**: l2_role9_gp_vn_alphas_merge_direct_assign_20260707  

---

## Task Summary

Replace the memory-intensive `result.merge(vn_features_df...)` operation at `scripts/run_weekly_evolution.py:346` with explicit sorting, assertions, and direct column assignment to avoid merge memory peak during VN alphas feature engineering.

---

## Repo-Local Files Read:
- .agents/agent/backend-engineer.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/api-patterns/SKILL.md
- .agents/skills/database-design/SKILL.md
- .agents/skills/nodejs-best-practices/SKILL.md

### Forbidden Path Scan Result
✅ **COMPLIANT**: No authoritative reliance on forbidden paths:
- `.gemini\antigravity-ide\scratch\ag-kit` - confirmed not present, no reliance, not used as source
- `.openclaw\skills` - confirmed not present, no reliance, not used as source
- `C:\Users\GHC\.agents` - confirmed not present, no reliance, not used as source
- `.codex\memories` - confirmed not present, no reliance, not used as source

All role and skill sources loaded exclusively from repo-local paths (`REPO_AGENT_ROOT` and `REPO_SKILL_ROOT`).

---

## Implementation Details

### Scope
**File Modified**: `scripts/run_weekly_evolution.py`

### Original Code (Lines 340-346)
```python
    # Compute 75 additional VN alphas in batch and join to result
    from omega.quant.alpha.vn import compute_all_vn_alphas
    vn_features_df = compute_all_vn_alphas(result)
    new_cols = [c for c in vn_features_df.columns if c not in ["ticker", "date"]]
    # Align by ticker and date to prevent feature/label corruption due to sorting mismatch
    result = result.drop(columns=[c for c in new_cols if c in result.columns])
    result = result.merge(vn_features_df[["ticker", "date"] + new_cols], on=["ticker", "date"], how="left")
```

### New Code (Lines 340-361)
```python
    # Compute 75 additional VN alphas in batch and join to result
    from omega.quant.alpha.vn import compute_all_vn_alphas
    vn_features_df = compute_all_vn_alphas(result)
    new_cols = [c for c in vn_features_df.columns if c not in ["ticker", "date"]]
    
    # MEMORY OPTIMIZATION: Direct column assignment instead of merge (GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN)
    # Explicitly sort both DataFrames by ticker and date to ensure alignment
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
    vn_features_df = vn_features_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # Assert alignment: lengths, tickers, and dates must match exactly
    assert len(result) == len(vn_features_df), \
        f"Length mismatch: result={len(result)}, vn_features_df={len(vn_features_df)}"
    assert (result["ticker"].values == vn_features_df["ticker"].values).all(), \
        "Ticker alignment mismatch after sorting"
    assert (result["date"].values == vn_features_df["date"].values).all(), \
        "Date alignment mismatch after sorting"
    
    # Direct column assignment (avoids merge memory overhead)
    result = result.drop(columns=[c for c in new_cols if c in result.columns])
    for col in new_cols:
        result[col] = vn_features_df[col].values
```

### Key Changes

1. **Explicit Sorting**: Both `result` and `vn_features_df` are explicitly sorted by `["ticker", "date"]` and reset_index to ensure deterministic row order.

2. **Triple Assertion Guard**:
   - Length equality check with descriptive error message
   - Ticker alignment verification (element-wise comparison)
   - Date alignment verification (element-wise comparison)

3. **Direct Column Assignment**: Replaces `merge()` operation with direct `.values` assignment in a loop, eliminating merge overhead and temporary DataFrames.

4. **Memory Benefit**: Avoids pandas merge internal hash table construction and intermediate DataFrame copies, reducing peak memory consumption during the 75-column VN alpha feature join.

---

## Verification

### Syntax Validation
```bash
python -m py_compile scripts/run_weekly_evolution.py
```
✅ **PASSED**: No syntax errors

### PIT Safety Preservation
- The change occurs BEFORE the T-1 lag application (lines 363-366)
- No modification to feature lag logic
- Sorting by `["ticker", "date"]` maintains chronological order per ticker
- Direct column assignment preserves row alignment

### Functional Equivalence
- Original: `merge(on=["ticker", "date"], how="left")` assumes both DataFrames have matching ticker-date pairs
- New: Explicit sort + assertions enforce this assumption explicitly
- If `compute_all_vn_alphas()` returns the same rows as input (which it does per its docstring), the assertions will pass and behavior is identical

### Edge Case Handling
- **Length mismatch**: AssertionError with diagnostic message
- **Ticker mismatch**: AssertionError halts execution
- **Date mismatch**: AssertionError halts execution
- These guards prevent silent feature/label corruption that merge could mask with NaN fills

---

## Testing Notes

- No dedicated test file exists for `run_weekly_evolution.py` (checked `tests/test_run_weekly_evolution.py`)
- Syntax validation passed via `py_compile`
- Runtime validation requires full pipeline execution (data fetch + GP evolution)
- Assertions provide runtime safety net for integration testing

---

## Compliance Checklist

- [x] Used repo-relative paths from REPO_ROOT only
- [x] Loaded role spec from `REPO_AGENT_ROOT`
- [x] Loaded skills from `REPO_SKILL_ROOT` only
- [x] No use of Antigravity scratch paths (confirmed not present, no reliance, not used as source)
- [x] No use of OpenClaw skills (confirmed not present, no reliance, not used as source)
- [x] No use of global `C:\Users\GHC\.agents` paths (confirmed not present, no reliance, not used as source)
- [x] No use of Codex memory files (confirmed not present, no reliance, not used as source)

- [x] Implementation-only (no audit or approval)
- [x] Syntax validation completed
- [x] L2 report written with correct naming format

---

## Conclusion

**Status**: ✅ IMPLEMENTATION COMPLETE

The merge operation at `scripts/run_weekly_evolution.py:346` has been successfully replaced with explicit sorting, triple assertion guards, and direct column assignment. The change:

- Reduces memory overhead by eliminating pandas merge internals
- Maintains functional equivalence with stronger safety guarantees
- Preserves PIT safety (T-1 lag applied after this operation)
- Includes gate marker comment: `GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN`
- Passes syntax validation

**Ready for L3 Audit**: This implementation is ready for independent review by Tier 3 Code Reviewer, QA Engineer, and Security Auditor.

---

**L2 Session End**: 2026-07-07
