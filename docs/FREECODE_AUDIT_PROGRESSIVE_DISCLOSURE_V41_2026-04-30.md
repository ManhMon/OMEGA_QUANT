# FreeCode Audit Report - Progressive Disclosure v4.1

Date: 2026-04-30
Audit ID: 2026-04-30-freecode-audit-v21-quant-pd41
Auditor: Codex
Scope:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md`
- `C:\Users\GHC\.openclaw\skills\skills_registry.json`

Notes:
- The requested relative paths `skills/team/SKILL.md` and `skills/skills_registry.json` do not exist under `C:\Users\GHC\.openclaw\workspace\V21_QUANT`.
- The active Progressive Disclosure artifacts are installed under `C:\Users\GHC\.openclaw\skills\`, and those are the files audited here.
- Current environment preflight observation during this audit: available RAM was about `9.49 GB`, below the `> 10 GB` threshold in `AGENTS.md`.

## Codex Verdict
| Truong | Gia tri | Dan chung / Chi tiet |
| :--- | :--- | :--- |
| Verdict | [NEEDS_FIX] | v4.1 claims key controls for RAM preflight, execution lock, and cloud confirmation, but those controls are not fail-closed in the audited artifacts. |
| PIT Safety | FAIL | No direct look-ahead code was found in scope, but the orchestration layer does not enforce the mandatory audit order strongly enough to guarantee PIT-safe execution. |
| Leakage Risk | HIGH | Cloud discovery/import/upload paths remain reachable with permissive defaults and without a centrally enforced confirmation gate. |
| Required Fixes | P1-P3 listed below | Highest-risk issues are missing RAM enforcement, missing execution lock enforcement, and cloud/parallel delegation drift. |

## Executive Summary
The audited files improve the documentation surface of Progressive Disclosure, but they do not meet institutional-grade control expectations yet. The strongest issue is that v4.1 advertises hard governance controls as if they are implemented, while the current artifacts provide only narrative instructions. In practice, RAM gating, execution locking, queueing, checkpoint-based anti-repeat logic, and cloud safety are either incomplete, contradictory, or not wired to an enforceable mechanism.

I did not find a direct PIT leak such as look-ahead math, label leakage logic, or T+0 feature use inside the audited files themselves. The problem is one layer above that: the orchestration contract that is supposed to guarantee PIT-safe audit sequencing is not reliable enough to be trusted as a production control.

## Findings

### P1-1: RAM preflight is declared but not implemented as a hard gate
Files:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:116`
- `C:\Users\GHC\.openclaw\workspace\scripts\setup_agent_context.ps1:5-15`

Evidence:
- `team/SKILL.md` says: check `RAM > 10GB` before delegation, otherwise `WAIT` or `ABORT`.
- `setup_agent_context.ps1` only exports static metadata such as `V21_RAM_LIMIT_MB=4096`; it does not measure free RAM or block execution.
- During this audit, observed free RAM was about `9.49 GB`, below policy, yet no automated control prevented execution.

Impact:
- The claimed v4.1 preflight is not fail-closed.
- Low-memory delegations can still occur, increasing instability and violating the documented protocol.

Required fix:
- Add an actual RAM probe before delegation and fail closed below threshold.
- Persist the sampled value and decision into an audit log or checkpoint.

### P1-2: Execution lock and queue semantics are documentation-only
Files:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:117-127`
- `C:\Users\GHC\.openclaw\workspace\AGENTS.md:17-19`

Evidence:
- `team/SKILL.md` promises `Execution Lock`, `QUEUE/WAIT`, and `Release Lock`.
- No orchestrator lock file, PID file, queue file, or lock-owner field was found in the audited control path.
- `C:\Users\GHC\.openclaw\workspace\V21_QUANT\state\skill_requests.log` does not exist.
- The only observed file-lock handling is unrelated retry logic for writing `agent_context.txt` in `setup_agent_context.ps1:29-53`; that is not an execution lock.

Impact:
- Single-agent protocol is advisory, not enforced.
- Concurrent runs can bypass intended audit ordering and undermine PIT governance.

Required fix:
- Implement an atomic execution lock with owner, PID/session id, timestamp, heartbeat, and guaranteed release in `finally`.
- Persist queue state if `QUEUE` is part of the contract.

### P1-3: Cloud import/upload and parallel delegation paths contradict the fail-closed governance model
Files:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:52-56`
- `C:\Users\GHC\.openclaw\skills\skills_registry.json:144-149`
- `C:\Users\GHC\.openclaw\skills\skill-discovery\SKILL.md:22-31`
- `C:\Users\GHC\.openclaw\skills\delegate-task\SKILL.md:21-31`
- `C:\Users\GHC\.openclaw\skills\delegate-task\SKILL.md:59-65`
- `C:\Users\GHC\.openclaw\skills\delegate-task\SKILL.md:84-125`

Evidence:
- `team/SKILL.md` adds a confirm + integrity rule for cloud import/upload, but only inside the in-loop request subsection.
- Registry metadata for `delegate-task` says it "spawns independent worker agents for parallel execution".
- `skill-discovery` uses `source="all"` and `auto_import=true` by default.
- `delegate-task` uses cloud-capable search by default and includes `upload_skill` workflows to the cloud community.

