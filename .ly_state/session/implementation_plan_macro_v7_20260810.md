# Macro & Fundamental Data V7 - Plan Remediation

**Status:** L2 V7 plan remediation complete; implementation explicitly deferred; awaiting independent L3 plan audit
**Owner:** Role 6 `system-architect` (Tier 2, OpenCode)
**Gate:** `macro_micro_data_v7_plan`
**Supersedes:** `.ly_state/session/implementation_plan_macro_v6_20260810.md`
**Audit basis:** `.ly_state/session/v6_advisory_audit_7_remediations.md` and `.ly_state/session/audit_reports/role20_macro_micro_data_v6_plan_20260810.md`
**Scope:** Plan-only correction of provider contracts, PIT schemas, deferred implementation artifacts, deferred tests, deferred checklist repair, deferred baseline handling, and deferred verification commands

## Goal

Produce one self-contained V7 implementation plan that closes all seven V6 audit remediations without writing or changing production code, tests, fixtures, checklist code, baseline exceptions, or gate metadata in this phase.

## Current Phase Boundary

This artifact is a plan. The current `macro_micro_data_v7_plan` gate evaluates document completeness only.

- Current L2 deliverables are only `.ly_state/session/implementation_plan_macro_v7_20260810.md` and `.ly_state/session/l2_role6_macro_micro_data_v7_plan_20260810.md`.
- Implementation is **DEFERRED to a subsequent L2 OpenCode Implementation Phase**. Deferred work includes code, tests, fixtures, dependency changes, checklist changes, baseline-exception creation, migrations, release artifacts, and command execution.
- File paths, structures, schemas, exceptions, test names, fixture names, thresholds, and commands below are normative specifications for that subsequent phase; their present existence or execution is not a V7 plan-audit requirement.
- The current phase must not run focused pytest, gate-control pytest, full pytest, checklist, or gate-enforcer acceptance commands.
- The current phase must not create, edit, approve, or pre-populate `.ly_state/session/phase_gates.json`.
- Role 6 does not audit, approve, or issue a verdict. A separate L3 Role 20 session decides the plan verdict.

## Current Plan-Audit Acceptance

The independent plan audit accepts or rejects only whether this document:

1. Maps all seven V6 remediations to explicit V7 contracts.
2. Corrects the VCI ratios schema and SBV source contract with exact fixture and parser specifications.
3. Defines deferred code structures, schemas, exceptions, tests, fixtures, baseline handling, and command order.
4. Preserves PIT, append-only, release, forecast, reconciliation, and SoD boundaries from the unchallenged V6 design.
5. Contains the repaired checklist delimiter text and both complete reconciliation test names.
6. Clearly separates current plan acceptance from future implementation acceptance.
7. Passes static Markdown, UTF-8, whitespace, required-literal, and forbidden-authoritative-reliance checks.

The current plan audit must not require any deferred file to exist, any deferred code to compile, or any deferred command to run or pass.

## V6 Audit Remediation Closure Matrix

| # | Required remediation | V7 plan closure | Phase |
|---|---|---|---|
| 1 | Correct VCI ratios branch | Uses one live `data` list-of-rows receipt; defines strict annual/quarter partition assertions, one raw fixture, and exact expected-slice fixtures. | Contract now; artifacts/tests deferred. |
| 2 | Replace dead SBV contract | Uses a reachable official SBV weekly article plus its downloadable PDF; pins selectors, title/date parsing, attachment rules, hashes, table schema, and fixtures. | Contract now; artifacts/parser/tests deferred. |
| 3 | Repair plan typos | Restores the checklist inline-code delimiter and exact `test_reconciliation_future_policy_knowledge_cannot_change_earlier_cutoff` and `test_reconciliation_future_decision_knowledge_cannot_change_earlier_cutoff` names. | Closed in this plan. |
| 4 | Implement release module, fixtures, tests, PIT trail | Defines exact deferred files, structures, exceptions, fixtures, tests, and executable PIT trail. | Deferred to next L2 OpenCode implementation phase. |
| 5 | Repair checklist under `cp1252` | Defines `_configure_utf8_stdio`, exact call placement, regression test, and command. | Deferred to next L2 OpenCode implementation phase. |
| 6 | Resolve five full-suite failures or approve exception | Names all five node IDs and exact V7 exception path/schema; fixes are preferred, independent L3 approval required for any exception. | Deferred to implementation and independent audit phases. |
| 7 | Rerun acceptance commands | Preserves exact ordered commands and non-waivable exits. | Execution deferred to next L2 OpenCode implementation phase. |

## Non-Negotiable V7 Decisions

- Schema identifier is `macro_micro/v7`.
- Silver may be empty. Missing trustworthy publication evidence never permits an invented publication time.
- A provider date without time is stored as `source_published_on`; availability begins at the first successful immutable receipt, never at an invented midnight or market-open time.
- Valid source-confirmed forecasts enter Forecast before historical Actual validation; they never enter Silver or Quarantine.
- Existing canonical files and prior releases are never modified in place.
- Every requested transport work item ends in adapter-proven terminal success or a durable failed attempt.
- Same provider revision replay is a canonical no-op. Distinct provider revisions append immutably.
- Provider-native histories remain separate. Cross-provider selection requires an immutable reconciliation decision eligible at the query cutoff.
- A sealed manifest never changes state. Activation and rollback occur only through pointer CAS plus append-only attempt evidence.
- No implementation or test artifact may mutate `phase_gates.json`; only independent L3 may write a concrete plan gate record.

## Deferred Minimal File Plan

Every item in this section is deferred to the subsequent L2 OpenCode implementation phase.

- Add `src/omega/data/macro_micro_release.py`: V7 schemas, canonical JSON, hashes, completeness validators, VCI ratio partitioning, forecast classification, revision rules, reconciliation PIT selection, derived lineage, manifests, pointer CAS, migration, rollback.
- Update `scripts/fetch_financial_statements.py`: seven-request VCI acquisition, immutable receipts, eight logical endpoint-period outputs, V7 normalization, candidate release build, compatibility export.
- Update `src/omega/data/macro_pipeline.py`: World Bank and Yahoo contracts, official SBV article/PDF acquisition, strict PDF extraction, publication/availability evidence, append-only macro revisions.
- Update `src/omega/quant/graph/fetcher.py`: provider preflight and four completeness-mode iterators; reject opaque financial DataFrame acquisition.
- Update `src/omega/quant/graph/loader.py`: pointer-only Actual reads, source-aware keys, full metric IDs, knowledge-time-safe reconciliation, Forecast rejection.
- Update `requirements.txt`: add exactly `pypdf==6.15.0`; no custom PDF parser or second PDF dependency.
- Update `.agents/scripts/checklist.py`: configure UTF-8 stdout/stderr before every current print path.
- Update `scripts/sod_gate_enforcer.py`: direct post-cutoff required-field enforcement independent of strict-gate discovery.
- Extend `tests/test_fetch_financial_statements.py`, `tests/test_macro_pipeline.py`, `tests/test_financial_loader.py`, and `tests/test_strict_repo_local_skill_loading.py`.
- Add `tests/test_macro_micro_release.py`.
- Add only the exact V7 fixtures named below under `tests/fixtures/macro_micro/v7/`.
- If needed after attempted fixes, use only `.ly_state/session/baseline_exceptions/macro_micro_data_v7_plan_full_suite_20260810.json` under the independent-approval contract below.
- Keep current CLI entrypoints. Add no parallel fetch script, service, database, factory layer, or speculative abstraction.

