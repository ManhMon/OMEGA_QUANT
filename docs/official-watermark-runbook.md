# Official HSX/HNX Watermark Runbook

## Scope

`omega.data.official_watermark` privately acquires one official response, validates it, and writes the artifact contract. It does not publish or enable scheduling.

## Contract

- Markets: exact `HSX` or `HNX`.
- Source: private fixed production URLs only; no public source-URL authority exists. URLs require HTTPS, no query or fragment, and exact final-URL equality. Caller URL or allowlist overrides are unavailable. HNX remains quarantined until an equivalent structured official endpoint is validated.
- Private capture: `_acquire_official_source` accepts only HTTP 200, exact final URL, `application/json`, and structured JSON fields containing the exact requested session date and exchange. HTML, text markers, redirects, off-domain responses, errors, wrong content types, invalid JSON/encoding fail closed. TLS verification uses certifi or the platform CA store; verification is never disabled.
- VCI: `materialize_watermark` accepts only config, exact market, and expected date. It reads the internally configured `VCI_API_TOKEN`, acquires privately, parses raw JSON internally, and validates every row from that raw payload. No public fetcher, client, evidence, or rows injection exists.
- Candidate: market match plus exact expected maximum date. No fallback date.
- Artifacts: raw bytes, canonical compact sorted UTF-8 JSON, receipt JSON.
- Provenance: market, source/effective URL, HTTP status, MIME, response SHA-256, validator version, retrieval timestamp, expected/candidate date, raw SHA-256, canonical SHA-256, `completed` status.
- Writes: repository-relative artifact root, no traversal/symlink, exclusive create, no overwrite.
- Tamper: `verify_artifact` rejects SHA mismatch.

## Statuses

`completed`, `vci_client_missing`, `vci_fetch_failed`, `market_invalid`, `url_not_allowed`, `candidate_exact_max_date_missing`, `artifact_exists`, `path_invalid`, `artifact_tampered`.

## Operations

1. Configure `OfficialWatermarkConfig` with `artifact_root` only. Set `VCI_API_TOKEN` through the runtime secret provider; never commit, log, or place it in receipts.
2. Call `materialize_watermark(config, market, expected_date)`. Acquisition, parsing, raw binding, and validation remain private. Never synthesize rows from missing or nonmatching content.
3. Verify receipt provenance and `verify_artifact` hashes before any downstream use.
4. Treat every non-`completed` status as quarantine. Do not overwrite or publish.

Scheduler integration remains disabled/quarantined by design.
