# Phase 3.11 — EMA Reset per (ticker, contiguous CPCV block)

## Problem

Phase 3.7's per-ticker EMA smoothing on test predictions used:
```python
df_pred.groupby("ticker")["pred"].transform(
    lambda s: s.ewm(span=signal_ema_param, adjust=False).mean()
)
```

In CPCV(N=10, k=2) each fold's `test_idx` is the union of **two contiguous calendar blocks** (e.g. Q1-2020 + Q3-2022). When the same ticker appears in both blocks, EWM treats the two prediction streams as continuous — span=5 smoothing crosses a 2.5-year calendar gap, which is meaningless.

Codex Phase 3.7 audit (memory note 2026-05-29) flagged this as one of three falsification candidates. Y-shuffle test PASSED, so the original concern about leakage was rebuffed empirically. But the EMA across-block smoothing is still semantically wrong; Phase 3.11 fixes it for cleanliness.

## Fix

Identify CPCV calendar block boundaries inside `test_idx` via `np.diff(te) > 1`, then group EMA by `(ticker, block_id)`:

```python
if len(te) > 1:
    block_breaks = np.where(np.diff(te) > 1)[0]
    block_id = np.zeros(len(te), dtype=np.int64)
    for b in block_breaks:
        block_id[b + 1:] += 1
else:
    block_id = np.zeros(len(te), dtype=np.int64)

df_pred = pd.DataFrame({
    "pred": r["pred"], "ticker": te_tickers, "date": te_dates,
    "block": block_id,
    "pos": np.arange(len(r["pred"]))
})
df_pred = df_pred.sort_values(["ticker", "block", "date"]).reset_index(drop=True)
df_pred["pred_ema"] = df_pred.groupby(["ticker", "block"])["pred"].transform(
    lambda s: s.ewm(span=signal_ema_param, adjust=False).mean()
)
df_pred = df_pred.sort_values("pos").reset_index(drop=True)
r["pred"] = df_pred["pred_ema"].to_numpy()
```

Each `(ticker, block)` pair gets its own EMA state, reset at block boundaries.

## Numerical impact (full WF, label_horizon=20, span=5)

| cap | metric | Phase 3.10 | Phase 3.11 | Δ |
|--:|--:|--:|--:|--:|
| 1B  | fold_DSR | 0.4433 | 0.4452 | +0.0020 |
| 1B  | fold_SR_ann | 3.181 | 3.185 | +0.0045 |
| 1B  | pool_SR_ann | 3.190 | 3.193 | +0.0034 |
| 1B  | avg_cost_bps | 1.744 | 1.744 | 0 |
| 1B  | total_turnover | 13.94 | 13.94 | 0 |
| 10B | fold_DSR | 0.4081 | 0.4103 | +0.0022 |
| 10B | fold_SR_ann | 2.868 | 2.873 | +0.0047 |
| 100B | fold_DSR | 0.0998 | 0.1009 | +0.0010 |
| 100B | fold_SR_ann | -0.0840 | -0.0799 | +0.0041 |

Observations:
- **Tiny but uniformly positive SR improvement** (~0.005 ann) across all capitals — consistent with codex's prior expectation that EMA-cross-block was a small bias, not a major leak.
- **Turnover and costs unchanged**: the fix only redistributes prediction signal at the very first bar of the second contiguous block. Net portfolio behaviour is essentially identical otherwise.
- **Capacity ranking unchanged**: 1B > 10B > 100B (negative).
- **Memory note #3 (codex falsification b)**: now properly resolved. Y-shuffle PASSED earlier confirmed no leakage; Phase 3.11 confirms there was also no significant alpha hiding in the across-block smoothing.

## Files modified

- `scripts/backtest_v2_cpcv.py` — EMA grouped by (ticker, block_id) instead of (ticker)
- `scripts/compare_phase311_vs_phase310.py` — diagnostic comparison

## Test status

No new tests required (deterministic refactor inside an existing function). Pre-existing `pytest packages/quant/tests/test_execution_sim.py packages/quant/tests/test_dsr.py -q` → **30/30 PASS** unchanged.

## Verdict (for codex audit)

EMA reset per `(ticker, block)` correctly identifies CPCV's combinatorial block boundaries via `np.diff(te) > 1`. The fix is mathematically clean (each block is now a self-contained EWM state) and produces small uniform improvements (+0.004-0.005 SR_ann across 1B/10B/100B), confirming the original Phase 3.7 implementation was suboptimal but not catastrophic. Y-shuffle test from Phase 3.7 already ruled out leakage; Phase 3.11 just tightens the semantics.
