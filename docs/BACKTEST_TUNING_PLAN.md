# OMEGA_QUANT V2.0 - Backtest, Paper Trading, and Alpha/Risk Tuning Plan

**Status**: Proposed execution plan  
**Scope**: Phases 1-22 complete system validation and tuning  
**Explicitly excluded**: Phase 24 Kubernetes/MLOps infrastructure  
**Primary dataset**: `data/market_2015_now.parquet`  
**Dataset lock ID**: `vn_market_2015_now`  
**Primary code paths**: `scripts/run_phase35_backtest.py`, `scripts/phase35_data_loader.py`, `packages/quant/src/omega/quant/phase35_walk_forward.py`, `packages/quant/src/omega/quant/live_trading_pipeline.py`, `packages/quant/src/omega/quant/realtime_risk_guard.py`, `packages/execution/src/omega/execution/broker_gateway.py`

## 1. Executive Goal

Build a defensible research-to-paper-trading path for OMEGA_QUANT V2.0 before any live capital is used.

The plan has three goals:

1. Produce leakage-safe, reproducible walk-forward backtests across VN market regimes.
2. Run paper trading in strict dry-run mode with the same risk guard and execution pipeline intended for production.
3. Tune Alpha and Risk parameters with statistically valid methods, avoiding overfit parameter choices.

Go-live decision is outside this document. This document ends at "paper trading approved for live readiness review".

## 2. Current Baseline

Existing evidence:

| Artifact | Current signal |
| --- | --- |
| `data/phase35_results/phase35_backtest_summary_xgboost.txt` | 8 folds, average Portfolio IC `0.0065`, average Sharpe `0.8384`, average Max DD `-57.92%` |
| `data/phase35_results/phase35_backtest_summary_drawdown_control.txt` | 8 folds, average Portfolio IC `0.0195`, average Sharpe `0.4507`, average Max DD `-7.74%` |
| `config/production.yaml` | PIT safety enabled, dry-run and paper trading enabled |
| `RealtimeRiskGuard` | Guards ADV, concentration, notional, drawdown, transaction cost |
| `PaperTradingEngine` | Immediate paper fill path exists; needs cost/slippage overlay for realistic evaluation |

Initial conclusion: drawdown control is already the strongest production-readiness improvement. Tuning should optimize robustness first, not headline Sharpe.

## 3. Non-Negotiable Guardrails

1. **No Phase 24 Kubernetes work**: no Kubernetes manifests, no cluster deployment, no MLOps cloud scope.
2. **No live orders**: keep `execution.dry_run: true` and `execution.paper_trading: true`.
3. **No PIT leakage**: all features use T-1 or earlier data; all labels use forward returns only inside train/eval boundaries.
4. **No random split validation**: only chronological walk-forward or purged time-series validation.
5. **No tuning on final holdout**: reserve final unseen period for one-time confirmation.
6. **No single-metric approval**: require return, drawdown, stability, turnover, cost, and risk-limit metrics.
7. **No unversioned datasets**: every accepted result must record data snapshot, config, commit, timestamp, and seed.

## 4. Target Operating Metrics

Minimum paper-readiness gates:

| Area | Gate |
| --- | --- |
| PIT safety | 100% PIT tests pass; no feature uses same-day future information |
| Backtest coverage | At least 8 walk-forward folds across locked dataset `vn_market_2015_now` (`2015-01-05` to `2026-05-14`) |
| Portfolio IC | Positive average IC and at least 60% positive test folds |
| Drawdown | Average max drawdown better than `-15%`; no fold worse than `-25%` without documented regime exception |
| Sharpe | Net-of-cost Sharpe above `0.8` preferred; above `0.5` acceptable if drawdown and stability are strong |
| Turnover | Explainable turnover; cost-adjusted performance remains positive |
| Risk rejects | Paper trading reject rate under 20%, and every reject has reason code |
| Paper trading | 20 trading days minimum, 60 preferred, zero live broker orders |
| Observability | Daily paper PnL, exposures, orders, rejects, and risk status exported |

