# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-23T17:14:08+07:00
**Gate**: HYBRID_REGIME_LIGHTGBM_COMPLIANCE_20260623
**Submission**: l2_role14_hybrid_regime_lightgbm_integration_20260623
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [APPROVED]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/agent/data-scientist.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Note: `.agents/skills/sops/SKILL.md` references separate SOP detail files, but only `SKILL.md` exists in the repo-local `sops` skill directory. The embedded PIT/BACKTEST rules in `SKILL.md` were used.

## SOD Checks

- Writer != auditor verified: `l2_role_id=14` and `l3_role_id=20`.
- L2 role verified repo-local: `.agents/agent/data-scientist.md` has `role_id=14`, `tier=2`, `platform=OpenCode`.
- L3 role verified repo-local: `.agents/agent/compliance-officer.md` has `role_id=20`, `tier=3`, `platform=Codex`, `sod_boundary` present.
- L2 report present: `.ly_state/session/l2_role14_hybrid_regime_lightgbm_integration_20260623.md`.
- L2 report lists repo-local role/skill evidence and forbidden path scan.
- L3 did not edit production source or tests. L3 wrote only this audit report and updated this gate entry.

## Scope Check

Audited requested scope:

- `src/omega/quant/pipeline_v2.py`
- `scripts/backtest_hybrid_regime.py`

Additional L2-reported regression coverage:

- `tests/phase35/test_hybrid_regime_backtest_perf.py`

Working tree contains other modified/untracked files outside this compliance scope. They were not evaluated for this verdict.

## Verification

Required command:

```powershell
python scripts/backtest_hybrid_regime.py --quick-mode --dynamic-universe --symbol-count 10 --workers 1 --model-type lightgbm
```

Result: exit 0. LightGBM execution completed 5 CPCV folds without NaN training/prediction failure.

Focused regression command:

```powershell
pytest tests/phase35/test_hybrid_regime_backtest_perf.py
```

Result: `41 passed, 33 warnings in 10.91s`.

## PIT Safety Findings

- `pipeline_v2.py` warmup fetch now starts before requested `start_date` and trims output back to `[start_date, end_date]`, so warmup rows do not enter returned results.
- Fallback Ridge path shifts alpha inputs per symbol with `groupby("symbol")[signal_cols].shift(1)` before training/prediction.
- Rolling OOS fit uses `train_mask = panel_date_idx < t`; same-day requested returns are not included for date `t`.
- Predictions are generated one date at a time with `test_mask = panel_date_idx == t`.
- Regression test instruments Ridge fit/predict and asserts every train date precedes prediction date.
- `backtest_hybrid_regime.py` train data is restricted to CPCV `train_dates`; prediction lags are `shift(1)` per symbol.

Conclusion: the fallback Ridge rolling OOS training resolves the same-day/test-period training leakage issue under the audited path.

## LightGBM Compliance

- LightGBM uses bounded conservative settings: `n_estimators=100`, `learning_rate=0.03`, `num_leaves=15`, `min_child_samples=10`, `subsample=0.9`, `colsample_bytree=0.9`, fixed `random_state=42`, `n_jobs=1`.
- LightGBM path preserves NaN lag values for native missing-value handling.
- Ridge path still imputes NaN/inf values through `_feature_values()`.
- Optional dependency behavior is explicit: missing LightGBM raises `ImportError` for `--model-type lightgbm`.

Advisory, non-blocking: the live smoke output showed feature-selection fallback with zero displayed ICs. Future L2 work should compute ICs on finite pairs when LightGBM preserves NaNs, so feature ranking remains data-driven.

## Forbidden Path Scan

Scanned audited source files and L2 report for forbidden authoritative skill/role reliance. No authoritative reliance found.

Forbidden paths are non-authoritative and not used as sources:

- `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source)
- `.openclaw\skills` (non-authoritative, not used as source)
- `C:\Users\GHC\.agents` (non-authoritative, not used as source)
- `.codex\memories` (non-authoritative, not used as source)

## CODEX AUDIT VERDICT

**Status:** [APPROVED]
**Date:** 2026-06-23T17:14:08+07:00
**Auditor:** Codex L3, Role 20 compliance-officer
**Scope:** Hybrid regime LightGBM integration compliance and PIT safety

### Phase Gates

- **l3_session_id:** l3_role20_hybrid_regime_lightgbm_compliance_20260623
- **l3_session_key:** role20_hybrid_regime_lightgbm_compliance_20260623
- **audit_report_path:** .ly_state/session/audit_reports/role20_hybrid_regime_lightgbm_compliance_20260623.md
- **final_verdict:** [APPROVED]

### Findings

No blocking compliance findings.

### Compliance Checks

- [x] PIT compliance verified for audited warmup/Ridge OOS path
- [x] No same-day requested return used for date `t` model fit
- [x] LightGBM quick-mode execution passed
- [x] L2 repo-local source evidence verified
- [x] SOD boundary verified

**Signature:** Codex L3 Auditor
