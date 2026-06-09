# P10 Multi-Horizon Blending - Role20 Compliance Rebuttal

Role: Compliance Officer / Role 20
Date: 2026-06-09
Scope: P10 multi-horizon blending PIT/compliance audit only. No implementation performed.

## Verdict

Verdict: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS

## Rebuttal Summary

Core PIT invariants are not disproven: per-horizon train/test embargo is applied, blend weights are derived from train/validation labels only, `fwd_ret_*` are not feature inputs in the reviewed P10 path, and quick-mode zero metrics are an expected one-symbol smoke artifact. However, P10 is not compliance-approvable because the Research Gate can fail every alpha and still allow that horizon into the blend through the existing fallback to `top_alphas`. This violates the P10 plan/L2 claim that a gate-failed horizon receives weight 0.

## Findings

### P1 - Research Gate failure does not remove horizon from blend

Evidence:
- `src/omega/quant/phase35_walk_forward.py:1143-1149` calls `validate_alpha_with_research_gate()` on the horizon validation slice.
- `src/omega/quant/phase35_walk_forward.py:1151-1153` intends to skip the horizon when `gated_alphas` is empty.
- But `src/omega/quant/phase35_walk_forward.py:675-681` falls back to `top_alphas` when all alphas fail the gate, so `gated_alphas` is normally not empty after a full gate failure.
- Probe result with `validate_research_gate` forced to fail for all alphas: `{'signal_is_none': False, 'gated': ['alpha_a', 'alpha_b'], 'gate_passed': [False, False]}`.

Compliance impact:
- The implementation can assign nonzero blend weight to a horizon whose alphas all failed validation gate.
- This contradicts the plan requirement: failed horizon -> weight 0; all fail -> fallback to current T+5 behavior.
- This is not direct test-label leakage, so `PIT Safety` remains PASS, but release gate should not approve this behavior.

### P2 - `blend_weight_method="train_ic"` is accepted but not implemented

Evidence:
- `src/omega/quant/phase35_walk_forward.py:1360-1365` stores only `validation_ic` as each horizon quality.
- `src/omega/quant/phase35_walk_forward.py:1373-1375` passes `method=self.blend_weight_method`, but `_blend_horizon_signals()` only logs/accepts `method`; it does not change quality source.
- `src/omega/quant/phase35_walk_forward.py:1181-1255` always weights from the supplied quality metric, which is validation IC from the caller.

Compliance impact:
- No test-label leakage observed.
- CLI/config promises a `train_ic` mode that does not exist, so auditability/reproducibility is weaker than the exposed API suggests.

### P2 - Tests are not adversarial enough for embargo/gate claims

Evidence:
- `tests/phase35/test_p10_multi_horizon_blend.py:163-201` checks h=1 and h=3 signal success, not exact rows removed or validation/train boundary exclusion.
- `tests/phase35/test_p10_multi_horizon_blend.py:211-232` tests blending from synthetic prebuilt qualities, not that production weights avoid test labels.
- The file advertises no `fwd_ret_*` evolved-path leakage coverage in its header, but no actual test enforces that exclusion.

Compliance impact:
- Current test pass is useful smoke, not sufficient evidence for the claimed gate and PIT invariants.

## Check Results

1. Per-horizon embargo for `fwd_ret_1`, `fwd_ret_3`, `fwd_ret_5`: PASS. `_compute_horizon_signal()` uses `tail_rank >= horizon` before train/validation IC/gate.
2. No test-label leakage into horizon weights: PASS. `validation_ic` is computed on `val_actual`, which is split from embargoed train data; no `test_df[fwd_ret_*]` participates in weights.
3. No `fwd_ret_*` as features in evolved/model paths: PASS for P10. Multi-horizon mode bypasses XGBoost/evolved paths; existing GP helper excludes all `fwd_ret_*` from feature columns.
4. Research Gate uses validation/train only: PASS for data source, FAIL for enforcement. It uses validation/train labels only, but full gate failure is silently converted to `top_alphas`.
5. Quick smoke zero metrics: expected smoke artifact, not a compliance blocker. Quick mode uses one symbol, so cross-sectional z-score/IC naturally collapses to zero/undefined while still exercising CLI/config wiring.
6. Subtle lookahead/current-day/cross-horizon leakage: no direct test-label leakage found. Residual concern: internal train/validation split is not separately purged at the train_actual/val_actual boundary, but this is inside historical training data and lower priority than the gate-bypass blocker.

## Verification Run

- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `12 passed`.
- Custom gate-failure probe -> all gate results `False`, yet horizon signal returned and `gated` contained failed alphas.

## Required Final Fields

Role: Compliance Officer / Role 20
Verdict: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS
Rebuttal Summary: PIT leakage was not proven, but Research Gate failure is not enforced; a fully failed horizon can still enter the blend with nonzero weight, so P10 cannot be compliance-approved until failed-gate horizons are excluded or assigned zero weight and all-fail fallback matches the plan.
