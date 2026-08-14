# macro_micro_data_v8 Detailed Implementation Plan

**Status:** Planning-only L3 detailed implementation plan; implementation deferred
**Role:** 26 `planning-architect` (Tier 3, Codex)
**Authoritative master:** `.ly_state/session/implementation_plan_macro_v8_20260810.md`
**Master SHA-256:** `F9A8010CA58E4CBC38A5D3A85AA4A071D033C3C6B32AECAA2C0598CE9EBB1C26`
**Plan gate:** `macro_micro_data_v8_detailed_plan`
**Future implementation gate:** `macro_micro_data_v8_implementation`
**Schema:** `macro_micro/v8`

## 1. Document Control

- This document converts the frozen master contracts into ordered, file-level implementation work for a subsequent L2 OpenCode implementation session.
- All paths are relative to the repository root.
- This session writes planning artifacts only. It does not edit production code, tests, fixtures, dependencies, baselines, or `.ly_state/session/phase_gates.json`.
- This document is not an audit, verdict, approval, gate record, or implementation evidence.
- The future implementation must use `macro_micro_data_v8_implementation`; it must not reuse, overwrite, or amend `macro_micro_data_v8_plan`.
- The future implementation acceptance commands remain deferred. None is executed during this planning session.

## 2. Delivery Outcome

The implementation delivers one immutable, PIT-safe macro/fundamental release pipeline with:

1. Acquisition-unique `RawReceiptV1` rows with exact schema, body integrity, and metadata-plus-body integrity.
2. Canonical Actual, Forecast, Derived, Quarantine, reconciliation, and receipt schemas.
3. Provider-native singleton revision semantics without fabricated ordering.
4. Immutable origin fields and rematerialization-stable consumer bytes.
5. Sealed, nonrecursive manifests anchored by a single authoritative pointer.
6. Unanimous required-provider/work-item activation with no degraded active state.
7. Contained no-follow filesystem access plus one exclusive pointer-lock/recovery chain.
8. Prepared/commit/abort pointer WAL, deterministic crash recovery, migration, rollback, and compatibility export.
9. Hermetic fixtures, focused regressions, PIT replay, pinned runtime, immutable acceptance transcripts, and hash-bound planning authority.

No service, database, alternate fetch CLI, interface/factory layer, custom PDF parser, or second PDF dependency is added.

## 3. Mandatory Closure Map

| Finding | Required implementation closure | Primary work packages | Release-blocking proof |
|---|---|---|---|
| Invalid genesis JSON | Use the exact valid canonical sentinel and declared hash. | WP1, WP6, WP9 | `test_genesis_fixture_is_valid_canonical_json_with_declared_sha256`. |
| Missing revision ordering | Declare all four current adapters as `singleton_immutable_evidence`; never manufacture order. | WP2, WP4, WP5, WP9 | Identical replay is a no-op; conflicting evidence yields `REVISION_SINGLETON_CONFLICT`. |
| PIT breaks after rematerialization | Separate immutable origin from physical release membership; compare consumer bytes without `release_id` and `materialized_at`. | WP1, WP2, WP6, WP9 | Earlier-cutoff consumer SHA-256 remains byte-identical after later releases. |
| Pointer/evidence crash window | Durably prepare before pointer replacement; durably commit while locked; recover every prepared nonterminal attempt deterministically. | WP6, WP9 | Crash-before/after-replace tests end in committed, aborted, or fail-closed divergence state. |
| Plan gate reused for implementation | Bind all future code, evidence, exception, audit, and gate metadata to `macro_micro_data_v8_implementation`. | WP8, WP10 | Gate-control tests reject cross-gate evidence. |
| Duplicate VCI transports | Fetch three dual-branch statement envelopes plus one ratio envelope. | WP3, WP4, WP9 | Exactly `4/4` transports and `8/8` logical outputs. |
| Recursive manifest inventory | Exclude `manifest.json` from its artifact list; anchor exact manifest bytes from `current.json`. | WP6, WP9 | Self-inventory rejected; pointer hash required on every read. |
| Raw receipt identity/schema incomplete | Implement acquisition-unique `RawReceiptV1`, exact Arrow types/nullability, `raw_body_sha256`, and domain-separated metadata-plus-body `receipt_sha256`. | WP1, WP3, WP9 | Schema/uniqueness/hash-vector tests reject every collision or mutation. |
| Degraded release activation undefined | Freeze required provider/work-item scope and require unanimous terminal success; V8 has no degraded active state. | WP3, WP6, WP9 | Any required failure or missing provider blocks seal, CAS, recovery commit, and reads. |
| Filesystem containment missing | Use canonical repository-relative paths and component-wise no-follow opens; reject traversal, absolute/UNC/device/ADS paths and all link/reparse forms. | WP1, WP6, WP7, WP9 | Attack matrix fails before any read/write/replace/export. |
| Gate metadata contract incomplete | Require literal `l2_completed=true` and concrete nonempty `l3_session_key`. | WP8, WP10 | Gate-control tests and post-L3 runner reject missing/false/placeholder values. |
| Detailed artifact not integrity-bound | Store exact detailed-plan and subsequent approving-audit paths/SHA-256 values in manifest `planning_authority`. | WP6, WP10 | Seal, activation, read, and handoff reject byte/hash/verdict mismatch. |
| Pointer lock/recovery underspecified | Use only kernel-backed `data/macro_micro/current.lock`; reject duplicate, multiple, disconnected, conflicting, or forked nonterminal chains. | WP6, WP9 | Concurrency/recovery tests never select by mtime/name and fail closed on ambiguity. |
| Acceptance transcript undefined | Add one Python parent runner with direct binary stream files, exact exit-code capture, fsync, byte counts, and SHA-256. | WP8, WP10 | Transcript tests prove non-overwrite, exact child parentage, and reproducible hashes. |
| Runtime reproducibility incomplete | Pin CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, Chromium revision `1234`, browser `151.0.7922.34`. | WP8, WP10 | Runner refuses any version/browser drift before spawning commands. |

## 4. Frozen Master Decisions

- Silver may be schema-correct and empty. No trustworthy publication evidence means no invented publication time.
- Date-only publication uses `source_published_on`; `source_published_at` remains null; availability begins at the first successful immutable receipt.
- Forecast classification precedes historical Actual validation. Forecast never enters Silver, Derived, historical graph inputs, features, or backtests.
- Existing canonical files, legacy input bytes, and prior release bytes are never modified in place.
- Every requested transport work item ends in adapter-proven success or a durable failed attempt.
- Same provider revision replay is a canonical no-op. Distinct singleton evidence is quarantined, never ordered or substituted.
- Provider streams remain source-separated until an immutable reconciliation decision is eligible at the query cutoff.
- Release lifecycle state belongs to pointer and attempt evidence. A sealed manifest is immutable and never inventories itself.
- Every frozen required provider/work item succeeds before seal or activation; no degraded pointer or consumer fallback exists.
- Every persisted/consumed path uses the shared containment validator and no-follow access.
- Activation and rollback use the same sole-lock pointer CAS and prepared/commit/abort WAL protocol.
- Every sealed manifest binds exact detailed-plan and subsequent independent approving-audit bytes.
- Implementation/tests never mutate gate metadata. Only an independent L3 audit may write a gate record.
- Runtime is exactly CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, and managed Chromium revision `1234` / browser `151.0.7922.34`; `pypdf==6.15.0` is the only new dependency.

## 5. Current-State Delta

| Path | Current risk | Required target |
|---|---|---|
| `src/omega/data/macro_micro_release.py` | No approved tracked V8 release-domain owner. A concurrently present untracked implementation is not accepted as evidence. | Create or reconcile one module owning schemas, canonical bytes, IDs, revision/reconciliation selection, lineage, quarantine, manifests, pointer CAS/WAL, migration, rollback, and validated readers. |
| `scripts/fetch_financial_statements.py` | Eight opaque DataFrame calls, synthetic `45/90`-day availability, destructive dedupe, direct legacy overwrite, in-place derived rows. | Four raw VCI transports, immutable receipts, eight logical slices, V8 normalization, candidate release build, activation, then validated compatibility export. |
| `src/omega/data/macro_pipeline.py` | Invented World Bank dates, permissive Yahoo `zip`, mutable legacy Parquet, rendered SBV table scraping, silent provider failures. | Exact World Bank/Yahoo contracts, official SBV article/PDF snapshot, strict extraction, immutable macro revisions, durable failure accounting. |
| `src/omega/quant/graph/fetcher.py` | Canonical acquisition can depend on opaque `vnstock` DataFrames. | Add raw, contract-pinned request paths and completeness iterators. Keep noncanonical compatibility only where required by existing graph bootstrap; never use it as V8 evidence. |
| `src/omega/quant/graph/loader.py` | Accepts arbitrary paths/DataFrames, collapses source, uses `item_code`, destructive duplicate choice, no pointer or Forecast guard. | Pointer-only Actual reads, manifest validation, source-aware revision selection, full `metric_id`, cutoff-safe reconciliation, fail-closed duplicate/Forecast handling. |
| `.python-version` | No V8 interpreter pin exists. | Add exact text `3.14.4` and reject any other CPython runtime before acceptance commands spawn. |
| `requirements.txt` | `pypdf` absent; V8 acceptance does not yet freeze PyArrow/Playwright versions. | Require exact `pyarrow==23.0.1` and `playwright==1.62.0`; add only new dependency `pypdf==6.15.0`. |
| `.agents/scripts/checklist.py` | UTF-8 setup does not precede every print path. | Add one guarded `_configure_utf8_stdio()` call before all output paths. |
| `scripts/sod_gate_enforcer.py` | Post-cutoff required fields can depend on strict-gate discovery. | Validate required post-cutoff fields directly and preserve writer/auditor separation. |
| Existing tests | Legacy behavior does not prove V8 contracts. | Extend four approved test files; add `tests/test_macro_micro_release.py` and `tests/test_macro_micro_acceptance_runner.py`; use only exact V8 fixtures. |
| `scripts/run_macro_micro_v8_acceptance.py` | No sole parent process or immutable transcript producer exists. | Add the only accepted implementation runner, with pinned-runtime validation, direct binary child-stream capture, exact exit-code capture, create-new evidence, and transcript hashing. |
| `scripts/run_graph_bootstrap.py` | Calls `GraphFetcher.financial()`. | Impact-only compatibility surface. Do not edit unless separately re-scoped; preserve its noncanonical behavior while removing it from V8 acquisition. |

Before implementation, L2 must treat every pre-existing untracked V8 code/test artifact as concurrent work: inspect it, reconcile it to this plan, and report it separately. Its presence does not satisfy any task or gate.

## 6. Target Storage and Authority

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
.ly_state/session/acceptance/macro_micro_data_v8_implementation/<run_id>/
  command_<nn>/stdout.bin
  command_<nn>/stderr.bin
  command_<nn>/result.json
  transcript.json
```

- Every release contains every listed artifact, including schema-correct empty Parquet files.
- `manifest.json` is required but absent from its own `artifacts` inventory.
- `data/macro_micro/current.json` is the sole publication authority.
- Release artifacts become immutable after sealing. Attempt evidence is append-only and never canonical data.
- Membership fields identify physical containment. Origin fields identify immutable first admission.
- Historical consumers validate pointer, manifest, artifact hash, schema, and membership before reading Actual rows.

## 7. Dependency Graph and Execution Order

```text
WP0 fixtures/baseline freeze
  -> WP1 canonical domain core
      -> WP2 revisions/reconciliation/derived/forecast/quarantine
      -> WP3 transport/completeness framework
          -> WP4 VCI ingestion
          -> WP5 World Bank/Yahoo/SBV ingestion
      -> WP6 manifest/pointer/WAL/recovery
          -> WP7 migration/readers/compatibility export
  -> WP8 dependency/checklist/gate hardening
  -> WP9 fixtures and tests
  -> WP10 acceptance evidence
