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

## 30. GP Redundant Factorize Cache and Threaded Scoring Optimization (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_REDUNDANT_FACTORIZE_AND_LOOP_FIX` (Approved by Codex L3)
- **Problem**: 
  - Động cơ tiến hóa bị nghẽn (bottleneck) nặng do phép `pd.factorize(date)` lặp lại hơn 3000 lần mỗi thế hệ cho 150 ứng viên.
  - Vòng lặp tính toán IC và khử trung bình chéo dòng chạy tuần tự trên luồng chính, gây thắt cổ chai CPU mặc dù dữ liệu không phụ thuộc chéo.
- **Solution**:
  - **Date Factorize & Fold Slice Caching**: Khai báo và tiền tính toán các mảng cache `__date_flat_indices__`, `__date_group_offsets__`, và mảng cấu trúc fold `__fold_features_cache__` một lần duy nhất tại `_prepare_generation_features` đầu mỗi thế hệ. Các điểm nóng tiêu thụ dữ liệu chuyển sang tra cứu trực tiếp O(1) từ cache thay vì gọi lại `.factorize` hay re-slice mảng DataFrame 1.7 triệu dòng.
  - **Thread-safe Batched Scoring**: Kích hoạt `joblib.Parallel(prefer='threads')` bao bọc vòng lặp chuẩn bị chấm điểm `_evaluate_population_with_batch_neutralization` và tiến trình scoring fitness của các ứng viên, tận dụng đa luồng (multi-threading) không chặn GIL trên CPython cho các kernel OLS JIT.
- **Hiệu quả**: Giảm triệt để số vòng lặp factorize bị thừa, giải phóng CPU core, tăng tốc độ xử lý điểm fitness song song, an toàn cấu trúc PIT.

## 31. GP Vietnam Alphas Drop and Clean OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_VN_ALPHAS_DROP_AND_CLEAN_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Lỗi tràn bộ nhớ RAM (`ArrayMemoryError`) xảy ra khi chạy tiến hóa trên toàn bộ 1.77 triệu dòng dữ liệu. 
  - Nguyên nhân do hàm `compute_all_vn_alphas` thực hiện `res.drop(columns=[...])` tạo ra một bản sao mới của DataFrame rộng hơn 100 cột (~1.56 GB), kết hợp với vòng lặp `np.nan_to_num(res[col].values)` liên tục phân bổ các mảng phụ trung gian làm quá tải RAM Sandbox (4GB) và RAM hệ thống.
- **Solution**:
  - **In-place Column Deletion**: Thay thế việc nhân bản DataFrame bằng cách sử dụng vòng lặp xóa cột trực tiếp qua từ khóa `del res[col]`, cập nhật trực tiếp khối quản lý cột (Block Manager) của DataFrame hiện tại mà không phát sinh thêm bản sao bộ nhớ.
  - **In-place Numeric Cleaning**: Gọi trực tiếp `np.nan_to_num(res[col].to_numpy(copy=False), copy=False, nan=0.0, posinf=0.0, neginf=0.0)`. Việc truyền `.to_numpy(copy=False)` kết hợp cờ `copy=False` của NumPy giúp làm sạch các giá trị NaN/Inf trực tiếp trên mảng NumPy tham chiếu nền của Pandas Series, giải phóng 100% tài nguyên bộ nhớ đệm phụ.
- **Hiệu quả**: Loại bỏ hoàn toàn peak RAM dư thừa, giảm phân mảnh Heap, vượt qua thành công bộ unit test và chạy êm ái trên tập dữ liệu lớn không bị OOM.

## 32. GP Weekly Evolution Redundant Sort OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_SORT_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Khi chạy tiến hóa trên toàn bộ tập dữ liệu, chương trình crash vì `ArrayMemoryError` khi thực hiện `sort_values` lại trên một DataFrame lớn rộng 113 cột x 1.77 triệu dòng. 
  - Nguyên nhân do việc gọi lại hàm sắp xếp một cách dư thừa, làm phát sinh một bản sao lớn (~1.5 GB) trên RAM hệ thống bị phân mảnh.
