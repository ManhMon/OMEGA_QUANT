# AGENT_WORKFLOW Audit R1

## Executive Summary

**Verdict**: [NEEDS_FIX]

`docs/AGENT_WORKFLOW.md` is not yet aligned with the current institutional spec and implementation-contract source of truth. The most serious defect is a platform-routing inversion: the workflow assigns production implementation and testing to `OpenCode` and audit to `Codex`, while the spec assigns orchestration/audit to `OpenClaw`, production repo changes and test implementation to `Codex CLI`, and `OpenCode CLI` only to prototyping / small patches / exploratory coding. Additional gaps exist in event contracts, approval gates, checkpoint/audit persistence, and example path fidelity. This document should not be treated as implementation-ready until the findings below are resolved.

## Scope

- Audited file: `docs/AGENT_WORKFLOW.md`
- Baselines:
  - `specs/omega_quant_ai_institutional_engineering_spec_full.md`
  - `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md`

## Findings

### P0

1. **Core platform routing contradicts the governing spec.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:38`, `docs/AGENT_WORKFLOW.md:40-42`, `docs/AGENT_WORKFLOW.md:185-202`, `docs/AGENT_WORKFLOW.md:433-446`, `docs/AGENT_WORKFLOW.md:517-567`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:1092-1113`
   - Problem: the workflow routes code/test/research execution to `OpenCode L2` and review/audit to `Codex L3`. The spec states `OpenClaw` owns orchestration, workflow state, gate control, and audit; `Codex CLI` owns production code, repository changes, large refactors, integration, and test implementation; `OpenCode CLI` is limited to prototype/small-patch/exploratory work.
   - Impact: every downstream task can be dispatched to the wrong runtime, invalidating the workflow as a source of truth.
   - Recommendation: rewrite lifecycle, routing, verification, and examples so platform ownership matches the spec exactly, or formally amend the spec first.

### P1

1. **Event schema is not compliant with the canonical event contract.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:223-240`, `docs/AGENT_WORKFLOW.md:247-258`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:280-326`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1268-1291`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:224-272`
   - Problem: the workflow schema omits `event_version`, `correlation_id`, `causation_id`, `severity`, and `trace_id`. It also omits required delivery/order/retry/dead-letter semantics and does not include several mandatory events such as `TASK_STARTED` and `TASK_RETRIED`.
   - Impact: event producers/consumers built from this doc will not satisfy the spec/contract layer and will be hard to replay, trace, or evolve safely.
   - Recommendation: adopt the canonical event schema and enumerate delivery guarantee, ordering guarantee, idempotency rule, retry rule, dead-letter rule, and schema evolution rule.

2. **Approval/gate model collapses required governance into a single verification approval.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:293-305`, `docs/AGENT_WORKFLOW.md:433-466`, `docs/AGENT_WORKFLOW.md:641-651`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:704-710`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1001-1021`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1148-1160`
   - Problem: phase approval is assigned only to `Verification Supervisor`, and the workflow acceptance criteria do not model the required risk gate, security gate, deployment gate, or explicit approval recording.
   - Impact: the process can approve work that has not passed mandated risk/security/governance controls.
   - Recommendation: define explicit gate owners, artifacts, and stop conditions for architecture, review, test, risk, security, and deployment gates.

### P2

1. **Checkpoint and audit persistence are under-specified versus recovery/audit requirements.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:344-364`, `docs/AGENT_WORKFLOW.md:377-380`, `docs/AGENT_WORKFLOW.md:624-637`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:252-270`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1504-1519`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:317-322`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:792-795`
   - Problem: checkpoint schema captures only `files_changed`, `tests_passed`, and `artifacts`, while the spec requires task state, context snapshot, metrics, and decision rationale. Audit logs are not defined as append-only or tamper-evident.
   - Impact: recovery fidelity and audit defensibility are below spec.
   - Recommendation: expand checkpoint/audit schemas to include the missing fields and immutability requirements.

2. **Low-memory policy uses hard task killing without the required recovery path.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:586-590`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:48-52`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:967-973`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1406-1412`
   - Problem: the workflow says to kill the lowest-priority task when RAM drops below 8GB, but does not require checkpoint-before-kill, forensic logging, replay, or restore semantics.
   - Impact: work loss and non-auditable failure handling become part of the normal control path.
   - Recommendation: replace hard-kill behavior with checkpoint -> quiesce/throttle -> resume/abort logic, with mandatory audit trail.

3. **Examples use non-canonical repository paths.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:525-526`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:56-99`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:60-103`
   - Problem: example outputs write to `packages/omega-core/src/omega/core/` and `packages/omega-core/tests/`, which do not match the canonical repo layouts defined in the baseline docs.
   - Impact: examples will mislead implementers and reduce path-level traceability.
   - Recommendation: switch examples to canonical paths or mark them explicitly as non-normative placeholders.

4. **Agent contracts are incomplete for an “Implementation-Ready” workflow document.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:53-202`, `docs/AGENT_WORKFLOW.md:665-668`
   - Source refs: `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:326-349`
   - Problem: only a subset of roles receives partial responsibility/constraint text, and the document does not define the required agent contract fields such as runtime, capabilities, outputs, scope, limits, failure modes, and escalation path for each role.
   - Impact: implementers cannot derive consistent agent-level contracts from this workflow alone.
   - Recommendation: add a role appendix or contract table covering all required agent fields for all 25 roles.

### P3

1. **Acceptance criteria are narrower than the system-level acceptance baseline.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:641-651`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:1146-1160`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1523-1545`
   - Problem: the workflow acceptance block omits several baseline checks, including bounded memory growth, reconciliation validation, rollback validation, and broader live-trading/runtime acceptance expectations.
   - Impact: teams can declare the workflow operational before critical acceptance conditions are proven.
   - Recommendation: expand acceptance criteria to cover the full runtime/live/audit baseline or explicitly scope the document as a partial workflow layer.

## Recommendations

1. Re-baseline `docs/AGENT_WORKFLOW.md` from the current spec/contract documents before any further process rollout.
2. Fix platform ownership first; every other workflow section depends on it.
3. Replace the local EventBus schema and event list with the canonical contract fields and mandatory events.
4. Introduce explicit gate definitions for review, test, risk, security, and deployment, including approver identity and artifact requirements.
5. Harden persistence sections: checkpoint completeness, append-only audit logs, tamper evidence, replay/restore path.
6. Normalize all example paths and role contracts to the canonical repository and agent-contract maps.

## Final Gate Decision

**Gate**: [NEEDS_FIX]

This document is **not approved** as an implementation-ready workflow baseline. The P0 routing contradiction is a release blocker by itself. Re-audit is required after the workflow is rewritten to match the governing spec and contract layers.
