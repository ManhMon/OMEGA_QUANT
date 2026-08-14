# Role 21 SoD Wording Hardening Plan Review

**Role**: Code Reviewer (Role 21, Codex L3)
**Date**: 2026-07-25
**Submission**: Revised implementation plan for permanent SoD report wording enforcement
**Review Type**: Final plan re-review

## Repo-Local Files Read
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/AGENTS.md`
- `scripts/sod_gate_enforcer.py`
- `scripts/omega_role_router.py`
- `scripts/sod_preflight.py`
- `tests/test_sod_gate_enforcer_startup.py`
- `tests/test_strict_repo_local_skill_loading.py`

The user-supplied external implementation plan was read only as the review submission. It was not used as an authoritative role or skill source.

## Forbidden Path Scan
All forbidden path mentions in this report are non-authoritative scan evidence only; no forbidden role or skill source was read or relied upon.
- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

## Review Findings
- **Deterministic cutoff**: PASS. The plan selects one constant, `CANONICAL_REPORT_EVIDENCE_CUTOFF = "2026-07-25T00:00:00Z"`, uses no parallel schema marker, defines precedence between gate-key and audit-report filename dates, treats equality as canonical mode, and fails closed on missing or contradictory selectors.
- **Authoritative producers**: PASS. The plan names `.agents/AGENTS.md` and `scripts/omega_role_router.py` as the exact producer files to modify, identifies the L2 template, L3 template, and routed-prompt builder responsibilities, and explicitly excludes `scripts/sod_preflight.py` as non-producer scope.
- **Exact tests and fixtures**: PASS. The plan names `tests/test_sod_report_evidence.py`, `tests/test_lint_sod_report_evidence.py`, `tests/test_sod_gate_enforcer_startup.py`, `tests/fixtures/sod_report_evidence/`, eight fixture filenames, compilation commands, focused pytest commands, and the combined pytest command.
- **Mandatory enforcer validation**: PASS. The plan requires `scripts/sod_gate_enforcer.py` to invoke the shared pure validator for every applicable gate. The CLI linter remains optional UX only. A post-cutoff validator failure must fail the gate and return exit code `1`.
- **Bypass prevention proof**: PASS. Integration coverage requires malformed post-cutoff fixtures to fail through the enforcer without invoking the lint CLI, canonical equivalents to pass through the same path, pre-cutoff legacy fixtures to pass, and missing or contradictory date selectors to fail closed.
- **Migration safety**: PASS. The rollout captures current malformed reports as regression fixtures before producer/report correction, preserving proof of the original failure and preventing a false green caused by rewriting evidence first.

## Non-Blocking Implementation Note
The selector intentionally derives day precision from `YYYYMMDD` gate/report suffixes while the cutoff constant is midnight UTC. Implementation must compare normalized dates consistently and must not consult filesystem timestamps, report body dates, or local timezone state.

## Verdict
[APPROVED]

The revised plan meets all requested hardening criteria and provides deterministic, mandatory, end-to-end enforcement against malformed post-cutoff report wording.
