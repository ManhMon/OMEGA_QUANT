# AGENT WORKFLOW - OMEGA_QUANT

**Version**: 2.4
**Status**: APPROVED (Independent Audit R3 Passed)
**Last Updated**: 2026-05-22 13:50 GMT+7
**Baselines**: `specs/omega_quant_ai_institutional_engineering_spec_full.md`, `specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md`
**Audit Input**: `docs/TEAM_AGENT_FINAL_AUDIT_R6.md`
**Independent Audit**: `docs/AGENT_WORKFLOW_AUDIT_R3.md`
**Gate Key**: `OMEGA_AGENT_WORKFLOW_GOVERNANCE_20260522`

---

## CHANGE LOG

- R2 fix: moved planning ownership to `OpenClaw/Ly` and made `OpenClaw/Ly` the formal audit-orchestration and gate-owner layer.
- R2 fix: normalized EventBus envelope to canonical `source` / `target` fields and expanded the mandatory baseline event inventory.
- R2 fix: replaced the partial role table with a full agent-contract schema covering `agent_id`, `agent_type`, `role`, `runtime`, `capabilities`, `inputs`, `outputs`, `scope`, `limits`, `failure_modes`, and `escalation_path`.
- R2 fix: removed normative `packages/omega-core` references; examples now use baseline package roots and mark legacy repo-specific paths as non-normative.
- R2 fix: aligned audit persistence to `.ly_state/session/audit_log.jsonl` with append-only JSONL hash-chain semantics.
- R2 fix: expanded acceptance criteria to include controlled coordination, working memory retrieval, backtest reproducibility, execution-simulator reasonableness, observability completeness, and evolution-loop operability.
- v1.3-SOD-FIX: Added explicit Segregation of Duties (SOD) and session-boundary enforcement rules. Implementation sessions must never audit or approve their own artifacts. Added mandatory session labeling and read-only constraints for audit-only roles. Clarified that Ly/OpenClaw owns the final gate decision, while Codex Review Agent provides a verdict recommendation. Added fresh session requirement for audits.

---

## 0. SOURCE-OF-TRUTH RULE

If this workflow conflicts with the institutional engineering spec or the implementation contracts, the spec or contract wins. This document is an operational routing layer, not a normative override.

---

## 1. EXECUTIVE SUMMARY

This document defines the orchestration workflow for the OMEGA_QUANT 25-role agent system.

- `OpenClaw/Ly` owns planning, workflow state, gate control, audit orchestration, and formal approval records.
- `OpenCode CLI` owns build/code implementation, repository changes, test implementation, and integration work for L2 delivery.
- `Codex CLI` owns audit, review, security validation, and verdict artifacts for L3 gate control.
- **Segregation of Duties (SOD)**: The implementation role/session must never audit or approve its own artifact. Writer and Auditor must be distinct roles in distinct sessions.
- Every task must remain traceable from request -> plan -> execution -> audit -> gate decision -> deployment or rollback.

---

## 2. PLATFORM OWNERSHIP

| Runtime | Canonical Ownership | Hard Limits |
|---|---|---|
| `OpenClaw / Ly` | Orchestration, planning, workflow state, gate control, audit orchestration, user interface, state persistence | No direct production code edits unless explicitly authorized by the user and later audited |
| `OpenCode CLI` | Implementation, code, build, design | Must emit explicit artifacts and reports; no silent completion |
| `Codex CLI` | Audit, review, security validation | Audit execution and reports |

**Session Boundary Rules**:
- **Implementation Sessions**: Must be labeled as `[L2-Impl:RoleXX-*]`.
- **Audit Sessions**: Must be labeled as `[L3-Audit:RoleXX-*]`.
- **Audit-Only Constraints**: Audit sessions are read-only for target artifacts. They may only write audit reports and audit logs.
- **No-MCP Self-Discovery Constraint**: L3 audit sessions MUST NOT load MCP/CRG tools or perform graph self-discovery. L1 (Ly) is the sole scanner and prepares the minimal context. L3 reads only the L1-prepared context, targets the defined files, runs validation, and writes the audit report.
- **Self-Approval Prohibition**: A session that modifies an artifact cannot audit or approve that same artifact. Impl session MUST terminate before Audit session spawns.

