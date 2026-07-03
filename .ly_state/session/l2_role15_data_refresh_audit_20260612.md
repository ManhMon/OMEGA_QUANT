# L2 Role 15 - Data Refresh Audit Report
**Date**: 2026-06-12
**Role**: 15 Data Engineer - OpenCode L2 Data Audit/Refresh
**Status**: AUDIT COMPLETE - NO PRODUCTION CHANGES MADE

---

## Executive Summary

Completed full audit of the OMEGA_QUANT data pipeline. Canonical warehouse
(`data/market_2015_now.parquet`) is structurally sound but has **three actionable
data quality issues** and **two critical code safety gaps**. A small controlled
sample was successfully fetched from vnstock/VCI to a parallel file, confirming
source access works without credentials. **No production code was modified.**

---

## 1. Canonical Data Health

| Metric | Value | Verdict |
|--------|-------|---------|
| Total rows | 3,392,283 | OK |
| Tickers | 1,534 | OK |
| Date range | 2015-01-05 to 2026-06-01 | STALE (11 days behind) |
| SHA256 | E9B0B4F1...8CAB5F | RECORDED |
| Duplicate (ticker,date) | 0 | CLEAN |
| OHLC violations | 0 | CLEAN |
| Nonpositive prices | 0 | CLEAN |
| Volume=0 rows | 1,075,868 (31.7%) | EXPECTED (suspended stocks) |
| Null dates | 20 (1 per VN30 ticker) | WARNING |
| Dead `time` column | 3,392,263/3,392,283 null | DEAD WEIGHT |
| Close ratio >20 | 920 rows | WARNING |
| Close ratio <0.05 | 899 rows | WARNING |
| 5d target abs >10 | 2,260 rows | ALERT |
| 5d target std | 22.34 | ALERT (should be <1.0) |

### Key Findings

**F1 - Null Date Rows (20 rows)**: Exactly 1 null date per VN30 TOP_SYMBOLS
ticker (VCB, HPG, FPT, VIC, MSN, MWG, VNM, SAB, VHM, GAS, BID, VPB, ACB, TCB,
MBB, HDB, STB, VIB, CTG, TPB). These match the `TOP_SYMBOLS` list in
`update_market_data.py`. Likely cause: a batch append where one row per symbol
had unparseable date. These rows carry OHLCV data but cannot be used by any
time-series operation.

**F2 - Extreme Close Ratios (1,819 rows)**: 920 rows where close/prev_close > 20
and 899 rows where close/prev_close < 0.05. These are likely unadjusted corporate
actions (splits, reverse splits, stock dividends) or data errors. The backtest
engine's DataSanitizer clips at 3-sigma, which partially handles these, but the
raw data should be quarantined or flagged.

**F3 - Target Outliers (2,260 rows, abs > 10)**: Forward 5-day returns exceeding
1000% are physically impossible on HOSE (7% daily limit). These are almost
certainly data errors (price scale mismatches, unadjusted splits near the end of
the lookback window). The target std of 22.34 (vs expected ~0.05) confirms
severe contamination.

---

## 2. Code Safety Audit

### CRITICAL: Overwrite Risk (Both Update Scripts)

**update_market_data.py (line 194)**:
```python
combined.to_parquet(WAREHOUSE_PATH, index=False)
```
Directly overwrites `data/market_2015_now.parquet` with no backup, no dry-run,
no checksum verification. A failed fetch or bad scaling could corrupt the entire
warehouse.

**update_recent_portfolio_data.py (line 75)**:
```python
combined.to_parquet(OUT, index=False)
```
Same overwrite pattern. `OUT` and `BASE` both point to the same canonical path.

### WARNING: Validation Gap

Neither update script uses `DataValidator` from `src/omega/data/validator.py`.
The validator has comprehensive rules (OHLC, price moves, gaps, provenance) but
is completely disconnected from the ingestion pipeline.

### INFO: Dead Code Duplication

