# L2 Session Report: Hybrid Backtest Postmortem — Architecture Review (FIX 1)

**Role:** 6 (System Architect)
**Tier:** 2
**Gate:** HYBRID_BACKTEST_POSTMORTEM_20260619
**Date:** 2026-06-20 (fix revision)
**Original Date:** 2026-06-19
**Fix Reason:** L3 audit (role 21) returned [NEEDS_FIX] — original report omitted 2 of 6 declared repo-local skill sources (`database-design`, `nodejs-best-practices`)
**Status:** COMPLETE — Re-submitted for Tier 3 Audit

---

## 1. Compliance & Provenance

### 1.1 Repo-Local Files Read — Agent & Skills (COMPLETE)

**Agent definition:**

| File | Path (repo-relative) | Purpose |
|------|---------------------|---------|
| Agent definition | `.agents/agent/system-architect.md` | Role frontmatter + constraints (75 lines) |

**Declared skills (6/6 — all from frontmatter `skills:` field):**

| # | Skill | Path (repo-relative) | Lines | Key Content |
|---|-------|---------------------|-------|-------------|
| 1 | `architecture` | `.agents/skills/architecture/SKILL.md` | 56 | ADR framework, trade-off analysis, context-discovery, pattern-selection, validation checklist |
| 2 | `api-patterns` | `.agents/skills/api-patterns/SKILL.md` | 82 | REST/GraphQL/tRPC decision tree, response formats, versioning, auth, rate-limiting, security-testing |
| 3 | `database-design` | `.agents/skills/database-design/SKILL.md` | 53 | Schema design, indexing, ORM selection, migration safety, query optimization |
| 4 | `clean-code` | `.agents/skills/clean-code/SKILL.md` | 202 | SRP/DRY/KISS/YAGNI, naming rules, function rules, guard clauses, mandatory self-check |
| 5 | `plan-writing` | `.agents/skills/plan-writing/SKILL.md` | 152 | Task breakdown principles, verification criteria, dynamic naming, plan structure |
| 6 | `nodejs-best-practices` | `.agents/skills/nodejs-best-practices/SKILL.md` | 335 | Framework selection, async patterns, layered architecture, error handling, security, testing |

**Skill directory supplemental files confirmed present:**

| Skill | Supplemental Files |
|-------|-------------------|
| `architecture` | `context-discovery.md`, `examples.md`, `pattern-selection.md`, `patterns-reference.md`, `trade-off-analysis.md` |
| `api-patterns` | `api-style.md`, `auth.md`, `documentation.md`, `graphql.md`, `rate-limiting.md`, `response.md`, `rest.md`, `security-testing.md`, `trpc.md`, `versioning.md`, `scripts/` |
| `database-design` | `database-selection.md`, `indexing.md`, `migrations.md`, `optimization.md`, `orm-selection.md`, `schema-design.md`, `scripts/` |
| `clean-code` | (SKILL.md only) |
| `plan-writing` | (SKILL.md only) |
| `nodejs-best-practices` | (SKILL.md only) |

**FIX 1 DELTA:** Skills #3 (`database-design`) and #6 (`nodejs-best-practices`) were missing from the original 2026-06-19 report. Both are now confirmed present and loaded from repo-local paths.

### 1.2 Repo-Local Files Read — Source Code

| File | Path (repo-relative) | Purpose |
|------|---------------------|---------|
| Pipeline V2 | `src/omega/quant/pipeline_v2.py` | Main orchestrator (544 lines) |
| Overlay base | `src/omega/quant/pipeline/overlays/base.py` | WeightOverlay interface |
| Overlay registry | `src/omega/quant/pipeline/overlays/__init__.py` | All overlay exports |
| TailControl overlay | `src/omega/quant/pipeline/overlays/tail_control.py` | Tail control wrapper (35 lines) |
| DrawdownControl overlay | `src/omega/quant/pipeline/overlays/drawdown_control.py` | DD stop-out + BOCPD (297 lines) |
| RiskSizing overlay | `src/omega/quant/pipeline/overlays/risk_sizing.py` | Risk sizing (312 lines) |
| SectorConcentration overlay | `src/omega/quant/pipeline/overlays/sector_concentration.py` | Sector caps (130 lines) |
| BoardLotRounding overlay | `src/omega/quant/pipeline/overlays/board_lot_rounding.py` | Lot rounding (102 lines) |
| WeightSmoothing overlay | `src/omega/quant/pipeline/overlays/weight_smoothing.py` | EMA smoothing (23 lines) |
| Tail controls (core) | `src/omega/quant/portfolio/tail_controls.py` | apply_tail_controls (169 lines) |
| Backtest script | `scripts/backtest_hybrid_regime.py` | Comparative backtest (239 lines) |

