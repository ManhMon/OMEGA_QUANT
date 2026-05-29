# L3 Audit — Phase 3.10 P1 Hardening (Codex)

**Date**: 2026-05-30 06:23 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e7609-bcdd-78c0-97a6-e03371a70830`
**Rollout file**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T06-20-10-019e7609-bcdd-78c0-97a6-e03371a70830.jsonl`
**Wall time**: ~3 min, multi-file read + pytest run + cross-check JSON.
**Invocation**: SOUL.md Rule 9.1 — prompt piped via stdin.

## Inputs reviewed
- `scripts/backtest_v2_cpcv.py` (ADV imputation block + run_pipeline carry note)
- `packages/quant/src/omega/quant/portfolio/execution_sim.py` (`prev_w_init` arg + `final_w`)
- `packages/quant/tests/test_execution_sim.py` (4 new tests)
- `.ly_state/session/phase3_10_full_{1B,10B,100B}.json`
- `.ly_state/session/phase3_10_summary.md`
- Ran `pytest packages/quant/tests/test_execution_sim.py -q` → 9/9 PASS

## Verdict

**[APPROVED]** — three P2 findings (cosmetic / dead-code / pre-existing). No P0/P1 blockers.

## Findings

### P2 #1 — Bootstrap not strictly PIT (FIXED)

`adv_series.iloc[first_valid_index()]` could pull one forward ADV value into pre-history rows. Strict PIT requires zero-fill until first observation.

**STATUS**: Fixed in follow-up edit. Bootstrap changed to `0.0`, with `apply_realistic_tc`'s `np.where(adv_row > 0, ...)` guard converting that to zero-slippage on cold-start bars (correct behaviour: no ADV known yet → no slippage attribution). Comment updated.

### P2 #2 — `prev_w_dict` path is dead code in CPCV (DOCUMENTED)

`per_date_returns` accepts `prev_w_dict` from `tail_kwargs`, but `run_pipeline` never sets it. Effectively `prev_w_init=None` everywhere → matches documented "zero cold-start in CPCV" decision and the zero-delta backtest numbers.

**STATUS**: Comment in `per_date_returns` updated to make intent explicit ("wired but DELIBERATELY left disconnected from run_pipeline's CPCV loop — it is here for the live-trading harness"). Path kept alive for live callers.

### P2 #3 — Pre-existing collection errors (BACKLOG)

`pytest packages/quant/tests -q` fails on `test_pipeline.py` and `test_portfolio_optimizer.py` with `ModuleNotFoundError: 'omega.quant.portfolio' is not a package` (because `portfolio.py` is a single module while a `portfolio/` package also exists). **Pre-existing**, not introduced by Phase 3.10. Phase 3.10's own tests (`test_execution_sim.py` 9/9 + `test_dsr.py` 21/21 = 30/30) all PASS.

**STATUS**: Out of scope for this phase. Logged for backlog cleanup.

### Confirmed correct (no fix)

- **ADV imputation block**: `pd.Series(adv_arr).expanding(min_periods=1).median().shift(1)` + zero-fill bootstrap + `mask_nan` overlay so non-NaN cells are untouched. Old `np.nanmedian` removed.
- **`prev_w_init` API**: shape validation raises `ValueError("prev_w_init shape ...")`; `prev_w = prev_w_init.astype(float, copy=True)`; `breakdown["final_w"] = prev_w.copy()` reflects last bar's adjusted weights.
- **4 new tests verified by codex**:
  - `test_final_w_returned_in_breakdown` (final_w == w.iloc[-1])
  - `test_prev_w_init_avoids_open_from_cash_cost` (bar-0 turnover delta = |w.iloc[0]|.sum())
  - `test_prev_w_init_shape_validation` (ValueError on mismatch)
  - `test_chaining_two_calls_matches_single_long_call` (split + carry == single run on turnover/commission/spread)
- **`run_pipeline` documentation**: explains why CPCV's combinatorial 45 folds make auto-carry harmful (+1.8% turnover); intentionally keeps `prev_w_init=None` per fold.
- **Phase 3.10 vs Phase 3.9 cross-check**: `fold_dsr` identical to 1e-15 at 1B/10B/100B (`0.4433 / 0.4081 / 0.0998`). Zero delta confirmed.
- **PIT/SOD**: imputation strictly causal; `final_w` is current-bar (no future leakage); SOD process-level unchanged. L3 audit session separate from L2 implementation.

## Disposition

**Gate APPROVED** for Phase 3.10. P2 #1 (bootstrap) and P2 #2 (dead code clarity) fixed in follow-up commit. P2 #3 (pre-existing test collection errors) deferred to backlog.

## Evidence chain

- `.ly_state/session/phase3_10_codex_audit.stdout` — codex agent_message extracted from rollout
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T06-20-10-*.jsonl` — full session log (128 KB, ends with `task_complete`)
- `pytest packages/quant/tests/test_execution_sim.py -q` → 9/9 PASS, executed by codex during audit