Impact:
- Leakage risk is elevated because external skill content can be imported or uploaded through paths that are not centrally blocked by the v4.1 team contract.
- Single-agent protocol can be bypassed conceptually by a registry-advertised parallel worker skill.

Required fix:
- Make local-only search the default for registry-driven automation.
- Require explicit user confirmation plus integrity verification for any cloud import, upload, or remote delegation.
- Remove or gate any parallel-worker path while `AGENTS.md` requires single-agent mode.

### P2-1: Registry integrity is broken for at least two advertised skills
Files:
- `C:\Users\GHC\.openclaw\skills\skills_registry.json:40-45`
- `C:\Users\GHC\.openclaw\skills\skills_registry.json:184-189`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:84-91`

Evidence:
- Registry advertises `coding-agent` at `coding-agent/SKILL.md`.
- Registry advertises `sops` at `sops/SKILL.md`.
- Those SKILL wrapper files are missing from `C:\Users\GHC\.openclaw\skills\`.
- `team/SKILL.md` hydrates skills via `Get-Content "C:/Users/GHC/.openclaw/skills/[SKILL_PATH]"`, so a selected missing path fails at runtime.

Impact:
- Skill hydration is not deterministic.
- Registry cannot be treated as a trustworthy source of truth.

Required fix:
- Add the missing wrapper files or remove those entries from the registry.
- Add a startup or CI validation step that fails if any registered path is missing.

### P2-2: Checkpoint contract drift prevents the advertised context-aware routing logic from working reliably
Files:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:67-70`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:101`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:125`
- `C:\Users\GHC\.openclaw\workspace\V21_QUANT\state\checkpoint.json:1-13`

Evidence:
- `team/SKILL.md` says routing uses `state/checkpoint.json` fields `last_task` and `last_skill`.
- The observed checkpoint file contains `last_checkpoint`, `project`, `status`, `last_action`, `active_branch`, `pending_task`, and `context_files`, but not `last_task` or `last_skill`.
- The skill also refers to a relative `state/checkpoint.json` path without anchoring it to `V21_WORKSPACE` or the actual `V21_QUANT` state directory.

Impact:
- Anti-repeat scoring and workflow-aware boosting are not backed by the current checkpoint schema.
- Context-aware prioritization can silently degrade or behave inconsistently across working directories.

Required fix:
- Normalize the state path with an absolute or env-resolved location.
- Extend checkpoint schema to include `last_skill`, `last_task`, timestamp, and lock owner fields expected by the workflow.

### P3-1: Version and status labels are internally inconsistent
Files:
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:1`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:5`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:96`
- `C:\Users\GHC\.openclaw\skills\team\SKILL.md:140-143`
- `C:\Users\GHC\.openclaw\skills\skills_registry.json:2-5`
- `C:\Users\GHC\.openclaw\skills\skills_registry.json:64-70`

Evidence:
- Header and workflow sections still label `/team` as `v4.0`.
- Footer labels the same file as `Version: 4.1` and `v4.1 ENABLED`.
- Registry still describes the team skill as `progressive disclosure v4.0`.

Impact:
- This is documentation drift rather than a direct safety bug.
- It increases ambiguity during audits and incident review.

Required fix:
- Align all version labels and changelog statements to the same release identifier.

## Control-Focused Assessment

### 1. PIT Safety
Status: FAIL

Reasoning:
- No direct temporal leakage logic was found in the two audited files.
- However, the v4.1 process control that is supposed to guarantee PIT-safe `/ac` sequencing is not enforceable enough.
- Missing execution lock, missing queue state, and checkpoint schema drift mean the audit-before-deploy rule is not institutionally reliable.

### 2. Leakage Risk
Status: HIGH

Reasoning:
- Registry-driven automation can reach cloud-capable skills.
- `skill-discovery` and `delegate-task` both default to cloud-inclusive search paths, and discovery can auto-import.
- Upload paths exist for sharing evolved skills back to the cloud.
- The confirm gate in `/team` is too narrow and not centrally enforced.

### 3. Institutional Grade Compliance
Status: FAIL

Reasoning:
- Institutional-grade controls should be deterministic, testable, and fail-closed.
- The current design depends too much on human compliance with markdown instructions.
- Broken registry entries and contract drift mean the control plane is not self-consistent.

### 4. RAM Preflight Checks
Status: FAIL

Reasoning:
- The policy exists in documentation.
- The implementation path does not actually measure or enforce available RAM.

### 5. Execution Lock Mechanism
Status: FAIL

Reasoning:
- No lock primitive, owner record, queue state, or release guarantee was found in scope.
- The design describes a lock but does not implement one.

## Recommended Remediation Order
1. Implement a real execution lock and queue owner contract.
2. Implement a hard RAM preflight gate with logging.
3. Fail closed on cloud import/upload and remote delegation unless explicitly confirmed.
4. Repair registry path integrity and add registry validation.
5. Align checkpoint schema with the `/team` workflow contract.
6. Clean up version drift across v4.0 and v4.1 labels.

## Final Verdict
The Progressive Disclosure upgrade is directionally useful, but it is not ready to be treated as an institutional-grade orchestration control set yet. The current state is best described as "documented intent with partial infrastructure", not "enforced governance".
