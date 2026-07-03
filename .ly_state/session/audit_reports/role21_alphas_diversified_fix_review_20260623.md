# Code Review Audit Report

**Role**: code-reviewer (Role 21, Codex L3)
**Date**: 2026-06-23T19:44:57+07:00
**Gate**: HYBRID_REGIME_ALPHAS_DIVERSIFIED_FIX_20260623
**L2 Session**: l2_role14_alphas_diversified_fix_20260623
**L2 Role**: data-scientist (Role 14, OpenCode L2)
**Scope**: scripts/backtest_hybrid_regime.py

## Repo-Local Sources Read

- .agents/agent/code-reviewer.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/omega-sod/SKILL.md

## Forbidden Path Scan

No authoritative reliance found. Forbidden path mentions were limited to repo-local SOD contract text and L2 report evidence marked non-authoritative.

## SOD Checks

- Writer != Auditor: PASS (14 != 21)
- L3 boundary: PASS. No production source/test edits made by L3.
- L2 report source evidence: PASS.
- Scope compliance: PASS for requested review file.

## Code Checks

- IC std/corr fix: PASS. scripts/backtest_hybrid_regime.py:808-811 uses a finite mask and applies it to np.corrcoef; np.std was replaced by np.nanstd.
- GMM training log fix: PASS. scripts/backtest_hybrid_regime.py:900-904 converts value_counts items with int(v), avoiding the prior TypeError.
- PIT safety: PASS for these fixes. Both changes are train-fold local diagnostics/logging and do not introduce future data access.

## Test Results

- `python -m py_compile "scripts/backtest_hybrid_regime.py"`: PASS
- `python -m pytest`: FAIL

Failures:

1. tests/phase35/test_hybrid_regime_alpha_improvement.py::TestDiagnosticJSON::test_realized_alpha_improvement_from_backtest
   - Baseline completed only 5 folds; test requires >= 10.
2. tests/phase35/test_hybrid_regime_backtest_perf.py::TestPITLeakRegression::test_ridge_coefficients_match_fold_local_reference
   - composite_signal mismatch: observed -0.0014318196898691665 vs reference -0.0008984822699337905.

Summary: 2371 passed, 2 failed, 660 warnings.

## Verdict

[NEEDS_FIX]

Requested code fixes are present, but the gate cannot be approved while full test execution fails.
