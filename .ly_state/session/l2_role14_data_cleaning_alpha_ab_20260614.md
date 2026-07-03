# L2 Data-Cleaning A/B Diagnostic Report — Phase 35 Alpha Recovery

**Date**: 2026-06-14
**Gate**: DATA_CLEANING_ALPHA_AB_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Verdict**: `RESEARCH_ONLY — DO_NOT_PROMOTE`
**Default behavior**: UNCHANGED

---

## 0. Provenance and Compliance

### Repo-Local Files Read

| Type | Repo-Relative Path |
|------|-------------------|
| Role definition | `.agents/agent/data-scientist.md` |
| Skill: quant-research | `.agents/skills/quant-research/SKILL.md` |
| Skill: data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |
| Skill: backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| Validation report (clean) | `.ly_state/session/cpcv12_formulaic_v3_clean_stat_validation_report_20260614.md` |
| Validation report (clean+WG) | `.ly_state/session/cpcv12_v3_winner_guard_clean_stat_validation_report_20260614.md` |
| Backtest JSON (clean) | `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v3_clean_xgboost.json` |
| Backtest JSON (clean+WG) | `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_clean_xgboost.json` |
| Backtest JSON (full, prior) | `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v3_full_xgboost.json` |

### Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source
- `.openclaw\skills` is non-authoritative and not used as source
- `C:\Users\GHC\.agents` is non-authoritative and not used as source
- `.codex\memories` is non-authoritative and not used as source

**Result**: No authoritative reliance on any forbidden path. All source material is repo-local under `REPO_ROOT`.

### Pre-Fix Semantics Caveat

No `cpcv12_v3_winner_guard_baseline` file was found or explicitly marked with pre-fix semantics in the scoped inputs. The prior comparator (`cpcv12_formulaic_v3_full`) uses the original full-data pipeline with `research_pool_mode: "full"` and no `formulaic_winner_guard` config field (default `false`). Cross-variant comparison is valid for directional assessment only; absolute metric levels may differ due to both data-cleaning and config differences.

---

## 1. Objective

Evaluate whether research-only data cleaning (outlier/edge-case handling) applied to the CPCV-12 formulaic v3 backtest pipeline produces measurable improvement in portfolio IC, Sharpe, and alpha-level signal quality. Additionally assess the interaction between data cleaning and the formulaic winner-guard selection mechanism.

---

## 2. A/B Variant Definitions

| Label | Config Tag | Data Cleaning | Winner Guard | Research Pool |
|-------|-----------|---------------|-------------|---------------|
| **A: Full (prior)** | `cpcv12_formulaic_v3_full` | No | No | full |
| **B: Clean** | `cpcv12_formulaic_v3_clean` | Yes | No | full |
| **C: Clean + WG** | `cpcv12_v3_winner_guard_clean` | Yes | Yes | full |

All variants: CPCV-12 folds, 3yr train / 1yr test, XGBoost ranker, 30 symbols, 5-day horizon, initial capital 1B VND, 30bps total cost (10bps slippage + 20bps commission).

---

## 3. Portfolio-Level Metrics Comparison

| Metric | A: Full (prior) | B: Clean | C: Clean+WG | B vs A Delta | C vs B Delta |
|--------|-----------------|----------|-------------|-------------|-------------|
| **Avg Portfolio IC** | -0.0028 | 0.0105 | 0.0157 | +0.0133 | +0.0052 |
| **Avg Portfolio Sharpe** | 1.577 | 1.983 | 1.899 | +0.406 | -0.083 |
| **Avg Max Drawdown** | -0.6995 | -0.6725 | -0.6866 | +0.027 | -0.014 |
| **Avg PnL (VND)** | 857M | 907M | 818M | +50M | -89M |
| **Positive IC Rate** | N/A (report scope) | 58.3% (7/12) | 66.7% (8/12) | — | +8.4% |
| **Positive Sharpe Rate** | N/A | 58.3% (7/12) | 58.3% (7/12) | — | 0.0% |
| **Fallback Frequency** | N/A | 0.0% | 0.0% | — | 0.0% |

