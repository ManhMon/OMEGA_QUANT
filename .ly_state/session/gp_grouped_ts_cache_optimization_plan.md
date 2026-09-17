# Kế hoạch triển khai - Tối ưu hóa hiệu năng toán tử cuộn thời gian (Grouped TS Caching)

Kế hoạch này tối ưu hóa hiệu năng của động cơ tiến hóa GP bằng cách cache lại kết quả sắp xếp (`order`) và chỉ mục phân nhóm (`starts`, `stops`) của chuỗi thời gian theo mã cổ phiếu (`tickers`) và ngày (`dates`). Điều này giúp loại bỏ hoàn toàn việc gọi lặp lại các hàm đắt đỏ như `pd.to_datetime`, `np.lexsort` và `np.unique` trên 647k dòng dữ liệu cho mỗi toán tử cuộn thời gian chéo 400,000 lượt đánh giá.

## User Review Required

> [!IMPORTANT]
> - **Cơ chế Caching cục bộ theo Worker và Quản lý Vòng đời (Collision-Safe Caching)**:
>   - **Tránh trùng lặp ID (ID-Reuse Prevention)**: Bộ nhớ cache `_GROUPED_TS_CACHE` lưu giữ tham chiếu cứng đến `tickers` và `dates` trong value tuple: `(order, starts, stops, tickers_ref, dates_ref)`. Việc giữ lại tham chiếu này ngăn chặn Python giải phóng đối tượng và tái sử dụng `id()` của chúng cho các mảng mới khác trong vòng đời tiến trình.
>   - **Hợp đồng Bất biến dữ liệu & Kiểm tra Đột biến biên (Immutability & Mutation Detection)**: 
>     - Chúng tôi chính thức đặc tả mảng `tickers` và `dates` là **read-only/bất biến** (immutable) trong suốt vòng đời của một lượt chạy tiến hóa GP.
>     - Để phòng vệ trước các thay đổi vô ý, khóa cache kiểm tra O(1) boundaries:
>       ```python
>       cache_key = (
>           id(tickers), len(tickers), tickers[0] if len(tickers) > 0 else None, tickers[-1] if len(tickers) > 0 else None,
>           id(dates) if dates is not None else None,
>           len(dates) if dates is not None else 0,
>           dates[0] if dates is not None and len(dates) > 0 else None,
>           dates[-1] if dates is not None and len(dates) > 0 else None
>       )
>       ```
>       Cơ chế này sẽ nhận diện nhanh các đột biến tại chỗ ở biên hoặc thay đổi kích thước mảng.
>   - **Vòng đời Cache và Dọn dẹp Deterministic**:
>     1. **GeneticEngine.evolve()**: Gọi `clear_grouped_ts_cache()` trước khi chạy và trong khối `finally` khi kết thúc evolve.
>     2. **Island/Evaluation Task (Loky Worker)**: Tại hàm chạy trên worker `_evaluate_genome_job()`, bao bọc toàn bộ logic trong `try/finally` và gọi `ge.clear_grouped_ts_cache()` ở `finally` để giải phóng bộ nhớ của worker ngay khi kết thúc tác vụ đánh giá genome đó.
>     3. **Island Boundary**: Tại `_evolve_island_job()`, bao bọc trong `try/finally` và gọi `ge.clear_grouped_ts_cache()` ở `finally`.
>     4. **Loky Worker Lifecycle**: Khai báo `initializer=ge.clear_grouped_ts_cache` khi khởi tạo `Parallel` pool tại `_evaluate_population()` trong `diverse_alpha_evolution.py:450`.

---

## Proposed Changes

### Component 1: Tối ưu hóa VM thực thi Alpha

#### [MODIFY] [genetic_engine.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py)
- Khai báo từ điển `_GROUPED_TS_CACHE: Dict[Tuple, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]` để giữ các tham chiếu và tránh ID-reuse.
- Triển khai hàm `_apply_grouped_ts_transform` kiểm tra khóa an toàn chứa biên phần tử và mảng rỗng.
- Định nghĩa hàm `clear_grouped_ts_cache()` thực hiện `_GROUPED_TS_CACHE.clear()`.
- Chèn khối `try/finally` để gọi `clear_grouped_ts_cache()` trong hàm `evolve()`.

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)
- Sửa đổi hàm `_evaluate_genome_job()` trên worker: Sử dụng khối `try/finally` để gọi `ge.clear_grouped_ts_cache()` ở `finally`.
- Sửa đổi hàm `_evolve_island_job()`: Sử dụng khối `try/finally` để gọi `ge.clear_grouped_ts_cache()` ở `finally`.
- Khai báo `initializer=ge.clear_grouped_ts_cache` tại lệnh gọi `Parallel` trong `_evaluate_population()`.

---

## Verification Plan

### Automated Tests
- Bổ sung các test case kiểm thử cụ thể trong `tests/test_diverse_alpha_evolution_parallel.py` (hoặc tệp test chuyên biệt):
  1. **Test repeated-hit parity**: Chạy thử nhiều toán tử cuộn kế tiếp, kiểm tra tính đồng nhất của kết quả.
  2. **Test train/validation separation**: Đảm bảo cache phân biệt chính xác hai tập dữ liệu (có địa chỉ bộ nhớ khác nhau).
  3. **Test dates=None**: Đảm bảo xử lý an toàn khi không có mảng ngày tháng.
  4. **Test in-place mutation**: Sửa đổi phần tử của mảng đầu vào (giữ nguyên độ dài) và kiểm tra xem cache có tự động nhận dạng qua biên phần tử và cập nhật lại không.
  5. **Test ID-reuse prevention**: Giả lập việc giải phóng và tái sử dụng `id()` để chứng minh tham chiếu cứng giữ cho ID không bị trùng lặp đột biến.
  6. **Test Loky worker cleanup validation**: Chạy song song và kiểm tra xem cache của các tiến trình con (workers) có thực sự trống rỗng sau khi các tác vụ đánh giá genome hoàn thành (kiểm tra gián tiếp thông qua việc rò rỉ bộ nhớ hoặc gọi hàm kiểm tra trạng thái cache trên worker).

### Manual Verification & Benchmarks
- Chạy thử 5 thế hệ với quy mô đầy đủ để đo đạc thời gian thực thi:
  - **Mục tiêu hiệu năng**: Thời gian xử lý thế hệ giảm từ **~40s/thế hệ** xuống còn **< 2s/thế hệ**.
  - Kiểm tra parities của Spearman IC và IR đảm bảo không có look-ahead bias và sai lệch kết quả.

---

## Repo-Local Skill Source Evidence

- **L2 Role Spec**: `backend-engineer.md`
- **L2 Declared Skills**:
  - `nodejs-best-practices`
  - `api-patterns`
  - `database-design`
  - `clean-code`
  - `testing-patterns`
  - `systematic-debugging`
- **Forbidden Path Scan**: No authoritative reliance.
