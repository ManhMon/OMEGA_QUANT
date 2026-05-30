# Phase 4 LSTM Spec

**Date**: 2026-05-30 07:00 GMT+7
**Status**: Design draft, awaiting user sign-off
**Baseline**: Phase 3.11 (SR_ann 3.185 @ 1B, fold_DSR 0.4452)

## Goal
Stack a small LSTM on top of Phase 3.11 features to capture sequence dependencies the linear Ridge model misses. Acceptance bar: fold_DSR > 0.50 at 1B without breaking PIT/SOD.

## Hardware constraints (verified)
- PyTorch 2.11 CPU-only (no CUDA)
- 24GB RAM, 12-core i5-12500
- Total compute budget per CPCV run: target < 30 min wall time

## Data shapes
- Panel 2019-2024: 2.05M rows, 1500 unique tickers, 1500 trading days
- Filtered universe (walk-forward 50/year): ~250 daily samples per fold, 167 unique tickers across 5 years
- 114 alpha features per (ticker, date) after Phase 3.11 pipeline

## Architecture (proposal A: per-bar regression)
- Input: sequence of 60 daily bars per (ticker, date) = (60, 114) tensor
- LSTM: 1 layer, hidden=64, dropout=0.2 -> projection to scalar
- Output: same target as Phase 3.11 (forward 20d return, demedian)
- Params: ~50k weights -> < 200KB model, fits in RAM easily

## Architecture (proposal B: cross-sectional encoder)
- Skipped for v1 (too expensive without GPU)

## CPCV integration
- 45 folds * (train + predict) on CPU is the bottleneck
- Strategy: train ONCE on full train_idx per fold, predict on test_idx
- Estimated cost: 45 folds * ~30s training = ~22 min total
- Use `torch.set_num_threads(4)` to avoid oversubscription with pandas

## PIT discipline
- Sequence built from features at t-60..t-1, target at t+20 (still demedian per-date)
- z-score on TRAIN ONLY per fold (mu, sd from X_tr like Phase 3.10)
- No normalization across the test split

## Falsification plan
- y-shuffle within date: SR should collapse to ~0
- LSTM-vs-Ridge sanity: ensemble (avg) should not be worse than Ridge alone
- Compute budget cap: kill if any fold > 90s

## Tests
- Unit: shape sanity, deterministic seed, gradient flow
- Integration: 1-fold smoke (5 tickers, 1 year) under 30s
- Falsification: 1 full WF run with shuffle_y

## Files
- `packages/quant/src/omega/quant/models/lstm_alpha.py` (new)
- `packages/quant/tests/test_lstm_alpha.py` (new)
- `scripts/backtest_v2_lstm.py` (new, sibling of `backtest_v2_cpcv.py`)

## Open decisions for user
1. Lookback window: 60d (default) vs 20d (matches label horizon) vs 252d (full year) ?
2. Hidden size: 32 / 64 / 128 ?
3. Use Phase 3.11 alphas as input OR raw OHLCV + a few engineered features ?
4. Single LSTM vs Ridge+LSTM ensemble vs LSTM-only ?
5. Per-fold retrain (clean PIT) vs warm-start from previous fold (faster) ?

Recommend defaults: 60d / 64 / Phase 3.11 alphas / Ridge+LSTM ensemble (avg) / per-fold retrain.

## Next concrete steps after sign-off
1. Implement `lstm_alpha.py` with deterministic training loop
2. Run 1-fold smoke (5 tickers, 1 year)
3. Run full CPCV (45 folds), capture wall time
4. Compare fold_DSR vs Phase 3.11 baseline
5. Codex L3 audit per SOD

## Risk: CPU-only training time
If 45-fold full WF exceeds 60 min, fallback to:
- Reduce hidden=32
- Reduce lookback=20
- Train every K=3 folds with rolling reuse
- Last resort: defer to GPU-equipped machine
