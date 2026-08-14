# Macro News Pipeline v8 Implementation Plan

## 1. Planning Boundary

- Date: `2026-08-13`.
- Artifact: `.ly_state/session/implementation_plan_macro_news_v8.md`.
- Parsed role frontmatter: `name=planning-architect`, `role_id=26`, `tier=3`, `platform=Codex`.
- Declared repo-local skills: `plan-writing`, `architecture`, `database-design`, `api-patterns`.
- SoD boundary: L3 planning only; no production implementation, test implementation, audit, approval, verdict, or gate decision.
- This revision addresses only the two blockers in `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v7_reaudit_20260813.md`; every unaffected v7 contract remains binding.
- Only this plan is written. Existing unrelated worktree changes remain untouched.
- Runtime remains a bounded one-shot CLI. No timer, scheduler, daemon, queue, service, or background poller.

## 2. Goal

1. Ingest the official SBV overnight VND interbank rate through an explicit WAF-capable Playwright transport with fixture-backed publication and revision evidence.
2. Replace the Yahoo `usd_vnd` default with the official SBV central VND-per-USD rate; never label Yahoo or Vietcombank data as SBV.
3. Bind VCI news ingestion to pinned `vnstock==4.0.4`: one supported call per ticker, then local filtering, sorting, dedupe, and caps.
4. Keep `.ly_state` output-only; require an explicit durable vnstock universe.
5. Preserve per-ticker vnstock provenance in physical raw identity.
6. Hash the exact serialized LLM HTTP body into mandatory `request_sha256`; semantic duplicates share extraction while retaining distinct provenance links.
7. Exclude receipt time from revision identity; preserve the immutable first receipt for PIT availability.

## 3. v7 Audit Blocker Remediation Matrix

| Blocker | Binding v8 contract | Acceptance evidence |
|---|---|---|
| Dynamic shell bytes were incorrectly bound to the stable SBV article hash | Navigation `Response.body()` is transport/rejection evidence only and is never hashed. Select the one registry-declared article container, obtain its `outerHTML`, encode it once as UTF-8 `article_fragment_bytes`, then fixture, hash, parse, and bind revisions only to those fragment bytes. | Two different full navigation bodies containing the identical selected fragment produce the same fragment SHA-256 and revision. A one-byte selected-fragment change fails the registry check and creates no accepted row. |
| `NgayBatDau` civil date was derived without an explicit Vietnam timezone conversion | Normalize `NgayBatDau`, `NgayKetThuc`, and `NgayBanHanh` as `Asia/Ho_Chi_Minh` civil dates before calling `.date()`. Offset-bearing instants are converted with `ZoneInfo('Asia/Ho_Chi_Minh')`; date-only values are already Vietnam civil dates; naive datetimes are rejected. | Regression proves `2026-08-12T17:00:00Z` normalizes to `2026-08-13`, and range/order/source evidence use the normalized civil dates. |

Every v7 contract not changed by these two bindings remains retained in this self-contained plan.

## 4. Non-Negotiable Runtime Boundaries

- `.ly_state` is operational output only: run manifests, evidence, and audit artifacts.
- Runtime code must not read `.ly_state` as a source registry, universe, cache authority, fallback, checkpoint, or configuration input.
- Require `--vnstock-universe <path>` with no default. Accept only a validated regular JSON file outside `.ly_state`; allow a reviewed `config/universes/` snapshot only when explicitly passed.
- Sole universe authority: the exact bytes of the resolved file explicitly named by `--vnstock-universe`; no repository filename, L2 artifact, or generated fallback is implicitly selected.
- Reject direct, symlink, junction, or resolved paths under `.ly_state` before package import or network access.
- Never derive membership from L2 session state, prior manifests, Parquet, process cache, environment fallback, hard-coded tickers, or live provider discovery.
- Pass the already-validated universe bytes/snapshot onward. Do not reopen or rediscover the input later.
- Persist raw macro/news data before any LLM request. LLM failure cannot roll back or rewrite valid raw data.
- Planning, L2, and audit files listed as evidence below are never runtime inputs.

## 5. Target Data Flow

```text
explicit universe JSON + reviewed source contracts
        |
        v
pre-network validation
        |
        +---- vnstock VCI: one supported call per ticker
        +---- news/research adapters
        +---- SBV browser navigation: interbank article + context-session PDF
        +---- same SBV browser context: central-rate bootstrap + structured-content API
        |
        v
raw atomic stores
  data/macro_news.parquet
  data/macro_indicators.parquet
        |
        v
shared alpha LLM resolver
        |
        v
exact body_bytes + request_sha256
        |
        v
data/macro_news_llm.parquet
data/macro_news_llm_links.parquet
        |
        v
.ly_state/session/... run evidence (output only)
```

## 6. Durable Vnstock Identity

- Preserve the strict `UniverseSnapshot` schema, normalized uppercase ticker, explicit exchange, validity interval, member uniqueness, and exact input-byte SHA-256.
- Keep article/revision identity content-level.
- Compute `provenance_id` from `source_id`, `origin_ticker`, and `origin_exchange`.
- Compute physical `raw_record_id` from `revision_id` plus `provenance_id`.
- Retain `origin_ticker` and `origin_exchange` on every VCI row and error record.
- URL/content dedupe must never erase another ticker observation.
- The same story for `AAA` and `BBB` produces one article/revision identity, two provenance identities, two raw identities, and two physical raw rows.

## 7. Pinned `vnstock==4.0.4` Contract

