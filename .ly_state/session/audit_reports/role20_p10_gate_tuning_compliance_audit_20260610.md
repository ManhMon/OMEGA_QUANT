# Role20 P10 Gate Tuning Compliance Audit - 2026-06-10

## Gate Contract

- l3_session_id: role20-p10-gate-compliance-20260610T064600+0700
- l3_session_key: codex:role20:p10-gate-compliance:20260610T064600+0700
- audit_report_path: .ly_state/session/audit_reports/role20_p10_gate_tuning_compliance_audit_20260610.md
- final_verdict: [NEEDS_FIX]

## Audit Header

- Role: [L3-Audit:Role20-ComplianceOfficer]
- Verdict: [NEEDS_FIX]
- PIT Safety: PASS
- Role Compliance: PASS
- Scope: Compliance audit of P10 gate tuning after Role21 approval for `src/omega/quant/phase35_walk_forward.py`, `scripts/run_phase35_backtest.py`, `tests/phase35/test_p10_multi_horizon_blend.py`, and supplied L2/L3 reports.

## Findings

### P1 - JSON/fold reporting can persist the wrong horizon metadata after partial horizon success

Evidence:

- `src/omega/quant/phase35_walk_forward.py:1652-1695` stores `horizon_details` for both included and excluded horizons, in requested-horizon insertion order.
- `src/omega/quant/phase35_walk_forward.py:1702-1724` only falls back to T+5 baseline when no horizons survive or when blend quality is non-positive. A partial-success case can continue on the normal multi-horizon path.
- `src/omega/quant/phase35_walk_forward.py:1755-1762` says it uses the first successful horizon, but actually uses `first_horizon = list(horizon_details.keys())[0]`. That is the first requested horizon, which can be excluded.
- `src/omega/quant/phase35_walk_forward.py:2118-2137` writes that selected `gate_metadata`, `gate_results`, and `gated_alphas` into `FoldMetrics`.
- `scripts/run_phase35_backtest.py:60-73` and `scripts/run_phase35_backtest.py:376` persist the `FoldMetrics.gate_metadata` and aliases into JSON.

Impact:

If horizon 1 is excluded but horizon 3 or 5 is included and the blend succeeds, JSON can report `selection_source: excluded`, `used_fallback_candidates: false`, empty `gated_alphas`, and gate counts from the excluded horizon while the actual signal came from a later included horizon. If the included later horizon used relaxed fallback candidates, that fallback label is not reliably persisted. This violates focus item 2 and item 6: fallback candidates must be labeled and persisted, and JSON/reporting must be truthful.

Required fix:

Persist metadata from the included horizon(s), not the first requested horizon. Minimum acceptable fix: select the first horizon where `included == True`. Better fix: persist per-horizon diagnostics for all requested horizons, including included/excluded status, gate metadata, quality metrics, and blend weight.

Test gap:

- `tests/phase35/test_p10_multi_horizon_blend.py:303-321` covers partial horizon success only at `_blend_horizon_signals()` level.
- Existing serialization tests at `tests/phase35/test_p10_multi_horizon_blend.py:1243-1311` verify a supplied metadata object is serialized, but do not verify `run_fold()` chooses truthful metadata in partial-success scenarios.

## Compliance Checklist

1. Relaxed gate explicit opt-in only; strict defaults unchanged: PASS
   - Engine defaults are strict at `src/omega/quant/phase35_walk_forward.py:188-194`.
   - CLI defaults are strict at `scripts/run_phase35_backtest.py:167-182`.
   - Strict zero-pass exclusion remains at `src/omega/quant/phase35_walk_forward.py:1303-1307`.

2. FAIL strings are not counted as pass; fallback candidates labeled and persisted: FAIL
   - FAIL string counting is fixed by `_is_gate_verdict_pass()` at `src/omega/quant/phase35_walk_forward.py:37-93` and robust gate counts at `src/omega/quant/phase35_walk_forward.py:1294-1297`.
   - Fallback labeling exists at `src/omega/quant/phase35_walk_forward.py:1431-1442` and JSON serialization exists at `scripts/run_phase35_backtest.py:60-73`.
   - Persistence is not truthful in partial-success folds because `run_fold()` can copy metadata from an excluded first requested horizon.

3. Relaxed fallback candidates do not bypass final-objective signed quality filter: PASS
   - Final-objective train/validation IC is mapped into `train_ic`/`validation_ic` at `src/omega/quant/phase35_walk_forward.py:1394-1422`.
   - Signed quality filter rejects single non-positive horizon and all non-positive blends at `src/omega/quant/phase35_walk_forward.py:1509-1541`; no `abs()` fallback observed.

4. All invalid/non-positive horizons fallback T+5 baseline: PASS with reporting caveat
   - Missing return columns produce excluded horizon metadata at `src/omega/quant/phase35_walk_forward.py:1222-1235`.
   - All horizon failure triggers baseline `return_col` fallback at `src/omega/quant/phase35_walk_forward.py:1702-1735`; script sets `RETURN_HORIZON = 5` and `return_col = f'fwd_ret_{RETURN_HORIZON}'` at `scripts/run_phase35_backtest.py:218-319`.
   - Non-positive quality triggers baseline fallback at `src/omega/quant/phase35_walk_forward.py:1510-1541` and `src/omega/quant/phase35_walk_forward.py:1715-1724`.

5. PIT safety/no lookahead: gate and weights use train/validation only: PASS
   - Per-horizon embargo before train/validation split at `src/omega/quant/phase35_walk_forward.py:1237-1268`.
   - Gate validation uses `val_actual`, not test data, at `src/omega/quant/phase35_walk_forward.py:1286-1292`.
   - Blend quality metrics are computed on `train_actual`/`val_actual` against final objective at `src/omega/quant/phase35_walk_forward.py:1394-1422`.

6. JSON/reporting truthful for compliance: FAIL
   - Same P1 finding: persisted fold metadata can describe an excluded horizon rather than the included/blended horizon.

## Verification Run

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q`: 42 passed.
- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py::TestP10GateTuningCLIPersist -q`: 3 passed.
- Warnings observed: Vnstock update notice, pandas/numpy warnings, and pytest cache path warning. No test failures.
- Code-review graph minimal-context call timed out after 120 seconds; direct source/test/report audit completed.

## Final Verdict

[NEEDS_FIX]
