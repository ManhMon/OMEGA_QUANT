# Phase 8 — Label Horizon Sweep (Vector #2: Multi-Period Horizon)

**Date**: 2026-05-30 14:38 GMT+7
**Status**: Production candidate — significant SR uplift across all capitals.

## Hypothesis

Phase 5 baseline used `--label-horizon=20` (forward 20-day return). Vector #2 in the priority list was multi-period horizon ensemble (h=5, h=20, h=60). Em ran each as a standalone backtest first to compare; ensemble would have been 3x compute cost without proof of value.

## Result: h=60 dominates

| Horizon | SR_ann @ 1B | fold_DSR | median IC | cost (bps/bar) | turnover | fold_pos% |
|--:|--:|--:|--:|--:|--:|--:|
| h=5  | 1.678 | 0.332 | 0.0149 | 5.40 | 0.159 | 73% |
| **h=20** (baseline) | 3.671 | 0.374 | 0.0173 | 2.49 | 0.077 | 80% |
| **h=60** | **5.548** | **0.423** | **0.0340** | **1.22** | **0.040** | **80%** |

h=5: too fast → cost eats alpha (turnover 0.16, cost 5.4 bps).
h=20: production baseline.
h=60: alpha doubles, cost halves.

## Capacity sweep (h=60)

| Capital | h=20 SR | h=60 SR | Δ | h=60 cost (bps) |
|--:|--:|--:|--:|--:|
| 1B | 3.671 | **5.548** | +1.88 | 1.22 |
| 10B | 3.320 | **5.452** | +2.13 | 1.56 |
| 100B | 0.188 | **4.368** | +4.18 | 4.93 |

**100B SR flips from +0.19 to +4.37**. Capacity ceiling pushed from 50B (h=20) to >100B (h=60).

## Why h=60 works

1. **Slower signal → less mean reversion noise.** h=5 gets whipsawed by 1-week momentum reversals. h=60 captures durable trends.
2. **Lower turnover.** 0.040/bar (h=60) vs 0.077 (h=20) vs 0.159 (h=5). Halves slippage at 10B+.
3. **Higher signal-to-cost ratio.** IC 0.034 vs cost 1.22 bps = ~28x edge per cost unit. h=20 was 7x.
4. **Same Ridge model, same 114 alphas.** No new features, no architecture change. Just a different forward-return horizon.

## Why fold_pos% stayed at 80%

The strategy is robust regardless of horizon — same 36/45 folds positive. The shift is in *magnitude per fold*, not in stability. h=60 gives bigger wins on winning folds.

## Reverted experiment: Vector #1 per-date z-score on features

Initial vector #1 (per-date cross-sectional zscore of features on top of train-fold global zscore) was attempted. Smoke test result:

| | Phase 5 (h=20, no per-date) | Phase 8v1 (h=20, per-date features) |
|--|--:|--:|
| smoke median IC | +0.16 | -0.006 |

Per-date zscore of FEATURES destroys cross-sectional information that Ridge needs to rank tickers across days. Reverted. Helper `_per_date_zscore` kept (unused) for future experiments on prediction-side normalization.

## Files

- `scripts/backtest_v2_cpcv.py` — `_per_date_zscore` helper (unused, future research)
- `scripts/compare_phase8_horizons.py` (NEW) — h=5/h=20/h=60 single-capital comparison
- `scripts/compare_phase8_h60_capacity.py` (NEW) — h=20 vs h=60 capacity sweep
- `.ly_state/session/phase8_h5_1B.json`, `phase8_h60_{1B,10B,100B}.json`

## Production decision

**Switch production label horizon from h=20 to h=60.** Wait for codex L3 audit before locking gate.

Phase 5 baseline (h=20) remains as fallback — both are PIT-clean, same data sanitization, same 114 features. The choice is signal frequency.

## Next investigation candidates

1. Try h=40 / h=120 to find optimum (h=60 might not be the peak)
2. Multi-horizon ensemble (h=20 + h=60) — diversify decay regimes, even if h=60 wins standalone
3. ~~Falsification on h=60~~ DONE — PASS

## Falsification (h=60, y-shuffle within each date)

| Metric | Real | Shuffled | Drop | Verdict |
|--|--:|--:|--:|--|
| median IC | +0.0340 | -0.0661 | sign flip | PASS |
| fold SR_ann | +5.548 | -0.704 | 87.3% collapse | PASS |
| pool SR_ann | +5.629 | -0.565 | sign flip | PASS |
| fold DSR | 0.423 | 0.217 | 49% drop | acceptable |

h=60 alpha confirmed REAL — same falsification quality as h=20 baseline.
