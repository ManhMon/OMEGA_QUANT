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
| **L1** | Ly / Antigravity | Orchestrator | Plan and delegate, record evidence, enforce gates; no implementation or audit |
| **L2** | OpenCode (this platform) | Implementer | Implement, refactor, run scoped tests, write L2 report |
| **L3** | Codex | Planner / independent auditor | Create delegated plans, audit independently, issue verdicts and gate metadata; no production-code or test edits |

> **Iron Law:** L3 auditors SHALL NOT write production code or tests. They review, challenge, and issue the independent verdict only. A delegated L3 non-audit role may create plans.

---

## Segregation Boundaries

### L1: Ly / Antigravity (Orchestration Layer)

**Capabilities:**
- Coordinate multi-platform workflows
- Delegate planning to an appropriate L3 non-audit role
- Direct L2 to implement scoped changes
- Direct L3 to perform independent audits
- Record evidence and enforce gate requirements

**Restrictions:**
- Does NOT write production code directly
- Does NOT perform audits directly (delegates to L3)
- Does NOT override an L3 verdict or manually approve a gate

**Example Workflow:**
```
Ly → delegates implementation to OpenCode (L2)
Ly → dispatches an independent audit to Codex (L3) after L2 saves state and exits
Ly → records the L3 verdict and enforces the gate; [NEEDS_FIX] returns to L2
```

---

### L2: OpenCode (Developer Layer)

**Capabilities:**
- Write production code
- Implement features and bug fixes
- Run tests and validation scripts
- Write the L2 implementation report
- Respond to audit findings
- Self-review before submitting to L3

**Restrictions:**
- CANNOT approve own code for production
- MUST submit all changes to L3 audit
- CANNOT override L3 verdicts
- MUST finish and save state before L3 starts
- MUST keep tests scoped to changed behavior and related test suites

**Example Workflow:**
```
OpenCode → Implement feature
OpenCode → Run local tests
OpenCode → Submit to Codex for audit
OpenCode → [Receives verdict] → Fix issues if needed
OpenCode → Resubmit until [APPROVED] verdict
```

---

### L3: Codex (Auditor Layer)

**Capabilities:**
- Review code for correctness, compliance, and quality
- Challenge design decisions
- Issue the authoritative structured verdict: `[APPROVED]` or `[NEEDS_FIX]`
- Create delegated plans and maintain gate metadata within the L3 write boundary
- Request clarifications
- Verify compliance with SOPs

**Restrictions:**
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT write production code
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT edit tests or files outside `.ly_state/`
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT commit changes to the codebase
- ❌ **ABSOLUTE PROHIBITION:** L3 SHALL NOT implement fixes (must report findings to L2)

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

1. **L3 write boundary:** L3 may write audit reports, plans, and gate metadata only within `.ly_state/session/`; production source and tests remain read-only.
2. **Audit gate:** L2 work is not approved until an independent L3 audit issues `[APPROVED]` and repository gate enforcement succeeds.
3. **Verdict required:** Missing or partial verdict means the gate remains pending.
4. **No self-approval or override:** L2 cannot approve its own implementation; L1 cannot replace or override the L3 verdict.

---

## Multi-Platform Coordination Protocol

### Standard Flow

```
┌─────────────────────────────────────────────────────┐
│ L1: Ly / Antigravity (Orchestration)                │
│ - Delegate planning to L3 non-audit role             │
│ - Route implementation to L2                         │
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

## Urgent Change Handling

Urgency does not bypass segregation or gate requirements. L1 records and routes the urgent request; L2 implements and tests; L3 independently audits. No emergency override, post-deployment approval, or manual verdict substitution is permitted.

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
Violation Detected → Notify Ly (L1) → record evidence → enforce the applicable gate
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

| Task | L1 (Ly / Antigravity) | L2 (OpenCode) | L3 (Codex) |
|------|-----------------------|---------------|------------|
| **Plan** | Delegate to L3 non-audit role | Implement from authorized scope | Create delegated plans |
| **Write production code/tests** | ❌ | ✅ | ❌ |
| **Review code** | ❌ | Self-review only | ✅ (independent audit) |
| **Issue authoritative verdict** | ❌ | ❌ | ✅ |
| **Record/enforce gate** | ✅ (no override) | Write L2 report | Update gate metadata within L3 boundary |
| **Orchestrate** | ✅ | ❌ | ❌ |

> **Remember:** L3 audits, L2 implements, L1 orchestrates and enforces gates. Never cross the streams.

---

## Quick Reference Card

**I am Ly (L1):**
- I orchestrate, delegate, record evidence, and enforce gates
- I delegate planning to L3 and implementation to L2
- I never implement, audit, approve, or override a verdict

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

- v1.3 (2026-10-02): Removed L1 override/approval claims; aligned role boundaries, urgent changes, and verdict handling with repository AGENTS.md.
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
2. For each declared skill: read `REPO_SKILL_ROOT/<skill_name>/skill.md`
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

---

## Pre-L3 Validation Gate (TOKEN SAVER — MANDATORY)

**Effective**: 2026-08-14. Prevents expensive L3 retry cycles from L2 report format errors.

### Why This Exists

Each L3 Codex audit costs ~400K tokens. Recurring L2 report format failures (missing heading, wrong wording, wrong filename) caused 5+ retry cycles in a single gate, wasting millions of tokens.

### L1 MUST Run Before Every L3 Dispatch

```powershell
python scripts/validate_l2_report.py <l2_session_id> <role_id> <role_name>
```

- **Exit 0** → safe to dispatch L3
- **Exit 1** → fix L2 report first (retry L2 only, do NOT dispatch L3)

### What It Checks

| Check | Requirement |
|-------|-------------|
| Filename | Must end `_YYYYMMDD.md` — no `_retry` suffix |
| `## Repo-Local Files Read` | Must exist with ≥1 file from REPO_AGENT_ROOT |
| Forbidden path scan wording | Each line must end: `non-authoritative scan evidence only; no reliance.` |
| Authoritative forbidden path usage | Must be zero |

### L2 Report Template

L2 agents MUST use the template at `.agents/skills/omega-sod/l2_report_template.md`.
Copy it exactly, fill in `[PLACEHOLDER]` values only. Do not invent structure.

---

## Automation Scripts (TOKEN SAVER)

| Script | Purpose |
|--------|---------|
| `scripts/dispatch_l2.py` | Generate L2 dispatch command (auto-validates role, embeds lessons, embeds report format) |
| `scripts/dispatch_l3.py` | Generate L3 dispatch command (model tiering: `--risk low` for fixtures/docs) |
| `scripts/validate_l2_report.py` | Pre-L3 format validation (blocks L3 if format wrong) |
| `scripts/update_gate.py` | Scoped phase_gates.json update (prevents corruption) |
| `scripts/sod_pipeline.py` | Full L2→validate→L3→enforcer in 1 command |

### Full Pipeline (Recommended)

```powershell
python scripts/sod_pipeline.py <l2_role> <l3_role> <gate> <slug> "<task>" "<scope>" [--risk low|high]
```

---

## L2 Optimization Tips

1. **Use l2_report_template.md** — copy format exactly
2. **Keep scope minimal** — smaller diff = faster audit
3. **Forbidden path scan** — 4 lines, exact suffix: `non-authoritative scan evidence only; no reliance.`
4. **No _retry suffix** — overwrite report file, don't create new ones

## L3 Optimization Tips

1. **Use update_gate.py** — never edit phase_gates.json manually
2. **Use --risk low** for fixture/doc/config gates — halves model cost
3. **Scoped checks only** — don't re-audit files outside scope
4. **Cite line numbers** in findings for precision
