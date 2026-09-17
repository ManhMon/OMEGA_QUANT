# L2 Report - role14 data-scientist

- Gate: `HYBRID_REGIME_WEIGHT_SMOOTHING_FIX_20260701`
- Scope: `src/omega/quant/pipeline_v2.py`, `tests/test_pipeline_v2.py`
- Session: `l2_role14_weight_smoothing_fix_20260701`

## Repo-local role/skill files read

- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden path scan result

- No authoritative role/skill loads from forbidden paths.
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

## Changes

- Updated `src/omega/quant/pipeline_v2.py` `WeightSmoothingOverlay` to match `src/omega/quant/pipeline/overlays/weight_smoothing.py` behavior.
- Added `exposure_blend: float = 0.0` parameter.
- Changed default `ema_alpha` from `0.2` to `0.05`.
- Removed unconditional exposure rescale.
- Added conditional blend logic:
  - `0.0` -> pure EMA smoothing, no rescale
  - `1.0` -> old full-rescale behavior
  - `(0, 1)` -> partial blend between smoothed and target exposure
- Updated log line to include `exposure_blend`.

## Regression coverage

- Updated `tests/test_pipeline_v2.py`.
- Added test: default non-rescaled EMA keeps smoothed exposure at `0.5` in a 2-bar decay case.
- Added test: `exposure_blend=1.0` preserves old full-rescale behavior.

## Verification

- Command: `pytest tests/test_pipeline_v2.py`
- Result: `11 passed, 4 warnings`
- Status: green

## Notes

- Implementation limited to requested fix + regression coverage.
- No audit/approval performed.
