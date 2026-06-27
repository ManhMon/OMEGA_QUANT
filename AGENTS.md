# AGENTS.md - OMEGA_QUANT Protocol
**Version**: 2.9 | **Updated**: 2026-06-12

## Tiers

| Tier | Platform | Role IDs | Boundary |
|------|----------|----------|----------|
| L1 | Ly / Antigravity | 1-5 | Orchestrate, plan, delegate, enforce gates |
| L2 | OpenCode | 6-16 | Implement, refactor, run tests, write L2 report |
| L3 | Codex | 17-25 | Independent audit, verdict, gate metadata |

## AG Kit Loading

- Role specs live in `.agents/agent/*.md`.
- Each role frontmatter defines `role_id`, `tier`, `platform`, `skills`, and `sod_boundary`.
- `sod_boundary` is binding; L1 must enforce it before delegation.
- Before delegation, L1 selects exactly one role and loads only declared skills.
- L2 receives: role spec + task + scope + requirements.
- L3 receives: audit role spec + scope + checks + verdict contract.
- **Role boundary evidence**: L2/L3 prompts MUST include role_id and role_name. L1 MUST verify writer != auditor before delegation.

## Repo-Local Skill Source Contract (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)

**Effective**: 2026-06-12. All L2/L3 dispatches MUST use repo-local role/skill sources only.

### Authoritative Paths

| Constant | Value | Purpose |
|----------|-------|---------|
| `REPO_AGENT_ROOT` | `{REPO_ROOT}/.agents/agent` | Role spec files (`*.md`) |
| `REPO_SKILL_ROOT` | `{REPO_ROOT}/.agents/skills` | Skill definition files (`*/SKILL.md`) |

### Loading Protocol (MANDATORY for L2 and L3)

1. **First**: Read role spec from `REPO_AGENT_ROOT/<role_name>.md` and parse frontmatter.
2. **Parse skills**: Extract `skills` list from frontmatter.
3. **Read skills**: For each declared skill, read `REPO_SKILL_ROOT/<skill_name>/SKILL.md` only.
4. **Report**: L2/L3 reports MUST list exact repo-local role/skill files read.
5. **Stop condition**: If any required repo-local source is missing/unreadable, stop and report `NEEDS_FIX` unless the role spec intentionally references a missing skill.

### Forbidden Paths (Non-Authoritative)

The following paths are **non-authoritative** for skill/role loading. Mentions are allowed ONLY if explicitly marked as non-authoritative or as forbidden-path scan evidence.

| Forbidden Path | Description |
|----------------|-------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | Antigravity IDE scratch |
| `.openclaw\skills` | OpenClaw skills |
| `C:\Users\GHC\.agents` | Global Codex agents directory |
| `.codex\memories` | Codex memory files |

**Enforcement**: `scripts/sod_gate_enforcer.py` validates that post-cutoff gates and audit reports include repo-local skill source evidence and do not rely on forbidden paths as authoritative sources.

## Routing Enforcement

L1 must validate role tier, platform, and role_id ranges before dispatch:

### Pre-Dispatch Role Resolution

Before ANY L2 or L3 dispatch, L1 MUST:
1. Read the role spec from `.agents/agent/<role_name>.md`
2. Parse frontmatter and extract: `role_id`, `tier`, `platform`, `role_name`, `sod_boundary`
3. Validate all fields are present and correctly typed
4. Verify role_name matches the filename stem exactly (case-sensitive)
5. Store resolved role metadata in delegation context

**Violation of pre-dispatch resolution blocks dispatch entirely.**

### L2 (OpenCode) Routing Constraints

- role_id MUST be in range 6-16
- tier MUST be 2
- platform MUST be "OpenCode"
- role_name MUST be extracted from `.agents/agent/*.md` frontmatter (exact match)
- Violation blocks dispatch

### L3 (Codex) Routing Constraints

- role_id MUST be in range 17-25
- tier MUST be 3
- platform MUST be "Codex"
- sod_boundary MUST be defined in frontmatter
- role_name MUST be extracted from `.agents/agent/*.md` frontmatter (exact match)
- Violation blocks dispatch

### Writer != Auditor Constraint

- l2_role_id MUST NOT equal l3_role_id
- Self-approval is forbidden
- Violation blocks gate approval
- L1 MUST verify this constraint before L3 dispatch and before gate approval

## SOD Rules

