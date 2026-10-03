# AG Kit Architecture

> Comprehensive AI Agent Capability Expansion Toolkit — Synced dynamically

---

## 📋 Overview

AG Kit is a modular system consisting of:

- **26 OMEGA Agents** - Three-tier role-based AI personas with segregation of duties
- **55 Skills** - Domain-specific knowledge modules with conditional loading
- **13 Workflows** - Slash command procedures

---

## 🏗️ Directory Structure

```plaintext
.agents/
├── ARCHITECTURE.md          # This file
├── agent/                  # OMEGA Agents (3-tier SOD)
├── skills/                  # Skills (with conditional loading)
├── workflows/               # Slash Commands
├── rules/                   # Global Rules
├── memory/                  # Persistent Memory
└── scripts/                 # Master Validation Scripts
```

---

## 🤖 OMEGA Agents

OMEGA agents follow a three-tier segregation of duties (SOD) architecture with strict boundaries between orchestration, implementation, and audit.

### Three-Tier Structure

- **Tier 1 (Ly)**: Orchestration and gate decisions only. Cannot implement or audit.
- **Tier 2 (OpenCode)**: Implementation and coding. Must test all code. Cannot self-approve. Must submit to Tier 3 for audit.
- **Tier 3 (Codex)**: READ-ONLY audit. No code modifications. Must provide final verdict: `[APPROVED]` or `[NEEDS_FIX]`. 

### Tier 1: Ly (Orchestration/Gate-Only)

| Role ID | Agent | Focus |
| ------- | ----- | ----- |
| 1 | `project-manager` | Strategic orchestration/resource allocation |
| 2 | `product-owner` | Feature prioritization/stakeholder alignment |
| 3 | `scrum-master` | Agile process/blocker removal |
| 4 | `release-manager` | Release coordination/deployment gates |
| 5 | `delivery-manager` | Timeline tracking/resource management |

### Tier 2: OpenCode (Implementation)

| Role ID | Agent | Focus |
| ------- | ----- | ----- |
| 6 | `system-architect` | System design/interface definition |
| 7 | `tech-lead` | Technical leadership/code standards |
| 8 | `frontend-engineer` | UI/UX implementation |
| 9 | `backend-engineer` | API/business logic implementation |
| 10 | `database-admin` | Schema design/DB performance |
| 11 | `devops-engineer` | CI/CD automation |
| 12 | `cloud-infra-engineer` | IaC |
| 13 | `ui-ux-integrator` | UI integration/styling |
| 14 | `data-scientist` | Model research/signal discovery |
| 15 | `data-engineer` | Data pipelines/ETL |
| 16 | `machine-learning-engineer` | Model training/deployment |

### Tier 3: Codex (Audit)

| Role ID | Agent | Focus |
| ------- | ----- | ----- |
| 17 | `qa-engineer` | Functional testing |
| 18 | `sdet` | Test automation/frameworks |
| 19 | `security-auditor` | Security compliance |
| 20 | `compliance-officer` | Standards compliance/PIT safety |
| 21 | `code-reviewer` | Peer review/audit reports |
| 22 | `penetration-tester` | Security testing/exploits |
| 23 | `performance-tester` | Load/stress testing |
| 24 | `uat-validator` | User acceptance validation |
| 25 | `it-systems-auditor` | Overall system audit |
| 26 | `planning-architect` | Master Planner / Architecture Documenter |

---

## 🧩 Skills

Modular knowledge domains that agents can load on-demand based on task context.

