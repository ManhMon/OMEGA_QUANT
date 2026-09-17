# L3 Advisory Report: Latent Space Dimension & Retraining Frequency Optimization
**Date**: 2026-06-11
**Platform**: Codex (L3)
**Model**: cx/gpt-5.5
**Role**: Code Reviewer (Role 21) & Machine Learning Engineer (Role 16)
**Status**: APPROVED

---

## 1. Kích thước Không gian ẩn (Latent Space Dimension)

### Khuyến nghị:
- **Default (Mặc định)**: `16`
- **Phạm vi tìm kiếm (Sweep Range)**: `[8, 16, 24, 32]`
- **Giới hạn trên (Maximum Cap)**: `32` (Tránh tăng lên `64+` trừ khi có bằng chứng vượt trội).

### Rationale (Cơ sở khoa học & kỹ thuật):
1. **Tỷ lệ Nén tối ưu**: Đầu vào của autoencoder sau khi trải phẳng (flatten) có kích thước là $T \times F = 60 \times 114 = 6840$. Nén từ `6840` về `16` đạt tỷ lệ nén **427.5:1**, giúp lọc bỏ cực mạnh nhiễu (noise) trong dữ liệu định lượng tài chính Việt Nam và giữ lại các thành phần đặc trưng tiềm ẩn chính.
2. **Tránh Quá khớp (Overfitting)**: Kích thước không gian ẩn lớn (ví dụ: `64+`) trong các mô hình Autoencoder phi giám sát rất dễ ghi nhớ nhiễu thị trường thay vì học các chế độ (regimes) giao dịch.
3. **Tiêu chuẩn chọn kích thước**: Nên quét qua các kích thước `[8, 16, 24, 32]` và chọn giá trị nhỏ nhất nằm trong khoảng sai số $1\sigma$ (1 Standard Error) của kết quả kiểm thử downstream (ví dụ: Sharpe Ratio trên tập OOS).

---

## 2. Tần suất Huấn luyện lại (Retraining Frequency)

### A. Trong quá trình Backtest / Cross-Validation (CPCV):
- **Quy tắc bắt buộc**: **Huấn luyện động (dynamically train) trong từng fold kiểm thử (chỉ dùng tập Train của fold đó)**.
- **Lý do**: Autoencoder là một phép biến đổi học máy (learned transform). Nếu chúng ta pre-train autoencoder trên toàn bộ dữ liệu trước khi chạy CPCV, thông tin phân phối của tương lai sẽ bị rò rỉ (look-ahead leak) vào các fold kiểm thử ở quá khứ thông qua biểu diễn ẩn.
- **Tối ưu hóa tốc độ**: Áp dụng cơ chế **caching** (lưu lại encoder weights + latent matrix dựa trên hash danh sách index của tập Train của fold) để tránh tính toán lặp khi các fold trùng lặp tập train.

### B. Trong môi trường Vận hành thực tế (Live / Production):
- **Tần suất tối ưu**: **Hàng quý (Quarterly)**.
- **Tần suất bổ sung**: Cập nhật **hàng tháng (Monthly)** khi kích hoạt các chỉ báo trôi lệch dữ liệu (Drift Triggers).
- **Lý do**: Việc huấn luyện lại hàng ngày hoặc hàng tuần sẽ tạo ra rất nhiều nhiễu, làm thay đổi cấu trúc không gian ẩn quá nhanh và gây bất ổn định cho mô hình dự báo downstream (do tính xoay trục và đảo dấu của không gian ẩn AE là ngẫu nhiên giữa các lần fit).

### Các chỉ báo trôi lệch kích hoạt cập nhật (Drift Triggers):
- Sai số tái tạo (Reconstruction Loss) tăng $> 20-30\%$ so với mức cơ sở.
- Kiểm định độ trôi lệch phân phối (PSI/KS test) của không gian ẩn vượt ngưỡng an toàn.
- Chỉ số chất lượng mô hình (OOS Sharpe Ratio) suy giảm mạnh trong tháng gần nhất.

---

## 3. Tối ưu hóa cho Cấu hình Máy hiện tại (CPU-only, 16GB RAM)

Để chạy mượt mà và không bị cạn bộ nhớ (OOM) hoặc đóng băng hệ thống:

| Tham số | Giá trị tối ưu | Ý nghĩa |
| :--- | :--- | :--- |
| **Dtype** | `float32` | Tránh `float64` để giảm 50% dung lượng RAM (ma trận dữ liệu đầu vào $39k \times 6840$ chỉ tốn ~1.07 GB thay vì 2.13 GB). |
| **Batch Size** | `128` hoặc `256` | Tận dụng tốt bộ đệm CPU L3. |
| **Epochs** | `10` đến `30` | Đi kèm Early Stopping với `patience=2` hoặc `3` để dừng sớm khi hội tụ. |
| **n_threads** | Cấp dưới `4` hoặc `8` | Tránh chiếm toàn bộ tài nguyên CPU làm treo hệ thống. |
| **num_workers** | `0` | Tránh overhead phân mảnh bộ nhớ của multiprocessing trên Windows. |
| **Downstream check**| So sánh với PCA | Nếu Autoencoder không vượt trội hơn IncrementalPCA về độ ổn định, nên ưu tiên dùng PCA để đảm bảo tốc độ cực nhanh và tính nhất quán. |

---

## Ký xác nhận
**Auditor**: Codex L3 Auditor (cx/gpt-5.5)  
**Phân quyền thực thi**: L2 (OpenCode) chịu trách nhiệm cấu hình các giá trị mặc định này trong mã nguồn.
