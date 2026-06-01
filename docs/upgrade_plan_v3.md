# Kế hoạch nâng cấp OMEGA_QUANT v3.0 (SOD & Expert Review)

## 1. Tích hợp Alternative Features vào ML Model
- **Đề xuất (Role 14 - Data Scientist):** Đưa 20 alt features (microstructure, volume divergence, momentum acceleration) vào mô hình ML XGBoost Classifier để tăng IC.
- **Phản bác (Role 21 - Code Reviewer):** Alt features tính trên rolling windows dễ gây look-ahead bias (rò rỉ dữ liệu tương lai).
- **Giải pháp:** Áp dụng bắt buộc bộ lọc `shift(1)` trên toàn bộ nhân tố mới. Viết script kiểm tra đơn điệu thời gian (monotonicity checker).
- **Thực thi:** Tạo file `scripts/train_ml_alt.py`.

## 2. Tối ưu hóa Hyperparameters bằng Optuna
- **Đề xuất (Role 16 - ML Engineer):** Chạy Optuna tìm kiếm không gian tham số tối ưu cho cả mô hình XGBoost và cấu trúc chia CPCV folds.
- **Phản bác (Role 20 - Compliance Officer):** Tự động hóa thay đổi CPCV folds (embargo, purge length) sẽ làm mất tính độc lập giữa các tập train/test, gây overfit chéo.
- **Giải pháp:** Giữ nguyên cấu trúc CPCV (10 folds, combinatorial C(10,2), 20-day purge). Chỉ sử dụng Optuna tối ưu hyperparams của mô hình XGBoost (max_depth, learning_rate, n_estimators).
- **Thực thi:** Tạo file `scripts/tune_optuna_xgboost.py`.

## 3. Tích hợp Execution Router (VWAP/TWAP)
- **Đề xuất (Role 9 - Backend Engineer):** Xây dựng bộ định tuyến lệnh VWAP/TWAP để mô phỏng trượt giá thực tế cho vốn 2B.
- **Phản bác (Role 6 - System Architect):** Sàn VN có luật T+2.5 và biên độ trần sàn (limit-lock). VWAP tiêu chuẩn sẽ bị lỗi khi cổ phiếu mất thanh khoản bên bán/mua.
- **Giải pháp:** Tích hợp kiểm tra limit-lock và giới hạn lệnh tối đa 10% ADV (Average Daily Volume) phiên trước.
- **Thực thi:** Cập nhật `packages/execution/src/omega/execution/order_router.py`.

## 📋 Quy trình kiểm soát SOD L2/L3 2-Step
1. **L2 (OpenCode):** Thực thi code thực tế, chạy test unit đạt 100% green.
2. **L3 (Codex Audit 2-Step):** 
   - Step 1: Gọi Codex CLI phân tích và in kết quả đánh giá (VERDICT/ISSUES) ra STDOUT.
   - Step 2: Ly ghi nhận kết quả và tạo báo cáo gate an toàn.