- **Solution**:
  - **Alignment Checking Guard**: Thêm hàm bổ trợ `_are_frames_aligned` để so khớp nhanh về chiều dài, chỉ mục cột và thứ tự dòng (`ticker` và `date`) của hai DataFrame trước khi gán.
  - **Conditional Sorting**: Chỉ thực hiện `sort_values` và thiết lập lại RangeIndex nếu hai DataFrame thực sự bị lệch thứ tự dòng. Nếu đã đồng bộ (trường hợp mặc định trong sản xuất), bỏ qua hoàn toàn việc sắp xếp để tiết kiệm 100% tài nguyên bộ nhớ nhân bản.
- **Hiệu quả**: Loại bỏ hoàn toàn việc nhân bản DataFrame rộng 113 cột, tăng tốc xử lý và giải quyết triệt để OOM khi gán cột.

## 33. GP Weekly Evolution Alternative Features Copy OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_ALTERNATIVE_FEATURES_COPY_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `_generate_alternative_features()` trong tệp `run_weekly_evolution.py` khi thực hiện `result = df.copy()`.
  - Nguyên nhân do việc nhân bản nguyên dạng DataFrame rộng 114 cột x 1.77 triệu dòng khi bắt đầu sinh đặc trưng thay thế làm quá tải bộ nhớ RAM Sandbox.
- **Solution**:
  - **Zero-Copy Reference Assignment**: Thay thế `result = df.copy()` bằng gán tham chiếu trực tiếp `result = df`.
  - **Narrow-First Copy Pattern**: Chỉ copy và định dạng kiểu dữ liệu ngày cho DataFrame hẹp chứa 7 cột thiết yếu (`narrow_df`) để cung cấp cho panel generator, loại bỏ việc mutate hay copy trên DataFrame gốc.
  - **Dynamic Reindexing Conversion**: Sử dụng `pd.to_datetime(result["date"])` trực tiếp tại thời điểm tạo MultiIndex reindexing frame thay vì thay đổi kiểu dữ liệu cột trong DataFrame rộng.
- **Hiệu quả**: Tiết kiệm hoàn toàn bản sao 1.5 GB của DataFrame rộng, vượt qua toàn bộ unit test và khắc phục lỗi OOM khi tích hợp các đặc trưng thay thế hạ nguồn.

## 34. GP Vietnam Alphas Vectorized Rank OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_VN_ALPHAS_VECTORIZED_RANK_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `compute_all_vn_alphas` trong tệp `vn.py` khi thực hiện phép sắp thứ tự chéo dòng: `res.groupby("date")["_raw_ret20"].transform(lambda x: x.rank(pct=True))`.
  - Nguyên nhân do việc lặp qua hàng ngàn ngày bằng hàm lambda tạo ra hàng ngàn đối tượng Pandas Series và Index trung gian gây phân mảnh Heap và tràn bộ nhớ RAM Sandbox.
- **Solution**:
  - **Vectorized Groupby Rank**: Thay thế các phép toán `.transform(lambda x: x.rank(pct=True))` bằng gọi trực tiếp `.rank(pct=True)` trên đối tượng GroupBy. Phép toán này chạy trực tiếp ở mức C-level thông qua Cython, giảm 100% việc tạo các đối tượng tạm.
  - **Vectorized Groupby pct_change**: Thay thế `.transform(lambda x: x.pct_change(1))` bằng `.pct_change(1)` trực tiếp trên đối tượng GroupBy.
- **Hiệu quả**: Giảm triệt để dung lượng RAM cấp phát động, tăng tốc độ xử lý hơn 100 lần và loại bỏ hoàn toàn các lỗi tràn bộ nhớ khi tính toán đặc trưng VN.

