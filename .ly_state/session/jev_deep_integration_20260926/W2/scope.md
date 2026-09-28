# W2 — Regime and Alpha Calibration

- **Gate**: `GATE_JEV_DEEP_INTEGRATION_W2_20260928`
- **Predecessor Gate**: `GATE_JEV_DEEP_INTEGRATION_W1_20260927` (Commit `72f1d8bf2832b3a60b59ece5cad7c502d37c9def`)
- **L2 Primary Role**: `14 data-scientist`
- **L3 Primary Role**: `20 compliance-officer`

## Deliverables in Scope
1. `src/omega/quant/portfolio/regime_overlay.py`:
   - Resolve 4-state HMM/rule mismatch vs 3-state BULL/BEAR/SIDEWAYS overlay per Master Plan Section 2 and 3.2.
   - Support regime arbitration with liquidity, valuation, trend context dimensions conforming to Section 3.2.
   - Maintain baseline equality when disabled or JEV unavailable.
2. `src/omega/quant/ensemble_optimizer.py`:
   - Calibrated alpha profile selection (`momentum_heavy`, `mean_reversion_heavy`, `balanced`, `defensive`) and alpha disagreement fallback (`trend_supported`, `reversal_supported`, `mixed`, `insufficient`).
   - Project weights onto bounded simplex with valid feasibility residuals.
3. `tests/test_jev_regime_alpha_weighting.py`:
   - B0-B4 experiment manifest assertions, baseline equivalence tests, PIT safety, and negative controls.
4. W2 Evidence files:
   - `.ly_state/session/jev_deep_integration_20260926/W2/scope.md`
   - `.ly_state/session/jev_deep_integration_20260926/W2/input_manifest.json`
   - `.ly_state/session/jev_deep_integration_20260926/W2/matrix_evidence.md`
    - `.ly_state/session/jev_deep_integration_20260926/W2/rollback.md`

## Calibration status
- Regime and alpha influence default to zero; positive influence requires independently calibrated policy.
- B0-B4 arms defined in `experiment_manifest.json`; no historical performance claim without frozen PIT datasets and out-of-sample measurements.
- Remediation F-001: regime choice uses registered three-state domain; alpha profile and disagreement use separate registered domains. Four-state labels remain HMM-only context.
- Remediation F-002: initial HMM volatility uses expanding historical observations; prefix-invariance regression covers future shocks.
- Remediation F-003: historical regime arbitration reads PIT-valid cached decisions with `cache_only`; cache miss preserves HMM baseline without provider access.
