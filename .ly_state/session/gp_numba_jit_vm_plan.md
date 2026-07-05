# Kế hoạch chi tiết Triển khai GP Numba JIT-Compiled Stack-Based VM (Bản sửa đổi 3)

## 1. Mục tiêu & Chỉ số chấp nhận (Acceptance Criteria)
Thay thế bộ dịch cây GP viết bằng Python đệ quy thô (`GPIndividualV4._execute_tree`) bằng một **Máy ảo Stack biên dịch JIT bằng Numba (`_numba_execute_rpn`)** nhằm giải phóng hoàn toàn khóa GIL của Python.
* **Mốc hiệu năng Baseline gốc**: **5060 giây (~84.3 phút)** cho 5 thế hệ (100 population, 3 Folds).
* **Mục tiêu tốc độ sau tối ưu**: **Dưới 4 phút** cho toàn bộ 5 thế hệ (tăng tốc độ thực tế **$\ge 20\text{x}$ lần**).
* **Giới hạn bộ nhớ**: Bộ nhớ RAM đỉnh điểm (Peak RSS) của toàn bộ tiến trình không vượt quá **4 GB**.

---

## 2. Thiết kế Kiến trúc Mã lệnh & Máy ảo (RPN Stack VM)

### A. Cấu trúc Bytecode & Operand
Mỗi cây biểu thức `GPNode` được biên dịch thành một cặp mảng NumPy 1D phẳng có độ dài bằng nhau:
1. `opcodes` (int32): Chứa mã lệnh chỉ thị tác vụ.
2. `operands` (int32): Chứa các tham số đi kèm (ví dụ: kích thước cửa sổ của toán tử rolling, hoặc chỉ số cột đặc trưng).

#### Định nghĩa Opcodes (Opcodes Registry):
* **Toán tử cơ bản (Arity 2)**:
  * `+`: 1, `-`: 2, `*`: 3, `/`: 4, `max`: 18, `min`: 19. (Operand = 0)
* **Toán tử một ngôi (Arity 1)**:
  * `abs`: 5, `log`: 6, `sqrt`: 7, `exp`: 8, `sigmoid`: 9, `neg`: 13. (Operand = 0)
* **Toán tử chuỗi thời gian (Arity 1 + Parameter)**:
  * `ts_std`: 14, `ts_mean`: 15, `ts_rank`: 16, `decay_linear`: 17. (Operand = `window_size` tính theo bar ngày)
* **Toán tử cắt ngang Cross-Sectional (Arity 1)**:
  * `cs_rank`: 11, `cs_zscore`: 12. (Operand = 0)
* **Nạp đặc trưng (Variables)**:
  * `OP_VAR`: 100. (Operand = `feature_col_index` - chỉ số cột trong ma trận dữ liệu)
* **Nạp hằng số (Constants)**:
  * `OP_CONST`: 50. (Operand = `const_index` - chỉ số của hằng số trong mảng thực `const_values`)

### B. Thiết kế Quản lý Bộ nhớ Stack (An toàn RAM <= 4GB)
Để tránh cấp phát động quá mức gây tràn RAM trên tập dữ liệu 1.25 triệu dòng:
* **Mảng Stack 2D cố định**: Mỗi luồng thực thi cấp phát một mảng Stack 2D phẳng duy nhất có kích thước `(MAX_STACK_DEPTH, N_ROWS)` kiểu `float64`, với `MAX_STACK_DEPTH = 12` (vượt xa giới hạn chiều sâu cây GP hiện tại là 6–8).
* **Dung lượng Stack dự phòng**: `12 * 1.254.349 * 8 bytes ≈ 120 MB` mỗi luồng, hoàn toàn nằm trong giới hạn an toàn RAM.
* **Stack Pointer (`sp`)**: Một số nguyên chỉ số chạy từ `-1` tăng dần để theo dõi đỉnh của stack.

### C. Thiết kế Phân nhóm & Trật tự Dòng (Đảm bảo PIT Safety & Cross-Sectional Correctness)
Để hỗ trợ cả các toán tử chuỗi thời gian (rolling TS) và toán tử cắt ngang theo ngày (daily CS) một cách chính xác mà không gây rò rỉ hoặc overhead sắp xếp lại mảng:
1. **Canonical Row-Ordering**: Dữ liệu đầu vào `feature_matrix` và các mảng trong stack được sắp xếp nhất quán theo trật tự **`(Ticker, Date)`** làm mặc định.
2. **Ticker rolling boundaries (Time-Series)**:
   * Vì dữ liệu sắp xếp theo `(Ticker, Date)`, dữ liệu lịch sử của từng ticker là **liên tục**.
   * Ta cung cấp mảng `ticker_group_offsets` (int32, kích thước `N_TICKERS + 1`) chứa các chỉ số dòng bắt đầu/kết thúc của từng cổ phiếu trong `feature_matrix`.
   * Các kernel rolling của Numba (`_numba_rolling_mean`, v.v.) sẽ lặp qua các ranh giới này để tính toán chuỗi thời gian độc lập cho từng cổ phiếu, loại bỏ rò rỉ chéo mã.
