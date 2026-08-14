# Macro & Fundamental Data V8 - Plan Remediation

**Status:** L2 V8 plan remediation submitted; implementation explicitly deferred; awaiting independent L3 plan audit
**Owner:** Role 6 `system-architect` (Tier 2, OpenCode)
**Gate:** `macro_micro_data_v8_plan`
**Future implementation gate:** `macro_micro_data_v8_implementation`
**Supersedes:** `.ly_state/session/implementation_plan_macro_v7_20260810.md`
**Audit basis:** `.ly_state/session/v7_advisory_audit_7_remediations.md`
**Scope:** Plan-only correction of provider contracts, PIT schemas, deferred implementation artifacts, deferred tests, deferred checklist repair, deferred baseline handling, and deferred verification commands

## Goal

Produce one self-contained V8 implementation plan that closes all seven V7 advisory findings and the final deep-audit findings without writing or changing production code, tests, fixtures, checklist code, baseline exceptions, or gate metadata in this phase.

## Current Phase Boundary

This artifact is a plan. The current `macro_micro_data_v8_plan` gate evaluates document completeness only.

- Current remediation deliverables are only `.ly_state/session/implementation_plan_macro_v8_20260810.md` and `.ly_state/session/implementation_plan_macro_v8_detailed_20260810.md`; this remediation creates no audit report or gate metadata.
- Implementation is **DEFERRED to a subsequent L2 OpenCode Implementation Phase**. Deferred work includes code, tests, fixtures, dependency changes, checklist changes, baseline-exception creation, migrations, release artifacts, and command execution.
- That subsequent phase uses `macro_micro_data_v8_implementation`. It must never reuse, replace, or overwrite `macro_micro_data_v8_plan`.
- File paths, structures, schemas, exceptions, test names, fixture names, thresholds, and commands below are normative specifications for that subsequent phase; their present existence or execution is not a V8 plan-audit requirement.
- The current phase must not run focused pytest, gate-control pytest, full pytest, checklist, or gate-enforcer acceptance commands.
- The current phase must not create, edit, approve, or pre-populate `.ly_state/session/phase_gates.json`.
- Role 6 does not audit, approve, or issue a verdict. A separate L3 Role 20 session decides the plan verdict.

## Current Plan-Audit Acceptance

The independent plan audit accepts or rejects only whether this document:

1. Maps all seven findings in `.ly_state/session/v7_advisory_audit_7_remediations.md` to explicit V8 contracts.
2. Defines valid genesis bytes, singleton revision semantics, rematerialization-stable PIT fields, crash-recoverable activation evidence, separate gates, `4/4` VCI transports, and nonrecursive manifest inventory.
3. Defines deferred code structures, schemas, exceptions, tests, fixtures, baseline handling, and command order without requiring those artifacts now.
4. Preserves unchallenged V7 provider, forecast, reconciliation, migration, rollback, checklist, and SoD contracts.
5. Clearly separates current plan acceptance from future implementation acceptance.
6. Passes static Markdown, UTF-8, whitespace, required-literal, and forbidden-authoritative-reliance checks.
7. Closes all eight final deep-audit findings with exact receipt, quorum, containment, gate, planning-authority, lock/recovery, transcript, and runtime contracts.

The current plan audit must not require any deferred file to exist, any deferred code to compile, or any deferred command to run or pass.

## V7 Advisory Remediation Closure Matrix

| # | Required remediation | V8 plan closure | Phase |
|---|---|---|---|
| 1 | Invalid genesis fixture | Quotes every JSON key/string while preserving the declared canonical SHA-256 `76e864...4fdd`. | Contract now; fixture/test deferred. |
| 2 | Impossible/unspecified provider order | Adds exact adapter identities and `singleton_immutable_evidence`; both order fields are null; conflicting second evidence is quarantined as `REVISION_SINGLETON_CONFLICT`. | Contract now; code/tests deferred. |
| 3 | Rematerialization breaks PIT | Adds immutable `origin_ingested_at`, physical `materialized_at`, origin-time filtering, and consumer-byte exclusion of membership metadata. | Contract now; code/tests deferred. |
| 4 | Pointer/evidence crash window | Requires durable `activation_prepared` WAL before replacement, embedded `activation_attempt_id`, commit evidence while locked, and deterministic recovery. | Contract now; code/tests deferred. |
| 5 | Plan gate reused for implementation | Keeps `macro_micro_data_v8_plan` plan-only; binds future work and baseline exceptions to `macro_micro_data_v8_implementation`. | Closed in this plan; gate mutation deferred. |
| 6 | Duplicate VCI statement transports | Uses three statement envelope GETs plus one ratio GET: `4/4` transports and `8/8` logical outputs. | Contract now; fixtures/tests deferred. |
| 7 | Manifest self-inventory ambiguity | Requires `manifest.json` but excludes it from its own inventory; `active_manifest_sha256` anchors exact manifest bytes. | Contract now; code/tests deferred. |

## Final Deep-Audit Closure Matrix

| # | Severity | Finding | V8 closure |
|---|---|---|---|
| 1 | HIGH | Raw receipt identity/schema incomplete | Defines acquisition-unique `RawReceiptV1`, exact Arrow types/nullability, body hash, and domain-separated metadata-plus-body `receipt_sha256`. |
| 2 | HIGH | Degraded release activation undefined | Forbids degraded activation; freezes required providers/work items and requires unanimous required-work success before seal or CAS. |
| 3 | HIGH | Filesystem containment missing | Requires canonical relative paths, traversal/device/ADS rejection, component-wise no-follow opens, and symlink/junction/reparse-point rejection. |
| 4 | HIGH | Gate metadata violates contract | Requires literal `l2_completed=true` and a concrete nonempty `l3_session_key` in every future gate record. |
| 5 | HIGH | Approved detailed artifact not integrity-bound | Adds manifest `planning_authority` hashes for the exact detailed plan and its subsequent approving audit; revalidates them at seal, activation, read, and handoff. |
| 6 | MEDIUM | Pointer lock/recovery underspecified | Fixes one kernel-backed exclusive `current.lock` contract and rejects duplicate, multiple, disconnected, conflicting, or forked nonterminal chains. |
| 7 | MEDIUM | Acceptance transcript creation undefined | Makes one Python runner the parent of every acceptance command and specifies binary stream, exit-code, fsync, byte-count, and SHA-256 capture. |
| 8 | MEDIUM | Runtime reproducibility incomplete | Pins CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, Chromium revision `1234`, and browser version `151.0.7922.34`. |

## Non-Negotiable V8 Decisions

- Schema identifier is `macro_micro/v8`.
- Silver may be empty. Missing trustworthy publication evidence never permits an invented publication time.
- A provider date without time is stored as `source_published_on`; availability begins at the first successful immutable receipt, never at an invented midnight or market-open time.
- Valid source-confirmed forecasts enter Forecast before historical Actual validation; they never enter Silver or Quarantine.
- Existing canonical files and prior releases are never modified in place.
- Every requested transport work item ends in adapter-proven terminal success or a durable failed attempt.
- Same provider revision replay is a canonical no-op. Distinct provider revisions append immutably.
- Current adapters without authoritative revision order use `singleton_immutable_evidence`; conflicting second evidence fails closed.
- Provider-native histories remain separate. Cross-provider selection requires an immutable reconciliation decision eligible at the query cutoff.
- A sealed manifest never changes state or inventories itself. The pointer anchors its exact hash.
- A release has no degraded active state: every frozen required provider and work item must succeed before seal and activation.
- All release, attempt, pointer, evidence, and compatibility paths use one fail-closed containment validator and no-follow filesystem access.
- Activation commits durable evidence while the sole kernel-backed pointer lock remains held; recovery rejects ambiguous nonterminal chains.
- Every sealed release binds exact approved planning authority bytes: the detailed plan and its subsequent independent approving audit.
- No implementation or test artifact may mutate `phase_gates.json`; only independent L3 may write a concrete plan gate record.

## Deferred Minimal File Plan

Every item in this section is deferred to the subsequent L2 OpenCode implementation phase.

