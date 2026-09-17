# L2 Report: llm_alpha_deep_audit

## Role
- role_id: 16
- role_name: `machine-learning-engineer`
- tier: 2
- platform: `OpenCode`
- gate: `llm_alpha_deep_audit`

## Scope
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py`
- `scripts/genetic_alpha_evolution_v4.py`

## Repo-Local Role/Skill Files Read
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\machine-learning-engineer.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\python-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\clean-code\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\testing-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\performance-profiling\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\systematic-debugging\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\ml-dl-rl\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\backtesting-pit-safety\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\vietnam-market-data\SKILL.md`

## Forbidden Path Scan Result
- No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## Changes
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py`
- Added token reconstruction check using a broader `token_pattern` so dropped punctuation/brackets fail with `Formula contains invalid or unmatched characters`.
- Added AST denylist handling so attribute/subscript/lambda-style syntax fails with `Disallowed syntax node: <NodeName>`.
- Added syntax-error classification so valid prefix expressions followed by extra payload fail with `Unexpected trailing tokens`.
- Preserved explicit rejection for bare infix formulas.
- `scripts/genetic_alpha_evolution_v4.py`
- Normalized liquidity mask handling in `_batch_fold_ir_scores` so fold-local, full-row, and cached fallback shapes align before broadcast masking.
- Guarded neutralization cache lookup with `.get(...)` for folds without a cached neutralization payload.

## Test Evidence
- Targeted:
- `pytest tests/quant_test_infinite_evolution.py -k formula_safety_parser` -> `8 passed`
- `pytest tests/test_genetic_alpha_evolution_v4.py -k "rule5_batch_fold_ir_matches_scalar_within_tolerance or rule5_batch_fold_ir_matches_scalar_random_probe"` -> `2 passed`
- Full suite:
- `pytest` -> `2695 passed, 0 failed`, exit `0`

## Notes
- Full-suite warnings remain non-blocking. Main recurring warning source: `.pytest_cache` path creation conflict on Windows.
