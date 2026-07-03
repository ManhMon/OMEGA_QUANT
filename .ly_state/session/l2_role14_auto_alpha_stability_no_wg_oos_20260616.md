# L2 Role 14 — Auto Alpha Stability Filter (No Winner Guard) OOS Experiment

**GATE**: `AUTO_ALPHA_STABILITY_NO_WINNER_GUARD_OOS_20260616`
**Role**: 14 (Data Scientist, Tier 2, OpenCode)
**Date**: 2026-06-16
**Status**: RESEARCH ONLY — no promotion

---

## Files Read - Repo-Local Skill Source Evidence

All skills loaded from authoritative repo-local paths:

| File | Path |
|------|------|
| Role definition | `.agents/agent/data-scientist.md` |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

All 10 files read from `REPO_AGENT_ROOT` / `REPO_SKILL_ROOT` only. No external skill sources used.

no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

---

## Context

Previous gate `AUTO_ALPHA_OOS_STABILITY_FILTER_20260616` was approved but was a **no-op** because the formulaic winner guard (`FORMULAIC_WINNER_SELECTION_GUARD_20260614`) blocked all `auto_*` alphas before they could reach the stability filter. The stability filter never evaluated any auto alphas — every fold reported `note: "no_bundle_alphas_in_candidates"`.

This experiment tests: what happens when the stability filter actually gets to evaluate auto alphas by disabling the winner guard?

---

## Experiment Configuration

| Parameter | Value |
|-----------|-------|
| Script | `scripts/run_phase35_backtest.py` |
| Folds | 12 (all executed) |
| Train window | 3 years |
| Test window | 1 year |
| Top N symbols | 30 (dynamic universe) |
| Dynamic universe | ENABLED (lookback=252d, rebalance=21d, top_n=30) |
| Automated OOS bundle | ENABLED (`auto_top5_real_ic_20260615`) |
| OOS stability filter | ENABLED (min_icir=0.15, min_sign_consistency=0.55, decay_penalty_factor=1.0) |
| Formulaic winner guard | **DISABLED** |
| Auto winner guard allowlist | DISABLED (not needed without WG) |
| Formulaic alphas | ENABLED (v3_pruned, 5 alphas) |
| XGBoost | DISABLED |
| Drawdown control | ENABLED (threshold=10%) |
| Data cleaning | ENABLED (expanding_zscore normalization) |
| Source changes | NONE — existing code used as-is |

---

## Results Summary

| Metric | This Experiment | Dynamic Baseline | Delta |
|--------|----------------|-----------------|-------|
| **Portfolio IC** | 0.0145 | 0.025 | -0.010 (worse) |
| **Sharpe** | 3.024 | 3.111 | -0.087 (worse) |
| **Max DD** | -11.65% | -12.25% | +0.60% (slightly better) |
| **PnL (VND)** | 612.3M | 616.0M | -3.7M (slightly worse) |

---

## Per-Fold Stability Filter Evidence

All 12 folds verified:
- `enabled=True`
- `pit_safe=True`
- `no_oos_label_use=True`
- `fallback_used=False`

From run logs — auto alpha pass/exclude counts per fold:

| Fold | Auto Alphas Reaching Filter | Passed | Excluded |
|------|---------------------------|--------|----------|
| 1 | 2 (auto_mr_zscore_20, auto_rsi_14) | 2 | 0 |
| 2 | 3 (auto_rsi_14, auto_mom_ret_60, auto_mr_zscore_20) | 3 | 0 |
| 3 | 3 (auto_rsi_14, auto_mom_ret_60, auto_mr_zscore_20) | 3 | 0 |
| 4 | 2 (auto_rsi_14, auto_vol_std_ratio_10_30) | 2 | 0 |
| 5 | 1 (auto_rsi_14) | 1 | 0 |
| 6 | 3 (auto_mr_zscore_20, auto_rsi_14, auto_mom_ret_60) | 3 | 0 |
| 7 | 2 (auto_mom_ret_20, auto_rsi_14) | 2 | 0 |
| 8 | 2 (auto_mom_ret_20, auto_mom_ret_60) | 2 | 0 |
| 9 | 3 (auto_mom_ret_60, auto_rsi_14, auto_mom_ret_20) | 3 | 0 |
| 10 | 3 (auto_rsi_14, auto_mr_zscore_20, auto_mom_ret_20) | 3 | 0 |
| 11 | 2 (auto_mr_zscore_20, auto_rsi_14) | 2 | 0 |
| 12 | 3 (auto_mom_ret_60, auto_vol_std_ratio_10_30, auto_rsi_14) | 3 | 0 |
| **Total** | **29 auto candidates reached filter** | **29 passed** | **0 excluded** |

