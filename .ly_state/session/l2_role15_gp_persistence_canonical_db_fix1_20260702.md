# L2 Implementation Report

- Role: `15 data-engineer`
- Gate: `GP_PERSISTENCE_CANONICAL_DB_FIX1_20260702`
- Date: `2026-07-02`
- Scope:
  - `scripts/precompute_all_features.py`
  - `scripts/genetic_alpha_evolution_v3.py`
  - `src/omega/core/registry/persistence.py`
  - `tests/data_test_gp_persistence_canonical_db.py`

## Repo-Local Files Read
- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `.ly_state/session/audit_reports/role21_gp_persistence_canonical_db_20260702.md`
- `scripts/precompute_all_features.py`
- `scripts/genetic_alpha_evolution_v3.py`
- `src/omega/core/registry/persistence.py`
- `src/omega/core/db/persistence.py`
- `tests/data_test_gp_persistence_canonical_db.py`

## Forbidden Path Scan
- Scoped source/test files scanned for non-authoritative references:
  - `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative check: not present, no reliance)
  - `.openclaw\skills` (non-authoritative check: not present, no reliance)
  - `C:\Users\GHC\.agents` (non-authoritative check: not present, no reliance)
  - `.codex\memories` (non-authoritative check: not present, no reliance)
- Result: no matches in scoped source/test files; no authoritative reliance on forbidden paths.

## Root Cause
- Canonical DB consumer path loaded every `ready` row for `genetic_alpha_v3_rank_*`.
- `compile_and_execute_gp_alphas()` then used `nsmallest(TOP_GP_EXPRESSIONS, "rank")` directly.
- Historical reruns left multiple `ready` rows for the same rank/name, so duplicate rank 1 rows could occupy top-N and push out rank 3.

## Fix Implemented
- Chose minimal safe consumer-side fix in `scripts/precompute_all_features.py`.
- `_load_gp_registry_rows()` now:
  - includes `created_at`
  - sorts newest-first by `created_at`/`version`
  - drops duplicates by `name` keeping the latest row
  - returns deduplicated rows sorted by `rank`
- Rationale: preserves DB as canonical source of truth, avoids mutating historical registry state/status, fixes active top-N selection at read time.

## Tests
- Added regression test: `test_precompute_loads_latest_ready_row_per_rank`
- Repro case: ready rows with ranks `1, 1, 2, 3`
- Assertion: canonical consumer rows resolve to ranks `1, 2, 3` using latest row for duplicated rank/name.

## Verification
- `pytest tests/data_test_gp_persistence_canonical_db.py -q` -> passed
- `python -m py_compile scripts/precompute_all_features.py scripts/genetic_alpha_evolution_v3.py src/omega/core/registry/persistence.py tests/data_test_gp_persistence_canonical_db.py` -> passed

## Files Changed
- `scripts/precompute_all_features.py`
- `tests/data_test_gp_persistence_canonical_db.py`

## Notes
- No audit/approval performed.
- `scripts/genetic_alpha_evolution_v3.py` and `src/omega/core/registry/persistence.py` were inspected but did not require code changes for this minimal fix.
