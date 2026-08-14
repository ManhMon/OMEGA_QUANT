# L2 Implementation Report

- Session: `l2_role15_vci_candidate_market_download_provenance_fix2_20260729`
- Role: Role 15 `data-engineer`, Tier 2 OpenCode
- Gate: `role21_vci_candidate_market_download_provenance_fix2_20260729`
- Verdict authority: Tier 3 only; no self-approval

## Scope

- `src/omega/data/official_watermark.py`
- Official watermark tests
- `docs/official-watermark-runbook.md`

## Fix

Removed `_materialize_validated`, the receipt-writing seam that accepted caller-supplied evidence and parsed rows. `materialize_watermark` now privately acquires the authenticated response; the internal write path reparses `source_evidence.raw` and derives candidate, coverage, hashes, and receipt metadata from that raw response only.

Direct calls supplying forged evidence/rows cannot write because no receipt-producing function accepts those values.

## Regression

Added `test_forged_rows_cannot_reach_receipt_writer`: a forged extra-argument call is rejected and creates no artifact.

## Verification

```text
python -m compileall -q src/omega/data/official_watermark.py tests/test_official_watermark.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_vci_updater_validation_write_blocker.py tests/test_update_market_data_official_watermark.py
```

Passed.

```text
python -m pytest tests/test_official_watermark.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_update_market_data_official_watermark.py tests/test_vci_updater_validation_write_blocker.py -q
```

`45 passed, 3 skipped`.

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

Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.
