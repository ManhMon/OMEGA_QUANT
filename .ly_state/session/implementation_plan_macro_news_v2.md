# Macro News Pipeline v2 Implementation Plan

## 1. Planning status and boundary

- Date: `2026-08-12`.
- Role frontmatter parsed: `name=planning-architect`, `role_id=26`, `tier=3`, `platform=Codex`, skills `plan-writing`, `architecture`, `database-design`, `api-patterns`.
- SoD boundary: planning-only, non-audit, no production code or tests.
- Remediation status: `READY_FOR_INDEPENDENT_REAUDIT`. The prior role-21 verdict remains `[NEEDS_FIX]` until a new independent audit approves this revision. All required repo-local role and skill sources exist, so the missing-source stop condition is not triggered.
- Artifact: `.ly_state/session/implementation_plan_macro_news_v2.md`.
- Web search was not used. Source expansion below is a validation backlog based on the repository and internal domain knowledge; L2 must not guess live endpoints.
- This session changes only this plan. Implementation, tests, live fetches, dependency installation, and LLM calls are explicitly deferred.

## 2. Goal

Complete the existing macro-news baseline as a two-stage, point-in-time-safe pipeline:

1. Ingest immutable raw news from `vnstock`, VCBS, the current ten-source registry, and every additional reliable source that passes a strict source contract.
2. Persist raw news before any LLM work so provider outages never lose source data.
3. Extract structured macro events with an LLM using the exact effective alpha LLM configuration resolver.
4. Persist versioned extraction results in a separate Parquet sidecar keyed by the exact canonical LLM request and extraction runtime identity.
5. Preserve provenance, publication availability, first observation, and extraction time for auditable research and operational replay.

## 3. Requirement mapping

| User requirement | Planned implementation | Acceptance evidence |
|---|---|---|
| Fetch data from vnstock | Add `VnstockNewsAdapter` using the repository's existing `vnstock.Company(symbol, source="VCI").news(cursor, limit, sort="public_date_desc")` contract | Cursor, schema, cutoff, per-symbol failure, dedupe, and PIT tests |
| Eliminate hidden universe state | Require `--vnstock-universe <versioned-json>`; validate its effective interval before network access; record its exact SHA-256 and effective dates in the manifest and vnstock raw rows | Missing/invalid/out-of-window input fails before network; `.ly_state/session/vci_universe_hsx_hnx.json` is never a runtime fallback |
| Include VCBS and many reliable macro sources | Make `vnstock_vci` and `vcbs_research` required; preserve the current ten sources; add official, multilateral, broker-research, and reputable-media candidates to a validated registry | Every candidate attempted; enabled sources pass fixture and live contract checks; disabled sources record a reason |
| Extract macro news with LLMs | Add deterministic article-level extraction, strict JSON validation, grounded evidence, bounded retry, and a versioned sidecar | Raw ingestion succeeds during LLM failure; only validated outputs persist |
| Use the alpha LLM provider | Move the alpha resolver to shared core code; retain alpha wrappers; macro imports the same resolver and effective config object | Alpha and macro resolver parity tests; no macro-specific provider/model/key variables |
| Write a full plan only | This document contains architecture, schemas, exact file changes, sequence, tests, security, PIT rules, and acceptance criteria | Worktree contains this planning artifact only |

## 4. Repository findings

### 4.1 Existing macro-news baseline

- `src/omega/data/macro_news_pipeline.py` already defines `RSSAdapter`, `ScraperAdapter`, and `MacroNewsPipeline`.
- Current output is `data/macro_news.parquet` with seven columns: `source`, `title`, `summary`, `url`, `published_at`, `available_at`, `ingested_at`.
- Current sources are CafeF, Vietstock, BaoChinhPhu, SBV, VCBS, SSI, VNDirect, VnEconomy, BaoDauTu, and TinNhanhChungKhoan.
- Current PIT rule is `available_at = published_at + 15 minutes` with UTC normalization.
- Current persistence is atomic, but `drop_duplicates("url", keep="last")` can overwrite first-observation provenance.
- Current institutional parser only recognizes a simple `<article><a><time>` shape. It does not support listing/detail traversal, JSON-LD, source-specific metadata, PDFs, JavaScript rendering, revisions, source health, or LLM extraction.
- `data/macro_news.parquet` is absent in this workspace snapshot. Schema-v1 migration remains required because another environment may already have produced it.

### 4.2 Existing vnstock contract

- `src/omega/data/news_aggregator.py` already lazily imports `vnstock.Company` and uses `source="VCI"`.
- The existing page call is `company.news(cursor=cursor, limit=100, sort="public_date_desc")`.
- The next cursor is read from `DataFrame.attrs["pagination"]["next_cursor"]`; repeated cursors are rejected.
- Required columns are currently `news_title` and `public_date`; `news_short_content` is optional.
- Existing sentiment code has a hard-coded `.ly_state/session/vci_universe_hsx_hnx.json` path. That file is workflow state, has no durable lifecycle contract, and is explicitly forbidden as a Macro News Pipeline runtime dependency.
- Macro v2 instead requires an operator-supplied, immutable, versioned universe JSON through the CLI. No implicit path, session-state lookup, hard-coded ticker fallback, or live listing discovery is permitted.
- Existing sentiment ingestion filters bullish/bearish keywords. Macro ingestion must not reuse that filter; the raw layer retains every valid article and the LLM classifies macro relevance.
- Local package inspection found `vnstock==4.0.4`; `requirements.txt` does not declare it.

### 4.3 Alpha LLM configuration

- Alpha resolution currently lives in `scripts/run_hybrid_alpha_evolution.py`.
- Supported providers are `mock` and `openai-compatible`.
- Provider precedence must remain exactly: explicit function/CLI override, external config from `OMEGA_ALPHA_LLM_CONFIG_PATH`, `OMEGA_LLM_PROVIDER`, then auto-detect `openai-compatible` when a key exists or `mock` otherwise.
- Routing-value precedence must remain: external config, shared `OMEGA_LLM_*` environment variables, then existing model default.
- External config is accepted only when it is an existing, canonical, absolute path outside the repository. Invalid input currently produces an empty file config; this behavior must remain covered by regression tests.
- Sanitized effective configuration verified on `2026-08-12`: provider `openai-compatible`, base URL `http://localhost:20128/v1`, model `cx/gpt-5.6-terra`, API key present. No secret value was printed or copied into this plan.

## 5. Target architecture

```text
config/macro_news_sources.json
        |
        v
validated SourceRegistry -----> per-source health and run manifest
        |
        +---- --vnstock-universe <versioned JSON>
        |            |
        |            v
        |     validate schema/effective interval/hash before network
        |            |
        +---- VnstockNewsAdapter receives immutable UniverseSnapshot
        +---- RSSAdapter
        +---- InstitutionalHtmlAdapter
        +---- ResearchDocumentAdapter
        +---- BrowserAdapter, opt-in fallback only
        |
        v
normalize -> article identity -> revision identity -> provenance identity
        |
        v
append immutable raw provenance revisions
        |
        v
data/macro_news.parquet
        |
        +---- build source-invariant canonical request bytes
        +---- compute request_sha256
        +---- select rows missing exact extraction/link identity
        |
        v
shared alpha LLM resolver -> OpenAI-compatible /chat/completions
        |
        v
strict JSON and evidence validator
        |
        v
data/macro_news_llm.parquet       one row per extraction_id
        |
        +---- data/macro_news_llm_links.parquet
              one row per raw_record_id/extraction_id link
        |
        v
source-time view or strict operational-time view
```

