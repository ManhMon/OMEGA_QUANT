# Code Review Audit Report

**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-24T17:15:06+07:00
**Gate**: VN_ALPHA_TC_OPTIMIZATION_20260624
**L2 Session**: l2_role14_vn_alpha_tc_optimization_20260624
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Forbidden Path Scan Result

No authoritative reliance on forbidden paths. The following paths were treated as non-authoritative only: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

## SOD Checks

- Writer != Auditor: PASS (`l2_role_id=14`, `l3_role_id=21`)
- L3 boundary: PASS, no production source/test edits by L3
- L2 report present: PASS, `.ly_state/session/l2_role14_vn_alpha_tc_optimization_20260624.md`
- L2 repo-local skill evidence: PASS
- Approved scope: PARTIAL. Requested audit scope was `src/omega/quant/pipeline_v2.py`, `src/omega/quant/portfolio/tail_controls.py`; L2 also changed tests, which is acceptable as verification evidence but outside the stated source scope.

## Tests Run

- `python -m compileall src\omega\quant\pipeline_v2.py src\omega\quant\portfolio\tail_controls.py`
- `python -m pytest tests\test_pipeline_v2.py tests\quant_test_tail_controls.py`
  - Result: 23 passed, 3 warnings in 9.23s
- `python -m pytest`
  - Result: 2402 passed, 649 warnings in 127.71s

## Findings

1. BLOCKING - Live cold-state path can liquidate existing positions.
   - Location: `src/omega/quant/pipeline_v2.py:811-838`, `src/omega/quant/pipeline_v2.py:300-313`
   - The new TC gate derives `prev_w_init` only from saved pipeline state. In live mode, current broker positions are held by `LiveOutputHandler`, but they are not passed into `_apply_trade_gating`.
   - With no saved `last_weights`, `prev_w` starts at zero. For a one-day live run, `_build_expected_alpha_frame` has no prior rolling return history, so expected alpha is zero; the TC gate keeps the zero prior weight. `LiveOutputHandler` then compares zero targets against real current positions and emits sell orders to flatten.
   - Reproduction run using the existing live test shape produced:
     - `HPG`: target `0.0`, current `0.1`, order `-0.1`
     - `SSI`: target `0.0`, current `0.2`, order `-0.2`
   - Required fix: align gating prior weights with actual live current positions, disable dynamic TC gating until sufficient PIT history exists, or make the gate explicitly mode-aware so cold-start live runs do not unintentionally flatten positions.

2. NON-BLOCKING - Dynamic TC diagnostics are not persisted.
   - Location: `src/omega/quant/pipeline_v2.py:839-845`, `src/omega/quant/pipeline_v2.py:875-879`
   - The implementation stores `state["dynamic_tc_gate"]`, then replaces state with `new_state` that omits `dynamic_tc_gate`. L2 report claims diagnostics are stored in pipeline state, but saved state does not include them.

## PIT Safety

- Expected alpha uses rolling absolute returns with `.shift(1)`: PASS.
- Signal model trains only on prior date rows for each prediction date: PASS.
- Smart-money and sentiment overlays shift scores by one symbol bar: PASS.
- ADV used for TC execution/gating is shifted one bar after requested-period trim: PASS for no look-ahead, though first requested bar falls back to default/no ADV.
- Blocking issue above is live execution safety, not look-ahead leakage.

## Verdict

[NEEDS_FIX]

The source passes tests and the main PIT checks, but the live cold-state liquidation behavior is a production-safety regression and must be fixed by L2 before approval.
