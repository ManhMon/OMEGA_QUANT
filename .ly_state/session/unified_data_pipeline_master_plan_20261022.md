# Master Plan: Unified Data Pipeline and Deprecation Cleanup

- **Date**: `2026-10-22`
- **Role**: `15 data-engineer` — L4 implementation planning; no approval authority.
- **Gate**: `GATE_UNIFIED_DATA_PIPELINE_AND_DEPRECATION_CLEANUP_20261022`
- **Session**: `l4_role15_unified_data_pipeline_plan_20261022`
- **Source baseline**: `91afe560b9d0e7439de83d13c632350707ee2e0e`
- **Observation cutoff**: `2026-10-22T02:11:03Z`
- **Delivery**: Plan and packaging specification only. No production pipeline, scheduler, endpoint, UI change, script retirement, data migration, or gate approval is implemented by this document.
- **Companion specification**: `.ly_state/session/unified_data_pipeline_package_20261022.json`.

## 1. Goal, non-goals and decisions

Provide one operator execution contract for market OHLCV, financial statements, news and market flow; one quality-report envelope; one durable run history; an opt-in scheduler; backend controls; IngestTab operations. Unification means shared dispatch, validation policy and evidence, not one schema or a provider rewrite.

Retain hardened existing engines and provenance authorities. Add no Airflow, Celery, Redis, DuckDB, APScheduler, or new provider dependency. Existing stdlib SQLite, zoneinfo, installed Arrow/pandas/FastAPI and repository clients suffice. Native Windows Task Scheduler can drive a short-lived due-dispatch command; no scheduler is installed during this task.

The first six scoped scripts are the six **public-execution retirement candidates** below. Their reusable functions and signed publication machinery remain in place until migration parity permits movement. No deletion by filename or static unimported status. The other three scripts are separately classified, not silently counted as part of the six.

Decisions that are not yet production authorization:

- Introduce a new explicit multi-domain CLI rather than silently changing the deprecated market-only alias.
- Keep live news, historical collection and macro extraction distinct operations. Historical collection does not become verified investable history.
- Make macro LLM extraction explicit opt-in. Ingestion failure and extraction failure remain distinguishable; do not hide paid external work behind a default refresh.
- Keep financials/flows independent of a freshly published market file. They need a validated frozen universe/configuration, not necessarily new OHLCV rows.
- A staged manifest is not a signed market provenance receipt. Never confer historical/PIT authority through orchestration metadata.
- Source code currently makes SSI canonical and VCI reference-only. Repo-local domain skill describes DirectVCIClient as the VCI ingestion SSOT. Preserve current canonical provider ordering; reconcile that documentation difference in P0. No new vnstock/VCI network call site.

## 2. Verified baseline and coverage limits

Graph artifact `.ly_state/session/graph_evidence_l4_role15_unified_data_pipeline_plan_20261022.json` SHA-256 `127d18ea3aa9e5ffe7b6ed6d05f55bb73c686d8bee1fe8c07e2369f71883a403`; contract `.ly_state/session/anti_drip_contract_l4_role15_unified_data_pipeline_plan_20261022.json` SHA-256 `fbfcc057561f7ecd6a5d09909240acb474c351aabecb75dc9b99bdca6cd7079a`. Both raw-byte hashes matched. HEAD matched the supplied revision; all 11 scope-file raw-byte hashes matched the graph snapshot.

Graph reports one complete impact batch, 11 requested/covered scope paths, `total_impacted=76`, 40 distinct names in `blast_radius.impacted_files`, `truncated=false`. These numbers are preserved as reported; neither the count's entity semantics nor an exhaustive 76-file source inspection is inferred. No external graph database is required. A delegated stale-graph/archive inference was rejected after exact-root verification: the bound batch-loader script is a full implementation, not an archived stub.

The worktree already contained unrelated modifications. No stash, checkout, reset, commit, dependency installation, or ingestion is part of this delivery. Do not alter contracts, sidecars, prompt artifacts, `.ly_state/session/audit_reports/`, or `.ly_state/session/phase_gates.json`. Baseline mode has no required finding IDs and requires no Root-Cause Architectural Sweep JSON.

Snapshots predate/equal the cutoff. Plan derivations, advisor completion timestamps and test execution occur later; they are not backdated observations or historical market evidence. Advisor requests use the mandated cutoff, pre-cutoff snapshot observations, and proposed instructions separately. Saved responses are advisory, not independent L3 receipts or approvals.

## 3. Existing source inventory

