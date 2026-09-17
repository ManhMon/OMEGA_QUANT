# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-23T09:41:13+07:00
**Gate**: HYBRID_REGIME_ALPHAS_DIVERSIFIED_COMPLIANCE_20260623
**L3 Session**: l3_role20_alphas_diversified_compliance_20260623
**L2 Session**: l2_role14_alphas_diversified_20260623
**L2 Role**: 14 data-scientist
**Verdict**: [APPROVED]

## Repo-Local Source Evidence

Authoritative L3 sources read:

- `.agents/agent/compliance-officer.md`
- `.agents/agent/data-scientist.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Additional SOP detail files referenced by `sops/SKILL.md` were not present in the repo-local `sops` skill directory: `SOP_AC.md`, `SOP_BACKTEST.md`, `SOP_PIT_SAFETY.md`. The embedded SOP sections in `.agents/skills/sops/SKILL.md` were used.

Forbidden path scan result: no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=14`, `l3_role_id=20`).
- L3 role validation: PASS (`role_id=20`, tier 3, platform Codex, `sod_boundary` present).
- L2 role validation: PASS (`role_id=14`, tier 2, platform OpenCode).
- L3 boundary: PASS, no production source or test edits made by L3.
- L2 report exists: PASS, `.ly_state/session/l2_role14_alphas_diversified_20260623.md`.
- L2 report lists exact repo-local role and skill files read: PASS.
- L2 report forbidden path scan evidence: PASS.

## Scope Compliance

Audited scoped files:

- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`

The working tree contains unrelated out-of-scope dirty files. They were not audited under this gate.

## Implementation Checks

- Quota selection buckets categorized alpha lag columns by HR/GP/LLM/VN.
- Each bucket is sorted by descending `abs(alpha_ics[c])` before selecting up to 2 alphas.
- Fallback behavior remains for no categorized finite-IC alphas.
- `TCostOverlay` Hybrid tuning is present with `cost_per_trade_bps=15.0` and `min_trade_threshold_bps=20.0`.
- Baseline scenario remains without `TCostOverlay`.
- Regression test covers the prior column-order bug by proving `alpha_hr_mid_lag1` is selected over earlier lower-IC `alpha_hr_low_lag1`.

## PIT Safety

PIT checks passed:

- Training ICs are computed on `train_feat` only.
- Training alpha features use per-symbol `shift(1)`.
- First rows with unavailable lag values are dropped rather than filled.
- Quota selection uses only fold-local training ICs.
- Prediction lag path uses backward-only per-symbol `shift(1)`.
- No `shift(-1)` or future-referencing quota logic was found in the audited scope.

## Test Evidence

- `python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -v --tb=short`: PASS, 38 passed, 3 warnings.
- `python -m pytest -q`: PASS, full suite passed, warnings only.
- `python scripts/sod_gate_enforcer.py`: FAIL before this report/gate update because this target gate and sibling review gate were still pending.

## Residual Gate Note

This compliance gate is approved. Global push gating still requires the separate `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` gate to receive its own L3 review verdict.

## CODEX AUDIT VERDICT

**Status:** [APPROVED]
**Date:** 2026-06-23T09:41:13+07:00
**Auditor:** Codex L3 compliance-officer (Role 20)
**Scope:** quota-based alpha selection, TCostOverlay tuning, PIT/SOD compliance
**Rationale:** Code, tests, PIT checks, repo-local source evidence, and L3 SOD boundaries pass for the target compliance gate.

**Signature:** Codex L3 Auditor
