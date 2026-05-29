# L3 Audit — Phase 3.11 EMA Reset per (ticker, CPCV block) (Codex)

**Date**: 2026-05-30 06:39 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e761a-2d9f-70e3-a9bf-27168f2255ca`
**Rollout**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T06-38-07-019e761a-2d9f-70e3-a9bf-27168f2255ca.jsonl`
**Wall time**: ~3 min, multi-file read + cross-check JSONs.
**Invocation**: SOUL.md Rule 9.1 (stdin pipe).

## Inputs reviewed
- `scripts/backtest_v2_cpcv.py` (EMA block in run_pipeline ~lines 308-340)
- `packages/quant/src/omega/quant/validation/cpcv.py` (test_idx construction)
- `.ly_state/session/phase3_10_full_1B.json`
- `.ly_state/session/phase3_11_full_{1B,10B,100B}.json`
- `.ly_state/session/phase3_11_summary.md`

## Verdict

**[APPROVED]** — 5 P2 verification points, all positive evidence. No P0/P1 blockers, no recommended changes.

## Findings

### P2 verification (all PASS)

1. **Block-boundary detection** (`backtest_v2_cpcv.py:330`): `np.where(np.diff(te) > 1)[0]` verified against `cpcv.py`. `CombinatorialPurgedKFold.split` builds each group as `np.arange(lo, hi)` and `test_idx = np.concatenate([groups[g] for g in test_groups]); test_idx.sort()`. For k=2 → te is sorted union of two contiguous arange's. **Adjacent group pairs (e.g. (0,1)) collapse to one contiguous range** with no `diff > 1` — semantically correct (same calendar continuum, EMA legitimately continues). **Non-adjacent pairs produce exactly one boundary**.

2. **`block_id` loop** (`backtest_v2_cpcv.py:333`): Correct (rows ≤ b keep lower id, rows ≥ b+1 increment). `len(te)==1` falls through to all-zero. Optional micro-cleanup suggested: `block_id = np.cumsum(np.r_[0, (np.diff(te) > 1).astype(np.int64)])` (vectorized equivalent, low priority).

3. **Position-index round-trip** (`backtest_v2_cpcv.py:336`): `pos = np.arange(len(r["pred"]))` round-trips correctly: sort by (ticker, block, date) → EWM transform (preserves group order) → sort by pos → `to_numpy()` aligns 1:1 with original te-position. `groupby(["ticker", "block"])` gives independent EWM state per pair. `adjust=False` means first bar of each block equals raw prediction (correct reset semantics).

4. **PIT compliance**: EMA inputs are `r["pred"]` (model output on `X_te`), `tickers[te]`, `dates[te]`, and `te` itself — all test-fold-local. Train data and labels never touch the smoother. zscore stats remain train-only (`mu`, `sd` from `X_tr`). No leakage introduced by Phase 3.11.

5. **Numerical sanity** confirmed against Phase 3.10 vs 3.11 1B JSONs:
   - `total_turnover` identical: 13.936186484576131
   - `total_cost` identical: 0.043956578655818666
   - `final_w` identical to last digit
   - `dsr_sr_ann` 3.1898 → 3.1932 (+0.0034)
   - `fold_dsr.sr_mean_annualized` 3.1806 → 3.1850 (+0.0045)
   - 10B and 100B JSONs corroborate uniformly positive aggregate Δ
   - Per-fold SRs change in mixed signs as expected (rebalanced bar-0 noise of block 2)

### SOD compliance

Phase 3.11 is a deterministic refactor inside `run_pipeline` only. No writes to `.ly_state/`, no audit-bypass, no self-approval path. Audit/Impl session separation honored. Pre-existing test suite (30/30) per summary remains green.

## Disposition

**Gate APPROVED** for Phase 3.11. No code changes recommended. P2 micro-cleanup (vectorized `block_id` via cumsum) deferred — current loop is clear and correct.

## Evidence chain

- `.ly_state/session/phase3_11_codex_audit.stdout` — codex agent_message extracted from rollout
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T06-38-07-*.jsonl` — full session log (119 KB, ends with `task_complete`)
- Pre-existing test suite still green: `pytest packages/quant/tests/test_execution_sim.py packages/quant/tests/test_dsr.py -q` → 30/30 PASS
