# CLI Role Templates — OMEGA_QUANT SOD Enforcement

**Version:** 1.0  
**Date:** 2026-05-10  
**Purpose:** Khóa role khi dùng OpenCode/Codex CLI thay vì `sessions_spawn`

---

## Nguyên tắc bắt buộc

1. **Role tag đầu prompt:** `[ROLE: X - Tên Role]`
2. **Tier tag:** `[L2-Impl:*]` hoặc `[L3-Audit:*]`
3. **Tách phiên tuyệt đối:** L2 terminate → Ly prep context → L3 spawn
4. **Artifact bắt buộc:** L2 code+test, L3 report+log+verdict
5. **Ly gate cuối:** Chỉ Ly chốt `[APPROVED]`/`[NEEDS_FIX]`

---

## Template L2 (OpenCode Implementation)

### Lệnh chuẩn
```powershell
opencode run "[ROLE: 9 - Backend Engineer] [L2-Impl:ModuleName] Task: <mô tả ngắn gọn>. Scope: <file paths>. Enforce PIT: T-1 lag, no T+0 joins. Output: (1) code files, (2) test files, (3) test results (pytest -v). Rule: Implementation only. No audit. No verdict. Terminate after artifact write."
```

### Ví dụ cụ thể
```powershell
opencode run "[ROLE: 9 - Backend Engineer] [L2-Impl:RiskGuard] Task: Implement RiskGuard module with circuit breaker logic. Scope: OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py, OMEGA_QUANT/tests/phase4/test_risk_guard.py. Enforce PIT: T-1 lag, no T+0 joins. Output: (1) risk_guard.py with CircuitBreaker class, (2) test_risk_guard.py with 8 tests, (3) pytest result. Rule: Implementation only. No audit. No verdict. Terminate after artifact write."
```

### Constraints bắt buộc trong prompt
- `Rule: Implementation only. No audit. No verdict.`
- `Terminate after artifact write.`
- `Enforce PIT: T-1 lag, no T+0 joins.`

---

## Template L3 (Codex Audit)

### Role 20 - Compliance Officer

#### Lệnh chuẩn
```powershell
codex exec --full-auto "[ROLE: 20 - Compliance Officer] [L3-Audit:ModuleName] Task: Audit <module> for <criteria>. Scope: <file paths>. Check: (1) <criterion 1>, (2) <criterion 2>, ... Run: pytest <test path> -v. Output: (1) OMEGA_QUANT/docs/<MODULE>_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/<module>_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

#### Ví dụ cụ thể
```powershell
codex exec --full-auto "[ROLE: 20 - Compliance Officer] [L3-Audit:RiskGuard] Task: Audit RiskGuard for PIT compliance and circuit breaker logic. Scope: OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py, OMEGA_QUANT/tests/phase4/test_risk_guard.py. Check: (1) T-1 lag enforced, (2) circuit breaker thresholds correct, (3) vectorized implementation, (4) tests cover edge cases. Run: pytest OMEGA_QUANT/tests/phase4/test_risk_guard.py -v. Output: (1) OMEGA_QUANT/docs/RISK_GUARD_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/risk_guard_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

### Role 21 - Code Reviewer

#### Lệnh chuẩn
```powershell
codex exec --full-auto "[ROLE: 21 - Code Reviewer] [L3-Audit:ModuleName] Task: Review <module> for <criteria>. Scope: <file paths>. Check: (1) <criterion 1>, (2) <criterion 2>, ... Run: pytest <test path> -v. Output: (1) OMEGA_QUANT/docs/<MODULE>_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/<module>_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

#### Ví dụ cụ thể
```powershell
codex exec --full-auto "[ROLE: 21 - Code Reviewer] [L3-Audit:SignalEngine] Task: Review SignalEngine for code quality and naming conventions. Scope: OMEGA_QUANT/packages/signals/src/omega/signals/signal_engine.py, OMEGA_QUANT/tests/phase3/test_signal_engine.py. Check: (1) OpenClaw naming conventions, (2) vectorized operations, (3) no loops over time series, (4) test coverage >90%. Run: pytest OMEGA_QUANT/tests/phase3/test_signal_engine.py -v. Output: (1) OMEGA_QUANT/docs/SIGNAL_ENGINE_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/signal_engine_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

### Role 25 - IT Systems Auditor

