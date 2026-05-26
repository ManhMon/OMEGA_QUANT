# AGENTS.md - OMEGA_QUANT Protocol (Per Spec Section 17)
**Version**: 2.4
**Status**: PD v4.2 (Progressive Disclosure + Auto Skill Injection)
**Last Updated**: 2026-05-11

Dự án OMEGA_QUANT: Hệ thống Quant AI Institutional Grade, vận hành bởi 25 Agent Roles chuyên biệt.

## 🚀 PD v4.2 - LY AUTO SKILL INJECTION (MỚI)

**Progressive Disclosure v4.2**: Ly (L1 Orchestrator) tự động load và inject skills vào Agent context dựa trên task type.

### Auto-Loading Protocol
```python
# Ly auto-detects task type and injects relevant skills
if task_type == "implementation":
    load_skill("OMEGA_QUANT/skills/team/SKILL.md")                    # Always
    load_skill("OMEGA_QUANT/skills/audit-cycle/SKILL.md")             # Always
    load_skill("OMEGA_QUANT/skills/elite_karpathy/karpathy-coder/SKILL.md")  # L2 only
elif task_type == "audit":
    load_skill("OMEGA_QUANT/skills/team/SKILL.md")                    # Always
    load_skill("OMEGA_QUANT/skills/audit-cycle/SKILL.md")             # Always
    load_skill("OMEGA_QUANT/skills/elite_karpathy/karpathy-auditor/SKILL.md") # L3 only
```

### Skill Injection Log
Mọi skill được load phải ghi log vào `.ly_state/session/loaded_skills.json`:
```json
{
  "session_id": "uuid",
  "loaded_at": "2026-05-11T16:50:00Z",
  "skills": [
    {"name": "team", "version": "2.4", "path": "OMEGA_QUANT/skills/team/SKILL.md"},
    {"name": "audit-cycle", "version": "2.4", "path": "OMEGA_QUANT/skills/audit-cycle/SKILL.md"},
    {"name": "karpathy-coder", "version": "2.1", "path": "OMEGA_QUANT/skills/elite_karpathy/karpathy-coder/SKILL.md"}
  ]
}
```

### Benefits
- **Token Efficiency**: Chỉ load skills cần thiết cho task hiện tại
- **Context Clarity**: Agent con nhận đúng "Hiến pháp" cho vai trò của mình
- **Observability**: Log skills giúp trace được Agent đang chạy với bộ luật nào
- **Consistency**: Đảm bảo mọi Agent đều tuân thủ cùng một bộ quy tắc

---

## 🤖 MÔ HÌNH 25 AGENT ĐỘC LẬP (STRICT ISOLATION)

**QUY TẮC CỐT LÕI (CORE PRINCIPLES)**:
1. **1 Agent = 1 Role**: Mỗi session spawn ra là 1 Agent duy nhất, đóng đúng 1 vai. Không có "Multi-role Agent".
2. **1 Agent = 1 Task**: Mỗi lần gọi, Agent chỉ nhận đúng 1 nhiệm vụ cụ thể, rõ ràng.
3. **Context Blindness (Sự mù mờ có chủ ý)**: Agent CHỈ được cung cấp đủ Context để làm đúng nhiệm vụ của mình. Tuyệt đối KHÔNG nhồi nhét toàn bộ Master Plan hay Architecture vào prompt của Agent con để tránh nhiễu và ảo giác (hallucination).
4. **Nền tảng (Platform)** chỉ là môi trường chạy (runtime), không phải là Agent.
   - Ly (Orchestrator L1) giữ gate decision, điều phối audit vòng lặp -> Spawn Agent con độc lập.
   - Agent con chạy -> Trả kết quả -> Tự hủy.

| Platform Runtime | Tier | Chức năng Runtime | Agents chạy trên Platform này |
| :--- | :--- | :--- | :--- |
| **Ly** | L1 | Orchestrator (Điều phối) | Roles 1-5 (Project/Delivery Management) |
| **OpenCode** | L2 | Build, Code, Design | Roles 6-16 (Architect to Machine Learning Eng) |
| **Codex** | L3 | Audit, Review, Security | Roles 17-25 (QA to Auditor) |

