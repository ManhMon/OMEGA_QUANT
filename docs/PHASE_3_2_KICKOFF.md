# Phase 3.2 Kickoff — Portfolio Optimization & Promotion Gate

## Purpose
Kick off Phase 3.2 to bridge signal generation (Phase 3.1) with portfolio construction and institutional-grade model promotion.

## Objectives
1. Implement Portfolio Optimizer (Mean-Variance / Risk-Parity baseline).
2. Establish Promotion Gate enhancements (Tiered validation: Dev → Staging → Prod).
3. Ensure PIT (Point-In-Time) consistency across portfolio weight generation.
4. Enforce strict SOD (Segregation of Duties) in promotion workflow.
5. Integrate Phase 3.1 alpha signals into portfolio construction pipeline.

## In-Scope Modules (Phase 3.2)
- `packages/quant/src/omega/quant/portfolio_optimizer.py`
  - Portfolio weight calculation (Mean-Variance, Risk-Parity, Equal-Weight baselines).
  - Risk constraint enforcement (max concentration, sector limits).
  - Turnover control and rebalancing logic.
  - Vectorized NumPy/Pandas implementation for performance.

- `packages/core/src/omega/core/promotion_gate.py`
  - Model tier management (Paper → Shadow → Live).
  - Statistical threshold checks for promotion eligibility.
  - Audit trail logging for state transitions.
  - Integration with Phase 2.3 `promotion.py` for embargo/window validation.

## Phase 3.1 Completion Reference
Phase 3.1 delivered 5 approved modules:
- `alpha_discovery.py` — Alpha signal generation primitives.
- `alpha_primitives.py` — Core statistical transforms (rolling, momentum, mean-reversion).
- `expression_generator.py` — Symbolic expression building for alpha factors.
- `label_engine.py` — Forward-looking label generation (T+1, T+3, T+5 horizons).
- `pit_guard.py` — PIT safety guardrails and leakage detection.

All modules passed PIT safety tests and contract validation.

## PIT Safety & Institutional Constraints
- **Causal Portfolio:** Portfolio weights at time `t` must only use data/signals available at `t-1`.
- **Signal Causality:** Alpha signals from Phase 3.1 must be T-1 safe (verified in Phase 3.1 tests).
- **Promotion Integrity:** Models cannot self-promote; external validation (Audit Agent L3) required.
- **Resource Constraints:** Optimization must fit within 4GB RAM envelope for large universes (500+ assets).
- **Vectorized Performance:** Use NumPy/Pandas vectorization; no Python loops in hot paths.
- **Determinism:** Identical input snapshot + config → identical portfolio weights.

## Acceptance Tests (Phase Gate)
1. **Portfolio PIT Test**
   - Verify portfolio weights at `t` computed only from signals/data timestamped `<= t-1`.
   - Assert no correlation between weight generation and future returns beyond expected alpha.

2. **Signal Integration Test**
   - Verify Phase 3.1 alpha signals feed correctly into portfolio optimizer.
   - Assert optimizer respects signal strength (higher alpha → higher weight).

3. **Promotion Flow Test**
   - Validate model transition from `Shadow` to `Live` only when:
     - Metric threshold met (IC > 0.1, Sharpe > 1.5).
     - Embargo period satisfied.
     - Auditor sign-off present (SOD: maker ≠ checker).

4. **Turnover Constraint Test**
   - Assert optimizer respects maximum turnover limits (e.g., 20% per rebalance).
   - Verify rebalancing frequency aligns with signal update cadence.

5. **Optimization Convergence Test**
   - Verify optimizer converges within time limits (< 30s for 100+ assets).
   - Assert solution quality (Sharpe improvement vs. equal-weight baseline).

6. **Determinism Test**
   - Run portfolio optimizer twice on same fixture; assert byte/array equality of weights.

## Implementation Notes
- **Portfolio Optimizer:**
  - Use `scipy.optimize` or `cvxpy` for convex optimization.
  - Implement constraint builder for sector/concentration limits.
  - Cache covariance matrix updates for efficiency.

- **Promotion Gate:**
  - Extend Phase 2.3 `promotion.py` with tier-based state machine.
  - Log all transitions to `.ly_state/session/audit_log.jsonl`.
  - Fail-closed: reject promotion on any validation failure.

- **Integration:**
  - Portfolio optimizer consumes alpha signals from Phase 3.1 pipeline.
  - Promotion gate validates portfolio backtest metrics before tier advancement.

## Non-Goals (This Kickoff)
- Live execution, order routing, or slippage modeling.
- Hyperparameter optimization or meta-strategy selection.
- Real-time risk monitoring or intraday rebalancing.

## Done Criteria for Kickoff Artifact
- Objectives documented and unambiguous.
- Module list documented with clear responsibilities.
- Acceptance tests documented with pass/fail criteria.
- PIT safety constraints documented.
- Phase 3.1 completion reference included.
- Integration points with Phase 3.1 signals defined.
