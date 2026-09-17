# L2 Implementation Report: Portfolio-Level Validation Guard

**GATE:** RISK_ADJUSTED_PORTFOLIO_GUARD_20260614
**ROLE:** 16 (Machine Learning Engineer) — Tier 2
**DATE:** 2026-06-14
**STATUS:** IMPLEMENTATION COMPLETE — SUBMIT TO TIER 3

---

## 1. Context & Failure Mode

Static risk-adjusted presets passed code audit but failed A/B backtesting:

| Variant | IC | Sharpe | MaxDD | Verdict |
|---------|------|--------|-------|---------|
| baseline | 0.0115 | 0.8905 | -7.51% | PASS |
| ic_first_guarded | -0.0073 | 0.5785 | -6.52% | FAIL |

**Root cause:** Per-alpha selection can pass individual quality checks but the portfolio/basket outcome is negative. The guard addresses this by validating the *combined basket* on validation data before accepting the risk-adjusted selection.

## 2. Scope & Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added `PortfolioGuardResult` dataclass, `compute_basket_validation_ic()`, `evaluate_portfolio_guard()`, `DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE` |
| `src/omega/quant/alpha/phase35.py` | Added `portfolio_guard_enabled` and `portfolio_guard_tolerance` constructor params; integrated guard in single-horizon and multi-horizon paths; added `portfolio_guard_evidence` to `FoldMetrics` |
| `tests/test_risk_adjusted_alpha_score.py` | Added 20 new tests across 8 test classes for portfolio guard |

## 3. Implementation Summary

### 3.1 New Dataclass: `PortfolioGuardResult`

Fields:
- `portfolio_guard_enabled` (bool) — always True when executed
- `portfolio_guard_status` (str) — `"ACCEPTED"` or `"FALLBACK_TO_BASELINE"`
- `selected_basket_validation_ic` (float) — Spearman IC of risk-adjusted basket on validation data
- `baseline_basket_validation_ic` (Optional[float]) — Spearman IC of baseline basket
- `guard_reason` (str) — human-readable decision explanation
- `selected_alphas` (List[str]) — effective basket after guard decision
- `rejected_risk_adjusted_evidence` (Optional[dict]) — rejected RA evidence on fallback

### 3.2 Function: `compute_basket_validation_ic()`

Computes basket-level validation IC for a set of alpha columns:
1. Builds IC-weighted combined signal using train_ics as weights
2. Z-score normalizes per date cross-sectionally
3. Computes Spearman IC between basket signal and forward returns on validation data
4. PIT-safe: only validation data used; no test future

### 3.3 Function: `evaluate_portfolio_guard()`

Decision logic:
1. If RA selection has no alphas → FALLBACK
2. Compute selected basket validation IC
3. If selected IC <= 0 → FALLBACK (non-positive predictive power)
4. If baseline available and `baseline_IC - selected_IC > tolerance` → FALLBACK (underperformance)
5. Otherwise → ACCEPTED

### 3.4 Integration in phase35.py

**Single-horizon path:**
- Before RA selection, computes baseline alphas (standard IC-based selection)
- After RA selection, if `portfolio_guard_enabled`, calls `evaluate_portfolio_guard()`
- On FALLBACK: replaces `top_alphas` with baseline, clears `ra_result`
- Guard evidence persisted in `FoldMetrics.portfolio_guard_evidence`

**Multi-horizon path (`_compute_horizon_signal()`):**
- Same pattern per horizon
- Guard evidence propagated through `gate_metadata['portfolio_guard_evidence']`
- Extracted at FoldMetrics construction for multi-horizon reporting

### 3.5 Constraints Preserved

- Opt-in default disabled (`portfolio_guard_enabled=False`)
- No live trading/execution changes (paper-trading-only boundary)
- PIT-safe: no test future data used
- No changes to baseline path when guard is disabled

## 4. Test Results

```
120 passed, 3 warnings in 7.58s
```

### New Test Classes (20 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestComputeBasketValidationIC` | 6 | Positive IC, negative IC, empty inputs, missing columns |
| `TestEvaluatePortfolioGuardAccept` | 2 | Accept with positive IC (no baseline, with baseline) |
| `TestEvaluatePortfolioGuardNegativeIC` | 2 | Fallback on negative/zero selected IC |
| `TestEvaluatePortfolioGuardUnderperform` | 2 | Fallback on underperform baseline; no fallback within tolerance |
| `TestEvaluatePortfolioGuardNoSelected` | 1 | Fallback when RA selection empty |
| `TestPortfolioGuardEvidenceFields` | 3 | All fields present (ACCEPTED, FALLBACK, JSON-serializable) |
| `TestPortfolioGuardDefaultTolerance` | 1 | Tolerance constant sensible |
| `TestPortfolioGuardResultDataclass` | 2 | Default values, to_dict roundtrip |

## 5. Evidence Contract

When the guard is enabled and risk-adjusted selection is active, each fold persists:

```json
{
  "portfolio_guard_enabled": true,
  "portfolio_guard_status": "ACCEPTED|FALLBACK_TO_BASELINE",
  "selected_basket_validation_ic": 0.0123,
  "baseline_basket_validation_ic": 0.0098,
  "guard_reason": "Selected basket IC=0.0123 > 0, baseline IC=0.0098, within tolerance=0.005",
  "selected_alphas": ["alpha_a", "alpha_b"],
  "rejected_risk_adjusted_evidence": null
}
```

On FALLBACK, `rejected_risk_adjusted_evidence` contains the full RA selection result for audit.

## 6. Forbidden Path Scan

`.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## 7. Repo-Local Source Files Read

- `.agents\agent\machine-learning-engineer.md` — role definition, frontmatter parsed (role_id=16, tier=2, skills=[python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data])
- `.agents\skills\python-patterns\SKILL.md`
- `.agents\skills\clean-code\SKILL.md`
- `.agents\skills\testing-patterns\SKILL.md`
- `.agents\skills\performance-profiling\SKILL.md`
- `.agents\skills\systematic-debugging\SKILL.md`
- `.agents\skills\ml-dl-rl\SKILL.md`
- `.agents\skills\backtesting-pit-safety\SKILL.md`
- `.agents\skills\vietnam-market-data\SKILL.md`

## 8. SOD Boundary

- Implementation-only (Tier 2)
- Tests required and passing (120/120)
- No self-approval — submit to Tier 3 (Code Reviewer role 21, QA Engineer role 17)
- No live trading/execution changes made
