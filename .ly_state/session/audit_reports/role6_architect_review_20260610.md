**Role 6 - System Architect Audit Report**

**Verdict: [NEEDS_FIX]**

Plan direction is correct, but not approvable as architecture yet. Main blockers: phase ordering too risky, backward-compat scope understated, duplicate `feature/` vs existing `features/`, circular dependency already present, success metric contradicts shim/orchestrator strategy.

**Evidence Checked**

Repo: `src/omega/quant/`

Observed:
- `120` root files confirmed.
- `231` Python files under `quant`.
- `17` root dirs confirmed.
- `ultimate_alpha_arsenal.py`: `200,179` bytes, `4,257` lines, `66` `compute_*` functions, `130` output alphas per docstring/metadata.
- AST import graph found 1 actual SCC: `ultimate_alpha_arsenal` <-> `promoted_alphas`.
- 16 files failed AST parse due BOM `U+FEFF`; migration tooling must handle encoding.

**1. Domain Structure**

Mostly right, but needs correction.

Problems:
- Proposed `feature/` conflicts with existing `features/`. Pick one. Prefer existing `features/` unless a formal migration path exists.
- Missing explicit domains: `validation/`, `models/`, `universe/`, `sentiment/`, `governance/pit/`, `calendar/venue`, `observability`.
- `monitoring/` duplicates existing broader observability naming. Prefer `observability/`.
- `factory/` as top-level domain is weak. Factories should live inside owning domains unless truly cross-domain.
- `0 root files` success metric conflicts with plan keeping `quant_engine.py`, `pipeline_factory.py`, and legacy shims.

Recommended target:
- Keep root only for `__init__.py`, public orchestrators, compatibility shims.
- Use stable layer order: `data -> features/alpha -> models/ml -> signal -> portfolio/risk -> execution/backtest -> pipeline/orchestration`.
- Do not create both singular/plural domains.

**2. Coupling / Circular Dependency Risk**

High unless split rules are explicit.

Existing cycle:
- `promoted_alphas.py` imports `ultimate_alpha_arsenal.compute_returns/compute_rsi`.
- `ultimate_alpha_arsenal.py` imports `promoted_alphas.compute_promoted_alphas` inside orchestration.

Phase 1 can accidentally preserve or worsen this if the legacy wrapper imports `alpha.arsenal`, while promoted code imports the wrapper.

Required dependency direction:
- `alpha.helpers` / `alpha.primitives`: no domain imports.
- Category modules import helpers/primitives only.
- `alpha.arsenal` imports category modules.
- Legacy `ultimate_alpha_arsenal.py` imports from new modules only.
- No new module imports legacy `ultimate_alpha_arsenal.py`.
- `promoted_alphas` must import from `alpha.momentum` or `alpha.primitives`, not legacy wrapper.

**3. Phase 1 Split Granularity**

16 modules is acceptable, but needs adjustment.

Good:
- Category-based split matches metadata categories.
- `arsenal.py` orchestration + `helpers.py` is directionally correct.

Fix:
- Add `registry.py` or `metadata.py` for alpha metadata/columns.
- Add `primitives.py` for shared compute primitives used by promoted/optimized factories.
- `microstructure.py` with 21 alphas is too broad. Split into `vn_microstructure.py`, `market_microstructure.py`, `phase34_microstructure.py` or keep existing modules wired under `alpha/`.
- Very small modules like `cross_sectional.py` with 2 alphas are okay if metadata-driven, but do not over-fragment internal helpers.
- Preserve all 66 public `compute_*` imports, not only `compute_ultimate_alphas` and `get_alpha_metadata`.

**4. Backward Compatibility**

Thin wrapper is necessary but not sufficient.

Must support:
- `from omega.quant.ultimate_alpha_arsenal import compute_roc`
- `compute_ultimate_alphas`
- `get_alpha_metadata`
- all current `compute_*` functions used by `alpha_factory_optimized.py`
- old root imports for duplicate modules during deprecation window: `portfolio_optimizer`, `execution_sim`, `neutralization`, etc.
- `omega.quant.__init__` lazy exports update.

Required artifacts:
- Import alias map old -> new.
- `__all__` in shims.
- Deprecation warnings only after tests are stable.
- Import smoke test for every old public path.
- Golden-output regression test comparing old vs new alpha columns/values.

**5. Highest Migration Risk**

Highest risk: **Phase 2 Domain Reorganization**.

Reason:
- It touches import paths across repo/tests/core/data.
- Existing tests still import root modules like `omega.quant.portfolio_optimizer`, `omega.quant.execution_sim`, `omega.quant.phase35_walk_forward`.
- Moving files before duplicate semantics are resolved creates two risks at once: path breakage + behavior drift.

Second-highest: **Phase 3 Duplicate Merge** because duplicate names may not be true duplicates. They may be wrappers, overlays, or versioned behavior.

Recommended reorder:
1. Phase 0: baseline import graph, golden alpha outputs, public API map.
2. Phase 1: split `ultimate_alpha_arsenal` with full shims.
3. Phase 2: resolve duplicates one family at a time with shims.
4. Phase 3: domain moves in small batches.
5. Phase 4: split remaining god-files.
6. Phase 5: cleanup only after deprecation window.

**6. Missing Architectural Concerns**

Add these before approval:
- Public API contract: define supported imports vs internal modules.
- Layering rules + forbidden imports checked in CI.
- Golden regression suite for alpha columns, dtype, index alignment, PIT lag behavior.
- Encoding cleanup policy for BOM files before AST-based tooling.
- Shim lifecycle: duration, deprecation policy, removal criteria.
- Import smoke matrix for CLI/tests/notebooks/scripts.
- Ownership map per domain.
- Performance baseline: import time, memory, alpha computation runtime before/after.
- PIT compliance gate for moved alpha/feature code.
- Rollback should not prescribe `git reset --hard` as default. Use tags/branches and revert commits unless explicitly approved.
- SOD section has platform inconsistency: says `L2 (Codex CLI) -> Implementation`; OMEGA spec says L2 is OpenCode, L3 is Codex.

**7. Recommendations**

Required before approval:
- Fix domain map: no `feature/` vs `features/` duplication; include missing existing domains.
- Define strict dependency layering.
- Break `ultimate_alpha_arsenal` <-> `promoted_alphas` cycle in Phase 1.
- Expand backward-compat plan to cover all public functions and root duplicate module imports.
- Replace `0 root files` success metric with “root contains only orchestrators + public shims”.
- Add Phase 0 baseline/golden-output stage.
- Reorder duplicate merge before broad domain reorg, or make domain reorg incremental by family.
- Add CI checks: import smoke, golden alpha regression, PIT checks, circular import detection, pycodestyle.

Final: **[NEEDS_FIX]**. Architecture intent is sound; execution plan needs stronger contracts before implementation.