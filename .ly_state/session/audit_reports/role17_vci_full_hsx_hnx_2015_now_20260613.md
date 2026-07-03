# QA Audit Report
**Role**: QA Engineer (Role 17)
**Date**: 2026-06-13T08:05:00+07:00
**Gate**: VCI_FULL_HSX_HNX_2015_NOW_20260613
**Submission**: l2_role15_vci_full_hsx_hnx_2015_now_20260613
**Tier 2 Engineer**: data-engineer (Role 15)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read
- .agents/agent/qa-engineer.md
- .agents/skills/webapp-testing/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/verify-changes/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/audit-cycle/SKILL.md

Forbidden path scan result: no authoritative reliance on forbidden paths. Forbidden/global/scratch sources were not used as authoritative role or skill sources.

## SOD Checks
- Writer != auditor: PASS (15 != 17)
- L3 role metadata: PASS (`qa-engineer`, role_id 17, tier 3, platform Codex, sod_boundary present)
- L2 report repo-local skill source evidence: PASS; exact `.agents/agent/...` and `.agents/skills/.../SKILL.md` files listed.
- L2 forbidden path wording: PASS; report states forbidden paths were non-authoritative and not used as source.
- L3 write boundary: PASS; only this audit report and target gate metadata updated.

## Verification Executed
- `python scripts/sod_gate_enforcer.py` before gate update: PASS, exit 0. Existing gates passed; target gate was not registered yet.
- Read-only independent parquet probe via inline Python using `pd.read_parquet`.
- Reviewed scoped scripts and state artifacts:
  - `scripts/vci_full_hsx_hnx_download_20260613.py`
  - `scripts/vci_full_hsx_hnx_validate_20260613.py`
  - `.ly_state/session/vci_universe_hsx_hnx.json`
  - `.ly_state/session/vci_full_hsx_hnx_stats.json`
  - `.ly_state/session/vci_full_hsx_hnx_validation.json`
  - `.ly_state/session/l2_role15_vci_full_hsx_hnx_2015_now_20260613.md`

## Passing Checks
- Parquet loads: PASS, 1,853,541 rows, 14 columns.
- Schema compatibility: PASS; columns are `ticker`, `date`, `exchange`, `open`, `high`, `low`, `close`, `volume`, `as_of`, `available_at`, `source`, `price_scale`, `adjusted`, `rebuild_date`.
- Output exchanges: PASS; only `HOSE` and `HNX`.
- Exchange split: PASS; HOSE 1,039,697 rows / 403 tickers; HNX 813,844 rows / 300 tickers.
- Universe coverage vs state artifact: PASS; 703/703 tickers covered, 0 missing, 0 extra.
- Fetch accounting: PASS; completed 703, fetched 703, empty 0, errors 0.
- Duplicate ticker-date: PASS; 0 duplicates.
- OHLCV nulls: PASS; 0 nulls for open/high/low/close/volume.
- Non-positive OHLC: PASS; 0 rows for open/high/low/close.
- Negative volume: PASS; 0 rows.
- OHLC invariant violations: PASS; 0 rows.
- No canonical overwrite: PASS by scoped output path inspection; canonical `data/market_2015_now.parquet` was not present in this workspace probe, and L2 output used a dated candidate file.

## Defect
1. Date scope violation: requested output is 2015 to now, but the parquet contains data before 2015-01-01.
   - Actual min date: 2011-03-15.
   - Pre-2015 rows: 82,280.
   - Pre-2015 tickers: 469.
   - Pre-2015 range: 2011-03-15 to 2014-12-31.
   - L2 documented the pre-2015 rows in the report and validation JSON, but documentation does not satisfy the requested 2015-to-now output contract. The download script declares `START_DATE = "2015-01-01"`, so the persisted file should be filtered to `date >= 2015-01-01` before save or the scope/name/report must be explicitly changed and re-approved.
   - The L2 validator is too weak for this requirement: `min_date_covers_2015` passes when `date_min <= 2015-12-31`, allowing pre-2015 leakage.

## Notes
- The universe artifact contains 403 HSX and 300 HNX symbols. The scoped download script loads this artifact and maps HSX to HOSE. The L2 report states the universe was built from VCI Listing API, not a canonical subset; the delivered scoped artifacts do not include the exact universe-generation command/code beyond that report evidence.
- Running `scripts/vci_full_hsx_hnx_validate_20260613.py` was intentionally skipped because it writes `.ly_state/session/vci_full_hsx_hnx_validation.json`, which is outside the L3 write boundary for this audit. Equivalent read-only checks were run inline.

## Verdict
[NEEDS_FIX]

Required fix: regenerate or filter `data/market_vci_hsx_hnx_2015_now_20260613.parquet` so every row has `date >= 2015-01-01`, then update validation to fail on pre-2015 rows and re-run the L2 report/audit cycle.
