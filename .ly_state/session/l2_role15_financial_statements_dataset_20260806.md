# L2 Role 15 Financial Statements Dataset 20260806

Gate: `FINANCIAL_STATEMENTS_DATASET_20260806`

## Scope

- Updated `scripts/fetch_financial_statements.py`: manifest generated during fetch contains `snapshot_date`, sorted symbols, source market parquet SHA-256, ticker count.
- Expanded `tests/test_fetch_financial_statements.py`: 8 dispatch cases plus PIT, durability, manifest/hash, divide, schema, timezone, replacement, empty-output coverage.

## PIT Contract

- `available_at = max(source_publish_at, fiscal_period_end + embargo)`.
- Quarterly embargo: 45 days. Annual embargo: 90 days.
- Missing source publish timestamp uses the embargo fallback.

## Verification

- `python -m pytest tests/test_fetch_financial_statements.py -vv`
- Result: `19 passed, 5 warnings in 6.45s`.
- `git diff --check`: no errors in scoped files. Existing unrelated whitespace warnings remain outside scope.

## Repo-Local Files Read

- REPO_AGENT_ROOT=.agents/agent REPO_SKILL_ROOT=.agents/skills
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

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.
- Result: no forbidden-path authoritative reliance.

No audit or approval performed.