**Routing invariant**:
- implementation, build, and design -> `OpenCode CLI`
- planning, workflow state, gate control, and audit control-plane ownership -> `OpenClaw/Ly`
- audit, review, security validation -> `Codex CLI`

---

## 3. END-TO-END TASK LIFECYCLE

```text
USER REQUEST
  -> OpenClaw/Ly: classify request + create task state
  -> OpenClaw/Ly / Project Manager (Role 1): task DAG + dependencies + resource plan
  -> System Architect (Role 6): contract and design artifacts if required
  -> OpenCode CLI (Implementation Session): production implementation + tests + execution artifacts
  -> [TERMINATE IMPLEMENTATION SESSION]
  -> OpenClaw/Ly: gate orchestration + prepare minimal context + dispatch audit
  -> Codex CLI Code Reviewer (Role 21) (Audit Session): audit execution + verdict recommendation
  -> [TERMINATE AUDIT SESSION]
  -> OpenClaw/Ly: formal audit artifact validation + final gate decision
  -> Gates: architecture + review + test + risk + security + deployment
  -> [APPROVED] commit/push/deploy
  -> [NEEDS_FIX] route back to implementation loop (fresh Writer session)
```

**Control-plane rule**:
- `OpenCode CLI` produces the implementation artifacts.
- `OpenClaw/Ly` decides when an audit is required, what scope is audited, and whether the artifact is sufficient for gate progression.
- `Codex CLI` produces the audit artifact and verdict recommendation.
- `OpenClaw/Ly` owns the final gate decision and records the approval or rejection in workflow state.
- **Independence**: The Review Agent must reject any implementation or fix requests. Implementation must be handled by a separate writer/fixer role.

---

## 4. AGENT CONTRACT BASELINE

Every invocation must conform to the baseline schema below:

```text
agent_id
agent_type
role
runtime
capabilities
inputs
outputs
scope
limits
failure_modes
escalation_path
```

### 4.1. Contract records

