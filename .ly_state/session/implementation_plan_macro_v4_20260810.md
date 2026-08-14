# Macro & Fundamental Data V3 — Audit-Closure Implementation Plan

**Status:** Ready for Role 20 re-audit after implementation evidence exists  
**Owner:** Role 6 `system-architect`  
**Audit basis:** `.ly_state/session/audit_reports/role20_macro_micro_data_v3_plan_20260810.md`  
**Scope:** Financial statements, macro indicators, historical loaders, graph/features, migration, release publication

## Goal

Replace the current overwrite/deduplication pipeline with a fail-closed, append-only, Point-In-Time-safe release contract. Close all six audit blockers: Append-only, Quarantine, Metric ID, Forecast, exact publication timestamp, and atomic deploy.

## Non-Negotiable Decisions

- Silver may be empty. Missing trustworthy publication timestamps never justify fabricated availability.
- Valid source-confirmed forecasts belong in Forecast, never Quarantine or historical Silver.
- Future rows are classified before historical-record validation.
- Existing canonical files are never migrated in place. Migration creates a new immutable generation and switches one pointer only after full validation.
- Exact replay changes no canonical row and does not advance the active pointer unless another artifact changes.
- Every failure persists its cursor/checkpoint, hashes, timestamps, phase, and error receipt. The prior pointer remains active.
- All API schemas and pagination capabilities pass preflight before bulk acquisition.
- Pagination uses provider-issued server cursors only. Client-side slicing, inferred offsets, and silent first-page acceptance are forbidden.

## Minimal File Plan

- Add `src/omega/data/macro_micro_release.py`: shared schemas, classification, revision rules, release manifest, CAS pointer, reader validation, and V3 migration.
- Update `src/omega/data/macro_pipeline.py`: exact source evidence, fail-closed timestamps, append-only revisions, Quarantine/Forecast outputs.
- Update `scripts/fetch_financial_statements.py`: paginated acquisition, raw receipts, classification, V3 normalization, no destructive deduplication.
- Update `src/omega/quant/graph/fetcher.py`: schema preflight and server-cursor page iterator.
- Update `src/omega/quant/graph/loader.py`: actual-only trust boundary and `metric_id` end-to-end.
- Extend `tests/test_fetch_financial_statements.py`, `tests/test_macro_pipeline.py`, and `tests/test_financial_loader.py`.
- Add `tests/test_macro_micro_release.py` for migration, manifest, CAS, rollback, and crash injection.
- Keep existing CLI entrypoints. Add no second fetch script.

## Release Layout

Every generation is immutable and complete:

```text
data/macro_micro/releases/<release_id>/
  bronze/financial_pages.parquet
  bronze/macro_pages.parquet
  silver/financial_actual.parquet
  silver/macro_actual.parquet
  quarantine/records.parquet
  quarantine/resolutions.parquet
  forecast/financial_forecast.parquet
  forecast/macro_forecast.parquet
  manifest.json

data/macro_micro/current.json
.ly_state/session/macro_micro_attempts/<attempt_id>/
  checkpoint.json
  attempt.json
  failure.json                 # present only on failure
```

All listed artifacts exist in every release, including schema-correct empty Parquet files. Readers never combine artifacts from different `release_id` values.

## Canonical Record Contract

### Common Provenance

Silver and Forecast rows require all fields below:

| Field | Contract |
|---|---|
| `schema_version` | Exact V3 schema identifier. |
| `release_id` | Immutable generation identifier. |
| `dataset` | Stable dataset name. |
| `record_type` | Exactly `actual` or `forecast`. |
| `source` | Stable provider identifier. |
| `source_url` | Exact source endpoint/document URL. |
| `source_receipt_id` | Immutable Bronze receipt/page identifier. |
| `raw_hash` | SHA-256 of exact raw evidence bytes. |
| `raw_hashed_at` | Timezone-aware RFC3339 timestamp when the checksum was computed. |
| `source_published_at` | Exact timezone-aware RFC3339 source publication timestamp. |
| `available_at` | Deterministically derived from `source_published_at` and the HOSE calendar. |
| `ingested_at` | Actual timezone-aware RFC3339 ingestion timestamp; never a publication substitute. |
| `revision_id` | Immutable content identity. |
| `revision_order_kind` | Exactly `source_revision_at` or `revision_seq`. |
| `source_revision_at` | Source-confirmed RFC3339 revision timestamp when timestamp ordering is used. |
| `revision_seq` | Source-confirmed positive integer when sequence ordering is used. |

`revision_order_kind` selects exactly one non-null ordering field. A logical series cannot change ordering kind between revisions.

### Logical Keys

| Dataset | Logical key |
|---|---|
| Financial | `(dataset, symbol, metric_id, fiscal_period_end)` |
| Macro | `(dataset, indicator, observation_date)` |

`source` participates in provenance and conflict checks. Provider reconciliation is not silently merged into one revision stream.

## 1. Append-Only and Exact Replay Contract

### Identity Versus Ordering

- Compute `revision_id = SHA256(canonical_json(dataset, logical_key, normalized_business_payload, source, raw_hash))`.
- Exclude `release_id`, `ingested_at`, and filesystem paths from `revision_id`.
- Order revisions only by the field selected by `revision_order_kind`; never sort or tie-break by `revision_id`.
- Require a total source order per logical key. Distinct revisions with the same ordering value enter Quarantine as `REVISION_ORDER_COLLISION`.
- Accept late-arriving older revisions immutably. As-of selection still follows the source ordering value and cutoff eligibility.

### Write Rules

- Same logical key plus same `revision_id`: canonical no-op.
- Same logical key plus distinct `revision_id`: append an immutable revision.
- Same `revision_id` with different canonical content or `raw_hash`: fail release and persist `REVISION_ID_CONFLICT` evidence.
- Remove `drop_duplicates(..., keep=last)` and every overwrite path used as business reconciliation.
- Build each candidate from the prior immutable generation plus new distinct revisions; never mutate the prior generation.

### As-Of Rules

Historical queries perform these steps in order:

1. Validate pointer, manifest, artifact hashes, schemas, and matching `release_id`.
2. Read Silver only and require `record_type == actual`.
3. Filter `available_at <= cutoff` and `ingested_at <= cutoff`.
4. Group by the dataset logical key.
5. Select the greatest eligible `source_revision_at` or `revision_seq` according to the fixed `revision_order_kind`.
6. Reject ties instead of using the revision hash, ingestion order, file order, or `keep=last`.

This preserves both future-mutation invariance and restatement PIT invariance.

## 2. Permanent Quarantine Contract

Every Quarantine row is immutable and requires these non-null fields:

| Field | Contract |
|---|---|
| `schema_version` | Quarantine schema version. |
| `quarantine_id` | Deterministic SHA-256 identity. |
| `release_id` | First release that recorded the evidence. |
| `dataset` | Source dataset. |
| `reason_code` | Stable machine-readable reason. |
| `source` | Provider identifier. |
| `source_url` | Exact source location when available. |
| `source_receipt_id` | Bronze receipt/page link. |
| `quarantined_at` | Timezone-aware RFC3339 timestamp. |
| `raw_hash` | SHA-256 of `raw_evidence`. |
| `raw_hashed_at` | Timezone-aware RFC3339 checksum time. |
| `raw_evidence` | Exact immutable bytes or byte-preserving encoded payload. |
| `source_record_locator` | Stable row/page locator inside the raw receipt. |
| `details` | Versioned structured validation details. |

Rules:

- Compute `quarantine_id` from schema version, dataset, source, reason, source locator, and `raw_hash`.
- Same exact invalid evidence is a no-op; distinct evidence or reason appends a new record.
- Never delete, update, or move a Quarantine record.
- Verify `SHA256(raw_evidence) == raw_hash` before staging and again in the published reader.
- Replay creates a new valid Silver/Forecast revision when possible and appends a Quarantine resolution event. It never edits the original record.

