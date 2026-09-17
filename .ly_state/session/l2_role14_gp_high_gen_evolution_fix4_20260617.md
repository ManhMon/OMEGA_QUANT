# L2 Implementation Report — Role 14 (data-scientist)

**Report**: `l2_role14_gp_high_gen_evolution_fix4_20260617.md`
**Date**: 2026-06-17
**Role**: 14 — Data Scientist (Tier 2, OpenCode Platform)
**Gate**: `GP_EXPANSION_ALTERNATIVE_REGIMES_20260617`
**Task**: Fix L2 report forbidden paths table — ensure all 8 exact forbidden paths are enumerated with correct labels
**Scope**: `.ly_state/session/l2_role14_gp_high_gen_evolution_fix4_20260617.md`
**SOD Boundary**: implementation-only, test required, no self-approval, submit to Tier 3

---

## 1. Agent Definition Source

| Field | Value |
|-------|-------|
| **Agent file (repo-relative)** | `.agents\agent\data-scientist.md` |
| **Role ID** | 14 |
| **Name** | data-scientist |
| **Description** | Model research/signal discovery |
| **Tier** | 2 |
| **Platform** | OpenCode |
| **SOD boundary** | implementation-only, test required, no self-approval, submit to Tier3 |

**Frontmatter skills list (9 required):**

| # | Skill Name | Source (repo-relative) | Status |
|---|-----------|----------------------|--------|
| 1 | `python-patterns` | `.agents\skills\python-patterns\SKILL.md` | READ OK |
| 2 | `clean-code` | `.agents\skills\clean-code\SKILL.md` | READ OK |
| 3 | `testing-patterns` | `.agents\skills\testing-patterns\SKILL.md` | READ OK |
| 4 | `systematic-debugging` | `.agents\skills\systematic-debugging\SKILL.md` | READ OK |
| 5 | `performance-profiling` | `.agents\skills\performance-profiling\SKILL.md` | READ OK |
| 6 | `quant-research` | `.agents\skills\quant-research\SKILL.md` | READ OK |
| 7 | `vietnam-market-data` | `.agents\skills\vietnam-market-data\SKILL.md` | READ OK |
| 8 | `backtesting-pit-safety` | `.agents\skills\backtesting-pit-safety\SKILL.md` | READ OK |
| 9 | `data-science-workflow` | `.agents\skills\data-science-workflow\SKILL.md` | READ OK |

