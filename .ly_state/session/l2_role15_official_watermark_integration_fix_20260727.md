# L2 Remediation Report: Official Watermark Integration

- Session: `l2_role15_official_watermark_integration_fix_20260727`
- Role: Role 15 `data-engineer`, L2 OpenCode
- Gate: `lessons_extraction_official_watermark_fix_20260727`
- Status: implementation complete; pending independent L3 audit

## Changes

- Integrated immutable artifact verification into `scripts/update_market_data.py` before `_create_vnstock_client()` and `fetch_symbols()`.
- Missing, tampered, invalid market, and candidate date mismatch evidence returns named `official_watermark_blocked` with `provenance_status`; client creation, fetch, staging, canonical write, and pointer publish are not reached.
- Maps updater `HOSE` to official `HSX`; canonical source exchange values remain `HOSE`/`HNX`.
- Passes verified provenance, hashes, source URL, dates, and receipt path into the publish manifest.
- Added `--watermark-root` test override. No production watermark artifacts created.
- CLI exits nonzero for `official_watermark_blocked`.

## Tests

- `tests/test_update_market_data_official_watermark.py`
  - `tmp_path` artifact setup
  - missing and tampered artifact statuses
  - date and market rejection
  - HOSE/HSX mapping
  - valid evidence reaches mocked client/fetch/publish and manifest
  - invalid evidence proves zero client/fetch/publish calls
- Existing `tests/test_official_watermark.py` retained.

## Verification

- `python -m pytest tests/test_official_watermark.py tests/test_update_market_data_official_watermark.py -q` -> `15 passed, 1 skipped`
- `python -m compileall -q scripts/update_market_data.py src/omega/data/official_watermark.py tests/test_update_market_data_official_watermark.py` -> pass
- `git diff --check -- scripts/update_market_data.py src/omega/data/official_watermark.py tests/test_update_market_data_official_watermark.py` -> pass
- Production refresh not run. No production artifacts written.

## Repo-local Sources Read

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

Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`; these are non-authoritative forbidden paths.

No approval asserted. Submit to independent Tier 3 audit.
