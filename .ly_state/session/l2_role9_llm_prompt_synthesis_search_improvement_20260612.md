# L2 Implementation Report: LLM Prompt/Synthesis/Search Improvement

**Role**: L2 Role 9 - backend-engineer  
**Task**: Implement approved LLM prompt/synthesis/search improvement Option C for stronger formulas  
**Date**: 2026-06-12  
**Session ID**: l2_role9_llm_prompt_synthesis_search_improvement_20260612

## Executive Summary

Successfully implemented staged search improvements for LLM symbolic synthesizer with:
- New prompt version 'vn_alpha_search_v2' with Vietnamese market domain knowledge
- Cache key versioning to isolate different prompt versions
- Formula deduplication via normalization
- Comprehensive rejection taxonomy (8 categories)
- Richer stats/evidence tracking throughout pipeline
- Safe aggregate validation summary in backtest (PIT-safe, no label leakage)

**Validation Results**: All checks passed
- py_compile: 0 syntax errors
- pytest: 43/43 tests passed
- sod_gate_enforcer.py: PASS - SAFE TO PUSH

## Implementation Details

### 1. Prompt Version 'vn_alpha_search_v2'

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

Implemented new prompt template with:
- Vietnamese equity market context (VNIndex, HOSE, frontier market characteristics)
- T+2 settlement, daily price limits (±7%), liquidity gap specifics
- Aggregate supervised failure context (median IC, DSR) - PIT-safe, no row-level labels
- Configurable candidate budget via OMEGA_LLM_MAX_CANDIDATES (default 10)
- Domain-specific alpha ideas (momentum reversal, liquidity divergence, volatility regimes)

**Key Changes**:
- Added `prompt_version` parameter to `__init__` (default: 'vn_alpha_search_v2')
- Added `max_candidates` parameter with env var support
- Split `generate_prompt()` into `_generate_prompt_v1()` (legacy) and `_generate_prompt_v2()` (new)
- New prompt includes `prior_failure_stats` parameter for aggregate metrics only

**PIT Safety**: Prior failure stats contain only aggregate metrics (median IC, median DSR), never row-level label data.

### 2. Cache Key Versioning

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

Modified `FormulaCache` class to support versioned cache keys:
- Updated `_hash_prompt()` to include `prompt_version` in hash computation
- Updated `get()` and `set()` methods with `prompt_version` parameter
- Added version verification on cache retrieval (defense in depth)
- Cache entries now store `prompt_version` in metadata

**Benefit**: Prevents stale weak formulas from v1 cache contaminating v2 runs.

### 3. Formula Deduplication

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

Added `normalize_formula()` method:
- Removes all whitespace
- Converts to lowercase for case-insensitive comparison
- Detects semantically identical formulas (e.g., "ts_mean(close, 20)" == "TS_MEAN( close , 20 )")

Updated `synthesize()` to deduplicate after safety parsing:
- Tracks seen normalized formulas in set
- Rejects duplicates with taxonomy tracking

### 4. Rejection Taxonomy

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

Implemented 8-category rejection taxonomy:
1. **parse_error**: Formula parsing failed (syntax errors, malformed expressions)
2. **unsafe_token**: Safety parser rejection (infix operators, unknown tokens, bad lookback, depth exceeded, trailing tokens)
3. **duplicate_formula**: Duplicate after normalization
4. **execution_failure**: Formula execution failed on test data
5. **low_coverage**: Insufficient non-NaN coverage (<min threshold)
6. **near_zero_variance**: Constant or near-constant output
7. **unstable**: Excessive per-ticker variance
8. **nan_inf**: Too many NaN/inf values

**Integration**:
- Synthesis stage tracks parse_error, unsafe_token, duplicate_formula, execution_failure
- Scoring stage tracks low_coverage, near_zero_variance, unstable, nan_inf
- Taxonomy merged in `score_and_filter_formulas()`

