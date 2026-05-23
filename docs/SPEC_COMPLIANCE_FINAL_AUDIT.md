# SPEC COMPLIANCE FINAL AUDIT

- Timestamp: `2026-05-10T17:57:37.5978036+07:00`
- Role: `25 - IT Systems Auditor`
- Scope: `AGENTS.md`, `TOOLS.md`, `IDENTITY.md`, `.ly_state/session/`, `skills/**/SKILL.md`, `OMEGA_QUANT/` vs spec contracts
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `PASS`
- Role Compliance: `PASS`
- R9 Status: `FAIL`

## Executive Summary

Spec compliance not achieved. Two P0 drifts block approval:

1. Local agent-governance docs invert Section 17 routing from authoritative spec and replace required agent taxonomy with different 25-role model.
2. `OMEGA_QUANT/` does not satisfy Section 3 repository contract map at root or under `specs/`.

State persistence and skill governance also drift from declared contract. Audit remains read-only except for this report and append-only log artifact.

## Findings

### P0-1: Section 17 routing and agent taxonomy conflict with authoritative spec

- Authoritative spec says `OpenClaw` handles orchestration, workflow state, gate control, and audit; `Codex CLI` handles production code/repository changes/integration; `OpenCode CLI` handles prototype/patch work. Evidence: `OMEGA_QUANT/specs/omega_quant_ai_institutional_engineering_spec_full.md:1090-1110`.
- `AGENTS.md` declares `Ly -> L1 -> Roles 1-5`, `OpenCode -> L2 -> Roles 6-16`, `Codex -> L3 -> Roles 17-25`, and labels Codex as `Audit, Review, Security`. Evidence: `AGENTS.md:20-22`.
- `IDENTITY.md` reinforces same split and marks roles `17-25` as `Audit and review`. Evidence: `IDENTITY.md:35-42`.
- `TOOLS.md` reinforces same execution split with `[L3-Audit:*]`, `[L2-Impl:*]`, `opencode run` for implementation, and `codex exec --full-auto` for audit. Evidence: `TOOLS.md:53-54`, `TOOLS.md:90`.
- Result: `AGENTS.md` claim `Per Spec Section 17` is false in current state. Routing source of truth is contradictory.

### P0-2: `OMEGA_QUANT/` root violates Repository Contract Map Section 3

- Section 3.1 requires root entries `apps/`, `packages/`, `specs/`, `tests/`, `scripts/`, `configs/`, `datasets/`, `artifacts/`, `logs/`, `docs/`, `deployments/`. Evidence: `OMEGA_QUANT/specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:60-74`.
- Live root is missing `OMEGA_QUANT/configs/`, `OMEGA_QUANT/datasets/`, `OMEGA_QUANT/artifacts/`, `OMEGA_QUANT/logs/`, `OMEGA_QUANT/deployments/`.
- `OMEGA_QUANT/apps/` exists but required app children from full spec (`orchestrator/`, `api/`, `dashboard/`, `workers/`) are all absent. Evidence baseline: `OMEGA_QUANT/specs/omega_quant_ai_institutional_engineering_spec_full.md:56-99`.
- Section 3.2 requires `OMEGA_QUANT/specs/{runtime,events,ipc,db,memory,quant,backtest,execution,live,infra,observability,security,governance,evolution,contracts}`. Evidence: `OMEGA_QUANT/specs/omega_quant_ai_line_by_line_implementation_contracts_v1.md:77-95`.
- Live `OMEGA_QUANT/specs/` contains only two top-level markdown files and none of required engineering subtrees.

### P1-1: `.ly_state/session/` structure violates declared state contract