| Scoped source | Existing responsibility and contract | Required disposition |
|---|---|---|
| `scripts/update_market_data.py:115-148`, `:1024-1098`, `:2730-3209` | 14-column canonical OHLCV; SSI canonical, VCI reference/reconciliation; overlap/anomaly/refetch and lifecycle gates; signed release receipts, publication ownership and pointer. CLI includes dry-run/start/end/output/canonical/symbols/refetch/lifecycle controls. | Reuse `run_updater`, validator and publication kernel. Preserve direct imports and market-only consumers. Do not bypass release gates. |
| `scripts/fetch_financial_statements.py:38-56`, `:113-138`, `:274-343` | `data/financial_statements_2015_now.parquet`; 13-column Arrow schema, six-column primary key; quarter/year records, raw cache, PIT availability, atomic output; market-path/output/active-only flags. | Financial stage preserves schema, source snapshots, revisions, universe selection and original failure semantics until an explicit compatibility change. |
| `scripts/run_macro_news_pipeline.py:28-39`, `:43-74`, `:100-181` | Explicit aware as-of and PIT universe; registry-enabled source collection; raw-first records and optional LLM extraction; macro raw, LLM and link parquet outputs plus run manifest. | Raw ingestion and extraction are separately visible substages. Preserve source-health, revision IDs, raw evidence and extraction error. |
| `scripts/fetch_news_sentiment.py:22-53`, `:160-269`, `:343-448`, `:451-743` | Live news v10 12-column output, quarantine and checkpoint; separate historical CAFEF shards/checkpoint/manifest and resume. Historical evidence reports `collection_not_investability`, `pit_verified=false`, `full_history_verified=false`. | Separate `news_live` and explicit historical collection; preserve incomplete/partial statuses. Never attach market release authority to caller/live records. |
| `scripts/update_market_flow.py:30-49`, `:157-297`, `:320-498` | Foreign/proprietary/derivatives schemas, CafeF/DChart retrieval, per-symbol and consolidated parquet, locks/atomic merge/backups; retrieval-time availability and unverified historical PIT; kind/symbol/universe/year/worker/dry-run flags. | Independent flow stage; no OHLCV coercion or historical certification by successful fetch. |
| `scripts/update_recent_portfolio_data.py:5-79` | Top-level five-symbol VCI retrieval and direct canonical overwrite; no reusable CLI; per-symbol errors can continue. | Never import for side effects. Replace required subset-selection behavior through the hardened market stage; block old direct-writer invocation at cutover. |
| `scripts/ingest_all_market_data.py:12-39` | Already deprecated positional ticker/start/end/output compatibility CLI; delegates exclusively to `update_market_data.main`. | Preserve market-only behavior. Do not change it into an unannounced all-data refresh. |
| `scripts/batch_market_loader_resume.py:1-498` | Active legacy parallel batch/checkpoint/resume loader in the verified checkout. | Exclude from routine schedule. Inventory checkpoints and external callers; migrate any needed recovery through the same validator/publication boundary. No implicit permission to archive/delete it in this six-script task. |
| `scripts/migrate_news_parquet.py:16-36` | Explicit live-news schema migration with row-count/schema checks and replacement. | Offline operator action, not daily ingestion; staged backup, target version and deterministic validation required before future production use. |
| `src/omega/api/routes/control.py` | Existing control/task and lifecycle contracts. | Add unified operations without changing existing response envelopes or routing old jobs to a different pipeline. See Section 9. |
| `omega-ui/src/modules/control_center/tabs/IngestTab.tsx` | Existing ingestion controls and task lifecycle. | Preserve supported actions, add server-authoritative unified controls. See Section 11. |

This inventory does not certify that current runtime failure branches are correct. Existing hazards become implementation acceptance requirements; no plan-only defect is silently declared fixed.

## 4. Runtime package specification (proposed, not created)

Keep few modules; no generic plugin registry, workflow factory, new ORM, or second provider layer.

| Proposed path / existing integration | Responsibility |
|---|---|
| `scripts/run_data_pipeline.py` (new) | Thin CLI: parse strict options, invoke service, emit run ID/summary, exit nonzero on failed/cancelled/incomplete requested work. Includes explicit `run`, `validate`, `resume`, `dispatch-due` operations. |
| `src/omega/data/pipeline.py` (new) | Fixed allowlisted stage map, normalized RunSpec, durable run/step ledger, shared conflict lock/fencing, checkpoint binding, cancellation and publication coordination. Import safe existing engines; extract only when necessary to avoid script import side effects. |
| `src/omega/data/pipeline_quality.py` (new) | Dataset-specific rule selection and common quality envelope; delegate numerical/data checks to `src/omega/data/sanitizer.py` and existing authoritative market validator. Do not create another sanitizer implementation. |
| `src/omega/data/pipeline_scheduler.py` (new only when P5 is implemented) | Calendar-aware due calculation and transactionally unique dispatch using the same pipeline service. No infinite in-process scheduler or per-ASGI-worker timer. |
| Existing `src/omega/api/routes/control.py` and existing task service | Strict DTOs and HTTP adaptation. Provider I/O and large parquet work do not run synchronously on the ASGI event loop. |
| Existing IngestTab and discovered frontend API/types | Unified run controls and summary. Extend existing client/types rather than hardcoding duplicate transport code. |
| Proposed focused Python and UI test files | Offline fixtures, fault-injection and API/UI contracts listed below. New runtime source/test paths outside the original 11 require explicit scope expansion before coding. |

Version the runtime package with source commit plus installed dependency-lock digest, validation-rule version and schema versions. Inventory non-secret environment names only; read secret values at runtime using existing configuration. No credentials, raw URLs with userinfo, user-supplied environment overrides, or provider payload bodies in packaging metadata.

Minimum run artifacts under a fixed repository-local operator root:

```text
.ly_state/session/data_pipeline_runs/<run_id>/
  request.json       normalized inputs; actor/trigger/config identity
  manifest.json      immutable durable dataset/partition/source/hash inventory
  quality.json       rule versions, counts, bounded redacted examples
  events.jsonl       bounded/redacted append-only events; sequence numbers
  staging/           private run-owned candidate partitions
```

A stdlib SQLite run ledger and a versioned current-generation pointer live under the same configured local state root; requests never choose arbitrary roots. State files are strict UTF-8, no BOM, LF; strict JSON rejects duplicate keys and non-finite constants. Path validation checks regular files, ownership, symlinks/reparse points, size limits and containment before reading or publishing.

### RunSpec and stage graph

Fixed stage IDs: `market`, `financials`, `news_live`, `macro_news`, `flows`. `news_historical` and `migrate_news` are explicit operator operations, excluded from daily defaults. Macro extraction is an explicit option requiring configured credentials; no secret value enters RunSpec.

RunSpec includes version, mode (`incremental`, `backfill`, `validate`), nonempty unique stage IDs, date interval, aware decision cutoff, frozen universe identity or bounded explicit symbols, dry-run, bounded workers, trigger and actor identity. Defaults never silently select an active-only universe for historical backfills. Configure at most 5 stages, 2,000 symbols, 5 workers; dates within authoritative calendar coverage. Bounds are proposed acceptance values, not additions to old CLI semantics. Unsupported calendar years fail closed, not weekday-only fallback. Large historical collections remain explicit operators with separate bounded partition contracts.

Preflight validates configuration/provider readiness, calendar coverage, immutable universe and lifecycle snapshot, input/output schemas, disk space budget, checkpoint version, trusted receipt requirements and overlapping publication ownership. Invalid input causes no provider calls or state mutation beyond a redacted rejected-request event.

