# Macro News Pipeline v3 Implementation Plan

## 1. Planning Boundary

- Date: `2026-08-13`.
- Artifact: `.ly_state/session/implementation_plan_macro_news_v3.md`.
- Parsed role: `name=planning-architect`, `role_id=26`, `tier=3`, `platform=Codex`, skills `plan-writing`, `architecture`, `database-design`, `api-patterns`.
- SoD boundary: planning only, non-audit, no production code, no test implementation, no gate approval.
- This revision fixes the three supplied P1 blockers. It does not issue an audit verdict.
- Only this plan is changed. Existing unrelated worktree changes remain untouched.
- Runtime remains a one-shot CLI. No timer, scheduler, daemon, queue, service, or background polling loop.
- No web lookup, live source request, LLM request, dependency installation, or data mutation occurred.

## 2. Goal

Extend the raw-first macro-news pipeline to:

1. Ingest `vnstock_vci`, required VCBS research, the current source set, and additional validated macro sources.
2. Use explicit durable point-in-time vnstock membership, never hidden `.ly_state` state.
3. Preserve every vnstock ticker/exchange observation in the physical raw key.
4. Persist raw records before any LLM call.
5. Extract structured macro events through the same effective LLM provider resolver used by alpha generation.
6. Key extraction/cache rows from the SHA-256 of the exact canonical request bytes sent over HTTP.
7. Reuse one content extraction across provenance-only duplicates through a separate link sidecar.

## 3. P1 Closure Matrix

| P1 blocker | Binding contract | Acceptance evidence |
|---|---|---|
| Hidden session-state dependency | Require explicit `--vnstock-universe <path>`. Resolve to a regular JSON file outside `.ly_state`. Allow an immutable repo-owned `config/universes/` snapshot only when explicitly passed. Forbid path search, environment fallback, session fallback, hard-coded membership, and live refresh. | Missing, malformed, symlinked-to-session, future, expired, duplicate-member, or `.ly_state` input fails before package import/network. Manifest records exact universe identity. |
| vnstock provenance lost | Keep article/revision identity content-level. Compute `provenance_id` from `source_id`, `origin_ticker`, `origin_exchange`; compute physical `raw_record_id` from `revision_id` plus `provenance_id`. | One story returned for `AAA` and `BBB` yields one article/revision, two provenance IDs, two raw IDs, two raw rows. Rerun remains idempotent. |
| LLM cache identity mismatch | Serialize once, hash exact body bytes as `request_sha256`, send the same bytes with `requests.post(data=body)`, and include `request_sha256` in extraction/link identity. | Captured HTTP body hash equals persisted `request_sha256`. Content/runtime changes miss cache. Ticker-only differences reuse extraction and create distinct links. |

## 4. Current Baseline and Target Flow

- `config/macro_news_sources.json` contains 27 entries; 11 enabled.
- `vnstock_vci` and `vcbs_research` are enabled and required.
- `scripts/run_macro_news_pipeline.py` already requires `--vnstock-universe`, rejects `.ly_state`, and passes validated bytes onward.
- `src/omega/data/macro_news_pipeline.py` already separates `article_id`, `revision_id`, `provenance_id`, and `raw_record_id`.
- `src/omega/data/macro_news_llm.py` already uses canonical compact UTF-8 request bytes and stores `request_sha256`.
- Macro already imports `resolve_alpha_llm_config` from shared core code.
- L2 preserves these partial fixes, adds regression coverage, replaces remaining name-based adapter dispatch, and completes source contracts.

```text
explicit universe JSON + source registry
        |
        v
pre-network validation
        |
        v
vnstock + RSS/HTML/VCBS adapters
        |
        v
data/macro_news.parquet
        +---- raw atomic commit completes first
        |
        v
shared alpha LLM resolver
        |
        v
canonical request bytes + request_sha256
        |
        v
data/macro_news_llm.parquet
        +---- data/macro_news_llm_links.parquet
        |
        v
.ly_state/session/macro_news_runs/<run_id>.json
```

`.ly_state` is operational output only. It is never a universe input. LLM failure may make the run non-zero, but cannot roll back or rewrite raw data.

## 5. Durable vnstock Universe

- Keep `--vnstock-universe` required; no default.
- Preferred input: immutable reviewed JSON under `config/universes/`, explicitly passed. External durable absolute paths remain valid.
- Never search, copy, or fallback to `.ly_state/session/vci_universe_hsx_hnx.json` or another session artifact.
- Never derive members from environment variables, prior manifests, raw Parquet, process cache, hard-coded tickers, or live provider discovery.
- Pass a validated immutable `UniverseSnapshot` to `VnstockNewsAdapter`; the adapter cannot discover or mutate membership.

