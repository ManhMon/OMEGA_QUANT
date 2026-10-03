# AGENTS.md - OMEGA_QUANT Protocol
**Version**: 3.0 | **Updated**: 2026-08-27

## Tiers

| Tier | Platform | Role IDs | Boundary |
|------|----------|----------|----------|
| L1 | Ly / Antigravity | 1-5 | Orchestrate, plan, delegate, enforce gates |
| L2 | OpenCode | 6-16 | Implement, refactor, run tests, write L2 report |
| L3 | Codex | 17-30 | Plan, independent audit, verdict, gate metadata |

## AG Kit Loading & Composite Role Protocol (COMPOSITE_ROLE_EXECUTION_20260824)

- Role specs live in `.agents/agent/*.md`.
- Each role frontmatter defines `role_id`, `tier`, `platform`, `skills`, and `sod_boundary`.
- `sod_boundary` is binding; L1 must enforce it before delegation.
- **Composite Role Execution Model (COMPOSITE_ROLE_EXECUTION_20260824)**:
  - **L2 Engineering Squad (Tier 2 OpenCode)**: A task may be executed by a Primary Lead Role (Role ID 6-16) with optional co-assigned Tier 2 specialist roles (e.g., `ui-ux-integrator` + `backend-engineer` + `data-engineer`). The L2 session is authorized to load and report skills declared across all co-assigned Tier 2 roles, provided each role spec file is read from `REPO_AGENT_ROOT/<role>.md` and listed under `## Repo-Local Files Read`.
  - **L3 Audit Council (Tier 3 Codex)**: An audit may be conducted by a Primary Lead Auditor (Role ID 17-30) with optional co-assigned Tier 3 auditor roles (e.g., `code-reviewer` + `security-auditor` + `it-systems-auditor` + `performance-tester`). The L3 session is authorized to load and report skills declared across all co-assigned Tier 3 roles, provided each role spec file is read from `REPO_AGENT_ROOT/<role>.md` and listed under `## Repo-Local Files Read`.
  - **Cross-Tier Separation**: L2 sessions MUST NOT load Tier 3 roles. L3 sessions MUST NOT load Tier 2 roles.
  - **Writer != Auditor**: The set of L2 role IDs must be strictly disjoint from the set of L3 role IDs (`set(l2_roles) & set(l3_roles) == empty`). Self-approval remains strictly forbidden.
  - **Hierarchical Tiered Model & Subagent Cost Optimization (HIERARCHICAL_SUBAGENT_OPTIMIZATION_20260913)**:
    - **Primary Lead Role (L2/L3)**: Runs on high-reasoning models (`high`: e.g. `cx/gpt-6.1-sol`, `gpt-5-6-thinking`). Responsible for overall orchestration, architecture, root-cause trace, dynamic 24-Dimension compliance, and signing final verdicts.
    - **Worker Subagents**: Supervised by the Lead Role, sub-workers run on `SUBAGENT_MODEL=ag/gemini` (high-speed, low-cost) for repetitive tasks: regex call-site searches, test boilerplate generation, AST inspections, and log parsing.
    - **Zero-Token Local Gate**: Local deterministic scripts (`validate_l2_report.py`, AST verification, pytest collection, `checklist.py`) MUST execute locally before LLM tokens are consumed. No LLM tokens may be spent on formatting, markdown heading validation, or AST assertion checks.
    - **Strict Boundary Isolation**: L2 worker subagents must remain strictly within Tier 2 (Antigravity/OpenCode). L3 audit subagents must remain strictly within Tier 3 (Codex). Subagents inherit their parent role's SoD tier; cross-tier subagent delegation is strictly prohibited.
- L2 receives: primary + co-role specs + task + scope + requirements.
- L3 receives: primary + co-audit role specs + scope + checks + verdict contract.
- **Role boundary evidence**: L2/L3 prompts MUST include primary role_id and role_name. L1 MUST verify writer != auditor before delegation.

## Repo-Local Skill Source Contract (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)

**Effective**: 2026-06-12. All L2/L3 dispatches MUST use repo-local role/skill sources only.

### Authoritative Paths

| Constant | Value | Purpose |
|----------|-------|---------|
| `REPO_AGENT_ROOT` | `{REPO_ROOT}/.agents/agent` | Role spec files (`*.md`) |
| `REPO_SKILL_ROOT` | `{REPO_ROOT}/.agents/skills` | Skill definition files (`*/skill.md`) |

### Loading Protocol (MANDATORY for L2 and L3)

1. **First**: Read role spec from `REPO_AGENT_ROOT/<role_name>.md` and parse frontmatter.
2. **Parse skills**: Extract `skills` list from frontmatter.
3. **Read skills**: For each declared skill, read `REPO_SKILL_ROOT/<skill_name>/skill.md` only.
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

### Graph-Gated Dispatch (SOD_GRAPH_GATED_DISPATCH_20260827)