3. **Daily CS boundaries (Cross-Sectional)**:
   * Vì dữ liệu được sắp xếp theo `(Ticker, Date)`, các dòng thuộc cùng một ngày giao dịch sẽ **không liên tục** (bị phân tán chéo qua các ticker).
   * Ta biên dịch bản đồ ngày thành một cấu trúc phân nhóm: `date_group_row_indices` (dạng List của các mảng số nguyên 1D, hoặc một mảng 2D chỉ số dòng nếu kích thước vũ trụ cổ phiếu cố định). Ở đây để hỗ trợ an toàn cho số lượng cổ phiếu biến động, ta dùng cấu trúc mảng chỉ số dòng phẳng được nén kèm theo `date_group_offsets` đánh dấu điểm bắt đầu/kết thúc của từng ngày trong mảng chỉ số phẳng.
   * Các toán tử `cs_rank` và `cs_zscore` sẽ nhận mảng chỉ số dòng của từng ngày từ mảng phẳng này, thực hiện xếp hạng/z-score gián tiếp qua chỉ số (`indirect indexing`) trên mảng stack, sau đó ghi ngược kết quả về đúng các dòng đó.
   * Cấu trúc này giúp tránh được việc transpose mảng dữ liệu khổng lồ 1.25M dòng mà vẫn bảo đảm các toán tử CS chạy hoàn toàn cách ly theo từng ngày.

---

## 3. Bản đồ thay đổi đề xuất (Proposed Changes)

### [MODIFY] [scripts/genetic_alpha_evolution_v4.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)
* Triển khai hàm Python dịch cây `_compile_tree_to_rpn(node, feature_names)` trả về `(opcodes, operands, const_values)`.
* Xây dựng máy ảo JIT:
  ```python
  @njit(cache=True, nogil=True, error_model='numpy')
  def _numba_execute_rpn(
      opcodes, 
      operands, 
      const_values, 
      feature_matrix, 
      ticker_group_offsets, 
      date_flat_indices,
      date_group_offsets, 
      stack
  ):
      # Thực thi tuyến tính qua vòng lặp opcodes
  ```
* Bổ sung các kernel tính toán JIT có phân nhóm:
  * `_numba_rolling_mean(x, window, ticker_group_offsets)`
  * `_numba_rolling_std(x, window, ticker_group_offsets)`
  * `_numba_rolling_rank(x, window, ticker_group_offsets)`
  * `_numba_rolling_decay(x, window, ticker_group_offsets)`
  * `_numba_cs_rank(x, date_flat_indices, date_group_offsets)`
  * `_numba_cs_zscore(x, date_flat_indices, date_group_offsets)`
* Thay đổi hàm `GPIndividualV4._execute_tree` để tự động hóa việc gọi JIT VM thay vì chạy đệ quy Python.

### [NEW] [tests/test_gp_numba_jit_vm.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/tests/test_gp_numba_jit_vm.py)
* Kiểm thử độ chính xác số học (Numerical Parity) giữa mã đệ quy Python cũ và JIT VM mới.
* Kiểm thử hành vi xử lý biên (NaN, Inf, chuỗi dữ liệu quá ngắn so với kích thước cửa sổ rolling).
* Kiểm thử ranh giới: Chứng minh `cs_rank` và `cs_zscore` không tính chéo hoặc rò rỉ dữ liệu qua các ngày giao dịch khác nhau.
* Kiểm thử rolling: Chứng minh các toán tử rolling TS không tính lan qua các ticker khác nhau.

---

## 4. Kế hoạch Kiểm tra & Xác nhận (Verification Plan)

### Kiểm thử Tự động
* Chạy pytest chốt chặn: `pytest tests/test_gp_numba_jit_vm.py`.
* Chạy toàn bộ suite kiểm thử SoD: `pytest tests/quant_test_genetic_engine_optimizations.py tests/test_genetic_alpha_evolution_v4.py tests/test_gp_numba_jit_vm.py`.

### Thử nghiệm Hiệu năng Ngoài Sandbox
* Thực thi lệnh benchmark ngoài Sandbox: `python scripts/benchmark_v4_advanced.py --population-size 100 --workers 10 --backend loky`
* Kết quả kỳ vọng: Tốc độ hoàn thành 5 thế hệ chéo các Folds dữ liệu chính thức giảm xuống **dưới 4 phút**; bộ bộ nhớ RAM đạt chuẩn **$\le 4$ GB**.
