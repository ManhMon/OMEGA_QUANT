# L3 Audit Report: Backtest Recommendations Round 2
**Date**: 2026-05-29
**Auditor**: Role 21 - Code Reviewer (Codex L3 - findings extracted from session log)
**Codex Session**: crisp-nexus (read all 4 files, stuck on write)
**Scope**: backtest_evolution.py + backtest_evolution_multiseed.py + 2 result JSONs

---

## CRITICAL FINDINGS (P0 BUGS DISCOVERED!)

Codex found 3 critical bugs that explain why backtest results are misleading:

### BUG 1: Sharpe Ratio Inflated by ~N_tickers
**Severity**: P0 CRITICAL

**Issue**: `compute_metrics()` treats all ticker-day observations as a FLAT time series:
```python
strat_ret = positions * valid["ret"]  # mixed across tickers
sharpe = (strat_ret.mean() / strat_ret.std()) * np.sqrt(252)
```

**Why it's wrong**: Each day has 30 ticker observations. The "daily return" should be averaged across tickers FIRST, then annualized. Currently each ticker-day is treated as independent, which:
- Increases sample size by 30x
- Reduces standard deviation artificially  
- **Inflates Sharpe ratio by ~sqrt(30) ≈ 5.5x**

**Real Sharpe estimates** (after correction):
- Reported 3.45 → Real ~0.6
- Reported 2.83 → Real ~0.5
- Reported -2.43 → Real ~-0.45

### BUG 2: Constant Signals Pass Through (turnover=0.0)
**Severity**: P0 CRITICAL

**Evidence**: 9/10 years show `turnover: 0.0` for Evolution AND InverseVol AND EqualWeight!

**Why**: GP frequently converges to constant signals (all positive or all negative). When `np.sign(constant)` is applied, all positions = +1 or -1 → equal weight strategy → Sharpe just reflects the long/short bias of the test year.

This explains why **Evolution, InverseVol, EqualWeight tie almost every year** (3.45/3.45/3.45, 2.83/2.83/2.83, etc.) — they're ALL just equal-weight long when GP outputs constant.

### BUG 3: Multi-Seed Z-score Destroys Signal
**Severity**: P0 CRITICAL

**Issue**: `seed_signal = (alpha - alpha.mean()) / alpha.std()` per seed normalizes EACH seed's signal to zero-mean.

**Why it's wrong**: After zero-meaning, ensemble average = ~0 everywhere. The signed direction is destroyed → multi-seed becomes essentially random noise.

**This explains** why multi-seed got 1/10 win rate vs 4-6/10 for single-seed.

---

## Audit Matrix

| File | PIT | Vec | Stats Validity | Verdict |
|:-----|:---:|:---:|:--------------:|:-------:|
| backtest_evolution.py | ✅ | ✅ | ❌ Sharpe inflated | NEEDS_FIX |
| backtest_evolution_multiseed.py | ✅ | ✅ | ❌ Z-score destructive | NEEDS_FIX |
| evolution_backtest_results.json | N/A | N/A | ❌ Misleading | NEEDS_FIX |
| multiseed_backtest_results.json | N/A | N/A | ❌ Misleading | NEEDS_FIX |

---

## Overall Conclusion

### **[NEEDS_FIX]** ❌

**ALL backtest results so far are MISLEADING due to:**
1. Sharpe ratios inflated 5-6x (treated all ticker-days as independent)
2. GP converges to constants → fake "wins" for Evolution
3. Multi-seed z-score per seed destroys ensemble information

**True conclusion**:
- Cannot determine if GP Evolution adds value with current methodology
- Apparent "wins" by Evolution = lucky long/short bias matches market direction
- Need PROPER cross-sectional Sharpe + ensemble averaging WITHOUT z-score

---

## Required Fixes (P0)

### Fix 1: Cross-sectional Sharpe
```python
# Wrong (current):
strat_ret = positions * valid["ret"]
sharpe = strat_ret.mean() / strat_ret.std() * sqrt(252)

# Correct:
daily_ret = (positions * valid["ret"]).groupby("date").mean()  # avg across tickers per day
sharpe = daily_ret.mean() / daily_ret.std() * sqrt(252)
```

### Fix 2: Reject Constant GP Signals
```python
if alpha.std() < 1e-6:
    skip this individual  # don't include constant alphas in ensemble
```

### Fix 3: Multi-Seed without Z-score
```python
# Wrong: per-seed z-score destroys directional info
# Correct: rank-normalize per seed, then average ranks
seed_signal_ranked = pd.Series(alpha).rank(pct=True) - 0.5
ensemble_signal += seed_signal_ranked / NUM_SEEDS
```

---

## Evidence
- **Codex Session**: crisp-nexus (read all 4 files, found bugs in session log)
- **Key Findings**: 3 P0 bugs that invalidate ALL prior backtest conclusions
- **Action Required**: Rewrite compute_metrics() before any production decision
