# L3 Audit Report: Backtest Results Analysis
**Date**: 2026-05-29
**Auditor**: Role 21 - Code Reviewer (Codex L3)
**Session**: keen-coral (read all code + results, write failed due to tool bug)
**Scope**: `data/backtest/evolution_backtest_results.json` + `scripts/backtest_evolution.py`

---

## 1. Sharpe Ratio Realism (VN Market)

| Strategy | Avg Sharpe | Realistic? |
|:---------|:-----------|:-----------|
| Evolution | 0.85 | YES - within VN quant range (0.5-3.0 for top strategies) |
| Mom20 | 0.60 | YES - standard momentum baseline |
| InverseVol | 1.28 | YES - low-vol anomaly well-documented |
| MeanReversion | -0.53 | YES - contrarian underperforms in trending VN market |
| EqualWeight | 1.28 | YES - diversification benefit |

**Verdict**: Sharpe ratios are realistic. No suspiciously high values (>5.0 would indicate leakage).

## 2. Overfitting Evidence

| Indicator | Finding | Concern? |
|:----------|:--------|:---------|
| Train IC vs Test IC | Train IC ~0.04-0.07, Test IC varies -0.12 to +0.09 | MODERATE |
| Year-to-year variance | Sharpe swings from -2.43 to +3.53 | HIGH VARIANCE |
| 2018/2022 negative Sharpe | -1.00 and -1.53 | Regime sensitivity |
| GP convergence | IC plateaus early (gen 2-3) | Population diversity issue |

**Assessment**: Moderate overfitting risk. GP finds patterns that work in some regimes but not others. The high variance (std of Sharpe ~2.0) suggests the evolved alphas are not robust across all market conditions.

**Recommendation**: Use in ensemble (weight 20-30%), not standalone.

## 3. PIT Safety

| Check | Status |
|:------|:-------|
| T-1 lag on all features | PASS - `df.groupby("ticker")[col].shift(1)` |
| Chronological split | PASS - train on year < Y, test on Y |
| No future data in target | PASS - `fwd_ret_5` only used as target, not feature |
| Walk-forward (no retraining on test) | PASS |

**Verdict**: [PASS] - PIT safety fully maintained.

## 4. ConstantInputWarnings

**Root Cause**: Some GP-generated alpha expressions produce constant arrays (e.g., `log(abs(0))` or degenerate trees). When these are correlated with HoF members via `spearmanr()`, scipy raises ConstantInputWarning.

**Impact**: NONE - the engine correctly handles this:
- Variance guard rejects constant signals (`std < 1e-6 -> fitness = -inf`)
- `np.isnan(ic)` check catches undefined correlations
- These individuals get eliminated by selection pressure

**Verdict**: Non-blocking. Suppress with `warnings.filterwarnings` if log noise is undesirable.

## 5. Regime Analysis: Why Evolution Loses

| Year | Market Regime | Evolution Sharpe | Why Lost |
|:-----|:-------------|:-----------------|:---------|
| 2018 | Bear market (-15% VNI) | -1.00 | GP trained on bull data (2015-2017), overfits to momentum |
| 2022 | Rate hike + liquidity crisis | -1.53 | Same issue: trained on recovery data, fails in crisis |
| 2025 | Low-vol consolidation | -2.43 | InverseVol dominates in low-vol regime; GP finds noisy patterns |

**Pattern**: Evolution fails when market regime shifts significantly from training period. This is expected behavior for any ML-based strategy.

**Mitigation**: 
- Regime detection (drift_detector.py already built)
- Auto-rollback to InverseVol/EqualWeight during detected regime shifts
- Shorter retraining window (quarterly instead of yearly)

## 6. Standalone vs Ensemble Recommendation

| Approach | Pros | Cons |
|:---------|:-----|:-----|
| Standalone Evolution | High Sharpe in trending markets | Catastrophic in regime shifts |
| Ensemble (Evo + Ridge ML) | Smoothed returns, lower drawdown | Slightly lower peak Sharpe |
| Ensemble + Regime Switch | Best risk-adjusted | More complex |

**RECOMMENDATION**: Use Evolution as ONE signal in the Ridge 142-feature ensemble (weight ~15-25%). Enable drift detection to auto-reduce Evolution weight during regime shifts.

---

## Overall Verdict

### [APPROVED] with CONDITIONS

**Conditions**:
1. Evolution MUST be used in ensemble, NOT standalone
2. Drift detection MUST be active (already wired in daily pipeline)
3. Consider quarterly retraining instead of yearly for better regime adaptation
4. Suppress ConstantInputWarnings in production (cosmetic)

---

## Evidence
- **Backtest Results**: `data/backtest/evolution_backtest_results.json`
- **Script**: `scripts/backtest_evolution.py`
- **Walk-Forward**: 10 years (2017-2026), top 30 liquid tickers
- **PIT Compliance**: 100%
- **Win Rate**: Evolution 6/10 years (60%)
- **Avg Sharpe**: 0.85 (acceptable for VN market)
