# MASTER_BACKTEST_PLAN.md - BẢN KẾ HOẠCH BACKTEST NHẤT QUÁN VÀ DUY NHẤT
**Trạng thái**: ACTIVE (Thực hiện xuyên suốt)
**Cập nhật cuối**: 2026-05-21
**Chủ sở hữu**: Ly (L1 Orchestrator)

---

## 🎯 1. MỤC TIÊU CHIẾN LƯỢC

1. **Chuẩn hóa E2E**: Quản lý và phân định rõ ràng các entrypoint kiểm thử theo đúng phạm vi (Research vs Production).
2. **Tối ưu hóa Risk/Reward**: Đưa Sharpe Ratio (Net) > 1.70, giảm Max Drawdown (Net) từ -21% xuống dưới -15%.
3. **ML Alpha Validation**: Định nghĩa rõ tiêu chuẩn đánh giá ML Gate (`ml_predictor`) không vi phạm PIT.
4. **Đồng bộ hóa Chi Phí**: Đồng nhất mô hình chi phí giao dịch (phí, thuế, trượt giá) trên toàn hệ thống.

---

## 📊 2. PHÂN ĐỊNH PHẠM VI KIỂM THỬ (SCOPE MATRIX)

Để tránh nhầm lẫn giữa kiểm thử nhanh và đánh giá hệ thống lớn, dự án quy định 4 phạm vi:

| Loại hình kiểm thử | Entrypoint Script | Dữ liệu kiểm thử | Mục đích sử dụng |
|:---|:---|:---|:---|
| **1. Research Backtest (Mẫu)** | `scripts/export_backtest_detailed.py` | 252 ngày, 30 mã thanh khoản cao nhất | Kiểm tra nhanh logic alpha mới, debug flow weights/turnover |
| **2. Production Acceptance** | `scripts/backtest_real_data.py` | 2015-2026, Universe 1534 mã | Đánh giá hiệu suất tổng thể trước khi deploy |
| **3. Walk-Forward Robustness** | `scripts/run_phase35_backtest.py` | 8-fold Walk-Forward (2015-2026) | Kiểm tra tính ổn định qua nhiều regime thị trường |
| **4. Shadow Live / Mock Run** | `scripts/live_test_e2e_mock_smoke.py` | Live VNStock API (T-1 lag) | Đo lường độ trễ khớp lệnh và trượt giá thực tế |

---

## 🛠️ 3. MÔ HÌNH CHI PHÍ ĐỒNG NHẤT (COST MODEL)

Baseline chi phí **chỉ áp dụng cho MASTER_BACKTEST_PLAN acceptance run**. Đây là giả định đánh giá của plan, **không phải** source-of-truth mặc định cho toàn repo hay cho các module runtime hiện hữu.
- **Phí giao dịch (Commission)**: 0.15% (15 bps) mỗi chiều mua/bán.
- **Thuế bán cổ phiếu (Tax)**: 0.10% (10 bps) chỉ áp dụng cho chiều bán.
- **Trượt giá giả định (Slippage)**: 0.05% (5 bps) cho mỗi giao dịch.
- **Tổng chi phí vòng quay (Round-trip cost)**: 0.45% (mua 0.20% + bán 0.25%).

**Source-of-truth note**:
- Runtime/module defaults có thể khác giữa `packages/backtest/`, `packages/quant/`, `transaction_cost_optimizer.py`, và `config/production.yaml`.
- Khi audit production behavior, phải đối chiếu trực tiếp module/config đang chạy; không suy ngược từ baseline của plan này.

---

## 📋 4. CHI TIẾT CÁC GIAI ĐOẠN ĐANG THỰC HIỆN

### 🚀 Giai đoạn 1: Chuẩn hóa & Đóng băng Quy trình Đánh giá (Ngày 1 - IMPLEMENTATION_DONE)
- **Công việc**:
  - Hợp nhất kế hoạch, xóa file kế hoạch cũ gây nhiễu.
  - Phân định rõ 4 scope chạy backtest.
  - Cô lập test smoke `*_smoke.py`.
