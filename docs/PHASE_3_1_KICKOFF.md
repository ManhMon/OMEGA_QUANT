# Phase 3.1 Kickoff — Alpha Discovery

## Purpose
Kick off Phase 3.1 Alpha Discovery with strict PIT-safe implementation scope.

## Objectives
1. Build deterministic Alpha Discovery baseline without lookahead leakage.
2. Keep all feature computation point-in-time correct (T-1 or earlier only).
3. Define minimal executable contract for Phase 3.1 modules.
4. Establish acceptance tests that fail on PIT violations.

## In-Scope Modules (Phase 3.1)
- `src/indicators/alpha_discovery.py`
  - Alpha signal generation primitives.
  - Rolling/statistical transforms constrained to historical window only.
- `src/features/pit_guard.py`
  - Guardrails enforcing T-1 feature availability.
  - Utility checks for timestamp alignment and leakage detection.
- `src/pipeline/alpha_discovery_pipeline.py`
  - Orchestration layer wiring data -> features -> alpha outputs.
  - Deterministic run path for repeatable validation.
- `tests/test_alpha_discovery_pit.py`
  - PIT and no-lookahead invariants.
- `tests/test_alpha_discovery_contract.py`
  - Module contract and deterministic output shape checks.

## PIT Safety Constraints (Mandatory)
- **T-1 Rule:** Any feature consumed at decision time `t` must be computed from data timestamped `<= t-1`.
- **No Lookahead:** No direct or indirect access to `t`/future labels, prices, or derived fields when building predictors for `t`.
- **Window Boundaries:** Rolling windows must be closed on prior bar only; no centered windows.
- **Join Discipline:** Any merge/join must preserve temporal causality; right-side records after `t-1` prohibited.
- **Determinism:** Identical input snapshot + config must produce identical output.

## Acceptance Tests (Phase Gate)
1. **Temporal Shift Test**
   - Given mock time-indexed data, verify all model input features at index `t` equal computations based only on indices `< t`.
2. **Leakage Sentinel Test**
   - Inject synthetic future-only signal; assert pipeline output unaffected.
3. **Rolling Window Integrity Test**
   - Validate rolling ops never include current bar (`t`) for prediction at `t`.
4. **Join Causality Test**
   - Assert merged feature table contains no right-table timestamps greater than allowed cutoff (`t-1`).
5. **Determinism Test**
   - Run pipeline twice on same fixture; assert byte/array equality of outputs.

## T-1 / No-Lookahead Implementation Notes
- Enforce explicit feature cutoff timestamp before transform stage.
- Centralize PIT checks in guard utility, called by pipeline entrypoint.
- Fail fast on violations (exception with offending column/time index).
- Record validation metadata for audit traceability.

## Non-Goals (This Kickoff)
- Strategy optimization, hyperparameter search, live deployment logic, or execution stack changes.
- Any forward-looking feature experimentation that cannot satisfy T-1 guarantees.

## Done Criteria for Kickoff Artifact
- Objectives documented.
- Module list documented.
- Acceptance tests documented.
- T-1/no-lookahead constraints documented and unambiguous.