### 5.1 Module boundaries

- Ingestion never imports or calls an LLM client.
- Extraction only reads validated raw rows; it never discovers or fetches news URLs.
- The shared LLM resolver imports neither alpha mining nor macro modules.
- No production code reads `.ly_state/session/vci_universe_hsx_hnx.json` or any other implicit session-state universe. The CLI validates its explicit universe argument before importing `vnstock` or opening a network session.
- The vnstock adapter receives an already-validated immutable `UniverseSnapshot`; it cannot discover, default, mutate, or refresh the universe.
- LLM request construction excludes source, ticker, URL, article IDs, and timestamps. Provenance remains in raw rows and the link sidecar rather than affecting reusable content extraction.
- CLI orchestration persists raw data first, then starts extraction.
- An LLM error never rolls back or rewrites the raw store.
- Parquet remains canonical. No database table, HTTP API, queue, worker service, or scheduler is added in v2.

### 5.2 Runtime outputs

- Raw canonical store: `data/macro_news.parquet`.
- LLM extraction store: `data/macro_news_llm.parquet`.
- LLM linkage store: `data/macro_news_llm_links.parquet`.
- Per-run audit manifest: `.ly_state/session/macro_news_runs/<run_id>.json`.
- The manifest records `universe_id`, `universe_schema_version`, exact input-byte `universe_sha256`, `generated_at`, `effective_from`, `effective_to`, ticker count, and per-exchange counts. It does not copy the universe payload.
- No raw article binaries, LLM raw responses, API keys, or authorization headers are persisted.

## 6. Source registry and expansion plan

### 6.1 Registry contract

Add `config/macro_news_sources.json` using the standard-library JSON loader. Each entry contains:

- `source_id`: stable snake-case identifier.
- `display_name` and `tier`: `official`, `multilateral`, `institutional_research`, `reputable_media`, or `aggregator`.
- `kind`: `vnstock`, `rss`, `html`, `pdf_research`, or `browser`.
- `enabled` and `required`.
- `discovery_url`, nullable for vnstock.
- `allowed_hosts`: exact host/subdomain allowlist; VCBS must include `vcbs.com.vn`.
- `adapter`: fixed parser ID, never an arbitrary import string.
- `source_delay_minutes`, default `15` unless source evidence supports another delay.
- `timestamp_policy`: timezone, accepted precision, and date-only handling.
- `max_pages`, `max_items`, `request_interval_seconds`, `timeout_seconds`, `max_response_bytes`.
- `allow_pdf`, `allow_browser_fallback`, and `disabled_reason`.

The registry loader fails closed on duplicate IDs, unknown adapters, invalid URL schemes/hosts, missing required fields, or a disabled required source.

### 6.2 Versioned vnstock universe input

`vnstock_vci` has no implicit universe. Because it is a required source, `scripts/run_macro_news_pipeline.py` requires `--vnstock-universe <path>` on every run. There is no default path, environment fallback, hard-coded ticker list, session lookup, live refresh, or adapter-side discovery. Production code must reject any path inside `.ly_state`; `.ly_state/session/vci_universe_hsx_hnx.json` remains audit evidence only and is never a runtime input.

The CLI reads the file once as exact bytes, computes `universe_sha256 = SHA256(input_bytes)`, then decodes and validates JSON before importing `vnstock`, constructing `requests.Session`, or opening any network connection. Schema version `1` is:

```json
{
  "schema_version": 1,
  "universe_id": "vci_hsx_hnx",
  "universe_version": "2026-08-12",
  "generated_at": "2026-08-12T00:00:00Z",
  "effective_from": "2026-08-12T00:00:00Z",
  "effective_to": null,
  "members": [
    {"ticker": "AAA", "exchange": "HSX"},
    {"ticker": "AAV", "exchange": "HNX"}
  ]
}
```

Validation rules:

- The canonical path must identify an existing regular file explicitly supplied by the operator. Symlink resolution is allowed only to identify and reject `.ly_state`; the loader never searches parent or sibling directories.
- `schema_version` must equal `1`; unknown and missing keys fail closed. `universe_id` and `universe_version` are required bounded stable tokens.
- `generated_at`, `effective_from`, and non-null `effective_to` must be timezone-aware UTC values. The validity interval is half-open: `effective_from <= as_of < effective_to`; null `effective_to` means open-ended.
- `generated_at <= as_of`; a universe produced after the requested historical `as_of` is rejected as PIT-unsafe. `effective_to`, when present, must be greater than `effective_from`.
- `members` must be a non-empty array. Each member has exactly `ticker` and `exchange`; ticker tokens must satisfy `re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", ticker)`, and exchange is exactly `HSX` or `HNX`.
- A ticker may appear once only. Duplicate ticker/exchange rows and the same ticker assigned to two exchanges fail the entire input. Validation returns an immutable, deterministically sorted `UniverseSnapshot`; it never rewrites the source file.
- The manifest records the canonical input name, exact-byte SHA-256, ID, version, generation/effective timestamps, total member count, and per-exchange counts. It does not copy members.

Universe lifecycle is external to this ingestion command. A reviewed producer creates a new immutable, version-named JSON file under a versioned repository path such as `config/universes/` or in a controlled artifact store. Membership or validity changes create a new file and `universe_version`; files are never edited in place. The operator passes the intended snapshot explicitly. Overlapping effective intervals for the same `universe_id` are prohibited by the producer/review process. Adding an automated universe builder is a separate audited scope.

### 6.3 Required and current sources

The first implementation stage preserves the current ten sources and adds vnstock:

| Source ID | Source | Tier | Target adapter |
|---|---|---|---|
| `vnstock_vci` | vnstock VCI company news | aggregator | `VnstockNewsAdapter` |
| `vcbs_research` | `vcbs.com.vn` | institutional_research | listing plus HTML/PDF detail |
| `sbv_news` | State Bank of Vietnam | official | source-specific HTML |
| `baochinhphu_economy` | BaoChinhPhu | official | RSS plus detail HTML |
| `cafef_macro` | CafeF | reputable_media | RSS plus detail HTML |
| `vietstock_macro` | Vietstock | reputable_media | RSS plus detail HTML |
| `ssi_research` | SSI | institutional_research | listing plus HTML/PDF detail |
| `vndirect_research` | VNDirect | institutional_research | listing plus HTML/PDF detail |
| `vneconomy_macro` | VnEconomy | reputable_media | RSS plus detail HTML |
| `baodautu_macro` | BaoDauTu | reputable_media | RSS plus detail HTML |
| `tinnhanhchungkhoan_macro` | TinNhanhChungKhoan | reputable_media | RSS plus detail HTML |

`vnstock_vci` and `vcbs_research` are required. A required-source failure still permits successful raw rows from other sources to be persisted, but the command exits non-zero after writing its manifest.

### 6.4 Additional reliable-source backlog

L2 must attempt validation for every candidate below. A candidate is enabled only after direct endpoint discovery, timestamp validation, allowlist validation, content extraction, a synthetic fixture, and a bounded live smoke pass. No endpoint may be guessed. Historical or renamed government domains must be recorded as disabled until current ownership and publication behavior are confirmed.

**Official Vietnam sources**

