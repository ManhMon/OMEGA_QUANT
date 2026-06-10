# Role21 P10 Gate Tuning Fix Re-Audit - 2026-06-10

## Gate Contract

- l3_session_id: role21-p10-gate-tuning-fix-20260610T061200+0700
- l3_session_key: codex:role21:p10-gate-tuning-fix:20260610T061200+0700
- audit_report_path: .ly_state/session/audit_reports/role21_p10_gate_tuning_fix_reaudit_20260610.md
- final_verdict: [NEEDS_FIX]

## Audit Header

- Role: [L3-Audit:Role21-CodeReviewer]
- Verdict: [NEEDS_FIX]
- PIT Safety: PASS
- Role Compliance: PASS
- Scope: Re-audit of F1/F2 fixes from `.ly_state/session/audit_reports/role21_p10_gate_tuning_audit_20260609.md` across `src/omega/quant/phase35_walk_forward.py`, `scripts/run_phase35_backtest.py`, `tests/phase35/test_p10_multi_horizon_blend.py`, and `.ly_state/session/l2_p10_gate_tuning_role21_fix_report_20260610.md`.

## Findings

### F1 - BLOCKER - Fallback labeling still does not survive persisted JSON artifacts

- Evidence:
  - `_compute_horizon_signal` now returns structured `gate_metadata` with `selection_source`, `used_fallback_candidates`, pass counts, gate mode, required passes, and passed-alpha list at `src/omega/quant/phase35_walk_forward.py:1424-1453`.
  - The multi-horizon caller stores that object in `horizon_details` at `src/omega/quant/phase35_walk_forward.py:1659-1695` and copies only the first horizon's metadata into `FoldMetrics` at `src/omega/quant/phase35_walk_forward.py:1755-1763`.
  - The CLI JSON writer still serializes fold details without `gate_metadata`, `selection_source`, `used_fallback_candidates`, or `gate_passed_alphas` at `scripts/run_phase35_backtest.py:326-343`. Static check: `gate_metadata in script: False`, `selection_source in script: False`.
- Impact: Prior F1 required the fallback source label to survive `_compute_horizon_signal -> horizon_details -> FoldMetrics/JSON where applicable`. The in-memory multi-horizon path is partially fixed, but persisted JSON still cannot distinguish fallback-only candidates from actual Research Gate-passed alphas.
- Required fix: Persist `m.gate_metadata` (or equivalent fold/horizon gate diagnostics) into `fold_details` JSON. If multi-horizon reporting remains first-horizon-only, the JSON must still carry the source label for the reported `gated_alphas`.

### F2 - BLOCKER - Required CLI parse/pass/persist test coverage still missing

- Evidence:
  - `tests/phase35/test_p10_multi_horizon_blend.py` has no references to `run_phase35_backtest`, `argparse`, `phase35_backtest_results`, or `json.dump` (`0` matches each).
  - The new `test_fold_metrics_includes_gate_metadata` is conditional: if `metrics.gate_metadata is not None`, it checks fields; if it is `None`, the test still passes at `tests/phase35/test_p10_multi_horizon_blend.py:1183-1187`.
  - Single-horizon `run_fold` explicitly sets `gate_metadata = None` at `src/omega/quant/phase35_walk_forward.py:2013-2014`, so the conditional test does not prove structural metadata is present.
- Impact: Prior F2 explicitly required coverage for fallback labeling and CLI parse/pass/persist behavior. Fallback metadata unit coverage exists for direct `_compute_horizon_signal`, but script-level parse/pass/persist coverage is still absent, and the FoldMetrics test can pass without metadata.
- Required fix: Add a real script-level or parser-helper test that verifies `--p10-gate-mode`, `--p10-gate-min-pass`, `--p10-gate-allow-fallback-candidates` parse, are passed into `Phase35WalkForwardEngine`, and are persisted. Add an assertion that fold JSON includes fallback labeling when fallback candidates are used.

## Verified Passes

- Default strict behavior unchanged: constructor defaults remain `p10_gate_mode="strict"`, `p10_gate_min_pass=1`, `p10_gate_allow_fallback_candidates=False`; strict mode excludes zero-pass horizons at `src/omega/quant/phase35_walk_forward.py:1303-1307`; tests cover this at `tests/phase35/test_p10_multi_horizon_blend.py:757-792`.
- Relaxed mode opt-in only: CLI defaults to `strict` and requires explicit `--p10-gate-allow-fallback-candidates` at `scripts/run_phase35_backtest.py:117-132`; relaxed fallback candidates are only admitted inside `self.p10_gate_mode == "relaxed"` at `src/omega/quant/phase35_walk_forward.py:1308-1331`.
- FAIL strings are not counted as pass: robust verdict checks reject `FAIL*`, `REJECT*`, `NEEDS_FIX*`; tests cover this at `tests/phase35/test_p10_multi_horizon_blend.py:491-575`.
- Fallback-only candidates are not treated as gate-passed in `_compute_horizon_signal`: fallback metadata reports `selection_source='fallback_candidate'`, `used_fallback_candidates=True`, `gate_passed_count=0`, and empty `gate_passed_alphas`; tests cover the direct function path at `tests/phase35/test_p10_multi_horizon_blend.py:1017-1078`.
- Final-objective signed weighting still blocks negative/zero quality: single surviving non-positive quality returns `None`; all non-positive quality returns `None`; no `abs()` or equal-weight fallback is used in `_blend_horizon_signals` at `src/omega/quant/phase35_walk_forward.py:1509-1539`; tests cover this at `tests/phase35/test_p10_multi_horizon_blend.py:590-738` and `tests/phase35/test_p10_multi_horizon_blend.py:931-967`.
- PIT safety/no lookahead regression: horizon gate and quality metrics are computed from embargoed train/validation slices at `src/omega/quant/phase35_walk_forward.py:1237-1292` and `src/omega/quant/phase35_walk_forward.py:1394-1422`; no new test-period return usage was found in gate decisions or blend weights.

## Verification Run

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q`: 39 passed.
- `python -m pytest tests/phase35/ -q`: 139 passed.
- Static script JSON check: `gate_metadata in script: False`; `selection_source in script: False`; P10 config keys present.
- Static test coverage check: `run_phase35_backtest: 0`, `argparse: 0`, `phase35_backtest_results: 0`, `json.dump: 0` in `tests/phase35/test_p10_multi_horizon_blend.py`.

## Final Verdict

[NEEDS_FIX]

The core PIT behavior and relaxed-mode opt-in controls remain acceptable, but F1/F2 are not fully closed because fallback labels are not persisted to JSON and required CLI parse/pass/persist tests are still absent.