`src/omega/data/vnstock_ingest.py` and `src/omega/quant/data/vci_ingest.py` are
near-identical copies with different API key handling (dummy_key vs required env
var). Both output to `data/v21_market_data.parquet`, not canonical.

### INFO: vnstock Deprecation

vnstock 4.0.2 emits deprecation notice for `Vnstock()` class as of 31/08/2025.
Migration path: `from vnstock.api.quote import Quote`.

---

## 3. Source Access Verification

| Check | Result |
|-------|--------|
| vnstock installed | YES (v4.0.2) |
| VCI source accessible | YES (no credentials needed) |
| Windows encoding workaround | REQUIRED (chcp 65001) |
| Sample fetch (6 symbols, 32 days) | SUCCESS (192 rows) |
| Sample OHLC quality | CLEAN |
| Sample price scale | Thousands (needs x1000 for VND) |
| Sample output path | `data/market_2015_now_refreshed_20260612.parquet` |

---

## 4. py_compile Results

All 6 scoped Python files compile successfully:
- `scripts/update_market_data.py` - OK
- `scripts/update_recent_portfolio_data.py` - OK
- `scripts/backtest_v2_cpcv.py` - OK
- `src/omega/data/vnstock_ingest.py` - OK
- `src/omega/quant/data/vci_ingest.py` - OK
- `src/omega/data/validator.py` - OK

---

## 5. Recommendations (Exact Safe Next Steps)

### R1: TARGETED QUARANTINE (Immediate, Low Risk)
Remove or flag the 20 null-date rows and quarantine the 1,819 extreme-ratio rows.
This can be done by writing a filtered copy to a new path without touching
canonical.

### R2: CODE GUARD - Backup Before Overwrite (High Priority)
Add a mandatory backup step to both update scripts:
```python
# Proposed guard for update_market_data.py line ~193:
import shutil
if WAREHOUSE_PATH.exists():
    backup = WAREHOUSE_PATH.with_suffix('.parquet.bak')
    shutil.copy2(WAREHOUSE_PATH, backup)
    logger.info(f"Backup created: {backup}")
```

### R3: CODE GUARD - Wire DataValidator (High Priority)
Add DataValidator integration to both update scripts before the write step.
Reject batches that fail validation instead of silently appending bad data.

### R4: FULL REBUILD (Medium Term, Requires Approval)
Once code guards are in place:
1. Fetch all 1,534 tickers via vnstock VCI (batched, rate-limited)
2. Apply x1000 price scaling
3. Run DataValidator per batch
4. Write to `data/market_2015_now_refreshed_20260612.parquet`
5. Validate merged dataset (duplicates, OHLC, ratios, targets)
6. Only after validation passes: replace canonical with backup

### R5: SCHEMA RECONCILIATION (Medium Term)
- Drop dead `time` column from canonical
- Standardize `as_of`/`available_at` presence across all rows
- Reconcile `symbol` vs `ticker` naming in vnstock_ingest.py / vci_ingest.py

### R6: CONSOLIDATE DUPLICATE INGESTION MODULES (Low Priority)
Merge `vnstock_ingest.py` and `vci_ingest.py` into a single module with
consistent API key handling.

---

## 6. Evidence Files

| File | Description |
|------|-------------|
| `.ly_state/session/data_code_audit_20260612.md` | Full code flow documentation |
| `.ly_state/session/data_refresh_plan_20260612.json` | Refresh plan with risks |
| `.ly_state/session/data_refresh_quality_20260612.json` | Validation results (canonical + sample) |
| `data/market_2015_now_refreshed_20260612.parquet` | Sample refreshed data (192 rows, 6 symbols) |

---

## 7. Verdict

**NO production code was modified.** Canonical data file was NOT overwritten.
A parallel sample file was created for validation purposes only.

**Recommended action**: R1 (quarantine) + R2 (backup guard) + R3 (validator wiring)
should be implemented before any full refresh (R4). The target outlier contamination
(F3) is the most impactful data quality issue for model training fidelity.
