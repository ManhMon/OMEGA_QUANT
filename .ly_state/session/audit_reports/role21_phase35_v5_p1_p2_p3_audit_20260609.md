# L3 Audit Report - Phase35 V5 P1/P2/P3

Date: 2026-06-09
Role: Code Reviewer (L3 - Codex)
Scope: Phase35 V5 improvements in `phase35_walk_forward.py`, P1 ensemble, P2 blend ceiling, P3 revert
VERDICT: [NEEDS_FIX]

## Gate Contract

- l3_session_id: 2687a6b7-34e0-48ad-add6-aa7dbb4b85f7
- l3_session_key: codex:role21:phase35-v5-p1-p2-p3-audit:20260609T065814+0700
- audit_report_path: .ly_state/session/audit_reports/role21_phase35_v5_p1_p2_p3_audit_20260609.md
- final_verdict: [NEEDS_FIX]

## Findings

1. P1 ensemble train IC does not match the deployed ensemble signal definition.
   - Severity: medium, blocking for approval.
   - File: `src/omega/quant/phase35_walk_forward.py:368-390`
   - Test-side ensemble normalizes each HoF tree before averaging, but train-side ensemble averages raw tree outputs before computing `train_ic`.
   - Because GP tree scale is arbitrary, the adaptive blend weight can be based on a different signal than the one deployed on test data.
   - Required fix: apply the same per-individual normalization to `train_ensemble_signals` before averaging and computing `train_ic`.

2. No targeted unit coverage for P1/P2.
   - Severity: medium, blocking as companion coverage gap for a changed weighting path.
   - Evidence: `rg` found no tests covering `_evolve_inline_signal`, GP ensemble normalization, or the 0.25 ceiling/floor logic.
   - Required fix: add tests proving tuple handling, same-length ensemble output, train/test normalization parity, and `w_evo <= 0.25`.

## Checks

- PIT Safety: PASS
  - GP trains on `train_actual` after embargo.
  - Raw OHLCV features are per-ticker T-1 lagged for train and test.
  - `return_col` and all `fwd_ret_*` columns are excluded from GP feature inputs.
  - Test forward returns are used only for logging `test_ic`, not for training or blend weight.

- Signal Alignment: PASS
  - `_evolve_inline_signal()` returns `Tuple[Optional[np.ndarray], float]`.
  - Caller unpacks `(evolved_signal, gp_train_ic)`.
  - Blend is guarded by `len(evolved_signal) == len(portfolio_signal)`.

- Blend Weight Bounds: PASS
  - Code caps `w_evo` at `0.25`.
  - Floor is `0.1 * evolved_blend_weight`.
  - With user weight `0.4`, bounds are `[0.04, 0.25]`; with current default `0.5`, floor is `0.05`.
  - `w_hand = 1.0 - w_evo` remains positive under constructor validation.

- P3 Revert: PASS
  - Engine defaults restored to `top_n_stocks=15`, `sector_cap_pct=0.40`.
  - Script constants match `15` and `0.40`.
  - Test assertions use `15` and `0.40`.
  - Test names/messages are stale in places but not behavior-breaking.

- Role Compliance: PASS
  - Audit-only review.
  - No production code modified.

## Verification

- `pytest tests/phase35 -q` -> 91 passed.
- `git diff --check 729fa0e..138d9b0 -- src/omega/quant/phase35_walk_forward.py scripts/run_phase35_backtest.py tests/phase35/test_stage2_wiring.py` -> trailing whitespace in P1 block lines 366, 378, 381, 388, 393, 398.

## Final Verdict

VERDICT: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS
