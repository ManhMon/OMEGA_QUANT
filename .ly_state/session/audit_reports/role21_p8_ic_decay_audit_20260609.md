# L3 Audit Report - P8 IC-Decay Weighting

Date: 2026-06-09T09:57:33+07:00
Role: Role 21 - Code Reviewer (L3 Codex)
Scope: Audit P8 change in `src/omega/quant/phase35_walk_forward.py::compute_alpha_ics()`.
VERDICT: [APPROVED]
PIT Safety: PASS
Role Compliance: PASS

## Gate Contract

- Session ID: 02e7b19c-eb61-4ef5-aa42-82f8d11315e9
- Session Key: codex:role21:p8-ic-decay-audit:20260609T095733+0700
- L2 Session ID: 7b12fca1-ad6e-43b8-b1b7-295dfdf9e66c
- audit_report_path: .ly_state/session/audit_reports/role21_p8_ic_decay_audit_20260609.md
- final_verdict: [APPROVED]

## Verification

- Read `src/omega/quant/phase35_walk_forward.py:412-475`.
- Read `src/omega/quant/phase35_walk_forward.py:209-241` for `compute_ic()` NaN/error behavior.
- Read `src/omega/quant/phase35_walk_forward.py:967-1005` for embargo, train/validation split, and caller context.
- Reviewed working-tree diff for `src/omega/quant/phase35_walk_forward.py`.
- Ran targeted Phase35 tests: `python -m pytest tests/phase35/test_stage2_wiring.py tests/phase35/test_stage3_ml_gate_integration.py tests/phase35/test_stage4_xgboost.py -q` -> 65 passed.
- Ran inline edge harness for 30-date decay path, 29-date fallback path, NaN masking, and missing alpha handling.

## Findings

None blocking.

## PIT Safety

PASS.

- `compute_alpha_ics()` is called for alpha selection with `train_actual` only after train embargo and train/validation split.
- P8 sub-windows are created from `sorted(df['date'].unique())` on the passed training slice; no test dates, validation outputs, portfolio IC, or future fold metrics are introduced.
- IC computation still uses the existing `compute_ic()` over alpha values and forward returns from the same historical slice.
- Decay weighting changes aggregation over training history only; it does not fit on or inspect out-of-sample data.

Note: forward-return labels near sub-window boundaries can naturally overlap the next sub-window by the forecast horizon. This is not a new P8 out-of-sample leak because all sub-windows are inside the same training slice, but it slightly blurs the interpretation of per-window trajectory.

## Correctness

PASS.

- Static weights are `[0.2, 0.3, 0.5]`; sum is `1.0`.
- For `n_dates >= 30`, `third = n_dates // 3`, so each window has at least 10 dates. Empty windows are not expected on the decay path.
- The code still guards `weight_sum > 0` and falls back to full-period IC if no weighted window contributes.
- For `n_dates < 30`, fallback uses the prior single full-period IC behavior.
- NaN pairs are masked by `compute_ic()`; insufficient valid pairs and NaN correlations return `0.0`.
- Missing alpha columns are handled with warning plus `0.0`, same as prior behavior.

## Role Compliance

PASS.

- Role 21 audit-only review.
- No production or test code modified.
- Audit report written to the requested path.
- Skill load state persisted to `.ly_state/session/loaded_skills.json`.

## Final Verdict

VERDICT: [APPROVED]
PIT Safety: PASS
Role Compliance: PASS
