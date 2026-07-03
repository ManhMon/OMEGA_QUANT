# L2 Report - Role 9 Backend Engineer

- Gate: `GP_V3_LABEL_AND_SPEED_20260703`
- Scope: `src/omega/quant/evolution/genetic_engine.py`
- Task: Fix neutralization cache NaN/Inf row alignment bug

## Repo-Local Sources Read

- Role: `.agents/agent/backend-engineer.md`
- Skill: `.agents/skills/clean-code/SKILL.md`
- Skill: `.agents/skills/testing-patterns/SKILL.md`
- Skill: `.agents/skills/systematic-debugging/SKILL.md`
- Skill: `.agents/skills/nodejs-best-practices/SKILL.md`
- Skill: `.agents/skills/api-patterns/SKILL.md`
- Skill: `.agents/skills/database-design/SKILL.md`

## Forbidden Path Scan

- No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`
- No authoritative reliance on `.openclaw\skills`
- No authoritative reliance on `C:\Users\GHC\.agents`
- No authoritative reliance on `.codex\memories`

## Root Cause

- Cached neutralization design matrix was built on rows with finite `mcap` and non-null `sector`.
- Per-date neutralization then filtered `alpha` again for finite rows, but reused the unfiltered cached design matrix.
- `np.linalg.lstsq(design, alpha_valid)` could receive mismatched row counts when `alpha` contained `NaN`/`Inf`, causing the date slice to be skipped.

## Change

- Kept cache format unchanged.
- In `_neutralize_cross_section`, compute `valid_rows = cached_valid & np.isfinite(alpha_slice)`.
- Filter `alpha` with `valid_rows`.
- Filter cached `design` with `valid_rows[cached_valid]` before `lstsq`.
- Write residuals back only to `valid_rows`.
- Added in-file assert-based regression self-check covering `NaN`/`Inf` alpha alignment.

## Verification

- `python -m py_compile "src/omega/quant/evolution/genetic_engine.py"`
- `python -c "from src.omega.quant.evolution.genetic_engine import _self_check_neutralize_cross_section_nan_alignment; _self_check_neutralize_cross_section_nan_alignment()"`
- `python -c "import numpy as np; from src.omega.quant.evolution.genetic_engine import _neutralize_cross_section; alpha=np.array([1.0, np.nan, 3.0, np.inf, 2.0]); mcap=np.array([10.,11.,12.,13.,14.]); sector=np.array(['A','A','B','B','C'], dtype=object); date=np.array(['2026-01-01']*5, dtype=object); out=_neutralize_cross_section(alpha,mcap,sector,date); print(out); print(np.isfinite(out[[0,2,4]]).all(), np.isnan(out[1]), np.isinf(out[3]))"`

## Result

- Row alignment preserved for cached design vs finite alpha rows.
- Finite rows remain neutralized.
- `NaN` and `Inf` alpha entries remain untouched instead of breaking the date regression.
