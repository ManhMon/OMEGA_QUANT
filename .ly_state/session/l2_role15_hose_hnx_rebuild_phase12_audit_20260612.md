# L2 Role 15 — HOSE/HNX Data Rebuild Phase 1+2 Audit Report

**Role:** 15 Data Engineer (OpenCode L2)
**Task ID:** HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
**Date:** 2026-06-12
**Status:** ⏳ AWAITING L3 REVIEW (No self-approval per Tier 2 constraints)

---

## Executive Summary

Completed full code audit of 53 scoped files across Phase 1+2 data ingestion, storage, validation, and all downstream consumers affected by price scale. Successfully rebuilt HOSE/HNX market data from VCI source to a **parallel file only** (canonical NOT overwritten). Identified critical price scale inconsistencies across ingestion paths and execution modules.

---

## 1. Scope

### 1.1 Files Audited: 53 total
- **8 data ingestion modules** (src/omega/data/*)
- **4 data loader scripts** (scripts/*)
- **12 backtest/execution modules** (src/omega/backtest/*, src/omega/execution/*)
- **19 feature/signal/label modules** (src/features/*, src/evolution/*, src/omega/quant/*)
- **10 docs/config/specs** (docs/*, config/*, SOUL.md)

### 1.2 Price Scale Decision Matrix
- **16 scale-invariant formulas** identified (returns, ratios, z-scores, ranks, bps)
- **14 scale-sensitive formulas** identified (price buckets, ADV VND, close×volume, board-lot sizing, order generation)
- **3 double-scaling bug risks** in execution modules (order_generator.py, trade_blotter.py, pnl_monitor.py)

---

## 2. Rebuild Artifact

| Attribute | Value |
|-----------|-------|
| **Output Path** | `data/market_hose_hnx_2015_now_rebuilt_20260612.parquet` |
| **Canonical** | `data/market_2015_now.parquet` (NOT overwritten ✓) |
| **Rows** | 3,233,304 |
| **Columns** | 14 (ticker, date, exchange, O/H/L/C, volume, as_of, available_at, source, price_scale, adjusted, rebuild_date) |
| **Date Range** | 2015-01-05 to 2026-06-12 (4,176 days, 2,855 unique trading days) |
| **Tickers** | 1,444 (94.1% of canonical 1,534) |
| **Price Scale** | VND_FULL (median close = 9,570 VND) |
| **Source** | VCI via vnstock 4.0.2 Quote.history() |
| **Adjustment** | Backward adjusted (VCI default) |

### 2.1 Exchange Coverage

| Exchange | Tickers | Rows | Notes |
|----------|---------|------|-------|
| HOSE | 172 | 436,118 | VNINDEX group |
| HNX | 26 | 72,307 | HNX30 group |
| UPCOM | 229 | 460,684 | UpcomIndex group |
| UNKNOWN | 1,017 | 2,264,195 | Delisted/bonds/warrants/inactive |

### 2.2 Yearly Coverage

| Year | Rows | Tickers |
|------|------|---------|
| 2015 | 173,022 | 752 |
| 2016 | 198,179 | 860 |
| 2017 | 250,558 | 1,119 |
| 2018 | 292,560 | 1,230 |
| 2019 | 295,538 | 1,278 |
| 2020 | 308,617 | 1,316 |
| 2021 | 322,924 | 1,361 |
| 2022 | 341,350 | 1,380 |
| 2023 | 344,806 | 1,393 |
| 2024 | 324,126 | 1,411 |
| 2025 | 278,017 | 1,395 |
| 2026 | 103,607 | 1,363 |

---

## 3. Validation Results

### 3.1 Quality Checks (ALL PASS ✓)

| Check | Result | Detail |
|-------|--------|--------|
| Null dates | 0 ✓ | All dates present |
| Null OHLCV | 0 ✓ | Complete price/volume data |
| Duplicate (ticker,date) | 0 ✓ | No duplicates |
| OHLC invariant | 0 violations ✓ | H≥max(O,C), L≤min(O,C) |
| Negative volume | 0 ✓ | All volumes ≥ 0 |
| Zero close | 0 ✓ | All close > 0 |
| Price scale | VND_FULL ✓ | Median close = 9,570 VND |
| Close < 1000 fraction | 1.7% | Expected (low-priced stocks) |
| Scale ratio vs canonical | 1.000 median ✓ | Same scale as canonical |
| Target 5d outliers | 0 (of 27,837) ✓ | No impossible forward returns |
| Discontinuity scan (top-20) | 0 moves > 20% ✓ | All within exchange limits |

### 3.2 ADV Sanity (VND scale confirmed)

| Ticker | ADV_20 (shares) | ADV_20 (VND billions) | Assessment |
|--------|-----------------|----------------------|------------|
| SHB | 51.2M | 704.5B | Very liquid (HNX flagship) |
| HPG | 20.0M | 476.1B | Top HOSE blue chip |
| SSI | 15.3M | 416.0B | Top brokerage |
| STB | 5.5M | 381.7B | Sacombank |
| HAG | 2.4M | 36.8B | Mid-cap (reasonable) |

### 3.3 py_compile: ALL 37 FILES PASS ✓

---

## 4. Blockers & Limitations

### 4.1 VCI Listing API Down (P1 Blocker)
- **Error:** `ConnectionError: API request failed: Expecting value: line 1 column 1 (char 0)`
- **Impact:** Cannot get authoritative ticker-exchange mapping; 1,017 tickers remain UNKNOWN exchange
- **Workaround:** Used `Company.overview()` `com_group_code` field (VNINDEX→HOSE, HNX30→HNX, UpcomIndex→UPCOM)
- **Result:** 427 tickers resolved (HOSE=172, HNX=26, UPCOM=229); 1,017 remain UNKNOWN

### 4.2 90 Tickers Missing
- **Cause:** API errors during fetch (rate limiting, delisted symbols, non-standard tickers)
- **Impact:** Rebuilt covers 94.1% of canonical universe

### 4.3 Company API Limited
- **Issue:** VCI `Company.overview()` returns `com_group_code` but no explicit `exchange` field
- **Impact:** Exchange mapping is best-effort proxy, not authoritative

---

## 5. Critical Findings for L3 Attention

### 5.1 Price Scale Inconsistency in Ingestion (P1)
| Module | VND Scaling | Risk |
|--------|------------|------|
| `vnstock_adapter.py` | NONE | Could write unscaled data to VND warehouse |
| `vnstock_live.py` | NONE | Same risk |
| `vnstock_vci.py` | Per-row ×1000 | Correct for VCI source |
| `vnstock_ingest.py` | Median-based ×1000 | Correct heuristic |
| `update_market_data.py` | Row-mask ×1000 | Correct |

### 5.2 Double-Scaling Bug Risk in Execution (P1)
Three execution modules hardcode `×1000`, assuming price input is in **thousands**:
- `order_generator.py`: `target_notional / (current_price * 1000.0)`
- `trade_blotter.py`: `quantity * price * 1000.0`
- `pnl_monitor.py`: `abs(quantity) * fill_price * price_scale` where `price_scale = 1000.0`

**If these receive VND-scaled prices from the canonical warehouse, notional will be 1,000,000× too large.**

### 5.3 DataValidator Disconnected (P2)
`src/omega/data/validator.py` has 12 comprehensive validation rules but is NOT wired into either `update_market_data.py` or `batch_market_loader_resume.py`.

---

## 6. Evidence Files Produced

| File | Content |
|------|---------|
| `phase12_data_code_audit_20260612.md` | Full code audit with 53-file enumeration, data flow map, critical findings |
| `price_scale_decision_matrix_20260612.json` | 16 scale-invariant + 14 scale-sensitive formulas with impact analysis |
| `hose_hnx_rebuild_quality_20260612.json` | Comprehensive validation results (all checks pass) |
| `hose_hnx_rebuild_manifest_20260612.json` | Artifact manifest with schema, source, coverage, blockers |
| `l2_role15_hose_hnx_rebuild_phase12_audit_20260612.md` | This file — executive summary |
| `exchange_map_20260612.json` | Per-ticker exchange mapping |

---

## 7. Recommendations for L3

1. **P1: Standardize VND scaling** — Add explicit `ensure_vnd_scale()` guard at every ingestion write point. Make `vnstock_adapter.py` and `vnstock_live.py` apply the same ×1000 heuristic.
2. **P1: Fix execution double-scaling** — Audit `order_generator.py`, `trade_blotter.py`, `pnl_monitor.py` for correct price unit assumptions. Add unit tests with known VND prices.
3. **P2: Wire DataValidator** — Connect `src/omega/data/validator.py` into `update_market_data.py` and `batch_market_loader_resume.py`.
4. **P2: Resolve exchange UNKNOWN** — When VCI Listing API recovers, re-run exchange resolution for 1,017 UNKNOWN tickers.
5. **P3: Schema normalization** — Standardize `ticker` (not `symbol`), remove dead `time` column, ensure consistent `as_of`/`available_at`.

---

## 8. Compliance

- ✅ No canonical overwrite (`data/market_2015_now.parquet` preserved)
- ✅ No Antigravity scratch paths used
- ✅ No API keys/secrets in code or outputs
- ✅ Repo-relative paths only
- ✅ py_compile clean (37/37 files)
- ✅ All evidence persisted to `.ly_state/session/`
- ✅ **NOT self-approved** — awaiting Tier 3 audit (roles 21, 17, 23)
