# L2 Role 14 — Recovery Selector Opt-In Implementation Report

**Gate**: RECOVERY_SELECTOR_OPT_IN_20260614
**Role**: 14 (data-scientist) — L2 implementation only, no self-approval
**Date**: 2026-06-14
**Status**: Implementation complete, submitted to Tier 3 audit

---

## 1. Source Files Read

### Repo-Local Role/Skill Files (Authoritative)

| File | Path | Status |
|------|------|--------|
| Role definition | `.agents/agent/data-scientist.md` | READ |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` | READ |
| clean-code | `.agents/skills/clean-code/SKILL.md` | READ |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | READ |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | READ |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | READ |
| quant-research | `.agents/skills/quant-research/SKILL.md` | READ |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | READ |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | READ |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | READ |

### Forbidden Path Scan Result

| Path | Scan Result |
|------|------------|
| `.gemini/antigravity-ide/scratch/ag-kit` | Forbidden-path scan: no repo-local files found. `.gemini\\antigravity-ide\\scratch\\ag-kit` is non-authoritative and not used as source. |
| `.openclaw/skills` | Forbidden-path scan: no repo-local files found. `.openclaw\\skills` is non-authoritative and not used as source. |
| `C:\Users\GHC\.agents` | Forbidden-path scan: outside repo boundary. `C:\Users\GHC\.agents` is non-authoritative and not used as source. |
| `.codex/memories` | Forbidden-path scan: no repo-local files found. `.codex\\memories` is non-authoritative and not used as source. |

---

## 2. Scope Files

| File | Status |
|------|--------|
| `src/omega/quant/walk_forward/alpha_selector.py` | MODIFIED |
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | MODIFIED |
| `scripts/analyze_alpha_weakness.py` | MODIFIED |
| `tests/test_risk_adjusted_alpha_score.py` | MODIFIED |
| `tests/test_analyze_alpha_weakness.py` | MODIFIED |
| `.ly_state/session/recovery_selector_ready_report_20260614.md` | GENERATED |

---

## 3. Implementation Summary

### 3.1 `risk_adjusted_alpha_score.py` — Helper Functions

Added at module level (before `_NEUTRAL_SCORE`):

- **Constants**: `RESEARCH_POOL_FULL`, `RESEARCH_POOL_RECOVERY_ONLY`, `RESEARCH_POOL_RECOVERABLE_ONLY`, `VALID_RESEARCH_POOL_MODES`
- **Selector verdict constants**: `SELECTOR_VERDICT_DO_NOT_PROMOTE`, `SELECTOR_VERDICT_CONDITIONAL_PROMOTE`, `SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE`
- **`filter_alphas_by_recovery_mode(alpha_cols, recovery_report, mode)`**: Pure function that filters alpha list by recovery classification. PIT-safe (uses only OOS-derived classifications). Raises `ValueError` on invalid mode.
- **`compute_selector_ready_verdict(full_ic, full_rate, rec_ic, rec_rate)`**: Computes selector verdict from pool A/B metrics. DO_NOT_PROMOTE when IC improved but fold rate did not.

### 3.2 `alpha_selector.py` — Opt-In Selector Mode

Added import of new constants and `filter_alphas_by_recovery_mode`.

Added method `filter_recovery_pool(alpha_cols, recovery_report, research_pool_mode='full')` to `AlphaSelectionMixin`:
- Default `research_pool_mode='full'` — no filtering, backward-compatible.
- `'recovery_only'` — excludes CONFIRMED_RETIRE alphas.
- `'recoverable_only'` — keeps only RECOVERABLE alphas.
- Empty pool fallback: logs warning, returns original list. Fallback remains failure.

### 3.3 `analyze_alpha_weakness.py` — Selector-Ready Report

- Added `enable_selector_ready` parameter to `generate_report()`.
- Added `--selector-ready` CLI flag (default False).
- New section "Selector-Ready Report (Opt-In)" with:
  - Pool A/B metrics table (mean IC, positive fold rate, pool size)
  - Selector verdict (`DO_NOT_PROMOTE`, `CONDITIONAL_PROMOTE`, `INSUFFICIENT_EVIDENCE`)
  - Recommendations section with pool mode guidance
  - DO_NOT_PROMOTE blocker text when recovery-only pool improves mean IC but not positive fold rate
  - No live trading note

### 3.4 A/B Finding Codified

The A/B showed recovery-only pool improves mean IC but NOT positive fold rate:
- **All 3 variants** (baseline, ra_guard, ra_no_guard) received `DO_NOT_PROMOTE` verdict
- Recovery-only pool mean IC: 0.0010 vs full pool: -0.0062 (improved)
- Recovery-only pool positive fold rate: 37.5% vs full pool: 50.0% (NOT improved)

---

## 4. Test Results

### Pytest Summary

```
tests/test_risk_adjusted_alpha_score.py tests/test_analyze_alpha_weakness.py
290 passed
```

### New Test Classes

| Test Class | File | Tests | Coverage |
|-----------|------|-------|----------|
| `TestRecoveryPoolModeConstants` | `test_risk_adjusted_alpha_score.py` | 5 | Constants defined correctly |
| `TestFilterAlphasByRecoveryMode` | `test_risk_adjusted_alpha_score.py` | 8 | Full/recovery_only/recoverable_only modes, edge cases |
| `TestComputeSelectorReadyVerdict` | `test_risk_adjusted_alpha_score.py` | 7 | All verdict paths, custom thresholds |
| `TestSelectorReadyReportOptIn` | `test_analyze_alpha_weakness.py` | 12 | Report sections, CLI flags, backward compat |

### Script Execution

```
python scripts/analyze_alpha_weakness.py \
    --input-dir data/phase35_results/ab_guard_20260614_101727 \
    --output .ly_state/session/recovery_selector_ready_report_20260614.md \
    --research-gates --recovery-diagnostics --recovery-pool-ab --selector-ready
```

Report generated successfully with DO_NOT_PROMOTE verdict across all variants.

---

## 5. Safety Constraints

| Constraint | Status |
|-----------|--------|
| Default `research_pool_mode='full'` unchanged | PASS |
| Opt-in only — no production behavior change | PASS |
| PIT safety — no look-ahead | PASS (uses only OOS-derived classifications) |
| Fallback remains failure | PASS (empty pool warns, returns original) |
| No live/default production behavior changes | PASS |

---

## 6. Tier 3 Audit Submission

**Submitted to:**
- Code Reviewer (role 21): Code quality and reproducibility review
- QA Engineer (role 17): Model validation and testing review

**Cannot proceed until:** All relevant Tier 3 roles return [APPROVED]

---

*Report generated by Role 14 (data-scientist). L2 implementation only — no self-approval.*