- Keep `vnstock==4.0.4` pinned.
- For each validated member, instantiate `Company(symbol=ticker, source=VCI)`; call `.news()` with no arguments.
- Perform exactly one provider call per ticker per run. No cursor loop, page loop, implicit refresh, or pagination retry.
- Remove `cursor`, `limit`, `sort`, `max_pages`, `_fetch_page(..., cursor)`, and `frame.attrs.pagination.next_cursor` behavior from implementation, registry semantics, and tests.
- Preserve the subprocess timeout boundary only if still needed to bound the synchronous call; pass only `ticker` to the worker.
- Require a `DataFrame`, enforce `news_title` and `public_date`, bound returned memory, normalize timestamps to aware UTC.
- Filter locally to `cutoff <= published_at <= as_of` and `published_at + source_delay <= as_of`.
- Normalize all successful rows before selection. Sort locally by `(published_at DESC, source_record_id ASC, canonical_url ASC, origin_ticker ASC, origin_exchange ASC)` with explicit null-safe string keys.
- Deduplicate only exact physical `raw_record_id` duplicates. Apply the global `max_items` cap after deterministic sorting, never in provider order.
- Keep failures ticker-scoped; one ticker failure does not discard successful records from another ticker.
- Document the result as a bounded provider snapshot, not a complete paginated historical crawl.

## 8. SBV Interbank Interest Contract

### 8.1 Series and Source Registry

- Indicator: `interbank_rate`.
- Provider: State Bank of Vietnam (`SBV`).
- Measure: VND average interbank interest rate, tenor `Qua đêm` (overnight), unit `%/year`.
- Emit only overnight. Validate other tenors as table-shape anchors; do not map them to `interbank_rate`.
- Emit one record per reviewed weekly report. Set `observation_date` to the covered period end (`2026-07-31` for the initial fixture); preserve period start/end as source evidence. Do not synthesize daily rows.
- Add durable `config/sbv_interbank_sources.json` with strict schema and explicit reviewed documents only.
- Initial article: `https://www.sbv.gov.vn/vi/w/di%E1%BB%85n-bi%E1%BA%BFn-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-ngo%E1%BA%A1i-t%E1%BB%87-v%C3%A0-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-li%C3%AAn-ng%C3%A2n-h%C3%A0ng-tu%E1%BA%A7n-t%E1%BB%AB-27-31.7.2026`.
- Initial PDF: `https://www.sbv.gov.vn/documents/20117/0/27-31.7.2026.pdf/b1920a14-5195-3d01-e326-af8ac4ee2d80?t=1785916376970`.
- Registry evidence: publication date `2026-08-05`; observation range `2026-07-27..2026-07-31`; allowed hosts; expected document type; canonical article-fragment and PDF fixture byte counts/SHA-256 values. Full response bytes are never hashed or registered.
- Runtime performs no web search, listing discovery, `.ly_state` lookup, or session-state fallback. New documents require reviewed registry entries and fixtures.

### 8.2 WAF-Capable Browser Transport

- Direct HTTP acquisition is not viable for this source: the observed article request returned a `244`-byte `Request Rejected` body. The SBV-interest adapter must not use bare `requests.get`, `urllib`, or a generic HTTP fallback for the article or PDF.
- One macro fetch launches at most one headless Chromium process and one non-persistent Playwright `BrowserContext` for both official SBV sources. Persist no browser profile, cookies, cache, downloads, or storage state.
- Interest article acquisition is binding and ordered:
  1. Open a fresh page in that context and navigate to the exact registry article URL with `page.goto(..., wait_until='domcontentloaded')`.
  2. Require a non-null navigation response, HTTP `200`, allowed final HTTPS host/path, at most `3` redirects, expected HTML MIME, completion within `30` seconds, and full navigation body bounds of `1 KiB..2 MiB`.
  3. Read `full_response_bytes = navigation_response.body()` only to detect empty/truncated bodies, `Request Rejected`, challenge/interstitial markers, invalid MIME, and transport bounds. Record at most status, final URL, MIME, redirect count, and byte count as sanitized diagnostics. Never hash, fixture, persist, parse, cache, or bind identity/revision to `full_response_bytes`.
  4. Wait for the exact `article_fragment_selector` declared by the registry. Require exactly one match. Obtain that element's `outerHTML` string, encode it exactly once with UTF-8 as `article_fragment_bytes`, enforce `1 KiB..512 KiB`, and compare its byte count/SHA-256 with `article_fragment_byte_count` and `article_fragment_sha256`.
  5. Parse only `article_fragment_bytes` for canonical article fields and the attachment link. Do not parse/hash `full_response_bytes`; do not use `page.content()`; do not silently switch selectors.
  6. Resolve the single reviewed attachment from the validated fragment. Fetch it with `context.request.get(...)` using the final article URL as `Referer`, `max_redirects=3`, `max_retries=0`, and a `30`-second timeout so the same browser-context cookie jar/session is reused.
  7. Require PDF HTTP `200`, allowed final HTTPS host/path, PDF MIME, `%PDF-` signature, size at most `8 MiB`, registry URL agreement, and declared content SHA-256 before parsing.
- Full-page shell variance is expected and non-semantic. Equal `article_fragment_bytes` plus equal PDF/source fields reuse the same revision even when `full_response_bytes` differs. Selected-fragment drift fails closed before parsing or persistence.
- Perform one acquisition attempt per registry entry. No unbounded retry, alternate host, search, mirror, direct-HTTP downgrade, stale-byte fallback, or raw-response hash fallback.
- Run SBV interest and SBV central-rate acquisition in separate source-scoped `try` blocks inside the shared context. Interest failure must not suppress a central-rate attempt; central-rate failure must not discard valid interest rows.
- Close every page in its `finally`; close the context, browser, and Playwright runtime in the outer `finally`. Browser launch/context failure yields zero rows for both SBV sources while independent providers continue; all-provider-empty still fails.