```

- WP0 and the protected-file baseline are first and serial.
- WP2, WP3, and the schema portions of WP6 may proceed after WP1 freezes canonical encodings.
- WP4 and WP5 may proceed in parallel after WP3 freezes receipt/completeness contracts.
- WP7 is blocked by WP2 and WP6 because migration and readers require stable identities, pointer validation, and reconciliation semantics.
- WP9 starts with fixture creation in WP0, then adds tests beside each completed work package. Final PIT and recovery tests wait for WP6/WP7.
- WP10 starts only after all code/test/fixture edits stop. Any later edit restarts the full ordered acceptance sequence.

## 8. File Ownership Matrix

| Path | Action | Detailed ownership | Primary proof |
|---|---|---|---|
| `src/omega/data/macro_micro_release.py` | Add/reconcile | Entire V8 domain core and release authority. | `tests/test_macro_micro_release.py`. |
| `scripts/fetch_financial_statements.py` | Update | VCI orchestration, candidate release, activation, `--output` compatibility export. | `tests/test_fetch_financial_statements.py`. |
| `src/omega/data/macro_pipeline.py` | Update | World Bank, Yahoo, SBV raw acquisition and macro normalization. | `tests/test_macro_pipeline.py`. |
| `src/omega/quant/graph/fetcher.py` | Update | Raw requests, retry boundary, preflight, four completeness modes. | Fetch and macro adapter tests. |
| `src/omega/quant/graph/loader.py` | Update | Pointer-only Actual loading and PIT-safe factor matrices. | `tests/test_financial_loader.py`. |
| `.python-version` | Add | Pin CPython to exact `3.14.4`. | Acceptance-runner runtime rejection tests. |
| `requirements.txt` | Update | Pin `pyarrow==23.0.1`, `playwright==1.62.0`, and add only new dependency `pypdf==6.15.0`. | Runtime/version assertions and acceptance transcript. |
| `scripts/run_macro_micro_v8_acceptance.py` | Add | Sole parent runner for ordered L2/post-L3 commands and immutable binary transcripts. | `tests/test_macro_micro_acceptance_runner.py`. |
| `.agents/scripts/checklist.py` | Update | UTF-8 stdout/stderr setup. | Forced-`cp1252` subprocess regression. |
| `scripts/sod_gate_enforcer.py` | Update | Direct post-cutoff gate-field enforcement. | Gate-control tests. |
| `tests/test_fetch_financial_statements.py` | Extend | VCI route, branch, partition, receipt, accounting, replay tests. | Focused pytest. |
| `tests/test_macro_pipeline.py` | Extend | World Bank, Yahoo, SBV, publication, append-only tests. | Focused pytest. |
| `tests/test_financial_loader.py` | Extend | Pointer/manifest, Actual-only, metric/source/reconciliation tests. | Focused pytest. |
| `tests/test_macro_micro_release.py` | Add/reconcile | Domain, receipt integrity, containment, quorum, planning authority, pointer lock/recovery, PIT, migration, rollback tests. | Focused pytest and exact PIT test. |
| `tests/test_macro_micro_acceptance_runner.py` | Add | Runtime pins, sole-parent spawning, binary streams, exit codes, fsync/hash, immutable run IDs, and transcript linkage. | Focused pytest. |
| `tests/test_strict_repo_local_skill_loading.py` | Extend | Checklist encoding and future implementation-gate controls. | Focused pytest. |
| `tests/fixtures/macro_micro/v8/` | Add exact inventory | Immutable raw/expected/contract/PIT/pointer fixtures only. | Fixture hashes and hermetic tests. |
| `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json` | Conditional add | Only independently warranted pre-existing unrelated full-suite failures. | Exact exception schema and L3 approval. |

Protected from this implementation scope unless separately authorized: `scripts/run_graph_bootstrap.py`, legacy input Parquet bytes, prior releases, planning artifacts, and all plan-gate metadata.

## 9. WP0 - Fixture and Baseline Freeze

### 9.1 Protected-State Snapshot

Before implementation edits:

1. Record Git revision or explicit dirty-tree evidence and the exact changed/untracked path list.
2. Hash `.ly_state/session/implementation_plan_macro_v8_20260810.md`, `.ly_state/session/phase_gates.json`, existing legacy input files, `data/macro_micro/current.json` if present, and every existing release artifact.
3. Record whether the genesis pointer, release root, and attempt root exist. Do not initialize or repair them during baseline capture.
4. Record pre-existing V8 code/test artifacts separately. Do not count them as completed work until reconciled and tested against every contract below.
5. Freeze the five inherited full-suite failing node IDs from the master. Reproduce them during the implementation phase before deciding whether to fix or request an exception.

Protected-state hashes are compared after implementation. Any unexpected legacy, prior-release, planning, or gate-byte change stops the release.

### 9.2 Exact Fixture Inventory

Create exactly these `29` V8 fixtures; do not add aliases or duplicate provider snapshots:

1. `tests/fixtures/macro_micro/v8/provider_contract.json`
2. `tests/fixtures/macro_micro/v8/vci/request_contract.json`
3. `tests/fixtures/macro_micro/v8/vci/income_statement_raw.json`
4. `tests/fixtures/macro_micro/v8/vci/income_statement_year.json`
5. `tests/fixtures/macro_micro/v8/vci/income_statement_quarter.json`
6. `tests/fixtures/macro_micro/v8/vci/balance_sheet_raw.json`
7. `tests/fixtures/macro_micro/v8/vci/balance_sheet_year.json`
8. `tests/fixtures/macro_micro/v8/vci/balance_sheet_quarter.json`
9. `tests/fixtures/macro_micro/v8/vci/cash_flow_raw.json`
10. `tests/fixtures/macro_micro/v8/vci/cash_flow_year.json`
11. `tests/fixtures/macro_micro/v8/vci/cash_flow_quarter.json`
12. `tests/fixtures/macro_micro/v8/vci/ratios_raw.json`
13. `tests/fixtures/macro_micro/v8/vci/ratios_year_expected.json`
14. `tests/fixtures/macro_micro/v8/vci/ratios_quarter_expected.json`
15. `tests/fixtures/macro_micro/v8/vci/ratios_contract.json`
16. `tests/fixtures/macro_micro/v8/world_bank/cpi_page_1.json`
17. `tests/fixtures/macro_micro/v8/world_bank/gdp_growth_page_1.json`
18. `tests/fixtures/macro_micro/v8/world_bank/m2_growth_page_1.json`
19. `tests/fixtures/macro_micro/v8/yahoo/usdvnd_chart.json`
20. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_article_root.html`
21. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31.pdf`
22. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_contract.json`
23. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_expected_rows.json`
24. `tests/fixtures/macro_micro/v8/reconciliation/future_policy.json`
25. `tests/fixtures/macro_micro/v8/reconciliation/future_decision.json`
26. `tests/fixtures/macro_micro/v8/serialization/canonical_json_cases.json`
27. `tests/fixtures/macro_micro/v8/forecast/classification_cases.json`
28. `tests/fixtures/macro_micro/v8/pit/acceptance_trail.json`
29. `tests/fixtures/macro_micro/v8/pointer/genesis_current.json`

`provider_contract.json` is the root fixture index. It records adapter IDs/versions, exact provider constants, every fixture path/hash, expected schema/count data, and the work-accounting invariants. Tests must not use live network.

### 9.3 Fixture Invariants

- Genesis bytes are exactly the master sentinel; SHA-256 is `76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`; no BOM or trailing newline.
- The FPT ratio fixture contains `41` raw rows partitioned as `8` annual, `33` quarterly, `0` leftovers.
- L2 downloads the official SBV article-root fixture with a repository script or Playwright, persists the exact response bytes, then records the actual byte count and computed lowercase SHA-256 in `provider_contract.json` and implementation evidence. No predeclared size or hash applies.
- L2 downloads the official SBV PDF fixture with a repository script or Playwright, persists the exact response bytes, then records the actual byte count and computed lowercase SHA-256 in `provider_contract.json` and implementation evidence. No predeclared size or hash applies.
- SBV expected output contains exactly the pinned `VND` and `USD` rows and seven tenors, including the `VND` nine-month null.
- JSON/HTML fixtures are immutable UTF-8. PDF is exact binary evidence. Every fixture hash is verified before parsing.

### 9.4 Exit Criteria

- Exact inventory count is `29`.
- Fixture paths, bytes, hashes, counts, and adapter literals match the master.
- No live-network dependency exists in tests.
- Protected-state baseline is durable and hash-addressed.

## 10. WP1 - Canonical Domain Core

**Owner:** `src/omega/data/macro_micro_release.py`

### 10.1 Module Order

Implement in this order to prevent downstream identity drift:

1. Typed exceptions.
2. Schema/version constants and Arrow schemas.
3. Schema validators and primitive normalization.
4. `canonical_json_v1` and `canonical_consumer_json_v1`.
5. Receipt, evidence, revision, reconciliation, lineage, manifest, pointer, and attempt structures.
6. Identity/hash builders.
7. Storage readers/writers and membership/origin validation.
8. Domain selectors and release operations in later work packages.

Use standard-library dataclasses or plain mappings plus explicit validators. Do not add a validation framework or one-implementation interface.

### 10.2 Exceptions

Define exactly the public exception family from the master:

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

Internal helpers raise typed errors with stable reason codes. CLI boundaries persist `failure.json`, preserve prior authority, and return nonzero. No internal broad exception swallowing.

### 10.3 Canonical Serialization

`canonical_json_v1(value) -> bytes` is the only V8 canonical serializer:

1. Validate the declared schema and reject unknown fields before encoding.
2. Normalize strings to Unicode NFC.
3. Encode timestamps as UTC RFC3339 with six fractional digits and `Z`.
4. Encode dates as `YYYY-MM-DD`.
5. Encode business decimals as non-exponent base-10 strings; trim trailing fractional zeroes; normalize signed zero to `0`.
6. Encode integers, booleans, null, and explicitly schema-approved byte wrappers only. Reject nonfinite numbers.
7. Preserve array order; sort object keys by Unicode code point.
8. Emit compact UTF-8 JSON with `ensure_ascii=false`, no BOM, and no trailing newline.

Implementation uses schema-owned normalization followed by the standard JSON encoder. It must not use `default=str`, object `__dict__`, `repr`, memory address, file order, or current time.

`canonical_consumer_json_v1(row)` validates the row, removes exactly `release_id` and `materialized_at`, then calls `canonical_json_v1`. No other field is removed.

### 10.4 Exact `RawReceiptV1` Schema and Identity

Both Bronze receipt Parquet files use this closed Arrow schema. Unknown columns fail. `string` means UTF-8, hashes are lowercase 64-character hexadecimal strings, JSON strings are exact `canonical_json_v1` text, and every timestamp is `timestamp[us, tz=UTC]`.

| Field | Arrow type | Nullable | Exact contract |
|---|---|---:|---|
| `schema_version` | `string` | no | Exactly `macro_micro_raw_receipt/v1`. |
| `release_id` | `string` | no | Physical containing release. |
| `materialized_at` | `timestamp[us, tz=UTC]` | no | Actual physical write time. |
| `origin_release_id` | `string` | no | First sealed release containing this receipt. |
| `origin_ingested_at` | `timestamp[us, tz=UTC]` | no | First immutable candidate-ingestion time. |
| `source_receipt_id` | `string` | no | Acquisition-unique identity defined below. |
| `attempt_id` | `string` | no | Owning attempt. |
| `work_item_id` | `string` | no | Frozen requested work item. |
| `acquisition_ordinal` | `uint64` | no | Attempt-global monotone ordinal allocated durably before I/O. |
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
| `raw_body_sha256` | `string` | no | Exact raw-body hash defined below. |
| `receipt_sha256` | `string` | no | Domain-separated metadata-plus-body hash defined below. |

Before each transport, the attempt ledger durably allocates a never-reused `acquisition_ordinal`. Both `(attempt_id, acquisition_ordinal)` and `source_receipt_id` are repository-unique. Define:

```text
source_receipt_id = hex(SHA256(canonical_json_v1({
  "schema_version":"source_receipt_id/v1",
  "attempt_id":...,
  "work_item_id":...,
  "acquisition_ordinal":...,
  "provider_id":...,
  "adapter_id":...,
  "adapter_version":...,
  "request_method":...,
  "request_url":...,
  "request_scope_json":...
})))
```

Every retry receives a new ordinal and ID even when its request or response bytes repeat. A transport failure before a complete response produces durable failed-attempt evidence, never a fabricated `RawReceiptV1`.

`raw_body_sha256 = hex(SHA256(raw_body))`. Validate `raw_body_size` and `raw_body_sha256`, then build `receipt_metadata_v1` from every schema field in table order except `release_id`, `materialized_at`, `raw_body`, and `receipt_sha256`. Let `metadata = canonical_json_v1(receipt_metadata_v1)`. Define:

```text
receipt_sha256 = hex(SHA256(
  b"RawReceiptV1\0" ||
  uint64_be(len(metadata)) || metadata ||
  uint64_be(len(raw_body)) || raw_body
))
```

Hash exact bytes before parsing. No decoding, decompression, newline normalization, header reordering outside canonical JSON, or timestamp reconstruction may precede or alter either hash. Rematerialization preserves immutable origin fields, `source_receipt_id`, `raw_body_sha256`, and `receipt_sha256`.

### 10.5 Persisted Structures

Implement the named structures without extra abstraction:

- `RawReceiptV1`
- `ReceiptRefV1`
- `RecordEvidenceV2`
- `CanonicalRecordV8`
- `ReconciliationDecisionV1`
- `DerivedRecordV1`
- `ReleaseManifestV1`
- `ActivePointerV1`
- `ActivationPreparedV1`
- `ActivationCommitV1`
- `ActivationAbortV1`
- `AttemptEventV1`

Every persisted structure has an exact `schema_version`, required-field set, unknown-field rejection, canonical-byte encoder, and Arrow/JSON storage validator as applicable.

### 10.6 Membership and Origin

- Every physical row has current `release_id` and actual `materialized_at` matching its containing release.
- Actual, Forecast, Derived, reconciliation, receipt, and resolution rows preserve immutable `origin_release_id` and `origin_ingested_at` across rematerialization.
- Quarantine preserves immutable `first_seen_release_id`, `origin_ingested_at`, and `quarantine_id` while updating only current membership.
- Origin/first-seen release sequence cannot exceed the containing release sequence.
- `materialized_at >= origin_ingested_at`.
- Membership/origin fields are validated before manifest sealing and on every production read.

### 10.7 Identity Separation

- `source_receipt_id`: the acquisition-unique pre-I/O SHA-256 projection in section 10.4; retries never reuse it. It is not a content hash or provider revision key.
- `raw_body_sha256`: SHA-256 of exact response bytes before parsing.
- `receipt_sha256`: the domain-separated metadata-plus-body SHA-256 in section 10.4; it excludes only physical rematerialization fields and binds immutable origin, acquisition, adapter, request, response, completeness, raw-body length/hash, and raw bytes.
- `record_evidence_sha256`: canonical `RecordEvidenceV2` bytes.
- `provider_revision_key`: exact provider value or immutable document identity; never synthesized.
- `revision_id`: canonical normalized revision identity, including source-aware key, record type, payload, publication evidence, declared order mode, immutable origin timing, and evidence hash; excluding current membership.

Duplicate `(attempt_id, acquisition_ordinal)` or `source_receipt_id`, or conflicting metadata/body bytes for one receipt identity, fail `RECEIPT_ID_CONFLICT`. Conflicting normalized bytes for one evidence hash fail `RECORD_EVIDENCE_HASH_CONFLICT`.

### 10.8 Exit Criteria

- Canonical fixture cases are byte-identical across repeated runs and line-ending environments.
- Unknown fields, nonfinite values, malformed timestamps/decimals, and unapproved byte forms fail closed.
- Rematerialization changes storage bytes only through `release_id` and `materialized_at`; consumer bytes and `revision_id` remain unchanged.
- Empty Arrow tables preserve exact schemas.

## 11. WP2 - Revision, Reconciliation, Derived, Forecast, Quarantine

**Owner:** `src/omega/data/macro_micro_release.py`

### 11.1 CanonicalRecordV8

Common fields implement the exact master contract: schema/membership/origin, dataset/record type, source and source URL, receipt/evidence identities, publication/observation/availability evidence, declared revision mode/order fields, and immutable `revision_id`.

Financial rows add `symbol`, `endpoint`, `period_type`, `item_code`, `metric_id`, `fiscal_period_end`, `item_value_decimal`, `currency`, and `unit`.

- `metric_id = endpoint:period_type:item_code`.
- Logical key: `(dataset, symbol, metric_id, fiscal_period_end)`.
- Provider-stream key: `(dataset, source, symbol, metric_id, fiscal_period_end)`.

Macro rows add `indicator`, `observation_date`, canonical `dimensions_json`, `value_decimal`, and `unit`.

- Logical key: `(dataset, indicator, observation_date, dimensions_json)`.
- Provider-stream key: `(dataset, source, indicator, observation_date, dimensions_json)`.

Unknown columns fail. Silver and Derived accept only `record_type=actual`.

### 11.2 Publication and Availability

1. Exact timestamp evidence uses `source_published_at`, `availability_basis=published_timestamp_session/v1`, and the versioned `Asia/Ho_Chi_Minh` session rule.
2. Date-only evidence uses `source_published_on`, null timestamp, `availability_basis=first_successful_receipt/v1`, and `available_at=first_observed_at`.
3. Never substitute midnight, market open, fetch date, file time, ingestion time, or current clock as provider publication time.
4. Missing both publication evidence and immutable first receipt yields `PUBLICATION_EVIDENCE_MISSING`.
5. Receipt-based rows require `first_observed_at <= available_at <= origin_ingested_at`; `materialized_at` is never a PIT input.

### 11.3 Singleton Revision Semantics

All current adapters use `revision_order_kind=singleton_immutable_evidence`; `source_revision_at` and `revision_seq` are null.

- Same provider-stream key, `revision_id`, and evidence hash: canonical no-op; append only a genuinely new evidence link.
- Same stream with a distinct revision or evidence hash: preserve accepted revision and raw evidence; append permanent Quarantine reason `REVISION_SINGLETON_CONFLICT`.
- Never compare receipt time, availability, origin ingestion, materialization, URL, hash, or file order to choose a winner.
- `REVISION_ORDER_MISSING` applies only to a future adapter declaring timestamp/sequence ordering but omitting that value.
- Mixed order kinds or equal ordered values with different revisions fail closed.

`select_provider_revision_as_of(rows, cutoff)` validates pointer membership first, filters Actual rows by `available_at` and `origin_ingested_at`, groups by source-aware provider key, then returns at most one accepted eligible native revision.

### 11.4 ReconciliationDecisionV1

Implement every master field: schema/current membership/immutable origin, canonical key, policy identity/hash/effective/knowledge/origin times, ordered candidate sources/revisions/availability/origin times, selected outcome, decision times, input hash, and `reconciliation_id`.

- Candidate arrays are ordered by configured priority then source ID; lengths must match.
- A policy/input/knowledge/outcome change appends a new immutable decision.
- Eligibility requires every policy, candidate, decision, and origin-ingestion timestamp at or before cutoff.
- Candidate revision-set equality is exact.
- `decision_created_at` is no earlier than all input knowledge; `decision_recorded_at >= decision_created_at`; `decision_origin_ingested_at >= decision_recorded_at`.
- Missing, stale, unresolved, contradictory, future-known, or candidate-mismatched decisions return no canonical value.

`select_reconciled_revision_as_of(native_rows, decisions, cutoff)` never silently falls back to source priority without an eligible decision.

### 11.5 DerivedRecordV1

Implement only:

- `derived_ratios:<period_type>:current_ratio` using `omega.financial.current_ratio` version `1.0.0`.
- `derived_ratios:<period_type>:debt_to_equity` using `omega.financial.debt_to_equity` version `1.0.0`.

Parents are exact selected Actual revisions at the cutoff, share symbol/period/provider-selection context, are finite, and have nonzero denominator. `ordered_parent_lineage` uses the exact 13 master fields and semantic order. `lineage_sha256` hashes canonical ordered lineage. Invalid or ambiguous derivation produces no value and a reasoned rejection.

### 11.6 Forecast Classifier

`classify_forecast_record(record, evidence)` executes exactly:

1. Validate envelope identity, hashes, locator, period fields, and adapter forecast markers.
2. Route explicitly source-marked forecast/estimate/guidance/consensus rows to Forecast.
3. Validate Forecast publication/availability/revision fields.
4. Route unmarked future periods to Quarantine as `FUTURE_PERIOD_UNCONFIRMED`.
5. Validate remaining rows as historical Actual.

No date-based inference may label a row as Forecast. Historical readers expose no weakening flag.

### 11.7 Permanent Quarantine

Quarantine rows preserve exact raw bytes or byte-preserving encoding, raw hash, current membership, immutable first-seen/origin identity, source/evidence identity, stable reason code, timestamps, and versioned details.

- Same invalid evidence plus same reason is a no-op.
- Distinct evidence or reason appends.
- Original Quarantine rows are never deleted, updated, or moved.
- Later valid replay appends a canonical revision plus resolution event.
- Hashes are verified before staging and through the published reader.

Include all VCI/SBV codes plus the master minimum generic codes, especially `REVISION_SINGLETON_CONFLICT`, `PUBLICATION_EVIDENCE_MISSING`, `FUTURE_PERIOD_UNCONFIRMED`, and `DERIVED_PARENT_SOURCE_MISMATCH`.

### 11.8 Exit Criteria

- Native selection never collapses `source`.
- Future policy or decision evidence changes zero earlier-cutoff consumer bytes.
- Forecast leakage count is zero across Silver, Derived, loader, graph, features, and backtests.
- Derived outputs match exact parent revisions and lineage hashes.
- Singleton conflicts never replace accepted rows.

## 12. WP3 - Transport and Completeness Framework

**Owners:** `src/omega/quant/graph/fetcher.py`, `src/omega/data/macro_micro_release.py`

### 12.1 Raw Transport Boundary

- Add explicit raw request helpers returning status, selected headers, exact bytes, URL/parameters, request/response/checksum times, and parsed envelope only after hashing.
- Before any request, create/fsync `attempt.json` with sorted unique `required_provider_ids`, `required_work_item_ids`, the exact provider-to-work-item mapping, and `required_scope_sha256`; allocate/fsync the next attempt-global `acquisition_ordinal` before I/O.
- Canonical V8 acquisition never calls opaque financial DataFrame helpers.
- Keep existing `GraphFetcher.financial()` only as a noncanonical compatibility path needed by `scripts/run_graph_bootstrap.py`; V8 code must not call it.
- Retry only classified transient transport failures. Every final failure becomes durable work-item evidence; no silent continue.
- Cookies and authorization remain forbidden for VCI. SBV browser-context cookies are retained only for its official linked PDF fetch.

### 12.2 Receipt and Evidence Construction

For each response:

1. Build the acquisition-unique `source_receipt_id` from the exact section 10.4 pre-I/O projection; never reuse an ordinal or ID for a retry.
2. Capture the complete response metadata/body, compute `raw_body_size` and `raw_body_sha256` over exact bytes, then compute the domain-separated metadata-plus-body `receipt_sha256` exactly as section 10.4 specifies.
3. Persist one schema-exact `RawReceiptV1` row containing request scope, URL/parameters, selected headers, status, redirects, exact bytes, actual timestamps, adapter identity, and completeness proof; unknown or nullable-contract violations fail closed.
4. Reread and reproduce both hashes before decoding or parsing.
5. Build `ReceiptRefV1` with both hashes, then `RecordEvidenceV2` with primary receipt, ordered context receipts, source locator, exact field paths/selectors/values, and adapter identity.
6. Checkpoint terminal success only after all referenced hashes reproduce and the declared completeness proof validates. Pre-response or incomplete-response failures create durable failure evidence and no receipt row.

### 12.3 Four Completeness Modes

Implement one validator per mode, selected by adapter contract:

- `cursor_token`: provider-issued cursor only; reject guesses, repeats, scope drift, or premature terminal state.
- `authoritative_numbered_pages`: fetch exactly `1..pages`; require stable metadata and exact `total` accounting.
- `explicit_single_envelope_terminal`: one pinned nonpaginated envelope; reject cursor, truncation, partial, or error markers.
- `official_article_attachment_snapshot`: one official article root plus exactly one official immutable attachment; hash both before parse; reject fallback pages/attachments/OCR/heuristics.

Every work item reaches terminal success or durable failure. Completeness validators return proof data stored with the receipt; they do not return a bare Boolean.

### 12.4 Provider Preflight

Preflight validates fixture-backed adapter constants and aborts the candidate release on any drift:

1. VCI `4/4` transports and `8/8` logical outputs.
2. Three World Bank IDs and stable page metadata.
3. Yahoo single result plus exact timestamp/close-array equality.
4. SBV article-root/PDF fixture replay only.
5. Adapter constants equal `provider_contract.json`.
6. Identical replay and one injected singleton conflict per adapter.
7. Route, header, selector, schema, hash, partition, completeness, or revision-mode mismatch is fatal.

### 12.5 Exit Criteria

- `100%` requested work items have exactly one declared completeness mode.
- `100%` work items terminate durably.
- Every sealable candidate has unanimous terminal success across the frozen required provider/work-item scope; any required failure keeps the candidate non-activatable.
- Exact `RawReceiptV1` schema, acquisition uniqueness, raw-body hash, and metadata-plus-body hash reproduce before and after normalization/rematerialization.
- No canonical V8 row can be produced without receipt, evidence, completeness, and terminal work accounting.

## 13. WP4 - VCI Financial Ingestion

**Owners:** `src/omega/quant/graph/fetcher.py`, `scripts/fetch_financial_statements.py`, `src/omega/data/macro_micro_release.py`

### 13.1 Frozen Adapter Contract

- Adapter: `vci_financial_raw/v2`.
- Completeness: `explicit_single_envelope_terminal`.
- Base: `https://iq.vietcap.com.vn/api/iq-insight-service`.
- Runtime contract: `vnstock==4.0.4` behavior evidence and `requests==2.33.1`; raw acquisition is performed through explicit requests, not DataFrame helpers.
- Method: `GET`.

