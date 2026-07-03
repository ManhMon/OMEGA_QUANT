# L2 Report: fast_optimization_combo fix2

## Role
- role_id: 14
- role_name: `data-scientist`
- tier: 2
- platform: `OpenCode`
- sod_boundary: `implementation-only, test required, no self-approval, submit to Tier3`

## Repo-Local Role/Skill Files Read
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

## Forbidden Path Scan Result
No authoritative reliance on forbidden role/skill sources. `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` were not used as authoritative sources in this session. Repo scan found string mentions in existing documentation, reports, and enforcement code only; those mentions are non-authoritative reference/scan evidence only.

## Scope
- `scripts/backtest_hybrid_regime.py`
- `src/omega/quant/portfolio/tail_controls.py`
- `src/omega/quant/pipeline/overlays/tail_control.py`
- `src/omega/quant/pipeline_v2.py`

## Changes Implemented
1. Reverted `LongOnlyConcentratedOverlay` in `scripts/backtest_hybrid_regime.py` to simple per-row top-k behavior.
2. Removed hysteresis retention logic from that overlay.
3. Changed CLI default `--risk-latent-gmm-bear-dampening` from `0.15` to `0.45` in `scripts/backtest_hybrid_regime.py` to match signature/scenario defaults.
4. Updated `tests/phase35/test_hybrid_regime_backtest_perf.py` to validate simple top-k behavior and tie truncation instead of hysteresis behavior.

## Files Modified
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Verification
- Command: `pytest tests/phase35/test_hybrid_regime_backtest_perf.py`
- Result: `52 passed, 22 warnings in 6.87s`
- Notes: warnings were pre-existing runtime/deprecation/cache warnings; no test failures.

## Outcome
- Audit finding 1 fixed: concentrated overlay restored to original simple top-k form.
- Audit finding 2 fixed: CLI default now matches `0.45` downstream default.
- PIT/backtest surface unchanged outside requested scope.

## Not Done
- No audit/approval performed.
- No broader test suite executed beyond targeted impacted phase35 suite.
