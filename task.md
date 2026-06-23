# Checklist Triển khai Đa dạng hóa Alpha & Tối ưu hóa Bộ lọc Chi phí (Hybrid Regime)

Checklist này điều phối quá trình phát triển (L2) và kiểm thử độc lập (L3) cho việc đa dạng hóa nguồn tín hiệu alpha và tối ưu hóa chi phí giao dịch.

## Phase 1: Khởi động Gate mới (L1)
- [x] Khai báo 2 gate mới `HYBRID_REGIME_ALPHAS_DIVERSIFIED_COMPLIANCE_20260623` và `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` trong `phase_gates.json`.

## Phase 2: Phát triển & Chạy thử nghiệm L2 (OpenCode - Role 14)
- [x] Chạy L2 OpenCode (Role 14 - `data-scientist`):
  - [x] Cấu trúc lại bộ lọc chọn đặc trưng trong `scripts/backtest_hybrid_regime.py` để phân nhóm và áp dụng Quota-based Selection (tối đa 2 alpha tốt nhất mỗi nhóm).
  - [x] Giảm nhẹ tham số cản chi phí giao dịch trong `TCostOverlay` ở kịch bản Hybrid.
  - [x] Chạy lại unit tests để xác minh tính ổn định của mã nguồn.
  - [x] Chạy backtest đầy đủ 45 folds để đo lường hiệu năng mới.
  - [x] Xuất báo cáo L2 tại `.ly_state/session/l2_role14_alphas_diversified_20260623.md`.

## Phase 3: Kiểm duyệt độc lập L3 (Codex - Role 20 & Role 21)
- [x] Chạy L3 Codex (Role 20 - `compliance-officer`):
  - [x] Kiểm duyệt tính compliance và PIT safety, phê duyệt gate `HYBRID_REGIME_ALPHAS_DIVERSIFIED_COMPLIANCE_20260623` thành `[APPROVED]`.
- [x] Chạy L3 Codex (Role 21 - `code-reviewer`):
  - [x] Kiểm duyệt chất lượng mã nguồn và pytest, phê duyệt gate `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` thành `[APPROVED]`.

## Phase 4: Nghiệm thu & Khóa cổng (L1)
- [x] Chạy enforcer `python scripts/sod_gate_enforcer.py` để khóa cổng tổng thể thành công.
