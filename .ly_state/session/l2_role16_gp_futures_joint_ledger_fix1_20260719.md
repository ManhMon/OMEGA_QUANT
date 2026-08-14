# L2 Report: gp_futures_joint_ledger_fix1

- Role: `16 machine-learning-engineer`
- Gate: `gp_futures_joint_ledger_fix1`
- Date: `2026-07-19`
- Repo-local files read:
  - `.agents/agent/machine-learning-engineer.md`
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/ml-dl-rl/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`
- Forbidden path scan result: no authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

## Changes

- `src/omega/quant/portfolio/execution_sim.py`
  - Fixed `stock_notional_t` to roll prior stock sleeve only.
  - Added futures affordability down-scaling against cash, initial margin, trade costs.
  - Fixed forced futures liquidation to reduce position, release margin into cash.
- `scripts/run_weekly_evolution.py`
  - Restored promotion gating through canonical metric key `signal_pnl_score`.
  - Kept threshold intent at `IC > 0.01` and `signal_pnl_score > 0.08`.
- `tests/test_futures_joint_ledger.py`
  - Added coverage for affordability scaling, liquidation state transition, no double-count stock sleeve.
- `tests/test_evolution_metric_migration.py`
  - Added executable migration test for canonical metric promotion path.

## Verification

- Target tests executed after patch.
- Master compliance scripts not run in this session; role spec requires follow-up before final gate close:
  - `python checklist.py`
  - `python verify_all.py`
