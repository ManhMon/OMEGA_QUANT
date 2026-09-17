# Vnstock Latest Standardization Report
**Date:** 2026-06-12
**Role:** 15 (Data Engineer, L2 Implementation)
**Gate:** VNSTOCK_LATEST_STANDARDIZATION_20260612

---

## 1. Version Upgrade

| Metric | Value |
|--------|-------|
| **Before** | vnstock 4.0.2 |
| **After** | vnstock 4.0.4 (latest stable on PyPI) |
| **Upgrade method** | `pip install --upgrade vnstock` |
| **Side-effect packages** | numpy 2.2.6, mplfinance 0.12.10b0, vnstock_ezchart 1.0.2 (auto-updated) |

## 2. Import Audit Summary

### Broken imports found and fixed

| File | Old Import | New Import | Issue |
|------|-----------|------------|-------|
| `src/omega/data/market_flow.py` | `from vnstock_data import Trading` | `from vnstock import Trading` | `vnstock_data` package not installed; vnstock 4.x exposes `Trading` at top level |
| `src/omega/quant/data/vn_market.py` | `from vnstock_data import Trading` | `from vnstock import Trading` | Same as above |
| `src/omega/quant/portfolio/sector_classifier.py` | `from vnstock_data import Listing` | `from vnstock import Listing` | Same as above |
| `src/omega/quant/utils/structure_features.py` | `from vnstock3 import Vnstock` | `from vnstock import Vnstock` | `vnstock3` package not installed; vnstock 4.x unified package |

### Stale docstring/comment references cleaned

| File | Change |
|------|--------|
| `src/omega/quant/data/vci_ingest.py` | Updated 4 comments referencing `vnstock3` to `vnstock` |
| `scripts/update_market_data.py` | Updated 2 comments referencing `vnstock3` to `vnstock` |

### Already-correct imports (no change needed)

All files already using `from vnstock import Quote`, `from vnstock import Listing`, `from vnstock import Market`, `from vnstock import Vnstock`, `from vnstock.core.types import TimeFrame` are correct with vnstock 4.0.4. These span:
- `src/omega/data/vnstock_adapter.py`
- `src/omega/data/vnstock_vci.py`
- `src/omega/data/vnstock_live.py`
- `src/omega/data/vnstock_ingest.py`
- `src/omega/data/loader.py`
- `src/omega/data/live_ingestor.py`
- `src/omega/quant/data/vnstock.py`
- `src/omega/quant/data/vnstock_vci.py`
- `src/omega/quant/data/vci_ingest.py`
- `src/omega/quant/execution/live_ingestor.py`
- `scripts/batch_market_loader_resume.py`
- `scripts/fetch_intraday_data.py`
- `scripts/rebuild_hose_hnx_20260612.py`
- `scripts/update_recent_portfolio_data.py`
- `scripts/test_vnstock_integration.py`
- `scripts/update_market_data.py`

## 3. New Unified Adapter: `src/omega/data/vnstock_client.py`

Created a unified facade wrapping vnstock 4.x classes with:
- **Quote**: `fetch_history()`, `fetch_intraday()` with VND_FULL guard
- **Listing**: `list_symbols()`, `all_symbols()`, `industries_icb()`, `symbols_by_industries()` with VCI primary + KBS fallback
- **Trading**: `fetch_foreign_trade()`, `fetch_prop_trade()`
- **Market**: `fetch_equity_ohlcv()` with VND_FULL guard
- **Company**: `fetch_company_profile()` via Vnstock().stock().company.profile()
- **Diagnostics**: `probe()` static method
- **Rate limiting**: Built-in sliding-window `RateLimiter` (60 req/min)
- **Singleton**: `get_client()` module-level convenience

Registered in `src/omega/data/__init__.py` as first-loaded submodule.

## 4. Listing Exchange Resolution: VCI Primary + KBS Fallback

Added VCI→KBS fallback to:
- `vnstock_client.py` (new adapter): `_LISTING_SOURCES = ("VCI", "KBS")`
- `vnstock_adapter.py` `list_symbols()`: now tries VCI then KBS
- `vnstock.py` (omega.quant.data) `list_symbols()`: now tries VCI then KBS

## 5. VND_FULL Guard

All price-returning methods in `vnstock_client.py` apply `ensure_vnd_scale()` by default (`normalize_vnd=True`), preserving the VND_FULL contract at every read boundary.

## 6. Files Touched

| File | Action |
|------|--------|
| `src/omega/data/vnstock_client.py` | **NEW** — unified adapter |
| `src/omega/data/__init__.py` | Added `vnstock_client` import |
| `src/omega/data/vnstock_adapter.py` | Added KBS fallback to `list_symbols()` |
| `src/omega/data/market_flow.py` | Fixed `vnstock_data` → `vnstock` import |
| `src/omega/quant/data/vn_market.py` | Fixed `vnstock_data` → `vnstock` import |
| `src/omega/quant/data/vci_ingest.py` | Cleaned stale `vnstock3` comments |
| `src/omega/quant/data/vnstock.py` | Added KBS fallback to `list_symbols()` |
| `src/omega/quant/portfolio/sector_classifier.py` | Fixed `vnstock_data` → `vnstock` import; added rationale comment |
| `src/omega/quant/utils/structure_features.py` | Fixed `vnstock3` → `vnstock` import |
| `scripts/update_market_data.py` | Cleaned stale `vnstock3` comments |

## 7. Canonical Data

**NOT MODIFIED:** `data/market_2015_now.parquet` — read/validate only if needed, no writes.

## 8. Verification Results

- **py_compile**: All 9 touched `.py` files compile cleanly
- **Smoke imports**: All pass (vnstock_client, market_flow, get_client, probe)
- **pytest** (data/provider): 74 passed, 0 failed
- **pytest** (deployment/execution): 57 passed, 0 failed
- **Total**: 131 relevant tests passed

## 9. Known Pre-existing Test Failures (Not Related)

- `tests/data_test_sanitizer.py` — pre-existing `ImportError: DataSanitizer` not in `omega.data`
- `tests/data_test_calendar.py` — pre-existing JSON file missing errors

---

**Status: AWAITING L3 AUDIT**
- Code Reviewer (role 21): Pipeline code quality review
- QA Engineer (role 17): Data quality validation
- Performance Tester (role 23): Pipeline performance review
