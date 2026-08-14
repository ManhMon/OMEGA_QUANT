# HNX Official Watermark Endpoint Research

**Role**: data-engineer (Role 15, L2 OpenCode)  
**Session**: `l2_role15_hnx_watermark_endpoint_research_20260803`  
**Research date**: 2026-08-03  
**Scope**: Read-only endpoint research. No code, config, test, watermark, canonical-data, pointer, receipt, or gate modification.

## Result

**[NEEDS_FIX]** No official HNX HTTPS JSON endpoint was verified that satisfies the existing watermark contract for session `2026-07-31`. The canonical maximum date remains `2026-06-30`, per the latest prior protected-state evidence at `.ly_state/session/audit_reports/role20_market_data_dryrun_20260801.md:61`.

## Contract Evaluated

- Fixed HTTPS URL, without query or fragment.
- HTTP `200`.
- Effective URL exactly equals source URL; no redirect.
- `Content-Type: application/json`.
- Structured JSON contains the exact session date `2026-07-31` and exact exchange `HNX`.
- HNX official ownership evidence.

## Official Ownership Evidence

- Authority domain: `https://hnx.vn`.
- Official HNX listed-stock trading-data page: `https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html`.
- The page footer states copyright belongs to `Sở Giao dịch Chứng khoán Hà Nội`; its navigation labels this page `Cổ phiếu niêm yết` / `Dữ liệu giao dịch`.
- The page embeds `txtSymbol_Date` and date selector values `31/07/2026`, showing HNX publishes the requested session through its official site. The page response is HTML, not JSON.

## Probes

### Official Page

| URL | HTTP | Final URL | Content type | Date/exchange evidence | Contract |
|---|---:|---|---|---|---|
| `https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html` | 200 | Exact source URL | `text/html; charset=utf-8` | HTML has `31/07/2026`; page is official HNX trading data | Fail: not JSON |

### Discovered JSON Endpoint

| URL | Method | HTTP | Final URL | Content type | Structured payload | Contract |
|---|---|---:|---|---|---|---|
| `https://hnx.vn/ModuleReportStockETFs/Report_FilterDataOnCBO_Common/MD_FilterSymbolByIndexIndustry` | POST | 200 | Exact source URL | `application/json; charset=utf-8` | Only `cboSymbolOption`, an HTML option-string of symbols. No `2026-07-31`, date field, market/exchange field, or session result. | Fail: exact date and HNX absent |

The POST target has no query or fragment. Request body was `pIndex=0&pIndustry=-1&pMarket=LIS_BRD_01`; this does not rescue the response contract because the response lacks date and exchange evidence.

### Date-Specific Trading-Data Endpoint

| URL | Method | Session supplied | HTTP | Final URL | Content type | Contract |
|---|---|---|---:|---|---|---|
| `https://hnx.vn/ModuleReportStockETFs/Report_MD_PriceVolatilyti/ListData_Listed` | POST | `31/07/2026` in the form body | 302 | `/Home/Error?aspxerrorpath=/ModuleReportStockETFs/Report_MD_PriceVolatilyti/ListData_Listed` | `text/html; charset=utf-8` | Fail: redirect and not JSON |

The official page JavaScript identifies this endpoint as the date-filtered detailed listed-stock result. Its successful browser workflow injects HTML, not JSON. A direct read-only probe, including a session cookie, returned the recorded `302`; contract rejects redirects regardless.

## Validation Evidence

- All probes used `https://hnx.vn` targets without source URL query or fragment.
- JSON candidate: HTTP 200, no observed redirect, JSON content type. Payload lacked the exact date and exchange required by `_structured_response_matches()` in `src/omega/data/official_watermark.py:157-174`.
- Date-specific candidate: failed HTTP/final-URL/content-type requirements before payload evaluation.
- Existing contract explicitly quarantines HNX until an equivalent structured official endpoint is validated: `docs/official-watermark-runbook.md:10-11`.
- No vnstock, KBS, VCI, broker, or third-party source was used as official HNX watermark authority.

## Required Next Step

Obtain an HNX-published, fixed, query-free HTTPS JSON endpoint or documented official JSON API whose direct response contains both `2026-07-31` and `HNX`; re-probe HTTP status, exact final URL, MIME, JSON structure, and payload fields before any watermark contract change or materialization.

## Repo-Local Sources Read

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
- `.ly_state/session/audit_reports/role20_market_data_dryrun_20260801.md`

## Forbidden-Path Scan

No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. These forbidden paths were not read for role, skill, endpoint, or watermark authority.
