# NEUTRALIZATION_AUDIT_R1

- **Role**: Code Reviewer (Role 21)
- **Scope**:
  - `OMEGA_QUANT/packages/core/src/omega/core/feature_neutralizer.py`
  - `OMEGA_QUANT/packages/core/tests/test_feature_neutralizer.py`
  - `OMEGA_QUANT/config/production.yaml`
- **Date**: 2026-05-12
- **Verdict**: `[NEEDS_FIX]`
- **PIT Safety**: `PASS (with test-coverage gaps)`
- **Role Compliance**: `PASS`

## Checks Run

1. `pytest -q packages/core/tests/test_feature_neutralizer.py` -> `16 passed, 1 warning`.
2. Fixture sanity check (script) -> per-date `market_return` std is `0.0` in both test fixtures.

## Findings

### P0-1: Vectorization requirement not fully satisfied for strict "no loops" policy

**Requirement**: Neutralization logic vectorized (`no iterrows/loops`).

**Evidence**:
- `feature_neutralizer.py` contains explicit Python loops in neutralization path:
  - feature iteration: line 121
  - impact iteration: line 201
  - style-factor validation iteration: line 263
- Additional row-wise loop exists in dependency engine path (`neutralization.py`, cap-weighted method):
  - `df.apply(..., axis=1)`: lines 203-206

**Impact**:
- Violates strict interpretation of "no loops" in neutralization flow.
- Current production config uses `sector_method: demean`, so row-wise cap-weighted path is dormant now, but code path remains non-vectorized if enabled later.

### P1-1: PIT safety test does not directly prove no-look-ahead invariants

**Requirement**: PIT safety preserved (no look-ahead).

**Evidence**:
- `test_pit_safety_preserved` checks within-date mean close to zero, not temporal leakage contract:
  - test logic lines 316-320.
- Wrapper code in `feature_neutralizer.py` performs no forward merges/shifts and delegates by date to engine, so no direct leak found in reviewed scope.

**Impact**:
- Implementation appears PIT-safe in reviewed wrapper.
- Proof strength is weaker than required for institutional audit because test does not inject forward-data sentinel or explicit anti-leak assertion.

### P1-2: Market neutralization tests do not exercise true beta-weighted branch behavior

**Requirement**: Integration tests prove exposure reduction.

**Evidence**:
- Fixture generates one `market_return` value per date and reuses it for all symbols:
  - sample fixture lines 33, 47
  - pipeline fixture lines 376, 390
- This makes per-date cross-sectional `market_return` variance zero, so beta-weighted branch can collapse to demean fallback in engine.

**Impact**:
- Tests confirm exposure reduction outcome, but do not conclusively validate beta-weighted regression behavior under non-degenerate cross-sectional market input.

## Requirement-by-Requirement Verification

1. **Vectorization (no iterrows/loops)**: **FAIL**
   - Explicit loops remain in wrapper and non-vectorized dormant path exists in engine.
2. **PIT safety (no look-ahead)**: **PASS (with gap)**
   - No direct look-ahead found in reviewed wrapper code; tests should be strengthened.
3. **Production YAML flags match spec**: **PASS**
   - `enabled: true`, `enable_market_neutral: true`, `enable_sector_neutral: true`, `enable_style_neutral: false`, `market_method: beta_weighted`, `sector_method: demean`, `style_method: regression`, `validation.tolerance: 0.1` in `config/production.yaml` lines 58-66, 79.
   - Matches documented integration spec in `docs/P0_NEUTRALIZATION_INTEGRATION.md` lines 70-77, 90.
4. **Integration tests prove exposure reduction**: **PARTIAL**
   - Outcome checks exist and pass (e.g., lines 111-112, 134-135, 158-159, 418-423), but fixture degeneracy weakens proof for beta-weighted mode.

## Required Fixes Before Approval

1. Remove or justify Python loops in neutralization path to meet strict vectorization contract.
2. Add PIT anti-leak tests with explicit time-shift sentinel assertions.
3. Add non-degenerate market fixture where cross-sectional market input variance per date is non-zero (or update engine/test contract) to validate true beta-weighted behavior.

