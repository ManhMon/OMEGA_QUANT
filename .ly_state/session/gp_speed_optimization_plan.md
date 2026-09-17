# GP Speed Optimization Plan V7

## Scope

- `scripts/genetic_alpha_evolution_v4.py`
- `tests/test_gp_numba_jit_vm.py`
- `tests/test_genetic_alpha_evolution_v4.py`
- `tests/quant_test_genetic_engine_optimizations.py`

## Goal

Đóng đủ cả 6 gap trong gate `gp_speed_optimization_plan_review` cho tối ưu GP JIT VM V4, giữ nguyên hợp đồng toán học/PIT:

1. mask safety / valid-row contract
2. correlation degeneracy contract
3. Cholesky fallback safety
4. float32 precision contract
5. atomic cache synchronization
6. cache identity / collision verification

## Exact Code Anchors

Các thay đổi phải neo vào đúng các hàm/site hiện có trong `scripts/genetic_alpha_evolution_v4.py`:

- `_ensure_neutralization_jit_context`
- `_numba_batch_ridge_neutralize`
- `_batch_fold_ir_scores`
- `_numba_daily_ics`
- `_group_row_indices_by_date`
- `_GLOBAL_FOLD_FEATURES_CACHE` declaration + lookup/store sites
- `_DATE_GROUPS_CACHE` declaration + lookup/store sites
- `_neutralize_target_once(..., fold_cache_key)` call sites

## Non-Goals

- Không đổi logic PIT/T-1 lag.
- Không đổi fitness definition, early reject, island model.
- Không thêm dependency mới.
- Không đổi solver contract ngoài fallback an toàn khi Cholesky không hợp lệ.
- Không mở rộng sang V3 hay module khác.

## Six Gaps Required By L3

### 1. Mask safety / valid-row contract

#### Change

- `_numba_daily_ics` và mọi path compare scalar-vs-batch phải dùng cùng một vị từ `valid_row`:
  - `valid_row = isfinite(alpha_i) and isfinite(target_i)`
  - nếu có neutralized/residualized intermediates thì chỉ row có cả input correlation hữu hạn mới được giữ; không “revive” row từ non-finite thành valid ở bước sau.
- Joint finite mask phải được định nghĩa rõ: mask luôn là phép `AND` trên mọi vector trực tiếp đi vào correlation ở row đó; không mask riêng từng vế rồi suy luận ngầm.
- Minimum observations: nếu `valid_count <= 5` thì correlation output cho date đó là `NaN`.
- Empty/all-invalid output: nếu `valid_count == 0` hoặc mọi row invalid sau joint mask thì output date đó là `NaN`.
- Hành vi này phải đồng nhất giữa scalar reference path, batch path, và mọi parity harness.

#### Edge Fixtures

- `all_invalid`: alpha/target toàn `NaN`/`inf` sau mask; expected daily IC = `NaN`.
- `exactly_five_valid_rows`: chỉ 5 row valid; expected daily IC = `NaN` vì ngưỡng là `<= 5`.
- `six_valid_rows_with_one_inf`: 7 row input, 1 row `inf`, còn 6 row finite; expected dùng đúng 6 row finite.
- `mixed_nan_alignment`: alpha và target có `NaN` lệch vị trí; expected mask là giao hai phía, không union.
- `constant_after_mask`: còn đủ số row nhưng giá trị hữu hạn sau mask là hằng; expected IC = `NaN` do degeneracy, không 0.

#### Required Tests

- `test_numba_daily_ics_returns_nan_for_all_invalid_rows`
- `test_numba_daily_ics_returns_nan_when_valid_count_is_five`
- `test_numba_daily_ics_uses_joint_finite_mask`
- `test_batch_fold_ir_mask_safety_parity_with_scalar`

#### Acceptance

- Plan nêu rõ `valid_row` predicate, joint finite mask, và ngưỡng `valid_count <= 5`.
- Empty/all-invalid output được định nghĩa là `NaN`.
- Có fixture edge-case và expected behavior cụ thể, không mô tả mơ hồ.

### 2. Correlation degeneracy contract

#### Change

- Correlation path trong `_numba_daily_ics` và batch/scalar reference phải coi daily correlation là suy biến và trả `NaN` khi một trong các điều kiện sau đúng:
  - `valid_count <= 5`
  - `alpha_variance <= 1e-12`
  - `target_variance <= 1e-12`
  - `denom <= 1e-12`
  - bất kỳ accumulator/intermediate cần cho covariance/correlation là non-finite
