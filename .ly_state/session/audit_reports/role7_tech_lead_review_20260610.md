# Role 7 - Tech Lead Review

**Verdict: [NEEDS_FIX]**

Plan is directionally correct, but not ready for execution. It mostly moves files first, quality second. For a Tech Lead gate, restructure must be refactor-safe, import-safe, style-gated, test-backed.

**Evidence Read**
Plan: [omega_quant_restructuring_master_plan_20260610.md](</Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/omega_quant_restructuring_master_plan_20260610.md>)  
Combined audit: [combined_l4_audit_restructuring_20260610.md](</Users/GHC/.gemini/antigravity-ide/brain/505ea644-19ea-4009-8a72-db306fcabaac/combined_l4_audit_restructuring_20260610.md>)  
Repo checked: [src/omega/quant](</Users/GHC/repos/OMEGA_QUANT/src/omega/quant>)

**1. Code Standards**

Current PEP 8 state is weak.

Observed:
- `231` Python files under `src/omega/quant`
- `120` root Python files
- `216` files with pycodestyle violations
- `9,870` pycodestyle violations total
- biggest classes: `E501=4,360`, `W293=4,890`
- config already enforces `max-line-length = 79` in `.flake8` / `setup.cfg`

Risk: restructuring without formatting gate will preserve or amplify violations. Moving code changes import lines, line lengths, module headers, `__init__` exports. PEP 8 will break unless enforced per phase.

Recommendation:
- Add Phase 0 quality baseline: `python -m pycodestyle src\omega\quant --statistics --count`
- Gate each phase on reducing, not just preserving, pycodestyle debt.
- Add formatter/linter policy: either strict pycodestyle remediation or deliberate `ruff/black` migration. Current “zero violations” target is not credible without a staged cleanup budget.

**2. Technical Debt**

Plan addresses structural debt: god-file, duplicate modules, flat root, inconsistent domains.

But it under-addresses behavioral/code debt:
- circular deps: `promoted_alphas <-> ultimate_alpha_arsenal`, plus self-imports in `alpha_factory_optimized.py`, `alpha_preprocessing.py`
- wall-clock usage in quant paths: `datetime.now()`, `pd.Timestamp.now()` appear in multiple modules
- random state usage without clear deterministic policy in ML/evolution/backtest paths
- generated/demo/test-like code embedded in production modules
- duplicate canonical choices need semantic diff, not name-based merge

Risk: moving modules can make debt harder to see. Phase 5 “dead code removal” is too late.

Recommendation:
- Add Phase 0: circular imports + import graph boundary rules.
- Add per-domain ownership docs before moving files.
- Merge duplicates before broad domain reorg where practical. Otherwise import rewrites target unstable canonical APIs.

**3. Code Review Feasibility**

After restructuring, reviews will be easier only if phases are sliced smaller.

Current Phase 2 is too broad: moving 120 files into 10+ domains creates noisy diffs, import churn, shim churn, weak semantic review.

Recommendation:
- Split Phase 2 by domain: alpha, feature, portfolio, execution, risk, ML, data, strategy, signal/backtest, utils.
- Require one reviewable PR/phaselet with:
  - moved files list
  - import map
  - public API diff
  - tests touched
  - smoke import result
- Use mechanical move commit separate from semantic edits.

**4. Developer Experience**

End state likely improves DX: domains, smaller files, clearer ownership, less root clutter.

Short-term DX worsens unless migration is controlled:
- old imports will still exist via wrappers
- duplicate modules remain during transition
- developers may import from both old/new paths
- IDE search/navigation improves only after stale shims are deprecated

Recommendation:
- Publish `MIGRATION.md` with canonical import table.
- Add deprecation warnings only in compatibility shims.
- Freeze new root-level modules immediately.
- Add import lint: block new imports from deprecated root paths.

**5. Import Complexity**

Plan can make imports cleaner, but proposed `quant.imports.alpha`, `quant.imports.feature` is a risk.

Import helper modules often become a second registry layer and hide real ownership. Current package already has 112 absolute `omega.quant...` internal imports and 46 relative imports. Adding helper indirection may increase coupling.

Recommendation:
- Prefer direct canonical imports: `omega.quant.alpha.arsenal`, `omega.quant.portfolio.optimizer`.
- Keep compatibility wrappers thin and temporary.
- Avoid `quant.imports.*` unless there is a concrete use case.
- Define stable public API only in domain `__init__.py`; keep internals private.

**6. Missing Code Quality Concerns**

Missing/underweighted:
- exact dead-code inventory before moves
- import cycle test in CI
- deterministic RNG policy for research/backtest/evolution
- PIT safety review for moved alpha/data/backtest code
- public API compatibility tests
- generated files policy, especially promoted alpha outputs
- `__pycache__` directories present in source tree
- type-check strategy: mypy config exists, but no phased typing goal
- performance baseline before/after alpha split
- discrepancy: local repo shows `27` Python files over 20KB; audit says `25`

**7. Required Fixes Before Approval**

1. Add Phase 0:
   - resolve circular imports
   - define canonical import map
   - run import smoke tests
   - establish pycodestyle baseline
   - add API compatibility tests for top public imports

2. Reorder:
   - Phase 0: dependency/style/test baseline
   - Phase 1: split `ultimate_alpha_arsenal.py`
   - Phase 2A-N: domain moves by domain, not all at once
   - Phase 3: duplicate merge can start earlier for isolated pairs
   - Phase 4: remaining god-files
   - Phase 5: docs/deprecation cleanup

3. Add gates:
   - `pycodestyle` count must not increase
   - import cycles must be zero or explicitly waived
   - old/new import smoke tests pass
   - representative alpha outputs match before/after
   - PIT-sensitive functions reviewed after move

4. Remove/avoid:
   - broad “0 files in root” success metric conflicts with plan keeping `quant_engine.py`, `pipeline_factory.py`, `__init__.py`
   - `quant.imports.*` helper layer unless justified
   - deleting duplicate files before compatibility shims and import telemetry exist

Final Tech Lead position: **[NEEDS_FIX]**. Approve the restructuring concept, reject the current execution plan until Phase 0, phased import strategy, style gate, and review slicing are added.

