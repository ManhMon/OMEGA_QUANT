# L3 Independent Plan Audit - `gp_sol_v7_plan`

**Verdict**: [NEEDS_FIX]
**Date**: 2026-07-19
**L2 session**: `l2_role16_gp_sol_v7_plan_20260719`
**L2 role**: `16 machine-learning-engineer`
**L3 session**: `l3_role21_gp_sol_v7_plan_20260719`
**L3 role**: `21 code-reviewer`

## SOD Verification

- Writer/auditor separation: PASS (`16 != 21`).
- L3 boundary: PASS. No production source or test files modified; only this audit report and the scoped `gp_sol_v7_plan` gate metadata are updated.
- Platform separation: PASS. No OpenCode invocation from L3.

## Repo-Local Source Evidence

Exact authoritative files read:

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Additional repo-local evidence read:

- `.agents/AGENTS.md`
- `.ly_state/session/l2_role16_gp_sol_v7_plan_20260719.md`
- `.ly_state/session/phase_gates.json`

Scope artifact read only as non-authoritative plan content:

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

Forbidden path scan: PASS. No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. Their appearances in the L2 report are explicit negative scan evidence only.

## Findings

1. **BLOCKING - stock MTM equation is dimensionally inconsistent.** The plan defines `realized_stock_weights_t_minus_1` as portfolio weights after execution, explicitly permits residual cash, and enforces `sum(realized_stock_weights_t) <= 1.0`. It then computes `stock_pnl_t = stock_notional_t_minus_1 * dot(realized_stock_weights_t_minus_1, stock_returns_t)`. This applies the stock allocation fraction twice whenever cash or margin exists. V7 must choose one consistent representation:
   - portfolio weights: `stock_pnl_t = nav_t_minus_1 * dot(realized_stock_weights_t_minus_1, stock_returns_t)`; or
   - stock-sleeve weights normalized to 1: retain multiplication by `stock_notional_t_minus_1` and store a separately named normalized vector.
   Add a test with nonzero cash/margin and stock exposure below 100% so the current erroneous formula cannot pass.

2. **IMPORTANT - metric migration test paths remain unspecified.** The acceptance criterion requires a clear code path and test path for every blocker, but the metric tests are assigned only to unspecified "adjacent existing test modules." Name the exact test file or add one exact test file to the scope and verification command.

## Blocker Coverage

- Ledger balance/VM double count: addressed at plan level, contingent on fixing the stock MTM representation above.
- Daily joint-ledger event order: addressed with one ordered event loop and end-of-day invariants.
- Margin effective-date schedule and MM/IM mechanics: addressed.
- Forced liquidation ordering, rounding, costs, and insolvency: addressed.
- Futures MTM and prior-position timing: addressed.
- Expiry roll calendar rollback to preceding trading day: addressed.
- Pre-trade IM plus close/open roll costs: addressed.
- Roll-before-retarget state transition and diagnostics: addressed.
- `TradingPipelineV2` overlay uniqueness/order and no-renormalization semantics: addressed.
- Metric rename conflict semantics: behavior addressed; exact test file unresolved.
- PIT crash-universe breadth and warm-up behavior: addressed.

## Test Evidence

- No implementation tests run. This gate audits an implementation plan, and the L2 report states no code/tests were executed.
- Planned commands are adequate after the two findings are corrected and the metric test file is named explicitly.

## Required Fix

Revise the stock MTM state/equation to use one weight denominator, add the underinvested-portfolio regression test, and specify the exact metric migration test file. Resubmit for independent L3 review.

## Verdict

[NEEDS_FIX]
