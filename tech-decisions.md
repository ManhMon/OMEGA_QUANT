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

## 12. GP V4 Advanced Optimization - Implementation & Parity Resolution (2026-07-05)
- **Decision Date**: 2026-07-05
- **Approved Implementation Gate**: `GP_V4_ADVANCED_IMPLEMENTATION`
- **CPython Address Reuse Cache Trap**: Discovered that Python's `id(arr)` can return duplicate memory address keys if temporary numpy arrays are garbage collected and new arrays allocate the same memory block. Resolved by keying the date-groups cache using a composite tuple: `(id(date_arr), len(date_arr), date_arr[0], date_arr[-1])` to guarantee 100% numerical correctness.
- **Multiprocessing Serialization Bug (Lock Pickling)**: Identified that storing a `threading.Lock` under `SUBTREE_CACHE_LOCK_KEY` in the `features` dictionary prevents standard Python serialization (pickling) required for joblib `loky` and `multiprocessing` backends on Windows. Resolved by removing the lock object from `features` and storing thread locks in a static, module-level weakref/dictionary cache mapping `id(features)` to `threading.Lock` instances. This restores full capability to scale evaluations horizontally across up to 10+ CPU processes.

## 13. GP V4 Advanced Batch Parallelization & Thread-Safe Cache (2026-07-05)
- **Decision Date**: 2026-07-05
- **Approved Gate**: `GP_PARALLEL_OPTIMIZATION_20260705` (Approved)
- **Problem**: In GP V4 Advanced, evaluating the candidate trees recursively was serial on a single CPU core. As generations progressed, tree depth/complexity increased, doubling the runtime per generation (Gen 2: 11.2 min, Gen 3: 22.3 min, Gen 4: 23.2 min). The main bottlenecks were: (1) heavy global lock contention recursive per node, and (2) recursive `node.to_string()` cache key construction.
- **Solution**:
  - **Threaded Parallelization**: Implemented joblib `Parallel(n_jobs=self.config.n_jobs, prefer="threads")` to run raw tree evaluations (`_execute_tree`) in parallel for the batch.
  - **Atomic GIL Operations**: Removed per-node get/set locks inside `_execute_tree` as CPython dictionary operations are atomic, converting lock contention to benign races with `.copy()` array isolation.
  - **Thread-safe cache helpers**: Added `_feature_cache_get` and `_feature_cache_set` locking only cache creation/eviction.

## 14. GP Numba JIT-Compiled Stack-Based VM (2026-07-05)
- **Decision Date**: 2026-07-05
- **Approved Gate**: `GP_NUMBA_JIT_VM_IMPLEMENTATION` (Approved)
- **Problem**: Python GIL and object-traversal overhead serialize execution of recursive `_execute_tree` calls even when using multiple threads. High latency on large datasets (1.25M rows) results in ~22 minutes per generation.
- **Solution**:
  - **RPN Bytecode Compiler**: Flattened symbolic trees into parallel `opcodes` (int32) and `operands` (int32) arrays.
  - **JIT VM Executor**: Implemented `@njit(cache=True, nogil=True, error_model='numpy')` function `_numba_execute_rpn` using a fixed 2D stack to guarantee memory stays $\le 4\text{ GB}$.
  - **Ticker rolling boundaries**: Provided `ticker_group_offsets` for contiguous time-series calculations.
  - **Daily CS boundaries**: Passed `date_flat_indices` and `date_group_offsets` to execute `cs_rank` and `cs_zscore` slice-by-slice without matrix transposition or cross-date leakage.