Each selected stage depends on a frozen validated universe/config snapshot. News extraction additionally depends on raw macro records from this run. Do not invent a financial-row dependency on market prices; if a legacy financial adapter derives its universe from market parquet, bind the existing published market generation explicitly. Stages execute sequentially first; add stage concurrency only after measured need and conflict proofs. Worker parallelism stays inside proven bounded engines.

## 5. Data quality and PIT contract

One report envelope, separate domain schemas. Use `DataSanitizer`, `DataValidator`, `ValidationIssue`, `DataQualityChecker` from `src/omega/data/sanitizer.py`; compatibility modules remain exact re-exports. For market publication, its existing validator, lifecycle/reconciliation gates, keys and receipts remain authoritative even if the common quality envelope reports pass.

Quality envelope fields: schema/rule version, run/stage/dataset, source/config/input hashes, schema fingerprint, row/partition counts, duplicate/null/non-finite counts, date/availability bounds, PIT status (`verified`, `unverified`, `violated`), coverage/freshness result, blocking rules, warnings, bounded redacted examples, output hash and validation timestamp. Unknown/missing rule status is not pass. Empty expected output fails unless an explicit calendar/no-new-data result is proven. A count alone cannot certify source completeness.

| Domain | Blocking rules | Provenance / warning policy |
|---|---|---|
| Market | Exact 14-field schema; required finite positive OHLC, nonnegative integral volume, high/low consistency, unique ticker/date, known exchange, monotonic dates, market release/lifecycle/reconciliation gates. | Normalize known provider scale exactly once and record `VND_FULL`; never use `max(close)>1000` as a universal proof. Legitimate sub-1000 Dong values are not rejected by magnitude alone. Corporate actions and illiquid/delisted gaps require lifecycle-aware evidence, not blanket outlier deletion. |
| Financials | Preserve exact 13 fields/six-key uniqueness and period/report ordering; finite values with dataset-specific signed/zero allowances; revision IDs and available-at semantics. | No estimated filing date silently becomes verified public availability. Missing or retrieval-only historical evidence remains unverified and excluded from strict PIT consumers. |
| Live news | Preserve v10 schema, record/article/revision identity, aware publication/availability, checkpoint/quarantine integrity and bounded text. | Ingestion/retrieval timestamps do not confer historical investability. Article revision availability must not move backwards. |
| Historical news | Validate each raw/projected shard digest, canonical universe/date/source/parser binding, duplicate pages and terminal manifest status. | Preserve `pit_verified=false` and collection-only semantics until independent evidence supports a different contract. Partial collection is never full-history verified. |
| Macro news/extraction | Raw evidence committed before derived extraction; deduplicate by source/revision; validate source registry, universe binding, extraction schema and links. | Derived availability at least the maximum availability of every input. Extraction/model version is provenance, not proof of contemporaneous knowledge. |
| Flows | Per-kind schema, finite signed cash fields where legitimate, quantities/units, unique instrument/time/source, strict merge and partition coverage. | `historical_pit_verified=False` persists. Intraday data is not treated as final EOD merely because the scheduler fired. |

Strict eligibility: `event/as_of <= available_at <= decision_time`, explicit UTC-aware instants and inclusive equality. A backfilled observation retrieved today may carry a verified earlier source-publication timestamp only when that evidence exists; otherwise use actual retrieval availability and mark unverified historical provenance. Never let a caller supply a truthy verified flag or reuse a trusted historical signature for unverified rows. Preserve prior revisions and their actual availability.

Trading calendar is exchange-aware and includes official holidays; current repository coverage is finite (2015–2027), not indefinite. 15:30 ICT is the proposed scheduling boundary, not a universal exchange-close or source-availability timestamp. Source-specific close/publication lag governs eligibility. Test cutoff equality, holidays, lunch/auction distinctions where relevant, delayed publications and unsupported years.

## 6. Durability, atomicity, failure and concurrency

1. Admit a normalized run under a unique request key. Same actor/key/body returns the same run; same key/different body conflicts. Acquire shared dataset publication ownership used by CLI/API/scheduler/compatibility entrypoints.
2. Fetch to run-private immutable partitions. Reuse provider timeout/payload/429 limits; impose a total run deadline. Do not multiply retries across adapter and orchestrator. Never retry permanent validation, authorization or integrity failures.
3. Validate every selected artifact and source binding. Persist/fync artifacts and immutable manifest before checkpoint progress. A completed unit is identified by input/universe/source/config/schema/code hashes plus partition and content hash.
4. Enter `prepared`, then publish through the existing market signed-release protocol and domain-specific safe publishers. Holding a DB transaction does not make file replacement atomic with it. Record intended predecessor/published hashes and recover by inspecting the durable pointer/manifest, not by replaying blindly.
5. For cross-dataset consistent readers, one generation pointer selects a complete manifest mapping to immutable dataset versions. Existing readers that still open independent fixed paths are not magically consistent: until all relevant readers adopt the pointer, claim only per-dataset atomicity and report partial publication explicitly. Cross-generation consistency is a separate required consumer-migration work package.
6. Use same-filesystem temporary files, flush/fsync, atomic replace and platform-appropriate directory durability. Preserve last-known-good generations; Windows handle sharing and replacement failures need explicit tests. Do not delete pre-existing files or another run's temporary artifacts.
7. Fencing token/generation prevents stale workers from publishing after ownership loss. Kernel-owned lock alone is not permission for a timed-out remote worker to continue. Serialize rollback, publish and prune through the same ownership boundary. Live-owner locks are never deleted based solely on age/PID.
8. Ledger commit failure after pointer replacement is an ambiguous commit: inspect pointer/content hashes, reconcile to published or recoverable failure, never silently claim rollback. Manifest publication failure before pointer replacement leaves the prior generation visible. Cross-store transactions are not promised.
9. Cancellation is cooperative at bounded work boundaries; accepted cancellation is not completed cancellation. A request after commit returns terminal conflict/current success; do not report a committed generation cancelled. A crash can resume only compatible durable units; incompatible/corrupt checkpoints fail before writes.
10. Rollback first disables schedule dispatch, acquires ownership, verifies retained artifacts/receipts, switches the pointer to a known valid generation, records a new rollback event and checks readers. Rollback never erases provenance or replays committed network work. Keep old reader/CLI contracts available until rehearsal succeeds.

