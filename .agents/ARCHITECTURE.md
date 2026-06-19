# AG Kit Architecture

> Comprehensive AI Agent Capability Expansion Toolkit — 2026.5.31

---

## 📋 Overview

AG Kit is a modular system consisting of:

- **25 OMEGA Agents** - Three-tier role-based AI personas with segregation of duties (OMEGA SOD customization 2026.6.11)
- **46 Skills** - Domain-specific knowledge modules with conditional loading (audit-cycle added 2026.6.12)
- **13 Workflows** - Slash command procedures

---

## 🏗️ Directory Structure

```plaintext
.agents/
├── ARCHITECTURE.md          # This file
├── agent/                  # 25 OMEGA Agents (3-tier SOD)
├── skills/                  # 45 Skills (with conditional loading)
├── workflows/               # 13 Slash Commands
├── rules/                   # Global Rules
├── memory/                  # Persistent Memory (2026.5.13)
└── scripts/                 # Master Validation Scripts
```

---

## 🤖 OMEGA Agents (25)

OMEGA agents follow a three-tier segregation of duties (SOD) architecture with strict boundaries between orchestration, implementation, and audit.

### Three-Tier Structure

- **Tier 1 (Ly)**: Orchestration and gate decisions only. Cannot implement or audit.
- **Tier 2 (OpenCode)**: Implementation and coding. Must test all code. Cannot self-approve. Must submit to Tier 3 for audit.
- **Tier 3 (Codex)**: READ-ONLY audit. No code modifications. Must provide final verdict: `[APPROVED]` or `[NEEDS_FIX]`.

### Phase Gate Fields

Each agent includes OMEGA metadata:
- `role_id`: Unique identifier (1-25)
- `tier`: 1 (Ly), 2 (OpenCode), or 3 (Codex)
- `platform`: Ly, OpenCode, or Codex
- `sod_boundary`: SOD constraints for the role

### Tier 1: Ly (Orchestration/Gate-Only)

| Role ID | Agent               | Focus                                  |
| ------- | ------------------- | -------------------------------------- |
| 1       | project-manager     | Strategic orchestration/resource allocation |
| 2       | product-owner       | Feature prioritization/stakeholder alignment |
| 3       | scrum-master        | Agile process/blocker removal          |
| 4       | release-manager     | Release coordination/deployment gates  |
| 5       | delivery-manager    | Timeline tracking/resource management  |

**SOD Boundary**: `"orchestration/gate-only, no implementation/audit"`

### Tier 2: OpenCode (Implementation)

| Role ID | Agent                      | Focus                           |
| ------- | -------------------------- | ------------------------------- |
| 6       | system-architect           | System design/interface definition |
| 7       | tech-lead                  | Technical leadership/code standards |
| 8       | frontend-engineer          | UI/UX implementation            |
| 9       | backend-engineer           | API/business logic implementation |
| 10      | database-admin             | Schema design/DB performance    |
| 11      | devops-engineer            | CI/CD automation                |
| 12      | cloud-infra-engineer       | IaC                             |
| 13      | ui-ux-integrator           | UI integration/styling          |
| 14      | data-scientist             | Model research/signal discovery |
| 15      | data-engineer              | Data pipelines/ETL              |
| 16      | machine-learning-engineer  | Model training/deployment       |

**SOD Boundary**: `"implementation-only, test required, no self-approval, submit to Tier3"`

### Tier 3: Codex (Audit)

| Role ID | Agent                | Focus                              |
| ------- | -------------------- | ---------------------------------- |
| 17      | qa-engineer          | Functional testing                 |
| 18      | sdet                 | Test automation/frameworks         |
| 19      | security-auditor     | Security compliance                |
| 20      | compliance-officer   | Standards compliance/PIT safety    |
| 21      | code-reviewer        | Peer review/audit reports          |
| 22      | penetration-tester   | Security testing/exploits          |
| 23      | performance-tester   | Load/stress testing                |
| 24      | uat-validator        | User acceptance validation         |
| 25      | it-systems-auditor   | Overall system audit               |

**SOD Boundary**: `"READ-ONLY audit, no code/file modifications, markdown audit report required, final verdict [APPROVED] or [NEEDS_FIX]"`

---

## 🧩 Skills (46)

Modular knowledge domains that agents can load on-demand based on task context. Each skill has a `when_to_use` frontmatter field for conditional/intelligent loading.

### Frontend & UI

| Skill                   | Description                                                           |
| ----------------------- | --------------------------------------------------------------------- |
| `nextjs-react-expert`   | React & Next.js performance optimization (Vercel - 58 rules)          |
| `web-design-guidelines` | Web UI audit - 100+ rules for accessibility, UX, performance (Vercel) |
| `tailwind-patterns`     | Tailwind CSS v4 utilities                                             |
| `frontend-design`       | UI/UX patterns, design systems                                        |