Resolution events require `resolution_id`, `quarantine_id`, `resolved_at`, `resolution_action`, `destination_dataset`, `destination_revision_id`, `release_id`, `resolver_version`, and `source_receipt_id`. The destination revision must exist in the same or a later immutable release.

Minimum reason codes include:

- `PUBLICATION_TIMESTAMP_MISSING`
- `PUBLICATION_TIMESTAMP_INVALID`
- `PUBLICATION_TIMESTAMP_DATE_ONLY`
- `PUBLICATION_TIMESTAMP_FABRICATED`
- `PUBLICATION_TIMESTAMP_INGESTION_SUBSTITUTION`
- `FUTURE_PERIOD_UNCONFIRMED`
- `API_SCHEMA_MISMATCH`
- `CURSOR_PROTOCOL_VIOLATION`
- `REVISION_ORDER_MISSING`
- `REVISION_ORDER_COLLISION`
- `METRIC_ID_AMBIGUOUS`
- `RAW_HASH_MISMATCH`

## 3. Frequency-Safe Metric ID and Lossless Migration

### Metric Contract

- Persist `metric_id = endpoint:period_type:item_code` in Bronze normalization, Silver, Forecast, Quarantine details, joins, pivots, graph nodes, and feature names.
- Preserve `endpoint`, `period_type`, and `item_code` as separate columns; `metric_id` is not a replacement for source fields.
- Split `metric_id` with a maximum of two delimiters so colons inside `item_code` remain lossless.
- Financial loader joins use `(symbol, metric_id)`.
- Pivots use `metric_id` as the column key.
- Graph node identity and feature names include the complete `metric_id`; bare `item_code` is forbidden at these boundaries.
- Derived ratios keep explicit endpoint/period provenance. Their `raw_hash` is the hash of ordered parent revision IDs plus formula version; `source_published_at`, `available_at`, and `ingested_at` are the maximum parent values.

### Atomic V3 Migration

Migration is an immutable release operation, not an in-place rewrite:

1. Hash and preserve the legacy Parquet file byte-for-byte in Bronze.
2. Preflight required columns and allowed values before transforming any row.
3. Classify source-confirmed future rows before historical validation.
4. Construct `metric_id` for every parseable financial row.
5. Detect old-key groups spanning multiple `period_type` values and record collision counts without collapsing rows.
6. Preserve every distinct annual and quarterly revision. Exact duplicate occurrences remain accounted for in the migration report and raw Bronze evidence.
7. Route ambiguous or unparseable rows to permanent Quarantine; never infer missing frequency from row order.
8. Require `legacy_input_rows == distinct_migrated_actual + distinct_migrated_forecast + quarantined_rows + exact_duplicate_occurrences`.
9. Validate zero duplicate V3 primary keys `(symbol, metric_id, fiscal_period_end, revision_id)`.
10. Publish only through the release CAS pointer. A failed migration leaves the legacy pointer and all legacy files unchanged.

## 4. Dedicated Forecast Contract

Classification happens before actual-record validation:

1. Validate only the raw envelope, source receipt, raw hash, period fields, and explicit source record type.
2. Partition records explicitly marked by the source as forecast, estimate, guidance, or consensus into Forecast candidates.
3. Validate Forecast candidates against the Forecast schema, including exact `source_published_at`, revision ordering, and provenance.
4. Send a future-period row without an explicit source forecast marker to Quarantine as `FUTURE_PERIOD_UNCONFIRMED`.
5. Validate remaining candidates as historical actuals.

Hard boundaries:

- Valid forecasts are never Quarantine records.
- Silver accepts only `record_type == actual`.
- `FinancialStatementLoader`, graph loaders, feature builders, and every backtest entrypoint reject Forecast paths, Forecast schemas, or non-actual rows before joins/pivots.
- Historical readers do not accept a caller option that weakens this boundary.
- Forecast access requires a separate explicit loader/API outside historical backtests.

