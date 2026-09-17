# L2 Implementation Report: Safe Real-LLM Provider Interface
**Role**: 9 backend-engineer - OpenCode L2 Implementation  
**Date**: 2026-06-12  
**Session**: l2_role9_llm_provider_safe_interface_20260612

## Executive Summary

Successfully implemented a safe, production-ready LLM provider interface for `LLMSymbolicSynthesizer` with comprehensive security controls, deterministic caching, and strict formula safety validation. All requirements met, 20/20 tests passing, SOD gate enforcer verified.

## Implementation Overview

### 1. Provider Abstraction Layer
- **MockProvider**: Offline/testing provider (default)
- **OpenAICompatibleProvider**: Real LLM API provider with security controls
- Abstract `LLMProvider` base class for extensibility

### 2. Security Controls
- API keys from environment variables only (`OMEGA_LLM_API_KEY`)
- Keys never logged or stored in cache
- Default provider: `mock` (safe offline mode)
- Real provider disabled unless explicitly enabled via env

### 3. Deterministic Cache
- On-disk cache: `.ly_state/session/llm_cache/`
- SHA256 prompt hashing for cache keys
- Never caches secrets (only formulas)
- Persistent across sessions

### 4. Formula Safety Parser
- Only prefix syntax allowed (rejects infix)
- Allowed operators: unary, binary, time-series
- Lookback range: [2, 60]
- Max depth: 5
- Max formulas: 10
- Rejects unknown terminals/operators

### 5. Grouped Execution (PIT-Safe)
- Mandatory per-ticker grouped execution preserved
- Time-series operators never cross ticker boundaries
- Existing `execute_node_grouped()` unchanged

## Files Modified

### 1. src/omega/quant/evolution/llm_symbolic_synthesizer.py
**Lines**: 1-450 (complete rewrite of core logic)
**Changes**:
- Added `LLMProvider`, `MockProvider`, `OpenAICompatibleProvider` classes
- Added `FormulaCache` with SHA256 hashing
- Added `FormulaSafetyParser` with strict validation
- Updated `LLMSymbolicSynthesizer.__init__()` to use provider system
- Updated `synthesize()` to use provider + cache + safety parser
- Preserved all existing methods: `tokenize()`, `parse_formula()`, `validate_expression()`, `execute_node_grouped()`

### 2. src/omega/quant/evolution/unified_feature_adapter.py
**Lines**: 31-42, 173
**Changes**:
- Added `llm_provider` parameter to `__init__()`
- Updated LLM synthesizer instantiation to pass provider parameter

### 3. scripts/backtest_v2_cpcv.py
**Lines**: 1310-1320, 1437
**Changes**:
- Added `--llm-provider` CLI flag (choices: mock, openai-compatible)
- Updated synthesizer instantiation to use `provider` parameter
- Added logging for provider selection

### 4. tests/quant_test_infinite_evolution.py
**Lines**: 50, 108, 132, 192, 242, 265-544
**Changes**:
- Updated all existing tests to use `provider="mock"` API
- Added 9 new security tests:
  - `test_llm_provider_disabled_without_env`
  - `test_formula_safety_parser_rejects_infix`
  - `test_formula_safety_parser_rejects_unknown_operator`
  - `test_formula_safety_parser_rejects_unknown_terminal`
  - `test_formula_safety_parser_rejects_bad_lookback`
  - `test_formula_safety_parser_accepts_valid`
  - `test_formula_cache_deterministic`
  - `test_secrets_not_in_cache`
  - `test_grouped_execution_mandatory`

## Security Controls Implemented

### Secret Management
- API key from `OMEGA_LLM_API_KEY` env var only
- Never logged (no API key in logs or output)
- Never cached (cache stores formulas only)
- Warning if api_key passed directly (deprecated)

### Provider Safety
- Default: `mock` (offline, safe)
- Real provider requires explicit env config:
  - `OMEGA_LLM_PROVIDER=openai-compatible`
  - `OMEGA_LLM_API_KEY=<key>`
  - `OMEGA_LLM_MODEL=<model>` (optional)
  - `OMEGA_LLM_BASE_URL=<url>` (optional)
- Fallback to mock if env incomplete

### Formula Safety
- Rejects infix operators (e.g., `close + volume`)
- Rejects unknown operators/terminals
- Enforces lookback range [2, 60]
- Enforces max depth 5
- Caps max formulas at 10
- Validates before caching

