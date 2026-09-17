# GP Convergence Analysis - 2026-07-03

## Diagnosis

Root cause: `GeneticEngine.evolve()` evaluated the same initialized population every generation but never built a next generation. Selection, crossover, and mutation methods existed, but the loop did not call them. With stochastic 100k-row generation subsampling, the fixed population was re-scored on different samples, so the best expression could alternate between a few incumbents. That matches the observed IC oscillation from generation 1.

Secondary issues:
- V3 config used high tournament pressure (`tournament_size=5`) plus low elitism diversity, which accelerates takeover once breeding is enabled.
- Complexity penalty was depth-only, so large equivalent trees were not penalized enough.
- Hall of Fame allowed duplicate expressions within the same generation.
- V3 feature engineering computed `returns_5d` from same-day close and did not lag the feature block.

## Changes

- Added `_next_generation()` and call it after each non-final generation.
- Copied non-mutated individuals instead of reusing the same object.
- Added tree node-count penalty via `tree_size_penalty_weight`.
- Added stagnation early stop via `early_stopping_rounds=10`.
- Added diversity-aware tournament duplicate penalty via `tournament_diversity_weight`.
- De-duplicated Hall of Fame expressions.
- Excluded metadata keys such as `__date__` from generated terminals.
- Updated V3 script config:
  - `mutation_rate`: 0.35 -> 0.50
  - `tournament_size`: 5 -> 3
  - `elitism_count`: 2 -> 1
  - `diversity_threshold`: 0.4 -> 0.3
  - enabled tree size penalty, early stopping, tournament diversity penalty
- Mapped CLI backend alias `threads` to joblib backend `threading`.

## Leak Check: `log(returns_5d)`

`returns_5d = close.pct_change(5)` is backward-looking, so `log(returns_5d)` is not directly using `fwd_ret_5` or future prices. However, V3 previously left all feature columns unlagged, so same-day close/high/low/volume were available to expressions at the prediction row. That is not T-1 safe if signals are assumed tradeable at that date.

Fix: V3 now shifts all `FEATURE_COLS` by 1 row per ticker after feature construction. `log(returns_5d)` now means prior-row 5-day return, while target remains `fwd_ret_5`.

## Verification

Commands run:

```powershell
python -m py_compile scripts/genetic_alpha_evolution_v3.py src/omega/quant/evolution/genetic_engine.py
python -m pytest tests/quant_test_genetic_engine.py -q
python scripts/genetic_alpha_evolution_v3.py --rounds 1 --population-size 20 --generations 3 --workers 1
```

Results:

- `py_compile`: pass
- `pytest`: `8 passed`
- V3 smoke: pass after backend alias fix
  - train rows: 21,968
  - test rows: 11,067
  - tiny run best current TestIC: 0.0305
  - expression: `(neg((close - returns_5d)) + (returns_1d ts_rank 5))`

Note: smoke run generated untracked result artifacts; they were removed after verification to avoid polluting the worktree.
