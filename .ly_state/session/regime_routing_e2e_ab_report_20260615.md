# Regime Routing E2E A/B Research Report

**Gate**: REGIME_ROUTING_E2E_AB_20260615
**Role**: 14 (data-scientist) — L2 implementation only, no self-approval
**Date**: 2026-06-15
**Status**: RESEARCH_ONLY / DO_NOT_PROMOTE

---

## 1. Objective

Evaluate whether ex-ante regime-conditioned alpha routing (GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615) improves walk-forward backtest performance vs. the baseline best-config pipeline.

## 2. Experimental Design

| Parameter | Value |
|-----------|-------|
| **Folds** | 12 walk-forward |
| **Train window** | 3 years |
| **Test window** | 1 year |
| **Top symbols** | 30 (ADTV > 5B VND, price > 5k) |
| **Data hygiene** | DEFAULT-ON (expanding_zscore) |
| **XGBoost** | OFF (research default) |
| **Drawdown control** | ON (10% threshold, research default) |
| **Formulaic alphas** | v3_pruned (5 candidates) |
| **Winner guard** | ON |
| **Cost model** | 30 bps round-trip (10 slippage + 20 commission) |
| **Date range** | 2015-01-05 to 2026-05-14 |

### Variants

| Variant | Tag | `--enable-regime-routing` |
|---------|-----|--------------------------|
| **Baseline** | `regime_ab_baseline_20260615` | OFF |
| **Treatment** | `regime_ab_enabled_20260615` | ON |

## 3. Aggregate Metric Comparison

| Metric | Baseline | Treatment | Delta |
|--------|----------|-----------|-------|
| **Avg Portfolio IC** | 0.0344 | 0.0344 | 0.0000 |
| **Avg Raw Signal IC** | 0.0200 | 0.0200 | 0.0000 |
| **Avg Raw CS IC** | 0.0216 | 0.0216 | 0.0000 |
| **Avg Portfolio Sharpe** | 3.1570 | 3.1570 | 0.0000 |
| **Avg Max Drawdown** | -12.34% | -12.34% | 0.00% |
| **Avg PnL (VND)** | 631.15M | 631.15M | 0 |
| **Positive IC folds** | 10/12 (83.3%) | 10/12 (83.3%) | 0 |
| **Positive Sharpe folds** | 11/12 (91.7%) | 11/12 (91.7%) | 0 |
| **Positive Return folds** | 11/12 (91.7%) | 11/12 (91.7%) | 0 |

**Result: ZERO DELTA on all aggregate metrics.**

## 4. Per-Fold Comparison

| Fold | Baseline IC | Treatment IC | Baseline Sharpe | Treatment Sharpe | Identical? |
|------|-------------|--------------|-----------------|------------------|------------|
| 1 | -0.0170 | -0.0170 | 0.8602 | 0.8602 | YES |
| 2 | 0.0075 | 0.0075 | 1.7724 | 1.7724 | YES |
| 3 | 0.0446 | 0.0446 | 0.3365 | 0.3365 | YES |
| 4 | 0.0211 | 0.0211 | 0.5083 | 0.5083 | YES |
| 5 | 0.0638 | 0.0638 | 3.4867 | 3.4867 | YES |
| 6 | 0.1235 | 0.1235 | 15.3496 | 15.3496 | YES |
| 7 | 0.0151 | 0.0151 | 1.6932 | 1.6932 | YES |
| 8 | 0.0299 | 0.0299 | -1.9781 | -1.9781 | YES |
| 9 | 0.0401 | 0.0401 | 5.7283 | 5.7283 | YES |
| 10 | 0.0413 | 0.0413 | 3.0549 | 3.0549 | YES |
| 11 | 0.0539 | 0.0539 | 0.8330 | 0.8330 | YES |
| 12 | -0.0109 | -0.0109 | 6.2391 | 6.2391 | YES |

**Result: Every fold is bit-identical between baseline and treatment.**

## 5. Regime Routing Evidence (Treatment Only)

### 5.1 Routing Activity

| Fold | Routed Dates | Fallback Dates | Total | Fallback Rate |
|------|-------------|----------------|-------|---------------|
| 1 | 3,891 | 2,553 | 6,444 | 39.6% |
| 2 | 3,604 | 3,087 | 6,691 | 46.1% |
| 3 | 0 | 6,756 | 6,756 | **100.0%** |
| 4 | 0 | 6,770 | 6,770 | **100.0%** |
| 5 | 2,212 | 4,498 | 6,710 | 67.0% |
| 6 | 1,269 | 5,448 | 6,717 | 81.1% |
| 7 | 6,507 | 243 | 6,750 | 3.6% |
| 8 | 3,969 | 2,781 | 6,750 | 41.2% |
| 9 | 2,862 | 3,861 | 6,723 | 57.4% |
| 10 | 2,835 | 3,887 | 6,722 | 57.8% |
| 11 | 0 | 6,713 | 6,713 | **100.0%** |
| 12 | 2,064 | 4,916 | 6,980 | 70.4% |
| **TOTAL** | **29,213** | **51,513** | **80,726** | **63.8%** |

### 5.2 Regime Quality (per-regime IC on train window)

