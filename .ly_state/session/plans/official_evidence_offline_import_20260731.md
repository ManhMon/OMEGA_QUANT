# Offline-Attested HSX/HNX Evidence Import — Hardened Contract

## Scope

Target candidate: **Friday `2026-07-31`**, only if a curator-provided, signed official completed-session artifact proves it.

No VCI/OHLCV access. No `urlopen`, HTTP client, `update_market_data.py`, canonical/pointer/release mutation, or market publication.

## User Review Required

> [!IMPORTANT]
> The importer verifies **OMEGA curator attestation**, not an exchange cryptographic signature. A curator verifies an official HOSE/HNX notice externally, builds/signs a bundle using a dedicated key, then hands it to the offline importer. Without that signed input, outcome is `BLOCKED`.

> [!CAUTION]
> This is evidence infrastructure. It does not authorize data acquisition or release, even after every test passes.

## Fixed Architecture

### Network isolation

#### [NEW] `src/omega/data/offline_evidence.py`

Pure offline verifier/importer. Allowed imports: stdlib parsing, hashing, HMAC, filesystem, dataclasses/typing. It must not import `official_watermark.py`, `urllib`, `requests`, `socket`, `subprocess`, or data updater modules. No CLI option can enable network.

#### [NEW] `scripts/import_official_evidence.py`

CLI imports only `offline_evidence`. Requires `--input-dir`, `--evidence-root`, `--expected-session`. All input paths must be local regular files; absent/invalid input blocks. No network dependencies or fallback.

#### [UNCHANGED] [official_watermark.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/official_watermark.py)

Keep v3 API/constants/serialization/behaviour byte-compatible. Do not import the new verifier there.

### Isolated evidence storage

Only this root is mutable:

```text
.ly_state/session/official_evidence/v4/
  bundles/<bundle_id>/manifest.json
  bundles/<bundle_id>/raw.bin
  bundles/<bundle_id>/canonical.json
  replay-ledger.json
```

No date filenames as trust identity. Every component is validated with `lstat` on every path segment; reject symlink, Windows reparse point/junction, absolute path, `..`, non-regular input, or root escape. Protected paths are explicitly enumerated and asserted unchanged:

- `data/market_2015_now.parquet`
- `data/market_current.json`
- `data/market_releases/`
- `.ly_state/session/update_market_data_result.json`
- `.ly_state/session/official_watermarks/`
- `.ly_state/session/phase_gates.json`

### Canonical v4 manifest

Schema is exchange-specific: one manifest per `HSX` or `HNX`. Corporate actions are in their respective exchange bundle, never a mixed issuer bundle.

```json
{
  "schema_version": 4,
  "bundle_id": "sha256(unsigned_identity_payload)",
  "market": "HSX|HNX",
  "expected_session_date": "YYYY-MM-DD",
  "issuer_claim": "HOSE|HNX",
  "source_url": "https://...",
  "effective_url": "https://...",
  "content_type": "application/json|text/html|application/pdf",
  "source_format": "hsx-json-v1|hnx-html-v1|hnx-pdf-v1",
  "raw_sha256": "...",
  "canonical_sha256": "...",
  "retrieved_at": "aware ISO-8601 UTC",
  "curated_at": "aware ISO-8601 UTC",
  "calendar_closures": [],
  "calendar_hash": "...",
  "corporate_actions": [],
  "integrity": {"algorithm":"HMAC-SHA256","key_id":"...","signature":"..."}
}
```

`unsigned_identity_payload` is the canonical manifest with `bundle_id` and `integrity.signature` removed. Its SHA-256 must equal `bundle_id`. HMAC input is the full manifest with only `integrity.signature` removed. All JSON parsing rejects duplicate keys before validation/canonicalization.

### Curator trust contract

Dedicated environment names only:

- `OMEGA_OFFICIAL_EVIDENCE_HMAC_ACTIVE_KEY_ID`
- `OMEGA_OFFICIAL_EVIDENCE_HMAC_KEYRING_JSON`
- `OMEGA_OFFICIAL_EVIDENCE_HMAC_REVOKED_KEY_IDS`

Rules:

- Curator signing workflow is outside importer; signer and importer have separate commands/access.
- Key IDs unique, regex bounded, explicit active key; key material base64-decoded is **exactly 32 bytes**. Shorter or longer material rejects.
- Reject unknown, revoked, duplicate, weak, malformed, inactive-for-new-signing keys.
- Verification allows known non-revoked rotated keys; signing uses active key only.
- `hmac.compare_digest` mandatory.
- No keys/secrets in code, artifact, report, test logs, Git.

### Strict adapters

- `hsx-json-v1`: UTF-8 JSON only, bounded bytes/depth/entries, duplicate-key reject.
- `hnx-html-v1`: UTF-8 HTML only, bounded bytes/tokens, deterministic parser extracting an exact exchange/date statement.
- `hnx-pdf-v1`: `%PDF-` magic required; bounded bytes/pages/object count; deterministic text extraction; exact exchange/date statement required.
- Claim/content mismatch, compressed input, malformed encoding/PDF/HTML, unsupported content type, URL userinfo/non-443 port/IDN mismatch, redirect mismatch, unallowlisted domain: reject.

