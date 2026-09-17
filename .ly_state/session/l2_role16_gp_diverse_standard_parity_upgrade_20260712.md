# L2 Report - Role 16 - GP Diverse Engine Standard Parity Upgrade

- Session ID: `l2_role16_gp_diverse_standard_parity_upgrade_20260712`
- Gate: `GP_DIVERSE_ENGINE_STANDARD_PARITY`
- Role: `16 machine-learning-engineer`
- Scope: `src/omega/quant/evolution/diverse_alpha_evolution.py`, `scripts/run_weekly_evolution.py`

## Repo-Local Files Read

- .agents/agent/machine-learning-engineer.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/ml-dl-rl/SKILL.md
- .agents/skills/backtesting-pit-safety/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md

## Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit`: no reliance.
- `.openclaw\skills`: no reliance.
- `C:\Users\GHC\.agents`: no reliance.
- `.codex\memories`: no reliance.
- Repo grep found mentions in historical memory/report files only; none used as authoritative role/skill sources for this task.

## Changes

- Replaced legacy diverse candidate scoring path with standard-engine-backed scoring in `src/omega/quant/evolution/diverse_alpha_evolution.py`.
- Added lossless diverse-node to standard `GPNode` conversion helper and reused `GPIndividual._execute_tree()`.
- Reused standard `GPConfig`, `_compute_time_fold_ir()`, `_neutralize_cross_section()`, `_batch_neutralize_cross_section()` infrastructure via standard-engine evaluation inputs.
- Added diverse config support for `neutralize_size_sector`, `use_time_fold_ir`, `time_folds`, `fold_ir_std_floor`, `min_observations`, `ortho_baseline_set`, `ortho_penalty_weight`, `ortho_correlation_threshold`.
- Switched diverse candidate expression serialization to standard `GPNode.to_string()` for parity.
- Updated diverse quality/diversity ranking to use standard-engine-derived fitness when available.
- Expanded `_convert_diverse_node()` in `scripts/run_weekly_evolution.py` to preserve `abs` and `neg` standard operators.
- Threaded standard parity settings from `run_evolution(..., engine_type="diverse")` into `DiverseEvolutionConfig`.
- Propagated standard fitness from diverse candidates into returned Hall of Fame individuals.
- Hardened embargo flow in `evaluate_and_promote()` so embargo-blocked alphas are removed before promotion serialization.

## Tests

- Passed: `pytest tests/test_diverse_alpha_evolution_parallel.py -q`
- Passed: `pytest tests/test_genetic_alpha.py -q`
- Passed: `pytest tests/test_diverse_alpha_evolution_parallel.py tests/test_genetic_alpha.py tests/test_genetic_alpha_evolution_v4.py -q`
- Attempted: `pytest -q`
  - Output was truncated by tool limits before completion.
  - No failure lines were captured in the visible output.
  - Final exit code could not be confirmed from truncated tool output.

## Added/Updated Test Coverage

- `tests/test_diverse_alpha_evolution_parallel.py`
  - diverse-to-standard `GPNode` conversion parity
  - standard time-fold/ortho-backed diverse candidate scoring
- `tests/test_genetic_alpha.py`
  - embargo-blocked promotions are excluded before serialized output

## Notes

- Windows worker safety preserved: no new process fan-out added; existing caps remain.
- Standard parity path intentionally does not invent new diverse operators beyond standard-engine support already present in scope.
- `sign` was not mapped into standard conversion because `genetic_engine.GPIndividual._execute_tree()` does not support it today; mapping left unchanged rather than widening standard-engine scope in this gate.
