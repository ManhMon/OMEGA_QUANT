# P10 Multi-Horizon Blend Fix Re-Audit

Role: Code Reviewer / Role21
Verdict: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS

Gate Contract:
- l3_session_id: 822c0123-ee7d-4602-a56f-f97919ca33d4
- l3_session_key: role21_p10_multi_horizon_blend_fix_reaudit_20260609
- audit_report_path: .ly_state/session/audit_reports/role21_p10_multi_horizon_blend_fix_reaudit_20260609.md
- final_verdict: [NEEDS_FIX]

## Scope

Reviewed:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/l2_p10_multi_horizon_blend_fix_report_20260609.md`
- `.ly_state/session/l2_p10_gate_truthiness_hotfix_report_20260609.md`
- Prior Role21/20/23/14 audit and rebuttal reports listed in the task.

## Findings

### P1 - Single surviving horizon bypasses non-positive IC rejection

`_blend_horizon_signals()` returns the only valid horizon directly at `src/omega/quant/phase35_walk_forward.py:1344-1348` before applying the signed-quality guard at `src/omega/quant/phase35_walk_forward.py:1353-1369`. A single gate-passing horizon with `validation_ic <= 0` or `train_ic <= 0` gets implicit 100% weight instead of zero weight/fallback.

Probe: `{3: (sig, {'train_ic': -0.1, 'validation_ic': -0.2})}` with `method='validation_ic'` returned `[1.0, 2.0, 3.0]` instead of `None` fallback.

Required fix: apply the same `quality_val <= 0` rejection before single-horizon return. If non-positive, return `None` so `run_fold()` falls back to the single-horizon baseline.

### P1 - Weights are not aligned to final objective `return_col`

`run_fold()` passes `final_objective_return_col=return_col` at `src/omega/quant/phase35_walk_forward.py:1488-1497`, and `_compute_horizon_signal()` computes `final_objective_validation_ic` at `src/omega/quant/phase35_walk_forward.py:1266-1275`. But `_blend_horizon_signals()` only allows `validation_ic` and `train_ic` at `src/omega/quant/phase35_walk_forward.py:1324-1328`, then weights by `qual_dict.get(method, 0.0)` at `src/omega/quant/phase35_walk_forward.py:1353-1359`.

Current `validation_ic` is own-target IC (`src/omega/quant/phase35_walk_forward.py:1262-1275`), so T+1/T+3 can be weighted for their own labels while final scoring/monetization uses `return_col` (`fwd_ret_5` by default). The final-objective IC is logged, not used.

Probe: synthetic metrics where own-target `validation_ic` favors h1 but `final_objective_validation_ic` favors h5 produced output `1.9` = 90% h1 + 10% h5. Final-objective ranking was ignored.

Required fix: make weight quality align to final `return_col`, e.g. use `final_objective_validation_ic` for validation weighting, or redefine train/validation quality consistently against `return_col`.

### P2 - `train_ic` branch is wired but not behavior-tested

The branch is real: valid methods at `src/omega/quant/phase35_walk_forward.py:1324-1328`; selected metric read at `src/omega/quant/phase35_walk_forward.py:1353-1359`. Tests only assert constructor storage at `tests/phase35/test_p10_multi_horizon_blend.py:452-458`. No test proves `method='train_ic'` changes weights versus `validation_ic`.

Required fix: add deterministic opposing-rank test for `train_ic` vs `validation_ic`.

### P2 - Tests miss all-quality-non-positive fallback

Fallback exists for no successful horizons at `src/omega/quant/phase35_walk_forward.py:1525-1531` and blend `None` at `src/omega/quant/phase35_walk_forward.py:1538-1545`. Tests cover missing/partial horizons at `tests/phase35/test_p10_multi_horizon_blend.py:270-321`, but not gate-passing horizons whose selected qualities are all `<= 0`. This gap missed P1.

## Required Checks

1. `blend_weight_method=train_ic` and `validation_ic`: PARTIAL. Both are wired; `train_ic` lacks behavioral test coverage.
2. Gate-failed horizons excluded: PASS. `_is_gate_verdict_pass()` is conservative at `src/omega/quant/phase35_walk_forward.py:37-93`; gate count uses it at `src/omega/quant/phase35_walk_forward.py:1230-1239`; tests cover FAIL strings at `tests/phase35/test_p10_multi_horizon_blend.py:491-575`.
3. All-horizon failure fallback: PARTIAL. Missing/all-gate-failed horizons fall back, but a single surviving non-positive horizon bypasses fallback.
4. Negative/zero IC handling: FAIL. Multi-valid-horizon path zeros non-positive IC at `src/omega/quant/phase35_walk_forward.py:1353-1369`; single-horizon path bypasses it at `src/omega/quant/phase35_walk_forward.py:1344-1348`.
5. Final objective alignment and PIT: FAIL for objective alignment, PASS for PIT. Weight quality comes from embargoed train/validation data, not test labels (`src/omega/quant/phase35_walk_forward.py:1183-1207`, `src/omega/quant/phase35_walk_forward.py:1222-1228`), but allocation still uses own-target IC.
6. Diagnostics/JSON behavior: PASS with caveat. CLI flags/persistence exist at `scripts/run_phase35_backtest.py:100-127`, `scripts/run_phase35_backtest.py:241-243`, and `scripts/run_phase35_backtest.py:289-291`; diagnostics include final-objective IC at `src/omega/quant/phase35_walk_forward.py:1593-1611`. Fallback reason is log-only.
7. Default P9 unchanged: PASS. Default remains `multi_horizon_blend=False`; regression test at `tests/phase35/test_p10_multi_horizon_blend.py:331-357`.
8. Tests cover above: PARTIAL. Missing tests for train-vs-validation behavior, final-objective weighting, single-horizon non-positive rejection, and all-quality fallback.

## Verification

Commands run:
```text
python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q
-> 24 passed

python -m pytest tests/phase35/ -q
-> 128 passed
```

Warnings only: vnstock update notice, pandas/correlation warnings, pytest cache warning.

## Minimal Fix List

1. Apply non-positive quality rejection before the single-horizon early return in `_blend_horizon_signals()`.
2. Align blend weights to final `return_col`; do not only log `final_objective_validation_ic`.
3. Add tests for `train_ic` vs `validation_ic`, final-objective weighting, single-horizon non-positive rejection, and all-quality-non-positive fallback.

Do not mark the gate approved until a fresh L3 re-audit clears these blockers.