## Deferred Release Layout

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
  failure.json
```

Every release contains every listed artifact, including schema-correct empty Parquet files. Release artifacts are immutable after sealing. Attempt events are append-only and never canonical data.

## 1. Provider Adapter and Completeness Contracts

### Pinned Runtime Contracts

| Provider | Adapter | Completeness mode | Pinned source/runtime |
|---|---|---|---|
| VCI financial | `vci_financial_raw/v2` | `explicit_single_envelope_terminal` | `vnstock==4.0.4` contract; base `https://iq.vietcap.com.vn/api/iq-insight-service`; `requests==2.33.1`. |
| World Bank | `world_bank_v2/v1` | `authoritative_numbered_pages` | `https://api.worldbank.org/v2/country/VN/indicator/{indicator}`; `requests==2.33.1`. |
| Yahoo USD/VND | `yahoo_chart_v8/v1` | `explicit_single_envelope_terminal` | `https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X`; `requests==2.33.1`. |
| SBV weekly interbank | `sbv_weekly_interbank_pdf/v2` | `official_article_attachment_snapshot` | Official `https://www.sbv.gov.vn`; `playwright==1.62.0`; Chromium `151.0.7922.34`; `beautifulsoup4==4.14.3`; `pypdf==6.15.0`. |
| Storage | `macro_micro_storage/v1` | N/A | `pandas==2.3.3`; `pyarrow==23.0.1`. |

### VCI Exact Routes and Fixtures

Method is `GET`. Required statement contracts remain:

| Logical output | Exact path/query | Required branch | Deferred exact fixture |
|---|---|---|---|
| `income_statement/year` | `/v1/company/{symbol}/financial-statement?section=INCOME_STATEMENT` | `data.years` | `tests/fixtures/macro_micro/v7/vci/income_statement_year.json` |
| `income_statement/quarter` | same route | `data.quarters` | `tests/fixtures/macro_micro/v7/vci/income_statement_quarter.json` |
| `balance_sheet/year` | `/v1/company/{symbol}/financial-statement?section=BALANCE_SHEET` | `data.years` | `tests/fixtures/macro_micro/v7/vci/balance_sheet_year.json` |
| `balance_sheet/quarter` | same route | `data.quarters` | `tests/fixtures/macro_micro/v7/vci/balance_sheet_quarter.json` |
| `cash_flow/year` | `/v1/company/{symbol}/financial-statement?section=CASH_FLOW` | `data.years` | `tests/fixtures/macro_micro/v7/vci/cash_flow_year.json` |
| `cash_flow/quarter` | same route | `data.quarters` | `tests/fixtures/macro_micro/v7/vci/cash_flow_quarter.json` |

Ratios use exactly one transport request:

```text
GET /v1/company/{symbol}/statistics-financial
response branch: data
required type: JSON array of row objects
```

Deferred ratio fixtures:

- `tests/fixtures/macro_micro/v7/vci/ratios_raw.json`: exact full raw response envelope, not a sliced helper result.
- `tests/fixtures/macro_micro/v7/vci/ratios_year_expected.json`: exact deterministic annual slice from the raw fixture.
- `tests/fixtures/macro_micro/v7/vci/ratios_quarter_expected.json`: exact deterministic quarterly slice from the same raw fixture.
- `tests/fixtures/macro_micro/v7/vci/ratios_contract.json`: row predicates, sort keys, counts, field names, and raw receipt hash.

`partition_vci_ratio_rows(rows, symbol)` must assert:

1. `rows` is a nonempty list; every element is an object.
2. Every row has `year`, `yearReport`, `quarter`, `ratioType`, `organCode`, and `ratioTTMId`.
3. `organCode` equals the requested symbol; `year` is four decimal digits; `yearReport == int(year)`.
4. Annual rows satisfy `ratioType == RATIO_YEAR`, `quarter == 5`, and non-null `ratioYearId`.
5. Quarterly rows satisfy `ratioType == RATIO_TTM`, `quarter in {1,2,3,4}`, and null `ratioYearId`.
6. Every raw row belongs to exactly one partition; no row is dropped, duplicated, or accepted by both predicates.
7. Annual output sorts by `(int(year), ratioYearId)`; quarterly output sorts by `(int(year), int(quarter), ratioTTMId)`.
8. Duplicate normalized identities fail as `VCI_RATIO_PARTITION_VIOLATION`.

The pinned FPT contract fixture records `41` raw rows: `8` annual and `33` quarterly, with `0` leftovers. Counts are fixture evidence, not a universal production row-count cap.

### VCI Work Accounting

- Raw transport requests per symbol: `7` (`3 statement endpoints x 2 period requests` plus `1 ratios request`).
- Logical endpoint-period outputs per symbol: `8` (`6` statement outputs plus `2` ratio partitions).
- Ratio annual and quarterly outputs share one immutable raw receipt and use distinct deterministic slice locators.
- Preflight requires `7/7` transport contracts and `8/8` logical output contracts. It must not issue duplicate ratio requests solely to emulate year/quarter helpers.

VCI request headers are frozen in `tests/fixtures/macro_micro/v7/vci/request_contract.json`:

| Header | Exact value |
|---|---|
| `Accept` | `application/json, text/plain, */*` |
| `Accept-Language` | `en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7` |
| `Connection` | `keep-alive` |
| `Content-Type` | `application/json` |
| `Cache-Control` | `no-cache` |
| `Sec-Fetch-Dest` | `empty` |
| `Sec-Fetch-Mode` | `cors` |
| `Sec-Fetch-Site` | `same-site` |
| `DNT` | `1` |
| `Pragma` | `no-cache` |
| `sec-ch-ua-platform` | `Windows` |
| `sec-ch-ua-mobile` | `?0` |
| `User-Agent` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36` |
| `Referer` | `https://trading.vietcap.com.vn/` |
| `Origin` | `https://trading.vietcap.com.vn/` |

Cookies and authorization are forbidden unless a future independently reviewed adapter version changes the contract. Opaque `vnstock` DataFrame helpers remain forbidden acquisition evidence.

### World Bank and Yahoo Contracts

World Bank uses `https://api.worldbank.org/v2/country/VN/indicator/{indicator_id}?format=json&page={page}` with exact IDs:

- `FP.CPI.TOTL.ZG` as `cpi`.
- `NY.GDP.MKTP.KD.ZG` as `gdp_growth`.
- `FM.LBL.BMNY.ZG` as `m2_growth`.

First-page fixtures remain under `tests/fixtures/macro_micro/v7/world_bank/`. Metadata fields `page`, `pages`, `per_page`, and `total` are mandatory. Yahoo uses `tests/fixtures/macro_micro/v7/yahoo/usdvnd_chart.json` and requires one bounded result with equal timestamp and close-array lengths.

### Four Completeness Modes