Proposed terminal run states: `completed`, `failed`, `cancelled`; nonterminal states `queued`, `running`, `cancelling`. Step state exposes skipped/no-new-data separately. `completed` requires all requested steps and required validation/publication evidence; HTTP acceptance, zero provider rows, a subprocess exiting early or extraction-only success never suffices. Use progress from completed work units, not elapsed-time guesses.

## 7. Exactly six retirement candidates and compatibility matrix

| Candidate public execution | Unified replacement | Compatibility evidence before warning/delegation |
|---|---|---|
| `scripts/update_market_data.py` | `run_data_pipeline.py run --stages market` | Preserve market CLI argument meanings, signed receipt format/keys, dry-run versus publish, lifecycle/refetch options, output contract, direct-import API and canonical readers. Keep engine functions initially. |
| `scripts/fetch_financial_statements.py` | `--stages financials` | Freeze fixture outputs, raw cache/revisions, market-path/universe selection, active-only meaning, key/order/PIT/schema and failure exit codes. |
| `scripts/run_macro_news_pipeline.py` | `--stages macro_news` plus explicit extraction | Preserve as-of/universe/registry flags, ingest-only behavior, raw-first failure handling, source-health/manifest, link and extraction schema. |
| `scripts/fetch_news_sentiment.py` | `--stages news_live`; explicit historical operation | Preserve both modes without conflating outputs; checkpoint/resume/workers/listing/source options and incomplete-manifest semantics; direct-import compatibility. |
| `scripts/update_market_flow.py` | `--stages flows` | Map all/foreign/proprietary/derivatives variants, symbols/universe/year/worker/dry-run; per-kind output and retrieval-time availability. |
| `scripts/update_recent_portfolio_data.py` | `--stages market --symbols <explicit subset>` | Preserve required portfolio symbol selection, not unsafe in-place overwrite, hardcoded dates or silent per-symbol continuation. Never import this top-level script as an adapter. |

Retirement sequence: inventory imports/process launch sites/docs/external scheduled tasks; add offline parity fixtures; add shared ownership before switching any writer; convert public execution to warnings/delegation while keeping tested imports; migrate API/UI/native schedule callers; run opt-in shadow only against isolated staging; observe agreed operator window with zero old writer usage; rehearse rollback; independent L3 review; then separately authorize deletion. No silent removal date. Unknown external schedules/runbooks block deletion, not the plan draft.

The already deprecated `ingest_all_market_data.py` remains market-only. The active batch loader requires explicit owner disposition and checkpoint migration; it cannot remain an unsynchronized writer during unified cutover. `migrate_news_parquet.py` remains explicit/offline and must not run concurrently with publication. If changing these beyond compatible coordination exceeds scope, obtain the expanded change list before implementation.

## 8. CLI and process packaging contract

Examples describe future interfaces, not runnable commands in the current repository:

```text
python scripts/run_data_pipeline.py run --stages market,financials,news_live,flows --mode incremental --as-of <aware-ISO8601> --dry-run
python scripts/run_data_pipeline.py validate --run-id <id>
python scripts/run_data_pipeline.py resume --run-id <id>
python scripts/run_data_pipeline.py dispatch-due --now <aware-ISO8601>
```

A dry-run may fetch only when explicitly requested; default preflight performs no network, publication or scheduling changes. Split `plan`/preflight semantics from network shadow semantics in help text. Exit 0 only for the requested successful/dry-run validation contract; invalid arguments retain argparse's existing 2; operational failure/cancellation/incomplete work is nonzero. Each wrapper documents original exit-code compatibility before cutover. Log bounded structured redacted summaries; stdout run IDs are not proof of completion. Subprocess use, if needed during transition, is a fixed executable/argument array without `shell=True`; no request-supplied command, provider URL, path or environment patch.

## 9. Backend endpoints and compatibility

### Existing routes (preserve, do not silently repurpose)

Router prefix is `/api/v1/control` (`control.py:265`). The two SSE aliases are unprefixed routes on a separate router (`:266`, `:2773-2774`). There are 18 ordinary path decorators plus two SSE decorators, sharing 19 handlers.

| Method | Existing full path | Source anchor |
|---|---|---|
| POST | `/api/v1/control/pipeline-run` | `control.py:1939` |
| POST | `/api/v1/control/cancel/{job_id}` | `:1969` |
| POST | `/api/v1/control/ingest-data` | `:1994` |
| POST | `/api/v1/control/compute-alphas` | `:2023` |
| POST | `/api/v1/control/optimize-portfolio` | `:2050` |
| POST | `/api/v1/control/run-backtest` | `:2077` |
| POST | `/api/v1/control/kill-switch` | `:2104` |
| POST | `/api/v1/control/rebalance` | `:2133` |
| GET | `/api/v1/control/tasks/{job_id}` | `:2284` |
| GET | `/api/v1/control/pipeline/dag` | `:2292` |
| GET | `/api/v1/control/status` | `:2311` |
| GET | `/api/v1/control/strategy/backtest/{strategy_id}` | `:2332` |
| GET | `/api/v1/control/receipts` | `:2468` |
| GET | `/api/v1/control/lakehouse-status` | `:2503` |
| GET | `/api/v1/control/dynamic-universe` | `:2640` |
| GET | `/sse/v1/pipeline/{job_id}/stream` | `:2773` |
| GET | `/sse/v1/tasks/{job_id}/progress` | `:2774` |
| GET | `/api/v1/control/optimization-bounds-preview` | `:2828` |
| GET | `/api/v1/control/ingest-scheduler/telemetry` | `:2947` |
| GET | `/api/v1/control/strategy-benchmarks` | `:3011` |

Existing `IngestDataRequest` (`:673-713`) allows symbols/ALL/VN703/VN30, sources vci/kbs/tcbs/macro/news, incremental/full_history/custom_range, start/end/as-of, dry_run/no_refetch/force_refresh and max_concurrency. Defaults include sources `[vci]`, end date `2023-12-31`, no explicit start; full_history supplies `2015-01-01`; custom_range needs a start. These defaults are compatibility constraints, not sensible new unified defaults. Do not silently reinterpret or delete old fields.

