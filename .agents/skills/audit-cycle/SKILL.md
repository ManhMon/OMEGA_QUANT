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

## Automation Scripts (TOKEN SAVER)

All scripts live in `scripts/`. Use them instead of manual prompt construction:

| Script | Purpose | Saves |
|--------|---------|-------|
| `dispatch_l2.py` | Generate L2 OpenCode dispatch command | ~5K L1 context |
| `validate_l2_report.py` | Pre-L3 validation of L2 report format | ~400K/retry avoided |
| `dispatch_l3.py` | Generate L3 Codex dispatch command + model tiering | ~5K L1 + 50% cost (low) |
| `update_gate.py` | Scoped phase_gates.json update (no corruption) | ~400K/retry avoided |
| `sod_pipeline.py` | Full L2→validate→L3→enforcer in 1 command | ~80K L1 context |
| `sod_gate_enforcer.py` | Final compliance check | Required |

### One-Command Pipeline (Recommended)

```powershell
python scripts/sod_pipeline.py <l2_role> <l3_role> <gate> <slug> "<task>" "<scope>" [--risk low|high] [--dry-run]
```

### Individual Script Usage

```powershell
# Step 1: Dispatch L2
python scripts/dispatch_l2.py <role> <gate> <slug> "<task>" "<scope>"

# Step 2: Validate L2 report (MANDATORY before L3)
python scripts/validate_l2_report.py <l2_session_id> <role_id> <role_name>

# Step 3: Dispatch L3
python scripts/dispatch_l3.py <l3_role> <gate> <l2_session_id> <l2_role> "<scope>" [--risk low|high]

# Step 4: Enforcer
python scripts/sod_gate_enforcer.py
```

---

## Audit Cycle Phases

### Phase 1: L2 Submission

**Dispatch:** `python scripts/dispatch_l2.py <role> <gate> <slug> "<task>" "<scope>"`

**L2 deliverables:**
- Code changes in scope
- Tests passing
- L2 report using template `.agents/skills/omega-sod/l2_report_template.md`
- Report MUST have `## Repo-Local Files Read` heading
- Report filename: `l2_role{id}_{slug}_{YYYYMMDD}.md` (no `_retry` suffix)

### Phase 1.5: Pre-L3 Validation (MANDATORY)

**Run:** `python scripts/validate_l2_report.py <session_id> <role_id> <role_name>`

- Exit 0 → proceed to Phase 2
- Exit 1 → fix L2 report, re-dispatch L2 (do NOT dispatch L3)

### Phase 2: L3 Independent Audit

**Dispatch:** `python scripts/dispatch_l3.py <l3_role> <gate> <l2_session_id> <l2_role> "<scope>" [--risk low|high]`

**Model tiering:**
- `--risk low`: test fixtures, docs, config → `cx/gpt-5.6-sol` (~50% cheaper)
- `--risk high` (default): production logic, security → `cx/gpt-5.6-sol(max)`

**L3 gate update:** L3 MUST use `python scripts/update_gate.py <gate> <field>=<value> ...` instead of editing phase_gates.json manually.

### Phase 3: Gate Recording

**L1 responsibilities:**
- Run `python scripts/sod_gate_enforcer.py`
- Exit 0 = safe to push; Exit 1 = blocked
- For low-risk gates with [APPROVED]: MAY skip final deep audit (record skip reason)

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

## L2 Optimization Tips

1. **Use l2_report_template.md** — copy exact format, don't invent structure
2. **Keep scope minimal** — smaller diff = faster audit, fewer issues
3. **Run tests before report** — include actual output in Verification section
4. **Forbidden path scan** — 4 lines, each ending exactly: `non-authoritative scan evidence only; no reliance.`

## L3 Optimization Tips

1. **Use update_gate.py** — never edit phase_gates.json manually (prevents corruption)
2. **Use --risk low** for fixture/doc/config gates — halves model cost
3. **Scoped checks only** — don't re-audit files outside scope
4. **Include line references** — cite exact line numbers for findings

---

## Integration

This skill coordinates with:
- **omega-sod**: Defines the SOD framework and platform hierarchy
- **code-review-checklist**: L3 uses for review standards
- **testing-patterns**: L2 uses for test quality

Automation scripts:
- `scripts/dispatch_l2.py`, `scripts/dispatch_l3.py`: Command builders
- `scripts/validate_l2_report.py`: Pre-L3 format validation
- `scripts/update_gate.py`: Safe scoped gate updates
- `scripts/sod_pipeline.py`: Full pipeline orchestration

---

> **Remember:** Every audit cycle must produce a verifiable gate with complete metadata and enforcer exit 0.
