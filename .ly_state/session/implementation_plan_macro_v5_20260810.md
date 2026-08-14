# Macro & Fundamental Data V5 - Remediation Implementation Plan

**Status:** L2 plan remediation complete; awaiting independent Role 20 audit
**Owner:** Role 6 `system-architect` (Tier 2, OpenCode)
**Gate:** `macro_micro_data_v5_plan`
**Supersedes:** `.ly_state/session/implementation_plan_macro_v4_20260810.md`
**Audit basis:** Advisory deep audit `[NEEDS_FIX]`, 9 implementation blockers plus 1 gate-control defect
**Scope:** Financial statements, macro indicators, historical loaders, derived ratios, release publication, compatibility migration, gate enforcement

## Goal

Produce one implementation-ready, fail-closed contract that resolves all ten required amendments without changing production code or approving the gate in this planning task.

## Required Amendment Closure Matrix

| # | Required amendment | V5 closure |
|---|---|---|
| 1 | Provider-specific completeness | Four named completeness modes, provider assignment, adapter/source pins, terminal evidence, and fail-closed preflight. |
| 2 | Release membership identity | Every artifact row carries the active candidate `release_id`; immutable origin is separate as `origin_release_id`, with `first_seen_release_id` for Quarantine. |
| 3 | Evidence and revision hashes | `receipt_sha256`, `record_evidence_sha256`, `provider_revision_key`, and `revision_id` are separate; all canonical hashes use `canonical_json_v1`. |
| 4 | Source-aware streams and provider reconciliation | `source` is part of every revision-stream key; canonical cross-provider choice is an explicit immutable reconciliation artifact. |
| 5 | Derived-record contract | Exact derived metric IDs, formula IDs/versions, ordered parent lineage, lineage hash, and lineage-bound revision semantics are specified. |
| 6 | Publication authority | Immutable manifests remain `state='sealed'`; only pointer CAS activates a release; activation evidence lives in the pointer and attempt ledger. |
| 7 | Generation zero and compatibility | A concrete sentinel, staged reader transition, post-activation `--output` export, legacy fallback limit, and monotonic rollback floor are specified. |
| 8 | Forecast ownership | `src/omega/data/macro_micro_release.py::classify_forecast_record` owns classification; exact tests are assigned. |
| 9 | Verification commands | Final verification is exactly the three required commands in this document. |
| 10 | Gate control | V5 gate metadata is complete and non-placeholder after independent audit; every non-grandfathered approved gate missing required fields hard-fails without strict-gate discovery. |

## Non-Negotiable Decisions

- Schema identifier is `macro_micro/v5`; V5 is both the plan revision and implementation schema version.
- Silver may be empty. Missing trustworthy publication evidence never permits a fabricated timestamp.
- Valid source-confirmed forecasts enter Forecast before historical validation; they never enter Silver or Quarantine.
- Existing canonical files and prior releases are never modified in place.
- Every requested work item ends in an adapter-proven terminal-success receipt or a durable failed attempt. Silent partial success is forbidden.
- Same revision replay is a canonical no-op. Distinct source revisions append immutably.
- Provider-native histories remain separate. Cross-provider canonicalization is explicit, inspectable, and reversible.
- A sealed manifest never becomes `published` or `active`; activation exists only in the CAS pointer and attempt ledger.
- No implementation or test artifact may mutate `phase_gates.json` for `macro_micro_data_v5_plan`; only an independent L3 audit may create the final gate record.

## Minimal File Plan

- Add `src/omega/data/macro_micro_release.py`: V5 schemas, `canonical_json_v1`, hash builders, completeness validators, forecast classifier, revision rules, reconciliation schema, derived lineage, sealed manifests, pointer CAS, readers, migration, rollback.
- Update `scripts/fetch_financial_statements.py`: direct VCI raw-envelope acquisition, immutable receipts, V5 normalization, derived ratio lineage, candidate release build, post-activation compatibility export.
- Update `src/omega/data/macro_pipeline.py`: pinned World Bank, Yahoo, and SBV adapters; provider completeness; exact publication evidence; append-only macro revisions.
- Update `src/omega/quant/graph/fetcher.py`: adapter preflight and the four completeness-mode iterators; opaque DataFrame financial acquisition is rejected.
- Update `src/omega/quant/graph/loader.py`: pointer-only actual reader after migration, source-aware keys, full `metric_id`, reconciliation selection, Forecast rejection.
- Update `scripts/sod_gate_enforcer.py`: direct post-cutoff required-field enforcement independent of `derive_strict_approval_timestamp()`.
- Extend `tests/test_fetch_financial_statements.py`, `tests/test_macro_pipeline.py`, `tests/test_financial_loader.py`, and `tests/test_strict_repo_local_skill_loading.py`.
- Add `tests/test_macro_micro_release.py` for release, lineage, reconciliation, CAS, migration, rollback, crash, and forecast classification contracts.
- Keep existing CLI entrypoints. Add no parallel fetch script, service, database, or dependency.

## Immutable Release Layout

```text
data/macro_micro/releases/<release_id>/
  bronze/financial_receipts.parquet
  bronze/macro_receipts.parquet
  bronze/record_evidence.parquet
  silver/financial_actual.parquet
  silver/macro_actual.parquet
  derived/financial_ratios.parquet
  quarantine/records.parquet
  quarantine/resolutions.parquet
  forecast/financial_forecast.parquet
  forecast/macro_forecast.parquet
  reconciliation/canonical_provider_selection.parquet
  migration/report.json
  manifest.json

data/macro_micro/current.json
.ly_state/session/macro_micro_attempts/<attempt_id>/
  attempt.json
  checkpoints/<work_item_id>.json
  events/<sequence>_<event_type>.json
  failure.json                         # failure only
```

Every release contains every listed release artifact, including schema-correct empty Parquet files. Every release artifact is immutable after manifest sealing. Attempt events are append-only and never used as canonical data.

## 1. Provider Adapter and Completeness Contract

### Pinned Runtime and Adapter Sources

