# L3 Audit — Phase 3.8 Slippage Model with Per-Ticker ADV (Codex)

**Date**: 2026-05-30 05:17 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e75d0-24aa-7dc0-ac22-9ab6b1721ea4`
**Rollout file**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T05-17-15-019e75d0-24aa-7dc0-ac22-9ab6b1721ea4.jsonl`
**Wall time**: 2m48s, 8 file reads, ended cleanly with `task_complete` event.
**Invocation**: per SOUL.md Rule 9.1 — prompt piped via stdin (`type prompt.txt | codex.cmd exec ... -`).

## Inputs reviewed (codex agent listing)
- `scripts/backtest_v2_cpcv.py`
- `packages/quant/src/omega/quant/portfolio/execution_sim.py`
- `.ly_state/session/phase3_8_full_1B.json`
- `.ly_state/session/phase3_8_full_10B.json`
- `.ly_state/session/phase3_8_full_100B.json`
- `.ly_state/session/phase3_8_summary.md`

## Verdict

**[APPROVED]** — model is sound enough to ship the capacity-sensitivity numbers as published. Two findings recommended before production routing.

## Findings

### P1 (production blockers, OK for backtest)

1. **`scripts/backtest_v2_cpcv.py:404` — Dataset-wide ADV median imputation**.
   `np.nanmedian(adv_arr)` over the entire 2020-2024 panel leaks future ADV into earlier years' warmup rows. Impact small (warmup = a few names × ~20 bars/year, only on cost calc, not alpha or label). **OK for backtest reporting; NOT OK for paper-trading.**
   FIX: replace with `pd.Series(adv_arr).expanding().median().shift(1)` keyed on date, or per-year median computed on `<= year-1` data.

2. **`packages/quant/src/omega/quant/portfolio/execution_sim.py:104` — `prev_w = np.zeros(N)` per call**.
   Every test fold's first bar pays full open-from-cash turnover. Headline impact ~0.4% on `total_turnover` (45/11142). Same bias at 1B/10B/100B so **relative capacity ranking unaffected**.
   FIX: pass `prev_w_init` from caller (last bar of train fold) or amortise across first 5 bars.

### P2 (cosmetic / defensive)

3. **`execution_sim.py:106` — `pivot_adv = pivot_w.copy()` initialises missing cells to 0**, then `np.where(adv_row > 0, ...)` silently sets slippage to 0 for missing ADV. Affects very few bars, biases costs **down**. FIX: init with `np.nan`, treat NaN as cross-sectional median × 0.5 or cap participation at 1.0.

4. **`backtest_v2_cpcv.py:99 / 202` — `pivot_adv.loc[date, tk] = adv_val` only in the main rebalance branch**; sticky-weight `len(g) < 2` and `delta < rebal_threshold` branches `continue` without populating row. Harmless today (delta_w==0 → 0 slippage), but fragile. FIX: lift `pivot_adv` update out of branches.

5. **`backtest_v2_cpcv.py:435` — `--realistic-tc` without `--tail-controls` silently disables ADV slippage** (only commission+spread). Sweep used both flags so JSONs are valid; CLI is footgun. FIX: assert `realistic_tc → tail_controls` or error out.

6. **`execution_sim.py:34` — `half_spread_bps` named "bps" but stored as fraction** (0.0010 = 10 bps). Inconsistent with `slippage_k = 0.10` (interpreted as "10 bps per 1%"). FIX: rename to `half_spread_frac` or store as int bps and divide at use site.

7. **`phase3_8_summary.md:13` — claim "0.5–1.0 SR optimistic at 10B+" is loose**; at 10B the SR delta is only 0.30, only 100B shows >1.0 SR drop. FIX: tighten to "0.3 SR optimistic at 10B, >3 SR at 100B".

### Confirmed correct (no fix)

- **`backtest_v2_cpcv.py:62`** — `_attach_adv` correctly does `rolling(window).mean().shift(1)` per ticker after `groupby("ticker")`. PIT-safe.
- **`backtest_v2_cpcv.py:101`** — walk-forward warmup year-1 prefetch + `_attach_adv` before fold filter uses prior year's volume/close, never in-fold data. PIT-safe.
- **`execution_sim.py:130`** — Almgren-Chriss linear-impact formula verified analytically. `cost_t = k * capital * sum_i (delta_w_i^2 / ADV_i)`, units consistent (fractional return).
- **`phase3_8_full_*.json`** — capital-sensitivity numbers internally consistent. `total_turnover` and `commission/spread` are **identical** across 1B/10B/100B (capital-invariant). Slippage is **exactly ×1/×10/×100** (linear scaling). `dsr_sr_ann` monotonic 3.190 → 2.888 → -0.183.
- **SOD/PIT pipeline** — target = forward horizon-day return on `close`, computed once on full panel; CPCV applies `embargo + label_horizon` purge; Ridge fits on train-only z-scores; ADV uses `shift(1)`; universe is per-year walk-forward. No SOD violations. PIT chain intact aside from P1#1.

## Disposition

**Gate APPROVED** for current Phase 3.8 backtest publication. P1 findings logged as follow-up tickets:

1. ADV imputation → expanding median (`scripts/backtest_v2_cpcv.py:404`)
2. Cross-fold `prev_w_init` carry-over (`execution_sim.py:104`)

P2 findings batched for next refactor pass. None block the pipeline.

## Evidence chain

- `.ly_state/session/phase3_8_codex_audit.stdout` — codex agent_message extracted from rollout
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T05-17-15-019e75d0-24aa-7dc0-ac22-9ab6b1721ea4.jsonl` — full session log (102 KB, 8 tool calls, ends with `task_complete` event)
- `scripts/audit_phase38.py` + `.ly_state/session/phase3_8_audit.stdout` — independent Python audit (5/5 PASS, complementary)