| Skill | Directory | Description |
| ----- | --------- | ----------- |
| `api-patterns` | `api-patterns` | API design principles and decision-making. REST vs GraphQL vs tRPC selection, response formats, versioning, pagination. |
| `app-builder` | `app-builder` | Main application building orchestrator. Creates full-stack applications from natural language requests. Determines project type, selects tech stack, coordinates agents. |
| `architecture` | `architecture` | Architectural decision-making framework. Requirements analysis, trade-off evaluation, ADR documentation. Use when making architecture decisions or analyzing system design. |
| `audit-cycle` | `audit-cycle` | SOD audit cycle workflow - coordinates L2 implementation submission to L3 independent audit and verdict collection. Implements the audit-cycle process defined by omega-sod. |
| `backtesting-pit-safety` | `backtesting-pit-safety` | Backtesting integrity and Point-In-Time (PIT) safety for OMEGA_QUANT. No look-ahead bias, survivorship-free, walk-forward validation, CPCV, corporate action handling, slippage/fee modeling. |
| `bash-linux` | `bash-linux` | Bash/Linux terminal patterns. Critical commands, piping, error handling, scripting. Use when working on macOS or Linux systems. |
| `batch-operations` | `batch-operations` | Apply operations across multiple files simultaneously. Pattern-based bulk modifications, search-and-replace across codebases, consistent changes to many files at once. |
| `behavioral-modes` | `behavioral-modes` | AI operational modes (brainstorm, implement, debug, review, teach, ship, orchestrate). Use to adapt behavior based on task type. |
| `brainstorming` | `brainstorming` | Socratic questioning protocol + user communication. MANDATORY for complex requests, new features, or unclear requirements. Includes progress reporting and error handling. |
| `clean-code` | `clean-code` | Pragmatic coding standards - concise, direct, no over-engineering, no unnecessary comments |
| `code-review-checklist` | `code-review-checklist` | Code review guidelines covering code quality, security, and best practices. |
| `code-review-graph` | `code-review-graph` | Token-efficient code review using Tree-sitter AST graphs and MCP. Cuts AI token usage on large codebases by computing the blast radius of changes instead of reading entire codebases. Uses a SQLite graph database for structural analysis. |
| `context-compression` | `context-compression` | Manage and compress conversation context in long sessions. Detect when context is growing large, summarize completed work phases, archive old findings while preserving key decisions. Prevents context degradation. |
| `coordinator-mode` | `coordinator-mode` | Advanced multi-agent orchestration with parallel workers, synthesis protocols, and coordinator lifecycle. Use when complex tasks require multiple agents working in parallel with intelligent result synthesis. |
| `cso` | `cso` | Security-audit guidance for signed receipts, secret handling, integrity controls, and fail-closed verification. |
| `data-science-workflow` | `data-science-workflow` | Data science workflow for OMEGA_QUANT. EDA, data quality assessment, experiment tracking, statistical tests, reproducibility protocols, and reporting standards for Vietnam equity quant research. |
| `database-design` | `database-design` | Database design principles and decision-making. Schema design, indexing strategy, ORM selection, serverless databases. |
| `deployment-procedures` | `deployment-procedures` | Production deployment principles and decision-making. Safe deployment workflows, rollback strategies, and verification. Teaches thinking, not scripts. |
| `documentation-templates` | `documentation-templates` | Documentation templates and structure guidelines. README, API docs, code comments, and AI-friendly documentation. |
| `elite-karpathy` | `elite-karpathy` | Enforces Karpathy coding principles, simplicity, surgical edits, vectorization, and compliance trails. |
| `frontend-design` | `frontend-design` | Design thinking and decision-making for web UI. Use when designing components, layouts, color schemes, typography, or creating aesthetic interfaces. Teaches principles, not fixed values. |
| `game-development` | `game-development` | Game development orchestrator. Routes to platform-specific skills based on project needs. |
| `geo-fundamentals` | `geo-fundamentals` | Generative Engine Optimization for AI search engines (ChatGPT, Claude, Perplexity). |
| `i18n-localization` | `i18n-localization` | Internationalization and localization patterns. Detecting hardcoded strings, managing translations, locale files, RTL support. |
| `intelligent-routing` | `intelligent-routing` | Automatic agent selection and intelligent task routing. Analyzes user requests and automatically selects the best specialist agent(s) without requiring explicit user mentions. |
| `lint-and-validate` | `lint-and-validate` | Automatic quality control, linting, and static analysis procedures. Use after every code modification to ensure syntax correctness and project standards. Triggers onKeywords: lint, format, check, validate, types, static analysis. |
| `mcp-builder` | `mcp-builder` | MCP (Model Context Protocol) server building principles. Tool design, resource patterns, best practices. |
| `memory-system` | `memory-system` | Persistent cross-session memory management. Enables agents to remember user preferences, project conventions, and past decisions across different sessions using a structured MEMORY.md index and topic files. |
| `ml-dl-rl` | `ml-dl-rl` | ML/DL/RL for OMEGA_QUANT time-series and portfolio optimization. Tree-based models (XGBoost/LightGBM/CatBoost), LSTM, autoencoder, PPO reinforcement learning. Leakage prevention, validation protocols, feature stores, RL environment and reward design. |
| `mobile-design` | `mobile-design` | Mobile-first design thinking and decision-making for iOS and Android apps. Touch interaction, performance patterns, platform conventions. Teaches principles, not fixed values. Use when building React Native, Flutter, or native mobile apps. |
| `nextjs-react-expert` | `nextjs-react-expert` | React and Next.js performance optimization from Vercel Engineering. Use when building React components, optimizing performance, eliminating waterfalls, reducing bundle size, reviewing code for performance issues, or implementing server/client-side optimizations. |
| `nodejs-best-practices` | `nodejs-best-practices` | Node.js development principles and decision-making. Framework selection, async patterns, security, and architecture. Teaches thinking, not copying. |
| `omega-sod` | `omega-sod` | Strict L1-L3 platform constraints (Ly L1 Orchestration, OpenCode L2 Developer, Codex L3 Auditor), segregation of duties, no direct coding for L3, verdict requirement |
| `parallel-agents` | `parallel-agents` | Multi-agent orchestration patterns. Use when multiple independent tasks can run with different domain expertise or when comprehensive analysis requires multiple perspectives. |
| `performance-profiling` | `performance-profiling` | Performance profiling principles. Measurement, analysis, and optimization techniques. |
| `plan-writing` | `plan-writing` | Structured task planning with clear breakdowns, dependencies, and verification criteria. Use when implementing features, refactoring, or any multi-step work. |
| `powershell-windows` | `powershell-windows` | PowerShell Windows patterns. Critical pitfalls, operator syntax, error handling. |
| `python-patterns` | `python-patterns` | Python development principles and decision-making. Framework selection, async patterns, type hints, project structure. Teaches thinking, not copying. |
| `quant-research` | `quant-research` | Factor/alpha research principles for OMEGA_QUANT Vietnam equity quant pipeline. IC/IR, turnover, capacity, neutralization, regime awareness, transaction-cost-aware alpha evaluation. |
| `red-team-tactics` | `red-team-tactics` | Red team tactics principles based on MITRE ATT&CK. Attack phases, detection evasion, reporting. |
| `rust-pro` | `rust-pro` | Master modern Rust (2024 edition) with async patterns, advanced type system features, and production-ready systems programming. Expert in the current Rust ecosystem including Tokio, axum, and modern crates. Use PROACTIVELY for Rust development, performance optimization, or systems programming. |
| `seo-fundamentals` | `seo-fundamentals` | SEO fundamentals, E-E-A-T, Core Web Vitals, and Google algorithm principles. |
| `server-management` | `server-management` | Server management principles and decision-making. Process management, monitoring strategy, and scaling decisions. Teaches thinking, not commands. |
| `simplify-code` | `simplify-code` | Reduce complexity of over-engineered code. Identify unnecessary abstractions, remove dead code, flatten deep nesting, and simplify logic while preserving behavior. |
| `skillify` | `skillify` | Auto-create new skills from repetitive workflows. When you notice yourself doing the same multi-step process repeatedly, extract it into a reusable skill.md that any agent can use. |
| `sops` | `sops` | Standard Operating Procedures (SOPs) index for OMEGA_QUANT (SOP_AC, SOP_BACKTEST, SOP_PIT_SAFETY, SOP_FIX_0_RETURN, SOP_APSE_INTEGRATION). |
| `systematic-debugging` | `systematic-debugging` | 4-phase systematic debugging methodology with root cause analysis and evidence-based verification. Use when debugging complex issues. |
| `tailwind-patterns` | `tailwind-patterns` | Tailwind CSS v4 principles. CSS-first configuration, container queries, modern patterns, design token architecture. |
| `tdd-workflow` | `tdd-workflow` | Test-Driven Development workflow principles. RED-GREEN-REFACTOR cycle. |
| `testing-patterns` | `testing-patterns` | Testing patterns and principles. Unit, integration, mocking strategies. |
| `verify-changes` | `verify-changes` | Prove code works by running it, not just checking it exists. Verification through execution rather than inspection. Use after writing or modifying code to ensure it actually functions correctly. |
| `vietnam-market-data` | `vietnam-market-data` | Vietnam equity market data principles for OMEGA_QUANT. HOSE/HNX/UPCOM exchanges, VCI/vnstock data providers, ticker lifecycle, VND_FULL price scale, sector mapping, delisting/survivorship, canonical data schema. |
| `vulnerability-scanner` | `vulnerability-scanner` | Advanced vulnerability analysis principles. OWASP 2025, Supply Chain Security, attack surface mapping, risk prioritization. |
| `web-design-guidelines` | `web-design-guidelines` | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices". |
| `webapp-testing` | `webapp-testing` | Web application testing principles. E2E, Playwright, deep audit strategies. |