Before L2 or L3 dispatch, `scripts/dispatch_l2.py` and `scripts/dispatch_l3.py` MUST:

1. Validate the external graph database at `C:\Users\GHC\tools\code-review-graph-data\omega_quant\graph.db` against current `HEAD`.
2. Rebuild with `C:\Users\GHC\tools\code-review-graph` outside OMEGA_QUANT when missing or stale; otherwise run an incremental update. Cloud embeddings are forbidden.
3. Resolve every scope token exactly. Reject missing, flag-like, traversal, and directory-expansion inputs above the explicit 200-file safe limit; never silently narrow scope. Existing docs/config may be reported `not_indexed`; source/test query failures remain errors.
4. Validate finite, bounded, type-correct graph schemas and exact target/count consistency. Persist canonical JSON plus SHA-256 lock as one rollback-safe atomic pair under `.ly_state/session/`; bind unchanged repository and graph commits through publication.
5. Fail closed before lessons, reports, prompts, model processes, or fallback on any graph, CLI, query, or evidence error.

### Gate-Close Transaction

Use `python scripts/update_gate.py close <gate> --message <message> --scope <file> [...]` only after L3 approval. It holds a single close lock, snapshots gate metadata, scoped files, and `HEAD` through enforcer and commit verification, revalidates exact `[APPROVED]`, rejects secrets and scope escapes, verifies parent/scope/blob hashes, pushes the immutable commit SHA once without force, then verifies the remote commit. Failure retains the local state; no silent retry.

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

- role_id MUST be in range 17-30
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

1. **1 Task Execution = 1 Primary Lead Role (+ Optional Co-Assigned Specialist Roles within same Tier)**.
2. **Writer != Auditor**. Self-approval forbidden. All L2 role IDs must be strictly disjoint from all L3 role IDs.
3. L2 must exit/save state before L3 starts.
4. L1 never plans, implements, or audits; L1 only delegates, records evidence, enforces gates. L1 MUST delegate all master plan and implementation plan creation to Codex L3 (model "cx/gpt-6.1-sol") using a non-audit role.
5. All state/evidence must be file-backed in `.ly_state/session/`.
6. Do not run OpenCode and Codex simultaneously. Platform cap: 4GB.
7. **L3 write boundary**: L3 may ONLY write to `.ly_state/session/audit_reports/`, `.ly_state/session/` (for plans), and update `.ly_state/session/phase_gates.json`. L3 MUST NOT edit production source code, tests, or any files outside `.ly_state/`.
8. **Scratch path prohibition**: L2 and L3 MUST NOT read or write Antigravity scratch paths. All operations use `REPO_ROOT` with repo-relative paths only.
9. **No manual override**: Manual approval overrides are forbidden. All gates require valid L3 audit with [APPROVED] verdict and `python scripts/sod_gate_enforcer.py` exit 0.
10. **L2 session ID format**: L2 session IDs MUST follow format `l2_role{role_id}_{task_slug}_{YYYYMMDD}` (e.g., `l2_role11_agents_md_strict_sod_hardening_20260611`).
11. **GEMINI.md Conflict Resolution**: In case of any conflict between the Tier 0 Edit Mode instructions in GEMINI.md (which may allow direct editing of single-file fixes by the L1 orchestrator) and the SoD platform isolation constraints in AGENTS.md, the SoD platform isolation constraints in AGENTS.md take absolute precedence. Under no circumstances is L1 allowed to bypass SoD or modify code directly. All code edits must go through L2 OpenCode.
12. **Anti-Polling & Zero-Idle Directive (ANTI_POLLING_ZERO_IDLE_20260918)**: L1, L2, and L3 MUST NOT loop, poll, or repeatedly invoke status/inspection tools (`git status`, `git status -s`, `sod_gate_enforcer.py`, `manage_task status`, process polling) to wait for task or background completion. When launching a long-running or background command, the agent MUST immediately stop calling tools and yield the turn. Unbounded polling loops and repeated status probes without user interaction or state mutations are strictly forbidden.

### L1 Audit Report Mechanical Correction Exception

L1 may directly correct an L3 audit report without a full L3 re-audit only when all conditions hold:

1. The report already contains an unchanged `[APPROVED]` verdict.
2. The correction is limited to an extremely simple syntax, formatting, or exact enforcer-required heading/wording omission.
3. The correction does not change the verdict, findings, evidence, scope, test results, role identities, gate metadata, or any substantive audit conclusion.
4. L1 records the exact report path, correction, and unchanged `[APPROVED]` verdict in file-backed session evidence, then reruns `python scripts/sod_gate_enforcer.py`.

This exception does not permit L1 to approve a gate, alter a `[NEEDS_FIX]` report, or make substantive report edits.


## Required Flow