| Provider | Adapter ID/version | Completeness mode | Pinned source and runtime |
|---|---|---|---|
| VCI financial | `vci_financial_raw/v1` | `explicit_single_envelope_terminal` | `vnstock==4.0.4`; source contract inspected at `vnstock/explorer/vci/financial.py`; direct base endpoint `https://iq.vietcap.com.vn/api/iq-insight-service`; transport `requests==2.33.1`. |
| World Bank indicators | `world_bank_v2/v1` | `authoritative_numbered_pages` | Versioned REST path `https://api.worldbank.org/v2/country/VN/indicator/{indicator}`; transport `requests==2.33.1`. |
| Yahoo USD/VND chart | `yahoo_chart_v8/v1` | `explicit_single_envelope_terminal` | `https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X`; transport `requests==2.33.1`. |
| SBV interbank table | `sbv_interbank_html/v1` | `immutable_html_snapshot` | `https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/tk/lsttlnh`; `playwright==1.62.0`; Chromium `151.0.7922.34`; `beautifulsoup4==4.14.3`. |
| Shared storage | `macro_micro_storage/v1` | N/A | `pandas==2.3.3`; `pyarrow==23.0.1`. |

Every Bronze receipt stores `adapter_id`, `adapter_version`, `adapter_source`, exact request scope, request URL and parameters, response status and selected headers, raw response bytes, `receipt_sha256`, request/response/checksum timestamps, and one completeness proof. An adapter-version or source-contract change requires a new adapter version and schema fixture.

The public `vnstock` financial methods are not acquisition evidence: they return opaque DataFrames and default-truncate to four rows. V5 calls the pinned VCI REST envelope directly. Any fallback to `GraphFetcher.financial()` or another opaque DataFrame path fails preflight as `OPAQUE_PROVIDER_RESPONSE`.

### Four Completeness Modes

`cursor_token`

- Request one page using only the provider-issued cursor from the immediately preceding response.
- The first request uses the adapter-defined null cursor. Each nonterminal response must expose a nonempty `next_cursor` token.
- Success requires an explicit provider terminal marker with no next cursor. Repeated, missing, client-generated, cyclic, or scope-changing cursors fail as `CURSOR_PROTOCOL_VIOLATION`.
- Persist every cursor transition before requesting the next page. Resume starts from the last hash-verified transition.
- No current V5 provider is assigned this mode. The shared iterator remains implemented and hermetically tested; it is never used as a fallback for another mode.

`authoritative_numbered_pages`

- Page 1 must return provider metadata containing current `page`, authoritative total `pages`, `per_page`, and `total`.
- Fetch exactly pages `1..pages`. Every page must echo its requested number; `pages`, `per_page`, request scope, and dataset identity must remain stable.
- Success requires all page numbers exactly once and an accounting check against provider `total`. Guessed pages, inferred offsets, local slicing, missing metadata, or changing totals fail closed.
- World Bank v2 uses this mode. The metadata object in the raw two-envelope response is part of every page's completeness evidence.

`explicit_single_envelope_terminal`

- The adapter declares one immutable request scope and one nonpaginated response envelope for that scope.
- Success requires the pinned envelope schema, exactly one successful result envelope, no pagination/cursor fields, no provider truncation/error marker, and an adapter terminal receipt stating `terminal_reason=single_envelope_contract`.
- VCI scope is one `(symbol, endpoint, period_type)` request. Yahoo scope is one bounded `(symbol, interval, period1, period2)` chart request.
- The VCI adapter rejects the known four-row helper default, unexplained row caps, or any envelope whose raw schema no longer proves single-envelope behavior. Yahoo rejects missing chart result, unequal timestamp/value arrays, or partial/error payloads.

`immutable_html_snapshot`

- Render one URL with the pinned browser, wait for the configured table selector, then capture UTF-8 HTML bytes once into Bronze before parsing.
- The immutable snapshot, not a live DOM or parsed DataFrame, is the evidence boundary. Parsing is replayable only from those stored bytes.
- Success requires the expected observed-date field, one configured rate table, required headers, at least one valid row, no detected pagination control for the configured table, and `SHA256(stored_bytes) == receipt_sha256`.
- SBV uses this mode. Its completeness claim is limited to the rendered page snapshot at the captured response time; V5 makes no unsupported claim of hidden historical coverage.

### Adapter Preflight and Work Accounting

- Probe all eight VCI endpoint/period pairs (`4 endpoints x 2 periods`) before bulk acquisition.
- Probe every configured World Bank indicator, the Yahoo request shape, and the SBV rendered selector/header contract.
- Verify source publication field, forecast marker, provider revision field, business rows, and assigned completeness proof against versioned fixtures.
- Abort the candidate release on any schema or completeness drift. Persist the exact failed receipt and reason.
- Require one terminal-success receipt for every requested `(symbol, endpoint, period_type)` and macro work item. Authoritative empty responses count only when the assigned adapter explicitly proves terminal emptiness.

## 2. Release Membership and Immutable Origin

Every row physically contained in release `<release_id>` carries `release_id == <release_id>`. This is a membership field, not an origin field. Manifest validation scans every artifact and rejects any row with a different or null membership ID.

Canonical Actual, Forecast, Derived, reconciliation, receipt, and resolution rows also carry immutable `origin_release_id`, defined as the first sealed release containing that logical immutable row. When a prior row is materialized into a later complete release, only membership `release_id` changes; `origin_release_id`, business identity, revision identity, and evidence identity remain unchanged.

Quarantine rows carry:

- `release_id`: current containing release.
- `first_seen_release_id`: first sealed release that recorded the invalid evidence.
- `quarantine_id`: immutable identity independent of both membership fields.

The migration report accounts for inherited versus newly originated rows by artifact. `origin_release_id` and `first_seen_release_id` must reference an existing release no newer than the containing release. A row may not claim a future or unknown origin.

Fields excluded from immutable identities: `release_id`, filesystem paths, attempt IDs, pointer generations, export paths, and current-clock validation timestamps.

## 3. Deterministic Serialization and Hash Separation

### `canonical_json_v1`

All deterministic IDs and canonical evidence hashes use one implementation: `src/omega/data/macro_micro_release.py::canonical_json_v1`.

Rules:

