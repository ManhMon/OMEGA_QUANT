# Macro News Ingestion Pipeline (Dữ Liệu Tin Tức Vĩ Mô)

Dữ liệu tin tức vĩ mô (văn bản) yêu cầu một quy trình xử lý tách biệt với dữ liệu vĩ mô định lượng (số liệu). Kế hoạch này đề xuất xây dựng `MacroNewsPipeline` để lấy tin tức từ nhiều nguồn báo chí và tổ chức tài chính uy tín của Việt Nam, tuân thủ tuyệt đối quy tắc Point-in-Time (PIT).

## Proposed Sources (Danh sách nguồn tối đa)
Các nguồn RSS/Web có cung cấp thời gian xuất bản chính xác:
1. **CafeF (Vĩ mô - Đầu tư)**: RSS `https://cafef.vn/vi-mo-dau-tu.rss`
2. **Vietstock (Kinh tế vĩ mô)**: RSS `https://vietstock.vn/kinh-te-vi-mo.rss`
3. **Báo Chính Phủ (Kinh tế)**: RSS `https://baochinhphu.vn/kinh-te.rss`
4. **SBV (Ngân hàng Nhà nước)**: Tin tức điều hành chính sách.
5. **VCBS (Vietcombank Securities)**: Báo cáo phân tích vĩ mô (vcbs.com.vn)
6. **VNDirect Research**: Báo cáo vĩ mô định kỳ.
7. **SSI Research**: Báo cáo chiến lược và vĩ mô.
8. **VnEconomy**: RSS Tin vĩ mô.
9. **Báo Đầu Tư**: RSS Tin kinh tế.
10. **Tin Nhanh Chứng Khoán**: RSS Tin vĩ mô.

## Proposed Changes

### `src/omega/data/macro_news_pipeline.py`
#### [NEW] [macro_news_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_news_pipeline.py)
- Khởi tạo `MacroNewsPipeline` với kiến trúc đa nguồn (Multi-Source Extractor).
- Viết các adapter chuyên biệt:
  - `RSSAdapter`: Xử lý tự động các feed chuẩn (CafeF, Vietstock, BaoChinhPhu, VnEconomy, v.v.)
  - `ScraperAdapter`: Chuyên crawl HTML cho các trang tổ chức (VCBS, SSI, VNDirect, SBV) do họ không có RSS chuẩn hoặc giấu trong iframe.
- Lọc trùng lặp bài báo dựa trên `URL` hoặc nội dung tương tự.
- **PIT Safety**: Trích xuất trường `pubDate` làm `published_at`. `available_at` sẽ bằng `published_at + 15 phút`. Không lấy bài viết nếu thiếu timestamp xuất bản chính xác.
- Schema: `['source', 'title', 'summary', 'url', 'published_at', 'available_at', 'ingested_at']`.
- Định dạng lưu: Parquet tại `data/macro_news.parquet`.

### `tests/test_macro_news_pipeline.py`
#### [NEW] [test_macro_news_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_news_pipeline.py)
- Unit test cho `RSSAdapter` và `ScraperAdapter`.
- Test PIT-safety (từ chối lưu nếu không tìm thấy pubDate hợp lệ).

## Verification Plan
### Automated Tests
- Chạy `pytest tests/test_macro_news_pipeline.py`.
- Chạy dry-run thử fetch 5 tin mới nhất từ VCBS và CafeF.

### L3 Audit
- Dispatch OpenCode L2 thực thi.
- Dispatch Codex L3 audit PIT-safety.
