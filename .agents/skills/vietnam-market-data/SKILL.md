---
name: vietnam-market-data
description: Vietnam equity market data principles for OMEGA_QUANT. HOSE/HNX/UPCOM exchanges, VCI/vnstock data providers, ticker lifecycle, VND_FULL price scale, sector mapping, delisting/survivorship, canonical data schema.
when_to_use: "When ingesting, transforming, validating, or querying Vietnam stock market data. Use for any data pipeline work involving HOSE/HNX/UPCOM equities, VCI/vnstock APIs, or VND price handling."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Vietnam Market Data — OMEGA_QUANT Data Contract

> Domain skill for Vietnam equity market data ingestion, validation, and canonical schema.
> **VND_FULL price scale, PIT-safe ingestion, survivorship-free universe.**

---

## 1. Exchange Structure

### Vietnam Equity Markets

| Exchange | Full Name | Characteristics |
|----------|-----------|----------------|
| **HOSE** | Ho Chi Minh Stock Exchange | Large/mid-cap, highest liquidity, VN-Index/VN30 |
| **HNX** | Hanoi Stock Exchange | Mid/small-cap, HNX-Index, HNX30 |
| **UPCOM** | Unlisted Public Company Market | OTC-like, smallest caps, wider spreads |

### Trading Sessions (UTC+7, Vietnam Time)

| Session | Time | Type |
|---------|------|------|
| **ATO** | 09:00 - 09:15 | Opening auction (single price) |
| **Continuous AM** | 09:15 - 11:30 | Continuous matching |
| **Lunch Break** | 11:30 - 13:00 | No trading |
| **Continuous PM** | 13:00 - 14:30 | Continuous matching |
| **ATC** | 14:30 - 14:45 | Closing auction (single price) |

### Market Rules

| Rule | Value | Notes |
|------|-------|-------|
| **Board lot** | 100 shares | Round to nearest 100 |
| **Daily price limit** | ±7% from reference | ±10% for stocks without reference price |
| **Settlement** | T+2.5 | T+1 shares arrive, T+2 cash settles |
| **Tick size (<10K VND)** | 10 VND | Price-dependent |
| **Tick size (10K-50K VND)** | 50 VND | |
| **Tick size (50K-100K VND)** | 100 VND | |
| **Tick size (100K-500K VND)** | 500 VND | |
| **Tick size (>=500K VND)** | 1000 VND | |
| **Foreign room** | Exists per stock | May block foreign buys at limit |

---

## 2. Data Sources

### Primary: DirectVCIClient (SSOT)

```python
from omega.data.vci_direct import DirectVCIClient

df = DirectVCIClient().fetch_history(
    "VNM", "2015-01-01", "2026-06-13", as_of="2026-06-14T09:00:00+07:00"
)
```

`DirectVCIClient` is the only active VCI network-ingestion SSOT. It enforces HTTPS/path allowlisting, bounded payloads and retries, redaction, calendar/session filters, and `as_of`/`available_at` PIT constraints. Do not add new `from vnstock import ...` network call sites. Archived adapters under `archive/legacy_adapters/` are fail-closed historical inventory.

### Provider Characteristics

| Provider | Pros | Cons |
|----------|------|------|
| **VCI** | Official, EOD OHLCV, wide coverage | Returns prices in THOUSANDS of VND |
| **vnstock wrapper** | Unified API, caching | Wrapper overhead |
| **Local parquet** | Fast, PIT-safe, versioned | Must be refreshed regularly |

### Data Refresh Pipeline

```
VCI API → DirectVCIClient.fetch_history() → ensure_vnd_scale() → DataSanitizer → parquet cache
                                                              ↓
                                                   data/market_*.parquet
```

### Validation SSOT

Use `src/omega/data/sanitizer.py` for `DataSanitizer`, `DataValidator`, `ValidationIssue`, and `DataQualityChecker`. Train with `fit(train_df)`, then validate later observations with `apply(test_df)`. Compatibility modules `omega.data.validator`, `omega.data.data_validator`, and `omega.data.data_quality` re-export these exact objects; they must not acquire duplicate logic.

---

## 3. VND_FULL Price Scale Contract

### CRITICAL: VCI Returns Prices in THOUSANDS

| Source | Price for VNM @ 50,000 VND |
|--------|---------------------------|
| **VCI raw** | 50.0 (thousands) |
| **VND_FULL (canonical)** | 50000.0 (whole Dong) |

