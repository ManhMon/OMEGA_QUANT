# L2 Implementation Report

**Session:** `l2_role15_vci_combined_merge_pit_duplicate_remediation_20260804`  
**Role:** 15 `data-engineer` (Tier 2, OpenCode)  
**Gate:** `VCI_COMBINED_MERGE_PIT_DUPLICATE_REMEDIATION_20260804`  
**Scope:** `scripts/update_market_data.py`; focused updater tests only.

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

## Forbidden-Path Scan

No authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`. All role and skill sources above are repo-local.

## Root Cause

`_normalize_legacy_vci_available_at()` coerced `available_at` to `object` before assigning repaired canonical values. It normalized only canonical input in the merge path. Mixed naive canonical and aware VCI candidate timestamps therefore prevented equivalent overlap resolution and retained PIT-invalid metadata.

## Implementation

- Normalize `available_at` with `pd.to_datetime(..., utc=True).dt.tz_convert(VN_TZ)`, preserving one aware datetime dtype.
- Normalize both canonical and VCI candidate frames before equivalence comparison and merge.
- Normalize fetched candidates before their standalone validation.
- Preserve existing conflict behavior: only exact `OVERLAP_EQUIVALENCE_COLUMNS` matches allow canonical precedence; conflicts return an error. No blanket duplicate removal added.
- Full-history replacement remains explicit through existing `full_history_symbols` canonical deletion before merge.

## Verification

1. `python -m pytest tests/test_market_release_gates.py tests/test_vci_updater_validation_write_blocker.py -q`
   - PASS: `16 passed`.
   - Pytest emitted an existing cache warning: `.pytest_cache` path collision. No test failure.
2. `python -m py_compile scripts/update_market_data.py`
   - PASS.
3. `git diff --check -- scripts/update_market_data.py tests/test_market_release_gates.py tests/test_vci_updater_validation_write_blocker.py`
   - PASS.
4. Runtime in-memory canonical plus deterministic VCI reproduction:
   - Canonical: `1,776,743` rows; original `available_at` dtype `datetime64[ns]`; source `vnstock_vci`.
   - Candidate: `13,039` same-key rows with aware VCI `available_at`.
   - Merged: `1,776,743` rows; duplicate `(ticker,date)` rows `0`; conflicts `0`; `available_at` dtype `datetime64[ns, Asia/Ho_Chi_Minh]`; `validate_dataframe()` PIT result PASS.

## Files Changed

- `scripts/update_market_data.py`
- `tests/test_market_release_gates.py`
- `tests/test_vci_updater_validation_write_blocker.py`

Canonical parquet and market pointer were not modified. L2 implementation complete; requires independent L3 audit. No approval issued.
