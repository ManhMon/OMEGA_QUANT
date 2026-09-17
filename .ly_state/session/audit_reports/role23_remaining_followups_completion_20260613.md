# Performance Test Audit Report

**Role**: 23 performance-tester (Codex L3)
**Date**: 2026-06-13T23:09:09+07:00
**Gate**: REMAINING_FOLLOWUPS_COMPLETION_20260613
**L2 Session**: l2_role16_remaining_followups_completion_20260613
**L2 Role**: 16 machine-learning-engineer
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/performance-tester.md`
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

Forbidden path scan: CLEAN - forbidden paths are non-authoritative and not used as source.

## SOD Checks

- Writer != auditor: PASS (`16 != 23`).
- L3 role spec: PASS (`role_id=23`, `tier=3`, `platform=Codex`, `sod_boundary` present).
- L2 role spec: PASS (`role_id=16`, `tier=2`, `platform=OpenCode`).
- L2 report repo-local evidence: PASS; report lists `.agents/agent/machine-learning-engineer.md` plus declared repo-local skills and a clean forbidden path scan.
- L3 write boundary: PASS; no production source edits by L3. Audit report and gate metadata only.

## Test Evidence

| Command | Result |
|---|---|
| `python -m pytest tests/test_feature_adapter_nonnumeric.py -q` | PASS, 9 passed |
| `python -m pytest tests/test_dashboard_data_control_integration.py -q` | PASS, 106 passed |
| `python scripts/run_backtest.py evolution-integration` | PASS, 6/6 checks |
| `python scripts/run_backtest.py evolution-multiseed --help` | PASS, shows `--workers` and `--quick` |
| `python scripts/run_backtest.py evolution-multiseed --quick` | FAIL, default `GP n_jobs=9`; all seeds fail with `[WinError 5] Access is denied`; exits with `ZeroDivisionError` |
| `python scripts/run_backtest.py evolution-multiseed --quick --workers 1` | PASS, 10/10 years completed, win rate 5/10 |
| `python scripts/run_backtest.py evolution-multiseed --quick --workers 2` | FAIL, all seeds fail with `[WinError 5] Access is denied`; exits with `ZeroDivisionError` |
| `python scripts/run_backtest.py full-pipeline` | PASS, Sharpe 1.6795, MaxDD -4.55%, duration 0.596s |

## Findings

1. BLOCKER - Required quick mode does not work with default worker selection.
   - Evidence: `python scripts/run_backtest.py evolution-multiseed --quick` fails on this machine.
   - Root cause evidence: `scripts/backtest_evolution_multiseed.py:145-146` defaults to `compute_safe_workers()`, producing `GP n_jobs=9`; `src/omega/quant/evolution/genetic_engine.py:583-584` then enters joblib parallel evaluation; every seed fails with `[WinError 5] Access is denied`.
   - Impact: L2's claimed verification that quick mode completes is not reproducible under the required command.

2. BLOCKER - No-results path crashes instead of returning a controlled failure.
   - Evidence: after all seeds fail, `scripts/backtest_evolution_multiseed.py:278` divides by `len(results)` when `results == []`, causing `ZeroDivisionError`.
   - Impact: failures are converted into an unhandled traceback, and CI/operator output cannot distinguish infrastructure failure from strategy failure.

3. HIGH - Explicit `--workers` is not safely capped.
   - Evidence: `scripts/backtest_evolution_multiseed.py:141-142` uses `n_jobs = max(1, args.workers)` for user input. This bypasses `compute_safe_workers()` and accepts arbitrarily large values.
   - Impact: the `--workers safe` requirement is not met. Even `--workers 2` fails here; larger values can oversubscribe the machine.

## Passed Checks

- Streamlit deprecation cleanup: PASS. `Select-String` found no remaining `use_container_width` in `apps/dashboard`; Streamlit 1.56 signatures support `width` for `st.dataframe`, `st.plotly_chart`, and `st.button`.
- Width replacements: PASS for the inspected API calls; `width="stretch"` is present across dashboard files.
- Phase35 verdict: PASS. `.ly_state/session/phase35_production_readiness_20260613.md` is evidence-based `NOT_PRODUCTION_READY`, citing failed CPCV, negative/weak evolution metrics, drawdowns, PIT notes, cost caveat, and shadow-only criteria.
- PIT regression: PASS for scoped changes. Multiseed feature lag remains T-1 (`groupby(...).shift(1)`), target remains forward return, chronological yearly train/test split is unchanged, and dashboard changes are UI-only.
- Full runtime documentation: PARTIAL PASS. Full mode prints `20-60 min` guidance; however the default quick command fails before delivering usable smoke-test evidence.

## Required Fix

- Make `python scripts/run_backtest.py evolution-multiseed --quick` pass with default settings on Windows.
- Handle zero successful years/seeds with a controlled nonzero exit and clear error message, not `ZeroDivisionError`.
- Cap/sanitize explicit `--workers` against `compute_safe_workers()` or an equivalent hard ceiling; document fallback behavior.
- Re-run the required command list after fixes.

## Verdict

[NEEDS_FIX]
