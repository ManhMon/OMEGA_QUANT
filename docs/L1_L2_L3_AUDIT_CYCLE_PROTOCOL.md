# L1→L2→L3 Audit Cycle Protocol (PD v4.2)

**Version**: 1.0  
**Date**: 2026-05-22  
**Status**: APPROVED (Operational Standard)  
**Baseline**: `docs/AGENT_WORKFLOW.md` v2.4

---

## EXECUTIVE SUMMARY

This protocol defines the standardized workflow for L1 (Ly orchestration) → L2 (OpenCode implementation) → L3 (Codex audit) → L1 (gate finalization) cycle in OMEGA_QUANT.

**Key Principles:**
1. **Segregation of Duties (SOD)**: L2 implementation session ≠ L3 audit session
2. **L3 SIGKILL Guard**: L3 runs in narrow workdir with L1-prepared context, no MCP self-discovery
3. **Gate Ownership**: L1 owns final gate decision; L3 provides verdict recommendation only
4. **State Persistence**: All state in `.ly_state/`, not RAM

---

## 1. L2 IMPLEMENTATION FLOW (OpenCode)

### 1.1. Invocation Pattern

**CLI Command:**
```powershell
opencode run "<task description>"
```

**Session Label:** `[L2-Impl:RoleXX-*]`

**Workdir:** `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT`

**Constraints:**
- L2 writes production code, tests, and implementation artifacts
- L2 MUST NOT audit or approve its own work
- L2 session MUST terminate before L3 audit begins

### 1.2. L2 Execution Checklist

- [ ] Task scope clearly defined
- [ ] Implementation complete with unit tests
- [ ] Tests run and PASS locally
- [ ] Artifacts written to expected paths
- [ ] Session terminates cleanly
- [ ] L1 verifies artifact existence before dispatching L3

### 1.3. L2 Output Contract

L2 MUST produce:
1. **Code artifacts**: Modified/new `.py` files in canonical package structure
2. **Test artifacts**: Test files in `tests/` with PASS evidence
3. **Session log**: Execution trace for L1 review

---

## 2. L3 AUDIT FLOW (Codex) - SIGKILL GUARD PROTOCOL

### 2.1. Problem Statement

**Observed Issue:** L3 Codex sessions die with SIGKILL near shutdown while touching side files like `loaded_skills.json` and `audit_log.jsonl`.

**Root Cause:** Likely shutdown/bookkeeping issue when L3 tries to write multiple files at end of session, not core audit failure.

**Evidence:** Main audit report often completes before death; RAM was not the bottleneck (16GB free observed).

### 2.2. Mitigation Strategy

**Three-Phase Flow:**
1. **L1 Prep**: Ly scans CRG/MCP and prepares focused context file
2. **L3 Audit**: Codex runs in narrow workdir, reads prep file, writes ONLY audit report
3. **L1 Finalize**: Ly reads audit report, updates `phase_gates.json` and `audit_log.jsonl`

### 2.3. L1 Prep Phase

**Tool:** `OMEGA_QUANT/scripts/l3_audit_manager.py --mode prep`

**Inputs:**
- `--phase <phase_id>`
- `--files <comma-separated file list>`
- `--tests <comma-separated test list>`
- `--pytest-cmd <pytest command>`

**Output:** `.ly_state/session/<phase>_l1_context_prep.md`

**Content:**
```markdown
# PHASE_X - L1 Context Prep for L3 Audit

## Scope
- **Files**: [list]
- **Tests**: [list]

## Fixes/Changes to Verify
[description]

## Test Evidence
- Command: [pytest command]

## L3 Task
Verify fixes by:
1. Reading declared files
2. Running pytest to verify all PASS
3. Writing audit report with verdict
```

### 2.4. L3 Audit Phase

**CLI Command:**
```powershell
codex exec --dangerously-bypass-approvals-and-sandbox "[L3-Audit:Role21-*] <task>"
```

**Session Label:** `[L3-Audit:Role21-*]` or `[L3-Audit:Role20-*]`

**Workdir:** `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT` (narrow, not workspace root)

**Constraints:**
- L3 reads L1 prep file: `.ly_state/session/<phase>_l1_context_prep.md`
- L3 reads target files listed in prep
- L3 runs pytest to verify tests
- L3 writes ONLY audit report: `.ly_state/session/audit_reports/role21_<phase>_<timestamp>.md`
- L3 MUST NOT write to `audit_log.jsonl` or `phase_gates.json`
- L3 MUST NOT load MCP/CRG for self-discovery (L1 already did this)

**Skills Allowed:**
- `/ac` (audit-cycle)
- `/karpathy-auditor`
- Other audit-focused skills