Schema version `1` keeps: `schema_version`, `universe_id`, `universe_version`, `generated_at`, `effective_from`, nullable `effective_to`, and non-empty `members[{ticker,exchange}]`.

Pre-network validation order:

1. Resolve the supplied path; require an existing regular file.
2. Reject resolved `.ly_state` paths, including symlink/junction targets.
3. Read exact bytes once; compute `universe_sha256 = SHA256(input_bytes)` before JSON normalization.
4. Require exact keys, schema version `1`, bounded identity tokens, and UTC-aware lifecycle timestamps.
5. Enforce `generated_at <= as_of` and half-open eligibility `effective_from <= as_of < effective_to`; null `effective_to` is open-ended.
6. Require unique uppercase tickers and exchanges `HSX` or `HNX`.
7. Pass the already-read bytes to the package loader. Path replacement cannot alter validated input.

Raw vnstock rows and the run manifest record `universe_id`, `universe_version`, exact `universe_sha256`, `generated_at`, `effective_from`, and `effective_to`. The manifest records only the input filename, not the payload.

## 6. Raw Identity, Provenance, Migration

Use canonical sorted compact JSON for every hash input:

```text
content_hash   = SHA256({title, summary, body_text})
article_id     = SHA256({v, source_id, source_record_id or canonical_url or publication fallback})
revision_id    = SHA256({v, article_id, content_hash})
provenance_id  = SHA256({v, source_id, origin_ticker, origin_exchange})
raw_record_id  = SHA256({v, revision_id, provenance_id})
```

- `article_id` excludes ticker, exchange, universe, ingestion time, and run ID.
- `revision_id` changes only when normalized content changes for the same article.
- vnstock rows require `origin_ticker` and `origin_exchange`; non-vnstock rows retain source provenance with null origin values.
- `raw_record_id` is the physical Parquet key. It retains ticker provenance without adding another content store.
- `story_hash` may support similarity analysis; it is never a persistence key.
- Persist with `drop_duplicates(raw_record_id, keep=first)` only after full identity validation.
- Never deduplicate vnstock rows on URL, provider story ID, `article_id`, or `revision_id` alone.

Required P1 example:

- One provider story appears for `AAA/HSX` and `BBB/HSX`.
- Both rows share `article_id`, `content_hash`, and `revision_id`.
- They have distinct `origin_ticker`, `provenance_id`, and `raw_record_id`.
- Result: two raw rows, one reusable LLM extraction, two raw-to-extraction links.
- A rerun adds zero rows.

Migration rules:

- Continue deterministic migration of the legacy seven-column non-vnstock schema.
- Recompute all identities; validate a staged file before atomic replacement.
- Never invent missing vnstock ticker, exchange, or universe provenance.
- A legacy vnstock row missing provenance is non-migratable: preserve the original store byte-for-byte, emit a bounded error, and require regeneration or an explicit reviewed mapping.
- Existing schema-v2 rows must pass formula recomputation. Identity mismatch is corruption, not a cache miss.

## 7. Source Registry and Expansion

Keep `config/macro_news_sources.json` as the only source registry. Each entry retains a stable `source_id`, display name, tier, kind, enabled/required state, discovery URL, host allowlist, fixed adapter ID, source delay, UTC timestamp policy, page/item bounds, request interval, timeout, response byte cap, PDF/browser flags, and concrete disabled reason.

Reject duplicate IDs, unknown fields/adapters, invalid public discovery URLs, host mismatch, disabled required sources, missing disabled reasons, and invalid bounds.

### Stage 1 - required baseline

- Required: `vnstock_vci`, `vcbs_research`.
- Preserve enabled optional sources: `cafef_macro`, `vietstock_macro`, `sbv_news`, `baochinhphu_economy`, `ssi_research`, `vndirect_research`, `vneconomy_macro`, `baodautu_macro`, `tinnhanhchungkhoan_macro`.

### Stage 2 - official Vietnam expansion

- Validate individually: `gso_releases`, `mof_releases`, `moit_releases`, `customs_releases`, `ssc_releases`, `vnx_releases`, `hsx_releases`, `hnx_releases`.
- Prefer official release/listing pages. Never infer publication time from fetch time or file modification metadata.

### Stage 3 - multilateral, research, media expansion

- Validate individually: `world_bank_vietnam`, `imf_vietnam`, `adb_vietnam`, `vietcap_research`, `mbs_research`, `kbsv_research`, `bsc_research`, `vnexpress_business`.

