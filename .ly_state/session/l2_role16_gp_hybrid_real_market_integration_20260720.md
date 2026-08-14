# L2 Report: gp_hybrid_real_market_integration

## Session
- role_id: 16
- role_name: machine-learning-engineer
- gate: gp_hybrid_real_market_integration
- date: 2026-07-20
- scope:
  - `scripts/run_hybrid_alpha_evolution.py`
  - `tests/test_hybrid_alpha_real_market.py`
  - `implementation_plan.md`

## Repo-Local Role/Skill Files Read
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan Result
- `.gemini/antigravity-ide/scratch/ag-kit/**`: not present in repo scan
- `.openclaw/skills/**`: not present in repo scan
- `.codex/memories/**`: not present in repo scan
- `C:\Users\GHC\.agents`: exists globally, treated as non-authoritative only, not read for role/skill loading

## Implemented
- Added `scripts/run_hybrid_alpha_evolution.py`.
- Real-market loader on `data/market_2015_now.parquet` with fail-closed schema checks for PIT metadata, `price_scale="VND"`, `adjusted="backward_adjusted"`, `available_at >= date + 1`.
- Per-ticker chronological `target_h5 = close[t+5] / close[t] - 1.0`.
- T-1 feature lag on model inputs (`open`, `high`, `low`, `close`, `volume`).
- Expanding walk-forward folds with hard-coded 5-session purge/embargo boundaries matching implementation plan fold windows.
- OOS lockbox support for `2024-04-01` to `2026-06-30`, excluding final 5 terminal sessions from evaluation.
- Direct AST allowlist validation on selected GP trees using repo operators/terminals, avoiding infix-string roundtrip mismatch.
- Reproducible promotion metrics persisted to `.ly_state/session/evolved_alphas.json`:
  - Mean IC
  - ICIR
  - net dollar-neutral `signal_pnl_score`
  - DSR
  - pairwise correlation gate
- Deterministic tie-break: DSR desc, Mean IC desc, AST depth asc, formula hash asc.
- Updated `implementation_plan.md` with L2 implementation status note.

## Verification
- `pytest tests/test_hybrid_alpha_real_market.py -q`
  - result: PASS (5 tests)
- `python scripts/run_hybrid_alpha_evolution.py`
  - result: PASS
  - wrote `.ly_state/session/evolved_alphas.json`
  - promoted_count: 0

## Notes
- Risk-adjusted selection evidence persisted under `risk_adjusted_selection_evidence` in `.ly_state/session/evolved_alphas.json`.
- Real-market run produced zero promoted alphas under the requested thresholds. This is an outcome, not an execution failure.
- `as_of` in canonical parquet behaves as snapshot ingestion timestamp, not PIT availability timestamp; fail-closed checks were anchored to `available_at`, `price_scale`, and `adjusted`, which are the binding PIT/corporate-action fields in this dataset.

## Files Changed
- `implementation_plan.md`
- `scripts/run_hybrid_alpha_evolution.py`
- `tests/test_hybrid_alpha_real_market.py`
