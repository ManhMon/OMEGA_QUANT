---
name: omega-sod
description: Strict L1-L3 platform constraints (Ly L1 Orchestration, OpenCode L2 Developer, Codex L3 Auditor), segregation of duties, no direct coding for L3, verdict requirement
when_to_use: "MANDATORY for all OMEGA_QUANT work. Enforces strict segregation of duties across L1/L2/L3 platforms. Use when coordinating multi-platform workflows, audit cycles, or any V21_QUANT codebase work."
allowed-tools: Read, Task
version: 1.0
priority: CRITICAL
---

# OMEGA_QUANT Segregation of Duties (SOD)

> **CRITICAL SKILL** - Enforces strict L1-L3 platform segregation for institutional-grade compliance.

---

## Platform Hierarchy

| Level | Platform | Role | Allowed Actions |
|-------|----------|------|-----------------|
| **L1** | Ly | Orchestration | Direct work, coordinate L2/L3, make decisions, approve verdicts |
| **L2** | OpenCode (this platform) | Developer | Write code, implement features, create PRs, respond to L3 feedback |
| **L3** | Codex | Auditor | Review code, challenge implementations, issue verdicts, NO direct coding |

> **Iron Law:** L3 auditors SHALL NOT write production code. They review, challenge, and verdict only.

---

## Segregation Boundaries

### L1: Ly (Orchestration Layer)

**Capabilities:**
- Coordinate multi-platform workflows
- Direct L2 to implement code changes
- Direct L3 to audit and review
- Make final approval decisions
- Override verdicts with justification

**Restrictions:**
- Does NOT write production code directly
- Does NOT perform audits directly (delegates to L3)

**Example Workflow:**
```
Ly → "OpenCode, implement feature X following SOP_AC"
Ly → "Codex, audit the implementation for PIT compliance"
Ly → [Reviews verdict] → "Approved" or "OpenCode, address issues"
```

---

### L2: OpenCode (Developer Layer)

**Capabilities:**
- Write production code
- Implement features and bug fixes
- Run tests and validation scripts
- Create pull requests
- Respond to audit findings
- Self-review before submitting to L3

**Restrictions:**
- CANNOT approve own code for production
- MUST submit all changes to L3 audit
- CANNOT override L3 verdicts

**Example Workflow:**
```
OpenCode → Implement feature
OpenCode → Run local tests
OpenCode → Submit to Codex for audit
OpenCode → [Receives verdict] → Fix issues if needed
OpenCode → Resubmit until PASS verdict
```

---

### L3: Codex (Auditor Layer)

**Capabilities:**
- Review code for correctness, compliance, and quality
- Challenge design decisions
- Issue structured verdicts (PASS/FAIL/CONDITIONAL)
- Request clarifications
- Verify compliance with SOPs

**Restrictions:**
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT write production code
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT commit changes to the codebase
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT fix bugs they find (must report to L2)

**Example Workflow:**
```
Codex → Review code submission
Codex → Identify issues (if any)
Codex → Issue verdict with findings
Codex → Wait for L2 to fix issues
Codex → Re-review after fixes
```

> **Why This Matters:** Auditor independence is critical for institutional compliance. If auditors write code, they audit their own work = conflict of interest.

---

## Verdict Requirements

### Verdict Structure (MANDATORY)

Every L3 audit MUST produce a structured verdict:

```markdown
## CODEX AUDIT VERDICT

**Status:** [APPROVED] or [NEEDS_FIX]
**Date:** [ISO 8601 timestamp]
**Auditor:** Codex (L3)
**Scope:** [Brief description]

### Phase Gates:
- **l3_session_id:** [Unique session identifier]
- **l3_session_key:** [Session key for traceability]
- **audit_report_path:** [Path to full audit report]
- **final_verdict:** [APPROVED] or [NEEDS_FIX]

### Findings:
1. [Issue 1 with severity and location]
2. [Issue 2 with severity and location]
...

### Compliance Checks:
- [ ] PIT compliance verified
- [ ] Vectorization standards met
- [ ] No look-ahead bias
- [ ] Audit trail complete
- [ ] SOP adherence confirmed

### Verdict Rationale:
[Explanation of decision]

### Required Actions (if [NEEDS_FIX]):
1. [Action 1]
2. [Action 2]
...

**Signature:** Codex L3 Auditor
```

---

## Workflow Enforcement Rules

### Rule 1: No L3 Code Commits

**Enforcement:**
```
IF platform == Codex (L3):
    IF action == "write code" OR action == "commit changes":
        REJECT with message: "L3 auditors cannot write production code. Report findings to L2 (OpenCode) for implementation."
```

### Rule 2: Mandatory L3 Review

**Enforcement:**
```
IF code_destination == production:
    IF NOT audited_by_L3:
        BLOCK with message: "All production code requires L3 (Codex) audit verdict before merge."
```

### Rule 3: Verdict Required

**Enforcement:**
```
IF L3_audit_complete:
    IF NOT verdict_issued:
        BLOCK with message: "L3 audit incomplete. Structured verdict required."
```

### Rule 4: L2 Cannot Self-Approve

**Enforcement:**
```
IF approver == implementer:
    BLOCK with message: "L2 developers cannot approve their own code. L3 audit required."
```

---

## Multi-Platform Coordination Protocol

### Standard Flow

```
┌─────────────────────────────────────────────────────┐
│ L1: Ly (Orchestration)                              │
│ - Define task                                        │
│ - Route to L2                                        │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│ L2: OpenCode (Development)                          │
│ - Implement code                                     │
│ - Run local validation                               │
│ - Submit to L3                                       │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│ L3: Codex (Audit)                                   │
│ - Review submission                                  │
│ - Issue verdict                                      │
│ - Report findings                                    │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
            ┌─────────────────┐
            │ [APPROVED]?     │
            └────┬────────┬───┘
                 │ Yes    │ No
                 │        │
                 ▼        ▼
            ┌────────┐  ┌──────────────┐
            │ Deploy │  │ Return to L2  │
            └────────┘  │ for fixes     │
                        └───────┬───────┘
                                │
                                ▼
                        (Loop back to L2)
```