### The `ensure_vnd_scale()` Function

| Check | Action |
|-------|--------|
| Max price < 1000 | Likely in thousands → multiply by 1000 |
| Max price >= 1000 | Already in VND_FULL → no action |
| Mixed scale detected | Raise `PITViolationError` |

### Price Scale Verification

```python
# Every data pipeline MUST verify VND_FULL scale
assert df['close'].max() > 1000, "Prices not in VND_FULL scale"
assert df['close'].min() > 0, "Negative prices detected"
```

### Anti-Pattern: Silent Scale Mismatch

| Don't | Do |
|-------|-----|
| Assume price scale | Always run `ensure_vnd_scale()` |
| Mix VND_FULL and thousands | Normalize at ingestion, never downstream |
| Ignore scale in calculations | Document VND_FULL in every function docstring |

---

## 4. Ticker Lifecycle

### Lifecycle Stages

```
IPO → Listed → Trading → [Warning/Delinquent] → Suspended → Delisted
                              ↓
                        [Sector change] [Stock split] [Reverse split]
                        [Rights issue] [Bonus shares] [Dividend]
```

### Ticker Status Flags

| Status | Meaning | Data Action |
|--------|---------|-------------|
| **Active** | Normal trading | Include in universe |
| **Warning** | Financial concern | Flag, may exclude |
| **Delinquent** | Disclosure failure | Exclude from universe |
| **Suspended** | Trading halted | Exclude, carry last price |
| **Delisted** | Removed from exchange | Keep historical, mark delisted |

### Corporate Actions

| Action | PIT-Safe Handling |
|--------|-------------------|
| **Stock split** | Adjust historical OHLCV on ex-date (available_at = ex-date) |
| **Bonus shares** | Adjust volume, adjust price on ex-date |
| **Cash dividend** | Adjust on ex-date (price drops by dividend amount) |
| **Rights issue** | Adjust on ex-date with theoretical ex-rights price |
| **Merger/acquisition** | Last trading day → mark delisted, remove from universe |

---

## 5. Survivorship Bias Prevention

### The Problem

Using only currently-listed stocks creates upward bias: you never see the returns of stocks that were delisted.

### OMEGA_QUANT Approach

| Principle | Implementation |
|-----------|---------------|
| **Point-in-time universe** | At each date T, use only stocks that were listed and tradeable at T |
| **Include delisted stocks** | Historical data for delisted stocks preserved in parquet |
| **Delisting return** | Mark final return as -100% (total loss) or actual liquidation value |
| **Universe snapshots** | Store universe composition at each rebalance date |

### Verification

- [ ] Universe at date T does not include stocks listed after T
- [ ] Universe at date T includes stocks later delisted (if they were active at T)
- [ ] Backtest engine uses point-in-time universe, not current universe
- [ ] Delisted stocks have terminal return recorded

---

## 6. Sector Mapping

### ICB Level-2 Sector Classification

| File | Path | Content |
|------|------|---------|
| **Sector mapping** | `data/sector_mapping_level2.csv` | ticker → sector assignment |

### Sector Uses

| Use Case | Why |
|----------|-----|
| **Sector neutralization** | Remove sector factor from alpha signals |
| **Sector risk limits** | Max 25% in any one sector |
| **Sector rotation** | Cross-sector momentum/mean-reversion |
| **Factor analysis** | Identify sector-specific alpha |

### Sector Mapping Rules

| Rule | Detail |
|------|--------|
| **PIT sector** | Sector assignment can change — use PIT sector at each date |
| **Missing sector** | Assign to "Other" or "Unclassified" |
| **Sector reclassification** | Track history, use PIT assignment |

---

## 7. Canonical Data Schema

### EOD OHLCV Parquet Schema

| Column | Type | Description |
|--------|------|-------------|
| **date** | datetime64 | Trading date (UTC+7 midnight) |
| **symbol** | str | Ticker symbol (e.g., "VNM") |
| **open** | float64 | Opening price (VND_FULL) |
| **high** | float64 | Highest price (VND_FULL) |
| **low** | float64 | Lowest price (VND_FULL) |
| **close** | float64 | Closing price (VND_FULL) |
| **volume** | int64 | Trading volume (shares) |
| **exchange** | str | HOSE / HNX / UPCOM |

### PIT Timestamp Columns

