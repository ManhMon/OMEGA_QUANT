# SOP: Call Codex L3 Audit (Strict Dynamic Template)
**Version**: 2.0  
**Date**: 2026-06-11  
**Author**: L1 Orchestration (Role 11 L2 Implementation)  

---

## ⚠️ CRITICAL REQUIREMENTS

### Pre-Dispatch Role Resolution (MANDATORY):
1. **Read** `.agents/agent/<role_name>.md` and extract frontmatter: `role_id`, `tier`, `platform`, `name`, `sod_boundary`
2. **Validate**: role_id 17-25, tier=3, platform=Codex, sod_boundary defined
3. **Verify** filename stem matches frontmatter `name` field exactly
4. **Verify** l2_role_id != l3_role_id (writer != auditor)
5. **Use** extracted `role_id` and `name` in prompt (NEVER hand-type role names)

### Codex Invocation:
- **MUST use** `--full-auto` flag and pipe prompt via `echo`
- **MUST include** `REPO_ROOT` and first-step `Set-Location` guard
- **NEVER** use interactive stdin (causes hang)

---

## Strict Dynamic L3 Template

### Command Structure (PowerShell):
```powershell
echo "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: {role_id} {role_name} - Codex L3 Independent Review. GATE: {gate_name}. L2_SESSION: {l2_session_id}. L2_ROLE: {l2_role_id} {l2_role_name}. SCOPE: [FILES]. CHECKS: [CHECKLIST]. REQUIREMENTS: first run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; use repo-relative paths from REPO_ROOT only; never read/write Antigravity scratch paths. AUDIT EVIDENCE CHECKLIST: 1. Verify l2_role_id={l2_role_id} != l3_role_id={role_id}. 2. Verify code changes match approved scope. 3. Run all tests. 4. Check PIT safety, no look-ahead bias. 5. Validate SOD boundaries. VERDICT: Write [APPROVED] or [NEEDS_FIX] to .ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md. GATE UPDATE: Update ONLY the '{gate_name}' entry in phase_gates.json with: l2_session_id='{l2_session_id}', l2_role_id={l2_role_id}, l2_role_name='{l2_role_name}', l3_session_id='{l3_session_id}', l3_role_id={role_id}, l3_role_name='{role_name}', audit_report_path='.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md', final_verdict='[verdict]', sod_boundary_checked=true, writer_auditor_separated=true. FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update." | codex exec --full-auto
```

### Field Definitions:
- `{role_id}`: L3 role ID (17-25), extracted from `.agents/agent/*.md` frontmatter
- `{role_name}`: Exact role name from frontmatter `name` field (e.g., "code-reviewer")
- `{gate_name}`: Gate being audited (e.g., "PHASE_2_SOD_HARDENING")
- `{l2_session_id}`: L2 session ID in format `l2_role{role_id}_{task_slug}_{YYYYMMDD}`
- `{l2_role_id}`: L2 role ID (6-16), extracted from L2 session metadata
- `{l2_role_name}`: L2 role name from frontmatter (e.g., "devops-engineer")
- `{l3_session_id}`: Unique L3 session ID (e.g., UUID or timestamp-based)
- `{gate_slug}`: Slugified gate name for file naming
- `{YYYYMMDD}`: Date in format YYYYMMDD (e.g., 20260611)

### Example (SOD Protocol Hardening):
```powershell
echo "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: 21 code-reviewer - Codex L3 Independent Review. GATE: PHASE_2_SOD_HARDENING. L2_SESSION: l2_role11_sod_protocol_final_hardening_20260611. L2_ROLE: 11 devops-engineer. SCOPE: AGENTS.md, .ly_state/session/sop_codex_l3_audit_call.md, scripts/sod_gate_enforcer.py. CHECKS: A. L2 template includes --dangerously-skip-permissions. B. Role placeholders use dynamic {role_id} {role_name}. C. L3 gate updates scoped to single gate. D. Enforcer validates l2_session_id, audit_report_path traversal. E. Duplicate detection includes session IDs. REQUIREMENTS: first run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; use repo-relative paths from REPO_ROOT only; never read/write Antigravity scratch paths. AUDIT EVIDENCE CHECKLIST: 1. Verify l2_role_id=11 != l3_role_id=21. 2. Verify code changes match approved scope. 3. Run python -m py_compile scripts/sod_gate_enforcer.py. 4. Run python scripts/sod_gate_enforcer.py (must exit 0). 5. Validate SOD boundaries. VERDICT: Write [APPROVED] or [NEEDS_FIX] to .ly_state/session/audit_reports/role21_sod_hardening_20260611.md. GATE UPDATE: Update ONLY the 'PHASE_2_SOD_HARDENING' entry in phase_gates.json with: l2_session_id='l2_role11_sod_protocol_final_hardening_20260611', l2_role_id=11, l2_role_name='devops-engineer', l3_session_id='[GENERATE_UUID]', l3_role_id=21, l3_role_name='code-reviewer', audit_report_path='.ly_state/session/audit_reports/role21_sod_hardening_20260611.md', final_verdict='[verdict]', sod_boundary_checked=true, writer_auditor_separated=true. FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update." | codex exec --full-auto
```

