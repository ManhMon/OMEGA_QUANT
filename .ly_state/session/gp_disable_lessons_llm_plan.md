# GP Disable Lessons LLM Plan

## Goal Description

Tối ưu hóa thời gian chạy của `sod_gate_enforcer.py`. Hiện tại, enforcer tự động gọi hàm `extract_lessons()` để phân tích tài liệu qua LLM ở mỗi lần chạy. Việc gọi qua mạng (9router/OpenRouter) làm chậm tiến trình chạy kiểm thử và kiểm tra SoD. Ta sẽ bổ sung cờ bỏ qua cuộc gọi LLM dựa trên biến môi trường `SKIP_LESSON_EXTRACTION=1` hoặc `OMEGA_SKIP_LLM=1`.

## Proposed Changes

### scripts/extract_lessons.py

#### [MODIFY] [extract_lessons.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/extract_lessons.py)

- Thêm kiểm tra biến môi trường ở đầu hàm `_extract_lesson_fields_with_llm()` (dòng 100-110):
  ```python
  if os.getenv("SKIP_LESSON_EXTRACTION") == "1" or os.getenv("OMEGA_SKIP_LLM") == "1":
      print(f"Skipping LLM call for gate {gate} as requested.")
      return {"symptom": "Skipped", "root_cause": "Skipped", "fix_pattern": "Skipped"}
  ```
- Giải pháp này bỏ qua phần gọi mạng chậm chạp mà vẫn giữ nguyên logic xử lý regex/local file của `extract_lessons()`.

## Verification Plan

### Automated Tests
- Chạy biên dịch trực tiếp file thay đổi: `python -m py_compile scripts/extract_lessons.py`.
- Chạy lệnh PowerShell: `$env:SKIP_LESSON_EXTRACTION='1'; python scripts/sod_gate_enforcer.py` để kiểm tra việc nhảy qua cuộc gọi LLM diễn ra lập tức và enforcer hoàn tất nhanh chóng.