**Skills Prohibited:**
- MCP graph tools (L1 already scanned)
- Implementation/fix tools (L3 is audit-only)

### 2.5. L3 Audit Report Contract

L3 MUST produce audit report with:
```markdown
# PHASE_X Audit Report

**l3_session_id**: `<uuid or session identifier>`
**l3_session_key**: `<session key>`
**audit_date**: `<ISO timestamp>`
**auditor**: `Code Reviewer (Role 21)` or `Compliance Officer (Role 20)`

## Scope
[files audited]

## Findings
[list of findings]

## Test Evidence
[pytest results]

## Verdict
**final_verdict**: `[APPROVED]` or `[NEEDS_FIX]`
**pit_safety**: `PASS` or `FAIL`
**role_compliance**: `PASS` or `FAIL`
**vectorization**: `PASS` or `FAIL`
```

### 2.6. L1 Finalize Phase

**Tool:** `OMEGA_QUANT/scripts/l3_audit_manager.py --mode finalize`

**Inputs:**
- `--phase <phase_id>`
- `--report-path <path to L3 audit report>`
- `--test-results <test summary>`

**Actions:**
1. Parse L3 audit report for contract fields:
   - `l3_session_id`
   - `l3_session_key`
   - `final_verdict`
2. Validate contract completeness
3. Update `.ly_state/session/phase_gates.json`:
   ```json
   {
     "PHASE_X_GATE_KEY": {
       "status": "APPROVED" or "NEEDS_FIX",
       "final_verdict": "[APPROVED]" or "[NEEDS_FIX]",
       "audit_date": "<ISO timestamp>",
       "auditor": "Code Reviewer (Role 21)",
       "l3_session_id": "<from report>",
       "l3_session_key": "<from report>",
       "audit_report_path": "<report path>",
       "pit_safety": "PASS",
       "role_compliance": "PASS",
       "vectorization": "PASS",
       "test_results": "<summary>"
     }
   }
   ```
4. Append to `.ly_state/session/audit_log.jsonl`:
   ```json
   {
     "timestamp": "<ISO>",
     "event": "audit_complete",
     "phase": "<phase_id>",
     "scope": "L1 CRG context prep + L3 audit; final verdict: <verdict>",
     "role": "L3-Audit:Role21-Code Reviewer",
     "session_id": "<l3_session_id>",
     "session_key": "<l3_session_key>",
     "final_verdict": "<verdict>",
     "pit_safety": "PASS",
     "vectorization": "PASS",
     "role_compliance": "PASS",
     "mcp_usage": "L1_ONLY",
     "artifacts": {
       "audit_report_path": "<path>"
     }
   }
   ```

### 2.7. SIGKILL Guard Checklist

- [ ] L1 prep file created before L3 spawn
- [ ] L3 workdir is `OMEGA_QUANT`, not workspace root
- [ ] L3 does NOT load MCP/CRG tools
- [ ] L3 writes ONLY audit report (no side files)
- [ ] L1 finalizes gate/log AFTER L3 terminates
- [ ] Main audit artifact exists even if L3 dies

---

## 3. GATE VALIDATION PROTOCOL

### 3.1. Pre-Push Gate Check

**Tool:** `OMEGA_QUANT/scripts/sod_gate_enforcer.py`

**Enforcement Points:**
1. Git pre-push hook: `.git/hooks/pre-push`
2. Manual check: `python scripts/sod_gate_enforcer.py`

**Validation Rules:**
- All phases in `phase_gates.json` MUST have:
  - `l3_session_id` (non-empty)
  - `l3_session_key` (non-empty)
  - `audit_report_path` (file exists)
  - `final_verdict` = `[APPROVED]`
- If ANY phase has `[NEEDS_FIX]` or missing fields → BLOCK PUSH

### 3.2. Gate File Locations

**Critical:** SOD enforcer reads from **workspace root gate file**, not repo-local:
- **Enforced:** `C:\Users\GHC\.openclaw\workspace\.ly_state\session\phase_gates.json`
- **Repo-local (ignored by git):** `OMEGA_QUANT/.ly_state/session/phase_gates.json`

**Implication:** Both files MUST be kept in sync for push to succeed.

### 3.3. Gate Lock Command

**Tool:** `OMEGA_QUANT/scripts/phase_workflow_enforcer.py`

**Usage:**
```powershell
python scripts/phase_workflow_enforcer.py --lock-gate <phase_id> <stage> \
  --l3_session_id <uuid> \
  --l3_session_key <key> \
  --audit_report_path <path> \
  --final_verdict [APPROVED]
```

---

## 4. COMPLETE WORKFLOW EXAMPLE

### Phase X Implementation + Audit