- National statistics releases: current statistics-office domain, plus historical `gso.gov.vn` archive if still authoritative.
- Ministry of Finance: `mof.gov.vn`.
- Ministry of Industry and Trade: `moit.gov.vn`.
- Vietnam Customs: `customs.gov.vn`.
- State Securities Commission: `ssc.gov.vn`.
- Vietnam Exchange: `vnx.vn`.
- HOSE: `hsx.vn`.
- HNX: `hnx.vn`.
- Government portal and Prime Minister decisions: `chinhphu.vn` / BaoChinhPhu.
- Ministry of Construction for housing and real-estate policy: `moc.gov.vn`.
- National Assembly economic resolutions: `quochoi.vn`.
- Official tax, treasury, public-debt, and bond-market release portals where stable public listings exist.

**Multilateral sources**

- World Bank Vietnam reports.
- IMF Vietnam Article IV and country releases.
- Asian Development Bank Vietnam outlooks and country reports.
- OECD Vietnam economic material when a stable public feed/listing exists.

**Institutional research sources**

- Vietcap Research.
- MBS Research.
- KBSV Research.
- BSC Research.
- FPTS Research.
- HSC Research.
- Mirae Asset Vietnam Research.
- Yuanta Vietnam Research.
- Maybank Securities Vietnam Research.
- ACBS Research.
- SHS Research.
- DSC Research.
- Kafi Research.
- Other licensed Vietnam broker research portals only after provenance and timestamp checks pass.

**Reputable media sources**

- VnExpress Business.
- VietnamPlus/VNA economics.
- Vietnam News economics.
- Tuoi Tre business/economics.
- Thanh Nien business/economics.
- Nhip Cau Dau Tu.
- Reuters Vietnam/Asia economics only when access and licensing permit automated ingestion.
- Bloomberg Vietnam-related macro coverage only when access and licensing permit automated ingestion.

Social media, anonymous blogs, repost farms, paywall/CAPTCHA bypasses, and sources without verifiable publication provenance are excluded.

### 6.5 Source health semantics

- Status values: `healthy`, `healthy_empty`, `partial`, `failed`, `disabled`.
- `healthy_empty` means the transport and parser contract passed but the requested window had no articles.
- A source transport/parser failure is isolated from every other source.
- A required-source failure is visible in the manifest and command exit code; it does not discard good data.
- Enabled sources require a parser fixture. DOM drift fails the source rather than falling back to permissive extraction that could create false records.

## 7. Adapter contracts

### 7.1 `VnstockNewsAdapter`

- Lazily import `vnstock.Company`. Import failure marks `vnstock_vci` failed with an actionable dependency error.
- Accept only the immutable `UniverseSnapshot` already validated by the CLI. The adapter has no file-loading, fallback, discovery, mutation, or refresh path.
- For each ticker, construct `Company(symbol=ticker, source="VCI")`.
- Call `news(cursor=cursor, limit=100, sort="public_date_desc")` to preserve the repository's existing server-side pagination contract.
- Require `news_title` and `public_date`; accept `news_short_content`, provider URL, provider record ID, and other provenance fields when present.
- Stop at the requested cutoff, `max_pages`, `max_items`, or a null cursor. Reject a repeated cursor.
- Isolate per-symbol failures and continue with the remaining universe.
- Remove sentiment-keyword filtering from this adapter. Every row with valid identity, title, and timestamp reaches the raw store.
- Copy `origin_ticker`, `origin_exchange`, `universe_id`, `universe_version`, exact-byte `universe_sha256`, `universe_generated_at`, `universe_effective_from`, and nullable `universe_effective_to` into each vnstock raw row. These are immutable first-observation provenance fields.
- Prefer the provider record ID, then canonical provider URL, for article identity. When neither exists, derive the article identity from `source_id`, published timestamp, and normalized title. Deliberately exclude ticker so one provider story has one `article_id`; ticker is preserved by `provenance_id` and `raw_record_id`. Do not invent a public URL.
- The same provider story returned for several symbols produces one raw row per ticker provenance. Exact source-invariant request identity may reuse one extraction, but raw rows never collapse for that reason.

### 7.2 `RSSAdapter`

- Retain the standard-library XML approach and bounded repair of bare ampersands.
- Support common RSS and Atom title, link, GUID, summary/content, published, and updated elements.
- Validate both discovery URLs and article URLs against the source allowlist.
- Prefer GUID/source ID, then canonical article URL, for identity.
- A feed summary is enough for a raw record when title and exact timestamp are valid; detail fetching enriches content but is not a prerequisite for preserving the observation.
- Missing or ambiguous timestamps are quarantined, not replaced with fetch time.

### 7.3 `InstitutionalHtmlAdapter`

- Separate discovery-page parsing from detail-page parsing.
- Prefer machine-readable timestamps in this order: JSON-LD `datePublished`/`dateModified`, explicit metadata, `<time datetime>`, then a source-specific visible-date selector.
- Use source-specific selectors for SBV, VCBS, SSI, VNDirect, and every new institutional source. The current generic `<article>` regex remains only a narrow compatibility parser for fixtures that satisfy its exact contract.
- Canonicalize relative URLs, remove fragment/tracking parameters, and validate the final redirected host.
- Preserve title, abstract, body text, report type, publication timestamp, update timestamp, source ID, and discovery provenance.
- A date-only release receives `timestamp_precision=date`; convert it conservatively to the end of that source's publication day in `Asia/Ho_Chi_Minh`, then add the configured source delay. Never map a date-only release to midnight.

### 7.4 `ResearchDocumentAdapter`

- Use the already-declared `pypdf` package for public broker and institution PDFs.
- Download only after listing/detail metadata validates the publication identity and timestamp.
- Require an allowed final host and a compatible PDF response; cap redirects, response bytes, pages, extracted characters, and processing time.
- Trust listing/detail publication time over embedded PDF metadata. Record a mismatch in the run manifest.
- Store normalized bounded text, not raw PDF bytes.
- Reject encrypted, malformed, empty, or image-only documents in v2; record them as unsupported rather than silently producing blank content.

### 7.5 `BrowserAdapter`

- Use the already-declared Playwright dependency only for sources explicitly configured with `allow_browser_fallback=true`.
- Static HTTP parsing remains the default. Browser fallback is for a verified JavaScript-only listing or detail page.
- Allow only configured hosts, bounded navigation, bounded response size, and a single page context per source run.
- Do not perform login, CAPTCHA bypass, arbitrary clicks, or unrestricted downloads.
- Browser failure degrades only that source and must not block raw persistence from other sources.

## 8. Raw data contract

Keep `data/macro_news.parquet` as the canonical raw store. Schema version `2` contains:

| Column | Logical type | Rule |
|---|---|---|
| `schema_version` | int16 | Constant `2` |
| `raw_record_id` | string | Physical primary key: hash of revision plus provenance identity |
| `article_id` | string | Stable provider-story identity; never includes `origin_ticker` |
| `revision_id` | string | Hash of `article_id` and `content_hash` |
| `provenance_id` | string | Hash of source context plus nullable ticker/exchange provenance |
| `content_hash` | string | SHA-256 of canonical title, summary, and body text |
| `story_hash` | string | Normalized-title hash for grouping only |
| `source_id` | string | Stable registry ID |
| `source_name` | string | Human-readable registry name |
| `source_tier` | string | Registry tier enum |
| `source_kind` | string | Adapter kind enum |
| `origin_ticker` | nullable string | vnstock ticker provenance |
| `origin_exchange` | nullable string | `HSX` or `HNX` from the validated snapshot |
| `universe_id` | nullable string | Required for vnstock; null for other adapters |
| `universe_version` | nullable string | Required for vnstock; null for other adapters |
| `universe_sha256` | nullable string | Exact input-byte hash; required for vnstock |
| `universe_generated_at` | nullable UTC timestamp | Snapshot generation time; required for vnstock |
| `universe_effective_from` | nullable UTC timestamp | Inclusive validity start; required for vnstock |
| `universe_effective_to` | nullable UTC timestamp | Exclusive validity end; null means open-ended |
| `source_record_id` | nullable string | Provider GUID/record ID |
| `title` | string | Required, whitespace-normalized |
| `summary` | nullable string | Bounded normalized text |
| `body_text` | nullable string | Bounded normalized article/PDF text |
| `url` | nullable string | Original discovered URL |
| `canonical_url` | nullable string | Safe normalized URL |
| `language` | string | `vi`, `en`, or `unknown` |
| `published_at` | UTC timestamp | Required source publication time |
| `source_updated_at` | nullable UTC timestamp | Explicit source revision time only |
| `timestamp_precision` | string | `second`, `minute`, or `date` |
| `available_at` | UTC timestamp | Earliest trusted public availability |
| `ingested_at` | UTC timestamp | Immutable local first-observation time |
| `raw_timestamp` | string | Original timestamp text/value |
| `payload_sha256` | string | Hash of the exact source payload or SDK row used |
| `adapter_version` | string | Parser contract version |

### 8.1 Identity, deduplication, and revisions

- All identities use versioned canonical JSON with sorted keys, UTF-8, and compact separators before SHA-256. Identity-version changes require a raw schema migration; ad hoc concatenation is forbidden.
- `article_id` identifies the provider story: hash `source_id` plus provider record ID; fallback to canonical URL; final fallback to `source_id`, `published_at`, and normalized title. `origin_ticker`, exchange, universe version, ingestion time, and parser version are excluded.
- `revision_id = SHA256({identity_version, article_id, content_hash})`. Changed canonical content creates a new revision under the same article.
- `provenance_id = SHA256({identity_version, source_id, origin_ticker, origin_exchange})`. Null ticker/exchange represent the single non-vnstock source context. Universe metadata is retained on the first raw observation but does not create duplicate rows when unchanged content is re-observed under a later snapshot.
- `raw_record_id = SHA256({identity_version, revision_id, provenance_id})`. This is the sole physical uniqueness key.
- An already-stored `raw_record_id` is skipped. The first `ingested_at` and first-observation universe fields win permanently.
- The same provider story and content returned for `AAA` and `BBB` has one `article_id`, one `revision_id`, two `provenance_id` values, two `raw_record_id` values, and two raw rows. No ticker provenance is discarded.
- The same `article_id` with different content has a new `revision_id`; each observed provenance gets its own new `raw_record_id`. Existing rows are never overwritten.
- Cross-source versions of the same story remain separate records because publication time, wording, and provenance differ.
- `story_hash` is only a grouping aid. It cannot delete or replace records.
- Cardinality is explicit: `article_id 1:N revision_id`; `revision_id 1:N raw_record_id`. LLM reuse occurs only through the separate request/extraction/link contract in section 10 and never changes raw cardinality.

### 8.2 PIT timestamp rules

- Exact source time: `available_at = published_at + source_delay_minutes`.
- Date-only source time: normalize to the end of the source's publication day, then add the delay.
- Explicit revision time: a revised row uses `source_updated_at + source_delay_minutes` as its availability floor.
- Content changed without an explicit revision timestamp: the revised row uses `ingested_at` as `available_at`; it must not be backdated to the original publication time.
- Reject or quarantine missing, unparseable, materially future-dated, or internally inconsistent timestamps.
- Source-time research eligibility: `available_at <= as_of`.
- Strict operational eligibility for LLM-derived data after joining raw, link, and extraction rows: `max(available_at, ingested_at, llm_extracted_at, linked_at) <= as_of`.
- Historical LLM backfill must never be represented as if its extraction existed at the article's original publication time.

### 8.3 Persistence and migration

- Retain temp-file plus `os.replace` atomic writes.
- Add an exclusive writer lock using the standard library and a lock file adjacent to the output. Lock acquisition is bounded; stale-lock cleanup is never automatic.
- Detect the exact current seven-column schema as schema v1 and migrate it in memory to v2 before merging.
- During v1 migration, derive all four IDs and hashes deterministically, use null ticker/universe provenance, and preserve all source/title/summary/url/timestamp values and their first observed timestamps.
- Any unknown, partial, or reordered legacy schema fails closed with a migration error. Do not infer arbitrary mappings.
- Validate the complete merged table before replacement.
- Persist raw data before opening or modifying either LLM sidecar.
- An extraction/link sidecar failure cannot modify, delete, or roll back raw data.

## 9. Shared alpha LLM configuration

### 9.1 Shared resolver

Create `src/omega/core/llm_config.py` and move the alpha runtime semantics into it:

- `SUPPORTED_LLM_PROVIDERS`.
- `ALPHA_LLM_CONFIG_ENV`.
- `load_external_alpha_config(repo_root)`.
- `resolve_alpha_llm_config(repo_root, provider_override=None)`.
- `sanitize_llm_config(config)`, returning provider, base URL, model, and API-key presence only.

`scripts/run_hybrid_alpha_evolution.py` retains public wrappers named `resolve_alpha_config()` and `resolve_llm_provider()` so existing imports and tests remain stable. Both wrappers delegate to the shared resolver. Mining, scoring, thresholds, provider artifacts, and CLI behavior are otherwise untouched.

### 9.2 Macro configuration rule

- `MacroNewsLLMExtractor` calls `resolve_alpha_llm_config(REPO_ROOT)` directly.
- Do not add `OMEGA_MACRO_LLM_PROVIDER`, `OMEGA_MACRO_LLM_MODEL`, `OMEGA_MACRO_LLM_BASE_URL`, `OMEGA_MACRO_LLM_API_KEY`, or equivalent config keys.
- Do not implement a separate provider fallback for macro extraction.
- Live extraction requires effective provider `openai-compatible` plus a nonblank API key, base URL, and model.
- `mock` is allowed only for unit tests and explicit dry-run behavior. A live CLI run must report extraction skipped/failed rather than persisting synthetic macro classifications.
- Permit plain HTTP only for loopback/local configured LLM endpoints. Remote LLM endpoints require HTTPS.

## 10. LLM extraction contract

### 10.1 Request behavior

- Call `{base_url.rstrip('/')}/chat/completions` through `requests.Session`; do not add the OpenAI SDK.
- Use the model returned by the shared alpha resolver and `temperature=0`.
- Process one canonical article-content payload per request in v2. Group candidates by exact request identity before HTTP so duplicate raw provenance rows do not trigger duplicate calls.
- The request body contains only the effective model, fixed prompt/schema text, deterministic generation fields, normalized title, normalized summary, and the exact bounded body text. It excludes `source_id`, source name/tier/kind, URL, `article_id`, `revision_id`, `raw_record_id`, ticker, exchange, universe fields, publication/update/availability/ingestion timestamps, and all other provenance.
- Never supply future returns, labels, portfolio state, secrets, local paths, or content from another article.
- Mark article text as untrusted data inside explicit delimiters. The model receives no tools and must ignore instructions contained in the article.
- Serialize the complete outbound JSON object once with sorted object keys, compact separators, UTF-8, and no ASCII escaping. Array order is fixed by the request builder. Compute `request_sha256 = SHA256(outbound_body_bytes)` and transmit those exact bytes with `data=outbound_body_bytes`; do not hash one serialization and send another through `json=`.
- Authentication and transport headers are excluded from `request_sha256`; secrets never enter cache identity. Retries reuse the identical body bytes and `request_sha256`.
- Normalize the endpoint to scheme, lowercase host, effective port, and `/chat/completions` path after rejecting userinfo, query, and fragment. Compute a secret-free `endpoint_id` from provider plus that normalized endpoint.
- Bound connect/read timeout and response bytes.
- Retry at most twice for network errors, `429`, and `5xx`, respecting a bounded `Retry-After`. Do not retry authentication errors, schema-invalid responses, or other non-transient `4xx` responses.

