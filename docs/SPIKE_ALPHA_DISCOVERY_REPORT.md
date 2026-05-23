# Phase 3.1: Alpha Discovery Engine Spike Report

## Objective
Design alpha discovery module. Focus: signal scoring, decay tracking, T-1 lag enforcement.

## Results
- `spike_alpha_discovery.py`: Prototype built.
- `test_spike_alpha_discovery.py`: Unit tests pass.

## Architecture
1. **T-1 Lag Enforcement**: Mandatory `shift(1)` per ticker. Prevents look-ahead bias (PIT safe).
2. **Signal Scoring**: Cross-sectional Z-score per date. Normalizes features across universe.
3. **Decay Tracking**: Exponential Moving Average (EMA) with configurable half-life. Models signal decay.
4. **Vectorization**: 100% Pandas operations. No loops over rows.

## Next Steps
- Main agent review.
- Integrate to OMEGA_QUANT codebase.
- Audit by Role 16 / 20.
