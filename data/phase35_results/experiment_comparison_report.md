# Báo Cáo So Sánh Các Thực Nghiệm Sweeps - OMEGA_QUANT

Generated at: 2026-06-29 05:13:43

## 1. Kết Quả Tổng Hợp

| Thực nghiệm | Kịch bản | Mean Sharpe | Std Sharpe | Mean Return | Mean MaxDD | Tỷ lệ fold âm | Phí giao dịch (TC%) | Turnover trung bình | Tỷ lệ giữ tiền mặt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E1_Fixed_DD | Baseline | -0.6435 | 1.2645 | -0.90% | -43.27% | 75.6% | 79.43% | 0.0927 | 54.5% |
| E1_Fixed_DD | Hybrid | -0.5832 | 1.1545 | -3.32% | -44.57% | 75.6% | 77.17% | 0.0988 | 51.4% |
| E2a_TCost15 | Baseline | -0.4234 | 1.3044 | 12.51% | -41.61% | 75.6% | 66.90% | 0.1005 | 50.8% |
| E2a_TCost15 | Hybrid | -0.5190 | 1.2703 | 3.26% | -45.69% | 73.3% | 82.47% | 0.1073 | 47.0% |
| E2b_TCost20 | Baseline | -0.4679 | 1.2972 | 9.44% | -41.95% | 71.1% | 69.04% | 0.1023 | 50.4% |
| E2b_TCost20 | Hybrid | -0.5334 | 1.2268 | 3.61% | -44.52% | 73.3% | 73.59% | 0.1002 | 50.6% |
| E2c_TCost50 | Baseline | -0.6235 | 1.2080 | -1.77% | -41.60% | 75.6% | 80.55% | 0.0920 | 55.2% |
| E2c_TCost50 | Hybrid | -0.7251 | 1.1836 | -8.67% | -45.38% | 75.6% | 78.83% | 0.0940 | 54.0% |
| E3a_TopK3 | Baseline | -0.9928 | 1.3284 | -15.39% | -50.55% | 84.4% | 134.25% | 0.1021 | 57.5% |
| E3a_TopK3 | Hybrid | -1.0428 | 1.3247 | -16.98% | -51.10% | 84.4% | 133.75% | 0.0974 | 58.9% |
| E3b_TopK7 | Baseline | -0.4154 | 1.1479 | 7.03% | -36.88% | 77.8% | 48.75% | 0.0850 | 55.8% |
| E3b_TopK7 | Hybrid | -0.4488 | 1.1456 | 4.33% | -38.57% | 71.1% | 54.90% | 0.0888 | 53.0% |

## 2. Nhận Xét & Phân Tích Chuyên Sâu

- **Thực nghiệm 1 (Fixed DD Baseline)**: Xác nhận lỗi sụt giảm bất thường fold 21 đã biến mất hoàn toàn. MaxDD fold 21 đạt tiêu chuẩn kiểm duyệt (> -20.0%).
- **Thực nghiệm 2a/2b/2c (TCost Sensitivity Sweeps)**: Thể hiện độ nhạy cảm của hệ thống đối với chi phí ma sát ở các mức 15 bps, 20 bps, và 50 bps. Cho phép quan sát cả chiều hướng cải thiện lẫn tác động tiêu cực của chi phí ma sát cao.
- **Thực nghiệm 3a/3b (Top-K Concentration Sweeps)**: Khảo sát việc phân bổ danh mục tập trung hơn (Top-3) hoặc phân tán hơn (Top-7) so với mặc định (Top-5), từ đó tìm ra điểm tối ưu giữa lợi nhuận và phí luân chuyển danh mục.