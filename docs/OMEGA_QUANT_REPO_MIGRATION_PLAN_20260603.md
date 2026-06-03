# OMEGA_QUANT Repo Migration Plan

Date: 2026-06-03
Status: Proposed only — no repo-wide move executed yet
Owner: Ly (L1 orchestration)
Constraint: Strict SOD for any implementation + audit

## 1. Current State

Current git root:

`C:\Users\GHC\.openclaw\workspace`

Current tracked root layout from `origin/main`:

- `apps/`
- `config/`
- `data/`
- `docs/`
- `memory/`
- `models/`
- `packages/`
- `scripts/`
- `spec/`
- `src/`
- `tests/`
- project files at repo root (`AGENTS.md`, `SOUL.md`, `pytest.ini`, etc.)

Current local-only/problematic non-app folders mixed into workspace:

- `.openclaw/`
- `.code-review-graph/`
- `.antigravitycli/`
- `skills/`
- `pi_skill/`
- `.pytest_cache/`
- `__pycache__/`
- tool-generated temp/cache artifacts

Current `OMEGA_QUANT/` folder is **not** repo root. It currently only contains:

- `docs/`
- `.ly_state/`

## 2. Goal

Move app source into a single top-level project directory named `OMEGA_QUANT/` **cleanly**, while preserving:

- git history readability
- import correctness
- test discovery
- script execution
- docs links
- CRG usability
- SOD workflow

Target intent:

```text
<repo root>/
  OMEGA_QUANT/
    apps/
    config/
    data/
    docs/
    memory/
    models/
    packages/
    scripts/
    spec/
    src/
    tests/
    AGENTS.md
    SOUL.md
    pytest.ini
    ...
```

Non-app runtime/tooling should live **outside** app tree.

## 3. Key Decision

Recommended structure:

### Option chosen by Ly
Keep git repository at current root for migration step, but make `OMEGA_QUANT/` the sole app subtree.

Why:

- simpler than creating a brand-new repo immediately
- preserves ability to review migration as one controlled rename/move set
- allows later optional step: make `OMEGA_QUANT/` the repo root in separate migration

## 4. What should move into `OMEGA_QUANT/`

Decision confirmed by user on 2026-06-03:

- keep `.ly_state/` in project scope
- keep `data/` in project scope
- keep `models/` in project scope
- items removed from active workspace should be moved into `archive/`, not deleted

Move these tracked app/project directories:

- `.ly_state/`
- `apps/`
- `config/`
- `data/`
- `docs/`
- `memory/`
- `models/`
- `packages/`
- `scripts/`
- `spec/`
- `src/`
- `tests/`

Move these tracked project files if still needed by app workflow:

- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `IDENTITY.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `pytest.ini`
- `conftest.py`
- `.code-review-graph.yml`
- any app-owned config files in repo root

## 5. What should NOT move into `OMEGA_QUANT/`

These are tooling/runtime/junk and should stay outside app tree or be relocated into `archive/` during cleanup:

- `.openclaw/`
- `.code-review-graph/`
- `.antigravitycli/`
- `skills/`
- `pi_skill/`
- `.pytest_cache/`
- `__pycache__/`
- ad-hoc scratch/temp dirs

## 6. Recommended destination for non-app folders

Confirmed cleanup policy for this workspace:

### Short term
Move non-app folders into repo-local archive buckets, not delete them:

- `archive/workspace_cleanup/tooling/.openclaw/`
- `archive/workspace_cleanup/tooling/.code-review-graph/`
- `archive/workspace_cleanup/tooling/.antigravitycli/`
- `archive/workspace_cleanup/tooling/skills/`
- `archive/workspace_cleanup/tooling/pi_skill/`
- `archive/workspace_cleanup/tooling/.pytest_cache/`
- `archive/workspace_cleanup/tooling/__pycache__/`

### Long term (preferred)
Outside app tree; ideally outside repo:

- `C:\Users\GHC\.openclaw\...` for OpenClaw runtime/config/skills
- `C:\Users\GHC\.openclaw\cache\code-review-graph\OMEGA_QUANT\` for CRG cache
- `C:\Users\GHC\.antigravitycli\` or `C:\Users\GHC\.openclaw\external-tools\antigravitycli\`

Project-state intentionally retained with app:

- `.ly_state/`
- `data/`
- `models/`
- `memory/`

## 7. Risks

### High risk
- hardcoded paths in docs/scripts/tests
- pytest root/config assumptions
- imports that assume repo root is working directory
- CI/local scripts that reference `workspace\src`, `workspace\packages`, etc.
- OpenClaw project-context files currently loaded from old root

### Medium risk
- markdown docs links
- CRG repo_root assumptions
- local batch/PowerShell scripts
- data/model relative paths

### Low risk
- pure Python package imports if `pytest.ini`/execution root updated correctly

## 8. Required path rewrite classes

### A. Absolute Windows workspace paths
Search and rewrite references like:

- `C:\Users\GHC\.openclaw\workspace\src\...`
- `C:\Users\GHC\.openclaw\workspace\packages\...`
- `C:\Users\GHC\.openclaw\workspace\tests\...`
- `C:\Users\GHC\.openclaw\workspace\docs\...`
- `C:\Users\GHC\.openclaw\workspace\scripts\...`

New form should point to:

- `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\...`

### B. Relative project-root assumptions
Examples:

- `src/...`
- `packages/...`
- `tests/...`
- `docs/...`

Need inspection in:

- `pytest.ini`
- `conftest.py`
- `scripts/*.py`
- root docs
- agent/project state docs

### C. Tooling/project config
Inspect and possibly update:

- OpenClaw project context expectations
- CRG repo root
- local helper scripts
- any IDE/task configs

## 9. Migration Phases

### Phase 0 — freeze + backup
- create branch for migration
- snapshot current tree
- capture git status
- checkpoint critical project files

### Phase 1 — classify + grep
- full grep of root-path references
- classify source/state/tooling
- produce exact move map

### Phase 2 — move non-app junk out of app scope
- do **not** delete yet
- relocate or ignore tooling/cache dirs first
- keep source diff cleaner

### Phase 3 — move tracked app tree into `OMEGA_QUANT/`
- use git-aware move strategy
- move directories first
- move root project files second
- keep changes as mostly rename-only where possible

### Phase 4 — rewrite paths/config
- fix pytest root discovery
- fix scripts
- fix docs and hardcoded references
- fix OpenClaw project file references if needed

### Phase 5 — verification
Minimum verification set:

- `python -m pytest` targeted smoke
- quant package targeted tests
- import smoke for major entrypoints
- grep for stale old-root path refs
- CRG rebuild against new app root

### Phase 6 — L3 audit
- Codex audit only
- separate session
- final verdict must be `[APPROVED]` before merge/push

## 10. Verification Checklist

### Must pass
- app imports resolve from new path
- targeted tests pass
- `pytest.ini` still works
- docs/scripts no longer point to old root layout
- no required app folder left behind outside `OMEGA_QUANT/`

### Must inspect manually
- OpenClaw context docs
- AGENTS/TOOLS/SOUL references
- `.ly_state` handling
- memory folder placement decision

## 11. SOD Execution Model

Because this is a repo-wide structural change, correct SOD flow is:

1. L1 (Ly): planning only
2. L2 (implementation session): perform migration + run tests
3. L2 session terminates
4. L3 (Codex audit): review move map, diffs, tests, path rewrites
5. L1 records gate only if full contract exists

## 12. Recommendation

Proceed, but **not directly in this turn as blind filesystem moves**.

Recommended next action:

### Next Action A (safer)
Generate exact move map + exact path rewrite inventory first.

### Next Action B (after approval)
Execute migration in L2 implementation session with bounded scope:

1. move tooling junk out of app scope
2. move app directories into `OMEGA_QUANT/`
3. rewrite paths
4. run smoke verification
5. hand off to L3 audit

## 13. Final Advice

This restructure is reasonable **if the strategic goal is to make `OMEGA_QUANT/` the single visible app root**.

It is **not** reasonable to move folders ad hoc without first:

- separating tool/runtime clutter
- inventorying path assumptions
- preserving SOD and auditability
