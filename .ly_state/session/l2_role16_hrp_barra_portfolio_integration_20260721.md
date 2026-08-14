# L2 Report: hrp_barra_portfolio_integration

- Session ID: `l2_role16_hrp_barra_portfolio_integration_20260721`
- Role: `16 machine-learning-engineer`
- Gate: `hrp_barra_portfolio_integration`
- Scope:
  - `src/omega/quant/portfolio/barra_factor_model.py`
  - `src/omega/quant/portfolio/hrp_optimizer.py`
  - `src/omega/quant/portfolio/execution_sim.py`
  - `tests/test_hrp_barra_portfolio.py`

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

## Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit`: not used as authoritative source
- `.openclaw\skills`: not used as authoritative source
- `C:\Users\GHC\.agents`: not used as authoritative source
- `.codex\memories`: not used as authoritative source

## Changes Implemented

1. `src/omega/quant/portfolio/execution_sim.py`
   - Clipped `returns_window` inside `build_hrp_barra_portfolio` to `index <= as_of_date - 1 day` before covariance estimation.
   - Effect: future returns on `as_of_date` cannot leak into HRP covariance.

2. `src/omega/quant/portfolio/hrp_optimizer.py`
   - Updated `_fallback_rank_weights` to use `w_val = min(max_position, 0.5 / half)`.
   - Changed fallback normalization rule: only renormalize when gross exposure is `>= 1.0`.
   - Effect: fallback path preserves 10% max-position cap instead of violating it via post-scaling.

3. `src/omega/quant/portfolio/barra_factor_model.py`
   - Added per-row fallback for null `available_at` values using `period_end + 90D`.
   - Effect: mixed-null fundamentals keep PIT lag behavior row-by-row.

4. `tests/test_hrp_barra_portfolio.py`
   - Added regression for future-return perturbation invariance.
   - Added regression for fallback 10% position cap without renormalization.
   - Added regression for mixed-null `available_at` fallback behavior.

## Verification

- Command: `pytest tests/test_hrp_barra_portfolio.py`
- Result: `7 passed, 4 warnings in 6.87s`

## Notes

- Warnings were pre-existing environment/dependency noise (`vnstock`, SQLAlchemy deprecation, pytest cache path). No scoped test failures.