- `denom` ở đây là mẫu số cuối cùng của correlation sau khi tính variance/covariance trên dữ liệu đã mask.
- Non-finite handling phải fail-closed thành `NaN`, không clip sang 0, không retry bằng công thức khác.
- Batch IR path phải propagate `NaN` hợp lệ từ daily IC thay vì ép thành 0 trước khi aggregate.

#### Required Regression Tests

- `test_numba_daily_ics_returns_nan_for_constant_alpha_regression`
- `test_numba_daily_ics_returns_nan_for_constant_target_regression`
- `test_numba_daily_ics_returns_nan_when_denom_below_threshold_regression`
- `test_numba_daily_ics_returns_nan_for_non_finite_accumulator_regression`
- `test_batch_fold_ir_scores_preserves_nan_from_daily_ic_degeneracy`

#### Acceptance

- Ngưỡng suy biến ghi rõ `variance <= 1e-12` và `denom <= 1e-12`.
- Non-finite handling ghi rõ trả `NaN`.
- Test names cụ thể, expected IC result cụ thể là `NaN`.

### 3. Cholesky fallback safety

#### Change

- `_numba_batch_ridge_neutralize` dùng Cholesky-first path khi gram ridge là SPD hợp lệ.
- Nếu `np.linalg.cholesky(...)` ném `LinAlgError`, fallback sang `np.linalg.solve`.
- Nếu diagonal sau ridge không hữu hạn hoặc có phần tử `<= 0`, bỏ qua Cholesky và đi thẳng sang `np.linalg.solve`.
- Contract này áp dụng cho cả shared gram và candidate-specific gram path.
- Không thêm retry ladder khác; một fallback là đủ.

#### Why

- Đóng blocker stability của solver khi giả định SPD bị phá bởi dữ liệu suy biến hoặc sai số số học.
- Giữ fast path cho case tốt, giữ correctness cho case xấu.

#### Required Tests

- `test_cholesky_fast_path_matches_ridge_reference`
- `test_cholesky_fallback_matches_ridge_reference_when_cholesky_fails`
- `test_cholesky_invalid_diagonal_uses_solve_reference`

#### Acceptance

- Không còn giả định Cholesky luôn thành công.
- `LinAlgError` không làm fail batch ridge path; solver fallback vẫn trả kết quả parity-safe.
- Invalid diagonal chặn Cholesky trước khi gọi factorization.

### 4. Float32 precision contract

#### Change

- Dtype contract phải được enumerate theo từng vùng tính toán:
  - `design_matrix`: build/solve bằng `float64`
  - Gram / ridge matrix: `float64`
  - Cholesky factorization: `float64`
  - `np.linalg.solve` fallback: `float64`
  - rank/correlation accumulators trong `_numba_daily_ics` và `_batch_fold_ir_scores`: `float64`
  - daily IC outputs: `float64`
  - neutralized outputs: `float64`
  - storage-only candidate matrices / preallocated stack buffers / cache payload snapshots: có thể giữ `float32` nếu chúng không phải accumulator hay solver workspace
- `float32` chỉ dùng cho storage/stack buffers; khi vào neutralization, rank, correlation, covariance, Cholesky, solve thì phải cast/promote sang `float64`.
- Adversarial tolerance contract:
  - IC drift tối đa giữa float32-storage path và float64 reference: `<= 1e-6`
  - neutralization drift tối đa giữa float32-storage path và float64 reference: `<= 1e-8`
- Không cho phép “all-float32 math” trong solver/correlation path.

#### Required Tests

- `test_float32_storage_daily_ic_matches_float64_reference_within_1e6`
- `test_float32_storage_neutralization_matches_float64_reference_within_1e8`
- `test_float32_storage_adversarial_rank_correlation_regression`

#### Acceptance

- Mỗi vùng tính toán chính có dtype contract rõ.
- Sai số đối kháng tối đa nêu rõ: IC `<= 1e-6`, neutralization `<= 1e-8`.
- Float32 chỉ còn là storage/stack-buffer contract.

### 5. Atomic cache synchronization

#### Change