**Step 1: L2 Implementation**
```powershell
# Ly dispatches to OpenCode
opencode run "[L2-Impl:Role9-Backend] Implement Phase X feature with unit tests"

# OpenCode writes code + tests, runs pytest
# Session terminates
```

**Step 2: L1 Prep**
```powershell
# Ly prepares context
python scripts/l3_audit_manager.py --mode prep \
  --phase phase_x \
  --files "packages/quant/src/omega/quant/feature_x.py" \
  --tests "packages/quant/tests/test_feature_x.py" \
  --pytest-cmd "pytest packages/quant/tests/test_feature_x.py -v"

# Output: .ly_state/session/phase_x_l1_context_prep.md
```

**Step 3: L3 Audit**
```powershell
# Ly dispatches to Codex
codex exec --dangerously-bypass-approvals-and-sandbox \
  "[L3-Audit:Role21-Review] Audit Phase X implementation. \
   Read .ly_state/session/phase_x_l1_context_prep.md for scope. \
   Write audit report to .ly_state/session/audit_reports/role21_phase_x_<timestamp>.md"

# Codex reads prep, audits files, runs pytest, writes report
# Session terminates (may SIGKILL but report already written)
```

**Step 4: L1 Finalize**
```powershell
# Ly finalizes gate
python scripts/l3_audit_manager.py --mode finalize \
  --phase phase_x \
  --report-path ".ly_state/session/audit_reports/role21_phase_x_20260522.md" \
  --test-results "10/10 PASS"

# Updates phase_gates.json and audit_log.jsonl
```

**Step 5: Verify + Push**
```powershell
# Verify gate
python scripts/sod_gate_enforcer.py
# [PASS] SOD GATE CHECK PASSED

# Commit + push
git add <files>
git commit -m "feat(phase_x): implement feature X"
git push origin master
# Pre-push hook runs sod_gate_enforcer.py automatically
# [APPROVED] SOD Check Passed. Proceeding to push...
```

---

## 5. TROUBLESHOOTING

### 5.1. L3 SIGKILL Still Occurs

**Symptoms:** L3 session dies before writing audit report.

**Diagnosis:**
1. Check RAM: `Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory`
2. Check workdir: Should be `OMEGA_QUANT`, not workspace root
3. Check MCP usage: L3 should NOT load MCP tools

**Mitigation:**
- Reduce L3 scope further (fewer files)
- Increase L1 prep detail (more explicit instructions)
- Use background exec with longer timeout

### 5.2. Gate Push Blocked

**Symptoms:** `git push` fails with "SOD GATE BLOCKED: Non-approved phases"

**Diagnosis:**
1. Check workspace root gate file: `C:\Users\GHC\.openclaw\workspace\.ly_state\session\phase_gates.json`
2. Look for phases with `[NEEDS_FIX]` or missing fields

**Fix:**
1. If stale gate: Remove old gate key from workspace root file
2. If legitimate block: Complete L3 audit cycle for that phase
3. Verify both repo-local and workspace-root gate files are in sync

### 5.3. L3 Report Missing Contract Fields

**Symptoms:** L1 finalize fails with "Missing contract fields from L3 report"

**Diagnosis:** L3 audit report does not contain required fields.

**Fix:**
1. Re-run L3 audit with explicit instruction to include contract fields
2. Or manually add fields to report (emergency only)
3. Update `l3_audit_manager.py` to parse report more robustly

---

## 6. MAINTENANCE

### 6.1. Protocol Updates

This protocol is versioned and audited. Changes require:
1. L2 implementation of tooling changes
2. L3 audit of protocol doc
3. L1 gate approval

### 6.2. Tooling Improvements

Priority improvements for `l3_audit_manager.py`:
- [ ] Robust report parsing (handle markdown variations)
- [ ] Auto timestamp generation
- [ ] Auto gate key mapping (phase → gate key pattern)
- [ ] NEEDS_FIX branch handling
- [ ] Strict validation before gate writes
- [ ] Sync workspace-root and repo-local gate files automatically

---

## 7. REFERENCES

- `docs/AGENT_WORKFLOW.md` - 25-role agent workflow baseline
- `docs/AGENT_WORKFLOW_AUDIT_R3.md` - Independent audit (7/7 PASS)
- `.ly_state/session/L3_SIGKILL_GUARD_PROTOCOL_20260522.md` - Original SIGKILL analysis
- `.ly_state/session/L3_AUDIT_LAUNCHER_TEMPLATE.md` - Launcher template
- `scripts/l3_audit_manager.py` - Automation helper
- `scripts/sod_gate_enforcer.py` - Pre-push gate validator
- `scripts/phase_workflow_enforcer.py` - Gate lock tool

---

**END OF PROTOCOL**