1. Validate against the target schema before serialization. Unknown fields and nonfinite numbers fail.
2. Normalize strings to Unicode NFC. Preserve case unless a field-specific schema normalizer says otherwise.
3. Encode timestamps as UTC RFC3339 with exactly six fractional digits and `Z`, for example `2026-08-10T01:02:03.000000Z`.
4. Encode dates as `YYYY-MM-DD`.
5. Encode decimal business values as base-10 strings: no exponent, no leading plus sign, no trailing fractional zeroes, and both positive and negative zero become `0`. Binary floats are converted through the schema-declared decimal parser, never by platform `repr`.
6. Encode integers in canonical base 10, booleans as JSON booleans, missing optional values as JSON `null`, and byte evidence only through an explicit base64 field or its SHA-256 field.
7. Preserve array order. Sort object keys by Unicode code point.
8. Emit compact JSON with separators `,` and `:`, `ensure_ascii=false`, UTF-8, no BOM, and no trailing newline.

Hermetic fixtures assert exact serialized bytes and SHA-256 values across key order, timezone offsets, decimal spellings, Unicode composition, nulls, and Windows/Linux line-ending inputs.

### Four Distinct Identities

`source_receipt_id`

- Stable adapter-generated locator for one exact raw provider response or HTML snapshot.
- Built from adapter ID/version, normalized request scope, request ordinal, and response ordinal.
- It is a locator, not a content hash or revision key.

`receipt_sha256`

- `SHA256(exact_raw_response_bytes)`.
- HTTP bodies and rendered HTML are hashed before parsing. Re-read verification is mandatory before normalization and publication.
- Headers, fetch timestamps, parsed rows, and filesystem paths are excluded from this byte hash.

`record_evidence_sha256`

- `SHA256(canonical_json_v1(record_evidence_v1))`.
- `record_evidence_v1` contains `source_receipt_id`, `receipt_sha256`, `source_record_locator`, adapter ID/version, exact source field paths/selectors, and the exact source field values used to create one normalized record.
- The immutable origin evidence hash is stored on the canonical record. Later exact-replay evidence appends to `bronze/record_evidence.parquet` without changing `revision_id` or the origin evidence link.

`provider_revision_key`

- Exact provider-supplied revision timestamp, sequence, version token, or immutable document revision key, normalized by the pinned adapter.
- It is never synthesized from `receipt_sha256`, `record_evidence_sha256`, ingestion time, row order, content hash, or current time.
- Missing or ambiguous provider revision evidence routes the record to Quarantine as `REVISION_ORDER_MISSING`; empty Silver remains valid.

`revision_id`

- `SHA256(canonical_json_v1(revision_identity_v1))`.
- `revision_identity_v1` contains schema version, dataset, `source`, source-aware logical key, record type, normalized business payload, exact source publication timestamp, revision order kind/value, and `provider_revision_key`.
- It excludes both receipt/evidence hashes, all release membership/origin fields, `ingested_at`, attempt IDs, and paths. The same provider revision observed in a later receipt remains the same canonical revision.

Conflicts fail closed:

- Same `revision_id`, same canonical revision content: record no-op; append only unseen evidence links.
- Same `revision_id`, different canonical revision content: `REVISION_ID_CONFLICT`, candidate release failure.
- Same `record_evidence_sha256`, different canonical evidence object: `RECORD_EVIDENCE_HASH_CONFLICT`, candidate release failure.
- Same `source_receipt_id`, different `receipt_sha256`: `RECEIPT_ID_CONFLICT`, candidate release failure.

## 4. Canonical Records, Source-Aware Revisions, Reconciliation

### Common Canonical Fields

Actual and Forecast rows require:

| Field | Contract |
|---|---|
| `schema_version` | Exactly `macro_micro/v5`. |
| `release_id` | Current containing release membership. |
| `origin_release_id` | First sealed release containing this immutable revision. |
| `dataset` | Stable dataset identifier. |
| `record_type` | Exactly `actual` or `forecast`. |
| `source` | Stable provider ID; never null. |
| `source_url` | Exact endpoint or document URL. |
| `source_receipt_id` | Origin raw receipt locator. |
| `receipt_sha256` | Origin raw response byte hash. |
| `source_record_locator` | Stable row/object locator inside the raw receipt. |
| `record_evidence_sha256` | Canonical origin record-evidence hash. |
| `source_published_at` | Exact timezone-aware source timestamp evidenced by the receipt. |
| `available_at` | Deterministic HOSE-session availability derived from `source_published_at`. |
| `ingested_at` | Actual timezone-aware ingestion timestamp; never a publication substitute. |
| `provider_revision_key` | Exact provider revision key. |
| `revision_order_kind` | Exactly `source_revision_at` or `revision_seq` for provider records. |
| `source_revision_at` | Exact provider revision timestamp when timestamp ordering is selected. |
| `revision_seq` | Positive provider sequence when sequence ordering is selected. |
| `revision_id` | Immutable normalized provider-revision identity. |

`revision_order_kind` selects exactly one non-null order field. One source-aware stream cannot change ordering kind. Distinct revisions with the same order value enter Quarantine as `REVISION_ORDER_COLLISION`; revision hash, receipt order, file order, and ingestion order never break the tie.

### Logical and Revision-Stream Keys

| Dataset | Canonical logical key | Provider revision-stream key |
|---|---|---|
| Financial | `(dataset, symbol, metric_id, fiscal_period_end)` | `(dataset, source, symbol, metric_id, fiscal_period_end)` |
| Macro | `(dataset, indicator, observation_date)` | `(dataset, source, indicator, observation_date)` |

All append, replay, collision, and as-of ordering rules operate on the provider revision-stream key including `source`. Revisions from two providers are never placed in one native revision stream.

### Provider-Native As-Of Selection

1. Validate pointer, sealed manifest, artifact hashes, schemas, and row membership.
2. Read Actual only and require `record_type == actual`.
3. Filter `available_at <= cutoff` and `ingested_at <= cutoff`.
4. Group by the provider revision-stream key including `source`.
5. Select the greatest eligible provider order value according to the stream's fixed order kind.
6. Reject ties or mixed order kinds.

This produces one eligible native revision per provider. It does not yet produce a cross-provider canonical value.

### Explicit Canonical-Provider Reconciliation

`reconciliation/canonical_provider_selection.parquet` is required in every release. Canonical readers may choose among providers only through this artifact.

Each immutable reconciliation decision requires:

| Field | Contract |
|---|---|
| `schema_version` | `canonical_provider_selection/v1`. |
| `release_id` | Current containing release. |
| `origin_release_id` | First sealed release containing this decision. |
| `dataset` | Financial or macro dataset. |
| `canonical_key_json` | `canonical_json_v1` encoding of the canonical logical key without `source`. |
| `selection_policy_id` | Named policy, for example `configured_source_priority`. |
| `selection_policy_version` | Immutable semantic version. |
| `candidate_sources` | Ordered source IDs considered by the policy. |
| `candidate_revision_ids` | Ordered one-to-one revision IDs for those sources. |
| `selected_source` | Exactly one candidate source, or null when unresolved. |
| `selected_revision_id` | Matching candidate revision, or null when unresolved. |
| `decision_status` | `selected` or `unresolved`. |
| `decision_reason` | Stable machine-readable policy outcome. |
| `decision_available_at` | Maximum availability of all inputs required for this decision. |
| `decision_ingested_at` | Maximum ingestion time of all inputs required for this decision. |
| `decision_input_sha256` | Hash of canonical policy, ordered candidates, and their revision IDs. |
| `reconciliation_id` | Hash of canonical key, policy/version, input hash, and outcome. |

Candidate arrays are ordered by configured source priority, then source ID; order is persisted and hashed. A new candidate or policy version appends a new reconciliation decision. Earlier decisions remain immutable for earlier cutoffs.

Canonical as-of readers first perform provider-native selection, then filter reconciliation decisions by both decision cutoffs, match the exact eligible candidate revision set, and return only the selected revision. Missing, stale, mismatched, or unresolved decisions fail closed; readers never use `drop_duplicates`, provider arrival order, or an implicit source preference.

The release manifest records the reconciliation policy file hash and policy version. Changing source priority creates a new release and new decisions; it never rewrites native histories.

### Append-Only Replay Rules

- Same source-aware logical key plus same `revision_id`: canonical revision no-op; append only unseen evidence links.
- Same source-aware logical key plus distinct ordered `revision_id`: append immutable revision.
- Late older provider revision remains stored and is selected only where its source order and cutoffs make it eligible.
- Prior complete releases remain byte-for-byte unchanged. Candidate releases materialize prior immutable rows with current membership `release_id` and preserved origin fields.

## 5. Metric IDs and Derived-Record Schema

### Frequency-Safe Metric IDs

- Provider financial metric ID remains `endpoint:period_type:item_code` throughout Bronze normalization, Actual, Forecast, Quarantine details, joins, pivots, graph nodes, and feature names.
- Preserve `endpoint`, `period_type`, and `item_code` as separate columns. Split `metric_id` with a maximum of two delimiters so colons inside `item_code` remain lossless.
- Financial joins use `(symbol, metric_id)`; pivots use `metric_id`; graph and feature identities include the full metric ID. Bare `item_code` is forbidden at these boundaries.

Exact derived metric IDs:

- `derived_ratios:<period_type>:current_ratio`
- `derived_ratios:<period_type>:debt_to_equity`

No other derived metric is added in V5.

### Formula Registry

| Derived metric suffix | `formula_id` | `formula_version` | Ordered expression |
|---|---|---|---|
| `current_ratio` | `omega.financial.current_ratio` | `1.0.0` | parent 0 `balance_sheet:<period_type>:current_assets` divided by parent 1 `balance_sheet:<period_type>:current_liabilities` |
| `debt_to_equity` | `omega.financial.debt_to_equity` | `1.0.0` | parent 0 `balance_sheet:<period_type>:total_liabilities` divided by parent 1 `balance_sheet:<period_type>:equity` |

The denominator must be nonzero. Both parent values and result must be finite canonical decimals. Missing parents, zero denominator, different symbols/periods, or mixed selected parent providers produce no derived value and persist a reasoned derivation rejection; they are never coerced to zero.

### Derived Row Fields

`derived/financial_ratios.parquet` uses `derived_record/v1` and requires:

| Field | Contract |
|---|---|
| `schema_version` | `derived_record/v1`. |
| `release_id` | Current containing release. |
| `origin_release_id` | First sealed release containing this derived revision. |
| `dataset` | `financial_derived`. |
| `record_type` | `actual`; V5 does not derive forecast ratios. |
| `source` | Exactly `derived_ratios`. |
| `symbol`, `period_type`, `fiscal_period_end`, `metric_id` | Exact derived logical key fields. |
| `item_value` | Deterministic formula result as schema decimal. |
| `formula_id`, `formula_version` | Exact registry identity above. |
| `ordered_parent_lineage` | Ordered list of parent structs; numerator first, denominator second. |
| `lineage_sha256` | Hash of the exact ordered parent lineage. |
| `source_published_at` | Maximum parent source publication timestamp. |
| `available_at` | Maximum of parent and required reconciliation-decision availability timestamps. |
| `ingested_at` | Maximum of parent and required reconciliation-decision ingestion timestamps. |
| `provider_revision_key` | Null; no provider revision is fabricated for derived data. |
| `revision_order_kind` | Exactly `parent_lineage`. |
| `record_evidence_sha256` | Hash of canonical formula/version, computed value, and ordered lineage evidence. |
| `revision_id` | Hash of derived logical key, formula/version, canonical value, and `lineage_sha256`. |

Each ordered parent struct contains exactly:

```text
ordinal
role                         # numerator or denominator
parent_dataset
parent_source
parent_symbol
parent_metric_id
parent_fiscal_period_end
parent_revision_id
parent_record_evidence_sha256
parent_value_decimal
parent_available_at
parent_ingested_at
reconciliation_id
```

`lineage_sha256 = SHA256(canonical_json_v1(ordered_parent_lineage))`. Parent order is semantic and may not be sorted after construction.

Derived revisions have no independent latest-wins order. At a cutoff, the reader first resolves the exact canonical parent revisions, then accepts only the derived row whose `lineage_sha256` matches those parents and formula version. Zero or multiple matches fail closed. This prevents hash ordering, future parent substitutions, and silent provider mixing.

## 6. Dedicated Forecast Classifier

Ownership is exact: `src/omega/data/macro_micro_release.py::classify_forecast_record`.

The function receives a parsed adapter record plus immutable evidence metadata and returns one typed classification result. It executes in this order:

1. Validate raw envelope identity, receipt/evidence hashes, source locator, period fields, and adapter forecast-marker contract.
2. If the pinned source explicitly marks forecast, estimate, guidance, or consensus, classify as Forecast before any historical-actual rule.
3. Validate that Forecast candidate against the Forecast schema, including exact publication timestamp and provider revision key.
4. If a future-period row lacks an explicit source forecast marker, classify to Quarantine with `FUTURE_PERIOD_UNCONFIRMED`.
5. Validate only the remaining record as historical Actual.

Hard boundaries:

- Valid source-confirmed forecasts are never Quarantine records.
- Silver and Derived accept only `record_type == actual`.
- `FinancialStatementLoader`, graph loaders, feature builders, and backtest entrypoints reject Forecast paths, Forecast schema versions, or non-actual rows before joins and pivots.
- Historical readers expose no flag that weakens this boundary. Forecast access requires a separate explicit API outside historical backtests.

Exact classifier tests in `tests/test_macro_micro_release.py`:

- `test_classify_forecast_record_routes_explicit_forecast_before_actual_validation`
- `test_classify_forecast_record_quarantines_unconfirmed_future_period`
- `test_classify_forecast_record_accepts_confirmed_historical_actual`
- `test_classify_forecast_record_rejects_implicit_date_based_forecast_inference`

Exact trust-boundary tests in `tests/test_financial_loader.py`:

- `test_financial_loader_rejects_forecast_path`
- `test_financial_loader_rejects_forecast_schema`
- `test_financial_loader_rejects_non_actual_rows`

## 7. Exact Publication Evidence and Permanent Quarantine

`source_published_at` is accepted only when exact time and timezone appear in immutable source evidence and the extractor records the exact JSON path, HTML selector, document field, or signed field used. Parsing must produce a timezone-aware RFC3339 value.

The following route to Quarantine, never Actual or Forecast:

- Date-only publication values.
- Financial `fiscal_period_end + 45/90 days` fallbacks.
- World Bank fabricated year-end or next-year publication dates.
- SBV ingestion time, fetch time, file modification time, or current clock substitutions.
- Any timestamp lacking an evidence path and valid `record_evidence_sha256`.
- Missing or synthesized provider revision keys.

Availability uses `Asia/Ho_Chi_Minh`, versioned `config/vn_holidays.json`, session open `09:00`, and close `15:00`:

- Trading day strictly before `15:00`: `available_at = source_published_at`.
- Trading day at or after `15:00`: next trading session at `09:00`.
- Weekend or holiday: next trading session at `09:00`.
- `available_at` may never precede `source_published_at`.
- As-of reads require both availability and ingestion cutoffs.

Every Quarantine row requires `schema_version`, `quarantine_id`, current `release_id`, immutable `first_seen_release_id`, dataset, reason code, source, source URL, source receipt ID, `receipt_sha256`, source locator, `record_evidence_sha256`, quarantined timestamp, exact raw evidence bytes or byte-preserving encoding, raw evidence SHA-256, and versioned details.

Quarantine rules:

- `quarantine_id` excludes current release membership and hashes schema, dataset, source, reason, locator, and evidence hash.
- Same exact invalid evidence/reason is a no-op; distinct evidence or reason appends.
- Never delete, update, or move a Quarantine record.
- Replay creates a new valid revision and appends a resolution event; it never edits the original evidence.
- Verify raw evidence hashes before staging and again through the published reader.

Minimum new reason codes include `OPAQUE_PROVIDER_RESPONSE`, `NUMBERED_PAGE_PROTOCOL_VIOLATION`, `SINGLE_ENVELOPE_PROTOCOL_VIOLATION`, `HTML_SNAPSHOT_PROTOCOL_VIOLATION`, `RECEIPT_ID_CONFLICT`, `RECORD_EVIDENCE_HASH_CONFLICT`, `DERIVED_PARENT_SOURCE_MISMATCH`, and all V4 timestamp, forecast, revision-order, metric, cursor, schema, and raw-hash codes.

## 8. Sealed Manifest and Pointer-CAS Publication Authority

### Sealed Manifest

`manifest.json` is written once with `state='sealed'`. It contains release ID/sequence, schema versions, cutoff, adapter pins, reconciliation policy version, every required artifact relative path, SHA-256, row count, schema fingerprint, current-membership count, inherited/origin counts, and the release-level accounting checks.

Seal procedure:

1. Write and fsync every candidate artifact under a new release directory.
2. Re-read every artifact; validate hash, schema, row count, membership `release_id`, origin constraints, cross-artifact foreign keys, completeness accounting, and PIT constraints.
3. Serialize the manifest with `canonical_json_v1`, write/fsync it atomically, and compute `manifest_sha256` from its exact bytes.
4. Re-open the manifest and all artifacts through the production reader validator.

The manifest is never mutated to `validated`, `published`, `active`, or `rolled_back`. `state='sealed'` is the only publishable manifest state.

### Exact Generation-Zero Sentinel

Before the first V5 release, `data/macro_micro/current.json` is atomically initialized, using create-new semantics, to the canonical bytes of:

```json
{activated_at:null,activation_attempt_id:null,activation_kind:genesis,active_manifest_path:null,active_manifest_sha256:null,active_release_id:null,active_release_sequence:0,legacy_fallback_allowed:true,pointer_generation:0,pointer_schema_version:macro_micro_pointer/v1,previous_pointer_sha256:null,rollback_floor_release_sequence:0}
```

These are the exact UTF-8 `canonical_json_v1` bytes: no BOM and no trailing newline. `GENESIS_POINTER_SHA256` is exactly `76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`. An absent pointer may be initialized once. An existing absent-field, noncanonical, or non-sentinel pointer is not guessed or overwritten.

### Active Pointer Schema

An active pointer has the same schema with non-null release/manifest/activation fields. `pointer_generation` increases by exactly one for every activation, rollback, or rollback-floor advance. `active_release_sequence` identifies the selected immutable release and may decrease only for a valid rollback. `rollback_floor_release_sequence` never decreases.

### CAS Activation

The pointer is the sole publication authority:

1. Acquire the pointer lock.
2. Read current pointer bytes privately and verify schema plus SHA-256.
3. Compare both expected pointer hash and expected `pointer_generation`.
4. Validate the target sealed manifest and all artifacts again.
5. Require target release sequence at or above the current rollback floor.
6. Build a next pointer with generation `current + 1`, target release/manifest identity, activation attempt ID/kind/time, prior pointer hash, and a nondecreasing rollback floor.
7. Write/fsync a same-directory temporary pointer, atomically replace `current.json`, fsync the directory where supported, then re-read and verify exact bytes.
8. Release the lock and append an immutable `activation_succeeded` event containing old/new pointer hashes, generations, target manifest hash, and timestamp.

Any compare mismatch, validation failure, or replace failure leaves the prior pointer authoritative. No manifest mutation may substitute for a failed pointer CAS.

### Attempt Ledger and Failures

`attempt.json` fixes attempt ID, candidate release ID/sequence, prior pointer hash/generation, requested scope, cutoff, and adapter pins. Checkpoints persist the last hash-verified completeness transition per work item. Ordered event files record seal, activation, compatibility export, rollback, and floor advance.

`failure.json` is fsynced on failure and contains phase, exception type/message, timestamps, completed artifact hashes, terminal-work accounting, last durable checkpoints, target manifest identity, and observed pointer identity. Failed candidates and receipts remain immutable; resume starts a new attempt and reuses only hash-verified evidence.

## 9. First Generation, `--output`, Reader Transition, Rollback Floor

### Legacy-to-Pointer Reader Transition

1. Deploy pointer-aware readers before first activation. With the exact generation-zero sentinel and `legacy_fallback_allowed=true`, they may read only the existing legacy paths.
2. Inventory and replace every in-repo direct read of `data/financial_statements_2015_now.parquet` and `data/macro_indicators.parquet`. Only migration input and compatibility-export code may retain those path constants.
3. Build release sequence 1 from byte-preserved legacy inputs plus new immutable provider evidence. Record source file hashes and full row accounting in `migration/report.json`.
4. CAS from `GENESIS_POINTER_SHA256` to sealed release 1. Pointer-aware readers immediately use release 1 and must not fall back while a nonzero active release is selected.
5. Complete post-activation compatibility export and reader smoke checks.
6. Perform a second CAS retaining release 1 while setting `rollback_floor_release_sequence=1` and `legacy_fallback_allowed=false`. This `cutover_committed` event ends legacy fallback permanently.

After floor commit, a missing, corrupt, or invalid active release hard-fails. It never falls back to legacy direct files.

### `--output` Compatibility Contract

- Keep `scripts/fetch_financial_statements.py --output PATH` for compatibility. It does not select the release directory and is never publication authority.
- After successful pointer activation, re-open the active pointer through the validated reader and create an Actual-only compatibility projection at `PATH`.
- Write Parquet metadata containing `macro_micro_release_id`, `macro_micro_manifest_sha256`, and `macro_micro_schema_version`; write by same-directory temp file, fsync, atomic replace, and re-read hash/schema validation.
- Forecast, Quarantine, reconciliation, receipts, derived lineage metadata, and alternate providers are not silently flattened into this export. The projection contains the legacy-compatible financial Actual columns plus full `metric_id`; unsupported columns require explicit versioned consumer migration.
- On first-generation cutover before floor commit, export or smoke-check failure triggers a CAS rollback to the generation-zero sentinel and leaves the old export untouched.
- After floor commit, export failure records `compatibility_export_failed`, preserves the old export, returns a nonzero CLI status, and does not roll back the authoritative pointer.
- A `--output` path inside `data/macro_micro/releases/`, equal to `current.json`, or equal to an immutable receipt/manifest path is rejected.

### Lossless Generation-One Migration

- Read exactly `data/financial_statements_2015_now.parquet` and `data/macro_indicators.parquet`; preserve their original bytes as `migration/legacy/financial_statements_2015_now.parquet` and `migration/legacy/macro_indicators.parquet` inside release 1, and include both files in the sealed manifest.
- Preserve each legacy input byte-for-byte under the sealed release migration evidence and record its SHA-256 before parsing.
- Preflight required columns and values before transformation.
- Classify explicit forecasts before actual validation.
- Construct full financial `metric_id`; never infer frequency from row order.
- Preserve every distinct annual/quarterly provider revision. Count exact duplicate occurrences without collapsing distinct revisions.
- Route ambiguous rows to permanent Quarantine.
- Require `legacy_input_rows == migrated_actual + migrated_forecast + quarantined_rows + exact_duplicate_occurrences` for each input.
- Require zero duplicate V5 keys `(source, symbol, metric_id, fiscal_period_end, revision_id)` and valid origin/membership fields.
- Failed migration never edits legacy files, the genesis pointer, or any prior release.

### Rollback Floor

- Release sequences are positive, immutable, and monotonically assigned. Pointer generations are separate and increase on every pointer change.
- A rollback validates the target sealed release exactly like a normal reader, requires `target_release_sequence >= rollback_floor_release_sequence`, then performs another pointer CAS and appends a rollback event.
- The floor may advance through a dedicated CAS after compatibility/schema retirement evidence. It may never decrease, including during rollback.
- Sequence 0 is the genesis sentinel, not a release. It is a legal rollback target only before the first `cutover_committed` floor advance.
- Deleting releases at or above the rollback floor is outside V5 and forbidden by this plan.

## 10. Gate Metadata and Direct Post-Cutoff Enforcement

### V5 Gate Record Boundary

This L2 planning task does not create, edit, approve, or pre-populate `macro_micro_data_v5_plan` in `.ly_state/session/phase_gates.json`.

Only after a real independent Role 20 audit may L3 write the V5 gate record. The record must contain concrete audit-derived values, not `N/A`, `[TBD]`, empty strings, copied prior-session identities, or invented session keys.

Required V5 gate fields:

```text
phase_name                       = macro_micro_data_v5_plan
timestamp                        = actual L3 completion timestamp
l2_session_id                    = l2_role6_macro_micro_data_v5_plan_20260810
l2_completed                     = true
l2_role_id                       = 6
l2_role_name                     = system-architect
l3_session_id                    = actual Role 20 session ID
l3_session_key                   = actual Role 20 session key
l3_role_id                       = 20
l3_role_name                     = compliance-officer
audit_report_path                = .ly_state/session/audit_reports/role20_macro_micro_data_v5_plan_20260810.md
final_verdict                    = actual bracketed Role 20 verdict
sod_boundary_checked             = true only when evidenced
writer_auditor_separated         = true only when evidenced
repo_local_skill_sources         = exact repo-local L2 and L3 role/skill files evidenced by both reports
forbidden_path_scan              = exact scoped no-authoritative-reliance result
```