- **Success Criteria**:
  - `Get-ChildItem docs/PLAN_*.md` trả về rỗng hoặc chỉ còn artifact được whitelist rõ ràng.
  - `git status --porcelain` không còn diff ngoài phạm vi thay đổi chủ đích của stage.
  - Có APPROVED gate record cho `MASTER_BACKTEST_PLAN_GATE`.
- **OMEGA Gate**:
  - L2 Owner: Backend Engineer (Role 9).
  - L3 Audit: Code Reviewer (Role 21) [PENDING_AUDIT] (Yêu cầu đầy đủ gate evidence từ L3 audit: `l3_session_id`, `l3_session_key`, `audit_report_path`, `final_verdict`).

### 📉 Giai đoạn 2: Tối ưu Risk & Giảm Drawdown (Ngày 2-3)
- **Công việc**:
  - Tăng số cổ phiếu tối đa nắm giữ: `top_n_stocks` từ 5 -> 8.
  - Áp dụng Sector Cap tối đa 30% tổng danh mục.
  - Tăng khoảng thời gian tái cơ cấu: `rebalance_freq` từ 5 ngày -> 7 ngày để giảm chi phí giao dịch.
- **Success Criteria**: Max Drawdown < -15%, Sharpe Ratio giữ vững > 1.5.

### 🧠 Giai đoạn 3: Định nghĩa Chính xác ML Gate (Ngày 4)
- **Công việc**:
  - Giữ nguyên ML Floor IC ở mức `0.08` cho Production Acceptance.
  - Định nghĩa "Research Gate": Chỉ chấp nhận signal có IC >= 0.05 trong validation set khi thoả mãn đồng thời:
    $$\text{Tỷ lệ } \frac{\text{Mean IC}}{\text{Std Rolling IC}} > 1.5$$ (với cửa sổ rolling 20 ngày và số mẫu kiểm thử tối thiểu N >= 60 ngày).
- **Success Criteria**: Signal XGBoost không bị overfit (kiểm tra `val_pit_ic >= 0.05` và `rolling_ic_mean / rolling_ic_std > 1.5` trên 60 ngày out-of-sample).

### 🎯 Giai đoạn 4: Robustness & Stress Test (Ngày 5)
- **Công việc**:
  - Chạy 8-fold Walk-Forward (2015-2026).
  - Stress test qua các thời kỳ khủng hoảng thị trường Việt Nam (COVID-2020, Bear Market 2022).
- **Success Criteria**: Lợi nhuận net dương trong mọi năm out-of-sample.

### 📊 Giai đoạn 5: Shadow Live (Ngày 6-7)
- **Công việc**:
  - Chạy mock trading hằng ngày dựa trên dữ liệu khớp lệnh thực tế cuối phiên.
  - Log chênh lệch trượt giá (Slippage) thực tế so với giả lập.
- **Success Criteria**: Slippage thực tế lệch không quá 2 bps so với backtest.

### ⚡ Giai đoạn 6: Tối ưu hóa Hiệu suất Nâng cao (Performance Uplift Roadmap)
- **Công việc**:
  - **Tối ưu hóa Cửa sổ Huấn luyện (Longer Train Window)**: Mở rộng `train_years` từ 1 năm lên 3 năm để mô hình XGBoost học đầy đủ các regime thị trường lớn.
  - **Tích hợp Chi phí Giao dịch vào Việc Lọc Alpha (Cost-Aware Alpha Selection)**: Liên kết trực tiếp kết quả của mô hình tối ưu hóa chi phí từ Phase 19 (`omega.quant.transaction_cost_optimizer.TransactionCostOptimizer` thông qua API hiện hữu `calculate_cost()`) để ước tính tổng chi phí giao dịch theo symbol, rồi dùng cost estimate đó làm penalty cho các alpha có daily turnover quá cao trước khi đưa vào danh mục.
  - **Quản lý Drawdown Chủ động (Active Drawdown Control)**: Tích hợp stop-loss động cấp độ danh mục (Stop-loss threshold 5%, tính toán dựa trên mức sụt giảm của NAV ngày T so với đỉnh NAV gần nhất trong fold; nếu vi phạm, set toàn bộ tỷ trọng portfolio weights về 0.0 - tức giữ cash, reset trạng thái khi bước sang fold tiếp theo) và bộ cắt mạch tự động (Circuit Breaker) trong Walk-Forward engine để bảo vệ tài sản trong các đợt sụt giảm mạnh.
