# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)
**Date**: 2026-06-15T13:50:54.5514065+07:00
**Gate**: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
**L2 Session**: l2_role14_nonredundant_alpha_generation_dynamic_20260615
**L2 Role**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Forbidden path scan: no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## SOD Checks

- Writer != auditor: PASS, 14 != 20.
- L3 write boundary: PASS, only this audit report and target `phase_gates.json` entry updated.
- L2 report present: PASS, `.ly_state/session/l2_role14_nonredundant_alpha_generation_dynamic_20260615.md` exists and lists repo-local role/skill files.
- Scope: Reviewed scoped files only for verdict evidence.

## Test Evidence

- `python -m pytest tests/phase35/test_nonredundant_alphas.py -q`: PASS, 32/32.
- `python -m pytest tests/phase35 -q`: PASS, 685/685.
- JSON evidence file is syntactically serializable: PASS.

## Blocking Findings

1. PIT T-1 per-ticker lag is not actually per-ticker for return-based NR alphas.

   Locations: `src/omega/quant/alpha/nonredundant_alphas.py:227`, `:366`, `:402`, `:434`, `:462`.

   These lines use `df.groupby(symbol_col)[close_col].pct_change().shift(1)`. The final `.shift(1)` is applied to the whole Series after `pct_change()`, not within each ticker group. Because `compute_nonredundant_alphas()` sorts by `[symbol_col, date_col]` at `src/omega/quant/alpha/nonredundant_alphas.py:558`, the first row of ticker B can receive the last return from ticker A. That violates the claimed per-ticker T-1 rule and can leak a later A-date return into an earlier B-date row.

   Reproduction from audit scratch execution:
   `global_shift: [nan, nan, 0.10000000000000009, nan]` vs expected per-group shift `group_shift: [nan, nan, nan, nan]` for two tickers with two dates.

   Required fix: shift within ticker groups, e.g. compute returns then `groupby(symbol).shift(1)` or equivalent, and add a boundary test proving first row of every ticker has no prior ticker contamination.

2. Required per-fold nonredundant alpha evidence is not persisted.

   Locations: `src/omega/quant/alpha/phase35.py:193-194`, `src/omega/quant/alpha/phase35.py:3718-3747`, `scripts/run_phase35_backtest.py:105-108`, `data/phase35_results/phase35_backtest_results_nonredundant_v1_baseline.json`.

   `FoldMetrics` defines `nonredundant_alpha_evidence`, and the serializer writes it when non-null, but `FoldMetrics(...)` never populates it. Audit parse of the baseline JSON found `folds=12`, `folds_with_nonredundant_alpha_evidence=0`, while `config.enable_nonredundant_alphas=true` and 10 `alpha_nr_*` ICs are present. This fails the requested evidence persistence check.

   Required fix: populate serializable per-fold evidence when NR alphas are enabled, including gate id, enabled flag, set name, max candidates, computed columns/count, sector-map/fallback status, PIT-safe flag, and any fallback reason. Regenerate the baseline JSON after fixing.

## Non-Blocking Observations

- Default-off CLI behavior is present via `--enable-nonredundant-alphas` using `store_true`.
- Metric framing is appropriately research-only/do-not-promote: mean Portfolio IC degrades from 0.0249 baseline to 0.0092 NR v1.
- Sector map fallback handles missing files by returning `None` and using market-relative residual logic.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Rationale:** Tests pass, but PIT per-ticker lag is violated in return-based alpha formulas and required per-fold NR evidence is absent from the generated result artifact. Gate cannot approve until L2 fixes both issues and reruns evidence/tests.

