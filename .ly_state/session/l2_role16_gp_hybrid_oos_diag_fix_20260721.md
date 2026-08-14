# L2 Report - gp_hybrid_oos_diag_integration

## Scope
- `scripts/run_hybrid_alpha_evolution.py`
- `tests/test_hybrid_alpha_real_market.py`

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
- Scan targets: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: matches exist only in repo-local policy, audit, plan, memory, or report files as non-authoritative scan evidence. No authoritative role/skill loading used any forbidden path. No forbidden path was read as source for this task.

## Changes
- Added configurable promotion threshold plumbing via 5 CLI flags: `--min-ic`, `--min-icir`, `--min-pnl-score`, `--min-dsr`, `--max-corr`.
- Replaced hard-coded promotion threshold usage with runtime threshold config passed into selection and persisted into output JSON `thresholds`.
- Added fail-closed float validation for non-negative thresholds and bounded `--max-corr` (`<= 1.0`).
- Added `lockbox_oos_report.top_candidates_diagnostic` for all selected top candidates, deterministically sorted by full-precision key `(-dsr, -mean_ic, ast_depth, formula_hash)`.
- Preserved OOS isolation: diagnostic lockbox telemetry is post-selection only and does not influence ranking, tuning, or promotion.
- Kept full reuse of existing GP core modules: `hybrid_alpha_miner`, `genetic_programming`, `llm_symbolic_synthesizer`.

## Tests
- `pytest tests/test_hybrid_alpha_real_market.py -q` - PASS (`26 passed`)
- `python -m pytest tests/test_hybrid_alpha_real_market.py -q` - PASS (`26 passed`)

## Additional Verification
- `checklist.py` not present at repo root.
- `verify_all.py` not present at repo root.

## Notes
- No required repo-local role/skill source was missing.
- Work stayed within requested scope.
