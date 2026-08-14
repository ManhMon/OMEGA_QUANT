# GP VN Alphas Drop Optimization Plan

## Goal Description

Giải quyết lỗi `ArrayMemoryError` phát sinh khi chạy `run_weekly_evolution.py`. Lỗi xảy ra tại `src/omega/quant/alpha/vn.py` dòng 274 khi gọi `res.drop(columns=["ticker", "date"], inplace=True)`. Thao tác `drop` này của Pandas buộc phải reindex và copy lại toàn bộ các cột đặc trưng để tái thiết kế Block Manager, tạo ra bản sao dung lượng lớn gây quá tải RAM.

## Codex L3 Review Resolved

- Không sử dụng phép trích xuất ma trận 2D rộng `res[cols_to_clean].values`.
- Gán trực tiếp từng mảng 1D dạng view: `final_dict[col] = res[col].to_numpy(copy=False)` để loại bỏ hoàn toàn chi phí phân bổ mảng 2D trung gian.

## Proposed Changes

### src/omega/quant/alpha/vn.py

#### [MODIFY] [vn.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/alpha/vn.py)

- Trong `compute_all_vn_alphas()` (dòng 274-277):
  - Xóa dòng:
    ```python
    res.drop(columns=["ticker", "date"], inplace=True)
    res_vals = res.values
    for i, col in enumerate(cols_to_clean):
        final_dict[col] = res_vals[:, i]
    ```
  - Thay thế bằng:
    ```python
    for col in cols_to_clean:
        final_dict[col] = res[col].to_numpy(copy=False)
    ```

## Verification Plan

### Automated Tests
- Chạy biên dịch trực tiếp file thay đổi: `python -m py_compile src/omega/quant/alpha/vn.py`.
- Chạy `pytest tests/test_vn_features_targeted.py -q` để đảm bảo logic tính toán đặc trưng VN không bị ảnh hưởng.
