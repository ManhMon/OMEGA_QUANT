# L2 Report: gp_hybrid_llm_db_persistence

- Session ID: `l2_role16_gp_hybrid_llm_db_persistence_20260723`
- Role: `16 machine-learning-engineer`
- Gate: `gp_hybrid_llm_db_persistence`
- Scope:
  - `scripts/run_hybrid_alpha_evolution.py`
  - `scripts/run_weekly_evolution.py`
  - `tests/test_hybrid_alpha_real_market.py`
  - `tests/test_run_weekly_evolution_diverse_ctor.py`

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
- `.agents/AGENTS.md`

## Forbidden Path Scan Result

- No authoritative role/skill loading from forbidden paths.
- Not used as authoritative sources:
  - `.gemini\antigravity-ide\scratch\ag-kit`
  - `.openclaw\skills`
  - `C:\Users\GHC\.agents`
  - `.codex\memories`

## Implemented

- Added hybrid LLM promoted-factor persistence into SQLite `model_registry` via canonical `DatabaseRegistry` targeting repo-relative `/.ly_state/session/conformal_registry.sqlite`.
- Stored promoted hybrid factor artifacts under repo-relative `/.ly_state/session/hybrid_alpha_registry/`.
- Persisted risk-adjusted selection evidence into DB metrics payload, including:
  - formula / formula_hash
  - validation metrics
  - lockbox metrics
  - thresholds
  - feature_columns
  - provider
  - neutralization flag
- Added payload evidence block `model_registry_persistence` to `run_hybrid_alpha_evolution.py` output.
- Added orthogonal baseline source `--orthogonalize hybrid_db` in `run_weekly_evolution.py`.
- Implemented DB-backed baseline loading from `conformal_registry.sqlite` using latest ready record per hybrid factor model name.
- Preserved fail-fast behavior: `ValueError` when orthogonalization is enabled and zero baseline signals load.

## Tests Added/Updated

- `tests/test_hybrid_alpha_real_market.py`
  - verified promoted hybrid factors persist into canonical SQLite registry
- `tests/test_run_weekly_evolution_diverse_ctor.py`
  - verified `hybrid_db` loads DB baselines
  - verified `main()` fails fast when `hybrid_db` yields zero baselines
  - verified CLI accepts `--orthogonalize hybrid_db`

## Verification

- Command:
  - `pytest tests/test_hybrid_alpha_real_market.py tests/test_run_weekly_evolution_diverse_ctor.py`
- Result:
  - `37 passed, 8 warnings in 35.70s`

## Notes

- Used repo-relative paths only.
- No audit/approval performed.
