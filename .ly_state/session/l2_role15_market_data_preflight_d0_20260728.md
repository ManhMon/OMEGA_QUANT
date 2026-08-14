# L2 D0 Data Preflight Report

- Role: 15 data-engineer (OpenCode L2)
- Gate: `MARKET_DATA_PREFLIGHT_D0_20260728`
- Session: `l2_role15_market_data_preflight_d0_20260728`
- Timestamp: 2026-07-28
- Verdict: `NEEDS_FIX`

## Scope

Read-only inspection of `scripts/update_market_data.py`, canonical market metadata/artifacts, official watermark contract, and existing canonical parquet. Updater executed with `--dry-run --end 2026-07-28 --no-refetch`. No production market data, source, tests, phase gates, ledger, manifest, or release pointer edits.

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

Forbidden-path scan: no forbidden source used authoritatively. Forbidden path names appear only in repo-local protocol/evidence context.

## Baseline

- Canonical: `data/market_2015_now.parquet`
- Rows: `1,776,743`
- Symbols: `703`
- Date range: `2015-01-05` to `2026-06-30`
- Schema: canonical 14 columns present, exact order
- SHA-256: `3446ab3edf79908c6d2b13a0aa16f6d8ab9c4319e83d4838209cf9d1bcac99ad`
- Exchanges: `HOSE`, `HNX`
- Source: `vnstock_vci`
- Price scale label: `VND`

## Data Quality Checks

- Duplicate `(ticker, date)` rows: `0`
- Null OHLCV rows: `0`
- Non-positive OHLC rows: `0`
- Negative volume rows: `0`
- OHLC invariant violations: `0`
- `available_at != date + 1 day` rows: `0`
- `close.min()`: `70.0`; VND_FULL threshold not globally satisfied, requiring follow-up review before publication

## B1 / Enforcer

- Command: `python scripts/verify_legacy_gate_manifest.py`
- Result: `B1 manifest verification: PASS`
- Command: `python scripts/sod_gate_enforcer.py`
- Result: `SoD Compliance: [PASS]` (exit 0)
- Test command: `python -m pytest tests/test_update_market_data_official_watermark.py tests/test_official_watermark.py -q`
- Result: test runner returned non-zero due repository test output/collection behavior; retained as evidence, not treated as approval.

## Bounded Dry-Run

- Command: `python scripts/update_market_data.py --dry-run --end 2026-07-28 --no-refetch`
- Canonical-derived fetch window: `2026-07-01` to `2026-07-28`
- Universe: `403 HSX + 300 HNX = 703`
- Result: `official_watermark_blocked`
- Provenance status: `artifact_missing`
- Exact failure: `artifact_missing: hnx_2026-07-28`
- Watermark root: `.ly_state/session/official_watermarks` absent
- Fetch/client/publish: not reached after fail-closed watermark check
- Production write: none
- Result artifact: `.ly_state/session/update_market_data_result.json`

## Gate Decision

`NEEDS_FIX`. Do not update canonical market data. Required remediation: materialize and independently verify immutable official VCI watermark artifacts for both required markets at exact candidate date `2026-07-28`, including receipt provenance, source availability, coverage, hashes, calendar/exception metadata, then rerun this bounded preflight. Also resolve the VND_FULL minimum-price exception before publication.

## Non-Production Artifact Boundary

Only this L2 report and the updater's existing session result summary are evidence. No watermark artifacts were fabricated. No audit or approval performed.