### 8.3 Canonical Article Fragment/PDF Parser

- Initial `article_fragment_selector`: `div.journal-content-article[data-analytics-asset-type=web-content]`.
- `#print-content` is not a silent runtime fallback. It may be used only by a future separately reviewed registry entry with its own selector, exact fragment fixture, byte count, and SHA-256.
- Page-level title selector `h1.title-page.detail` and publication selector `time.author-time[datetime]` may be checked as transport metadata, but full-page DOM/shell bytes never become canonical article content.
- Attachment selector inside the parsed fragment: `a[download]`; resolve exactly one allowed-host HTTPS URL agreeing with the registry.
- Frozen canonical fragment fixture: `sbv_interbank_article_fragment_20260805.html`, `53401` UTF-8 bytes; SHA-256 `578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234`.
- Frozen PDF fixture: `215439` bytes; SHA-256 `b003b92e4795cbd70da5d7eb8ae4a089b1436e2df14c575765f1fb442380f475`.
- Registry field names must be unambiguous: `article_fragment_selector`, `article_fragment_byte_count`, `article_fragment_sha256`, `pdf_byte_count`, and `pdf_sha256`. Reject ambiguous legacy names such as `article_byte_count` or `article_sha256`; no full-response hash may be computed or stored.
- Pin `pypdf==6.15.0`; allow at most `32` PDF pages and `1 MiB` extracted text; reject encrypted, malformed, empty, or excessive documents.
- Validate expected tenors: overnight `2.65`, 1 week `4.53`, 2 weeks `5.72`, 1 month `6.70`, 3 months `7.53`, 6 months `7.59`, 9 months null. Emit only overnight.
- Require registry publication date, covered observation range, tenor labels, numeric format, canonical fragment attachment identity, and PDF identity to agree with fixtures.

### 8.4 PIT, Revision, Failure

- Date-only publication evidence remains date-only. Never invent an SBV publication clock time.
- Persist `source_published_on` and immutable `first_receipt_at` when the exact revision is first acquired.
- Define conservative `published_at = first_receipt_at` when SBV supplies only a publication date. Validate that the receipt is not earlier than `source_published_on`; never invent a provider time.
- Define `available_at` as the first tradable session strictly after `published_at + configured_source_delay`; never use the publication session.
- Revision identity includes canonical article URL, canonical attachment URL, source publication date, observation range, canonical parsed table, `article_fragment_sha256`, and `pdf_sha256`. Exclude full-response byte count and receipt/ingestion time; no full-response hash exists.
- The same revision reuses its immutable first receipt. Dynamic full-page shell changes alone do not change the revision; changed canonical fragment bytes, PDF bytes, or parsed table create a new revision.
- URL-only acquisition/cache keys are forbidden. SBV-interest source identity uses canonical URL plus canonical fragment/PDF SHA-256, never full navigation response SHA-256; any request body must additionally contribute its exact `request_sha256`.
- `_sbv_records(...)` returns `list[dict]`, never `None`; `fetch()` calls `records.extend(self._sbv_records(...))`.
- SBV-interest failure returns zero rows with bounded sanitized logging. No substitute source. Independent providers continue. Whole fetch fails only when every configured provider yields zero rows.
## 9. Official SBV Central Exchange-Rate Contract

### 9.1 Series and Transport

- Indicator: `usd_vnd`.
- Measure: official SBV central VND-per-USD rate (`TyGiaSo`), not a market close, Yahoo quote, Vietcombank quote, or `vnstock.vcb_exchange_rate` value.
- Replace `DEFAULT_URLS[usd_vnd]` Yahoo mapping with an SBV-specific adapter/contract. Remove the Yahoo chart parser path for this indicator.
- Bootstrap URL: `https://sbv.gov.vn/vi/bieu-do-ty-gia-trung-tam`.
- Structured-content API: `https://sbv.gov.vn/o/headless-delivery/v1.0/content-structures/137473/structured-contents`.
- Query parameters: `page`, `pageSize=100`, `sort=datePublished:desc`.
- Bare HTTP is WAF-rejected. Reuse the single bounded non-persistent SBV `BrowserContext`: navigate the exact central-rate bootstrap page, then call `context.request.get(...)` for each structured-content page with the bootstrap URL as `Referer`, `max_redirects=3`, `max_retries=0`, and the same cookie jar. Do not create a second context or make a bare `requests` call.
- Pin `playwright==1.62.0`. Browser installation/runtime provisioning is deployment setup, not an automatic runtime download.
- Apply the Section 8 browser lifecycle and `30`-second request bounds; validate response status/final host/MIME/bytes before JSON parsing. Close the central bootstrap page in its source `finally`; the shared context/browser closes in the outer `finally`.

### 9.2 Envelope, Item, and Civil-Date Validation

