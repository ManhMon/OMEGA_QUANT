# L2 Report — role14 data-scientist

- Session: `l2_role14_penalty_and_rebalance_fix2_20260701`
- Gate: `HYBRID_REGIME_PENALTY_AND_REBALANCE_20260701`
- Role: `14 data-scientist`
- Scope: `scripts/backtest_hybrid_regime.py`, `src/omega/quant/pipeline/overlays/rebalance_frequency.py`, `tests/phase35/test_regime_features.py`

## Repo-Local Files Read

- Role file: `.agents/agent/data-scientist.md`
- Skill file: `.agents/skills/python-patterns/SKILL.md`
- Skill file: `.agents/skills/clean-code/SKILL.md`
- Skill file: `.agents/skills/testing-patterns/SKILL.md`
- Skill file: `.agents/skills/systematic-debugging/SKILL.md`
- Skill file: `.agents/skills/performance-profiling/SKILL.md`
- Skill file: `.agents/skills/quant-research/SKILL.md`
- Skill file: `.agents/skills/vietnam-market-data/SKILL.md`
- Skill file: `.agents/skills/backtesting-pit-safety/SKILL.md`
- Skill file: `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan Result

- Scan completed in repo only.
- Forbidden path strings do exist in repo docs/tests/tooling as references.
- No forbidden path was used as an authoritative role/skill source for this task.
- Non-authoritative paths not used as source: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

## Changes

- `scripts/backtest_hybrid_regime.py`
- Routed `train_fold_models()` feature selection through `select_alpha_features_by_penalized_ic(...)`.
- Added `alpha_turnover_penalty` arg to `train_fold_models()` and used `score = abs(ic) - alpha_turnover_penalty * turnover` for candidate ranking.
- Changed quota category sorting from absolute IC to penalized score with absolute-IC tie-break.
- Changed fallback global selection from absolute IC to penalized score.
- Stored selected lag columns in `composite_signal.attrs["selected_lag_cols"]` for regression verification.

- `src/omega/quant/pipeline/overlays/rebalance_frequency.py`
- No code change required. Existing bear-multiplier behavior already matched required test expectations.

- `tests/phase35/test_regime_features.py`
- Added regression coverage for `train_fold_models()` proving turnover penalty changes selected feature ordering in the real quota path.
- Kept direct helper-level turnover-penalty assertion.

## Verification

- Command: `pytest tests/phase35/test_regime_features.py tests/phase35/test_hybrid_regime_backtest_perf.py`
- Result: `58 passed, 22 warnings in 7.19s`

## Notes

- PIT preserved: turnover uses within-symbol first differences on train-only alpha history; selection still uses lagged train features for IC.
- No audit/approval performed.