| Column | Type | Description |
|--------|------|-------------|
| **as_of** | datetime64 | When the data point occurred |
| **available_at** | datetime64 | When it became knowable (T+1 09:00 VN) |

### Schema Invariants

| Invariant | Check |
|-----------|-------|
| `as_of <= available_at` | Always true — violation raises `PITViolationError` |
| `close > 0` | All prices positive, VND_FULL scale |
| `volume >= 0` | Non-negative volume |
| `high >= max(open, close)` | Intraday high consistency |
| `low <= min(open, close)` | Intraday low consistency |
| No duplicate (date, symbol) | Unique per day per ticker |
| Monotonic date per symbol | Dates in order, no gaps on trading days |

### Trading Calendar

| File | Path | Content |
|------|------|---------|
| **VN holidays** | `config/vn_holidays.json` | Vietnamese holidays 2015-2027 |

| Rule | Detail |
|------|--------|
| **Trading days** | Mon-Fri, excluding VN holidays |
| **Tet holiday** | ~7-10 days around lunar new year (Jan/Feb) |
| **Data gaps** | Only valid on non-trading days |

---

## 8. Data Quality Checks

### Ingestion Validation Checklist

- [ ] **Scale check**: VND_FULL verified via `ensure_vnd_scale()`
- [ ] **Completeness**: No missing trading days (check against VN holiday calendar)
- [ ] **OHLCV consistency**: high >= max(open, close), low <= min(open, close)
- [ ] **Volume sanity**: volume >= 0, no volume spikes > 10x 20-day average without flag
- [ ] **Price limits**: daily return within ±7% (±10% for no-reference stocks)
- [ ] **PIT timestamps**: as_of <= available_at for all rows
- [ ] **Duplicates**: no duplicate (date, symbol) pairs
- [ ] **Universe freshness**: new listings appear, delistings recorded

### Common Data Issues

| Issue | Detection | Fix |
|-------|-----------|-----|
| **Scale mismatch** | max(close) < 1000 | Run `ensure_vnd_scale()` |
| **Missing holidays** | Trading day with no data | Check against `vn_holidays.json` |
| **Split not adjusted** | Sudden 50% price drop + 2x volume | Verify corporate action adjustment |
| **Stale data** | Last update > T+2 | Re-fetch from VCI |
| **Wrong exchange** | Symbol on HOSE but tagged HNX | Cross-check exchange assignment |

---

## 9. Verification Checklist

- [ ] All prices in VND_FULL (whole Vietnamese Dong)
- [ ] VCI data multiplied by 1000 via `ensure_vnd_scale()`
- [ ] Trading calendar aligned with `config/vn_holidays.json`
- [ ] Universe is point-in-time (survivorship-free)
- [ ] Sector mapping uses PIT assignment from `data/sector_mapping_level2.csv`
- [ ] Corporate actions adjusted at `available_at`, not `as_of`
- [ ] Schema invariants pass on every parquet write
- [ ] Exchange field correctly populated (HOSE/HNX/UPCOM)

---

## 10. Anti-Patterns

| Don't | Do |
|-------|-----|
| Use raw VCI prices without scale check | Always `ensure_vnd_scale()` at ingestion |
| Use current universe for historical backtests | Use point-in-time universe snapshots |
| Ignore delisted stocks | Include with terminal delisting return |
| Assume 252 trading days/year | Use VN-specific calendar (~245-250 days) |
| Ignore lunch break | ATO/ATC auctions have different dynamics |
| Mix exchanges without tagging | Always carry exchange column |
| Forget foreign room constraints | Flag stocks at foreign ownership limit |
| Use US market assumptions | ±7% limits, T+2.5 settlement, 100-share lots |

---

## 11. SOD/PIT Guardrails

| Guardrail | Rule |
|-----------|------|
| **PIT: available_at** | EOD data available at T+1 09:00 VN time, not at close |
| **PIT: corporate actions** | Adjustments applied at `available_at` of ex-date, not retroactively |
| **SOD: data provenance** | Every dataset must document source, fetch date, and transformation steps |
| **SOD: no silent mutation** | Data transformations must be logged and versioned |
| **SOD: Tier 3 audit** | Data pipeline changes submitted to Code Reviewer (role 21) + QA Engineer (role 17) |

---

> **Remember:** Vietnam is not the US market. Price limits, T+2.5 settlement, board lots, VND scale, and exchange-specific rules all matter.