| agent_id | agent_type | role | runtime | capabilities | inputs | outputs | scope | limits | failure_modes | escalation_path |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | supervisor | Project Manager | `OpenClaw/Ly` | classify, route, lock, gate | user request, workflow state | task record, routing decision | end-to-end control plane | no code edits | unresolved blocker | user |
| 2 | supervisor | Product Owner | `OpenClaw/Ly` | define features, prioritize | user requests, roadmap | product backlog | feature definition | no architecture descisions | misaligned priorities | Project Manager |
| 3 | supervisor | Scrum Master | `OpenClaw/Ly` | manage agile process | task status, team feedback | sprint plan | process management | no code edits | process breakdown | Project Manager |
| 4 | supervisor | Release Manager | `OpenClaw/Ly` | manage deployment gates | gate artifacts, versions | release decision | deployment pipeline | no code edits | release failure | Project Manager |
| 5 | supervisor | Delivery Manager | `OpenClaw/Ly` | manage timelines, resources | schedules, resource stats | delivery plan | project delivery | no code edits | timeline slip | Project Manager |
| 6 | specialist | System Architect | `OpenCode CLI` | design system, contracts | requirements, specs | architecture delta | system design | production code | broken architecture | Project Manager |
| 7 | specialist | Tech Lead | `OpenCode CLI` | code standards, coordination | design docs, repo | impl plan | engineering standards | production code | poor code quality | System Architect |
| 8 | specialist | Frontend Engineer | `OpenCode CLI` | implement UI | design specs, repo | UI code | frontend scope | production code | UI bug | Tech Lead |
| 9 | specialist | Backend Engineer | `OpenCode CLI` | implement API | API specs, repo | backend code | backend scope | production code | API failure | Tech Lead |
| 10 | specialist | Database Admin | `OpenCode CLI` | schema design, performance | data models, queries | schema, tuning config | database scope | production code | slow queries | Tech Lead |
| 11 | specialist | DevOps Engineer | `OpenCode CLI` | CI/CD pipelines | infra requirements | pipeline config | CI/CD scope | production code | broken build | Tech Lead |
| 12 | specialist | Cloud Infra Engineer| `OpenCode CLI` | IaC, provisioning | architecture, scale needs| IaC config | infrastructure scope | production code | provisioning error | System Architect |
| 13 | specialist | UI/UX Integrator | `OpenCode CLI` | UI styling, consistency | mockups, components | styled UI | UI consistency scope | production code | styling issue | Frontend Engineer |
| 14 | specialist | Data Scientist | `OpenCode CLI` | signal research, models | datasets, alpha ideas | research report | ML research scope | production code | bad model | Tech Lead |
| 15 | specialist | Data Engineer | `OpenCode CLI` | data pipelines, ETL | data sources, schemas | ETL code | data pipeline scope | production code | missing data | Database Admin |
| 16 | specialist | Machine Learning Eng| `OpenCode CLI` | ML training pipelines | models, data | ML pipelines | ML deployment scope | production code | pipeline failure | Data Scientist |
| 17 | auditor | QA Engineer | `Codex CLI` | functional testing | test cases, app | test report | QA scope | audit only | uncaught bug | Release Manager |
| 18 | auditor | SDET | `Codex CLI` | automated test execution and validation | app, test framework | test execution report | test automation scope | audit only | broken test | QA Engineer |
| 19 | auditor | Security Auditor | `Codex CLI` | security scanning | repo, infra | security report | security scope | audit only | missed vuln | Release Manager |
| 20 | auditor | Compliance Officer | `Codex CLI` | compliance checks, PIT | quant rules | compliance report | compliance scope | audit only | PIT violation | Release Manager |
| 21 | auditor | Code Reviewer | `Codex CLI` | peer review | PR, code | review report | code review scope | audit only | missed bad code | Tech Lead |
| 22 | auditor | Penetration Tester | `Codex CLI` | adversarial testing | app, infra | pen test report | security scope | audit only | unexploited risk| Security Auditor |
| 23 | auditor | Performance Tester | `Codex CLI` | load testing | app, load spec | perf report | performance scope | audit only | slow app | QA Engineer |
| 24 | auditor | UAT Validator | `Codex CLI` | acceptance validation | app, criteria | UAT report | UAT scope | audit only | failed UAT | Product Owner |
| 25 | auditor | IT Systems Auditor | `Codex CLI` | overall governance audit| logs, systems | governance report | governance scope | audit only | compliance fail | Project Manager |

### 4.2. Invocation rules

- One invocation = one role = one task.
- Context must be minimal and task-scoped.
- Output must be an explicit artifact or explicit failure.
- Escalation must follow the declared `escalation_path`; silent abandonment is invalid.
- **Dual-Role Exception**: OpenCode acts as an implementation platform, Codex acts as an audit platform. They cannot perform both on the same artifact.
- **Review Agent Constraint**: The Code Reviewer (Role 21) and Compliance Officer (Role 20) are restricted to audit-only tasks. They must never perform code fixes or implement features. If a fix is required, the audit session must terminate and a fresh implementation session must be spawned.

---

## 5. TASK ROUTING PROTOCOL

### 5.1. `OpenClaw/Ly` responsibilities

- receive user requests
- classify complexity and scope
- invoke the Project Manager (Role 1)
- track task state in `.ly_state/session/active_tasks.json`
- automatically update the plan (via `update_plan` tool) after key milestones (gate approvals, phase completions, architecture pivots)
- enforce resource constraints before dispatch
- trigger audits and own gate progression
- escalate unresolved conflicts to the user

### 5.2. Routing rules

