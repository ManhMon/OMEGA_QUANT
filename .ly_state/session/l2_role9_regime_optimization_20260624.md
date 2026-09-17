# L2 Report: regime_optimization_20260624

- Role: `9 backend-engineer`
- Gate: `LABEL_HORIZON_SWEEP_ENSEMBLE_20260623`
- Scope:
  - `scripts/backtest_hybrid_regime.py`
  - `scripts/backtest_multihorizon_ensemble.py`
  - `tests/test_multihorizon_ensemble.py`
  - `tests/phase35/test_hybrid_regime_dynamic_brake.py`

## Repo-Local Skill Source Evidence

- Role spec read:
  - `.agents/agent/backend-engineer.md`
- Declared repo-local skill files read:
  - `.agents/skills/nodejs-best-practices/SKILL.md`
  - `.agents/skills/api-patterns/SKILL.md`
  - `.agents/skills/database-design/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan

- No authoritative role/skill loads from forbidden paths.
- The forbidden path `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- The forbidden path `.openclaw\skills` is non-authoritative and not used as source.
- The forbidden path `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- The forbidden path `.codex\memories` is non-authoritative and not used as source.

## Changes Implemented

### 1. Hybrid bear-market GMM re-entry tuning

- File: `scripts/backtest_hybrid_regime.py`
- Location: `build_scenario_overlays()` Hybrid `DrawdownControlOverlay`
- Changes:
  - `gmm_bull_confidence=0.25`
  - `gmm_partial_reentry_scale=0.50`
  - `gmm_reentry_cooldown_extension=1`

### 2. Ensemble alpha filter relaxation

- File: `scripts/backtest_multihorizon_ensemble.py`
- Changes:
  - `apply_fdr_filter()` -> `multipletests(..., alpha=0.15, method="fdr_bh")`
  - `apply_profit_factor_gate()` -> pass threshold relaxed from `1.3` to `1.20`
- `DrawdownControlOverlay` usage in this script: none found, so no ensemble overlay update required.

### 3. Test updates

- File: `tests/test_multihorizon_ensemble.py`
  - Added gate-panel helper for deterministic filter tests.
  - Added regression tests for:
    - relaxed PF threshold accepting `1.20`
    - PF filter rejecting weaker candidate in multi-alpha set
    - FDR using `alpha=0.15`
- File: `tests/phase35/test_hybrid_regime_dynamic_brake.py`
  - Added regression test asserting Hybrid scenario wires tuned GMM params into `DrawdownControlOverlay`.

## Verification

### Targeted tests

- Command:
  - `pytest tests/test_multihorizon_ensemble.py tests/phase35/test_hybrid_regime_dynamic_brake.py`
- Result:
  - `76 passed, 4 warnings in 6.97s`

### Full suite

- Command:
  - `pytest`
- Exit check:
  - `pytest -q --disable-warnings *> $null; if ($LASTEXITCODE -eq 0) { 'PYTEST_OK' } else { "PYTEST_FAIL:$LASTEXITCODE" }`
- Result:
  - `PYTEST_OK`

## Outcome

- Requested source changes applied.
- Requested test files updated.
- Full pytest suite passes.
- No audit performed.
