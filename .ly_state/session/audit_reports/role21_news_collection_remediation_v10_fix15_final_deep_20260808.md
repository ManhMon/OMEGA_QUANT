# Code Review Audit Report

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-08-08
**Gate**: `news_collection_remediation_v10`
**Submission**: `news_collection_remediation_v10_fix15`
**L2 Session**: `l2_role15_sentiment_batch_news_collection_fix15_20260808`
**L2 Role**: `15 data-engineer`
**L3 Session**: `l3_role21_news_collection_remediation_v10_fix15_final_deep_20260808`
**Scope**: `src/omega/data/news_aggregator.py`, `scripts/fetch_news_sentiment.py`, `scripts/migrate_news_parquet.py`, `tests/test_news_aggregator_scrapers.py`

## Finding

1. **HIGH - `src/omega/data/news_aggregator.py:409`**: `_scrape_vietcap_news()` never enforces `self.max_articles_per_source`. Every other scraper checks the configured cap, but Vietcap appends every row across every cursor page. Therefore `NewsAggregator(max_articles_per_source=1)` can return more than one Vietcap article, and the new CLI `--max-articles-per-source` does not control all sources as claimed. With the default historical window and `100000` CLI cap, this also leaves Vietcap pagination effectively unbounded until cursor exhaustion. Add cap checks before append and before fetching another page; add a multi-row/multi-page Vietcap regression test.

## Verification Evidence

- `python -m pytest tests/test_news_aggregator_scrapers.py tests/test_sentiment_dual_engine.py -q`: `42 passed`.
- `python -m pytest tests/test_news_aggregator_scrapers.py -q`: `30 passed`.
- `python -m py_compile src/omega/data/news_aggregator.py scripts/fetch_news_sentiment.py scripts/migrate_news_parquet.py tests/test_news_aggregator_scrapers.py`: passed.
- `git diff --check HEAD -- <scoped files>`: passed.
- Ruff: unavailable.
- SoD enforcer before this verdict update: passed.
- Code Review Graph calls timed out twice after 300 seconds; scoped Git/code/test analysis used instead.
- Existing cap regression covers only the HTML scraper at `tests/test_news_aggregator_scrapers.py:36`; no Vietcap cap assertion exists.

## Required Action

1. Enforce `self.max_articles_per_source` inside `_scrape_vietcap_news()` without fetching surplus cursor pages.
2. Add a Vietcap regression proving configured cap behavior across multi-row and paginated responses.
3. Re-run the 42-test scoped suite, compilation, diff check, and SoD enforcer.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `src/omega/data/news_aggregator.py`
- `scripts/fetch_news_sentiment.py`
- `scripts/migrate_news_parquet.py`
- `tests/test_news_aggregator_scrapers.py`
- `.ly_state/session/l2_role15_sentiment_batch_news_collection_fix15_20260808.md`
- `.ly_state/session/audit_reports/role20_news_collection_remediation_v10_fix15_20260808.md`
- `.ly_state/session/phase_gates.json`

## Forbidden Path Scan

No authoritative reliance on forbidden paths. Repo-local role and skill sources only.

## Verdict

**[NEEDS_FIX]**

Passing tests do not cover the configured-cap contract for Vietcap.

**Signature**: Codex L3 Code Reviewer, Role 21