- Add `src/omega/data/macro_micro_release.py`: V8 schemas, canonical JSON, hashes, completeness validators, VCI ratio partitioning, forecast classification, revision rules, reconciliation PIT selection, derived lineage, manifests, pointer CAS, migration, rollback.
- Update `scripts/fetch_financial_statements.py`: four-request VCI acquisition, immutable receipts, eight logical endpoint-period outputs, V8 normalization, candidate release build, compatibility export.
- Update `src/omega/data/macro_pipeline.py`: World Bank and Yahoo contracts, official SBV article/PDF acquisition, strict PDF extraction, publication/availability evidence, append-only macro revisions.
- Update `src/omega/quant/graph/fetcher.py`: provider preflight and four completeness-mode iterators; reject opaque financial DataFrame acquisition.
- Update `src/omega/quant/graph/loader.py`: pointer-only Actual reads, source-aware keys, full metric IDs, knowledge-time-safe reconciliation, Forecast rejection.
- Add `.python-version` containing exactly `3.14.4`; the acceptance runner fails unless `sys.version_info == (3, 14, 4, "final", 0)`.
- Update `requirements.txt`: pin existing `pyarrow==23.0.1` and `playwright==1.62.0`, add exactly `pypdf==6.15.0`; no custom PDF parser or second PDF dependency.
- Add `scripts/run_macro_micro_v8_acceptance.py`: sole parent runner for the ordered implementation acceptance commands and immutable binary transcript capture.
- Update `.agents/scripts/checklist.py`: configure UTF-8 stdout/stderr before every current print path.
- Update `scripts/sod_gate_enforcer.py`: direct post-cutoff required-field enforcement independent of strict-gate discovery.
- Extend `tests/test_fetch_financial_statements.py`, `tests/test_macro_pipeline.py`, `tests/test_financial_loader.py`, and `tests/test_strict_repo_local_skill_loading.py`.
- Add `tests/test_macro_micro_release.py`.
- Add `tests/test_macro_micro_acceptance_runner.py` for parent-process, binary transcript, runtime-pin, non-overwrite, and hash-capture behavior.
- Add only the exact V8 fixtures named below under `tests/fixtures/macro_micro/v8/`.
- If needed after attempted fixes, use only `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json` under the independent-approval contract below.
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
data/macro_micro/current.lock
.ly_state/session/macro_micro_attempts/<attempt_id>/
  attempt.json
  activation_prepared.json
  activation_committed.json
  activation_aborted.json
  checkpoints/<work_item_id>.json
  events/<sequence>_<event_type>.json
  failure.json
```

Every release contains every listed release artifact, including schema-correct empty Parquet files. `manifest.json` is required but excluded from its own artifact inventory. Release artifacts are immutable after sealing. Attempt events are append-only and never canonical data.

## 1. Provider Adapter and Completeness Contracts

### Pinned Runtime Contracts

| Provider | Adapter | Completeness mode | Pinned source/runtime |
|---|---|---|---|
| VCI financial | `vci_financial_raw/v2` | `explicit_single_envelope_terminal` | `vnstock==4.0.4` contract; base `https://iq.vietcap.com.vn/api/iq-insight-service`; `requests==2.33.1`. |
| World Bank | `world_bank_v2/v1` | `authoritative_numbered_pages` | `https://api.worldbank.org/v2/country/VN/indicator/{indicator}`; `requests==2.33.1`. |
| Yahoo USD/VND | `yahoo_chart_v8/v1` | `explicit_single_envelope_terminal` | `https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X`; `requests==2.33.1`. |
| SBV weekly interbank | `sbv_weekly_interbank_pdf/v2` | `official_article_attachment_snapshot` | Official `https://www.sbv.gov.vn`; `playwright==1.62.0`; Chromium `151.0.7922.34`; `beautifulsoup4==4.14.3`; `pypdf==6.15.0`. |
| Storage | `macro_micro_storage/v1` | N/A | `pandas==2.3.3`; `pyarrow==23.0.1`. |

The complete runtime is CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, and Playwright-managed Chromium revision `1234` with browser version `151.0.7922.34`. Installation uses `python -m playwright install chromium`. Runtime validation rejects a system browser, custom `executable_path`, different revision/version, or unpinned Python/package version. The acceptance transcript records `sys.version`, package versions, the installed Playwright `driver/package/browsers.json` exact-byte SHA-256, resolved managed browser path, revision, and browser version before any command runs.

### VCI Exact Routes and Fixtures

Method is `GET`. Each statement section is fetched exactly once. The immutable response envelope must contain object branch `data`, nonempty list branches `data.years` and `data.quarters`, and no provider error or truncation marker. `vnstock==4.0.4` performs one GET and then selects one branch; V8 retains that transport shape while materializing both deterministic slices.

| Statement GET | Exact path/query | Raw envelope fixture | Logical slices |
|---|---|---|---|
| `income_statement` | `/v1/company/{symbol}/financial-statement?section=INCOME_STATEMENT` | `tests/fixtures/macro_micro/v8/vci/income_statement_raw.json` | `data.years` to `income_statement_year.json`; `data.quarters` to `income_statement_quarter.json` |
| `balance_sheet` | `/v1/company/{symbol}/financial-statement?section=BALANCE_SHEET` | `tests/fixtures/macro_micro/v8/vci/balance_sheet_raw.json` | `data.years` to `balance_sheet_year.json`; `data.quarters` to `balance_sheet_quarter.json` |
| `cash_flow` | `/v1/company/{symbol}/financial-statement?section=CASH_FLOW` | `tests/fixtures/macro_micro/v8/vci/cash_flow_raw.json` | `data.years` to `cash_flow_year.json`; `data.quarters` to `cash_flow_quarter.json` |

`slice_vci_statement_envelope(envelope, section)` validates both branches before returning either. The two outputs share one `source_receipt_id` and `receipt_sha256`, and use distinct deterministic `source_record_locator` prefixes `data.years` and `data.quarters`. Missing either branch fails the entire statement transport; a second request solely to obtain the other period is forbidden.

Ratios use exactly one transport request:

```text
GET /v1/company/{symbol}/statistics-financial
response branch: data
required type: JSON array of row objects
```

Deferred ratio fixtures:

- `tests/fixtures/macro_micro/v8/vci/ratios_raw.json`: exact full raw response envelope, not a sliced helper result.
- `tests/fixtures/macro_micro/v8/vci/ratios_year_expected.json`: exact deterministic annual slice from the raw fixture.
- `tests/fixtures/macro_micro/v8/vci/ratios_quarter_expected.json`: exact deterministic quarterly slice from the same raw fixture.
- `tests/fixtures/macro_micro/v8/vci/ratios_contract.json`: row predicates, sort keys, counts, field names, and raw receipt hash.

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

- Raw transport requests per symbol: `4` (`3` statement envelope GETs plus `1` ratios GET).
- Logical endpoint-period outputs per symbol: `8` (`6` statement outputs plus `2` ratio partitions).
- Each statement year/quarter pair shares one immutable raw statement envelope and uses deterministic branch locators.
- Ratio annual and quarterly outputs share one immutable raw receipt and use distinct deterministic slice locators.
- Preflight requires `4/4` transport contracts and `8/8` logical output contracts. It must not issue duplicate statement or ratio requests solely to emulate year/quarter helpers.

VCI request headers are frozen in `tests/fixtures/macro_micro/v8/vci/request_contract.json`:

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

First-page fixtures remain under `tests/fixtures/macro_micro/v8/world_bank/`. Metadata fields `page`, `pages`, `per_page`, and `total` are mandatory. Yahoo uses `tests/fixtures/macro_micro/v8/yahoo/usdvnd_chart.json` and requires one bounded result with equal timestamp and close-array lengths.

### Four Completeness Modes

- `cursor_token`: continue only with a provider-issued next cursor; reject guessed offsets, repeated cursors, changing scope, or premature termination.
- `authoritative_numbered_pages`: fetch exactly `1..pages`; require stable page metadata and exact accounting against provider `total`. World Bank uses this mode.
- `explicit_single_envelope_terminal`: require one schema-pinned nonpaginated envelope with no cursor, truncation, partial-result, or error marker. VCI and Yahoo use this mode.
- `official_article_attachment_snapshot`: capture one schema-pinned official article root and exactly one linked immutable attachment; hash both before parsing; reject fallback pages, alternate attachments, OCR, or heuristic table recovery. SBV uses this mode.

Every Bronze receipt conforms exactly to `RawReceiptV1` below. Adapter or source-contract change requires a new adapter version and new fixtures.

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