## 5. Exact Publication Timestamp and Availability Contract

### Source Timestamp

`source_published_at` is accepted only when all conditions hold:

- Exact time and timezone are present in source evidence.
- Value parses as timezone-aware RFC3339.
- The source URL/receipt and `raw_hash` point to immutable evidence containing that timestamp.
- The extractor records the exact JSON field path, HTML selector, document field, or signed receipt field used.

The following never populate Silver or Forecast and instead enter Quarantine:

- Date-only values.
- `fiscal_period_end + 45/90 days`.
- Fabricated year-end or next-year dates.
- Fetch time, `ingested_at`, file modification time, or current clock substitutions.
- Parsed timestamps lacking source evidence.

Remove the financial +45/+90 fallback, SBV ingestion-time substitution, and World Bank fabricated publication date. Existing affected rows migrate to Quarantine. Empty Silver is valid when accounting and evidence gates pass.

### `available_at` Conversion

Use `Asia/Ho_Chi_Minh`, the versioned HOSE holiday calendar, session open `09:00`, and session close `15:00`:

- Trading day, publication strictly before `15:00`: `available_at = source_published_at`.
- Trading day, publication at or after `15:00`: next trading session at `09:00`.
- Weekend or holiday: next trading session at `09:00`.
- `available_at` must never precede `source_published_at`.
- `ingested_at` remains independent; as-of queries require both availability and ingestion cutoffs.

Tests cover before-close, exactly-at-close, after-close, Friday after-close, weekend, consecutive holidays, timezone conversion, and calendar-range failure.

## API Preflight, Cursor Pagination, and Raw Receipts

`GraphFetcher` exposes a page iterator, not a one-shot DataFrame fetch.

### Preflight

- Probe all 8 financial endpoint/period pairs (`4 endpoints x 2 periods`) and every configured macro endpoint before bulk acquisition.
- Validate provider-specific response envelope, data rows, publication field, forecast marker, revision-order field, and pagination metadata against a versioned adapter schema.
- Abort publication on any schema drift. Persist the raw response, hash, timestamps, adapter version, and `API_SCHEMA_MISMATCH` receipt.
- If the provider/client cannot expose a server cursor, fail preflight. Never simulate pagination with local slicing or inferred page numbers.

### Cursor Rules

- Send only the server-issued cursor for the next request.
- Persist `request_cursor`, `next_cursor`, page index, request timestamp, response timestamp, checksum timestamp, raw hash, row count, endpoint, period, symbol, and source URL for every page.
- Stop only on the provider's explicit terminal condition.
- Reject repeated cursors, missing cursor with `has_more`, cursor cycles, endpoint/symbol drift, and unaccounted pages.
- Fsync the checkpoint after every accepted page. Resume from the last committed server cursor after failure.
- Exact page replay with the same raw hash is a no-op in canonical data; the operational attempt receipt remains durable.

## 6. One Atomic Release for Bronze/Silver/Quarantine/Forecast

### Manifest Contract

One `manifest.json` covers the complete macro and financial generation. It requires:

- `manifest_schema_version`
- `release_id`
- `generation`
- `state`
- `created_at`, `validated_at`, `published_at`
- `cutoff`
- `prior_release_id`
- `prior_generation`
- `prior_pointer_sha256`
- one entry for every Bronze, Silver, Quarantine, Forecast, and resolution artifact
- for every artifact: relative path, class, dataset, schema version, row count, byte size, SHA-256, and timezone-aware `hashed_at`
- migration accounting and collision report
- pagination coverage report
- classification and provenance coverage report
- validation results and test evidence hashes

### Publication Protocol