Request headers must equal `tests/fixtures/macro_micro/v8/vci/request_contract.json`, including the exact Accept, language, cache, fetch, browser, Referer, and Origin values from the master. Cookies and authorization are forbidden.

### 13.2 Exact Four Transports

| Work item | Exact path/query | Required response | Logical outputs |
|---|---|---|---|
| Income | `/v1/company/{symbol}/financial-statement?section=INCOME_STATEMENT` | Object `data`; nonempty `data.years`; nonempty `data.quarters`; no error/truncation marker. | `income_statement:year`, `income_statement:quarter`. |
| Balance | `/v1/company/{symbol}/financial-statement?section=BALANCE_SHEET` | Same dual-branch contract. | `balance_sheet:year`, `balance_sheet:quarter`. |
| Cash flow | `/v1/company/{symbol}/financial-statement?section=CASH_FLOW` | Same dual-branch contract. | `cash_flow:year`, `cash_flow:quarter`. |
| Ratios | `/v1/company/{symbol}/statistics-financial` | `data` is a nonempty array of row objects. | `ratios:year`, `ratios:quarter`. |

`slice_vci_statement_envelope(envelope, section)` validates both statement branches before returning either. Year/quarter outputs share the receipt ID/hash and use deterministic `data.years` or `data.quarters` locator prefixes. Missing one branch fails the transport; a compensating second request is forbidden.

