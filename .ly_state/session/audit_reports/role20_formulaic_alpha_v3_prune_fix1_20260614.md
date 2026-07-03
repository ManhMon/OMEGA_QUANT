# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)
**Date**: 2026-06-14T20:28:04+07:00
**Gate**: FORMULAIC_ALPHA_V3_PRUNE_FIX1_20260614
**L2 Session**: l2_role14_formulaic_alpha_v3_prune_fix1_20260614
**L2 Role**: data-scientist (Role 14)
**Verdict**: [APPROVED]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Forbidden path scan: no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## SOD Checks

- Writer != auditor verified: L2 role 14 != L3 role 20.
- L3 boundary observed: no production source, test, data, or script edits by L3.
- L3 writes limited to this audit report and the FORMULAIC_ALPHA_V3_PRUNE_FIX1_20260614 gate metadata entry.
- L2 report lists repo-local skill source evidence and corrected forbidden-path wording.

## Scope Review

- `src/omega/quant/alpha/formulaic_alphas.py`: v3 registry retains 5 candidates at lines 98-110; default remains `small` at line 114; ablation metadata is exposed by `get_v3_ablation_report()` at lines 874-951.
- `scripts/run_phase35_backtest.py`: v3 is opt-in through `--enable-formulaic-alphas` and `--formulaic-alpha-set v3_pruned` at lines 287-314; formulaic alpha columns are appended only when enabled at lines 495-500.
- `data/phase35_results/formulaic_v3_ablation_report.json`: v3 retains 5 candidates and excludes `alpha_fml033_vol_vol_interact_10`, `alpha_fml078_range_compression_10`, and `alpha_fml089_amihud_illiq_20`; flags show PIT-safe, deterministic, default unchanged.
- `data/phase35_results/phase35_backtest_results_cpcv12_formulaic_v3_full_xgboost.json`: full run verified, not smoke: `n_folds=12`, `n_folds_executed=12`, `quick_mode=false`, `top_n_symbols=30`, `train_years=3`, `test_years=1`, `fold_details=12`.

## PIT / Backtest Checks

- PIT lagging verified by source inspection: formulaic computations use grouped `shift(1)`/historical lags; no negative shift pattern found in scoped tests/source check.
- Fold chronology verified from full CPCV JSON: every `train_end < test_start`.
- Full CPCV metrics finite: all portfolio metrics and alpha IC values in 12 fold details are finite.
- Formulaic v3 alpha count in full result is 5: `alpha_fml052_close_zscore_mr_20`, `alpha_fml012_mean_rev_rank_10`, `alpha_fml045_liq_turnover_5`, `alpha_fml067_vol_price_diverge_10`, `alpha_fml006_vp_corr_10`.

## Test Evidence

Command run:

```powershell
python -m pytest tests/phase35/test_formulaic_alpha_adapter.py -q
```

Result: 105 passed. Warnings only: deprecation warnings and pytest cache path warning.

## Statistical Validation

Reviewed `.ly_state/session/cpcv12_formulaic_v3_full_stat_validation_report_20260614.md`.

- Avg Portfolio IC: -0.0028.
- Positive IC rate: 5/12 (41.7%).
- Research alpha gates: 12/12 alphas classified `RETIRE`.
- Statistical validation verdict: `FAIL`.
- Promotion blocker: alpha pool mean IC below 0.02 gate.

Compliance marking: `DO_NOT_PROMOTE`. This approval covers only research-only opt-in implementation/evidence correctness. It does not approve production/live promotion.

## Findings

No blocking findings.

Residual risk: v3 candidate evidence remains weak and unstable; full CPCV12 validation supports research-only retention with `DO_NOT_PROMOTE`, not deployment.

## CODEX AUDIT VERDICT

**Status:** [APPROVED]
**Date:** 2026-06-14T20:28:04+07:00
**Auditor:** Codex L3 compliance-officer role 20
**Scope:** Formulaic alpha v3 prune fix1 report/evidence, v3 opt-in wiring, CPCV12 full artifact, PIT/stat validation.

### Phase Gates

- **l3_session_id:** l3_role20_formulaic_alpha_v3_prune_fix1_20260614
- **l3_session_key:** role20_formulaic_alpha_v3_prune_fix1_20260614
- **audit_report_path:** .ly_state/session/audit_reports/role20_formulaic_alpha_v3_prune_fix1_20260614.md
- **final_verdict:** [APPROVED]
- **promotion_status:** DO_NOT_PROMOTE

### Compliance Checks

- [x] PIT compliance verified
- [x] No look-ahead bias found in scoped review
- [x] Full CPCV12 artifact has 12 executed folds
- [x] Default/live behavior unchanged
- [x] V3 is research-only opt-in
- [x] SOD writer/auditor separation verified
- [x] Repo-local skill source contract verified

### Verdict Rationale

Implementation and evidence satisfy the fix1 audit checks. Statistical evidence is weak, so the gate is approved only as research-only with `DO_NOT_PROMOTE` for live/default promotion.

**Signature:** Codex L3 Auditor, Role 20 compliance-officer