```text
[L1 Orchestrator]
       │
       ▼
1. python scripts/dispatch_l2.py <l2_role> <gate> <slug> "<task>" "<scope>" [--co-role <role>] [--model <model>]
       │  └─ Pre-dispatch: Graph validation, lesson retrieval, anti-drip contract injection.
       │  └─ Execute generated command in terminal: L2 implements, refactors, tests, writes L2 report.
       ▼
2. python scripts/validate_l2_report.py <l2_session_id> <role_id> <role_name>
       │  └─ Zero-token gate: verifies filename, headings, repo-local skills, anti-drip sweep JSON. Exit 0 required.
       ▼
3. python scripts/dispatch_l3.py <l3_role> <gate> <l2_session_id> <l2_role> "<scope>" [--model <model>]
       │  └─ Pre-dispatch: Enforces Writer != Auditor, touches audit placeholder, generates Codex CLI command.
       │  └─ Execute generated command in terminal: L3 runs independent adversarial audit, evaluates 16 dims, runs update_gate.py.
       ▼
       ├─────────────────────────────────────────┐
       ▼ [NEEDS_FIX]                             ▼ [APPROVED]
4. Remediation Loop:                       5. Gate Close Transaction:
   a) python scripts/extract_lessons.py       a) python scripts/sod_gate_enforcer.py (exit 0)
      (Mandatory Hard Gate: deduplicate)      b) python scripts/update_gate.py close <gate> --message "<msg>" --scope <files>
   b) Re-run Step 1 (dispatch_l2.py              (Atomic close lock, scoped hash snapshot, immutable push & verify)
      in remediation mode with F-001..F-xxx)
```

**One-command pipeline (recommended for standard gates):**
```powershell
python scripts/sod_pipeline.py <l2_role> <l3_role> <gate> <slug> "<task>" "<scope>" [--risk low|high] [--model <model>] [--subagent-model <model>]
```

**Autonomous ReAct pipeline (ChatWeb / Aurora failover — zero-cost / unlimited via web reasoning model):**
```powershell
python scripts/sod_pipeline_au.py <l2_role> <l3_role> <gate> <slug> "<task>" "<scope>" [--model au/gpt-5-6-thinking] [--risk low|high] [--close]
```
- **L2 Worker (`scripts/run_l2_agent.py`)**: Executes autonomous ReAct loops (`read_file`, `patch_file`, `write_file`, `run_command`, `list_dir`) directly with `au/gpt-5-6-thinking` (free tier, no subagent required), sliding-window context compression, head/tail output truncation (6000 chars), and anti-drip sweep generation.
- **Pre-L3 Validation Gate (`scripts/validate_l2_report.py`)**: Enforces zero-token checks (format, headings, probe coverage, repo-local files) before invoking L3.
- **L3 Auditor (`scripts/run_l3_audit.py`)**: Executes independent dynamic 24-Dimension evaluation, code review directly via `au/gpt-5-6-thinking`, and writes structured findings `F-001..F-xxx`.
- **Remediation Loop**: Automatically runs `scripts/extract_lessons.py` upon `[NEEDS_FIX]` and feeds deduplicated findings back to L2.

### Hierarchical Subagent Cost Optimization (HIERARCHICAL_SUBAGENT_OPTIMIZATION_20260913)

To prevent wasting expensive reasoning models on repetitive or low-complexity work:
1. **Tiered Model Specialization**:
   - **Lead Role (`--model`)**: Premium high-reasoning models (`sol`/`xhigh`/`gpt-5-6-thinking`) are reserved strictly for high-level architecture, code synthesis, conflict resolution, and final audit verdicts.
   - **Worker Subagent (`--subagent-model`)**: High-speed, low-cost subagent model (`ag/gemini`) is delegated granular tasks: massive file scanning, boilerplate test drafting, documentation summarization, and AST searches. L2 subagents MUST strictly use `ag/gemini`.
2. **Zero-Token Local Execution**:
   - Local tool runs (`pytest`, `git diff`, AST analysis, syntax validation) run with 0 LLM tokens via `run_command` or dedicated pre-validation scripts (`validate_l2_report.py`, `sod_gate_enforcer.py`).
3. **Subagent Tooling & Explicit Phased Delegation (`task` in OpenCode, `spawn_agent` in Codex)**:
   - **L2 OpenCode Phased Workflow**:
     - *Phase 1 (Recon)*: Lead Role MUST call `task(agent='explorer', prompt=...)` for call-site regex sweeps and previous lesson retrieval before any file modification.
     - *Phase 2 (Boilerplate)*: Lead Role MUST call `task(agent='general', prompt=...)` to draft repetitive unit tests and dynamic 24-Dimension boundary cases.
     - *Phase 3 (Core Synthesis)*: Lead Role directly implements domain logic, mathematical algorithms, and PIT safety. Critical reasoning must never be delegated.
     - *Phase 4 (Verify & Sweep)*: Lead Role executes scoped test suite and writes the anti-drip L2 report.
   - **L3 Codex Structured Probes**:
     - Lead Auditor delegates 3 parallel audit probes via `spawn_agent(task_name=..., task=..., model='ag/gemini-3.8-flash-high')`:
       - *Probe 1 (`probe_24d_scan`)*: Regex AST scan for dynamic 24-Dimension invariants (timezone, lookahead, secret redaction).
       - *Probe 2 (`probe_test_exec`)*: Scoped pytest slices and failure traceback collection.
       - *Probe 3 (`probe_atomicity`)*: Atomic rename (.tmp -> final) and DB rollback verification.
     - Lead Auditor retrieves results via `wait_agent` and issues the authoritative verdict.


