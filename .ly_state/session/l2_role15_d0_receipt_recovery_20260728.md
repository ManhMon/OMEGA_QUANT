# L2 D0 Receipt Recovery Report

- **Role:** 15 data-engineer (OpenCode L2)
- **Session:** `l2_role15_d0_receipt_recovery_20260728`
- **Gate:** `MARKET_DATA_PREFLIGHT_D0_20260728`
- **Date:** 2026-07-28
- **Verdict:** `NEEDS_FIX`

## Scope

Trusted existing receipt/source configuration, official watermark tooling, and
`.ly_state/session/official_watermarks/` inspection only. No canonical market
data, updater, release pointer, phase gate, ledger, lock, manifest, source,
test, or audit edits. Production update was not run.

## Required Session Determination

- Canonical: `data/market_2015_now.parquet`
- Canonical date range: `2015-01-05` through `2026-06-30`
- Canonical max date: `2026-06-30`
- D0 bounded request end: `2026-07-28`
- D0 fetch window: `2026-07-01` through `2026-07-28`
- Calendar source: `config/vn_holidays.json`, loaded by `src/omega/data/calendar.py`
- Calendar result: `2026-07-28` is a trading day; no closure adjustment
- Exact required watermark session: `2026-07-28`
- Required markets: `HSX` and `HNX`

The target is derived from the bounded D0 request and verified calendar, not
assumed from the workspace date. Canonical max date establishes the start of
the missing refresh window; it does not replace the exact watermark session.

## Trusted Configuration and Artifact Check

- Official watermark root: `.ly_state/session/official_watermarks/`
- Root status: absent
- Existing trusted HSX receipt bundle: absent
- Existing trusted HNX receipt bundle: absent
- Existing raw/canonical/receipt artifacts for `2026-07-28`: none
- Existing receipt SHA-256 values: none available
- Existing raw SHA-256 values: none available
- Existing canonical SHA-256 values: none available
- Existing official URL allowlist: absent from production configuration
- Test-only URLs (`https://official.example/hsx`, `https://official.example/hnx`): rejected as non-production and not used
- Authorized verifier identity/signature: not configured or verifiable

`src/omega/data/official_watermark.py` is fail-closed. It requires exact
caller-supplied HSX/HNX URLs, an injected configured client/fetcher, exact
candidate maximum date, complete coverage, calendar metadata, exception
metadata, real cutoff/retrieval timestamps, and immutable hash-checked writes.
No existing evidence satisfies that contract.

## Verification Evidence

- D0 report: `.ly_state/session/l2_role15_market_data_preflight_d0_20260728.md`
- Prior acquisition report: `.ly_state/session/l2_role15_official_watermark_acquisition_20260728.md`
- D0 failure: `artifact_missing: hnx_2026-07-28`
- Prior acquisition result: no approved endpoint; HSX/HNX acquisition not attempted
- Watermark contract: `src/omega/data/official_watermark.py`
- Runbook: `docs/official-watermark-runbook.md`
- Canonical SHA-256 from D0 evidence: `3446ab3edf79908c6d2b13a0aa16f6d8ab9c4319e83d4838209cf9d1bcac99ad`
- Calendar check command: `$env:PYTHONPATH='src'; python -c "from datetime import datetime; from omega.data.calendar import VNTradingCalendar; print(VNTradingCalendar.is_trading_day(datetime(2026,7,28)))"`
- Calendar check result: `True`
- No fetch/client/materialization attempt made because trusted source configuration and verifier evidence are missing

## Decision

`NEEDS_FIX`. Stop. No watermark was materialized because no trusted official
HSX/HNX source configuration, authenticated verifier, or receipt evidence is
available. Fabricating URLs, receipts, signatures, hashes, timestamps, rows,
or coverage would violate the fail-closed contract.

## Missing Prerequisites

1. Exact approved HTTPS HSX source URL for session `2026-07-28`.
2. Exact approved HTTPS HNX source URL for session `2026-07-28`.
3. Authenticated VCI client/fetcher configuration with source identity.
4. Authorized verifier identity and verifiable receipt/signature status.
5. Valid HSX/HNX raw, canonical, and receipt artifacts, including provenance,
   coverage, calendar/exception metadata, cutoff/retrieval timestamps, and
   independently reproducible SHA-256 hashes.

## Repo-Local Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `src/omega/data/official_watermark.py`
- `src/omega/data/calendar.py`
- `config/vn_holidays.json`
- `docs/official-watermark-runbook.md`
- `.ly_state/session/l2_role15_market_data_preflight_d0_20260728.md`
- `.ly_state/session/l2_role15_official_watermark_acquisition_20260728.md`
- `.ly_state/session/audit_reports/l3_role21_d0_watermark_windows_fix_20260728.md`

Forbidden-path scan: no forbidden path used as an authoritative source.

## Mutation Boundary

- Created: `.ly_state/session/l2_role15_d0_receipt_recovery_20260728.md`
- Official watermark artifacts: none
- Canonical/update/release/ledger/lock/manifest changes: none
- Source/test/audit/phase-gate changes: none
- Production update: not run