### 10.2 Strict output schema

Initial schema/prompt version: `macro_news_extract_v2`. Required output:

- `is_macro_relevant`: boolean.
- `relevance_score` and `confidence`: numbers in `[0, 1]`.
- `event_type`: one of `monetary_policy`, `fiscal_policy`, `inflation`, `growth`, `trade`, `fx`, `rates`, `credit`, `liquidity`, `labor`, `commodities`, `real_estate`, `regulation`, `sovereign`, `external_risk`, `other`, `not_macro`.
- `topics`: unique bounded enum array.
- `summary_vi`: concise factual Vietnamese summary grounded in the article.
- `policy_stance`: `hawkish`, `dovish`, `neutral`, `mixed`, or `not_applicable`.
- `growth_direction`, `inflation_direction`, `liquidity_direction`, `rates_direction`, `fx_direction`, `equity_direction`: `negative`, `neutral`, `positive`, `unclear`, or `not_applicable`.
- `time_horizon`: `immediate`, `near_term`, `medium_term`, `long_term`, or `unknown`.
- `entities`: bounded array of `{name, type}`.
- `indicators`: bounded array of `{name, direction, period}`.
- `numeric_facts`: bounded array of `{name, value, unit, period, evidence}`.
- `evidence_spans`: at most three short source-grounded spans.

The validator must:

- Reject missing/unknown keys, wrong types, invalid enums, NaN/Inf, out-of-range scores, and oversized strings/arrays.
- Canonically sort and deduplicate arrays before persistence.
- Verify every evidence span and every numeric-fact evidence string occurs in the exact normalized, bounded article text sent in the request. Ungrounded evidence invalidates the extraction.
- Never repair invalid output with heuristic guesses. Record the validation failure in the manifest and leave the row eligible for a future retry.
- Normalize `is_macro_relevant=false` to `event_type=not_macro`, empty arrays, and `not_applicable` policy/direction fields.

### 10.3 Extraction sidecar schema

Store validated results in `data/macro_news_llm.parquet`:

| Column | Logical type | Rule |
|---|---|---|
| `extraction_id` | string | Physical primary key derived from exact request plus sanitized endpoint identity |
| `extraction_identity_version` | int16 | Constant `1` for canonical identity encoding |
| `request_sha256` | string | SHA-256 of the exact canonical UTF-8 JSON bytes sent |
| `schema_version` | int16 | Extraction schema version |
| `prompt_version` | string | `macro_news_extract_v2` |
| `provider` | string | Sanitized effective provider |
| `endpoint_id` | string | Secret-free hash of normalized provider endpoint identity |
| `model` | string | Effective alpha model |
| `is_macro_relevant` | bool | Validated output |
| `relevance_score` | float32 | `[0, 1]` |
| `confidence` | float32 | `[0, 1]` |
| `event_type` | string | Validated enum |
| `topics_json` | string | Canonical JSON array |
| `summary_vi` | string | Bounded text |
| `policy_stance` | string | Validated enum |
| direction columns | string | Validated enums |
| `time_horizon` | string | Validated enum |
| `entities_json` | string | Canonical JSON |
| `indicators_json` | string | Canonical JSON |
| `numeric_facts_json` | string | Canonical JSON |
| `evidence_json` | string | Canonical JSON |
| `llm_extracted_at` | UTC timestamp | First successful extraction time |
| `response_sha256` | string | Validated response hash |
| `input_tokens` | nullable int32 | Usage metadata when returned |
| `output_tokens` | nullable int32 | Usage metadata when returned |

- `extraction_id = SHA256(canonical_json({extraction_identity_version, request_sha256, provider, endpoint_id}))`. `request_sha256` is therefore a mandatory component of extraction and cache identity, not audit-only metadata.
- The cache lookup key is exactly `extraction_id`; a hit is valid only when persisted `request_sha256`, provider, and `endpoint_id` match the recomputed values. Any mismatch is corruption and fails closed.
- Prompt text, response schema instructions, model, temperature, or bounded article input changes alter the exact body and therefore `request_sha256`. Provider or normalized endpoint changes alter `extraction_id` even if request bytes are identical.
- A successful `extraction_id` is first-wins. Invalid or failed responses do not create extraction rows and remain retryable.
- The extraction store contains no `article_id`, `revision_id`, `raw_record_id`, ticker, source, URL, timestamp, or other ambiguous provenance column.
- Never persist the raw provider response, request authorization, external config contents, or full request body.

Store provenance linkage separately in `data/macro_news_llm_links.parquet`:

| Column | Logical type | Rule |
|---|---|---|
| `raw_record_id` | string | Foreign key to one immutable raw provenance revision |
| `article_id` | string | Denormalized integrity/audit field matching the raw row |
| `revision_id` | string | Denormalized integrity/audit field matching the raw row |
| `extraction_id` | string | Foreign key to one validated extraction row |
| `request_sha256` | string | Must match the referenced extraction |
| `linked_at` | UTC timestamp | Immutable first time this mapping became locally available |

- Physical uniqueness is `(raw_record_id, extraction_id)`. Duplicate links preserve the first `linked_at`.
- Cardinality is explicit: `article_id 1:N revision_id`; `revision_id 1:N raw_record_id`; `raw_record_id 1:N link rows` across extraction versions; `extraction_id 1:N link rows` across identical requests. Thus one article may map to many extractions, and one extraction may serve many articles/provenance rows, only through this link table.
- Before appending a link, validate that its raw row exists, its denormalized IDs match, its extraction row exists, and `request_sha256` matches the extraction. Never infer linkage from `content_hash` alone.
- On a cache miss, persist and validate the extraction store first, then append all missing links for raw rows sharing that exact `extraction_id`. On a cache hit, make no HTTP call and append only missing links.
- The two sidecars use adjacent bounded writer locks acquired in a fixed extraction-then-link order and independent atomic replacements. A crash after extraction persistence but before link persistence leaves a harmless unlinked extraction; the next run reuses it and repairs links. A link may never reference an absent extraction. Raw data is never rolled back.

### 10.4 LLM vintage and research safety

- The model may classify and extract only facts evidenced in the article. The prompt must forbid outcome inference, later market reaction, and external factual supplementation.
- Historical backfill with the current model records `retrospective_extraction=true` in the run manifest.
- Retrospective extraction cannot qualify for strict historical operational replay solely because the article was old; `llm_extracted_at` and `linked_at` remain operational availability floors.
- Building features, training models, or promoting alphas from these fields is a separate audited phase and is outside this implementation.

## 11. Security, reliability, and observability

