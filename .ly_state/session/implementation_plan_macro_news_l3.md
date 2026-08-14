# L3 Implementation Plan: Macro News Ingestion + LLM Extraction

**Date:** 2026-08-12
**Role:** 26 `planning-architect` / Codex L3
**Boundary:** Planning only. No production code or tests changed.

## Goal

Complete the existing macro-news baseline into a deterministic, PIT-safe pipeline that collects ten Vietnamese macro-news sources, writes `data/macro_news.parquet`, then enriches each article with sentiment, hawkish/dovish stance, and key entities through the alpha LLM runtime.

## Scope Reconciliation

- The request says **10 sources** but names nine: CafeF, Vietstock, SBV, VCBS, SSI, VNDirect, VnEconomy, BaoDauTu, TinNhanhChungKhoan.
- Existing `DEFAULT_SOURCES` supplies **BaoChinhPhu** as source ten. Preserve it unless L1 names a replacement before L2 dispatch.
- `src/omega/data/macro_news_pipeline.py` and `tests/test_macro_news_pipeline.py` already exist. Implement the delta; do not rebuild unrelated news systems.

## Architecture Decisions

1. Keep ingestion and LLM enrichment separate. Collection must work during LLM outages.
2. Keep one Parquet store. No DB, queue, service, or new dependency.
3. Use source-specific HTML extraction behind the existing registry; the generic `<article><time>` regex cannot cover SBV/research sites reliably.
4. Preserve `available_at = published_at + 15 minutes`; PIT queries require both `available_at <= as_of` and `ingested_at <= as_of`.
5. Preserve the first persisted payload for a canonical URL. Later edited pages must not rewrite history at the original publication time.
6. Reuse one shared alpha-LLM config resolver. No duplicate precedence or secret logic.
7. Use one deterministic JSON request per article, bounded retries, strict validation, and content-hash caching.

## Source Contract

| Source | Transport | Publication evidence |
|---|---|---|
| CafeF | RSS | RSS `pubDate` |
| Vietstock | RSS | RSS `pubDate` |
| BaoChinhPhu | RSS | RSS `pubDate` |
| SBV | HTML | JSON-LD/meta/`<time>`/source-specific visible date |
| VCBS | HTML | Report/listing timestamp |
| SSI | HTML | Report/listing timestamp |
| VNDirect | HTML | Report/listing timestamp |
| VnEconomy | RSS | RSS `pubDate` |
| BaoDauTu | RSS | RSS `pubDate` |
| TinNhanhChungKhoan | RSS | RSS `pubDate` |

Timestamp rules:

- Normalize to timezone-aware UTC; interpret timezone-free Vietnamese values as `Asia/Ho_Chi_Minh`.
- Date-only HTML values become `23:59:59` ICT with `timestamp_precision=date`; this prevents same-day use.
- Reject missing or impossible timestamps. Reject future minute/second timestamps beyond five minutes of clock skew; permit only the conservative end-of-day sentinel for a date-only value matching the local ingestion date.
- Persist `raw_published_at`; fetch article bodies only from the same source domain.
- Bound v1 to each configured feed/listing page; do not add recursive crawling or pagination. Use normalized article body when available, otherwise title plus source summary/listing excerpt.

## Canonical Parquet Schema

Use an explicit PyArrow schema:

| Column | Type | Contract |
|---|---|---|
| `source` | string | Non-null registry name |
| `title` | string | Non-empty |
| `summary` | string | Empty allowed |
| `text` | string | Non-empty normalized LLM input |
| `url` | string | Canonical, non-null, unique |
| `published_at` | timestamp[us, UTC] | Source publication time |
| `available_at` | timestamp[us, UTC] | `published_at + 15 minutes` |
| `ingested_at` | timestamp[us, UTC] | Completed observation of stored text |
| `raw_published_at` | string | Original source value |
| `timestamp_precision` | string | `second`, `minute`, or `date` |
| `payload_sha256` | string | Normalized source payload hash |
| `parser_version` | string | Parser provenance |
| `sentiment_score` | float64 nullable | Range `[-1, 1]` |
| `hawkish_dovish_scale` | float64 nullable | `-1` dovish, `0` neutral, `1` hawkish |
| `key_entities` | list<string> nullable | Normalized, stable-order, deduplicated |
| `llm_status` | string | `pending`, `succeeded`, or `failed` |
| `llm_model` | string nullable | Successful model |
| `llm_prompt_version` | string nullable | Cache namespace |
| `llm_input_sha256` | string nullable | Model/prompt/text hash |
| `llm_attempted_at` | timestamp[us, UTC] nullable | Latest extraction attempt provenance |
| `llm_extracted_at` | timestamp[us, UTC] nullable | Successful extraction provenance |
| `llm_error_code` | string nullable | Sanitized category only |