No candidate is enabled merely to satisfy a source count. Before enablement, document public endpoint, usage/licensing disposition, allowed hosts/redirects, publication timestamp evidence, pagination/response bounds, parser fixture, empty-result behavior, and one bounded live contract check. Otherwise retain `enabled=false` with exact missing evidence in `disabled_reason`.

## 8. VCBS Contract

- Change `vcbs_research.adapter` from generic `html` to fixed `vcbs`.
- Dispatch adapters from the registry `adapter` field, never source-name string matching.
- Keep the current listing URL and `vcbs.com.vn`/`www.vcbs.com.vn` allowlist unless implementation-time validation requires a reviewed registry update.
- Require non-empty title, canonical allowed-host detail URL, and source publication timestamp.
- Fetch only bounded same-host details discovered from the validated listing.
- Accept HTML or PDF when `allow_pdf=true`; use installed `pypdf`.
- Reject encrypted, oversized, page-excess, unsupported, or empty PDFs; cap extracted text.
- Recompute `content_hash`, `revision_id`, and `raw_record_id` after detail enrichment while retaining `provenance_id`.
- Listing drift, cross-host redirect, missing timestamp, empty detail, oversized response, or unsupported document fails VCBS closed.
- Because VCBS is required, failure sets `final_exit_state=required_source_failed`; previously persisted raw data remains intact.

## 9. PIT and Transport Controls

- Normalize accepted publication times to timezone-aware UTC.
- Preserve `raw_timestamp`, `timestamp_precision`, `published_at`, optional `source_updated_at`, `available_at`, and `ingested_at`.
- Compute `available_at` from publication/update evidence plus configured source delay; never from LLM extraction time.
- Accept only `cutoff <= published_at <= as_of` and `available_at <= as_of`.
- Validate public hosts before network use; reject credentials, fragments, unexpected schemes, private/local destinations, and cross-host redirects.
- Bound pages, items, response bytes, PDF pages/text, connect/read timeout, retries, and error text.
- Keep browser fallback disabled until a specific source has an approved fixture-backed need.
- Never persist cookies, authorization headers, API keys, raw LLM responses, or complete universe payloads.

## 10. Shared Alpha LLM Provider

- Macro imports `resolve_alpha_llm_config` from `src/omega/core/llm_config.py`, the same resolver used by alpha code.
- Do not add macro-specific provider, model, base URL, API key, config path, or precedence variables.
- Preserve resolver precedence: explicit provider override, external alpha config provider, existing `OMEGA_LLM_PROVIDER`; external alpha config fields before existing `OMEGA_LLM_*` fallbacks.
- Live macro extraction requires the same effective `openai-compatible` provider config: provider, API key, base URL, and model.
- Remote HTTP remains forbidden; only localhost may use HTTP. Remote endpoints require HTTPS.
- Persist only sanitized provider, base URL, model, and key-present metadata in the run manifest.
- If parity tests already pass, do not modify `src/omega/core/llm_config.py`.

## 11. Canonical Request and Cache Identity

Build one request object from the effective alpha model, `temperature=0`, a versioned system prompt, strict JSON output instructions, and bounded normalized `title`, `summary`, `body_text`.

Exclude `source_id`, URL, article IDs, ticker, exchange, universe fields, timestamps, ingestion metadata, and raw identity. These values do not change article semantics and must not fragment extraction reuse.

Serialize once:

```text
body_bytes = json.dumps(request, sort_keys=True, separators=(,, :), ensure_ascii=False).encode(utf-8)
request_sha256 = SHA256(body_bytes)
endpoint_id = SHA256({provider, canonical_chat_completions_endpoint})
extraction_id = SHA256({v, request_sha256, provider, endpoint_id})
```

The exact `body_bytes` object is passed as `requests.post(data=body_bytes)`. No second serialization is permitted.

### Extraction sidecar

- `data/macro_news_llm.parquet` primary key: `extraction_id`.
- Mandatory identity columns: `extraction_identity_version`, `request_sha256`, schema/prompt version, provider, endpoint ID, model.
- Retain validated output fields, extraction timestamp, response hash, and token counts.

### Link sidecar

- `data/macro_news_llm_links.parquet` composite key: `(raw_record_id, extraction_id)`.
- Mandatory columns: `article_id`, `revision_id`, `request_sha256`, `linked_at`.
- A link is valid only when raw foreign keys match the raw store, the extraction exists, and both rows share `request_sha256`.

### Cache validation and migration

