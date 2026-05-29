# L3 Audit Report — Phase 3.3 backtest_v2_cpcv.py

**Auditor**: L3-Audit:Role21-Review (Codex CLI session `swift-tidepool`)
**Date**: 2026-05-29 21:03 GMT+7
**Pattern**: 2-step (codex Step 1 STDOUT only, Ly Step 2 write)
**File audited**: `scripts/backtest_v2_cpcv.py` (192 lines)
**Result audited**: `.ly_state/session/phase3_3_full.json`

---

## VERDICT: `[NEEDS_FIX]`

Two P0 (look-ahead leak + DSR mis-spec), three P1 (semantic correctness), two P2 (statistical hygiene).

---

## P0 — must fix before next backtest

### P0-1: Ridge alpha selected on test IC (look-ahead leak)
**Location**: `evaluate_fold` lines 78-86

```python
for a in alphas:
    m.fit(X_tr, y_tr)
    p = m.predict(X_te)
    ic = np.corrcoef(p, y_te)[0,1]   # uses y_te
    if ic > best_ic:
        best_a = a
```

Picking `alpha` by max IC on `y_te` IS look-ahead. The "best" alpha then drives both the IC reported and the returns fed to DSR. Result: inflated IC, deflated DSR (because the return series isn't reproducible OOS).

**FIX**: tune `alpha` on the TRAIN fold only — split `(X_tr, y_tr)` further with `KFold` or `TimeSeriesSplit` and pick best by train-CV IC. Then refit on full train and predict on test exactly once.

### P0-2: `n_trials = n_folds` is wrong for DSR
**Location**: `run_pipeline` line 110, called at line 165

Bailey-LdP `N` is the SEARCH dimension (#strategies tried during research), not the cross-validation dimension. Using `n_trials = len(folds) = 45` mixes search bias with sampling bias and double-counts fold variance against itself (the same returns then deflate themselves).

**FIX**:
- `n_trials = len(alphas)` (4 here) IF alpha tuning is the only search.
- `trial_sharpes` should be the INTER-strategy SR distribution, not inter-fold.
- Folds aggregate into ONE pooled return series; pass that to DSR with `n_trials = 4`.

---

## P1 — semantic correctness

### P1-1: `fold_returns` uses GLOBAL median across the test bag
**Location**: line 95 (`fold_returns`) called at 110

```python
return np.sign(pred - np.median(pred)) * y
```

Test fold concatenates `n_tickers` × `n_days` rows. `np.median(pred)` is then a scalar across all rows — long the top half of (date×ticker), short the bottom. This is NOT a long-short portfolio; it's a cross-day artifact that washes the signal.

**FIX**: per-date demedian — group by `feat_df['date'].iloc[te_idx]`, demedian `pred` within each date, then aggregate per-date long-short returns into a daily series.

### P1-2: `label_horizon = 5 * n_tickers` is approximate
**Location**: line 175

`5 * n_tickers` only works when every ticker trades every day. With holidays and missing tickers, the flattened position-distance between (ticker=T, date=D) and (ticker=T, date=D+5) varies. Purge zone over- or under-counts.

**FIX (clean)**: do label-aware purge — for each test row `(ticker, date_te)` drop train rows of the SAME ticker with `date_tr ∈ [date_te - 5d, date_te + 5d]`. Requires extending CPCV API or pre-computing index pairs.

**FIX (workaround for Phase 3.3)**: use `label_horizon = 5 * max_tickers_per_day` and document the over-purge.

### P1-3: `cs_zscore` defined but never applied
**Location**: lines 51-58 (defined), line 155-156 (skipped)

Ridge fit on RAW alphas with wildly different scales (volume vs RSI vs returns). The L2 penalty then dominates large-magnitude features, biasing coefficients.

**FIX**: apply z-score INSIDE each train fold (computed on train only, then applied to test), avoiding cross-sectional leakage from test → train normalization.

---

## P2 — statistical hygiene

### P2-1: `if sr != 0.0` filter biases trial-Sharpe variance
**Location**: lines 113-115

Dropping degenerate folds biases `V[{SRₙ}]` upward → artificially shrinks `expected_max_sr` → DSR optimistic (here: doesn't matter since DSR = 0 anyway, but matters when signal is real).

**FIX**: include all folds; treat `sr=0` as a valid trial outcome.

### P2-2: Per-fold SR pooled with overall DSR — double-bookkeeping
**Location**: lines 108-112

`per_fold_sr = mean(rets) / std(rets)` is computed on a cross-sectional bag (49 tickers × n_days), then pooled into `all_returns` and passed to DSR which computes σ(SR) again. The same returns deflate themselves.

**FIX**: choose ONE metric stream — either per-fold (use mean/std fold-Sharpes for DSR-style robustness) OR pooled (just pass `all_returns` once). Don't mix.

---

## Notes (informational, not blocking)

- DSR=0.0 with median IC=0.0303 is internally consistent given P0-1 (alpha-on-test inflates IC) and P0-2 (over-deflated denominator). After fixes, expect IC to drop slightly but DSR to be more honest.
- CPCV(10, 2) on 5y × 49 tickers ≈ 1170 trading days × 49 = 57,330 bars. Each fold test block ≈ 117 days → reasonable.
- `label_horizon = 5 * 49 = 245` collides with `embargo_pct = 0.01 * 57438 ≈ 574 bars ≈ 12 days`. Embargo (12d) > horizon (5d) — currently safe but the sizing is coincidental.
- `n_trials` semantic mix: `n_trials` is SEARCH dimension, `T` is SAMPLE dimension. Don't conflate.
- Output path discrepancy: script default is `phase3_3_cpcv_results.json`, full run wrote `phase3_3_full.json` (CLI override). Not a bug, but document.

---

## Required fixes summary

| ID | Severity | File:line | Description |
|----|----------|-----------|-------------|
| P0-1 | P0 | `backtest_v2_cpcv.py:78-86` | Tune alpha on TRAIN-CV not test IC |
| P0-2 | P0 | `backtest_v2_cpcv.py:110,165` | n_trials = len(alphas), not n_folds |
| P1-1 | P1 | `backtest_v2_cpcv.py:95` | Per-date demedian, not global |
| P1-2 | P1 | `backtest_v2_cpcv.py:175` | Label-aware purge or workaround |
| P1-3 | P1 | `backtest_v2_cpcv.py:155` | Apply cs_zscore inside train fold |
| P2-1 | P2 | `backtest_v2_cpcv.py:113` | Don't filter sr=0 trials |
| P2-2 | P2 | `backtest_v2_cpcv.py:108-112` | Pick per-fold OR pooled, not both |

---

## Audit hygiene

- Codex Step 1 (collect): ran in session `swift-tidepool`, exited code 0
- Files read by codex: `backtest_v2_cpcv.py`, `validation/cpcv.py`, `validation/dsr.py` (full content)
- Files written by codex: NONE (per 2-step rule)
- This report: written by Ly via `write` tool (per SOD v2.1 rule #8)

After fixes: re-run smoke + full + add regression tests for P0-1 (alpha doesn't see test) and P1-1 (per-date demedian).
