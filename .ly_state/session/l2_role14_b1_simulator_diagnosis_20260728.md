# L2 Read-Only Diagnosis — SHARPE_TCOST_PHASE2_SIMULATOR_FIX

## Session

- Role: `14 data-scientist` / OpenCode L2
- Session: `l2_role14_b1_simulator_diagnosis_20260728`
- Gate: `SHARPE_TCOST_PHASE2_SIMULATOR_FIX`
- Scope: read-only diagnosis of `test_slippage_scales_with_capital` and `test_dynamic_capital_tracking_changes_slippage_path`
- Evidence date: `2026-07-28`

## Repo-Local Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `src/omega/quant/portfolio/execution_sim.py`
- `src/omega/quant/execution/market_impact.py`
- `src/omega/quant/execution/smart_execution.py`
- `tests/quant_test_execution_sim.py`
- `.ly_state/session/l2_role14_b1_simulator_reconcile_20260728.md`
- `.ly_state/session/l2_role14_sharpe_tcost_phase2_simfix_20260629.md`

## Forbidden-Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: no authoritative reliance.
- `.openclaw\skills`: no authoritative reliance.
- `C:\Users\GHC\.agents`: no authoritative reliance.
- `.codex\memories`: no authoritative reliance.

## Reproduction

Command:

```text
python -m pytest tests/quant_test_execution_sim.py::test_slippage_scales_with_capital tests/quant_test_execution_sim.py::test_dynamic_capital_tracking_changes_slippage_path -vv -s
```

Result: **2 failed**.

- `test_slippage_scales_with_capital`: actual `br_big["total_slippage_cost"] = 0.08894078761415344`; actual `br_small["total_slippage_cost"] = 0.01971858410132494`; ratio `4.51x`, expected `> 50x`.
- `test_dynamic_capital_tracking_changes_slippage_path`: `ExecutionSafetyError`; first bar reports `Cumulative slippage 63.03 bps exceeds kill-switch limit 50.00 bps`.

## Root Cause

The current `src/omega/quant/portfolio/execution_sim.py:407-427` is an uncommitted concurrent rewrite. It replaced the prior simulator formula with `calculate_nonlinear_slippage()`.

1. `calculate_nonlinear_slippage()` in `src/omega/quant/execution/market_impact.py:27-40` always uses `sqrt(order_volume / daily_volume)` and does not accept or read `VNCostModel.slippage_nonlinear_exp`. Therefore `VNCostModel(slippage_nonlinear_exp=1.0)` in both tests is ignored. Capital scaling becomes sublinear rather than the test's exponent-1 linear scaling.
2. The helper adds a fixed spread term (`theta_1 * spread`) to every traded name. That non-scaling term further compresses the large-AUM/small-AUM ratio below the test's `50x` threshold.
3. The rewrite passes `cost_model.slippage_k` as helper `volatility`, changing the simulator contract: `slippage_k` is no longer the direct impact coefficient used by the previous calibrated participation formula.
4. The rewrite adds `enforce_slippage_kill_switch(slippage_t * 10000.0)` at line 455. The test's first bar legitimately produces more than 50 bps under the new helper path, so the exception is raised before line 465 updates `running_capital`. This prevents the dynamic path from reaching the intended capital-tracking comparison.

## Attribution

Failures are attributable to the current uncommitted concurrent modification of `src/omega/quant/portfolio/execution_sim.py`, not to the focused tests. `git diff` shows `202` additions and `25` deletions in that file; the relevant lines 407-427 and 455 are uncommitted. The focused test file has no diff.

Historical implementation used the `VNCostModel.slippage_nonlinear_exp` branch, reference-participation calibration, and direct `slippage_k * participation_eff`. The current rewrite removed that behavior. Existing reconciliation evidence dated `2026-07-28` independently records the same two failures and `NEEDS_FIX`.

## Minimal Safe Fix Recommendation

Restore the simulator's cost-model contract in `apply_realistic_tc`:

- Compute participation from `trade_vnd / daily_adv`.
- Apply `cost_model.slippage_nonlinear_exp`, including the existing `slippage_k_ref_participation` calibration.
- Compute slippage as calibrated `cost_model.slippage_k * participation_eff * abs(delta_w)` so AUM scaling remains linear when exponent is `1.0`.
- Do not introduce an unconditional kill-switch call in this portfolio simulator path; if the safety check is required, pass an explicitly defined cumulative/portfolio-level policy that does not abort the deterministic simulator regression before capital tracking.
- Preserve PIT use of supplied prior-bar ADV, `running_capital` update after `net_t`, and existing breakdown fields.

No source or test change was made in this session. No audit or approval performed.

## Required Verification After L2 Fix

```text
python -m pytest tests/quant_test_execution_sim.py::test_slippage_scales_with_capital tests/quant_test_execution_sim.py::test_dynamic_capital_tracking_changes_slippage_path -q
python -m pytest tests/quant_test_execution_sim.py tests/test_pipeline_v2.py tests/phase35/test_hybrid_regime_cost_reduction.py -q
```

## Verdict

`NEEDS_FIX`
