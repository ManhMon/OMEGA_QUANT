# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-23T08:11:25+07:00
**Gate**: HYBRID_REGIME_BACKTEST_PERF_FIX2_COMPLIANCE_20260623
**L3 Session**: l3_role20_hybrid_regime_backtest_perf_fix2_compliance_20260623
**L2 Session**: l2_role14_tcost_rebalance_opt_fix2_20260623
**L2 Role**: data-scientist (Role 14)
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

Note: `.agents/skills/sops/SOP_AC.md`, `.agents/skills/sops/SOP_BACKTEST.md`, and `.agents/skills/sops/SOP_PIT_SAFETY.md` are referenced by the sops index but are not present. Embedded SOP content in `sops/SKILL.md` was used.

## Forbidden Path Scan

No authoritative reliance found on forbidden paths. L2 report marks these as non-authoritative and not relied on:

- `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative)
- `.openclaw\skills` (non-authoritative)
- `C:\Users\GHC\.agents` (non-authoritative)
- `.codex\memories` (non-authoritative)

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=14`, `l3_role_id=20`)
- L2 platform/role: PASS (`data-scientist`, tier 2, OpenCode)
- L3 platform/role: PASS (`compliance-officer`, tier 3, Codex, `sod_boundary` present)
- L3 write boundary: PASS; only this audit report and target gate entry are written
- L2 report repo-local evidence: PASS; report lists `REPO_AGENT_ROOT\data-scientist.md` and nine repo-local skill files

## Scope Checks

- `scripts/backtest_hybrid_regime.py`: in scope
- `tests/phase35/test_hybrid_regime_backtest_perf.py`: in scope
- Current working tree contains unrelated dirty files; this audit does not approve them.

## Implementation Checks

- `TOP_K = 7` verified in `train_fold_models()` at `scripts/backtest_hybrid_regime.py:780`.
- Training alpha lags are computed per fold from `train_feat` only via `groupby("symbol").shift(1)`.
- Global `precompute_alpha_lags()` remains deprecated and unused by `main()`.
- Prediction lag precompute uses backward-only `shift(1)`.
- No look-ahead bias found in the audited TOP_K path.

## PIT Safety

PASS for audited code path:

- `load_raw_data()` filters the requested historical period and does not fit models.
- `generate_features()` loads/merges precomputed features, then downstream training applies T-1 alpha lags.
- `train_fold_models()` filters to `train_dates` before fitting HMM, GMM, Ridge, IC selection, and regime models.
- Ridge IC selection and fitting use lagged alpha columns from train-only rows.
- CPCV held-out gap leakage is covered by regression tests.
- Backtest artifact reports `pit_safe: true`.

Residual note: full-period feature loading is acceptable here because model fitting and alpha usage are lagged/fold-scoped. This audit did not revalidate upstream generation of `data/precomputed_alpha_features.parquet`.

## Tests Run

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -v --tb=short -p no:cacheprovider
```

Result:

```text
30 passed, 2 warnings in 9.60s
```

Warnings were dependency deprecations, not failures.

## Backtest Artifact Check

- Artifact: `data/phase35_results/alpha_improvement_real_20260623_075617.json`
- SHA-256: `A1E2465BAE1C35EEB50AD40C185B6B1734083157D4CBA46C1D36EBFAB7E366E7`
- `measurement_type`: `REALIZED_45_FOLD_CPCV`
- `alpha_group`: `hybrid_regime`
- `alpha_columns_missing`: `[]`
- `pit_safe`: `true`
- `n_folds_total`: `45`
- Hybrid mean gross: `1.6525660034666059%`
- Hybrid mean net: `-6.484165987508934%`
- Net improvement: `33.70966188900053%`
- Gross target met: `false`

## JSON Gate State

`python -m json.tool .ly_state\session\phase_gates.json` passes. The earlier malformed JSON blocker has been resolved before this verdict.

## CODEX AUDIT VERDICT

**Status:** [APPROVED]
**Reason:** TOP_K implementation, scoped tests, PIT safety checks, repo-local source evidence, and gate JSON parse check pass for this compliance gate.

**Signature:** Codex L3 Compliance Officer
