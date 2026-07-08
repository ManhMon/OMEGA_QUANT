#[L2] GP_NUMBA_OLS_IMPLEMENTATION

- Role: `16 machine-learning-engineer`
- Gate: `GP_NUMBA_OLS_IMPLEMENTATION`
- Scope: `scripts/genetic_alpha_evolution_v4.py`, `tests/test_gp_numba_jit_vm.py`
- Status: `IMPLEMENTED`

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

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` -> not accessed (non-authoritative forbidden path)
- `.openclaw\skills` -> not accessed (non-authoritative forbidden path)
- `.codex\memories` -> not accessed (non-authoritative forbidden path)
- `C:\Users\GHC\.agents` -> not accessed (non-authoritative forbidden path)
- Result: no reliance on forbidden paths as authoritative sources.

## Changes

- Added Ridge-style OLS JIT kernels using `np.linalg.solve` with `alpha=1e-6`.
- Avoided per-date `X_sub` / `y_sub` / `y_res` allocations in JIT path by reusing row buffers, Gram matrix, RHS, beta buffers.
- Built `design_matrix` and `valid_mask` once in `_build_vm_context`.
- Attached JIT neutralization payload to `NEUTRALIZATION_CACHE_KEY` for single-series and batch neutralization paths.
- Ported optimized neutralization call sites to ensure JIT context exists before neutralization.
- Added tests for sklearn Ridge parity, singular design, small-N, all-NaNs stability, batch parity, date isolation.

## Verification

- Command: `pytest tests/test_gp_numba_jit_vm.py`
- Result: `9 passed`

## Notes

- Ridge regularization intentionally replaces prior rank-based singular skip behavior for this path.
- `ponytail:` current design matrix prep uses pandas factorization once in Python context build; upgrade path = pure-numba categorical encoding only if profiling shows prep bottleneck.
