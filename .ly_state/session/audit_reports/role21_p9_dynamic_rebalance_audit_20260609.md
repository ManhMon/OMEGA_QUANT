# L3 Audit Report - P9 Dynamic Rebalance Frequency

Date: 2026-06-09T11:35:00+07:00
Role: Role 21 - Code Reviewer (L3 Codex)
Scope: Audit P9 dynamic rebalance implementation in `src/omega/quant/phase35_walk_forward.py`.
VERDICT: [NEEDS_FIX]
PIT Safety: FAIL
Role Compliance: PASS

## Gate Contract

- Session ID: 5dfeb8ee-d066-4864-b005-8d6670d535f9
- Session Key: codex:role21:p9-dynamic-rebalance-audit:20260609T113500+0700
- audit_report_path: .ly_state/session/audit_reports/role21_p9_dynamic_rebalance_audit_20260609.md
- final_verdict: [NEEDS_FIX]

## Verification

- Reviewed working-tree diff for `src/omega/quant/phase35_walk_forward.py`.
- Read `_compute_dynamic_rebalance_freq()` at `src/omega/quant/phase35_walk_forward.py:781-868`.
- Read `_apply_stage2_constraints()` call site at `src/omega/quant/phase35_walk_forward.py:870-987`.
- Read `run_fold()` Stage 2 call at `src/omega/quant/phase35_walk_forward.py:1274-1295`.
- Checked P9 v3 evidence log `.ly_state/session/p9_fixed_v3_backtest_20260609.log`.
- Checked P8 baseline report `.ly_state/session/P8_FINAL_REPORT.md`.
- Ran `python -m pytest tests/phase35/ -q`: 100 tests passed; warnings only.

## Blocking Finding

### 1. Full-test volatility is fold-level lookahead

Severity: High

`_compute_dynamic_rebalance_freq()` computes `test_daily_vol` from the full OOS `test_df`, then uses `rolling(...).mean().iloc[-1]` as `current_vol` (`src/omega/quant/phase35_walk_forward.py:834-840`). `_apply_stage2_constraints()` calls this once before iterating over fold dates (`src/omega/quant/phase35_walk_forward.py:911-912`), and `run_fold()` enables it for the whole test fold (`src/omega/quant/phase35_walk_forward.py:1274-1280`). The resulting `rebal_freq` controls all dates in the OOS fold via `idx % rebal_freq` (`src/omega/quant/phase35_walk_forward.py:953-958`).

This means day 1 of a test fold can receive a rebalance cadence chosen using volatility from later test dates, including the final rolling 20-day window of the fold. That is not PIT-safe. Sorting by ticker/date, clipping returns, and using train-only baseline volatility are correct hygiene, but they do not remove the future-test information used in `current_vol`.

Required fix: replace the fold-level detector with a sequential detector. For each rebalance decision date, compute baseline from `train_df` plus only prior available test bars, never from current/future test bars. Acceptable pattern:

- Before first OOS bar: use train-only baseline/default cadence.
- For OOS date `d`: build current volatility from `train_tail + test_df[test_df.date < d]` only.
- Update cadence per date or per rebalance checkpoint; do not compute one frequency from full `test_df` before the fold starts.
- Add a regression test proving changes to future rows in `test_df` do not affect rebalance decisions/weights for earlier dates.

## Correctness Notes

- Baseline volatility is correctly limited to `train_df` and guards empty/invalid train data.
- Sorting before grouped `pct_change()` is correct because return computation is order-sensitive.
- Return clipping to `[-0.5, 0.5]` is reasonable protection against corporate-action/data jumps.
- Threshold mapping is implemented as specified: ratio `> 1.5` -> high/freq 5, `< 0.67` -> low/freq 10, otherwise base freq 7.
- The TypeError fallback is backward-compatible for legacy monkeypatches and does not mask non-signature TypeErrors.

## Metrics Assessment

P9 v3 metrics from evidence:

- Average Portfolio IC: 0.0020
- Average Raw Signal IC: 0.0029
- Average Raw Signal Daily CS IC: 0.0048
- Average Portfolio Sharpe: 1.0121
- Average Max Drawdown: -7.67%

P8 baseline:

- Average Portfolio IC: 0.0120
- Average Portfolio Sharpe: 0.90
- Average Max Drawdown: -8.32%

Sharpe improves by about 12.5% and MaxDD improves by 0.65 percentage points, but Portfolio IC drops from 0.0120 to 0.0020. That is an 83.3% degradation in predictive alignment. More importantly, the risk metrics are contaminated by fold-level lookahead, so they cannot justify approval. Even after a PIT-safe sequential fix, this tradeoff should be re-run and compared against P8 before merge.

## Regime Evidence

The logged regime ratios are numerically sane and match the requested evidence: 2.09, 1.34, 1.66, 0.78, 1.09, 0.79, 0.93, 1.46. The issue is not arithmetic stability; it is when the OOS information becomes available.

## Test Coverage

`tests/phase35/` passes, but current tests do not catch the PIT leak. Add at least one sequential invariance test: mutate future test close prices after an early OOS date and assert early rebalance decisions/weights remain unchanged.

## Role Compliance

PASS.

- Role 21 audit-only review.
- No production or test code modified.
- Audit report written to requested path.
- Skill load state exists in `.ly_state/session/loaded_skills.json`.

## Final Verdict

VERDICT: [NEEDS_FIX]
PIT Safety: FAIL
Role Compliance: PASS