Accept the existing seven-column schema, derive deterministic defaults/hashes, mark rows `pending`, validate, then atomically write the expanded schema. Local `data/macro_news.parquet` is currently absent; migration still covers deployed copies.

## LLM Contract

- Macro-news default config: `C:\Users\GHC\llm_configs\alpha_llm.json`; `OMEGA_ALPHA_LLM_CONFIG_PATH` overrides it, then existing `OMEGA_LLM_*` field fallback applies. Existing alpha-evolution callers do not opt into this fixed default, preserving offline behavior.
- Resolve one `{provider, api_key, base_url, model}` object. Expected model: `cx/gpt-5.6-terra`; endpoint: `http://localhost:20128/v1/chat/completions`.
- Require a non-empty API key for `openai-compatible`; send it only in `Authorization`. Never log or persist secrets.
- Send one `temperature=0` JSON-mode request per article using supplied title and a deterministic bounded text prefix; hash the exact prompt input.
- Define `sentiment_score` as negative `-1`, neutral `0`, positive `1`; define `hawkish_dovish_scale` as dovish `-1`, neutral `0`, hawkish `1`. Validate finite bounds and normalize/deduplicate named people, organizations, policy instruments, macro indicators, and locations in `key_entities`.
- Retry transport errors, HTTP 429, HTTP 5xx once. Preserve ingestion and prior successful extraction on failure.
- Cache successful output by model, prompt version, and normalized input hash.
- Treat the first successful extraction as immutable. Model or prompt changes require an explicit new dataset version, not an in-place historical rewrite.

LLM-derived fields are PIT-eligible only when `available_at`, `ingested_at`, and `llm_extracted_at` are all `<= as_of`.

## Planned File Changes

### `src/omega/data/macro_news_pipeline.py` - modify

- Replace the loose column list with the explicit Arrow schema and legacy migration.
- Assert the exact ten-source registry and supported adapter kinds.
- Harden malformed RSS handling while requiring publication evidence.
- Add source-specific HTML timestamp/body extraction using installed BeautifulSoup.
- Canonicalize URLs, enforce same-domain links, normalize text, calculate hashes.
- Preserve the first persisted URL payload; report later hash conflicts without backdating edits.
- Lock read/migrate/merge/validate/temp-write/`os.replace`; read back and validate the staged Parquet.
- Preserve the destination on all-source failure, validation failure, or write failure.
- Isolate remote failures per source.
- Add `query_as_of()` so raw rows require publication, availability, and ingestion timestamps no later than `as_of`; mask all extraction outputs/status/provenance until the relevant attempt or success timestamp is PIT-eligible.

### `src/omega/core/alpha_llm_config.py` - add

- Move alpha external-config validation and effective resolution from `scripts/run_hybrid_alpha_evolution.py`.
- Preserve canonical absolute outside-repo path checks, including traversal, symlink/junction, and Windows case variation rejection.
- Accept an optional caller-supplied default path; macro news supplies `alpha_llm.json`, while alpha evolution retains its current env-path-only behavior.
- Return one immutable effective config consumed by alpha evolution and macro-news extraction.

### `scripts/run_hybrid_alpha_evolution.py` - modify

- Import and re-export the shared resolver so current callers/tests retain behavior.
- Delete the duplicate private loader.

### `src/omega/data/macro_news_llm.py` - add

- Implement `MacroNewsLLMExtractor` with injected HTTP session and clock.
- Build deterministic prompts from title plus normalized article text.
- Validate strict OpenAI-compatible JSON responses.
- Enrich only `pending` or `failed` rows; never overwrite a successful extraction.
- Snapshot under lock, release the lock for network calls, reacquire, then merge only when input hashes still match.
- Validate the complete staged table before atomic replacement.

