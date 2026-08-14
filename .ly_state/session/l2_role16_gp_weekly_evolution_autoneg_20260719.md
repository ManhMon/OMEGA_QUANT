# L2 Report - gp_weekly_evolution_autoneg

- Session ID: `l2_role16_gp_weekly_evolution_autoneg_20260719`
- Role: `16 machine-learning-engineer`
- Gate: `gp_weekly_evolution_autoneg`
- Scope:
  - `scripts/run_weekly_evolution.py`
  - `tests/test_evolution_metric_migration.py`

## Repo-Local Skill Source Evidence

- Role file read:
  - `.agents/agent/machine-learning-engineer.md`
- Skill files read:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/ml-dl-rl/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan

- Non-authoritative paths not used as sources:
  - `.gemini\antigravity-ide\scratch\ag-kit`
  - `.openclaw\skills`
  - `C:\Users\GHC\.agents`
  - `.codex\memories`

## Changes

- Added negative-IC auto-flip in `evaluate_and_promote()`.
- Re-evaluate metrics after flipping predictions by `-1.0`.
- Preserve positive promoted metrics after flip.
- Register promoted flipped formulas as `neg(<original_formula>)` in bridge payload and serialized result.
- Added regression test covering negative IC flip, re-evaluation, promotion, and `neg(...)` formula output.

## Verification

- `pytest tests/test_evolution_metric_migration.py`
  - Result: `8 passed, 6 warnings in 6.03s`
- Repo-root compliance scripts:
  - `checklist.py`: not present
  - `verify_all.py`: not present

## Notes

- PIT behavior unchanged: only post-generation test-set prediction sign is flipped; labels, chronology, embargo flow unchanged.
- Promotion threshold logic still requires positive post-flip `signal_pnl_score` and non-trivial IC magnitude.