- `cursor_token`: continue only with a provider-issued next cursor; reject guessed offsets, repeated cursors, changing scope, or premature termination.
- `authoritative_numbered_pages`: fetch exactly `1..pages`; require stable page metadata and exact accounting against provider `total`. World Bank uses this mode.
- `explicit_single_envelope_terminal`: require one schema-pinned nonpaginated envelope with no cursor, truncation, partial-result, or error marker. VCI and Yahoo use this mode.
- `official_article_attachment_snapshot`: capture one schema-pinned official article root and exactly one linked immutable attachment; hash both before parsing; reject fallback pages, alternate attachments, OCR, or heuristic table recovery. SBV uses this mode.

Every Bronze receipt stores adapter ID/version, adapter source, exact request scope, URL/parameters, status, selected headers, exact raw bytes, `receipt_sha256`, request/response/checksum timestamps, and its completeness proof. Adapter or source-contract change requires a new adapter version and new fixtures.

### SBV Reachable Official Source Contract

Adapter ID is `sbv_weekly_interbank_pdf/v2`. The initial exact official work item is:

```text
article_url = https://www.sbv.gov.vn/vi/w/di%E1%BB%85n-bi%E1%BA%BFn-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-ngo%E1%BA%A1i-t%E1%BB%87-v%C3%A0-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-li%C3%AAn-ng%C3%A2n-h%C3%A0ng-tu%E1%BA%A7n-t%E1%BB%AB-27-31.7.2026
expected_title = Diễn biến thị trường ngoại tệ và thị trường liên ngân hàng tuần từ 27-31.7.2026
expected_published_on = 2026-08-05
expected_observation_start = 2026-07-27
expected_observation_end = 2026-07-31
```

Exact article selectors:

| Purpose | Exact selector/attribute |
|---|---|
| Immutable article root | `div.journal-content-article[data-analytics-asset-type=web-content]` |
| Printable content root | `div.journal-content-article[data-analytics-asset-type=web-content] #print-content` |
| Title | `h1.title-page.detail` |
| Provider publication date | `time.author-time[datetime]`; parse `datetime` only with `%d/%m/%Y` |
| Attachment | `article a[download]`; exactly one link; resolved URL must be official SBV HTTPS and contain `.pdf` |

Fetch the resolved attachment through the same Playwright browser context after the article loads, with origin cookies/credentials retained. Require HTTP `200`, `Content-Type: application/pdf`, and `%PDF-` magic before hashing. A bare unauthenticated fetch may return an HTML `200`; that response is a contract failure and must never be parsed or accepted as the fixture.

The title parser is anchored:

```regex
^Diễn biến thị trường ngoại tệ và thị trường liên ngân hàng tuần từ (?P<start_day>\d{1,2})(?:\.(?P<start_month>\d{1,2})\.(?P<start_year>\d{4}))?-(?P<end_day>\d{1,2})\.(?P<end_month>\d{1,2})\.(?P<end_year>\d{4})$
```

When start month/year are omitted, inherit them from the end date. Reject inverted ranges, ranges longer than seven days, ambiguous titles, selector multiplicity, non-SBV attachment hosts, non-PDF content type, or missing `%PDF-` signature.

Deferred immutable fixtures:

- `tests/fixtures/macro_micro/v7/sbv/weekly_2026-07-27_2026-07-31_article_root.html`
- `tests/fixtures/macro_micro/v7/sbv/weekly_2026-07-27_2026-07-31.pdf`
- `tests/fixtures/macro_micro/v7/sbv/weekly_2026-07-27_2026-07-31_contract.json`
- `tests/fixtures/macro_micro/v7/sbv/weekly_2026-07-27_2026-07-31_expected_rows.json`

Pinned fixture evidence:

```text
article_root_utf8_bytes = 53401
article_root_sha256 = 578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234
pdf_bytes = 215439
pdf_sha256 = b003b92e4795cbd70da5d7eb8ae4a089b1436e2df14c575765f1fb442380f475
```

`pypdf==6.15.0` extracts embedded text. OCR, browser visual scraping, alternate tables, and heuristic numeric recovery are forbidden fallbacks. The contract fixture pins this table:

| Currency | Qua đêm | 1 tuần | 2 tuần | 1 tháng | 3 tháng | 6 tháng | 9 tháng |
|---|---:|---:|---:|---:|---:|---:|---:|
| `VND` | `2.65` | `4.53` | `5.72` | `6.70` | `7.53` | `7.59` | `null` |
| `USD` | `3.63` | `3.69` | `3.78` | `3.78` | `3.90` | `4.60` | `4.58` |

All header tokens, row labels, decimal values, null placement, page count, title, dates, attachment URL, and hashes must match the contract fixture. Extra or missing tenor columns, duplicate currency rows, changed units, text-extraction failure, or hash mismatch fails closed.

The SBV source fields are PIT-safe:

- `observation_date = expected_observation_end` from the title range.
- `source_published_on` is the exact provider date from `time.author-time[datetime]`.
- `source_published_at = null`; no publication time is invented.
- `first_observed_at` is the actual timestamp of the first successful immutable article/PDF receipt.
- `availability_basis = first_successful_receipt/v1` and `available_at = first_observed_at`.
- `provider_revision_key` is the exact provider-supplied resolved attachment URL, including its document UUID/query token; it is not synthesized from a receipt hash.
- Primary `source_receipt_id` and `receipt_sha256` identify the PDF; ordered context receipt evidence identifies the article-root HTML.

Any SBV report added later must be supplied as an explicit official article URL in the immutable work manifest and pass the same versioned contract. V7 does not implement unpinned site-wide discovery.

SBV failures use exact reason codes:

- `SBV_ARTICLE_CONTRACT_VIOLATION`
- `SBV_ATTACHMENT_CONTRACT_VIOLATION`
- `SBV_PDF_HASH_MISMATCH`
- `SBV_PDF_TABLE_SCHEMA_DRIFT`
- `SBV_PUBLICATION_DATE_MISSING`
- `SBV_OBSERVATION_RANGE_INVALID`

### Provider Preflight

Preflight is deferred implementation work. It must:

1. Verify `7/7` VCI transport requests and `8/8` logical outputs for the fixture symbol.
2. Verify all three World Bank IDs and pagination metadata.
3. Verify Yahoo array equality and terminal envelope.
4. Replay SBV only from the pinned article-root and PDF fixtures; no live network is required for hermetic tests.
5. Compare adapter constants against `tests/fixtures/macro_micro/v7/provider_contract.json`.
6. Abort the candidate release on any route, header, selector, schema, hash, partition, or completeness drift.

## 2. Deferred Code Structures and Exceptions

`src/omega/data/macro_micro_release.py` is the single owner of release-domain logic. The subsequent implementation phase adds these concrete structures; no one-implementation interface layer is required.

### Structures

- `ReceiptRefV1`: `source_receipt_id`, `receipt_sha256`, `adapter_id`, `adapter_version`, `source_url`, `received_at`, `role` (`primary` or `context`).
- `RecordEvidenceV2`: primary receipt, ordered context receipts, source locator, exact field paths/selectors, exact source values, adapter identity, `record_evidence_sha256`.
- `CanonicalRecordV7`: canonical Actual/Forecast row schema below.
- `ReconciliationDecisionV1`: policy, candidate, decision knowledge-time schema below.
- `DerivedRecordV1`: formula and ordered-parent lineage schema.
- `ReleaseManifestV1`: sealed artifact inventory and hashes.
- `ActivePointerV1`: generation, active release identity/hash, rollback floor, previous pointer hash.
- `AttemptEventV1`: append-only attempt state transition.

