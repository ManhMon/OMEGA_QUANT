# PIT Exact Schedule Mapping for Free Macro Sources

Sử dụng lịch công bố thực tế để gán `published_at` chính xác cho các nguồn dữ liệu vĩ mô miễn phí (World Bank, Yahoo Finance, SBV), đảm bảo tuân thủ tuyệt đối quy tắc Point-in-Time (PIT) mà không tạo độ trễ (lag) giả lập làm ảnh hưởng tới mô hình.

## Proposed Changes

### `src/omega/data/macro_pipeline.py`
Cập nhật `MacroDataPipeline._records()` và `fetch()` để áp dụng lịch công bố (Release Schedule):

#### [MODIFY] [macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_pipeline.py)
- **World Bank (CPI, GDP, M2)**: Dữ liệu tháng/năm của GSO được công bố cố định vào **9:00 AM ngày 29 hàng tháng**.
  - Logic: Thay vì bỏ qua (vì data gốc của WB chỉ có năm/tháng), gán `published_at = observation_date + relativedelta(day=29, hours=9)`.
- **Yahoo Finance (USD/VND)**: Thị trường đóng cửa hàng ngày. 
  - Logic: Gán `published_at = observation_date` lúc 15:15 (T+0).
- **SBV (Lãi suất LNH)**: Cập nhật vào buổi chiều T+1. 
  - Logic: Gán `published_at = observation_date + 1 day` lúc 16:00.

### `tests/test_macro_pipeline.py`
#### [MODIFY] [test_macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_pipeline.py)
- Sửa lại các test case vốn mong đợi `RuntimeError("no records from any provider")` thành các test case kiểm tra việc ánh xạ ngày giờ chính xác cho từng loại nguồn.

## Verification Plan
### Automated Tests
- Chạy `pytest tests/test_macro_pipeline.py` để kiểm tra logic tính toán `published_at`.

### L3 Audit
- Dispatch OpenCode L2 thực hiện.
- Dispatch Codex L3 để kiểm định (audit) mã nguồn và đảm bảo không có lỗ hổng rò rỉ dữ liệu tương lai (look-ahead bias).
- Vượt qua `sod_gate_enforcer.py` để đóng gate thành công.
