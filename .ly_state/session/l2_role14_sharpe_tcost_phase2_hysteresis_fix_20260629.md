# L2 Report — SHARPE_TCOST_PHASE2_HYSTERESIS_FIX

- Session: `l2_role14_sharpe_tcost_phase2_hysteresis_fix_20260629`
- Role: `14 data-scientist`
- Gate: `SHARPE_TCOST_PHASE2_HYSTERESIS_FIX`
- Scope: governance-only follow-up gate for the hysteresis-line fix in `scripts/backtest_hybrid_regime.py` and the direct buffered-rank regression test additions in `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Repo-Local Skill Source Evidence

- Role file read:
  - `.agents/agent/data-scientist.md`
- Skill files read:
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

- Forbidden-path scan result for authoritative role/skill loading in this session:
  - `.gemini\antigravity-ide\scratch\ag-kit` -> non-authoritative; not used as a role source; not used as a skill source.
  - `.openclaw\skills` -> non-authoritative; not used as a role source; not used as a skill source.
  - `C:\Users\GHC\.agents` -> non-authoritative; not used as a role source; not used as a skill source.
  - `.codex\memories` -> non-authoritative; not used as a role source; not used as a skill source.
- Result: no forbidden path was used as an authoritative source; all authoritative role/skill reads came from repo-local files under `.agents/agent` and `.agents/skills`.

## Isolated Gate Scope

- In-scope for this follow-up gate:
  - `scripts/backtest_hybrid_regime.py`: only the hysteresis-line fix.
  - `tests/phase35/test_hybrid_regime_backtest_perf.py`: only the direct buffered-rank regression test additions.
- Out-of-scope context only:
  - Any other existing modifications in those same files belong to prior Phase 2 work and are not part of `SHARPE_TCOST_PHASE2_HYSTERESIS_FIX`.
- Production source/test behavior change for this governance cleanup: none.

## Scoped Change Context

- `LongOnlyConcentratedOverlay.apply()` appended prior holdings ranked within `top_k + eviction_buffer`.
- Then `keep_symbols = keep_symbols[:active_target]` truncated back to `top_k`.
- Result: hysteresis buffer branch was ineffective; buffered prior holdings were still evicted.

## Scoped Evidence

1. `scripts/backtest_hybrid_regime.py`
   - Follow-up gate evidence covers only removal of the post-buffer truncation of `keep_symbols`.
   - Result: prior active holdings ranked within `top_k + eviction_buffer` are retained as intended.
   - PIT safety unchanged: logic uses only current-row ranks plus prior active set from previous processed row; no forward-looking data introduced.

2. `tests/phase35/test_hybrid_regime_backtest_perf.py`
   - Follow-up gate evidence covers only the added direct regression test:
      - `test_hysteresis_retains_prior_holding_ranked_outside_top_k_but_within_buffer`
   - Repro case:
      - Day 1 active set includes `A` in top 3.
      - Day 2 ranks move `A` to rank 4.
      - `top_k=3`, buffer=3, so `A` should remain active.
   - Expected active set on day 2: `{"A", "B", "C", "D"}`.

## Verification

### Focused regression subset

```text
python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k "LongOnlyConcentratedOverlay or hysteresis" -q
```

- Result: `5 passed`

### Full required test file

```text
python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -q
```

- Result: `52 passed`

## Notes

- Existing warnings observed during pytest:
  - package update notice (`vnai`)
  - existing deprecation warnings
  - existing pytest cache path warning on Windows
- These warnings are pre-existing/non-blocking for this scope.