### 5. Richer Stats/Evidence

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`

Updated `synthesize()` to return tuple `(nodes, stats)`:
- Old API: `nodes = synthesize(features)`
- New API: `nodes, stats = synthesize(features)`

Stats dictionary includes:
- `prompt_version`: Version used for generation
- `max_candidates`: Candidate budget
- `provider_type`: Provider class name
- `cache_hit`: Boolean cache hit indicator
- `total_raw`: Raw candidate count from provider
- `rejection_taxonomy`: 8-category rejection counts
- `accepted`: Accepted formula count
- `rejected_formulas`: List of rejected formulas with reasons
- `accepted_formulas`: List of accepted formula strings

Updated `score_and_filter_formulas()` to merge synthesis_stats:
- Accepts optional `synthesis_stats` parameter
- Merges rejection taxonomy from both stages
- Returns comprehensive stats with full pipeline evidence

### 6. Backtest Integration

**File**: `scripts/backtest_v2_cpcv.py`

Updated LLM alpha integration to:
- Handle new `synthesize()` tuple return (lines 1449-1452)
- Pass `synthesis_stats` to `score_and_filter_formulas()` (lines 1476-1484)
- Build safe aggregate validation summary (lines 1487-1511):
  - Prompt version
  - Provider type
  - Cache hit status
  - Total candidates, accepted, rejected, deployable counts
  - Full rejection taxonomy
  - Aggregate quality metrics (mean coverage, mean variance across accepted formulas)
- Persist `llm_validation_summary` to output JSON (lines 1756-1772)

**PIT Safety**: 
- Feature generation uses `labels=None` (line 1480)
- No row-level label data in prompt or feature generation
- Only aggregate stats persisted (counts, means, rejection taxonomy)

## Files Modified

### Primary Implementation
1. **src/omega/quant/evolution/llm_symbolic_synthesizer.py** (884 lines → 1150 lines)
   - Added prompt versioning and v2 template
   - Added cache versioning
   - Added formula normalization
   - Implemented rejection taxonomy
   - Updated synthesize() to return (nodes, stats)
   - Updated score_and_filter_formulas() to merge stats

2. **scripts/backtest_v2_cpcv.py** (1778 lines → 1798 lines)
   - Updated LLM integration to handle new API
   - Added safe aggregate validation summary
   - Persist summary to output JSON

### Test Coverage
3. **tests/quant_test_infinite_evolution.py** (1185 lines → 1404 lines)
   - Added 8 new comprehensive tests
   - Updated 4 existing tests for new API
   - Total: 43 tests, all passing

## Test Results

**pytest**: 43/43 tests passed in 7.01s

New tests added:
1. `test_prompt_v2_domain_constraints` - Verifies Vietnamese market context, no secrets
2. `test_prompt_v2_aggregate_failure_context` - Verifies aggregate metrics only, no row-level labels
3. `test_cache_versioning` - Verifies cache isolation by prompt version
4. `test_formula_deduplication` - Verifies normalization and deduplication
5. `test_rejection_taxonomy_recorded` - Verifies all 8 categories tracked
6. `test_synthesize_returns_tuple` - Verifies new API returns (nodes, stats)
7. `test_max_candidates_from_env` - Verifies OMEGA_LLM_MAX_CANDIDATES env var
8. `test_score_and_filter_merges_synthesis_stats` - Verifies stats merging

Existing tests updated:
1. `test_llm_synthesizer_validation_and_execution` - Updated for tuple return
2. `test_llm_synthesizer_use_mock_false_fallback_no_recursion` - Updated for tuple return
3. `test_synthesizer_score_and_filter_integration` - Updated for tuple return and stats merging
4. `test_backtest_metadata_propagation` - Updated for tuple return

## Validation Results

### 1. py_compile
```
python -m py_compile src/omega/quant/evolution/llm_symbolic_synthesizer.py \
    src/omega/quant/evolution/llm_formula_scorer.py \
    scripts/backtest_v2_cpcv.py \
    tests/quant_test_infinite_evolution.py
