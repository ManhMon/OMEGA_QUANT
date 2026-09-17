# L2 Reconciliation Evidence

- Session: `l2_role14_b1_cleanup_reconcile_20260728`
- Role: `14 data-scientist` (OpenCode L2)
- Gate: `SHARPE_TCOST_PHASE2_HYSTERESIS_FIX_CLEANUP`
- Purpose: fresh reconciliation evidence only; no implementation, audit, or approval.
- Scope: `.ly_state/session/l2_role14_b1_cleanup_reconcile_20260728.md` only.

## Repo-Local Source Contract

- `REPO_ROOT=C:\Users\GHC\repos\OMEGA_QUANT`
- `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- Role file read: `.agents/agent/data-scientist.md`
- Declared repo-local skill files read:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/quant-research/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan

- `.gemini\\antigravity-ide\\scratch\\ag-kit`: non-authoritative; not used.
- `.openclaw\\skills`: non-authoritative; not used.
- `C:\Users\GHC\.agents`: non-authoritative; not used.
- `.codex\\memories`: non-authoritative; not used.
- Result: no forbidden path used as an authoritative role or skill source.

## Fixture Contract

- Input: `.ly_state/session/fixtures/b1_hysteresis_cleanup_input_20260728.json`
- Golden: `.ly_state/session/fixtures/b1_hysteresis_cleanup_golden_20260728.json`
- Input SHA256: `9070a0f5aa97a3e60993ca568addec718da9510f9c8297011e58291dbd257b44`
- Golden SHA256: `c0e064b1a5c6d5011229660eb72b2302671c6f35af354d89055eb1c16091eb13`
- Window: `2024-01-01` to `2024-01-02`
- Symbols: `A,B,C,D`
- Config: `top_k=3`, `hysteresis=1`, `seed=0`
- Tolerance: absolute output delta `<=1e-12`

## Commit / Source / Test Hashes

- HEAD commit: `f1981af123db5b8d828696b5e7a14e3fe1117bce1`
- Source `scripts/backtest_hybrid_regime.py` SHA256: `07cccb545bf5d016b4a1d8446ce9c1171b67cb3fa1c427594eb68bebbc29dfe`
- Test `tests/phase35/test_hybrid_regime_backtest_perf.py` SHA256: `8f4d709cd4e9fd09ff8b974c54b12c426e15fa5f0aafc80199c5d4e9b273cb07`

## Fresh Deterministic Verification

1. Direct `LongOnlyConcentratedOverlay.apply()` replay using the input fixture, fixed literal weights, `top_k=3`, `hysteresis=1`.
   - Result: `PASS`
   - Output max absolute delta versus golden: `0.0`
   - Day 1 output: `[0.44444444444444453, 0.33333333333333337, 0.22222222222222227, 0.0]`
   - Day 2 output: `[0.125, 0.5, 0.37499999999999994, 0.0]`
   - Final state: `{"long_only_concentrated_prev_selected":["A","B","C"]}`
2. `python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k "LongOnlyConcentratedOverlay or hysteresis" -q`
   - Result: `4 passed`
   - Warnings: dependency update/deprecation notices; pytest cache path collision only.

## Reconciliation Boundary

- Exact fixture hashes verified.
- Deterministic replay verified.
- Hysteresis state verified.
- No source, test, fixture, phase-gate, manifest, or audit-report mutation performed.
- No L3 audit or approval performed.
- Status: `READY_FOR_INDEPENDENT_L3_REAUDIT`
