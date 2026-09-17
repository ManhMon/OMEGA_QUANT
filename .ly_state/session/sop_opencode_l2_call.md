# SOP: Gọi OpenCode L2 (Role 9 - Backend Engineer)
**Version**: 1.0  
**Date**: 2026-06-10  
**Author**: L4 SOD  

---

## ⚠️ LƯU Ý QUAN TRỌNG

### Pattern đúng (từ hôm nay):
```powershell
opencode run --print-logs --log-level INFO --dir C:\Users\GHC\repos\OMEGA_QUANT --pure --dangerously-skip-permissions --format json "[L2-Impl:Role9-BackendEngineer] Read .ly_state/session/PROMPT_FILE.md and execute it exactly."
```

### Pattern sai:
- ❌ `opencode exec "prompt"` - sẽ treo
- ❌ `Get-Content file.md | opencode exec --full-auto` - syntax sai
- ❌ `opencode run --file file.md` - không support

---

## Workflow chuẩn

### 1. Tạo prompt file trước
```powershell
# Prompt file: .ly_state/session/l2_<task>_prompt_<date>.md
```

### 2. Gọi OpenCode L2
```powershell
opencode run --print-logs --log-level INFO --dir C:\Users\GHC\repos\OMEGA_QUANT --pure --dangerously-skip-permissions --format json "[L2-Impl:Role9-BackendEngineer] Read .ly_state/session/<prompt_file>.md and execute it exactly."
```

### 3. OpenCode sẽ:
- Đọc prompt file
- Thực hiện fixes
- Viết report ra `.ly_state/session/l2_<task>_report_<date>.md`
- Update phase_gates.json nếu có yêu cầu

---

## Flags quan trọng

| Flag | Ý nghĩa |
|------|---------|
| `--print-logs` | In logs ra stderr để debug |
| `--log-level INFO` | Log level INFO |
| `--dir <path>` | Working directory (bắt buộc) |
| `--pure` | Không load external plugins |
| `--dangerously-skip-permissions` | Auto-approve (cẩn thận!) |
| `--format json` | Output JSON format |

---

## Checklist trước khi gọi L2

- [ ] L3 audit đã hoàn thành và trả về [NEEDS_FIX]
- [ ] Prompt file đã viết rõ ràng với:
  - Scope (files được phép sửa)
  - Required fixes (danh sách issues)
  - Verification (pytest command)
  - Output (report file path)
- [ ] SOD compliance: L2 implementer ≠ L3 auditor
- [ ] Không self-approval

---

## Sau khi OpenCode trả về

1. **Đọc report**: `.ly_state/session/l2_<task>_report_<date>.md`
2. **Verify**: Chạy pytest để confirm fixes
3. **Re-submit L3 audit**: Nếu pytest pass, gọi Codex L3 lại
4. **Update gate**: Nếu L3 APPROVED, update phase_gates.json

---

## Common Pitfalls

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-------------|-----------|
| OpenCode không chạy | Dùng `exec` thay vì `run` | Dùng `opencode run` |
| Prompt không vào OpenCode | Dùng pipe hoặc --file | Dùng message string với "Read file.md" |
| Permission denied | Thiếu --dangerously-skip-permissions | Thêm flag |
| Log không thấy | Thiếu --print-logs | Thêm flag |

---

## File locations

- **L2 prompts:** `.ly_state/session/l2_*_prompt_*.md`
- **L2 reports:** `.ly_state/session/l2_*_report_*.md`
- **L3 audit reports:** `.ly_state/session/audit_reports/role21_*.md`
- **Phase gates:** `.ly_state/session/phase_gates.json`
- **SOP này:** `.ly_state/session/sop_opencode_l2_call.md`

---

**Last updated:** 2026-06-10 14:36 GMT+7