---

## 🎭 CHIẾN THUẬT CÔ LẬP AGENT (STRICT ISOLATION PROTOCOL)

Để đảm bảo tính chuyên môn hóa và tiết kiệm token, OMEGA áp dụng quy tắc:
1. **Role Specificity**: Mỗi Agent khi được spawn (via `sessions_spawn`) chỉ được gán đúng 1 Role ID từ danh sách 25 roles.
   - Session Impl (Writer/Fixer): Label `[L2-Impl:*]`.
   - Session Audit (Reviewer/Critic): Label `[L3-Audit:*]`.
2. **Minimal Context Injection**: 
   - Ly (Orchestrator) sẽ dùng `get_minimal_context` để lọc đúng file cần thiết.
   - Tuyệt đối KHÔNG gửi toàn bộ Master Plan cho Agent con.
   - Agent chỉ nhận được: (1) Role Spec, (2) Task Description, (3) Input Files.
3. **Ephemeral Lifecycle**: Agent con hoàn thành nhiệm vụ -> Trả kết quả -> Session bị đóng ngay lập tức.
4. **Platform Independence**: OpenCode/Codex chỉ là môi trường thực thi. Agent mới là thực thể có Persona.
5. **Segregation of Duties (SOD)**: Writer session KHÁC Auditor session. Tuyệt đối cấm self-approval. Impl session PHẢI terminate trước khi Audit session bắt đầu. Review Agent (Role 21) phải từ chối mọi yêu cầu implement/fix.
6. **Gate Contract (Bắt buộc trước khi APPROVED)**: `phase_gates.json` PHẢI có đủ các trường:
   - `l3_session_id` (required)
   - `l3_session_key` (required)
   - `audit_report_path` (required)
   - `final_verdict` = `[APPROVED]` hoặc `[NEEDS_FIX]`
   Nếu thiếu bất kỳ trường nào -> Gate INVALID, bắt buộc set `PENDING_AUDIT`.

## 📋 QUY TRÌNH SOD BẮT BUỘC (HARDCODED WORKFLOW)

1. **L2 Implementation**: Viết code và unit tests. Chạy `pytest` đạt 100% green.
2. **L3 Audit**: LUÔN LUÔN gọi Codex audit artifact của L2. Không được skip.
3. **Verdict**: 
   - Nếu `[NEEDS_FIX]`: Quay lại bước 1.
   - Nếu `[APPROVED]`: Ghi evidence vào `.ly_state/session/phase_gates.json`.
4. **Mandatory Verification**: Chạy `python scripts/sod_gate_enforcer.py` để verify gate lock.
5. **Release**: Chỉ được `git push` khi script verify PASS.

**Lý do**: Đảm bảo 100% code production được kiểm soát độc lập, tránh bias của người viết code.

---

## 🎭 DANH SÁCH 25 AGENT ROLES (STRICT ISOLATION)

### Tier 1: L1 (Ly) - Orchestrator & Management
| Role ID | Role Name | Platform | Responsibility |
|:--------|:----------|:---------|:---------------|
| 1 | Project Manager | Ly (L1) | Strategic orchestration, resource allocation |
| 2 | Product Owner | Ly (L1) | Feature prioritization, stakeholder alignment |
| 3 | Scrum Master | Ly (L1) | Agile process, blocker removal |
| 4 | Release Manager | Ly (L1) | Release coordination, deployment gates |
| 5 | Delivery Manager | Ly (L1) | Timeline tracking, resource management |

