# L2 Report: conformal_backtest_integration_and_sharpe_verification_fix3

## Scope
- `scripts/genetic_alpha_evolution_v3.py`

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
- `.gemini\antigravity-ide\scratch\ag-kit` -> not present
- `.openclaw\skills` -> not present
- `C:\Users\GHC\.agents` -> present, not used as authoritative source
- `.codex\memories` -> not present

## Changes Implemented
- Exposed CLI args in `scripts/genetic_alpha_evolution_v3.py`:
  - `--rounds`
  - `--population-size`
  - `--generations`
  - `--workers`
- Passed `--workers` through `GPConfig(..., n_jobs=args.workers)`.
- Refactored script into `main()` + helpers to support CLI entry and isolated registration logic.
- Added end-of-run DB registration using `DatabaseRegistry` against repo-relative `.ly_state/session/conformal_registry.sqlite`.
- Registered top-15 evolved models under names `genetic_alpha_v3_rank_XX`.
- Persisted per-model JSON artifacts in `data/stable/genetic_alpha_v3_models/` and stored artifact path + metrics in registry.

## Verification
- `python -m py_compile "scripts/genetic_alpha_evolution_v3.py"` -> pass
- `python "scripts/genetic_alpha_evolution_v3.py" --help` -> pass; args exposed
- `python "scripts/genetic_alpha_evolution_v3.py" --rounds 1 --population-size 8 --generations 1 --workers 1` -> timed out after data load; no code error observed before timeout
- `python -c "from datetime import datetime; import scripts.genetic_alpha_evolution_v3 as m; sample=[{'rank':1,'round':1,'train_IC':0.1,'test_IC':0.2,'hit_rate':0.55,'expression':'x','serialized_tree':'t'},{'rank':2,'round':1,'train_IC':0.09,'test_IC':0.19,'hit_rate':0.54,'expression':'y','serialized_tree':'u'}]; m.register_top_models(sample, datetime.utcnow().replace(tzinfo=None).astimezone()); print('ok')"` -> pass
- `python -c "import sqlite3; db=r'.ly_state/session/conformal_registry.sqlite'; con=sqlite3.connect(db); cur=con.cursor(); cur.execute('select count(*) from models where name like ?', ('genetic_alpha_v3_rank_%',)); print(cur.fetchone()[0]); con.close()"` -> `2`

## Master Script Contract Check
- `checklist.py` -> not found in repo
- `verify_all.py` -> not found in repo
- Result: unable to run role-specified master scripts because required repo files are missing

## Notes
- Registry helper verified directly without full GP runtime completion because the full script smoke run exceeded 120s during heavy data loading/evolution.
- Helper verification inserted 2 sample `genetic_alpha_v3_rank_*` rows into `.ly_state/session/conformal_registry.sqlite`.
