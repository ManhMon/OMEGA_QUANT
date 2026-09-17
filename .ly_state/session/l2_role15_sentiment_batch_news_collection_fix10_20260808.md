# L2 Remediation Report: news_collection_remediation_v10

## Session

- Session ID: `l2_role15_sentiment_batch_news_collection_fix10_20260808`
- Role: `15 data-engineer` (L2 OpenCode)
- Scope: `scripts/fetch_news_sentiment.py`, `tests/test_news_aggregator_scrapers.py`
- Status: implementation and scoped tests complete; pending independent L3 audit.

## Changes

- `scripts/fetch_news_sentiment.py`: non-incremental collection now raises `ValueError` whenever no valid rows were collected, independent of output-file existence.
- `tests/test_news_aggregator_scrapers.py`: labelled-pair evaluation uses the production title predicate: normalized-title equality or Levenshtein similarity strictly greater than `0.88`; thresholds remain precision `>= 0.95`, recall `>= 0.90`.
- Quarantine-only test calls use `incremental=True`, preserving their quarantine/atomicity assertions without violating the new non-incremental data-quality invariant.

## Verification

- PASS: `pytest -q tests/test_news_aggregator_scrapers.py` - 27 passed.
- PASS: `python -m py_compile scripts/fetch_news_sentiment.py tests/test_news_aggregator_scrapers.py`.
- PASS: `git diff --check` for scoped changes.
- BLOCKED: `pytest -q tests/test_sentiment_dual_engine.py` has an out-of-scope failure in `test_news_engine_passes_hours_back_to_aggregator`: it expects a successful non-incremental zero-row run, which the requested guard now rejects.
- UNAVAILABLE: `python scripts/checklist.py` and `python scripts/verify_all.py`; both files are absent from `scripts/`.

## Root Cause

The prior zero-row guard was conditional on `output_path.exists()`, allowing a non-incremental empty first write. The new guard applies before any staging or writes.

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

## Forbidden Path Scan

No authoritative role or skill source was read from `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## SoD

No audit or approval performed. Submit this L2 evidence and source diff to Tier 3.