| Task Type | Primary Route | Rationale |
|---|---|---|
| new feature | Project Manager (Role 1) | requires DAG, dependencies, resource plan |
| architecture change | System Architect (Role 6) | requires contract and interface review |
| bug fix | Tech Lead (Role 7) | direct implementation oversight |
| research spike | Data Scientist (Role 14) | exploratory work only |
| test failure | QA Engineer (Role 17) | test orchestration and acceptance |
| security concern | Security Auditor (Role 19) | immediate security review |
| risk concern | Compliance Officer (Role 20) | immediate risk gate evaluation |
| runtime instability | DevOps Engineer (Role 11) | scheduler, checkpoint, worker analysis |

### 5.3. Specialist execution protocol

1. Receive one task from the owning supervisor or `OpenClaw/Ly`.
2. Load only the role spec, task description, and input files.
3. Execute task and persist state changes to `.ly_state/session/` or `.ly_state/memory/`.
4. Emit artifacts and completion or failure events.
   - **Anti-Silent-Failure Rule**: All execution agents MUST verify their artifacts exist before terminating. They MUST catch command/script errors and report them, never timing out silently. Output payload MUST contain the explicit path to the verified artifact.
5. Terminate after handoff.

---

## 6. EVENT-DRIVEN IPC

### 6.1. EventBus Architecture (Section 22/5.1)

```text
[Agent A] -> EventBus (Real Message Backbone) -> [Agent B]
               |
          [State Store / Database]
          (DB/Registry for durable records, .ly_state/ for local session checkpointing)
```

No direct agent-to-agent side channel is allowed for workflow-critical coordination. The EventBus must use real queues with retry, dead-letter, idempotent consumer, and at-least-once delivery guarantees. Local `.jsonl` file logs may remain as a single-node Phase A fallback only.

### 6.2. Canonical event envelope

All EventBus messages must use this envelope:

```json
{
  "event_id": "uuid",
  "event_version": "semver",
  "event_type": "string",
  "timestamp": "ISO-8601",
  "source": "string",
  "target": "string",
  "correlation_id": "uuid",
  "causation_id": "uuid|null",
  "trace_id": "uuid",
  "severity": "DEBUG | INFO | WARN | ERROR | CRITICAL",
  "payload": {},
  "metadata": {
    "priority": 0,
    "retry_count": 0,
    "timeout_ms": 0,
    "schema_hash": "sha256"
  }
}
```

### 6.3. Mandatory baseline event types

- `TASK_CREATED`
- `TASK_PLANNED`
- `TASK_DISPATCHED`
- `TASK_STARTED`
- `TASK_COMPLETED`
- `TASK_FAILED`
- `TASK_RETRIED`
- `TASK_ABORTED`
- `ARTIFACT_CREATED`
- `ARTIFACT_VALIDATED`
- `DATASET_REGISTERED`
- `DATA_QUALITY_FAILED`
- `MODEL_TRAINED`
- `MODEL_PROMOTED`
- `MODEL_ROLLED_BACK`
- `RISK_LIMIT_BREACHED`
- `DEPLOYMENT_STARTED`
- `DEPLOYMENT_COMPLETED`
- `DEPLOYMENT_ROLLED_BACK`
- `MEMORY_SNAPSHOT_CREATED`
- `EVOLUTION_PROMOTED`

### 6.4. Delivery semantics

- delivery: at-least-once
- ordering: causal ordering per `correlation_id`
- idempotency: consumers must dedupe by `event_id`
- retry: bounded exponential backoff with `TASK_RETRIED`
- dead letter: exhausted retries -> `.ly_state/session/dead_letters.jsonl`
- schema evolution: additive-only for minor versions; breaking changes require a new major `event_version`

### 6.5. Example event routing map