A task is not complete until `python scripts/sod_gate_enforcer.py` exits `0`.

### Verdict Handling

- **[APPROVED]**: L1 records gate metadata, then dispatches a final deep audit to Codex CLI model `cx/gpt-6.1-sol` after L3 approval and before the final enforcer. The audit is advisory only, read-only, must not edit source, tests, phase gates, or audit reports, and may run in the background when appropriate. L3's `[APPROVED]` verdict remains the sole approval authority. L1 runs enforcer and proceeds if exit 0. **TOKEN SAVER**: L1 MAY skip the final deep audit for low-risk gates where scope is limited to test fixtures, documentation, or static config files with no production logic changes. L1 MUST record the skip decision and reason in file-backed session evidence before running the enforcer.
- **[NEEDS_FIX]**: L1 MUST complete the lesson extraction hard gate below before creating or dispatching any remediation L2 session; after extraction succeeds, L1 creates a new L2 session with fix scope, L3 re-audits after fix, cycle repeats until [APPROVED]
- **No verdict or partial verdict**: Gate remains `PENDING_L3_AUDIT`, no progression
- **Manual override**: Forbidden. All approvals require valid L3 audit + enforcer exit 0

### Anti-Drip Zero-Patch Consolidation Protocol (ANTI_DRIP_PROTOCOL_20260823)

To prevent iterative drip/piecemeal fixes (fix1, fix2, fix3...) and achieve single-shot `[APPROVED]` verdicts, all agents MUST follow:

1. **Zero-Patch Consolidated Prompting**: L1 MUST NOT dispatch piecemeal tasks. L1 must consolidate 100% of audit findings, edge cases, and dynamic 24-Dimension invariants into a single itemized prompt: `(1)..., (2)..., (3)...`.
2. **Root-Cause Architectural Sweeping**: L2 MUST NOT apply symptom-level single-line patches. When a defect is identified (e.g. case-sensitivity, path aliasing, exit codes), L2 must use search tools to locate and fix all matching patterns across the entire module.
3. **Pre-Audit Self-Fuzzing**: L2 MUST write adversarial unit tests covering boundary conditions (None/empty types, Math extremes/div0, File/rollback durability, Lock timeouts) prior to publishing reports.
4. **Scoped Regression Closure**: L2 MUST execute the scoped related test suite (e.g. `pytest tests/test_<module>*.py -v`; do NOT run the full repository-wide 4,400+ test suite) ensuring zero regression breakage before submitting.
5. **Zero-Token Pre-Validation Gate**: L1 MUST run `python scripts/validate_l2_report.py` prior to invoking L3. Any formatting, heading, or placeholder defect MUST be rejected at zero LLM token cost.

### 24-Dimension Adversarial Matrix (dynamic catalog)

Every L2 implementation self-fuzzing and L3 independent audit MUST explicitly verify all 24 dimensions. JEV supplies one extra focus dimension; it never excludes other dimensions:
1. **Malformed/out-of-bounds types**: NaN, Inf, non-scalar strings, lists.
2. **Invalid/directory I/O paths**: Strict UTF-8, BOM handling & Windows charmap/CRLF encoding invariance.
3. **Corrupted/duplicate/partial checkpoint shards**: Integrity verification before state mutation.
4. **Fail-closed exit codes & error states**: Non-zero exit code on failure, never continue silently.
5. **Rollback & transactional atomicity**: Atomic file replacement (`.tmp` -> rename), DB rollback.
6. **PIT & look-ahead safety**: `as_of <= available_at`, strict UTC/ICT (15:30) timezone boundary check.
7. **Trading calendar & holiday boundaries**: Vietnam statutory holidays & market closed days.
8. **Numeric precision & overflow**: Zero-division guard, deterministic RNG seed invariance.
9. **Concurrency & race condition resistance**: Multi-worker isolation, file/DB locks.
10. **VND_FULL price scale & unit invariance**: No raw thousand-dong vs dong unit confusion.
11. **Survivorship & delisting anomalies**: Handling delisted/frozen tickers without look-ahead.
12. **CLI injection & flag smuggling sanitization**: Whitelist identifier arguments, shell escape.
13. **Schema drift & unexpected column mutation**: Immutable contracts, schema validation.
14. **Resource exhaustion & memory bounds**: Streaming parquet/chunks, no OOM on full universe.
15. **Network timeout & 429 retry exhaustion**: Bounded exponential backoff, circuit breaker.
16. **Secret redaction & credential leak prevention**: Strip bearer tokens/API keys from logs/reports.
17. **JEV routing input validation**: Role, risk, cycle, and model-focus type/range validation.
18. **Model catalog & cross-tier allowlisting**: Preserve role-specific model allowlists.
19. **Decision context binding & replay prevention**: Bind gate, role, risk, and session.
20. **Decision schema & digest integrity**: Enforce exact fields and SHA-256 verification.
21. **Decision publication durability & rollback**: Fsync temporary data and atomically replace.
22. **Decision lock ownership & concurrency**: Preserve live locks; safely recover confirmed stale locks.
23. **Provider retry & fallback safety**: Bound retries; permit only approved low-risk first-cycle fallback.
24. **JEV secret-safe prompt routing**: Sanitize task context and routing evidence.

