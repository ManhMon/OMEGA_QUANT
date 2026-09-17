# Compliance Audit Report
**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-22T23:02:37+07:00
**Gate**: HYBRID_REGIME_BACKTEST_PERF_20260621
**Submission**: l2_role14_tcost_rebalance_opt_fix_20260622
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read
- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Referenced but missing under repo-local `sops`: `SOP_AC.md`, `SOP_BACKTEST.md`, `SOP_PIT_SAFETY.md`. Inline SOP content in `sops/SKILL.md` was used.

## SOD Checks
- L2 role: 14 `data-scientist`, tier 2, platform OpenCode.
- L3 role: 20 `compliance-officer`, tier 3, platform Codex, `sod_boundary` present.
- Writer != auditor: PASS, 14 != 20.
- L3 write boundary: PASS, no source/test files modified by auditor.
- L2 report present: `.ly_state/session/l2_role14_tcost_rebalance_opt_fix_20260622.md`.
- L2 repo-local skill evidence: PASS, report lists `.agents/agent/data-scientist.md` and 9 repo-local skills.
- Forbidden path scan: PASS for authoritative reliance. Forbidden paths appear only as non-authoritative scan evidence in the L2 report.

## Scope Review
- Approved scope: `scripts/backtest_hybrid_regime.py`, `src/omega/quant/pipeline_v2.py`, `scripts/run_backtest.py`.
- Current working diff includes `src/omega/quant/pipeline_v2.py`, `scripts/run_backtest.py`, and `.ly_state/session/phase_gates.json`.
- `scripts/backtest_hybrid_regime.py` is untracked (`git ls-files` returns no entry; `git status --short` shows `?? scripts/backtest_hybrid_regime.py`). Current content was reviewed for the reported PIT lag logic, but L2 must ensure the intended script is tracked with the final change set.

## Test Evidence
- `python -m py_compile scripts/backtest_hybrid_regime.py src/omega/quant/pipeline_v2.py scripts/run_backtest.py`: PASS.
- `git diff --check -- scripts/backtest_hybrid_regime.py src/omega/quant/pipeline_v2.py scripts/run_backtest.py`: PASS.
- `python -m pytest tests/test_pipeline_v2.py::test_adaptive_sizing_overlay_uses_prior_expanding_adv -q`: FAIL.
- `python -m pytest`: FAIL, 4 failed, 2358 passed, 630 warnings in 135.89s.

Full-suite failures:
- `tests/phase35/test_hybrid_regime_alpha_improvement.py::TestDiagnosticJSON::test_realized_alpha_improvement_from_backtest`
- `tests/test_pipeline_v2.py::test_trading_pipeline_v2_backtest`
- `tests/test_pipeline_v2.py::test_signal_overlays_use_prior_day_scores`
- `tests/test_pipeline_v2.py::test_adaptive_sizing_overlay_uses_prior_expanding_adv`

## Findings

### 1. BLOCKING: AdaptiveSizingOverlay still leaks future ADV and breaks the PIT contract
Location: `src/omega/quant/pipeline_v2.py:289-295`

The implementation computes a shifted expanding ADV per row, then collapses it with:

```python
adv_series = _sorted.groupby("symbol")["_adv_expanding"].mean()
```

This returns a symbol-level Series, not a date x symbol DataFrame. The collapse uses the whole sample to produce one liquidity limit per symbol, so early backtest dates still receive information from later rows through the aggregate mean. It also breaks the existing contract expected by `tests/test_pipeline_v2.py:246-272`, which verifies that first-date ADV is NaN and later dates use only prior observations.

Evidence:
- Targeted test fails with `pandas.errors.IndexingError: Too many indexers` because the captured ADV object is a Series.
- The portfolio sizing function already supports a PIT-safe DataFrame path at `src/omega/quant/portfolio/adaptive_sizing_overlay.py:123-127`.
- The modular overlay implementation shows the expected pattern at `src/omega/quant/pipeline/overlays/adaptive_sizing.py:19-29`.

Required fix:
- Return a date x symbol ADV DataFrame aligned to `weights.index` and `weights.columns`.
- Compute per-symbol expanding mean with `shift(1)` before pivot/reindex.
- Keep first date per symbol as NaN so liquidity defaults do not inject current-day information.

### 2. BLOCKING: Required full test suite is not green
Location: test command `python -m pytest`

The gate contract requires running all tests. Full suite currently fails. At least one failure is directly tied to this L2 submission (`test_adaptive_sizing_overlay_uses_prior_expanding_adv`). Gate approval is blocked until the suite is green or failures are formally scoped as pre-existing with evidence.

### 3. BLOCKING: `hybrid-regime` CLI mode points at an untracked production script
Location: `scripts/run_backtest.py:62`, `scripts/backtest_hybrid_regime.py`

The new `hybrid-regime` CLI mapping points to `scripts/backtest_hybrid_regime.py`, but that target is currently untracked. If the tracked change set includes only `scripts/run_backtest.py`, the new mode will fail after commit/merge because the target script is absent from version control.

Required fix:
- Add/track the intended `scripts/backtest_hybrid_regime.py` file, or map only to a tracked target.
- Re-run the script existence check from a clean tracked checkout before re-audit.

## PIT Safety Review
- `scripts/backtest_hybrid_regime.py:744-764`: training lags use per-symbol `shift(1)` on train-only data and preserve NaN first rows before dropping them. No blocking PIT issue found in current content.
- `scripts/run_backtest.py:41-90`: static mode mapping and subprocess forwarding; no PIT issue found.
- `src/omega/quant/pipeline_v2.py:289-295`: NOT PIT-safe due date-axis collapse described above.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Date:** 2026-06-22T23:02:37+07:00
**Auditor:** Codex L3, Compliance Officer role 20
**Scope:** `scripts/backtest_hybrid_regime.py`, `src/omega/quant/pipeline_v2.py`, `scripts/run_backtest.py`

### Phase Gates
- **l3_session_id:** l3_role20_tcost_rebalance_opt_fix_20260622
- **l3_session_key:** role20_tcost_rebalance_opt_fix_20260622
- **audit_report_path:** .ly_state/session/audit_reports/role20_tcost_rebalance_opt_fix_20260622.md
- **final_verdict:** [NEEDS_FIX]

### Required Actions
1. Fix `AdaptiveSizingOverlay` in `src/omega/quant/pipeline_v2.py` to pass a PIT-safe date x symbol ADV DataFrame to `apply_adaptive_sizing`.
2. Re-run `python -m pytest tests/test_pipeline_v2.py::test_adaptive_sizing_overlay_uses_prior_expanding_adv -q`.
3. Ensure `scripts/backtest_hybrid_regime.py` is tracked if `scripts/run_backtest.py` maps to it.
4. Re-run `python -m pytest`; resolve or evidence-scope all remaining failures before re-audit.

**Signature:** Codex L3 Auditor, Role 20 Compliance Officer