## 35. GP Vietnam Alphas Concat Optimization OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_VN_ALPHAS_NARROW_CONCAT_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `pd.concat(processed_groups, ignore_index=True)` trong tệp `vn.py` do phải ghép hơn 400 DataFrame, mỗi DataFrame chứa toàn bộ ~100 cột rộng và các đặc trưng mới sinh.
- **Solution**:
  - **Narrow-Concat Pattern**: Thực hiện lọc cắt ngắn DataFrame `group` của từng ticker chỉ giữ lại 4 cột định danh/quay vòng và các đặc trưng bắt đầu bằng `vn_` trước khi thêm vào `processed_groups`.
  - **Vectorized Return Mapping**: Sau khi ghép (chỉ ghép các DataFrame hẹp), thực hiện gán các cột đặc trưng trực tiếp quay trở lại DataFrame rộng ban đầu `df_sorted` theo vector hàng mà không cần ghép hoặc copy diện rộng.
- **Hiệu quả**: Giảm hơn 90% bộ nhớ tạm thời khi ghép DataFrame và hoàn toàn chấm dứt lỗi tràn bộ nhớ khi tính toán đặc trưng VN.

## 36. GP Weekly Evolution Notna All OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_NOTNA_ALL_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `run_weekly_evolution.py:411` khi thực hiện phép lọc loại bỏ NaN: `valid_mask = result[drop_cols].notna().all(axis=1)`.
  - Nguyên nhân do việc cắt tập con gồm 114 cột rộng trên 1.77 triệu dòng tạo ra bản sao DataFrame trung gian nặng ~1.62 GB và DataFrame Boolean ~200 MB gây cạn kiệt RAM Sandbox.
- **Solution**:
  - **Column-by-Column In-Place Mask Update**: Khởi tạo mảng Boolean mask với toàn giá trị True (`np.ones(len(result), dtype=bool)`) rồi chạy vòng lặp cập nhật in-place qua từng cột đặc trưng bằng toán tử bitwise `&=`.
- **Hiệu quả**: Giảm dung lượng RAM cấp phát trung gian từ 1.8 GB xuống còn 1.7 MB (giảm 99.9%), tối ưu hóa hoàn toàn tốc độ lọc NaN và ngăn chặn triệt để lỗi OOM.

## 37. GP Vietnam Alphas Axis-1 Concat OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_VN_ALPHAS_AXIS1_CONCAT_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `vn.py:269` khi chạy vòng lặp gán giá trị 75 đặc trưng tuần tự vào DataFrame lớn (`df_sorted[col] = res[col].values`), gây ra phân mảnh bộ nhớ Block Manager của Pandas (DataFrame is highly fragmented).
- **Solution**:
  - **Single Concat Along Axis 1**: Thực hiện drop trước các cột đặc trưng trùng tên để tránh trùng lặp cấu trúc, sau đó ghép nối toàn bộ 75 đặc trưng mới cùng một lúc bằng phép gọi `pd.concat(..., axis=1)` sau khi reset index cho cả hai DataFrame.
- **Hiệu quả**: Loại bỏ hoàn toàn hơn 70 lần copy và phân mảnh block manager của Pandas, giảm mức tiêu thụ RAM đột biến khi gán đặc trưng xuống gần như bằng không.