### Lesson Extraction Hard Gate (lessons_extraction_hard_gate_20260726)

Before ANY L2 remediation dispatch triggered by an L3 or final advisory `[NEEDS_FIX]`, L1 MUST:

1. Run the existing extractor from `REPO_ROOT`: `python scripts/extract_lessons.py` over the current `.ly_state/session/audit_reports/` evidence.
2. Verify extraction completed successfully and persisted/deduplicated lessons in `.agents/knowledge/lessons.jsonl`. The extractor's persisted count and deduplication outcome MUST be recorded in a file-backed evidence report under `.ly_state/session/`.
3. Use `python scripts/get_relevant_lessons.py` only for retrieval/context. Retrieval is not extraction and MUST NOT substitute for `extract_lessons.py`.
4. Block remediation dispatch when extraction fails, persistence cannot be verified, deduplication cannot be determined, or the evidence report is missing.

The extraction evidence MUST include gate name `lessons_extraction_hard_gate_20260726`, source evidence paths/date scope, exact extractor command, exit status, exact count persisted, deduplication outcome, lesson-store path, and timestamp. No manual override is permitted.

## Call L2 OpenCode Implementation Work

**Pre-dispatch requirements:**
1. Read `.agents/agent/<role_name>.md` and extract frontmatter: `role_id`, `tier`, `platform`, `name`
2. Validate: role_id 6-16, tier=2, platform=OpenCode
3. Verify filename stem matches frontmatter `name` field exactly
4. Run `python scripts/get_relevant_lessons.py <role_id>` and append the output to the implementation task requirements to alert the worker about past mistakes.

> [!IMPORTANT]
> **MANDATORY PRE-DISPATCH STEP**: L1 MUST run `python scripts/get_relevant_lessons.py <role_id> "<task_query>"` first and embed the retrieved lessons output in the `LESSONS` parameter of**Automated dispatch (RECOMMENDED):**
```powershell
python scripts/dispatch_l2.py <role_name> <gate_name> <task_slug> "<task_description>" "<scope>" [--risk low|high] [--subagent-model <model>] [--token-saver]
```
Copy lệnh từ output `---COMMAND---` rồi chạy. Script tự động: validate role, load lessons, infer model tier (`9router/cx/gpt-6.1-sol` high / `9router/cx/gpt-6-luna` medium/low), cấu hình subagent `ag/gemini`, tiêm chỉ thị subagent bắt buộc, tạo session ID.