## 15. GP Numba JIT-Compiled OLS Neutralization (2026-07-05)
- **Decision Date**: 2026-07-05
- **Approved Gate**: `GP_NUMBA_OLS_IMPLEMENTATION` (Approved)
- **Problem**: Mặc dù việc tính toán cây biểu thức đã được tăng tốc bằng Numba JIT VM, nhưng bước khử trùng lặp chéo dòng OLS Neutralization (`_neutralize_cross_section` và `_batch_neutralize_cross_section` cho 2.500 ngày của 700 mã) vẫn chạy trong vòng lặp Python thuần và chiếm giữ khóa GIL, làm hạn chế hiệu năng tổng thể của đa luồng chéo các cá thể.
- **Solution**:
  - **Hợp đồng Solver Ridge**: Sử dụng hồi quy Ridge với hệ số phạt $\lambda = 10^{-6}$ thay thế cho OLS lstsq thô để đảm bảo an toàn tuyến tính chéo dòng khi số dòng nhỏ hoặc suy biến. So khớp đúng đắn số học với scikit-learn Ridge.
  * **Thiết kế Zero-Allocation**: Phẳng hóa cache ma trận thiết kế thành `design_matrix` ($N \times K$) và `design_valid_mask`. Nhân JIT OLS tích lũy trực tiếp Gram matrix ($K \times K$) và RHS ($K$) từ chỉ số dòng của ngày mà không cần slicing hay phân bổ mảng động bên trong vòng lặp ngày, giải quyết hoàn toàn gánh nặng GC/Heap trên Windows.
  - **Chạy song song**: Nhân JIT OLS được biên dịch với `@njit(cache=True, nogil=True)` giúp giải phóng GIL hoàn toàn, cho phép luồng chạy song song chéo cá thể ngoài tận dụng tối đa đa nhân CPU vật lý.

## 16. GP Numba JIT-Compiled OLS Neutralization - Gram-Sharing Optimization (2026-07-05)
- **Decision Date**: 2026-07-05
- **Approved Gate**: `GP_NUMBA_OLS_OPTIMIZATION` (Approved)
- **Problem**: Mặc dù nhân JIT OLS đã giải phóng GIL và chạy song song, nhưng trong vòng lặp ngày, ma trận Gram ($X^T X$) vẫn bị dựng lại vô ích cho mỗi ứng viên (100 ứng viên chéo ngày). Do ma trận thiết kế của ngày là cố định chéo các ứng viên, việc này nhân thêm 100x lần số phép toán dựng Gram không cần thiết, làm nghẽn tiến trình tiến hóa sâu (Gen 3, 4, 5).
- **Solution**:
  - **Gram-Sharing**: Tính toán ma trận Gram $X^T X$ cơ sở một lần duy nhất cho mỗi nhóm ngày (date group) và cộng sẵn Ridge penalty `ridge_alpha` vào đường chéo.
  - **Fast Path / Slow Path Branching**:
    - *Fast Path*: Nếu số lượng dòng hợp lệ thực tế của ứng viên bằng số dòng chuẩn (không chứa NaN - chiếm >99.9% trường hợp), sao chép ma trận Gram dựng sẵn và giải trực tiếp hệ phương trình OLS Ridge mà không dựng lại Gram.
    - *Slow Path*: Nếu tín hiệu ứng viên chứa NaN, thực hiện fallback dựng lại Gram riêng cho ứng viên đó để đảm bảo tính đúng đắn toán học tuyệt đối.
  - **Hiệu quả**: Loại bỏ 99% chi phí dựng ma trận Gram trong JIT OLS, kỳ vọng tăng tốc độ tổng thể của thế hệ lên gấp nhiều lần.

## 17. GP Numba Parallel Batch Kernels Implementation (2026-07-06)
- **Decision Date**: 2026-07-06
- **Approved Gate**: `GP_NUMBA_PARALLEL_BATCH_KERNELS_IMPL` (Approved)
- **Problem**: Mặc dù JIT VM và OLS Gram-Sharing đã tối ưu hóa tốc độ chạy tuần tự của đơn ứng viên, các ứng viên trong lô vẫn được đánh giá tuần tự, dẫn đến việc chưa khai thác hết khả năng xử lý song song đa nhân của CPU trên tập dữ liệu lớn.
- **Solution**:
  - **Song song hóa cấp nhân JIT**: Sử dụng `@njit(parallel=True, nogil=True)` kết hợp với `prange` chéo các ứng viên cho cả hồi quy Ridge khử chéo dòng (`_numba_batch_ridge_neutralize`) và tính toán tương quan ngày (`_numba_batch_daily_ics`).
  - **Thread-Safety body-allocation**: Đảm bảo an toàn luồng bằng cách khai báo phân bổ các bộ đệm trung gian (`row_buffer`, `gram`, `rhs`, `beta`) trực tiếp bên trong thân vòng lặp `prange` để Numba biên dịch thành các biến cục bộ riêng biệt cho từng luồng (thread-private allocations), loại bỏ race conditions mà không cần khóa đồng bộ.

