# Code Review Audit Report
**Role**: code-reviewer (Role 21)
**Date**: 2026-06-25T22:36:36.7627972+07:00
**Gate**: CONCENTRATED_LONG_ONLY_TCOST_20260625
**Submission**: `scripts/backtest_hybrid_regime.py`, `tests/phase35/test_hybrid_regime_backtest_perf.py`
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [APPROVED]

## Repo-Local Skill Source Evidence
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Forbidden Path Scan
No authoritative reliance on forbidden paths.
- `.gemini\antigravity-ide\scratch\ag-kit` not used as source
- `.openclaw\skills` not used as source
- `C:\Users\GHC\.agents` not used as source
- `.codex\memories` not used as source

## SOD Checks
- Writer != Auditor verified: L2 role_id `14` != L3 role_id `21`
- L3 remained read-only on production code
- L2 report lists repo-local role/skill files and forbidden-path scan

## Verification
- `pytest tests/phase35/test_hybrid_regime_backtest_perf.py -q` -> `43 passed`
- Verified that concentration invariant holds across the full overlay stack in `test_scenario_concentration_invariant` under weight smoothing.

## Findings & Resolution
1. **[RESOLVED] `scripts/backtest_hybrid_regime.py`**
   `LongOnlyConcentratedOverlay` was moved after `WeightSmoothingOverlay` in both Baseline and Hybrid stacks. This guarantees that weight smoothing does not leak previously-dropped names back into the final weights. Final portfolios strictly preserve the `top_k` invariant.
2. **[RESOLVED] `tests/phase35/test_hybrid_regime_backtest_perf.py`**
   Added a new scenario-level test `test_scenario_concentration_invariant` that exercises the full stack from `build_scenario_overlays()` and asserts the final weights preserve the concentration invariant (number of active assets <= `top_k`). Test runs and passes.

## PIT / Scope
- No new look-ahead path found in the reviewed changes.
- Audit scope limited to the two requested files. Workspace contains unrelated dirty files outside scope.