## 5. Data Strategy

### 5.1 Locked Data Source

All L0, L1, L2, L3 backtest work must load the same physical parquet file directly:

```text
dataset_id = vn_market_2015_now
dataset_path = data/market_2015_now.parquet
absolute_path = C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\data\market_2015_now.parquet
size_bytes = 35332314
sha256 = 20e7948a1192c5428aaf4b0d7f37a7ebd04c6409972175de76995035e82d81cc
date_min = 2015-01-05
date_max = 2026-05-14
row_count = 3392023
symbols = 1534
columns = ticker,date,open,high,low,close,volume,as_of,available_at
```

The plan must not reference generated placeholder warehouse files for formal evaluation. U30, U50, U80, and sector-balanced universes are derived views from this locked file, not separate source datasets.

Required loader contract:

```python
from pathlib import Path

from scripts.phase35_data_loader import Phase35DataLoader

PROJECT_ROOT = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
DATASET_ID = "vn_market_2015_now"
DATASET_PATH = PROJECT_ROOT / "data" / "market_2015_now.parquet"
DATA_START = "2015-01-05"
DATA_END = "2026-05-14"

loader = Phase35DataLoader(warehouse_path=str(DATASET_PATH))
df = loader.load_and_prepare(
    start_date=DATA_START,
    end_date=DATA_END,
    top_n_symbols=TOP_N_SYMBOLS,
    forward_horizons=[1, 3, 5, 10],
)
```

Every run config and result JSON must include:

```json
{
  "dataset_id": "vn_market_2015_now",
  "dataset_path": "data/market_2015_now.parquet",
  "dataset_sha256": "20e7948a1192c5428aaf4b0d7f37a7ebd04c6409972175de76995035e82d81cc",
  "dataset_date_min": "2015-01-05",
  "dataset_date_max": "2026-05-14"
}
```

### 5.2 Derived Universes

Use staged universes:

| Stage | Universe | Purpose |
| --- | --- | --- |
| U30 | Top 30 liquid names derived from `vn_market_2015_now` | Fast baseline and regression testing |
| U50 | Top 50 liquid names derived from `vn_market_2015_now` | Main tuning universe |
| U80 | Top 80 liquid names derived from `vn_market_2015_now` | Capacity and robustness check |
| Sector-balanced | Liquidity-filtered sector sample derived from `vn_market_2015_now` | Sector-cap stress validation |

Required filters:

- Minimum listing age: 252 sessions.
- Minimum non-null OHLCV coverage: 95%.
- Minimum liquidity: configurable 20-day ADV floor.
- Corporate-action adjustment: split/dividend-adjusted prices only.
- Survivorship control: preserve delisted/suspended symbols when source supports it; otherwise mark limitation in result metadata.

### 5.3 Dataset Lock

Before any formal L0-L3 run, lock `data/market_2015_now.parquet` under ID `vn_market_2015_now`. Store the manifest at:

```text
data/backtest_manifests/vn_market_2015_now.json
```

Required manifest:

```json
{
  "dataset_id": "vn_market_2015_now",
  "created_at": "ISO-8601 timestamp",
  "source": "OMEGA_QUANT/data/market_2015_now.parquet",
  "path": "data/market_2015_now.parquet",
  "size_bytes": 35332314,
  "date_min": "2015-01-05",
  "date_max": "2026-05-14",
  "symbols": 1534,
  "row_count": 3392023,
  "sha256": "20e7948a1192c5428aaf4b0d7f37a7ebd04c6409972175de76995035e82d81cc",
  "columns": ["ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at"],
  "pit_lag_days": 1,
  "corporate_action_adjusted": true
}
```

Backtest outputs must reference `vn_market_2015_now`. If the file hash, row count, date range, or schema changes, create a new dataset ID instead of mutating this lock.

## 6. Backtest Strategy

### 6.1 Backtest Layers

Run four layers in order:

| Layer | Purpose | Output |
| --- | --- | --- |
| L0 Smoke | Confirm data load, feature generation, PIT checks | pass/fail, row counts |
| L1 Alpha Diagnostics | IC, Rank IC, decay, hit rate, turnover by alpha | alpha whitelist/blacklist |
| L2 Portfolio Backtest | Portfolio construction, sector caps, rebalance rules | fold metrics and risk profile |
| L3 Execution-Aware Backtest | Costs, slippage, ADV caps, order sizing | net performance and capacity |

All layers must load `data/market_2015_now.parquet` through `Phase35DataLoader(warehouse_path=str(DATASET_PATH))` and must emit `dataset_id: vn_market_2015_now`.

| Layer | Required load |
| --- | --- |
| L0 Smoke | Load `vn_market_2015_now`, `start_date="2015-01-05"`, `end_date="2026-05-14"`, `top_n_symbols=30`, `forward_horizons=[1,3,5,10]`; assert path exists, schema matches lock, hash matches lock, row count is non-zero, PIT metadata columns `as_of` and `available_at` are present |
| L1 Alpha Diagnostics | Load same locked file with `top_n_symbols=30` first; rerun with `top_n_symbols=50` before promotion; compute IC only inside chronological folds from the locked date range |
| L2 Portfolio Backtest | Load same locked file with `top_n_symbols=50`; use `DATA_START="2015-01-05"` and `DATA_END="2026-05-14"`; persist dataset lock fields in every fold metrics JSON |
| L3 Execution-Aware Backtest | Load same locked file with `top_n_symbols=50`; derive ADV, cost, slippage, and participation constraints from the same rows; no alternate parquet, cache snapshot, or synthetic immediate-fill dataset is allowed |

L0 and L1 run on U30 first. L2 and L3 run on U50. U80 is a capacity and robustness run after candidate selection, still derived from `vn_market_2015_now`.

### 6.2 Walk-Forward Design

Default formal setup:

- Start date: `2015-01-05`
- End date: `2026-05-14`
- Dataset lock: `vn_market_2015_now`
- Training window: 3 years
- Test window: 1 year
- Folds: rolling yearly folds
- Embargo: `return_horizon + 1` sessions between train and test when labels overlap
- Return horizons: T+1, T+3, T+5, T+10
- Primary horizon: T+5 unless T+3 shows materially better stability net of costs

Sensitivity setup:

| Parameter | Values |
| --- | --- |
| Train years | `2`, `3`, `4`, `5` |
| Test months | `3`, `6`, `12` |
| Embargo sessions | `return_horizon + 1`, `2 * return_horizon` |
| Universe | U30, U50, U80, all derived from `vn_market_2015_now` |
| Rebalance frequency | `3`, `5`, `7`, `10`, `20` sessions |

### 6.3 Cost and Slippage Model

Baseline costs:

- Commission: from `config/production.yaml` portfolio cost settings.
- Slippage: base bps plus liquidity penalty.
- Market impact: function of participation rate against 20-day ADV.
- Board-lot compliance: 100-share lot rules.
- No free immediate fills in formal L3 evaluation.

Recommended formula:

```text
net_return = gross_return
           - commission_bps
           - slippage_bps
           - impact_bps(participation_rate, volatility, spread_proxy)
```

Participation-rate buckets:

| ADV participation | Impact assumption |
| --- | --- |
| <= 1% ADV | low impact |
| 1-3% ADV | medium impact |
| 3-5% ADV | high impact |
| > 5% ADV | reject or penalize heavily |

### 6.4 Required Backtest Reports

Every formal run must produce:

- Config JSON.
- Dataset manifest reference.
- Alpha IC by fold.
- Portfolio metrics by fold.
- Gross and net performance.
- Max drawdown and drawdown duration.
- Turnover and estimated costs.
- Sector exposure.
- Position concentration.
- Risk-limit reject simulation.
- Top contributors and detractors.
- Regime notes for crisis years: 2018, 2020, 2022.

## 7. Alpha Tuning Plan

### 7.1 Alpha Candidate Metrics

Each alpha must be ranked by:

- Mean IC.
- Rank IC.
- IC t-stat.
- IC information ratio.
- IC decay by horizon.
- Hit rate.
- Turnover induced.
- Cross-alpha correlation.
- Regime stability.
- Cost-adjusted contribution.

### 7.2 Alpha Parameter Search Space

| Parameter | Values |
| --- | --- |
| `min_ic_threshold` | `0.005`, `0.010`, `0.015`, `0.020`, `0.030` |
| `top_n_alphas` | `3`, `5`, `7`, `10` |
| `return_horizon` | `1`, `3`, `5`, `10` |
| alpha weighting | equal, IC-weighted, ICIR-weighted, shrinkage IC-weighted |
| alpha direction | signed IC, absolute IC with train-only sign lock |
| neutralization | market, sector, market+sector, none as ablation |
| ML path | baseline, XGBoost enabled |

XGBoost tuning should be secondary. Tune raw alpha/risk controls first so the system does not depend on a model to hide weak construction.

Candidate ML hyperparameters:

| Parameter | Values |
| --- | --- |
| `max_depth` | `2`, `3`, `4` |
| `n_estimators` | `50`, `100`, `200` |
| `learning_rate` | `0.01`, `0.03`, `0.05`, `0.10` |
| `subsample` | `0.6`, `0.8`, `1.0` |
| `colsample_bytree` | `0.6`, `0.8`, `1.0` |
| `reg_alpha` | `0`, `0.1`, `1.0` |
| `reg_lambda` | `1`, `5`, `10` |

### 7.3 Alpha Selection Rules

Promote an alpha only if:

1. Mean test IC is positive after sign lock.
2. At least 60% of folds have positive IC.
3. IC decay is explainable across horizons.
4. Turnover does not destroy net performance.
5. Cross-alpha correlation does not duplicate an already stronger alpha.
6. It survives at least one adverse regime fold.

Demote an alpha if:

- It only works in one fold.
- It increases drawdown without increasing net return.
- It creates high turnover.
- It fails under U50/U80 universes derived from `vn_market_2015_now`.

## 8. Risk Tuning Plan

### 8.1 Risk Parameter Search Space

| Parameter | Values |
| --- | --- |
| `top_n_stocks` | `5`, `8`, `12`, `20` |
| `rebalance_freq` | `3`, `5`, `7`, `10`, `20` sessions |
| `sector_cap_pct` | `0.20`, `0.25`, `0.30`, `0.35` |
| max position | `0.05`, `0.075`, `0.10`, `0.15` |
| `max_adv_pct` | `0.01`, `0.02`, `0.03`, `0.05` |
| `max_concentration_pct` | `0.10`, `0.15`, `0.20` |
| `max_notional_currency` | `100M`, `250M`, `500M` VND |
| `circuit_breaker_drawdown` | `0.03`, `0.05`, `0.08`, `0.10` |
| cost limit per order | `10`, `20`, `35`, `50` bps |

### 8.2 Risk Objective

Primary score:

```text
score = 0.30 * normalized_net_sharpe
      + 0.25 * normalized_calmar
      + 0.20 * normalized_fold_stability
      + 0.15 * normalized_avg_ic
      - 0.10 * normalized_turnover
      - 0.20 * drawdown_breach_penalty
      - 0.15 * concentration_breach_penalty
```

Use score only for ranking. Approval still requires hard gates.

### 8.3 Drawdown-First Candidate Filter

A candidate configuration is rejected before Sharpe ranking if:

- Any fold max drawdown is worse than `-25%`.
- Average max drawdown is worse than `-15%`.
- Net total return is negative in more than 40% of folds.
- It violates ADV or concentration limits in more than 20% of simulated orders.
- Performance disappears after doubling cost assumptions.

## 9. Optimization Method

Use a staged process:

1. **Coarse grid** over Alpha and Risk parameters.
2. **Successive halving**: keep top 25% by hard gates and primary score.
3. **Local search** around top candidates.
4. **Stress rerun** with doubled costs, stricter ADV, and wider universe.
5. **Final holdout** exactly once.

