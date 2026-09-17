# L2 Implementation Report: LLM Scoring Real-Provider Smoke Workflow

**Role**: 9 - backend-engineer (OpenCode L2)  
**Date**: 2026-06-12  
**Session**: l2_role9_llm_scoring_real_provider_smoke_20260612  
**Status**: ✅ SUCCESS

---

## Executive Summary

Successfully verified the LLM scoring layer behavior using mock provider (safe mode without API keys). The scoring system correctly:
- Generates candidate formulas via MockProvider
- Filters formulas based on quality metrics (coverage, variance, stability)
- Tracks validation metadata (deployable vs unsupervised_only)
- Logs explicit warnings for non-deployable formulas
- Maintains PIT safety via grouped per-ticker execution
- Prevents secret leakage in output

**Key Finding**: System correctly identifies that formulas scored without supervised validation (no forward returns) are marked as `unsupervised_only` and **NOT production-deployable**, with explicit warnings logged at multiple layers.

---

## Scope

### Files Verified
- `src/omega/quant/evolution/llm_formula_scorer.py` - Formula quality scorer
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py` - LLM synthesis orchestrator
- `src/omega/quant/evolution/unified_feature_adapter.py` - Feature generation pipeline
- `scripts/backtest_v2_cpcv.py` - Backtest entry point (reviewed)
- `tests/quant_test_infinite_evolution.py` - Test suite

### Test Environment
- **Provider**: MockProvider (offline mode, no API keys required)
- **Panel**: Synthetic 2-ticker × 50-date OHLCV panel (100 rows)
- **Scoring Mode**: Unsupervised only (no forward returns/labels)
- **Platform**: Windows PowerShell, Python 3.14

---

## Evidence Collected

### 1. Formula Generation & Scoring

**Source**: `.ly_state/session/llm_scoring_mock_smoke_20260612.json`

```json
{
  "provider": "mock",
  "status": "SUCCESS",
  "formulas": {
    "mock_generated": 3,
    "accepted": 1,
    "rejected": 2
  },
  "validation_metadata": {
    "deployable": 0,
    "unsupervised_only": 1,
    "mode": "unsupervised_only (no labels in feature generation)"
  },
  "secrets_check": "PASS"
}
```

**Analysis**:
- MockProvider generated 3 candidate formulas
- 1 formula accepted: `alpha_llm_0` (100% coverage, variance=1.24e-01)
- 2 formulas rejected:
  - `alpha_llm_1`: Near-zero variance (4.75e-12 < 1.00e-08 threshold)
  - 1 formula failed execution/parsing (filtered before scoring)

### 2. Validation Metadata Tracking

**Observed Logs** (from smoke test execution):

```
INFO - FormulaScorer - Formula ACCEPTED [alpha_llm_0] 
  mode=unsupervised_only deployable=False: 
  coverage=100.00% var=1.24e-01 |IC|=N/A DSR=N/A

WARNING - FormulaScorer - Formula [alpha_llm_0] accepted with 
  UNSUPERVISED checks only - NOT PRODUCTION-DEPLOYABLE 
  without supervised validation

WARNING - LLMSymbolicSynthesizer - Accepted 1 UNSUPERVISED-ONLY 
  formulas - NOT PRODUCTION-DEPLOYABLE without supervised validation. 
  These formulas passed basic quality checks (coverage, variance, 
  stability) but have NOT been validated against forward returns.

WARNING - UnifiedFeatureAdapter - LLM formulas accepted with 
  UNSUPERVISED checks only - NOT PRODUCTION-DEPLOYABLE. 
  Use for research/exploration only, not live trading.