- Validate persisted cache and links before network access.
- Duplicate extraction IDs, identity mismatch, response-hash mismatch, malformed JSON columns, or broken links fail closed.
- Valid current rows bound to exact `request_sha256` remain reusable.
- A legacy row lacking `request_sha256`, endpoint identity, or a verifiable formula cannot prove transmitted bytes. Preserve original sidecars, emit a bounded rebuild-required error, and rebuild from raw rows into staged sidecars.
- Prompt, model, article text, endpoint, or provider changes create a new extraction ID.
- Ticker, exchange, universe, or raw ID changes alone create another link, not another extraction.
- Keep separate locks, staged validation, and atomic replacement for extraction and link sidecars.

## 12. Exact Planned File Changes

### `config/macro_news_sources.json`

- Set `vcbs_research.adapter` to `vcbs`.
- Preserve required `vnstock_vci` and VCBS controls.
- Complete candidate evidence; enable only validated sources.

### `scripts/run_macro_news_pipeline.py`

- Preserve required explicit universe input and pre-import validation.
- Keep already-read universe bytes as the package handoff.
- Preserve raw-persist-before-LLM ordering and sanitized manifest fields.
- Add no hidden input fallback or background execution.

### `src/omega/data/macro_news_pipeline.py`

- Dispatch by registry adapter ID.
- Preserve and validate physical provenance identities on every read/write path.
- Harden VCBS listing/detail/PDF behavior.
- Add fail-closed handling for non-reconstructable vnstock migration.

### `src/omega/data/macro_news_llm.py`

- Preserve canonical single-serialization request hashing.
- Require `request_sha256` in extraction/cache/link validation.
- Preserve provenance-invariant extraction plus separate links.
- Add fail-closed legacy cache handling.

### `src/omega/core/llm_config.py`

- Modify only if parity tests show macro and alpha receive different effective resolver output. Otherwise leave unchanged.

### `tests/test_macro_news_pipeline.py`

- Add durable-universe, provenance, adapter dispatch, VCBS, registry, migration, PIT, atomicity, and required-source failure tests.

### `tests/test_macro_news_llm.py`

- Add exact-body hash, extraction identity, cache miss/hit, provenance reuse, corrupt cache/link, provider parity, and raw-preservation tests.

### `tests/quant_test_infinite_evolution.py`

- Extend existing alpha config regressions only where required to prove shared resolver parity.

### `tests/fixtures/macro_news/*`

- Add minimal source-owned listing/detail/PDF fixtures only for enabled adapters.

No new dependency is planned. `requirements.txt` already contains `pandas`, `pyarrow`, `pypdf`, and pinned `vnstock==4.0.4`.

## 13. Ordered Implementation Sequence

### Stage 1 - freeze P1 contracts

1. Add failing CLI/loader tests for explicit durable universe input and pre-network rejection.
2. Add the two-ticker/one-story raw identity and persistence rerun tests.
3. Add captured HTTP byte/hash and provenance-only extraction reuse tests.
4. Add fail-closed legacy raw/cache migration tests with destination preservation.

### Stage 2 - complete ingestion

5. Refactor adapter dispatch to use `entry[adapter]`.
6. Bind `vcbs_research` to `VCBSAdapter`; add listing, HTML, PDF, drift, and bounds fixtures.
7. Validate `raw_record_id = hash(revision_id, provenance_id)` across creation, enrichment, migration, merge, and read validation.
8. Validate each additional candidate; enable only entries with complete evidence and fixtures.
9. Confirm required-source status and raw-first manifest behavior.

### Stage 3 - complete LLM identity

10. Prove macro and alpha resolve the same effective provider config; avoid resolver changes when parity already holds.
11. Bind request construction, SHA-256, extraction identity, and HTTP transport to one canonical byte object.
12. Validate extraction/link foreign keys and provenance-invariant reuse before network access.
13. Preserve raw output on LLM failure; atomically stage extraction and link sidecars.

### Stage 4 - verification

14. Run focused macro ingestion and LLM tests.
15. Run targeted alpha resolver regressions.
16. Run syntax/import checks and `git diff --check` on the implementation set.
17. Inspect the final diff for hidden `.ly_state` universe reads, ticker-blind dedupe, second request serialization, secrets, timer/scheduler code, or unrelated edits.

## 14. Required Test Matrix

### Durable universe

- Missing CLI argument fails through argparse.
- Direct `.ly_state` input and a symlink/junction resolving there fail before package import/network.
- Exact-byte hash remains stable across path replacement because validated bytes are passed onward.
- Invalid JSON, unknown keys, naive timestamps, future generation, inactive interval, duplicate ticker, invalid exchange, and empty members fail closed.
- Explicit valid `config/universes/...json` input succeeds; no automatic selection occurs.

