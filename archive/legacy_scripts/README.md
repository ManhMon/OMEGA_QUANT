# Archive: Legacy Scripts & Historical Phase Artifacts

## Mục đích & Nguyên tắc Bất biến (Archival Invariants)

Thư mục này lưu trữ các script lịch sử gắn với các phase phát triển cũ và các công cụ di chuyển/vá tạm đã hoàn thành nhiệm vụ.

1. **Chỉ phục vụ đối chiếu lịch sử và bằng chứng kiểm toán (Audit Trail)**.
2. **CẤM NHẬP (STRICTLY NO IMPORTS)**: Không bất kỳ file nào trong `src/`, `tests/` hoặc `scripts/` được phép import từ thư mục `archive/`.
3. **CẤM CHẠY TRONG PIPELINE VẬN HÀNH**: Không được gọi từ CI/CD, crontab, hoặc SoD pipeline hiện hành.
4. **LOẠI KHỎI KIỂM THỬ**: Thư mục này được loại khỏi test discovery và lint vận hành.
