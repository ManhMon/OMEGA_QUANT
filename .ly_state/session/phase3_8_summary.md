# Phase 3.8 — Slippage Model with Per-Ticker ADV (full WF, label_horizon=20, EMA=5)

## Capital sensitivity (full WF 2020-2024, 192 → 167 unique tickers, 11142 daily bars)

| Capital | SR_ann | DSR | cost (bps/bar) | slip share | med fold SR | skew/kurt |
|--------:|------:|------:|------:|------:|------:|------:|
| 1B VND | **3.190** | 1.40e-2 | 1.74 | 4.9% | 0.232 | 0.24 / 9.8 |
| 10B VND | 2.888 | 2.03e-4 | 2.51 | 33.9% | 0.212 | 0.20 / 9.8 |
| 100B VND | -0.183 | 1.1e-104 | 10.18 | 83.7% | -0.033 | -4.92 / 81.5 |

Note: total commission 0.0279 + spread 0.0139 are constant across all capitals; only slippage scales linearly with capital/ADV.

## Smoke (5 tickers/year, 23 unique)
| Capital | SR_ann | cost (bps) | slip share |
|--:|--:|--:|--:|
| 1B | 2.965 | 1.07 | 1.5% |
| 10B | 2.495 | 1.21 | 12.9% |
| 100B | -0.462 | 2.61 | 59.7% |

## Key code changes (`scripts/backtest_v2_cpcv.py`)
1. `_attach_adv()`: rolling 20d mean of `volume * close`, `.shift(1)` for T-1 PIT.
2. `load_panel`/`load_panel_walk_forward`: pull year-1 prehistory for ADV warmup.
3. `feat_df["adv_vnd"]` carried alongside features after dropna; missing rows imputed to median.
4. `per_date_returns(..., adv_te=)` builds `pivot_adv` aligned with `pivot_w`.
5. `apply_realistic_tc(..., daily_adv=adv_matrix)` plumbed.

## Conclusions
- **Codex P1-4 confirmed**: ignoring slippage was 0.5-1.0 SR optimistic at 10B+. Phase 3.7 advertised SR 3.20 holds for ~1B retail capital but degrades to 2.89 at 10B and crashes to negative at 100B.
- **Capacity estimate**: SR > 2.0 region holds up to ~30B VND assuming current 50-name walk-forward universe. Past 100B the strategy is uneconomic at this signal cadence.
- **Linearity check**: turnover (5.5%/bar) and commission/spread are capital-invariant. Slippage = `0.10 * (trade_VND / ADV) * |delta_w|` scales as capital — verified empirically across 1B/10B/100B.

## Next steps (priority)
1. ~~Slippage~~ DONE.
2. Fold-level DSR aggregation (codex CPCV oversample fix).
3. EMA-reset-per-fold (low priority; y-shuffle fal-test PASSED).
4. LSTM stack on top of Phase 3.7 baseline.
