# HSX Official Watermark Endpoint Research

**Role**: data-engineer (Role 15, L2 OpenCode)  
**Session**: `l2_role15_hsx_watermark_endpoint_research_20260803`  
**Research date**: 2026-08-03  
**Scope**: Read-only endpoint research. No source, configuration, test, canonical-data, watermark, receipt, gate, or release-pointer changes. No watermark or receipt was materialized.

## Result

**[NEEDS_FIX]** No official HSX structured HTTPS JSON endpoint was verified for session `2026-07-31` under the existing watermark contract. Canonical state remains unchanged.

## Existing Contract

`src/omega/data/official_watermark.py:24-28` fixes HSX to:

`https://api.hsx.vn/m/api/v1.0/data-feed/files`

`docs/official-watermark-runbook.md:9-16` requires an official fixed HTTPS URL with no query or fragment, HTTP `200`, exact final URL equality, `application/json`, valid structured JSON, and payload evidence of exact market and requested date. Any failure quarantines the candidate.

## Authority Ownership

- Official owner: Ho Chi Minh Stock Exchange, branded HOSE/HSX.
- Official web domain: `https://www.hsx.vn`.
- Read-only official-homepage retrieval rendered `HOSE` and `Sở Giao dịch Chứng khoán Thành phố Hồ Chí Minh`.
- Official HSX API candidate domain: `https://api.hsx.vn`; it is the fixed production candidate already owned by the existing watermark contract.
- No VCI, vnstock, KBS, broker, mirror, or third-party source was used as HSX authority.

## Probes

| URL | HTTP | Final URL | Content type | Date/exchange evidence | Contract |
|---|---:|---|---|---|---|
| `https://api.hsx.vn/m/api/v1.0/data-feed/files` | 401 | Exact source URL | Absent | No body eligible for JSON/date/exchange validation | Fail: not HTTP 200; no `application/json`; no structured exact `2026-07-31` and `HSX` evidence |
| `https://api.hsx.vn/m/api/v1/market/trading-summary` | 404 | Exact source URL | Absent | No payload | Fail: not HTTP 200; no JSON/date/exchange evidence |

Both source URLs use HTTPS and have no query or fragment. `curl.exe --location --max-redirs 0` returned an empty redirect URL for both probes; neither response passed the required HTTP/MIME gate.

## Excluded Discovery

Prior repo-local capture identifies the HSX UI request pattern:

`https://api.hsx.vn/m/api/v1/market/trading-summary?date={date}&securitiesType={securitiesType}`

This cannot qualify because the existing contract prohibits query URLs. The prior live captures for `2026-07-28` returned `404` for documented `securitiesType` values. This research did not submit a date query, preserving the no-query source-URL requirement.

## Fail-Closed Decision

- HTTP `200`: failed.
- No redirect/exact final URL: observed, but insufficient.
- `application/json`: failed.
- Structured JSON: unavailable.
- Exact date `2026-07-31`: unproven.
- Exact exchange `HSX`/`HOSE`: unproven in payload.

No endpoint meets every requirement. Do not change `_OFFICIAL_SOURCE_URLS`, materialize a watermark/receipt, advance a date, or alter canonical state.

## Required Next Step

Obtain an HSX-published fixed, query-free HTTPS JSON endpoint or official API documentation plus a direct response that returns HTTP `200`, no redirect, `application/json`, and structured fields proving `2026-07-31` and `HSX`/`HOSE`. Re-probe before any contract change or materialization.

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
- `docs/official-watermark-runbook.md`
- `.ly_state/session/l2_role15_hsx_receipt_recovery_fix4_20260729.md`

## Forbidden-Path Scan

No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. These paths were not read for role, skill, endpoint, or watermark authority.