**Manual dispatch (fallback nếu dispatch_l2.py không dùng được):**
```powershell
echo "" | opencode run -m "9router/cx/gpt-6-luna" --pure --dangerously-skip-permissions --dir "C:\Users\GHC\repos\OMEGA_QUANT" "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: {role_id} {role_name} - OpenCode L2 Implementation Work. TASK: [TASK]. GATE: [GATE_NAME]. LESSONS: [APPENDED_LESSONS_LEARNED]. MANDATORY HIERARCHICAL SUBAGENT WORKER DIRECTIVE: Lead Role operates on MODEL=9router/cx/gpt-6-luna. Repetitive searches, boilerplate tests, AST scans MUST be delegated to subagents via task(agent='explorer'|'general', prompt='...'). SKILL SOURCE CONTRACT: REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent; REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills. First run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; first read REPO_AGENT_ROOT\{role_name}.md and parse frontmatter; then read required skill.md files only from REPO_SKILL_ROOT for declared skills. Any skill loaded from Antigravity scratch/OpenClaw/C:\Users\GHC\.agents/Codex memory is non-authoritative. Report exact repo-local role/skill files read and forbidden path scan result. SCOPE: [FILES]. REQUIREMENTS: use repo-relative paths from REPO_ROOT only; implement/refactor/test only; write L2 report to .ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md. Do not audit or approve. Stop/NEEDS_FIX if required repo-local source missing. L2 REPORT FORMAT (MANDATORY - copy exactly): The report MUST contain these sections in order: (1) Header with Role, Gate, Session, Date fields. (2) '## Repo-Local Files Read' heading followed by bullet list of every file actually read from REPO_AGENT_ROOT and REPO_SKILL_ROOT (e.g. '- .agents/agent/{role_name}.md', '- .agents/skills/{skill}/skill.md'). (3) '## Changes Made' listing modified files. (4) '## Verification' with test results. (5) '## Forbidden Path Scan' with EXACTLY four lines, one per forbidden path, each line ending with the EXACT phrase: 'non-authoritative scan evidence only; no reliance.' — The four lines must mention: '.gemini\antigravity-ide\scratch\ag-kit', '.openclaw\skills', 'C:\Users\GHC\.agents', '.codex\memories'. FILENAME must be l2_role{role_id}_{task_slug}_{YYYYMMDD}.md with NO _retry suffix."
```-kit', '.openclaw\skills', 'C:\Users\GHC\.agents', '.codex\memories'. FILENAME must be l2_role{role_id}_{task_slug}_{YYYYMMDD}.md with NO _retry suffix."
```

**Platform lock protocol:** OpenCode L2 sessions MUST NOT call Codex or any L3 platform directly. L1 controls all cross-platform delegation.

**Strict report naming:** L2 reports MUST follow format: `.ly_state/session/l2_role{role_id}_{task_slug}_{YYYYMMDD}.md`

**L2 report template:** L2 agents MUST use `.agents/skills/omega-sod/l2_report_template.md`. Copy it exactly, fill in `[PLACEHOLDER]` values only.

**Windows requirements:** always use `echo "" |`, `--pure`, `--dangerously-skip-permissions`, and `--dir "C:\Users\GHC\repos\OMEGA_QUANT"`. Prompts must define `REPO_ROOT`; workers must not resolve `.agents` through Antigravity scratch paths.

**Repo-local skill source contract:** L2 prompts MUST include `REPO_AGENT_ROOT`, `REPO_SKILL_ROOT`, instruction to read repo-local role spec first, parse skills, read only repo-local skill.md files, and report exact files read. Global/scratch/OpenClaw/Codex memory sources are non-authoritative.

### Pre-L3 Validation Gate (TOKEN SAVER — MANDATORY)

> [!IMPORTANT]
> After L2 completes, L1 MUST run this BEFORE dispatching L3 Codex. Catches format errors cheaply without spending L3 tokens.

```powershell
python scripts/validate_l2_report.py {l2_session_id} {role_id} {role_name}
```

- **Exit 0** → safe to dispatch L3
- **Exit 1** → retry L2 only (do NOT dispatch L3)

This check validates: filename format (`_YYYYMMDD.md` only, no `_retry`), `## Repo-Local Files Read` heading, forbidden path scan wording (exact suffix required), authoritative forbidden path usage (must be zero).


**Pre-dispatch requirements:**
1. Read `.agents/agent/<role_name>.md` and extract frontmatter: `role_id`, `tier`, `platform`, `name`, `sod_boundary`
2. Validate: role_id 17-25, tier=3, platform=Codex, sod_boundary defined
3. Verify filename stem matches frontmatter `name` field exactly
4. Verify l2_role_id != l3_role_id (writer != auditor)
5. Run `python scripts/get_relevant_lessons.py <role_id>` and append the output to the review requirements.
6. Use extracted `role_id` and `name` in prompt (never hand-type role names)
7. Touch/create the empty audit report file at `.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md` before dispatching Codex, to prevent file-system sandbox patch failures on Windows.

**Automated dispatch (RECOMMENDED):**
```powershell
python scripts/dispatch_l3.py <l3_role> <gate> <l2_session_id> <l2_role> "<scope>" [--risk low|high] [--subagent-model <model>] [--run]
```
Copy lệnh từ output `---COMMAND---` rồi chạy. Script tự động: validate role (17-30, tier=3, Codex), load lessons, tạo placeholder report file, infer risk, bật `--enable multi_agent`, và tiêm chỉ thị bắt buộc spawn subagent.

Script xử lý bước 1-7 tự động bao gồm lessons retrieval, role validation, và pre-creation report file.

