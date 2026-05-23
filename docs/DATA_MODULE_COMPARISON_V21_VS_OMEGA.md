# Data Module Comparison: V21_QUANT vs OMEGA_QUANT

**Date**: 2026-05-12  
**Purpose**: 1-1 mapping of data processing modules between V21 baseline and OMEGA canonical structure  
**Status**: Comprehensive Analysis

---

## Executive Summary

**Migration Status**: ~85% complete for core data processing  
**Key Gaps**: Corporate actions (P1), Provenance tracking (P2), Advanced feature engineering  
**Risk Level**: LOW (most critical paths migrated and L3 approved)

---

## 1. Data Ingestion & Loading

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **Raw Data Loader** | `src/v21_system/data.py` (MarketDataIngestor) | `packages/data/src/omega/data/loader.py` (DataLoader) | ✅ MIGRATED | OMEGA has PIT enforcement + corporate actions |
| **VNStock Integration** | Scattered across multiple scripts | `packages/data/src/omega/data/vnstock_vci.py` | ✅ CANONICAL | OMEGA centralized |
| **Cache Management** | Basic file cache | Parquet cache + metadata sidecar | ✅ ENHANCED | OMEGA has checksum validation |
| **PIT Timestamps** | Manual `as_of`/`available_at` | Automatic T+1 lag enforcement | ✅ ENHANCED | OMEGA enforces `as_of <= available_at` |
| **Corporate Actions (P1)** | ❌ NOT IMPLEMENTED | ✅ `corporate_action.py` + adjustment logic | ✅ NEW | Dividend/split/rights with PIT filter |
| **Provenance Tracking (P2)** | ❌ NOT IMPLEMENTED | ✅ `dataset_version`, `source`, `adjustments_applied`, SHA256 checksum | ✅ NEW | Sidecar metadata files |
| **Holiday Calendar** | Hardcoded or missing | `calendar.py` + JSON config (2015-2027) | ✅ ENHANCED | OMEGA has versioned config |

**Risk Assessment**: ✅ LOW - Core ingestion path is production-ready in OMEGA

---

## 2. Data Sanitization & Cleaning

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **OHLCV Cleaning** | `src/v21_system/core_intelligence/sanitization.py` (DataSanitizer) | `packages/data/src/omega/data/sanitizer.py` (DataSanitizer) | ✅ MIGRATED | Near-identical API |
| **Duplicate Removal** | ✅ Keep first | ✅ Keep first | ✅ SAME | |
| **Forward Fill** | ✅ Causal (max 3 days) | ✅ Causal (max 3 days) | ✅ SAME | |
| **Outlier Clipping** | ✅ 3-sigma per symbol | ✅ 3-sigma per symbol | ✅ SAME | |
| **Fit/Apply Pattern** | ✅ fit() on train, apply() on test | ✅ fit() on train, apply() on test | ✅ SAME | PIT-safe |
| **Invalid Price Removal** | ✅ min_price threshold | ✅ min_price threshold | ✅ SAME | |
| **PIT Safety Enforcement** | ⚠️ Manual | ✅ Automatic in apply() | ✅ ENHANCED | OMEGA enforces `as_of <= available_at` |

**Risk Assessment**: ✅ LOW - API compatible, OMEGA has stricter PIT enforcement

---

## 3. Data Validation

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **OHLC Consistency** | ❌ Basic checks | ✅ `validator.py` (structural_ohlc) | ✅ ENHANCED | OMEGA validates high >= low, etc. |
| **Price Jump Detection** | ❌ NOT IMPLEMENTED | ✅ 20% session move threshold | ✅ NEW | |
| **Zero Volume Detection** | ❌ NOT IMPLEMENTED | ✅ ADV-based liquidity check | ✅ NEW | |
| **Data Gap Detection** | ❌ NOT IMPLEMENTED | ✅ VN trading calendar validation | ✅ NEW | |
| **Provenance Validation** | ❌ NOT IMPLEMENTED | ✅ `dataset_version`, `source`, `adjustments_applied` format checks | ✅ NEW | |
| **Checksum Validation** | ❌ NOT IMPLEMENTED | ✅ SHA256 sidecar validation | ✅ NEW | |
| **Double-Adjustment Detection** | ❌ NOT IMPLEMENTED | ✅ Price consistency heuristics | ✅ NEW | |

**Risk Assessment**: ✅ LOW - OMEGA has comprehensive validation, V21 had minimal checks

---