- `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_article_root.html`
- `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31.pdf`
- `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_contract.json`
- `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_expected_rows.json`

Downloaded fixture evidence, resolved during the L2 implementation phase:

```text
article_root_utf8_bytes = actual byte count of downloaded official SBV article-root fixture
article_root_sha256 = SHA-256 computed from downloaded official SBV article-root fixture
pdf_bytes = actual byte count of downloaded official SBV PDF fixture
pdf_sha256 = SHA-256 computed from downloaded official SBV PDF fixture
```

L2 must acquire both official SBV files with a repository script or Playwright, persist the exact downloaded bytes, then compute and record their actual byte counts and lowercase SHA-256 values in `provider_contract.json` and the implementation evidence before offline parsing or tests. No predeclared byte count or hash is required, and L2 must not invent either value.

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
- `provider_revision_key` is the exact provider-supplied resolved attachment URL, including its document UUID/query token. Under V8 it is immutable document identity, not an ordering timestamp or sequence.
- Primary `source_receipt_id` and `receipt_sha256` identify the PDF; ordered context receipt evidence identifies the article-root HTML.

Any SBV report added later must be supplied as an explicit official article URL in the immutable work manifest and pass the same versioned contract. V8 does not implement unpinned site-wide discovery.

SBV failures use exact reason codes:

- `SBV_ARTICLE_CONTRACT_VIOLATION`
- `SBV_ATTACHMENT_CONTRACT_VIOLATION`
- `SBV_PDF_HASH_MISMATCH`
- `SBV_PDF_TABLE_SCHEMA_DRIFT`
- `SBV_PUBLICATION_DATE_MISSING`
- `SBV_OBSERVATION_RANGE_INVALID`

### Exact Adapter Revision Identity and Ordering

No current adapter exposes a contract-pinned authoritative revision timestamp or monotone sequence. V8 therefore uses one explicit fail-closed mode for all four current adapters instead of manufacturing order from URLs, hashes, receipt times, file order, or ingestion order.

| Adapter ID | Canonical `source` | Exact provider-stream identity | `provider_revision_key` | `revision_order_kind` | `source_revision_at` | `revision_seq` |
|---|---|---|---|---|---|---|
| `vci_financial_raw/v2` | `vci` | `(financial, vci, symbol, metric_id, fiscal_period_end)` | `null`; source locator is evidence identity only | `singleton_immutable_evidence` | `null` | `null` |
| `world_bank_v2/v1` | `world_bank` | `(macro, world_bank, indicator, observation_date, {})` | `null`; indicator/date are stream identity, not order | `singleton_immutable_evidence` | `null` | `null` |
| `yahoo_chart_v8/v1` | `yahoo` | `(macro, yahoo, usdvnd, observation_date, {})` | `null`; chart timestamp is observation identity, not revision order | `singleton_immutable_evidence` | `null` | `null` |
| `sbv_weekly_interbank_pdf/v2` | `sbv` | `(macro, sbv, interbank_rate, observation_date, dimensions_json)` | Exact resolved official attachment URL as document identity only | `singleton_immutable_evidence` | `null` | `null` |

Singleton semantics are exact:

1. One accepted normalized revision may exist for each provider-stream identity under V8.
2. Replay with the same `revision_id` and `record_evidence_sha256` is a canonical no-op; only a previously unseen evidence link may append.
3. A second normalized revision or different evidence hash for the same stream is never ordered. Preserve the accepted revision, retain the new raw evidence, and route the conflicting candidate to permanent Quarantine with `REVISION_SINGLETON_CONFLICT`.
4. `REVISION_ORDER_MISSING` does not apply to a valid singleton row because both order fields are required to be null. It remains reserved for a future adapter that declares timestamp or sequence ordering but omits its required value.
5. An official correction to an existing singleton stream requires a separately reviewed adapter/schema version and explicit migration policy; V8 does not guess which value is newer.
6. A stream cannot mix singleton, timestamp, or sequence modes. Hashes, receipt times, `available_at`, `origin_ingested_at`, and `materialized_at` never break revision ties.

### Provider Preflight

Preflight is deferred implementation work. It must:

1. Verify `4/4` VCI transport requests and `8/8` logical outputs for the fixture symbol.
2. Verify all three World Bank IDs and pagination metadata.
3. Verify Yahoo array equality and terminal envelope.
4. Replay SBV only from the pinned article-root and PDF fixtures; no live network is required for hermetic tests.
5. Compare adapter constants against `tests/fixtures/macro_micro/v8/provider_contract.json`.
6. Replay identical evidence and inject one conflicting revision per adapter to prove singleton no-op and `REVISION_SINGLETON_CONFLICT` behavior.
7. Abort the candidate release on any route, header, selector, schema, hash, partition, completeness, or revision-mode drift.

## 2. Deferred Code Structures and Exceptions

`src/omega/data/macro_micro_release.py` is the single owner of release-domain logic. The subsequent implementation phase adds these concrete structures; no one-implementation interface layer is required.

### Structures

- `RawReceiptV1`: acquisition-unique immutable transport receipt with the exact schema and two-layer integrity contract below.
- `ReceiptRefV1`: `source_receipt_id`, `raw_body_sha256`, `receipt_sha256`, `adapter_id`, `adapter_version`, `source_url`, `received_at`, `role` (`primary` or `context`).
- `RecordEvidenceV2`: primary receipt, ordered context receipts, source locator, exact field paths/selectors, exact source values, adapter identity, `record_evidence_sha256`.
- `CanonicalRecordV8`: canonical Actual/Forecast row schema below.
- `ReconciliationDecisionV1`: policy, candidate, decision knowledge-time schema below.
- `DerivedRecordV1`: formula and ordered-parent lineage schema.
- `ReleaseManifestV1`: sealed artifact inventory and hashes.
- `ActivePointerV1`: generation, active release identity/hash, rollback floor, previous pointer hash.
- `ActivationPreparedV1`: durable WAL containing exact prior and target pointer bytes/hashes plus `activation_attempt_id`.
- `ActivationCommitV1`: durable commit evidence binding one prepared record to the observed authoritative pointer hash.
- `ActivationAbortV1`: durable abort evidence binding one prepared record to unchanged authoritative prior-pointer bytes.
- `AttemptEventV1`: append-only attempt state transition.

### Exact `RawReceiptV1` Schema and Identity

The two Bronze receipt Parquet files use this closed Arrow schema; unknown columns fail. `string` means UTF-8, hashes are lowercase 64-character hexadecimal strings, JSON strings are exact `canonical_json_v1` text, and all timestamps are `timestamp[us, tz=UTC]`.

| Field | Arrow type | Nullable | Contract |
|---|---|---:|---|
| `schema_version` | `string` | no | Exact `macro_micro_raw_receipt/v1`. |
| `release_id` | `string` | no | Physical containing release. |
| `materialized_at` | `timestamp[us, tz=UTC]` | no | Physical write time. |
| `origin_release_id` | `string` | no | First sealed release containing this receipt. |
| `origin_ingested_at` | `timestamp[us, tz=UTC]` | no | First immutable candidate-ingestion time. |
| `source_receipt_id` | `string` | no | Acquisition identity defined below. |
| `attempt_id` | `string` | no | Owning attempt. |
| `work_item_id` | `string` | no | Frozen requested work item. |
| `acquisition_ordinal` | `uint64` | no | Attempt-global monotone ordinal allocated before I/O. |
| `provider_id` | `string` | no | Frozen provider identity. |
| `adapter_id` | `string` | no | Contract-pinned adapter identity. |
| `adapter_version` | `string` | no | Contract-pinned adapter version. |
| `completeness_mode` | `string` | no | One of the four declared modes. |
| `request_method` | `string` | no | Uppercase HTTP method. |
| `request_url` | `string` | no | Canonical requested URL without credentials. |
| `request_scope_json` | `string` | no | Canonical normalized parameters/body/scope. |
| `request_headers_json` | `string` | no | Canonical allowlisted, secret-redacted request headers. |
| `requested_at` | `timestamp[us, tz=UTC]` | no | Actual request start. |
| `response_started_at` | `timestamp[us, tz=UTC]` | no | First response-byte time. |
| `received_at` | `timestamp[us, tz=UTC]` | no | Last response-byte time. |
| `body_hashed_at` | `timestamp[us, tz=UTC]` | no | Time exact body hashing completed. |
| `response_status` | `int32` | no | Exact HTTP status. |
| `response_url` | `string` | no | Final URL after allowed redirects. |
| `redirect_chain_json` | `string` | no | Canonical ordered redirect evidence; `[]` when absent. |
| `response_headers_json` | `string` | no | Canonical allowlisted response headers. |
| `content_type` | `string` | yes | Exact normalized media type; null only when absent. |
| `completeness_proof_json` | `string` | no | Canonical mode-specific terminal proof. |
| `raw_body` | `binary` | no | Exact response bytes, including valid zero-length bodies. |
| `raw_body_size` | `uint64` | no | Exact byte length of `raw_body`. |
| `raw_body_sha256` | `string` | no | Raw-body hash defined below. |
| `receipt_sha256` | `string` | no | Metadata-plus-body hash defined below. |