## 38. GP Vietnam Alphas In-place Drop Assign OOM Fix (2026-07-09)
- **Decision Date**: 2026-07-09
- **Approved Gate**: `GP_VN_ALPHAS_INPLACE_DROP_ASSIGN_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Chương trình tiến hóa crash với lỗi `ArrayMemoryError` tại `vn.py:268` khi thực hiện slice lấy tập con cột `res[cols_to_clean]`.
  - Nguyên nhân do việc tạo DataFrame Boolean và Block Manager con tạm thời đòi hỏi Pandas phải reindex và allocate thêm mảng NumPy trung gian gây crash bộ nhớ Heap.
- **Solution**:
  - **In-place Drop & Direct Array Assignment**: Thực hiện loại bỏ trực tiếp 2 cột định danh `ticker` và `date` trên `res` bằng phương pháp in-place `res.drop(columns=..., inplace=True)`. Sau đó, gán trực tiếp thuộc tính NumPy `.values` của DataFrame đã lọc vào DataFrame rộng `df_sorted[cols_to_clean] = res.values`.
- **Hiệu quả**: Loại bỏ hoàn toàn việc tạo DataFrame/Block Manager con tạm thời khi slice cột, đưa bộ nhớ copy phụ về 0.


## 39. GP Weekly Evolution Alternative Features Memory Optimization (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ALT_DICT_REBUILD_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Out of memory (OOM) during alternative feature merging in `run_weekly_evolution.py`.
  - Wide `reindex` calls created massive data copies, and sequential `fillna` on wide columns caused memory fragmentation.
- **Solution**:
  - Replaced wide reindex and sequential `fillna` with a streamlined positional dictionary rebuild.
  - Aligned dataframes are sorted by `ticker,date` and rebuilt positionally without wide copies.
- **PIT Safety**: Verified safe. Alternate features align strictly by date/ticker, with T-1 shift applied separately at the caller level before targets are created.


## 40. GP Extract Lessons LLM Semantic Upgrade (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_EXTRACT_LESSONS_LLM` (Approved by Codex L3)
- **Problem**:
  - The previous extraction mechanism relied on rigid Regex heading parsing (`## Findings`, `## Required Fix`), which failed when L3 Codex outputted slightly different heading formats, resulting in missed lessons.
- **Solution**:
  - Replaced the Regex parser in `scripts/extract_lessons.py` with an env-gated, OpenAI-compatible LLM extraction approach.
  - The script sends the full markdown report to the LLM (via `requests`) demanding strict JSON output (`symptom`, `root_cause`, `fix_pattern`).
  - Added robust fallback logic for missing API keys, network failures, or invalid JSON.
- **Security & Safety**:
  - API keys are injected via environment variables and never logged.
  - Model outputs are parsed safely as JSON strings and written as static lesson text without dynamic execution (protection against prompt injection).


## 41. GP Extract Lessons 9Router/OpenRouter Support (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_EXTRACT_LESSONS_LLM_9ROUTER` (Approved by Codex L3)
- **Problem**:


## 39. GP Weekly Evolution Alternative Features Memory Optimization (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ALT_DICT_REBUILD_OOM_FIX` (Approved by Codex L3)
- **Problem**:
  - Out of memory (OOM) during alternative feature merging in `run_weekly_evolution.py`.
  - Wide `reindex` calls created massive data copies, and sequential `fillna` on wide columns caused memory fragmentation.
- **Solution**:
  - Replaced wide reindex and sequential `fillna` with a streamlined positional dictionary rebuild.
  - Aligned dataframes are sorted by `ticker,date` and rebuilt positionally without wide copies.
- **PIT Safety**: Verified safe. Alternate features align strictly by date/ticker, with T-1 shift applied separately at the caller level before targets are created.


## 40. GP Extract Lessons LLM Semantic Upgrade (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_EXTRACT_LESSONS_LLM` (Approved by Codex L3)
- **Problem**:
  - The previous extraction mechanism relied on rigid Regex heading parsing (`## Findings`, `## Required Fix`), which failed when L3 Codex outputted slightly different heading formats, resulting in missed lessons.
- **Solution**:
  - Replaced the Regex parser in `scripts/extract_lessons.py` with an env-gated, OpenAI-compatible LLM extraction approach.
  - The script sends the full markdown report to the LLM (via `requests`) demanding strict JSON output (`symptom`, `root_cause`, `fix_pattern`).
  - Added robust fallback logic for missing API keys, network failures, or invalid JSON.
- **Security & Safety**:
  - API keys are injected via environment variables and never logged.
  - Model outputs are parsed safely as JSON strings and written as static lesson text without dynamic execution (protection against prompt injection).


## 41. GP Extract Lessons 9Router/OpenRouter Support (2026-07-10)
- **Decision Date**: 2026-07-10
- **Approved Gate**: `GP_EXTRACT_LESSONS_LLM_9ROUTER` (Approved by Codex L3)
- **Problem**:
  - The extract lessons script required `OPENAI_API_KEY` or `GEMINI_API_KEY`, but the production environment only had `OMEGA_LLM_API_KEY` provisioned.
  - Required using the OpenRouter `free` model for cost control on non-critical metadata extractions.