Current ingestion worker selects equity feeds; macro/news choices do not prove implemented domain ingestion. `dry_run` and `no_refetch` declarations do not establish worker behavior. Checkpoints count completed symbols but do not prove skip-on-resume. Existing task/SSE state is process-local; telemetry's cron/auto-refresh fields do not create a running scheduler. Lakehouse hardcoded dates/counts/lineage are not source validation evidence (`:2503-2635`, `:2947-3008`). These are current-source limitations to address explicitly during implementation, not fixed by this plan. Never dispatch mixed-source requests while labeling an unrelated first source as primary provenance.

### Proposed additive unified contract

All following paths are **new proposals**, not existing endpoints. Keep old DTOs/status strings/SSE aliases stable; adapt unified runs through a typed mapping rather than rewriting old clients. New run IDs map explicitly to old task IDs only when the existing task service owns the same work.

| Method / proposed path | Contract |
|---|---|
| POST `/api/v1/control/data-pipeline/runs` | Strict RunSpec plus actor-bound Idempotency-Key. Return 202 `{run_id,status:"queued",status_url}` only after durable admission. Repeated identical request returns the same run; different body/key reuse conflicts. |
| GET `/api/v1/control/data-pipeline/runs` | Bounded cursor pagination, allowlisted filters and actor authorization; list excludes raw payloads/secrets. Proposed limit default 20, maximum 100. |
| GET `/api/v1/control/data-pipeline/runs/{run_id}` | Durable state, timestamps, requested steps, completed units, publication/quality summaries and explicit cancellation/resume eligibility. Unknown/unauthorized records never leak paths. |
| GET `/api/v1/control/data-pipeline/runs/{run_id}/quality` | Same actor/identifier/ownership checks as detail; validated report only. Missing report distinguished from failed validation. No caller-supplied report path. |
| GET `/api/v1/control/data-pipeline/runs/{run_id}/logs` | Bounded sequence cursor/tail, redacted messages, truncation marker; no arbitrary file read. Proposed max 200 events per response, 4 KiB/event. |
| POST `/api/v1/control/data-pipeline/runs/{run_id}/cancel` | Idempotent cancellation request; 202 cancelling only when recorded. Already cancelled returns its state; already committed terminal work returns explicit conflict/current terminal state. Do not pretend acknowledged cancellation means rollback. |
| POST `/api/v1/control/data-pipeline/runs/{run_id}/resume` | Only eligible failed/interrupted work with exact input/config/schema/code/source binding. Durable new attempt linked to original; no mutation on invalid checkpoint or actor mismatch. |
| GET `/api/v1/control/data-pipeline/schedule` | Durable configured state, enabled=false by default, config version, next eligible run, last dispatch and readiness reason. This is not the old telemetry probe. |
| PUT `/api/v1/control/data-pipeline/schedule` | Strict profile/stages/local-time/enabled DTO, optimistic version/If-Match, authorization and change event. Reject arbitrary cron, URLs, command strings and paths. Save does not immediately run history. |

New endpoints consistently classify 422 malformed/range/type/unknown field; 401/403 authentication/authorization under existing policy; 404 unknown authorized identifier; 409 conflicting run/idempotency/config/resume/publication; 424 unavailable required provider/input/trusted evidence; 503 saturated executor/temporarily unavailable service; 500 unexpected internal failure with redacted stable error code. HTTP admission never reports provider failure as completed. Old endpoint status behavior stays unchanged unless separately versioned and tested.

Public DTOs use strict integer/boolean/list handling, finite numeric checks and field bounds; no bool-as-int, arbitrary provider URLs, paths, subprocess flags or environment maps. Apply identifier/actor/report/error validation symmetrically across list/detail/log/quality/cancel/resume. Do not introduce delete until retention/authorization semantics exist; pruning is a separately guarded operator operation. Preserve existing security/TOTP boundaries; new write operations may not weaken whatever control authentication is enforced.

Durable run history and scheduler coordination cannot rely on process dictionaries or SSE connection affinity. Existing SSE remains a bounded notification channel; durable status is the source of truth. A new run stream is optional, not required for initial release; bounded HTTP polling suffices. New publication/quality receipts are artifacts, not cryptographic verification unless checked against the trusted receipt verifier.

## 10. Auto-scheduler specification

Default disabled. Native Windows Task Scheduler may trigger `dispatch-due` periodically; application due calculation decides eligible work. Installation/enabling is an outward-facing operational action requiring separate authorization. On non-Windows deployments use the same CLI via the platform scheduler; no background timer in every API worker.

Persist schedule ID, enabled flag, named fixed daily profile, stages, `Asia/Ho_Chi_Minh` timezone, `15:30` local trigger, source readiness/lag rules, schema/config version and last eligible dispatched session. Proposed API allows a daily local time, not arbitrary cron/shell expressions. Setting a schedule does not retroactively launch history.

A dispatch obtains one leadership/fencing owner, computes latest eligible official exchange session at the supplied aware now, and inserts a unique `(schedule_id, session, config_version)` trigger and run atomically in SQLite. Existing trigger returns the same run. Restart catch-up selects at most the latest eligible session; no unbounded missed-day backlog. Respect unsupported calendar coverage, weekends/holidays and per-source lag. If provider freshness is not ready, record not-ready/retry eligibility rather than publish stale data as fresh. Persist retry bounds/deadline; no tight status polling.

Manual requests, legacy delegates and scheduled requests share dataset conflict ownership. Overlap cannot double-publish; duplicate dispatch returns the existing job or an explicit conflict. Pause affects future automatic dispatch only, not unrelated manual jobs; cancel is separate. Saving disabled config is durable before UI confirmation. Config updates use optimistic version/ETag conflict checks. Test process restart, two dispatchers, crash before/after unique insert, lock expiry, backward clock movement, cutoff equality and DST-safe UTC conversion even though Vietnam does not currently change clocks.

