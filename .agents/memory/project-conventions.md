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
- **Unsandboxed Heavy Computations Policy (Chạy ngoài Sandbox cho Tác vụ Nặng)**: Đối với toàn bộ các tiến trình kiểm thử hiệu năng (benchmark), chạy tiến hóa GP, thử nghiệm lại (backtest), hoặc quét tham số có khối lượng xử lý tính toán nặng, L1/L2/L3 bắt buộc phải đăng ký xin quyền chạy ngoài Sandbox (`unsandboxed` permission) để giải phóng giới hạn phần cứng (Platform Cap 4GB) và khai thác tối đa cấu hình phần cứng vật lý (20GB+ RAM).


