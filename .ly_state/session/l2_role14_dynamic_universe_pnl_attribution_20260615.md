# L2 Role 14 Analysis: Dynamic Universe PnL Attribution

**Gate:** `DYNAMIC_UNIVERSE_PNL_ATTRIBUTION_20260615`
**Role:** 14 data-scientist (Tier 2, OpenCode)
**Date:** 2026-06-15
**SOD boundary:** implementation-only, test required, no self-approval, submit to Tier 3
**Status:** COMPLETE — awaiting Tier 3 audit

---

## 1. Objective

Quantify PnL attribution, robustness, and regime dependence of the dynamic universe E2E backtest result (`phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json`), and recommend the next gate.

## 2. Scope & Constraints

- **Read-only analysis:** No production source code modified
- **Primary source:** Single JSON artifact from existing E2E run
- **Comparison sources:** Rolling universe and static CPCV12 baseline JSONs
- **Methodology:** Fold-level decomposition, concentration analysis, outlier impact, correlation analysis, winner guard pattern mining, dynamic universe evidence audit
- **Skill files used:** quant-research, backtesting-pit-safety, data-science-workflow (all repo-local under `.agents/skills/`)

## 3. Headline Metrics

| Metric | Dynamic Universe |
|--------|-----------------|
| Avg IC | 0.0249 |
| **Median IC** | **0.0167** |
| Avg Sharpe | 3.11 |
| **Median Sharpe** | **1.62** |
| Avg Max DD | -12.3% |
| Median Max DD | -12.3% |
| Total PnL (sum folds) | 7,392 B VND |
| Median PnL/fold | 234 M VND |
| Win Rate | 83% (10/12) |

**Mean vs Median divergence:** Mean Sharpe (3.11) is 1.9x the median (1.62), indicating positive skew driven by Fold 6 (Sharpe=15.75). **Median is the more reliable headline.**

## 4. Fold-Level PnL Concentration

| Metric | Value |
|--------|-------|
| Positive folds | 10/12 (83%) |
| Negative folds | 2/12 (F4: -7M, F8: -132M) |
| Top-1 fold share (positive) | 39.4% (Fold 6) |
| Top-3 fold share (positive) | 77.0% (F6 + F12 + F9) |
| Top-5 fold share (positive) | 89.8% |

**Concentration risk:** Top 3 folds account for 77% of positive PnL. All three correspond to strong VN-Index bull runs. Strategy is regime-dependent.

## 5. Fold 6 Outlier Deep Dive

| Metric | Fold 6 | Average (all 12) | Excluding F6 (11 folds) |
|--------|--------|-------------------|-------------------------|
| IC | 0.1096 | 0.0249 | 0.0172 |
| Sharpe | 15.75 | 3.11 | 1.96 |
| Return | +296.4% | +48.8% | +26.1% |
| Max DD | -10.9% | -12.3% | -12.4% |
| PnL | 2,964 B | 616 M | 403 M |
| Share of total | 40.1% | — | — |

**Period context:** Fold 6 tested 2021-05 to 2022-05, covering the VN-Index peak bull run (index hit 1500+). The extreme return is regime-specific, not alpha-driven.

**Impact assessment:** Excluding Fold 6, the strategy still produces:
- 4.4B VND total PnL
- Mean Sharpe of 1.96 (still strong)
- 9/11 positive folds (82% win rate)
- Median PnL drops only 11.3% (from 234M to 207M)

**Verdict:** Fold 6 is an outlier but the strategy does not collapse without it. The headline mean is misleading; median is representative.

## 6. IC/Sharpe/PnL Correlation Matrix

| Pair | Pearson r | Interpretation |
|------|-----------|----------------|
| IC ↔ PnL | +0.576 | Moderate — IC partially explains PnL |
| IC ↔ Sharpe | +0.688 | Strong — IC is a reasonable Sharpe predictor |
| Sharpe ↔ PnL | **+0.978** | Near-perfect — Sharpe dominates PnL |
| IC ↔ \|Max DD\| | -0.457 | Moderate — higher IC slightly reduces drawdowns |

**Critical observation:** Fold 12 has IC=-0.009 (negative) yet Sharpe=+6.24 and Return=+172.5%. This decoupling suggests the portfolio construction stage (Stage 2: top-15 stock selection + sector cap + drawdown control) generates alpha independently of cross-sectional signal ranking during trending markets.