- Require envelope fields `page`, `pageSize`, `lastPage`, `totalCount`, and `items` with internally consistent types/ranges.
- Require each item to expose `contentStructureId=137473`, `externalReferenceCode`, `uuid`, `id`, `key`, `datePublished`, `dateModified`, and fields `NgayBatDau`, `NgayKetThuc`, `TyGiaSo`, `TyGiaChu`, `SoVanBan`, `NgayBanHanh`.
- Validate `TyGiaSo` as a finite positive integer VND-per-USD value; do not parse `TyGiaChu` as the numeric authority.
- Verified fixture item: `TyGiaSo=25566`, `SoVanBan=333/TB-NHNN`, `datePublished=2026-08-13T01:26:00Z`, and `NgayBatDau=2026-08-12T17:00:00Z`.
- Normalize each of `NgayBatDau`, `NgayKetThuc`, and `NgayBanHanh` through one strict helper before civil-date extraction:
  1. An offset-bearing or `Z` datetime must parse as an aware instant, convert with `.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))`, then call `.date()`.
  2. An exact date-only `YYYY-MM-DD` value is interpreted directly as an `Asia/Ho_Chi_Minh` civil date; do not attach UTC or shift it.
  3. A naive datetime, malformed value, null, ambiguous format, or out-of-range value fails the item closed.
- Preserve both the raw provider values and normalized `ngay_bat_dau_on`, `ngay_ket_thuc_on`, and `ngay_ban_hanh_on` in canonical source evidence. Require `ngay_bat_dau_on <= ngay_ket_thuc_on`.
- Validate page continuity, unique stable item identities, no conflicting duplicates, deterministic descending source order, item count not exceeding `totalCount`, and terminal-page agreement.
- Apply `cutoff`, `as_of`, and final deterministic ordering locally even though the API requests descending order; date filtering uses the normalized Vietnam civil observation date.

### 9.3 Revision and PIT

- Stable item identity uses the provider identifiers (`contentStructureId`, `externalReferenceCode`, `uuid`, `id`, `key`) after exact consistency checks.
- Canonical item SHA-256 covers provider identifiers, canonicalized provider instants, raw civil-date source values, normalized Vietnam civil dates, document fields, and numeric value.
- Revision identity includes stable item identity, `dateModified`, and canonical item SHA-256. Exclude first receipt and ingestion time.
- Persist immutable `first_receipt_at` per revision; reruns reuse it.
- Parse provider `datePublished` and `dateModified` as aware instants. Reject missing, naive, reversed, or future-beyond-tolerance timestamps.
- Define `published_at = max(datePublished, first_receipt_at)`.
- Define `available_at` as the first tradable session strictly after `published_at + configured_source_delay`; no same-session availability.
- Set `observation_date = ngay_bat_dau_on` only after the `Asia/Ho_Chi_Minh` conversion. Preserve normalized start/end/issuance civil dates plus raw source values. Exact regression: `2026-08-12T17:00:00Z` becomes `2026-08-13`, never `2026-08-12`. Do not expand a range into invented daily rows and do not infer dates from receipt time.
- Browser/API failure returns zero SBV-FX rows, never Yahoo/VCB fallback. Independent macro providers continue; whole fetch fails only if all providers are empty.

## 10. Macro Evidence, Receipt, and Cache Identity

- Extend macro indicator rows with typed nullable source evidence needed to revalidate SBV revisions: `observation_start`, `observation_end`, `source_record_id`, `source_published_on`, `source_published_at`, `source_modified_at`, `source_content_sha256`, `source_article_fragment_sha256`, and `source_attachment_sha256`. For SBV interest, persist the last two explicit hashes; never persist a full-navigation-body hash.
- Keep `ingested_at` as the immutable first successful receipt for the revision. Do not overwrite it on rerun.
- Compute `revision_id` only from source-invariant canonical fields: indicator, value, observation period, stable source identity, provider publication/modification evidence, and source content SHA-256. Exclude `ingested_at`, effective `published_at`, and `available_at`.
- During merge, validate each existing and incoming row against its revision formula, group by `revision_id`, require all source-invariant fields to match, retain the earliest valid `ingested_at`, then recompute receipt-derived `published_at` and `available_at` from that immutable first receipt.
- Stage schema migration and merged output in the destination directory; validate reread bytes before atomic replacement. A malformed legacy row or revision conflict leaves the destination unchanged.
- Existing non-SBV providers may use null source-evidence fields only under explicit provider-specific validation; migration must not invent unavailable evidence.
- Add no macro transport cache in this work. Fetch bounded official sources each run; immutable revision merge supplies idempotence.
- Any future/accompanying transport cache must use either: (a) `request_sha256` of the exact dispatched request representation, or (b) a source-invariant revision key containing stable provider identity plus a source-specific canonical payload SHA-256. For SBV interest, canonical payload evidence is `article_fragment_sha256` plus `pdf_sha256`; navigation `Response.body()` is excluded. URL-only identity is forbidden.
- For HTTP request identity, hash the exact normalized method, final query-bearing URL, representation-affecting headers, and exact body bytes used for dispatch. For bodyless GET, the request-body component is empty bytes. Response identity remains source-specific canonical content, never a dynamic transport shell.
- For VCI SDK calls, do not pretend the hidden HTTP request is known. Add no transport cache; use stable provider fields plus canonical returned payload SHA-256 for revision identity.

## 11. Existing News/Research Contracts Retained

- Dispatch adapters from `config/macro_news_sources.json[adapter]`, never source-name matching.
- Keep `vnstock_vci` and `vcbs_research` required.
- Change `vcbs_research.adapter` to `vcbs`; retain bounded same-host listing/detail discovery, publication evidence, HTML/PDF support, and fail-closed required-source behavior.
- Pin `pypdf`; reject encrypted, oversized, excessive-page, unsupported, or empty VCBS PDFs; recompute content/revision/raw identities after detail enrichment while retaining provenance.
- Keep generic browser fallback disabled. The only planned browser use is the explicit shared official-SBV transport for the reviewed interbank article/PDF and central-rate bootstrap/API.
- Enable additional sources only after endpoint, licensing/usage, timestamp, redirect/host, pagination/bounds, fixture, and empty-result contracts exist. Otherwise retain `enabled=false` with a concrete `disabled_reason`.