1. **1 Agent = 1 Role = 1 Task**.
2. **Writer != Auditor**. Self-approval forbidden.
3. L2 must exit/save state before L3 starts.
4. L1 never implements or audits; L1 only delegates, records evidence, enforces gates.
5. All state/evidence must be file-backed in `.ly_state/session/`.
6. Do not run OpenCode and Codex simultaneously. Platform cap: 4GB.
7. **L3 write boundary**: L3 may ONLY write to `.ly_state/session/audit_reports/` and update `.ly_state/session/phase_gates.json`. L3 MUST NOT edit production source code, tests, or any files outside `.ly_state/`.
8. **Scratch path prohibition**: L2 and L3 MUST NOT read or write Antigravity scratch paths. All operations use `REPO_ROOT` with repo-relative paths only.
9. **No manual override**: Manual approval overrides are forbidden. All gates require valid L3 audit with [APPROVED] verdict and `python scripts/sod_gate_enforcer.py` exit 0.
10. **L2 session ID format**: L2 session IDs MUST follow format `l2_role{role_id}_{task_slug}_{YYYYMMDD}` (e.g., `l2_role11_agents_md_strict_sod_hardening_20260611`).

## Required Flow

```text
L2 OpenCode: implement + tests + L2 report
  -> L3 Codex: independent audit -> [APPROVED] / [NEEDS_FIX]
  -> L1 Ly: update phase_gates.json + run sod_gate_enforcer.py
  -> exit 0: safe to push
```

A task is not complete until `python scripts/sod_gate_enforcer.py` exits `0`.

### Verdict Handling

- **[APPROVED]**: L1 records gate metadata, runs enforcer, proceeds if exit 0
- **[NEEDS_FIX]**: L1 creates new L2 session with fix scope, L3 re-audits after fix, cycle repeats until [APPROVED]
- **No verdict or partial verdict**: Gate remains `PENDING_L3_AUDIT`, no progression
- **Manual override**: Forbidden. All approvals require valid L3 audit + enforcer exit 0

## Call L2 OpenCode Implementation Work

**Pre-dispatch requirements:**
1. Read `.agents/agent/<role_name>.md` and extract frontmatter: `role_id`, `tier`, `platform`, `name`
2. Validate: role_id 6-16, tier=2, platform=OpenCode
3. Verify filename stem matches frontmatter `name` field exactly
4. Use extracted `role_id` and `name` in prompt (never hand-type role names)

```powershell
echo "" | opencode run --pure --dangerously-skip-permissions --dir "C:\Users\GHC\repos\OMEGA_QUANT" -m "tr/MiniMax-M3" "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: {role_id} {role_name} - OpenCode L2 Implementation Work. TASK: [TASK]. GATE: [GATE_NAME]. SKILL SOURCE CONTRACT: REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent; REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills. First run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; first read REPO_AGENT_ROOT\{role_name}.md and parse frontmatter; then read required SKILL.md only from REPO_SKILL_ROOT for declared skills. Any skill loaded from Antigravity scratch/OpenClaw/C:\Users\GHC\\.agents/Codex memory is non-authoritative. Report exact repo-local role/skill files read and forbidden path scan result. SCOPE: [FILES]. REQUIREMENTS: use repo-relative paths from REPO_ROOT only; implement/refactor/test only; write L2 report to .ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md. Do not audit or approve. Stop/NEEDS_FIX if required repo-local source missing."
```

**Platform lock protocol:** OpenCode L2 sessions MUST NOT call Codex or any L3 platform directly. L1 controls all cross-platform delegation.

**Strict report naming:** L2 reports MUST follow format: `.ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md`

**Windows requirements:** always use `echo "" |`, `--pure`, `--dangerously-skip-permissions`, and `--dir "C:\Users\GHC\repos\OMEGA_QUANT"`. Prompts must define `REPO_ROOT`; workers must not resolve `.agents` through Antigravity scratch paths.

**Repo-local skill source contract:** L2 prompts MUST include `REPO_AGENT_ROOT`, `REPO_SKILL_ROOT`, instruction to read repo-local role spec first, parse skills, read only repo-local SKILL.md files, and report exact files read. Global/scratch/OpenClaw/Codex memory sources are non-authoritative.

## Call L3 Codex Independent Review

**Pre-dispatch requirements:**
1. Read `.agents/agent/<role_name>.md` and extract frontmatter: `role_id`, `tier`, `platform`, `name`, `sod_boundary`
2. Validate: role_id 17-25, tier=3, platform=Codex, sod_boundary defined
3. Verify filename stem matches frontmatter `name` field exactly
4. Verify l2_role_id != l3_role_id (writer != auditor)
5. Use extracted `role_id` and `name` in prompt (never hand-type role names)