`phase_name` must equal the JSON gate key. The audit report must name the exact L2 session above. An approval record with missing or placeholder identity is invalid even when the report text contains `[APPROVED]`.

### Enforcer Repair

In `scripts/sod_gate_enforcer.py`, define one typed required-field set for every approved, non-superseded, non-residual gate not proven grandfathered by a valid timestamp strictly before `SKILL_LOADING_CUTOFF`:

```text
phase_name
timestamp
l2_session_id
l2_completed
l2_role_id
l2_role_name
l3_session_id
l3_session_key
l3_role_id
l3_role_name
audit_report_path
final_verdict
sod_boundary_checked
writer_auditor_separated
repo_local_skill_sources
forbidden_path_scan
```

Enforcement order:

1. A gate is grandfathered only when it has a valid timestamp strictly before `SKILL_LOADING_CUTOFF` and qualifies under existing explicit legacy rules. Missing or invalid timestamps are not grandfathered.
2. For every other approved or partially approved gate, calculate missing fields directly and hard-fail before role/report validation.
3. Require `l2_completed is True`, boolean SOD fields, valid concrete session identifiers/keys, matching `phase_name`, valid roles, writer/auditor separation, valid audit path/report verdict, exact repo-local source evidence, and nonempty forbidden-path scan evidence.
4. Reject placeholder tokens and whitespace-only strings in session identity, report path, phase name, and verdict-bearing fields.
5. Validate repo-local source paths against declared role frontmatter and repository roots.
6. Keep explicit residual/legacy reconciliation behavior, but do not let discovery or approval time of a strict gate weaken current gate validation.

Remove `strict_approval_ts` from the decision path for missing required fields. Delete `derive_strict_approval_timestamp()` if it has no remaining non-enforcement caller. Post-cutoff failure must be identical whether the strict gate exists, is renamed, is malformed, or is absent.

Required gate-control tests in `tests/test_strict_repo_local_skill_loading.py`:

- `test_post_cutoff_missing_fields_fail_without_discoverable_strict_gate`
- `test_missing_or_invalid_timestamp_is_not_grandfathered`
- `test_phase_name_l2_completed_and_l3_session_key_are_required`
- `test_placeholder_session_identity_is_rejected`
- `test_valid_pre_cutoff_gate_remains_explicitly_grandfathered`
- `test_complete_post_cutoff_gate_passes_without_strict_gate_dependency`

## Quantitative Publication Gates

All thresholds are release-blocking:

| Gate | Required threshold |
|---|---|
| VCI adapter preflight | `8/8` endpoint-period pairs pass the pinned raw-envelope schema. |
| Macro adapter preflight | `100%` of configured World Bank, Yahoo, and SBV work items pass pinned schemas. |
| Completeness assignment | `100%` of work items use exactly one declared completeness mode; no generic fallback. |
| Terminal receipts | `100%` requested work items have terminal-success receipts or the attempt fails. |
| Raw receipt integrity | `100%` exact raw bytes match `receipt_sha256`. |
| Record evidence integrity | `100%` evidence objects reproduce `record_evidence_sha256` through `canonical_json_v1`. |
| Release membership | `100%` artifact rows have current containing `release_id`; `0` mixed-generation rows. |
| Immutable origin | `100%` inherited rows preserve valid `origin_release_id` or `first_seen_release_id`. |
| Revision integrity | `100%` revisions have source-aware streams, provider keys, and one valid source order; `0` hash tie-breaks. |
| Classification accounting | `100%` normalized source records map once to Actual, Forecast, Quarantine, or documented exact replay. |
| Reconciliation | `100%` canonical cross-provider reads have an exact eligible `selected` decision; unresolved decisions return no canonical value. |
| Metric identity | `100%` financial rows retain full frequency-safe metric IDs; `0` annual/quarterly collapses. |
| Derived lineage | `100%` derived rows match registered formula/version and ordered-parent lineage hash; `0` mixed-provider parent sets. |
| Forecast leakage | `0` Forecast rows accepted by Silver, Derived, historical loader, graph, feature, or backtest paths. |
| Quarantine evidence | `100%` required evidence hash-valid; `0` deleted or mutated records. |
| Release integrity | `100%` required artifacts present under one sealed manifest; `0` manifest state mutations. |
| Publication authority | `100%` active releases selected by verified pointer CAS; `0` manifest-only activations. |
| Rollback safety | `0` rollbacks below the monotonic floor; genesis rollback only before cutover commit. |
| Gate metadata | `100%` required V5 fields concrete after L3 audit; post-cutoff missing fields always hard-block. |

Silver and Derived row counts have no minimum. A zero-row release is valid only when every requested source record and exclusion is fully evidenced and accounted for.

## Implementation Tasks

- [ ] Implement `canonical_json_v1`, hash separation, membership/origin validators, source-aware revision schemas, and exact replay evidence links in `src/omega/data/macro_micro_release.py`.
- [ ] Implement the four completeness modes and pinned adapter preflight in `src/omega/quant/graph/fetcher.py`; reject opaque financial DataFrames.
- [ ] Replace financial acquisition with direct VCI raw envelopes in `scripts/fetch_financial_statements.py`; remove four-row truncation, synthetic availability, destructive dedupe, and overwrite publication.
- [ ] Implement World Bank numbered pages, Yahoo bounded single envelope, and immutable SBV snapshots in `src/omega/data/macro_pipeline.py`; remove fabricated/fetch-time publication substitutions.
- [ ] Implement `classify_forecast_record` and permanent Forecast/Quarantine routing before actual validation.
- [ ] Implement full metric IDs, the two exact formula-registry entries, ordered parent lineage, and lineage-bound derived selection.
- [ ] Implement explicit canonical-provider reconciliation and update loaders to consume it after provider-native as-of selection.
- [ ] Implement sealed release manifests, genesis pointer, lock-protected CAS, attempt ledger, pointer-only readers, post-activation `--output` export, migration, rollback, and monotonic floor.
- [ ] Transition all in-repo legacy readers; permit fallback only at the exact generation-zero sentinel.
- [ ] Repair gate enforcement and its unit tests; do not mutate the V5 gate from implementation code.
- [ ] Add hermetic fixtures and tests in the exact named files; preserve prior releases and legacy inputs on every injected failure.