### Replay registry

`replay-ledger.json` has canonical JSON object `{schema_version, entries}` keyed by `bundle_id`; entry binds `bundle_id`, market, expected session, `canonical_sha256`, `raw_sha256`, and importer timestamp.

- Atomic reservation uses exclusive creation of a sibling lock plus fsync/atomic replace of ledger; crashes leave a recoverable lock whose content is validated before cleanup.
- Same `bundle_id` + identical hashes: idempotent `already_imported`; no artifact mutation.
- Same `(market, expected_session_date)` with a different bundle/hashes: `conflict`, block.
- Different payload claiming existing `bundle_id`: tamper, block.
- Concurrent reservation: one succeeds; other returns deterministic `already_imported`/`conflict` only after re-read.
- Bundle directory writes are temporary sibling directory then atomic rename; failure cleans temporary only, preserves prior valid state.

### Corporate-action contract

Each active record is issuer-bound to its manifest and contains:

```json
{
  "action_id":"sha256(exchange|notice_id|revision|ticker|type|ex_date|typed_terms)",
  "notice_id":"...", "notice_revision":1,
  "status":"active|amended|cancelled|rejected",
  "supersedes_action_id":null,
  "ticker":"...", "action_type":"split|bonus|cash_dividend|rights_issue|merger",
  "ex_date":"YYYY-MM-DD", "terms":{},
  "authority_url":"https://...", "document_sha256":"...",
  "announced_at":"UTC aware ISO-8601", "ingested_at":"UTC aware ISO-8601",
  "available_at":"UTC aware ISO-8601", "reconciliation_status":"..."
}
```

`available_at == max(announced_at, ingested_at)` exactly after UTC normalization. No future/naive timestamp. Amendment requires an existing record in the same manifest lineage. Cancellation makes superseded action unavailable. Duplicate active identity rejects.

### Reconciliation math

Inputs: **unadjusted VND_FULL** close/volume for `pre_session` and `ex_date`; no adjusted series accepted.

Each action creates affine price transform `P' = aP - b` and volume multiplier `v`:

| Type | `a` | `b` | `v` |
|---|---:|---:|---:|
| split `new/old=n` | `1/n` | `0` | `n` |
| bonus `old:m,new:n` | `m/(m+n)` | `0` | `(m+n)/m` |
| cash dividend `d` | `1` | `d` | `1` |

Rights issue/merger are `not_applicable`, always release-blocking until a separately approved model exists.

For same ticker/ex-date: compose in notice revision order, then action type order `split`, `bonus`, `cash_dividend`, then `action_id`; `(a,b,v)` composition is `a_total *= a`, `b_total = a * b_total + b`, `v_total *= v`. Compare `close_ex` to `a_total * close_pre - b_total` with relative price tolerance `0.001` and absolute VND_FULL tolerance `1`; compare volume ratio to `v_total` with relative tolerance `0.01`. Round only final expected price to VND full Dong and final volume to whole share. Any incomplete/mismatch/suspect/not-applicable action blocks downstream release.

### Transaction journal

Every import has a unique `tx_id` and `.tx/<tx_id>.json` journal inside the evidence root. The journal is **mutable only through atomic replacement**: each state replacement writes complete canonical JSON to a sibling temp file, fsyncs it, atomically replaces journal, then fsyncs its parent directory. Journal fields: `tx_id`, `bundle_id`, hashes, market, session, owner PID/start time, state, all temp/final paths, and the **complete intended ledger entry including one fixed `imported_at` timestamp created at `reserved`**. Recovery reuses this entry byte-for-byte; it never creates a new timestamp. State transitions are monotonic:

```text
reserved → staged → bundle_committed → ledger_committed → finalized
```

1. **reserved**: exclusive lock `locks/<bundle_id>.lock` created with bounded canonical `{tx_id,bundle_id,hashes,owner_pid,owner_process_started_at,owner_started_at}`; `owner_pid` is a positive bounded integer and `owner_process_started_at` is an aware ISO-8601 instant captured from the OS process identity. File fsync + parent directory fsync; atomically journal `reserved`.
2. **staged**: raw/canonical/manifest written to a unique sibling temporary directory, each file fsynced; manifest/hash revalidated; temp directory fsynced; atomically journal `staged`.
3. **bundle_committed**: atomic rename temp directory to `bundles/<bundle_id>`; parent directory fsynced; atomically journal `bundle_committed`.
4. **ledger_committed**: atomically replace a fully fsynced temporary ledger containing the new entry; ledger directory fsynced; atomically journal `ledger_committed`.
5. **finalized**: cross-validate bundle+ledger, atomically journal `finalized`, then **delete lock and fsync lock directory; only then delete journal and fsync `.tx` directory**. This ordering leaves a recoverable journal if cleanup crashes.

No success is returned before `ledger_committed`; `finalized` cleanup failure returns a recoverable status, not a failed import.

### Startup recovery