### Functions

- `canonical_json_v1(value) -> bytes`
- `sha256_canonical(value) -> str`
- `partition_vci_ratio_rows(rows, symbol) -> tuple[list, list]`
- `validate_sbv_weekly_contract(article_bytes, pdf_bytes, contract) -> list[dict]`
- `classify_forecast_record(record, evidence) -> ClassificationResult`
- `select_provider_revision_as_of(rows, cutoff) -> CanonicalRecordV7 | None`
- `select_reconciled_revision_as_of(native_rows, decisions, cutoff) -> CanonicalRecordV7 | None`
- `seal_manifest(candidate_dir) -> ReleaseManifestV1`
- `activate_release_cas(expected_pointer_hash, sealed_manifest) -> ActivePointerV1`
- `migrate_generation_one(legacy_paths) -> MigrationReportV1`
- `rollback_release(expected_pointer_hash, target_release_id) -> ActivePointerV1`

### Exceptions

- `MacroMicroContractError`
- `ProviderContractError`
- `CompletenessError`
- `EvidenceIntegrityError`
- `RevisionConflictError`
- `ReconciliationKnowledgeError`
- `PublicationError`
- `PointerCASConflict`
- `MigrationError`

All public CLI boundaries catch these typed exceptions, persist a durable failed-attempt record, preserve prior canonical state, and return nonzero. Internal helpers do not swallow them.

## 3. Deferred Canonical Serialization and Hash Contracts

All work in this section is a specification for the subsequent L2 OpenCode implementation phase.

### Release Membership and Immutable Origin

Every row physically contained in release `<release_id>` carries `release_id == <release_id>`. This is current membership, not immutable origin. Manifest validation rejects null or mixed membership.

Actual, Forecast, Derived, reconciliation, receipt, and resolution rows also carry `origin_release_id`, the first sealed release containing that immutable logical row. Later complete releases may rematerialize the row with a new membership `release_id`; they must preserve `origin_release_id`, business identity, revision identity, and evidence identity.

Quarantine rows instead carry current `release_id`, immutable `first_seen_release_id`, and immutable `quarantine_id`. Origin or first-seen IDs must reference an existing release no newer than the containing release. Filesystem paths, attempt IDs, pointer generations, export paths, and current-clock validation timestamps are excluded from immutable identities.

### `canonical_json_v1`

`src/omega/data/macro_micro_release.py::canonical_json_v1` is the only canonical serializer used by V7 IDs and evidence hashes:

1. Validate the declared schema first; unknown fields and nonfinite numbers fail.
2. Normalize strings to Unicode NFC; preserve case unless a field schema defines a normalizer.
3. Encode timestamps as UTC RFC3339 with exactly six fractional digits and `Z`.
4. Encode dates as `YYYY-MM-DD`.
5. Encode business decimals as base-10 strings with no exponent, leading plus sign, or trailing fractional zeroes; both signed zero forms become `0`.
6. Encode integers in canonical base 10, booleans as JSON booleans, optional missing values as JSON `null`, and raw bytes only through explicit base64 or SHA-256 fields.
7. Preserve array order; sort object keys by Unicode code point.
8. Emit compact UTF-8 JSON with separators `,` and `:`, `ensure_ascii=false`, no BOM, and no trailing newline.

Hermetic byte fixtures must cover object-key order, timestamp offsets, decimal spellings, Unicode composition, nulls, and Windows/Linux line endings.

### Distinct Identities

- `source_receipt_id`: adapter-generated locator for one exact provider response; derived from adapter ID/version, normalized request scope, and request/response ordinals. It is not a content hash or provider revision key.
- `receipt_sha256`: `SHA256(exact_raw_response_bytes)` before parsing. Headers, timestamps, parsed rows, and paths are excluded.
- `record_evidence_sha256`: `SHA256(canonical_json_v1(record_evidence_v2))`. Evidence contains primary/context receipts, source locator, exact field paths/selectors, exact values, and adapter identity.
- `provider_revision_key`: exact provider timestamp, sequence, version token, or immutable document revision key. It is never synthesized from hashes, ingestion time, row order, or current time.
- `revision_id`: `SHA256(canonical_json_v1(revision_identity_v7))`, containing schema, dataset, source-aware logical key, record type, normalized payload, publication evidence, revision ordering, and origin evidence hash.

Conflicting bytes for one `source_receipt_id` fail as `RECEIPT_ID_CONFLICT`. Conflicting normalized evidence for one `record_evidence_sha256` fails as `RECORD_EVIDENCE_HASH_CONFLICT`. Missing or ambiguous provider revision order routes to Quarantine as `REVISION_ORDER_MISSING`.

## 4. Deferred `CanonicalRecordV7` Schema

`CanonicalRecordV7` is a tagged union of financial and macro records. Unknown columns fail schema validation.

### Common Fields

| Field | Exact contract |
|---|---|
| `schema_version` | Exactly `macro_micro/v7`. |
| `release_id` | Current containing release membership. |
| `origin_release_id` | First sealed release containing the immutable revision. |
| `dataset` | Exactly `financial` or `macro`. |
| `record_type` | Exactly `actual` or `forecast`. |
| `source` | Stable non-null provider ID. |
| `source_url` | Exact endpoint, article, or attachment URL used. |
| `source_receipt_id` | Origin raw receipt locator. |
| `receipt_sha256` | Origin raw-byte SHA-256. |
| `source_record_locator` | Stable row/object/table-cell locator inside the receipt. |
| `record_evidence_sha256` | Canonical origin evidence hash. |
| `source_published_on` | Exact provider calendar date when the source supplies a date; nullable only when an exact timestamp exists without a separate date field. |
| `source_published_at` | Exact timezone-aware provider timestamp; null when the source supplies date only. |
| `first_observed_at` | Actual timezone-aware first successful immutable receipt time. |
| `availability_basis` | Exactly `published_timestamp_session/v1` or `first_successful_receipt/v1`. |
| `available_at` | PIT availability instant produced by the selected basis. |
| `ingested_at` | Actual timezone-aware candidate-release ingestion time. |
| `provider_revision_key` | Exact provider-supplied ordering identity. |
| `revision_order_kind` | Exactly `source_revision_at` or `revision_seq`. |
| `source_revision_at` | Exact provider revision timestamp when timestamp ordering is selected; otherwise null. |
| `revision_seq` | Positive provider sequence when sequence ordering is selected; otherwise null. |
| `revision_id` | Immutable normalized provider-revision identity. |

Exactly one revision-order value is non-null. One provider-native stream cannot change ordering kind. Equal order values with different revisions fail as `REVISION_ORDER_COLLISION`; hashes, receipt order, file order, and ingestion order never break ties.

### Financial Variant

Financial rows add exactly: `symbol`, `endpoint`, `period_type`, `item_code`, `metric_id`, `fiscal_period_end`, `item_value_decimal`, `currency`, and `unit`.