- **Success Criteria**: Đạt mục tiêu tối ưu hóa chiến dịch lớn: Sharpe Ratio > 1.70, Max Drawdown giảm thiểu xuống dưới -15.00% (vượt xa mức baseline thô).

---


## 📈 QUY TẮC PHÊ DUYỆT CUỐI CÙNG (GO/NO-GO RULES)

| Chỉ số | Target (Mục tiêu) | Floor (Chấp nhận tối thiểu) | Phương pháp đo lường |
|:---|:---|:---|:---|
| **Sharpe Ratio (Net)** | > 1.70 | > 1.20 | Lợi nhuận net chia cho Std Net (năm hóa) |
| **Max Drawdown (Net)** | < -15.00% | < -25.00% | Mức sụt giảm tối đa từ đỉnh tài sản net |
| **Avg Daily Turnover** | < 10.00% | < 15.00% | Tổng khối lượng giao dịch chia cho tài sản |
| **PIT Compliance** | 100% | 100% | Đạt chuẩn PIT Safety (No look-ahead bias, T-1 lag enforced, chronological train/test splitting) và được verify qua `sod_gate_enforcer.py`. |

**Quy tắc Go/No-Go khi có kết quả hỗn hợp:**
1. Nếu bất kỳ chỉ số nào rơi vào dưới mức **Floor** → **NO-GO** (Bắt buộc dừng lại để sửa lỗi logic/code).
2. Nếu tất cả các chỉ số nằm giữa mức **Floor** và **Target** → **HOLD** (Cần tối ưu thêm tham số trước khi lên production).
3. Nếu tất cả các chỉ số vượt mức **Target** và đạt 100% PIT Safety → **GO** (Cho phép deploy production).

---

## 🔒 OMEGA GATE APPROVAL CONTRACT (SOD Compliance)

**Gate ID**: `MASTER_BACKTEST_PLAN_GATE`
**Status**: `PENDING_AUDIT`
**Owner**: Ly (L1 Orchestrator - Role 1)

### Strict Isolation Contract (Bắt buộc theo AGENTS.md):
- **1 Agent = 1 Role**: Mỗi session chỉ được đóng đúng 1 vai trò.
- **1 Agent = 1 Task**: Mỗi session chỉ xử lý đúng 1 nhiệm vụ cụ thể.
- **Context Blindness + Minimal Context**: Ly phải dùng `get_minimal_context` để chỉ cấp đúng context cần thiết cho task, không nhồi toàn bộ master plan.
- **Ephemeral Lifecycle**: Session con hoàn thành nhiệm vụ phải đóng ngay (terminate), không giữ context kéo dài.
- **L3 Audit-Only Boundary**: Role 21/20 chỉ audit, tuyệt đối không fix code/doc.

### L3 Audit Evidence (Required before [APPROVED]):
- `l3_session_id`: (Chờ Codex audit hoàn thành)
- `l3_session_key`: (Chờ Codex audit hoàn thành)
- `audit_report_path`: (Sẽ là `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\.ly_state\session\audit_reports\role21_master_backtest_plan_audit_YYYYMMDD_HHMMSS.md`)
- `final_verdict`: (Chờ L3 Code Reviewer (Role 21) verdict: `[APPROVED]` hoặc `[NEEDS_FIX]`)
- `pit_safety`: (Chờ L3 verification)
- `role_compliance`: (Chờ L3 verification)

### Mandatory Execution Protocol (Bắt buộc tuân thủ - 6 bước chuẩn):
1. **Pre-flight Check**: Trước khi write/update bất kỳ config hay logic nào:
   ```powershell
   python scripts/sod_preflight.py --check-before-write C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\MASTER_BACKTEST_PLAN.md master_backtest
   ```