### Key Observations

1. **Data cleaning (B vs A)**: Portfolio IC improved from -0.0028 to +0.0105 (+0.013). Sharpe improved +0.41. Drawdown reduced by 2.7pp. PnL improved by 50M VND.
2. **Winner guard on clean (C vs B)**: Portfolio IC further improved from 0.0105 to 0.0157 (+0.005). However, Sharpe slightly decreased (-0.08) and PnL decreased (-89M VND), suggesting the guard's alpha substitution alters risk/return profile without clear net benefit.
3. **Positive IC rate**: Clean+WG achieves 66.7% vs 58.3% for clean-only — the guard improves IC consistency across folds.

---

## 4. Alpha-Level IC Comparison

Per-alpha mean OOS IC is identical between B and C (the guard operates at selection time, not on per-alpha IC computation). All 12 alphas remain below the 0.02 IC gate:

| Alpha | Mean IC (B=C) | Assessment |
|-------|--------------|------------|
| close_auction_drift_10 | 0.0197 | BELOW GATE (< 0.02) — closest to threshold |
| tick_signed_volume_imbalance_5 | 0.0112 | BELOW GATE |
| alpha_fml006_vp_corr_10 | 0.0045 | BELOW GATE |
| alpha_fml067_vol_price_diverge_10 | 0.0044 | BELOW GATE |
| alpha_fml012_mean_rev_rank_10 | -0.0009 | MARGINAL (negative mean) |
| alpha_fml045_liq_turnover_5 | -0.0007 | MARGINAL (negative mean) |
| micro_momentum_5_20 | -0.0037 | MARGINAL (negative mean) |
| alpha_fml052_close_zscore_mr_20 | -0.0122 | MARGINAL (negative mean) |
| liquidity_provision_ratio_10 | -0.0131 | MARGINAL (negative mean) |
| kyle_lambda_20 | -0.0132 | MARGINAL (negative mean) |
| volume_clock_acceleration_10 | -0.0137 | MARGINAL (negative mean) |
| volatility_compression_5 | -0.0283 | WEAK — RETIRE candidate |

**Critical finding**: No alpha in any variant achieves mean IC >= 0.02. The entire alpha pool fails the quant-research promotion gate.

---

## 5. Statistical Validation Gates

| Metric | B: Clean | C: Clean+WG | Gate |
|--------|----------|-------------|------|
| **ICIR** | 0.3469 (MARGINAL) | 0.5067 (STRONG) | Min 0.5: B fails, C passes |
| **DSR** | 0.1366 | 0.1206 | Min 0.0: both pass |
| **PBO** | 0.3333 | 0.3333 | Max 0.5: both pass |
| **CPCV-ready** | YES (12 folds) | YES (12 folds) | >= 10 folds: both pass |
| **Stat Validation Verdict** | FAIL | FAIL | Weak alpha blocker |

Both variants fail overall statistical validation due to the **weak alpha blocker**: all 12 individual alphas have mean IC below 0.02 and all receive RETIRE verdict under BH-FDR corrected research gates (q-values range 0.32–0.97, none significant at FDR=0.05).

---

## 6. Recovery Pool Evidence (from Validation Reports)

| Recovery Class | B: Clean | C: Clean+WG |
|---------------|----------|-------------|
| RECOVERABLE | 5 alphas | 4 alphas |
| RESEARCH_ONLY | 4 alphas | 5 alphas |
| CONFIRMED_RETIRE | 3 alphas | 3 alphas |

Recovery pool A/B (full vs recovery-only) shows:
- **Recovery-only pool mean IC**: 0.0010 (vs full pool -0.0038) — improves signal quality
- **Recovery-only positive fold rate**: 58.3% (vs full pool 25.0%) — substantial improvement