## 7. Alpha Selection & Winner Guard Patterns

### Guard Mechanics
- Gate: `FORMULAIC_WINNER_SELECTION_GUARD_20260614`
- Allowlist: 5 formulaic alphas (fml052, fml012, fml045, fml067, fml006)
- Min validation IC threshold: 0.0
- Fallback to full allowlist when no pre-guard candidates pass

### Guard Behavior by Fold

| Fold | Pre-guard | Post-guard | Excluded | Fallback |
|------|-----------|------------|----------|----------|
| 1 | 5 | 2 | 5 | YES |
| 2 | 5 | 1 | 5 | YES |
| 3 | 5 | 2 | 3 | no |
| 4 | 5 | 1 | 4 | no |
| 5 | 2 | 5 | 2 | YES |
| 6 | 5 | 1 | 4 | no |
| 7 | 5 | 1 | 5 | YES |
| 8 | 5 | 1 | 4 | no |
| 9 | 5 | 1 | 4 | no |
| 10 | 5 | 3 | 2 | no |
| 11 | 5 | 2 | 3 | no |
| 12 | 5 | 1 | 4 | no |

### Post-Guard Alpha Durability

| Alpha | Frequency | Durability |
|-------|-----------|------------|
| fml052_close_zscore_mr_20 | 6/12 (50%) | Highest — mean-reversion |
| fml045_liq_turnover_5 | 5/12 (42%) | High — liquidity signal |
| fml006_vp_corr_10 | 4/12 (33%) | Moderate — vol-price corr |
| fml067_vol_price_diverge_10 | 4/12 (33%) | Moderate — divergence |
| fml012_mean_rev_rank_10 | 2/12 (17%) | Low — secondary mean-rev |

### Key Pattern
- **p34 microstructure alphas NEVER survive the guard** — all excluded in every fold
- Formulaic alphas dominate post-guard selection
- Fallback used in 33% of folds (early folds with weak validation IC)
- Guard is appropriately conservative: averages 3.5 exclusions per fold

## 8. Dynamic Universe Evidence

| Metric | Value |
|--------|-------|
| Total rebalance events | 127 |
| All PIT-safe | YES (selection_end < rebalance_date) |
| Universe size range | 7 - 29 symbols |
| Mean universe size | 21.6 symbols |
| Mean turnover per rebalance | 1.4% |
| Zero-turnover rebalances | 81% |
| Max single turnover | 15.4% |

The dynamic universe demonstrates excellent stability: low turnover, monotonic growth with market development, and full PIT safety across all 127 rebalance events.

## 9. Symbol/Date/Sector Contribution

**UNAVAILABLE.** The JSON does not contain:
- Per-symbol PnL contribution within folds
- Per-date return breakdown
- Per-sector attribution (ICB Level-2)

**Instrumentation recommendations:**
1. Add `per_symbol_pnl: [{symbol, pnl_vnd, weight, sector}]` to fold_details
2. Add `daily_returns: [{date, return_pct}]` to fold_details
3. Add `rebalance_positions: [{date, positions: [{symbol, weight, sector}]}]` to fold_details
4. Record `adv_participation_rate` per position at each rebalance

## 10. Robustness Scorecard

| Metric | Value | Pass/Fail |
|--------|-------|-----------|
| Median PnL > 0 | 234 M VND | PASS |
| Median Return > 0 | 23.4% | PASS |
| Median Sharpe > 0.5 | 1.62 | PASS |
| Median IC > 0.02 | 0.0167 | **MARGINAL** (below 0.02 threshold) |
| Win Rate > 50% | 83% | PASS |
| Positive IC Rate > 50% | 67% | PASS |
| Sharpe > 0 Rate > 50% | 83% | PASS |
| PnL Top-1 < 50% | 39.4% | PASS |
| PnL Top-3 < 75% | 77.0% | **FAIL** |
| Max DD > -25% | -12.3% median | PASS |
| Negative fold loss contained | -132 M max | PASS |
| Dynamic universe PIT-safe | 127/127 | PASS |

**Score: 10/12 PASS, 1 MARGINAL, 1 FAIL**