2. **Transition Validation**: Trước khi chuyển stage:
   ```powershell
   python scripts/sod_gate_enforcer.py --validate-transition master_backtest PENDING_AUDIT
   ```
3. **L3 Independent Audit**: L3 (Codex) chạy lệnh độc lập kiểm tra và ghi report (mặc định dùng CLI trực tiếp; không dùng `sessions_spawn` trừ khi user yêu cầu explicit **hoặc** CLI trực tiếp không khả dụng; audit session phải tách biệt hoàn toàn khỏi implementation session):
   ```powershell
   codex exec --dangerously-bypass-approvals-and-sandbox "[L3-Audit:Role21-Review] Audit MASTER_BACKTEST_PLAN.md"
   ```
4. **Gate Lock After L3**: Ngay sau khi L3 hoàn thành audit:
   ```powershell
   python scripts/sod_gate_enforcer.py --lock-gate master_backtest L3_AUDIT_COMPLETE --l3-session-id <id> --l3-session-key <key> --audit-report-path <path>
   ```
5. **Approval Validation**: L1 chạy validate approval trước khi ghi nhận gate:
   ```powershell
   python scripts/sod_gate_enforcer.py --validate-approval master_backtest
   ```
6. **Final Gate + Pre-push Block**: Khi pass, L1 ghi APPROVED và verify trước push:
   ```powershell
   python scripts/sod_gate_enforcer.py --lock-gate master_backtest APPROVED --l3-session-id <id> --l3-session-key <key> --audit-report-path <path>
   python scripts/sod_gate_enforcer.py --check-before-push
   ```
   - `.git/hooks/pre-push` phải tự động block push nếu SOD violation. Không bypass.

### Ly Bootstrap Protocol (Bắt buộc trước mọi thao tác):
Trước khi thực thi bất kỳ gate workflow nào, Ly (L1 Orchestrator) phải:

**Bước 1: Auto-Load Skills (PD v4.2)**
- Ly tự động scan task context và load relevant skills:
  * Priority skills (luôn load): `OMEGA_QUANT/skills/team/SKILL.md` (v2.4 - Orchestration protocol), `OMEGA_QUANT/skills/audit-cycle/SKILL.md` (v2.4 - SOD workflow)
  * Conditional skills (load khi cần): `OMEGA_QUANT/skills/elite_karpathy/karpathy-coder/SKILL.md` (v2.1 - Khi L2 implementation), `OMEGA_QUANT/skills/elite_karpathy/karpathy-auditor/SKILL.md` (v2.1 - Khi L3 audit)
- Skill injection protocol:
  ```python
  if task_type == "implementation":
      load_skill("team")
      load_skill("audit-cycle")
      load_skill("karpathy-coder")
  elif task_type == "audit":
      load_skill("team")
      load_skill("audit-cycle")
      load_skill("karpathy-auditor")
  ```

**Bước 2: Đọc Memory & State**
- Đọc `MEMORY.md` và `memory/YYYY-MM-DD.md` - Lấy context từ session trước (nếu chưa có file ngày thì ghi nhận `PENDING_MEMORY_INIT`)
- Đọc `.ly_state/session/active_tasks.json` - Xác nhận không có task conflict
- Đọc `.ly_state/session/phase_gates.json` - Kiểm tra gate status hiện tại
- Đọc `.ly_state/session/agent_locks.json` - Kiểm tra execution locks
- Đọc `.ly_state/session/context_cache.json` - Kiểm tra context đã nạp

**Bước 3: Load Constitutional Files**
- Đọc `AGENTS.md` - 25 roles mapping
- Đọc `TOOLS.md` - CLI execution rules
- Đọc `SOUL.md` - SOD protocol
- Đọc `HEARTBEAT.md` - System status

**Bước 4: In ra Dashboard & Resource Control**
- Xác nhận vai trò (L1/L2/L3), MCP status, pending tasks
- Kiểm tra RAM > 10GB (bắt buộc trước mọi task theo `AGENTS.md:163`)
- Kiểm tra Single-Platform Protocol: Không gọi OpenCode và Codex chạy song song đồng thời (trừ khi isolated)
- Áp dụng Platform Capping: Giới hạn 4GB RAM cho mỗi platform execution
- Thực hiện Context Pruning: Xóa context role-specific ngay sau khi hoàn thành task
- Kiểm tra Execution Locks (không có conflict)
- Hiển thị loaded skills