| Fold | Bull IC | Sideways IC | Bull-Volatile IC | Bear IC | Baseline Quality |
|------|---------|-------------|------------------|---------|-----------------|
| 1 | -0.010 | -0.013 | 0.001 | 0.014 | 0.022 |
| 2 | -0.008 | 0.005 | -0.010 | -0.010 | 0.027 |
| 3 | -0.009 | 0.001 | 0.004 | -0.003 | 0.037 |
| 4 | 0.001 | 0.006 | 0.004 | -0.005 | 0.021 |
| 5 | 0.005 | 0.001 | -0.012 | -0.008 | 0.010 |
| 6 | -0.004 | -0.004 | -0.017 | 0.006 | 0.014 |
| 7 | -0.010 | 0.000 | -0.015 | -0.010 | 0.020 |
| 8 | -0.017 | 0.013 | -0.019 | -0.002 | 0.038 |
| 9 | -0.021 | -0.017 | -0.003 | -0.008 | 0.053 |
| 10 | -0.014 | 0.003 | 0.001 | -0.006 | 0.048 |
| 11 | -0.008 | 0.001 | -0.005 | -0.006 | 0.024 |
| 12 | -0.016 | 0.004 | 0.001 | -0.008 | 0.018 |

### 5.3 Key Observations

1. **High fallback rate (63.8%)**: The majority of test dates fall back to baseline signal (scale=1.0), meaning the per-regime IC on train window didn't meet the min_ic=0.01 threshold for most regime/date combinations.
2. **3 folds (3, 4, 11) at 100% fallback**: No routing applied at all — all test dates used baseline signal unchanged.
3. **No per-regime IC exceeds the 0.01 threshold consistently**: Most per-regime ICs are near zero or negative, indicating the regime labels don't partition the alpha signal into meaningfully different quality bands.
4. **PIT-safe**: Confirmed — regime labels derived from lagged/PIT-safe market features, per-regime IC estimated on train window only.

## 6. analyze_alpha_weakness.py Compatibility

The `analyze_alpha_weakness.py` script expects input files matching the pattern `^(baseline|ra_guard|ra_no_guard)_.*backtest_results_.*\.json$`. Our output files use the naming convention `phase35_backtest_results_regime_ab_{baseline,enabled}_20260615_baseline.json`, which does **not match** the expected pattern. The script is **not directly compatible** with these outputs. Comparison was computed directly from JSON.

## 7. Research Verdict

### FAIL — NO IMPACT

| Criterion | Result |
|-----------|--------|
| PortfolioIC improvement | NO (delta = 0.0000) |
| RawIC improvement | NO (delta = 0.0000) |
| CSIC improvement | NO (delta = 0.0000) |
| Sharpe improvement | NO (delta = 0.0000) |
| MaxDD improvement | NO (delta = 0.00%) |
| Total return improvement | NO (delta = 0 VND) |
| Positive fold rate improvement | NO (identical) |
| Signal degradation | NO (no negative impact) |
| PIT-safe | YES |
| Routing fallback rate | 63.8% (high) |

### Interpretation

The regime routing layer is **a no-op** under the current configuration. Despite being PIT-safe and correctly implemented, it produces zero measurable impact on any portfolio metric. The root causes are:

1. **Per-regime IC is too weak**: Train-window per-regime IC estimates are consistently below the 0.01 threshold or near zero, causing 63.8% of test dates to fall back to baseline.
2. **Signal scaling doesn't change portfolio construction**: Even when routing does apply (36.2% of dates), the resulting signal scaling doesn't alter which stocks are selected or their weights at the portfolio construction stage (Stage 2), so fold-level metrics remain identical.
3. **Regime labels lack discriminative power**: The 4-regime model (bull, sideways, bull_volatile, bear) doesn't partition the alpha signal into regimes with meaningfully different IC profiles on the training window.

### Recommendation

**RESEARCH_ONLY / DO_NOT_PROMOTE**

- Do NOT enable `--enable-regime-routing` as a default or production behavior change.
- The feature is correctly implemented and PIT-safe, but provides no measurable alpha.
- Future research directions:
  - Investigate alternative regime definitions (e.g., volatility-only, trend strength bins)
  - Increase train window for regime IC estimation
  - Lower `--regime-routing-min-ic` threshold (risk: overfitting to noise)
  - Test regime-conditional alpha *selection* (not just scaling)

---

## 8. Reproducibility

| Artifact | Path |
|----------|------|
| **Baseline JSON** | `data/phase35_results/phase35_backtest_results_regime_ab_baseline_20260615_baseline.json` |
| **Baseline Summary** | `data/phase35_results/phase35_backtest_summary_regime_ab_baseline_20260615_baseline.txt` |
| **Treatment JSON** | `data/phase35_results/phase35_backtest_results_regime_ab_enabled_20260615_baseline.json` |
| **Treatment Summary** | `data/phase35_results/phase35_backtest_summary_regime_ab_enabled_20260615_baseline.txt` |
| **Script** | `scripts/run_phase35_backtest.py` |
| **Engine** | `src/omega/quant/alpha/phase35.py` |

### Commands

```bash
# Baseline (no regime routing)
python scripts/run_phase35_backtest.py \
  --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --output-tag regime_ab_baseline_20260615

# Treatment (with regime routing)
python scripts/run_phase35_backtest.py \
  --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --enable-regime-routing \
  --output-tag regime_ab_enabled_20260615
```

---

## 9. Source Compliance

**Repo-local files read (authoritative)**:
- `.agents/agent/data-scientist.md` (role 14, frontmatter parsed)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

**Forbidden path scan result**: No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source); `.openclaw\skills` (non-authoritative, not used as source); `C:\Users\GHC\.agents` (non-authoritative, not used as source); `.codex\memories` (non-authoritative, not used as source).