- Thêm `threading.Lock` cho mỗi global cache mutation path có pattern check-then-set:
  - `_DATE_GROUPS_CACHE`
  - `_GLOBAL_FOLD_FEATURES_CACHE`
  - target neutralization shared cache nếu là global/shared mutable state
- Lock chỉ bọc vùng tối thiểu để đảm bảo atomically:
  - check entry hiện có
  - xác minh collision nếu hit
  - set/replacement nếu miss hoặc collision mismatch
- Không khóa compute loops nặng bên ngoài critical section.
- `_ensure_neutralization_jit_context` phải nằm trong plan thread-safety vì path này mutate shared feature dict/context.

#### Required Test

- `test_thread_stress_global_fold_target_and_program_caches`

#### Acceptance

- Thread stress không exception, không deadlock, output deterministic.
- Shared caches không bị corruption do concurrent warm-up.
- Lock scope tối thiểu, không kéo cả compute path vào critical section.

### 6. Cache identity / collision verification

#### Change

- Giữ content digest key làm khóa chính cho date groups, fold features, target neutralization.
- Bổ sung bước xác minh va chạm sau khi hit cache: nếu digest key trùng, phải so `np.array_equal(..., equal_nan=True)` giữa payload hiện tại và payload đã gắn với cache entry trước khi reuse.
- Nếu hash/digest trùng nhưng nội dung khác, coi là cache miss và rebuild entry.
- Cache entry vì vậy phải giữ cả value và canonical array snapshot/reference cần thiết để xác minh collision, tối thiểu cho các cache trong scope:
  - `_DATE_GROUPS_CACHE`
  - `_GLOBAL_FOLD_FEATURES_CACHE`
  - target neutralization fold cache path
- `array_equal` check phải match cả `shape` và `dtype` trước; chỉ so nội dung khi hai yếu tố này khớp.

#### Required Tests

- `test_date_groups_cache_clone_hits_and_forced_collision_rebuilds`
- `test_fold_features_cache_clone_hits_and_forced_collision_rebuilds`
- `test_target_neutralization_cache_nan_payload_collision_rebuilds`

#### Acceptance

- Copy/clone cùng nội dung vẫn hit cache.
- Hai mảng khác nội dung nhưng cùng digest key giả lập không được reuse nhầm.
- Mọi cache hit trong scope dùng xác minh `dtype`/`shape` + `np.array_equal(..., equal_nan=True)` trước khi trả entry.

## File-Level Implementation Breakdown

### `scripts/genetic_alpha_evolution_v4.py`

1. Giữ helper digest key theo content cho array-backed caches trong scope.
2. Đổi cache entry shape để giữ metadata phục vụ collision verification (`dtype`, `shape`, canonical array hoặc snapshot đủ để `array_equal`).
3. Thêm helper nhỏ cho cache hit validation:
   - kiểm `dtype`
   - kiểm `shape`
   - kiểm `np.array_equal(..., equal_nan=True)`
4. Bọc check-then-set của `_DATE_GROUPS_CACHE` và `_GLOBAL_FOLD_FEATURES_CACHE` bằng `threading.Lock`.
5. Siết `_ensure_neutralization_jit_context` mutation path nếu cần để thread stress pass mà vẫn giữ pickle-safe feature dict.
6. Cập nhật `_numba_batch_ridge_neutralize` sang Cholesky-first với fallback `np.linalg.solve` khi `LinAlgError` hoặc diagonal không hợp lệ.
7. Chuẩn hóa `_numba_daily_ics` quanh hợp đồng `valid_row`, `valid_count <= 5`, `variance <= 1e-12`, `denom <= 1e-12`, non-finite to `NaN`.
8. Giữ correlation/rank/solver math ở `float64`; chỉ để `float32` ở storage/stack buffers nơi không ảnh hưởng accumulator/solver correctness.

### `tests/test_gp_numba_jit_vm.py`

- Thêm test parity cho Cholesky fast path, fallback path, invalid-diagonal path.
- Mọi parity test khóa `dtype`, `shape`, rồi `assert_allclose(..., equal_nan=True)`.
- Thêm case mask safety và correlation degeneracy với expected `NaN` rõ ràng.
- Thêm adversarial float32-storage-versus-float64-reference regressions.

### `tests/test_genetic_alpha_evolution_v4.py`

- Thêm regression cho cache collision verification.
- Thêm test clone-hit và collision-mismatch-rebuild cho fold/date/target cache path phù hợp.
- Thêm parity regression cho output chứa `NaN` nếu scope test đi qua batch/scalar compare.