Before any transport, the attempt ledger durably allocates a never-reused `acquisition_ordinal`. `(attempt_id, acquisition_ordinal)` and `source_receipt_id` are repository-unique. `source_receipt_id = hex(SHA256(canonical_json_v1({"schema_version":"source_receipt_id/v1","attempt_id":...,"work_item_id":...,"acquisition_ordinal":...,"provider_id":...,"adapter_id":...,"adapter_version":...,"request_method":...,"request_url":...,"request_scope_json":...})))`. Every retry allocates a new ordinal and ID even when request or response bytes repeat; a pre-response transport failure produces durable attempt failure evidence, not a fabricated `RawReceiptV1`.

`raw_body_sha256 = hex(SHA256(raw_body))`. Build `receipt_metadata_v1` from every schema field in table order except `release_id`, `materialized_at`, `raw_body`, and `receipt_sha256`; validate `raw_body_size` and `raw_body_sha256` first. Let `metadata = canonical_json_v1(receipt_metadata_v1)`. Then `receipt_sha256 = hex(SHA256(b"RawReceiptV1\0" || uint64_be(len(metadata)) || metadata || uint64_be(len(raw_body)) || raw_body))`. Hash exact bytes; perform no decoding, decompression, newline normalization, header reordering outside canonical JSON, or timestamp reconstruction. Rematerialization preserves origin fields and both hashes.

### Functions

- `canonical_json_v1(value) -> bytes`
- `sha256_canonical(value) -> str`
- `open_contained_no_follow(root, relative_path, mode) -> BinaryIO`
- `partition_vci_ratio_rows(rows, symbol) -> tuple[list, list]`
- `validate_sbv_weekly_contract(article_bytes, pdf_bytes, contract) -> list[dict]`
- `classify_forecast_record(record, evidence) -> ClassificationResult`
- `select_provider_revision_as_of(rows, cutoff) -> CanonicalRecordV8 | None`
- `select_reconciled_revision_as_of(native_rows, decisions, cutoff) -> CanonicalRecordV8 | None`
- `seal_manifest(candidate_dir) -> ReleaseManifestV1`
- `activate_release_cas(expected_pointer_hash, sealed_manifest) -> ActivePointerV1`
- `recover_prepared_activation(pointer_path, attempts_dir) -> RecoveryResult`
- `migrate_generation_one(legacy_paths) -> MigrationReportV1`
- `rollback_release(expected_pointer_hash, target_release_id) -> ActivePointerV1`

### Exceptions

- `MacroMicroContractError`
- `ProviderContractError`
- `CompletenessError`
- `EvidenceIntegrityError`
- `FilesystemContainmentError`
- `ReleaseQuorumError`
- `PlanningAuthorityError`
- `RevisionConflictError`
- `ReconciliationKnowledgeError`
- `PublicationError`
- `PointerCASConflict`
- `PointerLockError`
- `PointerRecoveryDivergence`
- `MigrationError`

All public CLI boundaries catch these typed exceptions, persist a durable failed-attempt record, preserve prior canonical state, and return nonzero. Internal helpers do not swallow them.

## 3. Deferred Canonical Serialization and Hash Contracts

All work in this section is a specification for the subsequent L2 OpenCode implementation phase.

### Release Membership and Immutable Origin

Every row physically contained in release `<release_id>` carries `release_id == <release_id>` and a release-specific `materialized_at`, the actual timestamp that physical row was written into that containing release. Manifest validation rejects null or mixed membership. These two fields are physical membership metadata, not immutable origin or consumer identity.

Actual, Forecast, Derived, reconciliation, receipt, and resolution rows also carry immutable `origin_release_id` and `origin_ingested_at`: respectively the first sealed release containing the logical row and the actual ingestion instant when that immutable row first entered its origin candidate release. Later complete releases may rematerialize the row with a new `release_id` and `materialized_at`; they must preserve `origin_release_id`, `origin_ingested_at`, business identity, revision identity, evidence identity, availability, and payload.

Quarantine rows instead carry current `release_id`, current `materialized_at`, immutable `first_seen_release_id`, immutable `origin_ingested_at`, and immutable `quarantine_id`. Origin or first-seen IDs must reference an existing release no newer than the containing release. `materialized_at >= origin_ingested_at` is required.

`canonical_consumer_json_v1(row)` validates the schema, removes exactly `release_id` and `materialized_at`, then applies `canonical_json_v1`. Historical loaders, reconciliation outputs, PIT acceptance hashes, compatibility exports, graph inputs, features, and backtests compare or expose these consumer bytes. Rematerializing an unchanged row must therefore change only storage membership bytes while leaving consumer bytes and `revision_id` byte-identical.

### `canonical_json_v1`

`src/omega/data/macro_micro_release.py::canonical_json_v1` is the only canonical serializer used by V8 IDs and evidence hashes:

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

- `source_receipt_id`: acquisition-unique SHA-256 identity over the exact pre-I/O projection defined by `RawReceiptV1`; retries never reuse it. It is not a content hash or provider revision key.
- `raw_body_sha256`: `SHA256(exact_raw_response_bytes)` before parsing.
- `receipt_sha256`: domain-separated `RawReceiptV1` metadata-plus-body SHA-256; it binds immutable origin, acquisition, adapter, request, response, completeness, raw-body length/hash, and exact raw bytes while excluding only physical rematerialization fields.
- `record_evidence_sha256`: `SHA256(canonical_json_v1(record_evidence_v2))`. Evidence contains primary/context receipts, source locator, exact field paths/selectors, exact values, and adapter identity.
- `provider_revision_key`: nullable exact provider timestamp, sequence, version token, or immutable document identity. Singleton rows may leave it null. It is never synthesized from hashes, ingestion time, row order, or current time.
- `revision_id`: `SHA256(canonical_json_v1(revision_identity_v8))`, containing schema, dataset, source-aware logical key, record type, normalized payload, publication evidence, declared revision mode, immutable origin timing, and origin evidence hash. It excludes `release_id` and `materialized_at`.

Duplicate `(attempt_id, acquisition_ordinal)` or `source_receipt_id`, or conflicting metadata/body bytes for one receipt identity, fail as `RECEIPT_ID_CONFLICT`. Conflicting normalized evidence for one `record_evidence_sha256` fails as `RECORD_EVIDENCE_HASH_CONFLICT`. A singleton conflict routes to Quarantine as `REVISION_SINGLETON_CONFLICT`. Missing or ambiguous order routes to `REVISION_ORDER_MISSING` only when the adapter declares timestamp or sequence ordering.

## 4. Deferred `CanonicalRecordV8` Schema

`CanonicalRecordV8` is a tagged union of financial and macro records. Unknown columns fail schema validation.

### Common Fields

| Field | Exact contract |
|---|---|
| `schema_version` | Exactly `macro_micro/v8`. |
| `release_id` | Current containing release membership. |
| `materialized_at` | Actual timestamp this physical row was written into the containing release; excluded from consumer bytes and immutable identity. |
| `origin_release_id` | First sealed release containing the immutable revision. |
| `origin_ingested_at` | Actual timestamp the immutable revision first entered its origin candidate release; preserved across rematerialization and used for PIT eligibility. |
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
| `provider_revision_key` | Nullable exact provider-supplied ordering or immutable-document identity; never a synthesized tie-breaker. |
| `revision_order_kind` | Exactly `singleton_immutable_evidence`, `source_revision_at`, or `revision_seq`. |
| `source_revision_at` | Exact provider revision timestamp when timestamp ordering is selected; otherwise null. |
| `revision_seq` | Positive provider sequence when sequence ordering is selected; otherwise null. |
| `revision_id` | Immutable normalized provider-revision identity. |

