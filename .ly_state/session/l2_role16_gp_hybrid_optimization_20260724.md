# L2 Report: gp_hybrid_optimization

- Session ID: `l2_role16_gp_hybrid_optimization_20260724`
- Role: `16 machine-learning-engineer`
- Gate: `gp_hybrid_optimization`
- Date: `2026-07-24`
- Scope:
  - `src/omega/quant/evolution/hybrid_alpha_miner.py`
  - `src/omega/quant/evolution/llm_symbolic_synthesizer.py`
  - `tests/test_hybrid_alpha_real_market.py`

## Repo-Local Role/Skill Files Read

- Role:
  - `.agents/agent/machine-learning-engineer.md`
- Skills:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/ml-dl-rl/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit`: not used
- `.openclaw\skills`: not used
- `C:\Users\GHC\.agents`: not used as authoritative source
- `.codex\memories`: not used

## Changes Implemented

1. `score_candidate()` synth injection
- Added optional `synth` parameter to `NestedCVObjective.score_candidate()`.
- `HybridAlphaMiner.run()` now constructs one `LLMSymbolicSynthesizer(provider="mock")` and reuses it across candidate scoring.
- Preserved fallback local construction when `synth` not provided.

2. Candidate memory release
- Added `CandidateRecord.clear_signals()`.
- Clears `_fold_values`.
- Clears dynamic `_alpha_values` when present.
- `HybridAlphaMiner.run()` now drops non-viable candidates early and calls `clear_signals()` immediately for rejected candidates.

3. In-memory sub-tree execution cache
- Added `LLMSymbolicSynthesizer._subtree_cache`.
- Added `clear_execution_cache()`.
- Added `_execute_tree_cached()` with per-group cache keying.
- `execute_node_grouped()` now evaluates trees through cached sub-tree execution instead of recomputing identical AST fragments repeatedly.
- Reused existing protected math/time-series helpers from `genetic_programming.py` to preserve behavior.

4. Unit tests updated
- Added regression tests for:
  - candidate signal cleanup
  - injected synthesizer reuse
  - duplicate sub-tree in-memory caching
  - rejected candidate buffer release in `HybridAlphaMiner.run()`

## Verification

- Command: `pytest tests/test_hybrid_alpha_real_market.py -q`
- Result: `37 passed`

- Command: `pytest tests/quant_test_closed_loop_cpcv_fixes.py -k "score_candidate or HybridAlphaMiner" -q`
- Result: completed without failures in selected scope

## Notes

- No out-of-scope source files modified.
- No audit or approval performed.