### Raw provenance

- Same vnstock story for `AAA` and `BBB` yields two physical raw rows.
- Same ticker/story rerun adds zero rows.
- Content revision changes `revision_id` and `raw_record_id` while retaining article/provenance identity.
- URL/article-level dedupe never removes a second ticker provenance.
- Corrupt stored identities fail before destination replacement.

### VCBS and sources

- Registry dispatch uses adapter ID, not source spelling.
- VCBS listing fixture requires publication evidence and allowed-host details.
- HTML and PDF details recompute content/revision/raw identities.
- Encrypted, oversized, excessive-page, cross-host, empty, timestamp-less, or drifted VCBS input fails closed.
- Disabled candidates report concrete reasons; enabled candidates have endpoint, fixture, timestamp, licensing, and bounds evidence.

### Shared alpha LLM and cache

- Macro and alpha receive equal sanitized effective config under file/environment precedence cases.
- Persisted `request_sha256` equals SHA-256 of captured posted bytes.
- Reordered Python mappings produce identical canonical bytes.
- Prompt, model, endpoint, provider, or article content changes extraction identity.
- Ticker/exchange/universe/raw ID changes alone reuse one extraction and create distinct links.
- Legacy unbound cache, corrupt extraction identity, mismatched request/response hash, or broken foreign key fails before HTTP.
- LLM failure leaves raw Parquet valid and present; no secret reaches logs or manifest.

## 15. Verification

Run focused macro ingestion, macro LLM, and alpha resolver regressions after L2 implementation.

Required commands: focused `pytest`, targeted alpha resolver `pytest`, `compileall`, CLI `--help`, then `git diff --check` on the planned file set.

Any bounded live source check uses explicit temporary outputs and an explicit durable universe. It never modifies canonical Parquet before fixture validation passes.

## 16. Completion Criteria

- Explicit durable universe; no `.ly_state` input or fallback.
- Same story from two tickers persists two physical raw keys.
- Exact transmitted request bytes hash to mandatory `request_sha256`.
- Provenance-only duplicates share one extraction through separate links.
- VCBS is required, registry-dispatched, bounded, fixture-backed, HTML/PDF capable.
- Extra sources are verified and enabled, or disabled with exact evidence gaps.
- Macro uses the shared alpha LLM resolver; no macro-only provider config.
- Raw persistence completes before LLM extraction.
- Invalid legacy/corrupt raw or cache data fails closed without destination damage.
- No timer, scheduler, daemon, queue, service, new DB, or unrelated refactor.

## 17. Deliberate Simplifications

- Keep Parquet plus sidecars; no database or API.
- Keep physical raw rows per provenance; normalize content only after measured storage pressure.
- Keep explicit CLI universe selection; no discovery layer.
- Keep source-specific adapters only where fixtures prove need.
- Keep unverified sources disabled; invent no endpoints.
- Add no dependency.

## 18. Exact Repo-Local Files Read

- `.agents/agent/planning-architect.md`
- `.agents/AGENTS.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`

Task context and prior plans:

- `.ly_state/session/implementation_plan_macro_news.md`
- `.ly_state/session/implementation_plan_macro_news_l3.md`
- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_reaudit.md` - read only to locate the supplied P1 wording; no audit work performed.

Current implementation, configuration, and tests:

- `config/macro_news_sources.json`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/core/llm_config.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_news_llm.py`
- `tests/quant_test_infinite_evolution.py`
- `setup.cfg`
- `requirements.txt`

No repo-local scratch file content was opened or used as authority.

## 19. Forbidden Path Scan Result

Metadata-only existence checks were performed for prohibited non-repo skill and memory roots:

.gemini\antigravity-ide\scratch\ag-kit non-authoritative scan evidence only; no reliance.
.openclaw\skills non-authoritative scan evidence only; no reliance.
C:\Users\GHC\.agents non-authoritative scan evidence only; no reliance.
.codex\memories non-authoritative scan evidence only; no reliance.

- A filename-only repository scan reported 3,408 paths under directories named `scratch`; zero scratch file contents were opened or used.
- Required skills were read only from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.
- Role content was read only from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`.
- Result: zero forbidden content reads; zero forbidden authoritative reliance.

## 20. Handoff

L1 reviews this plan, then dispatches the ordered file-scoped tasks to L2. Independent review, audit, and gate decisions remain outside role 26.
