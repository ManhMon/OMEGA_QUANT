# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-15T09:05:26.6811635+07:00
**Gate**: DYNAMIC_REBALANCE_UNIVERSE_20260615
**Submission**: l2_role14_dynamic_rebalance_universe_20260615
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `.agents/agent/data-scientist.md`
- `.ly_state/session/l2_role14_dynamic_rebalance_universe_20260615.md`

Note: `sops/SKILL.md` references `SOP_AC.md`, `SOP_PIT_SAFETY.md`, and `SOP_BACKTEST.md`, but those files are not present under repo-local `.agents/skills/sops/`. The embedded SOP rules in `sops/SKILL.md` were used.

## SOD Checks

- Writer != auditor: PASS. L2 role_id 14 != L3 role_id 20.
- L2 role spec: PASS. `.agents/agent/data-scientist.md` has role_id 14, tier 2, platform OpenCode.
- L3 role spec: PASS. `.agents/agent/compliance-officer.md` has role_id 20, tier 3, platform Codex, sod_boundary defined.
- L3 write boundary: PASS. Audit wrote only this report and the scoped gate metadata update.
- L2 source evidence: PASS. L2 report lists exact repo-local role/skill files read.
- Forbidden path scan: PASS. Forbidden paths appear only as non-authoritative scan evidence in the L2 report; scoped source files do not rely on them.

## Tests Run

- `python -m pytest tests/phase35/test_phase35_dynamic_universe.py -q` -> 34 passed.
- `python -m pytest tests/phase35 -q` -> 607 passed.

## Findings

### Blocking: Per-Fold Dynamic Universe Evidence Is Never Attached

`src/omega/quant/alpha/phase35.py:170` adds `FoldMetrics.dynamic_universe_evidence`, and `scripts/run_phase35_backtest.py:95-98` serializes it if present. But `src/omega/quant/alpha/phase35.py:3179-3204` constructs `FoldMetrics` without passing `dynamic_universe_evidence`. Result: `fold_details[*].dynamic_universe_evidence` is absent even when dynamic universe is enabled. This contradicts the L2 report claim and weakens auditability at fold level.

Required fix: attach fold-scoped dynamic universe evidence to each `FoldMetrics`, or remove the per-fold claim and add tests proving the intended evidence location.

### Blocking: Dynamic Universe Carry-Forward State Can Leak Across Folds

`src/omega/quant/alpha/phase35.py:1894-1901` stores `_last_dyn_universe` on the engine instance. `run_walk_forward` reuses the same engine across all folds (`src/omega/quant/alpha/phase35.py:3241-3243`). With overlapping or adaptive folds, a later date from fold N can be carried into an earlier date in fold N+1 when there is no exact schedule entry for that date. That violates the requested date-level carry-forward safety requirement and can become PIT leakage.

Required fix: reset carry-forward state at fold start and carry forward by date only from the latest schedule date strictly <= current rebalance date. Add a regression test covering overlapping folds or direct `_apply_stage2_constraints` calls where prior fold state is future relative to the next fold's first rebalance.

## Passed Checks

- Dynamic universe CLI is opt-in; default is disabled in parser.
- Selector uses `[rebalance_date - lookback_days, rebalance_date)` with `< rebalance_date` filter and asserts `selection_end < rebalance_date`.
- Top-level dynamic universe schedule/evidence is JSON serializable in focused tests.
- Security scan of scoped files found no eval/exec/pickle/secrets patterns.
- Focused and phase35 regression tests pass.

## Verdict

[NEEDS_FIX]

The implementation is close, but approval is blocked by missing per-fold evidence persistence and unsafe cross-fold carry-forward state. Fixes must be implemented by L2 and resubmitted for L3 review.