#### Lệnh chuẩn
```powershell
codex exec --full-auto "[ROLE: 25 - IT Systems Auditor] [L3-Audit:ModuleName] Task: Audit <module> for <criteria>. Scope: <file paths>. Check: (1) <criterion 1>, (2) <criterion 2>, ... Run: pytest <test path> -v. Output: (1) OMEGA_QUANT/docs/<MODULE>_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/<module>_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

#### Ví dụ cụ thể
```powershell
codex exec --full-auto "[ROLE: 25 - IT Systems Auditor] [L3-Audit:DataPipeline] Task: Audit DataPipeline for system integration and data flow correctness. Scope: OMEGA_QUANT/packages/data/src/omega/data/pipeline.py, OMEGA_QUANT/tests/phase2/test_pipeline.py. Check: (1) data integrity checks present, (2) error handling complete, (3) logging adequate, (4) integration points validated. Run: pytest OMEGA_QUANT/tests/phase2/test_pipeline.py -v. Output: (1) OMEGA_QUANT/docs/DATA_PIPELINE_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/data_pipeline_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write."
```

### Constraints bắt buộc trong prompt
- `Rule: Audit only. No implementation. No fixes.`
- `Terminate after artifact write.`
- `Output: ... with verdict [APPROVED]/[NEEDS_FIX]`
- `Run: pytest ... -v` (verify test pass)

---

## Workflow chuẩn (SOD enforcement)

```
1. Ly (L1) xác định task + role
   ↓
2. Ly spawn L2 OpenCode CLI
   exec(command: "opencode run '[ROLE: 9 - ...] [L2-Impl:*] ...'", background: true, pty: true)
   ↓
3. L2 chạy → ghi artifact → terminate
   ↓
4. Ly verify L2 artifacts (ALL 3 required):
   - read(code_file_path)           # (1) Code artifact
   - read(test_file_path)           # (2) Test artifact
   - exec("pytest <test_path> -v")  # (3) Test result artifact
   ↓
5. Ly spawn L3 Codex CLI (only after ALL L2 artifacts verified)
   exec(command: "codex exec --full-auto '[ROLE: 20 - Compliance Officer] [L3-Audit:*] ...'", pty: true)
   ↓
6. L3 chạy → ghi audit report + verdict → terminate
   ↓
7. Ly đọc verdict
   ↓
8. Ly gate decision:
   - [APPROVED] → commit + push
   - [NEEDS_FIX] → loop back to step 2 (fresh L2 session)
```

---

## Anti-patterns (tuyệt đối cấm)

❌ **Gộp L2+L3 trong 1 lệnh**
```powershell
# SAI
opencode run "Implement + audit RiskGuard"
```

❌ **L2 tự audit**
```powershell
# SAI
opencode run "[ROLE: 9] Implement RiskGuard and verify PIT compliance"
```

❌ **L3 sửa code**
```powershell
# SAI
codex exec "[ROLE: 20] Audit RiskGuard and fix bugs if found"
```

❌ **Multi-role tags (vi phạm 1 Agent = 1 Role)**
```powershell
# SAI
codex exec "[ROLE: 20/21/25 - Auditor] Audit RiskGuard"
# ĐÚNG: Chọn đúng 1 role
codex exec "[ROLE: 20 - Compliance Officer] Audit RiskGuard"
```

❌ **L2/L3 thực hiện gate decision (quyền duy nhất của Ly)**
```powershell
# SAI
opencode run "[ROLE: 9] Implement and commit if tests pass"
codex exec "[ROLE: 21] Review and approve for merge"
```

❌ **Không ghi artifact**
```powershell
# SAI
opencode run "[ROLE: 9] Implement RiskGuard" # không chỉ rõ output path
```

❌ **Ly không verify artifact trước khi spawn L3**
```powershell
# SAI
exec("opencode run '...'")
exec("codex exec '...'")  # chạy liền không check L2 output
```

---

## Checklist trước khi chạy CLI

### L2 Implementation
- [ ] Role tag: `[ROLE: 9 - Backend Engineer]`
- [ ] Tier tag: `[L2-Impl:*]`
- [ ] Scope: file paths rõ ràng
- [ ] PIT constraint: `Enforce PIT: T-1 lag, no T+0 joins.`
- [ ] Output: code + test + pytest result
- [ ] Rule: `Implementation only. No audit. No verdict. Terminate after artifact write.`

### L3 Audit
- [ ] Role tag: Single role only - `[ROLE: 20 - Compliance Officer]` OR `[ROLE: 21 - Code Reviewer]` OR `[ROLE: 25 - IT Systems Auditor]`
- [ ] Tier tag: `[L3-Audit:*]`
- [ ] Scope: file paths rõ ràng
- [ ] Check criteria: liệt kê đầy đủ
- [ ] Run: `pytest ... -v`
- [ ] Output: audit report `.md` + log `.jsonl` + verdict
- [ ] Rule: `Audit only. No implementation. No fixes. Terminate after artifact write.`

### Ly Gate
- [ ] Verify ALL 3 L2 artifacts exist:
  - [ ] Code file (read file)
  - [ ] Test file (read file)
  - [ ] Test result (exec pytest -v)
- [ ] Verify L3 verdict artifact exist (read file)
- [ ] Parse verdict: `[APPROVED]` hoặc `[NEEDS_FIX]`
- [ ] Gate decision: commit nếu approved, loop nếu needs fix
- [ ] Log gate decision vào `.ly_state/session/phase_gates.json`

---

## Ví dụ đầy đủ (Phase 4 Risk Guard)

### Bước 1: Ly spawn L2
```powershell
exec(
  command: "opencode run '[ROLE: 9 - Backend Engineer] [L2-Impl:RiskGuard] Task: Implement RiskGuard with circuit breaker. Scope: OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py, OMEGA_QUANT/tests/phase4/test_risk_guard.py. Enforce PIT: T-1 lag, no T+0 joins. Output: (1) risk_guard.py, (2) test_risk_guard.py with 8 tests, (3) pytest result. Rule: Implementation only. No audit. No verdict. Terminate after artifact write.'",
  background: true,
  pty: true,
  yieldMs: 5000
)
```

### Bước 2: Ly verify ALL 3 L2 artifacts
```powershell
# (1) Verify code artifact
read("OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py")