### Cache Safety
- Deterministic: same prompt = same cache key
- Only caches formulas (no secrets)
- SHA256 hashing prevents collisions
- Persistent across sessions

## Testing Results

### Test Execution
```
pytest tests/quant_test_infinite_evolution.py -q
....................                                                     [100%]
20 passed, 5 warnings in 7.68s
```

### Test Coverage
- **Existing tests**: 11 tests updated to new API (all passing)
- **New security tests**: 9 tests added (all passing)
- **Total**: 20 tests passing

### Key Test Scenarios
1. Default mock behavior works
2. Provider fallback without env vars (no recursion)
3. Safety parser rejects invalid formulas
4. Cache is deterministic
5. Secrets not in cache files
6. Grouped execution still mandatory

## Validation Results

### 1. Syntax Check (py_compile)
All 4 scoped files compiled successfully:
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py` ✓
- `src/omega/quant/evolution/unified_feature_adapter.py` ✓
- `scripts/backtest_v2_cpcv.py` ✓
- `tests/quant_test_infinite_evolution.py` ✓

### 2. Test Execution
```
pytest tests/quant_test_infinite_evolution.py -q
20 passed
```

### 3. SOD Gate Enforcer
```
[PASS] SOD GATE CHECK PASSED
   Verified 98 phases
   All L3 audit evidence present
   All role boundary checks validated
[PASS] SAFE TO PUSH
```

## Breaking Changes

### API Changes
**Old API**:
```python
LLMSymbolicSynthesizer(use_mock=True, api_key="...")
```

**New API**:
```python
LLMSymbolicSynthesizer(provider="mock")  # or "openai-compatible"
```

**Migration**: Update all instantiations to use `provider` parameter. The `use_mock` parameter is deprecated but still accepted for backward compatibility.

### Environment Variables
**New required for real provider**:
- `OMEGA_LLM_PROVIDER=openai-compatible`
- `OMEGA_LLM_API_KEY=<key>`

**Optional**:
- `OMEGA_LLM_MODEL=<model>` (default: gpt-4)
- `OMEGA_LLM_BASE_URL=<url>` (default: https://api.openai.com/v1)

### Backtest CLI
**New flag**:
```bash
python scripts/backtest_v2_cpcv.py --use-llm-alphas --llm-provider mock
python scripts/backtest_v2_cpcv.py --use-llm-alphas --llm-provider openai-compatible
```

Default: `--llm-provider mock` (safe offline)

## Known Limitations

1. **OpenAI-compatible only**: Currently only supports OpenAI-compatible APIs. Anthropic Claude, Google Gemini, etc. require additional provider implementations.

2. **No streaming**: Provider uses synchronous requests, no streaming support.

3. **Cache invalidation**: No automatic cache expiry. Manual deletion of `.ly_state/session/llm_cache/` required to clear cache.

4. **Formula parsing**: Only supports prefix syntax. Complex nested formulas may hit depth limit.

5. **Network timeouts**: 30-second timeout for API calls. No retry logic.

## Recommendations for L3 Audit

### Critical Items
1. **Secret leakage**: Verify API keys never appear in logs, cache files, or error messages
2. **Formula injection**: Verify safety parser rejects malicious formulas
3. **PIT safety**: Verify grouped execution still works correctly
4. **Fallback behavior**: Verify graceful degradation when provider unavailable

### Security Checks
1. Test with real OpenAI API key (if available)
2. Verify cache files don't contain secrets
3. Test formula parser with adversarial inputs
4. Verify env var handling (missing vars, empty vars, invalid values)

### Performance Checks
1. Cache hit rate in production workloads
2. Formula validation overhead
3. Network latency impact on backtest runtime

### Code Quality
1. Error handling completeness
2. Logging verbosity (debug vs info vs warning)
3. Documentation accuracy

## Conclusion

All requirements successfully implemented:
- ✓ Provider abstraction (mock + openai-compatible)
- ✓ API key from env only, never logged
- ✓ Deterministic cache with prompt hashing
- ✓ Strict formula safety parser
- ✓ Backtest CLI safe opt-in flags
- ✓ Grouped execution preserved
- ✓ Comprehensive tests (20/20 passing)
- ✓ All validation passed (py_compile, pytest, SOD gate)

**Status**: Ready for L3 independent audit.

---
**L2 Implementation Complete**  
**Backend Engineer (Role 9)**  
**2026-06-12**