## 4. Neutralization

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **Cross-Sectional (Hierarchical)** | `src/v21_system/core_intelligence/neutralization.py` (4-tier fallback) | `packages/core/src/omega/core/neutralization.py` (4-tier fallback) | ✅ MIGRATED | Same logic: Sector×Price → Sector → Exchange → Market |
| **Factor-Based (Fama-French)** | `src/v21_system/core_intelligence/factor_neutralization.py` (3-factor) | `packages/core/src/omega/core/neutralization.py` (FactorNeutralizer) | ✅ MIGRATED | Market/SMB/HML regression |
| **Winsorization** | ✅ 1%/99% quantiles | ✅ 1%/99% quantiles | ✅ SAME | |
| **Fallback Distribution Logging** | ✅ Stats tracking | ✅ Stats tracking | ✅ SAME | |
| **PIT Safety** | ✅ No temporal leakage | ✅ No temporal leakage | ✅ SAME | |
| **Integration with Feature Pipeline** | ⚠️ Manual wiring | ✅ `feature_neutralizer.py` auto-wiring | ✅ ENHANCED | OMEGA has dedicated bridge module |

**Risk Assessment**: ✅ LOW - Core logic migrated, OMEGA has better integration

---

## 5. Feature Engineering

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **Basic Features (ret_1, ret_5, vol_z)** | `src/v21_system/core_intelligence/feature_engineering.py` | `packages/quant/src/omega/quant/feature_module.py` | ✅ MIGRATED | Same API |
| **Advanced Features (RSI, MACD, BB, ATR)** | ⚠️ Partial implementation | ✅ Full implementation in `feature_module.py` | ✅ ENHANCED | OMEGA has complete suite |
| **Promoted Alphas** | ❌ NOT IMPLEMENTED | ✅ `promoted_alphas.py` integration | ✅ NEW | |
| **PIT Guard (T-1 lag)** | ⚠️ Manual enforcement | ✅ Automatic in `transform()` | ✅ ENHANCED | OMEGA enforces `i-1` lookback |
| **Vectorization** | ⚠️ Mixed (some loops) | ✅ 100% vectorized (numpy/pandas) | ✅ ENHANCED | OMEGA audit-approved |
| **Warmup Period Handling** | ⚠️ Inconsistent | ✅ Consistent `global_start` calculation | ✅ ENHANCED | |
| **VN Calendar Validation** | ❌ NOT IMPLEMENTED | ✅ Optional `validate_vn_calendar` flag | ✅ NEW | |

**Risk Assessment**: ⚠️ MEDIUM - V21 has some advanced features not yet in OMEGA, but OMEGA has better PIT enforcement

---

## 6. Data Contracts & Types

| Function | V21_QUANT | OMEGA_QUANT | Status | Notes |
|----------|-----------|-------------|--------|-------|
| **CleanDataFrame** | `src/v21_system/types.py` (dict-based) | Implicit in `feature_module.py` | ✅ COMPATIBLE | Same structure |
| **FeatureMatrix** | `src/v21_system/types.py` (dict-based) | Implicit in `feature_module.py` | ✅ COMPATIBLE | Same structure |
| **Schema Lock** | ✅ `schema_locked` flag | ✅ `require_schema_lock` flag | ✅ SAME | |
| **Contract Hash** | ✅ SHA256 hash | ✅ SHA256 hash | ✅ SAME | |

**Risk Assessment**: ✅ LOW - Contracts are compatible

---

## 7. Gap Analysis

### Critical Gaps (P0 - Must Fix Before Production)
**Status**: ✅ ALL CLOSED (P0/P1/P2 shipped)

### High-Priority Gaps (P1 - Should Fix Soon)
1. ❌ **Advanced Feature Parity**: V21 has some quant features (smart money, microstructure proxies) not yet in OMEGA
   - **Impact**: Medium (can add incrementally)
   - **Effort**: 2-3 days
   - **Mitigation**: Use V21 feature engineering as reference

### Medium-Priority Gaps (P2 - Nice to Have)
1. ❌ **Factor Exposure Analysis**: V21 has `factor_exposure.py` for portfolio attribution
   - **Impact**: Low (not critical for alpha generation)
   - **Effort**: 1 day
   - **Mitigation**: Can port later if needed

2. ❌ **Rolling Factor Neutralization**: V21 has `RollingFactorNeutralizer` for time-series
   - **Impact**: Low (cross-sectional is primary)
   - **Effort**: 1 day
   - **Mitigation**: Can port later if needed

---

## 8. Migration Recommendations

### Immediate Actions (This Week)
1. ✅ **DONE**: P1 Corporate Action Wiring (commit `0c203bd`)
2. ✅ **DONE**: P2 Provenance Tracking (commit `0c203bd`)
3. ✅ **DONE**: Boundary Test for future corporate actions (commit `9429b8d`)

### Short-Term (Next 2 Weeks)
1. ⏳ **Port Advanced Features**: Migrate V21's smart money features to OMEGA
   - Files: `src/v21_system/core_intelligence/feature_engineering.py` (lines 200-400)
   - Target: `packages/quant/src/omega/quant/feature_module.py`
   - Effort: 2 days

