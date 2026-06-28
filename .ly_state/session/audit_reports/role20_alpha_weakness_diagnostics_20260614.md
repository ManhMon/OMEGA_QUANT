# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)  
**Date**: 2026-06-14  
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614  
**L2 Session**: l2_role14_alpha_weakness_diagnostics_20260614  
**L2 Role**: data-scientist (Role 14)  
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Referenced SOP detail files named by `sops/SKILL.md` were not present at `.agents/skills/sops/SOP_AC.md`, `.agents/skills/sops/SOP_PIT_SAFETY.md`, or `.agents/skills/sops/SOP_FIX_0_RETURN.md`. Core required role and skill source files above were read from repo-local paths only.

## Forbidden Path Scan

All forbidden paths are non-authoritative and not referenced: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

## Evidence

- Writer/auditor separation: PASS (`l2_role_id=14`, `l3_role_id=20`).
- L2 report source evidence: PASS; `.ly_state/session/l2_role14_alpha_weakness_diagnostics_20260614.md` lists repo-local L2 role and skill files plus forbidden path scan.
- Tests: PASS; `python -m pytest tests/test_analyze_alpha_weakness.py -q` -> `29 passed, 1 warning`.
- Script run: PASS; `python scripts/analyze_alpha_weakness.py --input-dir data/phase35_results/ab_guard_20260614_101727 --output .ly_state/session/alpha_weakness_diagnostics_20260614_audit.md` completed and wrote the audit reproduction report.
- Scope: PASS for diagnostics-only files; no production model behavior changes detected in reviewed code.
- PIT safety: PASS for direct leakage risk; script reads already-produced fold JSON and emits aggregate diagnostics, with no feature construction, model training, split generation, or `.shift(-1)`/future-data access.
- SOD enforcer: BLOCKED as expected; `python scripts/sod_gate_enforcer.py` reports `ALPHA_WEAKNESS_DIAGNOSTICS_20260614: [NEEDS_FIX]`.
## Findings

1. HIGH - System recommendation hard-codes incorrect fallback rates.
   - Location: `scripts/analyze_alpha_weakness.py:642` and `scripts/analyze_alpha_weakness.py:645`.
   - Evidence: reproduced report shows fallback table values of Baseline `5/8 (62.5%)`, RA + Guard `7/8 (87.5%)`, RA + No Guard `7/8 (87.5%)` at `.ly_state/session/alpha_weakness_diagnostics_20260614_audit.md:75-77`, but system recommendations state `100% fallback rate` and `100% fallback-to-baseline` at lines `226-227`.
   - Impact: the diagnostics report can drive incorrect gate-tuning decisions and overstate guard failure severity.

2. MEDIUM - Guard false-positive classification uses post-fallback fold portfolio metrics rather than rejected RA basket outcome.
   - Location: `scripts/analyze_alpha_weakness.py:267-271`.
   - Evidence: the code increments false positives when `portfolio_sharpe > 1.0` and `portfolio_ic > 0` after `FALLBACK_TO_BASELINE`. In the reproduced report, rejected folds are labeled false positives while the fold portfolio metrics reflect the fallback/baseline result, not the rejected RA basket outcome (`.ly_state/session/alpha_weakness_diagnostics_20260614_audit.md:89-98`).
   - Impact: false-positive count can mischaracterize the guard as wrong when it may have correctly avoided an underperforming selected basket.

## Required Fixes

1. Replace hard-coded system-level fallback statements with computed values from `variants[*]["fallback_rate"]` and `guard_analysis["guard_fallback_to_baseline"] / guard_enabled_folds`; add tests covering non-100% real or fixture fallback rates.
2. Redefine guard false-positive logic using metrics for the rejected RA basket, or rename the current metric to clearly state it is based on post-fallback portfolio performance; add tests that distinguish selected basket IC, baseline basket IC, and realized fold metrics.

## Verdict

[NEEDS_FIX]
