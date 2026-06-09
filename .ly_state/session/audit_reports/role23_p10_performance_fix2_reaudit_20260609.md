# P10 Fix2 Performance Re-Audit - Role23

Role: Performance Tester / Role 23
Verdict: [APPROVED]
Performance Safety: PASS
Role Compliance: PASS

Gate Contract:
- l3_session_id: 68b8cf1a-f2bf-4911-920d-d480b7fe594a
- l3_session_key: role23_p10_performance_fix2_reaudit_20260609
- audit_report_path: .ly_state/session/audit_reports/role23_p10_performance_fix2_reaudit_20260609.md
- final_verdict: [APPROVED]

## Scope

Reviewed as L3 audit only. No production code or tests were modified by this audit.

Inputs reviewed:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/audit_reports/role23_p10_performance_rebuttal_20260609.md`
- `.ly_state/session/audit_reports/role21_p10_multi_horizon_blend_fix2_reaudit_20260609.md`
- `.ly_state/session/audit_reports/role20_p10_compliance_fix2_reaudit_20260609.md`
- `.ly_state/session/p10_role21_fix_reaudit_prompt_20260609.md`
- `.ly_state/session/audit_reports/role21_p9_cadence_fix_reaudit_20260609.md`

## Verification

- `code-review-graph/get_minimal_context_tool` attempted for review context and timed out after 120s; direct source, tests, and artifacts were used.
- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `28 passed`.
- Warnings observed: vnstock update notice, pandas downcasting, constant-input/empty-slice numeric warnings, pytest cache warning. No failures.

## Findings

No blocking performance findings remain for P10 as an opt-in experimental feature. P10 is not approved as a default strategy or as a proven performance improvement over P9.

### 1. Negative or zero IC cannot receive positive blend weight

PASS. `_blend_horizon_signals()` now uses signed selected quality only. It validates `method`, filters invalid horizons, maps `quality_val <= 0` to `0.0`, and normalizes only positive qualities at `src/omega/quant/phase35_walk_forward.py:1331`, `src/omega/quant/phase35_walk_forward.py:1364`, `src/omega/quant/phase35_walk_forward.py:1368`, `src/omega/quant/phase35_walk_forward.py:1370`, and `src/omega/quant/phase35_walk_forward.py:1385`.

The all-non-positive path returns `None`, not equal weights, at `src/omega/quant/phase35_walk_forward.py:1377` through `src/omega/quant/phase35_walk_forward.py:1383`. The blend loop applies the resulting normalized positive weights only at `src/omega/quant/phase35_walk_forward.py:1396` through `src/omega/quant/phase35_walk_forward.py:1405`.

Coverage exists for all non-positive qualities at `tests/phase35/test_p10_multi_horizon_blend.py:610` through `tests/phase35/test_p10_multi_horizon_blend.py:638` and positive-weight normalization at `tests/phase35/test_p10_multi_horizon_blend.py:239` through `tests/phase35/test_p10_multi_horizon_blend.py:260`.

### 2. Single surviving non-positive horizon falls back

PASS. The single-horizon guard checks the selected method quality before returning the signal. If `quality_val <= 0`, it returns `None` to trigger baseline fallback at `src/omega/quant/phase35_walk_forward.py:1351` through `src/omega/quant/phase35_walk_forward.py:1360`.

Coverage is explicit at `tests/phase35/test_p10_multi_horizon_blend.py:590` through `tests/phase35/test_p10_multi_horizon_blend.py:608`.

### 3. `train_ic` and `validation_ic` are real and behavior-tested

PASS. `_compute_horizon_signal()` computes final-objective train and validation IC from train/validation slices only, then maps those values into `train_ic` and `validation_ic` at `src/omega/quant/phase35_walk_forward.py:1266` through `src/omega/quant/phase35_walk_forward.py:1280`. The final objective return column is passed into the horizon worker at `src/omega/quant/phase35_walk_forward.py:1501` through `src/omega/quant/phase35_walk_forward.py:1510`.

Method selection is real at `src/omega/quant/phase35_walk_forward.py:1331` through `src/omega/quant/phase35_walk_forward.py:1335` and `src/omega/quant/phase35_walk_forward.py:1368`.

Coverage proves different deterministic outputs for `train_ic` vs `validation_ic` at `tests/phase35/test_p10_multi_horizon_blend.py:640` through `tests/phase35/test_p10_multi_horizon_blend.py:690`, and final-objective alignment at `tests/phase35/test_p10_multi_horizon_blend.py:693` through `tests/phase35/test_p10_multi_horizon_blend.py:739`.

### 4. Quick/full labeling is sufficient for audit use

PASS with residual note. Quick mode is structurally a smoke configuration: `TOP_N_SYMBOLS = 1`, `N_FOLDS = 2`, `TRAIN_YEARS = 1`, `TEST_YEARS = 1` at `scripts/run_phase35_backtest.py:137` through `scripts/run_phase35_backtest.py:146`. The CLI emits explicit warnings that quick mode is `SMOKE TEST MODE - NOT PERFORMANCE EVIDENCE`, that cross-sectional metrics may collapse, and that full performance validation requires `top_n_symbols >= 30` at `scripts/run_phase35_backtest.py:180` through `scripts/run_phase35_backtest.py:188`.

Saved JSON also records `quick_mode`, `top_n_symbols`, `n_folds`, `multi_horizon_blend`, `blend_horizons`, and `blend_weight_method` at `scripts/run_phase35_backtest.py:265` through `scripts/run_phase35_backtest.py:285` and `scripts/run_phase35_backtest.py:306` through `scripts/run_phase35_backtest.py:309`.

Residual note: output filenames still use the generic `xgboost`/`baseline` suffix at `scripts/run_phase35_backtest.py:322` through `scripts/run_phase35_backtest.py:330`, so humans must inspect JSON/config or logs before treating an artifact as full P10 evidence. This is not blocking because the quick artifact is machine-labeled and the CLI warning is explicit, but future cleanup should add `quick`/`p10` to filenames or summary headers.

### 5. Full P10 degradation is documented and acceptable only as opt-in experimental

PASS for opt-in safety; not a performance-lift approval.

Documented full comparable P10 evidence: command completed with Portfolio IC `-0.0028`, Raw IC `0.0038`, Raw Daily CS IC `0.0067`, Sharpe `0.9475`, MaxDD `-7.88%`; note says P10 mostly fell back because strict gate excluded all horizons at `.ly_state/session/p10_role21_fix_reaudit_prompt_20260609.md:33` through `.ly_state/session/p10_role21_fix_reaudit_prompt_20260609.md:37`.

P9 baseline evidence remains IC `0.0091`, Sharpe `0.9854`, MaxDD `-8.12%` at `.ly_state/session/audit_reports/role21_p9_cadence_fix_reaudit_20260609.md:34`.

Assessment: P10 underperforms P9 on IC and Sharpe, while MaxDD is slightly better. That is not acceptable as proof of improvement and must not be marketed as a production upgrade. It is acceptable for gate approval only because P10 is default-off/opt-in, strict-gate failures fallback to the approved single-horizon baseline, and Role20/Role21 already approved the safety fixes.

Default-off/opt-in references: constructor default remains off at `src/omega/quant/phase35_walk_forward.py:187`, CLI exposure requires `--multi-horizon-blend` at `scripts/run_phase35_backtest.py:100` through `scripts/run_phase35_backtest.py:114`, and default single-horizon behavior is regression-tested at `tests/phase35/test_p10_multi_horizon_blend.py:331` through `tests/phase35/test_p10_multi_horizon_blend.py:357`.

### 6. Runtime/performance risk is bounded

PASS. P10 adds per-horizon work over the configured horizons at `src/omega/quant/phase35_walk_forward.py:1497` through `src/omega/quant/phase35_walk_forward.py:1511`. Default horizons are three (`1,3,5`), so overhead is expected and bounded for the opt-in path.

If no horizons pass or all selected quality is non-positive, fallback executes the standard single-horizon baseline at `src/omega/quant/phase35_walk_forward.py:1539` through `src/omega/quant/phase35_walk_forward.py:1581`. This caps behavioral risk: a weak P10 blend does not silently become equal-weight or wrong-way; it falls back. Runtime remains acceptable for experiment use, not for making P10 default without a separate benchmark budget.

## Final Verdict

[APPROVED]

Role23 approves P10 Fix2 performance safety only under these constraints: P10 remains opt-in, quick mode remains smoke-only, and the documented full result is treated as experimental evidence with degradation versus P9, not as a strategy improvement claim.
