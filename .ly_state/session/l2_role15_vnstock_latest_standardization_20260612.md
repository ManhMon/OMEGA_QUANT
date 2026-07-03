# L2 Implementation Report — Role 15 Data Engineer
**Task:** VNSTOCK_LATEST_STANDARDIZATION_20260612
**Date:** 2026-06-12
**Agent:** data-engineer (Tier 2, OpenCode L2)

---

## Executive Summary

Standardized all vnstock-related imports and call sites to the latest stable vnstock 4.0.4 package. Created a unified internal adapter (`src/omega/data/vnstock_client.py`) that wraps Quote, Listing, Trading, and Market with source normalization, VND_FULL guard, and VCI+KBS fallback. Fixed 4 broken imports (`vnstock_data` and `vnstock3` packages that were never installed). Cleaned 6 stale docstring references. All 131 relevant tests pass.

## Work Completed

### 1. Package Upgrade
- vnstock 4.0.2 → 4.0.4 (latest stable on PyPI)
- No breaking API changes between versions

### 2. Import Audit (Full Repo Scan)
- Searched `src/`, `scripts/`, `tests/` for `vnstock`, `vnstock_data`, `vnstock3`
- Found 35 import/call sites across 16+ files in `src/`
- Found 8 import/call sites across 6 scripts
- 0 import sites in `tests/`
- 4 broken imports identified (using non-installed packages)

### 3. Unified Adapter Created
**File:** `src/omega/data/vnstock_client.py` (new, ~280 lines)
- Classes: `VnstockClient`, `RateLimiter`
- Functions: `get_client()`, `VnstockClient.probe()`
- Re-exports: `Quote`, `Listing`, `Trading`, `Market`, `TimeFrame`
- VND_FULL guard on all price-returning methods
- VCI primary + KBS fallback for all Listing methods
- Registered in `src/omega/data/__init__.py`

### 4. Broken Import Fixes
| File | Before | After |
|------|--------|-------|
| `src/omega/data/market_flow.py` | `from vnstock_data import Trading` | `from vnstock import Trading` |
| `src/omega/quant/data/vn_market.py` | `from vnstock_data import Trading` | `from vnstock import Trading` |
| `src/omega/quant/portfolio/sector_classifier.py` | `from vnstock_data import Listing` | `from vnstock import Listing` |
| `src/omega/quant/utils/structure_features.py` | `from vnstock3 import Vnstock` | `from vnstock import Vnstock` |

### 5. Listing Exchange Resolution
Added VCI→KBS fallback to:
- `vnstock_client.py` (new adapter, all Listing methods)
- `vnstock_adapter.py` `VnstockVCIDataSource.list_symbols()`
- `vnstock.py` (omega.quant.data) `VnstockVCIDataSource.list_symbols()`

### 6. Stale Reference Cleanup
- `vci_ingest.py`: 4 docstring references `vnstock3` → `vnstock`
- `update_market_data.py`: 2 references `vnstock3` → `vnstock`
- `sector_classifier.py`: Added rationale comment for retained direct import

### 7. Verification
- **py_compile**: 9/9 touched files PASS
- **Smoke imports**: 12/12 PASS
- **pytest data/provider**: 74 passed, 0 failed
- **pytest deployment/execution**: 57 passed, 0 failed
- **Total**: 131 passed, 0 failed

## Design Decisions

1. **Why a new adapter file instead of modifying existing `vnstock_adapter.py`?**
   - The existing `vnstock_adapter.py` is a VCI-specific data source class. The new `vnstock_client.py` is a higher-level facade that unifies ALL vnstock 4.x APIs (Quote, Listing, Trading, Market) and can be used by any consumer without coupling to VCI-specific internals.

2. **Why keep direct `vnstock` imports in existing provider modules?**
   - Modules like `vnstock_vci.py`, `vnstock_live.py`, `vnstock_adapter.py` are low-level provider modules that already have documented rationale for their direct imports. They serve as the implementation layer; the new adapter delegates to the same vnstock classes.

3. **VCI+KBS fallback strategy:**
   - VCI is the richest source (full HOSE/HNX/UPCOM coverage, ICB classification, foreign/prop flow).
   - KBS serves as a lightweight fallback for basic symbol listing when VCI is unavailable.
   - Fallback is implemented as a simple for-loop over source priority.

## Constraints Respected
- No Antigravity scratch paths used
- No secrets/API keys in code (existing env-var based key handling preserved)
- `data/market_2015_now.parquet` NOT modified
- Repo-relative paths only
- No self-approval; state set to AWAITING L3

## Awaiting L3 Audit
- Code Reviewer (role 21): Pipeline code quality review
- QA Engineer (role 17): Data quality validation
- Performance Tester (role 23): Pipeline performance review
