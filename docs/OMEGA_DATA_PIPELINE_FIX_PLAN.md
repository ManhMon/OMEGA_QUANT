# OMEGA Data Pipeline - Fix Plan
**Date**: 2026-05-13  
**Status**: PENDING L2 IMPLEMENTATION  
**Gate Status**: `[NEEDS_FIX]` (from L3 Audit)  
**L3 Session**: `L3-Audit-Role21-20260513T031231+0700`  
**L3 Report**: `OMEGA_QUANT/docs/OMEGA_DATA_PIPELINE_AUDIT_20260513.md`

---

## Overview

L3 Audit identified **6 blockers** (1 CRITICAL, 3 HIGH, 2 MEDIUM) preventing production readiness. This plan breaks down fixes into discrete L2 tasks.

**Target**: All blockers fixed, tests 100% PASS, L3 re-audit APPROVED.

---

## Blocker 1: CRITICAL - PIT Wall-Clock Timestamps

**Severity**: CRITICAL  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/loader.py`  
**Lines**: 674, 710

### Problem
- `loader.py:674` uses `datetime.now()` for `ingestion_timestamp`
- `loader.py:710` uses `datetime.now().isoformat()` for sidecar `created_at`
- **Risk**: Metadata depends on wall-clock, not explicit `as_of_time` → breaks reproducibility

### Fix
Replace `datetime.now()` with `as_of_time` parameter:

```python
# BEFORE (line 674):
df['ingestion_timestamp'] = datetime.now()

# AFTER:
df['ingestion_timestamp'] = as_of_time

# BEFORE (line 710):
metadata['created_at'] = datetime.now().isoformat()

# AFTER:
metadata['created_at'] = as_of_time.isoformat()
```

### Verification
- ✅ No `datetime.now()` in hot paths
- ✅ All timestamps use `as_of_time` parameter
- ✅ Tests pass with deterministic timestamps

---

## Blocker 2: HIGH - Vectorization Requirement Violated

**Severity**: HIGH  
**Files**: 
- `OMEGA_QUANT/packages/data/src/omega/data/pipeline/production_pipeline.py` (lines 28-39, 46-75, 99-109, 125-130)
- `OMEGA_QUANT/packages/data/src/omega/data/loader.py` (lines 326, 595, 626, 738)
- `OMEGA_QUANT/packages/data/src/omega/data/sanitizer.py` (lines 196-197, 308-319, 338-363, 381-408)
- `OMEGA_QUANT/packages/data/src/omega/data/validator.py` (lines 195, 283, 294, 116)
- `OMEGA_QUANT/packages/data/src/omega/data/corporate_action.py` (lines 173-222)

### Problem
- Spec requires **100% vectorized** (no loops)
- Current implementation has many `for` loops in hot paths
- **Risk**: Throughput bottleneck, doesn't scale to 1533 symbols

### Fix Strategy

#### production_pipeline.py
```python
# BEFORE (lines 28-39):
for sym in df[symbol_col].unique():
    for col in ['open', 'high', 'low', 'close']:
        # ... loop logic

# AFTER (vectorized):
df_grouped = df.groupby(symbol_col)[['open', 'high', 'low', 'close']].apply(
    lambda x: x.fillna(method='ffill').fillna(method='bfill')
)
```

#### loader.py (lines 326, 595, 626, 738)
Replace row iteration with `apply()` or `groupby()`:
```python
# BEFORE:
for idx, row in df.iterrows():
    # ... process row

# AFTER:
df = df.apply(lambda row: process_row_vectorized(row), axis=1)
```

#### sanitizer.py (lines 196-197, 308-319, 338-363, 381-408)
Use pandas `groupby()` + `transform()`:
```python
# BEFORE:
for sym in df['symbol'].unique():
    for col in ['open', 'high', 'low', 'close']:
        # ... per-symbol, per-column logic

# AFTER:
df[['open', 'high', 'low', 'close']] = df.groupby('symbol')[['open', 'high', 'low', 'close']].transform(
    lambda x: x.clip(lower=x.quantile(0.01), upper=x.quantile(0.99))
)
```

#### validator.py (lines 195, 283, 294, 116)
Use numpy vectorized checks:
```python
# BEFORE:
for row in rows:
    if row['close'] < 0:
        issues.append(...)

