# Role 21 - Code Reviewer Audit Report

**Verdict**: `[NEEDS_FIX]`

**Scope Audited**: plan only. No files modified.

**Blocking Findings**

1. **SOD definition is non-compliant.**  
   Plan says `L2 (Codex CLI) -> Implementation` at [master plan:229](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:229). Repo protocol defines **L2 = OpenCode**, **L3 = Codex** at [AGENTS.md:60](C:/Users/GHC/repos/OMEGA_QUANT/AGENTS.md:60), [AGENTS.md:110](C:/Users/GHC/repos/OMEGA_QUANT/AGENTS.md:110), [AGENTS.md:125](C:/Users/GHC/repos/OMEGA_QUANT/AGENTS.md:125).  
   Fix: replace phase workflow with `L2 OpenCode impl -> L3 Codex audit -> L1 gate`, with L2 terminated before L3.

2. **Undefined L4 gate role.**  
   Plan introduces `L4 (Gemini)` verification at [master plan:233](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:233). AGENTS defines only L1/L2/L3 25-role model. L4 can provide external verification evidence, but cannot be gate owner unless protocol amended.  
   Fix: L1 writes gate; L4 evidence optional, not authoritative.

3. **Gate process incomplete.**  
   AGENTS mandates `python scripts/sod_gate_enforcer.py` before release at [AGENTS.md:92](C:/Users/GHC/repos/OMEGA_QUANT/AGENTS.md:92). Plan lists gate JSON fields but omits mandatory enforcer execution. Existing `phase_gates.json` also has mixed schemas, so plan must define exact append/update format.

4. **Backward compatibility conflicts with delete step.**  
   Plan says create shims then “Delete duplicate files” at [master plan:192-193](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:192). Deleting old import files breaks current imports in `scripts/`, `src/`, `tests`. Example: `omega.quant.execution_sim`, `omega.quant.portfolio_optimizer`, `omega.quant.features.neutralization`, `omega.quant.portfolio.portfolio_optimizer` all have live references.  
   Fix: keep old files as thin wrappers for at least one release window; remove only after deprecation gate.

5. **Success metric impossible as written.**  
   Plan keeps `quant_engine.py`, `pipeline_factory.py`, `__init__.py` in root at [master plan:161-163](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:161), but success metric says `0 files in root` at [master plan:296](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:296).  
   Fix: define allowed root API files, likely `__init__.py`, `quant_engine.py`, `pipeline_factory.py`.

6. **Rollback plan is unsafe.**  
   Plan recommends `git reset --hard pre-restructure-phase-X` at [master plan:263](C:/Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md:263). This can discard unrelated user work.  
   Fix: use branch-per-phase, clean worktree precheck, revert commit/PR, no `reset --hard` unless explicitly approved.

**Completeness**

Missing required Phase 0:
- API/import inventory with public symbols.
- golden output baseline for `compute_ultimate_alphas`.
- full import smoke matrix for old and new paths.
- duplicate diff report before choosing canonical files.
- PIT/lookahead regression suite.
- performance baseline: import time, peak RAM, alpha runtime.
- exact test commands + acceptance thresholds.
- deprecation policy for wrappers.
- `sod_gate_enforcer.py` gate step.
- loaded skill/state logging compliance.

**Feasibility**

`4-6 weeks` is optimistic but possible only with strict compatibility wrappers and mostly mechanical moves. As written, with 120 root files, 231 Python files under `src/omega/quant`, 99 test files, 11 duplicate groups, and many active legacy imports, realistic estimate is:

- **6-8 weeks** with one focused L2 implementer plus recurring L3 audit.
- **4-6 weeks** only if Phase 2 is reduced to mechanical moves, no semantic merges, no deletion of legacy paths.
- **8-10 weeks** if duplicate merge semantics, PIT parity, full regression, docs, and deprecation are done properly.

**Phase Ordering**

Current order is suboptimal: Phase 2 domain reorg before Phase 3 duplicate merge creates more import churn.

Recommended order:
1. Phase 0: Baseline freeze, API manifest, golden outputs, import graph.
2. Phase 1: Split `ultimate_alpha_arsenal.py` with wrapper parity only.
3. Phase 2: Resolve duplicates behind compatibility wrappers.
4. Phase 3: Domain reorg via mechanical moves/codemod.
5. Phase 4: Split remaining god-files.
6. Phase 5: cleanup, docs, deprecation notices.

**Duplicate Resolution**

Several canonical choices need re-audit before approval:
- `black_litterman`: plan says `quant/black_litterman.py`; actual files are `pipeline/overlays/black_litterman.py` and `strategy/black_litterman.py`.
- `neutralization`: plan chooses `portfolio/neutralization.py`, but tests import `features/neutralization.py`; canonical should not move without semantic justification.
- `portfolio_optimizer`: root file is 716 lines; `portfolio/portfolio_optimizer.py` is 149 lines. Do not assume existing subdir file is canonical.
- `execution_sim`: root file is 730 lines; `portfolio/execution_sim.py` is 218 lines. Needs behavior diff.
- `ml_engine`: `ml/ml_engine.py` is larger and likely canonical, but rename to `ml/engine.py` adds unnecessary churn.

**Testing Strategy**

Insufficient. `pytest 6/6` is not enough for repo restructure. Required:
- full targeted `pytest` for quant/import/API suites, plus existing smoke baseline.
- `python -m compileall src tests scripts`.
- import smoke for every old path and new path.
- golden dataframe comparison for alpha outputs, tolerances declared.
- future-sentinel PIT tests for rolling/groupby/shift-sensitive logic.
- performance regression: import time, runtime, memory.
- pycodestyle using current `setup.cfg` 79-char config.
- gate enforcer PASS after each phase.

**Backward Compat Edge Cases**

Plan must cover:
- direct imports of individual `compute_*` funcs from `ultimate_alpha_arsenal.py`.
- scripts using old root modules.
- tests importing both root and subpackage paths.
- `__all__`, lazy imports, circular imports.
- serialized configs/models referencing module paths.
- CLI/notebook/user scripts outside `src`.
- old wrapper deprecation warnings without breaking runtime.

**Risk Assessment**

Missing risks:
- accidental behavior drift during alpha split.
- PIT leakage introduced by reordering/groupby refactor.
- circular imports from new domain package boundaries.
- stale `phase_gates.json` schema collision.
- external import breakage.
- destructive rollback.
- performance/memory regression.
- duplicate merge losing richer implementation.

**Final**

`[NEEDS_FIX]`

Plan direction is valid, inventory mostly matches current repo, but approval is blocked by SOD violation, unsafe deletion/rollback strategy, impossible success metric, weak test gate, stale duplicate mapping, and missing Phase 0 baseline.