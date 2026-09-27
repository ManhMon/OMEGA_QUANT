# W1 — Contracts, PIT, and Bounded Invocation

- **Gate**: `GATE_JEV_DEEP_INTEGRATION_W1_20260927`
- **Predecessor Gate**: `GATE_JEV_DEEP_INTEGRATION_W0_20260927` (Commit `1c19b8727e1a12c53e50e226f420dc7dde18669a`)
- **L2 Primary Role**: `16 machine-learning-engineer`
- **L3 Primary Role**: `19 security-auditor`

## Deliverables in Scope
1. `src/omega/core/llm_config.py`:
   - Common classification envelope conforming to Section 3.1.
   - Domain registry for the 11 registered domains conforming to Section 3.2.
   - Cache key calculation with multi-attribute canonical serialization conforming to Section 3.3.
    - Deterministic selective invocation policy & budget accounting.
    - Legacy v1 daily-key compatibility; W1 registered domains use v2 full-cutoff binding.
2. `tests/test_sod_jev_model_routing.py`:
   - Verification suite covering W1 envelope, schema validation, cache key invariants, and 16D matrix.
3. W1 Evidence files:
   - `.ly_state/session/jev_deep_integration_20260926/W1/scope.md`
   - `.ly_state/session/jev_deep_integration_20260926/W1/input_manifest.json`
   - `.ly_state/session/jev_deep_integration_20260926/W1/matrix_evidence.md`
   - `.ly_state/session/jev_deep_integration_20260926/W1/rollback.md`
