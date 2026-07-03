# QA Audit Report

**Role**: QA Engineer (Role 17, L3 Codex)
**Date**: 2026-06-13T08:14:00+07:00
**Gate**: VCI_FULL_HSX_HNX_2015_NOW_20260613
**Submission**: l2_role15_vci_full_hsx_hnx_2015_now_fix1_20260613
**Tier 2 Engineer**: data-engineer (Role 15)
**Verdict**: [APPROVED]

## Repo-Local Sources Read

- `.agents/agent/qa-engineer.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/verify-changes/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`

Forbidden/global/scratch sources were not used as authoritative sources.

## SOD Checks

- Writer != auditor: PASS (L2 role_id 15 != L3 role_id 17)
- L3 boundary: PASS. No production source or test files edited by L3.
- L2 report repo-local source evidence: PASS. Report lists `.agents/agent/data-engineer.md` and repo-local skill files from `.agents/skills/...`.
- L2 forbidden path scan evidence: PASS. Report marks `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` as non-authoritative only.
- Pre-update `python scripts/sod_gate_enforcer.py`: expected FAIL only for target gate remaining `[NEEDS_FIX]`; no strict evidence errors printed.

## Verification Evidence

- Parquet load: PASS (`1,771,261` rows, `14` columns).
- Date scope: PASS. `date_min=2015-01-05`, `date_max=2026-06-12`, pre-2015 rows `0`.
- Exchange/ticker scope: PASS. Exchanges `['HNX', 'HOSE']`; tickers `703` total (`403` HOSE, `300` HNX).
- Universe coverage: PASS. HSX missing `0`, HNX missing `0`, HOSE extra `0`, HNX extra `0`.
- Empty/error counts: PASS. `empty=0`, `errors=0` in stats.
- Duplicate ticker-date: PASS. `0` duplicates.
- OHLCV nulls: PASS. `open/high/low/close/volume` null counts all `0`.
- Non-positive OHLC: PASS. `open/high/low/close` non-positive counts all `0`.
- Negative volume: PASS. `0` rows.
- Canonical overwrite: PASS. `data/market_2015_now.parquet` does not exist; download/validator scripts reference only `data/market_vci_hsx_hnx_2015_now_20260613.parquet`.
- Script syntax: PASS. AST parse passed for download and validator scripts without writing bytecode.

## Validator Hard-Fail Check

PASS. `scripts/vci_full_hsx_hnx_validate_20260613.py` contains hard checks:

- `min_date_gte_2015`: requires `date_min >= pd.Timestamp("2015-01-01")`
- `no_pre_2015_rows`: requires `(df["date"] < pd.Timestamp("2015-01-01")).sum() == 0`

The checked validation JSON reports both as PASS and `all_pass=true`. I did not rerun the validator directly because the script unconditionally writes `.ly_state/session/vci_full_hsx_hnx_validation.json`, which is outside the L3 write boundary. Independent parquet probes above verified the same conditions read-only.

## Verdict

[APPROVED]

The fix satisfies the requested 2015-now VCI HSX/HNX dataset scope and strict repo-local SOD evidence requirements.