For `source_revision_at`, only the timestamp is non-null. For `revision_seq`, only the positive sequence is non-null. For `singleton_immutable_evidence`, both are null. One provider-native stream cannot change ordering kind. Equal ordered values with different revisions fail as `REVISION_ORDER_COLLISION`; singleton differences fail as `REVISION_SINGLETON_CONFLICT`. Hashes, receipt order, file order, origin ingestion, and materialization never break ties.

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
5. `first_observed_at <= available_at <= origin_ingested_at` for receipt-based availability. Timestamp-based availability must not precede the exact provider timestamp or origin-ingestion cutoff. `materialized_at` is never an availability or PIT cutoff input.

## 5. Deferred Source-Aware Revision and Reconciliation Contract

### Provider-Native As-Of Selection

1. Validate pointer, sealed manifest, artifact hashes, schemas, and membership.
2. Read only `record_type=actual` for historical consumers.
3. Filter `available_at <= cutoff` and `origin_ingested_at <= cutoff`; never filter by `release_id` or `materialized_at` after pointer membership validation.
4. Group by the provider-stream key including `source`.
5. For `singleton_immutable_evidence`, select the sole accepted eligible revision and reject multiple accepted revisions as `REVISION_SINGLETON_CONFLICT`.
6. For timestamp or sequence mode, select the greatest eligible provider order according to the stream's fixed order kind.
7. Reject ties, mixed order kinds, malformed timestamps, or absent required ordering evidence.

This yields at most one eligible native revision per provider. It does not choose a cross-provider canonical value.

### `ReconciliationDecisionV1` Schema

Every release contains `reconciliation/canonical_provider_selection.parquet`, including a schema-correct empty file. Each immutable row requires:

| Field | Exact contract |
|---|---|
| `schema_version` | Exactly `canonical_provider_selection/v1`. |
| `release_id` | Current containing release. |
| `materialized_at` | Actual physical write time in the containing release; excluded from reconciliation consumer bytes and identity. |
| `origin_release_id` | First sealed release containing the decision. |
| `dataset` | `financial` or `macro`. |
| `canonical_key_json` | `canonical_json_v1` of the logical key without `source`. |
| `selection_policy_id` | Stable named policy. |
| `selection_policy_version` | Immutable semantic version. |
| `selection_policy_sha256` | SHA-256 of exact policy bytes. |
| `policy_effective_at` | Earliest instant the policy may govern selection. |
| `policy_available_at` | Earliest evidenced instant the exact policy bytes were knowable. |
| `policy_origin_ingested_at` | Actual instant the exact policy bytes first entered their origin candidate release. |
| `candidate_sources` | Ordered source IDs. |
| `candidate_revision_ids` | Ordered one-to-one revision IDs. |
| `candidate_available_at` | Ordered one-to-one availability instants. |
| `candidate_origin_ingested_at` | Ordered one-to-one immutable origin-ingestion instants. |
| `selected_source` | One candidate source or null. |
| `selected_revision_id` | Matching candidate revision or null. |
| `decision_status` | Exactly `selected` or `unresolved`. |
| `decision_reason` | Stable machine-readable outcome. |
| `decision_created_at` | Actual instant the exact candidates and policy were evaluated. |
| `decision_recorded_at` | Actual instant the immutable decision became durable. |
| `decision_origin_ingested_at` | Actual instant the immutable decision first entered its origin candidate release. |
| `decision_input_sha256` | Hash of exact policy bytes/times and ordered candidates/times/revisions. |
| `reconciliation_id` | Hash of canonical key, policy identity, input hash, all decision times, and outcome. |

Candidate arrays are ordered by configured priority then source ID; lengths must match. A policy, candidate, policy-knowledge, or decision-knowledge change appends a new row.

At cutoff, eligibility requires every policy, candidate, and decision timestamp, including all `*_origin_ingested_at` values, at or before cutoff; exact candidate revision-set equality; `decision_created_at` no earlier than every input knowledge time; `decision_recorded_at >= decision_created_at`; `decision_origin_ingested_at >= decision_recorded_at`. `materialized_at` is ignored after release validation. Missing, stale, unresolved, contradictory, future-known, or candidate-mismatched decisions return no canonical value.

Deferred fixtures:

- `tests/fixtures/macro_micro/v8/reconciliation/future_policy.json`
- `tests/fixtures/macro_micro/v8/reconciliation/future_decision.json`

Deferred exact tests:

- `test_reconciliation_future_policy_knowledge_cannot_change_earlier_cutoff`
- `test_reconciliation_future_decision_knowledge_cannot_change_earlier_cutoff`

Each test freezes an earlier cutoff result, appends only future-known evidence, reruns the earlier cutoff, and requires byte-identical output.

### Append-Only Replay Rules

- Same provider-stream key plus same `revision_id`: canonical no-op; append only unseen evidence links.
- Singleton stream plus a distinct revision: preserve raw evidence and append permanent Quarantine reason `REVISION_SINGLETON_CONFLICT`; never replace the accepted row.
- Ordered stream plus a distinct, validly ordered `revision_id`: append immutable revision. Late older revisions remain stored and become eligible only where provider order and cutoffs permit.
- Prior releases remain byte-identical. Later complete releases preserve origin IDs, `origin_ingested_at`, immutable identities, and consumer bytes while changing only `release_id` and `materialized_at`.

## 6. Deferred Derived, Forecast, and Quarantine Contracts

### Frequency-Safe Metrics and Derived Lineage

Only these derived metrics are in V8:

- `derived_ratios:<period_type>:current_ratio`
- `derived_ratios:<period_type>:debt_to_equity`

| Metric | `formula_id` | Version | Ordered expression |
|---|---|---|---|
| `current_ratio` | `omega.financial.current_ratio` | `1.0.0` | parent 0 `balance_sheet:<period_type>:current_assets` divided by parent 1 `balance_sheet:<period_type>:current_liabilities` |
| `debt_to_equity` | `omega.financial.debt_to_equity` | `1.0.0` | parent 0 `balance_sheet:<period_type>:total_liabilities` divided by parent 1 `balance_sheet:<period_type>:equity` |

Parents must be the exact canonical Actual revisions selected at the cutoff, share symbol/period/provider-selection context, be finite, and have a nonzero denominator. Invalid derivations produce no derived value and append a reasoned rejection.

`DerivedRecordV1` requires `schema_version`, current `release_id`, current `materialized_at`, immutable `origin_release_id`, immutable `origin_ingested_at`, `dataset=financial_derived`, `record_type=actual`, `source=derived_ratios`, `symbol`, `period_type`, `fiscal_period_end`, `metric_id`, `item_value_decimal`, `formula_id`, `formula_version`, `ordered_parent_lineage`, `lineage_sha256`, `source_published_on`, `source_published_at`, `first_observed_at`, `availability_basis`, `available_at`, null `provider_revision_key`, `revision_order_kind=parent_lineage`, `record_evidence_sha256`, and `revision_id`.

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
parent_origin_ingested_at
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

Minimum V8 reason codes include `OPAQUE_PROVIDER_RESPONSE`, `NUMBERED_PAGE_PROTOCOL_VIOLATION`, `SINGLE_ENVELOPE_PROTOCOL_VIOLATION`, `ARTICLE_ATTACHMENT_PROTOCOL_VIOLATION`, `RECEIPT_ID_CONFLICT`, `RECORD_EVIDENCE_HASH_CONFLICT`, `REVISION_ORDER_MISSING`, `REVISION_ORDER_COLLISION`, `PUBLICATION_EVIDENCE_MISSING`, `FUTURE_PERIOD_UNCONFIRMED`, `DERIVED_PARENT_SOURCE_MISMATCH`, and every VCI/SBV code declared above.

## 7. Deferred Sealed Release and Pointer-CAS Contract

### Filesystem Containment and No-Follow Contract