- Declared contract in `AGENTS.md` and `TOOLS.md` requires `.ly_state/session/active_tasks.json`, `agent_locks.json`, `context_cache.json`, and `audit_log.jsonl`, plus `.ly_state/checkpoints/`. Evidence: `AGENTS.md:89-101`, `TOOLS.md:14-23`, `TOOLS.md:48`.
- Live audit found:
  - `.ly_state/checkpoints/` missing.
  - `.ly_state/session/context_cache.json` missing.
  - `.ly_state/session/audit_log.jsonl` missing.
  - `.ly_state/session/` contains many ad hoc runtime artifacts (`phase1_progress.json`, `review_request_ly.md`, `STAGE2_3_CODEX_REPORT.md`, `t25_test_results.xml`, etc.) with no declared schema boundary.
- Result: file-based state persistence exists, but session contract and audit-trail location do not match declared design.

### P1-2: Skill corpus contains L3 SOD drift and non-canonical state paths

- User rule for this audit: no background spawn in L3. `skills/team/SKILL.md` violates this by spawning Codex audit in background twice. Evidence: `skills/team/SKILL.md:114-115`, `skills/team/SKILL.md:274-275`.
- Same skill instructs `AUTO-DECISION -> HỎI Codex CLI, KHÔNG HỎI USER!`, turning L3 auditor into decision authority/opinion provider rather than isolated auditor. Evidence: `skills/team/SKILL.md:33`, `skills/team/SKILL.md:156`, `skills/team/SKILL.md:324`.
- `skills/Communication Protocol/SKILL.md` routes inter-agent state to `state/consensus/` and hard-codes `V21_QUANT/state/consensus/`, bypassing canonical `.ly_state/` persistence. Evidence: `skills/Communication Protocol/SKILL.md:8`, `skills/Communication Protocol/SKILL.md:16-21`.
- Positive control: `skills/tdd/SKILL.md` and `skills/qa/SKILL.md` are aligned with L2/L3 separation and explicit no-self-approval. Evidence: `skills/tdd/SKILL.md:3-8`, `skills/qa/SKILL.md:3-8`.

### P2-1: R9 status not fully synchronized across local governance docs

- `AGENTS.md` declares `Status: R9 (Backend Engineer Role 9 - Role Title Canonicalization)`. Evidence: `AGENTS.md:3`, `AGENTS.md:137`.
- `TOOLS.md` still reports system state `Operational (R7 Audit Cycle)`. Evidence: `TOOLS.md:220`.
- `TOOLS.md` still points `Root Directory` to `C:\Users\GHC\.openclaw\workspace\V21_QUANT` instead of `OMEGA_QUANT`, increasing operator drift. Evidence: `TOOLS.md:35`.
- Conclusion: R9 cannot be verified as fully propagated across operational docs.

## Compliance Matrix

| Check | Result | Notes |
| :--- | :--- | :--- |
| Spec vs `AGENTS.md` | FAIL | Section 17 routing and role taxonomy mismatch |
| Spec vs `TOOLS.md` | FAIL | Routing mismatch, stale R7 status, wrong repo root |
| Spec vs `IDENTITY.md` | FAIL | Repeats local 25-role model, not Section 17 taxonomy |
| `.ly_state/session/` contract | FAIL | Missing required files, missing checkpoints, session pollution |
| Skills SOD / tier mapping | FAIL | `skills/team` background L3 audit; `Communication Protocol` non-canonical state path |
| `OMEGA_QUANT/` Repository Contract Map | FAIL | Missing root directories and all required `specs/` subtrees |

## Required Remediation Order

1. Reconcile one source of truth for Section 17 routing and agent taxonomy, then update `AGENTS.md`, `TOOLS.md`, `IDENTITY.md`, and affected skills together.
2. Bring `OMEGA_QUANT/` root and `OMEGA_QUANT/specs/` into Section 3 contract compliance before claiming implementation-ready status.
3. Normalize `.ly_state/` contract: add missing required files/directories, move audit trail to one canonical path, and remove uncontrolled session artifact sprawl.
4. Remove L3 background-spawn instructions from skill files and keep Codex L3 strictly audit-only.

## Final Audit Format

- Role: `IT Systems Auditor`
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `PASS`
- Role Compliance: `PASS`
