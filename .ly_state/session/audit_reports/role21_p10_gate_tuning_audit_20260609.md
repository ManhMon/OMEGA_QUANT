# Role21 P10 Gate Tuning Audit - 2026-06-09

## Gate Contract

- l3_session_id: role21-p10-gate-tuning-20260609T221500+0700
- l3_session_key: codex:role21:p10-gate-tuning:20260609T221500+0700
- audit_report_path: .ly_state/session/audit_reports/role21_p10_gate_tuning_audit_20260609.md
- final_verdict: [NEEDS_FIX]

## Audit Header

- Role: [L3-Audit:Role21-CodeReviewer]
- Verdict: [NEEDS_FIX]
- PIT Safety: PASS
- Role Compliance: PASS
- Scope: P10 gate tuning changes in `src/omega/quant/phase35_walk_forward.py`, `scripts/run_phase35_backtest.py`, `tests/phase35/test_p10_multi_horizon_blend.py`, L2 report, relaxed summary JSON.

## Findings

### F1 - Fallback candidates are still represented as `gated_alphas` downstream

- Severity: BLOCKER
- Evidence:
  - `src/omega/quant/phase35_walk_forward.py:772-780` falls back to `top_alphas` when all alphas fail Research Gate, then logs and returns them as `gated_alphas`.
  - `src/omega/quant/phase35_walk_forward.py:1291-1299` marks relaxed fallback use only in local logs; no returned/structured flag is carried with the candidate set.
  - `src/omega/quant/phase35_walk_forward.py:1599-1604` stores included horizon details as `gated_alphas` + `gate_results` only.
  - `src/omega/quant/phase35_walk_forward.py:1678-1680` collapses multi-horizon reporting to first horizon `gated_alphas`/`gate_results`; no fallback-candidate source label survives into `FoldMetrics`.
  - `scripts/run_phase35_backtest.py:326-345` persists fold details without gate/fallback candidate diagnostics.
  - Relaxed evidence log shows the mislabel sequence: `Gated alphas (...)` immediately followed by `relaxed gate: using fallback candidates` in `.ly_state/session/p10_tuning_relaxed_20260609/relaxed_h35_train.log:68-80`.
- Impact: Requirement 3 is not fully met. Operators can see fallback use in logs, but persisted artifacts and API-facing fold metrics can still imply failed-gate fallback alphas are true gated alphas.
- Minimal L2 fix: carry a structured label from `_compute_horizon_signal` into `horizon_details`/`FoldMetrics`/JSON, e.g. `selection_source: "research_gate" | "fallback_candidate"`, `used_fallback_candidates`, `gate_passed_count`, `gate_total`, and avoid naming fallback-only candidates as `gated_alphas` without a source label.

### F2 - Required test coverage does not include CLI JSON persistence or fallback labeling

- Severity: BLOCKER
- Evidence:
  - Collected test list has 36 tests; new `TestP10GateTuning` covers constructor defaults, relaxed/strict engine behavior, invalid mode/min-pass, and non-positive blend quality.
  - No test invokes or unit-tests `scripts/run_phase35_backtest.py` argument parsing / engine argument pass-through / JSON config persistence for `p10_gate_mode`, `p10_gate_min_pass`, `p10_gate_allow_fallback_candidates`.
  - No test asserts fallback candidates are structurally labeled separately from actual gate-passing alphas.
- Impact: Requirement 7 is not met for required item 6 and the structured part of item 3.
- Minimal L2 fix: add script-level test or parser helper test for the three CLI flags and JSON config persistence; add relaxed fallback test asserting the returned/persisted diagnostics label fallback candidates explicitly.

## Verified Passes

- Default strict behavior unchanged: constructor defaults are `strict`, `1`, `False` at `src/omega/quant/phase35_walk_forward.py:190-192`, validation/storage at `src/omega/quant/phase35_walk_forward.py:272-293`, strict excludes zero passes at `src/omega/quant/phase35_walk_forward.py:1275-1280`; unit test covers this at `tests/phase35/test_p10_multi_horizon_blend.py:757-792`.
- Relaxed mode opt-in only: CLI choices/default keep `strict` at `scripts/run_phase35_backtest.py:117-135`; fallback candidates are only considered inside `self.p10_gate_mode == "relaxed"` at `src/omega/quant/phase35_walk_forward.py:1280-1303`.
- FAIL strings are not counted as gate passes: `_is_gate_verdict_pass` only accepts `True`, `PASS`, `APPROVED`, and rejects `FAIL*`/unknown strings at `src/omega/quant/phase35_walk_forward.py:37-76`; tests cover FAIL/REJECT/NEEDS_FIX at `tests/phase35/test_p10_multi_horizon_blend.py:492-575`.
- Final-objective signed weighting blocks non-positive quality: final-objective IC is assigned into `train_ic`/`validation_ic` at `src/omega/quant/phase35_walk_forward.py:1349-1368`; blend rejects single/all non-positive quality without `abs(IC)` or equal-weight fallback at `src/omega/quant/phase35_walk_forward.py:1434-1469`; tests cover this at `tests/phase35/test_p10_multi_horizon_blend.py:590-738` and `tests/phase35/test_p10_multi_horizon_blend.py:931-967`.
- Invalid/missing horizons and non-positive blend quality fallback to T+5 baseline: missing return cols return `None` at `src/omega/quant/phase35_walk_forward.py:1214-1217`; all failed/missing and all non-positive quality trigger fallback at `src/omega/quant/phase35_walk_forward.py:1617-1664`.
- CLI flags parse, pass to engine, and are persisted to JSON in implementation: parse at `scripts/run_phase35_backtest.py:117-135`, pass-through at `scripts/run_phase35_backtest.py:244-265`, persisted config at `scripts/run_phase35_backtest.py:288-316`. Manual `--help` check confirmed all flags are exposed.
- Relaxed matrix evidence matches stated candidate: `.ly_state/session/p10_tuning_relaxed_20260609/summary.json` includes `relaxed_h35_train` with IC `0.0005`, RawIC `0.0133`, CSIC `0.0127`, Sharpe `1.4324`, MaxDD `-6.26`, Fallbacks `1`, NonEmptyHorizonFolds `1`, RelaxedCandidateUses `16`.
- PIT safety: no new use of test-period returns in gate decisions or blend weights. Gate/quality metrics are computed from embargoed train/validation slices at `src/omega/quant/phase35_walk_forward.py:1219-1264` and `src/omega/quant/phase35_walk_forward.py:1340-1368`; test-period signal generation remains after gate selection.

## Verification Run

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q`: 36 passed.
- `python scripts/run_phase35_backtest.py --help | Select-String -Pattern 'p10-gate-mode|p10-gate-min-pass|p10-gate-allow-fallback-candidates|blend-horizons'`: flags present.
- Sample JSON `.ly_state/session/p10_tuning_relaxed_20260609/relaxed_h35_train.json`: config persisted `p10_gate_mode=relaxed`, `p10_gate_min_pass=1`, `p10_gate_allow_fallback_candidates=true`.

## Minimal L2 Fixes Required

1. Add structured fallback-candidate labeling that survives `_compute_horizon_signal` -> `horizon_details` -> `FoldMetrics`/JSON. Do not expose fallback-only candidates as plain `gated_alphas` without source metadata.
2. Add tests for structured fallback labeling and CLI flag parse/pass/persist behavior.

