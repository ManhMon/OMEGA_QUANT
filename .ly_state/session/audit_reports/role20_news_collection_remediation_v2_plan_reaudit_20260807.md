# Compliance Audit Report

**Role**: Compliance Officer (Role 20, Codex L3)
**Date**: 2026-08-07
**Submission**: `implementation_plan_remediation_v2.md`
**Proposed writer**: Data Engineer (Role 15)

## Blocking Findings

1. **PIT availability remains unsafe.** Vietcap `publish_time + 1 hour` is synthetic and unproven. GDELT `ingestion_time` is undefined. Community `file_creation_time` is mutable local metadata, not release availability.
2. **Provenance cannot be preserved.** `NewsRecord` lacks `canonical_id`, duplicate-group ID, raw payload reference, capture timestamp, dataset revision, content hash, and parser version despite promising original-record retention.
3. **Ticker verification is incorrect.** Exact-date trading presence rejects weekend, holiday, and suspended-security news. Market data ends 2026-06-30 while collection ends 2026-08-07. Rename, transfer, multi-ticker, unknown-ticker, and delisting rules remain absent.
4. **Community sources are not reproducibly pinned.** Kaggle owner/slug, exact files, per-file hashes, command, and license-use decision are absent. Hugging Face config, split, full revision, files, hashes, and command are absent.
5. **GDELT controls are not executable.** Dry-run estimates cost but does not enforce it. No `maximum_bytes_billed`, deterministic daily iteration, stable key, watermark, export method, destination, or restart proof exists.
6. **Wayback controls are incomplete.** HTTP is specified. CDX pagination, resume key, status/mimetype filtering, snapshot collapse, allowlist, redirect policy, timeout, size limit, content validation, and robots/terms evidence are absent.
7. **Dedupe validation is undefined.** `tests/fixtures/labeled_news_pairs.json` does not exist. No labeling policy, holdout split, class balance, metric formulas, threshold selection, survivor policy, or false-merge guard exists.
8. **Recovery can lose work.** Checkpoint fields, atomicity, locking, partial-page commit, checksum, quarantine manifest, replay, retryable statuses, jitter, and retry deadline are absent. `.ly_state/session/` is evidence storage, not durable canonical storage.
9. **Acceptance does not prove 11-year completeness.** `> 1,000` rows lacks yearly/source/ticker coverage, earliest/latest bounds, error budgets, provenance integrity, idempotency, restart injection, and quarantine reconciliation.
10. **Migration and SoD ownership conflict.** Existing parquet has six fields versus nine proposed, without migration/versioning. Current writer uses `publish_time + 1 day`. Production ingestion must not write `.ly_state/session/phase_gates.json`; gate ownership belongs to L1/L3.
11. **No L2 execution package exists.** No new Role 15 report, implementation hashes, source/license receipts, dry-run evidence, fixture, or execution results support approval.

## Verified Evidence

- Named suite collects 31 tests.
- `tests/fixtures/labeled_news_pairs.json` is absent.
- `data/market_2015_now.parquet`: 1,776,743 rows, 703 tickers, maximum date 2026-06-30.
- `data/news_sentiment_2015_now.parquet`: 102 rows, 2024-10-07 through 2026-08-07, six-column schema.
- `scripts/fetch_news_sentiment.py` currently sets `available_at = publish_time + 1 day`.

## Required Fixes

1. Use immutable observed/released timestamps and explicit fallback/rejection rules.
2. Add complete canonical-group and raw-source provenance contracts.
3. Use listing intervals/as-of identity resolution; align universe watermark.
4. Pin exact source artifacts, hashes, commands, licenses, and permitted use.
5. Specify executable GDELT/Wayback iteration, cost, watermark, and restart controls.
6. Supply labeled holdout data and deterministic dedupe evaluation.
7. Define atomic durable checkpoint, quarantine, and replay semantics.
8. Add executable coverage, PIT, provenance, idempotency, restart, cost, and migration gates.
9. Remove production-script phase-gate writes.
10. Submit a fresh Role 15 L2 package.

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
- `src/omega/data/news_aggregator.py`
- `scripts/fetch_news_sentiment.py`

## Forbidden-Path Scan

No authoritative reliance on forbidden paths.

## Verdict

**[NEEDS_FIX]**

No approved phase gate until blockers and L2 evidence are resolved.