---

## Pre-Audit Checklist

- [ ] **L2 implementation complete** (all code changes committed)
- [ ] **L2 report written** (`.ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md`)
- [ ] **Tests pass** (pytest or relevant test suite)
- [ ] **phase_gates.json entry created** (status `PENDING_L3_AUDIT`)
- [ ] **L3 role resolved** (read `.agents/agent/{role_name}.md`, extract role_id/name)
- [ ] **Writer != Auditor verified** (l2_role_id != l3_role_id)
- [ ] **Use `--full-auto` flag** (prevents stdin hang)
- [ ] **Pipe prompt via `echo`** (NEVER use direct stdin)
- [ ] **All placeholders filled** ({role_id}, {role_name}, {gate_name}, etc.)

---

## Post-Audit Workflow

### If [APPROVED]:
1. **Verify gate metadata** in phase_gates.json contains:
   - `l2_session_id`, `l2_role_id`, `l2_role_name`
   - `l3_session_id`, `l3_role_id`, `l3_role_name`
   - `audit_report_path` (relative path under `.ly_state/session/audit_reports/`)
   - `final_verdict: "[APPROVED]"`
   - `sod_boundary_checked: true`
   - `writer_auditor_separated: true`

2. **Run enforcer** (L1 orchestration):
   ```powershell
   python scripts/sod_gate_enforcer.py
   ```

3. **If exit 0**: Proceed to next phase/task
4. **If exit 1**: Fix validation errors, update gate metadata, re-run enforcer

### If [NEEDS_FIX]:
1. **Read audit report** (`.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md`)
2. **Create new L2 session** with fix scope:
   - New session ID: `l2_role{role_id}_{task_slug}_fix_{YYYYMMDD}`
   - Scope: Only files/issues identified in audit report
3. **L2 implements fixes** and writes new L2 report
4. **Re-submit to L3** with updated L2 session ID
5. **Repeat until [APPROVED]**

---

## Audit Evidence Requirements (L3 MUST Document)

1. **Writer != Auditor verification**: Confirm l2_role_id={l2_role_id} != l3_role_id={role_id}
2. **Scope compliance**: All changes match approved L2 scope
3. **Test execution**: Run full test suite, document results
4. **PIT safety**: No look-ahead bias, T-1 lag maintained
5. **SOD boundary compliance**: L2 did not audit own work, L3 did not modify production code

---

## Platform Isolation Rules

### L3 Write Boundary:
- **ALLOWED**: Write to `.ly_state/session/audit_reports/` ONLY
- **ALLOWED**: Update phase_gates.json (scoped to audited gate)
- **FORBIDDEN**: Edit production source code
- **FORBIDDEN**: Edit tests
- **FORBIDDEN**: Modify files outside `.ly_state/`
- **FORBIDDEN**: Call OpenCode or other L2 platforms

### L3 Read Access:
- **ALLOWED**: Read all project files for audit
- **ALLOWED**: Run tests (read-only verification)
- **FORBIDDEN**: Read/write Antigravity scratch paths

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| Codex hangs at stdin | Missing `--full-auto` flag | Add `--full-auto` to `codex exec` |
| Prompt not received | Using `codex exec "prompt"` directly | Pipe via `echo "prompt" \| codex exec --full-auto` |
| L3 doesn't update phase_gates.json | Missing instruction in prompt | Include explicit "GATE UPDATE" section in prompt |
| Audit report not created | Path doesn't exist | Ensure `.ly_state/session/audit_reports/` exists |
| Hand-typed role names | Manual prompt construction | Use dynamic {role_id} {role_name} from frontmatter |
| Multiple gates updated | L3 modified wrong gate | Specify "Update ONLY the '{gate_name}' entry" |
| Enforcer fails after approval | Missing required fields | Validate all gate fields before running enforcer |
| Path traversal in audit_report_path | Absolute or parent paths | Use relative path under `.ly_state/session/audit_reports/` |

---

## File Locations

- **Agent role specs**: `.agents/agent/*.md` (frontmatter contains role_id, name, tier, platform, sod_boundary)
- **L2 reports**: `.ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md`
- **L3 audit reports**: `.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md`
- **Phase gates**: `.ly_state/session/phase_gates.json`
- **SOD enforcer**: `scripts/sod_gate_enforcer.py`
- **This SOP**: `.ly_state/session/sop_codex_l3_audit_call.md`

---

**Version History:**
- **1.0** (2026-06-10): Initial SOP with --full-auto requirement
- **2.0** (2026-06-11): Strict dynamic template with role resolution, scoped gate updates, audit evidence checklist

**Last updated:** 2026-06-11 16:53 UTC
