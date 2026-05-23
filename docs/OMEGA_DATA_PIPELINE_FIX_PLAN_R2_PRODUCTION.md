# OMEGA Data Pipeline - Fix Plan Round 2 (PRODUCTION GRADE)
**Date**: 2026-05-13  
**Status**: PENDING L2 IMPLEMENTATION  
**Previous Audit**: L3 re-audit `role21-reaudit-20260513-034602` verdict `[NEEDS_FIX]`  
**Commit**: `8b21e0e`

---

## Overview

L3 re-audit identified **3 remaining blockers**. This plan provides **production-grade fixes** (no stubs, no fake classes).

**Target**: All blockers fixed, L3 re-audit APPROVED.

---

## Blocker 1: HIGH - Checksum Validator Not Wired to Runtime

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/validator.py`, `OMEGA_QUANT/packages/data/src/omega/data/loader.py`

### Problem
- `DataValidator._validate_checksum_from_sidecar()` exists but never called in production
- `validate_rows()` skips checksum validation

### Fix
Wire checksum into `validate_rows()`:

```python
# In validator.py, update validate_rows():
def validate_rows(self, rows: List[Dict[str, Any]], symbol: Optional[str] = None, parquet_path: Optional[Path] = None) -> List[ValidationIssue]:
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda r: r.get("timestamp"))
    sym = symbol or str(sorted_rows[0].get("symbol", "UNKNOWN"))
    issues: List[ValidationIssue] = []

    issues.extend(self._validate_structural_ohlc(sorted_rows, sym))
    issues.extend(self._validate_price_moves(sorted_rows, sym))
    issues.extend(self._validate_zero_volume_liquidity(sorted_rows, sym))
    issues.extend(self._validate_data_gaps(sorted_rows, sym))

    if self.validate_provenance:
        issues.extend(self._validate_provenance_metadata(sorted_rows, sym))
        # NEW: Wire checksum validation
        if parquet_path:
            issues.extend(self._validate_checksum_from_sidecar(parquet_path, sym))

    return issues
```

Update loader call:
```python
# In loader.py load_prices():
validation_issues = self.validator.validate_rows(
    df.to_dict('records'), 
    symbol=ticker,
    parquet_path=cache_path
)
```

---

## Blocker 2: HIGH - Production Pipeline Import Path Broken

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/pipeline/production_pipeline.py`

### Problem
- Line 10 imports from `src.v21_system...` (V21 legacy path)
- Fails with `ModuleNotFoundError`
- **Solution**: Remove dependency on non-existent modules; keep only what exists in OMEGA

### Fix
**Option A (Recommended)**: Remove unused imports, keep only what's available:

```python
# BEFORE (lines 9-12):
from src.v21_system.layer_01_core_intelligence.data_validator import DataValidator, ValidationIssue
from src.v21_system.layer_01_core_intelligence.feature_module import FeatureModule, FeatureModuleConfig
from src.v21_system.layer_01_core_intelligence.neutralization_engine import NeutralizationEngine
from src.v21_system.layer_01_core_intelligence.corporate_action import CorporateActionAdjuster, CorporateAction

# AFTER (production-grade):
from omega.data.validator import DataValidator, ValidationIssue
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
# NOTE: FeatureModule, NeutralizationEngine not yet in OMEGA package
# These will be integrated in Phase 12 (Portfolio Optimization)
```

Remove or comment out code that uses missing modules:
```python
# Lines 120-130: Remove feature_module and neutralization_engine calls
# These are Phase 12 features, not Phase 10 scope
```

**Verification**:
```bash
python -c "from omega.data.pipeline.production_pipeline import ProductionDataPipeline"
# Should succeed without ModuleNotFoundError
```

---

## Blocker 3: MEDIUM - Vectorization Not Complete

**Severity**: MEDIUM  
**Files**: 
- `OMEGA_QUANT/packages/data/src/omega/data/loader.py` (line 595)
- `OMEGA_QUANT/packages/data/src/omega/data/pipeline/production_pipeline.py` (lines 121, 130)

### Problem
- `loader.py:595` uses `iterrows()` (slow, non-vectorized)
- `production_pipeline.py:121, 130` loops symbol-by-symbol

### Fix

#### loader.py (line 595)
Replace `iterrows()` with vectorized operation:

```python
# BEFORE:
for idx, row in df.iterrows():
    # ... process row

# AFTER (vectorized):
# Use apply() or groupby() instead of iterrows()
df_processed = df.apply(lambda row: process_row_vectorized(row), axis=1)
```

#### production_pipeline.py (lines 121, 130)
Replace symbol loops with groupby:

```python
# BEFORE:
for s in clean_data["index"]["symbol"]:
    clean_data["data"][s] = {...}

# AFTER (vectorized):
grouped = df.groupby('symbol')
clean_data["data"] = {
    sym: {col: group.set_index('timestamp')[col].to_dict() for col in cols}
    for sym, group in grouped
}
```

---

## Implementation Rules (PRODUCTION GRADE)

1. **NO STUBS**: Do not create fake classes or stub implementations
2. **NO FAKE IMPORTS**: Do not import non-existent modules
3. **FAIL FAST**: If a module doesn't exist, remove the dependency or document as Phase 12 future work
4. **VECTORIZED ONLY**: Replace all `iterrows()` and explicit loops with pandas/numpy operations
5. **TEST DRIVEN**: Run tests after each fix; verify 100% PASS

---

## L2 Handoff

**To**: OpenCode (L2 Implementation)  
**Task**: Fix 3 blockers with production-grade code (no stubs)  
**Acceptance Criteria**:
- ✅ Checksum validator wired into runtime
- ✅ Production pipeline imports only existing OMEGA modules
- ✅ No `iterrows()` or explicit symbol loops
- ✅ Smoke import test PASSES
- ✅ All tests PASS (54+ tests)
- ✅ Clean commit (OMEGA-only, no .ly_state, no V21, no temp)

**L3 Re-Audit**: After L2 completion, L3 will re-audit and issue final verdict.

---

**Created by**: Ly (L1 Orchestrator)  
**Date**: 2026-05-13 03:54 GMT+7  
**Status**: READY FOR L2 IMPLEMENTATION (PRODUCTION GRADE)
