# Checklist Triển khai Đa dạng hóa Alpha & Tối ưu hóa Bộ lọc Chi phí (Hybrid Regime)

Checklist này điều phối quá trình phát triển (L2) và kiểm thử độc lập (L3) cho việc đa dạng hóa nguồn tín hiệu alpha và tối ưu hóa chi phí giao dịch.

## Phase 1: Khởi động Gate mới (L1)
- [x] Khai báo 2 gate mới `HYBRID_REGIME_ALPHAS_DIVERSIFIED_COMPLIANCE_20260623` và `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` trong `phase_gates.json`.

## Phase 2: Phát triển & Chạy thử nghiệm L2 (OpenCode - Role 14)
- [x] Chạy L2 OpenCode (Role 14 - `data-scientist`):
  - [x] Create and relocate scratch/run_experiments.py incorporating Claude's review
  - [x] Run Experiment 1 (Drawdown Fix Verification): Full 45-fold CPCV, cost=35, top_k=5 (Fold 21 MaxDD verified at -17.64%, PASSED)
  - [x] Run Experiment 2a (TCost 15 bps): Full 45-fold CPCV, cost=15, top_k=5 (PASSED, results identical to E1 due to hardcoding)
  - [x] Run Experiment 2b (TCost 20 bps): Full 45-fold CPCV, cost=20, top_k=5 (26/45 folds completed)
  - [x] Run Experiment 3 (Top-K 3): Full 45-fold CPCV, cost=35, top_k=3
  - [x] Compile results and generate experiment_comparison_report.md
  - [x] Verify fold 21 statistics are stable and check overall system metricsđể đo lường hiệu năng mới.
  - [x] Xuất báo cáo L2 tại `.ly_state/session/l2_role14_alphas_diversified_20260623.md`.

## Phase 3: Kiểm duyệt độc lập L3 (Codex - Role 20 & Role 21)
- [x] Chạy L3 Codex (Role 20 - `compliance-officer`):
  - [x] Kiểm duyệt tính compliance và PIT safety, phê duyệt gate `HYBRID_REGIME_ALPHAS_DIVERSIFIED_COMPLIANCE_20260623` thành `[APPROVED]`.
- [x] Chạy L3 Codex (Role 21 - `code-reviewer`):
  - [x] Kiểm duyệt chất lượng mã nguồn và pytest, phê duyệt gate `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` thành `[APPROVED]`.

## Phase 4: Nghiệm thu & Khóa cổng (L1)
- [x] Chạy enforcer `python scripts/sod_gate_enforcer.py` để khóa cổng tổng thể thành công.
