# L2 Report: gp_threads_n_jobs_ctor_fix

## Repo-Local Files Read
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

Forbidden path scan result:
- `.gemini/antigravity-ide/scratch/ag-kit`: not present under repo root
- `.openclaw/skills`: not present under repo root
- `C:\Users\GHC\.agents`: forbidden global path; explicitly non-authoritative; not scanned or used as a role/skill source
- `.codex/memories`: not present under repo root
- Result: no authoritative reliance on forbidden paths

## Scope
- `scripts/run_weekly_evolution.py`
- `tests/test_run_weekly_evolution_diverse_ctor.py`

## Diagnosis
- Runtime failure source: call-site drift in `scripts/run_weekly_evolution.py`, not config rename.
- `run_evolution(..., engine_type="diverse")` constructed `DiverseEvolutionConfig` with unsupported kwargs including `n_jobs`.
- Actual constructor in `src/omega/quant/evolution/diverse_alpha_evolution.py` accepts a narrow island-model config only: `population_per_island`, `generations`, `corr_threshold`, etc.
- The immediate failure was `TypeError: DiverseEvolutionConfig.__init__() got an unexpected keyword argument 'n_jobs'`, but multiple additional kwargs at the same call site were also incompatible.

## Changes
- Reduced the diverse-engine config construction in `scripts/run_weekly_evolution.py` to supported kwargs only.
- Preserved population sizing behavior by computing `population_per_island` from `population_size / n_islands`.
- Mapped `ortho_correlation_threshold` to `corr_threshold`, the only overlapping semantic control available in the target config.
- Left PIT logic and prior alt-features behavior untouched.

## Verification
- Narrow regression test:
  - `pytest tests/test_run_weekly_evolution_diverse_ctor.py`
  - Result: passed
- Lightweight reproduction of constructor path:
  - `python -c "from scripts.run_weekly_evolution import run_evolution; ... engine_type='diverse' ..."`
  - Result: returned `list 1`; no constructor `TypeError`

## Notes
- Existing file `tests/test_diverse_alpha_evolution_parallel.py` has an unrelated import-time collection failure against the current `diverse_alpha_evolution` module surface. Not changed here to preserve scope.
