# V21_ERROR_RESOLUTIONS_LOG.md

## Error Resolution Log - V21_QUANT Project

### 📋 DANH SÁCH LỖI & CÁCH XỬ LÝ (CONSOLIDATED)

| ID | Ngày | Phân loại | Lỗi (Issue) | Triệu chứng (Symptom) | Cách xử lý (Resolution) | Người thực hiện | Severity | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P0-01** | 28/04/26 | **Risk** | ADV Unit Mismatch | Orders bị clamp về 0 hoặc 1 cổ phiếu vì tưởng vượt thanh khoản. | Đổi `adv_unit` từ 'shares' sang 'vnd'. Đồng bộ với vốn 2 tỷ. | OpenCode | P0 | ✅ FIXED |
| **P0-02** | 29/04/26 | **Arch** | Hard-coded Risk Limits | Layer 03 ghi đè cấu hình từ SystemOrchestrator. | Inject `RiskLimitsConfig` động từ `SystemConfig` vào `ExecutionEngine`. | OpenCode | P0 | ✅ FIXED |
| **P0-03** | 29/04/26 | **Data** | Price Scale Mismatch (1000x Factor) | Giá VN stock ở dạng '1000 VND' (25.5 = 25,500 VND) nhưng Capital là 'VND'. Gây lỗi 1000x khiến lệnh bị Risk Guard Reject. | Áp dụng nhân `1000.0` tại **14 vị trí** chuyển đổi: system_orchestrator.py, risk_limits.py, rebalancer.py, execution_engine.py. | OpenCode | P0 | ✅ FIXED |
| **P1-01** | 29/04/26 | **Backtest** | 0% Return / No Trades | Chạy 605 ngày nhưng NAV không đổi. | 1. Kiểm tra Alpha Features (XGBoost). 2. Nới Risk Guard (Notional Cap) để khối lượng lệnh 300M có thể khớp. | OpenCode | P1 | ⚠️ IN-PROGRESS |
| **P1-02** | 29/04/26 | **ML** | XGBoost Feature Drift | Model train với 0 features hoặc feature không khởi (OOS). | Đảm bảo list `alpha_cols` được truyền nhất quán giữa Train và Predict loop. | OpenCode | P1 | ✅ FIXED |
| **P1-03** | 30/04/26 | **Data** | Price Scale Mismatch (Test Suite) | VN stock prices không được scale ×1000 trong test suite. | Đảm bảo tất cả price features ×1000 trước khi tính toán. | OpenCode | P1 | ✅ FIXED |
| **P2-01** | 30/04/26 | **Infra** | Permission Denied (tmux) | User không có quyền tạo tmux session. | Chạy command với elevated permissions hoặc dùng exec thay vì pty. | Ly | P2 | ✅ FIXED |
| **P3-01** | 30/04/26 | **Env** | PATH tmux not found | tmux không có trong PATH của MSYS2. | Dùng OpenClaw sessions thay tmux hoặc cài đặt tmux vào PATH. | Ly | P3 | ✅ FIXED |
| **P1-04** | 07/05/26 | **Infra** | SOV CLI Execution [WinError 2] | SOV không thể gọi `codex`/`opencode` từ Python subprocess. | Dùng PowerShell wrapper: `subprocess.run(['powershell', '-Command', 'codex', ...], shell=True)`. | OpenCode | P1 | ✅ FIXED |

---

## 💡 BÀI HỌC KINH NGHIỆM (KEY LESSONS)

1. **Về Vốn (Capital)**: Khi nâng vốn lên 2 tỷ, tất cả các ngưỡng Notional và ADV phải được tính toán lại theo VND, không dùng Share.
2. **Về Quy trình**: Luôn chạy `/ac` sau khi OpenCode fix để Codex kiểm tra tính nhất quán (Consistency) giữa các Layer.
3. **Về Dữ liệu**: Kiểm tra Feature Importance sau khi train XGBoost. Nếu Importance của tất cả Alphas < 0.01 -> Model đang bị rác.
4. **Về Price Scale (TCB/VNM...)**: Giá VN stock tải về luôn ở đơn vị '1000 VND'. Luôn nhân `price * 1000.0` khi chuyển sang Notional hoặc Shares. **CẤM dùng raw price cho Capital VND**.
5. **Về Progressive Disclosure**: Chỉ nạp Skill Catalog cho L1 (Ly), các agent L2/L3 chỉ nhận skill cụ thể khi cần.
6. **Về State Persistence**: Không bao giờ dựa vào RAM của tiến trình con. Luôn ghi state xuống `.ly_state/`.
7. **Về PTY vs Exec**: Dùng PTY cho phiên dài (audit nhiều vòng), dùng exec/run cho tác vụ ngắn (sinh code 1 lượt).

---

## 🔄 TỰ ĐỘNG HÓA KINH NGHIỆM (AUTO-LOGGING SOP)
Mọi thay đổi thành công sau Audit phải được ghi vào file này ngay lập tức. Ly sẽ không đợi anh Mạnh nhắc.

---

## 📊 Error Summary (Last 7 Days)
- **Total Errors**: 8
- **P0 (Critical)**: 3 (37.5%)
- **P1 (High)**: 3 (37.5%)
- **P2 (Medium)**: 1 (12.5%)
- **P3 (Low)**: 1 (12.5%)

## Top Root Causes
1. **Data Format Mismatch (Price Scale)**: 3 (37.5%)
2. **Architecture Issues**: 1 (12.5%)
3. **Infrastructure/Environment**: 2 (25%)
4. **ML Model Issues**: 1 (12.5%)
5. **Backtest Logic**: 1 (12.5%)

## Prevention Measures
- **Price Scale**: Thêm validation layer trước khi tính toán features. Luôn nhân ×1000 cho VN stock prices.
- **Permissions**: Kiểm tra quyền trước khi chạy command. Dùng OpenClaw sessions thay vì tmux.
- **Environment**: Document required tools trong TOOLS.md. Kiểm tra PATH trước khi chạy CLI tools.
- **State Management**: Luôn dùng `.ly_state/` cho persistence, không dựa vào RAM.

---

**Last Updated**: 2026-04-30 02:50 (Asia/Bangkok)  
**Maintainer**: Ly (L1 Orchestrator)  
**Version**: V21.5 Elite - PD v4.1 (Stateful & Self-Learning)