Do not use Bayesian or genetic optimization until the backtest harness records every run with immutable config and dataset references. Black-box optimizers increase overfit risk unless experiment tracking is strict.

## 10. Statistical Validation

Required checks:

- Bootstrap confidence intervals for Sharpe, IC, and max drawdown.
- Fold-level sign test for positive IC.
- Deflated Sharpe Ratio or equivalent overfit adjustment.
- White's Reality Check or block bootstrap for multiple-testing bias when many configs are compared.
- Parameter stability heatmaps.
- Regime attribution: bull, bear, sideways, high-volatility periods.
- Ablation: no neutralization, no sector cap, no drawdown control, no ML path.

Approval favors flat robust regions over sharp best points.

## 11. Paper Trading Setup

### 11.1 Mode

Paper trading must use:

- `execution.dry_run: true`
- `execution.paper_trading: true`
- `LiveTradingPipeline`
- `RealtimeRiskGuard`
- `LiveExecutionBridge`
- `PaperTradingEngine`

No real broker credentials should be used. If broker config fields are required, use explicit paper placeholders only.

### 11.2 Paper Trading Flow

Daily flow:

1. Load latest T-1 market data.
2. Build alpha features.
3. Generate target portfolio.
4. Diff target portfolio against paper positions.
5. Create candidate orders.
6. Run `RealtimeRiskGuard.check_order()`.
7. Submit approved orders to `LiveExecutionBridge` in paper mode.
8. Record fill, reject, exposure, cost estimate, and risk verdict.
9. Export paper trading report.

### 11.3 Paper Ledger

Create or extend a paper ledger with:

| Field | Meaning |
| --- | --- |
| `trade_date` | Trading date |
| `symbol` | Ticker |
| `side` | BUY/SELL |
| `quantity` | Board-lot rounded quantity |
| `decision_price` | Price used for signal and order decision |
| `paper_fill_price` | Simulated fill price |
| `slippage_bps` | Simulated slippage |
| `commission` | Estimated commission |
| `risk_verdict` | PASS or reject reason |
| `order_id` | Internal order ID |
| `strategy_config_id` | Backtest config linked to this trade |

Recommended path: `data/paper_trading/paper_ledger.csv`.

### 11.4 Paper Trading Metrics

Daily:

- Paper PnL.
- Gross and net exposure.
- Cash usage.
- Sector exposure.
- Position concentration.
- Turnover.
- Risk rejects by reason.
- Fill rate.
- Estimated cost.
- Signal hit rate for T+1/T+3/T+5 once labels mature.

Weekly:

- Net Sharpe estimate.
- Drawdown.
- IC by alpha.
- Drift versus backtest expectations.
- Reject-rate review.
- Orders that would breach live constraints.

### 11.5 Paper Trading Approval Gates

Paper trading can move to live readiness review only if:

1. At least 20 trading days completed; 60 preferred.
2. No accidental live orders.
3. No unresolved data freshness failures.
4. No unexplained position mismatch.
5. Risk guard rejects are explainable and under threshold.
6. Net performance is within expected backtest confidence band.
7. Drawdown and exposure remain inside configured limits.

## 12. Execution Timeline

### Week 0: Preparation

- Freeze Phase 24 Kubernetes scope as excluded.
- Confirm all Phase 1-22 tests relevant to quant, risk, execution, and data pass.
- Create `data/backtest_manifests/vn_market_2015_now.json` from `data/market_2015_now.parquet`.
- Define output directories:
  - `data/backtest_runs/`
  - `data/backtest_manifests/`
  - `data/paper_trading/`
  - `docs/backtest_reports/`

Deliverable: baseline reproducibility checklist.

### Week 1: Backtest Harness Hardening

- Parameterize `scripts/run_phase35_backtest.py` instead of editing constants by hand.
- Add config file support for backtest runs.
- Persist full config, dataset manifest, and metrics.
- Add L0 smoke run and PIT validation report against `vn_market_2015_now`.
- Reproduce current XGBoost and drawdown-control baselines.