```

**Verification**: ✅ PASS
- Validation metadata correctly identifies formulas as `unsupervised_only`
- `is_deployable=False` for all accepted formulas (no supervised validation)
- Explicit warnings at 3 layers: Scorer → Synthesizer → Adapter
- Clear messaging about production deployment restrictions

### 3. Feature Generation

**Alpha LLM Features Added**: 1 feature
- `alpha_llm_0`: ts_rank or decay_linear-based formula (from mock templates)

**Total Feature Pipeline Output**: 16 features added
- 10 microstructure alphas
- 5 macro alphas
- 1 LLM synthesized alpha

**Feature Groups**:
```json
{
  "alt_features": 0,
  "alt_data": 0,
  "arsenal": 15,
  "llm_synth": 1
}
```

### 4. Security & PIT Safety

**Secrets Check**: ✅ PASS
- No API keys in output JSON
- No secrets in generated panel columns
- Cache files contain only formulas (no auth tokens)

**PIT Safety**: ✅ PASS (verified via code review + tests)
- Grouped execution per ticker (line 689-767 in `llm_symbolic_synthesizer.py`)
- Time-series operators (ts_mean, ts_rank, decay_linear) operate within each ticker's sorted date sequence
- No cross-ticker contamination (verified by `test_execute_node_grouped_no_cross_ticker_contamination`)
- No forward returns used in feature generation stage

### 5. Quality Filtering Behavior

**Rejection Reasons Observed**:
- `alpha_llm_1`: "Near-zero variance: 4.75e-12 < 1.00e-08"
  - Formula produced constant or near-constant output
  - Correctly rejected by unsupervised quality check

**Acceptance Criteria Met** (`alpha_llm_0`):
- Coverage: 100.00% (≥ 70% threshold)
- Variance: 1.24e-01 (≥ 1e-8 threshold)
- NaN/inf ratio: 0% (≤ 30% threshold)
- Per-ticker stability: Within bounds

---

## Compliance Verification

### py_compile
```bash
python -m py_compile src/omega/quant/evolution/*.py scripts/backtest_v2_cpcv.py
```
**Result**: ✅ PASS - All scoped files compile successfully

### pytest
```bash
pytest tests/quant_test_infinite_evolution.py -q
```
**Result**: ✅ PASS - 35/35 tests passed
- Tokenization & parsing tests
- Grouped execution tests (PIT safety)
- Formula safety parser tests
- Formula scorer tests (unsupervised & supervised modes)
- Validation metadata propagation tests
- Cache determinism tests
- Secrets exclusion tests

### SOD Gate Enforcer
```bash
python scripts/sod_gate_enforcer.py
```
**Result**: ✅ PASS
- All 101 phases verified
- All L3 audit evidence present
- All role boundary checks validated
- All P0/P1/P2 hardening checks passed
- Safe to push

---

## Key Findings

### 1. Scoring Layer Correctness
The scoring system correctly implements a **safe-by-default** policy:
- Formulas without supervised validation are marked `unsupervised_only`
- `is_deployable=False` prevents accidental production deployment
- Explicit warnings logged at multiple layers (scorer, synthesizer, adapter)
- Only formulas passing supervised checks (IC, DSR thresholds) are marked deployable

### 2. Mock Provider Fallback
When real provider API key is not set:
- System automatically falls back to MockProvider (lines 486-500 in `llm_symbolic_synthesizer.py`)
- No recursion errors (fixed in prior work)
- Returns 3 hardcoded Vietnamese-market-targeted formulas
- Safe offline operation for testing/CI

### 3. Quality Filtering Effectiveness
The unsupervised quality checks correctly filter out broken formulas:
- Near-zero variance → rejected (prevents constant predictions)
- Excessive NaN → rejected (prevents unstable formulas)
- Low coverage → rejected (prevents sparse predictions)

### 4. Validation Metadata Propagation
The metadata flows correctly through all layers:
- `FormulaScorer` computes and attaches metadata to `FormulaQualityMetrics`
- `LLMSymbolicSynthesizer.score_and_filter_formulas()` aggregates stats
- `UnifiedFeatureAdapter.generate_all()` logs warnings based on metadata
- End-to-end visibility of deployment safety

### 5. Security & PIT Compliance
- **No secrets in output**: Cache and JSON files contain only formulas
- **PIT-safe execution**: Grouped per-ticker, sorted by date, no look-ahead
- **No future data**: Feature generation uses only panel data (no forward returns)

---

## Real Provider Testing Instructions

### Prerequisites
User must configure environment variables locally (never commit to git):

```powershell
# Set provider and API key
$env:OMEGA_LLM_PROVIDER = 'openai-compatible'
$env:OMEGA_LLM_API_KEY = 'your-api-key-here'

# Optional: customize model and endpoint
$env:OMEGA_LLM_MODEL = 'gpt-4'  # default: gpt-4
$env:OMEGA_LLM_BASE_URL = 'https://api.openai.com/v1'  # default
```

### Run Real Provider Smoke Test
```powershell
# Set environment variables (see above)
# Then run the smoke test
$env:PYTHONPATH = "$PWD/src"
python .ly_state/session/llm_scoring_smoke_test_20260612.py
```

### Expected Behavior (Real Provider)
- Provider will call OpenAI-compatible API with configured credentials
- Generated formulas will be Vietnamese-market-specific (per prompt)
- Formulas will be validated via `FormulaSafetyParser` (prefix syntax, depth/lookback caps)
- Valid formulas will be scored (unsupervised only, no labels in feature generation)
- Results will be cached (deterministic, secrets excluded)
- Same warnings about `unsupervised_only` status will be logged

### Security Notes
⚠️ **CRITICAL**:
- Never commit API keys to git
- API keys are read from env vars only (never logged)
- Cache files contain only formulas (no auth tokens)
- Review cache files in `.ly_state/session/llm_cache/` before committing

---

## Recommendations for L3 Audit

### Areas to Verify
1. **Validation Metadata Contract**: Confirm that `is_deployable=False` for `unsupervised_only` formulas is correctly enforced downstream (e.g., in backtest result interpretation, model deployment pipelines)

2. **Warning Visibility**: Verify that warnings about non-deployable formulas are surfaced to end users (not just logged)

3. **Real Provider Behavior**: Test with actual OpenAI API to confirm:
   - Generated formulas are syntactically valid
   - Safety parser rejects malicious/invalid formulas
   - Cache behavior is deterministic
   - No secrets leak into cache or logs

4. **Supervised Scoring Path**: Test scoring with labels (forward returns) to verify:
   - IC and DSR thresholds correctly reject weak formulas
   - `is_deployable=True` only for formulas passing supervised checks
   - Metadata propagates correctly in supervised mode

5. **Integration with Backtest**: Verify that `alpha_llm_*` features generated with `unsupervised_only` validation are handled appropriately in `backtest_v2_cpcv.py`:
   - Are they excluded from production model selection?
   - Are results flagged as research-only?
   - Is there a supervised re-validation step before deployment?

### Edge Cases to Test
- Formula with 100% NaN output (should be rejected)
- Formula with excessive per-ticker variance (should be rejected)
- Formula with weak IC but good unsupervised metrics (should be `unsupervised_only`)
- Formula with strong IC and good metrics (should be `deployable`)

---

## Conclusion

**Status**: ✅ L2 COMPLETE - READY FOR L3 AUDIT

The LLM scoring layer has been verified in mock mode and is functioning correctly:
- Quality filtering works as designed (rejects low-variance/high-NaN formulas)
- Validation metadata correctly tracks deployable vs unsupervised_only status
- Explicit warnings prevent accidental production deployment of unvalidated formulas
- PIT safety maintained via grouped per-ticker execution
- No secrets in output
- All compliance checks passed (py_compile, pytest, SOD gate enforcer)

**Next Steps**:
1. L3 independent audit of this implementation and evidence
2. User testing with real provider (API keys configured locally)
3. Supervised validation testing (with forward returns/labels)
4. Integration testing with full backtest pipeline

**Artifacts**:
- Evidence JSON: `.ly_state/session/llm_scoring_mock_smoke_20260612.json`
- Smoke test script: `.ly_state/session/llm_scoring_smoke_test_20260612.py`
- This report: `.ly_state/session/l2_role9_llm_scoring_real_provider_smoke_20260612.md`

---

**L2 Sign-off**: Backend Engineer (Role 9), 2026-06-12  
**Awaiting**: L3 Audit (Role 17-25, Codex platform)
