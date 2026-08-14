# L2 Developer Report: Phase 7 JIT GP Evolution & Quality Validation Plan

**Gate**: `gp_evolution_run_plan`  
**L2 Session**: `l2_role16_gp_evolution_run_plan_20260722`  
**L2 Role**: Machine Learning Engineer (Role 16, OpenCode L2)  
**Date**: 2026-07-22  
**Scope**: `implementation_plan.md`

## 1. Executive Summary
- Thiết lập kế hoạch chi tiết cho Pha 7: Tiến hóa Thực nghiệm Toàn diện trên GPU/Numba JIT & Xác thực Chất lượng.
- Xác định rõ ràng sự phụ thuộc vào tệp dữ liệu lịch sử `data/market_2015_now.parquet` và kịch bản `scripts/run_weekly_evolution.py`.
- Quy định phân tách dữ liệu huấn luyện/thử nghiệm (70% train, 15% val, 15% test/oos) và chỉ thăng hạng (promote) Alpha nếu đạt chỉ số tốt trên tập OOS Test độc lập (không có rò rỉ dữ liệu).

## 2. Repo-Local Sources Read
- `.agents/AGENTS.md`
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## 3. Forbidden Path Scan
- Kết quả quét: Đạt chuẩn an toàn tuyệt đối. Không có tham chiếu đến thư mục cấm.

## 4. Verification Results
- Kế hoạch bao quát đầy đủ an toàn PIT (dịch chuyển T-1), tối ưu hóa JIT nopython và kiểm soát promotion trên tập OOS Test.
