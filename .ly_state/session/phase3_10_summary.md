# Phase 3.10 — P1 Hardening from Codex Phase 3.8 Audit

## Goal

Address two P1 findings from the codex Phase 3.8 audit (2026-05-30 05:17):
1. `backtest_v2_cpcv.py:404` — dataset-wide `np.nanmedian` ADV imputation leaks future ADV.
2. `execution_sim.py:104` — `prev_w = np.zeros(N)` per call charges synthetic open-from-cash on every fold's bar 0.

Both flagged "OK for backtest, NOT OK for live trading".

## What changed

### Change A: causal expanding-median ADV imputation (`scripts/backtest_v2_cpcv.py`)

```python
# OLD: np.nanmedian over full panel (look-ahead)
med = float(np.nanmedian(adv_arr))
adv_arr = np.where(np.isnan(adv_arr), med, adv_arr)

# NEW: causal expanding median, shift(1), bootstrap with first-valid
adv_series = pd.Series(adv_arr)
causal_med = adv_series.expanding(min_periods=1).median().shift(1)
bootstrap = float(adv_series.iloc[adv_series.first_valid_index()])
causal_med = causal_med.fillna(bootstrap)
adv_arr = np.where(np.isnan(adv_arr), causal_med.to_numpy(), adv_arr)
```

### Change B: `prev_w_init` API in `execution_sim.apply_realistic_tc` + `final_w` in breakdown

```python
def apply_realistic_tc(..., prev_w_init: np.ndarray | None = None):
    if prev_w_init is None:
        prev_w = np.zeros(N)
    else:
        if prev_w_init.shape != (N,):
            raise ValueError(...)
        prev_w = prev_w_init.astype(float, copy=True)
    ...
    breakdown["final_w"] = prev_w.copy()
```

Live-trading callers can now chain runs without the synthetic open-from-cash bias. Tests added:
- `test_final_w_returned_in_breakdown`
- `test_prev_w_init_avoids_open_from_cash_cost`
- `test_prev_w_init_shape_validation`
- `test_chaining_two_calls_matches_single_long_call`

## Numerical impact on backtest

**Zero delta vs Phase 3.9 across all 3 capitals**:

| cap | metric | Phase 3.9 | Phase 3.10 | Δ |
|--:|--:|--:|--:|--:|
| 1B  | fold_DSR | 0.4433 | 0.4433 | 0 |
| 1B  | fold_SR_ann | 3.181 | 3.181 | 0 |
| 1B  | total_turnover | 13.94 | 13.94 | 0 |
| 1B  | total_cost_bps | 1.744 | 1.744 | 0 |
| 10B | fold_DSR | 0.4081 | 0.4081 | 0 |
| 10B | fold_SR_ann | 2.868 | 2.868 | 0 |
| 100B | fold_DSR | 0.0998 | 0.0998 | 0 |
| 100B | fold_SR_ann | -0.084 | -0.084 | 0 |

**Why zero delta**:
- `load_panel_walk_forward()` pulls year-1 prehistory before the test window, so by the time `_attach_adv` runs, every in-fold bar has a non-NaN ADV. The imputation path is never triggered in the current pipeline (no `ADV imputation: filled X NaN cells` log line emitted).
- `prev_w_init` defaults to `None` → still zero-cold-start in CPCV. We attempted to auto-carry `prev_w` between consecutive folds but reverted (see "Reverted experiment" below).

The change is **strictly defensive**: future callers who skip the prehistory prefetch (e.g. live paper-trading harness) will now get PIT-safe imputation automatically. Existing CPCV reporting numbers are unchanged.

## Reverted experiment: cross-fold `prev_w` carry

Initially threaded `prev_w_dict_carry` through `run_pipeline` so each fold seeded its bar-0 prev_w from the previous fold's last bar. **Result was worse**:

| cap | total_turnover (3.9) | total_turnover (3.10 carry) | Δ |
|--:|--:|--:|--:|
| 1B  | 13.94 | 14.18 | +0.247 (+1.8%) |
| 10B | 13.94 | 14.18 | +0.247 (+1.8%) |
| 100B | 13.94 | 14.18 | +0.247 (+1.8%) |

Root cause: CPCV(10,2) emits 45 **combinatorial** folds, not chronological. Test windows interleave on the calendar timeline. Carrying weights between non-adjacent folds frequently flips signs and inflates turnover by ~1.8% rather than reducing it.

The codex P1 fix proposal "pass `prev_w_init` from caller (e.g. last bar of train fold)" was right in spirit but requires running the cost loop on the in-sample fit too, which is a deeper refactor (Phase 3.11+ candidate). For now we keep the cleaner approach: zero-cold-start in CPCV (codex-known 0.4% bias, relative capacity ranking unaffected) plus the explicit `prev_w_init` API for live callers.

## Tests

- Pre-existing: 21 DSR + 5 execution_sim = 26
- Added: 4 execution_sim → 30 total
- All PASS: `python -m pytest packages/quant/tests -q` → 30/30

## Files modified

- `scripts/backtest_v2_cpcv.py` — causal expanding-median ADV imputation
- `packages/quant/src/omega/quant/portfolio/execution_sim.py` — `prev_w_init` arg + `final_w` in breakdown
- `packages/quant/tests/test_execution_sim.py` — 4 new tests
- `scripts/compare_phase310_vs_phase39.py` — diagnostic comparison

## Verdict (for codex audit)

P1 #1 (ADV imputation): **fixed** — causal expanding median, shift(1), bootstrap with first valid. PIT-safe. Numerically inactive on current pipeline (no NaN to fill), but live-safe.

P1 #2 (prev_w_init): **API exposed + tested**. Auto-carry inside CPCV reverted (combinatorial fold ordering makes it harmful). Documentation added explaining why. Live-trading harness must call `apply_realistic_tc(..., prev_w_init=<last_run_final_w>)`.