Every persisted or consumed path for release artifacts, manifests, pointers, attempts, checkpoints, events, failures, activation evidence, planning authority, fixtures, acceptance evidence, and `--output` compatibility exports is a canonical forward-slash repository-relative string beneath one explicit trusted root. The parser rejects empty input; NUL; backslash; leading slash; `//`; drive prefixes; UNC, `\\?\\`, `\\.\\`, and `\??\` device forms; any colon or alternate-data-stream syntax; empty, `.` or `..` segments; trailing dot/space; and case-insensitive DOS device segments `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, or `LPT1`-`LPT9` with or without an extension. Absolute paths are never converted to relative paths.

Lexical validation is necessary but insufficient. The implementation opens the trusted root, every existing intermediate component, and the final component with component-wise no-follow semantics; rejects symbolic links, junctions, mount-point substitutions, and every filesystem reparse point at the root, intermediate, or final component; retains verified parent handles through the operation; and verifies the handle-derived final location remains beneath the same trusted root. POSIX uses handle-relative `openat` with `O_NOFOLLOW` and `O_DIRECTORY` where applicable. Windows opens every component with `CreateFileW` using `FILE_FLAG_OPEN_REPARSE_POINT` and `FILE_FLAG_BACKUP_SEMANTICS` where applicable, rejects `FILE_ATTRIBUTE_REPARSE_POINT`, and never reopens a validated target by an unchecked string. New files use create-new under a verified parent; atomic replacement uses a verified same-directory temporary and revalidates the destination parent. `Path.resolve()`, `absolute()`, string-prefix checks, or pre-check-then-follow access alone do not satisfy this contract.

### Required Success Quorum and Planning Authority

`attempt.json` immutably freezes sorted unique `required_provider_ids`, `required_work_item_ids`, the provider-to-work-item mapping, and `required_scope_sha256` before acquisition. V8 defines no optional provider, warning-only required failure, or degraded active pointer. A candidate may preserve failure evidence, but seal and CAS require every required work item to have exactly one adapter-proven terminal success, zero required failures, and at least one successful work item for every required provider.

`ReleaseManifestV1` stores the frozen sets and mapping plus `required_provider_count`, `successful_provider_count`, `required_work_item_count`, `successful_work_item_count`, `failed_required_work_item_ids`, `quorum_met`, and `release_health`. A sealable/activatable manifest requires equal required/success counts, `failed_required_work_item_ids=[]`, `quorum_met=true`, and `release_health="complete"`. Seal, recovery commit, activation CAS, rollback target validation, and every reader reject any other combination; there is no implicit consumer fallback to a partial release.

The manifest also contains a closed `planning_authority` object: `detailed_plan_path`, `detailed_plan_sha256`, `approving_plan_audit_path`, `approving_plan_audit_sha256`, `approving_plan_audit_verdict`, and `implementation_gate`. The detailed path is exactly `.ly_state/session/implementation_plan_macro_v8_detailed_20260810.md`; `implementation_gate` is exactly `macro_micro_data_v8_implementation`; the verdict is exactly `[APPROVED]`. Both hashes are lowercase SHA-256 over exact raw file bytes with no decoding, BOM removal, newline normalization, or canonical reserialization. The approving audit must be produced after the final detailed-plan bytes, explicitly quote the same detailed-plan hash, and be independent; any pre-remediation audit artifact is ineligible. Seal, activation, recovery, every authoritative read, and final implementation handoff re-read both files through the containment validator and require both exact hashes and the audit's bound detailed hash/verdict.

### Sealed Manifest

`manifest.json` is written once with `state=sealed`. It contains release ID/sequence, schema versions, cutoff, adapter pins, reconciliation-policy identity and knowledge times, required-success quorum, planning authority, every required non-manifest artifact path/hash/row count/schema fingerprint, current-membership count, inherited/origin counts, fixture hashes, and release accounting checks. `manifest.json` is required release metadata but is explicitly excluded from its own `artifacts` inventory; recursive self-hashing is forbidden.

Seal procedure:

1. Write and fsync every non-manifest artifact under a new candidate release directory.
2. Re-read those artifacts; validate bytes, schemas, row counts, membership, origin references, foreign keys, completeness, PIT constraints, required-success quorum, path containment, and planning-authority hashes.
3. Build the manifest inventory from exactly those required non-manifest artifacts. Assert no inventory path resolves to `manifest.json`.
4. Serialize the manifest with `canonical_json_v1`, atomically write/fsync it, fsync the release directory, and hash its exact bytes.
5. Re-open the manifest and all inventoried artifacts through the production reader validator.
6. On activation and every read, require `SHA256(exact manifest bytes) == current.json.active_manifest_sha256` before trusting any manifest field or artifact hash.

The manifest is never mutated to `validated`, `published`, `active`, or `rolled_back`. Pointer state and attempt events hold lifecycle state.

### Generation-Zero Sentinel

Deferred fixture: `tests/fixtures/macro_micro/v8/pointer/genesis_current.json`. Exact UTF-8 bytes, no BOM or trailing newline:

```json
{"activated_at":null,"activation_attempt_id":null,"activation_kind":"genesis","active_manifest_path":null,"active_manifest_sha256":null,"active_release_id":null,"active_release_sequence":0,"legacy_fallback_allowed":true,"pointer_generation":0,"pointer_schema_version":"macro_micro_pointer/v1","previous_pointer_sha256":null,"rollback_floor_release_sequence":0}
```

`GENESIS_POINTER_SHA256 = 76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`. `test_genesis_fixture_is_valid_canonical_json_with_declared_sha256` must parse, canonical-reserialize, assert exact bytes, assert no BOM/trailing newline, and assert the declared hash. Initialization uses create-new semantics; an existing malformed pointer is never guessed or overwritten.

### Pointer CAS and Attempt Ledger

The pointer is sole publication authority. The only publication lock is `data/macro_micro/current.lock`, opened through the containment validator as a non-reparse regular file. Writers acquire a kernel-backed exclusive lock over byte range `[0,1)` on one retained file handle (`LockFileEx` on Windows; `flock(LOCK_EX)` on POSIX) before enumerating attempts. Acquisition waits for exclusive ownership; interruption or OS failure raises `PointerLockError`. File contents, PID text, timestamps, and existence do not signal ownership; the file is never deleted, replaced, or treated as stale. No per-attempt lock, alternate lock path, or in-process mutex is publication authority. The same handle remains locked through recovery, pointer CAS, terminal evidence fsync, and parent-directory fsync.

Activation and rollback use the same WAL protocol:

1. Acquire `current.lock`. Before starting new work, validate the complete attempt ledger and recover the sole allowed durable nonterminal `activation_prepared` record, if one exists.
2. Read exact prior pointer bytes; verify schema/hash; compare expected pointer hash and generation.
3. Revalidate the target sealed manifest, its nonrecursive inventory, and all artifacts; require target sequence at or above rollback floor.
4. Allocate one immutable `activation_attempt_id`. Build generation `current + 1` with target identity, activation metadata, prior pointer hash, nondecreasing floor, and that exact embedded `activation_attempt_id`.
5. Before pointer replacement, create and fsync `activation_prepared.json`, then fsync its parent directory. It contains schema `activation_prepared/v1`, attempt ID, activation kind, exact prior pointer bytes/hash/generation, exact target pointer bytes/hash/generation, target release/manifest path/hash, prepared timestamp, and prepared-record SHA-256.
6. Write/fsync a same-directory temporary pointer, atomically replace `current.json`, fsync the pointer directory, and re-read exact authoritative bytes while still holding the lock.
7. Require the observed pointer to equal the prepared target bytes/hash and embedded attempt ID. Create and fsync `activation_committed.json`, then fsync its parent directory, while still holding the lock. Commit evidence contains schema `activation_committed/v1`, attempt ID, prepared-record hash, target pointer hash, observed pointer hash, commit timestamp, and `recovered=false`.
8. Release the retained kernel lock only after durable commit or abort evidence and its parent directory are fsynced. Append ancillary lifecycle events after terminal evidence; they are not substitutes for the prepared/terminal pair.

Deterministic recovery first enumerates all attempt directories under the lock, validates every prepared/commit/abort schema and self-hash, and constructs chains from exact prior/target pointer hashes and generations. Each prepared record has zero or exactly one matching terminal record; commit-plus-abort, duplicate terminal records, duplicate attempt IDs, or mismatched prepared hashes fail closed. Across the repository, the nonterminal prepared set has cardinality `0` or `1`. Multiple records, forks sharing one prior pointer, disconnected generations, conflicting targets, or any competing nonterminal chain raise `POINTER_RECOVERY_DIVERGENCE`; recovery never chooses by mtime, filename, directory order, or highest generation.

