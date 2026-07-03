# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-22T20:10:41+07:00
**Gate**: HYBRID_REGIME_BACKTEST_PERF_20260621
**L2 Session**: l2_role14_tcost_rebalance_opt_20260622
**Tier 2 Engineer**: data-scientist (Role 14)
**L3 Session**: l3_role20_tcost_rebalance_opt_20260622

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `.agents/agent/data-scientist.md`

Note: `.agents/skills/sops/SKILL.md` references `SOP_AC.md`, `SOP_BACKTEST.md`, and `SOP_PIT_SAFETY.md`, but those referenced files are not present under `.agents/skills/sops/`. Inline SOP content in `SKILL.md` was used.

## Forbidden Path Scan

No authoritative reliance found on forbidden paths. Mentions of forbidden paths appear only as non-authoritative scan evidence or policy text:

- `.gemini\antigravity-ide\scratch\ag-kit`
- `.openclaw\skills`
- `C:\Users\GHC\.agents`
- `.codex\memories`

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=14`, `l3_role_id=20`)
- L3 boundary: PASS, no production source files modified by this audit
- L2 report present: PASS (`.ly_state/session/l2_role14_tcost_rebalance_opt_20260622.md`)
- L2 repo-local source evidence: FAIL, incomplete declared skill loading
- Scope compliance: FAIL, out-of-scope modified file detected
- Tests: FAIL, full pytest suite has failures
- PIT safety: FAIL, PIT regression test currently fails

## Findings

1. HIGH - PIT regression failure blocks approval.
   - Evidence: `python -m pytest` failed at `tests/phase35/test_hybrid_regime_backtest_perf.py:523`.
   - Failure: `train_fold_models` prediction differs from fold-local Ridge reference (`-0.0008535344708131623` vs `-0.0008984822699337905`).
   - Relevant implementation area: `scripts/backtest_hybrid_regime.py:755` fills train lag NaNs with `0.0`, changing the fold-local training matrix expected by the PIT regression.
   - Impact: cannot confirm no look-ahead / fold-local training behavior for the hybrid backtest path.

2. HIGH - Full test suite is not passing.
   - Command: `python -m pytest`
   - Result: `5 failed, 2357 passed, 630 warnings in 132.63s`.
   - Failures:
     - `tests/phase35/test_hybrid_regime_alpha_improvement.py:488`
     - `tests/phase35/test_hybrid_regime_backtest_perf.py:523`
     - `tests/test_pipeline_v2.py::test_trading_pipeline_v2_backtest`
     - `tests/test_pipeline_v2.py::test_signal_overlays_use_prior_day_scores`
     - `tests/test_pipeline_v2.py::test_adaptive_sizing_overlay_uses_prior_expanding_adv`

3. MEDIUM - Approved scope mismatch.
   - Approved scope: `src/omega/quant/pipeline/overlays/rebalance_frequency.py`, `src/omega/quant/pipeline/overlays/__init__.py`, `scripts/backtest_hybrid_regime.py`.
   - Worktree also has `scripts/run_backtest.py:55` modified (`"hybrid-regime": "backtest_hybrid_regime.py"`).
   - L2 report lists only the three approved files at lines 29-35 and omits `scripts/run_backtest.py`.
   - Impact: scope compliance cannot be approved until L1 expands scope or L2 removes/documents the change.

4. MEDIUM - L2 did not load all declared repo-local skills.
   - `.agents/agent/data-scientist.md` declares 9 skills.
   - L2 report lists only 4 skills loaded: `backtesting-pit-safety`, `python-patterns`, `quant-research`, `clean-code`.
   - Missing from L2 evidence: `testing-patterns`, `systematic-debugging`, `performance-profiling`, `vietnam-market-data`, `data-science-workflow`.
   - Impact: violates STRICT_REPO_LOCAL_SKILL_LOADING_20260612 loading protocol for L2 dispatches.

## Verification

- Syntax check: PASS
  - `python -m py_compile src/omega/quant/pipeline/overlays/rebalance_frequency.py src/omega/quant/pipeline/overlays/__init__.py scripts/backtest_hybrid_regime.py`
- Import smoke with `PYTHONPATH=src`: import printed `import ok True`, but command timed out after 10s during import side effects.
- Full tests: FAIL
  - `python -m pytest`

## Verdict

[NEEDS_FIX]

Required before re-audit:

1. Fix `tests/phase35/test_hybrid_regime_backtest_perf.py::TestPITLeakRegression::test_ridge_coefficients_match_fold_local_reference`.
2. Fix `tests/phase35/test_hybrid_regime_alpha_improvement.py::TestDiagnosticJSON::test_realized_alpha_improvement_from_backtest`.
3. Resolve or document the out-of-scope `scripts/run_backtest.py` change through L1 scope expansion or L2 cleanup.
4. Regenerate L2 report with complete repo-local role/skill evidence for all declared `data-scientist` skills.
5. Re-run full pytest and submit passing evidence.
