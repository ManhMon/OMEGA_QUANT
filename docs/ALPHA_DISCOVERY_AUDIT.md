# ALPHA_DISCOVERY Phase 3.1 Audit

Verdict: **[NEEDS_FIX]**

## Scope
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_discovery.py`
- `OMEGA_QUANT/tests/phase3/test_alpha_discovery.py`

## Test Execution
Command:
`python -m pytest OMEGA_QUANT/tests/phase3/test_alpha_discovery.py -v`

Result:
- 6 collected
- 6 passed
- Runtime: 1.10s

## Findings

### 1) Pipeline integration across modules
Status: **Partial / flawed**

What works:
- Pipeline imports and calls:
  - `label_engine.generate_forward_return_labels`
  - `pit_guard.detect_lookahead_leakage`
  - `alpha_primitives.calculate_ic`, `calculate_sharpe`
  - `expression_generator.generate_polynomial_expression`, `generate_cross_sectional_expression`

Critical issue:
- PIT lag computed (`lagged_features`) but candidate generation uses **raw `features`**:
  - `poly_features = generate_polynomial_expression(features, degree=2)`
  - `cs_features = generate_cross_sectional_expression(features)`
- This bypasses intended T-1 enforcement for generated candidate factors.

Impact:
- Logical integration claim present, but PIT-safe data path inconsistent.

### 2) PIT safety (T-1 lag + available_at discipline)
Status: **Not fully enforced**

Observations:
- T-1 shift exists at start of pipeline.
- Leakage check only tests first lagged column against labels. Not full candidate set.
- Candidate features mostly derived from unshifted raw data.
- Imported `enforce_t_minus_1_lag`, `validate_temporal_shift` unused in this pipeline path.

Conclusion:
- PIT policy intent visible, enforcement incomplete.

### 3) `filter_alphas` thresholds
Status: **Pass**

- IC: requires any horizon max abs(IC) >= threshold.
- Sharpe: rejects only when finite Sharpe below threshold; NaN tolerated.
- Turnover: rejects only when finite turnover above threshold; NaN tolerated.
- Unit test validates IC/Sharpe/Turnover gating behavior.

### 4) Report generation stability
Status: **Pass**

- Handles empty input (`"No alphas discovered."`).
- Produces deterministic section structure for non-empty input:
  - header, totals, IC/Sharpe/Turnover stats, top-10 listing.
- Tests assert required sections.

### 5) Test coverage quality (E2E + edge cases)
Status: **Good but incomplete for PIT guarantees**

Covered:
- E2E run returns structured records.
- Empty input safe.
- Filtering thresholds.
- Report non-empty + empty paths.

Gaps:
- No test proving polynomial/cross-sectional candidates built from lagged features.
- No test validating `detect_lookahead_leakage` over all candidate columns.
- No explicit available_at/temporal-shift validation test.

## Required Fixes
1. Build candidate features from `lagged_features` only:
   - `generate_polynomial_expression(lagged_features, ...)`
   - `generate_cross_sectional_expression(lagged_features)`
2. Apply leakage check on every candidate factor (or at least all selected/passing factors), not only first base column.
3. Add tests that fail on current behavior and pass after PIT-safe refactor:
   - raw-vs-lagged candidate provenance test,
   - full-set leakage detection coverage test,
   - temporal shift/available_at discipline validation.

## Final Verdict
**[NEEDS_FIX]**

Reason: PIT safety claim not reliably true in candidate generation path despite passing tests.
