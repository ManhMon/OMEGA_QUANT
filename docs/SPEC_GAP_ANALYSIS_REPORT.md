# SPEC GAP ANALYSIS REPORT

**Date**: 2026-05-10
**Auditor Role**: [ROLE: 16 - Review Agent]
**Session Type**: [L3-Audit:Role16-Review]
**Target Artifacts**:
- Original Specs: `omega_quant_ai_institutional_engineering_spec_full.md`, `omega_quant_ai_line_by_line_implementation_contracts_v1.md`
- Governance Docs: `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md`, `TEAM_ARCHITECTURE.md`, `AGENT_WORKFLOW.md`, `IMPLEMENTATION_CONTRACT_CHECKLIST.md`

## EXECUTIVE SUMMARY

A line-by-line comparison between the original Institutional Engineering and Contracts specs (v1.0) and the current active governance documents (Version 2.3) reveals high alignment on the agent-role definitions and segregation of duties, but significant deviations and gaps in **persistence layers, API definitions, experiment governance, and artifact registries**. The governance docs have skewed heavily towards CLI/CLI-orchestration via `.ly_state` while neglecting the structured database, API layers, and formal registry structures mandated by the spec.

**Verdict**: [NEEDS_FIX] (for Governance Docs / Architectural Implementation Plans)

## FINDINGS (P0 - P3)

### P1: Missing Database and Structured Registry Persistence (Section 6)
- **Spec**: Section 6.2 mandates core tables/collections including `datasets`, `models`, `experiments`, `backtests`, `risk_reports`, and `executions`. Section 6.4 and 6.5 mandate a Model Registry and Artifact Store.
- **Current Docs**: `AGENTS.md` and `TOOLS.md` restrict all state persistence to the `.ly_state/` filesystem (`session/`, `memory/`, `checkpoints/`). There is no governance tracking for the `artifacts/`, `datasets/`, or database-level stores required by the spec. The `.ly_state` mechanism covers Task State (Section 4.2) but ignores the broader Data/Artifact storage requirements.
- **Deviation**: The CLI-centric `.ly_state` filesystem cannot fulfill the relational/query requirements of the Model Registry, Dataset Versions, or Backtest tracking.

### P1: Omission of API Contract Spec (Section 21)
- **Spec**: Section 21 mandates stateless request handling, versioned endpoints, and core APIs (Task API, Artifact API, Dataset API, Model API, Backtest API, Execution API).
- **Current Docs**: `AGENT_WORKFLOW.md` and `TEAM_ARCHITECTURE.md` only document CLI execution flows (`exec(pty=true)`, background sessions, OpenClaw/Ly).
- **Gap**: The entire API layer required for institutional integration is absent from the workflow and state models.

### P2: Evolution Engine & Experiment Registry Gap (Section 16 & 29)
- **Spec**: Requires an `experiments` store, `benchmark_runner`, and `promotion_manager` to log hypothesis, configs, and metrics before promotion.
- **Current Docs**: Mentions Evolution Supervisor/Agent, but provides no structured persistence protocol (like `.ly_state/experiments/`) to track these lifecycles.

### P2: EventBus Implementation Deviation (Section 5 & 22)
- **Spec**: Requires `at-least-once delivery`, `idempotent consumer`, and queues (task, retry, dead-letter, scheduled, priority).
- **Current Docs**: `AGENT_WORKFLOW.md` models the EventBus purely as a state store interaction: `[Agent A] -> EventBus -> [Agent B]` over `.ly_state/`.
- **Deviation**: Relying entirely on local file writes (`.ly_state/session/event_log.jsonl`) without an actual message broker limits scaling to the "Phase A" (Single-node) roadmap (Section 32) and may fail the IPC robustness required in Section 5.3.

### P3: Superficial Versioning Checks in Checklist
- **Spec**: Section 2.5 mandates semantic versioning for everything (schema, model, dataset).
- **Current Docs**: `IMPLEMENTATION_CONTRACT_CHECKLIST.md` rigidly requires the literal string `Version: 2.3` as a passing criteria (Items 1, 5, 11). This is brittle and conflates the document version with the semantic version of individual components.

## RECOMMENDATIONS / REQUIRED FIXES

1. **Expand Persistence Governance**: Update `TOOLS.md` and `AGENT_WORKFLOW.md` to define how the Model Registry, Dataset Registry, Experiment Store, and Artifact Store are persisted alongside `.ly_state/`.
2. **Reintegrate API Specifications**: If the system is currently in Phase A (single-node CLI), explicitly state this in `HEARTBEAT.md` or `AGENT_WORKFLOW.md` to formally defer Section 21 (API Contracts) to Phase B, rather than silently omitting it.
3. **Formalize EventBus Backbone**: Clarify whether the EventBus is currently mocked via `.jsonl` files or if `Queue Agent` is tasked with standing up a real broker (e.g., Redis/RabbitMQ/Kafka).
4. **Fix Checklist Versioning**: Update `IMPLEMENTATION_CONTRACT_CHECKLIST.md` to verify generic semantic versioning (`schema_version`, etc.) rather than hardcoding `Version: 2.3`.