## 11. IngestTab controls

### Existing behavior and compatibility

`IngestTab.tsx:5-23` receives activeTasks/runOperation/onIngest/onStopIngest, source selection and force-refresh from its parent. It renders VCI/KBS/TCBS/MACRO/NEWS toggle buttons with aria-pressed, FORCE REFRESH, DISPATCH INGEST, STOP INGEST, scheduler/feed-health text and a dataset freshness/rows table. Running detection uses DATA_INGESTION plus RUNNING/PENDING/RECONNECTING. Dataset parsing checks identity/name/freshness; numeric display guards non-finite row counts (`:26-34`).

Telemetry is loaded with Promise.allSettled, AbortController and generation ownership on mount/running-state changes (`:8-21`). Current scheduler request passes `probe=true`; mounting the UI can therefore invoke provider probing. Preserve telemetry compatibility but make any live probe a clearly labelled explicit action in future implementation, not proof of a scheduler loop or a free passive read.

Dispatch currently submits `{sources,force_refresh}`. Do not pretend existing source toggles already execute all five domains. Preserve old actions while adding the unified panel; unsupported legacy source combinations must not falsely appear successful. Existing stop flow uses `/cancel/{job_id}` through client/hook; UI acknowledgement must not become terminal cancelled when the request failed. Parent props/types/client/hook changes are explicit dependencies outside IngestTab and require future scope expansion.

### Proposed unified controls and transitions

- **Stage selection:** accessible labelled checkboxes for market, financials, live news, macro news, flows. Default incremental daily profile; historical collection/migration not selected or scheduled. Provider identity displayed from backend capability metadata, not arbitrary text. No user-entered provider URL or path.
- **Range and cutoff:** incremental/backfill/validate mode, explicit ISO dates where needed, aware as-of input with ICT display and UTC value. Show authoritative calendar coverage; reject empty selection/start>end/unsupported years/naive cutoff before submit and mirror server errors. Preserve old date defaults only on the legacy path.
- **Preflight/validation:** separate no-network preflight action from fetch-enabled shadow/dry-run. Explain that existing script dry-run flags may fetch/write non-publication evidence; do not label them offline. Show planned stages, frozen universe, expected source readiness and required credentials by name only. Macro extraction has an explicit opt-in and cost/network notice.
- **Run:** submit once per normalized request with a stable idempotency key; disable while submitting or overlapping conflict, empty/invalid selection, unsupported provider mode or missing server capability. Handle 422 per-field errors, 409 existing-run/config conflict, 424 required-source/provenance failure, 503 backpressure and redacted network/internal errors. Never show completed on 202.
- **Active run:** durable run ID, state, per-step completed units, cancellation pending, resume eligibility, requested versus published generation and last update. Do not compute fictitious percentage from elapsed time or infer success from a receipt filename.
- **Quality and logs:** show blocking issues separately from warnings and unverified PIT, no-new-data and partial publication. Rows/freshness come from validated artifact metadata, not hardcoded historical coverage. Logs bounded by cursor/tail, explicit truncation and secret redaction; no unlimited client accumulation.
- **Cancel:** labelled button, confirmation of affected run/stages, pending disabled state; display cancellation-request acknowledgement separately. Failed cancel remains visible and polling continues. Terminal commit race displays server outcome, not a fabricated rollback.
- **Resume:** enabled only when server eligibility and exact checkpoint binding permit; explain incompatible config/schema/input and open a new linked attempt. Retry transient telemetry read does not resubmit ingestion.
- **Scheduler:** clearly separate configured schedule from feed-health telemetry. Read saved enabled/time/profile/version/next eligible session/readiness; edit with version check; explicit save and enable/disable confirmation. Initial disabled state, 15:30 ICT labelled as dispatch policy. Save errors leave prior saved value authoritative; pause does not cancel active work.
- **Lifecycle:** use existing SSE when it truly maps to the same task, otherwise poll only the active run at a bounded interval with backoff; stop on terminal state/unmount, abort outstanding reads and fence stale responses by generation/run ID. Manual refresh for terminal/history views. Do not add an always-on status loop.
- **Accessibility:** visible form labels, aria-pressed/checked, keyboard operation, focus restoration after errors/dialogs, aria-live polite status and concise error text. Loading/disabled reasons remain perceivable. No chart, visual redesign or new UI dependency is required.

Component acceptance: invalid empty/range/cutoff requests blocked, one submit despite double-click, 202 remains queued, reconnect uses durable state, stale run response ignored, abort on unmount, cancel failure never shows cancelled, terminal race handled, resume eligibility enforced, quality warnings/unverified PIT visible, bounded logs and scheduling save/version conflict preserve server truth. Preserve existing lifecycle and old control-operation tests.

## 12. Delivery work packages and owners

All runtime packages below are future work, not changes made in this delivery. Owners are role responsibilities, not gate approvers.

| Package | Owner / dependency | Deliverable | Acceptance before next package |
|---|---|---|---|
| P0 — inventory/contract freeze | Role 15; roles 6/8 for API boundaries | Exact six mappings, all callers and external tasks, schemas/flags/exit codes, source hashes, calendar/provider/consumer decisions, approved change scope. | Reproducible source inventory; direct-import and legacy DTO fixtures; no unexplained writer or falsely verified provenance. |
| P1 — quality envelope | Role 15; P0 | Existing SSOT validators reused; dataset policies, strict trust boundaries, quarantine/report schema. | Malformed/non-finite/schema/PIT/unit/lifecycle fixtures, no mutation on invalid input; no universal price-magnitude heuristic. |
| P2 — unified engine and publication | Role 15; P1 | Fixed service/CLI, durable ledger, owner/fencing, checkpoint/cancel/recovery and honest atomicity model. | Fault injection before/after every durable boundary; no partial-success claim, stale publish or incompatible resume. |
| P3 — six public-entrypoint delegates | Role 15; P2 | Compatible wrappers, unsafe portfolio path removed from execution, active batch disposition, migration exclusion, caller changes. | All flags/imports/output/exit branches parity-tested; one conflict boundary; no duplicate scheduled writer. |
| P4 — API and task integration | Role 8 backend; P2 | Additive typed endpoints and existing task lifecycle bridge; authorization and bounded log/report reads. | Request/error/idempotency/list/detail/cancel/resume symmetry; restart persistence; old endpoint tests unchanged. |
| P5 — native scheduler dispatch | Roles 9/15; P2/P4 | Durable disabled-by-default schedule, calendar-aware due dispatch, versioned config, enable/disable operations. | 15:30 ICT/holiday/publication-lag/restart/concurrency/catch-up tests; no per-worker scheduler. |
| P6 — IngestTab | UI implementation role; P4/P5 | Existing controls preserved, unified run/quality/schedule controls, accessible status/error/log handling. | Component/API contract tests, keyboard/focus/live-region checks, no duplicate submit or polling after unmount/terminal state. |
| P7 — controlled rollout and evidence | Roles 15/8/9; P0–P6 | Isolated shadow, parity/rollback rehearsal, versioned release evidence and operator handoff. | All scoped tests and related regression suites pass; bounded resources; separate independent L3 review. No self-approval. |

