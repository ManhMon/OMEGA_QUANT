# OMEGA_QUANT Backtest & Tuning Session Summary
**Date**: 2026-05-26
**Duration**: ~10 hours (05:35 - 16:01 GMT+7)

## Best Configuration (Production Candidate)

**Source**: Island Model GP V1 (`island_gp_and_l3_backtest.py`)
**Config**: `top8_rebal10_cost25bps_evolved_momentum`

| Parameter | Value |
|---|---|
| Universe | U15 (top 15 liquid VN stocks) |
| Top N Stocks | 8 |
| Rebalance Frequency | 10 days |
| Slippage | 10 bps |
| Commission | 15 bps |
| Total Cost | 25 bps per turnover |
| Alpha Source | 3 evolved GP alphas + momentum 20d/60d |
| Signal Weighting | 50% evolved + 25% mom20 + 25% mom60 |

## Performance (After Costs, 8-Fold Walk-Forward)

| Metric | Value |
|---|---|
| **Average Net Sharpe** | **+0.4943** |
| **Average Total Return** | **+1.20%** per fold |
| **Average Max Drawdown** | **-3.59%** |
| **Positive Folds** | **5/8 (62.5%)** |

### Per-Fold Breakdown

| Fold | Net Sharpe | Return | Max DD |
|---|---|---|---|
| 1 | -1.38 | -4.20% | -1.00% |
| 2 | +0.50 | +0.76% | -1.96% |
| 3 | +1.43 | +6.17% | -8.10% |
| 4 | +2.10 | +5.66% | -5.98% |
| 5 | -0.94 | -3.61% | -2.00% |
| 6 | +1.69 | +3.62% | -3.65% |
| 7 | -0.99 | -3.26% | -1.36% |
| 8 | +1.53 | +4.48% | -4.71% |

## Evolved Alphas (Hall of Fame)

| # | Island | Train IC | Test IC | Expression |
|---|---|---|---|---|
| 1 | 3 | 0.0351 | 0.0439 | `neg(...)` |
| 2 | 6 | 0.0450 | 0.0378 | `abs(...) - ...` |
| 3 | 3 | 0.0373 | 0.0346 | `volume / ...` |

Best single alpha discovered: **IC=0.0520** (Island 8, not reproducible due to GP stochasticity)

## Universe

```
HPG, STB, VHM, VPB, SSI, GEL, TCB, SHB, NVL, FPT, MBB, MSN, MWG, DIG, VRE
```

## Data

| Field | Value |
|---|---|
| Dataset | `data/market_2015_now.parquet` |
| Lock ID | `vn_market_2015_now` |
| SHA256 | `20e7948a1192c5428aaf4b0d7f37a7ebd04c6409972175de76995035e82d81cc` |
| Rows | 3,392,023 |
| Tickers | 1,534 |
| Date Range | 2015-01-05 to 2026-05-14 |

## Journey Summary

| Step | Result |
|---|---|
| Microstructure Alpha (Phase 34) | Net Sharpe -1.82 (FAIL) |
| Momentum V2 (U15, rebal 10d) | Net Sharpe +0.35 |
| **Island GP + Momentum** | **Net Sharpe +0.49 (BEST)** |
| GP V2 (IC=0.0520 target) | Net Sharpe +0.03 (not reproducible) |

## Infrastructure Fixes

- Restored 196 missing .py files from `archive/cloneOMEGA`
- Restored 28 scripts, 7 tests, 1 config
- Merged multi-package structure into monolithic `src/omega/`
- PYTHONPATH simplified to single path: `OMEGA_QUANT/src`

## Next Steps

1. Paper Trading simulation (20 days minimum) with best config
2. Improve GP engine (island migration, novelty search, adaptive mutation)
3. Add fundamental factors (PE, PB, ROE) when data available
4. Production deployment after paper trading validation

## Files Generated

- `data/phase35_results/l3_evolved_alpha_backtest.csv`
- `data/phase35_results/l3_evolved_summary.json`
- `data/phase35_results/genetic_alpha_v3_results.csv`
- `data/phase35_results/alpha_risk_tuning_v2_grid.csv`
- `data/phase35_results/l1_alpha_diagnostics_u30.csv`
- `data/backtest_manifests/vn_market_2015_now.json`
- `docs/BACKTEST_TUNING_PLAN.md`