For the sole valid prepared record lacking terminal evidence:

- If `current.json` exactly equals the prepared target bytes/hash and its `activation_attempt_id` matches, validate the target again and write durable `activation_committed.json` with `recovered=true`; never rewrite the pointer.
- If `current.json` exactly equals the prepared prior bytes/hash, write durable `activation_aborted.json` with schema `activation_aborted/v1`, attempt ID, prepared-record hash, prior pointer hash, observed pointer hash, abort timestamp, `recovered=true`, and abort-record SHA-256; leave the pointer unchanged.
- Any other pointer bytes, hash, generation, or attempt ID fail closed as `POINTER_RECOVERY_DIVERGENCE`. No new activation, rollback, export, or reader fallback may proceed until independently remediated.

`attempt.json` fixes attempt ID, candidate release identity, prior pointer hash/generation, requested scope, required-provider/work-item quorum, cutoff, and adapter pins. Checkpoints store last hash-verified work transition. `failure.json` stores phase, typed exception, timestamps, artifact hashes, terminal accounting, checkpoints, target manifest, and observed pointer. Pre-replacement failures leave authority unchanged. A crash after replacement is not reported as failure or success until the deterministic recovery rule durably commits or aborts it.

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
- Deleting releases at or above the floor is outside V8 and forbidden.

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

The subsequent implementation phase must first reproduce, diagnose, and prefer fixes for these five inherited full-suite failures recorded by the V7 plan:

1. `tests/test_extract_lessons.py::test_extract_lessons_fails_closed_for_malformed_store_and_lock_contention`
2. `tests/test_market_release_gates.py::test_release_gate_replay_uses_supplied_durable_ledger`
3. `tests/test_market_release_gates.py::test_downstream_release_failure_does_not_consume_lifecycle_receipt`
4. `tests/test_market_release_gates.py::test_dry_run_validation_does_not_consume_lifecycle_receipt`
5. `tests/test_vci_updater_validation_write_blocker.py::TestCombinedValidationWriteBlocker::test_write_proceeds_when_combined_valid`

No failure is automatically grandfathered. If a failure is caused or exposed by V8 work, fix it. A baseline exception is allowed only for failures proven pre-existing, unrelated to every V8 changed path and execution flow, still reproducible before and after V8 implementation, and independently approved by L3.

The only permitted deferred exception path is `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json`.

Exact `baseline_exception/v1` fields:

| Field | Contract |
|---|---|
| `schema_version` | `baseline_exception/v1`. |
| `gate` | Exactly `macro_micro_data_v8_implementation`; the plan gate is forbidden here. |
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

This plan phase does not create, edit, approve, or pre-populate `macro_micro_data_v8_plan` in `.ly_state/session/phase_gates.json`. Only a fresh independent Role 20 plan audit may write that plan-gate record with actual identities and verdict.

The subsequent L2 OpenCode Implementation Phase uses the distinct gate `macro_micro_data_v8_implementation`. Its implementation report, baseline exception, independent L3 implementation audit, and eventual gate record must bind to that exact name. They must not reuse, replace, amend, or overwrite `macro_micro_data_v8_plan` or its approval history.

Each future gate record must contain concrete `phase_name`, timestamp, L2/L3 session and role identities, literal `l2_completed=true`, a concrete nonempty `l3_session_key` for the independent approving L3 session, audit path, bracketed verdict, SOD booleans, exact repo-local role/skill evidence, and forbidden-path scan evidence. Missing or false `l2_completed`, missing/blank/placeholder `l3_session_key`, copied prior-session IDs, missing timestamps, cross-gate evidence, and self-approval are invalid.

The deferred `scripts/sod_gate_enforcer.py` repair keeps direct post-cutoff required-field validation independent of strict-gate discovery. Required gate-control tests remain in `tests/test_strict_repo_local_skill_loading.py`. Implementation and tests never mutate gate metadata. After independent L3 writes `macro_micro_data_v8_implementation`, L1 reruns `python scripts/sod_gate_enforcer.py`.

## 12. Deferred Fixture Inventory

The subsequent implementation phase creates only these V8 contract groups:

- `tests/fixtures/macro_micro/v8/provider_contract.json`
- `tests/fixtures/macro_micro/v8/vci/request_contract.json`
- Three exact raw statement envelope fixtures: `income_statement_raw.json`, `balance_sheet_raw.json`, and `cash_flow_raw.json`.
- Six deterministic statement-slice fixtures named in the VCI table above.
- `tests/fixtures/macro_micro/v8/vci/ratios_raw.json`
- `tests/fixtures/macro_micro/v8/vci/ratios_year_expected.json`
- `tests/fixtures/macro_micro/v8/vci/ratios_quarter_expected.json`
- `tests/fixtures/macro_micro/v8/vci/ratios_contract.json`
- `tests/fixtures/macro_micro/v8/world_bank/cpi_page_1.json`
- `tests/fixtures/macro_micro/v8/world_bank/gdp_growth_page_1.json`
- `tests/fixtures/macro_micro/v8/world_bank/m2_growth_page_1.json`
- `tests/fixtures/macro_micro/v8/yahoo/usdvnd_chart.json`
- Four exact SBV article/PDF/contract/expected-row fixtures named above.
- Two exact reconciliation fixtures named above.
- `tests/fixtures/macro_micro/v8/serialization/canonical_json_cases.json`
- `tests/fixtures/macro_micro/v8/forecast/classification_cases.json`
- `tests/fixtures/macro_micro/v8/pit/acceptance_trail.json`
- `tests/fixtures/macro_micro/v8/pointer/genesis_current.json`

Every fixture is immutable UTF-8 or exact binary evidence with a SHA-256 recorded in `provider_contract.json` or its local contract. Adapter constants must equal fixture literals. Tests use fixtures, not live network.

## 13. Deferred Test and PIT Acceptance Trail

### Test Ownership

- `tests/test_fetch_financial_statements.py`: exactly four VCI transports, eight logical outputs, three dual-branch statement envelopes, exact `RawReceiptV1` schema, acquisition uniqueness, raw-body and metadata-plus-body hashes, strict raw ratio partition, deterministic locators, replay, and no row truncation.
- `tests/test_macro_pipeline.py`: World Bank pagination, Yahoo envelope, SBV selectors/title/date/attachment/hash/PDF table, date-only availability, and append-only macro revisions.
- `tests/test_financial_loader.py`: pointer-only Actual reads, full metric IDs, source-aware streams, reconciliation cutoffs, and Forecast rejection.
- `tests/test_macro_micro_release.py`: canonical consumer bytes, membership/origin/rematerialization, containment attack cases, required-success quorum, planning-authority hashes, singleton replay/conflict, derived lineage, Forecast/Quarantine, manifest self-exclusion, exclusive pointer lock, prepared/commit/abort recovery-chain rejection, migration, rollback, and PIT invariance.
- `tests/test_macro_micro_acceptance_runner.py`: sole-parent spawn, `shell=False`, direct binary stdout/stderr files, exact return code, fsync-before-hash, byte counts, immutable run IDs, transcript linkage, and Python/PyArrow/Playwright/Chromium pin rejection.
- `tests/test_strict_repo_local_skill_loading.py`: checklist `cp1252` regression, post-cutoff gate-control behavior, literal `l2_completed=true`, and concrete nonempty `l3_session_key` enforcement.

### Exact PIT Trail

`tests/fixtures/macro_micro/v8/pit/acceptance_trail.json` contains ordered receipt, policy, decision, and cutoff events plus expected canonical output bytes/SHA-256 at each cutoff. The exact deferred test is:

`tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable`

The exact executable trail command is:

```powershell
python -m pytest tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable -q
```

It must prove: later receipt, provider revision, policy, reconciliation decision, forecast, rematerialization, or rollback evidence cannot alter consumer bytes returned for an earlier cutoff; repeating the trail is idempotent; every output hash matches the fixture. A rematerialized row changes only `release_id` and `materialized_at`, while preserving `origin_ingested_at`, `revision_id`, eligibility, and expected consumer SHA-256.

## 14. Deferred Implementation Tasks

