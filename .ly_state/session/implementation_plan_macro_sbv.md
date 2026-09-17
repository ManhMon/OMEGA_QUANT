# Kế hoạch Mở rộng và Sửa lỗi Pipeline Dữ liệu Vĩ mô (Macro Data Pipeline)

Cập nhật lại pipeline dữ liệu vĩ mô nhằm khắc phục các lỗi API 404 từ SBV (Ngân hàng Nhà nước), bổ sung các chỉ số kinh tế vĩ mô quan trọng (CPI, GDP, M2), đồng thời vá các lỗ hổng rò rỉ PIT (Point-in-Time) nghiêm trọng vừa được phát hiện. Đảm bảo toàn vẹn dữ liệu (data integrity) và xử lý xung đột ghi disk.

## Đề xuất Thay đổi

### 1. Existing-store integrity (P0)
- **Lock Scope & Lifetime**: Sử dụng `filelock.FileLock` bao quanh toàn bộ chu trình: đọc store hiện tại -> xác thực schema/dtype/invariants -> merge dữ liệu mới -> ghi ra file tạm (`.tmp`) trong cùng thư mục -> validate file tạm -> `os.replace` nguyên tử sang destination path. Nếu xảy ra lỗi ở bất kỳ bước nào, destination path giữ nguyên hash và file tạm được xóa bỏ (destination-preservation).
- **Store Validation Invariants**:
  - `SCHEMA` đầy đủ: `["indicator", "value", "observation_date", "published_at", "available_at", "ingested_at", "revision_id", "source"]`.
  - Kiểu dữ liệu: `value` bắt buộc là `float` hữu hạn (`math.isfinite()`), không chấp nhận `NaN`, `±inf`.
  - PIT ordering invariant: `observation_date <= published_at < available_at` cho từng bản ghi.
  - `revision_id` không được null, là chuỗi hex SHA-256 duy nhất cho mỗi sự kiện công bố.
  - Kiểm tra conflict bất biến: Nếu hai bản ghi có cùng `revision_id`, toàn bộ các trường nội dung (`indicator`, `value`, `observation_date`, `published_at`, `source`) phải khớp nhau 100%. Nếu cùng ID khác nội dung -> ném lỗi `ValueError` (fail-closed).

### 2. SBV parser contract & Date semantics (P0 & P1)
- **Cào HTML SBV**: Sử dụng `BeautifulSoup` cào từ `https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/tk/lsttlnh`.
- **Parser Contract**:
  - Kiểm tra `response.status_code == 200` và header `Content-Type` chứa `text/html`.
  - Tìm chính xác selector bảng lãi suất: `table.tbl-rate` hoặc `table` có header chứa các nhãn: `["Kỳ hạn", "Lãi suất (%/năm)", "Doanh số"]`.
  - Chuẩn hóa locale tiếng Việt: Xử lý dấu phẩy thập phân (e.g. `4,50%` -> `4.5`), loại bỏ ký tự khoảng trắng thừa.
  - Fail-closed: Nếu không tìm thấy bảng, số dòng hợp lệ = 0, hoặc có dòng chứa giá trị không hợp lệ -> Ném ngoại lệ `RuntimeError("Zero valid rows in SBV HTML payload")`. Không âm thầm bỏ qua.
- **SBV Date Semantics per Series**:
  | Series | Provenance Label | `observation_date` | `published_at` | Timezone | Missing Date Policy |
  |---|---|---|---|---|---|
  | `interbank_rate` | Ngày giao dịch liên ngân hàng | Parse từ tiêu đề/cột ngày báo cáo của SBV (ví dụ: `Ngày 08/08/2026`) | Gán bằng `ingested_at` tại thời điểm cào được bản tin (vì SBV không công bố giờ phát hành) | `Asia/Ho_Chi_Minh` | Reject dòng nếu thiếu ngày quan sát. Cấm suy diễn `published_at = observation_date`. |
  | `sbv_rate` | Quyết định điều hành lãi suất | Ngày hiệu lực quyết định của SBV | Gán bằng ngày công bố quyết định hoặc `ingested_at` | `Asia/Ho_Chi_Minh` | Reject nếu không có ngày hiệu lực. |