2. ⏳ **Port Factor Exposure**: Migrate V21's factor attribution to OMEGA
   - Files: `src/v21_system/core_intelligence/factor_exposure.py`
   - Target: `packages/quant/src/omega/quant/factor_exposure.py` (new)
   - Effort: 1 day

### Long-Term (Phase 12+)
1. ⏳ **Unified Data Pipeline**: Consolidate all data processing into single orchestrator
2. ⏳ **Real-Time Data Feed**: Integrate T+0 live data ingestion
3. ⏳ **Data Quality Dashboard**: Build monitoring UI for data validation metrics

---

## 9. File-Level Mapping Table

| V21_QUANT File | OMEGA_QUANT File | Migration Status | Notes |
|----------------|------------------|------------------|-------|
| `src/v21_system/data.py` | `packages/data/src/omega/data/loader.py` | ✅ MIGRATED | OMEGA has more features |
| `src/v21_system/core_intelligence/sanitization.py` | `packages/data/src/omega/data/sanitizer.py` | ✅ MIGRATED | API compatible |
| `src/v21_system/core_intelligence/neutralization.py` | `packages/core/src/omega/core/neutralization.py` | ✅ MIGRATED | Same logic |
| `src/v21_system/core_intelligence/factor_neutralization.py` | `packages/core/src/omega/core/neutralization.py` | ✅ MIGRATED | Merged into single module |
| `src/v21_system/core_intelligence/feature_engineering.py` | `packages/quant/src/omega/quant/feature_module.py` | ⚠️ PARTIAL | Basic features migrated, advanced features pending |
| `src/v21_system/core_intelligence/factor_exposure.py` | ❌ NOT MIGRATED | ⏳ PENDING | Low priority |
| `src/v21_system/vnstock_vci.py` (scattered) | `packages/data/src/omega/data/vnstock_vci.py` | ✅ CANONICAL | OMEGA centralized |
| ❌ N/A | `packages/data/src/omega/data/corporate_action.py` | ✅ NEW | P1 implementation |
| ❌ N/A | `packages/data/src/omega/data/validator.py` | ✅ NEW | Comprehensive validation |
| ❌ N/A | `packages/data/src/omega/data/calendar.py` | ✅ NEW | VN holiday calendar |

---

## 10. Test Coverage Comparison

| Test Category | V21_QUANT | OMEGA_QUANT | Status |
|---------------|-----------|-------------|--------|
| **Data Loader Tests** | ⚠️ Basic (5 tests) | ✅ Comprehensive (14 tests) | ✅ ENHANCED |
| **Sanitizer Tests** | ⚠️ Basic (8 tests) | ✅ Comprehensive (16 tests) | ✅ ENHANCED |
| **Validator Tests** | ❌ NOT IMPLEMENTED | ✅ Comprehensive (15 tests) | ✅ NEW |
| **Neutralization Tests** | ✅ Good (16 tests) | ✅ Good (16 tests) | ✅ SAME |
| **Feature Module Tests** | ⚠️ Basic (10 tests) | ✅ Comprehensive (20+ tests) | ✅ ENHANCED |
| **Corporate Action Tests** | ❌ NOT IMPLEMENTED | ✅ Comprehensive (14 tests) | ✅ NEW |
| **Provenance Tests** | ❌ NOT IMPLEMENTED | ✅ Comprehensive (15 tests) | ✅ NEW |

**Total Test Count**:
- V21_QUANT: ~39 data tests
- OMEGA_QUANT: ~110 data tests (including P1/P2)

---

## 11. Conclusion

### Summary
- **Core Data Processing**: ✅ 85% migrated and L3 approved
- **P0 Neutralization**: ✅ SHIPPED (commit `5d5428d`)
- **P1 Corporate Actions**: ✅ SHIPPED (commit `0c203bd`)
- **P2 Provenance Tracking**: ✅ SHIPPED (commit `0c203bd`)
- **Boundary Test**: ✅ SHIPPED (commit `9429b8d`)

### Key Strengths of OMEGA vs V21
1. **PIT Safety**: Automatic enforcement throughout pipeline
2. **Provenance**: Full audit trail with checksums
3. **Validation**: Comprehensive data quality checks
4. **Test Coverage**: 3x more tests than V21
5. **Corporate Actions**: Production-ready adjustment logic
6. **Hermetic Tests**: Workspace-local fixtures (no OS temp dependency)

### Remaining Work
1. ⏳ Port advanced features from V21 (smart money, microstructure)
2. ⏳ Port factor exposure analysis (low priority)
3. ⏳ Real-time data feed integration (Phase 12+)

### Risk Assessment
- **Overall Risk**: ✅ LOW
- **Production Readiness**: ✅ READY for Phase 12 (Portfolio Optimization)
- **Recommendation**: Proceed with Phase 12, port advanced features in parallel

---

**Last Updated**: 2026-05-12 23:44 GMT+7  
**Author**: Ly (L1 Orchestrator)  
**Status**: APPROVED for Phase 12 kickoff
