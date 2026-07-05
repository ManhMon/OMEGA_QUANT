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

## 7. GP Performance Optimization (2026-07-03 Claude Code + Codex L3 Audit, Revised)
- **Audit Date**: 2026-07-03
- **Audit Sources**: Claude Code advisory + Codex L3 (performance-tester, role 23) independent audit + Claude Code plan review
- **Audit Report**: `.ly_state/session/audit_reports/role23_gp_performance_20260703.md`
- **Revised Implementation Plan**: `gp_performance_optimization_plan.md` (revised after Claude Code review)
- **Current Performance Issue**: 150 pop × 25 gen × 5 rounds = 18,750 evaluations running slow due to HoF cache bug (dominant bottleneck), redundant fold recomputation, and pandas GIL-holding operations.
- **Top Bottlenecks (Revised Attribution)**:
  1. **Hall of Fame Cache Bug (Extra-1)** - **DOMINANT BOTTLENECK**: Broken cache causes ~10 HoF tree re-executions per individual. Attempts to set `hall_of_fame._alpha_cache` on plain `list` silently fail (`AttributeError`). Expected ~2-3× speedup from fix alone.
  2. **Redundant Fold Recomputation (Fix C)**: Date masks + feature slices recomputed 150× per generation (identical across individuals). Small-medium speedup.
  3. **Diversity + Orthogonalization Penalties (Fix A)**: ~15 pandas `DataFrame(...).dropna() + spearmanr()` per individual, but ortho is **minor fraction** compared to neutralization `lstsq` (untouched). Small speedup only.
  4. **Wasted Pandas Operations (Extra-2)**: `dropna` in `evaluate()` after `nan_to_num` already cleaned. Small GIL reduction.
- **Approved Safe Optimizations** (Revised after Claude Code review blockers fixed):
  - **Fix Extra-1** (hero): Fix HoF cache via unified injection pattern (`gen_features['__hof_alphas__']` built in `evolve()` pre-parallelization). Expected ~2-3× speedup.
  - **Fix C**: Cache fold masks/indices using same injection pattern (`gen_features['__fold_cache__']`). Thread-safe, built before `Parallel()`. Small-medium speedup.
  - **Fix A**: Precompute ortho baseline ranks once globally → vectorized Pearson-on-ranks (Spearman equivalent). Small speedup (ortho is minor cost).
  - **Fix Extra-2**: Replace pandas `dropna` in `evaluate()` with numpy finite mask. Small speedup.
- **Critical Requirements**:
  - **Thread Safety**: All caches built in `evolve()` before `Parallel()` call to avoid race conditions (threads backend).
  - **Rollback Mechanism**: `GPConfig.use_fast_penalties: bool = True` feature flag for easy revert.
  - **Test Coverage**: Per-function equivalence tests (NaN baselines, inf targets, staleness, determinism) + end-to-end sanity check.
  - **Realistic Performance Claims**: **2-4× aggregate speedup** (not 5-10×). Extra-1 is dominant win. Neutralization `lstsq` (largest single cost) is untouched and requires separate optimization.
- **Excluded**:
  - **Fix B (Time-Fold IR Subsampling)**: Codex verdict: "zero IC impact" claim is **FALSE**. Row-random subsampling changes fitness semantics. Acceptable only as deterministic fold/date-stratified fast mode with full-data final HoF scoring (future work).
- **Backend Recommendation**: Keep `threads` default. Avoid `loky`/`multiprocessing` due to Windows worker permission failures (`[WinError 5]`) and serialization overhead for large numpy arrays.
- **PIT Safety**: All approved fixes preserve PIT safety (features already shifted, ortho baselines use train-only, caches keyed to current feature slice and invalidate on identity change).


## 8. Size/Sector Neutralization & Liquidity Filter (Gate 7 Upgrade)
- **Audit Date**: 2026-07-04
- **Gate**: `GATE7_NEUTRALIZATION_LIQUIDITY_20260704` (Approved)
- **Engine Modifications**:
  - Centralized mask: Implemented `_evaluation_mask()` combining finite price checks and `__liquidity_mask__` used across observation counting and all IC paths.
  - Neutralization extension: Target array is now neutralized symmetrically along with the alpha signal using the existing per-date OLS `_neutralize_cross_section` helper.
- **Script-Side v3 Enhancements**:
  - Restored Fold Contract: Fixed time folds config `time_folds=8` -> `3` to comply with Gate 6 chronological fold IR specification.
  - Traded-Value Filter: Added CLI parameters `--min-avg-volume` and `--avg-volume-window`. Volume checks evaluate `traded_value = close * volume` in VND and shift by ticker at $T-1$ for PIT safety.
  - Consistent Selection: Replaced raw daily validation IC ranking with engine-consistent scorer evaluating intervals under the same target residualization, liquidity masking, and fold IR constraints.
  - Sector Proxy Semantics: Documented in code comments that 'sector' refers to the dynamically-computed volume-quartile proxy rather than economic sectors.