### Backend & API

| Skill                   | Description                    |
| ----------------------- | ------------------------------ |
| `api-patterns`          | REST, GraphQL, tRPC            |
| `nodejs-best-practices` | Node.js async, modules         |
| `python-patterns`       | Python standards, FastAPI      |
| `rust-pro`              | Rust async, systems, type system |

### Database

| Skill             | Description                 |
| ----------------- | --------------------------- |
| `database-design` | Schema design, optimization |

### Cloud & Infrastructure

| Skill                   | Description               |
| ----------------------- | ------------------------- |
| `deployment-procedures` | CI/CD, deploy workflows   |
| `server-management`     | Infrastructure management |

### Testing & Quality

| Skill                   | Description              |
| ----------------------- | ------------------------ |
| `testing-patterns`      | Jest, Vitest, strategies |
| `webapp-testing`        | E2E, Playwright          |
| `tdd-workflow`          | Test-driven development  |
| `code-review-checklist` | Code review standards    |
| `lint-and-validate`     | Linting, validation      |

### Security

| Skill                   | Description              |
| ----------------------- | ------------------------ |
| `vulnerability-scanner` | Security auditing, OWASP |
| `red-team-tactics`      | Offensive security       |

### Architecture & Planning

| Skill           | Description                |
| --------------- | -------------------------- |
| `app-builder`   | Full-stack app scaffolding |
| `architecture`  | System design patterns     |
| `plan-writing`  | Task planning, breakdown   |
| `brainstorming` | Socratic questioning       |

### Mobile

| Skill           | Description           |
| --------------- | --------------------- |
| `mobile-design` | Mobile UI/UX patterns |

### Game Development

| Skill              | Description           |
| ------------------ | --------------------- |
| `game-development` | Game logic, mechanics |

### SEO & Growth

| Skill              | Description                   |
| ------------------ | ----------------------------- |
| `seo-fundamentals` | SEO, E-E-A-T, Core Web Vitals |
| `geo-fundamentals` | GenAI optimization            |

### Shell/CLI

| Skill                | Description               |
| -------------------- | ------------------------- |
| `bash-linux`         | Linux commands, scripting |
| `powershell-windows` | Windows PowerShell        |

### Orchestration & Memory (2026.5.13)

| Skill                     | Description                                                 |
| ------------------------- | ----------------------------------------------------------- |
| `coordinator-mode`        | Multi-agent orchestration with parallel workers & synthesis  |
| `memory-system`           | Persistent cross-session memory with MEMORY.md index        |
| `context-compression`     | Auto-compress context in long sessions                      |
| `verify-changes`          | Prove code works by running it, not just inspecting         |
| `batch-operations`        | Multi-file pattern-based modifications                      |
| `simplify-code`           | Reduce over-engineered complexity                           |
| `skillify`                | Auto-create skills from repetitive workflows                |
| `code-review-graph`       | Token-efficient code review via Tree-sitter AST + MCP       |
| `audit-cycle`             | SOD audit cycle workflow (L2->L3->gate coordination)        |
| `omega-sod`               | OMEGA_QUANT SOD framework with repo-local skill contract    |

### Other

| Skill                     | Description               |
| ------------------------- | ------------------------- |
| `clean-code`              | Coding standards (Global) |
| `behavioral-modes`        | Agent personas            |
| `parallel-agents`         | Multi-agent patterns      |
| `mcp-builder`             | Model Context Protocol    |
| `documentation-templates` | Doc formats               |
| `i18n-localization`       | Internationalization      |
| `performance-profiling`   | Web Vitals, optimization  |
| `systematic-debugging`    | Troubleshooting           |
| `intelligent-routing`     | Request → agent routing   |

---

## 🔄 Workflows (13)

Slash command procedures. Invoke with `/command`.

| Command          | Description                                    |
| ---------------- | ---------------------------------------------- |
| `/brainstorm`    | Socratic discovery                             |
| `/coordinate`    | **NEW** Advanced multi-agent coordination      |
| `/create`        | Create new features                            |
| `/debug`         | Debug issues                                   |
| `/deploy`        | Deploy application                             |
| `/enhance`       | Improve existing code                          |
| `/orchestrate`   | Multi-agent coordination                       |
| `/plan`          | Task breakdown                                 |
| `/preview`       | Preview changes                                |
| `/remember`      | **NEW** Save to persistent memory              |
| `/status`        | Check project status                           |
| `/test`          | Run tests                                      |
| `/verify`        | **NEW** Prove code works by running it         |

---