Before every import, run recovery under the same root lock. Recoverer reads journal state **and independently verifies** whether final bundle and exact ledger entry exist; it never trusts state alone:

| Journal state | Valid final bundle | Exact valid ledger entry | Recovery |
|---|---:|---:|---|
| `reserved`/`staged` | no | no | Delete validated temp only; remove journal/lock. |
| `reserved`/`staged` | yes | no | Rename occurred before journal update: atomically advance `bundle_committed`, commit ledger, finalize. |
| `reserved`/`staged` | yes | yes | Rename and ledger replace occurred before journal updates: atomically advance `ledger_committed`, finalize. |
| `bundle_committed` | yes | no | Commit exact journal-derived ledger, atomically advance `ledger_committed`, finalize. |
| `bundle_committed` | yes | yes | Ledger replace preceded journal update: atomically advance `ledger_committed`, finalize. |
| `ledger_committed` | yes | yes | Finalize only. |
| `finalized` | yes | yes | Delete lock, fsync lock directory; delete journal, fsync `.tx` directory. |

If a valid journal is absent but a lock remains, recovery may remove that lock only after independently finding a matching valid bundle+ledger pair and proving no live owner; otherwise it quarantines and blocks.

**Pre-journal lock-only exception:** a stale/dead lock may be safely deleted only when all of the following are true: its bounded canonical lock payload parses and has valid `bundle_id`, positive `owner_pid`, and aware `owner_process_started_at`; the OS confirms no live process with the exact `(owner_pid, owner_process_started_at)` identity; no journal for that `tx_id`; no `bundles/<bundle_id>` directory; no ledger entry for `bundle_id`; and no transaction temporary directory/artifact matching its `tx_id` or `bundle_id`. Recovery checks the lease plus PID/start-identity rules first, deletes only the lock, and fsyncs the lock directory. Any partial artifact, malformed identity, reused PID, or ambiguous process lookup remains quarantine/block.

Any other combination—ledger without verified bundle, tampered hashes, bundle with no valid journal, unknown state, duplicate transaction ownership, stale lock with unverifiable journal, or inconsistent final paths—is quarantined under `.quarantine/<tx_id>` and blocks all imports. Never silently repair.

Lock is stale only when owner PID is not running **and** age exceeds a fixed 15-minute lease. Live/PID-ambiguous lock blocks. A concurrent caller re-reads ledger after lock release, returning idempotent/conflict deterministically.

All journal/ledger/bundle writes reject reparse/symlink paths. Windows directory fsync limitation is surfaced in journal metadata; file flush plus atomic replace is required, and unsupported durability blocks the transaction rather than claiming durable commit.

### HMAC clarification

Each decoded dedicated curator HMAC secret is **exactly 32 bytes**. Shorter or longer material rejects. Signing uses active non-revoked key; verification permits any known non-revoked 32-byte rotated key.

## SoD execution and gate semantics

- Gate: `official_evidence_offline_import_20260731`.
- Before dispatch: L1 writes SHA-256 of approved plan in `.ly_state/session/plans/official_evidence_offline_import_20260731.plan.sha256` and copies plan beside it. L2 verifies both.
- L2: Role 15 `data-engineer`; report `.ly_state/session/l2_role15_official_evidence_offline_import_20260802.md`.
- **Sole L3 approval authority**: Role 21 `code-reviewer`. It is the only auditor that updates the standard single-L3 gate record, preserving the existing enforcer schema.
- Role 17 `qa-engineer`, Role 20 `compliance-officer`, Role 23 `performance-tester` write read-only **advisory** reports only. Their report filenames/paths are enumerated in Role 21's checklist. Any advisory `[NEEDS_FIX]` blocks Role 21 approval. Advisory `[APPROVED]` does not edit gates.
- Role 21's report must list all advisory reports, their SHA-256, role IDs, and verdicts; require all three `[APPROVED]`. It alone writes the canonical `final_verdict`, its own session/role fields, and its report path in `phase_gates.json`.
- L1 runs final deep advisory audit then enforcer. No enforcer contract change required.

Reports list repo-local sources; forbidden paths only as non-authoritative scan evidence.

## Tests

- Preserve public v3 import/API snapshot and full existing v3 tests unchanged.
- Correct Friday candidate, weekend/holiday rejection.
- No network import/call test.
- All adapter malformed/size/depth/URL/encoding cases.
- Signature tamper, duplicate JSON key, key rotation/revocation/unknown/non-exact-32-byte key.
- Exact replay, conflict replay, concurrent import, journal state recovery at every boundary, missing/tampered orphan quarantine, stale/live/ambiguous lock behavior.
- Symlink/junction/reparse/path escape, partial transaction cleanup.
- Action PIT, duplicate/amend/cancel, boundary/tolerance/composition tests.
- Protected canonical/pointer/release/projection hashes byte-identical before/after success and failure.

## Verification

Targeted new suite + all existing v3 watermark/receipt tests. Then advisory L3 reviews, Role 21 gate audit, final deep advisory audit, final SoD enforcer. No live market-data updater in this gate.