1. Acquire the publication lock and read the active pointer bytes once.
2. Create a unique immutable `release_id` candidate directory.
3. Write and fsync every artifact under that directory.
4. Re-read each artifact; validate schema, row count, `release_id`, cutoff, and SHA-256.
5. Write and fsync the sealed manifest.
6. Re-read and validate the manifest plus all referenced artifacts.
7. Compare expected `prior_generation` and `prior_pointer_sha256` with the still-active pointer.
8. Write a temporary pointer containing `release_id`, generation, manifest path, and manifest SHA-256.
9. Fsync the temporary pointer, atomically replace `data/macro_micro/current.json`, then fsync its parent directory where supported.
10. Mark the attempt published in `.ly_state/session`; never mutate the sealed release.

Any exception before step 9 leaves the prior pointer unchanged. Any stale generation/hash fails the compare-and-swap.

### Failure Persistence and Rollback

- On failure, fsync `failure.json` with attempt/release ID, failed phase, exception type/message, timestamps, cutoff, prior pointer hash, completed artifact hashes, last durable cursor per work item, and validation results.
- Keep the failed candidate and checkpoints immutable; no automatic cleanup is added in this change.
- Resume creates a new attempt and reuses only hash-verified completed pages/artifacts.
- Rollback validates the prior release exactly like a normal reader, then performs another CAS pointer replacement and writes an immutable rollback receipt.

### Reader Contract

- Read pointer and manifest into private bytes.
- Verify pointer manifest hash before reading data.
- Require manifest state `published` and all required artifact classes, including empty artifacts.
- Verify every artifact hash, schema version, row count, release ID, and cutoff before returning any frame.
- Reject missing, incomplete, mixed-generation, stale-schema, or mismatched artifacts. Never fall back to direct canonical file paths.

## Quantitative Publication Gates

All thresholds are release-blocking:

| Gate | Required threshold |
|---|---|
| Financial schema preflight | `8/8` endpoint-period pairs pass. |
| Macro schema preflight | `100%` of configured endpoints pass. |
| Requested work receipts | `100%` of symbol/endpoint/period and macro work items have terminal-success receipts; authoritative empty responses count as success. |
| Cursor completion | `100%` of successful work items reach an explicit terminal cursor state; `0` repeated, cyclic, inferred, or missing cursors. |
| Raw provenance | `100%` of pages have source URL/receipt, request/response/checksum timestamps, and valid SHA-256. |
| Classification accounting | `100%`; each normalized source row maps exactly once to actual, forecast, Quarantine, or documented exact replay. |
| Publication provenance | `100%` of Silver and Forecast rows have exact source timestamp, evidence link, and valid raw hash. |
| Metric identity | `100%` of financial rows have V3 `metric_id`; `0` annual/quarterly collapses. |
| Forecast leakage | `0` Forecast rows accepted by Silver, graph, feature, or backtest loaders. |
| Quarantine evidence | `100%` hash-valid required fields; `0` deleted or mutated records. |
| Release integrity | `100%` required artifacts present and manifest-verified; `0` mixed release IDs. |

Silver row count has no minimum. A zero-row Silver release is publishable only when every source row is accounted for and all excluded actual candidates exist in permanent Quarantine with valid evidence.

## Implementation Tasks

- [ ] **Define V3 schemas and validators** in `src/omega/data/macro_micro_release.py`. Verify malformed provenance, revision order, hashes, and record types fail closed.
- [ ] **Add API preflight and cursor iteration** in `src/omega/quant/graph/fetcher.py`. Verify all 8 combinations, terminal cursors, repeated-cursor rejection, and durable checkpoints.
- [ ] **Refactor financial ingestion** in `scripts/fetch_financial_statements.py`. Verify future classification precedes actual validation; synthetic publication fallback and destructive dedupe are absent.
- [ ] **Refactor macro ingestion** in `src/omega/data/macro_pipeline.py`. Verify SBV/World Bank timestamp substitutions quarantine and as-of selection uses source revision order.
- [ ] **Implement permanent Quarantine and Forecast flows** through the shared release module. Verify replay appends resolution events without deleting evidence.
- [ ] **Implement lossless Metric ID migration** and update `src/omega/quant/graph/loader.py`. Verify annual and quarterly values remain distinct through load, join, pivot, graph node, and feature name.
- [ ] **Implement atomic multi-artifact publication and readers** using the proven manifest/pointer pattern from `scripts/update_market_data.py`. Verify CAS, rollback, and mismatched-generation rejection.
- [ ] **Add hermetic tests and migration fixtures** in the named test files. Verify exact replay, restatements, PIT invariance, timestamp conversion, Forecast exclusion, Quarantine retention, cursor resumption, coverage gates, and crash injection.
- [ ] **Run final verification last**: targeted pytest, repository master checklist, repository master verification, then write L2 evidence under `.ly_state/session/` for independent Role 20 review.