---

## Emergency Override Protocol

**When:** Critical production issues requiring immediate fix

**Process:**
1. Ly (L1) declares emergency
2. OpenCode (L2) implements fix
3. Fix deployed with "EMERGENCY OVERRIDE" tag
4. Codex (L3) performs post-deployment audit within 24 hours
5. If L3 finds issues, immediate remediation required

**Documentation:**
```markdown
## Emergency Override Record
- **Timestamp:** [ISO 8601]
- **Issue:** [Description]
- **Fix:** [What was changed]
- **Approver:** Ly (L1)
- **Post-Audit Status:** [Pending/Complete]
```

---

## Audit Trail Requirements

### Every Code Change MUST Record:

| Field | Description |
|-------|-------------|
| **Author** | Who wrote the code (L2 platform/user) |
| **Reviewer** | Who audited (L3 platform/user) |
| **Timestamp** | ISO 8601 format |
| **Verdict** | [APPROVED] or [NEEDS_FIX] |
| **l3_session_id** | L3 audit session identifier |
| **l3_session_key** | Session key for traceability |
| **audit_report_path** | Path to full audit report |
| **SOP Reference** | Which SOP governs this change |
| **Ticket/Issue** | Traceability link |

### Storage Location:
- Git commit messages (structured format)
- `.omega/audit-trail/` directory with JSON logs
- CHANGELOG.md entries for production releases

---

## Violations and Enforcement

### Common Violations:

| Violation | Severity | Action |
|-----------|----------|--------|
| L3 writes production code | **CRITICAL** | Reject commit, escalate to Ly |
| L2 self-approves | **HIGH** | Block merge, require L3 audit |
| Missing verdict | **HIGH** | Block deployment until verdict issued |
| Incomplete audit trail | **MEDIUM** | Require documentation before merge |

### Escalation Path:
```
Violation Detected → Alert Ly (L1) → Ly investigates → Ly decides action
```

---

## Integration with Other Skills

### This skill coordinates with:

- **karpathy-coder**: L2 developers use this for coding standards
- **karpathy-auditor**: L3 auditors use this for review criteria
- **sops**: References SOPs for specific workflows (AC, backtest, PIT)
- **audit-cycle**: Implements the SOD workflow for /ac command

---

## Summary: Who Does What

| Task | L1 (Ly) | L2 (OpenCode) | L3 (Codex) |
|------|---------|---------------|------------|
| **Write Code** | ❌ | ✅ | ❌ |
| **Review Code** | ✅ (final approval) | ✅ (self-review) | ✅ (audit) |
| **Issue Verdict** | ✅ (override) | ❌ | ✅ |
| **Deploy** | ✅ (authorize) | ✅ (execute) | ❌ |
| **Orchestrate** | ✅ | ❌ | ❌ |

> **Remember:** Independence is the foundation of trust. L3 audits, L2 codes, L1 orchestrates. Never cross the streams.

---

## Quick Reference Card

**I am Ly (L1):**
- I coordinate and decide
- I tell OpenCode what to build
- I tell Codex what to audit
- I approve final verdicts

**I am OpenCode (L2):**
- I write code
- I submit to Codex for audit
- I fix issues Codex finds
- I never approve my own work

**I am Codex (L3):**
- I review and challenge
- I issue verdicts
- I NEVER write production code
- I maintain auditor independence

---

## Version History

- v1.2 (2026-06-12): Fixed .agents junction (was symlink to forbidden scratch, replaced with real repo-local directory). Added audit-cycle skill. Hardened enforcer: sentence-level forbidden path detection, tightened L2/audit report validation, required gate fields, hard-blocking post-cutoff enforcement.
- v1.1 (2026-06-12): Added Repo-Local Skill Source Contract (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)
- v1.0 (2026-06-10): Initial OMEGA_QUANT SOD framework

---

## Repo-Local Skill Source Contract (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)

**Effective**: 2026-06-12. Enforced by `scripts/sod_gate_enforcer.py`.

### Authoritative Source Paths

| Constant | Value |
|----------|-------|
| `REPO_AGENT_ROOT` | `{REPO_ROOT}/.agents/agent` |
| `REPO_SKILL_ROOT` | `{REPO_ROOT}/.agents/skills` |

### Mandatory Loading Order

1. Read `REPO_AGENT_ROOT/<role_name>.md` - parse frontmatter for `role_id`, `tier`, `platform`, `skills`, `sod_boundary`
2. For each declared skill: read `REPO_SKILL_ROOT/<skill_name>/SKILL.md`
3. Report exact files read in L2/L3 output
4. If required source missing: stop and report `NEEDS_FIX`

### Forbidden Paths (Non-Authoritative)

The following MUST NOT be used as authoritative skill/role sources:
- `.gemini\antigravity-ide\scratch\ag-kit` (Antigravity scratch)
- `.openclaw\skills` (OpenClaw)
- `C:\Users\GHC\.agents` (Global Codex agents)
- `.codex\memories` (Codex memory)

Mentions of forbidden paths are allowed ONLY when:
- Explicitly marked as "non-authoritative"
- Part of forbidden-path scan evidence in audit reports

### Gate Enforcement

`scripts/sod_gate_enforcer.py` validates:
- Post-cutoff gates include `repo_local_skill_sources` evidence
- L2 reports list exact repo-local files read
- No authoritative reliance on forbidden paths
- Forbidden path scan result is documented
