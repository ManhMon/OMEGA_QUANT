# Kế hoạch Triển khai: Thu thập & Khử trùng dữ liệu tin tức báo chí 11 năm (Remediation V10)

Kế hoạch này được lưu trữ chính thức trong kho mã nguồn để khắc phục toàn bộ các điểm chặn thẩm định L3 từ Compliance Officer (Role 20).

---

## 1. Định nghĩa Nguồn dữ liệu & Đặc tả kỹ thuật 11 năm

Để loại bỏ các rào cản về bản quyền, chi phí quét BigQuery và lỗi nghẽn mạng của Wayback Machine, hệ thống sẽ sử dụng bộ nguồn dữ liệu đã được xác thực sau:

1. **vnstock / Vietcap REST API (Nguồn lịch sử chính - 11 năm)**:
   - **Mục đích**: Tải dữ liệu tin tức doanh nghiệp lịch sử từ **2015-08-01** (mốc thời gian sớm nhất có dữ liệu thực tế trong backend Vietcap) đến **2026-06-30** (mốc kết thúc dữ liệu giá lịch sử).
   - **Hợp đồng Request (Executable Request Contract)**:
     - URL: `https://iq.vietcap.com.vn/api/iq-insight-service/v1/news?ticker=&fromDate={YYYYMMDD}&toDate={YYYYMMDD}&languageId=1&page={page}&size={size}`
     - Ví dụ minh họa: `https://iq.vietcap.com.vn/api/iq-insight-service/v1/news?ticker=&fromDate=20240101&toDate=20240107&languageId=1&page=0&size=10`
     - HTTP Headers bắt buộc: `{"User-Agent": "Mozilla/5.0", "Accept": "application/json"}`
     - Cấu trúc Response Schema: `{"data": {"content": [{"id": str, "newsTitle": str, "publicDate": str, "ticker": str|None}]}}`
     - Rate-limit: Tối đa 10 requests/giây.
   - **Phân trang tuần tự & Khử trùng lặp Idempotent**: Truy vấn theo từng phân vùng ngày (`fromDate` = `toDate`). Duyệt tuần tự `page = 0, 1, 2...` với `size = 100`. Tiêu chí kết thúc là khi `len(content) < size` hoặc `content` rỗng. Để chống lặp trang do thứ tự server thay đổi, duy trì tập `seen_news_ids` trong bộ nhớ cho mỗi ngày để loại bỏ các bản ghi trùng lặp.

2. **HTML Scrapers (Nguồn realtime tích lũy hàng ngày)**:
   - **CafeF Scraper**: `https://cafef.vn/thi-truong-chung-khoan.chn`
   - **TinNhanhChungKhoan Scraper**: `https://tinnhanhchungkhoan.vn/chung-khoan/`
   - **VnEconomy Scraper**: `https://vneconomy.vn/chung-khoan.htm`
   - **Vietstock Scraper**: `https://vietstock.vn/chung-khoan.htm`

---

## 2. Đặc tả Cấu trúc Dữ liệu `NewsRecord` & Ma trận khả dụng PIT

Dữ liệu tin tức chuẩn hóa sẽ tuân thủ cấu trúc dữ liệu mở rộng 9 cột sau:
```python
class NewsRecord:
    symbol: str               # Mã chứng khoán được xác thực PIT-safe
    title: str                # Tiêu đề bài viết gốc
    publish_time: datetime    # Thời điểm xuất bản (UTC)
    sentiment_score: float    # Điểm tâm lý (-1.0 đến 1.0)
    available_at: datetime    # Thời điểm tin tức khả dụng bất biến trong hệ thống (UTC)
    url: str                  # Canonical URL đã chuẩn hóa
    source: str               # Tên nguồn cào tin (Vietcap, CafeF, v.v.)
    source_id: str            # ID duy nhất của bài báo từ nguồn gốc
    provenance: str           # Chuỗi JSON lưu vết: raw_publish_time, capture_time, content_hash
```

### Ma trận khả dụng PIT bất biến (Immutable PIT Availability Truth Table)

| Nguồn cào tin (Source) | Quy tắc xác định `available_at` (UTC) |
| :--- | :--- |
| **Realtime Web Scrapers** | `= publish_time + 1 day` |
| **vnstock / Vietcap API** | `= publish_time + 1 day` |

*Cơ chế Replay-Stable & Invariants*:
- Để đảm bảo tính an toàn PIT tuyệt đối, mọi bản ghi tiêu thụ trong backtest bắt buộc phải thỏa mãn ràng buộc:
  `publish_time <= available_at <= as_of_time`
  (với `as_of_time` là thời gian giả lập hiện tại của backtest).
- Bằng cách sử dụng quy tắc bất biến `available_at = publish_time + 1 day`, mốc khả dụng `available_at` luôn cố định và độc lập với thời điểm chạy lại dữ liệu, loại bỏ hoàn toàn look-ahead bias và lỗi không thể tái lập khi replay.
- *Xử lý múi giờ & thời gian tương lai*: Mọi thời gian được quy đổi chuẩn sang UTC. Nếu tin tức có `publish_time` trong tương lai so với thời điểm cào thực tế hoặc thiếu thông tin múi giờ không thể phân tích, bản ghi sẽ bị loại bỏ vào thư mục cách ly.

---

## 3. Khử trùng lặp & Dynamic Ticker Verification