## 12. Shared Alpha LLM and Exact Request Identity

- Macro uses `resolve_alpha_llm_config` from `src/omega/core/llm_config.py`; add no macro-only provider, model, URL, key, config path, or precedence.
- Build one request object from the effective provider/model, `temperature=0`, versioned prompt, strict JSON output schema, and bounded normalized semantic fields.
- Exclude URL, source ID, ticker, exchange, universe, raw IDs, timestamps, and ingestion metadata from the semantic request so provenance-only duplicates can reuse extraction.
- Serialize once:

```python
body_bytes = json.dumps(
    request,
    sort_keys=True,
    separators=(',', ':'),
    ensure_ascii=False,
).encode('utf-8')
request_sha256 = hashlib.sha256(body_bytes).hexdigest()
```

- Send those exact bytes via `requests.post(..., data=body_bytes)` with explicit JSON content type. No second serialization and no `json=request` transport.
- Define `endpoint_id` from provider plus canonical chat-completions endpoint; define `extraction_id` from identity version, `request_sha256`, provider, and `endpoint_id`.
- `data/macro_news_llm.parquet` requires `request_sha256` in every extraction row.
- `data/macro_news_llm_links.parquet` links each `(raw_record_id, extraction_id)` and repeats `request_sha256`; provenance-only duplicates retain distinct links to one extraction.
- Validate extraction/link identity, response hash, foreign keys, and matching request hash before network access.
- Legacy cache rows lacking verifiable `request_sha256` or endpoint identity are not reusable. Preserve existing files, fail with bounded rebuild-required evidence, rebuild through staged sidecars only.
- Prompt, model, endpoint, provider, or semantic content changes the extraction identity. Ticker, exchange, universe, URL, or raw ID alone changes only the link.

## 13. Exact Planned File Changes

### `requirements.txt`

- Preserve `vnstock==4.0.4`.
- Change unpinned `pypdf` to `pypdf==6.15.0`.
- Add `playwright==1.62.0`.
- Add no other dependency.

### `config/sbv_interbank_sources.json` (new)

- Store strict versioned reviewed article-fragment/PDF records, observation range, publication date, allowed hosts, `article_fragment_selector`, explicit fragment/PDF byte counts and hashes, parser contract version, and enabled state. Forbid every full-response hash field.
- Reject unknown keys, duplicate source identity, invalid HTTPS hosts, missing hashes, reversed ranges, or unreviewed discovery fields.

### `config/macro_news_sources.json`

- Keep `vnstock_vci` required and pinned to adapter `vnstock`; remove `max_pages` semantics from that entry while retaining a post-normalization `max_items` cap and subprocess timeout/memory bounds.
- Change `vcbs_research.adapter` from `html` to `vcbs`.
- Preserve disabled candidates unless their full evidence contract and fixtures are supplied.

### `src/omega/data/macro_pipeline.py`

- Replace the stub `_sbv_records()` with the reviewed interbank adapter returning a list; use navigation `Response.body()` only for bounded transport/rejection checks, extract/hash/parse the selected article fragment, fetch the PDF through the same `BrowserContext.request`, and extend returned records in `fetch()`.
- Replace Yahoo `usd_vnd` routing/parser behavior with the official SBV central-rate adapter reusing the same bounded SBV browser context.
- Add one shared SBV browser lifecycle plus strict fragment/PDF registry, transport-versus-canonical evidence separation, browser/API envelope/item, bounds, host, redirect, status, MIME, timestamp, Vietnam civil-date, and field validation.
- Extend the macro schema with source evidence required to recompute revision identity and PIT availability.
- Make revision identity source-invariant; preserve earliest immutable receipt; recompute receipt-derived times during validated merge.
- Preserve per-source failure isolation, all-provider-empty failure, file locking, staged validation, and atomic replacement.

### `src/omega/data/macro_news_pipeline.py`

- Change `_vnstock_news_worker` to accept only connection and ticker; call exactly `Company(symbol=ticker, source=VCI).news()`.
- Replace pagination with one bounded call per ticker and deterministic local normalization/filtering/sorting/dedupe/cap.
- Preserve `origin_ticker`, `origin_exchange`, content-level revision identity, provenance identity, and physical raw identity.
- Dispatch adapters by registry adapter ID; retain the fixture-backed VCBS contract and fail-closed migrations.

### `scripts/run_macro_news_pipeline.py`

- Preserve required explicit universe input, pre-import validation, validated-byte handoff, raw-before-LLM order, and sanitized output manifest.
- Add no `.ly_state` input/fallback and no background execution.

### `src/omega/data/macro_news_llm.py`

- Preserve single serialization; require exact `request_sha256`; dispatch identical bytes with `data=body_bytes`.
- Validate extraction/link identities and fail closed on unverifiable legacy cache rows.
- Preserve provenance-invariant extraction plus per-raw-row links and atomic sidecar replacement.

### `src/omega/core/llm_config.py`

- No planned modification when parity tests show macro and alpha resolve the same effective config. Modify only if a failing parity test proves a shared-resolver defect.

### `tests/test_macro_pipeline.py`

- Replace Yahoo-specific `usd_vnd` expectations with official SBV fragment/PDF and central-rate fixtures, same-context transport contracts, dynamic-shell invariance, Vietnam civil-date normalization, PIT, revision, receipt, isolation, migration, and atomicity tests.

