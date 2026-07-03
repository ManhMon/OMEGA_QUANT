# Backtest Report

## Metadata
- Gate: `HYBRID_REGIME_FULL_BACKTEST_20260620`
- Perf gate: `HYBRID_REGIME_BACKTEST_PERF_20260621`
- Diagnostic gate: `HYBRID_REGIME_PROFITABILITY_DIAG_20260621`

## Configuration
- Date range: 2015-01-01 -> 2026-12-31
- Capital: 2,000,000,000 VND
- CPCV: 10 folds, 2 test folds, embargo 1.00%
- Label horizon: 60 days
- Dynamic universe: True
- Symbols: 30
- Quick mode: False
- Workers: 4

## Aggregate Comparison
| Strategy | Mean Sharpe | Mean Return | Mean Max DD | Folds Done | Folds Error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | -0.3576 | 1.74% | -18.28% | 45 | 0 |
| Hybrid | -0.3788 | 4.46% | -19.50% | 45 | 0 |

## Hybrid Profitability
- Mean gross return: 15.99%
- Median gross return: -4.36%
- Mean total transaction cost: 11.54%
- Median total transaction cost: 10.98%
- Min/Max gross return: -13.03% / 168.84%

## Hybrid Alpha IC By Regime
| Regime | Mean IC | Std IC | Folds |
| --- | ---: | ---: | ---: |
| Bull | 0.0147 | 0.0098 | 23 |
| Sideways | -0.0064 | 0.0263 | 23 |
| Bear | 0.0117 | 0.0097 | 44 |

## Runtime
- Total elapsed: 2479.54 sec (41.33 min)

ponytail: report is summary-only from current JSON schema; add charts/per-fold appendix when consumers need deeper diagnostics.