### 13.3 Ratio Partition

`partition_vci_ratio_rows(rows, symbol)` performs the exact eight assertions from the master:

1. Nonempty list; every row is an object.
2. Required fields: `year`, `yearReport`, `quarter`, `ratioType`, `organCode`, `ratioTTMId`.
3. Requested symbol match; four-digit year; `yearReport == int(year)`.
4. Annual: `ratioType == RATIO_YEAR`, `quarter == 5`, non-null `ratioYearId`.
5. Quarterly: `ratioType == RATIO_TTM`, quarter `1..4`, null `ratioYearId`.
6. Every row belongs to exactly one partition.
7. Annual sort `(int(year), ratioYearId)`; quarterly sort `(int(year), int(quarter), ratioTTMId)`.
8. Duplicate normalized identity fails `VCI_RATIO_PARTITION_VIOLATION`.

The pinned fixture proves `41 = 8 + 33 + 0`; production accepts other counts only when all predicates/accounting pass.

### 13.4 Financial CLI Refactor

Refactor `scripts/fetch_financial_statements.py` without adding another CLI:

1. Preserve universe selection and `--active-only` behavior, but record the immutable symbol work manifest in `attempt.json`.
2. Replace `ENDPOINTS x PERIODS` acquisition with four work items per symbol.
3. Persist each exact raw response and terminal completeness proof before normalization.
4. Materialize eight logical slices from the four receipts; never cache a DataFrame serialization as raw evidence.
5. Normalize fields to `CanonicalRecordV8`, preserving endpoint, period, full metric ID, exact decimals, publication evidence, source locator, and source-aware keys.
6. Run forecast classification before Actual validation.
7. Apply singleton replay/conflict semantics; no `drop_duplicates(... keep=last)` in canonical paths.
8. Build a complete candidate release through release-domain APIs. Derived ratios are produced only after cutoff-safe Actual selection, not inline from one mutable statement list.
9. Seal and activate through pointer CAS/WAL.
10. Only after successful activation, run `--output PATH` compatibility export from the validated active release.

Existing raw snapshot filenames may be read only as migration evidence if exact bytes and origin can be proven. They are not automatically valid V8 receipts.

### 13.5 VCI Tests

`tests/test_fetch_financial_statements.py` covers:

- Exactly four HTTP calls per symbol and no period-duplicate calls.
- Three dual-branch statement envelopes and shared receipt hashes.
- Eight logical outputs and deterministic locators.
- Header, route, method, branch, error/truncation, and symbol contract failures.
- Ratio `41/8/33/0` partition plus unclassified, duplicate, malformed, and sort cases.
- Identical replay no-op; injected singleton conflict quarantine.
- Zero dropped raw rows and exact terminal work accounting.
- Compatibility export happens after activation and preserves the old output on failure.

### 13.6 Exit Criteria

- `4/4` raw transports and `8/8` logical outputs for every successful symbol.
- No V8 canonical row originates from `vnstock` DataFrame output.
- No synthetic `45/90`-day publication/availability values.
- No destructive dedupe, direct canonical overwrite, or pre-activation compatibility export.

## 14. WP5 - World Bank, Yahoo, and SBV Ingestion

**Owners:** `src/omega/data/macro_pipeline.py`, `src/omega/quant/graph/fetcher.py`, `src/omega/data/macro_micro_release.py`

### 14.1 Macro Pipeline Refactor

Keep `MacroDataPipeline` and `fetch_macro_indicators` as public compatibility entrypoints, but change their authoritative work:

1. Build provider work items and attempt evidence before network work.
2. Acquire/persist raw receipts through WP3 helpers.
3. Validate provider-specific completeness before parsing.
4. Normalize to V8 candidate rows; never append directly to `data/macro_indicators.parquet` as canonical state.
5. Route explicit Forecast before Actual checks; quarantine malformed/unsupported evidence permanently.
6. Merge by append-only revision identity, not mutable DataFrame dedupe.
7. Candidate release, seal, and activation use WP6. Any legacy output is a post-activation projection only.

Silent warning-and-continue behavior is removed for requested work. Failures are durable and terminal; Silver may remain empty when no row has trustworthy publication evidence.

### 14.2 World Bank

- Adapter: `world_bank_v2/v1`.
- Completeness: `authoritative_numbered_pages`.
- URL: `https://api.worldbank.org/v2/country/VN/indicator/{indicator_id}?format=json&page={page}`.
- Exact IDs: `FP.CPI.TOTL.ZG` to `cpi`; `NY.GDP.MKTP.KD.ZG` to `gdp_growth`; `FM.LBL.BMNY.ZG` to `m2_growth`.

Implementation:

1. Fetch page 1, validate metadata `page`, `pages`, `per_page`, and `total`.
2. Fetch exactly pages `2..pages`; require stable metadata/scope and exact total accounting.
3. Preserve each page as its own receipt with deterministic page ordinal.
4. Treat the provider `date` year as observation identity only. Never invent year-end, next-year, or publication timestamps.
5. Populate publication fields only from exact provider evidence. Where the canonical publication contract cannot be satisfied, retain Bronze evidence and route the candidate per the master instead of fabricating Silver.
6. Use `singleton_immutable_evidence`; indicator/date is stream identity, not revision order.

### 14.3 Yahoo USD/VND

- Adapter: `yahoo_chart_v8/v1`.
- Completeness: `explicit_single_envelope_terminal`.
- URL: `https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X`.

Require one bounded result, exact timestamp/close-array length equality, valid finite close values or explicit null exclusion accounting, no cursor/truncation/error marker, and no permissive `zip` truncation. Chart timestamp is observation identity, not revision order or publication evidence.

### 14.4 SBV Official Article/PDF

- Adapter: `sbv_weekly_interbank_pdf/v2`.
- Completeness: `official_article_attachment_snapshot`.
- Article: `https://www.sbv.gov.vn/vi/w/di%E1%BB%85n-bi%E1%BA%BFn-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-ngo%E1%BA%A1i-t%E1%BB%87-v%C3%A0-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-li%C3%AAn-ng%C3%A2n-h%C3%A0ng-tu%E1%BA%A7n-t%E1%BB%AB-27-31.7.2026`.
- Expected title: `Diễn biến thị trường ngoại tệ và thị trường liên ngân hàng tuần từ 27-31.7.2026`.
- Published date: `2026-08-05`; observation range: `2026-07-27` through `2026-07-31`.

Use exact selectors:

- Article root: `div.journal-content-article[data-analytics-asset-type=web-content]`.
- Printable root: `div.journal-content-article[data-analytics-asset-type=web-content] #print-content`.
- Title: `h1.title-page.detail`.
- Date: `time.author-time[datetime]`, parsed only with `%d/%m/%Y`.
- Attachment: `article a[download]`, exactly one official SBV HTTPS URL containing `.pdf`.

Fetch the PDF through the same Playwright browser context. Require HTTP `200`, `Content-Type: application/pdf`, and `%PDF-` magic before hashing. An HTML `200` is a contract failure.

Parse the title only with the anchored master regex. Inherit omitted start month/year from the end date. Reject inverted, longer-than-seven-day, ambiguous, or selector-multiple ranges.

Use `pypdf==6.15.0` embedded-text extraction only. Require exact page/header/row/unit/null schema and the two pinned currency rows. OCR, visual scraping, alternate tables, and heuristic numeric recovery are forbidden.

SBV PIT mapping:

- `observation_date` is the title range end.
- `source_published_on` is the exact article date.
- `source_published_at` is null.
- `first_observed_at` is the actual first successful immutable article/PDF receipt time.
- `availability_basis=first_successful_receipt/v1`; `available_at=first_observed_at`.
- `provider_revision_key` is the exact resolved attachment URL as immutable document identity only.
- PDF is primary receipt; article root is ordered context evidence.

Use the six exact SBV reason codes from the master. No unpinned site-wide discovery.

### 14.5 Macro Tests

`tests/test_macro_pipeline.py` covers:

- World Bank exact IDs, page enumeration, stable metadata, total accounting, replay, and page-protocol failures.
- Yahoo single-result schema, array equality, null accounting, and terminal-envelope failures.
- SBV selector multiplicity, title/date range, attachment host, browser-context PDF, HTTP/content-type/magic/hash, exact extraction table, and every reason code.
- Date-only publication and first-receipt availability.
- No invented World Bank/Yahoo publication timestamps.
- Append-only native source streams, identical replay no-op, and singleton conflict quarantine.
- Candidate release abort on any requested provider work failure not explicitly represented as a durable failed attempt.

### 14.6 Exit Criteria

- All three World Bank IDs complete exact numbered-page accounting.
- Yahoo timestamp/close arrays have equal lengths; zero silent truncation.
- SBV article and PDF structure, title/date/attachment linkage, and extracted tenor rows match expected content; zero fallback extraction.
- Macro canonical state is release-based and append-only; legacy Parquet is not authority.

## 15. WP6 - Manifest, Pointer WAL, Recovery, Rollback

**Owner:** `src/omega/data/macro_micro_release.py`

### 15.1 Contained Durable I/O Primitives

Implement private helpers for create-new, write/fsync, atomic same-directory replace, directory durability, exact-byte reread, and SHA-256 verification.

- Every persisted or consumed release, manifest, pointer, lock, attempt, checkpoint, event, failure, activation-evidence, planning-authority, fixture, acceptance-evidence, and `--output` path is a canonical forward-slash repository-relative string beneath one explicit trusted root.
- Lexical validation rejects empty input, NUL, backslash, leading slash, `//`, drive prefixes, absolute paths, UNC forms, `\\?\\`, `\\.\\`, `\??\` device forms, any colon or alternate-data-stream syntax, empty/`.`/`..` segments, trailing dot/space, and case-insensitive DOS device segments `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, or `LPT1`-`LPT9` with or without an extension. Absolute paths are never converted to relative paths.
- Open the trusted root, every existing intermediate component, and the final component with component-wise no-follow semantics. Reject symbolic links, junctions, mount-point substitutions, and every filesystem reparse point at the root, intermediate, or final component. Retain verified parent handles and verify the handle-derived final location remains under the same trusted root.
- POSIX uses handle-relative `openat` with `O_NOFOLLOW` and `O_DIRECTORY` where applicable. Windows uses `CreateFileW` with `FILE_FLAG_OPEN_REPARSE_POINT` and `FILE_FLAG_BACKUP_SEMANTICS` where applicable, rejects `FILE_ATTRIBUTE_REPARSE_POINT`, and never reopens a validated target through an unchecked string.
- New files use create-new under a verified parent. Atomic replacement uses a verified same-directory temporary and revalidates the destination parent. `Path.resolve()`, `absolute()`, string-prefix checks, or pre-check-then-follow access alone are insufficient.
- A directory-sync `PermissionError` no-op is forbidden for authoritative pointer/attempt/release writes.
- POSIX uses directory descriptor fsync.
- Windows uses a minimal platform-native directory flush implementation or fails closed if durability cannot be established; no new dependency is added.
- Native handles/pointers never enter canonical serialization or state hashes. Resource ownership is explicit; every handle closes in `finally`.
- Temporary files are same-directory, uniquely named, and removed on pre-replace failure.

### 15.2 Required Success Quorum and Planning Authority

Before acquisition, `attempt.json` immutably freezes sorted unique `required_provider_ids`, sorted unique `required_work_item_ids`, the complete provider-to-work-item mapping, and `required_scope_sha256`. V8 has no optional provider, warning-only required failure, degraded active pointer, partial consumer mode, or fallback from an incomplete active release. A failed candidate may retain evidence, but sealing and activation require every required work item to have exactly one adapter-proven terminal success, zero required failures, and at least one successful work item for every required provider.

`ReleaseManifestV1` stores the frozen scope plus `required_provider_count`, `successful_provider_count`, `required_work_item_count`, `successful_work_item_count`, `failed_required_work_item_ids`, `quorum_met`, and `release_health`. A sealable or readable release requires equal required/success counts, `failed_required_work_item_ids=[]`, `quorum_met=true`, and `release_health="complete"`. Seal, recovery commit, activation CAS, rollback-target validation, compatibility export, and every consumer reject every other state. No consumer may silently use a partial release or legacy fallback because a required provider failed.

The manifest also contains one closed `planning_authority` object with exactly `detailed_plan_path`, `detailed_plan_sha256`, `approving_plan_audit_path`, `approving_plan_audit_sha256`, `approving_plan_audit_verdict`, and `implementation_gate`. Required values/contracts:

- `detailed_plan_path` is exactly `.ly_state/session/implementation_plan_macro_v8_detailed_20260810.md`.
- `implementation_gate` is exactly `macro_micro_data_v8_implementation`.
- `approving_plan_audit_verdict` is exactly `[APPROVED]`.
- Both SHA-256 values are lowercase hashes over exact raw file bytes, with no decoding, BOM removal, newline normalization, or canonical reserialization.
- The approving audit is produced after the final detailed-plan bytes, explicitly binds the same detailed-plan SHA-256, and comes from an independent audit role; every pre-remediation audit artifact is ineligible.
- Seal, activation, recovery, rollback-target validation, every authoritative read, compatibility export, and final implementation handoff reopen both files through the containment validator and require exact path/hash/verdict agreement.