**Manual dispatch (fallback):**
```powershell
New-Item -ItemType File -Path .ly_state\session\audit_reports\role{role_id}_{gate_slug}_{YYYYMMDD}.md -Force; echo "REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT. ROLE: {role_id} {role_name} - Codex L3 Independent Review. GATE: {gate_name}. L2_SESSION: {l2_session_id}. L2_ROLE: {l2_role_id} {l2_role_name}. MANDATORY HIERARCHICAL SUBAGENT AUDIT DIRECTIVE: Lead Auditor operates on MODEL=cx/gpt-6-astra(low). You MUST delegate test execution (pytest) and AST scans to subagents via spawn_agent(task_name='probe', task='...', model='ag/gemini-3.8-flash-high') and retrieve results via wait_agent. Do NOT run test suites directly on Lead Auditor thread. SKILL SOURCE CONTRACT: REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent; REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills. First read REPO_AGENT_ROOT\{role_name}.md and parse frontmatter; read required skill.md files only from REPO_SKILL_ROOT. Any skill from Antigravity scratch/OpenClaw/C:\Users\GHC\.agents/Codex memory is non-authoritative. Report exact repo-local files read and forbidden path scan result. SCOPE: [FILES]. CHECKS: [CHECKLIST]. REQUIREMENTS: first run Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'; use repo-relative paths from REPO_ROOT only; never read/write Antigravity scratch paths. AUDIT EVIDENCE CHECKLIST: 1. Verify l2_role_id={l2_role_id} != l3_role_id={role_id}. 2. Verify code changes match approved scope. 3. Run all tests. 4. Check PIT safety, no look-ahead bias. 5. Validate SOD boundaries. 6. Verify L2 report lists repo-local skill source evidence. VERDICT: Write [APPROVED] or [NEEDS_FIX] to .ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md. GATE UPDATE: Run 'python scripts/update_gate.py {gate_name} l2_session_id={l2_session_id} l2_role_id={l2_role_id} l2_role_name={l2_role_name} l3_session_id={l3_session_id} l3_role_id={role_id} l3_role_name={role_name} audit_report_path=.ly_state/session/audit_reports/role{role_id}_{gate_slug}_{YYYYMMDD}.md final_verdict=[verdict] sod_boundary_checked=true writer_auditor_separated=true l2_completed=true'. Do NOT edit phase_gates.json manually. FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update." | codex exec -m "cx/gpt-6-astra(low)" --enable multi_agent -s danger-full-access --dangerously-bypass-approvals-and-sandbox
```

**Scoped gate updates:** L3 MUST use `python scripts/update_gate.py` to update gates. Do NOT edit phase_gates.json manually. Do not modify other gates or create new gates.

