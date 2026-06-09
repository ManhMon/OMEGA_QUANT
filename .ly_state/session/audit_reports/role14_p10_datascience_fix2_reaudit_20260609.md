# P10 Fix2 Scientific Re-Audit - Role14 Data Scientist

Role: Data Scientist / Role14 (L3 audit-only scientific review)
Verdict: [APPROVED]
Scientific Validity: PASS
Role Compliance: PASS

Gate Contract:
- l3_session_id: 9f37d9f4-71b5-4f1a-86c7-b184c4de5a6a
- l3_session_key: role14_p10_datascience_fix2_reaudit_20260609
- audit_report_path: .ly_state/session/audit_reports/role14_p10_datascience_fix2_reaudit_20260609.md
- final_verdict: [APPROVED]

## Scope

Reviewed as L3 audit only. No production code or tests were modified by this audit.

Inputs reviewed:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/audit_reports/role14_p10_datascience_rebuttal_20260609.md`
- `.ly_state/session/audit_reports/role21_p10_multi_horizon_blend_fix2_reaudit_20260609.md`
- `.ly_state/session/audit_reports/role20_p10_compliance_fix2_reaudit_20260609.md`
- `.ly_state/session/audit_reports/role23_p10_performance_fix2_reaudit_20260609.md`

## Verification

- `code-review-graph/get_minimal_context_tool` attempted; timed out after 120s. Direct source/report/test audit used.
- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `28 passed`.
- Warnings observed: vnstock update notice, pandas downcasting, empty-slice/constant-input numeric warnings, pytest cache warning. No failures.

## Findings

No blocking scientific findings remain for P10 Fix2 as a default-off, opt-in experimental gate. P10 is not approved as a proven performance improvement over P9.

### 1. Negative or zero IC cannot receive positive blend weight

PASS. `_blend_horizon_signals()` now uses signed selected quality only. Invalid method falls back to `validation_ic` at `src/omega/quant/phase35_walk_forward.py:1331` through `src/omega/quant/phase35_walk_forward.py:1335`; single surviving non-positive quality returns `None` at `src/omega/quant/phase35_walk_forward.py:1351` through `src/omega/quant/phase35_walk_forward.py:1360`; multi-horizon `quality_val <= 0` is set to zero at `src/omega/quant/phase35_walk_forward.py:1364` through `src/omega/quant/phase35_walk_forward.py:1373`; all non-positive quality returns `None` rather than equal weighting at `src/omega/quant/phase35_walk_forward.py:1377` through `src/omega/quant/phase35_walk_forward.py:1383`; only positive qualities are normalized at `src/omega/quant/phase35_walk_forward.py:1385` through `src/omega/quant/phase35_walk_forward.py:1405`.

Coverage: single non-positive, all non-positive, train-vs-validation weights, and final-objective alignment are tested at `tests/phase35/test_p10_multi_horizon_blend.py:590` through `tests/phase35/test_p10_multi_horizon_blend.py:739`.

### 2. Blend weights align to final objective `return_col`

PASS. `_compute_horizon_signal()` computes own-target train/validation IC for diagnostics, then separately computes final-objective train/validation IC against `final_objective_return_col` at `src/omega/quant/phase35_walk_forward.py:1257` through `src/omega/quant/phase35_walk_forward.py:1275`. It maps `train_ic` and `validation_ic` to final-objective ICs at `src/omega/quant/phase35_walk_forward.py:1277` through `src/omega/quant/phase35_walk_forward.py:1284`. The multi-horizon caller passes the fold objective `return_col` as `final_objective_return_col` at `src/omega/quant/phase35_walk_forward.py:1501` through `src/omega/quant/phase35_walk_forward.py:1510`.

This clears the prior objective-mismatch blocker from `.ly_state/session/audit_reports/role14_p10_datascience_rebuttal_20260609.md:61` through `.ly_state/session/audit_reports/role14_p10_datascience_rebuttal_20260609.md:65` for the limited opt-in experiment scope.

### 3. Gate-failed horizons are excluded; all fail falls back to T+5 baseline

PASS. Robust verdict parsing rejects `FAIL*`, `REJECT*`, `NEEDS_FIX*`, unknown strings, false, and null at `src/omega/quant/phase35_walk_forward.py:37` through `src/omega/quant/phase35_walk_forward.py:90`. Horizon gate pass count uses that parser at `src/omega/quant/phase35_walk_forward.py:1230` through `src/omega/quant/phase35_walk_forward.py:1239`; zero pass count returns `None`, excluding the horizon from the blend. The caller adds only non-null signals to `horizon_results` at `src/omega/quant/phase35_walk_forward.py:1513` through `src/omega/quant/phase35_walk_forward.py:1532`.

If every horizon fails or the blend has no positive quality, fallback executes the approved single-horizon path with original `return_col` at `src/omega/quant/phase35_walk_forward.py:1539` through `src/omega/quant/phase35_walk_forward.py:1581`. Role20 independently verified the all-fail fallback and PIT source at `.ly_state/session/audit_reports/role20_p10_compliance_fix2_reaudit_20260609.md:41` through `.ly_state/session/audit_reports/role20_p10_compliance_fix2_reaudit_20260609.md:55`.

### 4. Diagnostics retain own-target and final-objective ICs; label-correlation caveat remains documented

PASS with residual research caveat. `quality_metrics` retains `final_objective_train_ic`, `final_objective_validation_ic`, `own_target_train_ic`, and `own_target_validation_ic` at `src/omega/quant/phase35_walk_forward.py:1277` through `src/omega/quant/phase35_walk_forward.py:1284`. Per-fold diagnostics log included/excluded horizons, blend method, fallback status, gate count, and final-objective validation IC at `src/omega/quant/phase35_walk_forward.py:1607` through `src/omega/quant/phase35_walk_forward.py:1626`.

The label-correlation concern is still scientifically real: prior Role14 measured T+3 vs T+5 Spearman `0.7430`, daily CS Spearman `0.7047`, and sign agreement `81.83%`, concluding horizons are highly redundant at `.ly_state/session/audit_reports/role14_p10_datascience_rebuttal_20260609.md:26` through `.ly_state/session/audit_reports/role14_p10_datascience_rebuttal_20260609.md:32`. Fix2 does not make the horizons independent; it makes the experiment honest and gated.

### 5. Scientific status: experimental, not performance-lift proof

PASS for default-off experimental gate; FAIL as production improvement claim. Role23 records full comparable P10 metrics of Portfolio IC `-0.0028`, Raw IC `0.0038`, Raw Daily CS IC `0.0067`, Sharpe `0.9475`, MaxDD `-7.88%` at `.ly_state/session/audit_reports/role23_p10_performance_fix2_reaudit_20260609.md:72`. P9 baseline remains IC `0.0091`, Sharpe `0.9854`, MaxDD `-8.12%` at `.ly_state/session/audit_reports/role23_p10_performance_fix2_reaudit_20260609.md:74`. Role23 correctly concludes P10 underperforms P9 on IC and Sharpe and must not be marketed as a production upgrade at `.ly_state/session/audit_reports/role23_p10_performance_fix2_reaudit_20260609.md:76`.

This is acceptable for approval only because P10 remains default-off/opt-in: constructor default is `multi_horizon_blend=False` at `src/omega/quant/phase35_walk_forward.py:187`; CLI requires explicit `--multi-horizon-blend` at `scripts/run_phase35_backtest.py:99` through `scripts/run_phase35_backtest.py:114`; config persists `multi_horizon_blend`, `blend_horizons`, and `blend_weight_method` at `scripts/run_phase35_backtest.py:265` through `scripts/run_phase35_backtest.py:291`. Quick-mode output is labeled smoke-only at `scripts/run_phase35_backtest.py:180` through `scripts/run_phase35_backtest.py:188`.

### 6. PIT safety / no lookahead

PASS. Per-horizon embargo is applied before train/validation selection at `src/omega/quant/phase35_walk_forward.py:1183` through `src/omega/quant/phase35_walk_forward.py:1185`. Train/validation slices are built only from embargoed training data at `src/omega/quant/phase35_walk_forward.py:1195` through `src/omega/quant/phase35_walk_forward.py:1204`. Horizon IC/gate work uses `train_actual` and `val_actual` only at `src/omega/quant/phase35_walk_forward.py:1206` through `src/omega/quant/phase35_walk_forward.py:1228`. Final-objective IC weights are computed only on train/validation frames at `src/omega/quant/phase35_walk_forward.py:1266` through `src/omega/quant/phase35_walk_forward.py:1274`. Test-period IC at `src/omega/quant/phase35_walk_forward.py:1599` through `src/omega/quant/phase35_walk_forward.py:1605` is post-blend reporting only.

## Final Verdict

[APPROVED]

Role14 scientific approval is limited: P10 Fix2 may pass as a default-off experimental option with signed/final-objective/gated blending and T+5 fallback. It remains unproven and currently underperforms P9 on IC and Sharpe; any default enablement or performance-improvement claim requires a fresh full-sample scientific audit.