### Tier 2: L2 (OpenCode) - Build, Code, Design
| Role ID | Role Name | Platform | Responsibility |
|:--------|:----------|:---------|:---------------|
| 6 | System Architect | OpenCode (L2) | System design, interface definition |
| 7 | Tech Lead | OpenCode (L2) | Technical leadership, code standards |
| 8 | Frontend Engineer | OpenCode (L2) | UI/UX implementation |
| 9 | Backend Engineer | OpenCode (L2) | API and business logic implementation |
| 10 | Database Admin | OpenCode (L2) | Schema design, DB performance |
| 11 | DevOps Engineer | OpenCode (L2) | CI/CD, automation |
| 12 | Cloud Infra Engineer| OpenCode (L2) | Infrastructure as Code |
| 13 | UI/UX Integrator | OpenCode (L2) | UI integration, styling |
| 14 | Data Scientist | OpenCode (L2) | Model research, signal discovery |
| 15 | Data Engineer | OpenCode (L2) | Data pipelines, ETL |
| 16 | Machine Learning Eng| OpenCode (L2) | Model training, deployment |

### Tier 3: L3 (Codex) - Audit, Review, Security
| Role ID | Role Name | Platform | Responsibility |
|:--------|:----------|:---------|:---------------|
| 17 | QA Engineer | Codex (L3) | Functional testing |
| 18 | SDET | Codex (L3) | Test automation, frameworks |
| 19 | Security Auditor | Codex (L3) | Security scanning, threat modeling |
| 20 | Compliance Officer | Codex (L3) | Standards compliance, PIT safety check |
| 21 | Code Reviewer | Codex (L3) | Peer review, audit reports |
| 22 | Penetration Tester | Codex (L3) | Security testing, exploits |
| 23 | Performance Tester | Codex (L3) | Load and stress testing |
| 24 | UAT Validator | Codex (L3) | User acceptance validation |
| 25 | IT Systems Auditor | Codex (L3) | Overall system audit |

---

## 📦 STATE PERSISTENCE (KHÔNG DÙNG RAM)

### Quy tắc Bắt buộc:
- **Tất cả state phải được lưu vào file**: Không lưu trữ state trong biến RAM.
- **Thư mục State**: `.ly_state/` trong workspace root.
- **Cấu trúc State Files**:
  ```
  .ly_state/
  ├── session/
  │   ├── active_tasks.json    # Task đang chạy (map Role -> Platform)
  │   ├── agent_locks.json     # Platform locks
  │   ├── context_cache.json   # Role-specific context
  │   └── .ly_state/session/audit_log.jsonl      # Audit logs (append-only, hash-chained)
  ├── memory/
  │   └── session_*.json      # Role memory snapshots
  └── checkpoints/
      └── checkpoint_*.json   # Checkpoint snapshots
  ```

---

## 🛡️ CHIẾN THUẬT QUẢN LÝ TÀI NGUYÊN (16GB RAM)

1. **Check First**: Check RAM > 10GB trước mỗi task.
2. **Single-Platform Protocol**: Không gọi OpenCode và Codex cùng lúc (trừ khi isolated).
3. **Platform Capping**: OpenCode/Codex giới hạn 4GB RAM mỗi task.
4. **Context Pruning**: Xóa context role-specific ngay sau khi hoàn thành task.

---

## 🚀 CLI EXECUTION VIA ISOLATED BACKGROUND SESSIONS (PD v4.2)

### Quy trình:
```powershell
# 1. Ly (L1) xác định Role & Platform cần dùng
# 2. Ly gọi exec(background: true) kèm instruction cho Role
# 3. Platform (OpenCode/Codex) thực thi và ghi state
# 4. Ly theo dõi qua process(action: "log")
```

---

## 📋 QUY TRÌNH AUDIT CHUẨN HÓA (CODEX FORMAT)

| Trường | Giá trị | Chi tiết |
| :--- | :--- | :--- |
| **Role** | Code Reviewer / Compliance Officer / Security Auditor | Role thực hiện audit |
| **Verdict** | `[APPROVED]` / `[NEEDS_FIX]` | Kết luận cuối cùng |
| **PIT Safety** | `PASS` / `FAIL` | Kiểm tra T-1 Lag & No Look-ahead |
| **Role Compliance** | `PASS` / `FAIL` | Kiểm tra thực thi đúng role-spec |

---

**Version**: 2.3
**Status**: R9 (Backend Engineer Role 9 - Role Title Canonicalization)
**Cập nhật lần cuối**: 10/05/2026 - 17:25 GMT+7 (OMEGA Standard - Strict Isolation v1.0)
