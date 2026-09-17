# Kế hoạch Thiết kế Kiến trúc GP Evolution V4 & Tối ưu hóa Tốc độ (Đã hiệu chỉnh theo phản biện)

Kế hoạch này phác thảo các thay đổi kiến trúc cốt lõi cho **GP Evolution Engine V4** nhằm tối ưu hóa tốc độ thực thi, chuyển đổi công nghệ tính toán từ Pandas sang NumPy chéo phẳng kết hợp Numba JIT và Feature Bank (WorldQuant-style), giải quyết triệt để phản biện từ Claude Code CLI.

---

## Repo-Local Source Evidence
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` -> False
- `.openclaw\skills` -> False
- `C:\Users\GHC\.agents` -> True, non-authoritative, not read
- `.codex\memories` -> False

---

## User Review Required

> [!IMPORTANT]
> - **Mục tiêu hiệu năng**: Điều chỉnh mục tiêu tăng tốc xuống **2x - 4x** thực tế (phù hợp với khuyến nghị của §7 do phép tính khử trùng lập sector/size OLS `lstsq` chiếm phần lớn chi phí chưa được can thiệp sâu).
> - **PIT-Safety**: Cam kết Feature Bank tiền tính toán hoàn toàn theo trục thời gian chéo của từng cổ phiếu biệt lập, dịch chuyển thông tin bằng độ trễ $T-1$ trước khi nạp vào GP, bảo toàn tính địa phương của fold (fold locality) để loại bỏ mọi nguy cơ rò rỉ dữ liệu tương lai.
> - **Sai số cho phép (Equivalence Tolerance)**: Cho phép sai số nhỏ (dung sai tương quan tín hiệu $\ge 0.9999$ hoặc sai lệch tuyệt đối $\le 1e-5$) giữa V4 và V3 thay vì khớp 6 chữ số thập phân, để tương thích với các tối ưu hóa của Numba.
> - **Biệt lập mã nguồn**: Không sửa đè lên V3 mà tạo mới hoàn toàn tệp `genetic_alpha_evolution_v4.py`.

---

## Proposed Changes

### 1. Xây dựng Feature Bank & Caching (WorldQuant-Style)
* **Feature Bank**: Tiền tính toán các đặc trưng cơ sở (`decay_linear`, `ts_rank`, `vol_ratio`, `rolling_std`, `rolling_mean`) theo từng ticker riêng biệt, dịch chuyển thông tin $T-1$ để PIT-safe. Lưu trữ dưới dạng mảng NumPy 3D `(Feature x Ticker x Date)`.
* **Sub-tree Caching (Memoization)**: Áp dụng bảng băm lưu trữ các biểu thức con. Bản đồ băm sẽ được xây dựng tĩnh trước khi thực hiện luồng song song (pre-parallelization) hoặc sử dụng các biến khóa thread-safe để tránh race-conditions dưới môi trường joblib `threads`.

### 2. Vector hóa hoàn toàn Fitness (Spearman daily IC)
* **Vectorized IC**: Thay thế vòng lặp tính Spearman IC chéo phần bằng phép toán ma trận NumPy trên mảng 2D. Đảm bảo nhân rộng đầy đủ cơ chế của V3 bao gồm:
  - Khử trùng lặp chéo (neutralization) đồng thời cho cả alpha tín hiệu và target.
  - Áp dụng mặt nạ thanh khoản (`_evaluation_mask`).
  - Xử lý các trường hợp đồng hạng (tie handling) tương thích với `scipy.stats.spearmanr`.

### 3. Tăng tốc bằng Numba JIT & Tránh Oversubscription
* Biên dịch các hàm lăn (rolling) bằng `@njit(fastmath=False)` (tắt fastmath để bảo toàn độ chính xác số học).
* Tắt cờ `parallel=True` của Numba khi kết hợp với joblib `threads` để tránh tranh chấp tài nguyên luồng (CPU oversubscription).

---

## Proposed Files

### [NEW] [genetic_alpha_evolution_v4.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/genetic_alpha_evolution_v4.py)
* Phiên bản cải tiến chứa kiến trúc GP V4, tích hợp Feature Bank, Numba JIT và Vectorized Spearman IC.

### [NEW] [tests/test_genetic_alpha_evolution_v4.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/tests/test_genetic_alpha_evolution_v4.py)
* Bộ unit test và regression test cho lõi tính toán V4.

---

## Verification Plan

### Kiểm thử hiệu năng (Benchmarking)
* Đo đạc hiệu năng thực tế (evaluations/sec). Chỉ tiêu nghiệm thu: **V4 nhanh hơn V3 từ 2x - 4x**.

### Kiểm định tính đúng đắn (Equivalence Check)
* So sánh chéo tín hiệu đầu ra của V4 và V3 trên cùng tập tham số. Hệ số tương quan Pearson giữa 2 tín hiệu phải đạt $\ge 0.9999$.