## 18. GP WorldQuant-Style Performance Refactor Plan (2026-07-06)
- **Decision Date**: 2026-07-06
- **Approved Gate**: `GP_WORLDQUANT_PERFORMANCE_REFACTOR_PLAN` (Approved)
- **Problem**: Chi phí lặp chéo ngày và xử lý đối tượng Pandas DataFrame/Series trong vòng lặp chính của động cơ GP tạo gánh nặng lớn lên garbage collection và GIL, khiến tốc độ chạy Production quy mô lớn vẫn còn chậm.
- **Solution**:
  - Đề xuất loại bỏ hoàn toàn việc sử dụng Pandas trong các vòng lặp nóng, chuyển đổi sang cấu trúc mảng 3D/2D NumPy (Feature Bank).
  - Thay thế vòng lặp 2,500 ngày khi tính Spearman IC bằng phép nhân tích vô hướng 3D ma trận vector hóa.
  - Phân rã tiến hóa thành các Đảo tiến hóa song song (Island Model) đa tiến trình CPU không khóa.

## 19. GP WorldQuant-Style Performance Refactor Implementation (2026-07-06)
- **Decision Date**: 2026-07-06
- **Approved Gate**: `GP_WORLDQUANT_PERFORMANCE_REFACTOR_IMPL` (Approved)
- **Solution**:
  - **Feature Bank**: Triển khai `_compute_feature_bank_for_ticker` và `_build_feature_bank` để tiền tính toán toàn bộ chỉ báo kỹ thuật của 1.25 triệu dòng dữ liệu sang mảng NumPy 3D. Áp dụng trễ $T-1$ cho tất cả các tính năng để loại bỏ triệt để look-ahead bias (bảo vệ PIT safety).
  - **Khử trùng lặp OLS và Spearman IC 3D**: Vector hóa hoàn toàn Spearman IC chéo ngày và chéo ứng viên thông qua `@njit(parallel=True)` chéo các candidate, loại bỏ hoàn toàn các mảng NumPy động phân bổ trên Heap.
  - **Island Model**: Thiết lập cơ chế di cư ring-topology chéo các đảo tiến hóa độc lập với RNG seed riêng biệt.
  - **Đo lường**: Đạt tỷ lệ pass test 16/16 và được L3 Codex Opus phê chuẩn thành công.

## 20. GP Codebase Remediation and Optimizations (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_CODEBASE_REMEDIATION_AND_OPTIMIZATIONS` (Approved)
- **Problem**: 
  - Đa luồng song song trên Windows khi không bị giới hạn số lượng CPU dẫn đến tình trạng tranh chấp GIL, vỡ Heap và thrashing bộ nhớ (RAM < 16GB).
  - Sử dụng địa chỉ CPython `id()` làm khóa cache dẫn đến lỗi gán nhầm cache (aliasing) khi các dictionary chứa mảng lát cắt bị tạo lại chéo các thế hệ.
- **Solution**:
  - **Capping Workers trên Windows**: Cấu hình giới hạn cứng số lượng CPU song song của joblib ở mức `min(cpu_count, 4)` riêng trên môi trường Windows.
  - **Content-Based Cache Fingerprinting**: Thiết lập mã băm nội dung `_compute_feature_fingerprint` dựa trên: Tên chỉ báo, Kích thước mảng, Giá trị biên (first, last, min, max) thay thế cho `id()` để làm khóa cache VM/JIT, tăng tính ổn định chéo thế hệ.
  - **Bảo vệ PIT Safety**: Nhóm dữ liệu chéo dòng theo ngày chuẩn, nhóm dữ liệu chuỗi thời gian theo ticker và thiết lập độ trễ $T-1$ cho các tính năng thay thế (sentiment) để tránh look-ahead bias.
  - **Đo lường**: Toàn bộ hệ thống test suite (2599 passed) hoàn thành sạch sẽ, được enforcer phê duyệt `SoD Compliance: [PASS]`.

## 21. GP Alternative Features Memory Optimization (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_ALTERNATIVE_FEATURES_MEMORY_FIX` (Approved)
- **Problem**: 
  - Khi kích hoạt dữ liệu thay thế, việc sao chép dataframe 90+ cột (rộng ~1.51 GB) trong `AlternativeFeatureGenerator` và `AlternativeDataFetcher` gây lỗi tràn bộ nhớ `MemoryError` trên tập dữ liệu 1.77 triệu dòng.
  - Thao tác cắt lát mảng lịch sử tăng dần chéo 2500 ngày của 1.77 triệu dòng trong vòng lặp ngày của `_derive_sentiment_indicators` gây bão cấp phát Heap và rò rỉ bộ nhớ.
