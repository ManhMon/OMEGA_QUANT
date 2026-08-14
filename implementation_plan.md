# Kế hoạch Triển khai Chi tiết Pha 7: Tiến hóa Thực nghiệm Toàn diện trên GPU/Numba JIT & Xác thực Chất lượng

## 1. Bối cảnh & Mục tiêu Kỹ thuật Pha 7
* **Vấn đề hiện tại**:
  - Toàn bộ cơ sở hạ tầng tăng tốc JIT (Numba JIT accelerated operators) và bộ giám sát FDR-controlled decay monitor đã được tích hợp thành công ở Pha 6.
  - Bây giờ cần thực thi một chu trình tiến hóa thực tế toàn diện (Empirical Evolution Run) để sản sinh và thăng hạng các nhân tố Alpha tối ưu nhất cho hệ thống giao dịch live, lưu vào tệp kết quả đầu ra.
* **Mục tiêu Pha 7**:
  1. Khởi chạy tiến trình GP Alpha Evolution toàn diện thông qua kịch bản `scripts/run_weekly_evolution.py` tích hợp tăng tốc JIT.
  2. Đánh giá kiểm tra độ trực giao (orthogonalization) và kiểm định ngoài mẫu (Out-Of-Sample Test set) thông qua champion/challenger promotion.
  3. Xuất kết quả các Alpha thăng hạng chất lượng nhất vào tệp tin `.ly_state/session/evolved_alphas.json`.

---

## 2. Bản đồ Tệp tin & Cam kết Bảo toàn Mã nguồn
* **Tệp tạo mới / Nâng cấp cốt lõi**:
  - Không có tệp mã nguồn hoặc tệp cấu hình sản xuất nào bị thay đổi ở Pha 7. Mọi logic vận hành JIT và FDR của Pha 6 đã hoạt động đầy đủ và được tái sử dụng.
  - Đầu ra của Pha 7 là tệp dữ liệu kết quả: `.ly_state/session/evolved_alphas.json` [MODIFY].
* **Dữ liệu đầu vào bắt buộc**:
  - Tệp lịch sử giá: `data/market_2015_now.parquet` [READ] (phụ thuộc dữ liệu VN-Index cập nhật hàng tuần).
* **Kiểm thử liên quan**:
  - `tests/test_run_weekly_evolution_diverse_ctor.py` [RUN].

---

## 3. Đặc tả Toán học & Quy trình Chạy Tiến hóa

### A. Chu kỳ Kích hoạt (Weekly Trigger Schedule)
* Tiến trình được chạy định kỳ hàng tuần (vào mỗi chiều thứ Sáu sau khi kết thúc phiên giao dịch và nhận dữ liệu cập nhật mới) để làm mới pool Alpha, giảm thiểu alpha decay.

### B. Phân chia Dữ liệu Tránh Leakage (Train/Val/Test Split)
Hệ thống sử dụng cơ chế phân mảnh thời gian (chronological split) phi chồng chéo:
- **Train Set (70%)**: Từ 2015-01-01 đến 2022-04-30 (dùng để tìm kiếm cây biểu thức Alpha GP).
- **Validation Set (15%)**: Từ 2022-05-01 đến 2024-04-30 (dùng để culling/lọc thô các Alpha có IC âm hoặc không ổn định).
- **OOS Test Set (15%)**: Từ 2024-05-01 đến hiện tại (dùng để so sánh Champion/Challenger và ra quyết định thăng hạng cuối cùng).

### C. Quy trình Chạy GP Evolution & Luật Thăng Hạng Ngoài Mẫu (OOS-Only Promotion)
Tiến trình tiến hóa thực nghiệm sẽ được khởi động thông qua dòng lệnh:
```bash
python scripts/run_weekly_evolution.py --generations 15 --population-size 150 --workers 4 --backend threads --regime all
```
* **Cơ chế JIT VM**: JIT VM cài đặt tự động từ các tối ưu hóa của `genetic_alpha_evolution_v4` sẽ biên dịch nhanh các toán tử chuỗi thời gian tăng tốc độ tính toán.
* **Quy trình Lọc và Thăng Hạng OOS-Only**:
  1. Tính toán hiệu suất (Spearman IC và Sharpe/PnL score) của các Alpha Challenger vượt qua culling.
  2. **Quy tắc thăng hạng**: Việc thăng hạng các Alpha ứng viên được thực thi **chỉ trên tập OOS Test Set** độc lập ($\text{OOS\_IC} \ge 0.01$ và $\text{OOS\_Sharpe} \ge 0.08$ đối với thị trường Việt Nam) để đảm bảo loại bỏ hoàn toàn look-ahead bias và overfitting.
  3. Lọc bỏ các Alpha có độ tương quan với các nhân tố Style Factors (Size, Value, Momentum, Volatility, Liquidity) vượt ngưỡng quy định.
  4. Ghi các Alpha thăng hạng vượt qua kiểm định OOS Test vào `.ly_state/session/evolved_alphas.json`.

---

## 4. An toàn PIT & Tiêu chuẩn Kiểm thử Chấp nhận (Acceptance Criteria)

### A. Quy tắc PIT Safety
* Kịch bản sử dụng cơ chế dịch chuyển `shift(1)` trên toàn bộ đặc trưng đầu vào trước khi căn chỉnh mục tiêu dự báo ngày $T$, đảm bảo không có Look-Ahead leakage.

### B. Tiêu chuẩn Kiểm thử Chấp nhận
1. **Evolution Run Completion**: Chạy tiến trình hoàn tất không phát sinh bất kỳ runtime errors nào, ghi nhận kết quả đầu ra thành công.
2. **Promoted Alphas Validation**: Tệp `.ly_state/session/evolved_alphas.json` chứa danh sách các cây biểu thức Alpha hợp lệ với đầy đủ siêu dữ liệu (OOS Sharpe, OOS IC).
3. **Diverse Constructor Test Pass**: Khẳng định unit test `tests/test_run_weekly_evolution_diverse_ctor.py` hoàn thành đạt kết quả `PASS`.

---

## 5. Repo-Local Skill Sources & Forbidden Path Scan

### Authoritative Repo-Local Files Read (Role 16 L2):
- `.agents/AGENTS.md`
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

### Forbidden Path Scan Result:
- Hoàn toàn tuân thủ, không truy cập bất kỳ nguồn non-authoritative nào.