## 11. Dynamic vs Rolling vs Static Comparison

| Metric | Dynamic | Rolling | Static (WG) | Dynamic Edge |
|--------|---------|---------|-------------|-------------|
| Avg IC | 0.0249 | 0.0263 | 0.0029 | ~8.5x vs static |
| Avg Sharpe | 3.11 | 2.86 | 1.59 | ~2.0x vs static |
| Avg Max DD | -12.3% | -12.3% | -70.0% | ~5.7x tighter |
| Avg PnL (M) | 616 | 600 | 857* | *Static has uncontrolled DD |

Dynamic and rolling are near-equivalent. Both dramatically outperform static. The universe selection mechanism itself (not the specific algorithm) is the value driver.

## 12. Next Gate Recommendation

### Recommended: **Diversified Basket**

| Gate | Recommendation | Rationale |
|------|----------------|-----------|
| **Diversified Basket** | **PROCEED** | PnL concentration (77% in top 3 folds) motivates multi-strategy diversification. Median Sharpe 1.62 supports allocation across 2-3 uncorrelated strategy variants. |
| Alpha Generation | DEFER | p34 microstructure alphas consistently fail the winner guard. Formulaic alphas dominate. Need new alpha sources (sentiment, alternatives, longer-horizon factors) before this gate. |
| Capacity Stress | DEFER | No per-symbol PnL attribution exists. Cannot estimate ADV participation rates or max AUM without instrumenting position-level tracking. |

### Pre-conditions for Diversified Basket
1. Identify 1-2 uncorrelated strategy variants (e.g., momentum overlay, sector rotation)
2. Verify PIT safety of any new strategy components
3. Maintain dynamic universe selection for all variants
4. Ensure combined portfolio Max DD remains below -15%

### Pre-conditions for future Alpha Generation gate
1. Investigate why all p34 microstructure alphas fail winner guard
2. Evaluate alpha IC decay curves (T+1 through T+10)
3. Consider regime-conditional alpha selection
4. Add non-price-based alpha sources

### Pre-conditions for future Capacity Stress gate
1. Instrument per-symbol PnL and position weight tracking
2. Compute per-position ADV participation rate
3. Estimate max AUM at 10% ADV participation per name
4. Evaluate liquidity impact of 81% zero-turnover rebalances

## 13. Compliance & Audit Trail

### Files Read (Repo-Local Authoritative)

| File | Type |
|------|------|
| `.agents/agent/data-scientist.md` | Role definition |
| `.agents/skills/quant-research/SKILL.md` | Domain skill |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | Domain skill |
| `.agents/skills/data-science-workflow/SKILL.md` | Domain skill |
| `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` | Primary data source |
| `data/phase35_results/phase35_backtest_results_rolling_universe_best_config_20260615_baseline.json` | Comparison source |
| `data/phase35_results/phase35_backtest_summary_rolling_universe_best_config_20260615_baseline.txt` | Comparison source |
| `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_baseline.json` | Comparison source |

### Artifacts Produced

| Artifact | Location |
|----------|----------|
| PnL Attribution Report | `.ly_state/session/dynamic_universe_pnl_attribution_report_20260615.md` |
| L2 Analysis (this file) | `.ly_state/session/l2_role14_dynamic_universe_pnl_attribution_20260615.md` |
| Analysis Script | `.ly_state/session/pnl_attribution_analysis.py` |

### No Source Code Modified
This analysis is read-only. No production source files were created, modified, or deleted.

### Forbidden Path Scan
No authoritative reliance on external paths. `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source. `.openclaw\skills` is non-authoritative and not used as source. `C:\Users\GHC\.agents` is non-authoritative and not used as source. `.codex\memories` is non-authoritative and not used as source.

### SOD Compliance
- **No self-approval:** This analysis requires Tier 3 audit by Role 21 (Code Reviewer) and Role 17 (QA Engineer)
- **Evidence persisted:** All artifacts in `.ly_state/session/`
- **Reproducible:** Analysis script available at `.ly_state/session/pnl_attribution_analysis.py`
- **PIT-safe assessment:** All 12 fold results and 127 dynamic universe entries confirmed PIT-safe

---

*Generated by Role 14 data-scientist. Submit to Tier 3 for audit before any gate advancement.*
