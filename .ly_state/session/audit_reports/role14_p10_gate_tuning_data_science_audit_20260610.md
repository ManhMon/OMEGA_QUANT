# [L3-Audit:Role14-DataScientist] P10 Gate Tuning Data Science Audit

**Date**: 2026-06-10  
**Role**: Role14 - Data Scientist, constrained to L3 audit-only execution by task instruction  
**Verdict**: `[APPROVED]`  
**Scientific Validity**: PASS  
**Role Compliance**: PASS  

## Gate Contract

- **l3_session_id**: role14-p10-gate-datascience-20260610T080000+0700
- **l3_session_key**: codex:role14:p10-gate-datascience:20260610T080000+0700
- **audit_report_path**: `.ly_state/session/audit_reports/role14_p10_gate_tuning_data_science_audit_20260610.md`
- **final_verdict**: `[APPROVED]`

## Scope

- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/p10_tuning_relaxed_20260609/summary.json`
- `.ly_state/session/audit_reports/role21_p10_gate_tuning_json_persist_fix_reaudit_20260610.md`
- `.ly_state/session/audit_reports/role20_p10_gate_tuning_partial_metadata_fix_reaudit_20260610.md`
- `.ly_state/session/audit_reports/role23_p10_gate_tuning_performance_audit_20260610.md`

## Findings

No P0/P1 data-science blockers found. Approval is narrow: relaxed gate tuning is valid only as an opt-in experiment with observed Sharpe/MaxDD improvement. It does not justify an IC or alpha-quality upgrade claim.

## Verification Matrix

1. **No lookahead in relaxed gate decisions or blend weights**: PASS  
   Horizon gate eligibility is computed only from embargoed train/validation data. `_compute_horizon_signal()` drops the last `horizon` rows per ticker before IC/gate computation (`phase35_walk_forward.py:1237-1246`), splits that cleaned train set into train/validation (`1259-1268`), validates the Research Gate on validation (`1286-1292`), and computes blend quality on train/validation only (`1394-1422`). The test-period signal is used later for fold outcome IC, not for gate admission or weights.

2. **Final-objective IC alignment**: PASS  
   Multi-horizon scoring passes the fold objective `return_col` into each horizon as `final_objective_return_col` (`phase35_walk_forward.py:1659-1669`). The metrics used by `_blend_horizon_signals()` are assigned from final-objective train/validation IC (`1413-1422`), while own-target IC is retained only as diagnostics. Test coverage directly asserts final-objective weighting beats own-target weighting (`test_p10_multi_horizon_blend.py:693-746`).

3. **Signed IC filtering, no abs/equal-weight fallback**: PASS  
   `_blend_horizon_signals()` rejects a single non-positive surviving horizon (`phase35_walk_forward.py:1509-1520`), zeroes non-positive quality for multi-horizon blends without `abs()` (`1522-1531`), and returns `None` when all qualities are non-positive (`1535-1544`). Tests cover single/all non-positive quality and relaxed non-positive horizons (`test_p10_multi_horizon_blend.py:590-638`, `931-967`).

4. **T+5 fallback behavior intact**: PASS  
   If all requested horizons fail or all final-objective quality is non-positive, `run_fold()` falls back to the single-horizon baseline using the original objective `return_col` (`phase35_walk_forward.py:1702-1753`). With default objective this remains T+5 (`phase35_walk_forward.py:1572`). This prevents relaxed fallback candidates from becoming equal-weight or wrong-sign horizon blends.

5. **Scientific validity / claim boundary**: PASS  
   Best relaxed candidate in `summary.json` is `relaxed_h35_train`: IC `0.0005`, RawIC `0.0133`, CSIC `0.0127`, Sharpe `1.4324`, MaxDD `-6.26%`, Fallbacks `1`. Versus P9 baseline IC `0.0091`, Sharpe `0.9854`, MaxDD `-8.12%`, this supports Sharpe improvement `+0.4470` and drawdown improvement `+1.86pp`, but IC is worse by `-0.0086`. Valid claim: opt-in relaxed gate improved Sharpe/MaxDD in this run. Invalid claim: IC/alpha upgrade.

6. **Gate metadata truthfulness**: PASS  
   Relaxed fallback admission is explicitly gated by `p10_gate_mode == "relaxed"` and `p10_gate_allow_fallback_candidates` with non-empty `top_alphas` (`phase35_walk_forward.py:1308-1322`). Included metadata labels `selection_source` as `fallback_candidate` only when fallback candidates were used, otherwise `research_gate`; `gate_passed_alphas` lists only actual pass verdicts (`1424-1442`). Tests verify fallback metadata values and empty pass list when all gates fail (`test_p10_multi_horizon_blend.py:1017-1080`). Archived 2026-06-09 tuning artifacts expose fallback use through aggregate `RelaxedCandidateUses`; current source/tests support truthful per-fold metadata on rerun.

7. **Partial-success metadata selection**: PASS  
   The normal blended path now selects metadata from `first_horizon = list(horizon_results.keys())[0]` (`phase35_walk_forward.py:1759-1764`). Because `horizon_results` is populated only for `signal is not None` (`1672-1683`), metadata comes from the first included horizon, not the first requested/excluded horizon. Test coverage directly models missing `fwd_ret_1` with included `h3/h5` and asserts non-excluded metadata (`test_p10_multi_horizon_blend.py:1355-1453`).

## Opt-In Controls

Relaxed mode is not default. Constructor defaults remain `multi_horizon_blend=False`, `p10_gate_mode="strict"`, `p10_gate_min_pass=1`, and `p10_gate_allow_fallback_candidates=False` (`phase35_walk_forward.py:189-194`). CLI flags also default to strict/no fallback (`run_phase35_backtest.py:167-182`) and pass relaxed settings only when explicitly configured (`run_phase35_backtest.py:310-315`).

## Test Evidence

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `43 passed`.
- Initial overly-specific pytest node selection failed because several methods are in a different test class than the selected node path; full scoped test file run passed.
- Warnings observed: vnstock update notice, pandas/numpy/scipy warnings, pytest cache warning. No test failure.
- Code-review graph minimal-context call timed out after 120s; direct source/artifact/test audit completed.

## Role Compliance Notes

- Audit-only constraint maintained: no production code or test fixes were made.
- Required audit artifact generated at the specified path.
- Role14 is used here for data-science validity review per task label; execution stayed within L3 audit-only constraints.

## Final Verdict

`[APPROVED]`
