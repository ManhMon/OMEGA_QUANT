# AGENTS.md - OMEGA_QUANT Protocol

> [!IMPORTANT]
> The authoritative rules and specifications for the OMEGA_QUANT multi-agent SoD protocol have been consolidated to the workspace customization root path to ensure a single source of truth:
> - [.agents/AGENTS.md](file:///C:/Users/GHC/repos/OMEGA_QUANT/.agents/AGENTS.md)

Please refer to and edit `.agents/AGENTS.md` for all protocol modifications, role updates, and platform specifications.

## Anti-Polling & Zero-Idle Directive

`ANTI_POLLING_ZERO_IDLE_20260918`: Never poll, loop, or repeatedly invoke status or gate-enforcer tools while waiting for background execution. Stop calling tools immediately and yield the turn when a long-running or background command starts.

## Resume-First Directive

`RESUME_FIRST_MANDATORY_20261008` (P0 Priority): Phần việc nào của L2/L3/L4 gián đoạn, pause, timeout hoặc cần bổ sung test evidence mà nền tảng hỗ trợ resume (ví dụ `codex exec resume <session_id>`, Claude Code resume session, Antigravity resume), TUYỆT ĐỐI KHÔNG CHẠY LẠI TỪ ĐẦU (no restarting from scratch). L2/L4 khởi tạo phiên mới khi bắt đầu chu kỳ remediation mới; L3 Codex BẮT BUỘC ƯU TIÊN RESUME phiên L3 trước đó khi re-audit chu kỳ remediation để kế thừa ngữ cảnh đối soát F-xxx, tiết kiệm token.

## Mandatory MCP Advisor & Critic Directive

`MANDATORY_MCP_ADVISOR_CRITIC_20261015` (P0 Priority): Luôn khởi động L2 và L4 với MCP advisor (`--mcp-advisor` / `--advisor-mode mcp`), TUYỆT ĐỐI KHÔNG dùng native advisor (`--advisor opus`). Luôn khởi động L3 Codex với MCP critic (`--mcp-critic` backed by `omega-l3-critic`).

