# L2 Official Receipt Recovery FIX4

- Role: `15 data-engineer` (L2 OpenCode)
- Session: `l2_role15_hsx_receipt_recovery_fix4_20260729`
- Gate: `GP_PERSISTENCE_CANONICAL_DB_20260702`
- Scope: watermark adapter/config/tests/runbook/source-capture evidence/D0 dry-run only
- Requested session: `2026-07-28`
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
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/lint-and-validate/SKILL.md`
- `.agents/skills/verify-changes/SKILL.md`

Forbidden-path scan: forbidden/global/scratch paths were not used as authoritative sources. Any protocol mentions are non-authoritative scan evidence only.

## Root Cause And Fix

`fetch_official_source` validated against the module-global `OFFICIAL_SOURCE_URLS`, so injected test/config allowlists could not be used. FIX4 adds an explicit `official_urls` mapping parameter, defaulting to the approved production allowlist. Existing exact URL, TLS, HTTP 200, no redirect, content-type, JSON, date, and market checks remain unchanged.

## HSX Public Source Capture

The official page bundle was inspected read-only:

- Page: `https://www.hsx.vn/vi/du-lieu-giao-dich/thong-ke/du-lieu-cuoi-ngay`
- Bundle: `https://www.hsx.vn/static/js/main.d430e296.js`
- Page status: HTTP 200, exact URL, JavaScript shell
- Discovered UI endpoint: `https://api.hsx.vn/m/api/v1/market/trading-summary?date={date}&securitiesType={securitiesType}`
- Method: `GET`
- Expected response shape: JSON `{ "success": true, "data": ... }`

Live probes for `2026-07-28`:

- `.../market/trading-summary?date=2026-07-28&securitiesType=STOCK`: HTTP 404
- `.../market/trading-summary?date=2026-07-28&securitiesType=ALL`: HTTP 404
- `.../market/trading-summary?date=2026-07-28&securitiesType=1`: HTTP 404
- `.../market/trading-summary?date=2026-07-28&securitiesType=STOCK` with official page `Origin`/`Referer`: HTTP 404
- `.../market/trading-summary?date=2026-07-28&securitiesType=STOCK` at `/m/api/v1.0`: HTTP 404

No HTTP 200 structured exact-date HSX response was obtained. No HSX raw hash or receipt was accepted. No authenticated 401 endpoint, redirect, browser-rendered text, mirror, or fabricated payload was used.

## Changes

- `src/omega/data/official_watermark.py`: caller-injected official URL allowlist for `fetch_official_source`.
- `tests/test_official_source_receipt.py`: test allowlist injection while retaining fail-closed response checks.
- No canonical data, release pointer, publication, phase gate, ledger, or manifest changed.

## Verification

Command:

```text
python -m pytest tests/test_official_watermark.py tests/test_official_source_receipt.py tests/test_update_market_data_official_watermark.py -q -ra
```

Result: exit `0`; Windows symlink capability test skipped.

Command:

```text
python -m py_compile src/omega/data/official_watermark.py tests/test_official_source_receipt.py
```

Result: pass.

Command:

```text
git diff --check -- src/omega/data/official_watermark.py tests/test_official_source_receipt.py
```

Result: pass.

Ruff is unavailable in this environment; no Ruff result claimed.

## D0 Updater Dry-Run

Command:

```text
python scripts/update_market_data.py --dry-run --end 2026-07-28 --symbols AAA --watermark-root .ly_state/session/official_watermarks
```

Result: `official_watermark_blocked`, `artifact_missing: hnx_2026-07-28`.

- VCI client creation: not reached
- Symbol fetch: not reached
- Publish: not reached
- Canonical write: none
- HSX/HNX receipt bundle: not materialized because HSX source validation remains unavailable

No audit or approval asserted. Submit to independent Tier 3 audit.