## Required Hermetic Verification

### Append-Only

- Exact replay leaves canonical row counts/hashes and active generation unchanged.
- A distinct restatement appends and becomes visible only after its own `available_at` and `ingested_at`.
- A late older revision remains stored but does not replace a later source revision.
- Two distinct revisions with the same ordering value quarantine; hash order never decides the winner.

### Quarantine

- Required fields are enforced.
- Raw evidence hash mismatch blocks publication.
- Replay preserves the original record and appends one resolution linked to the destination revision.
- Replaying the same resolution is idempotent; a different resolution appends.

### Metric ID

- The same `item_code` from annual and quarterly data survives migration, load, as-of join, pivot, graph materialization, and feature naming as two distinct metrics.
- Migration row accounting equals `100%`; no distinct revision disappears.

### Forecast

- Explicit source forecast enters Forecast before actual validation.
- Unconfirmed future row enters Quarantine.
- Forecast cannot enter historical Silver, `FinancialStatementLoader`, graph loaders, feature builders, or backtests.

### Publication Time

- Missing, invalid, date-only, +45/+90, year-end fabrication, fetch-time, and ingestion-time substitutions quarantine.
- Before-close stays same-session; exactly-at-close and after-close move to next session; weekends and holidays move to next session.

### Atomic Release

- Crash injection after each artifact write, after manifest write, before pointer replace, and during pointer replace never exposes a mixed generation.
- Stale generation and stale pointer hash both fail CAS.
- Reader rejects missing artifact, wrong hash, wrong schema, wrong row count, wrong cutoff, and mixed `release_id`.
- Rollback validates and atomically restores the prior release.
- Failure receipt and last cursor survive every injected crash.

## Done When

- All six blocker rows below are satisfied by code plus hermetic evidence.
- Quantitative gates pass exactly as specified.
- Existing active data remains readable until the V3 pointer switch succeeds.
- L2 report lists repo-local role/skill sources, exact changed files, commands, outputs, migration counts, artifact hashes with timestamps, and failure-injection evidence.
- Role 20 returns `[APPROVED]`; no self-approval is claimed here.

| Audit blocker | Closure evidence |
|---|---|
| Append-only | Separate identity/order, exact replay no-op, immutable distinct revisions, PIT tests. |
| Quarantine | Permanent evidence schema, hash validation, append-only resolution lineage. |
| Metric ID | End-to-end `endpoint:period_type:item_code`, lossless atomic migration, collision tests. |
| Forecast | Dedicated store, pre-validation classification, hard historical-loader rejection. |
| Publication timestamp | Exact RFC3339 source evidence, fail-closed substitutions, explicit session conversion. |
| Atomic deploy | One release/manifest/pointer for all four classes, CAS, verified readers, rollback/crash tests. |

## Repo-Local Planning Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/system-architect.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.ly_state/session/audit_reports/role20_macro_micro_data_v3_plan_20260810.md`
- `src/omega/data/macro_pipeline.py`
- `scripts/fetch_financial_statements.py`
- `src/omega/quant/graph/fetcher.py`
- `src/omega/quant/graph/loader.py`
- `scripts/update_market_data.py`
- `tests/test_fetch_financial_statements.py`
- `tests/test_macro_pipeline.py`

The only non-repo path read or written is the authorized `implementation_plan.md` artifact itself.
