# L2 Fix Report: HOSE/HNX Data Rebuild Phase 1+2
## Gate: HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612

**Role:** 15 data-engineer (OpenCode L2)
**Date:** 2026-06-12T19:45:00+07:00
**Status:** [AWAITING_L3_REVIEW]
**Prior Verdict:** [NEEDS_FIX] by role 20 compliance-officer (Codex L3)

---

## Fixes Applied

### Fix 1: Exchange UNKNOWN Resolution

**Problem:** 70.43% of tickers (1,017/1,444) mapped to UNKNOWN exchange in the session exchange map. Exchange drives VN-specific costs, price bands, board-lot/execution assumptions, liquidity tiers, and capacity/slippage classification.

**Solution:** Created `src/omega/data/exchange_resolver.py` providing:
- `resolve_exchange(ticker, exchange_map)` - resolves single ticker, validates against known exchanges
- `assign_exchange_column(df, exchange_map)` - assigns exchange column to DataFrames
- `build_promoted_candidate(df, exchange_map, exclude_unknown=True)` - builds promoted dataset that **excludes UNKNOWN rows by default**
- `write_promoted_manifest(manifest, path)` - writes manifest JSON

**Behavior:** UNKNOWN exchange rows are explicitly excluded from the promoted candidate dataset. The manifest documents included/excluded counts per exchange. No pretense that UNKNOWN is safe.

**Files created:**
- `src/omega/data/exchange_resolver.py` (175 lines)

**Files modified:**
- `src/omega/data/__init__.py` (registered exchange_resolver)

### Fix 2: VND_FULL Price-Unit Contract

**Problem:** Split-brain in price units. `vnstock_adapter.py` and `vnstock_live.py` passed raw VCI THOUSANDS through, while `vnstock_vci.py`, `vnstock_ingest.py`, and `update_market_data.py` scaled to VND. No centralized guard existed.

**Solution:** Created `src/omega/data/vnd_price_contract.py` providing:
- `VND_FULL` constant - canonical price unit (whole VND, e.g. 50000.0)
- `THOUSANDS` constant - legacy VCI 4.x raw unit (e.g. 50.0)
- `ensure_vnd_scale(df)` - single authoritative guard that detects THOUSANDS and converts to VND_FULL
- `detect_price_unit(df)` - heuristic detection via median price
- `get_price_multiplier(price_unit)` - returns 1.0 or 1000.0 for consumers
- `price_scale_metadata()` - metadata dict for manifests

**Wired into all ingestion write boundaries:**
- `src/omega/data/vnstock_adapter.py` - added `_normalize_price_vnd()` using centralized constants
- `src/omega/data/vnstock_live.py` - added `ensure_vnd_scale()` call after fetching prices
- `src/omega/data/vnstock_vci.py` - refactored to import from centralized contract
- `src/omega/data/vnstock_ingest.py` - refactored to delegate to `ensure_vnd_scale()`
- `src/omega/data/live_ingestor.py` - refactored to delegate to `ensure_vnd_scale()`
- `scripts/update_market_data.py` - replaced inline scaling with `ensure_vnd_scale()`

**Files created:**
- `src/omega/data/vnd_price_contract.py` (126 lines)

**Files modified:**
- `src/omega/data/vnstock_adapter.py`
- `src/omega/data/vnstock_live.py`
- `src/omega/data/vnstock_vci.py`
- `src/omega/data/vnstock_ingest.py`
- `src/omega/data/live_ingestor.py`
- `scripts/update_market_data.py`
- `src/omega/data/__init__.py`

### Fix 3: Execution/PnL Hardcoded *1000 Paths

**Problem:** `order_generator.py` divided by `current_price * 1000.0`, `trade_blotter.py` multiplied `quantity * price * 1000.0`, `pnl_monitor.py` defaulted `price_scale=1000.0`. Feeding VND_FULL prices into these paths would under-size orders, overstate notional/PnL.

**Solution:** Parameterized all *1000 paths with `price_unit` parameter. Default is VND_FULL (price_scale=1.0). Backward-compatible via `price_unit="THOUSANDS"`.

**Changes:**
- `src/omega/execution/order_generator.py`:
  - `convert_signal_to_order()`: added `price_unit` param (default VND_FULL), uses `get_price_multiplier()`
  - `validate_compliance()`: added `price_unit` param, computes `price_vnd` via multiplier
  - Fixed ADV check: now rejects orders when `adv <= 0` (no-liquidity protection)

- `src/omega/execution/trade_blotter.py`:
  - `record_trade()`: added `price_unit` param (default VND_FULL), uses `get_price_multiplier()`

- `src/omega/quant/monitoring/pnl_monitor.py`:
  - `__init__()`: default `price_scale=1.0` (was 1000.0), added `price_unit` param
  - If `price_unit != VND_FULL`, uses `get_price_multiplier()` for backward compat

**Files modified:**
- `src/omega/execution/order_generator.py`
- `src/omega/execution/trade_blotter.py`
- `src/omega/quant/monitoring/pnl_monitor.py`

### Fix 4: Tests

**Test file:** `tests/data_test_vnd_full_exchange_fix.py` (39 new tests)

| Test Class | Tests | Coverage |
|---|---:|---|
| TestVndPriceContract | 10 | ensure_vnd_scale, detect_price_unit, get_price_multiplier, metadata |
| TestExchangeResolver | 7 | resolve_exchange, assign_exchange_column, promoted candidate exclude/flag, zero-volume stats |
| TestOrderGeneratorVndFull | 5 | VND_FULL qty, THOUSANDS backward compat, compliance |
| TestTradeBlotterVndFull | 4 | VND_FULL notional, commission, summary stats |
| TestPnLMonitorVndFull | 6 | VND_FULL notional, cash, realized PnL, unrealized snapshot, slippage bps, THOUSANDS compat |
| TestAdvCapacityZeroVolume | 3 | Zero-volume ADV, zero-ADV rejection, exchange-aware ADV |
| TestPipelineVndFullConsistency | 2 | End-to-end ingest-to-order, ingest-to-PnL |

**Updated existing tests to VND_FULL:**
- `tests/execution_test_order_generator.py` (prices 50.0 -> 50000.0)
- `tests/execution_test_trade_blotter.py` (prices 50.0 -> 50000.0, 25.0 -> 25000.0)
- `tests/quant_test_pnl_monitor.py` (prices 80.1 -> 80100.0, 30.0 -> 30000.0, etc.)

**Total: 54 tests, all passing.**

### Fix 5: Quality Checks

**py_compile:** 14 scoped Python files - all PASS.
**pytest:** 54 tests (39 new + 15 existing updated) - all PASS.

---

## Canonical Replacement Status

The rebuilt parquet `data/market_hose_hnx_2015_now_rebuilt_20260612.parquet` remains a **parallel audit artifact only**. `data/market_2015_now.parquet` has **NOT** been modified.

Canonical replacement remains blocked pending L3 re-review because:
1. The exchange map still contains ~1,017 UNKNOWN tickers. The promoted candidate **excludes** these, but the full dataset does not.
2. The VCI Listing API outage that caused the UNKNOWN mapping is external and unresolved.
3. 90 missing tickers vs canonical remain (data completeness gap).

---

## Awaiting L3 Review

This report is submitted for L3 audit by:
- Role 20 compliance-officer (Codex L3)
- Role 21 code-reviewer
- Role 17 qa-engineer

**Do not self-approve. Do not replace canonical data.**