- **Solution**:
  - **Narrow-Copy Refactoring**: Trích xuất duy nhất 5 cột OHLCV thiết yếu để thực hiện tính toán đặc trưng thay thế trên mảng hẹp, sau đó `.join()` nông để gộp lại mảng chính (giảm hơn 95% RAM phụ).
  - **Loại bỏ cắt lát thừa**: Chuyển thẳng bộ dữ liệu nguồn vào `analyze()` thay vì cắt lát vòng lặp, tận dụng bộ lọc PIT thông minh tích hợp sẵn trong `analyze()`.
  - **Vectorized Date Mapping**: Thay thế vòng lặp gán nhãn boolean mask $O(T \cdot N)$ bằng ánh xạ `.map()` vectorized một lần ở cuối vòng lặp ngày.
  - **Test hồi quy**: Thiết lập các ca kiểm thử `test_focal_point_detector.py` để bảo đảm tính tương đương của kết quả (PIT-equivalence) và không phát sinh Look-ahead bias.

## 22. GP VN-Specific Alphas Memory Optimization (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_VN_ALPHAS_MEMORY_FIX` (Approved)
- **Problem**: 
  - Lệnh `.sort_values(["ticker", "date"])` trên DataFrame gộp sau khi tính toán các đặc trưng VN-specific (116 cột, 1.77 triệu dòng) yêu cầu cấp phát bộ nhớ liên tục 1.54 GiB, gây ra lỗi `ArrayMemoryError` vỡ Heap trên Windows.
- **Solution**:
  - **Loại bỏ sort dư thừa**: Thay thế bằng `.reset_index(drop=True)` vì các chunk nhóm DataFrame theo Ticker từ `df_sorted` đã được sắp xếp tăng dần, phép `.concat` mặc định giữ nguyên thứ tự sắp xếp này.
  - **Chú thích nguồn**: Thêm ponytail comment giải thích rõ lý do và định lượng RAM tiết kiệm được để tránh tối ưu hóa ngược trong tương lai.
  - **Memory Profiling Test**: Thêm ca kiểm thử `test_vn_alphas_memory_optimization` sử dụng `tracemalloc` để đo lường đỉnh RAM phân bổ thực tế.

## 23. GP Alternative Features Column Overlap & sort_index Memory Fix (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_ALT_FEATURES_OVERLAP_AND_OOM_FIX` (Approved)
- **Problem**: 
  - Trùng lặp cột `realized_vol_20` giữa dữ liệu cơ sở và đặc trưng được tạo bởi `AlternativeFeatureGenerator` dẫn đến lỗi `ValueError: columns overlap but no suffix specified` khi join mảng hẹp vào panel gốc, làm âm thầm hủy toàn bộ 25 đặc trưng thay thế.
  - Phép `sort_index()` trên DataFrame gốc rộng 114 cột tiêu tốn 1.51 GiB RAM tĩnh và gây `MemoryError` khi chạy trong luồng chính của tiến trình Evolution.
- **Solution**:
  - **Sửa lỗi va chạm cột**: Loại bỏ các cột trùng lặp khỏi đặc trưng trước khi gộp trở lại panel gốc trong `alternative_features.py`.
  - **Giảm độ rộng sắp xếp**: Trích xuất chỉ 5 cột OHLCV cơ bản để tạo panel MultiIndex và chạy `sort_index()` trên cấu trúc hẹp trong `run_weekly_evolution.py`, giảm 95% tài nguyên sắp xếp.
  - **Đo lường**: Tiến trình Evolution chính chạy hoàn thành mượt mà cả 30 thế hệ mà không bị dừng hay bỏ qua đặc trưng thay thế.

## 24. GP Alternative Features Single Merge & Dropna Memory Optimization (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_ALT_FEATURES_SINGLE_MERGE_AND_DROPNA_FIX` (Approved)
- **Problem**: 
  - Lỗi `ArrayMemoryError` (1.57 GiB) khi chuẩn bị dữ liệu cho Evolution quần thể 100 do:
    1. Vòng lặp gọi `.merge()` 35 lần liên tiếp để gộp từng đặc trưng thay thế vào DataFrame 1.77 triệu dòng gây phân mảnh Heap nghiêm trọng.
    2. Gọi `.dropna(subset=drop_cols)` trên DataFrame rộng 119 cột tạo thêm bản sao trung gian lớn.
