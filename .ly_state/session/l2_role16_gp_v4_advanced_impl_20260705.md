# L2 Report: GP_V4_ADVANCED_IMPLEMENTATION

## Role
- role_id: 16
- role_name: machine-learning-engineer
- tier: 2
- platform: OpenCode
- sod_boundary: implementation-only, test required, no self-approval, submit to Tier3

## Repo-Local Files Read
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## Declared Skills
- python-patterns
- clean-code
- testing-patterns
- performance-profiling
- systematic-debugging
- ml-dl-rl
- backtesting-pit-safety
- vietnam-market-data

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` is not present and non-authoritative
- `.openclaw\skills` not read and non-authoritative
- `C:\Users\GHC\.agents` not read and non-authoritative
- `.codex\memories` not read and non-authoritative

## Scope
- `scripts/genetic_alpha_evolution_v4.py`
- `tests/test_genetic_alpha_evolution_v4.py`

## Changes
- `_group_row_indices_by_date(date_arr)` cache key hardened to `(id(date_arr), len(date_arr), first_val, last_val)`.
- `_group_row_indices_by_date(date_arr)` now clears `_DATE_GROUPS_CACHE` when cache size exceeds 500.
- Added `_get_date_groups(...)` helper to reuse cached `__date_groups__` only when bounds fit current `date_arr`; otherwise recompute and refresh.
- `_optimized_neutralize_cross_section(...)` now reads/writes `neutralization_cache['__date_groups__']` when `neutralization_cache` is a dict.
- `_optimized_batch_neutralize_cross_section(...)` now reads/writes `neutralization_cache['__date_groups__']` when `neutralization_cache` is a dict.
- `_build_fold_views(...)` now copies neutralization-cache dicts per fold and strips stale `__date_groups__` entry to avoid cross-fold index reuse.
- Updated parity cache assertion for new key shape.
- Added regression test covering shared `__date_groups__` storage on neutralization cache.

## Test Execution
- `pytest tests/test_genetic_alpha_evolution_v4.py` -> passed (`15 passed`)
- `pytest -q` -> passed (`PYTEST_EXIT=0`)

## Notes
- Root cause: CPython memory address reuse + stale cached date-group indices crossing array/fold boundaries.
- Fix preserves reuse benefits while validating cache applicability to current row domain.