### Khử trùng lặp tiêu đề
1. **Lớp 1 (Exact URL)**: Loại bỏ các tham số theo dõi (`utm_*`, `ref`, `from`, `fbclid`, `gclid`), so khớp URL canonical chính xác.
2. **Lớp 2 (Exact Title)**: So khớp `normalized_title` (chữ thường, xóa khoảng trắng thừa, xóa dấu tiếng Việt).
3. **Lớp 3 (Fuzzy Title Match)**: Sử dụng khoảng cách Levenshtein (similarity > 0.88) trong cửa sổ rolling 48 giờ để lọc các bài tin sao chép sửa đổi nhẹ.
*Bảo toàn Provenance*: Lưu vết bài viết xuất hiện sớm nhất, đồng thời nối tiếp nguồn bị trùng vào trường `provenance`.
*Xác minh chất lượng tự động*: Thuật toán khử trùng lặp được đánh giá trực tiếp qua bài test kiểm thử độ chính xác trên tệp fixture `tests/fixtures/labeled_news_pairs.json` (chứa 100 cặp tin tức được gắn nhãn độc lập không trùng), cam kết đạt tỷ lệ **Precision >= 95%** và **Recall >= 90%**.

### Dynamic Ticker Verification (Tránh Survivorship Bias)
- Với mỗi bài tin tại thời điểm `publish_time`, xác thực trạng thái niêm yết của mã chứng khoán bằng cách so khớp xem mã đó có phát sinh giao dịch trong lịch sử giá `data/market_2015_now.parquet` vào năm xuất bản hay không.
- *Phạm vi tuyên bố*: Quy tắc này đảm bảo xác thực doanh nghiệp có niêm yết/giao dịch thực tế trong năm, loại bỏ survivorship bias từ các mã chưa niêm yết hoặc đã hủy niêm yết từ lâu (không mô phỏng các đợt tạm dừng giao dịch 1-2 ngày do thiếu lịch tạm dừng giao dịch).
- Đối với mốc thời gian sau `2026-06-30` (vượt quá market watermark): Hệ thống sẽ lập tức **fail-closed** (ngừng cào và báo lỗi).

---

## 4. Giải pháp Vận hành, Di trú Schema & Quản lý Lỗi
- **Robots.txt & Rate-Limit**: Bắt buộc tuân thủ Robots.txt của từng tên miền, duy trì độ trễ tối thiểu 2.0 giây cho mỗi lượt request. Nếu không đọc được `robots.txt` do lỗi kết nối mạng, scraper sẽ áp dụng cơ chế fail-closed để dừng tiến trình.
- **Tự động phục hồi (Durable Checkpoint)**: Ghi nhận trạng thái checkpoint theo ngày vào `data/cache/scrapers_checkpoint/` dạng JSON ghi đè nguyên tử, bao gồm cả mã băm checksum SHA-256 của tệp Parquet để đảm bảo tính toàn vẹn.
- **Cơ chế Retry & Quarantine**: Tích hợp decorator retry với cơ chế exponential backoff (3 lượt thử, thời gian chờ tối thiểu 4 giây, tối đa 16 giây). Các bản ghi lỗi được cách ly vào thư mục `data/cache/quarantine/` (nằm ngoài thư mục bằng chứng SoD `.ly_state`) kèm mã lỗi.
- **Di trú Schema (Schema Migration Contract)**: Tạo script di trú `scripts/migrate_news_parquet.py` để đọc tệp Parquet 6 cột hiện tại, bổ sung các cột `source = 'CafeF'`, `source_id = 'legacy_' + content_hash`, `provenance = '{"migration": "v1_legacy_migration"}'`. Ghi nguyên tử sang tệp tạm và đổi tên; hủy tệp tạm nếu gặp lỗi.

---

## 5. Kế hoạch Kiểm thử & Tiêu chí Nghiệm thu

### Kịch bản kiểm thử (Automated Tests)
1. Chạy toàn bộ test suite hiện có (31 tests passed):
   ```powershell
   python -m pytest tests/test_news_aggregator_scrapers.py tests/test_sentiment_dual_engine.py tests/test_news_aggregator.py -v
   ```
2. Thêm bài test kiểm thử độ chính xác Precision/Recall của logic khử trùng lặp trên tệp `tests/fixtures/labeled_news_pairs.json`.
3. Thêm bài test kiểm thử preflight API Vietcap, logic cào tin batch, phân trang, di trú schema 9 cột, lưu checkpoint, retry, robots.txt và kiểm tra phân phối dữ liệu theo năm (2015-2026).

### Tiêu chí Nghiệm thu (Acceptance Criteria)
- 100% dòng dữ liệu thỏa mãn ràng buộc PIT: `publish_time <= available_at <= as_of_time`.
- Tỷ lệ Null của các cột cốt lõi (`symbol`, `title`, `publish_time`) bằng 0.0%.
- 0 lỗi vi phạm SoD: Writer Role 15 ≠ Auditor Role 20. Phán quyết Cổng chỉ do L3 Codex ghi nhận tại `.ly_state/session/phase_gates.json`.
- Tệp Parquet đầu ra `data/news_sentiment_2015_now.parquet` tuân thủ đúng schema 9 cột sạch (bao gồm cột provenance và source).
- Script vận hành không tự ý cập nhật phase_gates.json.
- Độ phủ dữ liệu kiểm chứng bao quát toàn bộ các năm từ 2015 đến 2026 (mốc kết thúc 2026-06-30, tối thiểu 5 bài/năm từ 2016-2025).
