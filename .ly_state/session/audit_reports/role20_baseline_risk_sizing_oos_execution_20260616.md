# Compliance Audit Report

**Role**: Compliance Officer (Role 20, Tier 3, Codex)
**Date**: 2026-06-16
**Gate**: BASELINE_RISK_SIZING_OOS_EXECUTION_20260616
**L2 Session**: l2_role14_baseline_risk_sizing_oos_execution_20260616
**L2 Role**: 14 data-scientist (Tier 2, OpenCode)
**L3 Session**: l3_role20_baseline_risk_sizing_oos_execution_20260616

---

## 1. Writer != Auditor Verification

- L2 role_id: **14** (data-scientist)
- L3 role_id: **20** (compliance-officer)
- 14 != 20: **PASS** - Writer and auditor are separated.

## 2. Scope Compliance

L2 session executed 12-fold dynamic OOS backtests for 3 risk/sizing overlay variants.
No source code changes were made - execution only. Artifacts produced:

| Artifact | Path | Exists |
|----------|------|--------|
| IVOL JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_ivol_20260616_baseline.json` | YES |
| CONF JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_conf_20260616_baseline.json` | YES |
| BOTH JSON | `data/phase35_results/phase35_backtest_results_risk_sizing_both_20260616_baseline.json` | YES |
| L2 Report | `.ly_state/session/l2_role14_baseline_risk_sizing_oos_execution_20260616.md` | YES |
| Execution Report | `.ly_state/session/baseline_risk_sizing_oos_execution_report_20260616.md` | YES |

Scope compliance: **PASS** - all artifacts within approved scope.

## 3. OOS Metric Verification (12-Fold Dynamic)

### 3a. JSON Summary vs L2 Report Cross-Check

| Metric | L2 Report (IVOL) | JSON Actual | Match |
|--------|------------------|-------------|-------|
| Portfolio IC | 0.0291 | 0.02906 | YES (rounded) |
| Sharpe | 3.9845 | 3.9845 | YES |
| MaxDD | -11.92% | -11.92% | YES |
| Avg PnL | 822M VND | 822,021,832 | YES |
| Folds | 12 | 12/12 | YES |

| Metric | L2 Report (CONF) | JSON Actual | Match |
|--------|------------------|-------------|-------|
| Portfolio IC | 0.0151 | 0.01507 | YES (rounded) |
| Sharpe | 3.0673 | 3.0673 | YES |
| MaxDD | -11.77% | -11.77% | YES |
| Avg PnL | 632M VND | 632,191,405 | YES |
| Folds | 12 | 12/12 | YES |

| Metric | L2 Report (BOTH) | JSON Actual | Match |
|--------|------------------|-------------|-------|
| Portfolio IC | 0.0280 | 0.02804 | YES (rounded) |
| Sharpe | 3.3736 | 3.3736 | YES |
| MaxDD | -12.39% | -12.39% | YES |
| Avg PnL | 732M VND | 731,893,443 | YES |
| Folds | 12 | 12/12 | YES |

All 3 variant summaries match JSON source data exactly (within rounding). **PASS**.

### 3b. Strict Promotion Gate Verification

Baseline reference: IC 0.0249, Sharpe 3.1106, MaxDD -12.25%, PnL 616M.

| Variant | Sharpe > BL | PnL > BL | MaxDD > BL | IC > BL | All 4 | Gate |
|---------|-------------|----------|------------|---------|-------|------|
| Inverse-Vol | 3.9845 > 3.1106 PASS | 822M > 616M PASS | -11.92% > -12.25% PASS | 0.0291 > 0.0249 PASS | YES | **PASS** |
| Confidence | 3.0673 < 3.1106 FAIL | 632M > 616M PASS | -11.77% > -12.25% PASS | 0.0151 < 0.0249 FAIL | NO | FAIL |
| Both | 3.3736 > 3.1106 PASS | 732M > 616M PASS | -12.39% < -12.25% FAIL | 0.0280 > 0.0249 PASS | NO | FAIL |

**Inverse-Vol ONLY passes all strict promotion criteria. Confidence and Both FAIL.** **PASS**.

### 3c. Per-Fold Verification (Inverse-Vol)

12 folds confirmed in JSON fold_details. Per-fold IC, Sharpe, MaxDD, PnL values verified
against L2 execution report Section 5 - all match within floating-point precision.
10/12 folds positive PnL; 2 negative (Folds 4, 8 in bear regimes). No catastrophic loss.

## 4. PIT Safety Verification