---

## 🔄 Workflows

Slash command procedures. Invoke with `/command`.

| Command | Description |
| ------- | ----------- |
| `/brainstorm` | /brainstorm - Structured Idea Exploration |
| `/coordinate` | /coordinate — Advanced Multi-Agent Coordination |
| `/create` | /create - Create Application |
| `/debug` | /debug - Systematic Problem Investigation |
| `/deploy` | /deploy - Production Deployment |
| `/enhance` | /enhance - Update Application |
| `/orchestrate` | Multi-Agent Orchestration |
| `/plan` | /plan - Project Planning Mode |
| `/preview` | /preview - Preview Management |
| `/remember` | /remember — Persistent Memory Management |
| `/status` | /status - Show Status |
| `/test` | /test - Test Generation and Execution |
| `/verify` | /verify — Prove Code Works |

---

## 📊 Statistics

- **Total Agents**: 26
- **Total Skills**: 55
- **Total Workflows**: 13

---

## OMEGA_QUANT Data Architecture SSOT

The repository architecture is documented in the root `ARCHITECTURE.md`. For market data, `src/omega/data/vci_direct.py` is the ingestion SSOT and `src/omega/data/sanitizer.py` is the validation SSOT.

```text
VCI HTTPS → DirectVCIClient → canonical OHLCV/PIT frame → DataSanitizer → research/backtest
```

- `DirectVCIClient` owns VCI allowlisting, HTTPS transport, bounded reads, retry exhaustion, redaction, VND normalization, and PIT/session filtering.
- `DataSanitizer` owns causal cleaning, duplicate handling, fitted outlier parameters, and `as_of <= available_at` enforcement.
- `src/omega/data/validator.py`, `data_validator.py`, and `data_quality.py` are compatibility shims re-exporting canonical objects by identity.
- `archive/legacy_adapters/` and `archive/legacy_validators/` are historical, fail-closed inventory; never use them as active dependencies.