All 9 required skills were loaded exclusively from the authoritative repo-local skill root (`.agents\skills\` within `C:\Users\GHC\repos\OMEGA_QUANT`).

---

## 2. Skill Source Contract

| Parameter | Value |
|-----------|-------|
| **REPO_ROOT** | `C:\Users\GHC\repos\OMEGA_QUANT` |
| **REPO_AGENT_ROOT** | `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent` |
| **REPO_SKILL_ROOT** | `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills` |

**Contract**: Skills are authoritative ONLY when loaded from `REPO_SKILL_ROOT` (`.agents\skills\` within the repo). Any skill content loaded from the following locations is **non-authoritative** and must be rejected:

- `.gemini\antigravity-ide\scratch\ag-kit` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `.gemini/antigravity-ide/scratch/ag-kit` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `.openclaw\skills` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `.openclaw/skills` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `C:\Users\GHC\.agents` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `C:/Users/GHC/.agents` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `.codex\memories` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.
- `.codex/memories` is a forbidden path — not used as source; any skill loaded from this forbidden path is non-authoritative.

---

## 3. Forbidden Path Scan Table

Every path below was scanned and confirmed as a forbidden path that is not used as source. Each entry is labeled with the required enforcer keywords.

| # | Exact Path | Variant | Classification | Enforcer Labels |
|---|-----------|---------|---------------|----------------|
| 1 | `.gemini\antigravity-ide\scratch\ag-kit` | backslash | forbidden path | not used as source; non-authoritative if loaded |
| 2 | `.gemini/antigravity-ide/scratch/ag-kit` | forward-slash | forbidden path | not used as source; non-authoritative if loaded |
| 3 | `.openclaw\skills` | backslash | forbidden path | not used as source; non-authoritative if loaded |
| 4 | `.openclaw/skills` | forward-slash | forbidden path | not used as source; non-authoritative if loaded |
| 5 | `C:\Users\GHC\.agents` | backslash | forbidden path | not used as source; non-authoritative if loaded |
| 6 | `C:/Users/GHC/.agents` | forward-slash | forbidden path | not used as source; non-authoritative if loaded |
| 7 | `.codex\memories` | backslash | forbidden path | not used as source; non-authoritative if loaded |
| 8 | `.codex/memories` | forward-slash | forbidden path | not used as source; non-authoritative if loaded |

**Scan result**: ALL 8 forbidden paths confirmed present in scan table. No skill content was read from any forbidden path. All skill reads originated from the authoritative repo-local `.agents\skills\` directory under `REPO_ROOT`.

### Forbidden Path Detailed Notes

- `.gemini\antigravity-ide\scratch\ag-kit` (backslash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `.gemini/antigravity-ide/scratch/ag-kit` (forward-slash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `.openclaw\skills` (backslash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `.openclaw/skills` (forward-slash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `C:\Users\GHC\.agents` (backslash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `C:/Users/GHC/.agents` (forward-slash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `.codex\memories` (backslash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.
- `.codex/memories` (forward-slash variant) — this is a forbidden path; it was not used as source and is non-authoritative for this report.

---

## 4. Repo-Local Files Read

All files read are within `REPO_ROOT` (`C:\Users\GHC\repos\OMEGA_QUANT`). No files from any forbidden path were accessed.

| # | Repo-Relative Path | Purpose |
|---|-------------------|---------|
| 1 | `.agents\agent\data-scientist.md` | Agent definition; parsed frontmatter for 9 required skills |
| 2 | `.agents\skills\python-patterns\SKILL.md` | Skill: Python development principles, framework selection, async patterns, type hints |
| 3 | `.agents\skills\clean-code\SKILL.md` | Skill: Pragmatic coding standards — SRP, DRY, KISS, YAGNI, naming, function rules |
| 4 | `.agents\skills\testing-patterns\SKILL.md` | Skill: Testing pyramid, AAA pattern, unit/integration/E2E, mocking strategies |
| 5 | `.agents\skills\systematic-debugging\SKILL.md` | Skill: 4-phase debugging (Reproduce, Isolate, Understand, Fix & Verify) |
| 6 | `.agents\skills\performance-profiling\SKILL.md` | Skill: Core Web Vitals, profiling workflow, bundle analysis, runtime profiling |
| 7 | `.agents\skills\quant-research\SKILL.md` | Skill: Alpha lifecycle, IC/IR metrics, turnover/costs, capacity, neutralization, regime awareness |
| 8 | `.agents\skills\vietnam-market-data\SKILL.md` | Skill: HOSE/HNX/UPCOM exchanges, VND_FULL scale, ticker lifecycle, sector mapping, canonical schema |
| 9 | `.agents\skills\backtesting-pit-safety\SKILL.md` | Skill: PIT safety, survivorship-free, walk-forward, CPCV, corporate actions, slippage/fee model |
| 10 | `.agents\skills\data-science-workflow\SKILL.md` | Skill: EDA protocol, data quality, statistical tests, experiment tracking, reproducibility |

**Total repo-local files read**: 10 (1 agent definition + 9 skill definitions).

---

## 5. Skill Summary (9 Required from Frontmatter)

### 5.1 python-patterns
- **Description**: Python development principles and decision-making. Framework selection, async patterns, type hints, project structure.
- **Key topics**: FastAPI vs Django vs Flask decision tree, async vs sync, Pydantic validation, project structure principles, error handling, testing with pytest-asyncio.

### 5.2 clean-code
- **Description**: Pragmatic coding standards — concise, direct, no over-engineering.
- **Key topics**: SRP, DRY, KISS, YAGNI, Boy Scout rule, naming conventions, function rules (max 20 lines, max 3 args), guard clauses, self-check verification.

### 5.3 testing-patterns
- **Description**: Testing patterns and principles. Unit, integration, mocking strategies.
- **Key topics**: Testing pyramid, AAA pattern, test type selection, mocking principles (stub/spy/mock/fake), test organization, test data strategies.

### 5.4 systematic-debugging
- **Description**: 4-phase systematic debugging methodology with root cause analysis.
- **Key topics**: Phase 1 Reproduce, Phase 2 Isolate, Phase 3 Understand (5 Whys), Phase 4 Fix & Verify, debugging checklist, anti-patterns.

### 5.5 performance-profiling
- **Description**: Performance profiling principles. Measurement, analysis, and optimization.
- **Key topics**: Core Web Vitals (LCP/INP/CLS), 4-step profiling workflow, bundle analysis, runtime profiling, memory analysis, quick win priorities.

### 5.6 quant-research
- **Description**: Factor/alpha research for OMEGA_QUANT Vietnam equity quant pipeline.
- **Key topics**: Alpha lifecycle, IC/IR metrics (Spearman rank IC), turnover/cost control (27bps round-trip), capacity analysis, neutralization hierarchy, 4-regime model, genetic programming alpha, ensemble methods.

### 5.7 vietnam-market-data
- **Description**: Vietnam equity market data principles for OMEGA_QUANT.
- **Key topics**: HOSE/HNX/UPCOM exchanges, VCI data provider, VND_FULL price scale (multiply by 1000), ticker lifecycle, survivorship bias prevention, ICB Level-2 sector mapping, canonical parquet schema.

### 5.8 backtesting-pit-safety
- **Description**: Backtesting integrity and Point-In-Time (PIT) safety for OMEGA_QUANT.
- **Key topics**: PIT rules (T-1 lag mandatory, as_of <= available_at), survivorship-free protocol, walk-forward validation (12+ OOS folds), CPCV (N=10, k=2, 45 folds), corporate action handling at available_at, transaction cost model (27bps round-trip).

### 5.9 data-science-workflow
- **Description**: Data science workflow for OMEGA_QUANT research standards.
- **Key topics**: EDA protocol (8 steps), data quality assessment (6 dimensions), statistical tests (Spearman, ADF, KS, bootstrap), experiment tracking (MLflow), reproducibility protocol, analysis reporting standards, common statistical pitfalls.

---

## 6. Forbidden Path Compliance Verification

### Previous Failure (L3 Audit)
The prior L2 report failed the L3 audit because the forbidden paths section:
1. Used aliases (e.g., "Antigravity scratch", "OpenClaw") instead of exact paths.
2. Omitted `.codex\memories` and `.codex/memories` entirely.

### Fix Applied in This Report
This report enumerates all 8 exact forbidden paths with both backslash and forward-slash variants. Every line and sentence that references any of these paths includes at least one of the required enforcer keywords: **"forbidden path"**, **"non-authoritative"**, or **"not used as source"**.

### Enforcer Keyword Coverage

| Forbidden Path | "forbidden path" | "non-authoritative" | "not used as source" |
|---------------|-----------------|---------------------|---------------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `.gemini/antigravity-ide/scratch/ag-kit` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `.openclaw\skills` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `.openclaw/skills` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `C:\Users\GHC\.agents` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `C:/Users/GHC/.agents` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `.codex\memories` | YES (table + notes) | YES (table + notes) | YES (table + notes) |
| `.codex/memories` | YES (table + notes) | YES (table + notes) | YES (table + notes) |

---

## 7. Gate Reference

| Gate | Status |
|------|--------|
| `GP_EXPANSION_ALTERNATIVE_REGIMES_20260617` | L2 implementation complete — forbidden paths table fixed, all 8 paths enumerated with enforcer keywords, all 9 skills documented, all 10 repo-local files cataloged |

---

## 8. SOD Boundary Acknowledgment

This L2 report is **implementation-only**. The data-scientist (Role 14, Tier 2) does NOT:
- Audit or approve its own work
- Promote alpha signals to live trading
- Approve backtest results for deployment

All work products must be submitted to Tier 3 for audit:
- **Code Reviewer (Role 21)**: Code quality and reproducibility review
- **QA Engineer (Role 17)**: Model validation and testing review

---

## 9. Conclusion

- **Forbidden paths table**: All 8 exact forbidden paths listed with backslash and forward-slash variants. Every mention tagged with "forbidden path", "non-authoritative", and/or "not used as source".
- **Skills**: All 9 required skills from `data-scientist.md` frontmatter documented and loaded from authoritative repo-local source (`.agents\skills\`).
- **Repo-local files**: 10 files read (1 agent + 9 skills), all within `REPO_ROOT`.
- **No forbidden path content used**: Zero files read from any forbidden path location.
- **Gate**: `GP_EXPANSION_ALTERNATIVE_REGIMES_20260617` — L2 report written, ready for Tier 3 audit.

**Status**: READY_FOR_TIER3_AUDIT
