# L3 Audit Report — Phase 3.1+3.2 Validation Framework

**Auditor**: L3-Audit:Role21-Review (Codex CLI session `grand-nudibranch`, terminated mid-write — findings reconstructed from session log)
**Date**: 2026-05-29
**Files**:
- `packages/quant/src/omega/quant/validation/cpcv.py` (195 lines)
- `packages/quant/src/omega/quant/validation/dsr.py` (178 lines)
- `packages/quant/tests/test_cpcv.py` (12 tests)
- `packages/quant/tests/test_dsr.py` (10 tests)

**Test baseline**: 22/22 PASS (verified by L3 in fresh codex session).

---

## VERDICT: `[NEEDS_FIX]`

Two P1 correctness bugs found in CPCV; DSR is mostly correct with minor improvements needed.

---

## CPCV findings

### P1-A: Asymmetric purge — train AFTER test block not handled

**Location**: `cpcv.py::purge_train_indices`, line ~50

```python
block_mask = (train_idx <= hi) & (train_idx + label_horizon >= lo)
```

This only catches train samples whose label window extends INTO test (forward leakage from train to test). It misses the case where a train sample at `i ∈ [hi+1, hi+horizon]` has a label window `[i, i+horizon]` that overlaps with the SAME forward-return realization touched by the last test sample at `hi`. Per AFML §7.4 (Lopez de Prado), purge must be bidirectional: drop any train whose label time interval intersects any test label time interval.

**Correct condition** (for test block `[lo, hi]` and label horizon `h`):
```
drop train_idx[i] iff [i, i+h] ∩ [lo, hi+h] ≠ ∅
        iff i <= hi+h  AND  i+h >= lo
        iff i ∈ [lo-h, hi+h]
```

Current code: `i ∈ [-∞, hi] ∩ [lo-h, +∞] = [lo-h, hi]`. **Missing post-test region `[hi+1, hi+h]`.**

**Fix**:
```python
block_mask = (train_idx <= hi + label_horizon) & (train_idx + label_horizon >= lo)
```

**Impact**: With test=[0..199], train=[200..999], label_horizon=5: train samples 200..204 currently NOT purged but they should be (their label window extends into the same forward-return regime as test sample 199). Embargo at 1% only catches 200..209 (10 bars), so for `embargo_pct < label_horizon/N` (e.g. 0.5%) this is a real leak.

### P1-B: API ambiguity — `timestamps` parameter ignored

**Location**: `purge_train_indices`, line ~46 (`_ = timestamps`)

The function accepts `timestamps: pd.Series` but discards it, doing position-based math instead. This works ONLY if all bars are uniformly spaced (no missing bars, no mixed frequencies). Code comment notes this but signature is misleading.

**Fix options**:
1. Drop `timestamps` parameter (cleanest, but breaks API).
2. Validate `timestamps` is monotonic + uniformly-spaced and raise if not.
3. Implement true ts-based purge for irregular series (more code).

**Recommendation**: option 2 for v1 (assert assumption), option 3 in Phase 4.

### Minor — embargo loop performance

`_embargo_indices` builds Python `set` per fold and uses list comprehension for masking. For large fold counts (45) × large train (10k+ samples), this is O(N×K). Vectorize with `np.searchsorted`:

```python
embargo_arr = np.unique(np.concatenate([np.arange(end+1, end+embargo_bars+1) for _, end in blocks]))
keep_mask = ~np.isin(train_idx, embargo_arr)
```

Not blocking; correctness is fine.

---

## DSR findings

### P2-A: Annualized Sharpe uses exact `== 0` std check

**Location**: `dsr.py::annualized_sharpe`, line ~84

```python
if len(r) < 2 or np.std(r, ddof=1) == 0:
```

Inconsistent with `deflated_sharpe_ratio` which now uses tolerance `1e-12 * max(|mean|, 1.0)`. Constant returns producing 1e-19 std will bypass guard and produce huge SR.

**Fix**: copy the same tolerance check.

### P2-B: Per-bar vs annualized scaling not exposed clearly

DSR formulas use per-bar SR throughout (correct, matches Bailey-LdP). However `sr_benchmark` parameter accepts per-bar values but users typically think annualized. Risk of misuse.

**Fix**: rename to `sr_benchmark_per_bar` OR auto-convert from `sr_benchmark_annualized` parameter.

### Minor — test coverage gaps

1. No numeric reference test: feed (returns, n_trials) with known DSR from Bailey-LdP paper Table 1.
2. No negative SR test (DSR should be < 0.5 if observed SR < 0).
3. No SR=0 + n_trials=1 edge case (should give DSR=0.5 if normal moments).

---

## What WAS verified correct

CPCV:
- ✅ `n_folds == C(n_splits, n_test_splits)` (12/12 unit tests, including 45 for default 10/2).
- ✅ Time-ordered, no shuffling.
- ✅ Train ∩ Test = ∅ across all folds.
- ✅ Embargo correctly applied AFTER each test block (per AFML §7.4 main rule).
- ✅ Position-based math equivalence for uniform daily bars.
- ✅ Handles non-contiguous test groups (purge per-block, not test_min..test_max).

DSR:
- ✅ σ(SR̂) eq.(1) implementation matches Bailey & LdP 2014.
- ✅ E[max{SRₙ}] eq.(2) closed form correct (uses Euler-Mascheroni constant 0.5772156649).
- ✅ DSR = Φ(z) where z = (SR - E[max] - benchmark) / σ(SR), eq.(3).
- ✅ Skew bias-corrected (`bias=False`); kurtosis non-Fisher (Pearson, normal=3).
- ✅ Selection bias deflation works monotonically (test passes with 1 vs 1000 trials).
- ✅ Empirical trial variance overrides default V=1 when provided.
- ✅ Constant returns near-zero-std guard.

---

## Required fixes before APPROVED

| ID | File | Fix | Severity |
|----|------|-----|----------|
| P1-A | `cpcv.py:48-52` | Bidirectional purge: `train_idx <= hi + label_horizon` | P1 |
| P1-B | `cpcv.py:25-44` | Validate `timestamps` uniform-spaced or drop parameter | P1 |
| P2-A | `dsr.py:84` | Use same near-zero std tolerance as DSR | P2 |
| P2-B | `dsr.py:96` | Rename/document `sr_benchmark` units | P2 |

After fixes: re-add unit tests for P1-A leak case + DSR negative-SR test.

---

## Files audited

```
packages/quant/src/omega/quant/validation/cpcv.py    7,680 bytes
packages/quant/src/omega/quant/validation/dsr.py     6,149 bytes
packages/quant/tests/test_cpcv.py                    5,267 bytes
packages/quant/tests/test_dsr.py                     3,363 bytes
```

Test baseline: `22 passed in 0.82s` (verified pre-audit).
