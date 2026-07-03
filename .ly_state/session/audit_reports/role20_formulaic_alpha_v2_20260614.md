# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-14T19:58:31+07:00
**Gate**: FORMULAIC_ALPHA_V2_20260614
**Submission**: l2_role14_formulaic_alpha_v2_20260614
**Tier 2 Engineer**: data-scientist (Role 14)
**Tier 3 Auditor**: compliance-officer (Role 20)

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Linked SOP detail files referenced by `.agents/skills/sops/SKILL.md` are not present under `.agents/skills/sops/`; inline SOP text in `SKILL.md` was used. No forbidden-path fallback was used.

## SOD Checks

- Writer != auditor verified: 14 != 20.
- L3 boundary observed: no production source/test/data code edits by this audit.
- L2 report exists: `.ly_state/session/l2_role14_formulaic_alpha_v2_20260614.md`.
- L2 report lists repo-local role/skill evidence and forbidden path wording.
- Forbidden paths are non-authoritative and not used as source: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

## Scope Reviewed

- `src/omega/quant/alpha/formulaic_alphas.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_formulaic_alpha_adapter.py`
- `data/phase35_results/phase35_backtest_results_formulaic_v2_smoke_baseline.json`
- `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v2_baseline.json`
- `.ly_state/session/l2_role14_formulaic_alpha_v2_20260614.md`

## Audit Findings

Blocking SOD evidence finding:
- `.ly_state/session/l2_role14_formulaic_alpha_v2_20260614.md` lists forbidden paths as `NOT accessed`, but does not explicitly mark each as non-authoritative / not used as source. `scripts/sod_gate_enforcer.py` blocks the gate on this wording.

Implementation checks otherwise passed.

Evidence:
- V2 set `mean_reversion_liquidity` is research-only opt-in via CLI choice and `--enable-formulaic-alphas`.
- Default behavior unchanged: `DEFAULT_FORMULAIC_ALPHA_SET == "small"`, CLI default is `"small"`, engine `enable_formulaic_alphas` default is `False`.
- V2 has 8 candidates; `alpha_fml001_ts_rank_momentum_20` is excluded.
- New v2 candidates present: `alpha_fml052_close_zscore_mr_20`, `alpha_fml067_vol_price_diverge_10`, `alpha_fml078_range_compression_10`, `alpha_fml089_amihud_illiq_20`.
- PIT check passed: scoped source has no `.shift(-...)` or `.shift(0)`; v2 computations use lagged OHLCV/volume before rolling/ranking.
- Output sanitation passed: pytest finite-output tests passed; smoke and CPCV12 JSON numeric values are finite.
- No external data dependency added in scoped files; no dynamic execution, unsafe deserialization, shell execution, or secret patterns found in scoped files.
- CLI accepts `mean_reversion_liquidity`.

## Test Execution

Command:

```powershell
python -m pytest tests/phase35/test_formulaic_alpha_adapter.py -q
```

Result: `71 passed`.

Warnings: SQLAlchemy deprecation/import deprecation and pytest cache path warning only; no test failures.

## Backtest Artifact Checks

- Smoke JSON: `enable_formulaic_alphas=true`, `formulaic_alpha_set="mean_reversion_liquidity"`, 8 formulaic alpha ICs, 2 folds, all train/test splits ordered, no non-finite numeric values.
- CPCV12 JSON: `enable_formulaic_alphas=true`, `formulaic_alpha_set="mean_reversion_liquidity"`, 8 formulaic alpha ICs, 12 folds, all train/test splits ordered, no non-finite numeric values.

Non-blocking research caveat: `alpha_fml089_amihud_illiq_20` has negative CPCV12 IC in the submitted artifact. Because v2 is opt-in research-only and no promotion/default behavior is changed, this is not a gate blocker.

## Forbidden Path Scan

No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Date:** 2026-06-14T19:58:31+07:00
**Auditor:** Codex L3 compliance-officer (Role 20)
**Scope:** FORMULAIC_ALPHA_V2_20260614
**final_verdict:** [NEEDS_FIX]

### Compliance Checks

- [x] Writer != auditor verified
- [x] Scope compliance verified
- [x] Tests passed
- [x] PIT compliance verified
- [x] No look-ahead bias found in scoped implementation
- [x] No live/default behavior changes found
- [x] Repo-local skill source evidence verified
- [x] Forbidden paths treated as non-authoritative

### Verdict Rationale

The implementation satisfies the requested research-only v2 alpha set, keeps default/live behavior unchanged, passes targeted tests, and produces finite smoke/CPCV12 artifacts. The gate still needs an L2 report wording fix because SOD strict repo-local skill loading rejects forbidden-path mentions without explicit non-authoritative context markers.

### Required Actions

1. L2 must update `.ly_state/session/l2_role14_formulaic_alpha_v2_20260614.md` forbidden path scan wording to include `no authoritative reliance` and mark each forbidden path as `non-authoritative and not used as source`.
2. Resubmit for L3 re-audit after the L2 report is fixed.

**Signature:** Codex L3 Auditor
