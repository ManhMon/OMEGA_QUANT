# AGENT_WORKFLOW Audit R2

## Standardized Audit Header

| Field | Value | Detail |
|---|---|---|
| Role | Review Agent / Critic Agent | Requested as a combined session for this audit |
| Verdict | [NEEDS_FIX] | R1 fixes are incomplete |
| PIT Safety | PASS | No new PIT or look-ahead issue introduced by this doc revision |
| Role Compliance | FAIL | This audit request merged Role 16 and Role 20 into one session, which conflicts with strict-isolation policy |

## Executive Summary

`docs/AGENT_WORKFLOW.md` v1.1-R1-FIX improved materially over R1. The explicit 6-gate model is now present, the low-memory hard-kill behavior was replaced with checkpoint/quiesce semantics, and checkpoint/audit persistence is much closer to spec.

However, the document is still not fully aligned with the governing spec/contract layer. The biggest remaining gaps are: `OpenClaw` planning/audit ownership is still not fully reflected in the workflow, the EventBus contract is still not baseline-complete, the "canonical" repo paths still invent `packages/omega-core`, and the role contract table still omits required agent-contract fields. Re-audit is still required after another revision.

## Scope

- Audited file: `docs/AGENT_WORKFLOW.md`
- Baselines:
  - `specs/omega_quant_ai_institutional_engineering_spec_full.md`
  - `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md`
- Prior audit input:
  - `docs/AGENT_WORKFLOW_AUDIT_R1.md`

## R1 Resolution Matrix

| Prior finding | R2 status | Notes |
|---|---|---|
| R1 P0 - platform routing contradiction | PARTIALLY RESOLVED | Production impl/test routing now points to `Codex CLI`, but planning/audit ownership still diverges from spec |
| R1 P1 - event schema not canonical | UNRESOLVED | Envelope improved, but field names and mandatory event set still do not match the baseline |
| R1 P1 - gate model collapsed | RESOLVED | 6-gate model now exists with owners, artifacts, stop conditions, and `phase_gates.json` recording |
| R1 P2 - checkpoint/audit persistence under-specified | PARTIALLY RESOLVED | Checkpoint schema now includes task state/context/metrics/rationale, but directory structure still says `audit_*.json` while protocol requires append-only JSONL |
| R1 P2 - low-memory hard kill without recovery | RESOLVED | Replaced with checkpoint -> quiesce/throttle -> resume/abort flow |
| R1 P2 - examples use non-canonical paths | UNRESOLVED | `packages/omega-core` is still not grounded in either baseline spec |
| R1 P2 - agent contracts incomplete | PARTIALLY RESOLVED | 25-role table added, but required contract fields are still incomplete |
| R1 P3 - acceptance criteria too narrow | PARTIALLY RESOLVED | Broader than R1, but still narrower than the system-level baseline |

## Findings

### P1

1. **R1 P0 is only partially resolved because planning/audit ownership is still not fully aligned with the spec.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:48-53`, `docs/AGENT_WORKFLOW.md:69-74`, `docs/AGENT_WORKFLOW.md:492-496`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:1092-1106`
   - Problem: the document correctly routes production code/tests to `Codex CLI`, but it still assigns planning work to `Planner Supervisor` on `Codex CLI` and frames the formal audit artifact as a `Codex CLI` execution step. The spec assigns `OpenClaw` to planning, workflow state, gate control, and audit.
   - Impact: the most dangerous R1 inversion is reduced, but the control-plane ownership model is still not source-of-truth clean.
   - Recommendation: either move planning/audit ownership back to `OpenClaw` in the workflow, or amend the governing spec first.