### `scripts/fetch_macro_news.py` - add

- Minimal orchestration: ingestion first, enrichment second.
- Support `--output` defaulting to `data/macro_news.parquet`, `--skip-llm`, and `--llm-limit` for bounded smoke/recovery runs.
- Exit non-zero for store/config/invariant failures; summarize source/article remote failures without secrets.

### `tests/test_macro_news_pipeline.py` - modify

- Assert the exact ten-source registry and adapter kinds.
- Cover RSS and source-specific HTML fixtures, including timezone-free and date-only publication values.
- Reject missing, malformed, or future publication timestamps and cross-domain article links.
- Verify per-record `ingested_at` is captured after stored text retrieval.
- Verify canonical URL deduplication, first-payload immutability, and hash-conflict reporting.
- Verify legacy-schema migration, explicit Arrow dtypes, lock contention, staged-read validation, and destination preservation on failure.
- Verify `query_as_of()` excludes future raw rows and masks LLM fields not yet extracted at the requested instant.

### `tests/test_alpha_llm_config.py` - add

- Cover fixed default path, environment path override, file-over-environment field precedence, and environment fallback.
- Preserve rejection tests for relative, in-repo, traversal, symlink/junction, and Windows case-variant paths.
- Confirm `cx/gpt-5.6-terra` plus `http://localhost:20128/v1` resolves without exposing `api_key` in logs or representations.

### `tests/quant_test_infinite_evolution.py` - modify

- Point existing alpha-config regression tests at the shared resolver/re-export.
- Prove alpha evolution receives the same effective config after duplicate loader removal.

### `tests/test_macro_news_llm.py` - add

- Mock the OpenAI-compatible response and assert endpoint, bearer header, JSON mode, `temperature=0`, timeout, and deterministic prompt payload.
- Validate score bounds, finite numbers, required keys, stable entity normalization, malformed JSON rejection, and sanitized error codes.
- Cover one retry for transport, HTTP 429, and HTTP 5xx; no retry for permanent HTTP 4xx or schema errors.
- Verify successful-result caching, immutable successful rows, failed-row recovery, concurrent input-hash conflict rejection, and atomic destination preservation.
- Exercise CLI ordering, `--skip-llm`, `--llm-limit`, non-zero invariant failures, and secret-free summaries.

## Ordered Implementation Tasks

1. **Freeze contracts** - Add failing schema/source/timestamp tests before runtime changes. Verify: new assertions fail against the seven-column baseline.
2. **Harden collection adapters** - Live-check each configured endpoint, capture minimal fixtures, then implement source-specific RSS/HTML publication/body extraction with canonical same-domain URLs. Verify: fixture adapters return UTC records; invalid timestamps return none.
3. **Make storage PIT-safe** - Add schema migration, `FileLock`, immutable merge, staged read-back, atomic replacement, and `query_as_of()`. Verify: fault-injection tests retain the original file byte-for-byte.
4. **Extract shared LLM config** - Move resolver logic to `src/omega/core/alpha_llm_config.py`, add the fixed external default, then re-export from the alpha script. Verify: old precedence/security tests plus new default-path tests pass.
5. **Implement deterministic enrichment** - Add strict request/response handling, bounded retry, hashes, cache rules, and immutable successful results. Verify: mocked HTTP tests cover success and every retry/validation branch.
6. **Add minimal orchestration** - Implement `scripts/fetch_macro_news.py` with ingestion-first execution and recovery flags. Verify: CLI tests prove LLM failure cannot remove or block collected news.
7. **Run focused regressions** - Execute macro, news, sentiment, and alpha-config suites. Verify: no existing public import or alpha resolver behavior regresses.
8. **Run isolated smoke checks** - Write only to `.ly_state/session/tmp`, inspect Parquet schema/PIT invariants, then delete smoke artifacts. Verify: ten source attempts are reported and one bounded LLM extraction succeeds when the local endpoint is available.

## Verification Commands

Run from `C:\Users\GHC\repos\OMEGA_QUANT` after L2 implementation:

```powershell
python -m pytest tests/test_macro_news_pipeline.py tests/test_alpha_llm_config.py tests/test_macro_news_llm.py tests/quant_test_infinite_evolution.py -q
python -m pytest tests/test_macro_pipeline.py tests/test_free_news_rss_scraper.py tests/test_news_aggregator.py tests/test_news_aggregator_scrapers.py tests/test_llm_sentiment_scoring.py -q
python scripts/fetch_macro_news.py --output .ly_state/session/tmp/macro_news_smoke.parquet --skip-llm
python scripts/fetch_macro_news.py --output .ly_state/session/tmp/macro_news_smoke.parquet --llm-limit 1
```

Inspect the smoke artifact with `pandas.read_parquet()` and assert: 22 exact columns, unique non-null URLs, UTC timestamp dtypes, `available_at == published_at + 15 minutes`, precise timestamps not later than `ingested_at`, score bounds, and no secret-bearing column. Delete the artifact after review.

Individual remote-source failures may be reported. The live smoke fails the gate when no source yields a valid article, a store invariant fails, or the required local LLM call is unavailable. Never target `data/macro_news.parquet` during verification.

## Done When

- The registry contains exactly CafeF, Vietstock, BaoChinhPhu, SBV, VCBS, SSI, VNDirect, VnEconomy, BaoDauTu, and TinNhanhChungKhoan.
- Every row has publication evidence, UTC timestamps, normalized text, a canonical unique URL, and immutable first-observation provenance.
- `data/macro_news.parquet` uses the explicit 22-column Arrow schema and migrates the existing seven-column shape deterministically.
- Raw as-of reads require `available_at` and `ingested_at`; LLM fields remain hidden until `llm_extracted_at <= as_of`.
- Config resolves `openai-compatible`, `cx/gpt-5.6-terra`, and `http://localhost:20128/v1`; secrets never enter Parquet, logs, exceptions, or test output.
- LLM output contains validated `sentiment_score`, `hawkish_dovish_scale`, and normalized `key_entities`; failure never corrupts ingestion or a prior success.
- Focused tests, regressions, schema assertions, and isolated smoke checks pass before independent L3 audit.

## Repo-Local Source Evidence

Role frontmatter parsed first:

- `.agents/agent/planning-architect.md` - `name=planning-architect`, `role_id=26`, `tier=3`, `platform=Codex`, skills `plan-writing`, `architecture`, `database-design`, `api-patterns`, boundary `planning-only, non-audit, no production code`.

Required repo-local skills read, with no other authoritative skill source:

- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`

Repo-local protocol and implementation context read or searched:

- `.agents/AGENTS.md`
- `src/omega/data/macro_news_pipeline.py`
- `tests/test_macro_news_pipeline.py`
- `src/omega/data/macro_pipeline.py`
- `tests/test_macro_pipeline.py`
- `src/omega/data/news_rss_scraper.py`
- `src/omega/data/news_aggregator.py`
- `scripts/fetch_news_sentiment.py`
- `scripts/run_sentiment_enrichment.py`
- `tests/test_llm_sentiment_scoring.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`
- `tests/test_free_news_rss_scraper.py`
- `scripts/run_hybrid_alpha_evolution.py`
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py`
- `tests/quant_test_infinite_evolution.py`
- `tech-decisions.md`
- `requirements.txt`
- `setup.cfg`
- `.ly_state/session/implementation_plan_macro_news.md`

External task input checked without emitting its secret value:

- `C:\Users\GHC\llm_configs\alpha_llm.json` exists with `provider=openai-compatible`, `model=cx/gpt-5.6-terra`, `base_url=http://localhost:20128/v1`, and a non-empty `api_key`.

Forbidden-path scan result: **PASS**. Zero role or skill files were read from Antigravity scratch, OpenClaw skills, `C:\Users\GHC\.agents`, or Codex memory. None were authoritative. All five authoritative role/skill files resolve under the supplied `REPO_AGENT_ROOT` or `REPO_SKILL_ROOT`.

## L3 Boundary

- This document is planning output only under `.ly_state/session/`.
- No production source, test, gate, config, or dataset file was modified.
- L1 must resolve the nine-named/ten-requested source mismatch before L2 dispatch if BaoChinhPhu is not the intended tenth source.
- L2 implements and records test evidence; a different Codex L3 audit role reviews PIT, security, scope, and SoD before approval.
