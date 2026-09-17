# L2 Session Report: Hybrid Backtest Postmortem — Architecture Review

**Role:** 6 (System Architect)
**Tier:** 2
**Gate:** HYBRID_BACKTEST_POSTMORTEM_20260619
**Date:** 2026-06-19
**Status:** COMPLETE — Submitted for Tier 3 Audit

---

## 1. Compliance & Provenance

### 1.1 Repo-Local Files Read

| File | Path (repo-relative) | Purpose |
|------|---------------------|---------|
| Agent definition | `.agents/agent/system-architect.md` | Role frontmatter + constraints |
| Skill: architecture | `.agents/skills/architecture/SKILL.md` | ADR framework |
| Skill: api-patterns | `.agents/skills/api-patterns/SKILL.md` | Interface design patterns |
| Skill: plan-writing | `.agents/skills/plan-writing/SKILL.md` | Task planning framework |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` | Code quality standards |
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

### 1.2 Forbidden Path Scan

| Forbidden Path | Scanned? | Found? | Result |
|---------------|----------|--------|--------|
| `C:\Users\GHC\.agents\` | YES | NO | PASS |
| Antigravity scratch | YES | NO | PASS |
| OpenClaw | YES | NO | PASS |
| Codex memory | YES | NO | PASS |

**All skills and role definitions loaded exclusively from repo-local `.agents/` directory.**

### 1.3 Agent Frontmatter Parsed

```yaml
name: system-architect
role_id: 6
tier: 2
platform: OpenCode
skills: [architecture, api-patterns, database-design, clean-code, plan-writing, nodejs-best-practices]
sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"
```

---

## 2. Source File Availability Check

| File | Required? | Present? | Status |
|------|-----------|----------|--------|
| `src/omega/quant/pipeline_v2.py` | YES | YES | PASS |
| `src/omega/quant/pipeline/overlays/` (all) | YES | YES (18 files) | PASS |
| `scripts/backtest_hybrid_regime.py` | YES | YES | PASS |
| `src/omega/quant/portfolio/tail_controls.py` | YES | YES | PASS |

**No STOP/NEEDS_FIX conditions triggered. All required repo-local sources present.**

---

## 3. Architectural Findings

### 3.1 Turnover Root Cause Confirmed

**Location:** `pipeline_v2.py:477-486`

```python
pivot_sig = panel.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
demedian = pivot_sig.subtract(pivot_sig.median(axis=1), axis=0)
pos = np.sign(demedian)  # <-- ROOT CAUSE: binary ±1
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
1. `TailControlOverlay` → `apply_tail_controls()` internal trip-and-hold DD breaker (`tail_controls.py:143-153`)
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

**Current ordering is CORRECT:** RiskSizing → Sector → TailControl → DrawdownControl → BoardLot

Rationale:
- Smooth risk controls (vol-targeting) before hard emergency brakes (stop-out)
- Prevents vol-targeting from re-leveraging during DD cooldown
- Board lot rounding must always be last

---

## 5. Recommended Implementation Sequence

```
Phase 1 (P0 — immediate):
├── Fix weight construction: signal-proportional instead of np.sign
├── Add rebalance_throttle to TradingPipelineV2
└── Add WeightSmoothingOverlay to backtest scenarios

Phase 2 (P1 — next sprint):
├── Add rebalance_frequency (weekly) to TradingPipelineV2
├── Expose max_leverage on TailControlOverlay
└── Expose lookback + periods_per_year on TailControlOverlay

Phase 3 (P2 — cleanup):
├── Add dd_enabled flag to TailControlOverlay to disable internal DD
├── Run A/B backtest: baseline vs throttle vs weekly vs combined
└── Submit to Tier 3 audit
```

---

## 6. SoD Compliance

| Constraint | Compliant? |
|-----------|------------|
| Implementation-only (no production code changes) | YES — only design docs + ADR |
| Test required | N/A — no code written |
| No self-approval | YES — submitted to Tier 3 |
| Submit to Tier 3 (Architecture Auditor, Security Auditor) | PENDING |

---

## 7. Outputs Produced

| Artifact | Path | Status |
|----------|------|--------|
| ADR Document | `docs/ADR_TURNOVER_REDUCTION_20260619.md` | WRITTEN |
| L2 Session Report | `.ly_state/session/l2_role6_hybrid_backtest_postmortem_arch_20260619.md` | WRITTEN (this file) |

---

## 8. Tier 3 Submission

Submitted to:
- [ ] Role 20 (Architecture Auditor) — Architectural soundness review
- [ ] Role 18 (Security Auditor) — Security architecture review
- [ ] Role 23 (Performance Tester) — Scalability and performance review

**Cannot proceed to implementation until all relevant Tier 3 roles return [APPROVED].**

---

*End of L2 Session Report — Role 6 System Architect*
