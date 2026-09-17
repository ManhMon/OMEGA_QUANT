# QA Audit Report: VCI Candidate Market Download

**Role**: QA Engineer (Role 17, L3 Codex)  
**Date**: 2026-06-12T23:49:00+07:00  
**Gate**: VCI_CANDIDATE_MARKET_DOWNLOAD_20260612  
**L2 Session**: l2_role15_vci_candidate_market_download_20260612  
**Tier 2 Engineer**: data-engineer (Role 15)  
**Verdict**: [NEEDS_FIX]

## Repo-Local Source Evidence

Role/skill files read from REPO_AGENT_ROOT / REPO_SKILL_ROOT only:

- `.agents/agent/qa-engineer.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/verify-changes/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`

Forbidden path scan result: no authoritative reliance on forbidden paths by this L3 audit. Exact role/skill sources used by L3 are the repo-local files listed above.

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=15`, `l3_role_id=17`).
- L3 role metadata: PASS (`role_id=17`, `tier=3`, `platform=Codex`, `sod_boundary` present).
- L2 report source evidence: NEEDS_FIX; report lists `.agents/agent/data-engineer.md` and six repo-local skill files under `.agents/skills/.../SKILL.md`, but its forbidden-path evidence lines are rejected by `scripts/sod_gate_enforcer.py` because each forbidden path mention lacks the required `non-authoritative` context marker.
- Scope compliance: PASS; audit covered candidate parquet, scripts, stats/validation JSON, L2 report, and target gate only.

## Commands Run

- `python scripts/sod_gate_enforcer.py` before gate update: exit 0, `[PASS] SAFE TO PUSH`, 113 phases verified, advisory legacy warnings only.
- `python scripts/sod_gate_enforcer.py` after gate update: exit 1, blocked on target gate because the L2 report forbidden-path evidence does not satisfy STRICT_REPO_LOCAL_SKILL_LOADING scanner requirements.
- Inline read-only pandas validation of `data/market_vci_candidate_20260612.parquet` versus `data/market_2015_now.parquet`.
- Inline compile check via Python `compile(...)` for `scripts/vci_candidate_download_20260612.py` and `scripts/vci_candidate_validate_20260612.py`: both OK, no pyc write.
- `git status --short -- <scope>` and `git hash-object` / `git rev-parse` for canonical/candidate integrity evidence.

## Candidate Validation

- Candidate exists and loads: PASS, `1,763,089` rows, `14` columns.
- Canonical exists and loads: PASS, `1,687,749` rows, `14` columns.
- Schema vs canonical: PASS, ordered columns equal, no missing/extra columns, no dtype diffs.
- Counts: candidate `665` tickers, `3,668` dates; canonical `666` tickers, `2,855` dates.
- Exchange values: PASS, only `HNX` and `HOSE`.
- Duplicate `(ticker, date)`: PASS, `0`.
- Null OHLCV: PASS, `open=0`, `high=0`, `low=0`, `close=0`, `volume=0`.
- Non-positive OHLC prices: PASS, all `0`.
- Volume sanity: PASS, `volume_negative=0`; `volume_zero=278,116` documented as illiquid/suspended rows.
- Date range: candidate `2011-03-15` to `2026-06-12`; canonical `2015-01-05` to `2026-06-12`.
- PIT safety: PASS, `future_beyond_canonical=0`, `future_beyond_current_2026_06_12=0`.
- Coverage vs canonical: PASS with documented gap, `1,684,909` candidate rows in canonical range; missing canonical ticker `BTW`; no candidate-only tickers.
- Candidate source/scale: PASS, `source=vnstock_vci`, `price_scale=VND`, close min/median/max `70 / 10410 / 377080`.

## Canonical Integrity

- Candidate path is separate from canonical path: PASS.
- Current canonical is not overwritten by candidate: PASS; canonical rows/source differ from candidate (`1,687,749` rows, source sample `VCI` vs candidate `1,763,089` rows, `vnstock_vci`).
- Hash evidence: current canonical `9e5a45e2244e012f77c712a92c223a638b73e80e`; HEAD canonical `bfda9071f91575a50ec326f1df994317ce0073bb`; candidate `191f7144cdfbfcb0baa28b3c3b6892899a6e2cb8`.
- Residual note: `git status` shows `data/market_2015_now.parquet` modified versus HEAD, so this audit does not claim the canonical worktree file is identical to HEAD. It only verifies it was not replaced by the VCI candidate artifact in this scope.

## Findings

1. BLOCKER: `.ly_state/session/l2_role15_vci_candidate_market_download_20260612.md` uses forbidden-path mentions with `NOT used`, but the strict scanner requires an accepted non-authoritative context marker in each sentence or line. Reproduction: `python scripts/sod_gate_enforcer.py` after adding the gate exits 1 and reports forbidden path violations for the L2 report.

Data quality checks passed, but SOD gate enforcement did not pass. L2 must revise the L2 report evidence wording, then resubmit for L3 re-audit.

## Verdict

[NEEDS_FIX] - Candidate data validation passes, but the gate is blocked by STRICT_REPO_LOCAL_SKILL_LOADING evidence wording in the L2 report.