- SSRF: news URLs permit only configured `http`/`https` hosts. Validate the original URL, DNS/IP destination, redirects, and final host. Reject loopback, private, link-local, and unexpected cross-domain destinations.
- The trusted LLM base URL has a separate rule: loopback HTTP is allowed because the verified alpha runtime is local; remote LLM endpoints require HTTPS.
- Bound response bytes, decompressed text, redirects, article characters, PDF pages, pages per source, articles per run, and LLM response size.
- Treat article content as hostile prompt data. No tools, filesystem access, shell execution, or arbitrary URL retrieval is available to the model.
- Keep API keys only in the authorization header. Sanitize logs, exceptions, manifests, tests, caches, and persisted config summaries.
- Use source isolation, bounded retry, request pacing, and a stable user agent.
- Preserve raw data with full validation, exclusive writer locking, atomic replacement, and immutable first-observation timestamps.
- Respect source terms, robots/access policy, and licensing. Do not bypass login, paywalls, CAPTCHA, or access controls.
- Manifest fields: run ID, `as_of`, sanitized alpha LLM configuration, sanitized universe input name, universe ID/version/schema, exact-byte universe SHA-256, generation/effective timestamps, ticker/exchange counts, source statuses/counts/durations, inserted/skipped/revised raw counts, unique request groups, extraction cache hits/successes/failures, inserted/skipped link counts, retrospective flag, and final exit state.
- Do not include article bodies, secrets, authorization data, or raw LLM responses in manifests.

## 12. Exact implementation file changes

The implementation should stop at the smallest coherent diff below. Do not refactor unrelated news, database, or alpha-mining code.

### 12.1 New files

1. `config/macro_news_sources.json`
   - Versioned source registry.
   - Contains the eleven initial sources, including required `vnstock_vci` and `vcbs_research`.
   - Contains every expansion candidate from section 6.4. Unverified candidates remain `enabled=false` with a concrete validation or access reason.
   - Contains no credentials, cookies, arbitrary headers, or executable import paths.

2. `src/omega/core/llm_config.py`
   - Shared alpha LLM resolver and sanitized config view.
   - Preserves the exact alpha provider/value precedence and external-path validation behavior.
   - Contains no macro-specific configuration branch.

3. `src/omega/data/macro_news_llm.py`
   - `MacroNewsLLMExtractor` and its strict request/response schema.
   - Source-invariant canonical request-byte builder, exact `request_sha256`, `extraction_id`, evidence-grounding validation, bounded retry, cache reuse, extraction/link integrity checks, fixed lock order, and atomic persistence for both sidecars.
   - Depends only on the raw schema, shared LLM resolver, `requests`, `pandas`, and standard library.

4. `scripts/run_macro_news_pipeline.py`
   - Thin CLI orchestration only: parse arguments, run raw ingestion, persist raw, optionally run extraction, write manifest, return truthful exit code.
   - Minimum flags: `--as-of`, `--hours-back`, `--sources-config`, `--vnstock-universe`, `--raw-output`, `--llm-output`, `--llm-links-output`, `--ingest-only`, and `--max-articles`.
   - `--as-of` is mandatory and UTC-aware. `--vnstock-universe` is mandatory and has no default. No macro provider/model/key flags are allowed.
   - Parse registry and universe bytes first; validate schema, path, hash, and PIT interval before any adapter import, HTTP session, or network operation.

5. `tests/test_macro_news_llm.py`
   - Unit tests with fake `requests.Session` responses; no network and no real LLM cost.
   - Covers exact request serialization/hash, source invariance, extraction identity, one-call/many-link mapping, one-article/many-extraction mapping, link integrity/repair, schema validation, evidence grounding, retry classes, secret redaction, and the raw/LLM failure boundary.

No fixture files are required initially. Keep small synthetic RSS/HTML/JSON-LD/VCBS/PDF-metadata payloads inline in tests, matching the existing test style. Add external fixture files only when a source sample becomes too large to understand inline.

No universe data snapshot is created, copied, or committed by this implementation. It is a required versioned runtime data input owned by a reviewed external producer/operator. L2 must not promote `.ly_state/session/vci_universe_hsx_hnx.json` into `config/`, tests, or production defaults.

### 12.2 Modified files

1. `src/omega/data/macro_news_pipeline.py`
   - Load and validate the JSON source registry.
   - Add the exact-byte `load_universe_snapshot(path, as_of)` validator and immutable `UniverseSnapshot` contract; never read a default/session universe.
   - Expand the normalized raw record contract to schema v2 with article, revision, provenance, and physical identities plus universe provenance.
   - Add `VnstockNewsAdapter`, source-specific discovery/detail parsing, PDF text extraction, safe URL policy, source health, provenance-preserving revision append, exact v1 migration, writer lock, and atomic persistence.
   - Keep `MacroNewsPipeline`, `RSSAdapter`, `ScraperAdapter`, and `SCHEMA` as compatibility names where existing imports require them. Prefer thin aliases/wrappers over a broad breaking rename.
   - Do not import the LLM extractor.

2. `scripts/run_hybrid_alpha_evolution.py`
   - Import the shared resolver from `omega.core.llm_config`.
   - Preserve `resolve_alpha_config()` and `resolve_llm_provider()` wrappers, return shape, precedence, validation messages where tested, and CLI semantics.
   - Make no mining, scoring, feature, threshold, lockbox, artifact, or promotion change.

3. `requirements.txt`
   - Add `vnstock==4.0.4`, the locally verified API version used by the existing repository code.
   - Add no OpenAI SDK, HTML parser framework, ORM, queue, or service dependency. Use standard-library HTML parsing plus existing `pypdf`, Playwright, pandas, pyarrow, and requests runtime.

4. `tests/test_macro_news_pipeline.py`
   - Replace the seven-column-only assumptions with schema-v2 assertions and explicit schema-v1 migration coverage.
   - Add registry, source health, RSS/JSON-LD/source-specific HTML, VCBS, PDF metadata, vnstock cursor, identity/revision, first-observation, timestamp precision, URL safety, lock, and atomic-write tests.
   - Preserve focused legacy adapter tests through compatibility names where useful.

5. `tests/test_hybrid_alpha_real_market.py`
   - Retain all current provider precedence tests.
   - Add parity assertions proving the alpha wrappers delegate to the shared resolver without changing effective behavior.

### 12.3 Explicit no-change files

- `src/omega/core/database.py`: no new table or persistence path.
- `src/omega/data/macro_pipeline.py`: numeric macro indicator ingestion remains independent.
- `src/omega/data/macro_client.py`: no API expansion.
- `src/omega/data/news_aggregator.py`: sentiment ingestion remains unchanged; do not couple it to macro extraction or risk changing current keyword-filter behavior.
- `src/omega/data/news_rss_scraper.py`: no consolidation refactor in this scope.
- `scripts/run_sentiment_enrichment.py`: not reused as the macro extractor because it has a different output contract and legacy provider paths.
- `config/development.yaml`: source endpoints and LLM secrets do not belong in the general environment config.
- `tech-decisions.md`: per repository protocol, L1 updates it only after an implementation gate is `[APPROVED]`.

## 13. Implementation sequence

1. **Share the alpha resolver**
   - Move only configuration-resolution logic to `src/omega/core/llm_config.py`.
   - Keep alpha wrappers and run the existing provider tests before touching macro code.
   - Verify: sanitized alpha behavior and exception behavior are unchanged.