A global generation-pointer migration affects readers beyond the 11 paths. Inventory market/models/portfolio/quant/server and frontend lifecycle readers identified by the graph before claiming global consistency; request separate authorization for those changes. Preserve backward compatibility during staged rollout.

## 13. Adversarial acceptance matrix (planned runtime tests)

These are required future tests, **not results**. Plan-package mutation tests only prove the manifest records every dimension; they do not execute a pipeline, lock, provider, API or scheduler. Standing existing security regressions are retested separately in this delivery.

| # | Cases and oracle |
|---|---|
| 1 | None/empty/list/string/bool-as-int, NaN/Inf/-Inf, date/range/worker/ticker bounds; reject before any fetch/write. |
| 2 | Missing/file-as-directory/directory-as-file/traversal/symlink/reparse, invalid UTF-8/BOM/CRLF/duplicate JSON keys; no escape or mutation. |
| 3 | Duplicate/truncated/corrupt/cross-run shards and mismatched config/input/schema/source digest; no unsafe resume. |
| 4 | Empty unexpected output, provider/validator/subprocess failure; nonzero CLI and explicit failed state, never false completed. |
| 5 | Inject write/flush/fsync/replace/disk-full/cleanup/backup/pointer/DB commit failure; last-known-good or explicit recoverable ambiguous commit. |
| 6 | Event-after-availability, future-available revision, naive/mixed-zone timestamp, exact cutoff, derived max input availability, caller provenance forgery. |
| 7 | Vietnam holidays/weekend/unsupported years, 15:29:59/15:30:00/15:30:01 ICT, delayed source close/publication, lunch/auctions where applicable. |
| 8 | Zero/negative denominators, huge integers/finite overflow, precision and signed cash values; no NaN or incorrect generic domain ban. |
| 9 | Manual+schedule+legacy overlap, live/stale ownership, fencing expiry, cancellation/commit and prune/publish race; single durable publisher. |
| 10 | Known provider thousand-Dong conversion once; explicit VND_FULL metadata, legitimate small Dong price and mixed-scale rejection. |
| 11 | Delisted/frozen/new listing/relisting and historical universe snapshots; preserve lifecycle receipts and no current-universe leakage. |
| 12 | CLI flag smuggling, shell strings, URL/path/environment injection and malformed identifiers; allowlists and fixed argument arrays. |
| 13 | Missing/extra/renamed/mutated columns, invalid types/keys/version; no schema drift published. |
| 14 | Large dates/symbols/workers/payloads/logs/checkpoints, pagination and memory limits; bounded failure, streaming partitions. |
| 15 | Provider timeout/429/Retry-After exhaustion/cancel; finite attempts/deadline using fake clocks, no real retry waits. |
| 16 | Credential/userinfo/query-token leakage in logs/errors/artifacts; bounded redacted messages. |
| 17 | JEV role/risk/cycle/focus invalid types/ranges remain covered by existing routing tests; pipeline cannot weaken them. |
| 18 | Existing role/tier model allowlists unchanged; mandated advisor model retained; no catalog bypass. |
| 19 | Gate/session/role/risk/actor binding, idempotency body mismatch, wrong-run/cross-actor resume and replay; deny. |
| 20 | Canonical JSON, duplicate keys, graph/contract/source/advisor digest and manifest tamper; reject before use. |
| 21 | Temporary-file fsync/atomic replacement/cleanup failure, durable decision/run publication and rollback; explicit state. |
| 22 | Decision and pipeline owner locks, concurrent publishers, live/stale owners, crash/restart; no lock stealing. |
| 23 | Bounded retry, no silent data-source provenance upgrade, existing low-risk-only advisor fallback. |
| 24 | Secret-safe JEV/advisor task context, no auth request/printing, advisory receipts and URL redaction. |

Proposed exact new runtime test families: `tests/test_unified_data_pipeline.py`, `tests/test_unified_data_pipeline_quality.py`, `tests/api/test_unified_data_pipeline_contracts.py`, `tests/test_unified_data_pipeline_scheduler.py`, and a colocated IngestTab component test. File creation requires the future scope approval noted in Section 4. Tests isolate state with temporary directories and restore globals/environment; no production data or real provider network in unit runs. Fault injection must cover every error/rollback/durability/concurrency branch changed, not only a happy-path fixture.

## 14. Evidence package and verification

Current deliverables: this Master Plan; machine-readable proposal/source hashes; two hash-verifiable advisor responses; one package-integrity/adversarial-metadata test module; required L4 report; collection/focused/related JUnit evidence. No runtime module is created.

Plan-package tests bind role/gate/session/cutoff, all 11 source hashes, original graph/contract bytes, exactly six unretired candidates, disabled schedule, all 24 planned dimensions, model and advisor response/context hashes, report structure/LF and protected phase-gate digest. Mutation tests reject malformed input, path escape, wrong hashes, duplicate JSON keys, omitted dimensions and false runtime/retirement claims. They deliberately do not certify future pipeline behavior.