- `period_type` is `year` or `quarter`.
- `metric_id = endpoint:period_type:item_code` and remains intact across normalization, joins, pivots, graph nodes, and feature names.
- Financial logical key is `(dataset, symbol, metric_id, fiscal_period_end)`.
- Financial provider-stream key is `(dataset, source, symbol, metric_id, fiscal_period_end)`.

### Macro Variant

Macro rows add exactly: `indicator`, `observation_date`, `dimensions_json`, `value_decimal`, and `unit`.

- `dimensions_json` is canonical JSON. It is `{}` for scalar series and contains explicit keys such as `currency` and `tenor` for the SBV table.
- Macro logical key is `(dataset, indicator, observation_date, dimensions_json)`.
- Macro provider-stream key is `(dataset, source, indicator, observation_date, dimensions_json)`.

### Publication and Availability Rules

1. Exact timestamp evidence sets `source_published_at`; `available_at` uses the versioned `Asia/Ho_Chi_Minh` trading-session rule and `availability_basis=published_timestamp_session/v1`.
2. Date-only evidence, including the pinned SBV article date, sets `source_published_on`, leaves `source_published_at=null`, sets `availability_basis=first_successful_receipt/v1`, and sets `available_at=first_observed_at`.
3. No midnight, market-open, fetch-date, file-time, or ingestion-time publication timestamp may be invented.
4. Missing both exact publication date/timestamp and immutable first-receipt evidence routes to Quarantine as `PUBLICATION_EVIDENCE_MISSING`.
5. `first_observed_at <= available_at <= ingested_at` for receipt-based availability. Timestamp-based availability must not precede the exact provider timestamp or ingestion cutoff.

## 5. Deferred Source-Aware Revision and Reconciliation Contract

### Provider-Native As-Of Selection

1. Validate pointer, sealed manifest, artifact hashes, schemas, and membership.
2. Read only `record_type=actual` for historical consumers.
3. Filter `available_at <= cutoff` and `ingested_at <= cutoff`.
4. Group by the provider-stream key including `source`.
5. Select the greatest eligible provider order according to the stream's fixed order kind.
6. Reject ties, mixed order kinds, malformed timestamps, or absent ordering evidence.

This yields at most one eligible native revision per provider. It does not choose a cross-provider canonical value.

### `ReconciliationDecisionV1` Schema

Every release contains `reconciliation/canonical_provider_selection.parquet`, including a schema-correct empty file. Each immutable row requires:

| Field | Exact contract |
|---|---|
| `schema_version` | Exactly `canonical_provider_selection/v1`. |
| `release_id` | Current containing release. |
| `origin_release_id` | First sealed release containing the decision. |
| `dataset` | `financial` or `macro`. |
| `canonical_key_json` | `canonical_json_v1` of the logical key without `source`. |
| `selection_policy_id` | Stable named policy. |
| `selection_policy_version` | Immutable semantic version. |
| `selection_policy_sha256` | SHA-256 of exact policy bytes. |
| `policy_effective_at` | Earliest instant the policy may govern selection. |
| `policy_available_at` | Earliest evidenced instant the exact policy bytes were knowable. |
| `policy_ingested_at` | Actual policy ingestion instant. |
| `candidate_sources` | Ordered source IDs. |
| `candidate_revision_ids` | Ordered one-to-one revision IDs. |
| `candidate_available_at` | Ordered one-to-one availability instants. |
| `candidate_ingested_at` | Ordered one-to-one ingestion instants. |
| `selected_source` | One candidate source or null. |
| `selected_revision_id` | Matching candidate revision or null. |
| `decision_status` | Exactly `selected` or `unresolved`. |
| `decision_reason` | Stable machine-readable outcome. |
| `decision_created_at` | Actual instant the exact candidates and policy were evaluated. |
| `decision_recorded_at` | Actual instant the immutable decision became durable. |
| `decision_ingested_at` | Actual instant the decision entered the candidate release. |
| `decision_input_sha256` | Hash of exact policy bytes/times and ordered candidates/times/revisions. |
| `reconciliation_id` | Hash of canonical key, policy identity, input hash, all decision times, and outcome. |

Candidate arrays are ordered by configured priority then source ID; lengths must match. A policy, candidate, policy-knowledge, or decision-knowledge change appends a new row.

At cutoff, eligibility requires every policy, candidate, and decision timestamp at or before cutoff; exact candidate revision-set equality; `decision_created_at` no earlier than every input knowledge time; `decision_recorded_at >= decision_created_at`; `decision_ingested_at >= decision_recorded_at`. Missing, stale, unresolved, contradictory, future-known, or candidate-mismatched decisions return no canonical value.

Deferred fixtures:

- `tests/fixtures/macro_micro/v7/reconciliation/future_policy.json`
- `tests/fixtures/macro_micro/v7/reconciliation/future_decision.json`

Deferred exact tests:

- `test_reconciliation_future_policy_knowledge_cannot_change_earlier_cutoff`
- `test_reconciliation_future_decision_knowledge_cannot_change_earlier_cutoff`

Each test freezes an earlier cutoff result, appends only future-known evidence, reruns the earlier cutoff, and requires byte-identical output.

### Append-Only Replay Rules

- Same provider-stream key plus same `revision_id`: canonical no-op; append only unseen evidence links.
- Same provider-stream key plus distinct ordered `revision_id`: append immutable revision.
- Late older revisions remain stored and become eligible only where provider order and cutoffs permit.
- Prior releases remain byte-identical. Later complete releases preserve origin IDs and immutable identities.

## 6. Deferred Derived, Forecast, and Quarantine Contracts

### Frequency-Safe Metrics and Derived Lineage

Only these derived metrics are in V7:

- `derived_ratios:<period_type>:current_ratio`
- `derived_ratios:<period_type>:debt_to_equity`

| Metric | `formula_id` | Version | Ordered expression |
|---|---|---|---|
| `current_ratio` | `omega.financial.current_ratio` | `1.0.0` | parent 0 `balance_sheet:<period_type>:current_assets` divided by parent 1 `balance_sheet:<period_type>:current_liabilities` |
| `debt_to_equity` | `omega.financial.debt_to_equity` | `1.0.0` | parent 0 `balance_sheet:<period_type>:total_liabilities` divided by parent 1 `balance_sheet:<period_type>:equity` |

Parents must be the exact canonical Actual revisions selected at the cutoff, share symbol/period/provider-selection context, be finite, and have a nonzero denominator. Invalid derivations produce no derived value and append a reasoned rejection.

`DerivedRecordV1` requires `schema_version`, current `release_id`, immutable `origin_release_id`, `dataset=financial_derived`, `record_type=actual`, `source=derived_ratios`, `symbol`, `period_type`, `fiscal_period_end`, `metric_id`, `item_value_decimal`, `formula_id`, `formula_version`, `ordered_parent_lineage`, `lineage_sha256`, `source_published_on`, `source_published_at`, `first_observed_at`, `availability_basis`, `available_at`, `ingested_at`, null `provider_revision_key`, `revision_order_kind=parent_lineage`, `record_evidence_sha256`, and `revision_id`.

Each ordered parent struct contains exactly:

```text
ordinal
role
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

`lineage_sha256 = SHA256(canonical_json_v1(ordered_parent_lineage))`. Parent order is semantic. At a cutoff, accept only the derived row whose formula version and lineage hash match the exact selected parents; zero or multiple matches fail closed.

### Forecast Classifier

Ownership is `src/omega/data/macro_micro_release.py::classify_forecast_record`. Order is normative:

1. Validate envelope identity, receipt/evidence hashes, source locator, period fields, and adapter forecast markers.
2. Route an explicitly source-marked forecast, estimate, guidance, or consensus row to Forecast before historical-Actual validation.
3. Validate the Forecast schema, publication/availability evidence, and provider revision key.
4. Route an unmarked future-period row to Quarantine as `FUTURE_PERIOD_UNCONFIRMED`.
5. Validate remaining records as historical Actual.

Silver and Derived accept Actual only. `FinancialStatementLoader`, graph loaders, feature builders, and backtest entrypoints reject Forecast paths, schemas, and rows before joins or pivots. Historical APIs expose no weakening flag.

Deferred exact classifier tests in `tests/test_macro_micro_release.py`:

- `test_classify_forecast_record_routes_explicit_forecast_before_actual_validation`
- `test_classify_forecast_record_quarantines_unconfirmed_future_period`
- `test_classify_forecast_record_accepts_confirmed_historical_actual`
- `test_classify_forecast_record_rejects_implicit_date_based_forecast_inference`

Deferred trust-boundary tests in `tests/test_financial_loader.py`:

- `test_financial_loader_rejects_forecast_path`
- `test_financial_loader_rejects_forecast_schema`
- `test_financial_loader_rejects_non_actual_rows`

### Permanent Quarantine

Date-only provider publication evidence is valid under the receipt-based availability rule; it is not quarantined merely for lacking a time. These failures do quarantine:

- Missing publication date/timestamp or immutable first-receipt evidence.
- Fabricated financial `fiscal_period_end + 45/90 days` timestamps.
- Fabricated World Bank year-end or next-year timestamps.
- Fetch, ingestion, file-modification, or current-clock substitutions presented as provider publication time.
- Missing evidence locator/hash, synthesized provider revision key, ambiguous revision order, schema drift, or raw-byte hash mismatch.

Every Quarantine row requires `schema_version`, `quarantine_id`, current `release_id`, immutable `first_seen_release_id`, dataset, reason code, source, source URL, source receipt ID, `receipt_sha256`, source locator, `record_evidence_sha256`, `quarantined_at`, exact raw evidence bytes or byte-preserving encoding, raw evidence SHA-256, and versioned details.

- Same invalid evidence and reason is a no-op; distinct evidence or reason appends.
- Never delete, update, or move a Quarantine record.
- Replay appends a new valid revision and a resolution event; it never edits original evidence.
- Verify raw evidence hashes before staging and through the published reader.

Minimum V7 reason codes include `OPAQUE_PROVIDER_RESPONSE`, `NUMBERED_PAGE_PROTOCOL_VIOLATION`, `SINGLE_ENVELOPE_PROTOCOL_VIOLATION`, `ARTICLE_ATTACHMENT_PROTOCOL_VIOLATION`, `RECEIPT_ID_CONFLICT`, `RECORD_EVIDENCE_HASH_CONFLICT`, `REVISION_ORDER_MISSING`, `REVISION_ORDER_COLLISION`, `PUBLICATION_EVIDENCE_MISSING`, `FUTURE_PERIOD_UNCONFIRMED`, `DERIVED_PARENT_SOURCE_MISMATCH`, and every VCI/SBV code declared above.

## 7. Deferred Sealed Release and Pointer-CAS Contract

### Sealed Manifest

`manifest.json` is written once with `state=sealed`. It contains release ID/sequence, schema versions, cutoff, adapter pins, reconciliation-policy identity and knowledge times, every required artifact path/hash/row count/schema fingerprint, current-membership count, inherited/origin counts, fixture hashes, and release accounting checks.

Seal procedure:

1. Write and fsync every artifact under a new candidate release directory.
2. Re-read all artifacts; validate bytes, schemas, row counts, membership, origin references, foreign keys, completeness, and PIT constraints.
3. Serialize the manifest with `canonical_json_v1`, atomically write/fsync it, and hash its exact bytes.
4. Re-open the manifest and all artifacts through the production reader validator.

The manifest is never mutated to `validated`, `published`, `active`, or `rolled_back`. Pointer state and attempt events hold lifecycle state.

### Generation-Zero Sentinel

Deferred fixture: `tests/fixtures/macro_micro/v7/pointer/genesis_current.json`. Exact UTF-8 bytes, no BOM or trailing newline:

```json
{activated_at:null,activation_attempt_id:null,activation_kind:genesis,active_manifest_path:null,active_manifest_sha256:null,active_release_id:null,active_release_sequence:0,legacy_fallback_allowed:true,pointer_generation:0,pointer_schema_version:macro_micro_pointer/v1,previous_pointer_sha256:null,rollback_floor_release_sequence:0}
```

`GENESIS_POINTER_SHA256 = 76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`. `test_genesis_fixture_is_valid_canonical_json_with_declared_sha256` must parse, canonical-reserialize, assert exact bytes, assert no BOM/trailing newline, and assert the declared hash. Initialization uses create-new semantics; an existing malformed pointer is never guessed or overwritten.

### Pointer CAS and Attempt Ledger

The pointer is sole publication authority:

1. Acquire the pointer lock.
2. Read pointer bytes and verify schema/hash.
3. Compare expected pointer hash and generation.
4. Revalidate target sealed manifest and artifacts.
5. Require target release sequence at or above rollback floor.
6. Build generation `current + 1` with target identity, activation metadata, prior pointer hash, and nondecreasing floor.
7. Write/fsync a same-directory temporary pointer, atomically replace `current.json`, re-read exact bytes, then release the lock.
8. Append immutable success/failure evidence.

`attempt.json` fixes attempt ID, candidate release identity, prior pointer hash/generation, requested scope, cutoff, and adapter pins. Checkpoints store last hash-verified work transition. `failure.json` stores phase, typed exception, timestamps, artifact hashes, terminal accounting, checkpoints, target manifest, and observed pointer. A failed attempt never changes the authoritative pointer or prior releases.

## 8. Deferred Migration, Compatibility, and Rollback

### Reader Transition and Migration

1. Deploy pointer-aware readers while the exact genesis sentinel allows legacy fallback.
2. Inventory all direct reads of `data/financial_statements_2015_now.parquet` and `data/macro_indicators.parquet`; retain constants only in migration and compatibility export.
3. Build release sequence 1 from byte-preserved legacy inputs plus immutable provider evidence.
4. Preserve both original files inside release 1 under `migration/legacy/`, record hashes before parsing, and include them in the sealed manifest.
5. Require per-input accounting: `legacy_input_rows == migrated_actual + migrated_forecast + quarantined_rows + exact_duplicate_occurrences`.
6. CAS from genesis to sealed release 1; run compatibility export and pointer-aware smoke checks.
7. Perform a second CAS retaining release 1, setting floor `1` and `legacy_fallback_allowed=false`, then append `cutover_committed`.

Failed migration never edits legacy files, genesis pointer, or prior releases. After floor commit, missing or corrupt active data hard-fails; no legacy fallback remains.

### `--output` Compatibility

Keep `scripts/fetch_financial_statements.py --output PATH`. It is not publication authority. After activation, read the active release through validated pointer logic and atomically write an Actual-only legacy projection with Parquet metadata `macro_micro_release_id`, `macro_micro_manifest_sha256`, and `macro_micro_schema_version`. Preserve the old export on failure. Reject output paths inside immutable releases or equal to pointer, receipt, or manifest paths.

Before floor commit, export/smoke failure CAS-rolls back to genesis. After floor commit, export failure records `compatibility_export_failed`, keeps the authoritative pointer and old export, and returns nonzero.

### Rollback Floor

- Release sequences are positive and immutable; pointer generation increments for activation, rollback, and floor advance.
- Rollback revalidates the target, requires `target_release_sequence >= rollback_floor_release_sequence`, performs pointer CAS, and appends a rollback event.
- The floor never decreases. Sequence 0 is legal only before `cutover_committed`.
- Deleting releases at or above the floor is outside V7 and forbidden.

## 9. Deferred Checklist Encoding Repair

The current observed `UnicodeEncodeError` sites are `.agents/scripts/checklist.py:42` and `.agents/scripts/checklist.py:184`. Line numbers are evidence locations, not patch anchors.

The subsequent L2 OpenCode implementation phase adds exactly one helper near the imports:

```python
def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors='replace')
```

Call `_configure_utf8_stdio()` once at module startup immediately after its definition, before `Colors`, any helper invocation, argparse errors, headers, icons, or other print path. If `reconfigure` is unavailable, retain the stream without detaching, replacing, or closing it. Do not remove Unicode output to hide the bug.

Deferred regression:

`tests/test_strict_repo_local_skill_loading.py::test_checklist_stdout_is_utf8_safe_under_cp1252` launches a subprocess with `PYTHONUTF8=0` and `PYTHONIOENCODING=cp1252`, imports `.agents/scripts/checklist.py`, exercises `print_header`, `print_step`, `print_success`, `print_warning`, and `print_error`, and requires exit `0` plus UTF-8-decodable stdout/stderr bytes.

The production command remains exactly `python .agents/scripts/checklist.py . --skip-performance`.

The corrected quantitative delimiter text is: simulated `cp1252` subprocess and exact checklist command both exit `0`; UTF-8 output never raises `UnicodeEncodeError`.

## 10. Deferred Five-Failure Resolution and Exception Contract

The subsequent implementation phase must first reproduce, diagnose, and prefer fixes for these exact V6-audit failures:

1. `tests/test_extract_lessons.py::test_extract_lessons_fails_closed_for_malformed_store_and_lock_contention`
2. `tests/test_market_release_gates.py::test_release_gate_replay_uses_supplied_durable_ledger`
3. `tests/test_market_release_gates.py::test_downstream_release_failure_does_not_consume_lifecycle_receipt`
4. `tests/test_market_release_gates.py::test_dry_run_validation_does_not_consume_lifecycle_receipt`
5. `tests/test_vci_updater_validation_write_blocker.py::TestCombinedValidationWriteBlocker::test_write_proceeds_when_combined_valid`

No failure is automatically grandfathered. If a failure is caused or exposed by V7 work, fix it. A baseline exception is allowed only for failures proven pre-existing, unrelated to every V7 changed path and execution flow, still reproducible before and after V7 implementation, and independently approved by L3.

The only permitted deferred exception path is `.ly_state/session/baseline_exceptions/macro_micro_data_v7_plan_full_suite_20260810.json`.

Exact `baseline_exception/v1` fields:

| Field | Contract |
|---|---|
| `schema_version` | `baseline_exception/v1`. |
| `gate` | `macro_micro_data_v7_plan`. |
| `command` | `python -m pytest -q`. |
| `command_output_path`, `command_output_sha256` | Immutable repo-relative output plus exact lowercase SHA-256. |
| `baseline_revision`, `implementation_revision` | Git revisions or explicit dirty-tree evidence IDs. |
| `failing_node_ids` | Sorted unique exact pytest node IDs. |
| `pre_change_reproduction`, `post_change_reproduction` | Each contains `exit_code`, output path/hash, and RFC3339 `observed_at`. |
| `non_impact_proof` | `changed_files`, affected-flows evidence path/hash, and specific statement. |
| `owner` | Named remediation owner. |
| `expires_at` | RFC3339, no more than 30 days after approval. |
| `independent_approval` | Actual Role 20 session, audit path, `[APPROVED_EXCEPTION]`, and approval timestamp. |

Constraints:

- `failing_node_ids` must be a subset of, and exactly equal to, the current waived failures from the five node IDs above.
- L2 may collect reproduction and non-impact evidence but may not populate or claim independent approval.
- L3 approval must be explicit, file-backed, unexpired, and tied to exact output hashes and revision evidence.
- Focused tests, gate-control tests, checklist, and gate enforcer cannot be excepted.
- Any changed failure set, output hash, affected flow, expiry, or implementation revision invalidates the exception.

## 11. Deferred Gate Metadata and Enforcer Boundary

This plan phase does not create, edit, approve, or pre-populate `macro_micro_data_v7_plan` in `.ly_state/session/phase_gates.json`. Only a fresh independent Role 20 audit may write the gate record with actual identities and verdict.

The future gate record must contain concrete `phase_name`, timestamp, L2/L3 session and role identities, `l2_completed`, audit path, bracketed verdict, SOD booleans, exact repo-local role/skill evidence, and forbidden-path scan evidence. Placeholders, copied prior-session IDs, missing timestamps, and self-approval are invalid.

The deferred `scripts/sod_gate_enforcer.py` repair keeps direct post-cutoff required-field validation independent of strict-gate discovery. Required gate-control tests remain in `tests/test_strict_repo_local_skill_loading.py`. Implementation and tests never mutate gate metadata. After independent L3 gate mutation, L1 reruns `python scripts/sod_gate_enforcer.py`.

## 12. Deferred Fixture Inventory

The subsequent implementation phase creates only these V7 contract groups:

- `tests/fixtures/macro_micro/v7/provider_contract.json`
- `tests/fixtures/macro_micro/v7/vci/request_contract.json`
- Six statement-slice fixtures named in the VCI table above.
- `tests/fixtures/macro_micro/v7/vci/ratios_raw.json`
- `tests/fixtures/macro_micro/v7/vci/ratios_year_expected.json`
- `tests/fixtures/macro_micro/v7/vci/ratios_quarter_expected.json`
- `tests/fixtures/macro_micro/v7/vci/ratios_contract.json`
- `tests/fixtures/macro_micro/v7/world_bank/cpi_page_1.json`
- `tests/fixtures/macro_micro/v7/world_bank/gdp_growth_page_1.json`
- `tests/fixtures/macro_micro/v7/world_bank/m2_growth_page_1.json`
- `tests/fixtures/macro_micro/v7/yahoo/usdvnd_chart.json`
- Four exact SBV article/PDF/contract/expected-row fixtures named above.
- Two exact reconciliation fixtures named above.
- `tests/fixtures/macro_micro/v7/serialization/canonical_json_cases.json`
- `tests/fixtures/macro_micro/v7/forecast/classification_cases.json`
- `tests/fixtures/macro_micro/v7/pit/acceptance_trail.json`
- `tests/fixtures/macro_micro/v7/pointer/genesis_current.json`

Every fixture is immutable UTF-8 or exact binary evidence with a SHA-256 recorded in `provider_contract.json` or its local contract. Adapter constants must equal fixture literals. Tests use fixtures, not live network.

## 13. Deferred Test and PIT Acceptance Trail

### Test Ownership

- `tests/test_fetch_financial_statements.py`: seven VCI requests, eight logical outputs, strict raw ratio partition, headers, receipts, replay, and no row truncation.
- `tests/test_macro_pipeline.py`: World Bank pagination, Yahoo envelope, SBV selectors/title/date/attachment/hash/PDF table, date-only availability, and append-only macro revisions.
- `tests/test_financial_loader.py`: pointer-only Actual reads, full metric IDs, source-aware streams, reconciliation cutoffs, and Forecast rejection.
- `tests/test_macro_micro_release.py`: canonical bytes/hashes, membership/origin, replay/collision, derived lineage, forecast classification, Quarantine, manifest sealing, CAS, crash safety, migration, rollback, and PIT invariance.
- `tests/test_strict_repo_local_skill_loading.py`: checklist `cp1252` regression and post-cutoff gate-control behavior.

### Exact PIT Trail

`tests/fixtures/macro_micro/v7/pit/acceptance_trail.json` contains ordered receipt, policy, decision, and cutoff events plus expected canonical output bytes/SHA-256 at each cutoff. The exact deferred test is:

`tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable`

The exact executable trail command is:

```powershell
python -m pytest tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable -q
```

It must prove: later receipt, provider revision, policy, reconciliation decision, forecast, or rollback evidence cannot alter bytes returned for an earlier cutoff; repeating the trail is idempotent; every output hash matches the fixture.

## 14. Deferred Implementation Tasks

- [ ] Implement `macro_micro_release.py` structures, schemas, canonical serialization, identity separation, membership/origin validation, revisions, reconciliation, lineage, manifest, pointer, migration, and rollback.
- [ ] Implement VCI seven-request acquisition and one-response ratio partition; remove opaque DataFrame evidence, truncation, destructive dedupe, and overwrite publication.
- [ ] Implement exact World Bank, Yahoo, and official SBV article/PDF adapters with immutable receipts and fixture replay.
- [ ] Implement publication-date/timestamp evidence without invented times; use first receipt for date-only availability.
- [ ] Implement forecast-first classification, permanent Quarantine, full metric IDs, and two exact derived formulas.
- [ ] Implement pointer-aware readers, generation-one migration, compatibility export, crash-safe CAS, rollback floor, and attempt ledger.
- [ ] Implement `_configure_utf8_stdio` and the forced-`cp1252` regression.
- [ ] Diagnose and fix the five full-suite failures; use the exact exception contract only if independently warranted.
- [ ] Add every deferred fixture and test above, including the executable PIT trail.
- [ ] Run the future implementation acceptance sequence and preserve hashed evidence.

## 15. Deferred Quantitative Gates

All are release-blocking in the subsequent implementation phase:

- VCI: `7/7` raw transports, `8/8` logical outputs, `41 = 8 + 33 + 0` for the pinned FPT ratio fixture.
- SBV: exact article/PDF byte counts and hashes, one title/date/attachment match, exact two-row tenor table, no fallback extraction.
- Completeness: `100%` work items use one declared mode and end in terminal success or a durable failed attempt.
- Integrity: `100%` receipt, evidence, manifest, pointer, and raw Quarantine hashes reproduce.
- Membership/revision: `0` mixed releases, future origins, source-stream collapses, order ties, or hash tie-breaks.
- PIT reconciliation: `100%` selected decisions have all policy/candidate/decision knowledge eligible at cutoff; future evidence changes `0` earlier bytes.
- Forecast leakage: `0` Forecast rows in Silver, Derived, historical loaders, graph, feature, or backtest paths.
- Publication evidence: `0` invented publication times; date-only rows use exact dates plus first-receipt availability.
- Release safety: `0` manifest mutations, partial pointer activations, mixed releases, or rollback-floor violations.
- Checklist: simulated `cp1252` subprocess and exact checklist command both exit `0`; UTF-8 output never raises `UnicodeEncodeError`.

Silver and Derived may contain zero rows only when every requested record and exclusion is hash-evidenced and fully accounted for.

## 16. Future L2 Implementation Acceptance

This section is **DEFERRED to the subsequent L2 OpenCode Implementation Phase**. None of these commands is a current plan-audit prerequisite, and none is run while producing this V7 plan.

After implementation, run from repository root in this exact order; restart the sequence after any code, test, fixture, checklist, or enforcer remediation:

```powershell
python -m pytest tests/test_fetch_financial_statements.py tests/test_macro_pipeline.py tests/test_financial_loader.py tests/test_macro_micro_release.py tests/test_strict_repo_local_skill_loading.py -q
python -m pytest tests/test_strict_repo_local_skill_loading.py -q
python -m pytest -q
python .agents/scripts/checklist.py . --skip-performance
python scripts/sod_gate_enforcer.py
```

Commands 1, 2, 4, and 5 must exit `0`; no exception may waive them. Command 3 must exit `0` unless only exact pre-existing unrelated failures remain under the valid, unexpired, independently approved V7 exception file.

The future L2 implementation report records every command, start/end RFC3339 timestamps, exit code, stdout/stderr artifact path and SHA-256, pass/fail/skip counts, exact environment overrides, and applicable exception path. After independent L3 writes V7 gate metadata, L1 reruns command 5 and requires exit `0`.

Future implementation is complete only when all deferred files, schemas, fixtures, tests, and migrations exist; quantitative gates pass; the PIT trail is byte-stable; legacy bytes and prior releases remain unchanged; acceptance evidence is hashed; and L2 submits without self-audit or approval.

## 17. Current Plan Completion Boundary

Current plan completion requires only:

- This V7 document maps and specifies all seven remediations.
- The companion L2 evidence report records repo-local role/skill loading, static checks, provider-contract evidence, and non-execution of deferred commands.
- Only the two current plan deliverables are created by this task.
- `.ly_state/session/phase_gates.json`, code, tests, fixtures, checklist code, dependency files, and baseline exceptions remain unchanged.

An independent L3 Role 20 session may return its own plan verdict. Role 6 does not audit or approve this artifact.

## 18. Repo-Local Planning Sources Read

Role and frontmatter-declared skills:

- `.agents/agent/system-architect.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`

Additional repo-local planning evidence:

- `.agents/AGENTS.md`
- `.agents/scripts/checklist.py`
- `requirements.txt`
- `.ly_state/session/implementation_plan_macro_v6_20260810.md`
- `.ly_state/session/l2_role6_macro_micro_data_v6_plan_20260810.md`
- `.ly_state/session/audit_reports/role20_macro_micro_data_v6_plan_20260810.md`
- `.ly_state/session/v6_advisory_audit_7_remediations.md`

No non-repository role or skill source is authoritative for this plan.
