# Phase 3.4 Kickoff — Self-Evolution Alpha Discovery (GP)

## Purpose
Automate alpha discovery using Genetic Programming (GP) to find signals for T+3 and T+5 horizons, building on the Phase 3.1 baseline.

## Objectives
1. Implement a Genetic Programming engine to evolve alpha expressions.
2. Search space: primitives (RSI, MACD, Volume, Volatility) + operators (+, -, *, /, log, rank, delay).
3. Fitness criteria: Sharpe Ratio + Turnover Penalty + PIT Safety.
4. Target horizons: T+3 and T+5 (T-1 lag enforced).

## In-Scope Modules (Phase 3.4)
- `src/evolution/genetic_alpha.py`
  - Genome representation (tree-based or stack-based).
  - Genetic operators: Crossover, Mutation, Reproduction.
- `src/evolution/fitness.py`
  - Fitness evaluator with Sharpe/Turnover logic.
  - Integration with `src/pipeline/alpha_discovery_pipeline.py`.
- `tests/test_genetic_alpha.py`
  - Functional tests for GP operators and PIT compliance.

## Genetic Operators Constraints
- **Primitives**: `close`, `open`, `high`, `low`, `volume`, `returns`.
- **Functions**: `std(n)`, `mean(n)`, `max(n)`, `min(n)`, `rank()`, `delay(n)`.
- **Strict PIT**: Every evolved alpha must go through `enforce_t_minus_1_lag()`.
- **Complexity Penalty**: Penalize deep trees to prevent overfitting/overcomplication.

## Acceptance Tests (Phase Gate)
1. **GP Engine Integrity**: Verify crossover/mutation produces valid syntax trees.
2. **PIT Genome Test**: Ensure every evolved signal respects T-1 lag automatically.
3. **Fitness Monotonicity**: Higher Sharpe/Lower turnover must yield higher fitness score.
4. **Performance Benchmark**: Run 10 generations on 50 symbols in < 60s.

## Implementation Notes
- Use `gplearn` or custom lightweight vectorized tree evaluator.
- Seed population with Phase 3.1 indicators (RSI, MACD).
- Resulting alphas must be exported as human-readable expressions.