# AFTER:
negative_mask = df['close'] < 0
issues = [ValidationIssue(...) for idx in df[negative_mask].index]
```

#### corporate_action.py (lines 173-222)
Use pandas merge + groupby:
```python
# BEFORE:
for action in actions:
    for time in times:
        # ... apply adjustment

# AFTER:
df_merged = df.merge(actions_df, on=['symbol', 'date'], how='left')
df['adjusted_close'] = df.groupby('symbol')['close'].transform(
    lambda x: x * df_merged['adjustment_factor']
)
```

### Verification
- ✅ `rg "for " OMEGA_QUANT/packages/data/src/omega/data/` returns 0 matches in hot paths
- ✅ All operations use pandas/numpy vectorized methods
- ✅ Performance test: 1533 symbols × 252 days < 5s

---

## Blocker 3: HIGH - Sanitizer PIT Contract Break

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/packages/data/src/omega/data/sanitizer.py`  
**Lines**: 204

### Problem
- `sanitizer.py:204` calls `_enforce_pit_safety(df_clean, date_col)` without `as_of_time`
- `_enforce_pit_safety()` requires `as_of_time` parameter and raises if missing
- **Risk**: 3 tests fail (`test_clean_ohlcv_legacy`, `test_fit_apply_pattern`, `test_forward_fill_limit`)

### Fix
Add `as_of_time` parameter to method signature and call:

```python
# BEFORE (line 204):
self._enforce_pit_safety(df_clean, date_col)

# AFTER:
self._enforce_pit_safety(df_clean, date_col, as_of_time=self.as_of_time)

# Update method signature:
def _enforce_pit_safety(self, df: pd.DataFrame, date_col: str, as_of_time: datetime = None) -> pd.DataFrame:
    if as_of_time is None:
        raise ValueError("as_of_time is mandatory for PIT compliance")
    # ... rest of logic
```

### Verification
- ✅ `test_clean_ohlcv_legacy` PASS
- ✅ `test_fit_apply_pattern` PASS
- ✅ `test_forward_fill_limit` PASS

---

## Blocker 4: HIGH - Production Pipeline Tests Missing

**Severity**: HIGH  
**Files**: `OMEGA_QUANT/tests/phase2/test_production_pipeline.py` (NEW)

### Problem
- No tests for `ProductionDataPipeline` class
- End-to-end logic (corp action, neutralization, report) unverified
- **Risk**: Production bugs undetected

### Fix
Create comprehensive test suite:

```python
# OMEGA_QUANT/tests/phase2/test_production_pipeline.py

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime
from omega.data.pipeline.production_pipeline import ProductionDataPipeline

class TestProductionDataPipeline:
    
    def test_pipeline_initialization(self):
        """Test pipeline initializes with mandatory as_of_time."""
        with pytest.raises(ValueError, match="as_of_time is mandatory"):
            ProductionDataPipeline(
                input_path="data/test.parquet",
                output_path="data/output.parquet",
                as_of_time=None
            )
    
    def test_corporate_actions_applied(self):
        """Test corporate actions are applied with ex_date filter."""
        # Create test data with dividend action
        df = pd.DataFrame({
            'symbol': ['VNM', 'VNM'],
            'timestamp': pd.to_datetime(['2026-01-10', '2026-01-15']),
            'close': [100.0, 100.0],
            'volume': [1000, 1000]
        })
        
        pipeline = ProductionDataPipeline(
            input_path="data/test.parquet",
            output_path="data/output.parquet",
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        # Verify corporate actions applied
        assert len(pipeline.pipeline_stats) > 0
    
    def test_neutralization_mapping_preserved(self):
        """Test neutralization output preserves date dimension."""
        # Verify (symbol, date) composite key maintained
        pass
    
    def test_quality_report_generated(self):
        """Test L7 quality report is generated."""
        # Verify report contains pipeline_stats, validation_issues, data_quality
        pass
    
    def test_output_persisted(self):
        """Test L8 output is saved to parquet + JSON report."""
        # Verify output files exist and are readable
        pass
```

### Verification
- ✅ 5+ tests PASS
- ✅ Coverage includes corp action, neutralization, report persistence

---

## Blocker 5: MEDIUM - Checksum Validator Not Wired

**Severity**: MEDIUM  
**Files**: 
- `OMEGA_QUANT/packages/data/src/omega/data/validator.py` (line 309)
- `OMEGA_QUANT/packages/data/src/omega/data/loader.py`