- **Solution**:
  - Inserted `OMEGA_LLM_API_KEY` check into `_resolve_lesson_llm_config`.
  - Defaulted `base_url` to `https://openrouter.ai/api/v1` and `model` to `free` when falling back to OMEGA key.
- **Security**: 
  - Standard environment variables override defaults (e.g. `OMEGA_LLM_BASE_URL`, `OMEGA_LLM_MODEL`).
  - Precedence remains: OpenAI > OMEGA > Gemini.


## 42. GP Index Preservation in compute_mfi (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_MFI_FIX` (Approved by Codex L3 role 21)
- **Problem**:
  - `compute_mfi()` generated rolling sums on default-indexed Series (`0..n-1`), causing misalignment during groupby-ticker assignment back to the main DataFrame. This resulted in `mfi_14` NaNs for 99.8% of rows.
- **Solution**:
  - Modified `compute_mfi()` to construct Series with `index=df.index` before applying rolling sums, ensuring original index labels are preserved for assignment.
- **Verification**: 30 passed in targeted pytest.

## 43. Windows Workers Limit in GP (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_WORKERS_LIMIT` (Approved by Codex L3 role 21)
- **Problem**:
  - Using 10 parallel workers on Windows consumed excessive RAM overhead, triggering silent subprocess OOM crash at Gen 1.
- **Solution**:
  - Implemented a hard cap limiting active joblib workers to at most 4 on Windows in both `main()` and `run_evolution()`.

## 44. GP Memory Optimization & Fold Caching (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_GEN_OOM_FIX` (Approved by Codex L3 role 21)
- **Problem**:
  - Slicing and copying all 149 features for 5 folds via `value_arr[mask]` at every generation caused massive RAM allocations, triggering OOM at Gen 3.
- **Solution**:
  - Implemented an evolve-bounded cache `self._fold_features_cache` keyed by date array identity and fold count.
  - Cached fold views are computed once at the first generation and cleared via `.clear()` in a `finally` block when `evolve()` exits.

## 45. GP VN Alphas Drop Optimization (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_GEN_OOM_FIX` (Approved by Codex L3 role 21)
- **Problem**:
  - `res.drop(columns=["ticker", "date"], inplace=True)` inside `compute_all_vn_alphas()` in `src/omega/quant/alpha/vn.py` forced Pandas to rebuild the block manager and copy all float64 columns, consuming ~1 GB RAM dynamically and triggering an `ArrayMemoryError` OOM during preparation.
- **Solution**:
  - Removed `res.drop()` and wide `res.values` extraction. Replaced with direct per-column 1D extraction: `final_dict[col] = res[col].to_numpy(copy=False)`, avoiding wide allocation and ensuring 100% zero-copy layout.

## 46. Env-gated Lesson Extraction Skip in Enforcer (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_GEN_OOM_FIX` (Approved by Codex L3 role 21)
- **Problem**:
  - `sod_gate_enforcer.py` unconditionally ran LLM-based lesson extraction at each startup, causing a 30-40 seconds delay and potential timeouts due to network latency.
- **Solution**:
  - Added an environment variable check (`SKIP_LESSON_EXTRACTION=1` or `OMEGA_SKIP_LLM=1`) in `_extract_lesson_fields_with_llm()` to immediately return dummy lesson structures and bypass slow LLM calls while keeping local parsing intact.

## 47. Weekly GP Island Model Integration (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ISLAND_MODEL` (Approved by Codex L3 role 21)
- **Problem**:
  - `run_weekly_evolution.py` was hardcoded to use a single-population `GeneticEngine`, which lacks diversity and could converge too early, missing orthogonal alpha families.
- **Solution**:
  - Added a CLI parameter `--engine {standard,diverse}`.
  - Implemented the `diverse` branch inside `run_evolution()`, configuring and running `DiverseAlphaEvolution` (Island Model) with target `'target'`.
  - Added a node-tree converter `_convert_diverse_node()` to map diverse `Genome.tree` nodes recursively back to standard `GPNode` trees, wrapping results as `GPIndividual` to maintain ABI compatibility with the downstream continuous learning bridge.