| event_type | source | target | payload minimum | purpose |
|---|---|---|---|---|
| `TASK_CREATED` | `OpenClaw/Ly` | `Project Manager (Role 1)` | `task_id`, `description` | create planning record |
| `TASK_PLANNED` | `Project Manager (Role 1)` | `OpenClaw/Ly` | `task_id`, `task_graph_ref` | return DAG |
| `TASK_DISPATCHED` | `OpenClaw/Ly` | role runtime | `task_id`, `role`, `artifact_targets` | dispatch execution |
| `TASK_COMPLETED` | execution role | `OpenClaw/Ly` | `task_id`, `artifacts` | mark task complete |
| `ARTIFACT_CREATED` | execution role | `OpenClaw/Ly` | `task_id`, `artifact_path` | register output |
| `ARTIFACT_VALIDATED` | gate owner | `OpenClaw/Ly` | `artifact_path`, `gate` | confirm artifact is gate-usable |
| `RISK_LIMIT_BREACHED` | `Compliance Officer (Role 20)` | `OpenClaw/Ly` | `task_id`, `breach` | stop progression |
| `MEMORY_SNAPSHOT_CREATED` | `Project Manager (Role 1)` | `OpenClaw/Ly` | `task_id`, `snapshot_path` | record resume point |
| `DEPLOYMENT_COMPLETED` | `DevOps Engineer (Role 11)` | `OpenClaw/Ly` | `deployment_id`, `status` | complete rollout |

---

## 7. DEPENDENCY GRAPH AND GATE MODEL

### 7.1. Gate model and API Contracts (Section 21)

All governance decisions, artifact registration, and state mutations must flow through the Section 21 versioned, stateless API contracts.

**Core APIs**: Task API, Artifact API, Dataset API, Model API, Backtest API, Execution API.

| Gate | Owner | Required Artifact | Stop Condition |
|---|---|---|---|
| Architecture Gate | System Architect (Role 6) | design delta or contract diff | missing contract, unresolved dependency |
| Review Gate | Code Reviewer (Role 21) | audit report with P0-P3 findings | any unresolved P0 or P1 |
| Test Gate | QA Engineer (Role 17) / SDET (Role 18) | test log and coverage result | failing tests or inadequate coverage |
| Risk Gate | Compliance Officer (Role 20) | risk validation report | PIT breach, leakage, or limit breach |
| Security Gate | Security Auditor (Role 19) | security validation report | secret leak, unsafe permission, unsafe write target |
| Deployment Gate | Project Manager (Role 1) | approval record and rollback plan | missing rollback or reconciliation plan |

A phase is `[APPROVED]` only when all required gates are approved and recorded in `.ly_state/session/phase_gates.json`.

### 7.2. Dependency rules

- sequential: downstream task waits for upstream completion
- parallel: tasks may run concurrently if locks and RAM permit
- conditional: downstream task starts only after condition-specific artifact validation

Blocked tasks must remain in `.ly_state/session/blocked_tasks.json` until their dependencies are resolved.

### 7.3. Blocking conditions

**Hard blockers**:
- missing credentials
- destructive operation approval
- business decision required
- external dependency unavailable
- severe risk breach
- severe security finding

**Soft blockers**:
- temporary resource exhaustion
- timeout with retry budget remaining
- flaky test quarantined for rerun

---

## 8. STATE PERSISTENCE SOP

### 8.1. Persistence Architecture (Section 6)

The storage layer is divided into durable enterprise state and local session state:

**Enterprise Database / Registry Layer** (Durable, Versioned)
- `datasets`: dataset registry
- `models`: model registry
- `experiments`: experiment records
- `backtests`: backtest results
- `risk_reports`: risk reports
- `executions`: execution records
- `artifact_store`: blob/file storage for trained models, reports, etc.

**Local Session Checkpoints & Caches** (Ephemeral / Worker State)
```text
.ly_state/
  session/
    active_tasks.json
    task_graph.json
    blocked_tasks.json
    agent_locks.json
    phase_gates.json
    context_cache.json
    event_log.jsonl
    .ly_state/session/audit_log.jsonl
    dead_letters.jsonl
    checkpoints/
      <task_id>.json
  memory/
    session_*.json
```

### 8.2. Checkpoint protocol