- [ ] Implement `macro_micro_release.py` structures, schemas, canonical serialization, identity separation, membership/origin validation, revisions, reconciliation, lineage, manifest, pointer, migration, and rollback.
- [ ] Implement VCI four-request acquisition: three dual-branch statement envelopes plus one ratio envelope; remove opaque DataFrame evidence, duplicate period requests, truncation, destructive dedupe, and overwrite publication.
- [ ] Implement exact World Bank, Yahoo, and official SBV article/PDF adapters with immutable receipts and fixture replay.
- [ ] Implement publication-date/timestamp evidence without invented times; use first receipt for date-only availability.
- [ ] Implement forecast-first classification, permanent Quarantine, full metric IDs, and two exact derived formulas.
- [ ] Implement pointer-aware readers, generation-one migration, compatibility export, `activation_prepared`/commit WAL recovery, rollback floor, and attempt ledger.
- [ ] Implement `RawReceiptV1`, path containment/no-follow access, unanimous required-work activation quorum, planning-authority validation, exclusive `current.lock`, and ambiguous-chain rejection.
- [ ] Implement the pinned-runtime acceptance runner and immutable binary transcript procedure.
- [ ] Implement `_configure_utf8_stdio` and the forced-`cp1252` regression.
- [ ] Diagnose and fix the five full-suite failures; use the exact exception contract only if independently warranted.
- [ ] Add every deferred fixture and test above, including the executable PIT trail.
- [ ] Run the future implementation acceptance sequence and preserve hashed evidence.

## 15. Deferred Quantitative Gates

All are release-blocking in the subsequent implementation phase:

- VCI: `4/4` raw transports, `8/8` logical outputs, all three statement envelopes contain both branches, and `41 = 8 + 33 + 0` for the pinned FPT ratio fixture.
- SBV: article and PDF documents pass format-aware structural validation and expected-content checks, one title/date/attachment match, exact two-row tenor table, no fallback extraction.
- Completeness: `100%` work items use one declared mode and end in terminal success or a durable failed attempt.
- Integrity: `100%` raw-body, metadata-plus-body receipt, evidence, planning-authority, manifest, pointer, transcript, and raw Quarantine hashes reproduce.
- Membership/revision: `0` mixed releases, future origins, source-stream collapses, singleton replacements, order ties, or hash tie-breaks; rematerialization changes `0` consumer bytes.
- PIT reconciliation: `100%` selected decisions have all policy/candidate/decision knowledge eligible at cutoff; future evidence changes `0` earlier bytes.
- Forecast leakage: `0` Forecast rows in Silver, Derived, historical loaders, graph, feature, or backtest paths.
- Publication evidence: `0` invented publication times; date-only rows use exact dates plus first-receipt availability.
- Release safety: `0` degraded activations, required-work failures, unsafe/escaping paths, followed reparse points, planning-authority mismatches, manifest self-inventory entries, manifest mutations, unanchored manifests, ambiguous/nonterminal prepared chains after recovery, partial pointer activations, mixed releases, or rollback-floor violations.
- Runtime/transcript: exact CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, Chromium revision `1234` / version `151.0.7922.34`; `100%` child streams, byte counts, exit codes, and transcript hashes captured by the sole parent runner.
- Checklist: simulated `cp1252` subprocess and exact checklist command both exit `0`; UTF-8 output never raises `UnicodeEncodeError`.

Silver and Derived may contain zero rows only when every requested record and exclusion is hash-evidenced and fully accounted for.

## 16. Future L2 Implementation Acceptance

This section is **DEFERRED to the subsequent L2 OpenCode Implementation Phase**. None of these commands is a current plan-audit prerequisite, and none is run while producing this V8 plan.

Acceptance evidence is valid only when `scripts/run_macro_micro_v8_acceptance.py` is the direct parent process. L2 invokes `python scripts/run_macro_micro_v8_acceptance.py --phase l2`; after independent L3 writes valid implementation-gate metadata, L1 invokes `python scripts/run_macro_micro_v8_acceptance.py --phase post-l3`. Manual execution is diagnostic only. The runner's immutable child-command table is this exact combined order; any code, test, fixture, checklist, runner, or enforcer remediation requires a new L2 run ID:

```powershell
python -m pytest tests/test_fetch_financial_statements.py tests/test_macro_pipeline.py tests/test_financial_loader.py tests/test_macro_micro_release.py tests/test_macro_micro_acceptance_runner.py tests/test_strict_repo_local_skill_loading.py -q
python -m pytest tests/test_strict_repo_local_skill_loading.py -q
python -m pytest -q
python .agents/scripts/checklist.py . --skip-performance
python scripts/sod_gate_enforcer.py
```

`--phase l2` runs commands 1-4 sequentially. `--phase post-l3` runs only command 5, requires the accepted L2 transcript hash as input, and verifies the concrete implementation gate has `l2_completed=true` plus a nonempty `l3_session_key`. Commands 1, 2, 4, and 5 must exit `0`; no exception may waive them. Command 3 must exit `0` unless only exact pre-existing unrelated failures remain under the valid, unexpired, independently approved `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json` bound to `macro_micro_data_v8_implementation`.

For each invocation, the runner creates `.ly_state/session/acceptance/macro_micro_data_v8_implementation/<run_id>/` with create-new semantics; `run_id` is UTC `YYYYMMDDTHHMMSSffffffZ_<uuid4hex>`. It freezes repo-root identity, phase, child argv arrays, runtime pins, environment overrides, and the accepted prior transcript hash before spawning. Each child receives `subprocess.Popen(argv, shell=False, cwd=repo_root, stdin=subprocess.DEVNULL, stdout=stdout_handle, stderr=stderr_handle, env=env)`; `env` sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and `PYTHONUNBUFFERED=1`. No shell, pipe, tee, inherited console stream, or wrapper process may stand between runner and child.

Before spawn, the runner opens `command_<nn>/stdout.bin` and `command_<nn>/stderr.bin` in exclusive binary `xb` mode and passes those handles directly to the child. The parent records start/end RFC3339 UTC timestamps, calls `wait()`, captures the exact integer `Popen.returncode`, flushes and `os.fsync()`s both streams, closes them, then hashes their exact post-close bytes with streaming SHA-256. `command_<nn>/result.json` is create-new canonical JSON containing argv, timestamps, exit code, stdout/stderr relative paths, byte counts, lowercase SHA-256 values, environment overrides, and parsed test counts where applicable. Bytes are never decoded, newline-normalized, truncated, or rewritten before size/hash capture.

After all phase commands, the runner writes/fsyncs create-new `transcript.json` containing ordered result-file hashes plus the verified CPython/package/browser metadata, fsyncs the run directory, closes the file, and emits its exact-byte lowercase SHA-256 and byte count to the implementation report. A rerun always uses a new run directory; overwrite, append, log reuse, or mixing result files across run IDs is invalid. The runner exits nonzero for any unexcepted command failure or evidence/hash/runtime mismatch.

The future L2 implementation report records the L2 run ID, exact `transcript.json` path/hash/byte count, every command result, and applicable exception path. After independent L3 writes `macro_micro_data_v8_implementation` metadata, L1 runs the post-L3 phase, records its distinct run ID and transcript hash, and requires command 5 exit `0`.

Future implementation is complete only when all deferred files, schemas, fixtures, tests, and migrations exist; quantitative gates pass; the PIT trail is byte-stable; legacy bytes and prior releases remain unchanged; both acceptance transcripts are hash-bound; the sealed manifest revalidates the exact detailed-plan and approving-audit hashes; and L2 submits without self-audit or approval.

## 17. Current Plan Completion Boundary

Current plan-remediation completion requires only:

- The master and detailed V8 plans map all seven V7 advisory remediations and all eight final deep-audit findings.
- Static document checks verify the new contracts and the detailed plan's exact master-plan SHA-256.
- Only the two current plan artifacts are edited by this task; no audit report is written.
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
- `.ly_state/session/implementation_plan_macro_v7_20260810.md`
- `.ly_state/session/l2_role6_macro_micro_data_v7_plan_20260810.md`
- `.ly_state/session/v7_advisory_audit_7_remediations.md`
- `src/omega/data/macro_pipeline.py`
- `tests/test_macro_pipeline.py`

No non-repository role or skill source is authoritative for this plan.
