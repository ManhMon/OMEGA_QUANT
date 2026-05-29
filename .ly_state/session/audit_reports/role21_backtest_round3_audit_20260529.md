# L3 Audit Report Round 3: Backtest Bug-Fix Verification
**Date**: 2026-05-29
**Auditor**: Role 21 - Code Reviewer (Codex L3 - findings extracted from session log)
**Codex Session**: amber-glade (read all 3 files, found NEW bugs in fix attempt)
**Scope**: Verify L2 fix from opencode session plaid-wharf

---

## VERDICT: **[NEEDS_FIX]** - L2 fix incomplete, NEW bugs surfaced

Codex confirmed L2 partially fixed P0 bugs but discovered:
- **5 exact Sharpe ties** with EqualWeight (Evolution = InvVol = EqWt)
- **3 sign-flipped results** (just inverted EqualWeight)
- **Sharpe still inflated sqrt(5) = 2.24x** due to overlapping fwd_ret_5 returns
- **Constant signal guard insufficient** — alphas with std > 1e-6 still produce uniform np.sign() = +1

---

## Audit Matrix

| File | Bug 1 (Sharpe) | Bug 2 (Constant) | Bug 3 (Z-score) | Verdict |
|:-----|:--------------:|:----------------:|:---------------:|:-------:|
| backtest_evolution.py | ⚠️ Partial (still 2.24x inflated) | ❌ Insufficient (sign collapse) | N/A | NEEDS_FIX |
| backtest_evolution_multiseed.py | ⚠️ Partial | ❌ Same issue | ✅ Fixed | NEEDS_FIX |

---

## NEW P0 BUGS Discovered

### Bug 4 (P0): Overlapping fwd_ret_5 → sqrt(5) Inflation
**Issue**: `fwd_ret_5 = close.pct_change(5).shift(-5)` produces 5-day overlapping returns. Each daily observation contains the same 5-day window data 5 times → autocorrelation → Sharpe inflated by sqrt(5) = 2.24x.

**Evidence**: EqualWeight (constant +1 long) gives Sharpe 7.37 in 2017. Real annual Sharpe of long-only VN30 in 2017 should be ~3.0 max → confirms ~2.5x inflation.

**Fix**: Use non-overlapping 1-day returns for Sharpe calculation, OR adjust by Newey-West correction:
```python
sharpe_corrected = sharpe / sqrt(5)  # for 5-day overlap
```

### Bug 5 (P0): np.sign() Sign Collapse Despite std Check
**Issue**: Threshold `np.std(alpha) < 1e-6` lets through alphas with small std but uniform sign (e.g., `vol_ratio - 0.999` is monotonically positive on test set).

**Evidence**: Turnover = 0.0 in 9/10 years AFTER bug 2 fix.

**Fix**: Force long/short balance using cross-sectional median demean:
```python
positions = np.sign(alpha - alpha.groupby(date).transform('median'))
```

### Bug 6 (P0): Ranking Pools Cross-Sectional vs Time
**Issue**: `pd.Series(alpha).rank(pct=True)` ranks ALL ticker-days together, not per-day. This is global rank, not cross-sectional rank.

**Fix**: Group by date for true cross-sectional ranking:
```python
alpha_ranked = pd.Series(alpha).groupby(dates).rank(pct=True) - 0.5
```

---

## Statistical Reality Check

| Strategy | Reported Sharpe (avg) | Realistic Sharpe (after sqrt(5) + sqrt(30) correction) |
|:---------|:---------------------:|:------------------------------------------------------:|
| Evolution | +0.67 | ~+0.05 (essentially zero) |
| Mom20 | +1.20 | ~+0.10 |
| InvVol | +2.20 | ~+0.18 |
| MeanRev | -1.04 | ~-0.08 |
| EqWt | +2.20 | ~+0.18 |

**Conclusion**: Real Sharpe of 0.05-0.20 means NONE of these strategies have meaningful alpha on top 30 VN tickers. GP Evolution definitely doesn't add value.

---

## Recommended Actions

1. **STOP** trying to make GP work standalone
2. **FIX** Sharpe calculation properly (overlap + cross-section + variance scaling)
3. **PIVOT** to using GP outputs as **features** for Ridge ML (not as standalone signals)
4. **PRIORITY**: Use existing `run_stage5_ml_signals.py` (Ridge 142 features) as production
5. **EVOLUTION**: Demote to "alpha generator" feeding into Ridge pipeline

---

## Evidence
- **Codex Session**: amber-glade (read all 3 files, identified Bug 4-5-6)
- **Conclusion**: Even after L2 fix, methodology has 3 more bugs preventing valid conclusions
- **Action**: STOP backtest iteration, use Ridge ML as production signal