2. **Define registry and raw contracts**
   - Add the JSON registry loader, versioned universe schema/validator, schema v2 constants, source-status contract, four identity/hash helpers, timestamp rules, and exact schema-v1 migration.
   - Verify: missing/invalid/session/out-of-window universe inputs fail before imports/network; registry and migration tests pass offline.

3. **Implement static ingestion adapters**
   - Complete RSS, source-specific HTML, JSON-LD, detail fetch, and PDF extraction.
   - Add required VCBS coverage before optional source expansion.
   - Verify: synthetic parser fixtures and URL/timestamp safety tests pass.

4. **Implement vnstock ingestion**
   - Pass the immutable validated snapshot into VCI `Company.news` pagination; add per-symbol isolation, cutoff handling, and ticker/exchange/universe provenance mapping.
   - Verify: mocked vnstock tests prove no sentiment-keyword filter, no repeated-cursor loop, and two tickers for one story remain two raw rows.

5. **Make raw persistence immutable**
   - Add `article_id`, `revision_id`, `provenance_id`, `raw_record_id`, first-observation semantics, revision append, lock, full-table validation, atomic replace, and source run statistics.
   - Verify: same-story multi-ticker, duplicate, revision, concurrency, and error-path tests pass.

6. **Add LLM extraction sidecar**
   - Implement source-invariant canonical outbound bytes, `request_sha256`, `extraction_id`, strict parser, evidence checks, exact cache lookup, extraction store, and provenance link store.
   - Verify: fake-provider tests cover valid, invalid, transient, auth, timeout, request invariance, one-call/many-links, versioned mappings, crash repair, and secrets.

7. **Add the thin CLI and manifest**
   - Require explicit universe and link-output arguments, orchestrate raw-first operation, optional `--ingest-only`, required-source status, sanitized universe/runtime summary, and truthful exit codes.
   - Verify: CLI tests prove universe failure precedes network and raw persistence survives LLM/link failure.

8. **Validate and enable expansion sources**
   - Work official sources first, then broker research, then media, then high-impact global drivers.
   - For each candidate: discover an authoritative endpoint, add allowlist/parser config, create a synthetic structural fixture, run a bounded live smoke, and enable only on success.
   - Verify: every candidate is either enabled with evidence or disabled with a concrete reason; no guessed endpoint remains enabled.

9. **Run final verification**
   - Run targeted tests, related regressions, compilation, diff checks, and an approved temporary-output smoke.
   - Verification is last. Do not mix unrelated fixes into failures found here.

Critical path: `1 -> 2 -> 3/4 -> 5 -> 6 -> 7 -> 9`. Source-family validation in step 8 may be parallelized only with disjoint registry/test write ownership.

## 14. Test matrix

### 14.1 Shared LLM configuration

- External canonical absolute config outside the repo overrides shared environment values.
- Relative, missing, malformed, in-repo, symlink/non-canonical, non-object, and unsupported-provider external configs preserve the alpha resolver's current failure/fallback behavior.
- Explicit provider override wins only where the current alpha contract permits it.
- No configured provider and no key resolves to `mock`; a key with no provider resolves to `openai-compatible`.
- Sanitized config contains no key or secret-bearing source content.
- Alpha wrappers and macro resolver return identical provider, base URL, model, and key-presence state for the same environment.

### 14.2 Registry and transport safety

- Duplicate IDs, missing fields, unknown adapter IDs, invalid schemes, empty allowlists, and disabled required sources fail closed.
- Missing universe argument; missing/non-file/session-state path; malformed JSON; unknown schema/keys; invalid UTC/effective interval; future `generated_at`; duplicate/cross-exchange ticker; invalid ticker/exchange; and empty membership all fail before `vnstock` import, HTTP session creation, or any network call.
- Valid universe bytes produce the exact expected SHA-256, immutable sorted members, and manifest ID/version/generation/effective/count fields without copying member data.
- Redirects to unexpected hosts, loopback/private/link-local addresses, or excessive redirect chains are rejected.
- Oversized HTML, XML, JSON, PDF, and LLM responses are rejected before unbounded allocation or parsing.
- One failed source leaves successful source rows intact.
- Required-source failure persists good raw data, writes a manifest, and returns non-zero.

### 14.3 RSS, HTML, and research documents

- Valid RSS/Atom timestamps normalize to UTC; missing/ambiguous timestamps quarantine the item.
- JSON-LD publication time takes precedence over less precise visible text.
- Source-specific VCBS and SBV fixtures extract correct title, URL, timestamp, and report content.
- Date-only releases map to the conservative end-of-day policy.
- PDF content type, host, size, page count, encryption, empty text, and timestamp mismatch paths are covered.
- DOM drift produces a source failure rather than an invented record.

### 14.4 vnstock

- `Company(symbol=<ticker>, source="VCI")` is called for validated universe symbols.
- `news(cursor, limit=100, sort="public_date_desc")` is called with progressing cursors.
- Cutoff, page cap, article cap, null cursor, and repeated cursor terminate correctly.
- Missing `news_title` or `public_date` fails the source contract.
- A failing symbol does not block later symbols.
- Articles lacking bullish/bearish keywords remain in macro raw output.
- Missing provider URL still yields a stable source-level article ID without including ticker.
- One provider story returned for `AAA` and `BBB` produces one `article_id`, one `revision_id`, two `provenance_id` values, two `raw_record_id` values, and two raw rows carrying their exact ticker/exchange/universe provenance.

### 14.5 Persistence and PIT

- Exact schema v1 migrates to v2 without losing source/title/summary/url/timestamps.
- Unknown legacy schemas fail before replacing the canonical file.
- Repeating `raw_record_id` preserves the original `ingested_at` and first-observation universe provenance.
- Changed content appends a `revision_id` and provenance-specific `raw_record_id`, then applies the revision availability rule.
- Source-time and strict operational-time eligibility use the correct raw, extraction, and link timestamp floors.
- Lock contention cannot produce a lost update; timeout leaves the existing file unchanged.
- Temp files are removed after success and failure.

### 14.6 LLM extraction

- Valid strict JSON persists with canonical arrays and hashes.
- Markdown fences, prose outside JSON, unknown keys, missing keys, bad types/enums/ranges, NaN/Inf, and oversized output are rejected.
- Evidence not present in normalized input is rejected.
- `is_macro_relevant=false` normalizes to the required `not_macro` contract.
- Changing only source, URL, IDs, ticker, universe fields, or timestamps leaves canonical outbound bytes and `request_sha256` unchanged.
- The SHA-256 is calculated from the exact bytes captured by the fake HTTP session; retries send byte-identical bodies.
- Identical request bytes plus the same provider/endpoint produce one `extraction_id`, one HTTP call, one extraction row, and one link per matching raw row. A cache hit repairs missing links without another HTTP call.
- A title/summary/body, prompt/schema instruction, deterministic generation field, or model change changes `request_sha256`; a provider/endpoint change changes `extraction_id`.
- One `article_id` may link to multiple extraction versions; one `extraction_id` may link to multiple article/revision/provenance rows. The extraction store contains no ambiguous `article_id`.
- A link with a missing/mismatched raw row, extraction, denormalized ID, or `request_sha256` fails before replacement. Extraction/link crash recovery never creates a dangling link.
- Network, `429`, and `5xx` retries are bounded; `401/403` and schema failures are not retried.
- Timeout or extractor failure cannot modify raw Parquet.
- Requests, logs, manifests, exceptions, and sidecar rows contain no API key.