MCP architecture response: `.ly_state/session/l4_role15_unified_data_pipeline_plan_20261022_advisor_architecture.json`; correctness response: `.ly_state/session/l4_role15_unified_data_pipeline_plan_20261022_advisor_correctness.json`. Both status `advice`, model `cx/gpt-6-astra`, role 15, risk low, exact gate/session/cutoff, no provider error. Canonical response SHA-256 verification succeeded. The private caller recomputes sanitized context digests; response digests are authoritative, not the placeholder input digest. No authorization material is requested, printed or packaged. Advisor lacked source content; its metadata-only limitations remain, not adopted as local claims of unverified hashes after local verification.

Exact executed commands, node IDs and full outputs are in `.ly_state/session/l4_role15_unified_data_pipeline_plan_20261022.md` and its verification JSON/JUnit files. Final focused run: 62/62 passed (54 plan-package checks plus all eight standing classes). Full related ingestion/control suite: 1,316/1,318 passed; two existing backtest tests return 422 because omitted end-date defaults conflict with the same-day 08:30 UTC PIT boundary before that time. Full transport/advisor suite: 2,544/2,545 passed; one environment-snapshot test inherits `OMEGA_DISPATCH_CUTOFF` absent from its fixture reset. No unrelated runtime or test fix is applied. **Handoff status NEEDS_FIX**: required full suites are not green. Runtime pipeline fault-injection remains planned, not executed; no production readiness or gate approval is asserted.

## 15. Open decisions and release stops

- External scheduled tasks/runbooks and old CLI usage are not disproved by repository search; operations must inventory them before retirement.
- Six-candidate selection follows the supplied first-six scope ordering; confirm operator intent before deletion. Existing deprecated alias and active batch loader are separate, not extra silent retirements.
- Decide whether consumers need global generation consistency. If yes, authorize and test all pointer readers before promising atomic multi-dataset snapshots.
- Agree calendar ownership/coverage renewal and per-source readiness lags; no unsupported-year success.
- Agree production data/resource retention, max partition sizes, run deadline and observation window from measured fixtures. Do not add configurability before a real limit is established.
- Reconcile provider documentation with live SSI-primary canonical code; no source switch in this plan.
- Resolve any actual related-suite failures before implementation closure; preserve current evidence and do not self-approve.

Release stop: missing repo-local role/skill source, mismatched bound artifact/source hash, required advisor error, failing scoped acceptance, unknown provenance or unsafe concurrent publication. Separate L3 review remains required; no gate state is modified here.

## Appendix A. Static search ledger

Search dispositions are for this plan-only delivery: source/caller matches are inventoried, not modified. `changed_matches=0`; matched implementation behavior is non-actionable for production editing in this drafting task. `unresolved_matches=0` means no required finding/search hit is dropped from planning; it does not assert external schedules, runtime hazards or future parity tests are resolved. Baseline required finding IDs are empty. Avoid equating static source inventory with an architectural fix.

| Regex / exact operation | Scanned path set | Total matches | Changed | Non-actionable / inventoried disposition | Unresolved matches |
|---|---|---:|---:|---|---:|
| `\b(def|class)\s+\w+\s*\(|add_argument\(` | Six candidate scripts listed in Section 7 | 190 across 5 files; portfolio script has top-level execution | 0 | 190 inventoried declarations/CLI boundaries; preserve source, map to future stages | 0 |
| `scripts\.(fetch_financial_statements|update_market_flow|fetch_news_sentiment|run_macro_news_pipeline|update_recent_portfolio_data|update_market_data)\|subprocess.*(fetch_financial_statements|update_market_flow|fetch_news_sentiment|run_macro_news_pipeline|update_recent_portfolio_data|update_market_data)` (alternation between import and subprocess expressions) | `tests/**/*.py` | 15 across 8 files | 0 | 15 compatibility/test references, no production edit | 0 |
| Six candidate basenames joined with regex alternation | `tests/**/*.py` | 46 across 13 files | 0 | 46 test/fixture/prose references; direct imports are compatibility constraints | 0 |
| Six candidate basenames joined with regex alternation | `scripts/**/*.py` | 26 across 9 files | 0 | 12 historical report/advisor-prompt mentions; 14 retained caller/reference mapping requirements | 0 |
| Six candidate basenames joined with regex alternation | `README*`, `docs/**/*.md`, `config/**/*.json`, `.github/workflows/*.yml`, `scripts/**/*.py`, `pyproject.toml`, `requirements*.txt` | 31 across 11 files | 0 | 17 historical docs/formatter/advisor references, 14 compatibility inventory references; no candidate-name hits reported in scanned workflow/config/dependency files | 0 |
| `.gemini[\\/]antigravity-ide[\\/]scratch[\\/]ag-kit`; `.openclaw[\\/]skills`; `C:[\\/]Users[\\/]GHC[\\/].agents`; `.codex[\\/]memories` (dots escaped in executed Python regex) | Exact repo-local role plus nine authorized skill files, 10 files total | 0 for each of four patterns | 0 | 0 external authority references; forbidden locations themselves unread | 0 |
| Exact graph/contract and 11 scope-file SHA-256 comparisons | Fixed authorized artifact and source paths in companion manifest | 13 successful comparisons | 0 | 13 evidence/integrity bindings, no source edits | 0 |
| AST enumeration of every function/async function/class (no regex) | All 10 scoped Python files | 265 declarations: market 76, financials 18, macro 7, sentiment 21, flows 26, portfolio 0, ingest alias 1, batch 14, migration 2, control 100 | 0 | 265 inventoried boundaries; exact-root AST count supersedes inconsistent delegated declaration counts | 0 |
| `@(?:sse_control_)?router\\.(get|post|put|delete|patch)\\(` plus AST decorator enumeration | `src/omega/api/routes/control.py` | 20 path decorators, 19 handlers | 0 | 18 prefixed paths and 2 unprefixed SSE aliases all listed in Section 9 | 0 |

Delegated searches may overlap; counts are per query, not a unique total. All reported paths and source conclusions must match the authorized root and raw-byte source hashes; stale alternate-checkout/archive inferences are discarded.