### `tests/quant_test_genetic_engine_optimizations.py`

- Giữ stress test `ThreadPoolExecutor`.
- Bổ sung assertion nhắm đúng atomic cache synchronization: concurrent warm-up không double-corrupt, không race visible, không hang.
- Thêm assertion deterministic cho float32 storage buffers không đổi output ngoài bound đã khai báo.

## Verification Plan

### Required Tests

- `pytest tests/test_gp_numba_jit_vm.py`
- `pytest tests/test_genetic_alpha_evolution_v4.py`
- `pytest tests/quant_test_genetic_engine_optimizations.py`

### Required Assertions

1. Solver parity: `assert actual.dtype == expected.dtype`, `assert actual.shape == expected.shape`, rồi `assert_allclose(..., rtol=1e-8, atol=1e-8, equal_nan=True)`.
2. IC/rank parity: `assert actual.dtype == expected.dtype`, `assert actual.shape == expected.shape`, rồi `assert_allclose(..., rtol=1e-6, atol=1e-6, equal_nan=True)`.
3. Mask safety: `valid_count <= 5` trả `NaN`; joint finite mask phải match scalar reference exactly.
4. Correlation degeneracy: `variance <= 1e-12` hoặc `denom <= 1e-12` trả `NaN`; non-finite intermediate trả `NaN`.
5. Float32 precision: float32-storage path so với float64 reference không vượt IC drift `1e-6`, neutralization drift `1e-8`.
6. Cache collision: forced-collision scenario phải rebuild/miss, không reuse sai entry.
7. Thread stress: completed futures count == submitted count trong timeout; repeated outputs identical; không cache corruption.
8. Cholesky fallback: cả `LinAlgError` path và invalid-diagonal path đều trả kết quả khớp reference solver.

### Acceptance Criteria

1. Plan đóng đủ cả 6 gaps của L3, không còn framing chỉ 4 blockers.
2. Mask safety contract nêu rõ `valid_row`, joint mask, `valid_count <= 5`, empty/all-invalid = `NaN`, fixtures cụ thể.
3. Correlation degeneracy contract nêu rõ `variance <= 1e-12`, `denom <= 1e-12`, non-finite = `NaN`, regression names cụ thể.
4. Cholesky plan nêu rõ fallback `np.linalg.solve` khi `LinAlgError` hoặc diagonal không hợp lệ.
5. Float32 plan nêu rõ dtype per function/region, float64 accumulators/solver, float32 chỉ storage, bounds `1e-6` và `1e-8`.
6. Thread-safety plan nêu rõ `threading.Lock` cho atomic check-then-set trên shared caches.
7. Cache hit contract trong scope bao gồm collision verification bằng `np.array_equal(..., equal_nan=True)`.

## Risks And Mitigations

### Risk: collision verification giữ thêm array snapshot làm tốn RAM

- Mitigation: chỉ giữ snapshot tối thiểu cho cache entries nóng trong scope; không mở rộng ra cache ngoài scope.

### Risk: lock quá rộng làm chậm throughput

- Mitigation: chỉ khóa check/validate/set path; compute ngoài lock.

### Risk: fallback `np.linalg.solve` che mất lỗi dữ liệu thật

- Mitigation: chỉ fallback cho failure toán học kỳ vọng; test phải khóa parity với ridge reference để bắt regression.

### Risk: float32 storage silently leaks vào solver/correlation math

- Mitigation: plan khóa rõ vùng nào phải promote/cast sang `float64`; regression đối kháng bắt drift vượt ngưỡng.

## Lessons Applied

- Lesson 1: giữ pre-allocation/reuse, không thêm allocation thừa trong hot loop; collision verification nằm ở cache boundary.
- Lesson 2: thread stress vẫn tôn trọng caps trên joblib threads; lock chỉ quanh shared cache mutation.
- Lesson 3: không đụng fast path `searchsorted` split ngoài phạm vi 6 gaps này.

## Deliverable Shape For Implementation Phase

- Patch tối thiểu, tập trung vào `scripts/genetic_alpha_evolution_v4.py` và các test liên quan.
- Không thêm abstraction thừa ngoài helper collision-check/lock đủ nhỏ.
- Không audit hay approve; chỉ chuẩn bị plan đủ chặt để L3 review lại.