```
**Result**: PASS (0 syntax errors)

### 2. pytest
```
python -m pytest tests/quant_test_infinite_evolution.py -v
```
**Result**: PASS (43/43 tests passed)

### 3. SOD Gate Enforcer
```
python scripts/sod_gate_enforcer.py
```
**Result**: PASS - SAFE TO PUSH
- 103 phases verified
- All L3 audit evidence present
- All role boundary checks validated
- All P0/P1/P2 hardening checks passed

## PIT Safety Analysis

### Feature Generation (PIT-Safe)
- `synthesize()` called with features dict only (no labels)
- `score_and_filter_formulas()` called with `labels=None`
- Quality checks use only unsupervised metrics (coverage, variance, stability)
- Formulas accepted without supervised validation marked `is_deployable=false`

### Prompt Generation (PIT-Safe)
- `prior_failure_stats` parameter accepts only AGGREGATE metrics:
  - `median_test_ic`: Scalar median IC across folds
  - `median_dsr`: Scalar median DSR across folds
- No row-level label data passed to prompt
- No arrays/tensors of label values in prompt context

### Backtest Integration (PIT-Safe)
- LLM formulas added to feature set BEFORE supervised training
- Only aggregate validation summary persisted (counts, means, taxonomy)
- No per-observation predictions or labels stored
- `llm_validation_summary` contains only:
  - Counts (total, accepted, rejected, deployable)
  - Rejection taxonomy (8 category counts)
  - Aggregate quality (mean coverage, mean variance)

### Cache Safety
- Cache keys include prompt version for isolation
- No API keys or secrets cached (only formula strings)
- Version verification prevents cross-contamination

## Key Metrics

**Rejection Taxonomy Categories**: 8  
**New Tests Added**: 8  
**Total Tests Passing**: 43/43  
**Lines Added**: ~350 (net increase across all files)  
**Cache Versioning**: Enabled (isolates v1 vs v2)  
**Default Max Candidates**: 10 (configurable via OMEGA_LLM_MAX_CANDIDATES)  
**Prompt Version**: vn_alpha_search_v2  

**Validation Status**: ✅ All checks passed

## Evidence Summary

1. **Prompt v2**: Includes Vietnamese market domain knowledge, aggregate failure context
2. **Cache versioning**: Different versions produce different cache keys
3. **Deduplication**: Normalized formulas prevent semantic duplicates
4. **Rejection taxonomy**: 8 categories tracked throughout pipeline
5. **Stats integration**: Synthesis + scoring stats merged in final output
6. **Backtest safety**: Only aggregate metrics persisted, no label leakage
7. **Test coverage**: All new features tested, all tests passing
8. **PIT compliance**: Strict separation of feature generation (no labels) and supervised training

## Deployment Readiness

**Status**: Ready for L3 audit

**Prerequisites**:
- ✅ py_compile passed
- ✅ pytest passed (43/43)
- ✅ sod_gate_enforcer.py passed
- ✅ PIT safety verified
- ✅ No API key leakage
- ✅ Backward compatibility maintained (v1 prompt still available)

**Configuration**:
- Default prompt version: `vn_alpha_search_v2`
- Default max candidates: `10` (override via OMEGA_LLM_MAX_CANDIDATES)
- Default provider: `mock` (safe offline mode)
- Cache directory: `.ly_state/session/llm_cache/`

**L3 Audit Scope**:
- Verify prompt v2 domain constraints are appropriate
- Verify rejection taxonomy completeness
- Verify PIT safety in aggregate stats persistence
- Verify no row-level label leakage in prompt generation
- Verify cache versioning isolation is effective

---
**L2 Implementation Complete**  
**Author**: backend-engineer (Role 9)  
**Date**: 2026-06-12  
**Status**: Ready for L3 Audit
