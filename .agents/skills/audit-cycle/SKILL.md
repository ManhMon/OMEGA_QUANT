---
name: audit-cycle
description: SOD audit cycle workflow - coordinates L2 implementation submission to L3 independent audit and verdict collection. Implements the audit-cycle process defined by omega-sod.
when_to_use: "When coordinating an audit cycle: L2 completes implementation, submits to L3, L3 reviews and issues verdict, gate metadata recorded. Use with /ac workflow or when driving L2->L3->gate cycle."
allowed-tools: Read, Glob, Grep, Bash
version: 1.0
priority: HIGH
---

# Audit Cycle

> Orchestrates the L2 -> L3 -> Gate audit workflow for OMEGA_QUANT SOD compliance.

---

## Overview

The audit cycle implements the mandatory segregation of duties workflow:

1. **L2 (OpenCode)**: Implements, tests, writes L2 report
2. **L3 (Codex)**: Independent audit, issues verdict
3. **L1 (Ly)**: Records gate metadata, runs enforcer

---

## Audit Cycle Phases

### Phase 1: L2 Submission

**Pre-conditions:**
- L2 role spec loaded from `REPO_AGENT_ROOT/<role>.md`
- L2 skills loaded from `REPO_SKILL_ROOT/<skill>/SKILL.md`
- Implementation complete with tests passing

**L2 deliverables:**
- Code changes in scope
- Tests passing
- L2 report at `.ly_state/session/l2_role{id}_{slug}_{YYYYMMDD}.md`
- Report MUST list exact repo-local files read

### Phase 2: L3 Independent Audit

**Pre-conditions:**
- L2 session complete and saved
- L3 role_id != L2 role_id (writer != auditor)
- L3 role spec loaded from `REPO_AGENT_ROOT/<role>.md`

**L3 deliverables:**
- Audit report at `.ly_state/session/audit_reports/role{id}_{slug}_{YYYYMMDD}.md`
- Verdict: `[APPROVED]` or `[NEEDS_FIX]`
- Gate metadata update in `phase_gates.json`

### Phase 3: Gate Recording

**L1 responsibilities:**
- Record gate metadata with all required fields
- Run `python scripts/sod_gate_enforcer.py`
- Exit 0 = safe to push; Exit 1 = blocked

---

## Gate Metadata Contract

```json
{
  "l2_session_id": "l2_role{id}_{slug}_{YYYYMMDD}",
  "l2_completed": true,
  "l2_role_id": 0,
  "l2_role_name": "...",
  "l3_session_id": "...",
  "l3_session_key": "...",
  "l3_role_id": 0,
  "l3_role_name": "...",
  "audit_report_path": ".ly_state/session/audit_reports/...",
  "final_verdict": "[APPROVED]",
  "sod_boundary_checked": true,
  "writer_auditor_separated": true
}
```

### Post-2026-06-12 Fields (STRICT_REPO_LOCAL_SKILL_LOADING)

```json
{
  "repo_local_skill_sources": [".agents/agent/role.md", ".agents/skills/skill/SKILL.md"],
  "forbidden_path_scan": "No authoritative reliance on forbidden paths"
}
```

---

## Verdict Handling

| Verdict | Action |
|---------|--------|
| `[APPROVED]` | Record gate, run enforcer, proceed if exit 0 |
| `[NEEDS_FIX]` | New L2 session with fix scope, cycle repeats |
| No verdict | Gate remains `PENDING_L3_AUDIT` |

---

## Repo-Local Skill Source Contract

**STRICT_REPO_LOCAL_SKILL_LOADING_20260612** enforcement:

1. L2/L3 MUST read role spec from `REPO_AGENT_ROOT` only
2. L2/L3 MUST read skills from `REPO_SKILL_ROOT` only
3. Forbidden paths are non-authoritative:
   - `.gemini\antigravity-ide\scratch\ag-kit`
   - `.openclaw\skills`
   - `C:\Users\GHC\.agents`
   - `.codex\memories`
4. Reports MUST document exact repo-local files read
5. Reports MUST include forbidden path scan result

---

## Anti-Patterns

| Don't | Do |
|-------|-----|
| Skip L3 audit | Always submit to L3 |
| L3 writes code | L3 audits only |
| L2 self-approves | L3 issues verdict |
| Use forbidden paths as source | Use repo-local paths only |
| Manual gate override | Enforcer exit 0 required |
| Missing repo-local evidence | Document all files read |

---

## Integration

This skill coordinates with:
- **omega-sod**: Defines the SOD framework and platform hierarchy
- **code-review-checklist**: L3 uses for review standards
- **testing-patterns**: L2 uses for test quality

---

> **Remember:** Every audit cycle must produce a verifiable gate with complete metadata and enforcer exit 0.