### `tests/test_macro_news_pipeline.py`

- Replace cursor pagination tests with pinned API signature, one-call-per-ticker, local filtering/sorting/cap, per-ticker provenance, timeout, error isolation, and rerun tests.
- Retain registry dispatch, VCBS, durable-universe, migration, and raw identity regressions.

### `tests/test_macro_news_llm.py`

- Retain/add captured-body hash, cache hit/miss, semantic reuse, distinct link, corrupt sidecar, raw-preservation, and provider-parity regressions.

### `tests/quant_test_infinite_evolution.py`

- Extend only if needed to prove the existing alpha resolver contract. Otherwise leave unchanged.

### `tests/fixtures/macro/` (new minimal fixtures)

- `sbv_interbank_article_fragment_20260805.html`: exact reviewed selected-container `outerHTML` UTF-8 bytes.
- `sbv_interbank_response_shell_a.html` and `sbv_interbank_response_shell_b.html`: minimal transport fixtures with different shell bytes and the identical canonical article fragment. Do not hash these full-response fixtures.
- `sbv_interbank_20260727_20260731.pdf`: exact reviewed attachment bytes.
- `sbv_central_rate_bootstrap.html`: minimal sanitized bootstrap contract fixture.
- `sbv_central_rate_page_1.json`: structured-content envelope containing the verified `25566` item and `NgayBatDau=2026-08-12T17:00:00Z` regression value.

No production file outside this list is planned.

## 14. Ordered Implementation Sequence

### Stage 1 - Freeze Contracts

1. Add dependency pins, the strict fragment/PDF registry, and immutable canonical fixtures with asserted fragment/PDF byte counts and SHA-256; define full-response evidence as non-canonical.
2. Add failing macro tests for the exact SBV browser lifecycle, two different navigation bodies with one identical selected fragment, selected-fragment drift rejection, same-context PDF request, central-rate Vietnam civil-date normalization, PIT, revision identity, first receipt, failure isolation, and no substitution.
3. Add failing VCI tests proving the exact zero-argument `news()` call, one call per ticker, deterministic local bounds, and per-ticker provenance.
4. Add failing macro-news LLM tests proving exact posted-byte SHA-256 and provenance-only extraction reuse.

### Stage 2 - Implement Official SBV Sources

5. Extend macro evidence schema and write fail-closed staged migration/merge logic before changing providers.
6. Implement the single bounded SBV browser lifecycle, reviewed registry loader, navigation-response transport validation, exact selected-fragment extraction/hash/parser, same-context PDF acquisition/parser, overnight-only record builder, and `records.extend(...)` integration.
7. Reuse that context for the exact central-rate bootstrap and cookie-sharing API requests; implement validated pagination, strict `Asia/Ho_Chi_Minh` civil-date normalization, central-rate parsing, and official `usd_vnd` records.
8. Remove Yahoo/VCB substitution paths and add source-scoped failure handling.

### Stage 3 - Correct VCI and Retain v5 Contracts

9. Replace worker/adapter cursor behavior with one supported `Company(...).news()` call per ticker.
10. Apply local UTC filtering, canonical normalization, deterministic global sorting/dedupe/cap, and provenance-preserving persistence.
11. Complete adapter-ID dispatch and VCBS detail/PDF behavior without enabling unverified sources.
12. Preserve explicit durable universe validation and raw-first CLI order; add no session-state input.

### Stage 4 - Complete Identity and Verification

13. Bind LLM serialization, `request_sha256`, extraction identity, transport bytes, and link validation to one byte object.
14. Validate legacy raw/cache behavior, locks, staged reread, atomic replacement, and destination preservation on every failure case.
15. Run focused tests, shared-resolver regressions, compile checks, CLI help, prohibited-pattern scans, and `git diff --check`.
16. Inspect the implementation diff for unrelated changes, hidden `.ly_state` reads, unsupported VCI arguments, non-SBV FX substitution, receipt-bound revisions, URL-only caches, full-response hashing, UTC-date-first SBV civil dates, or second LLM serialization.

## 15. Required Test Matrix

### SBV Interbank

- Strict registry accepts only the reviewed article-fragment/PDF identity; unknown keys, ambiguous article hash fields, bad host/scheme/hash/date/range fail before browser launch or network.
- Browser transport navigates the exact article URL and validates full `Response.body()` only for status/MIME/bounds/rejection evidence. It selects exactly one registry-declared container, obtains `outerHTML`, UTF-8 encodes once, and reproduces the `53401`-byte fragment SHA-256 plus the `215439`-byte PDF SHA-256.
- Repeat-fetch regression supplies two distinct full navigation bodies with byte-identical selected fragments. The test computes no full-response hash. Both produce the same `article_fragment_sha256`, parsed record, and revision ID; full-response diagnostics do not enter identity.
- Drift regression changes one selected-fragment byte while keeping URL/PDF/shell valid. Registry validation fails closed before parse/persist. A shell-only change remains accepted without a false revision.
- A fake/stub Playwright contract proves one non-persistent context, exact URLs, shared request client, Referer, redirect/retry/time bounds, and `finally` closure. A `244`-byte `Request Rejected` response, missing/duplicate selector, cross-host redirect, bad status/MIME/signature, encrypted/oversized/excessive-page/empty PDF fails closed.
- Parser consumes only canonical fragment bytes, validates all expected tenor anchors, emits only overnight `2.65`, and records observation period `2026-07-27..2026-07-31` without invented daily rows.
- Date-only publication uses immutable first receipt as `published_at`; availability starts only on the strictly following tradable session after delay.
- Same source revision with a later rerun receipt keeps the first receipt and same revision ID; fragment/PDF/table drift creates a new reviewed revision, while full-page shell drift does not.
- `_sbv_records()` always returns a list; `fetch()` extends it. Interest acquisition/parser failure yields zero rows, never substitutes another source, still attempts central rate in the shared context, and other providers continue.