However, even the recovery-only pool mean IC (0.0010) is far below the 0.02 gate.

---

## 7. Winner Guard Mechanism Analysis (C variant only)

The formulaic winner guard (`formulaic_winner_guard: true`) restricts alpha selection to a formulaic-only allowlist (5 alphas: `fml006`, `fml012`, `fml045`, `fml052`, `fml067`). Per-fold evidence shows:

- **Fallback usage**: 4 of 12 folds used fallback (folds 1, 2, 5, 7) — the guard excluded all pre-guard candidates due to negative validation IC, forcing fallback to allowlist members.
- **PIT-safe**: All 12 folds confirm `pit_safe: true`.
- **Net effect**: Guard improves Portfolio IC (0.0157 vs 0.0105) and positive IC rate (66.7% vs 58.3%), but at the cost of slightly lower Sharpe and PnL. The guard prevents selection of strong non-formulaic alphas (e.g., `close_auction_drift_10` with IC 0.0197) that happen to be the best performers.

---

## 8. Verdict and Rationale

### `RESEARCH_ONLY — DO_NOT_PROMOTE`

**Blockers** (all must clear for promotion):

1. **Weak alpha pool**: All 12 alphas have mean IC < 0.02 across all variants. Zero alphas pass the quant-research IC gate. This is the primary blocker.
2. **Research gate verdict**: All 12 alphas receive RETIRE under BH-FDR corrected statistical testing (q-values all > 0.05).
3. **Statistical validation**: Both clean variants return FAIL due to weak alpha blocker.
4. **ICIR below promotion threshold** for the clean-only variant (0.3469 < 0.5).

**Positive signals** (noted but insufficient for promotion):

- Data cleaning improves portfolio IC by +0.013 (from negative to positive).
- Winner guard on clean data further improves IC to 0.0157 and achieves ICIR 0.5067.
- Recovery-only pool outperforms full pool (mean IC +0.005, positive fold rate +33pp).
- DSR and PBO gates pass for both clean variants.

**Conclusion**: While data cleaning produces a measurable directional improvement in portfolio-level metrics, the underlying alpha pool lacks sufficient individual alpha strength (mean IC < 0.02) for promotion. The improvement is necessary but not sufficient. No production source changes are warranted.

---

## 9. Default Behavior

- **`research_pool_mode`**: `"full"` (unchanged across all variants).
- **`formulaic_winner_guard`**: `false` by default (only enabled in C variant config).
- **No production code paths are affected** by this diagnostic.
- **No config defaults are changed**.

---

## 10. Recommendations (Research-Only)

1. **Data cleaning**: The +0.013 portfolio IC improvement suggests data cleaning is beneficial. Recommend incorporating into future research pipelines for evaluation, but NOT as a production default change at this time.
2. **Alpha pool augmentation**: The fundamental blocker is weak individual alpha IC. Priority should be new alpha discovery or feature engineering to produce alphas with mean IC >= 0.02.
3. **`volatility_compression_5`**: Consistently worst performer (mean IC -0.028). Confirm retirement from all active pools.
4. **`close_auction_drift_10`**: Best performer (mean IC 0.0197, closest to gate). Monitor for potential future promotion if IC strengthens.
5. **Winner guard interaction**: The guard improves IC consistency but excludes the strongest non-formulaic alphas. Consider an expanded allowlist that includes `close_auction_drift_10` and `tick_signed_volume_imbalance_5` in future research iterations.

---

## 11. SOD / Audit Trail

- **Author**: Role 14 (data-scientist), L2 implementation only
- **No self-approval**: This report is research documentation, not a promotion request
- **Tier 3 submission**: Required before any production consideration
- **No production source changes made**
- **Reproducibility**: All metrics sourced from persisted JSON backtest results and validation reports in `.ly_state/session/` and `data/phase35_results/`

---

*Report generated 2026-06-14. L2 implementation only — submit to Tier 3 audit before any production consideration.*