### 15.3 Sealed Manifest

`seal_manifest(candidate_dir)` performs:

1. Write/fsync all `12` required non-manifest artifacts; generation-one migration may additionally include only the two authorized byte-preserved legacy files.
2. Reread and validate exact bytes, schemas, row counts, membership, origins, foreign keys, completeness, PIT, required-success quorum, containment, planning-authority hashes, and accounting.
3. Build inventory from required non-manifest paths only; reject any resolved `manifest.json` entry.
4. Include release identity/sequence, cutoff, schema versions, adapter pins, reconciliation-policy identity/knowledge, frozen required scope/quorum, closed planning authority, artifact path/hash/count/fingerprint, current/inherited/origin counts, fixture hashes, and accounting checks.
5. Canonical-serialize once with `state=sealed`; atomically write/fsync; fsync release directory; hash exact bytes.
6. Reopen through the production reader validator before activation.

The manifest is never mutated to another lifecycle state.

### 15.4 Genesis Pointer

Create `data/macro_micro/current.json` only with create-new semantics from exact fixture bytes:

```json
{"activated_at":null,"activation_attempt_id":null,"activation_kind":"genesis","active_manifest_path":null,"active_manifest_sha256":null,"active_release_id":null,"active_release_sequence":0,"legacy_fallback_allowed":true,"pointer_generation":0,"pointer_schema_version":"macro_micro_pointer/v1","previous_pointer_sha256":null,"rollback_floor_release_sequence":0}
```

Declared SHA-256: `76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`. Existing malformed bytes are never guessed, rewritten, or normalized in place.

### 15.5 Activation CAS

`activate_release_cas(expected_pointer_hash, sealed_manifest)` and rollback use the same locked protocol:

1. Open only `data/macro_micro/current.lock` through the containment validator as a non-reparse regular file. Acquire one kernel-backed exclusive lock over byte range `[0,1)` on a retained handle using `LockFileEx` on Windows or `flock(LOCK_EX)` on POSIX; wait for ownership, and raise `PointerLockError` on interruption or OS failure.
2. While holding that same handle, validate the complete attempt ledger and recover the sole allowed prepared nonterminal attempt before starting a new CAS.
3. Read exact prior pointer bytes; validate containment, schema, hash, generation, and expected hash.
4. Revalidate target manifest hash, nonrecursive inventory, all artifacts, required-success quorum, planning authority, sequence, and rollback floor.
5. Allocate immutable `activation_attempt_id`; build generation `current + 1` target bytes embedding that same ID and prior pointer hash.
6. Create/fsync `activation_prepared.json`; fsync its parent before pointer replacement. Store exact prior/target bytes, hashes, generations, target identity/path/hash, timestamp, and prepared-record hash.
7. Write/fsync a verified same-directory temporary pointer; atomically replace `current.json`; fsync pointer directory; reread exact authoritative bytes while locked.
8. Require observed bytes/hash/attempt ID equal the prepared target. Create/fsync `activation_committed.json`; fsync its parent while still locked. Bind attempt ID, prepared hash, target/observed pointer hashes, timestamp, and `recovered=false`.
9. Release the retained lock only after durable commit or abort evidence and its parent directory are fsynced. Ancillary lifecycle events follow; they never substitute for prepare/terminal evidence.

Lock-file contents, PID text, timestamps, existence, or age never signal ownership. `current.lock` is never deleted, replaced, or treated as stale. No alternate lock path, per-attempt lock, or in-process mutex is publication authority.

### 15.6 Deterministic Recovery

`recover_prepared_activation(pointer_path, attempts_dir)` runs only while the sole `current.lock` handle is retained. It enumerates every attempt directory, validates every prepared/commit/abort schema and self-hash, and constructs chains from exact prior/target pointer hashes and generations.

- Every prepared record has zero or exactly one matching terminal record. Commit-plus-abort, duplicate terminal records, duplicate attempt IDs, mismatched prepared hashes, or malformed links fail closed.
- Across the repository, the nonterminal prepared set has cardinality `0` or `1`. Multiple nonterminal records, forks sharing one prior pointer, disconnected generations, conflicting targets, or competing chains raise `POINTER_RECOVERY_DIVERGENCE`.
- Recovery never selects by mtime, filename, directory order, PID text, lock-file age, or highest generation.

For the sole valid prepared record without terminal evidence:

- Pointer exactly equals prepared target and attempt ID: revalidate target; write commit evidence with `recovered=true`; do not rewrite pointer.
- Pointer exactly equals prepared prior: create/fsync `activation_aborted.json` with schema `activation_aborted/v1`, attempt ID, prepared-record hash, prior pointer hash, observed pointer hash, abort timestamp, `recovered=true`, and abort-record SHA-256; fsync its parent and leave the pointer unchanged.
- Any other bytes, hash, generation, or attempt ID: raise `POINTER_RECOVERY_DIVERGENCE`; block activation, rollback, export, and reader fallback until independent remediation.

A crash after pointer replacement is neither success nor failure until recovery durably commits or aborts it.

### 15.7 Attempt Ledger

- `attempt.json` freezes attempt ID, candidate identity, prior pointer hash/generation, sorted required provider IDs, sorted required work-item IDs, provider-to-work-item mapping, `required_scope_sha256`, cutoff, and adapter pins.
- Checkpoints record last hash-verified work transition.
- Append-only events use deterministic sequence ordering and canonical bytes.
- `failure.json` records phase, typed exception/reason, times, artifact hashes, terminal accounting, checkpoints, target manifest, and observed pointer.
- Pre-replacement failure leaves publication authority byte-identical.

### 15.8 Rollback

`rollback_release(expected_pointer_hash, target_release_id)`:

1. Revalidates target release, containment, complete required-success quorum, planning authority, and manifest anchor.
2. Requires positive immutable target sequence at or above `rollback_floor_release_sequence`.
3. Uses the same CAS/WAL protocol and increments pointer generation.
4. Preserves a nondecreasing floor and appends immutable rollback evidence.
5. Allows sequence zero only before `cutover_committed`.

Deleting releases at or above the floor is forbidden and outside V8.

### 15.9 Exit Criteria

- Every read requires `SHA256(exact manifest bytes) == current.json.active_manifest_sha256`.
- Manifest self-inventory count is zero; manifest mutation count is zero.
- Every frozen required provider/work item succeeds before seal/CAS; degraded active releases and partial consumer fallback count is zero.
- Every prepared attempt recovers to committed, aborted, or fail-closed divergence; multiple, duplicate, disconnected, conflicting, or forked nonterminal chains are never selected.
- Unsafe/escaping path acceptance, followed symlinks/junctions/reparse points, planning-authority mismatch, partial activation, generation reuse, decreasing floor, or unanchored release count is zero.
## 16. WP7 - Migration, Pointer-Aware Readers, Compatibility Export

**Owners:** `src/omega/data/macro_micro_release.py`, `src/omega/quant/graph/loader.py`, `scripts/fetch_financial_statements.py`, `src/omega/data/macro_pipeline.py`

### 16.1 Exact Legacy Access Inventory

Freeze this production inventory before editing; line numbers are evidence locations, not patch anchors:

| Path | Current legacy surface | Required end state |
|---|---|---|
| `scripts/fetch_financial_statements.py` | `OUTPUT_PATH` names `data/financial_statements_2015_now.parquet`; `write_parquet()` and `--output` publish directly to it. It is not currently a reader. | Remove direct publication. Retain the path only as the generation-one input identity and the validated post-activation `--output` compatibility target. |
| `src/omega/data/macro_pipeline.py` | `DEFAULT_OUTPUT_PATH` names `data/macro_indicators.parquet`; `MacroDataPipeline.run()` reads, merges, and replaces it; `query_as_of()` directly reads a caller path. | Remove legacy read/merge/query authority. Retain the path only for generation-one migration and any explicitly retained post-activation compatibility projection. |
| `src/omega/quant/graph/loader.py` | `FinancialStatementLoader` accepts an arbitrary path or DataFrame and calls `pd.read_parquet()` directly. | Production historical loading enters through the validated active pointer only. Remove arbitrary path/DataFrame authority and every legacy-file bypass. |
| `src/omega/data/macro_micro_release.py` | No approved tracked legacy reader exists. | Own the only centralized generation-zero fallback, migration input reader, active-release reader, and compatibility-export reader. |

After refactoring, scan production code for both exact literals. Any occurrence outside migration or compatibility-export constants is release-blocking. `scripts/run_graph_bootstrap.py` remains protected and noncanonical; do not edit it or treat its compatibility path as V8 evidence.

### 16.2 Pointer-Aware Reader Contract

Implement one validated reader path in `macro_micro_release.py`; graph, feature, backtest, compatibility-export, and smoke-check callers reuse it instead of opening Parquet directly:

1. Read exact `data/macro_micro/current.json` bytes and validate `macro_micro_pointer/v1`, canonical encoding, generation, active identity, previous-pointer hash, rollback floor, and activation-attempt fields before using any path from it.
2. Permit legacy fallback only when the pointer bytes equal the exact generation-zero sentinel, `pointer_generation=0`, `active_release_sequence=0`, and `legacy_fallback_allowed=true`. A malformed, normalized, or merely equivalent JSON document is not genesis.
3. For an active release, require non-null release/manifest fields, read exact manifest bytes, and require `SHA256(manifest bytes) == active_manifest_sha256` before trusting the manifest.
4. Require `state=sealed`, unanimous required-provider/work-item success, `quorum_met=true`, `release_health="complete"`, and exact planning-authority path/hash/verdict agreement; reject every degraded or partial manifest without fallback.
5. Validate every pointer, manifest, planning-authority, and artifact path through the shared lexical and component-wise no-follow contract before opening it; reject traversal, absolute/UNC/device/ADS paths, symlinks, junctions, mount substitutions, and reparse points.
6. Reject `manifest.json` in its own inventory, validate every required artifact hash/row count/schema fingerprint, and validate membership/origin foreign keys before returning rows.
7. Expose Actual rows only to historical consumers. Forecast rows, unresolved Quarantine rows, mixed release IDs, source-stream collapse, or unapproved reconciliation decisions fail closed.
8. Apply cutoff eligibility through the WP2 provider-native and reconciliation selectors using immutable origin, evidence, policy, candidate, and decision knowledge times. Never use current `materialized_at` to establish historical eligibility.
9. Emit full `metric_id` and source-aware keys. Do not restore `item_code`-only grouping, destructive duplicate choice, degraded mode, or an option that weakens containment, pointer, hash, Forecast, quorum, planning-authority, or PIT validation.

Readers do not repair malformed state. Activation/rollback/export first invoke WP6 recovery under the pointer lock; `POINTER_RECOVERY_DIVERGENCE` blocks reader fallback and all publication operations until independent remediation.

### 16.3 Generation-One Migration

`migrate_generation_one(legacy_paths) -> MigrationReportV1` runs only against the exact valid genesis pointer and creates positive immutable release sequence `1`:

1. Require the expected genesis pointer SHA-256 `76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`; reject an existing active release, malformed pointer, reused sequence, or pre-existing candidate directory.
2. Open `data/financial_statements_2015_now.parquet` and `data/macro_indicators.parquet` read-only through the containment/no-follow validator. Record each repo-relative path, byte count, SHA-256, Parquet schema fingerprint, and row count before parsing.
3. Copy each exact byte stream to release 1 under `migration/legacy/financial_statements_2015_now.parquet` and `migration/legacy/macro_indicators.parquet`; fsync and rehash the copies. Original and copied hashes must match.
4. Normalize rows through the same V8 validators used for new provider evidence. Classify Forecast before Actual validation; admit only evidence-supported Actual rows; route unsupported/conflicting rows to permanent Quarantine rather than inventing publication or revision order.
5. Preserve immutable provider evidence and source separation. Exact duplicate occurrences are accounted for explicitly; they are not hidden by `drop_duplicates` or last-row-wins behavior.
6. For each input independently require `legacy_input_rows == migrated_actual + migrated_forecast + quarantined_rows + exact_duplicate_occurrences`. Require the same equality for the combined totals.
7. Write all `12` standard non-manifest release artifacts plus the two byte-preserved migration inputs. Record input hashes, disposition counts, duplicate counts, reason counts, output artifact hashes, and accounting checks in `migration/report.json`.
8. Seal release 1 through WP6. The sealed manifest inventories both preserved legacy files and every standard non-manifest artifact, but never inventories itself.

Any missing file, hash drift, parse failure, unaccounted row, schema mismatch, unsupported evidence, or seal failure raises `MigrationError`, writes durable attempt failure evidence, and leaves the original files, genesis pointer, and every prior release byte-identical.

### 16.4 Two-CAS Cutover

Cutover is two separate pointer generations; never combine activation and floor advance:

1. CAS from exact genesis to sealed release 1 using the WP6 prepare/replace/commit protocol. Keep rollback floor `0` and `legacy_fallback_allowed=true` in this first active generation.
2. Through the authoritative pointer, run manifest/artifact validation, pointer-aware Actual reads, representative cutoff queries, and the required compatibility export.
3. If any pre-floor smoke or export step fails, use the same WAL/CAS protocol to return authority to genesis. Record the failed cutover attempt; preserve release 1 and all legacy bytes for diagnosis.
4. Only after every smoke/export check passes, perform a second CAS that retains release 1, increments pointer generation, sets `rollback_floor_release_sequence=1`, and sets `legacy_fallback_allowed=false`.
5. Verify the second pointer bytes and durable commit evidence while locked, then append immutable `cutover_committed` evidence bound to that pointer hash and generation.

After `cutover_committed`, sequence `0` is unreachable, missing/corrupt active data hard-fails, and no legacy fallback or manual path override is legal.

### 16.5 Validated `--output` Compatibility Export

Keep `scripts/fetch_financial_statements.py --output PATH`; redefine it as a projection, never publication authority:

1. Run only after successful activation or against an already active validated release.
2. Read through the pointer-aware production reader; export only financial Actual rows eligible under the active release contract. Forecast, Quarantine, and nonselected reconciliation candidates are excluded.
3. Preserve the legacy column/order contract required by existing consumers while sourcing values from full V8 metric/source identities without destructive dedupe.
4. Require `PATH` to pass the same repository-relative lexical and component-wise no-follow validator; absolute, traversal, UNC/device/ADS, symlink, junction, mount, and reparse targets fail before any write.
5. Write a verified same-directory temporary Parquet file with metadata `macro_micro_release_id`, `macro_micro_manifest_sha256`, and `macro_micro_schema_version`; fsync, reopen through the retained parent, validate rows/metadata, then atomically replace the target.
6. Reject a target inside `data/macro_micro/releases/` or equal to any pointer, lock, manifest, receipt, evidence, attempt-ledger, planning-authority, or other immutable artifact path.
7. On failure, delete only the temporary file, preserve the previous export byte-for-byte, append `compatibility_export_failed`, and return nonzero.

Before the floor commit, export or smoke failure triggers the genesis rollback in section 16.4. After the floor commit, export failure never changes the authoritative pointer and never re-enables fallback.

### 16.6 Rollback Floor and Reader Failure Tests

Add migration/reader/compatibility cases to `tests/test_macro_micro_release.py`, `tests/test_financial_loader.py`, and `tests/test_fetch_financial_statements.py` proving:

- Exact genesis is the only state that permits legacy fallback.
- Release 1 preserves both legacy files byte-for-byte and satisfies per-input plus aggregate accounting.
- The two CAS operations create distinct monotonic pointer generations; the second sets floor `1` without changing the active release.
- Rollback below the floor fails; rollback at or above the floor revalidates the target and uses the same WAL/CAS path.
- Active readers reject manifest-anchor drift, missing artifacts, hash/schema/count drift, mixed membership, future origins, Forecast leakage, and unresolved reconciliation.
- `--output` is Actual-only, carries all three metadata keys, preserves the previous export on failure, and cannot target immutable storage.
- Pre-floor export failure returns to genesis; post-floor export failure preserves the active pointer.
- Original legacy bytes and prior release bytes remain unchanged across success, failure, recovery, export, and rollback.

### 16.7 Exit Criteria

- Production direct-read inventory outside centralized migration/fallback/export logic is zero.
- Release sequence `1` is sealed from hash-preserved legacy inputs with complete row accounting.
- Cutover uses exactly two successful CAS generations before `cutover_committed`.
- Historical consumers are pointer-only, Actual-only, source-aware, and cutoff-safe.
- Historical consumers reject incomplete quorum, degraded state, planning-authority drift, unsafe paths, and every followed link/reparse point.
- Rollback floor never decreases; sequence `0` is legal only before floor commit.
- Compatibility export failure cannot corrupt the old export or canonical authority.

## 17. WP8 - Dependency, Checklist, Failure Baseline, Gate Hardening

**Owners:** `.python-version`, `requirements.txt`, `.agents/scripts/checklist.py`, `scripts/sod_gate_enforcer.py`, `tests/test_strict_repo_local_skill_loading.py`, `tests/test_macro_micro_acceptance_runner.py`; conditional evidence owner: `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json`

### 17.1 Dependency Boundary

- Add `.python-version` with exact UTF-8 text `3.14.4` plus one trailing newline. The acceptance runner requires CPython with `sys.version_info == (3, 14, 4, "final", 0)` and rejects every other implementation/version before spawning a child.
- Require exact `pyarrow==23.0.1` and `playwright==1.62.0` pins in `requirements.txt`; add exactly one new dependency, `pypdf==6.15.0`.
- Use it only for embedded-text extraction from the hash-verified SBV PDF after HTTP, content-type, magic-byte, and fixture checks.
- Add no OCR package, alternate PDF parser, HTML-table fallback, custom PDF parser, validation framework, service, database, or second PDF dependency.
- Install the browser only with `python -m playwright install chromium`. The accepted browser is the Playwright-managed Chromium revision `1234`, reporting browser version `151.0.7922.34`; a system browser, custom `executable_path`, different revision/version, or alternate channel is forbidden.
- Before any acceptance command, record and validate CPython implementation/version, `pyarrow`, `playwright`, and `pypdf` versions, exact installed Playwright `driver/package/browsers.json` path/byte count/lowercase SHA-256, resolved managed browser executable path, Chromium revision, and reported browser version. Any drift is a pre-spawn contract failure.

### 17.2 Exact UTF-8 Startup Repair

In `.agents/scripts/checklist.py`, add exactly one helper near the imports:

```python
def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors='replace')
```

Call `_configure_utf8_stdio()` once immediately after its definition, before `Colors`, argparse behavior, helper calls, headers, icons, warnings, errors, or any other output path. If `reconfigure` is absent, keep the existing stream untouched; never detach, replace, or close it. Preserve Unicode output rather than deleting symbols to conceal the encoding defect.

The production checklist command remains exactly:

```powershell
python .agents/scripts/checklist.py . --skip-performance
```

### 17.3 Forced-`cp1252` Regression

Add `tests/test_strict_repo_local_skill_loading.py::test_checklist_stdout_is_utf8_safe_under_cp1252`:

1. Launch a fresh Python subprocess with `PYTHONUTF8=0` and `PYTHONIOENCODING=cp1252`.
2. Import `.agents/scripts/checklist.py` without replacing its stdout/stderr objects.
3. Exercise `print_header`, `print_step`, `print_success`, `print_warning`, and `print_error` with representative Unicode content.
4. Capture raw stdout/stderr bytes; require process exit `0` and strict UTF-8 decoding of both streams.
5. Fail on `UnicodeEncodeError`, early output before configuration, missing helper coverage, or replacement/closure of inherited streams.

The release-blocking delimiter is exact: the simulated `cp1252` subprocess and exact checklist command both exit `0`; UTF-8 output never raises `UnicodeEncodeError`.

### 17.4 Five Inherited Full-Suite Failures

Before requesting any exception, reproduce, diagnose, and prefer fixing these exact inherited node IDs:

1. `tests/test_extract_lessons.py::test_extract_lessons_fails_closed_for_malformed_store_and_lock_contention`
2. `tests/test_market_release_gates.py::test_release_gate_replay_uses_supplied_durable_ledger`
3. `tests/test_market_release_gates.py::test_downstream_release_failure_does_not_consume_lifecycle_receipt`
4. `tests/test_market_release_gates.py::test_dry_run_validation_does_not_consume_lifecycle_receipt`
5. `tests/test_vci_updater_validation_write_blocker.py::TestCombinedValidationWriteBlocker::test_write_proceeds_when_combined_valid`

No node is grandfathered. Fix every failure caused, exposed, or behaviorally affected by a V8 changed file or execution flow. Capture pre-change and post-change reproduction under frozen-tree identities before classifying any remaining failure as pre-existing and unrelated.

### 17.5 Conditional Baseline Exception

The only permitted path is `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json`. Do not create it unless attempted fixes leave exact failures independently proven pre-existing, unrelated, reproducible, and eligible for Role 20 approval.

Exact `baseline_exception/v1` contract:

| Field | Required value/evidence |
|---|---|
| `schema_version` | Exactly `baseline_exception/v1`. |
| `gate` | Exactly `macro_micro_data_v8_implementation`; `macro_micro_data_v8_plan` is forbidden. |
| `command` | Exactly `python -m pytest -q`. |
| `command_output_path`, `command_output_sha256` | Immutable repo-relative output evidence and exact lowercase SHA-256. |
| `baseline_revision`, `implementation_revision` | Git revisions or explicit immutable dirty-tree evidence IDs. |
| `failing_node_ids` | Sorted unique exact pytest node IDs. |
| `pre_change_reproduction`, `post_change_reproduction` | Each records exit code, output path/hash, and RFC3339 `observed_at`. |
| `non_impact_proof` | Exact changed files, affected-flow evidence path/hash, and a specific non-impact statement. |
| `owner` | Named remediation owner. |
| `expires_at` | RFC3339 timestamp no more than `30` days after approval. |
| `independent_approval` | Actual Role 20 session identity, audit path, `[APPROVED_EXCEPTION]`, and approval timestamp. |

Constraints:

- `failing_node_ids` must be a subset of the five IDs in section 17.4 and exactly equal the failures being waived in the recorded full-suite output.
- L2 may write reproduction and non-impact evidence but may not populate, simulate, or claim independent approval.
- Approval is valid only when file-backed, unexpired, bound to exact output hashes and tree/revision evidence, and written by an independent Role 20 session.
- Focused tests, strict gate-control tests, checklist, and gate enforcer are never excepted.
- Any changed failure set, output hash, affected flow, expiry, implementation tree, or approval evidence invalidates the exception and requires fresh reproduction/review.

### 17.6 Implementation-Gate and Enforcer Separation

- Leave every `macro_micro_data_v8_plan` record and approval byte untouched. This detailed plan does not create, edit, approve, or pre-populate it.
- Bind future code, fixtures, tests, implementation report, exception, independent implementation audit, and gate metadata only to `macro_micro_data_v8_implementation`.
- In `scripts/sod_gate_enforcer.py`, validate post-cutoff required fields directly, independent of strict-gate discovery. Discovery determines applicable gates; it must not suppress required-field validation for an applicable post-cutoff record.
- Keep required gate-control regressions in `tests/test_strict_repo_local_skill_loading.py`; tests use isolated temporary metadata and never edit `.ly_state/session/phase_gates.json`.
- A valid future implementation-gate record contains concrete `phase_name`, timestamp, L2/L3 session and role identities, literal Boolean `l2_completed=true`, a concrete nonempty non-placeholder `l3_session_key`, audit path, bracketed verdict, SOD booleans, exact repo-local role/skill evidence, and forbidden-path scan evidence.
- Reject `l2_completed` when absent, null, string-valued, or false. Reject `l3_session_key` when absent, null, non-string, empty/whitespace-only, or a placeholder such as `pending`, `unknown`, `todo`, or `tbd`.
- Reject placeholders, copied prior-session IDs, missing timestamps, cross-gate evidence, self-approval, unapproved exception data, or any attempt to reuse, replace, amend, or overwrite `macro_micro_data_v8_plan` history.
- Implementation work and tests never write gate metadata. Only independent L3 writes the concrete implementation gate after review; L1 then reruns `python scripts/sod_gate_enforcer.py`.

### 17.7 Exit Criteria

- `.python-version` pins CPython `3.14.4`; `requirements.txt` pins PyArrow `23.0.1`, Playwright `1.62.0`, and adds only `pypdf==6.15.0` for V8.
- Acceptance rejects runtime/browser drift before child spawn and records the exact managed Chromium revision `1234` / version `151.0.7922.34` plus `browsers.json` hash.
- Checklist configures inherited stdout/stderr before every print path; forced `cp1252` and production commands both exit `0`.
- The five inherited failures are fixed or covered by the exact valid, unexpired, independently approved implementation-gate exception.
- Focused tests, gate-control tests, checklist, and enforcer have no waiver path.
- Gate-control tests require literal `l2_completed=true` and a concrete nonempty `l3_session_key`.
- `macro_micro_data_v8_plan` bytes and approval history remain unchanged; all implementation evidence names `macro_micro_data_v8_implementation`.

## 18. WP9 - Exact Fixtures, Tests, PIT Trail, Quantitative Gates

**Owners:** `tests/fixtures/macro_micro/v8/`, `tests/test_fetch_financial_statements.py`, `tests/test_macro_pipeline.py`, `tests/test_financial_loader.py`, `tests/test_macro_micro_release.py`, `tests/test_macro_micro_acceptance_runner.py`, `tests/test_strict_repo_local_skill_loading.py`

### 18.1 Exact 29-Path Fixture Inventory

Create exactly these `29` V8 fixture paths; add no aliases, duplicate snapshots, live-response caches, or alternate expected files:

1. `tests/fixtures/macro_micro/v8/provider_contract.json`
2. `tests/fixtures/macro_micro/v8/vci/request_contract.json`
3. `tests/fixtures/macro_micro/v8/vci/income_statement_raw.json`
4. `tests/fixtures/macro_micro/v8/vci/income_statement_year.json`
5. `tests/fixtures/macro_micro/v8/vci/income_statement_quarter.json`
6. `tests/fixtures/macro_micro/v8/vci/balance_sheet_raw.json`
7. `tests/fixtures/macro_micro/v8/vci/balance_sheet_year.json`
8. `tests/fixtures/macro_micro/v8/vci/balance_sheet_quarter.json`
9. `tests/fixtures/macro_micro/v8/vci/cash_flow_raw.json`
10. `tests/fixtures/macro_micro/v8/vci/cash_flow_year.json`
11. `tests/fixtures/macro_micro/v8/vci/cash_flow_quarter.json`
12. `tests/fixtures/macro_micro/v8/vci/ratios_raw.json`
13. `tests/fixtures/macro_micro/v8/vci/ratios_year_expected.json`
14. `tests/fixtures/macro_micro/v8/vci/ratios_quarter_expected.json`
15. `tests/fixtures/macro_micro/v8/vci/ratios_contract.json`
16. `tests/fixtures/macro_micro/v8/world_bank/cpi_page_1.json`
17. `tests/fixtures/macro_micro/v8/world_bank/gdp_growth_page_1.json`
18. `tests/fixtures/macro_micro/v8/world_bank/m2_growth_page_1.json`
19. `tests/fixtures/macro_micro/v8/yahoo/usdvnd_chart.json`
20. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_article_root.html`
21. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31.pdf`
22. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_contract.json`
23. `tests/fixtures/macro_micro/v8/sbv/weekly_2026-07-27_2026-07-31_expected_rows.json`
24. `tests/fixtures/macro_micro/v8/reconciliation/future_policy.json`
25. `tests/fixtures/macro_micro/v8/reconciliation/future_decision.json`
26. `tests/fixtures/macro_micro/v8/serialization/canonical_json_cases.json`
27. `tests/fixtures/macro_micro/v8/forecast/classification_cases.json`
28. `tests/fixtures/macro_micro/v8/pit/acceptance_trail.json`
29. `tests/fixtures/macro_micro/v8/pointer/genesis_current.json`

`provider_contract.json` is the root fixture index. It records every fixture path/hash, adapter ID/version, exact provider literal, expected schema/count, completeness mode, and work-accounting invariant. Adapter constants equal fixture literals. Tests never use live network.

### 18.2 Fixture Integrity Contracts

- JSON and HTML fixtures are immutable UTF-8. The SBV PDF is exact binary evidence. Hash every fixture before parsing and compare it to the owning contract.
- The FPT ratio fixture has exactly `41` rows partitioned as `8` annual, `33` quarterly, and `0` leftovers.
- The SBV article-root fixture is acquired from the official source with a repository script or Playwright; its byte count and lowercase SHA-256 are determined from the actual downloaded file and recorded in the owning contract before offline tests. L2 must not invent either value.
- The SBV PDF fixture is acquired from the official source with a repository script or Playwright; its byte count and lowercase SHA-256 are determined from the actual downloaded file and recorded in the owning contract before offline tests. L2 must not invent either value.
- The SBV expected rows contain exactly `VND` and `USD`, seven tenors, and the pinned `VND` nine-month null; no fallback-derived row is accepted.
- Reconciliation fixtures introduce future policy and future decision knowledge without changing output for an earlier cutoff.
- Serialization and forecast fixtures cover all accepted cases plus unknown fields, malformed values, nonfinite numbers, and ambiguous forecast evidence.

`tests/fixtures/macro_micro/v8/pointer/genesis_current.json` uses these exact UTF-8 bytes, with no BOM or trailing newline:

```json
{"activated_at":null,"activation_attempt_id":null,"activation_kind":"genesis","active_manifest_path":null,"active_manifest_sha256":null,"active_release_id":null,"active_release_sequence":0,"legacy_fallback_allowed":true,"pointer_generation":0,"pointer_schema_version":"macro_micro_pointer/v1","previous_pointer_sha256":null,"rollback_floor_release_sequence":0}
```

Its declared SHA-256 is `76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd`. `test_genesis_fixture_is_valid_canonical_json_with_declared_sha256` parses, canonical-reserializes, compares exact bytes, rejects BOM/trailing newline, and verifies that hash. Pointer initialization uses create-new semantics and never normalizes an existing file.

### 18.3 Test Ownership

- `tests/test_fetch_financial_statements.py`: exactly four VCI transports, eight logical outputs, three dual-branch statement envelopes, exact `RawReceiptV1` field/type/nullability validation, acquisition-unique IDs/ordinals, raw-body and metadata-plus-body hash vectors, strict ratio partition, request literals, deterministic locators, replay, terminal accounting, no truncation, activation ordering, and Actual-only `--output` export.
- `tests/test_macro_pipeline.py`: World Bank numbered pagination, Yahoo terminal envelope, SBV selectors/title/date/attachment/hash/PDF table, date-only publication, first-receipt availability, append-only native revisions, durable provider failure, and no direct legacy authority.
- `tests/test_financial_loader.py`: exact pointer/manifest validation, pointer-only Actual reads, full metric IDs, source-aware streams, cutoff-safe reconciliation, rematerialization invariance, and Forecast/Quarantine rejection.
- `tests/test_macro_micro_release.py`: canonical bytes, identity separation, membership/origin, singleton replay/conflict, ordered collision rules, reconciliation knowledge, derived lineage, forecast classification, permanent Quarantine, path-containment attacks, unanimous required-success quorum, closed planning-authority hashes, nonrecursive manifests, pointer anchoring, sole-lock concurrency, prepared/commit/abort recovery-chain rejection, generation-one migration, two-CAS cutover, compatibility failure, rollback floor, and PIT invariance.
- `tests/test_macro_micro_acceptance_runner.py`: sole-parent process enforcement, immutable argv order, `shell=False`, direct binary stdout/stderr capture, exact integer return codes, flush/fsync/close-before-hash behavior, byte counts, create-new result/transcript files, accepted-L2 transcript linkage, runtime/browser pin rejection, and overwrite/reuse rejection.
- `tests/test_strict_repo_local_skill_loading.py`: forced-`cp1252` checklist regression plus direct post-cutoff implementation-gate validation, cross-gate rejection, literal Boolean `l2_completed=true`, concrete nonempty non-placeholder `l3_session_key`, missing-field rejection, and writer/auditor separation.

Each focused test uses temporary directories and exact fixtures. Tests must not edit production data, legacy inputs, prior releases, `.ly_state/session/phase_gates.json`, plan-gate history, or the conditional baseline exception.

### 18.4 Required Failure and Recovery Matrix

At minimum, exercise these release- or handoff-blocking transitions:

1. `RawReceiptV1` rejects unknown/missing fields, wrong Arrow types/nullability, malformed hashes, duplicate `(attempt_id, acquisition_ordinal)`, duplicate `source_receipt_id`, reused retry ordinals, or conflicting identity bytes; exact vectors reproduce `source_receipt_id`, `raw_body_size`, `raw_body_sha256`, and domain-separated `receipt_sha256`, and every bound metadata/body mutation changes or invalidates the receipt hash.
2. Identical receipt/evidence/revision replay is byte-stable and a canonical no-op; each singleton adapter accepts one immutable evidence item and quarantines conflicting second evidence as `REVISION_SINGLETON_CONFLICT`, with no fabricated order or hash tie-break.
3. Later receipt, policy, decision, Forecast, rematerialization, or rollback evidence cannot alter an earlier-cutoff result.
4. Missing/failed/duplicate required work, a required provider with zero successful work, frozen-scope hash drift, unequal required/success counts, nonempty `failed_required_work_item_ids`, `quorum_met!=true`, or `release_health!="complete"` blocks seal, recovery commit, activation CAS, rollback-target use, export, and every read; no degraded pointer, partial consumer mode, or legacy fallback is selected.
5. Empty, NUL, backslash, traversal, absolute, drive, UNC, device, ADS, reserved-name, trailing-dot/space, or empty-segment paths fail before I/O; root/intermediate/final symlinks, junctions, mount substitutions, and reparse points fail under component-wise no-follow access before read, write, replace, lock, recovery, export, or evidence creation.
6. Missing/extra planning-authority fields, wrong detailed-plan path/hash, wrong approving-audit path/hash, non-`[APPROVED]` verdict, pre-remediation audit, wrong implementation gate, or post-seal byte mutation blocks seal, activation, recovery, rollback, read, and handoff.
7. Manifest self-inventory, manifest mutation, pointer-anchor mismatch, artifact hash/count/schema drift, future origin, mixed membership, and missing required empty artifact all fail before row return.
8. Only the retained kernel lock on `data/macro_micro/current.lock` serializes activation/rollback; alternate lock paths, lock-file text/PID/mtime/existence ownership, deletion/replacement, or concurrent unlocked CAS fail closed.
9. The repository-wide prepared nonterminal set has cardinality `0` or `1`; duplicate records, multiple chains, shared-prior forks, disconnected generations, conflicting targets, or competing chains raise `POINTER_RECOVERY_DIVERGENCE` and are never selected by mtime or name.
10. Crash before pointer replacement recovers to durable `ActivationAbortV1`; crash after exact target replacement recovers to durable commit without rewriting the pointer; divergent bytes/generation/attempt ID fail as `POINTER_RECOVERY_DIVERGENCE`.
11. Gate-control tests reject absent/null/string/false `l2_completed`, absent/null/non-string/blank/placeholder `l3_session_key`, copied sessions, cross-gate evidence, or self-approval; only literal Boolean `l2_completed=true` plus a concrete independent L3 session key may reach post-L3 acceptance.
12. The acceptance runner is the direct parent of every child, uses immutable argv with `shell=False`, captures stdout/stderr to direct binary files, waits for and records the exact integer return code, fsyncs/closes before byte count and SHA-256, and rejects manual evidence, overwrite, append, reused logs, or mixed run IDs.
13. Any CPython, PyArrow, Playwright, Chromium revision/version, or `browsers.json` hash drift fails before the runner spawns a child; L2 and post-L3 transcripts bind the verified runtime and accepted prior transcript.
14. Migration accounts for every row per input, preserves both legacy byte streams, and leaves genesis/legacy/prior releases unchanged on every injected failure.
15. Pre-floor export failure WAL-rolls back to genesis; post-floor export failure preserves authority and the old export.
16. Forecast is classified before historical validation and appears in zero Silver, Derived, loader, graph, feature, or backtest outputs.

### 18.5 Exact PIT Acceptance Trail

`tests/fixtures/macro_micro/v8/pit/acceptance_trail.json` contains ordered receipt, policy, reconciliation-decision, rematerialization, rollback, and cutoff events plus expected canonical consumer bytes and SHA-256 at each cutoff.

The exact test is:

`tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable`

The exact executable trail command is:

```powershell
python -m pytest tests/test_macro_micro_release.py::test_pit_acceptance_trail_replay_is_byte_stable -q
```

It proves all of the following in one deterministic replay:

- Future receipt, provider revision, policy, reconciliation decision, Forecast, rematerialization, and rollback evidence changes `0` consumer bytes for every earlier cutoff.
- Repeating the complete trail is idempotent; every expected byte sequence and SHA-256 matches the fixture.
- Rematerialization changes only `release_id` and `materialized_at`; it preserves `origin_ingested_at`, `revision_id`, cutoff eligibility, and canonical consumer SHA-256.
- Policy, candidate, and decision knowledge are all eligible before a reconciled row can be selected.

### 18.6 Quantitative Release Gates

All gates are release-blocking:

- VCI: `4/4` raw transports; `8/8` logical outputs; all three statement envelopes contain both branches; pinned FPT ratio accounting is `41 = 8 + 33 + 0`.
- SBV: article and PDF documents pass format-aware structural validation and expected-content checks; exactly one title/date/attachment match; exact two-row tenor table; zero fallback extraction.
- Completeness: `100%` work items declare one completeness mode and end in terminal success or a durable failed attempt.
- Raw receipts: `100%` rows match the exact `RawReceiptV1` field/type/nullability contract; `(attempt_id, acquisition_ordinal)` and `source_receipt_id` are repository-unique; `100%` raw-body sizes/hashes and metadata-plus-body receipt hashes reproduce; accepted collisions or mutations equal `0`.
- Activation quorum: required/success provider and work-item counts are equal, failed required work is `0`, `quorum_met=true`, and `release_health="complete"` for `100%` sealed/active/readable releases; degraded activations and fallback reads equal `0`.
- Containment: unsafe/escaping path acceptance and followed root/intermediate/final symlink, junction, mount, or reparse-point count is `0` across authoritative reads/writes/replaces/locks/recovery/exports/evidence.
- Planning authority: `100%` sealed manifests reproduce the exact detailed-plan and independent approving-audit raw-byte SHA-256 values, path literals, `[APPROVED]` verdict, and `macro_micro_data_v8_implementation` gate; accepted mismatches equal `0`.
- Integrity: `100%` receipt, evidence, planning-authority, manifest, pointer, acceptance transcript, and raw Quarantine hashes reproduce.
- Membership/revision: `0` mixed releases, future origins, source-stream collapses, singleton replacements, order ties, or hash tie-breaks; rematerialization changes `0` consumer bytes.
- PIT reconciliation: `100%` selected decisions have eligible policy/candidate/decision knowledge at cutoff; future evidence changes `0` earlier bytes.
- Forecast leakage: `0` Forecast rows in Silver, Derived, historical loaders, graph, feature, or backtest paths.
- Publication evidence: `0` invented publication times; date-only rows use exact dates plus first-receipt availability.
- Pointer lock/recovery: exactly one authority path, `data/macro_micro/current.lock`; ambiguous, duplicate, multiple, disconnected, conflicting, or forked nonterminal chains selected equals `0`; every unambiguous prepared attempt ends committed or aborted.
- Gate metadata: `100%` accepted implementation records contain literal Boolean `l2_completed=true` and a concrete nonempty non-placeholder `l3_session_key`; invalid variants accepted equals `0`.
- Runtime/transcript: exact CPython `3.14.4`, PyArrow `23.0.1`, Playwright `1.62.0`, Chromium revision `1234` / version `151.0.7922.34`; `100%` child streams, byte counts, integer exit codes, result hashes, transcript hashes, and L2/post-L3 linkage are captured by the sole parent runner; overwritten or reused artifacts equal `0`.
- Release safety: `0` manifest self-inventory entries, manifest mutations, unanchored manifests, partial activations, mixed releases, or rollback-floor violations.
- Checklist: forced `cp1252` subprocess and exact production checklist command both exit `0`; UTF-8 output raises `0` `UnicodeEncodeError` instances.

Silver and Derived may contain zero rows only when every requested record and exclusion is hash-evidenced and fully accounted for.

### 18.7 Exit Criteria

- Fixture inventory count is exactly `29`; every path, byte stream, hash, schema, and expected count matches its contract.
- All six owned test files cover their assigned contracts without live network or production-state mutation.
- The exact PIT trail passes repeatedly with identical consumer bytes and hashes.
- Every one of the eight final deep-audit closures has a focused rejection test and a quantitative release/handoff gate.
- Every quantitative gate in section 18.6 passes before WP10 begins.

## 19. WP10 - Frozen-Tree Acceptance Evidence and Handoff

**Owners:** `scripts/run_macro_micro_v8_acceptance.py`, `tests/test_macro_micro_acceptance_runner.py`, future L2 implementation report/evidence artifacts; independent L3 owns implementation audit/gate metadata; L1 owns the post-L3 runner invocation

### 19.1 Acceptance Entry Freeze

WP10 begins only after all production, dependency, checklist, enforcer, fixture, runner, and test edits stop and every WP0-WP9 exit criterion is locally satisfied. Manual child-command execution is diagnostic only and never acceptance evidence.

Before the first L2 child spawn, the sole parent runner creates one immutable implementation-tree record containing:

1. Current Git `HEAD`, or the explicit baseline revision when testing a dirty worktree.
2. Exact staged and unstaged implementation-path lists plus SHA-256 values of their binary diffs.
3. Sorted untracked implementation paths with each exact file-byte SHA-256.
4. Exact raw-byte SHA-256 for the approved master, this detailed plan, the subsequent independent approving plan audit, all changed source/test/fixture/dependency/checklist/enforcer/runner inputs, both legacy inputs, `data/macro_micro/current.json`, and every pre-existing release artifact.
5. The exact closed manifest `planning_authority` values: detailed-plan path/hash, approving-plan-audit path/hash/verdict, and `macro_micro_data_v8_implementation`.
6. Predeclared acceptance-output roots excluded from implementation-input identity only because the runner creates them.
7. One deterministic lowercase `implementation_tree_id` over canonical record bytes.

Recompute the same implementation-input identity after every L2 child and before post-L3 command 5. Any source, test, fixture, dependency, checklist, enforcer, runner, legacy, pointer, prior-release, master, detailed-plan, or approving-plan-audit byte change invalidates the run. Independent implementation-audit/gate artifacts and new acceptance run directories are the only allowed post-L2 additions; they do not alter the frozen implementation inputs. Remediation requires a new L2 run ID starting at command 1.

### 19.2 Sole Parent and Exact Two-Phase Command Table

Acceptance evidence is valid only when `scripts/run_macro_micro_v8_acceptance.py` is the direct parent process. L2 invokes exactly:

```powershell
python scripts/run_macro_micro_v8_acceptance.py --phase l2
```

After independent L3 writes valid implementation-gate metadata, L1 invokes exactly:

```powershell
python scripts/run_macro_micro_v8_acceptance.py --phase post-l3 --accepted-l2-transcript-path <repo-relative-transcript.json> --accepted-l2-transcript-sha256 <64-lowercase-hex>
```

The runner owns this immutable ordered child argv table; `<PYTHON>` means the already validated `sys.executable` absolute path and is not caller-configurable:

1. `--phase l2`: `['<PYTHON>', '-m', 'pytest', 'tests/test_fetch_financial_statements.py', 'tests/test_macro_pipeline.py', 'tests/test_financial_loader.py', 'tests/test_macro_micro_release.py', 'tests/test_macro_micro_acceptance_runner.py', 'tests/test_strict_repo_local_skill_loading.py', '-q']`
2. `--phase l2`: `['<PYTHON>', '-m', 'pytest', 'tests/test_strict_repo_local_skill_loading.py', '-q']`
3. `--phase l2`: `['<PYTHON>', '-m', 'pytest', '-q']`
4. `--phase l2`: `['<PYTHON>', '.agents/scripts/checklist.py', '.', '--skip-performance']`
5. `--phase post-l3`: `['<PYTHON>', 'scripts/sod_gate_enforcer.py']`

`--phase l2` runs commands 1-4 sequentially. `--phase post-l3` runs only command 5, validates the accepted L2 transcript path/hash, verifies unchanged frozen implementation inputs, and rejects the gate before spawn unless `macro_micro_data_v8_implementation` contains literal Boolean `l2_completed=true` plus a concrete nonempty non-placeholder `l3_session_key`. Commands are never reordered, combined, parallelized, omitted, shell-expanded, or replaced.

### 19.3 Runtime Preflight and Immutable Run Layout

Before any child spawn in either phase, the runner requires CPython `3.14.4`, `pyarrow.__version__ == '23.0.1'`, installed `playwright == '1.62.0'`, managed Chromium revision `1234`, browser executable version `151.0.7922.34`, and the exact installed Playwright `browsers.json` path/hash. Version, executable, revision, metadata-file, or hash drift exits nonzero before `Popen`.

Each invocation creates `.ly_state/session/acceptance/macro_micro_data_v8_implementation/<run_id>/` with directory create-new semantics; `run_id` is UTC `YYYYMMDDTHHMMSSffffffZ_<uuid4hex>`. Before spawn it writes/fsyncs create-new canonical UTF-8 `run.json` containing phase, repo root, `implementation_tree_id`, ordered child argv arrays, runtime/browser metadata, exact environment overrides, and either explicit `accepted_l2_transcript=null` for L2 or the validated repo-relative L2 transcript path/hash/byte count for post-L3.

The post-L3 runner opens the accepted L2 transcript through the section 15.1 containment/no-follow contract, verifies its exact-byte SHA-256 and schema, requires `phase='l2'` with successful commands 1-4 under the same `implementation_tree_id`, and records that immutable link in both `run.json` and `transcript.json`. Missing, overwritten, reused-as-post-L3, cross-tree, or mismatched L2 evidence is rejected before command 5.

### 19.4 Exact Child Stream, Exit-Code, and Hash Procedure

For each phase command, the parent creates `command_<nn>/`, opens `stdout.bin` and `stderr.bin` once in exclusive binary `xb` mode, then directly calls:

```python
subprocess.Popen(
    argv,
    shell=False,
    cwd=repo_root,
    stdin=subprocess.DEVNULL,
    stdout=stdout_handle,
    stderr=stderr_handle,
    env=env,
)
```

`env` is the recorded inherited environment with exactly these required overrides: `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and `PYTHONUNBUFFERED=1`. No shell, pipe, tee, inherited console stream, intermediate wrapper, decoder, newline normalizer, truncator, or postprocessor may stand between child and binary file.

