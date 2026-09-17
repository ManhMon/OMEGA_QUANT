# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-14T20:05:39+07:00
**Gate**: FORMULAIC_ALPHA_V2_FIX1_20260614
**Submission**: l2_role14_formulaic_alpha_v2_fix1_20260614
**Tier 2 Engineer**: data-scientist (Role 14)
**Tier 3 Auditor**: compliance-officer (Role 20)

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Forbidden paths were not used as authoritative sources.

## Scope Reviewed

- `src/omega/quant/alpha/formulaic_alphas.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_formulaic_alpha_adapter.py`
- `data/phase35_results/phase35_backtest_results_formulaic_v2_smoke_baseline.json`
- `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v2_baseline.json`
- `.ly_state/session/l2_role14_formulaic_alpha_v2_20260614.md`
- `.ly_state/session/l2_role14_formulaic_alpha_v2_fix1_20260614.md`
- `.ly_state/session/audit_reports/role20_formulaic_alpha_v2_20260614.md`

## SOD Checks

- Writer != auditor verified: 14 != 20.
- L3 boundary observed: no production source/test/data edits by this audit.
- L2 report exists: `.ly_state/session/l2_role14_formulaic_alpha_v2_fix1_20260614.md`.
- Corrected L2 report lists exact repo-local role/skill evidence.
- Corrected L2 report explicitly states no authoritative reliance and marks every forbidden path as non-authoritative and not used as source.

## Implementation Checks

- V2 set `mean_reversion_liquidity` remains research-only opt-in via `--enable-formulaic-alphas` and CLI choice.
- Default behavior unchanged: `DEFAULT_FORMULAIC_ALPHA_SET == "small"`, CLI default is `"small"`, and engine `enable_formulaic_alphas` default is `False`.
- V2 has 8 candidates and excludes weak momentum `alpha_fml001_ts_rank_momentum_20`.
- New v2 candidates present: `alpha_fml052_close_zscore_mr_20`, `alpha_fml067_vol_price_diverge_10`, `alpha_fml078_range_compression_10`, `alpha_fml089_amihud_illiq_20`.
- PIT check passed: no `.shift(-...)` or `.shift(0)` in scoped source; v2 computations use lagged OHLCV/volume before rolling/ranking.
- No external data dependency, dynamic execution, unsafe deserialization, shell execution, or secret pattern found in scoped implementation.

## Test Execution

Command:

```powershell
python -m pytest tests/phase35/test_formulaic_alpha_adapter.py -q
```

Result: `71 passed`.

Warnings: SQLAlchemy/import deprecations and pytest cache path warning only; no failures.

## Backtest Artifact Checks

- Smoke JSON: `enable_formulaic_alphas=true`, `formulaic_alpha_set="mean_reversion_liquidity"`, 8 v2 formulaic alpha IC keys, 2 ordered folds, no non-finite numeric values.
- CPCV12 JSON: `enable_formulaic_alphas=true`, `formulaic_alpha_set="mean_reversion_liquidity"`, 8 v2 formulaic alpha IC keys, 12 ordered folds, no non-finite numeric values.
- Non-blocking research caveat remains: `alpha_fml089_amihud_illiq_20` has negative CPCV12 IC in the submitted artifact. Because v2 is opt-in research-only and defaults are unchanged, this does not block the gate.

## Forbidden Path Scan

No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## CODEX AUDIT VERDICT

**Status:** [APPROVED]
**Date:** 2026-06-14T20:05:39+07:00
**Auditor:** Codex L3 compliance-officer (Role 20)
**Scope:** FORMULAIC_ALPHA_V2_FIX1_20260614
**final_verdict:** [APPROVED]

### Compliance Checks

- [x] Writer != auditor verified
- [x] Scope compliance verified
- [x] Tests passed
- [x] PIT compliance verified
- [x] No look-ahead bias found in scoped implementation
- [x] No live/default behavior changes found
- [x] L2 repo-local skill source evidence verified
- [x] Forbidden paths treated as non-authoritative and not used as source

### Verdict Rationale

The corrected L2 report resolves the prior SOD wording blocker. The implementation remains research-only, opt-in, PIT-safe under scoped review, default behavior is unchanged, targeted tests pass, and smoke/CPCV12 artifacts are finite with ordered train/test splits.

**Signature:** Codex L3 Auditor