Checkpoint when:
- planning completes
- code patch is applied
- tests pass
- audit gates return
- deployment is about to start
- RAM drops below the workflow threshold

Checkpoint schema:

```json
{
  "checkpoint_id": "uuid",
  "task_id": "string",
  "timestamp": "ISO-8601",
  "agent_id": 0,
  "role": "string",
  "task_state": "READY | RUNNING | BLOCKED | FAILED | APPROVED",
  "context_snapshot": {
    "files": [],
    "prompts": [],
    "inputs_hash": "sha256"
  },
  "files_changed": [],
  "tests_passed": [],
  "metrics": {
    "duration_ms": 0,
    "ram_mb": 0,
    "coverage_pct": 0
  },
  "decision_rationale": "string",
  "artifacts": [],
  "resume_point": "string"
}
```

### 8.3. Audit log protocol

Audit logs must be written to `.ly_state/session/audit_log.jsonl` and must obey all of the rules below:

- append-only JSONL
- one audit record per line
- each record includes `prev_hash` and `record_hash`
- never rewritten in place
- report artifacts remain external Markdown files such as `docs/*AUDIT*.md`

Minimum audit-log record shape:

```json
{
  "audit_id": "uuid",
  "timestamp": "ISO-8601",
  "task_id": "string",
  "artifact_path": "string",
  "verdict": "APPROVED | NEEDS_FIX | CONDITIONAL",
  "prev_hash": "sha256|null",
  "record_hash": "sha256"
}
```

### 8.4. Resume protocol

1. Read the latest checkpoint from `.ly_state/session/checkpoints/`.
2. Restore file state and the `context_snapshot`.
3. Resume from `resume_point`.
4. Emit `TASK_STARTED` or `TASK_ABORTED` as appropriate.

---

## 9. CONFLICT RESOLUTION AND RESOURCE MANAGEMENT

### 9.1. Resource locks

Lock types:
- file lock
- platform lock
- RAM reservation

Lock protocol:
1. agent emits a lock-related event
2. EventBus checks availability
3. on success, write grant to `.ly_state/session/agent_locks.json`
4. on conflict, queue request and keep task blocked
5. releasing agent emits the corresponding release path through workflow state

### 9.2. Escalation path

1. specialist -> supervisor
2. supervisor -> `OpenClaw/Ly`
3. `OpenClaw/Ly` -> user

### 9.3. Low-memory policy

No hard kill without recovery.

Memory pressure flow:
1. checkpoint active task
2. emit pressure-related event and persist state
3. quiesce or throttle task
4. persist forensic log
5. resume when safe or abort with explicit audit trail

Thresholds:
- RAM < 10 GB -> no new heavy task
- RAM < 8 GB -> checkpoint and quiesce or throttle

---

## 10. AUDIT LOOP INTEGRATION

### 10.1. Mandatory audit rule

After every production implementation or workflow-governing documentation update, `OpenClaw/Ly` must trigger a Codex audit and require an explicit artifact.

### 10.2. Audit control flow

```text
OpenCode CLI implementation complete
  -> OpenClaw/Ly: register artifacts + open audit gate
  -> OpenClaw/Ly: dispatch Codex audit request with artifact target
  -> Code Reviewer (Role 21) on Codex CLI: execute audit and write report
  -> OpenClaw/Ly: validate report presence, scope, and verdict
  -> [APPROVED] advance gate state
  -> [NEEDS_FIX] route back to Tech Lead (Role 7)
```

### 10.3. Audit scope

- code changes
- tests and coverage
- contracts and interface compliance
- documentation that controls implementation behavior
- PIT safety, T-1 lag, and no-look-ahead rules where applicable

### 10.4. Audit artifact schema

A valid audit artifact must contain:
- executive summary
- verdict: `[APPROVED]`, `[NEEDS_FIX]`, or `[CONDITIONAL]`
- findings by severity with `file:line` references
- recommendations
- verdict recommendation

An empty or silent audit is invalid and must be retried.

### 10.5. Fix loop