### Problem
- `validator.py:309` defines `_validate_checksum_from_sidecar()` but it's never called
- Checksum validation only runs in tests, not production
- **Risk**: Data integrity checks skipped in runtime

### Fix
Wire checksum validation into runtime flow:

```python
# In validator.py, update _validate_rows():
def _validate_rows(self, rows: List[Dict[str, Any]], symbol: str, parquet_path: Path = None) -> List[ValidationIssue]:
    issues = []
    
    # ... existing checks ...
    
    # NEW: Add checksum validation if parquet_path provided
    if parquet_path and self.validate_provenance:
        checksum_issues = self._validate_checksum_from_sidecar(parquet_path, symbol)
        issues.extend(checksum_issues)
    
    return issues

# In loader.py, pass parquet_path to validator:
validation_issues = self.validator.validate(df, symbol_col='symbol', parquet_path=cache_path)
```

### Verification
- ✅ Checksum validation called in production flow
- ✅ Tests verify checksum validation triggers on sidecar mismatch

---

## Blocker 6: MEDIUM - Test Suite Reliability

**Severity**: MEDIUM  
**Files**: 
- `OMEGA_QUANT/tests/phase2/test_loader.py`
- `OMEGA_QUANT/tests/phase2/test_loader_corporate_actions.py`
- `OMEGA_QUANT/packages/data/tests/test_sanitizer.py`

### Problem
- 24 failed, 32 passed tests
- Failures: vnstock external dependency, temp-dir permissions, sanitizer PIT contract
- **Risk**: CI signal noisy, gate confidence reduced

### Fix

#### 1. Mock vnstock dependency
```python
# Use pytest-mock to mock VnstockVCIDataSource
@pytest.fixture
def mock_vnstock_source(mocker):
    mock = mocker.MagicMock()
    mock.fetch_price_data.return_value = [
        {'symbol': 'VNM', 'timestamp': 1704067200, 'open': 100, 'high': 101, 'low': 99, 'close': 100.5, 'volume': 1000}
    ]
    return mock
```

#### 2. Use workspace-local cache instead of OS temp
```python
# BEFORE:
with tempfile.TemporaryDirectory() as tmpdir:
    loader = DataLoader(cache_dir=tmpdir)

# AFTER:
cache_dir = Path(".ly_state/test_cache/loader_tests")
cache_dir.mkdir(parents=True, exist_ok=True)
loader = DataLoader(cache_dir=str(cache_dir))
```

#### 3. Fix sanitizer PIT contract
```python
# Pass as_of_time to sanitizer.clean_ohlcv()
sanitizer = DataSanitizer()
cleaned, stats = sanitizer.clean_ohlcv(
    data,
    as_of_time=datetime(2026, 5, 1, 10, 0, 0)
)
```

### Verification
- ✅ All 32+ tests PASS
- ✅ No external dependencies (vnstock mocked)
- ✅ No temp-dir permission errors
- ✅ Sanitizer PIT contract satisfied

---

## Implementation Order (L2 Priority)

| Priority | Blocker | Est. Time | Dependencies |
|:---:|:---|:---:|:---|
| 1 | Blocker 3 (Sanitizer Contract) | 30min | None |
| 2 | Blocker 1 (PIT Wall-Clock) | 1h | Blocker 3 |
| 3 | Blocker 6 (Test Stability) | 2h | Blocker 1, 3 |
| 4 | Blocker 2 (Vectorization) | 4h | Blocker 1, 3, 6 |
| 5 | Blocker 5 (Checksum Wiring) | 1h | Blocker 4 |
| 6 | Blocker 4 (Production Tests) | 2h | Blocker 1-3 |

**Total Est. Time**: ~10 hours  
**Target Completion**: 2026-05-13 (next day)

---

## L2 Handoff

**To**: OpenCode (L2 Implementation)  
**Task**: Fix all 6 blockers in priority order  
**Acceptance Criteria**:
- ✅ All blockers fixed per spec above
- ✅ 100% test PASS (50+ tests)
- ✅ No `datetime.now()` in hot paths
- ✅ No loops in vectorized sections
- ✅ Sanitizer PIT contract satisfied
- ✅ Production pipeline tests comprehensive
- ✅ Checksum validator wired into runtime

**L3 Re-Audit**: After L2 completion, L3 will re-audit and issue final verdict.

---

**Created by**: Ly (L1 Orchestrator)  
**Date**: 2026-05-13 03:19 GMT+7  
**Status**: READY FOR L2 IMPLEMENTATION
