# Label Horizon Sweep - 20260623

Command template: `python scripts/run_backtest.py hybrid-regime --quick-mode --workers 1 --label-horizon <H> --output-tag horizon_<H>`

| Horizon | Status | Scenario | Sharpe | Gross | Net | TC Drag | Max DD | Folds |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 10 | ok | Hybrid | -1.3996 | 61.21% | -26.67% | 87.89% | -28.52% | 5 |
| 15 | ok | Hybrid | -1.2366 | 38.38% | -25.01% | 63.39% | -27.18% | 5 |
| 20 | ok | Hybrid | -1.5419 | 55.25% | -28.76% | 84.01% | -30.22% | 5 |
| 30 | ok | Hybrid | -1.3197 | 41.58% | -24.86% | 66.44% | -26.49% | 5 |
| 40 | ok | Hybrid | -1.3804 | 25.24% | -29.49% | 54.73% | -30.99% | 5 |
| 60 | ok | Hybrid | -1.3124 | 51.11% | -26.81% | 77.92% | -28.55% | 5 |
| 90 | ok | Hybrid | -1.4993 | 68.51% | -29.36% | 97.87% | -32.10% | 5 |