## 🎯 Skill Loading Protocol (Conditional)

```plaintext
User Request → Check `when_to_use` frontmatter → Match? → Load full SKILL.md
                                                     ↓ No match
                                                  Skip (save tokens)
```

### Strict Repo-Local Skill Source Contract (STRICT_REPO_LOCAL_SKILL_LOADING_20260612)

**Effective**: 2026-06-12. All L2/L3 dispatches MUST load role specs and skills exclusively from repo-local paths.

| Constant | Value | Purpose |
|----------|-------|---------|
| `REPO_AGENT_ROOT` | `{REPO_ROOT}/.agents/agent` | Role spec files (`*.md`) |
| `REPO_SKILL_ROOT` | `{REPO_ROOT}/.agents/skills` | Skill definitions (`*/SKILL.md`) |

**Loading Protocol (MANDATORY):**
1. Read role spec from `REPO_AGENT_ROOT/<role_name>.md` and parse frontmatter
2. Extract `skills` list from frontmatter
3. Read each declared skill's `SKILL.md` from `REPO_SKILL_ROOT/<skill_name>/SKILL.md`
4. Report exact repo-local files read in L2/L3 output
5. Stop/NEEDS_FIX if required repo-local source is missing

**Forbidden Paths (Non-Authoritative):**

| Path | Description |
|------|-------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | Antigravity IDE scratch |
| `.openclaw\skills` | OpenClaw skills |
| `C:\Users\GHC\.agents` | Global Codex agents |
| `.codex\memories` | Codex memory files |

Mentions allowed ONLY if explicitly marked non-authoritative or as forbidden-path scan evidence.

**Enforcement:** `scripts/sod_gate_enforcer.py` validates repo-local skill source evidence for post-cutoff gates.

### Skill Structure

```plaintext
skill-name/
├── SKILL.md           # (Required) Metadata, when_to_use & instructions
├── scripts/           # (Optional) Python/Bash scripts
├── references/        # (Optional) Templates, docs
└── assets/            # (Optional) Images, logos
```

### Required Frontmatter Fields

```yaml
---
name: skill-name
description: What this skill does
when_to_use: "When to activate. NOT for X."  # 2026.5.13
allowed-tools: Read, Grep, Glob
---
```

### Enhanced Skills (with scripts/references)

| Skill               | Files | Coverage                            |
| ------------------- | ----- | ----------------------------------- |
| `app-builder`       | 20    | Full-stack scaffolding              |

---

## 🛠️ Scripts (2)

Master validation scripts that orchestrate skill-level scripts.

### Master Scripts

| Script          | Purpose                                 | When to Use              |
| --------------- | --------------------------------------- | ------------------------ |
| `checklist.py`  | Priority-based validation (Core checks) | Development, pre-commit  |
| `verify_all.py` | Comprehensive verification (All checks) | Pre-deployment, releases |

### Usage

```bash
# Quick validation during development
python .agents/scripts/checklist.py .

# Full verification before deployment
python .agents/scripts/verify_all.py . --url http://localhost:3000
```

### What They Check

**checklist.py** (Core checks):

- Security (vulnerabilities, secrets)
- Code Quality (lint, types)
- Schema Validation
- Test Suite
- UX Audit
- SEO Check

**verify_all.py** (Full suite):

- Everything in checklist.py PLUS:
- Lighthouse (Core Web Vitals)
- Playwright E2E
- Bundle Analysis
- Mobile Audit
- i18n Check

For details, see [scripts/README.md](scripts/README.md)

---

## 📊 Statistics

| Metric              | Value                             |
| ------------------- | --------------------------------- |
| **Total Agents**    | 20 (1 major upgrade in 2026.5.13) |
| **Total Skills**    | 45 (+7 new in 2026.5.13)          |
| **Total Workflows** | 13 (+2 new in 2026.5.13)          |
| **Total Scripts**   | 2 (master) + 16 (skill-level)     |
| **Coverage**        | ~95% web/mobile + orchestration   |
| **Token Efficiency**| Reduced via conditional skill loading |

---

## 🔗 Quick Reference

| Need     | Agent                 | Skills                                |
| -------- | --------------------- | ------------------------------------- |
| Web App  | `frontend-specialist` | nextjs-react-expert, frontend-design |
| API      | `backend-specialist`  | api-patterns, nodejs-best-practices   |
| Mobile   | `mobile-developer`    | mobile-design                         |
| Database | `database-architect`  | database-design                       |
| Security | `security-auditor`    | vulnerability-scanner                 |
| Testing  | `test-engineer`       | testing-patterns, webapp-testing      |
| Debug    | `debugger`            | systematic-debugging                  |
| Plan     | `project-planner`     | brainstorming, plan-writing           |
