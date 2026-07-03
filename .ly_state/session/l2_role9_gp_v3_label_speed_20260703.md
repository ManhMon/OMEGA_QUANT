# L2 Report - GP_V3_LABEL_AND_SPEED_20260703

## Role
- role_id: 9
- role_name: backend-engineer
- tier: 2
- platform: OpenCode

## Scope
- `src/omega/quant/evolution/genetic_engine.py`

## Repo-local sources read
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden path scan
- Non-authoritative paths not used as sources: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`

## Changes
- Log label fix: generation progress log now prints `Fold_IR=` instead of misleading `IC=`.
- Neutralization cache: added per-date design-matrix cache via `NEUTRALIZATION_CACHE_KEY` + `_build_neutralization_cache()`.
- Reuse path: `_neutralize_cross_section()` now accepts optional cache and reuses prebuilt date matrices.
- Fold IR fast mode: added `GPConfig.time_folds_fast_mode: bool = False`; when enabled, `_compute_time_fold_ir()` uses 2 folds.
- Profiling logs: added `logger.debug(...)` timing around `_compute_time_fold_ir()` and `_neutralize_cross_section()`.
- Bug fix during verification: fold feature slicing now ignores scalar/object cache entries safely.

## Verification
- `python -m py_compile "src/omega/quant/evolution/genetic_engine.py"` -> PASS
- Synthetic smoke: `python ".ly_state/session/tmp_gp_v3_label_speed_smoke_20260703.py"` -> PASS
- Smoke assertions:
  - cached neutralization == uncached neutralization
  - `_compute_time_fold_ir()` returns finite value with cache present
  - evolution log contains `Fold_IR=` and does not contain `IC=`

## Evidence
- Smoke output included: `SMOKE_OK cache_dates=6 fold_ir=3.043478`

## Notes
- `time_folds_fast_mode` defaults off for back-compat; enable explicitly for ~33% fewer fold evaluations.
- Timing logs are `DEBUG` level only.
