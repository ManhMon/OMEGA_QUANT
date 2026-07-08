# Kế hoạch Chi tiết Tối ưu hóa Gram-Sharing JIT OLS (`GP_NUMBA_OLS_OPTIMIZATION`)

## 1. Mục tiêu & Chỉ số chấp nhận (Acceptance Criteria)
Khắc phục triệt để điểm nghẽn tính toán lặp ma trận Gram ($X^T X$) trong nhân hồi quy lô JIT OLS `_numba_batch_ridge_neutralize`:
1. **Chia sẻ ma trận Gram chéo ứng viên (Gram-Sharing)**: Tính toán ma trận Gram $X^T X$ một lần duy nhất cho mỗi nhóm ngày (date group) và dùng chung cho tất cả 100 ứng viên (candidates), thay vì tính lại 100 lần.
2. **Đảm bảo Parity số học tuyệt đối**: Bảo toàn chính xác kết quả số học của hồi quy Ridge ($\lambda = 10^{-6}$), bao gồm cả cơ chế xử lý biên khi ứng viên chứa NaNs (sử dụng phân nhánh fallback khi số lượng dòng hợp lệ khác nhau).
3. **Mục tiêu hiệu năng**:
   * Tốc độ chạy 5 thế hệ (100 population) trên toàn vũ trụ 700 mã (~1.25M dòng) hoàn tất trong **dưới 3 phút** (thay vì nghẽn hàng chục phút như hiện tại).

---

## 2. Thiết kế Kỹ thuật Gram-Sharing JIT OLS

### A. Thuật toán tối ưu trong nhân `_numba_batch_ridge_neutralize`
Chúng ta sẽ sửa đổi cấu trúc vòng lặp trong hàm JIT như sau:
1. Duyệt qua từng ngày (`group_idx` từ 0 đến `date_group_offsets.size - 1`).
2. **Dựng Gram cơ sở**:
   * Dựng mảng chỉ mục dòng hợp lệ cho ngày (`valid_mask` của thiết kế là True).
   * Tính toán ma trận Gram nền tảng `base_gram` ($K \times K$) từ các dòng hợp lệ này và cộng thêm Ridge penalty `ridge_alpha` vào đường chéo.
   * Đếm tổng số dòng hợp lệ chuẩn của ngày `base_valid_count`.
3. **Duyệt chéo ứng viên**:
   * Với từng ứng viên `candidate_idx`:
     * Đếm số dòng hợp lệ thực tế `valid_count` (chỉ lọc bỏ các dòng có giá trị `y_val` là NaN/Inf).
     * **Phân nhánh tối ưu (Fast Path)**: Nếu `valid_count == base_valid_count` (không có NaN trong tín hiệu ứng viên - chiếm >99.9% trường hợp):
       * Sao chép ma trận `base_gram` sang `gram_solve` để làm đầu vào cho solver (tránh solver ghi đè ma trận gốc).
       * Dựng RHS vector $X^T y$ từ tín hiệu ứng viên.
       * Giải hệ phương trình bằng `np.linalg.solve(gram_solve, rhs)`.
     * **Phân nhánh fallback (Slow Path)**: Nếu `valid_count < base_valid_count` (ứng viên chứa NaNs):
       * Dựng lại ma trận Gram riêng cho ứng viên từ các dòng hợp lệ thực tế.
       * Dựng RHS và giải hệ phương trình OLS Ridge bình thường (đảm bảo parity toán học tuyệt đối).

---

## 3. Danh sách File thay đổi dự kiến

### GP Engine
#### [MODIFY] [genetic_alpha_evolution_v4.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)
* Cập nhật hàm `_numba_batch_ridge_neutralize` triển khai cơ chế tính trước `base_gram` một lần chéo ngày và phân nhánh Fast Path / Slow Path.
* Tối ưu hóa bộ nhớ đệm: bổ sung `base_gram` và `gram_solve` vào các biến cấp phát một lần trước vòng lặp (zero-allocation).

---

## 4. Kế hoạch Kiểm tra & Xác thực (Verification Plan)

### Kiểm thử tự động
1. Chạy suite unit tests hiện tại để chứng thực tính đúng đắn toán học:
   ```powershell
   pytest tests/test_gp_numba_jit_vm.py tests/quant_test_genetic_engine_optimizations.py
   ```
   *Yêu cầu*: 100% tests phải PASS. Kết quả hồi quy sau tối ưu phải trùng khớp tuyệt đối với Ridge OLS của scikit-learn.

### Đo đạc hiệu năng
1. Thực thi benchmark đầy đủ 5 thế hệ chéo 700 mã:
   ```powershell
   python scripts/benchmark_v4_advanced.py --population-size 100 --workers 10 --backend threads
   ```
   *Yêu cầu*: Hoàn thành toàn bộ tiến trình trong dưới 3 phút.
