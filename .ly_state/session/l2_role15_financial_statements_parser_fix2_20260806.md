# L2 Implementation Report: FINANCIAL_STATEMENTS_PARSER_FIX2_20260806

## Scope

- Updated `scripts/fetch_financial_statements.py`.
- Updated `tests/test_fetch_financial_statements.py`.
- Inspected only `src/omega/quant/graph/fetcher.py`; preserved `_call` 2.0s delay and `BaseException` retry handling.
- Preserved `_configure_utf8_stdio()`.

## Change

- `normalize_statement()` now recognizes vnstock wide-pivot period columns: `YYYY-Q[1-4]`, including duplicate suffixes such as `2025-Q4_1`, and `YYYY`.
- Wide rows use `item_id` as `item_code`, falling back to `item`.
- Quarter columns produce quarter-end dates and `period_type="quarter"`; annual columns produce December 31, quarter zero, and `period_type="year"`.
- Added wide quarterly and annual normalization regression tests.

## Verification

- `python -m pytest tests/test_fetch_financial_statements.py`: PASS, `23 passed`.
- Scoped `git diff --check -- scripts/fetch_financial_statements.py tests/test_fetch_financial_statements.py src/omega/quant/graph/fetcher.py`: PASS.
- `checklist.py`: not present in repository.
- `verify_all.py`: not present in repository.
- `python -m pytest -q`: FAIL, unrelated pre-existing failure: `tests/test_hybrid_alpha_real_market.py::test_candidate_record_clear_signals_releases_cached_arrays` raises `AttributeError: 'CandidateRecord' object has no attribute 'clear_signals'` at line 338.

## Repo-Local Files Read

REPO_AGENT_ROOT=.agents/agent
REPO_SKILL_ROOT=.agents/skills

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

- `.gemini\\antigravity-ide\\scratch\\ag-kit`: absent.
- `.openclaw\\skills`: absent.
- `C:\\Users\\GHC\\.agents`: exists; not read or used as an authoritative source.
- `.codex\\memories`: absent.
- Result: no authoritative reliance on forbidden paths.

## Handoff

- L2 implementation complete. No approval or audit performed.