**Key finding**: The stability filter passes ALL auto alphas that reach it. Zero exclusions across all 12 folds.

---

## PIT Safety Verification

| Check | Result |
|-------|--------|
| `pit_safe` | True (all 12 folds) |
| `no_oos_label_use` | True (all 12 folds) |
| Winner guard evidence | Absent (correctly disabled) |
| Stability filter data source | `train_df` only (confirmed by source inspection + 28 unit tests) |
| Current-bar leakage | None (stability filter uses T-1 lagged features, confirmed by design) |
| Unit tests | 28/28 stability filter tests PASS |
| Integration tests | 33/33 auto alpha integration tests PASS |

---

## Comparison Matrix

| Experiment | IC | Sharpe | MaxDD | PnL (VND) | WG | Stability |
|-----------|-----|--------|-------|-----------|-----|-----------|
| Dynamic baseline | 0.025 | 3.111 | -12.25% | 616.0M | ON | OFF |
| Auto bundle + WG | 0.015 | 3.076 | -12.11% | 609.3M | ON | OFF |
| WG allowlist | ~0.000 | 2.278 | -12.09% | 444.7M | ON+auto | OFF |
| Stability + WG (no-op) | 0.015 | 3.076 | -12.11% | 609.3M | ON | ON (no-op) |
| **This: Stability, no WG** | **0.015** | **3.024** | **-11.65%** | **612.3M** | **OFF** | **ON (active)** |

---

## Analysis

1. **Stability filter is permissive**: The default thresholds (ICIR >= 0.15, sign consistency >= 0.55) pass all auto alphas. The auto bundle alphas have sufficient train-period IC stability to clear these gates.

2. **No winner guard = slightly worse IC**: Without the winner guard filtering out negative-IC formulaic alphas (like `alpha_fml052_close_zscore_mr_20`, `alpha_fml045_liq_turnover_5`, `alpha_fml067_vol_price_diverge_10`), these negative-IC candidates can enter the top-N selection, diluting the portfolio signal.

3. **Does NOT beat strict dynamic baseline**: IC 0.015 vs 0.025 baseline; Sharpe 3.02 vs 3.11 baseline.

4. **PIT-safe**: All evidence confirms no look-ahead, no OOS label use, no current-bar leakage.

---

## Verdict

**RESEARCH ONLY** — the stability filter without winner guard produces IC 0.015, Sharpe 3.02, which does NOT beat the strict dynamic baseline (IC 0.025, Sharpe 3.11). No promotion recommended.

**Submitted to Tier 3 for audit**: Code Reviewer (role 21), QA Engineer (role 17).

---

## Output Artifacts

| Artifact | Path |
|----------|------|
| JSON results | `data/phase35_results/phase35_backtest_results_auto_stability_no_wg_20260616_baseline.json` |
| TXT summary | `data/phase35_results/phase35_backtest_summary_auto_stability_no_wg_20260616_baseline.txt` |
| Session doc | `.ly_state/session/l2_role14_auto_alpha_stability_no_wg_oos_20260616.md` |
| Report | `.ly_state/session/auto_alpha_stability_no_wg_oos_report_20260616.md` |