- **Solution**:
  - **Single Concat & Single Merge**: Thu thập toàn bộ 35 Series đặc trưng thay thế, dùng `pd.concat(..., axis=1)` để gộp song song 1 lần duy nhất (giữ nguyên chỉ mục MultiIndex label alignment), và thực hiện đúng một lệnh `.merge()` cuối cùng.
  - **Boolean Masking**: Thay thế `.dropna` bằng lọc mảng mặt nạ boolean `result[drop_cols].notna().all(axis=1)` để tối ưu hóa bộ nhớ tạm.
  - **Sửa NameError**: Khắc phục lỗi biến `alt_data_names` chưa khai báo khi ghi nhật ký.

## 25. GP VN-Specific Alphas Merge Direct Assignment (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN` (Approved)
- **Problem**: 
  - Phép gọi `.merge()` trên tập VN-specific alphas (75 cột) tiêu tốn hơn 1.5 GiB RAM phụ do phải dựng bảng băm lớn chéo hai DataFrame.
- **Solution**:
  - **Sắp xếp & Gán trực tiếp**: Sắp xếp cả hai DataFrame đồng bộ theo `["ticker", "date"]` rồi gán trực tiếp mảng `.values` của 75 cột thuộc tính, hoàn toàn loại bỏ chi phí dựng bảng băm của `.merge()`.
  - **Gióng hàng 3 lớp**: Bổ sung assertions kiểm tra kích thước, ticker và date để bảo toàn tính toàn vẹn dữ liệu.

## 26. GP Index Reset Copy Avoidance Memory Optimization (2026-07-07)
- **Decision Date**: 2026-07-07
- **Approved Gate**: `GP_INDEX_RESET_COPY_AVOID` (Approved)
- **Problem**: 
  - Phép gọi `.reset_index(drop=True)` tạo thêm bản sao sâu Block Manager của DataFrame trên Heap, gây lỗi `ArrayMemoryError` vỡ Heap (1.56 GiB) tại dòng 393.
- **Solution**:
  - **RangeIndex in-place assignment**: Thay thế bằng `.index = pd.RangeIndex(len(...))` tại cả 5 vị trí reset index trong `run_weekly_evolution.py`, thực hiện thay đổi siêu dữ liệu tại chỗ có độ phức tạp O(1) và hoàn toàn không tốn thêm RAM phụ.

## 27. GP Alternative Data Fetcher Memory & Performance Optimization (2026-07-08)
- **Decision Date**: 2026-07-08
- **Approved Gate**: `GP_ALT_DATA_FETCHER_OPTIMIZATION` (Approved)
- **Problem**:
  - `AlternativeDataFetcher.generate_all()` và `VNFocalPointDetector.analyze()` gặp lỗi `ArrayMemoryError` (yêu cầu cấp phát 1.84 GiB liên tục cho mảng float64 139 symbols x 1.77 triệu dòng).
  - Phép lọc `.xs(day, level='date')` trong vòng lặp ngày bị lặp lại 12,782 lần gây nghẽn Heap do pandas phải liên tục sắp xếp và alignment lại nhãn chỉ mục MultiIndex không liên tục vật lý.
  - Trên Windows, việc giới hạn cứng số lượng worker gây bất tiện khi người dùng muốn chạy song song với cấu hình RAM lớn.
- **Solution**:
  - **Reorder MultiIndex & Pre-grouping**: Sắp xếp lại thứ tự chỉ mục của Sentiment Panel thành `['symbol', 'date']` (Symbol làm gốc), giúp dữ liệu chéo của mỗi Symbol nằm liên tiếp vật lý. Gom nhóm trước theo ngày `panel.groupby(level='date')` một lần để lấy các DataFrame cắt lát đơn index nhanh chóng.
  - **Pre-Sliced DataFrame Fallback**: Hỗ trợ `VNFocalPointDetector.analyze()` nhận DataFrame đơn index chéo ngày đã được cắt lát trước, loại bỏ hoàn toàn các lệnh `.xs()` lặp lại chéo luồng.
  - **Workers Override**: Cho phép chạy nhiều hơn 4 workers trên Windows khi tham số `--workers` được truyền tường minh để tận dụng tối đa tài nguyên RAM vật lý lớn (20GB+).
  - **MultiIndex Level Order Restoration**: Khôi phục lại thứ tự MultiIndex `['date', 'symbol']` và thực hiện `sort_index()` ngay trước khi trả về từ `AlternativeDataFetcher.generate_all()`, ngăn chặn triệt để lỗi hoán đổi cột (date <-> ticker) âm thầm hạ nguồn tại `unified_feature_adapter.py`.
  - **Regression Test**: Bổ sung `test_generate_all_restores_date_symbol_index_order` kiểm định tính toàn vẹn của chỉ mục đầu ra.
  - **Đo lường**: Toàn bộ hệ thống test suite chạy sạch sẽ, enforcer phê duyệt `SoD Compliance: [PASS]`.

