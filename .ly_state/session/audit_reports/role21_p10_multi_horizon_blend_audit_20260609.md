# P10 Multi-Horizon Blending Audit

Role: Code Reviewer / Role 21
Verdict: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS

Gate Contract:
  - l3_session_id: b72f813b-ca67-406b-aaff-6bf465fa5179
  - l3_session_key: role21_p10_multi_horizon_blend_audit_20260609
  - audit_report_path: .ly_state/session/audit_reports/role21_p10_multi_horizon_blend_audit_20260609.md
  - final_verdict: [NEEDS_FIX]

## Scope

Audited files:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`

Inputs reviewed:
- Plan: `C:\Users\GHC\.gemini\antigravity-ide\brain\1b42015e-a973-481b-a807-c6bedd9eaa36\implementation_plan.md`
- L2 report: `.ly_state/session/l2_p10_multi_horizon_blend_report_20260609.md`
- L2 log: `.ly_state/session/p10_l2_multi_horizon_opencode_20260609.jsonl`
- Quick smoke artifacts: `data/phase35_results/phase35_backtest_results_xgboost.json`, `data/phase35_results/phase35_backtest_summary_xgboost.txt`

## Blockers

1. `--blend-weight-method train_ic` is accepted/persisted but not implemented.

   Evidence: `scripts/run_phase35_backtest.py:111-114` advertises `validation_ic` or `train_ic`; `scripts/run_phase35_backtest.py:229-231` passes the value into the engine. But `src/omega/quant/phase35_walk_forward.py:1167-1179` only returns `validation_ic`, and `_blend_horizon_signals()` at `src/omega/quant/phase35_walk_forward.py:1181-1255` ignores `method` except logging and always weights by the second tuple element. Selecting `--blend-weight-method train_ic` silently produces validation-IC weights.

   Minimal L2 repair: return both train and validation quality from `_compute_horizon_signal()` or store a per-horizon quality dict, then branch on `blend_weight_method` with validation of allowed values. Add a test proving `train_ic` and `validation_ic` choose different supplied quality values.

2. All-horizon failure raises instead of falling back safely to current T+5 behavior.

   Evidence: the plan requires failed horizons to get weight 0 and all-fail to fallback to T+5 current behavior. Current code returns `None` for missing return columns at `src/omega/quant/phase35_walk_forward.py:1099-1102`, then raises when no horizon succeeds at `src/omega/quant/phase35_walk_forward.py:1368-1371`; `_blend_horizon_signals()` also raises for empty valid horizons at `src/omega/quant/phase35_walk_forward.py:1220-1222`. This violates required check 5 for safe missing-horizon fallback.

   Minimal L2 repair: if all requested horizons fail, run the existing single-horizon path for `return_col` (`fwd_ret_5` by default) or fail only when that fallback column is also absent. Add a test where requested horizons are missing/invalid and `return_col='fwd_ret_5'` still produces metrics through fallback.

## Required Checks

1. PIT safety: PASS. Each horizon uses `fwd_ret_{horizon}` in `run_fold()` (`phase35_walk_forward.py:1347-1357`), applies horizon-specific embargo (`phase35_walk_forward.py:1104-1106`), computes train IC on `train_actual` with the matching return column (`phase35_walk_forward.py:1127-1128`), and gates on validation data with that same return column (`phase35_walk_forward.py:1143-1149`).

2. Blend weights no lookahead: PASS for implemented `validation_ic`. Weight quality is computed on embargoed train/validation data (`phase35_walk_forward.py:1167-1171`) and not from test labels. Blocker 1 is functional wiring, not test-label leakage.

3. Stage2 after blended raw signal: PASS. Multi-horizon signals are blended at `phase35_walk_forward.py:1368-1375`; Stage2 applies only after both paths converge at `phase35_walk_forward.py:1611-1628`.

4. Default unchanged: PASS. `multi_horizon_blend=False` uses the original single-horizon branch at `phase35_walk_forward.py:1403-1609`; tests passed.

5. Missing horizon fallback: FAIL. Partial horizon success works, but all-horizon failure raises instead of safe T+5 fallback. See blocker 2.

6. CLI flags/config persistence: FAIL. Flags are present and persisted (`run_phase35_backtest.py:100-115`, `run_phase35_backtest.py:277-279`), but `blend_weight_method=train_ic` is not semantically wired. See blocker 1.

7. Tests: PARTIAL. Required suites pass, but they miss the two blocker cases. `tests/phase35/test_p10_multi_horizon_blend.py:211-232` only asserts blended length/non-NaN, not no-test-label behavior; `tests/phase35/test_p10_multi_horizon_blend.py:235-252` checks weight math; `tests/phase35/test_p10_multi_horizon_blend.py:291-306` covers partial horizon success only.

8. Quick smoke zero metrics: ACCEPTABLE AS SMOKE ONLY. The artifact records `quick_mode=true`, `top_n_symbols=1`, `n_folds=2`, and all-zero metrics. With a one-symbol cross-section, per-date z-score normalization can collapse the signal, so this does not prove a P10 logic blocker. It also does not validate model quality.

9. Unrelated dashboard/deployment changes: PASS for audited diff. Production code changes are limited to `phase35_walk_forward.py` and `run_phase35_backtest.py`; test file is new. Existing dirty result artifacts under `data/phase35_results/` are backtest outputs, not dashboard/deployment code.

## Verification Run

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> 12 passed.
- `python -m pytest tests/phase35/ -q` -> 116 passed.

## Residual Notes

- PIT posture is acceptable for the implemented validation-IC path.
- Do not update `phase_gates.json` to approved until the blockers are fixed and re-audited by a fresh L3 session.
