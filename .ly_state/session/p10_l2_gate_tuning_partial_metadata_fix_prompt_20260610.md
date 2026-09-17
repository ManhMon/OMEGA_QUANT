# [L2-Impl:Role9-BackendEngineer] P10 Gate Tuning Partial-Horizon Metadata Fix

You are L2 implementation only. Do not audit/approve.

## Scope
Allowed files only:
- `src/omega/quant/phase35_walk_forward.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/l2_p10_gate_tuning_partial_metadata_fix_report_20260610.md`

## Read first
- `.ly_state/session/audit_reports/role20_p10_gate_tuning_compliance_audit_20260610.md`

## Required fix

Role20 found JSON/fold reporting can persist wrong horizon metadata in partial-success folds:
- `horizon_details` includes excluded + included horizons.
- Current code uses first requested horizon metadata, not first included/successful horizon.
- If horizon 1 excluded but horizon 3 included, FoldMetrics/JSON can report excluded metadata while signal uses horizon 3.

Fix:
1. In `run_fold()` multi-horizon path, choose metadata/gated_alphas/gate_results from the first included horizon, not first requested key.
2. Better if surgical: persist per-horizon diagnostics for all requested horizons in `FoldMetrics.gate_metadata`, e.g. include `horizon_details_summary` or `all_horizon_gate_metadata` with included/excluded status. But minimum: first included horizon metadata must be truthful.
3. Ensure fallback path remains unchanged.

Tests:
- Add a test where `horizon_details` or run_fold scenario has horizon 1 excluded and horizon 3 included, then assert FoldMetrics.gate_metadata corresponds to included horizon 3 metadata.
- If easier, unit-test helper/function that selects reported horizon metadata.
- Ensure existing P10 tests still pass.

Verification:
```powershell
python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q
python -m pytest tests/phase35/ -q
```

Report:
Write `.ly_state/session/l2_p10_gate_tuning_partial_metadata_fix_report_20260610.md` with fix/test results.

Do not commit/push.
