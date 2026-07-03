# L2 Implementation Report - l2_role14_hybrid_regime_expected_alpha_fix_20260626

- Role: `14 data-scientist`
- Gate: `HYBRID_REGIME_EXPECTED_ALPHA_FIX_20260626`
- Scope: `src/omega/quant/pipeline_v2.py`, `tests/test_pipeline_v2.py`
- Boundary: implementation/test only; no audit/approval performed.

## Repo-Local Skill Source Evidence

Read from `REPO_AGENT_ROOT`:
- `.agents/agent/data-scientist.md`

Read from `REPO_SKILL_ROOT`:
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan Result

No authoritative reliance on forbidden paths. All forbidden paths were treated as non-authoritative and not used as role/skill sources:
- `.gemini\antigravity-ide\scratch\ag-kit` not used as source
- `.openclaw\skills` not used as source
- `C:\Users\GHC\.agents` not used as source
- `.codex\memories` not used as source

## Root Cause

`_build_expected_alpha_frame(...)` normalized signal conviction using the median of the full cross-section after inactive names had already been converted to `0.0` in `pivot_sig`.

- Inactive symbols were entering the denominator as zero-strength names.
- That diluted the median used for expected-alpha normalization.
- Result: active names received inflated expected alpha relative to the actually tradeable cross-section.

## Changes

1. `src/omega/quant/pipeline_v2.py`
- Added optional `active_mask` to `_build_expected_alpha_frame(...)`.
- When `active_mask` is present, the normalization denominator uses only active names for each date.
- Inactive names are zeroed after normalization so they cannot contribute synthetic expected alpha.
- Built `active_signal_mask` from the pre-`fillna` signal pivot and passed it into `_build_expected_alpha_frame(...)`.
- PIT behavior unchanged: trailing realized vol still uses prior data only via `.shift(1)`.

2. `tests/test_pipeline_v2.py`
- Added regression test covering inactive-name dilution in expected-alpha normalization.
- Added companion test confirming legacy behavior is unchanged when no `active_mask` is supplied.

## Verification

Command run:

```powershell
pytest tests/test_pipeline_v2.py -q
```

Result:

```text
13 passed, 4 warnings in 7.64s
```

## Notes

- `checklist.py` and `verify_all.py` were requested by role guidance but are not present in this repo, so they could not be executed.
- No files outside scoped source/tests and this L2 report were modified.