### SBV Central Rate

- Transport reuses the one bounded SBV `BrowserContext`, visits the exact bootstrap URL, requests exact API URL/parameters through `context.request`, closes the bootstrap page and outer resources, and makes no bare `requests` call to either WAF-protected SBV source.
- Envelope validation covers page continuity, page size, last page, total count, items type, duplicate stable IDs, count/order drift, response bounds, and local cutoff.
- Required provider/item fields are non-null and consistent; `contentStructureId` must equal `137473`.
- Verified fixture emits numeric `usd_vnd=25566`, retains `333/TB-NHNN`, and parses `2026-08-13T01:26:00Z`.
- Civil-date regression converts each offset-bearing `NgayBatDau`, `NgayKetThuc`, and `NgayBanHanh` instant to `ZoneInfo('Asia/Ho_Chi_Minh')` before `.date()`. Specifically, `NgayBatDau=2026-08-12T17:00:00Z` yields `observation_date=2026-08-13`; UTC-date-first behavior fails.
- Date-only civil values remain unchanged; naive datetimes, malformed offsets, reversed normalized ranges, or missing normalized issuance dates fail closed. Raw values and normalized Vietnam dates remain in canonical evidence.
- Yahoo `USDVND=X`, Vietcombank, and `vcb_exchange_rate` are rejected as SBV substitutes.
- Revision changes on `dateModified` or canonical item content, including normalized Vietnam civil dates, not receipt time. Later rerun retains first receipt.
- `published_at=max(datePublished, first_receipt_at)`; availability begins on the strictly following tradable session after delay.
- API/browser failure yields zero FX rows while independent providers continue; all-provider-empty still fails.

### VCI `vnstock==4.0.4`

- Spy/fake `Company` proves constructor `(symbol=ticker, source='VCI')` and exactly one `.news()` call with no arguments per ticker.
- No cursor, limit, sort, page count, or `frame.attrs.pagination` behavior remains.
- Missing/invalid `DataFrame`, required columns, timestamps, oversized memory, timeout, and provider exception are bounded ticker-scoped errors.
- Unsorted input with before-cutoff, after-as-of, and delayed-unavailable rows is filtered and sorted locally before the global cap.
- Provider row order does not change selected records or output order.
- Same story from `AAA` and `BBB` produces two raw rows with distinct provenance/raw IDs; rerun adds none.

### Identity, Cache, Atomicity

- Macro revision formula excludes receipt/ingestion time and validates all stored source-invariant evidence.
- Merge selects earliest valid receipt for a repeated revision, recomputes receipt-derived times, rejects conflicting source evidence, and preserves destination on failure.
- URL-only cache identity is absent. Any HTTP cache test proves exact request SHA-256 or stable provider identity plus source-specific canonical payload SHA-256; SBV-interest tests explicitly reject full-navigation-body hashing.
- Captured LLM HTTP bytes hash to persisted mandatory `request_sha256`; `data=body_bytes` sends those identical bytes.
- Semantic input/provider/model/prompt/endpoint changes extraction ID; ticker/exchange/universe/URL/raw ID alone reuses extraction and creates distinct valid links.
- Corrupt or unverifiable legacy rows fail before network/replacement; LLM failure leaves raw stores valid and unchanged.

### Retained Contracts

- Explicit universe missing, malformed, inactive, future, duplicate, direct/resolved `.ly_state`, or hidden fallback fails before import/network.
- Registry dispatch uses adapter ID; VCBS validates timestamp, host, HTML/PDF detail, bounds, enrichment identity, and required-source failure.
- Macro and alpha receive equal sanitized effective LLM config under supported precedence cases; no secret reaches logs or manifests.

## 16. Verification Commands

Run after L2 implementation, from `C:\Users\GHC\repos\OMEGA_QUANT`:

```powershell
pytest -q tests/test_macro_pipeline.py tests/test_macro_news_pipeline.py tests/test_macro_news_llm.py
pytest -q tests/quant_test_infinite_evolution.py -k 'llm and config'
python -m compileall src/omega/data/macro_pipeline.py src/omega/data/macro_news_pipeline.py src/omega/data/macro_news_llm.py src/omega/core/llm_config.py scripts/run_macro_news_pipeline.py
python scripts/run_macro_news_pipeline.py --help
rg -n 'news\([^)]*(cursor|limit|sort)|attrs.*pagination|max_pages' src/omega/data/macro_news_pipeline.py tests/test_macro_news_pipeline.py config/macro_news_sources.json
rg -n 'USDVND=X|query1\.finance\.yahoo|vcb_exchange_rate' src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py
rg -n 'requests\.post\([^\n]*json=|json=request' src/omega/data/macro_news_llm.py
rg -n 'separators=.*sort_keys|encode.*utf-8|request_sha256|data=body_bytes' src/omega/data/macro_news_llm.py tests/test_macro_news_llm.py
rg -n 'requests\.get|urllib|page\.content\(' src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py
rg -n 'article_fragment_(selector|byte_count|sha256)|outerHTML|full_response_bytes' src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py config/sbv_interbank_sources.json
rg -n 'sha256\([^)]*full_response|hashlib[^\n]*full_response|full_response[^\n]*sha256' src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py config/sbv_interbank_sources.json
rg -n 'Asia/Ho_Chi_Minh|ZoneInfo|NgayBatDau|NgayKetThuc|NgayBanHanh' src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py
git diff --check -- requirements.txt config/sbv_interbank_sources.json config/macro_news_sources.json src/omega/data/macro_pipeline.py src/omega/data/macro_news_pipeline.py scripts/run_macro_news_pipeline.py src/omega/data/macro_news_llm.py src/omega/core/llm_config.py tests/test_macro_pipeline.py tests/test_macro_news_pipeline.py tests/test_macro_news_llm.py tests/quant_test_infinite_evolution.py tests/fixtures/macro
```