**Bước 5: Skill Injection Log**
- Ghi log skills được load vào `.ly_state/session/loaded_skills.json`
- Format: `{"session_id": "uuid", "loaded_at": "ISO8601", "skills": [{"name": "...", "version": "...", "path": "..."}]}`

**Bước 6: SOP Pre-Work Checks (SEARCH-BEFORE-BUILD)**
Trước khi giao việc mới cho bất kỳ Agent nào:
1. **SEARCH FIRST**: Sử dụng `ls -R`, `grep` hoặc `query_graph` để tìm xem tính năng này đã tồn tại chưa
2. Đọc `SYSTEM_MASTER_LOG.md` - Kiểm tra xem module cần dùng đã được Approve chưa
3. Đọc `OMEGA_SUPER_MASTER_PLAN.md` - Đối chiếu với Phase/Week hiện tại
4. Nếu module CHƯA có: Giao **OpenCode** viết/sửa triển khai L2, sau đó gọi **Codex** audit/review L3

### L2 Implementation Control (Bắt buộc trước L3 Audit):
Trước khi L3 Audit được phép chạy, L2 Implementation phải hoàn thành đầy đủ:
1. **L2 Session Start**: Chạy `opencode run "[L2-Impl:Role9-Backend] <task>"` (không dùng `sessions_spawn` trừ khi user yêu cầu explicit **hoặc** CLI trực tiếp không khả dụng).
2. **Unit Tests**: Chạy `pytest` đạt 100% green (không có failed tests)
3. **L2 Session Terminate & Pruning**: L2 session tự hủy sau khi hoàn thành (không self-approve, Segregation of Duties - SOD), đồng thời thực hiện Context Pruning xóa context role-specific ngay sau khi hoàn thành task.
4. **Isolation Verification**: Ly xác nhận L2 session đã đóng trước khi spawn L3.
5. **Gate Lock After L2**: Ngay sau khi L2 hoàn thành:
   ```powershell
   python scripts/sod_gate_enforcer.py --lock-gate master_backtest L2_DONE --l2-session-id <id> --l2-session-key <key>
   ```


### Gate Decision Rules (L1 Only):
1. **L3 audits và tạo report** → Ghi `l3_session_id`, `l3_session_key`, `audit_report_path`, `final_verdict`
2. **L1 (Ly) đọc evidence từ L3** → Verify đầy đủ 4 trường bắt buộc (`l3_session_id` không rỗng và nhất quán với report, `l3_session_key` không rỗng và nhất quán với report/gate artifact hiện hành, `audit_report_path` file tồn tại và có nội dung, `final_verdict` là `[APPROVED]``). Không hardcode prefix/session-key regex; hệ thống chấp nhận mọi format evidence sống nếu nhất quán, truy vết được, và do L3 phát hành hợp lệ.
3. **Nếu L3 verdict = `[APPROVED]`** → L1 chạy `--lock-gate` và ghi vào `.ly_state/session/phase_gates.json` (master gate file), đồng bộ bản ghi phụ tại `.ly_state/gates/master_backtest_gate.json`
4. **Nếu L3 verdict = `[NEEDS_FIX]` hoặc L3 crash (429/Timeout)** → Ly PHẢI retry hoặc chờ, không được bypass, không được tự ý ghi gate
5. **Nếu thiếu bất kỳ evidence nào trong 4 trường bắt buộc** → AUTO REJECT, set `PENDING_AUDIT`

**Note**: Theo OMEGA_QUANT SOD Protocol, L3 (Codex) chỉ audit và tạo report. L1 (Ly) là actor duy nhất được phép ghi gate decision vào `.ly_state/session/phase_gates.json` sau khi verify evidence từ L3; file `.ly_state/gates/<phase>_gate.json` dùng để theo dõi evidence cấp phase.