### 1.3 Forbidden Path Scan

| Forbidden Path | Exists on Disk? | Accessed This Session? | Result |
|---------------|----------------|----------------------|--------|
| `C:\Users\GHC\.agents\` | YES (contains `skills/`) | NO | **PASS** — not accessed |
| Antigravity scratch | NO (does not exist in repo) | NO | **PASS** |
| OpenClaw | NO (does not exist in repo) | NO | **PASS** |
| Codex memory (`C:\Users\GHC\.agents\Codex`) | NO (does not exist) | NO | **PASS** |
| `scratch/` (repo-local) | YES (10 entries, utility scripts) | NO | **PASS** — not accessed |

**All skills and role definitions loaded exclusively from repo-local `.agents/` directory. No forbidden paths were accessed. No external agent memory sources were consulted.**

### 1.4 Agent Frontmatter Parsed

```yaml
name: system-architect
description: System design/interface definition
role_id: 6
tier: 2
platform: OpenCode
skills: [architecture, api-patterns, database-design, clean-code, plan-writing, nodejs-best-practices]
sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"
```

**Declared skill count:** 6
**Skill files confirmed present and loaded:** 6/6
**Missing skill files:** 0 — No STOP/NEEDS_FIX condition.

---

## 2. Source File Availability Check

| File | Required? | Present? | Status |
|------|-----------|----------|--------|
| `src/omega/quant/pipeline_v2.py` | YES | YES | PASS |
| `src/omega/quant/pipeline/overlays/` (all) | YES | YES (18 files) | PASS |
| `scripts/backtest_hybrid_regime.py` | YES | YES | PASS |
| `src/omega/quant/portfolio/tail_controls.py` | YES | YES | PASS |
| `.agents/agent/system-architect.md` | YES | YES | PASS |
| `.agents/skills/architecture/SKILL.md` | YES | YES | PASS |
| `.agents/skills/api-patterns/SKILL.md` | YES | YES | PASS |
| `.agents/skills/database-design/SKILL.md` | YES | YES | PASS |
| `.agents/skills/clean-code/SKILL.md` | YES | YES | PASS |
| `.agents/skills/plan-writing/SKILL.md` | YES | YES | PASS |
| `.agents/skills/nodejs-best-practices/SKILL.md` | YES | YES | PASS |

**No STOP/NEEDS_FIX conditions triggered. All required repo-local sources present.**

---

## 3. Architectural Findings

> **Preserved from original 2026-06-19 report. No contradictions found during fix revision.**

### 3.1 Turnover Root Cause Confirmed

**Location:** `pipeline_v2.py:477-486`

```python
pivot_sig = panel.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
demedian = pivot_sig.subtract(pivot_sig.median(axis=1), axis=0)
pos = np.sign(demedian)  # <-- ROOT CAUSE: binary +/-1
weights_long = (pos > 0).astype(float).div(longs, axis=0)
weights_short = -(pos < 0).astype(float).div(shorts, axis=0)
weights = weights_long + weights_short
```

Any signal crossing the median by any epsilon triggers a full long-to-short or short-to-long flip. With 10 stocks and daily signal noise, this produces 132-143% daily turnover.

### 3.2 TailControlOverlay Parameter Gap

**Location:** `tail_control.py:13-14` vs `tail_controls.py:73-85`

`TailControlOverlay.__init__` does not accept `max_leverage`, `lookback`, or `periods_per_year`. These parameters exist in the underlying `apply_tail_controls()` function but are never passed through. The overlay hard-codes the function defaults.

### 3.3 Redundant DD Mechanisms

Two independent drawdown control mechanisms exist:
1. `TailControlOverlay` -> `apply_tail_controls()` internal trip-and-hold DD breaker (`tail_controls.py:143-153`)
2. `DrawdownControlOverlay` — full stateful stop-out with BOCPD gating

Both are active simultaneously in the backtest scenarios, creating potential double-cutting.

### 3.4 WeightSmoothingOverlay Exists But Unused

`WeightSmoothingOverlay` (EMA smoothing, `weight_smoothing.py`) is registered in the overlay registry but NOT included in either backtest scenario in `scripts/backtest_hybrid_regime.py`. This is a ready-made turnover reduction tool.

---

## 4. Design Deliverables

### 4.1 ADR Document

**Written to:** `docs/ADR_TURNOVER_REDUCTION_20260619.md`

Contains:
- Full problem context with metrics from prior L2 sessions
- 4 architectural decisions with interface contracts:
  1. `rebalance_throttle` — minimum weight change threshold
  2. `rebalance_frequency` — calendar-based rebalance filtering (daily/weekly/monthly)
  3. `TailControlOverlay.max_leverage` — parameter passthrough
  4. Overlay ordering evaluation (validated current ordering as correct)
- Implementation priority matrix (P0-P2)
- Risk assessment
- Consequences analysis

### 4.2 Interface Contracts Summary

| Design | Insertion Point | Parameters | PIT Safety |
|--------|----------------|------------|------------|
| `rebalance_throttle` | `pipeline_v2.py` post-overlay (after L495) | `throttle: float = 0.02` | Uses `state["last_weights"]` (T-1) only |
| `rebalance_frequency` | `pipeline_v2.py` post-overlay (after L495) | `frequency: str = "weekly"`, `day_of_week: int = 0` | Calendar-based (inherently PIT-safe) |
| `max_leverage` passthrough | `tail_control.py` constructor | `max_leverage: float = 3.0` | No PIT impact (parameter only) |

### 4.3 Overlay Ordering Verdict

**Current ordering is CORRECT:** RiskSizing -> Sector -> TailControl -> DrawdownControl -> BoardLot

Rationale:
- Smooth risk controls (vol-targeting) before hard emergency brakes (stop-out)
- Prevents vol-targeting from re-leveraging during DD cooldown
- Board lot rounding must always be last

---

## 5. Recommended Implementation Sequence

```
Phase 1 (P0 -- immediate):
+-- Fix weight construction: signal-proportional instead of np.sign
+-- Add rebalance_throttle to TradingPipelineV2
+-- Add WeightSmoothingOverlay to backtest scenarios

