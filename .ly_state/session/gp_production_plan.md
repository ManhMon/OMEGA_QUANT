# Kế hoạch Triển khai GP Production Run & Tối ưu hóa Sửa lỗi Hệ thống

Kế hoạch này khắc phục các lỗi logic của script GP và tích hợp, thực hiện chạy thực tế (Production Run) với cấu hình workflow hiện hành (3 rounds, 50 generations, 2 workers), và chạy kiểm định backtest trên toàn bộ tập dữ liệu lịch sử.

## User Review Required

> [!IMPORTANT]
> - **Sửa đổi mã nguồn**: Việc sửa đổi logic sắp xếp, thứ tự validate, cảnh báo p-value, và xử lý crash ngày giao dịch trong [genetic_alpha_evolution_v3.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v3.py) sẽ được giao cho OpenCode (L2, Role 16) sửa đổi và kiểm thử trước.
> - **Thời gian chạy Production**: Chạy 3 rounds x 50 generations với tập dữ liệu đầy đủ theo workflow hiện hành vẫn là tác vụ nặng và cần theo dõi log trong môi trường Windows local.

## Open Questions

Không có câu hỏi mở.

## Proposed Changes

### 1. Thành phần logic GP Evolution & Registry (L2 OpenCode)

#### [MODIFY] [genetic_alpha_evolution_v3.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v3.py)
- **Vá lỗi sắp xếp (Sorting Bug)**: Đổi sort trong `export_gp_views` thành sort 2 tầng ổn định để giữ rank tăng dần nhưng version mới nhất đứng đầu:
  ```python
  rows.sort(key=lambda row: str(row["version"]), reverse=True)
  rows.sort(key=lambda row: int(row["rank"]))
  ```
  *Lưu ý*: Sử dụng giả định chronological sorting dựa trên định dạng version của timestamp `%Y%m%dT%H%M%S_rNN`.
- **Thứ tự đăng ký & Gate 6 checks (Refactor để test độc lập)**: Tách logic kiểm định Gate 6 và đăng ký thành một hàm riêng biệt (ví dụ: `validate_and_register_models`). Thực hiện chạy `run_gate6_validation` và kiểm tra lỗi trước khi thực hiện `register_top_models` để tránh ghi nhận rác vào database nếu Gate 6 thất bại.
- **Biến đổi p-value**: Đổi cảnh báo `p_value > 0.05` thành raise ValueError để từ chối các mô hình không có ý nghĩa thống kê.
- **Tránh crash `dates.index`**: Thay thế các lệnh lookup `dates.index(...)` tại `build_split_windows` bằng `np.searchsorted(dates, split_date)` để xử lý an toàn các ngày nghỉ/ngày thiếu trong dữ liệu. Thực hiện guard biên để tránh lỗi tràn/thiếu index.
- **Sắp xếp theo độ chính xác cao**: Sắp xếp `all_hof` dựa trên giá trị `val_IC_daily` chưa làm tròn kèm theo tie-breaker (như `id`) để đảm bảo tính tất định (reproducibility).

### 2. Triển khai Production Run

- **Lệnh thực thi**:
  ```powershell
  $env:PYTHONPATH = "C:\Users\GHC\repos\OMEGA_QUANT\src"
  python scripts/genetic_alpha_evolution_v3.py --rounds 3 --population-size 150 --generations 50 --workers 2 --backend threads
  ```

### 3. Tích hợp và Backtest

- **Quy trình chạy**:
  1. **Bước 1**: Chạy tiền tính toán đặc trưng GP từ registry để ghi nhận các cột `alpha_gp_00`, `alpha_gp_01`, `alpha_gp_02` vào tệp parquet:
     ```powershell
     python scripts/precompute_all_features.py
     ```
  2. **Kiểm tra chốt chặn**: Thực thi kiểm tra schema của parquet đảm bảo cột `alpha_gp_00` tồn tại và không rỗng trước khi chạy backtest:
     ```powershell
     python -c "import pandas as pd; df=pd.read_parquet('data/precomputed_alpha_features.parquet'); assert 'alpha_gp_00' in df.columns, 'Missing GP feature'; assert df['alpha_gp_00'].notna().sum() > 0, 'GP feature is empty'"
     ```
  3. **Bước 2**: Chạy backtest so sánh và chọn lọc đặc trưng với conformal overlay được huấn luyện on-the-fly cho từng fold (không load trực tiếp JSON từ registry làm conformal predictor):
     ```powershell
     python scripts/backtest_hybrid_regime.py --workers 4 --alpha-group hybrid_regime --enable-conformal
     ```

---

## Verification Plan

### Automated Tests
- Chạy toàn bộ test suite hiện tại:
  ```powershell
  pytest tests/test_genetic_alpha_evolution_v3.py tests/test_genetic_alpha_evolution_v3_gate6.py tests/test_genetic_engine_liquidity.py
  ```
- **Viết thêm test hồi quy (Regression/Unit Tests)** trong `tests/test_genetic_alpha_evolution_v3_gate6.py`:
  - `test_stable_sorting`: Kiểm định thứ tự sort 2 tầng ổn định của `export_gp_views` (giữ rank tăng dần, version mới nhất đứng đầu).
  - `test_searchsorted_split_handling`: Kiểm định `searchsorted` tránh crash khi ngày phân hoạch bị thiếu trong chuỗi dữ liệu thực tế và kiểm tra guard biên.
  - `test_no_register_on_gate_fail`: Xác nhận logic đăng ký (sau khi refactor) không được gọi/ghi nhận dữ liệu vào registry khi Gate 6 validation thất bại.
  - `test_p_value_hard_fail`: Kiểm định raise ValueError khi hoán vị p-value > 0.05 và xác nhận không có ghi nhận vào database.
  - `test_unrounded_val_ic_sorting`: Xác nhận việc sort và chọn `all_hof` sử dụng độ chính xác thực tế thay vì làm tròn 4 chữ số.

### Manual Verification
- Xác nhận các mô hình mới được đăng ký thành công vào `conformal_registry.sqlite`.

---

## Lưu ý bổ sung từ Claude Code Review (V4)
- **Artifact Export Prevention**: Việc chặn ghi khi Gate 6 thất bại phải áp dụng cho cả việc ghi nhận database và xuất các tệp artifacts (như `best.json`).
- **Stable Sort Test Case**: Test `test_stable_sorting` cần phủ thêm trường hợp timestamp trùng lặp nhưng khác định danh hậu tố để đảm bảo tính tất định.
- **Log GP Run**: Ghi log chi tiết trong suốt quá trình chạy 2-4 tiếng của GP để tránh mất dữ liệu khi bị gián đoạn.
- **Cấu hình**: Chế độ chạy paper run an toàn (`broker: mock`, `dry_run: true`) được giữ nguyên trong `production.yaml`.
