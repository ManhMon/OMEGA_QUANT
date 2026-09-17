# [L2-Impl:Role9-BackendEngineer] P10 Gate Tuning JSON Persist Fix

You are L2 implementation only. Do not audit/approve.

## Scope
Allowed files only:
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/l2_p10_gate_tuning_json_persist_fix_report_20260610.md`

## Read first
- `.ly_state/session/audit_reports/role21_p10_gate_tuning_fix_reaudit_20260610.md`

## Required fixes

### F1: Persist gate metadata to JSON
`scripts/run_phase35_backtest.py` currently serializes fold details without `gate_metadata` / `selection_source`.

Add to each `fold_details` item if present on FoldMetrics:
- `gate_metadata`
- ideally convenience aliases:
  - `selection_source`
  - `used_fallback_candidates`
  - `gate_passed_count`
  - `gate_total`
  - `gate_required_passes`
  - `gate_mode`
  - `gate_passed_alphas`

Ensure JSON serializable.

### F2: Test CLI parse/pass/persist
Add tests proving:
1. `run_phase35_backtest.py` source/persist schema includes gate tuning config keys:
   - `p10_gate_mode`
   - `p10_gate_min_pass`
   - `p10_gate_allow_fallback_candidates`
2. fold JSON serialization includes `gate_metadata` and source labels when a dummy FoldMetrics has metadata.

If current script has no helper, add a small pure helper function in `scripts/run_phase35_backtest.py`, e.g.:
- `serialize_fold_details(results)`
- maybe `build_results_payload(...)`

Keep change surgical. Do not run full backtest inside unit tests.

## Verification
Run:
```powershell
python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q
python -m pytest tests/phase35/ -q
python scripts/run_phase35_backtest.py --quick-mode --multi-horizon-blend --blend-horizons 1,3,5 --p10-gate-mode relaxed --p10-gate-allow-fallback-candidates
```

## Report
Write `.ly_state/session/l2_p10_gate_tuning_json_persist_fix_report_20260610.md` with fixes + command results.

Do not commit/push.