1. Tech Lead (Role 7) analyzes findings.
2. P0 and P1 issues are fixed first.
3. The appropriate implementation role applies the fix.
4. Tests rerun.
5. `OpenClaw/Ly` retriggers the Codex audit.
6. Loop until `[APPROVED]` or user intervention.

### 10.6. Current audit requirement

For this revision, `OpenClaw/Ly` must dispatch an independent Codex audit with an explicit artifact requirement at:

`docs/AGENT_WORKFLOW_AUDIT_R7.md`

### 10.7. Segregation of Duties (SOD) Enforcement

1. **Independent Verification**: Every artifact modified in an `[L2-Impl]` session MUST be verified in a separate `[L3-Audit]` session.
2. **Fresh Context**: The `OpenClaw/Ly` orchestrator must prepare a fresh, minimal context for the Audit session, ensuring it only contains the target artifacts and relevant specs.
3. **No Self-Approval**: No agent role is authorized to approve its own work. Even if an agent has `Codex` capabilities, it cannot issue an `[APPROVED]` verdict for an artifact it created or modified.
4. **Gate decision**: The final `APPROVED` status in `phase_gates.json` is written only by `OpenClaw/Ly` based on the independent audit verdict.

---

## 11. CANONICAL PATH RULE

### 11.1. Normative package roots

Workflow examples must use baseline-backed package roots only:

```text
packages/core/
packages/contracts/
packages/memory/
packages/quant/
packages/backtest/
packages/execution/
packages/risk/
packages/data/
packages/infra/
packages/observability/
packages/security/
packages/governance/
```

### 11.2. Legacy path note

Any repo-specific path such as `packages/omega-core` is legacy and non-normative for this workflow document unless a governing spec is updated to define it explicitly.

### 11.3. Example: new feature request

**User Request**: "Implement RSI indicator with T-1 lag"

1. `OpenClaw/Ly` receives request and creates task state.
2. Project Manager (Role 1) writes the task DAG to `.ly_state/session/task_graph.json`.
3. System Architect (Role 6) writes the contract delta to `specs/quant/` or `packages/contracts/`.
4. Backend Engineer (Role 9) implements the production patch in `packages/quant/`.
5. DevOps Engineer (Role 11) or Backend Engineer (Role 9) writes or updates regression coverage in `tests/`.
6. `OpenClaw/Ly` dispatches the Codex audit.
7. Code Reviewer (Role 21) writes the report artifact to `docs/*AUDIT*.md`.
8. `OpenClaw/Ly` records the final gate decision.

---

## 12. ACCEPTANCE CRITERIA

This workflow is operational only when all of the following are true:

- the task graph runs stably
- agent-team coordination is controlled by the declared routing and gate model
- the EventBus and IPC layers enforce the canonical schema
- working memory retrieval operates correctly
- backtests are reproducible
- the execution simulator is reasonable against the governing contract
- the risk gate blocks bad cases
- live-trading flows have reconciliation
- observability is complete enough for tracing, metrics, logs, and audit
- deployment has rollback
- the evolution loop is operational
- all behavior is auditable
- all 25 roles have complete contract records
- checkpoint and resume are tested and documented
- audit logs remain append-only and hash-chained
- gate approvals are recorded in `.ly_state/session/phase_gates.json`
- Codex audit artifacts are non-empty and verdict-bearing
- **independent audit**: every change is audited in a fresh session distinct from the implementation session
- **no self-approval**: implementation agents never approve their own work; Review Agents never write implementation code

---

## 13. NEXT STEPS

1. Run the Codex R7 audit and require `docs/AGENT_WORKFLOW_AUDIT_R7.md`.
2. Sync related routing and identity documents if this workflow becomes the new control-plane baseline.
3. Run an end-to-end workflow drill from feature request through gate completion.

---

**Document Owner**: `OpenClaw/Ly`
**Reviewed By**: Supervisors and Codex audit roles
**Last Updated**: 2026-05-10 17:10 GMT+7
**Version**: 2.3
