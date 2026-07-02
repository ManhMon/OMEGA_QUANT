---
type: reference
created: 2026-07-02
updated: 2026-07-02
---

# Technical Decisions

## 1. Hybrid Regime Winner Configuration (C3)
- **Parameters**:
  - `--cost-per-trade-bps`: `15.0`
  - `--min-trade-threshold-bps`: `200.0`
  - `--rebalance-every-n-days`: `10`
  - `--top-k`: `7`
- **Rationale**: Rebalancing every 10 days with a 200 bps threshold filters out trading noise, saves ~1pp of transaction costs, and increases the Median Sharpe Ratio to -0.3224 while reducing max drawdown to -26.32%.

## 2. Database Storage Integration (Phase 15 & GP Persistence)
- **Storage**: SQLite database (`omega.db` or configured URI).
- **Tables**:
  - `news_articles`: stores cafef/vietstock RSS feed articles with sentiment scores.
  - `macro_data`: GDP, CPI, and gold/oil/FX commodity series.
  - `ticker_sectors`: Dynamic sector mappings with effective dates.
  - `datasets`: Registry metadata for dataset checkpoints (version, path, checksum, provenance, as_of_time).
  - `models`: Canonical source of truth for GP alpha expressions (serialized_tree, status, metrics, pit_embargo).
  - `audit_logs`: Cryptographic audit trail with chain-hashed logs.
- **ORM**: SQLAlchemy models defined in `src/omega/core/db/models.py` and `src/omega/core/db/persistence.py`.
- **GP Runner Cleanup**: Legacy evolution scripts `genetic_alpha_evolution.py` (v1) and `genetic_alpha_evolution_v2.py` (v2) are deleted; replaced completely by `genetic_alpha_evolution_v3.py` accessing the SQLite registry directly.

## 3. Conformal & Multi-Horizon Modeling (Phase 17 & 18)
- **Quantile Predictor**: `LGBMRegressor(objective='quantile')` predicting $\tau \in \{0.3, 0.7\}$ return horizons.
- **Mondrian Conformalization**: Calibrates the bounds per `(regime × liquidity_bucket)` to guarantee an 80% out-of-sample coverage.
- **Triple-Barrier Labeling**: Paths are labeled with dynamic barriers scaled by EWMA Volatility to penalize buying at peaks.
- **Fractional Differentiation**: Preserves long-term memory in features while ensuring stationarity ($d \in (0, 1)$).

## 4. Daily Oracle, Free Fallbacks & Price Ladder (Phase 19)
- **Timezone Standardization**: Strict UTC-aware normalization off `report_cutoff_utc(D)` at `D 09:00:00+07:00` VN-local time to prevent type crashes.
- **Asymmetric CQR Price Ladder**: Implements Romano-2019 CQR (`lower_model - q`, `upper_model + q`) calibrated across nested alphas $\alpha \in \{0.50, 0.20, 0.10, 0.05\}$. Price rungs are rounded to the VN tick size and clamped to daily limits.
- **Macro Feature Normalization**: Realized-lag available dates, 5 to 400 days staleness gates, robust rolling z-scores using median and MAD (Median Absolute Deviation) per-frequency (756 for daily, 60 for monthly, 20 for quarterly).
- **Automated Sector Report**: Dedicated generator `generate_sector_report.py` producing markdown reports and json audit files tracking breadth, flow_z (ADV ratios), sentiment_z, and leader attribution.

## 5. Conformal Backtest Integration & Sharpe Verification (Phase 20)
- **Sharpe Calculation Audited**: Confirmed rf = 0 is implicitly assumed across production backtests; DSR deflated Sharpe uses `periods_per_year=252` with raw per-bar inputs; implemented exact diagnostic `verify_sharpe_objective.py`.
- **PIT-Safe Conformal Gating**: Resolved look-ahead bias by enforcing that `ConformalGateOverlay` relies *only* on PIT-safe predicted interval width (`upper - lower` from GBR point/quantile forecasts) and width threshold limits (`max_width_abs`). Eliminated test-window realized coverage feedback from active sizing/gating logic.
- **Strategy B Default**: Swapped backtest pipeline default to Strategy B (per-fold refit) to enforce strict split-level out-of-sample GBR training and eliminate metadata-dependency leaks.
 
 
## 6. GP Evolutionary Alpha Search & Diversity Engine (v3 Upgrade)
- **Engine**: `GeneticEngine` and `GPConfig` in `omega.quant.evolution.genetic_engine`.
- **Search Space Configuration**:
  - Population size: `150`
  - Generations: `25`
  - Evolutionary rounds: `5` (with dynamic niche mutation to prevent convergence)
  - Top-K: `15` models selected by out-of-sample Spearman rank correlation (Spearman IC).
- **Features/Primitives**: OHLCV data + rolling indicators (`decay_linear`, `ts_rank`, `vol_ratio`, `hl_range`, `oc_range`).
- **Storage/Registry Integration**: Evolved models are registered to `conformal_registry.sqlite` with the naming pattern `genetic_alpha_v3_rank_<rank:02d>`. Metrics registered include `train_IC`, `test_IC`, `hit_rate`, and `serialized_tree`.
- **Views**: Registry model records are exported as offline CSV/JSONL views (`genetic_alpha_v3_results.csv` / `.jsonl`) for caching, but the SQLite registry remains the single canonical source of truth for runtime features compilation.
