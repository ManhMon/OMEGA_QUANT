# L2 Report: HYBRID_REGIME_OOM_FIX_20260624

- Date: 2026-06-24
- Role: 9 backend-engineer
- Scope: `scripts/backtest_hybrid_regime.py`
- Gate: `HYBRID_REGIME_OOM_FIX_20260624`
- Status: IMPLEMENTED

## Repo-Local Skill Source Evidence

- Role spec read: `.agents/agent/backend-engineer.md`
- Skill files read:
  - `.agents/skills/nodejs-best-practices/SKILL.md`
  - `.agents/skills/api-patterns/SKILL.md`
  - `.agents/skills/database-design/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan Result

- No authoritative role/skill reads from forbidden paths.
- Not read; all forbidden paths below are non-authoritative:
  - `.gemini\antigravity-ide\scratch\ag-kit` - non-authoritative
  - `.openclaw\skills` - non-authoritative
  - `C:\Users\GHC\.agents` - non-authoritative
  - `.codex\memories` - non-authoritative

## Change Summary

- `train_fold_models()` hot path updated to build lag-feature blocks with single `pd.concat(...)` calls instead of repeated column growth patterns.
- Removed redundant temporary `.copy()` of full lag-column blocks before concat.
- Kept PIT-safe NaN handling unchanged.

## File Changes

- `scripts/backtest_hybrid_regime.py:796-802`
  - `temp_train` now appends `train_lag_df[lag_col_names_all]` via one `pd.concat(...)`.
- `scripts/backtest_hybrid_regime.py:884-894`
  - `ridge_train` now appends `temp_train[lag_col_names]` via one `pd.concat(...)`.

## Rationale

- Repeated pandas column insertion/block growth can fragment memory and amplify allocation pressure.
- Single-block concat reduces intermediate allocations in the per-fold multiprocessing path, lowering risk of `ArrayMemoryError` / OOM on Windows.

## Verification

- Syntax:
  - `python -m py_compile "scripts/backtest_hybrid_regime.py"`
- Targeted tests:
  - `pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k train_fold_models`
  - Result: `1 passed, 40 deselected`

## Notes

- `scripts/backtest_hybrid_regime.py` already had unrelated in-flight edits in the worktree before this task. This L2 change was limited to the two memory hot-path blocks above.
- No audit/approval performed. Ready for L3 review.
