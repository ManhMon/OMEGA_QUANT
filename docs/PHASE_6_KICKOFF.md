# Phase 6 Kickoff — Memory & Evolution Engine Migration

## Purpose
Migrate Memory & Evolution Engine from legacy V21 system into `omega.observability` and `omega.evolution` packages.

## Objectives
1. Memory compression and retrieval with semantic metadata.
2. Evolution engine for hypothesis generation and promotion workflow.
3. Continuous learning loop integration hooks.

## In-Scope Modules
- `packages/observability/src/omega/observability/neural_memory.py`
- `packages/quant/src/omega/quant/evolution_engine.py`
- `tests/phase6/test_neural_memory.py`
- `tests/phase6/test_evolution_engine.py`

## Constraints
- PIT safety: no future data usage in memory snapshots.
- Determinism for same input/state.

## Acceptance Tests
1. Memory snapshot store/retrieve/expire.
2. Evolution hypothesis generation deterministic with seed.
3. Promotion logic only accepts improved candidates.
4. Continuous loop logs decisions with timestamped audit trail.
