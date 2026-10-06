---
type: project
created: 2026-05-25
updated: 2026-05-25
---

# Project Conventions

## Git Workflow
- Always create a new dedicated branch for major code changes.
- Branch name format should follow: `feature/[task-slug]` or `fix/[bug-slug]`.

## OMEGA_QUANT Constitution (SOD & AG Kit Rules)
- **Strict SOD Tiers**: Ly (L1 Orchestration/Gate-Only, Role 1-5), OpenCode (L2 Implementation/Testing, Role 6-16), Codex (L3 READ-ONLY Audit, Role 17-25). Never self-approve or write code in L1/L3.
- **Vietnamese Language Rule**: Always communicate with the user in Vietnamese.
- **Zero-Timer Policy**: Absolutely DO NOT use `schedule`, `cron`, or background sleep/timers. Rely exclusively on Reactive Wakeup (the system resumes execution automatically when tasks finish).
- **Agent Selection Checklist**:
  1. **Phân tích miền tri thức (Domain Analysis)**: L1 phân tích xem câu hỏi thuộc miền nào (Kiến trúc hệ thống, Giải thuật toán ML, Phê duyệt cổng, DevOps, v.v.).
  2. **Giải quyết Vai trò Kết hợp (Composite L1 Role)**: Vai trò mặc định của L1 là `orchestrator`, nhưng bắt buộc kết hợp song song cùng vai trò chuyên gia khác tùy theo miền tri thức để tăng chất lượng điều phối. Ví dụ:
     * Kiến trúc/Thiết kế giải thuật: `orchestrator / tech-lead` hoặc `orchestrator / machine-learning-engineer`.
     * Kiểm soát cổng/Phát hành: `orchestrator / release-manager`.
     * Kiểm thử/Vận hành: `orchestrator / qa-engineer`.
  3. **Thông báo đầu câu trả lời**: Ghi nhận và hiển thị ngay dòng đầu tiên:
     ```markdown
     🤖 **Applying knowledge of `@[l1-role-1 / l1-role-2]`...**
     ```

- **Memory Update Gate (Chốt cập nhật bộ nhớ)**: Mỗi khi một cổng kiểm duyệt đạt trạng thái `[APPROVED]` và trước khi kết thúc phiên/chuyển phase, L1 bắt buộc phải kiểm tra và cập nhật các thay đổi kiến trúc, kết quả tối ưu, hoặc tham số mới vào `tech-decisions.md` để đảm bảo bộ nhớ không bị out-of-date.
- **Unsandboxed Heavy Computations Policy (Chạy ngoài Sandbox cho Tác vụ Nặng)**: Đối với toàn bộ các tiến trình kiểm thử hiệu năng (benchmark), chạy tiến hóa GP, thử nghiệm lại (backtest như walk-forward validation, CPCV backtesting), quét tham số, các tính toán huấn luyện học máy (Machine Learning training như LightGBM, XGBoost, tối ưu hóa siêu tham số Optuna), tiền tính toán đặc trưng quy mô lớn (feature precomputation), và mô phỏng thử nghiệm căng thẳng (Monte Carlo stress testing) có khối lượng xử lý nặng, L1/L2/L3 bắt buộc phải đăng ký xin quyền chạy ngoài Sandbox (`unsandboxed` permission) để giải phóng giới hạn phần硬件 (Platform Cap 4GB) và khai thác tối đa cấu hình phần cứng vật lý (20GB+ RAM).
- **Pytest Execution Safety (Chống sập IPC Server / Agent Host trên Windows)**: Khi thực thi `pytest` trong IDE tool (`run_command`), TUYỆT ĐỐI KHÔNG chạy stream stdout trực tiếp với terminal escape codes/colorama dài khiến IPC pipe bị context canceled / crash server. Bắt buộc:
  1. Dùng cờ an toàn: `pytest -q -o addopts="" --capture=sys -p no:terminal`
  2. Hoặc redirect output ra file log: `pytest ... > .ly_state/pytest.log 2>&1`
  3. Hoặc yêu cầu chạy ngoài terminal độc lập nếu test suite dài.
- **Strict Dispatch Command Integrity (Nguyên tắc bất di bất dịch cho L2/L3 dispatch)**:
  1. BẮT BUỘC chỉ copy và thực thi đúng 100% câu lệnh trong khối `---COMMAND---` do `dispatch_l2.py` hoặc `dispatch_l3.py` kết xuất.
  2. TUYỆT ĐỐI CẤM tự ý chuyển sang script ReAct phụ hoặc model webchat fallback (như `scripts/run_l2_agent.py`, `sod_pipeline_au.py`, model `au/gpt-*`) trừ khi có chỉ thị rõ ràng từ người dùng.
  3. Phải dùng đúng CLI và model đã được cấu hình tự động bởi lệnh dispatch (Opencode `9router/cx/gpt-6-luna`, `9router/cx/gpt-6.1-sol` hoặc Codex `cx/gpt-6.1-sol`).
- **L2 Remediation Performance Optimization (Tối ưu hóa hiệu năng vòng lặp L2)**:
  1. **Nâng cấp Model Lead sang Sol ở vòng 4**: Nếu sau 3 vòng remediation L2 vẫn chưa đạt `[APPROVED]` từ L3, ở vòng 4 bắt buộc nâng cấp model L2 lên `9router/cx/gpt-6.1-sol` (`--model 9router/cx/gpt-6.1-sol` hoặc `--risk high`) để tối đa hóa khả năng suy luận logic và thông lượng token.
  2. **Cắt giảm tràn ngữ cảnh kiểm thử (Output Truncation)**: Chạy pytest với cờ rút gọn `-q --tb=short -o addopts=""`, ngăn đẩy hàng nghìn dòng log/trace vào context gây phình token (Context Inflation) làm chậm TTFT.
  3. **Cưỡng chế Phân luồng Subagent (Enforced Subagent Offloading)**: Bắt buộc Lead model ủy quyền toàn bộ các tác vụ lặp lại (quét AST/regex diện rộng, chạy test suite 300+ ca, thu thập log lỗi) cho subagent (`task(agent='general')`). **Subagent L2/L3 dùng model `cx/gpt-6-luna` (hoặc `9router/cx/gpt-6-luna`) thay thế cho `gemini`** (Lead model tuyệt đối cấm dùng Luna, bắt buộc dùng `cx/gpt-6.1-sol`). Cấm Lead model tự chạy các lệnh kiểm thử dài inline để bảo toàn ngữ cảnh và giữ phiên Lead dưới 25-30 steps.
  4. **Giảm tải I/O Snapshot**: Giữ sạch worktree, hạn chế thay đổi file không cần thiết để tránh nghẽn I/O git tracking của OpenCode trên Windows NTFS.
  5. **Cơ chế Tiền kiểm tra Zero-Token (Pre-Dispatch Local Sweeps)**: Tự động chạy script python cục bộ (`validate_l2_report.py`, test collection) trước khi gọi LLM để Lead không phải tốn token/bước suy luận cho các kiểm tra tĩnh.
  6. **No-Luna Lead Model Policy (Cấm dùng Luna làm Lead Model)**: TUYỆT ĐỐI KHÔNG dùng lead model `cx/gpt-6-luna` hoặc `9router/cx/gpt-6-luna` cho các vòng L2/L3 vì tốc độ xử lý quá chậm. Bắt buộc dùng `cx/gpt-6.1-sol` (hoặc `9router/cx/gpt-6.1-sol`) cho Lead model ở mọi vòng điều phối (cả baseline lẫn remediation).