### 3. Deterministic Vintage Selection (P1)
- Trong `MacroDataPipeline.query_as_of(parquet_path, as_of_date)`:
  1. Chuẩn hóa `as_of_date` về timezone `Asia/Ho_Chi_Minh`.
  2. Đọc và xác thực store Parquet theo các invariant ở mục 1.
  3. Lọc các bản ghi hợp lệ theo điều kiện Point-in-Time: `available_at <= as_of_date` VÀ `ingested_at <= as_of_date`.
  4. Sắp xếp giảm dần theo: `published_at DESC`, `ingested_at DESC`, `revision_id DESC`.
  5. Nhóm theo `["indicator", "observation_date"]` và lấy dòng đầu tiên (`.first()`) để đảm bảo trả về duy nhất **một latest vintage** cho mỗi observation date.
  6. Sắp xếp kết quả cuối cùng theo `["indicator", "observation_date"]` tăng dần trước khi trả về.

### 4. Sửa Lỗi Nghiêm Trọng PIT Sentiment (Đã đồng bộ)
- **Điều kiện PIT sentiment**: Sửa lại điều kiện kiểm tra thành `available_at <= as_of < timestamp`.
- **Validation `NaN`/`±inf`**: Yêu cầu các giá trị base signals, sentiment scores, age, article counts phải hữu hạn.

### 5. Tích hợp thêm Chỉ số Vĩ mô mới (World Bank API)
- **Lạm phát / CPI** (`FP.CPI.TOTL.ZG`), **Tăng trưởng GDP** (`NY.GDP.MKTP.KD.ZG`), **Cung tiền M2** (`FM.LBL.BMNY.ZG`) từ World Bank API.
- Áp dụng `published_at` theo chu kỳ công bố chuẩn (Cuối năm T+1 cho số liệu năm).

## Kế hoạch Thực hiện

### [MODIFY] [macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_pipeline.py)
- Thay đổi `DEFAULT_URLS` sang URL HTML của SBV và các URL API World Bank.
- Thêm HTML parser cho SBV với contract strict date, regex parse locale, table selector `tbl-rate`.
- Sửa hàm `run()` sử dụng `filelock`, schema validation, kiểm tra corruptions, null/duplicate `revision_id`, atomic replace qua file `.tmp`.
- Cập nhật hàm `query_as_of` thực hiện deterministic latest-vintage selection theo thứ tự ưu tiên `published_at DESC, ingested_at DESC, revision_id DESC`.

### [MODIFY] [sentiment_alpha.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/signal/sentiment_alpha.py)
- Sửa logic kiểm tra PIT thành `available_at <= as_of < timestamp`.

### [MODIFY] [test_macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_pipeline.py) & [test_sentiment_alpha_opt.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_sentiment_alpha_opt.py)
- **Test cases bắt buộc**:
  - `test_sbv_html_malformed_page_rejected`: Kiểm tra fail-closed khi thiếu bảng hoặc 0 dòng.
  - `test_existing_store_corruption_preserves_destination`: Kiểm tra hash file đích không đổi khi ghi lỗi.
  - `test_concurrent_writers_safety`: Kiểm tra `filelock` khi 2 tiến trình ghi cùng lúc.
  - `test_query_as_of_latest_vintage_deterministic`: Kiểm tra deterministic selection khi có nhiều revisions.
  - `test_missing_sbv_publication_date_fail_closed`: Kiểm tra loại bỏ bản ghi thiếu ngày quan sát.

## Kế hoạch Xác minh
```powershell
pytest tests/test_macro_pipeline.py tests/test_sentiment_alpha_opt.py -v
```
Chạy `fetch_macro_indicators()` và kiểm tra file đầu ra `data/macro_indicators.parquet`.
