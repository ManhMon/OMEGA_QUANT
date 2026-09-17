# Code Review Audit Report

**Role**: Code Reviewer (Role 21)  
**Date**: 2026-07-19  
**Gate**: `gp_futures_joint_ledger_fix1`  
**L2 session**: `l2_role16_gp_futures_joint_ledger_fix1_20260719`  
**L2 role**: `16 machine-learning-engineer`  
**L3 session**: `l3_role21_gp_futures_joint_ledger_fix1_20260719`  
**L3 role**: `21 code-reviewer`

## SOD Verification

- Writer/auditor separation: PASS (`16 != 21`).
- L3 role spec: PASS. `.agents/agent/code-reviewer.md` frontmatter has `role_id=21`, `tier=3`, `platform=Codex`, and SOD boundary.
- L3 boundary: PASS. L3 wrote only this audit report and the scoped `gp_futures_joint_ledger_fix1` gate entry.
- L2 report skill evidence: PASS. L2 report lists exact repo-local role/skill files under `.agents/agent` and `.agents/skills`.

## Repo-Local Files Read

Authoritative role/skill files:

- `.agents/agent/code-reviewer.md`
- `.agents/AGENTS.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Repo-local audit evidence:

- `.ly_state/session/l2_role16_gp_futures_joint_ledger_fix1_20260719.md`
- `.ly_state/session/audit_reports/role21_gp_futures_joint_ledger_implementation_20260719.md`
- `.ly_state/session/audit_reports/role21_gp_relaxed_promotion_threshold_20260718.md`
- `.ly_state/session/audit_reports/role21_gp_relaxed_sharpe_threshold_20260718.md`
- `.ly_state/session/l2_role9_gp_relaxed_promotion_threshold_20260718.md`
- `.ly_state/session/l2_role9_gp_relaxed_sharpe_threshold_20260718.md`
- `.ly_state/session/phase_gates.json`

Scoped source/test files reviewed:

- `src/omega/quant/portfolio/execution_sim.py`
- `scripts/run_weekly_evolution.py`
- `tests/test_futures_joint_ledger.py`
- `tests/test_evolution_metric_migration.py`

## Forbidden Path Scan Result

No authoritative reliance on forbidden paths. Scoped scan found forbidden path strings only in repo-local SOD policy files and L2/L3 report evidence explicitly marking those paths non-authoritative:

- `.gemini\antigravity-ide\scratch\ag-kit`
- `.openclaw\skills`
- `C:\Users\GHC\.agents`
- `.codex\memories`

Codex memory was not used as an authoritative skill/role source.

## Test Evidence

- `python -m pytest -q`: timed out after 124 seconds before summary.
- `python -m pytest -q --disable-warnings -p no:cacheprovider`: PASS, exit 0, full suite completed.
- Runtime probe for prior examples: PASS for corrected stock notional (`55.0`), positive oversized target downscale (`margin_locked_t=0.0`, `cash_free_t=10.0`), and forced futures liquidation (`forced_futures_contracts=1.0`, `margin_locked_t=1300.0`).
- Runtime probe for short hedge affordability: FAIL. `target_futures_contracts=-10.0`, cash `10.0`, price `100.0`, multiplier `100.0` returned `margin_locked_t=13000.0`, `cash_free_t=-12990.0`, `required_cash_t=0.0`.

## Previous Blocking Findings

1. `stock_notional_t` double-counting: RESOLVED for reviewed examples. Current code derives prior stock sleeve from `nav_t_minus_1 - cash - margin - vm` and adds only stock PnL.
2. Futures affordability enforcement: NOT FULLY RESOLVED. Positive long target downscales, but negative/short hedge targets bypass required initial margin.
3. Forced futures liquidation state transition: RESOLVED for reviewed examples. Final exposure and `margin_locked_t` reflect reduced contracts after cash deficit liquidation.
4. Weekly promotion canonical metric migration: RESOLVED. `evaluate_and_promote` calls `resolve_metric_config`, promotes on `signal_pnl_score`, and persists `signal_pnl_score`.
5. Threshold change outside scope: RESOLVED by evidence. `gp_relaxed_promotion_threshold` and `gp_relaxed_sharpe_threshold` are prior approved gates covering `IC > 0.01` and `signal_pnl_score > 0.08` intent.

## Findings

1. **BLOCKING - `src/omega/quant/portfolio/execution_sim.py:112-125`**: Pre-trade margin affordability still uses `max(incremental_contracts, 0.0)`, so short futures increases require zero initial margin. A normal hedge direction from `0` to `-10` contracts with only `10` cash returns `margin_locked_t=13000.0`, `cash_free_t=-12990.0`, and `required_cash_t=0.0`. Futures margin is symmetric by notional; affordability must use absolute exposure increase or an equivalent margin-delta check. This leaves previous blocking finding 2 unresolved for short hedges.

## PIT Safety

- No look-ahead found in the reviewed metric migration path. Promotion still uses post-test metrics and embargo validation; no train/test data leakage was introduced.
- The ledger bug is not a look-ahead issue. It is an execution accounting/margin-safety defect.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]  
**Date:** 2026-07-19  
**Auditor:** Codex (L3)  
**Scope:** `src/omega/quant/portfolio/execution_sim.py`, `scripts/run_weekly_evolution.py`, `tests/test_futures_joint_ledger.py`, `tests/test_evolution_metric_migration.py`

### Phase Gates

- **l3_session_id:** `l3_role21_gp_futures_joint_ledger_fix1_20260719`
- **l3_session_key:** `l3_role21_gp_futures_joint_ledger_fix1_20260719`
- **audit_report_path:** `.ly_state/session/audit_reports/role21_gp_futures_joint_ledger_fix1_20260719.md`
- **final_verdict:** [NEEDS_FIX]

### Required Actions

1. Fix pre-trade affordability for short futures targets so required margin is based on absolute exposure/margin delta, not only positive `incremental_contracts`.
2. Add a regression test for an underfunded short hedge target that must downscale or reject without negative free cash.

**Signature:** Codex L3 Auditor
