# L2 Report - GP Production Run Bug Fixes

- Session: `l2_role16_gp_prod_run_bugs_20260704`
- Gate: `GP_PRODUCTION_RUN_PLAN_REVIEW`
- Role: `16 machine-learning-engineer`
- Scope: `scripts/genetic_alpha_evolution_v3.py`, `tests/test_genetic_alpha_evolution_v3_gate6.py`

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
- `.ly_state/session/gp_production_plan.md`
- `scripts/genetic_alpha_evolution_v3.py`
- `tests/test_genetic_alpha_evolution_v3_gate6.py`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit`: `False` via `Test-Path`; non-authoritative; not used.
- `.openclaw\skills`: `False` via `Test-Path`; non-authoritative; not used.
- `C:\Users\GHC\.agents`: `True` via `Test-Path`; non-authoritative; not used.
- `.codex\memories`: `False` via `Test-Path`; non-authoritative; not used.

## Changes
- Gate 6 pass/fail now includes permutation p-value hard fail; no warning-only path.
- Registration moved behind `validate_and_register_models(...)` so failed Gate 6 cannot pollute registry DB.
- Split-window date lookup now uses `np.searchsorted` with clamped bounds instead of fragile `dates.index(...)`.
- GP export sort now uses stable 2-pass ordering: rank asc, version desc within rank.
- Hall-of-fame ranking now uses unrounded `val_IC_daily_raw` with `id` tie-break for deterministic ordering.

## Verification
- `pytest tests/test_genetic_alpha_evolution_v3_gate6.py` -> `10 passed`
- `pytest tests/test_genetic_alpha_evolution_v3.py tests/test_genetic_alpha_evolution_v3_gate6.py` -> `15 passed`

## Regression Coverage Added
- `test_stable_sorting`
- `test_searchsorted_split_handling`
- `test_no_register_on_gate_fail`
- `test_p_value_hard_fail`
- `test_unrounded_val_ic_sorting`

## Boundary
- L2 implementation only. No audit. No approval.
