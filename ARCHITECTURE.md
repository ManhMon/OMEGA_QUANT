# OMEGA_QUANT Architecture

## Purpose

OMEGA_QUANT is a Python quantitative-research platform for Vietnamese equities on HOSE, HNX, and UPCOM. The architecture separates external market-data ingestion, canonical validation, research/backtesting, execution controls, and durable artifacts. Point-in-time (PIT) correctness is a system invariant, not an optional pipeline feature.

## System Boundary

```text
VCI HTTPS API
    |
    v
DirectVCIClient  -- allowlist, HTTPS, bounded payload, retry/rate limits
    |
    v
Canonical OHLCV + provenance + PIT timestamps
    |
    v
DataSanitizer   -- fit(train) / apply(test), causal cleaning, PIT guard
    |
    +--> parquet/data artifacts --> research, signals, portfolio, backtests
    |
    +--> validation reports      --> observability and audit evidence
```

The `src/omega` package is the active implementation. `archive/` is historical evidence only and is not an ingestion or validation dependency.

## Data Ingestion SSOT

`src/omega/data/vci_direct.py` owns direct VCI access through `DirectVCIClient`. Active loaders and market-data consumers must use this client or a wrapper that delegates to it; they must not import retired `vnstock` adapters for network access.

### DirectVCIClient contract

- HTTPS endpoints only; host and path are allowlisted; credentials, fragments, query injection, and traversal are rejected.
- Ticker, date range, timeout, attempts, and payload size are validated before I/O.
- Response bytes are read with a hard cap. Invalid UTF-8, malformed JSON, non-2xx status, timeout, and exhausted 429 retries fail closed.
- Retry behavior is bounded. Secrets and userinfo are redacted in errors.
- VCI columnar payloads become the canonical OHLCV schema, with VND scale normalization and source provenance.
- Returned rows are filtered by `as_of`, `available_at`, trading calendar, and the 15:30 ICT session boundary. No future row may enter a historical view.

## Validation SSOT

`src/omega/data/sanitizer.py` owns `DataSanitizer`, `DataValidator`, `ValidationIssue`, and `DataQualityChecker`. `fit()` learns statistics from training data only; `apply()` uses those parameters on later data. The sanitizer removes duplicate `(date, symbol)` rows, performs causal forward-fill within its bound, clips fitted outliers, removes invalid prices, and enforces `as_of <= available_at`.

Compatibility modules `src/omega/data/validator.py`, `data_validator.py`, and `data_quality.py` re-export the exact canonical objects. They contain no independent validation logic. `src/omega/quant/data/sanitizer.py` and `src/omega/quant/utils/sanitization.py` are legacy/transition surfaces and must not become new SSOT implementations.

## Canonical Data Contract

Canonical market data carries `date`, `symbol`, `open`, `high`, `low`, `close`, `volume`, and `exchange`, plus PIT metadata `as_of` and `available_at`. Prices use `VND_FULL` (whole VND); VCI THOUSANDS values are normalized once at ingestion. Schema drift, duplicate keys, invalid OHLC relationships, negative volume, non-trading dates, and future availability fail closed.

Universe construction is point-in-time. Historical records for suspended or delisted symbols remain available with lifecycle status and terminal handling. Current listings must never define historical membership.

## Persistence and Interfaces

Parquet/data artifacts are versioned outputs, not mutable in-memory truth. Writers validate schema and PIT invariants before publication, use temporary-file replacement for atomicity, and preserve provenance. Research modules consume canonical frames; they do not reach into VCI transport details. Scripts are adapters at the boundary, not alternate domain implementations.

## Legacy Inventory

Archived network adapters:

- `archive/legacy_adapters/vnstock_vci.py`
- `archive/legacy_adapters/vnstock_live.py`
- `archive/legacy_adapters/vci_bridge.py`
- `archive/legacy_adapters/vnstock_adapter.py`
- `archive/legacy_adapters/vnstock_ingest.py`

Archived validators:

- `archive/legacy_validators/validator.py`
- `archive/legacy_validators/data_validator.py`
- `archive/legacy_validators/data_quality.py`

Other historical areas include `archive/2026-06-06_monolith_migration/`, `archive/2026-06-04/`, `archive/legacy_scripts/`, `archive/backtests/`, `archive/pipeline/`, `archive/portfolio/`, `archive/risk/`, and `archive/tests/`. Archived modules may fail closed on import or invocation by design. They are not supported call sites.

## Architectural Decisions

1. Direct VCI transport is the ingestion SSOT: fewer hidden wrappers, explicit security and PIT controls.
2. `DataSanitizer` is the validation SSOT: one lifecycle and one canonical object identity for all compatibility imports.
3. Archive rather than delete: historical adapters remain inspectable, but fail closed to prevent accidental network or logic reactivation.
4. Validate at boundaries: external payloads, persisted artifacts, and research inputs each receive explicit schema and temporal checks.

## Operational Rules

- New data integrations require a documented source, schema, availability timestamp, rate limit, and failure mode.
- No backtest may use data before `available_at`.
- No production path may add a second sanitizer or bypass `ensure_vnd_scale()`.
- Changes require scoped tests plus independent Tier 3 audit; L2 authors do not self-approve.
