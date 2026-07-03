# Legacy Data Loader Inventory

**Gate:** CANONICAL_VCI_UPDATER_LEGACY_TRACKING_20260613  
**Role:** Data Engineer (Role 15, L2)  
**Date:** 2026-06-13  
**Canonical Replacement:** `scripts/update_market_data.py`

---

## Summary

| File | Status | Replacement |
|------|--------|-------------|
| `scripts/batch_market_loader_resume.py` | legacy | `scripts/update_market_data.py` |
| `src/omega/quant/data/vnstock_vci.py` | legacy | `src/omega/data/vnstock_client.py` |
| `src/omega/quant/data/vci_ingest.py` | legacy | `scripts/update_market_data.py` |
| `scripts/vci_candidate_download_20260612.py` | superseded | `vci_full_hsx_hnx_download_20260613.py` + updater |
| `scripts/vci_candidate_validate_20260612.py` | superseded | `vci_full_hsx_hnx_validate_20260613.py` + updater |
| `scripts/update_market_data.py` (old behavior) | replaced | `scripts/update_market_data.py` (new) |

---

## Detailed Inventory

### 1. `scripts/batch_market_loader_resume.py` - LEGACY

**Status:** Legacy  
**Reason:** Parallel batch loader using `VnstockVCIDataSource` (omega.quant.data.vnstock_vci) with thread pool and checkpoint resume. Superseded by canonical updater which uses the unified `VnstockClient` adapter (omega.data.vnstock_client) with proper VND_FULL normalization, canonical schema, and atomic write.

**Issues:**
- Imports from `omega.quant.data.vnstock_vci` (legacy VCI adapter)
- Does not enforce canonical 14-column schema
- No PIT `available_at` enforcement
- No exchange whitelist validation
- No pre-write validation (duplicates, nulls, OHLC invariants)
- No atomic write with backup

### 2. `src/omega/quant/data/vnstock_vci.py` - LEGACY

**Status:** Legacy  
**Reason:** V21-era VCI data source using raw vnstock Quote API. Superseded by `omega.data.vnstock_client.VnstockClient` which provides unified adapter with rate limiting, VND_FULL normalization, and source fallback.

**Issues:**
- Direct vnstock imports (Quote, TimeFrame) instead of unified adapter
- No VND_FULL price normalization at read boundary
- Used by `batch_market_loader_resume.py` (also legacy)
- Domain: `omega.quant.data` instead of `omega.data`

### 3. `src/omega/quant/data/vci_ingest.py` - LEGACY

**Status:** Legacy  
**Reason:** V21-era one-shot VCI ingestion script. Hardcoded price normalization, no canonical schema, no PIT columns. Superseded by the canonical updater pipeline.

**Issues:**
- No canonical 14-column schema
- Inline price normalization (not centralized)
- No PIT `available_at`
- No validation framework
- No incremental update support

### 4. `scripts/vci_candidate_download_20260612.py` - SUPERSEDED

**Status:** Superseded  
**Reason:** VCI candidate download for cross-source validation on 2026-06-12. Derived universe from canonical tickers (not VCI Listing). Superseded by `vci_full_hsx_hnx_download_20260613.py` (full HSX/HNX from VCI Listing) and the canonical updater.

**Issues:**
- Universe derived from canonical (not VCI Listing API)
- No hard 2015-01-01 lower bound enforcement
- One-shot output, not canonical
- Purpose: one-time cross-source validation, now complete

### 5. `scripts/vci_candidate_validate_20260612.py` - SUPERSEDED

**Status:** Superseded  
**Reason:** Validation script for the 2026-06-12 candidate dataset. One-time validation purpose fulfilled. Superseded by `vci_full_hsx_hnx_validate_20260613.py` and canonical quality checks in the updater.

**Issues:**
- Hardcoded canonical row count assertion (1687749)
- One-time validation purpose, now complete
- No reusable validation framework

### 6. `scripts/update_market_data.py` (OLD BEHAVIOR) - REPLACED

**Status:** Replaced (in-place rewrite)  
**Reason:** Old version was VN30-only with hardcoded TOP_SYMBOLS list (20 tickers), no canonical schema enforcement, no dry-run, no validation framework, no atomic write. Completely rewritten as canonical VCI updater supporting full HSX/HNX universe (703 tickers).

**Old Issues:**
- VN30-only: hardcoded TOP_SYMBOLS list (20 tickers out of 703)
- Direct vnstock import instead of unified VnstockClient adapter
- No canonical 14-column schema enforcement
- No dry-run/no-write validation mode
- No pre-write validation
- No atomic write with backup
- No PIT available_at enforcement
- No hard 2015-01-01 lower bound
- No incremental backfill support

---

## Action: DO NOT DELETE

Per task scope: "Do NOT delete legacy files in this task. Track only."
Deletion decisions deferred to L3 Tier 3 review (Code Reviewer role 21).
