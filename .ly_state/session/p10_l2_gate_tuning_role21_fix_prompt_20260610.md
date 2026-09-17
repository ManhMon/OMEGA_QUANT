# [L2-Impl:Role9-BackendEngineer] P10 Gate Tuning Role21 Fix

You are L2 implementation only. Do not audit/approve.

## Scope
Allowed files only:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/l2_p10_gate_tuning_role21_fix_report_20260610.md`

## Read first
- `.ly_state/session/audit_reports/role21_p10_gate_tuning_audit_20260609.md`

## Required fixes

### F1: Structured fallback-candidate labeling
Problem: relaxed fallback candidates are returned as plain `gated_alphas`, then persisted/metrics can imply they passed Research Gate.

Implement structured metadata carried from `_compute_horizon_signal()` through P10 horizon details and persisted JSON/fold details.

Minimum fields per horizon:
- `selection_source`: `research_gate` or `fallback_candidate`
- `used_fallback_candidates`: bool
- `gate_passed_count`: int
- `gate_total`: int
- `gate_required_passes`: int
- `gate_mode`: strict/relaxed
- actual gate-passing alpha list if practical: `gate_passed_alphas`
- selected alpha list can remain `gated_alphas`, but must have source label so fallback-only candidates are not misrepresented.

Also adjust log wording if easy: avoid saying fallback-only candidates are truly gated; e.g. `Selected alphas` or include source in log.

Ensure this metadata survives into:
- P10 `horizon_details` / diagnostics
- `FoldMetrics` where relevant
- backtest JSON `fold_details` or equivalent persisted output

### F2: Tests
Add tests for:
1. Relaxed fallback candidates produce `selection_source='fallback_candidate'` and `used_fallback_candidates=True`.
2. Strict/actual gate pass produces `selection_source='research_gate'` and `used_fallback_candidates=False`.
3. Persisted/serializable fold diagnostics include the new fields.
4. CLI flag parse/pass/persist behavior for:
   - `p10_gate_mode`
   - `p10_gate_min_pass`
   - `p10_gate_allow_fallback_candidates`

If `run_phase35_backtest.py` lacks parser helper, add a small testable helper only if surgical; otherwise test generated JSON config via quick-mode subprocess if existing test style permits.

## Verification
Run:
```powershell
python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q
python -m pytest tests/phase35/ -q
python scripts/run_phase35_backtest.py --quick-mode --multi-horizon-blend --blend-horizons 1,3,5 --p10-gate-mode relaxed --p10-gate-allow-fallback-candidates
```

## Report
Write `.ly_state/session/l2_p10_gate_tuning_role21_fix_report_20260610.md` mapping F1/F2 to fixes and command results.

Do not commit/push.
