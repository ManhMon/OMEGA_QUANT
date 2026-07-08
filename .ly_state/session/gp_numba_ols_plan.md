# Kế hoạch Chi tiết Triển khai GP Numba OLS JIT Neutralization

## 1. Mục tiêu & Chỉ số chấp nhận (Acceptance Criteria)
Tối ưu hóa triệt để điểm nghẽn OLS Neutralization trong hệ thống tiến hóa GP V4 trên toàn vũ trụ 700 mã (~1.25M dòng):
1. **JIT hóa OLS Neutralization**: Thay thế các hàm khử trùng lặp hồi quy bình phương tối thiểu chéo dòng của Python bằng các nhân tố **Numba JIT `@njit(cache=True, nogil=True)`** chạy song song giải phóng GIL hoàn toàn.
* **Mục tiêu hiệu năng**:
  * Tốc độ thực thi OLS Neutralization tăng tốc **$\ge 10\text{x}$ lần**.
  * Thời gian tiến hóa toàn tải 5 thế hệ (100 population, 3 Folds) trên toàn vũ trụ ~1.25M dòng hoàn tất trong **dưới 3 phút** (rất nhanh so với mức hàng chục phút cũ!).

---

## 2. Thiết kế Kỹ thuật OLS JIT Neutralization

### A. Cấu trúc Ma trận Thiết kế (Design Matrix) phẳng
* Thay vì lưu trữ cache thiết kế dưới dạng Dictionary của các ma trận con ở lớp Python, chúng ta sẽ tiền xây dựng và chuyển đổi toàn bộ ma trận thiết kế OLS thành một mảng NumPy 2D phẳng duy nhất `design_matrix` có kích thước `(N_ROWS, K)` (với $K$ là số lượng cột biến giải thích bao gồm intercept, log_mcap và các biến dummy sector).
* Mảng nhị phân `design_valid_mask` (bool, kích thước `N_ROWS`) đánh dấu dòng hợp lệ của ma trận thiết kế cũng được phẳng hóa.

### B. Thuật toán Giải OLS song song chéo Ngày (Numba JIT) và Rank-Safety (Ridge Regression)
Để giải quyết triệt để các vấn đề Codex L3 cảnh báo trong đợt audit trước, thiết kế giải thuật được chuẩn hóa như sau:

1. **Hợp đồng Solver (Explicit Ridge Contract)**:
   * Chấp nhận hồi quy Ridge (L2 regularization) với tham số phạt $\lambda = 10^{-6}$ là hợp đồng tính toán chính thức thay thế cho OLS lstsq truyền thống. 
   * Tính toán Ridge đảm bảo độ ổn định ma trận tuyệt đối khi số lượng dòng thực tế bị thu hẹp hoặc gặp hiện tượng đa cộng tuyến.
   * Tất cả các bộ test kiểm thử đúng đắn số học sẽ được viết để so khớp kết quả JIT Kernel với mô hình Ridge chính thức của Python (`scikit-learn.linear_model.Ridge(alpha=1e-6, fit_intercept=False)`), thay vì so sánh với OLS thông thường.

2. **Thiết kế Không phân bổ bộ nhớ (Zero-Allocation Design)**:
   * Loại bỏ hoàn toàn việc phân bổ mảng động (`X_sub`, `y_sub`, `indices_sub`, `y_res`) trong vòng lặp ngày. Việc cấp phát bộ nhớ động liên tục trong 2.500 ngày sẽ gây ra overhead lớn và phân mảnh bộ nhớ trên Windows.
   * Tận dụng khả năng lưu trữ biến cục bộ của Numba JIT (dịch thành Stack/Registers cực nhanh). Các mảng hiệp biến `XtX` ($K \times K$) và `Xty` ($K$) được khởi tạo một lần cục bộ và tái sử dụng.
   * **Cơ chế Accumulate trực tiếp**: Duyệt qua các chỉ số dòng của ngày trong mảng `date_flat_indices` và trực tiếp cộng tích lũy tổng bình phương vào `XtX` và `Xty` mà không cần cắt mảng.
   * **Cơ chế residuals 2-Pass**: 
     * Pass 1: Tích lũy hiệp biến và giải hệ phương trình tìm $\beta$ bằng `np.linalg.solve`.
     * Pass 2: Duyệt lại các dòng của ngày để trừ đi phần dự phóng và ghi đè trực tiếp kết quả vào mảng `out`.