## 15. Verification commands for implementation and audit

These commands are specified for L2/L3; they are not run by this planning session.

```powershell
Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'
python -m py_compile src/omega/core/llm_config.py src/omega/data/macro_news_pipeline.py src/omega/data/macro_news_llm.py scripts/run_macro_news_pipeline.py scripts/run_hybrid_alpha_evolution.py
pytest -q tests/test_macro_news_pipeline.py tests/test_macro_news_llm.py tests/test_hybrid_alpha_real_market.py tests/test_news_aggregator.py tests/test_news_aggregator_scrapers.py
git diff --check
git status --short
```

Run a live smoke only after approval, with bounded temporary output and no LLM cost:

```powershell
$UniversePath = 'C:\approved-artifacts\omega_quant\universes\vci_hsx_hnx_2026-08-12.json' # operator replaces with the reviewed immutable snapshot
python scripts/run_macro_news_pipeline.py --as-of 2026-08-12T00:00:00Z --vnstock-universe $UniversePath --ingest-only --max-articles 5 --raw-output .ly_state/session/macro_news_smoke.parquet --llm-output .ly_state/session/macro_news_llm_smoke.parquet --llm-links-output .ly_state/session/macro_news_llm_links_smoke.parquet
```

Use the actual current UTC timestamp instead of the example `2026-08-12T00:00:00Z` when executing a live smoke. A one-article live LLM smoke requires explicit cost/network approval and must first print only the sanitized effective configuration.

## 16. Acceptance criteria

- `vnstock_vci` and `vcbs_research` are required, enabled, fixture-covered, and present in source health output.
- Every run requires an explicit versioned `--vnstock-universe`; no runtime code reads `.ly_state` or discovers/defaults/refreshes membership. Invalid or PIT-ineligible input fails before import/network, and exact-byte hash plus lifecycle/count metadata appear in the manifest and vnstock raw rows.
- The current ten-source baseline is preserved.
- Every source candidate in section 6.4 is evaluated; enabled candidates have a validated authoritative endpoint and parser, while disabled candidates have a precise reason.
- Raw ingestion persists independently of LLM availability.
- `data/macro_news.parquet` is append-only by `raw_record_id`, preserves one row per vnstock ticker provenance, is schema-v2 validated, and migrates the exact schema-v1 baseline.
- `data/macro_news_llm.parquet` is keyed by an `extraction_id` containing exact `request_sha256`; request construction is source-invariant and contains no ambiguous article linkage.
- `data/macro_news_llm_links.parquet` implements the validated one-to-many article/revision/provenance/extraction mapping, supports one-call/many-links reuse, and is independently repairable from raw plus extraction rows.
- Macro extraction uses the same shared resolver and effective provider/base URL/model/key source as alpha. No macro-specific LLM routing exists.
- The sanitized current runtime still resolves to provider `openai-compatible`, base URL `http://localhost:20128/v1`, model `cx/gpt-5.6-terra`, with a key present.
- No secret appears in source, tests, output, cache, manifest, or logs.
- Publication, availability, first-ingestion, revision, and extraction timestamps are validated and tested.
- Required-source failures produce truthful non-zero status without destroying successful raw data.
- No database, API, queue, feature-engineering, model-training, or alpha-promotion expansion enters this scope.
- Targeted tests, related regressions, compilation, and `git diff --check` pass.

## 17. Rollback and operations

- Disable a broken source in the registry with a reason; never delete its historical rows.
- A parser version change may create a new raw revision when extracted content changes; it must not rewrite old revisions.
- A bad prompt/model/schema version is stopped by disabling new extraction runs; previous sidecar rows and all raw rows remain intact.
- Both LLM sidecars can be rebuilt from raw data and the effective LLM runtime; raw data cannot be reconstructed from either sidecar.
- Shared resolver rollback must retain the alpha-script wrappers so existing imports do not break.
- Do not automatically remove a stale lock. Report its path and require an operator to confirm no live writer before manual cleanup.

## 18. Deliberate simplifications

- One canonical article-content payload per LLM request in v2; exact duplicates share a cache row and links. Add batching only when measured uncached volume or latency justifies the added failure complexity.
- No queue, service, database, or distributed scheduler; add one only after a single scheduled process misses a defined throughput/reliability target.
- No fuzzy cross-source deletion; keep provenance and group with `story_hash`. Add clustering only for a demonstrated downstream use case.
- No OCR for image-only PDFs; add OCR only when a required source has material inaccessible coverage.
- No automatic source discovery crawler; registry entries remain reviewed and allowlisted.
- No trading feature generation in this phase; add it only under a separate PIT/backtest audit.

## 19. Exact repo-local files read

The following repo-local files were intentionally opened or directly inspected for this plan.

### Role and required skills

- `.agents/agent/planning-architect.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/AGENTS.md`

### Configuration, dependencies, and decisions

- `.env` - only relevant key names, routing values, external config path, and secret presence were inspected; the secret value was not emitted.
- `.gitignore`
- `config/development.yaml`
- `config/production.yaml`
- `requirements.txt`
- `setup.cfg`
- `tech-decisions.md`

### Alpha LLM paths

- `scripts/run_hybrid_alpha_evolution.py`
- `scripts/run_weekly_evolution.py`
- `scripts/genetic_alpha_evolution_v4.py`
- `src/omega/quant/evolution/llm_formula_scorer.py`
- `src/omega/quant/evolution/llm_formula_search.py`
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

### Macro, news, and data paths

- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/macro_client.py`
- `src/omega/data/news_rss_scraper.py`
- `src/omega/data/news_aggregator.py`
- `src/omega/data/datasource_config.py`
- `src/omega/core/database.py`
- `scripts/run_sentiment_enrichment.py`
- `scripts/fetch_news_sentiment.py`
- `scripts/migrate_news_parquet.py`
- `scripts/select_universe_dynamic.py`
- `scripts/walk_forward_universe.py`
- `src/omega/data/exchange_resolver.py`
- `src/omega/data/vnstock_vci.py`
- `src/omega/quant/data/vnstock_vci.py`
- `src/omega/quant/alpha/discovery_universe.py`

### Tests inspected

- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_pipeline.py`
- `tests/test_free_news_rss_scraper.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`
- `tests/test_db_news_macro.py`
- `tests/test_hybrid_alpha_real_market.py`
- `tests/quant_test_infinite_evolution.py`

### Prior session artifacts inspected

- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/implementation_plan_macro_news.md`
- `.ly_state/session/implementation_plan_macro_news_l3.md`
- `.ly_state/session/l2_role9_macro_news_pipeline_20260812.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan.md`
- `.ly_state/session/vci_universe_hsx_hnx.json` - inspected only as evidence of the forbidden session-state shape; it is not a runtime or membership authority.

The repo-external runtime file `C:\Users\GHC\llm_configs\alpha_llm.json` was checked only through a sanitized provider/base-URL/model/key-presence projection. It is not a role, skill, or repository authority. No authority was taken from global skills, `.openclaw`, or other non-repo protocol paths.

## 20. Handoff

- L1 reviews and approves this plan before dispatching L2.
- L2 reads its own repo-local role and declared skills, reports those exact files, and implements only the approved file map.
- L3 audit verifies writer/auditor separation, scope, source evidence, provider parity, security, PIT behavior, tests, and worktree cleanliness before any gate approval.
- L1 updates `tech-decisions.md` only after an `[APPROVED]` gate, as required by the repository protocol.
