# L2 Report — B1 Hysteresis Cleanup Oracle

- Session: `l2_role14_b1_cleanup_oracle_20260728`
- Role: `14 data-scientist`
- Gate: `B1_HYSTERESIS_CLEANUP_ORACLE`
- Status: `READY_FOR_L3_AUDIT`; no self-approval.
- Scope: exactly two fixture JSON files and this L2 report.

## Entrypoint

- `scripts/backtest_hybrid_regime.py:95-140`
- Class/function: `LongOnlyConcentratedOverlay.apply()`
- Invocation: `LongOnlyConcentratedOverlay(top_k=3, hysteresis=1).apply(weights, pd.DataFrame(), state)`
- Behavior exercised: prior `A` is rank 4 on day 2, retained because `top_k + hysteresis = 4`; output remains normalized across `A`, `B`, `C`.

## Fixtures

- Input: `.ly_state/session/fixtures/b1_hysteresis_cleanup_input_20260728.json`
- Golden: `.ly_state/session/fixtures/b1_hysteresis_cleanup_golden_20260728.json`
- Date range: `2024-01-01` to `2024-01-02`
- Symbols: `A`, `B`, `C`, `D`
- Seed: `0` (entrypoint is deterministic; no stochastic branch)
- Config: `{"hysteresis":1,"top_k":3}`
- Config canonical serialization: UTF-8 JSON, sorted keys, compact separators, no trailing newline
- Config SHA256: `b79445813bcf68afd918ac5a108453070df7adaeba3a3865fbbe9662dbeaa0d0`
- Tolerance: `1e-12` absolute per output value

## Canonical Hashes

- Input canonical serialization: UTF-8 JSON, sorted keys, compact separators, `ensure_ascii=true`; fixture JSON is semantically equivalent.
- Input SHA256: `cffb4875cfd1b8e1d233702e8a9b4c1e7a2eb9d8977a0b4bd558c1d68e81de72`
- Golden canonical serialization: UTF-8 JSON, sorted keys, compact separators, `ensure_ascii=true`; fixture JSON is semantically equivalent.
- Golden SHA256: `22934bb8cf1cccf3a81650cc52cd92e849e3cf5db0e12d1afeec3318960258f2`

## Verification

Command:

```text
python -c "import json, hashlib, pandas as pd, sys; sys.path.insert(0,'scripts'); from backtest_hybrid_regime import LongOnlyConcentratedOverlay; dates=['2024-01-01','2024-01-02']; symbols=['A','B','C','D']; weights=[[0.4,0.3,0.2,0.1],[0.1,0.4,0.3,0.2]]; overlay=LongOnlyConcentratedOverlay(top_k=3,hysteresis=1); state={}; out=overlay.apply(pd.DataFrame(weights,index=pd.to_datetime(dates),columns=symbols),pd.DataFrame(),state); assert abs(float(out.iloc[0,0])-0.44444444444444453) <= 1e-12; assert abs(float(out.iloc[1,0])-0.125) <= 1e-12; assert state['long_only_concentrated_prev_selected'] == ['A','B','C']"
```

- Result: pass; deterministic behavior exercised.
- No source, test, phase gate, manifest, or data file mutation.

## Repo-Local Role/Skill Sources Read

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

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative; not used.
- `.openclaw\skills`: non-authoritative; not used.
- `C:\Users\GHC\.agents`: non-authoritative; not used.
- `.codex\memories`: non-authoritative; not used.
- Result: no forbidden path used as an authoritative role or skill source.

## PIT / Determinism

- PIT: fixture is a pure current-row rank/state transition; no future data or market-data lookup.
- Determinism: fixed literal input, fixed config, seed recorded as `0`; repeated direct invocation produces the same output within `1e-12`.
- No `NEEDS_FIX`: current behavior is deterministically exercisable.
