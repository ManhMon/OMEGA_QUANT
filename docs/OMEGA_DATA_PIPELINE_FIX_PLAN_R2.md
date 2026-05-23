# OMEGA Data Pipeline - Fix Plan Round 2
**Date**: 2026-05-13  
**Status**: PENDING L2 IMPLEMENTATION  
**Previous Audit**: L3 re-audit `role21-reaudit-20260513-034602` verdict `[NEEDS_FIX]`  
**Commit**: `8b21e0e`

---

## Overview

L3 re-audit identified **3 remaining blockers** preventing production readiness. This plan addresses the gaps from Round 1 fixes.

**Target**: All blockers fixed, L3 re-audit APPROVED.

---

## Blocker 1: HIGH - Checksum Validator Not Wired to Runtime

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/validator.py`, `OMEGA_QUANT/packages/data/src/omega/data/loader.py`

### Problem
- `DataValidator._validate_checksum_from_sidecar()` exists at `validator.py:309` but is never called
- `validate_rows()` at line 56 only calls `_validate_provenance_metadata()`, skipping checksum validation
- Checksum integrity checks only run in tests, not production runtime

### Fix
Wire checksum validation into `validate_rows()`:

```python
# In validator.py, update validate_rows() method:
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

    # Validate provenance metadata if enabled
    if self.validate_provenance:
        issues.extend(self._validate_provenance_metadata(sorted_rows, sym))
        
        # NEW: Add checksum validation if parquet_path provided
        if parquet_path:
            issues.extend(self._validate_checksum_from_sidecar(parquet_path, sym))

    return issues
```

Update loader to pass `parquet_path`:
```python
# In loader.py, update validation call:
validation_issues = self.validator.validate_rows(
    df.to_dict('records'), 
    symbol=ticker,
    parquet_path=cache_path  # NEW: pass cache path for checksum validation
)
```

### Verification
- ✅ Checksum validation called in production flow
- ✅ Tests verify checksum validation triggers on sidecar mismatch

---

## Blocker 2: HIGH - Production Pipeline Import Path Broken

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/pipeline/production_pipeline.py`

### Problem
- Line 10: `from src.v21_system.layer_01_core_intelligence.data_validator import DataValidator, ValidationIssue`
- Smoke import fails: `ModuleNotFoundError: No module named 'src.v21_system.layer_01_core_intelligence.data_validator'`
- Production pipeline module is not executable in OMEGA repo layout

### Fix
Update import to use OMEGA canonical path:

```python
# BEFORE (line 10):
from src.v21_system.layer_01_core_intelligence.data_validator import DataValidator, ValidationIssue

# AFTER:
from omega.data.validator import DataValidator, ValidationIssue
```

### Verification
- ✅ `python -c "import omega.data.pipeline.production_pipeline"` succeeds
- ✅ No `ModuleNotFoundError` in smoke test

---

## Blocker 3: MEDIUM - Vectorization Not Complete

**Severity**: MEDIUM  
**Files**: 
- `OMEGA_QUANT/packages/data/src/omega/data/loader.py` (line 595)
- `OMEGA_QUANT/packages/data/src/omega/data/pipeline/production_pipeline.py` (lines 121, 130)

### Problem
- `loader.py:595` uses `iterrows()` in `_df_to_clean_dataframe()`
- `production_pipeline.py:121, 130` loops symbol-by-symbol for clean_data/reshape

### Fix

#### loader.py (line 595)
```python
# BEFORE:
for idx, row in df.iterrows():
    # ... process row

# AFTER (vectorized):
df_dict = df.to_dict('records')  # Convert once, no row iteration
```

#### production_pipeline.py (lines 121, 130)
```python
# BEFORE:
for s in clean_data["index"]["symbol"]:
    clean_data["data"][s] = {c: df[df['symbol']==s].set_index('timestamp')[c].to_dict() for c in ['open','high','low','close','volume']}

# AFTER (vectorized):
# Use groupby + apply for parallel symbol processing
grouped = df.groupby('symbol')
clean_data["data"] = {
    sym: {col: group.set_index('timestamp')[col].to_dict() for col in ['open','high','low','close','volume']}
    for sym, group in grouped
}
```

### Verification
- ✅ No `iterrows()` in hot paths
- ✅ No explicit symbol loops in production pipeline
- ✅ Performance test: 1533 symbols × 252 days < 5s

---

## Implementation Order (L2 Priority)

| Priority | Blocker | Est. Time | Dependencies |
|:---:|:---|:---:|:---|
| 1 | Blocker 2 (Import Path) | 15min | None |
| 2 | Blocker 1 (Checksum Wiring) | 30min | Blocker 2 |
| 3 | Blocker 3 (Vectorization) | 1h | Blocker 1, 2 |

**Total Est. Time**: ~2 hours  
**Target Completion**: 2026-05-13 (same day)

---

## L2 Handoff

**To**: OpenCode (L2 Implementation)  
**Task**: Fix 3 remaining blockers in priority order  
**Acceptance Criteria**:
- ✅ Checksum validator wired into runtime validation path
- ✅ Production pipeline import path fixed (OMEGA canonical)
- ✅ No `iterrows()` or explicit symbol loops in hot paths
- ✅ Smoke import test passes
- ✅ All tests PASS

**L3 Re-Audit**: After L2 completion, L3 will re-audit and issue final verdict.

---

**Created by**: Ly (L1 Orchestrator)  
**Date**: 2026-05-13 03:49 GMT+7  
**Status**: READY FOR L2 IMPLEMENTATION (ROUND 2)
