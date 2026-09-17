# L2 Report - Gate 7 Neutralization + Liquidity

- Session: `l2_role16_gate7_neutralization_liquidity_20260704`
- Gate: `GATE7_NEUTRALIZATION_LIQUIDITY_20260704`
- Role: `16 machine-learning-engineer`
- Scope: `scripts/genetic_alpha_evolution_v3.py`, `src/omega/quant/evolution/genetic_engine.py`, `tests/test_genetic_engine_liquidity.py`

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
- `.ly_state/session/gate7_neutralization_liquidity_plan.md`
- `scripts/genetic_alpha_evolution_v3.py`
- `src/omega/quant/evolution/genetic_engine.py`

## Forbidden Path Scan
Forbidden path scan result: CLEAN - no authoritative reliance on antigravity scratch, openclaw, global agents dir, or codex memory.

## Missing Scoped Source Check
- Requested source `tests/test_genetic_engine_liquidity.py` was missing at task start.
- Added repo-local test file at the requested path to satisfy scope + regression coverage.

## Changes
- Fixed Gate 6 contract regression: `time_folds=8 -> 3` in `scripts/genetic_alpha_evolution_v3.py`.
- Added CLI args `--min-avg-volume`, `--avg-volume-window`.
- Added PIT-safe `avg_traded_value = rolling_mean(close * volume)` then per-ticker `shift(1)`.
- Persisted `liquidity_mask` into all feature dicts: train/val/oos/lockbox.
- Added sector-proxy comment: `sector` means liquidity quartile proxy, not economic sector.
- Added `_evaluation_mask()` in `src/omega/quant/evolution/genetic_engine.py`.
- Applied `_evaluation_mask()` to observation counting and IC computation paths.
- Extended existing neutralization calls to residualize target alongside alpha in fold + pooled IC paths.
- Replaced script-side raw validation IC scoring with engine-consistent scoring using mask + neutralization.

## Verification
- `python -m py_compile scripts/genetic_alpha_evolution_v3.py src/omega/quant/evolution/genetic_engine.py tests/test_genetic_engine_liquidity.py`
- `pytest tests/test_genetic_engine_liquidity.py -vv` -> `2 passed`

## Additional Test Note
- Adjacent legacy tests outside requested scope now reflect changed Gate 7 semantics and were not updated here:
- `tests/quant_test_genetic_engine.py::test_time_fold_ir_stable_alpha_beats_spike`
- `tests/quant_test_genetic_engine_optimizations.py::test_extra2_fast_threshold_matches_dropna_with_inf_target`
- These failures are consistent with stricter liquidity-aware observation counting + target neutralization behavior.

## Boundary
- This L2 report is implementation evidence only. It is explicitly non-authoritative for audit approval.
