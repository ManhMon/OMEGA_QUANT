# L2 Remediation Report

- Session: `l2_role15_vci_candidate_market_download_provenance_20260729`
- Role: `15 data-engineer`, OpenCode L2
- Gate: `role21_vci_candidate_market_download_provenance_20260729`
- Verdict: implementation submitted; no audit or approval performed.

## Changes

- Removed public `fetch_official_source` and `OfficialSourceResponse` construction surface.
- `materialize_watermark(config, market, expected_date)` now owns private HTTPS acquisition, token validation, raw JSON parsing, and row binding.
- Runtime token comes only from `VCI_API_TOKEN`; no token is written to logs, receipts, or repository files.
- Retained private pure `_parse_official_payload`, `_materialize_validated`, and `_acquire_official_source` seams for tests.
- Added adversarial checks for unavailable public APIs, rejected HTML, and restricted materialization signature.
- Updated `docs/official-watermark-runbook.md`.

## Repo-local sources read

- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

Forbidden path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## Verification

- `python -m pytest tests/test_official_watermark.py tests/test_official_source_receipt.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_vci_updater_validation_write_blocker.py -q`: `35 passed, 4 skipped`.
- `python -m py_compile src/omega/data/official_watermark.py`: pass.
- `git diff --check`: pre-existing unrelated worktree whitespace warnings only; no remediation-file error.
- `python scripts/sod_gate_enforcer.py`: `SoD Compliance: [PASS]` (legacy residual evidence notice remains outside this scope).

Protected-file SHA-256 after:

- `src/omega/data/official_watermark.py`: `6C9A8519F2AC17D2F9686DAAB6F2CEA8EAB47A0375C7BD51A036C217D1186DF9`
- `tests/test_official_watermark.py`: `8A23C06AC745465F8FEF31C4C41942E35A05E74EA7607EF52F385D95B35CCEDD`
- `tests/test_official_source_receipt.py`: `052D2ADB1DEA5E31080C6220E1635956801675B92699ED42DA84510638795425`
- `tests/test_update_market_data_official_watermark.py`: `67C5B3C17F969A1413A3F54CB87A5B43D66681E404E7DDC63C654F92433465CF`
- `tests/test_vci_production_safety_20260727.py`: `4FA7899164B516974A20F434C3D14D3E06153EEE0B0394585F32F8D3D242BAF2`
- `tests/test_vci_final_safety_closure_20260728.py`: `F73BA00947774FA57B4E008E5951A0A1B808D3AFE27C62CE8906E84BDEAC445A`
- `tests/test_vci_updater_validation_write_blocker.py`: `FAE0931AEB1703B658A01C5D56BE92FBD67BE0139D6A24B1AC3A6785BF5472DC`
- `docs/official-watermark-runbook.md`: `094D37B38761533C22BB38F1221691AF7F8DE1EAE29C5AF442D8711C68B87A74`

Baseline hash: not present in the remediation evidence supplied; after hashes recorded for L3 comparison.