Phase 2 (P1 -- next sprint):
+-- Add rebalance_frequency (weekly) to TradingPipelineV2
+-- Expose max_leverage on TailControlOverlay
+-- Expose lookback + periods_per_year on TailControlOverlay

Phase 3 (P2 -- cleanup):
+-- Add dd_enabled flag to TailControlOverlay to disable internal DD
+-- Run A/B backtest: baseline vs throttle vs weekly vs combined
+-- Submit to Tier 3 audit
```

---

## 6. SoD Compliance

| Constraint | Compliant? |
|-----------|------------|
| Implementation-only (no production code changes) | YES — only design docs + ADR |
| Test required | N/A — no code written |
| No self-approval | YES — submitted to Tier 3 |
| Submit to Tier 3 (Architecture Auditor, Security Auditor) | PENDING |

**EXPLICIT STATEMENT: Role 6 remained strictly design-only throughout this session. No production code was written, modified, or committed. All outputs are documentation artifacts (ADR + session reports) pending Tier 3 audit approval.**

---

## 7. Outputs Produced

| Artifact | Path | Status |
|----------|------|--------|
| ADR Document | `docs/ADR_TURNOVER_REDUCTION_20260619.md` | WRITTEN (unchanged) |
| L2 Session Report (original) | `.ly_state/session/l2_role6_hybrid_backtest_postmortem_arch_20260619.md` | WRITTEN (superseded) |
| L2 Session Report (FIX 1) | `.ly_state/session/l2_role6_hybrid_backtest_postmortem_arch_fix1_20260620.md` | WRITTEN (this file) |

---

## 8. Fix Revision Summary

| Item | Original (2026-06-19) | FIX 1 (2026-06-20) |
|------|----------------------|-------------------|
| Skills listed in provenance | 4 of 6 | **6 of 6** |
| `database-design` skill loaded | NO | **YES** — `.agents/skills/database-design/SKILL.md` (53 lines) |
| `nodejs-best-practices` skill loaded | NO | **YES** — `.agents/skills/nodejs-best-practices/SKILL.md` (335 lines) |
| Forbidden path scan | PASS | **PASS** (re-verified with explicit disk existence checks) |
| Architectural findings | 4 findings | **Unchanged** (no contradictions) |
| ADR document | `docs/ADR_TURNOVER_REDUCTION_20260619.md` | **Unchanged** |
| Role 6 design-only statement | Implied | **Explicitly stated** |

---

## 9. Tier 3 Submission

Submitted to:
- [ ] Role 20 (Architecture Auditor) — Architectural soundness review
- [ ] Role 18 (Security Auditor) — Security architecture review
- [ ] Role 23 (Performance Tester) — Scalability and performance review

**Cannot proceed to implementation until all relevant Tier 3 roles return [APPROVED].**

---

*End of L2 Session Report (FIX 1) — Role 6 System Architect*