## 9. GP Production Run & Bug Fixes Plan (GP_PRODUCTION_RUN_PLAN_REVIEW_V4)
- **Audit Date**: 2026-07-04
- **Gate**: `GP_PRODUCTION_RUN_PLAN_REVIEW_V4` (Approved by Claude Code & Codex L3)
- **Proposed Logic Modifications**:
  - Stable Sort: Two-pass sorting in `export_gp_views` (`version` reverse-chronological primary, `rank` secondary).
  - Validate-Before-Register: Refactored database model registration to validate top models against Gate 6 criteria *before* performing database/registry writes or exporting file artifacts.
  - Hard p-value Constraint: Raise ValueError on hoán vị p-value > 0.05 to reject non-significant models.
  - Searchsorted Split: Replace `dates.index(...)` with `np.searchsorted(dates, split_date)` plus index bounds guard.
  - Unrounded Tie-break: Order candidates in `all_hof` using full-precision `val_IC_daily` with candidate ID tie-breaker.
- **Verification & Acceptance Criteria**:
  - Explicit schema validation assert on parquet outputs (`alpha_gp_00` column presence and non-null) before backtest.
  - Conformal backtest trained on-the-fly per fold without direct model JSON loads as predictors.
  - Mandatory regression tests: `test_stable_sorting`, `test_searchsorted_split_handling`, `test_no_register_on_gate_fail`, `test_p_value_hard_fail`, `test_unrounded_val_ic_sorting`.

## 10. Future Performance Roadmap for GP Evolution Engine V4 (WorldQuant-Style Architecture)
- **Core Speed Optimization Guidelines**:
  1. **Feature Bank**: Precalculate all base time-series indicators (e.g. rolling std, rolling mean) globally and reuse them instead of executing time-series operators dynamically inside candidate trees.
  2. **NumPy over Pandas**: Convert the entire data pipeline to NumPy contiguous arrays to bypass Pandas overhead and GIL-holding operations.
  3. **Vectorization**: Eradicate all Python loops (especially per-date daily IC loops) by computing rank correlation cross-sectionally using vectorized matrix operations.
  4. **Numba JIT**: Compile performance-critical rolling, ranking, and correlation operations to machine code using `@jit`.
  5. **Batch Fitness**: Evaluate batches of 32–256 candidates simultaneously to maximize CPU pipeline utilization.
  6. **Parallel CPU**: Run multiple independent worker processes using optimal parallel backends.
  7. **Subtree Cache**: Implement memoization of identical sub-trees to avoid redundant computations within and across generations.
  8. **Compile GP**: Translate symbolic GP trees directly to bytecode or stack-based representation before execution.
  9. **Early Rejection**: Terminate evaluation of candidates that fail to pass basic sanity or initial fold requirements.
  10. **Search Space Reduction**: Enforce strict constraints on tree depth and primitive vocabulary size.
  11. **Island Model**: Distribute the population into independent islands running on separate nodes.
  12. **Walk-forward**: Restrict evaluation and backtesting purely to relevant split windows.
  13. **GPU Acceleration**: Offload large-scale matrix operations to GPU tensors (e.g. using CuPy or PyTorch), keeping I/O latency in mind.
  14. **Distributed Computing**: Scale execution horizontally across multiple machines using Ray, Dask, or Apache Spark.
- **WorldQuant-Style Pipeline Architecture**:
  - `Feature Bank` $\rightarrow$ `GP Engine` $\rightarrow$ `IC Engine` $\rightarrow$ `Alpha Pool` $\rightarrow$ `Correlation Filter` $\rightarrow$ `Ensemble`.

## 11. GP V4 Advanced Optimization (Rules 5, 9, 11) Design Decisions
- **Decision Date**: 2026-07-05
- **Approved Plan Gate**: `GP_V4_ADVANCED_PLAN_REVIEW`
- **Design Parameters**:
  - **Early Rejection**: Chronological evaluation (Fold 0 -> Fold 1 -> Fold 2) on Train Folds only. Hard penalty of `-2.0` on failure, with 5% random auditing.
  - **Island Model**: 3 independent processes/threads with distinct deterministic seeds (`base_seed + island_idx * 1000`) and island-specific caches. Ring migration of symbolic JSON trees every 5 generations.
  - **Batch Fitness**: Gộp lô 32 ứng viên sau khi tính xong tín hiệu 1D, xử lý song song OLS neutralization và Spearman IC bằng mảng NumPy 3D để tối ưu hóa CPU.
  - **Performance Acceptance**: Wall-clock speedup $\ge 3.0x$ compared to V4 basic, peak RSS memory $\le 4GB$. Measured via `scripts/benchmark_v4_advanced.py`.