Each fold in all 3 variant JSONs contains `risk_sizing_evidence` with:

| Check | IVOL | CONF | BOTH |
|-------|------|------|------|
| `pit_safe` | True | True | True |
| `no_current_bar_use` | True | True | True |
| `no_oos_label_use` | True | True | True |
| Trailing data only | Confirmed (inverse_vol_window=20, trailing) | Confirmed (confidence_window=60, trailing) | Confirmed (both windows trailing) |

IVOL config: `inverse_vol_sizing=True, confidence_scaling=False, inverse_vol_window=20`
CONF config: `inverse_vol_sizing=False, confidence_scaling=True, confidence_window=60`
BOTH config: `inverse_vol_sizing=True, confidence_scaling=True`

No forward returns, no OOS labels, no current-bar leakage detected. **PASS**.

## 5. SOD Boundary Compliance

- L2 (role 14, data-scientist) executed backtests and wrote reports only - no self-approval.
- L2 explicitly states "No self-approval. Tier 3 audit required."
- No source code changes in this session (execution-only).
- L3 (role 20, compliance-officer) performs read-only audit.
- L3 writes only to `.ly_state/session/audit_reports/` and updates `phase_gates.json`.
- No cross-platform violations detected.

SOD boundary: **PASS**.

## 6. L2 Repo-Local Skill Source Evidence

L2 report `.ly_state/session/l2_role14_baseline_risk_sizing_oos_execution_20260616.md` contains:
- "Files Read - Repo-Local Skill Source Evidence" section with table listing 10 repo-relative paths
- Agent definition: `.agents/agent/data-scientist.md`
- Skills: `.agents/skills/python-patterns/SKILL.md`, `.agents/skills/clean-code/SKILL.md`,
  `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/systematic-debugging/SKILL.md`,
  `.agents/skills/performance-profiling/SKILL.md`, `.agents/skills/quant-research/SKILL.md`,
  `.agents/skills/vietnam-market-data/SKILL.md`, `.agents/skills/backtesting-pit-safety/SKILL.md`,
  `.agents/skills/data-science-workflow/SKILL.md`
- Forbidden path scan: no authoritative reliance on forbidden paths.
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

L2 repo-local skill source evidence: **PASS**.

## 7. L3 Repo-Local Skill Source Evidence

Files read by this L3 audit (compliance-officer, role 20):

| File | Repo-Relative Path |
|------|-------------------|
| Agent definition | `.agents/agent/compliance-officer.md` |
| audit-cycle | `.agents/skills/audit-cycle/SKILL.md` |
| vulnerability-scanner | `.agents/skills/vulnerability-scanner/SKILL.md` |
| code-review-checklist | `.agents/skills/code-review-checklist/SKILL.md` |
| omega-sod | `.agents/skills/omega-sod/SKILL.md` |
| sops | `.agents/skills/sops/SKILL.md` |

Forbidden path scan: no authoritative reliance on forbidden paths.
`.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
`.openclaw\skills` is non-authoritative and not used as source.
`C:\Users\GHC\.agents` is non-authoritative and not used as source.
`.codex\memories` is non-authoritative and not used as source.

## 8. Audit Summary

| Check | Result |
|-------|--------|
| Writer != Auditor (14 != 20) | PASS |
| Scope compliance | PASS |
| 12-fold OOS execution (all 3 variants) | PASS |
| IVOL strict promotion gate | PASS |
| CONF strict promotion gate | FAIL (as expected) |
| BOTH strict promotion gate | FAIL (as expected) |
| JSON vs L2 report metric match | PASS |
| PIT safety (all variants) | PASS |
| No OOS label leakage | PASS |
| No current-bar leakage | PASS |
| SOD boundary compliance | PASS |
| L2 repo-local skill source evidence | PASS |
| L2 forbidden path scan | PASS |
| L3 repo-local skill source evidence | PASS |
| L3 forbidden path scan | PASS |

No blockers found. All checks pass.

## Verdict

[APPROVED]

All 3 risk/sizing variants executed 12-fold OOS successfully. Inverse-vol variant passes
all strict promotion criteria (IC 0.0291 > 0.0249, Sharpe 3.9845 > 3.1106, MaxDD -11.92% >
-12.25%, PnL 822M > 616M). Confidence-only and Both variants correctly identified as FAIL.
PIT safety verified in all fold-level evidence. SOD boundaries respected. L2 report contains
complete repo-local skill source evidence with forbidden path scan. No blockers.

