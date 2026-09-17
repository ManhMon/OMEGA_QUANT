# Phase 35 Production Readiness Verdict

**Date:** 2026-06-13
**Author:** Role 16 (Machine Learning Engineer, L2)
**Gate:** REMAINING_FOLLOWUPS_COMPLETION_20260613
**Status:** EVIDENCE-BASED VERDICT — NOT AN APPROVAL

---

## Verdict: NOT_PRODUCTION_READY

---

## Evidence Summary

### 1. Phase35 Full Feature CPCV Metrics (45-fold)

Source: `.ly_state/session/phase3_5_1B.json`

| Metric | Value | Threshold | Pass? |
|--------|-------|-----------|-------|
| median_test_ic | +0.0050 | > 0.02 | NO |
| median_train_cv_ic | -0.0006 | > 0.01 | NO |
| median_fold_sr | +0.053 | > 0.30 | NO |
| dsr_sharpe | +0.051 | > 0.50 | NO |
| dsr_sr_ann | +0.806 | > 1.00 | NO |
| dsr (p-value proxy) | 4.96e-11 | significant | MARGINAL |
| skew | -2.76 | > -1.0 | NO (heavy left tail) |
| kurtosis | 52.64 | < 10 | NO (extreme fat tails) |
| **overall pass** | **false** | true | **NO** |

Multiple CPCV folds show negative test IC (folds 0-7 all negative).

### 2. Evolution Walk-Forward Metrics (Yearly, 2017-2026)

Source: `data/backtest/evolution_backtest_results.json`

| Year | Evo IC | Evo Sharpe | Evo MaxDD | Baseline IC | Baseline Sharpe | Winner |
|------|--------|------------|-----------|-------------|-----------------|--------|
| 2017 | -0.1122 | -2.82 | -71.1% | -0.0007 | +2.03 | BASELINE |
| 2018 | -0.0242 | +0.08 | -18.8% | +0.0176 | +0.92 | BASELINE |
| 2019 | +0.0282 | -0.09 | -14.0% | -0.0132 | +0.05 | TIE |
| 2020 | -0.0346 | -2.74 | -77.2% | +0.1001 | +1.40 | BASELINE |
| 2021 | -0.0202 | -0.35 | -43.3% | -0.0300 | +2.19 | BASELINE |
| 2022 | +0.0270 | -0.77 | -41.4% | +0.0076 | +0.07 | TIE |
| 2023 | +0.0025 | +1.49 | -18.3% | -0.0753 | +0.54 | EVOLUTION |
| 2024 | -0.0084 | -0.60 | -15.3% | -0.0757 | +1.39 | BASELINE |
| 2025 | -0.0219 | -0.17 | -34.8% | -0.0095 | +0.01 | TIE |
| 2026 | -0.1059 | -1.55 | -20.5% | -0.0674 | +1.61 | BASELINE |

**Averages:**
- Evolution IC mean: -0.027 (negative)
- Evolution Sharpe mean: -0.75 (negative)
- Evolution MaxDD mean: -35.5% (severe)
- Baseline Mom20 Sharpe mean: +1.02 (positive)

**Evolution wins only 1 of 10 years on Sharpe.**

### 3. Evolved-Only Metrics (Multiseed — no results yet)

No `multiseed_backtest_results.json` exists in `data/backtest/`. The multiseed script
has not yet completed a full run. The `--quick` smoke mode was added in this session
to enable bounded execution.

### 4. Full-Pipeline Metrics

No `full_pipeline` results exist in `data/backtest/`. The full-pipeline script depends on
upstream backtest scripts completing successfully.

### 5. PIT and Cost Comments

- **PIT Safety:** All features use T-1 shift per ticker. `_validate_chronological_split()`
  blocks random shuffles. Walk-forward split ensures train < test chronologically.
  PIT enforcement is defense-in-depth (generator + evaluator both apply lag).
- **Cost Model:** Commission 15bps + tax 10bps + slippage 2bps = ~27bps round-trip.
  Evolution results are NOT cost-adjusted in the existing JSON — gross metrics overstate
  performance.
- **Survivorship:** Point-in-time universe with delistings included.
- **Transaction Cost Impact:** Evolution turnover ranges 0.03-0.65, implying
  0.8-17.5 bps/day drag (significant at high turnover years).

### 6. L3 Audit History (Phase35)

- P10 multi-horizon blend: Required 5+ fix rounds across roles 14, 20, 21
- P10 is default-off (opt-in via `--multi-horizon-blend`)
- Quick-mode labeled "smoke-only" in run_phase35_backtest.py
- Gate tuning required compliance reaudits (role 20)
- Data cleaning (P11) required additional audit cycle

---

## Decision Rationale

| Factor | Status | Impact |
|--------|--------|--------|
| IC consistently near zero or negative | CRITICAL | No reliable alpha signal |
| Sharpe mostly negative across 10 years | CRITICAL | Strategy loses money risk-adjusted |
| Max drawdown up to -77% | CRITICAL | Unacceptable for any capital allocation |
| Baseline momentum outperforms 9/10 years | CRITICAL | Evolution adds no value vs simple baseline |
| CPCV 45-fold pass=false | CRITICAL | Statistical validation fails |
| Extreme kurtosis (52.6) and negative skew (-2.8) | HIGH | Tail risk unacceptable |
| No cost-adjusted results available | HIGH | True performance even worse |
| P10 multi-horizon default-off | MEDIUM | Advanced features not validated |

**Correct verdict per L4 default: NOT_PRODUCTION_READY**

Shadow-only would require at minimum:
- Positive OOS IC across majority of walk-forward folds
- Net-of-cost Sharpe > 0.5
- Max drawdown < 25%
- Evolution consistently beating baseline

None of these criteria are met.

---

## Recommendations

1. Do not deploy Phase35 to production or shadow trading
2. Continue research: improve GP feature set, increase training data, explore regime-conditional alphas
3. Run full-pipeline with cost-adjusted metrics to get ground truth
4. Re-evaluate after significant algorithmic improvements
5. Baseline momentum (Mom20) alone shows better risk-adjusted returns — consider as interim strategy

---

*This verdict is evidence-based. No forced approval. L2 Role 16 does not audit or approve its own work.*
*Submitted to Tier 3 (Performance Tester, Role 23) for independent verification.*