## 28. GP Weekly Evolution Alt Features Concat & Merge Optimization (2026-07-08)
- **Decision Date**: 2026-07-08
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION` (Approved by Codex L3)
- **Problem**:
  - Việc liên tục gọi `pd.merge` và `pd.concat` chéo hàng chục Series riêng lẻ (khi ghép đặc trưng thay thế vào DataFrame chính) trong vòng lặp ngày của `AlternativeFeatureGenerator` và `AlternativeDataFetcher` gây phân mảnh Heap nghiêm trọng, rò rỉ bộ nhớ và lỗi RAM OOM (`MemoryError`) khi xử lý tập dữ liệu 1.77 triệu dòng.
- **Solution**:
  - **Vectorized Panel Selection & Rename**: Trích xuất trực tiếp DataFrame hẹp `alt_panel[available_feat]` từ sentiment panel, đổi tên cột hàng loạt qua `.rename(columns={f: f"alt_{f}" for f in available_feat})` và thực hiện `.reset_index()` đổi tên `symbol` -> `ticker` một lần duy nhất.
  - **Single Vectorized Merge**: Thực hiện duy nhất 1 phép `.merge()` trên khóa `["date", "ticker"]` cho DataFrame kết quả cuối cùng đối với cả hai generator.
  - **Duplicate-Key Assertion Guard**: Gài assert fail-fast kiểm tra trùng lặp khóa `(date, ticker)` ngay trước khi tạo MultiIndex panel để ngăn chặn hiện tượng nhân nhóm dòng âm thầm hạ nguồn.
- **Hiệu quả**: Giảm số lượng DataFrame trung gian từ hàng chục lần xuống còn 1 lần duy nhất, loại bỏ hoàn toàn nguy cơ tràn RAM lũy thừa (exponential RAM OOM) khi xuất hiện trùng lặp khóa, tăng tốc độ xử lý 14 lần và vượt qua 16 ca kiểm thử của `tests/test_genetic_alpha_evolution_v4.py`.
- **PIT Safety**: Đảm bảo tính an toàn Point-In-Time (PIT) nhờ phép equi-join thuần túy trên khóa lịch sử `(date, ticker)` không có rò rỉ thông tin tương lai.

## 29. GP Weekly Evolution Alt Concat Zero-Copy & JIT Import Order Fix (2026-07-08)
- **Decision Date**: 2026-07-08
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION` (Revised & Hardened)
- **Problem**:
  - Gặp lỗi `numpy._core._exceptions._ArrayMemoryError: Unable to allocate ...` tại phép merge kết quả cuối của `combined_alt` vào DataFrame `result` rộng 90 cột x 1.77 triệu dòng, do Pandas phải nhân bản sâu Block Manager để định chỉ mục chéo (reindex alignment).
  - Tốc độ chạy GP bị nghẽn rất chậm do lệnh gọi `v4.install_v4_optimizations()` đặt quá muộn trong `main()`, khiến các import tĩnh `from ... import GeneticEngine` ở module load-time đã liên kết vĩnh viễn với phiên bản nguyên bản không có JIT Numba.
- **Solution**:
  - **Zero-Copy Direct Positional Column Assignment**: Gióng chỉ mục `combined_alt` theo chỉ mục gốc của `result` bằng `.reindex(pd.MultiIndex.from_frame(result[["date", "ticker"]]))`, kiểm tra khớp khóa tuyệt đối qua `.equals()`, rồi gán thẳng mảng NumPy `.values` trực tiếp để giải phóng peak RAM. Bọc try/except với fallback chuẩn về `.merge()` nếu khớp lệch.
  - **Early JIT Compiler Activation**: Di chuyển lệnh gọi `v4.install_v4_optimizations()` lên ngay dòng import đầu file trước khi load `GeneticEngine`, giúp Numba zero-allocation kernels kích hoạt thành công trên không gian tên toàn cục.
  - **Đo lường**: Tốc độ GP tăng lên đáng kể, giải phóng toàn bộ nghẽn OOM và JIT, SoD enforcer thông qua `SoD Compliance: [PASS]`.