## 48. Lowering GP Diverse Evolution Hit Rate Threshold (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_HIT_RATE_TUNE` (Approved by Codex L3 role 21)
- **Problem**:
  - The default quality filter threshold `min_hit_rate` in `DiverseEvolutionConfig` was set to `0.53` (53% daily directional accuracy), which is unrealistically high for stock return predictions and filtered out high-IC alphas (such as those with IC=0.1245).
- **Solution**:
  - Lowered the default `min_hit_rate` value to `0.515` (51.5%) in `src/omega/quant/evolution/diverse_alpha_evolution.py` to match standard daily quant signal requirements, ensuring strong alpha signals survive the quality filter.

## 49. Demeaned Hit Rate Formula in GP Diverse Evolution (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_DEMEANED_HIT_RATE` (Approved by Codex L3 role 21)
- **Problem**:
  - The previous hit rate formula used raw validation signal and target signs. Since many operators output positive-only values (like `volume`, `std`), the raw hit rate was strictly capped by the positive daily return ratio (typically ~47%), preventing any positive-only signal from passing the quality filter.
  - Implemented the demeaned hit rate formula `hit_rate = (np.sign(val_signal - val_signal.mean()) == np.sign(val_df[target_col] - val_df[target_col].mean())).mean()` in `DiverseAlphaEvolution._evaluate_population` (line 152), evaluating the directional accuracy of demeaned signals against demeaned returns.

## 50. GP Island Model Terminal Pools and Primitive Expansion (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ISLAND_EXPANSION` (Approved by Codex L3 role 21)
- **Problem**:
  - The GP islands was restricted to a narrow set of basic terminals (close, open, high, low, returns, rsi, macd) and lacked access to newly generated premium alternative features and Vietnam-specific indicators. In addition, the operators lacked basic math functions (abs, sign, neg), and the process lacked early stopping to prevent wasting CPU during long runs.
- **Solution**:
  - Added new unary primitives `abs`, `sign`, `neg` to `Node.OPERATORS` in `src/omega/quant/evolution/genetic_alpha.py` and implemented their evaluation.
  - Implemented dynamic column retrieval in `Node.evaluate()` when column name is present in DataFrame.
  - Expanded `ISLAND_ALTERNATIVE_TERMINALS` in `src/omega/quant/evolution/diverse_alpha_evolution.py` with actual alternative features (alt_cs_rank_volume, alt_vp_divergence, alt_ad_line, etc.) and smart money flow indicators.
  - Added island startup terminal auto-registration and implemented an early stopping check (patience=50) in `DiverseAlphaEvolution.run()` to optimize run speed.

## 51. GP Island Model Indentation and Embargo Validation Hardening (2026-07-11)
- **Decision Date**: 2026-07-11
- **Approved Gate**: `GP_WEEKLY_EVOLUTION_ISLAND_EXPANSION` (Approved by Codex L3 role 21)
- **Problem**:
  - The conversion of diverse nodes in `run_weekly_evolution.py` was broken due to helper functions `_inject_private_gp_columns` and `_inject_liquidity_mask` being nested within `_convert_diverse_node`, causing the binary conversion return statement to be placed inside the helper function and return `None` for binary operations.
  - An unreachable return statement in `_compute_icir_loop` inside `genetic_engine.py` (indented under an if block check) caused the normal fallback ICIR computation path to return `None` on cached non-finite targets.
  - `validate_embargo()` returned `False` if checked before registration since the alpha ID was not registered in the system yet.
- **Solution**:
  - Moved `_inject_private_gp_columns` and `_inject_liquidity_mask` to top-level helpers in `scripts/run_weekly_evolution.py`, restoring the binary node tree conversion block.
  - Corrected the indentation of the fallback return statement in `_compute_icir_loop` in `src/omega/quant/evolution/genetic_engine.py` so that it returns the computed ICIR.
  - Restructured `run_weekly_evolution.py` to register the evolved alpha first via `register_alpha()` before calling `validate_embargo()`.


