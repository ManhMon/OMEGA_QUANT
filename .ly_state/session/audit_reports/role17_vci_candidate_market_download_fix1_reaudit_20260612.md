# QA Re-Audit Report: VCI Candidate Market Download Fix1

**Role**: QA Engineer (Role 17, L3 Codex)  
**Date**: 2026-06-12T23:59:00+07:00  
**Gate**: VCI_CANDIDATE_MARKET_DOWNLOAD_20260612  
**L2 Session**: l2_role15_vci_candidate_market_download_fix1_20260612  
**Tier 2 Engineer**: data-engineer (Role 15)  
**Verdict**: [APPROVED]

## Repo-Local Source Evidence

Role/skill files read from REPO_AGENT_ROOT / REPO_SKILL_ROOT only:

- `.agents/agent/qa-engineer.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/verify-changes/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`

Forbidden path scan result: no authoritative reliance on forbidden paths. Forbidden global/scratch sources were treated as non-authoritative only.

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=15`, `l3_role_id=17`).
- L3 role metadata: PASS (`role_id=17`, `tier=3`, `platform=Codex`, `sod_boundary` present).
- Original L2 report strict evidence: PASS. `_validate_l2_report_content(c, 15, 'data-engineer')` returned `(True, 'L2 report contains repo-local skill source evidence')`; `validate_forbidden_path_usage(c)` returned `(False, [])`.
- Fix1 L2 report strict evidence: PASS. `_validate_l2_report_content(c, 15, 'data-engineer')` returned `(True, 'L2 report contains repo-local skill source evidence')`; `validate_forbidden_path_usage(c)` returned `(False, [])`.
- L2 fix1 report lists exact repo-local role/skill files: PASS.
- Scope compliance: PASS; re-audit covered L2 reports, candidate/canonical parquet read-only validation, scripts read-only scope, target gate only.

## Commands Run

- Direct enforcer function checks for original and fix1 L2 reports via inline Python import of `scripts.sod_gate_enforcer`.
- Inline read-only pandas validation of `data/market_vci_candidate_20260612.parquet` versus `data/market_2015_now.parquet`.
- `python scripts/sod_gate_enforcer.py` before gate update: exit 1 only because `VCI_CANDIDATE_MARKET_DOWNLOAD_20260612: [NEEDS_FIX]`; no STRICT_REPO_LOCAL_SKILL_LOADING forbidden-path errors.

## Candidate Validation

- Candidate exists and loads: PASS, `1,763,089` rows, `14` columns.
- Canonical exists and loads: PASS, `1,687,749` rows, `14` columns.
- Schema vs canonical: PASS, ordered columns equal.
- Dtypes vs canonical: PASS.
- Exchange values: PASS, only `HNX` and `HOSE`.
- Duplicate `(ticker, date)`: PASS, `0`.
- Null OHLCV: PASS, `open=0`, `high=0`, `low=0`, `close=0`, `volume=0`.
- Date range: candidate `2011-03-15` to `2026-06-12`; canonical `2015-01-05` to `2026-06-12`.
- PIT/date safety: PASS; no candidate date beyond current/canonical max date `2026-06-12`.
- Ticker coverage: candidate `665`, canonical `666`; missing canonical ticker remains documented as `BTW`.
- Canonical not overwritten: PASS; canonical row count remains `1,687,749`, distinct from candidate `1,763,089`.

## Verdict

[APPROVED] - Fix1 resolves the prior STRICT_REPO_LOCAL_SKILL_LOADING evidence blocker, candidate data spot checks pass, writer/auditor separation holds, and pre-update enforcer is blocked only by the target gate's prior `[NEEDS_FIX]` status.
