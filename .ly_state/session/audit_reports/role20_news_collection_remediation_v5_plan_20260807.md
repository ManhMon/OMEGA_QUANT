# Compliance Audit Report

**Role**: Compliance Officer (Role 20, Codex L3)
**Date**: 2026-08-07
**Submission**: `implementation_plan_remediation_v2.md` Remediation V5
**Proposed writer**: Data Engineer (Role 15)

## Blocking Findings

1. **Historical source is not validated.** Proposed Vietcap request returned HTTP 400 for `2015-01-01` through `2015-01-07`. Missing request/auth, response schema, pagination rules, stable ordering, terminal-page rule, retry statuses, proof of 2015 coverage. "Batch without loops" contradicts pagination.
2. **PIT truth table is unstable.** `max(publicDate_UTC, ingestion_time)` becomes ingestion time for backfill. No immutable first-ingestion receipt or replay rule exists. Re-runs can move `available_at`. Current code uses `publish_time + 1 day`.
3. **Schema contradicts acceptance.** `NewsRecord` defines eight fields; acceptance requires six. Existing parquet omits `source` and `source_id`. Duplicate provenance has no field/table. No migration/version exists.
4. **Ticker verification is not listing verification.** Price presence does not prove listing interval. Previous-day fallback can accept pre-IPO, post-delisting, renamed, transferred, or suspended tickers. Current-universe fallback after `2026-06-30` creates survivorship bias.
5. **Dedupe remains unmeasurable.** Layer 3 lacks a match definition. Accent stripping risks false merges. The 100-pair fixture is absent. No labeling guide, holdout, metric thresholds, false-merge ceiling, or survivor/provenance rule exists.
6. **Recovery contract is incomplete.** Quarantine uses audit/session storage. Checkpoints lack fields, locking, page watermarks, partial-page commit, checksum, replay, and crash recovery semantics.
7. **Robots/retry controls are not executable.** Fixed delay does not establish compliance. Missing redirect policy, crawl-delay parsing, timeout, jitter, `Retry-After`, retry deadline, fail-closed behavior.
8. **Acceptance does not prove 11 years.** The 31-test suite passes but validates existing behavior only. Missing executable coverage, pagination, replay-stable PIT, idempotency, restart, quarantine, provenance, dedupe, license, and terms checks.
9. **No auditable L2 submission exists.** Missing fresh Role 15 report, hashes, source receipt, fixture, migration result, and V5 execution evidence.

## Verified Evidence

- Named pytest suite: 31 passed, 8 warnings.
- `data/market_2015_now.parquet`: 1,776,743 rows; maximum date `2026-06-30`.
- `data/news_sentiment_2015_now.parquet`: 102 rows; six columns.
- `tests/fixtures/labeled_news_pairs.json`: missing.
- `scripts/fetch_news_sentiment.py:71`: `available_at = article.timestamp + timedelta(days=1)`.
- Proposed Vietcap historical request: HTTP 400 on `2026-08-07`.

## Required Fixes

1. Provide a successful Vietcap request contract and fixture proving 2015 coverage and deterministic pagination.
2. Define immutable first-observed receipts and replay-stable `available_at` rules.
3. Choose one canonical schema; preserve source identity/provenance; define migration/versioning.
4. Use PIT listing intervals and ticker identity history; reject dates beyond verified watermarks.
5. Add labeled holdout data, metric thresholds, false-merge limit, and survivor rules.
6. Define durable checkpoints, locking, atomic commit, quarantine manifest, replay, retry, and crash tests.
7. Add executable 11-year completeness, PIT, provenance, idempotency, recovery, robots/terms, and migration gates.
8. Submit a fresh Role 15 L2 package with repo-local source evidence.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `implementation_plan_remediation_v2.md`
- `.ly_state/session/audit_reports/role20_news_collection_remediation_v2_plan_20260807.md`
- `.ly_state/session/audit_reports/role20_news_collection_remediation_v2_plan_reaudit_20260807.md`
- `src/omega/data/news_aggregator.py`
- `scripts/fetch_news_sentiment.py`
- `tests/test_news_aggregator_scrapers.py`
- `tests/test_sentiment_dual_engine.py`
- `tests/test_news_aggregator.py`

## Forbidden-Path Scan

No authoritative reliance on forbidden paths.

## Verdict

**[NEEDS_FIX]**

Do not delegate V5 implementation or update a phase gate until blockers are resolved and a complete Role 15 L2 package exists.
