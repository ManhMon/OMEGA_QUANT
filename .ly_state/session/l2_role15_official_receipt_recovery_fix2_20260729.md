# L2 Official Receipt Recovery FIX2

- Role: data-engineer (Role 15, L2)
- Session: `l2_role15_official_receipt_recovery_fix2_20260729`
- Scope: `src/omega/data/official_watermark.py`, `tests/test_official_source_receipt.py`, `docs/official-watermark-runbook.md`
- Gate: `VCI_FULL_HSX_HNX_2015_NOW_20260613`
- Verdict: implementation complete; live receipt capture blocked; no approval claimed

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

## Forbidden Path Scan

Forbidden paths are non-authoritative scan evidence only: `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, `.codex\\memories`. No authoritative reliance.

## Root Cause

The prior adapter accepted page-text markers. HSX is a JavaScript shell whose public structured API references were discoverable, but the official `https://api.hsx.vn/m/api/v1.0/data-feed/files` endpoint returns HTTP 401 without credentials. HNX page capture redirects to `/Home/Error` and local Python TLS verification fails with `CERTIFICATE_VERIFY_FAILED` even using certifi.

## Changes

- Replaced text marker validation with recursive structured JSON validation requiring exact date and exchange fields.
- Requires HTTP 200, exact final URL, `application/json`, valid UTF-8 JSON, and successful structured payload.
- Uses a verified TLS context from certifi, falling back to the platform CA store. No verification bypass.
- Added exact structured parsing tests and text-marker rejection test.
- Updated runbook: HSX authenticated endpoint and HNX TLS/endpoint blockers remain quarantined.

## Verification

Command: `python -m pytest tests/test_official_source_receipt.py tests/test_official_watermark.py -q -ra`

Result: `16 passed, 1 skipped`, exit `0` (symlink capability skip on Windows).

## Live Capture Blockers

- HSX: official structured endpoint `https://api.hsx.vn/m/api/v1.0/data-feed/files` returned `401 Unauthorized`; no public exact-date receipt validated.
- HNX: `https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html` returned `302` to `/Home/Error`; direct Python capture failed certificate verification using certifi.
- No validated HSX/HNX receipts materialized. No dry-run executed. No canonical update, publish, pointer, gate, ledger, lock, manifest, or approval operation performed.