- The first three prohibited-pattern scans must return no implementation matches after expected test names/messages are removed or renamed.
- Review the SBV scans manually: explicit rejection tests/messages are allowed; production bare HTTP and `page.content()` remain forbidden. `Response.body()` may appear only in bounded transport validation and must never be hashed, parsed, fixtured as canonical content, cached, or used for revision identity.
- The fragment scan must show explicit canonical-fragment fields and tests proving shell-only variance is revision-invariant. The full-response-hash scan must return no matches. The timezone scan must show `ZoneInfo('Asia/Ho_Chi_Minh')` conversion before `.date()` plus the `2026-08-12T17:00:00Z` regression.
- Review any `.ly_state` code match manually: rejection/output-manifest logic is allowed; opening it as runtime input is not.
- A bounded live source smoke check is optional after fixture tests. It uses explicit temporary outputs, never canonical Parquet, and never mutates source registries.

## 17. Completion Criteria

- Plan identity is v8 in both title and artifact path.
- Official SBV interest and central-rate contracts share one bounded WAF-capable Playwright context, are fixture-backed, PIT-safe, revision-safe, and source-isolated.
- SBV interest full navigation bytes are transport evidence only. Canonical article identity, fixture, parser, and revision use the exact selected-container `outerHTML` UTF-8 bytes; the PDF comes from the same context request client. No bare-HTTP downgrade exists.
- `usd_vnd` means official SBV central rate; no Yahoo or Vietcombank substitution remains. `NgayBatDau`, `NgayKetThuc`, and `NgayBanHanh` normalize through `Asia/Ho_Chi_Minh` before civil-date extraction.
- Pinned VCI integration calls only supported `vnstock==4.0.4` API and makes one bounded call per ticker.
- Local VCI filtering/sorting/cap is deterministic and retains ticker/exchange provenance.
- `.ly_state` remains output-only; L2 session state is never a runtime input.
- Receipt time is excluded from revision identity; reruns retain immutable first receipt.
- No URL-only cache identity exists; exact request SHA-256 or source-invariant canonical fragment/PDF identity is mandatory. Dynamic full-page shell bytes never create a source revision.
- LLM serializer uses valid `separators=(',', ':')` and `.encode('utf-8')`; `request_sha256` equals the exact `body_bytes` sent; provenance-only duplicates share extraction and retain distinct links.
- Raw persistence precedes LLM work; migration/cache/source failures preserve existing destinations.
- Focused tests, compile checks, CLI help, pattern scans, and diff checks pass.

## 18. Deliberate Simplifications

- Keep Parquet and current sidecars; add no DB, API, scheduler, or service.
- Use an explicit reviewed SBV interbank registry; add no crawler or discovery engine.
- Use one non-persistent Playwright context only for the two reviewed WAF-protected official SBV sources; add no second context, generic browser fallback, or direct-HTTP downgrade.
- Use one VCI snapshot call per ticker; make no unsupported historical-completeness claim.
- Keep unverified sources disabled; invent no endpoints or publication times.
- Modify the shared LLM resolver only when a parity test proves a defect.

## 19. Exact Repo-Local Files Read

Role and authoritative instructions, in loading order:

- `.agents/agent/planning-architect.md` - read first; frontmatter parsed as `name=planning-architect`, `role_id=26`, `tier=3`, `platform=Codex`, skills `[plan-writing, architecture, database-design, api-patterns]`, `sod_boundary=planning-only, non-audit, no production code`.
- `.agents/AGENTS.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`

Task evidence and plan inputs:

- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v7_reaudit_20260813.md`
- `.ly_state/session/implementation_plan_macro_news_v7.md`
- `.ly_state/session/implementation_plan_macro_news_v8.md` - authored, then reread for validation.

The repository-root `AGENTS.md` redirect was supplied verbatim in the task context; it was not reopened from disk. `.ly_state/AGENTS.md` and `.ly_state/session/AGENTS.md` were existence-checked and absent; no content was read. No other repo-local file content was read for this revision.

## 20. Forbidden Path Scan Result

Metadata-only `Test-Path` scan:

- `C:\Users\GHC\repos\OMEGA_QUANT\.gemini\antigravity-ide\scratch\ag-kit`: absent.
- `C:\Users\GHC\.openclaw\skills`: exists; content not opened.
- `C:\Users\GHC\.agents`: exists; content not opened.
- `C:\Users\GHC\.codex\memories`: exists; content not opened.
- Role authority came only from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`.
- Skill authority came only from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.
- Result: zero forbidden filesystem content reads, zero forbidden authoritative reliance, zero forbidden writes. No Antigravity scratch, OpenClaw skill, user-level `.agents`, or Codex memory file supplied role/skill authority or plan content.

## 21. Non-Audit Handoff

- L1 may review this plan and dispatch file-scoped implementation to L2.
- Independent audit, approval, verdict, and phase-gate decisions remain outside role 26 and outside this artifact.
