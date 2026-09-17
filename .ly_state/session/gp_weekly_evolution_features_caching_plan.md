# GP Weekly Evolution Features Caching Plan

## Goal Description

Giải quyết lỗi OOM phát sinh khi chạy GP evolution trên Windows.
- Joblib thread pool (`prefer="threads"`) lưu giữ các đối số của task (`features` dict) trong ngữ cảnh thực thi thread.
- Nếu `fold_features` (chứa các mảng sao chép lớn của 5 folds) được đính kèm vào `features`, nó sẽ bị Joblib thread giữ lại vĩnh viễn, gây rò rỉ 1.25 GB bộ nhớ mỗi generation và dẫn đến crash OOM ở Gen 3.

## Codex L3 Review Resolved

- **Keyed Global Cache**: Định nghĩa biến toàn cục `_GLOBAL_FOLD_FEATURES_CACHE` dạng dictionary. Sử dụng key `(id(date_arr), fold_count)` để liên kết chính xác các tập fold features tương ứng với mảng ngày tháng và số lượng fold hiện tại, loại bỏ sự phụ thuộc vào so sánh `gen_features is features`.
- **Tránh rò rỉ cache**: Đảm bảo cache được `.clear()` trong khối `finally` của hàm `evolve()`.

## Proposed Changes

### scripts/genetic_alpha_evolution_v4.py

#### [MODIFY] [genetic_alpha_evolution_v4.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)

1. **Định nghĩa biến toàn cục `_GLOBAL_FOLD_FEATURES_CACHE`**:
   - Thêm biến toàn cục `_GLOBAL_FOLD_FEATURES_CACHE = {}` ở mức module.
2. **Ẩn cache khỏi đối số của Joblib**:
   - Trong `_prepare_generation_features`: Thay vì gắn `fold_features` vào `gen_features[FOLD_FEATURES_CACHE_KEY]`, ta lưu trữ nó vào `_GLOBAL_FOLD_FEATURES_CACHE` bằng key `(id(date_arr), fold_count)`.
   - Xóa bỏ việc đính kèm `FOLD_FEATURES_CACHE_KEY` vào `gen_features` để Joblib không nhìn thấy và không lưu giữ tham chiếu này.
3. **Đọc cache trực tiếp từ biến toàn cục**:
   - Trong `_batch_fold_ir_scores` (dòng 1210) và `_compute_time_fold_ir_v4` (dòng 1477): Đọc `fold_views` từ `_GLOBAL_FOLD_FEATURES_CACHE.get((id(date_arr), fold_count))`. Nếu None (ví dụ khi test đơn lẻ), fall back tự rebuild để bảo toàn tính tương thích.
4. **Giải phóng triệt để bộ nhớ trong `finally`**:
   - Ở cuối hàm `evolve()`, trong khối `finally`, gọi `_GLOBAL_FOLD_FEATURES_CACHE.clear()` và `gc.collect()`.

## Verification Plan

### Automated Tests
- Chạy biên dịch trực tiếp file thay đổi: `python -m py_compile scripts/genetic_alpha_evolution_v4.py`.
- Chạy `pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q` để đảm bảo logic tiến hóa GP không bị sai lệch.
- Chạy lại GP evolution thực tế để xác nhận tiến trình vượt qua Gen 30 thành công không bị OOM.