Deliverable: reproducible baseline run pack.

### Week 2: Alpha Diagnostics

- Run U30 and U50 alpha diagnostics from `vn_market_2015_now`.
- Compute IC, Rank IC, ICIR, decay, hit rate, turnover, and correlation.
- Build alpha whitelist/demote list.
- Run neutralization ablations.

Deliverable: Alpha candidate report.

### Week 3: Risk and Portfolio Tuning

- Run risk parameter grid.
- Prioritize drawdown, concentration, cost, and stability.
- Stress candidates with doubled costs and stricter ADV.
- Select 3 candidate configurations.

Deliverable: Risk tuning report and 3 paper candidates.

### Week 4: Final Holdout and Paper Wiring

- Run final holdout once for selected candidates.
- Pick one primary and one fallback paper config.
- Wire paper ledger and daily paper report.
- Confirm `dry_run` and `paper_trading` are enforced.

Deliverable: paper trading launch checklist.

### Weeks 5-8: Paper Trading Soak

- Run daily paper trading.
- Review risk rejects and position drift.
- Compare paper realized results to backtest expectation bands.
- Freeze config changes unless a gate-breaking issue appears.

Deliverable: 20-day paper trading review.

### Weeks 9-12: Extended Soak

- Continue to 60 paper trading days if results are marginal or regime coverage is weak.
- Produce live readiness review package.

Deliverable: live readiness dossier, not live approval.

## 13. Deliverables

| Deliverable | Path |
| --- | --- |
| Backtest/tuning plan | `docs/BACKTEST_TUNING_PLAN.md` |
| Dataset manifests | `data/backtest_manifests/*.json` |
| Backtest run configs | `data/backtest_runs/*/config.json` |
| Backtest metrics | `data/backtest_runs/*/metrics.json` |
| Backtest reports | `docs/backtest_reports/*.md` |
| Paper ledger | `data/paper_trading/paper_ledger.csv` |
| Daily paper report | `data/paper_trading/reports/YYYY-MM-DD.md` |
| Final paper review | `docs/PAPER_TRADING_REVIEW.md` |

## 14. Decision Gates

### Gate A: Baseline Reproduced

Pass when current known baselines can be reproduced from a clean config and locked dataset `vn_market_2015_now`.

### Gate B: Alpha Candidate Approved

Pass when alpha selection survives fold, regime, cost, and universe robustness checks.

### Gate C: Risk Candidate Approved

Pass when risk configuration meets drawdown, concentration, ADV, and cost gates.

### Gate D: Paper Trading Ready

Pass when paper pipeline is wired, dry-run enforced, ledger/reporting working, and candidate config frozen.

### Gate E: Paper Soak Passed

Pass when paper trading completes minimum duration with no safety breach and expected performance drift explained.

## 15. Immediate Next Actions

1. Convert `scripts/run_phase35_backtest.py` constants into CLI/config parameters, including `dataset_id`, `dataset_path`, `start_date`, and `end_date`.
2. Add dataset manifest creation and checksum tracking for `vn_market_2015_now`.
3. Re-run existing XGBoost and drawdown-control baselines under the `vn_market_2015_now` manifest.
4. Build Alpha diagnostics report for U30 and U50 derived from `vn_market_2015_now`.
5. Start Risk grid with drawdown-first filtering.
6. Wire paper ledger around `LiveTradingPipeline` and `PaperTradingEngine`.

## 16. Recommended Starting Candidate

Use drawdown-control baseline as starting point because it materially reduces max drawdown versus the XGBoost baseline:

```text
train_years = 3
test_years = 1
return_horizon = 5
min_ic_threshold = 0.02
top_n_alphas = 5
top_n_stocks = 8
rebalance_freq = 7
sector_cap_pct = 0.30
use_xgboost = false for first risk tuning pass
```

Then tune risk controls before enabling XGBoost. If XGBoost improves net performance without worsening drawdown, turnover, or parameter stability, promote it to paper candidate. Otherwise keep the simpler baseline.
