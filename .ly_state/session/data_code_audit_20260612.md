# Data Code Audit - 2026-06-12

## Scope
All scoped data producer/consumer code inspected and documented.

## Files Audited

### 1. scripts/update_market_data.py (PRODUCER - DAILY INGESTION)
- **Data flow**: vnstock VCI -> fetch per symbol -> quality check -> tag ticker -> scale prices -> append to warehouse
- **Source**: `Vnstock().stock(symbol=sym, source='VCI').quote.history()`
- **Output**: `data/market_2015_now.parquet` (OVERWRITES CANONICAL)
- **Universe**: 20 VN30 representative tickers only
- **Schema handling**: Renames `time` -> `date`, normalizes to date-only
- **Price scaling**: Detects close < 1000 and multiplies by 1000 (VCI thousands -> VND)
- **Dedup**: `drop_duplicates(subset=['ticker','date'], keep='last')`
- **Quality gate**: Checks empty, >50% NaN per price col, nonpositive close
- **OVERWRITE RISK**: HIGH - writes directly to canonical path with no backup
- **VALIDATION GAP**: No DataValidator integration; no close-ratio extreme check

### 2. scripts/update_recent_portfolio_data.py (PRODUCER - PORTFOLIO UPDATE)
- **Data flow**: vnstock VCI (Quote API) -> fetch 5 symbols -> normalize -> append
- **Source**: `Quote(source='VCI', symbol=s).history()`
- **Output**: `data/market_2015_now.parquet` (OVERWRITES CANONICAL)
- **Universe**: 5 symbols only: VNM, VIC, HPG, TCB, BID
- **Schema**: Adds `as_of`, `available_at` columns (NOT in canonical schema for older rows)
- **Price scaling**: `close.median() < 1000` threshold for x1000 scaling
- **Overlap handling**: Removes old rows for updated symbols+window, then dedup
- **OVERWRITE RISK**: HIGH - writes directly to canonical path with no backup
- **SCHEMA MISMATCH**: Produces columns not present in older canonical data
- **VALIDATION GAP**: No DataValidator; no quality gate

### 3. scripts/backtest_v2_cpcv.py (CONSUMER - BACKTEST ENGINE)
- **Data flow**: Read canonical parquet -> filter by universe+year -> mask_suspended -> sanitize_ohlcv -> attach ADV -> compute features
- **Source**: `pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")`
- **Output**: `.ly_state/session/phase3_3_v2.json` (results only, no data modification)
- **READ-ONLY**: Does NOT modify canonical data
- **Sanitization**: Uses DataSanitizer (ffill <=3d, 3-sigma clip, dedup, min_price=0.01)
- **Suspended filtering**: Drops volume==0 rows
- **ADV**: T-1 PIT-lagged rolling 20d dollar volume
- **WALK-FORWARD**: Supports per-year universe files for PIT compliance

### 4. src/omega/data/vnstock_ingest.py (PRODUCER - V21 INGESTION)
- **Data flow**: vnstock VCI -> fetch per symbol -> normalize prices -> save
- **Output**: `data/v21_market_data.parquet` (SEPARATE FILE - no canonical overwrite)
- **Schema**: Uses `symbol` column (not `ticker`), has `time` column
- **API key**: Uses `dummy_key` fallback (works without credentials)
- **SCHEMA MISMATCH**: `symbol` vs `ticker`, output path differs from canonical

### 5. src/omega/quant/data/vci_ingest.py (PRODUCER - V21 DUPLICATE)
- **Data flow**: Nearly identical to vnstock_ingest.py
- **Output**: `data/v21_market_data.parquet` (SEPARATE FILE)
- **API key**: Requires `VNSTOCK_API_KEY` env var (different from vnstock_ingest.py)
- **DUPLICATE CODE**: Same logic as vnstock_ingest.py in different location
- **SCHEMA MISMATCH**: Same as vnstock_ingest.py

### 6. src/omega/data/validator.py (VALIDATION FRAMEWORK)
- **Rules**: OHLC structure, price moves >20%, zero volume, data gaps, provenance
- **Checksum**: SHA256 from .metadata.json sidecar
- **Price consistency**: Detects potential double-adjustment and unadjusted splits
- **NOT WIRED**: Not used by update_market_data.py or update_recent_portfolio_data.py

## Schema Discrepancies
| Column | Canonical | update_market | update_recent | vnstock_ingest | vci_ingest |
|--------|-----------|---------------|---------------|----------------|------------|
| ticker | YES | YES (added) | YES (added) | NO (symbol) | NO (symbol) |
| date | YES | YES (renamed) | YES (renamed) | YES (derived) | YES (derived) |
| time | DEAD (99.9% null) | N/A | N/A | YES (raw) | YES (raw) |
| as_of | PARTIAL (300 null) | NO | YES | NO | NO |
| available_at | PARTIAL (300 null) | NO | YES | NO | NO |
| open/high/low/close | YES (VND) | YES (scaled) | YES (scaled) | YES (scaled) | YES (scaled) |
| volume | YES | YES | YES | YES | YES |

## Overwrite Risk Summary
- **update_market_data.py**: DIRECT overwrite of canonical. No backup. No dry-run mode.
- **update_recent_portfolio_data.py**: DIRECT overwrite of canonical. No backup.
- **backtest_v2_cpcv.py**: SAFE - read-only consumer.
- **vnstock_ingest.py / vci_ingest.py**: SAFE - writes to separate path.

## Validation Gaps
1. Neither update script integrates DataValidator
2. No close-ratio extreme detection (>20x or <0.05x)
3. No target outlier detection (5d forward return abs > 10)
4. No backup/checksum before overwrite
5. Dead `time` column not reconciled
6. 20 null-date rows unexplained (match TOP_SYMBOLS from update_market_data.py)