```python
@njit(cache=True, nogil=True, error_model='numpy')
def _numba_ols_neutralize_kernel(
    alpha,                 # Mảng tín hiệu 1D (N_ROWS)
    design_matrix,         # Ma trận thiết kế phẳng (N_ROWS, K)
    valid_mask,            # Mặt nạ thiết kế hợp lệ (N_ROWS)
    date_flat_indices,     # Chỉ số dòng phẳng đã phân nhóm ngày
    date_group_offsets,    # Vị trí ranh giới phân nhóm ngày
    out                    # Mảng ghi kết quả residuals (N_ROWS)
):
    out[:] = alpha[:]
    k_cols = design_matrix.shape[1]
    
    # Cấp phát cố định một lần trên Stack của Numba
    XtX = np.zeros((k_cols, k_cols), dtype=np.float64)
    Xty = np.zeros(k_cols, dtype=np.float64)
    
    for g in range(date_group_offsets.size - 1):
        start = date_group_offsets[g]
        stop = date_group_offsets[g + 1]
        n_date_rows = stop - start
        if n_date_rows < 2:
            continue
            
        # Reset các bộ tích lũy cố định
        for r in range(k_cols):
            Xty[r] = 0.0
            for c in range(k_cols):
                XtX[r, c] = 0.0
                
        # Pass 1: Tích lũy các phần tử hiệp biến trực tiếp (Không phân bổ X_sub/y_sub)
        n_valid = 0
        for i in range(start, stop):
            idx = date_flat_indices[i]
            val_y = alpha[idx]
            if valid_mask[idx] and np.isfinite(val_y):
                n_valid += 1
                for r in range(k_cols):
                    val_xr = design_matrix[idx, r]
                    Xty[r] += val_xr * val_y
                    for c in range(k_cols):
                        XtX[r, c] += val_xr * design_matrix[idx, c]
                        
        if n_valid < k_cols:
            continue
            
        # Áp dụng Tikhonov Regularization (Ridge) đảm bảo Rank-Safe
        for col in range(k_cols):
            XtX[col, col] += 1e-6
            
        # Giải hệ tuyến tính tìm beta
        beta = np.linalg.solve(XtX, Xty)
        
        # Pass 2: Tính toán residuals và ghi đè trực tiếp kết quả
        for i in range(start, stop):
            idx = date_flat_indices[i]
            val_y = alpha[idx]
            if valid_mask[idx] and np.isfinite(val_y):
                proj = 0.0
                for col in range(k_cols):
                    proj += design_matrix[idx, col] * beta[col]
                val_res = val_y - proj
                if np.abs(val_res) < 1e-12:
                    val_res = 0.0
                out[idx] = val_res
```

---

## 3. Bản đồ thay đổi đề xuất (Proposed Changes)

### [MODIFY] [scripts/genetic_alpha_evolution_v4.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)
* Tiền xây dựng ma trận thiết kế phẳng `design_matrix` (N_ROWS, K) và mảng hợp lệ `design_valid_mask` đưa vào `VMContext` tại hàm `_build_vm_context`.
* Triển khai kernel JIT OLS `_numba_ols_neutralize_kernel` và hàm batch `_numba_batch_ols_neutralize_kernel` tích hợp Ridge Regularization và giải thuật Zero-Allocation.
* Thay đổi hàm `_optimized_neutralize_cross_section` và `_optimized_batch_neutralize_cross_section` để chuyển hướng trực tiếp cuộc gọi sang kernel Numba JIT OLS đã tối ưu hóa.

### [MODIFY] [tests/test_gp_numba_jit_vm.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/tests/test_gp_numba_jit_vm.py)
* Bổ sung các bài kiểm thử độ chính xác (Parity Tests) xác thực kết quả JIT OLS trùng khớp hoàn toàn với giải thuật Ridge của scikit-learn (`alpha=1e-6`).
* Kiểm thử ranh giới cách ly ngày đối với JIT OLS.
* Kiểm thử các ca biên: Ma trận suy biến (Singular), Số dòng nhỏ (small-N), Dữ liệu toàn bộ NaN (All-NaN).

---

## 4. Kế hoạch Kiểm tra & Xác nhận (Verification Plan)

### Kiểm thử Tự động
* Chạy kiểm thử đơn vị: `pytest tests/test_gp_numba_jit_vm.py`.
* Chạy toàn bộ suite kiểm thử SoD: `pytest tests/quant_test_genetic_engine_optimizations.py tests/test_genetic_alpha_evolution_v4.py tests/test_gp_numba_jit_vm.py`.

### Đo đạc tốc độ (Benchmark)
* Thực thi lệnh benchmark ngoài Sandbox: `python scripts/benchmark_v4_advanced.py --population-size 100 --workers 10 --backend loky`
* Kết quả hiệu năng kỳ vọng: Thời gian chạy 5 thế hệ chéo các Folds dữ liệu hoàn tất trong **dưới 3 phút**.