2. **R1 P1 event-contract remediation is incomplete.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:271-299`, `docs/AGENT_WORKFLOW.md:303-317`, `docs/AGENT_WORKFLOW.md:580-581`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:280-326`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:224-272`
   - Problem: the envelope now contains most tracing fields, but it still renames canonical fields from `source`/`target` to `source_agent`/`target_agent`, and its event list omits baseline mandatory events such as `TASK_PLANNED`, `TASK_DISPATCHED`, `TASK_ABORTED`, `ARTIFACT_CREATED`, `DATASET_REGISTERED`, `MODEL_TRAINED`, `MODEL_PROMOTED`, `BACKTEST_COMPLETED`, `RISK_BREACH`/`RISK_LIMIT_BREACHED`, `DEPLOYMENT_COMPLETED`, `MEMORY_SNAPSHOT_CREATED`, and `EVOLUTION_PROMOTED`.
   - Impact: implementers following this workflow would still build an EventBus contract that is incompatible with the spec/contract layer.
   - Recommendation: use the canonical field names and expand the mandatory event inventory to the full baseline set.

### P2

1. **R1 P2 agent-contract coverage is still incomplete.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:63-93`
   - Source refs: `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:326-349`
   - Problem: the new 25-role table is an improvement, but it still does not provide the full required contract field set. The baseline requires `agent_id`, `agent_type`, `role`, `runtime`, `capabilities`, `inputs`, `outputs`, `scope`, `limits`, `failure_modes`, and `escalation_path`. The workflow table omits capabilities and explicit inputs, and compresses scope into informal prose.
   - Impact: the document is still weak as an implementation-ready role contract source.
   - Recommendation: expand the role appendix so every role has a complete contract record matching the baseline schema.

2. **R1 P2 canonical-path remediation is still open.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:552-569`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:56-99`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:60-103`
   - Problem: the document now labels `OMEGA_QUANT/packages/omega-core/` as canonical, but neither governing baseline defines `packages/omega-core`. The institutional spec defines top-level packages such as `packages/core`, `packages/contracts`, `packages/memory`, `packages/quant`, etc.
   - Impact: examples are still capable of sending implementers to non-baseline paths.
   - Recommendation: replace `packages/omega-core` with baseline-backed paths, or mark the example as explicitly non-normative.

3. **R1 P2 persistence hardening is improved but still internally inconsistent.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:372-385`, `docs/AGENT_WORKFLOW.md:417-423`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:252-270`, `specs/omega_quant_ai_institutional_engineering_spec_full.md:1504-1519`
   - Problem: the protocol correctly requires append-only, hash-chained JSONL audit logs, but the directory structure still declares `logs/audit_*.json`.
   - Impact: storage-path guidance and immutability guidance can diverge in implementation.
   - Recommendation: make the directory structure and protocol text agree on append-only JSONL artifacts.

### P3

1. **R1 P3 acceptance criteria are broader now but still narrower than the baseline system acceptance.**
   - Audited refs: `docs/AGENT_WORKFLOW.md:578-588`
   - Source refs: `specs/omega_quant_ai_institutional_engineering_spec_full.md:1148-1160`
   - Problem: the workflow acceptance block now covers more governance and recovery items, but it still omits baseline checks for controlled agent-team coordination, working memory retrieval, backtest reproducibility, execution-simulator reasonableness, observability completeness, and evolution-loop operability.
   - Impact: the workflow can still be declared "operational" before the broader system-level baseline is met.
   - Recommendation: either inherit the full baseline acceptance list by reference, or clearly scope this document as a workflow-only subset instead of an operational definition.

## Resolved Since R1

- The 6-gate governance model is now explicit, with owners/artifacts/stop conditions and `phase_gates.json` recording (`docs/AGENT_WORKFLOW.md:323-334`).
- The low-memory policy no longer hard-kills work; it now requires checkpointing, throttling/quiescing, forensic logging, and explicit resume/abort handling (`docs/AGENT_WORKFLOW.md:468-480`).
- The checkpoint schema now includes task state, context snapshot, metrics, decision rationale, and resume point, which materially closes the largest R1 persistence gap (`docs/AGENT_WORKFLOW.md:397-412`).

## Final Gate Decision

**Gate**: [NEEDS_FIX]

This revision is better than R1, but it is not yet approved as a source-of-truth workflow baseline. Re-audit after:

1. planning/audit ownership is reconciled with `OpenClaw` routing rules,
2. the EventBus contract is made fully canonical,
3. `packages/omega-core` is removed or formally justified, and
4. the agent-contract table is completed to the baseline schema.
