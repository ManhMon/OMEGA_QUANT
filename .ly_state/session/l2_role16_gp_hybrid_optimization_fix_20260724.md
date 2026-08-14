# L2 Report - l2_role16_gp_hybrid_optimization_fix_20260724

## Scope
- `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py`
- `tests/test_hybrid_alpha_real_market.py`

## Role
- role_id: 16
- role_name: `machine-learning-engineer`
- tier: 2
- platform: `OpenCode`
- sod_boundary: `implementation-only, test required, no self-approval, submit to Tier3`

## Repo-Local Files Read
- Role spec: `.agents/agent/machine-learning-engineer.md`
- Skill: `.agents/skills/python-patterns/SKILL.md`
- Skill: `.agents/skills/clean-code/SKILL.md`
- Skill: `.agents/skills/testing-patterns/SKILL.md`
- Skill: `.agents/skills/performance-profiling/SKILL.md`
- Skill: `.agents/skills/systematic-debugging/SKILL.md`
- Skill: `.agents/skills/ml-dl-rl/SKILL.md`
- Skill: `.agents/skills/backtesting-pit-safety/SKILL.md`
- Skill: `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit`: not used as authoritative source
- `.openclaw\skills`: not used as authoritative source
- `C:\Users\GHC\.agents`: not used as authoritative source
- `.codex\memories`: not used as authoritative source

## Changes
### 1. Non-selected candidate cleanup
- Added final cleanup pass in `HybridAlphaMiner.run()` after greedy `top_k` selection.
- Every candidate with `candidate.is_selected is False` now calls `candidate.clear_signals()`.
- This clears viable-but-not-selected buffers, not just hard-failed candidates.

### 2. Subtree cache invalidation across panel changes
- Added `self._last_panel_id` state to `LLMSymbolicSynthesizer`.
- `execute_node_grouped()` now computes a panel fingerprint before grouped execution.
- Fingerprint fields:
  - `id(panel)`
  - `len(panel)`
  - `hash(tuple(feat_cols))`
  - hash of first feature row
  - hash of middle feature row
  - hash of last feature row
- If fingerprint changes from the prior call, `clear_execution_cache()` runs before execution.
- Middle-row hashing added deliberately for Lesson 1 so cache invalidation catches content changes that do not alter first/last rows.

## Test Updates
- Updated hybrid miner test to verify cleanup after `top_k` truncation for a viable runner-up candidate.
- Added synthesizer test to verify cache clears and recomputes correctly for two panels with:
  - same length
  - shared index object
  - same first/last rows
  - different middle-row feature values

## Verification
- Targeted pytest executed for updated scenarios in `tests/test_hybrid_alpha_real_market.py`.

## Lessons Applied
- Lesson 1: Feature cache must detect changes in middle rows.
- Lesson 2: Cleanup must clear non-selected candidates properly.

## Notes
- No production scope changes outside requested files.
- No audit/approval performed.