The parent records the RFC3339 UTC start timestamp, calls `wait()`, reads the exact integer `Popen.returncode`, records the end timestamp, flushes and `os.fsync()`s both stream handles, closes both handles, obtains exact byte counts, then computes streaming lowercase SHA-256 over the closed files' exact bytes. It writes/fsyncs/closes create-new canonical UTF-8 `command_<nn>/result.json` containing ordinal, phase, argv, timestamps, working directory, environment overrides, integer exit code, stdout/stderr repo-relative paths, byte counts, SHA-256 values, `implementation_tree_id` before/after, parsed test counts where applicable, and command-3 exception path/hash or `none`. No exit code is inferred from text and no stream byte is decoded or rewritten before count/hash.

After the phase ends, the parent verifies every `result.json` and stream hash, then writes/fsyncs/closes create-new canonical UTF-8 `transcript.json` containing phase, run ID, `implementation_tree_id`, `run.json` hash, ordered result paths/hashes, runtime/browser metadata, aggregate result, and accepted L2 transcript linkage. It fsyncs the run directory, then computes the transcript's exact post-close byte count and streaming lowercase SHA-256 for the implementation report. A rerun always creates a new run directory; overwrite, append, path reuse, stream reuse, result reuse, transcript reuse, or mixing artifacts across run IDs is invalid.

### 19.5 Result Rules

- Commands `1`, `2`, `4`, and `5` must exit integer `0`; no baseline exception can waive them.
- Command `3` must exit integer `0` unless its only failures are the exact current, pre-existing, unrelated node IDs covered by a valid, unexpired, independently approved `.ly_state/session/baseline_exceptions/macro_micro_data_v8_implementation_full_suite_20260810.json` bound to `macro_micro_data_v8_implementation`.
- A child interrupted, timed out, spawn-failed, run from another directory, run with an unrecorded environment override, or missing complete stdout/stderr/result/transcript evidence is failed evidence and requires a fresh L2 sequence.
- The five inherited node IDs are not accepted from memory or a prior log. Their current failure set and output hash must match the exception exactly.
- Focused-test, runner-test, strict-test, checklist, enforcer, PIT-trail, fixture-hash, planning-authority, protected-byte, runtime-pin, transcript, or quantitative-gate failure always blocks handoff.

### 19.6 Hashed Evidence and SOD Handoff

1. L2 records the L2 run ID, exact `run.json` and `transcript.json` repo-relative paths/hashes/byte counts, every command result/stream path/hash/byte count/exit code, fixture inventory, `pypdf` version, quantitative gates, PIT output/hash, planning-authority validation, protected before/after hashes, final implementation inventory, and command-3 exception path/hash or `none`.
2. L2 submits implementation work and that evidence report under `macro_micro_data_v8_implementation`; L2 states completion only and does not audit, approve, or write gate metadata.
3. Independent L3 reviews the exact frozen tree, L2 transcript, command artifacts/hashes, any exception, protected-byte comparison, PIT trail, planning-authority values, runtime pins, and quantitative gates.
4. Only independent L3 may write the concrete `macro_micro_data_v8_implementation` record in `.ly_state/session/phase_gates.json`. It must contain actual phase name/timestamp and L2/L3 identities, literal Boolean `l2_completed=true`, a concrete nonempty non-placeholder `l3_session_key`, audit path, bracketed verdict, SOD booleans, repo-local role/skill evidence, and forbidden-path scan evidence.
5. The implementation record never reuses, replaces, amends, or overwrites `macro_micro_data_v8_plan` or its approval history.
6. L1 runs the exact post-L3 invocation in section 19.2. Its runner validates the accepted L2 transcript and gate fields, runs command 5 once, records a distinct post-L3 run ID/transcript hash linked to L2, and requires exit `0`.

Cross-gate evidence, placeholder identities, copied sessions, self-approval, missing timestamps, unapproved exceptions, implementation/test mutation of gate metadata, manual command evidence, or unlinked transcripts invalidates the handoff.

### 19.7 Final Completion Criteria

Future implementation is complete only when:

- Every deferred file, schema, fixture, test, adapter, migration, reader, export, recovery, rollback, runner, and runtime-pin contract exists in the approved minimal file set.
- All WP quantitative gates pass and the exact PIT trail is repeatably byte-stable.
- Both legacy inputs, every prior release, master/detailed plans, approving plan audit, and plan-gate history retain protected bytes.
- The sealed manifest reopens and rehashes the exact approved detailed plan and subsequent independent approving plan audit, with matching `planning_authority` paths, lowercase SHA-256 values, `[APPROVED]` verdict, and implementation gate.
- L2 commands 1-4 and post-L3 command 5 satisfy section 19.5 under unchanged frozen implementation inputs, with create-new hash-linked transcripts produced only by the sole parent runner.
- Any full-suite exception satisfies the exact WP8 contract and independent Role 20 approval.
- Independent L3 writes only the implementation gate, post-L3 command 5 exits `0`, and L2 never self-audits or self-approves.

This Role 26 session remains planning-only. It does not execute the deferred commands, create implementation evidence, modify gate metadata, or issue a verdict.
