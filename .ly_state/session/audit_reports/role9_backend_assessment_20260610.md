# Role 9 - Backend Engineer Assessment

**Verdict: [NEEDS_FIX]**

Plan feasible in direction, not ready for implementation approval. Main issue: it treats restructuring as file moves. Actual repo needs API-preserving staged migration, import shims, regression fixtures, and test/mock path strategy.

**1. Implementation Feasibility**

Phase 1 can be done cleanly, but not as a 2-3 day split unless scope is only mechanical extraction.

Observed:
- [ultimate_alpha_arsenal.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:106): 80 top-level funcs, 66 `compute_*` funcs, 208 internal call edges.
- [compute_ultimate_alphas](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3542): orchestration owns group selection, memory guard, concat ordering, VN extras, promoted alphas.
- [get_alpha_metadata](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3977): large metadata registry must stay exact.

Hidden complexities:
- Individual funcs are imported externally, not only `compute_ultimate_alphas`.
- `ultimate_alpha_arsenal` imports `market_microstructure`, `phase34_microstructure_alphas`, `vn_alphas`, `promoted_alphas`.
- `promoted_alphas` imports `compute_returns`, `compute_rsi` back from arsenal → real circular edge.
- Column order/output equality matters for downstream model/test stability.
- PIT behavior can regress if helper reuse/lag conventions drift during extraction.

Phase 1 recommendation:
- Add `alpha/helpers.py`, category modules, `alpha/arsenal.py`.
- Keep `ultimate_alpha_arsenal.py` as full compatibility shim re-exporting every public function.
- Golden regression test: same input → same columns, same values, same dtypes/NaN profile.

**2. API Impact**

High if files are moved without wrappers.

Critical entrypoints:
- [quant_engine.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/quant_engine.py:37): imports root modules directly: `feature_factory`, `alpha_factory`, `model_module`, `signal_module`, etc.
- [quant_engine.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/quant_engine.py:659): already uses lazy imports to avoid circular bootstrap issues. Preserve this pattern.
- [pipeline_factory.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pipeline_factory.py:10): imports concrete classes from `phase35_walk_forward`, `pipeline_v2`, `walk_forward`.
- [__init__.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/__init__.py:9): lazy top-level public API. Must update only after shims pass.

Break risk:
- External imports like `omega.quant.portfolio_optimizer`, `omega.quant.execution_sim`, `omega.quant.phase35_walk_forward` are used by tests.
- Test mocks patch exact module strings, especially `omega.quant.phase35_walk_forward.*`; re-export alone is not enough if patched symbols move.

**3. Dependency Management**

Current static scan:
- 231 modules under `src/omega/quant`.
- 192 internal `omega.quant` import edges.
- 320 `omega.quant` import refs across `src` + `tests`.
- Top root targets include `ultimate_alpha_arsenal`, `pipeline_v2`, `neutralization`, `portfolio_optimizer`, `promoted_alphas`.

Import update complexity: medium for Phase 1, high for Phase 2/3.

Use `libcst` or Bowler-style rewrite. Do not regex imports. Keep old modules as shims for at least one full audit cycle.

**4. Data Flow Impact**

Pipeline impact is real but manageable.

Relevant paths:
- [pipeline_v2.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pipeline_v2.py:15): pulls `omega.data.sanitizer`, portfolio execution sim, overlays.
- [phase35_walk_forward.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/phase35_walk_forward.py:25): compatibility shim over `walk_forward` package.
- [walk_forward/__init__.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/walk_forward/__init__.py:4): already modularized.

Risk:
- Moving pipeline/portfolio/execution duplicates can alter `isinstance` checks in [pipeline_factory.py](/c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pipeline_factory.py:68).
- State/output paths in pipeline classes can write runtime artifacts; smoke tests need temp dirs.
- Data flow should not change if Phase 1 is alpha-only. Phase 2/3 can affect backtest/live paths.

**5. Testing Impact**

Current tree has 99 Python test files, not 89. Audit count is stale or filtered.

Observed:
- 170 relevant `omega.quant.*` refs in 55 test files.
- Many tests import old root modules directly.
- Phase35 tests patch exact old module paths.

Required tests before Phase 1:
- Golden alpha parity test for `compute_ultimate_alphas`.
- Direct import smoke for old + new paths.
- `alpha_factory`, `alpha_factory_optimized`, `promoted_alphas`, `microstructure_alphas` compatibility tests.
- Pipeline smoke: `pipeline_factory`, `pipeline_v2`, `phase35_walk_forward`.

**6. Estimated Effort**

4-6 weeks is plausible only with strict compatibility shims and automated rewrites.

Backend estimate:
- Phase 0: dependency/circular cleanup + golden tests: 2-3 days.
- Phase 1: split arsenal safely: 4-6 days.
- Phase 2: domain reorg: 2-3 weeks.
- Phase 3: duplicate merge: 1-2 weeks.
- Phase 4: other god-files: 1-2 weeks.
- Phase 5: docs/cleanup/type hints: 1 week.

Realistic total: 6-8 weeks with audit loops. 4-6 weeks is optimistic.

**7. Required Plan Fixes**

Before approval:
- Add Phase 0 as mandatory.
- Correct Phase 1 scope: 14-ish modules, not “6 modules”.
- Define public API freeze list.
- Require backward-compatible shims for every moved root module.
- Add automated import rewrite plan.
- Add golden output regression fixtures.
- Update test count/current baseline.
- Add mock-path strategy for tests using `patch("omega.quant...")`.
- Do not delete duplicate modules in same phase as moving them. First shim, then deprecate, then delete after green audit.

Final Role 9 position: architecture direction approved, implementation plan not approved yet. Needs Phase 0 + compatibility contract before L2 implementation starts.

