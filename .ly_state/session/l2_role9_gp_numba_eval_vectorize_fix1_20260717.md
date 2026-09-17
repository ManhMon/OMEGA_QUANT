## L2 Report

- Session: `l2_role9_gp_numba_eval_vectorize_fix1_20260717`
- Role: `9 backend-engineer`
- Gate: `gp_numba_eval_vectorize`
- Scope:
  - `src/omega/quant/evolution/genetic_programming.py`
  - `tests/test_gp_vectorized_eval.py`

## Repo-Local Skill Source Evidence

- Role file read:
  - `.agents/agent/backend-engineer.md`
- Skill files read:
  - `.agents/skills/nodejs-best-practices/SKILL.md`
  - `.agents/skills/api-patterns/SKILL.md`
  - `.agents/skills/database-design/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan Result

- No authoritative reliance on forbidden paths.
- Not read for implementation:
  - `.gemini\antigravity-ide\scratch\ag-kit`: not used as source (non-authoritative, forbidden path scan evidence only)
  - ` (non-authoritative, forbidden path scan evidence only).openclaw\skills`
  - `C:\Users\GHC\.agents`: not used as source (non-authoritative, forbidden path scan evidence only)
  - `.codex\memories`: not used as source (non-authoritative, forbidden path scan evidence only)

## Changes

1. Fixed `_rank_transform` NaN parity.
   - Old behavior ranked `NaN` values via `scipy.stats.rankdata`.
   - New behavior leaves `NaN` positions as `NaN`, ranks only non-NaN values, divides by non-NaN count.
   - Matches `pd.Series.rank(pct=True, method="average")` semantics.

2. Fixed `_precompute_target_ranks` mask parity.
   - Old behavior used `np.isfinite(target)`, dropping `+/-Inf`.
   - New behavior uses `~np.isnan(target)`, preserving `+/-Inf` like `DataFrame.dropna()`.

3. Added regression tests.
   - `test_rank_nan_parity`
   - `test_cached_mask_inf_parity`

## Test Results

1. `pytest tests/test_gp_vectorized_eval.py -v`
   - Result: `6 passed`

2. `pytest tests/test_diverse_alpha_evolution_parallel.py -v`
   - Result: `11 passed`

## Notes

- Warnings observed during pytest only; no test failures.
- No other production files changed.