## Required Hermetic Evidence

### Completeness and Adapters

- Cursor mode accepts a valid terminal chain; rejects missing, repeated, cyclic, inferred, or scope-changing tokens; resumes from the last durable transition.
- World Bank mode fetches exactly authoritative pages, detects missing/duplicate pages and changing metadata, and accounts for provider total.
- VCI and Yahoo modes accept only pinned single-envelope fixtures and reject row caps, pagination drift, partial arrays, and opaque DataFrames.
- SBV extraction replays only from stored HTML bytes and rejects wrong hash, missing date/table/header, empty valid rows, or detected pagination controls.
- Every configured work item has exactly one adapter/version/source pin and one terminal receipt.

### Serialization, Evidence, Membership

- `canonical_json_v1` byte fixtures are identical across key order, timezone representations, decimal spellings, Unicode composition, and platform line endings.
- Receipt bytes, canonical record evidence, provider revision key, and revision identity remain distinct under mutation tests.
- Same provider revision in a different receipt keeps one `revision_id` and appends one evidence link.
- Every materialized artifact row uses the candidate release membership while preserving immutable origin/first-seen identity.
- Mixed or future origin IDs, evidence hash conflicts, and receipt ID conflicts block sealing.

### Revision and Reconciliation PIT

- `source` separates otherwise identical logical keys into independent provider streams.
- Exact replay is a no-op; ordered restatement appends; late older revision remains stored; equal source-order values quarantine.
- Provider-native as-of selection requires both cutoffs and never uses hashes or arrival order.
- Reconciliation output lists ordered candidates and one explicit selected/unresolved result.
- A later provider candidate or policy version cannot alter a query cutoff before its decision availability and ingestion times.
- Missing, stale, unresolved, or candidate-mismatched reconciliation decisions fail closed.

### Metric, Derived, Forecast

- Annual and quarterly instances of the same item survive migration, load, join, pivot, graph identity, and feature naming as different metric IDs.
- Both exact formulas emit only with two same-provider canonical parents, valid denominator, ordered parent structs, matching lineage hash, and matching formula version.
- A parent restatement creates a new lineage-bound derived revision without mutating the prior derived row.
- Explicit forecast classification precedes actual validation; unconfirmed future rows quarantine.
- Historical loaders reject Forecast path, Forecast schema, and non-actual rows before transformation.

### Publication Evidence and Quarantine

- Missing, invalid, date-only, formula-derived, year-end-fabricated, fetch-time, and ingestion-time publication values quarantine.
- Before-close remains same-session; exactly-at-close, after-close, weekends, and consecutive holidays move to the next `09:00` session.
- Raw Quarantine evidence re-hashes exactly; replay preserves the original and appends an idempotent resolution.
- Zero-row Silver publishes only with complete work and classification accounting.

### Manifest, Pointer, Migration, Rollback

- Manifest stays byte-identical and `state='sealed'` before and after activation, rollback, and export.
- Genesis pointer bytes and `GENESIS_POINTER_SHA256` match the fixed fixture.
- Crash injection after each artifact, after manifest seal, before pointer replace, during replace, after activation, during export, and during floor advance never exposes a mixed release.
- Stale pointer hash or generation fails CAS. Reader rejects wrong manifest hash, artifact hash, schema, row count, release membership, cutoff, or origin reference.
- First-generation export/smoke failure rolls back to genesis before floor commit; after floor commit export failure preserves the active pointer and old export.
- Legacy fallback works only at the exact sentinel and is permanently rejected after floor 1.
- Rollback validates target release, increments pointer generation, preserves manifest bytes, and rejects targets below floor.
- Migration row accounting is exactly `100%`; legacy input hashes and files remain unchanged on success and failure.

### Gate Control

- A complete post-cutoff approved gate passes with no discoverable strict gate.
- Every required field removed one at a time causes failure.
- Missing/invalid timestamp, placeholder session identity, false `l2_completed`, mismatched `phase_name`, or absent repo-local/scan evidence hard-fails.
- A valid explicitly grandfathered pre-cutoff gate retains legacy behavior.
- `macro_micro_data_v5_plan` is absent until independent L3 writes a concrete audited record.

## Required Verification

```powershell
python -m pytest tests/test_fetch_financial_statements.py tests/test_macro_pipeline.py tests/test_financial_loader.py tests/test_macro_micro_release.py -q
python .agents/scripts/checklist.py . --skip-performance
python scripts/sod_gate_enforcer.py
```

## Implementation Done When

- All ten amendment rows are implemented in the named minimal file set with hermetic evidence above.
- All quantitative gates pass and all three required verification commands exit zero.
- Release 1 cutover preserves legacy bytes, completes compatibility export/smoke checks, then commits rollback floor 1.
- L2 implementation evidence reports exact migration counts, artifact/manifest/pointer hashes, adapter versions, command outputs, crash outcomes, and gate-enforcer tests.
- Independent Role 20 review returns its own verdict. No L2 artifact claims audit or approval.

## Repo-Local Planning Sources Read

Role and declared skills:

- `.agents/agent/system-architect.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`

Additional repo-local planning evidence:

- `.agents/AGENTS.md`
- `.ly_state/session/implementation_plan_macro_v4_20260810.md`
- `.ly_state/session/l2_role6_macro_micro_data_v4_plan_20260810.md`
- `.ly_state/session/audit_reports/role20_macro_micro_data_v4_plan_20260810.md`
- `.ly_state/session/phase_gates.json`
- `scripts/sod_gate_enforcer.py`
- `scripts/fetch_financial_statements.py`
- `src/omega/data/macro_pipeline.py`
- `src/omega/quant/graph/fetcher.py`
- `src/omega/quant/graph/loader.py`
- `tests/test_fetch_financial_statements.py`
- `tests/test_macro_pipeline.py`
- `tests/test_financial_loader.py`
- `tests/test_strict_repo_local_skill_loading.py`

No non-repo role or skill source is authoritative for this plan.