```powershell
echo "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: {role_id} {role_name} - Codex L3 Independent Review. GATE: {gate_name}. L2_SESSION: {l2_session_id}. L2_ROLE: {l2_role_id} {l2_role_name}. SKILL SOURCE CONTRACT: REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent; REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills. First read REPO_AGENT_ROOT\{role_name}.md and parse frontmatter; read required SKILL.md only from REPO_SKILL_ROOT. Any skill from Antigravity scratch/OpenClaw/C:\Users\GHC\.agents/Codex memory is non-authoritative. Report exact repo-local files read and forbidden path scan result. SCOPE: [FILES]. CHECKS: [CHECKLIST]. REQUIREMENTS: first run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; use repo-relative paths from REPO_ROOT only; never read/write Antigravity scratch paths. AUDIT EVIDENCE CHECKLIST: 1. Verify l2_role_id={l2_role_id} != l3_role_id={role_id}. 2. Verify code changes match approved scope. 3. Run all tests. 4. Check PIT safety, no look-ahead bias. 5. Validate SOD boundaries. 6. Verify L2 report lists repo-local skill source evidence. VERDICT: Write [APPROVED] or [NEEDS_FIX] to .ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md. GATE UPDATE: Update ONLY the '{gate_name}' entry in phase_gates.json with: l2_session_id='{l2_session_id}', l2_role_id={l2_role_id}, l2_role_name='{l2_role_name}', l3_session_id='{l3_session_id}', l3_role_id={role_id}, l3_role_name='{role_name}', audit_report_path='.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md', final_verdict='[verdict]', sod_boundary_checked=true, writer_auditor_separated=true. FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update." | codex exec --full-auto
```

**Scoped gate updates:** L3 MUST update only the specific gate being audited. Do not modify other gates or create new gates.

**Audit evidence requirements:** L3 audit reports MUST document:
- Writer != Auditor verification (l2_role_id != l3_role_id)
- Scope compliance check
- Test execution results
- PIT safety verification
- SOD boundary compliance
- Repo-local skill source evidence (L2 report lists exact files read from REPO_AGENT_ROOT/REPO_SKILL_ROOT)
- Forbidden path scan result (no authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`)

**Platform isolation:** Codex L3 sessions MUST NOT call OpenCode or modify production source code directly. L3 writes only to `.ly_state/session/audit_reports/` and updates phase_gates.json.

**Codex requirements:** always pipe prompt via `echo`; never use interactive stdin. Prompt must include `REPO_ROOT` and a first-step `Set-Location` guard.

## Gate Contract

Valid gate requires all fields:

```json
{
  "l2_session_id": "...",
  "l2_completed": true,
  "l2_role_id": 0,
  "l2_role_name": "...",
  "l3_session_id": "...",
  "l3_session_key": "...",
  "l3_role_id": 0,
  "l3_role_name": "...",
  "audit_report_path": "...",
  "final_verdict": "[APPROVED]",
  "sod_boundary_checked": true,
  "writer_auditor_separated": true
}
```

**Field requirements (gates after 2026-06-11)**:
- `l2_role_id`: Integer role ID (6-16 for OpenCode L2), must exist in `.agents/agent/*.md`
- `l2_role_name`: Role name from spec (e.g., "backend-engineer", "compliance-officer")
- `l3_role_id`: Integer role ID (17-25 for Codex L3), validated: tier=3, platform=Codex, has sod_boundary
- `l3_role_name`: Role name from spec (e.g., "code-reviewer", "compliance-officer")
- `l2_role_id != l3_role_id`: Writer != Auditor enforcement
- `audit_report_path`: Must exist as file and contain the verdict string
- `sod_boundary_checked`: Must be `true`
- `writer_auditor_separated`: Must be `true`

**Field requirements (gates after 2026-06-12, STRICT_REPO_LOCAL_SKILL_LOADING_20260612)**:
- `repo_local_skill_sources`: List of exact repo-local files read (from REPO_AGENT_ROOT and REPO_SKILL_ROOT)
- `forbidden_path_scan`: Result of forbidden path scan (must show no authoritative reliance)
- L2 report MUST list exact repo-local role/skill files read
- L3 audit MUST verify L2 repo-local skill source evidence

Missing/invalid fields -> `PENDING_L3_AUDIT`.

**Backward compatibility**: Gates created before 2026-06-11 with `[APPROVED]` verdict are grandfathered. New gates (after 2026-06-11) require all fields including role boundary evidence.

## State Directory

- `.ly_state/session/phase_gates.json`
- `.ly_state/session/audit_reports/`
- `.ly_state/session/l2_*.md`