# (2) Verify test artifact
read("OMEGA_QUANT/tests/phase4/test_risk_guard.py")

# (3) Verify test result artifact
exec("python -m pytest OMEGA_QUANT/tests/phase4/test_risk_guard.py -v")
```

### Bước 3: Ly spawn L3
```powershell
exec(
  command: "codex exec --full-auto '[ROLE: 20 - Compliance Officer] [L3-Audit:RiskGuard] Task: Audit RiskGuard PIT compliance. Scope: OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py, OMEGA_QUANT/tests/phase4/test_risk_guard.py. Check: (1) T-1 lag enforced, (2) circuit breaker logic correct, (3) vectorized, (4) tests pass. Run: pytest OMEGA_QUANT/tests/phase4/test_risk_guard.py -v. Output: (1) OMEGA_QUANT/docs/RISK_GUARD_AUDIT.md with verdict [APPROVED]/[NEEDS_FIX], (2) .ly_state/logs/risk_guard_audit.jsonl. Rule: Audit only. No implementation. No fixes. Terminate after artifact write.'",
  pty: true
)
```

### Bước 4: Ly đọc verdict
```powershell
read("OMEGA_QUANT/docs/RISK_GUARD_AUDIT.md")
# Parse verdict: [APPROVED] hoặc [NEEDS_FIX]
```

### Bước 5: Ly gate decision
```powershell
# Nếu [APPROVED]
exec("git add OMEGA_QUANT/packages/risk/src/omega/risk/risk_guard.py OMEGA_QUANT/tests/phase4/test_risk_guard.py OMEGA_QUANT/docs/RISK_GUARD_AUDIT.md .ly_state/logs/risk_guard_audit.jsonl")
exec("git commit -m 'feat(risk): RiskGuard implementation and audit [APPROVED]'")
exec("git push origin master")

# Nếu [NEEDS_FIX]
# Loop back to Bước 1 với fresh L2 session
```

---

## Lưu ý quan trọng

1. **Background task cho L2 dài (>30s)**
   - Dùng `background: true` + `yieldMs: 5000`
   - Track qua `process(action: "log", sessionId: "...")`

2. **L3 không cần background**
   - Audit thường nhanh (<2min)
   - Chạy foreground để lấy output trực tiếp

3. **Ly luôn verify artifact trước khi tiếp**
   - Không tin "done" claim từ CLI
   - Phải `read()` file hoặc `exec("test -f ...")` để chắc chắn

4. **Gate decision là quyền duy nhất của Ly**
   - L2/L3 không được tự commit/push
   - Chỉ Ly mới ghi vào `phase_gates.json`

---

**Version:** 1.0  
**Last Updated:** 2026-05-10 20:38 GMT+7