**Audit evidence requirements:** L3 audit reports MUST document:
- Writer != Auditor verification (l2_role_id != l3_role_id)
- Scope compliance check
- Test execution results
- PIT safety verification
- SOD boundary compliance
- Repo-local skill source evidence (L2 report lists exact files read from REPO_AGENT_ROOT/REPO_SKILL_ROOT)
- Forbidden path scan result (no authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`)

**Platform isolation:** Codex L3 sessions MUST NOT call OpenCode or modify production source code directly. L3 writes only to `.ly_state/session/audit_reports/` and updates phase_gates.json.

**Codex requirements:** always pipe prompt via `echo`; never use interactive stdin. Prompt must include `REPO_ROOT` and a first-step `Set-Location` guard. On Windows sandbox-restricted environments, always use `--dangerously-bypass-approvals-and-sandbox` instead of `--full-auto` to prevent restricted-token failures and infinite loops.

### L3 Platform Fallback Protocol (L3_FALLBACK_AURORA_WEBCHAT)

Khi nền tảng Codex CLI gặp sự cố (lỗi nhị phân, mất kết nối, 429 quota, hoặc không tương thích API `wire_api = "responses"` với các model chat), L3 **TỰ ĐỘNG FALLBACK** sang Aurora WebChat (`scripts/run_l3_audit.py`):
- **Fallback Platform / Service**: Aurora ChatGPT Web Bridge trên port 8080 (`http://127.0.0.1:8080/v1`).
- **Fallback Model**: `gpt-5-6-thinking` (hoặc `chatgpt-web/gpt-5-6-thinking` qua token ChatGPT Web trong `~/.config/opencode/opencode.json`).
- **Tự động hóa**: Thực thi trực tiếp qua `python scripts/run_l3_audit.py <gate_name> --model gpt-5-6-thinking` (hoặc cờ `--aurora` trong `scripts/dispatch_l3.py`). Script tự động thực hiện pytest trên scope, nén ngữ cảnh, gửi request tới Aurora port 8080, trích xuất verdict, ghi báo cáo L3 audit và cập nhật gate bằng `scripts/update_gate.py`. Trường hợp Aurora gặp sự cố, script tự động dự phòng sang 9router (`ag/gemini-3.8-flash-high`).
- **Bảo toàn SoD**: Phiên L3 WebChat Aurora vẫn tuân thủ 100% ranh giới SoD của Tier 3 (Role ID 17-30, Writer != Auditor, quyền ghi chỉ giới hạn trong `.ly_state/session/audit_reports/` và cập nhật gate qua `scripts/update_gate.py`, tuyệt đối không sửa file mã nguồn).

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
- `l3_role_id`: Integer role ID (17-30 for Codex L3), validated: tier=3, platform=Codex, has sod_boundary
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

## L1 Orchestrator Bootstrap Rules

1. **Vietnamese Communication**: Always respond to the user in Vietnamese.
2. **Timer Ban**: Absolutely do not use timer tools (`schedule`, `cron`, or background sleeps). Rely strictly on Reactive Wakeup.
3. **L1 Dynamic Composite Role**: L1's base role is `orchestrator`. Depending on the task domain, L1 must dynamically combine it with a specialist role (e.g. `tech-lead` or `machine-learning-engineer` for quant/architecture, `release-manager` for gates). Announce this composite role on the very first line of the response: `🤖 **Applying knowledge of @[orchestrator / <specialist-role>]...**`.
4. **Memory Update Gate**: Whenever a gate is `[APPROVED]`, L1 must review and update `tech-decisions.md` to record the new configurations/findings before starting a new phase.
5. **Final Codex Deep Audit Rule**: After L3 returns `[APPROVED]` and before the final enforcer, L1 MUST dispatch a final deep audit to Codex CLI model `"cx/gpt-6-astra(low)"`. The audit is advisory and read-only, must not edit source, tests, phase gates, or audit reports, and may run in the background when appropriate. Codex L3's verdict remains the sole approval authority. Use this safe command pattern:
   ```powershell
   echo "<TASK_PROMPT>" | codex exec -m "cx/gpt-6-astra(low)" --dangerously-bypass-approvals-and-sandbox
   ```
6. **Plan Creation & Approval Rule**: L1 TUYỆT ĐỐI KHÔNG ĐƯỢC TỰ LẬP KẾ HOẠCH. Mọi tác vụ lập kế hoạch tổng thể (master plan) và kế hoạch chi tiết (implementation_plan.md) bắt buộc phải được giao cho Codex L3 (sử dụng model `"cx/gpt-6-astra(low)"`) với một role phù hợp (không phải role audit) thực hiện. Sau khi kế hoạch được lập, quy trình audit bởi Codex L3 (role audit) vẫn phải diễn ra nghiêm ngặt trước khi chuyển cho L2 triển khai thực tế. L1 chỉ đóng vai trò điều phối, không được phép viết hay chỉnh sửa kế hoạch.
7. **24-Dimension Pre-Audit Directive Enforcement**: L1 must ensure all L2 dispatches utilize `scripts/dispatch_l2.py` with the dynamic 24-Dimension Master Adversarial Matrix. L1 MUST execute `python scripts/validate_l2_report.py` before dispatching any L3 audit, mechanically rejecting invalid heading orders, unreplaced placeholders, and path traversal at zero token cost.

## 24-Dimension Master Adversarial Testing Matrix (STRICT_ADVERSARIAL_MATRIX_20260927)

All L2 implementations must rigorously self-fuzz the canonical `scripts/jev_model_router.py` catalog before submitting reports:
1. **Malformed/out-of-bounds types**: NaN, Inf, strings, lists, and bounded input validation.
2. **Invalid/directory I/O paths**: Regular-file checks, strict UTF-8, BOM, and CRLF handling.
3. **Corrupted/duplicate/partial checkpoint shards**: Integrity checks before state mutation.
4. **Fail-closed exit codes & error states**: Non-zero failure states; no silent continuation.
5. **Rollback/atomicity failures**: Atomic replacement, rollback, and durability.
6. **PIT & look-ahead safety**: `as_of <= available_at` with explicit timezone boundaries.
7. **Trading calendar & holiday boundaries**: Vietnam exchange sessions, holidays, and closures.
8. **Numeric precision & zero-division overflow**: Finite arithmetic, precision, and zero guards.
9. **Concurrency & race condition resistance**: Lock ownership, worker isolation, and race safety.
10. **VND_FULL price scale & unit invariance**: Dong-scale consistency without thousand-dong confusion.
11. **Survivorship & delisting anomalies**: Delisted/frozen instruments without look-ahead.
12. **CLI injection & flag smuggling sanitization**: Allowlisted identifiers and shell-safe arguments.
13. **Schema drift & unexpected column mutation**: Strict schemas and immutable contracts.
14. **Resource exhaustion & memory bounds**: Bounded input, response, and memory use.
15. **Network timeout & 429 retry exhaustion**: Bounded retries and safe provider failure behavior.
16. **Secret redaction & credential leak prevention**: Credential-safe logs, reports, and artifacts.
17. **JEV routing input validation**: Role, risk, cycle, and model-focus type/range validation.
18. **Model catalog & cross-tier allowlisting**: Lead/subagent choices remain role-specific and allowlisted.
19. **Decision context binding & replay prevention**: Gate, role, risk, and session binding.
20. **Decision schema & digest integrity**: Exact fields, canonical bytes, and SHA-256 verification.
21. **Decision publication durability & rollback**: Temporary-file fsync, atomic replace, and cleanup.
22. **Decision lock ownership & concurrency**: Live/stale owner checks and concurrent publisher isolation.
23. **Provider retry & fallback safety**: Bounded 429/timeout retry and low-risk-only fallback.
24. **JEV secret-safe prompt routing**: Sanitized task context and credential-safe routing evidence.
