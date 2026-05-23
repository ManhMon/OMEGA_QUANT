# Phase 5 Kickoff — Risk Management Migration

## Purpose
Migrate the Risk Management layer (Individual Risk Guard, Circuit Breakers, Contagion Validator) into the `omega.risk` namespace.

## Objectives
1. Migrate Individual-Scale Risk Guard (2B-5B VND capital).
2. Migrate Advanced Circuit Breakers (market-wide, sector, asset-level).
3. Migrate Contagion Risk Validator (correlation spikes, beta jumps).
4. Port existing tests and ensure 100% test pass rate.

## In-Scope Modules
- `packages/risk/src/omega/risk/individual_risk_guard.py`
- `packages/risk/src/omega/risk/circuit_breaker.py`
- `packages/risk/src/omega/risk/contagion_validator.py`
- `tests/phase5/` (test suite)

## Constraints
- Strict PIT safety: Risk checks must use T-1 limits or point-in-time constraints.
- Vectorized execution: No iterrows in risk limit calculations.

## Acceptance Tests
1. **Risk Limits**: Concentration < 25%, Max ADV < 40%.
2. **Circuit Breakers**: Halt trading on 7% single-day drop or 15% 5-day drop.
3. **Contagion Detection**: Trigger correlation alerts if > 0.8 rolling correlation.
