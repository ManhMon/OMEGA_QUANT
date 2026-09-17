# L2 Role 15 - Canonical Data Replacement Exchange Resolution

**Task**: CANONICAL_DATA_REPLACEMENT_EXCHANGE_RESOLUTION_20260612
**Date**: 2026-06-12T19:20:59.280367+07:00
**Role**: 15 data-engineer (Tier 2)
**Status**: **AWAITING L3 APPROVAL** - DO NOT OVERWRITE CANONICAL

---

## 1. Exchange Resolution Summary

### Sources Queried
| Source | API | Status | Rows |
|--------|-----|--------|------|
| VCI | symbols_by_exchange() | FAILED (ConnectionError) | - |
| KBS | symbols_by_exchange(get_all=True) | OK | 3249 |
| VND | all_symbols() | NOT_AVAILABLE (vnstock 4.x) | - |
| MSN | symbols_by_exchange() | FAILED (NotImplementedError) | - |

### Resolution Stats
| Metric | Value |
|--------|-------|
| Old map entries | 1444 |
| KBS stocks resolved | 1531 |
| KBS non-stocks excluded | 1718 |
| Old map kept (not in KBS) | 0 |
| Conflicts resolved (KBS wins) | 10 |
| Still UNKNOWN | 6 |
| Authoritative map total | 3255 |

### Conflicts Found
10 tickers had different exchange assignments between old map and KBS.
KBS data takes precedence in all cases.

### Still Unknown
6 tickers remain UNKNOWN in the authoritative map.
6 of these appear in the rebuilt parquet.
These are excluded from the HOSE/HNX candidate.

---

## 2. Candidate Dataset

### Schema
| Column | Type | Notes |
|--------|------|-------|
| ticker | object | Stock ticker symbol |
| date | datetime64 | Trading date |
| exchange | object | HOSE or HNX only |
| open | float64 | Open price (VND) |
| high | float64 | High price (VND) |
| low | float64 | Low price (VND) |
| close | float64 | Close price (VND) |
| volume | int64 | Trading volume |
| as_of | object | Data snapshot timestamp |
| available_at | datetime64 | PIT availability timestamp |
| source | object | Data source (VCI) |
| price_scale | object | VND |
| adjusted | object | backward_adjusted |
| rebuild_date | object | Date of rebuild |

### Basic Stats
| Metric | Value |
|--------|-------|
| Total rows | 1,687,749 |
| Total tickers | 666 |
| Date range | 2015-01-05 00:00:00 to 2026-06-12 00:00:00 |
| HOSE tickers | 380 |
| HNX tickers | 286 |
| HOSE rows | 953,440 |
| HNX rows | 734,309 |
| File size | 19.8 MB |

---

## 3. Validation Results

### Data Quality
| Check | Result | Pass |
|-------|--------|------|
| UNKNOWN exchange rows | 0 | YES |
| UNKNOWN exchange tickers | 0 | YES |
| Duplicate ticker-date pairs | 0 | YES |
| Total nulls (OHLCV) | 0 | YES |
| OHLC invariant violations | 0 | YES |
| PIT available_at > date | 0 | YES |

### Null Breakdown
| Column | Null Count |
|--------|-----------|
| open | 0 |
| high | 0 |
| low | 0 |
| close | 0 |
| volume | 0 |

### Volume Statistics
| Metric | Value |
|--------|-------|
| Zero-volume rows | 262,362 (15.55%) |
| Fully inactive tickers | 0 |
| Active rows | 1,425,387 |

### ADV / Capacity Sanity
| Metric | Value |
|--------|-------|
| ADV median (shares/day) | 18,092 |
| ADV mean (shares/day) | 916,835 |
| Daily turnover median (VND) | 296,768,250 |
| Daily turnover total (VND) | 15,438,078,898,513 |

---

## 4. Backup & Integrity

| File | Path | SHA-256 |
|------|------|---------|
| Canonical (original) | data/market_2015_now.parquet | e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f |
| Backup | data/market_2015_now.backup_20260612.parquet | e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f |
| Candidate | data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet | 206196b1889b1a308b302b5278cd7de0a55d30cad1a2003db22f4034e2514285 |
| Backup matches canonical | True |
| Canonical NOT modified | True |

---

## 5. Comparison: Canonical vs Candidate

| Metric | Canonical (old) | Candidate (new) |
|--------|-----------------|-----------------|
| Rows | 3,392,283 | 1,687,749 |
| Tickers | 1,534 | 666 |
| Date max | 2026-06-01 | 2026-06-12 00:00:00 |
| Exchange column | No | Yes (HOSE/HNX only) |
| Price scale | Mixed | VND |
| Source columns | 10 | 14 |

---

## 6. Governance

- **Canonical NOT overwritten**: data/market_2015_now.parquet is untouched.
- **Backup created**: data/market_2015_now.backup_20260612.parquet
- **Candidate ready**: data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet
- **Awaiting L3 approval**: Code Reviewer (role 21), QA Engineer (role 17), Performance Tester (role 23)
- **L1 final enforcer** required for actual canonical replacement.
- No secrets/API keys in outputs.
- No Antigravity scratch paths used.
- All artifacts in .ly_state/session/ (repo-relative).

---

## 6b. Code Quality Verification

### py_compile (6/6 PASS)
| File | Status |
|------|--------|
| src/omega/data/exchange_resolver.py | PASS |
| src/omega/data/vnstock_vci.py | PASS |
| src/omega/data/vnstock_adapter.py | PASS |
| src/omega/data/vnstock_ingest.py | PASS |
| src/omega/data/vnd_price_contract.py | PASS |
| .ly_state/session/tmp/canonical_exchange_resolution_20260612.py | PASS |

### pytest (39/39 PASS, 0 failed, 5.70s)
| Test File | Tests | Status |
|-----------|-------|--------|
| tests/data_test_vnd_full_exchange_fix.py | 39 | PASS |

### Post-Verification
- Canonical SHA-256 re-verified after pipeline: `e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f`
- Canonical file confirmed UNTOUCHED.

---

## 7. Artifacts Produced

| Artifact | Path |
|----------|------|
| Exchange sources | .ly_state/session/vnstock_exchange_sources_20260612.json |
| Exchange resolution report | .ly_state/session/exchange_resolution_report_20260612.json |
| Quality report | .ly_state/session/canonical_replacement_candidate_quality_20260612.json |
| Backup manifest | .ly_state/session/canonical_backup_manifest_20260612.json |
| Candidate parquet | data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet |
| Backup parquet | data/market_2015_now.backup_20260612.parquet |
| This report | .ly_state/session/l2_role15_canonical_data_replacement_exchange_resolution_20260612.md |
