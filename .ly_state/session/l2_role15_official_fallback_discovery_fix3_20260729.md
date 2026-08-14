# L2 Official Fallback Discovery FIX3

- Role: `15 data-engineer` (L2 OpenCode)
- Session: `l2_role15_official_fallback_discovery_fix3_20260729`
- Scope: official watermark source adapter/config/tests/runbook, official source discovery, nonproduction capture evidence
- Requested date: `2026-07-28`
- Verdict authority: Tier 3 only; no self-approval

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

Forbidden-path scan: `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, `.codex\\memories` not used as authoritative sources.

## Changes

- `fetch_official_source` now permits HNX's official HTML market-data page only with exact structured `txtSymbol_Date` date and HNX identity markers.
- HSX remains JSON-only; generic text markers remain rejected.
- Added regression coverage for HNX exact date marker.
- Updated runbook with HNX HTML validation rule.
- No canonical data, publication, pointer, gate, ledger, manifest, or approval changed.

## Endpoint Discovery Evidence

| Market | Endpoint | Status | Effective URL | Content type | Validation outcome |
|---|---|---:|---|---|---|
| HNX | `https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html` | 200 | exact URL | `text/html` | PASS: official page contains `txtSymbol_Date=28/07/2026`, HNX page identity; SHA256 `f5d7b7b524d1d31f9bb904366d09d3278d990ee3387015935da65a01316eb1e0` |
| HSX | `https://www.hsx.vn/vi/du-lieu-giao-dich/thong-ke/du-lieu-cuoi-ngay` | 200 | exact URL | `text/html` | FAIL: JavaScript shell, no exact structured date/exchange payload |
| HSX API | `https://api.hsx.vn/m/api/v1.0/data-feed/files` | 401 | not accepted | JSON/error | FAIL: authentication required; no public receipt |
| HNX report files | `https://owa.hnx.vn/ftp///THONGKEGIAODICH//20260728/CP/20260728_NY_Quy_mo_giao_dich.pdf` | not captured | official page-linked file | PDF | Discovered link only; not accepted as structured parser input |
| `hsx.vn` | `https://hsx.vn` | transport error | n/a | n/a | FAIL |
| `ssc.gov.vn` | `https://ssc.gov.vn` | timeout | n/a | n/a | FAIL |
| `sdc.vn` | `https://sdc.vn` | transport error | n/a | n/a | FAIL |
| `sd.vn` | `https://sd.vn` | transport error | n/a | n/a | FAIL |

TLS verification remained enabled. No auth/TLS bypass, mirror, social source, fabricated receipt, or unverified third-party data used.

## Verification

Command: `python -m pytest tests/test_official_watermark.py tests/test_official_source_receipt.py -q -ra`

Result: pass; one Windows symlink capability skip.

Command: `python -c "import urllib.request,hashlib; u='https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html'; r=urllib.request.urlopen(u,timeout=30); b=r.read(); print(r.status,r.geturl(),r.headers.get_content_type(),len(b),hashlib.sha256(b).hexdigest())"`

Result: `200`, exact URL, `text/html`, 156974 bytes, SHA256 `f5d7b7b524d1d31f9bb904366d09d3278d990ee3387015935da65a01316eb1e0`.

## Receipt / D0 Status

No watermark receipt materialized. HNX source proves the exact official session marker but does not yet provide injected validated rows required by `materialize_watermark`; HSX remains unavailable. D0 dry-run not executed because both exchange receipts are required. Canonical update and publish remain blocked.
